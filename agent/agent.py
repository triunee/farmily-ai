"""
agent.py  —  Farmily AgentCore 메인 엔트리포인트

아키텍처:
  [클라이언트]
      └→ ECS Fargate 컨테이너 (BedrockAgentCoreApp HTTP 하니스, :8080)
           └→ Strands Agent  (apac.claude-3-5-sonnet-v2)
                ├→ @tool get_diary
                ├→ @tool get_crop_info
                ├→ @tool search_recipe
                ├→ @tool search_local_specialty
                ├→ @tool get_content_history
                └→ @tool search_trend

기존 Lambda 대비 변경점:
  - farmily-generate-content Lambda (오케스트레이터) → @app.entrypoint
  - bedrock-agent-runtime.invoke_agent()            → strands Agent()
  - Action Group Lambda 5개                         → @tool 함수 (tools.py)
  - bedrock-agent-runtime VPC Endpoint              → 불필요 (bedrock-runtime만 사용)
"""
import json
import logging
import os
import random
import re
import time
from concurrent.futures import ThreadPoolExecutor

import boto3
import psycopg2.extras
from opentelemetry import baggage, context as otel_context, trace
from bedrock_agentcore import BedrockAgentCoreApp as BedrockAgentCore
from strands import Agent
from strands.models import BedrockModel

from farmily_utils import get_connection, sanitize_text
from tools import (
    get_diary,
    get_crop_info,
    search_recipe,
    search_local_specialty,
    get_content_history,
    search_trend,
)

# ── 설정 ───────────────────────────────────────────────────────────────────
REGION               = os.environ.get("AWS_REGION", "ap-northeast-2")
MODEL_ID             = os.environ.get("MODEL_ID", "apac.anthropic.claude-3-5-sonnet-20241022-v2:0")
MEMORY_ID            = os.environ.get("AGENTCORE_MEMORY_ID", "")  # 미설정 시 Memory 비활성화
CARD_RENDERER_LAMBDA = os.environ.get("CARD_RENDERER_LAMBDA", "farmily-card-renderer")
GUARDRAIL_ID         = os.environ.get("GUARDRAIL_ID", "")
GUARDRAIL_VERSION    = os.environ.get("GUARDRAIL_VERSION", "1")

_lambda_client = boto3.client("lambda", region_name=REGION)
_cw_client     = boto3.client("cloudwatch", region_name=REGION)

logging.basicConfig(level=logging.INFO, format="%(message)s")
_logger = logging.getLogger("farmily.agentcore")

def _log(level: str, event: str, **fields):
    _logger.info(json.dumps({
        "level": level,
        "event": event,
        "ts":    time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        **fields,
    }, ensure_ascii=False))

def _emit(metric: str, value: float, unit: str = "Count", dims: list = None):
    try:
        _cw_client.put_metric_data(
            Namespace="Farmily/AgentCore",
            MetricData=[{
                "MetricName": metric,
                "Value":      value,
                "Unit":       unit,
                "Dimensions": dims or [],
            }],
        )
    except Exception:
        pass  # 메트릭 발행 실패가 메인 흐름을 막지 않도록

_PROMPTS_DIR = os.path.join(os.path.dirname(__file__), "prompts")

def _load_system_prompt() -> str:
    base = open(os.path.join(_PROMPTS_DIR, "base_instruction.txt"), encoding="utf-8").read()
    angles_dir = os.path.join(_PROMPTS_DIR, "angles")
    angle_guides = "\n\n".join(
        open(os.path.join(angles_dir, f), encoding="utf-8").read()
        for f in sorted(os.listdir(angles_dir))
        if f.endswith(".txt")
    )
    return base + "\n\n## PART 3-1. 각도별 textPool 가이드\n\n" + angle_guides

SYSTEM_PROMPT = _load_system_prompt()

# OTel 트레이서 — job 루트 span 생성용 (prefetch·agent·렌더러를 한 trace로 묶기 위함)
_tracer = trace.get_tracer("farmily-agentcore")

# BedrockModel 클라이언트는 컨테이너 기동 시 1회만 생성.
# 프롬프트 캐싱(cache_prompt)은 제거했다 — Guardrail과 동시 사용 불가이고
# (함께 보내면 ConverseStream이 AccessDenied로 거부), 저트래픽(5분 TTL 잦은 만료)에선
# 캐싱 이득이 미미해 가드레일 안전성을 우선한다. 고빈도 배치 생성이 생기면 재검토.
_model_kwargs = dict(model_id=MODEL_ID, region_name=REGION)
if GUARDRAIL_ID:
    _model_kwargs.update(
        guardrail_id=GUARDRAIL_ID,
        guardrail_version=GUARDRAIL_VERSION,
        guardrail_trace="enabled",
    )
_model = BedrockModel(**_model_kwargs)

app = BedrockAgentCore()

# 조건부 도구(각도 결정 후 호출)만 LLM에 노출.
# 결정적 도구 4개(get_diary/get_crop_info/get_content_history/search_trend)는
# _prefetch_tool_data로 핸들러에서 병렬 사전조회 → LLM 왕복 제거.
_TOOLS = [search_recipe, search_local_specialty]


def _make_session_manager(user_id: str, job_id: int):
    """AGENTCORE_MEMORY_ID 설정 시 Memory 세션 매니저 반환, 미설정 시 None."""
    if not MEMORY_ID:
        return None
    from bedrock_agentcore.memory.integrations.strands.config import (
        AgentCoreMemoryConfig, RetrievalConfig,
    )
    from bedrock_agentcore.memory.integrations.strands.session_manager import (
        AgentCoreMemorySessionManager,
    )
    return AgentCoreMemorySessionManager(
        agentcore_memory_config=AgentCoreMemoryConfig(
            memory_id        = MEMORY_ID,
            session_id       = f"job-{job_id}",
            actor_id         = user_id,
            retrieval_config = {
                "/preferences/{actorId}": RetrievalConfig(top_k=5,  relevance_score=0.6),
                "/facts/{actorId}":       RetrievalConfig(top_k=10, relevance_score=0.3),
                # 리포트 Lambda(별도)가 재생성 이력을 종합해 쓰는 고차 인사이트.
                # 아직 아무도 안 쓰면 조회 결과가 항상 빈 배열이라 안전(에러 없음).
                "/insights/{actorId}":    RetrievalConfig(top_k=3,  relevance_score=0.5),
            },
        ),
        region_name=REGION,
    )


# ── AgentCore 엔트리포인트 ─────────────────────────────────────────────────
@app.entrypoint
def handler(payload, context):
    # 1. 입력 파싱
    if isinstance(payload.get("body"), str):
        body = json.loads(payload["body"])
    elif "body" in payload:
        body = payload["body"] or {}
    else:
        body = payload

    user_id       = str(body.get("userId", "")).strip()
    platform      = body.get("platform", "INSTAGRAM").upper()
    diary_ids     = [int(x) for x in body.get("diaryIds") or []]
    keywords      = sanitize_text(body.get("keywords", ""))
    photo_s3_keys = body.get("photoS3Keys") or []
    job_id        = int(body.get("jobId", 0))

    if not user_id:
        return {"error": "userId 필수"}
    if not job_id:
        return {"error": "jobId 필수"}

    _log("INFO", "request_received",
         user_id=user_id, platform=platform, diary_count=len(diary_ids), job_id=job_id)

    # OTel baggage에 session.id=job_id 주입 → GenAI Observability에서 job 단위로 trace 상관
    _otel_token = otel_context.attach(baggage.set_baggage("session.id", f"job-{job_id}"))
    # job 루트 span 시작 → 이후 _fetch_context·prefetch·agent()·card-renderer 호출이
    # 모두 이 span 아래로 묶여 한 trace 트리가 된다(흩어진 고아 span 방지)
    _job_span = _tracer.start_span("agentcore.job")
    _job_span.set_attribute("job.id", job_id)
    _job_span.set_attribute("platform", platform)
    _span_token = otel_context.attach(trace.set_span_in_context(_job_span))

    # 2. DB 컨텍스트 조회 (crop_id, crop_name, region 등)
    ctx = _fetch_context(user_id, diary_ids)
    if "error" in ctx:
        otel_context.detach(_span_token)
        _job_span.end()
        otel_context.detach(_otel_token)
        return ctx

    # 3. 백엔드 job_id 사용 (agentcore 자체 job 생성 없음)
    _update_job(job_id, "ANALYZING", 10)

    try:
        # 4. Strands Agent 호출
        #    요청마다 새 Agent 인스턴스 → 대화 히스토리 격리
        #    AGENTCORE_MEMORY_ID 설정 시 Memory 자동 연동
        agent_kwargs = dict(model=_model, tools=_TOOLS, system_prompt=SYSTEM_PROMPT)
        session_mgr  = _make_session_manager(user_id, job_id)
        if session_mgr:
            agent_kwargs["session_manager"] = session_mgr
        agent = Agent(**agent_kwargs)

        _update_job(job_id, "ENRICHING", 30)
        _log("INFO", "agent_start", job_id=job_id, crop_name=ctx["crop_name"], platform=platform)
        _agent_start = time.time()

        # 결정적 도구 4개를 병렬 사전조회해 주입 → LLM이 STEP 1~2를 도구로 돌 필요 없음
        prefetched = _prefetch_tool_data(user_id, diary_ids, ctx["crop_name"])

        # STEP 3-1(비율 규칙)을 코드로 미리 계산해 후보만 LLM에 전달
        # → 프롬프트는 STEP 3-2/3-3(Memory·트렌드 해석)에만 집중
        angle_decision = _decide_angle_candidates(platform.lower(), prefetched.get("contentHistory") or {})

        agent_input = json.dumps({
            "userId":        user_id,
            "platform":      platform.lower(),
            "cropName":      ctx["crop_name"],
            "region":        ctx["region"],
            "farmingMethod": ctx["farming_method"],
            "handle":        ctx["handle"],
            "diaryIds":      diary_ids,
            "keywords":      keywords,
            "prefetched":    prefetched,
            "angleDecision": angle_decision,
        }, ensure_ascii=False)

        response = agent(agent_input)
        raw_text = str(response)
        elapsed_ms = int((time.time() - _agent_start) * 1000)
        _update_job(job_id, "GENERATING", 60)

        # 5. JSON 파싱
        parsed = _parse_response(raw_text)
        if parsed.get("reasoning") == "JSON 파싱 실패 — fallback":
            raise ValueError(f"응답 파싱 실패. raw={raw_text[:200]}")

        usage = response.metrics.accumulated_usage
        input_tokens  = usage.get("inputTokens", 0)
        output_tokens = usage.get("outputTokens", 0)

        _log("INFO", "agent_done",
             job_id=job_id, elapsed_ms=elapsed_ms,
             input_tokens=input_tokens, output_tokens=output_tokens,
             angle=parsed.get("angle"), content_type=parsed.get("contentType"))
        _emit("AgentResponseTime", elapsed_ms, unit="Milliseconds",
              dims=[{"Name": "Platform", "Value": platform}])
        _emit("InputTokensPerJob",  input_tokens,  unit="Count",
              dims=[{"Name": "Platform", "Value": platform}])
        _emit("OutputTokensPerJob", output_tokens, unit="Count",
              dims=[{"Name": "Platform", "Value": platform}])
        _emit("ContentJobDone", 1,
              dims=[{"Name": "Platform", "Value": platform}])

        # 6. DB 저장
        caption  = parsed.get("instagramCaption", "")
        hashtags = parsed.get("hashtags", [])
        cards    = parsed.get("textPool", {})
        meta     = {k: v for k, v in parsed.items()
                    if k not in ("instagramCaption", "hashtags")}
        _save_result(job_id, caption, hashtags, meta)
        _update_job(job_id, "GENERATING", 70)

        # 7. farmily-card-renderer 동기 호출 → 카드 키 획득 후 DB 업데이트
        template_type = 'smartstore' if platform == "SMARTSTORE" \
            else random.choice(['template_a', 'template_b', 'template_c'])
        card_keys = []
        try:
            card_keys = _invoke_card_renderer(job_id, user_id, cards, photo_s3_keys, template_type)
            _update_card_image_keys(job_id, card_keys)
        except Exception as render_exc:
            print(f"[WARN] card-renderer 호출 실패 (job_id={job_id}): {render_exc}")
        _update_job(job_id, "DONE", 100)

        return {
            "jobId":        job_id,
            "status":       "DONE",
            "caption":      caption,
            "hashtags":     hashtags,
            "textPool":     cards,
            "angle":        parsed.get("angle", ""),
            "contentType":  parsed.get("contentType", ""),
            "reasoning":    parsed.get("reasoning", ""),
            "cardImageKeys": card_keys,
        }

    except Exception as exc:
        _log("ERROR", "job_failed", job_id=job_id, user_id=user_id, error=str(exc))
        _emit("ContentJobFailed", 1,
              dims=[{"Name": "Platform", "Value": platform}])
        _fail_job(job_id, str(exc))
        return {"error": str(exc), "jobId": job_id}

    finally:
        otel_context.detach(_span_token)
        _job_span.end()
        otel_context.detach(_otel_token)


# ── DB 헬퍼 ───────────────────────────────────────────────────────────────
def _fetch_context(user_id: str, diary_ids: list) -> dict:
    try:
        with get_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""
                    SELECT u.id,
                           u.handle,
                           fp.region,
                           fp.farming_method
                    FROM users u
                    LEFT JOIN farm_profiles fp ON fp.user_id = u.id
                    WHERE u.id = %s AND u.deleted_at IS NULL
                """, (user_id,))
                user = cur.fetchone()
                if not user:
                    return {"error": f"userId {user_id} 없음"}

                if diary_ids:
                    cur.execute("""
                        SELECT c.id, c.name FROM crops c
                        JOIN farm_diaries fd ON fd.crop_id = c.id
                        WHERE fd.id = ANY(%s) AND fd.user_id = %s
                          AND fd.deleted_at IS NULL AND c.deleted_at IS NULL
                        LIMIT 1
                    """, (diary_ids, user_id))
                else:
                    cur.execute("""
                        SELECT id, name FROM crops
                        WHERE user_id = %s AND deleted_at IS NULL
                        ORDER BY id LIMIT 1
                    """, (user_id,))
                crop = cur.fetchone()

        handle_raw = user["handle"] or ""
        handle = f"@{handle_raw}" if handle_raw and not handle_raw.startswith("@") else handle_raw

        return {
            "region":         user["region"] or "",
            "farming_method": user["farming_method"] or "",
            "handle":         handle,
            "crop_id":        crop["id"]   if crop else None,
            "crop_name":      crop["name"] if crop else "작물",
        }
    except Exception as exc:
        return {"error": str(exc)}



def _prefetch_tool_data(user_id: str, diary_ids: list, crop_name: str) -> dict:
    """STEP 1~2의 결정적 도구 4개를 병렬 사전조회 → LLM 왕복 제거.

    각 @tool 함수를 그대로 재사용하므로 반환 형식은 도구 직접 호출과 동일하다.
    개별 조회 실패는 {"error": ...}로 격리되어 전체 흐름을 막지 않는다.
    """
    # prefetch 묶음 span + 워커 스레드로 현재 OTel 컨텍스트 전파.
    # 컨텍스트는 스레드 경계를 자동 전파하지 않아, 안 하면 도구 내부 boto3/임베딩 span이
    # 부모 없는 고아 span이 된다. 부모(job 루트)를 워커에 attach해 한 트리로 묶는다.
    with _tracer.start_as_current_span("prefetch_tools"):
        _parent_ctx = otel_context.get_current()

        def _run(fn, *args):
            _tok = otel_context.attach(_parent_ctx)
            try:
                return fn(*args)
            finally:
                otel_context.detach(_tok)

        with ThreadPoolExecutor(max_workers=4) as ex:
            if diary_ids:
                diary_futures = [ex.submit(_run, get_diary, user_id, str(d)) for d in diary_ids]
            else:
                diary_futures = [ex.submit(_run, get_diary, user_id, "")]
            f_crop    = ex.submit(_run, get_crop_info, crop_name)
            f_history = ex.submit(_run, get_content_history, user_id, crop_name)
            f_trend   = ex.submit(_run, search_trend, crop_name)

            def _load(fut):
                try:
                    return json.loads(fut.result())
                except Exception as exc:
                    return {"error": str(exc)}

            return {
                "diaries":        [_load(f) for f in diary_futures],
                "cropInfo":       _load(f_crop),
                "contentHistory": _load(f_history),
                "trend":          _load(f_trend),
            }


# 각도 문자열 → 콘텐츠 유형 (prompts/angles/*.txt 첫 줄과 동기화)
_ANGLE_TYPE_MAP = {
    "레시피":     "정보형", "보관법": "정보형", "영양": "정보형", "제철 강조": "정보형",
    "수확 현장":  "공감형", "스토리텔링": "공감형",
    "지역 강조":  "신뢰형",
    "구매 유도":  "판매형",
}
_TYPE_ANGLES = {
    "정보형": ["레시피", "보관법", "영양", "제철 강조"],
    "공감형": ["수확 현장", "스토리텔링"],
    "신뢰형": ["지역 강조"],
    "판매형": ["구매 유도"],
}


# 콘텐츠 유형별 목표 비율 — 정보형40 / 공감형30 / 신뢰형20 / 판매형10
_TARGET_RATIO = {"정보형": 0.40, "공감형": 0.30, "신뢰형": 0.20, "판매형": 0.10}


def _decide_angle_candidates(platform: str, content_history: dict) -> dict:
    """usedAngles 목표 비율(STEP 3-1)을 결정론적으로 계산해 후보를 좁힌다.
    STEP 3-2(Memory 선호도)·3-3(트렌드)의 의미적 판단은 LLM에 그대로 남긴다
    — 자연어 해석이 필요한 부분까지 코드로 옮기면 억지 결정론이 되므로 제외.

    절대건수 임계값(정보형<4 등) 대신 목표비율 대비 부족분(deficit)을 계산한다.
    절대건수는 이력이 쌓일수록 조건이 항상 거짓이 되어 규칙이 무력화되지만,
    비율은 이력 규모와 무관하게 항상 유효하게 목표를 유지한다.
    """
    if platform == "smartstore":
        return {"fixedAngle": "smartstore_detail", "candidates": [], "excludeSale": False}

    history = content_history.get("history") or [] if isinstance(content_history, dict) else []
    total = len(history)

    type_counts = {"정보형": 0, "공감형": 0, "신뢰형": 0, "판매형": 0}
    for h in history:
        t = _ANGLE_TYPE_MAP.get(h.get("angle", ""))
        if t:
            type_counts[t] += 1

    # 판매형 연속 2회는 비율과 별개의 하드 규칙(반복 스팸 방지)
    recent_two = [h.get("angle", "") for h in history[:2]]
    exclude_sale = len(recent_two) >= 2 and all(_ANGLE_TYPE_MAP.get(a) == "판매형" for a in recent_two)

    # 목표비율 대비 부족분이 큰(목표에 못 미치는) 유형부터 후보로 제시.
    # 이력 0건(신규 유저)이어도 division-by-zero 없이 목표비율이 큰 순으로 자연스럽게 정렬됨.
    deficits = []
    for t, target in _TARGET_RATIO.items():
        if t == "판매형" and exclude_sale:
            continue
        actual = (type_counts[t] / total) if total else 0.0
        deficits.append((target - actual, t))
    deficits.sort(key=lambda x: -x[0])

    candidates = [
        {"contentType": t, "angles": _TYPE_ANGLES[t], "targetRatio": _TARGET_RATIO[t], "deficit": round(d, 3)}
        for d, t in deficits
    ]

    return {"fixedAngle": None, "candidates": candidates, "excludeSale": exclude_sale}


def _update_job(job_id: int, status: str, pct: int):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE content_jobs
                SET status = %s,
                    progress_pct = %s,
                    done_at = CASE WHEN %s = 'DONE' THEN now() ELSE done_at END
                WHERE id = %s
            """, (status, pct, status, job_id))
            conn.commit()


def _fail_job(job_id: int, reason: str):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE content_jobs
                SET status = 'FAILED', failure_reason = %s
                WHERE id = %s
            """, (reason[:500], job_id))
            conn.commit()


def _save_result(job_id, caption, hashtags, meta):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO content_results
                  (job_id, card_image_keys, caption, hashtags, meta)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (job_id) DO UPDATE
                  SET caption  = EXCLUDED.caption,
                      hashtags = EXCLUDED.hashtags,
                      meta     = EXCLUDED.meta
            """, (job_id, [], caption, hashtags,
                  json.dumps(meta, ensure_ascii=False)))
            conn.commit()


def _update_card_image_keys(job_id: int, keys: list):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE content_results
                SET card_image_keys = %s
                WHERE job_id = %s
            """, (keys, job_id))
            conn.commit()


# ── 응답 파싱 ──────────────────────────────────────────────────────────────
def _fix_json_literals(s: str) -> str:
    result, in_string, escape = [], False, False
    for ch in s:
        if escape:
            result.append(ch); escape = False
        elif ch == "\\":
            result.append(ch); escape = True
        elif ch == '"':
            in_string = not in_string; result.append(ch)
        elif in_string and ch == "\n":
            result.append("\\n")
        elif in_string and ch == "\r":
            result.append("\\r")
        elif in_string and ch == "\t":
            result.append("\\t")
        else:
            result.append(ch)
    return "".join(result)

def _parse_response(raw: str) -> dict:
    m = re.search(r"\{[\s\S]+\}", raw)
    if m:
        candidate = m.group(0)
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass
        try:
            return json.loads(_fix_json_literals(candidate))
        except json.JSONDecodeError:
            pass
    return {"reasoning": "JSON 파싱 실패 — fallback", "instagramCaption": raw}


# ── Lambda 호출 헬퍼 ──────────────────────────────────────────────────────
def _invoke_card_renderer(job_id: int, user_id: str, text_pool: dict, photo_s3_keys: list,
                          template_type: str = "template_b") -> list:
    """카드 렌더링 Lambda 동기 호출 → 생성된 카드 S3 키 목록 반환."""
    if not photo_s3_keys:
        return []
    payload = json.dumps({
        "textPool":     text_pool,
        "templateType": template_type,
        "userId":       user_id,
        "jobId":        str(job_id),
        "photoS3Keys":  photo_s3_keys,
    })
    resp = _lambda_client.invoke(
        FunctionName   = CARD_RENDERER_LAMBDA,
        InvocationType = "RequestResponse",
        Payload        = payload.encode(),
    )
    result = json.loads(resp["Payload"].read())
    body = json.loads(result.get("body", "{}")) if isinstance(result.get("body"), str) else result
    return body.get("keys", [])




if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
