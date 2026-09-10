"""
farmily-select-photo Lambda

영농일지 사진 여러 장 중 카드뉴스에 가장 적합한 1장을 선별하고
1080×1350으로 리사이징하여 S3에 저장한다.

STEP 1: Pillow 사전 필터링 (1080×1350 미만 제외)
STEP 2: Claude 3 Haiku Vision 적합도 평가 (순차)
STEP 3: 최고 score 사진 선정
STEP 4: LANCZOS + 중앙 크롭으로 1080×1350 리사이징
STEP 5: S3 저장 및 반환
"""
import base64
import io
import json
import os

import boto3
from PIL import Image

# ── 설정 ──────────────────────────────────────────────────────────────────
REGION       = os.environ.get("AWS_REGION", "ap-northeast-2")
S3_BUCKET    = os.environ.get("S3_BUCKET", "farmily-s3-bucket")
HAIKU_MODEL  = os.environ.get("HAIKU_MODEL_ID", "apac.anthropic.claude-3-haiku-20240307-v1:0")

TARGET_W, TARGET_H = 1080, 1350

_s3      = boto3.client("s3", region_name=REGION)
_bedrock = boto3.client("bedrock-runtime", region_name=REGION)

_EVAL_PROMPT = """당신은 농산물 카드뉴스 편집자입니다.
아래 사진을 카드뉴스 메인 이미지로 사용할 적합도를 평가하세요.

카드뉴스 구조:
- 사진 위에 반투명 텍스트 박스가 하단에 오버레이됩니다.
- 따라서 상단 영역의 이미지 품질이 특히 중요합니다.

평가 기준:
1. 작물이 화면의 50% 이상 차지하는가
2. 하단 텍스트 박스를 제외한 상단 영역의 이미지 품질
3. 선명도 및 조명 품질
4. 소비자가 보고 싶은 감성적 매력도

1~10점으로 평가하고 반드시 아래 JSON만 출력하세요:
{"score": <int 1~10>, "reason": "<한 문장 이유>"}"""


# ── 핸들러 ────────────────────────────────────────────────────────────────
def lambda_handler(event, context):
    photo_keys = event.get("photo_s3_keys") or []
    user_id    = str(event.get("userId", "")).strip()
    job_id     = str(event.get("jobId", "")).strip()

    if not photo_keys:
        return {"statusCode": 400, "body": "photo_s3_keys 필수"}

    # STEP 1 — Pillow 사전 필터링
    candidates = _filter_by_size(photo_keys)
    if not candidates:
        candidates = [photo_keys[0]]  # 모든 사진 탈락 시 첫 번째 강제 선택

    # STEP 2 & 3 — Claude Vision 평가 → 점수순 전체 순위
    # 카드뉴스는 사진 여러 장을 다 쓰므로, 1장만 뽑지 않고 순위 전체를 돌려준다.
    ranked = _rank_by_score(candidates)  # [(score, key), ...] 점수 내림차순
    best_key = ranked[0][1]

    # STEP 4 — 최상위 사진만 리사이징(대표 이미지 하위호환)
    img_bytes = _download_image(best_key)
    resized   = _center_crop_resize(img_bytes)

    # STEP 5 — S3 저장
    dest_key = f"processed/{user_id}/{job_id}/photo.jpg"
    ranked_out = [{"key": k, "score": s} for s, k in ranked]
    try:
        _s3.put_object(
            Bucket      = S3_BUCKET,
            Key         = dest_key,
            Body        = resized,
            ContentType = "image/jpeg",
        )
    except Exception:
        # S3 업로드 실패 시 원본 키 반환
        return {"best_photo_key": best_key, "ranked": ranked_out}

    return {"best_photo_key": dest_key, "ranked": ranked_out}


# ── STEP 1: Pillow 사전 필터링 ────────────────────────────────────────────
def _filter_by_size(keys: list) -> list:
    passed = []
    for key in keys:
        try:
            data = _download_image(key)
            with Image.open(io.BytesIO(data)) as img:
                w, h = img.size
                if w >= TARGET_W and h >= TARGET_H:
                    passed.append(key)
        except Exception:
            pass  # 손상된 이미지 건너뜀
    return passed


# ── STEP 2 & 3: Claude Vision 평가 ───────────────────────────────────────
def _rank_by_score(keys: list) -> list:
    """모든 후보를 점수순으로 정렬해 반환한다 (카드뉴스가 여러 장을 다 쓰므로
    1장만 고르지 않고 순위 전체를 넘긴다). 반환: [(score, key), ...] 내림차순."""
    scores = []
    for idx, key in enumerate(keys):
        score = _evaluate_with_haiku(key)
        scores.append((score, idx, key))

    # 최고 score, 동점 시 인덱스(업로드 순서) 우선
    scores.sort(key=lambda x: (-x[0], x[1]))
    print(f"[rank] 전체 순위: {[(s, k) for s, _, k in scores]}")
    return [(s, k) for s, _, k in scores]


def _evaluate_with_haiku(key: str) -> int:
    try:
        data = _download_image(key)
        b64  = base64.b64encode(data).decode()

        body = json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 200,
            "messages": [{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type":       "base64",
                            "media_type": _detect_media_type(data),
                            "data":       b64,
                        },
                    },
                    {"type": "text", "text": _EVAL_PROMPT},
                ],
            }],
        })

        resp = _bedrock.invoke_model(
            modelId     = HAIKU_MODEL,
            body        = body,
            contentType = "application/json",
            accept      = "application/json",
        )
        raw = json.loads(resp["body"].read())
        text = raw["content"][0]["text"].strip()

        parsed = json.loads(text)
        score = int(parsed.get("score", 5))
        print(f"[haiku-eval] key={key} score={score} reason={parsed.get('reason','')}")
        return score

    except Exception as exc:
        print(f"[haiku-eval][WARN] key={key} 평가 실패, 기본값(5) 사용: {exc}")
        return 5  # 파싱 실패 시 기본값


def _detect_media_type(data: bytes) -> str:
    if data[:4] == b"\x89PNG":
        return "image/png"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    return "image/jpeg"


# ── STEP 4: 리사이징 ──────────────────────────────────────────────────────
def _center_crop_resize(data: bytes) -> bytes:
    with Image.open(io.BytesIO(data)) as img:
        img = img.convert("RGB")
        src_w, src_h = img.size

        # 목표 비율에 맞게 크롭 영역 계산 (중앙 크롭)
        target_ratio = TARGET_W / TARGET_H
        src_ratio    = src_w / src_h

        if src_ratio > target_ratio:
            # 너비가 상대적으로 넓음 → 좌우 크롭
            crop_w = int(src_h * target_ratio)
            left   = (src_w - crop_w) // 2
            box    = (left, 0, left + crop_w, src_h)
        else:
            # 높이가 상대적으로 높음 → 상하 크롭
            crop_h = int(src_w / target_ratio)
            top    = (src_h - crop_h) // 2
            box    = (0, top, src_w, top + crop_h)

        cropped = img.crop(box)
        resized = cropped.resize((TARGET_W, TARGET_H), Image.LANCZOS)

        buf = io.BytesIO()
        resized.save(buf, format="JPEG", quality=90)
        return buf.getvalue()


# ── S3 다운로드 ───────────────────────────────────────────────────────────
def _download_image(key: str) -> bytes:
    resp = _s3.get_object(Bucket=S3_BUCKET, Key=key)
    return resp["Body"].read()
