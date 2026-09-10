"""
generate_content/handler.py
AI 콘텐츠 생성 Lambda:
  1. DB에서 user/farm/crop/사진 정보 조회 (seed 데이터 포함)
  2. content_jobs INSERT → job_id 발급
  3. Bedrock Agent invoke_agent 호출 → textPool JSON 생성
  4. S3 template_a 템플릿 4장에 textPool 주입 → filled HTML S3 저장
  5. content_results DB 저장 / job DONE 업데이트
  6. (선택) index.js Puppeteer Lambda 비동기 호출 → PNG 렌더링

입력 (Lambda URL / API GW / 직접 Invoke):
  {
    "userId":         "1",
    "platform":       "INSTAGRAM",     // or "SMARTSTORE"
    "diaryIds":       [11, 9],          // 없으면 최근 일지 자동 조회
    "keywords":       "친환경 재배",     // 선택
    "extraPhotoKeys": ["key1", "key2", "key3", "key4"]
    // 카드 순서대로 1:1 매핑. 1장이면 전체 공유, N장이면 카드 i에 index i 사용.
    // 부족한 인덱스는 [0]으로 폴백, 없으면 일지 사진으로 폴백.
  }

출력:
  {
    "jobId":        42,
    "status":       "DONE",
    "cardHtmlKeys": ["generated/1/42/card1.html", ...],
    "cardUrls":     ["https://cdn.farmily.kr/..."],
    "caption":      "...",
    "hashtags":     ["#딸기", ...],
    "textPool":     { ... }
  }
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import io
import hashlib
import json
import re
import boto3
import psycopg2.extras
from botocore.config import Config
from PIL import Image
from farmily_utils import get_connection, sanitize_text

# ── 환경 변수 ──────────────────────────────────────────────────────────────
REGION          = os.environ.get("AWS_REGION",              "ap-northeast-2")
S3_BUCKET       = os.environ["S3_BUCKET"]
TEMPLATE_PREFIX = os.environ.get("S3_TEMPLATE_PREFIX",      "templates/template_a")
OUTPUT_PREFIX   = os.environ.get("S3_OUTPUT_PREFIX",        "generated")
CLOUDFRONT_URL  = os.environ.get("CLOUDFRONT_URL",          "")
AGENT_ID        = os.environ["BEDROCK_AGENT_ID"]
AGENT_ALIAS_ID  = os.environ["BEDROCK_AGENT_ALIAS_ID"]
RENDER_LAMBDA   = os.environ.get("RENDER_LAMBDA_NAME",      "")

_s3     = boto3.client("s3",                    region_name=REGION)
_agent  = boto3.client("bedrock-agent-runtime", region_name=REGION,
                        config=Config(read_timeout=120, connect_timeout=10))
_lambda = boto3.client("lambda",                region_name=REGION)

CARD_W, CARD_H = 1080, 1440   # 카드 고정 해상도 (CSS background-size: cover 동일 로직)


# ── template_a 카드 정의 (template_mapping.md 기준) ──────────────────────
# template:  S3의 templates/template_a/ 아래 파일명
# map:       HTML {{TOKEN}} → textPool 키  (특수값: __image__, __logo__)
CARDS = [
    {
        "name":     "card1",
        "template": "card1.html",
        "map": {
            "IMAGE_URL": "__image__",
            "TITLE":     "mainTitle",
            "LOGO":      "__logo__",
        },
    },
    {
        "name":     "card2",
        "template": "card2.html",
        "map": {
            "IMAGE_URL": "__image__",
            "TITLE":     "mainTitle",
            "BODY":      "body1",
            "LOGO":      "__logo__",
        },
    },
    {
        "name":     "card3",
        "template": "card3.html",
        "map": {
            "IMAGE_URL":   "__image__",
            "TITLE":       "mainTitle",
            "BODY":        "body1",
            "HIGHLIGHT":   "highlight1",
            "HIGHLIGHT_2": "highlight2",
            "LOGO":        "__logo__",
        },
    },
    {
        "name":     "card4",
        "template": "card4.html",
        "map": {
            "IMAGE_URL": "__image__",
            "TITLE":     "closing",
            "LOGO":      "__logo__",
        },
    },
]


# ─────────────────────────────────────────────────────────────────────────────
def lambda_handler(event, context):
    # ── 입력 파싱 ──────────────────────────────────────────────────────────
    if isinstance(event.get("body"), str):
        body = json.loads(event["body"])
    elif "body" in event:
        body = event["body"] or {}
    else:
        body = event  # 직접 Invoke 또는 테스트

    user_id          = str(body.get("userId", "")).strip()
    platform         = body.get("platform", "INSTAGRAM").upper()
    diary_ids        = [int(x) for x in body.get("diaryIds") or []]
    keywords         = sanitize_text(body.get("keywords", ""))
    extra_photo_keys = body.get("extraPhotoKeys") or []

    if not user_id:
        return _resp(400, {"error": "userId 필수"})

    # 1. DB 컨텍스트 조회
    ctx = _fetch_context(user_id, diary_ids)
    if "error" in ctx:
        return _resp(400, ctx)

    # 2. content_jobs INSERT
    job_id = _create_job(
        user_id, platform, ctx["crop_id"],
        diary_ids, keywords, extra_photo_keys,
    )

    try:
        _update_job(job_id, "ANALYZING", 10)

        # 3. Bedrock Agent 호출
        agent_input = json.dumps({
            "userId":         user_id,
            "platform":       platform.lower(),
            "cropName":       ctx["crop_name"],
            "region":         ctx["region"],
            "farmingMethod":  ctx["farming_method"],
            "diaryIds":       diary_ids,
            "keywords":       keywords,
        }, ensure_ascii=False)

        raw_text = _invoke_agent(job_id, agent_input)
        _update_job(job_id, "GENERATING", 60)

        # 4. JSON 파싱
        parsed = _parse_agent_response(raw_text)

        # 5. content_results 저장 / job DONE (S3 템플릿·이미지 처리 생략)
        caption  = parsed.get("instagramCaption", "")
        hashtags = parsed.get("hashtags", [])
        meta     = {k: v for k, v in parsed.items()
                    if k not in ("instagramCaption", "hashtags")}
        _save_result(job_id, [], caption, hashtags, meta)
        _update_job(job_id, "DONE", 100)

        return _resp(200, {
            "jobId":       job_id,
            "status":      "DONE",
            "caption":     caption,
            "hashtags":    hashtags,
            "textPool":    parsed.get("textPool", {}),
            "angle":       parsed.get("angle", ""),
            "contentType": parsed.get("contentType", ""),
            "reasoning":   parsed.get("reasoning", ""),
        })

    except Exception as exc:
        _fail_job(job_id, str(exc))
        return _resp(500, {"error": str(exc), "jobId": job_id})


# ── DB 헬퍼 ──────────────────────────────────────────────────────────────────
def _fetch_context(user_id: str, diary_ids: list) -> dict:
    """user / farm_profile / 첫 번째 crop / 일지 사진 조회"""
    try:
        with get_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:

                # user + farm_profile
                cur.execute("""
                    SELECT u.id,
                           u.name          AS user_name,
                           fp.farm_name,
                           fp.region,
                           fp.farming_method
                    FROM users u
                    LEFT JOIN farm_profiles fp ON fp.user_id = u.id
                    WHERE u.id = %s AND u.deleted_at IS NULL
                """, (user_id,))
                user = cur.fetchone()
                if not user:
                    return {"error": f"userId {user_id} 없음"}

                # 첫 번째 활성 작물
                cur.execute("""
                    SELECT id, name FROM crops
                    WHERE user_id = %s AND deleted_at IS NULL
                    ORDER BY id LIMIT 1
                """, (user_id,))
                crop = cur.fetchone()

                # 일지 사진 (diaryIds 지정 시 해당 일지, 없으면 최근 일지)
                photo_key = None
                if diary_ids:
                    cur.execute("""
                        SELECT dp.s3_key
                        FROM diary_photos dp
                        WHERE dp.diary_id = ANY(%s)
                        ORDER BY dp.sort_order LIMIT 1
                    """, (diary_ids,))
                else:
                    cur.execute("""
                        SELECT dp.s3_key
                        FROM diary_photos dp
                        JOIN farm_diaries fd ON fd.id = dp.diary_id
                        WHERE fd.user_id = %s AND fd.deleted_at IS NULL
                        ORDER BY fd.diary_date DESC, dp.sort_order LIMIT 1
                    """, (user_id,))
                row = cur.fetchone()
                if row:
                    photo_key = row["s3_key"]

        return {
            "user_name":      user["user_name"] or "",
            "farm_name":      user["farm_name"] or "",
            "region":         user["region"] or "",
            "farming_method": user["farming_method"] or "",
            "crop_id":        crop["id"]   if crop else None,
            "crop_name":      crop["name"] if crop else "작물",
            "diary_photo_key": photo_key,
        }
    except Exception as exc:
        return {"error": str(exc)}


def _create_job(user_id, platform, crop_id, diary_ids, keywords, extra_photo_keys) -> int:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO content_jobs
                  (user_id, platform, crop_id, diary_ids, keywords, extra_photo_keys, status)
                VALUES (%s, %s, %s, %s, %s, %s, 'QUEUED')
                RETURNING id
            """, (
                user_id, platform, crop_id,
                diary_ids       or None,
                keywords        or None,
                extra_photo_keys or None,
            ))
            conn.commit()
            return cur.fetchone()[0]


def _update_job(job_id: int, status: str, pct: int):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE content_jobs
                SET status = %s,
                    progress_pct = %s,
                    done_at = CASE WHEN %s = 'DONE' THEN now() ELSE NULL END
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


def _save_result(job_id, card_keys, caption, hashtags, meta):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO content_results
                  (job_id, card_image_keys, caption, hashtags, meta)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (job_id) DO UPDATE
                  SET card_image_keys = EXCLUDED.card_image_keys,
                      caption         = EXCLUDED.caption,
                      hashtags        = EXCLUDED.hashtags,
                      meta            = EXCLUDED.meta
            """, (
                job_id, card_keys, caption, hashtags,
                json.dumps(meta, ensure_ascii=False),
            ))
            conn.commit()


# ── Bedrock Agent ─────────────────────────────────────────────────────────
def _invoke_agent(job_id: int, input_text: str) -> str:
    """invoke_agent → 전체 응답 텍스트 반환"""
    resp = _agent.invoke_agent(
        agentId      = AGENT_ID,
        agentAliasId = AGENT_ALIAS_ID,
        sessionId    = f"farmily-job-{job_id}",
        inputText    = input_text,
        enableTrace  = True,
    )
    parts = []
    for event in resp["completion"]:
        if "trace" in event:
            t = event["trace"].get("trace", {})
            if "orchestrationTrace" in t:
                ot = t["orchestrationTrace"]
                if "invocationInput" in ot:
                    ii = ot["invocationInput"]
                    print(f"[TRACE] invoking: {ii.get('invocationType')} / {ii.get('actionGroupInvocationInput', {}).get('function', '')}")
                elif "observation" in ot:
                    print(f"[TRACE] observation type: {ot['observation'].get('type')}")
                elif "modelInvocationInput" in ot:
                    print(f"[TRACE] calling Claude model")
        chunk = event.get("chunk", {})
        if "bytes" in chunk:
            parts.append(chunk["bytes"].decode("utf-8"))
    return "".join(parts).strip()


def _fix_json_literals(s: str) -> str:
    """JSON 문자열 내부의 literal 개행·탭을 이스케이프로 변환"""
    result = []
    in_string = False
    escape = False
    for ch in s:
        if escape:
            result.append(ch)
            escape = False
        elif ch == "\\":
            result.append(ch)
            escape = True
        elif ch == '"':
            in_string = not in_string
            result.append(ch)
        elif in_string and ch == "\n":
            result.append("\\n")
        elif in_string and ch == "\r":
            result.append("\\r")
        elif in_string and ch == "\t":
            result.append("\\t")
        else:
            result.append(ch)
    return "".join(result)


def _parse_agent_response(raw: str) -> dict:
    """
    에이전트 응답에서 JSON 블록 추출.
    실패 시 raw 텍스트를 mainTitle / body1 에 넣은 fallback dict 반환.
    """
    m = re.search(r"\{[\s\S]+\}", raw)
    if m:
        candidate = m.group(0)
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass
        # Claude가 문자열 내부에 literal 개행을 넣는 경우 재시도
        try:
            return json.loads(_fix_json_literals(candidate))
        except json.JSONDecodeError:
            pass

    # fallback: 응답 텍스트를 그대로 최소 구조로 감쌈
    summary = raw[:120] if raw else "오늘의 수확 이야기"
    return {
        "platform":    "instagram",
        "contentType": "공감형",
        "angle":       "수확 현장",
        "textPool": {
            "mainTitle":  summary[:40],
            "subTitle":   "",
            "body1":      raw[:200] if raw else "",
            "body2":      "",
            "highlight1": "",
            "highlight2": "",
            "closing":    summary[:40],
        },
        "instagramCaption": raw,
        "hashtags":    [],
        "reasoning":   "JSON 파싱 실패 — fallback",
    }


# ── 이미지 리사이즈 ───────────────────────────────────────────────────────
def _resize_image(data: bytes) -> bytes:
    """
    원본 이미지를 CARD_W × CARD_H 로 cover 크롭 (CSS background-size:cover 동일).
    scale = max(target_w/src_w, target_h/src_h) → 짧은 쪽 기준 확대 후 중앙 크롭.
    """
    with Image.open(io.BytesIO(data)) as img:
        img = img.convert("RGB")
        src_w, src_h = img.size
        scale = max(CARD_W / src_w, CARD_H / src_h)
        new_w = int(src_w * scale)
        new_h = int(src_h * scale)
        img = img.resize((new_w, new_h), Image.LANCZOS)
        left = (new_w - CARD_W) // 2
        top  = (new_h - CARD_H) // 2
        img  = img.crop((left, top, left + CARD_W, top + CARD_H))
        buf  = io.BytesIO()
        img.save(buf, format="JPEG", quality=88, optimize=True)
        return buf.getvalue()


def _resize_and_upload(src_key: str, job_id, user_id) -> str:
    """
    S3 원본 다운로드 → 리사이즈 → resized/{userId}/{jobId}/{hash8}.jpg 저장.
    같은 src_key는 hash가 동일하므로 동일 job 내 중복 업로드 방지.
    반환: CDN URL
    """
    data = _s3.get_object(Bucket=S3_BUCKET, Key=src_key)["Body"].read()
    resized = _resize_image(data)
    name_hash = hashlib.md5(src_key.encode()).hexdigest()[:8]
    dst_key   = f"resized/{user_id}/{job_id}/{name_hash}.jpg"
    _s3.put_object(
        Bucket      = S3_BUCKET,
        Key         = dst_key,
        Body        = resized,
        ContentType = "image/jpeg",
    )
    return _cdn(dst_key)


# ── 템플릿 처리 ───────────────────────────────────────────────────────────
def _fill_and_upload(
    job_id, user_id, parsed: dict,
    logo: str,
    diary_photo_key: str | None,
    extra_photo_keys: list,
) -> list:
    """
    4장 템플릿을 S3에서 읽고, textPool 값으로 {{TOKEN}} 치환 후 저장.
    카드별 이미지: extraPhotoKeys[i] → extraPhotoKeys[0] → diary_photo_key 폴백.
    S3 키 이미지는 1080×1440 cover 리사이즈 후 저장. 동일 소스는 캐시 재사용.
    반환: 저장된 HTML S3 key 목록 (순서 = CARDS 순)
    """
    text_pool   = parsed.get("textPool", parsed)
    saved_keys  = []
    resize_cache: dict[str, str] = {}   # src_key → CDN URL (job 내 중복 방지)

    for i, card in enumerate(CARDS):
        # 카드별 원본 이미지 키 결정
        raw_key = _pick_image_key(diary_photo_key, extra_photo_keys, i)

        # 이미지 URL 결정 (S3 키면 리사이즈, http URL이면 그대로)
        if raw_key and not raw_key.startswith("http"):
            if raw_key not in resize_cache:
                resize_cache[raw_key] = _resize_and_upload(raw_key, job_id, user_id)
            image_url = resize_cache[raw_key]
        else:
            image_url = raw_key or ""

        # 템플릿 HTML 로드
        tpl_s3_key = f"{TEMPLATE_PREFIX}/{card['template']}"
        html = _s3.get_object(
            Bucket=S3_BUCKET, Key=tpl_s3_key
        )["Body"].read().decode("utf-8")

        # 토큰 → 실제 값 치환
        for token, pool_key in card["map"].items():
            if pool_key == "__logo__":
                value = logo
            elif pool_key == "__image__":
                value = image_url
            else:
                value = text_pool.get(pool_key, "")
            html = html.replace(f"{{{{{token}}}}}", str(value))

        # S3 저장: generated/{user_id}/{job_id}/{card_name}.html
        out_key = f"{OUTPUT_PREFIX}/{user_id}/{job_id}/{card['name']}.html"
        _s3.put_object(
            Bucket      = S3_BUCKET,
            Key         = out_key,
            Body        = html.encode("utf-8"),
            ContentType = "text/html; charset=utf-8",
        )
        saved_keys.append(out_key)

    return saved_keys


def _pick_image_key(
    diary_photo_key: str | None,
    extra_photo_keys: list,
    idx: int = 0,
) -> str | None:
    """카드 인덱스에 맞는 원본 이미지 키/URL 반환 (리사이즈 전)."""
    return (
        (extra_photo_keys[idx] if idx < len(extra_photo_keys) else None)
        or (extra_photo_keys[0] if extra_photo_keys else None)
        or diary_photo_key
        or None
    )


def _cdn(s3_key: str) -> str:
    if CLOUDFRONT_URL:
        return f"https://{CLOUDFRONT_URL}/{s3_key}"
    return s3_key


# ── Puppeteer Lambda 호출 ─────────────────────────────────────────────────
def _invoke_renderer(job_id: int, user_id: str, card_html_keys: list):
    """index.js (Puppeteer) Lambda 비동기 호출. 이미지는 filled HTML에 이미 포함됨."""
    _lambda.invoke(
        FunctionName   = RENDER_LAMBDA,
        InvocationType = "Event",
        Payload        = json.dumps({
            "htmlKeys": card_html_keys,
            "userId":   str(user_id),
            "jobId":    str(job_id),
        }).encode("utf-8"),
    )


# ── HTTP 응답 래퍼 ────────────────────────────────────────────────────────
def _resp(status: int, body: dict) -> dict:
    return {
        "statusCode": status,
        "headers":    {"Content-Type": "application/json; charset=utf-8"},
        "body":       json.dumps(body, ensure_ascii=False),
    }
