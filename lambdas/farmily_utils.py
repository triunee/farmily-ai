"""
farmily_utils.py
공통 유틸리티:
  - DB 연결
  - Bedrock 임베딩
  - Canva 사용 제한 정책 기반 입력값 안전 필터
  - Bedrock Agent 응답 헬퍼
"""
import os
import re
import json
import boto3
import psycopg2
import psycopg2.extras

# ─── DB 연결 ───────────────────────────────────────────────────────────
DB_CONFIG = {
    "host":            os.environ["DB_HOST"],
    "port":            int(os.environ.get("DB_PORT", 5432)),
    "dbname":          os.environ["DB_NAME"],
    "user":            os.environ["DB_USER"],
    "password":        os.environ["DB_PASSWORD"],
    "connect_timeout": 10,  # 연결 실패 시 10초 안에 에러 반환
}

def get_connection():
    return psycopg2.connect(**DB_CONFIG)


# ─── Bedrock 임베딩 ────────────────────────────────────────────────────
REGION  = os.environ.get("AWS_REGION", "ap-northeast-2")
_bedrock = boto3.client("bedrock-runtime", region_name=REGION)

def embed(text: str, dimensions: int = 1024) -> list[float]:
    resp = _bedrock.invoke_model(
        modelId="amazon.titan-embed-text-v2:0",
        body=json.dumps({
            "inputText": text,
            "dimensions": dimensions,
            "normalize": True,
        }),
        contentType="application/json",
        accept="application/json",
    )
    return json.loads(resp["body"].read())["embedding"]


def vec_str(embedding: list[float]) -> str:
    return "[" + ",".join(str(v) for v in embedding) + "]"


# ─── Canva 사용 제한 정책 기반 입력값 안전 필터 ───────────────────────
# Canva Usage Policy 준수:
# - 차별·혐오 표현 금지
# - 폭력·해악 조장 금지
# - 허위·사기성 정보 금지
# - 불법 활동 조장 금지
# - 저작권·상표권 침해 금지

_BLOCKED_PATTERNS = [
    # 혐오·차별 표현
    r"(인종|민족|종교|성별|장애|나이|국적).{0,10}(차별|비하|혐오|모욕)",
    r"(죽여|죽이|폭탄|테러|살인|자살|자해)",

    # 허위 의학적 효능 주장
    r"(암|당뇨|고혈압|치매|코로나|바이러스).{0,10}(치료|예방|완치|억제|박멸)",
    r"(면역력|혈당|혈압).{0,5}(강화|개선|치료|정상화)",

    # 사기·기만
    r"(100%\s*천연|무농약\s*보장|유기농\s*인증(?!받은|획득|보유))",
    r"(특허|인증|허가).{0,5}(받은척|위조|가짜)",

    # 불법·성인
    r"(마약|도박|불법|음란|포르노|성인용)",
]

_COMPILED = [re.compile(p, re.IGNORECASE) for p in _BLOCKED_PATTERNS]

_FORBIDDEN_HEALTH_CLAIMS = [
    "면역력을 강화", "면역력 강화", "암을 예방", "당뇨를 치료",
    "혈압을 낮춰", "다이어트에 효과", "살을 빼", "체중 감량 효과",
    "치매 예방", "노화 방지 효과",
]


def is_safe_input(text: str) -> tuple[bool, str]:
    """
    Canva 정책 위반 여부 검사
    Returns: (is_safe, reason)
    """
    if not text or not text.strip():
        return True, ""

    for pattern in _COMPILED:
        if pattern.search(text):
            return False, f"정책 위반 패턴 감지: {pattern.pattern}"

    for claim in _FORBIDDEN_HEALTH_CLAIMS:
        if claim in text:
            return False, f"허위 의학적 효능 주장 감지: {claim}"

    # 길이 제한 (과도한 입력 방지)
    if len(text) > 500:
        return False, "입력값이 너무 깁니다 (최대 500자)"

    return True, ""


def sanitize_text(text: str) -> str:
    """HTML 태그 및 특수문자 기본 정제"""
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", "", text)           # HTML 태그 제거
    text = re.sub(r"[^\w\s가-힣.,!?()#@\-\n]", "", text)  # 허용 문자 외 제거
    return text.strip()


# ─── Bedrock Agent 응답 헬퍼 ───────────────────────────────────────────
def ok(event: dict, body: dict) -> dict:
    return {
        "messageVersion": "1.0",
        "response": {
            "actionGroup": event.get("actionGroup"),
            "function":    event.get("function"),
            "functionResponse": {
                "responseBody": {
                    "TEXT": {
                        "body": json.dumps(body, ensure_ascii=False)
                    }
                }
            }
        }
    }


def error(event: dict, message: str) -> dict:
    return ok(event, {"error": message})


def safety_error(event: dict, reason: str) -> dict:
    return ok(event, {
        "error": "안전 규칙 위반으로 콘텐츠를 생성할 수 없습니다.",
        "reason": reason,
    })


def parse_params(event: dict) -> dict:
    params = event.get("parameters", [])
    return {p["name"]: p["value"] for p in params}
