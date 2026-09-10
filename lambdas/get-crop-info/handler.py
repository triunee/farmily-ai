"""
farmily-get-crop-info
제철·작물 정보 조회
input:  { "cropName": "딸기" }
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from farmily_utils import (
    get_connection, parse_params, ok, error, safety_error, is_safe_input
)
import psycopg2.extras
from datetime import date

MONTH_KO = ["", "1월", "2월", "3월", "4월", "5월", "6월",
            "7월", "8월", "9월", "10월", "11월", "12월"]


def lambda_handler(event, context):
    try:
        params    = parse_params(event)
        crop_name = params.get("cropName", "")

        safe, reason = is_safe_input(crop_name)
        if not safe:
            return safety_error(event, reason)

        with get_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""
                    SELECT crop_name, category, harvest_months,
                           origin_region, cooking_method,
                           storage_method, nutrition_brief, effect_brief
                    FROM crop_knowledge
                    WHERE crop_name = %s
                """, (crop_name,))
                row = cur.fetchone()

        if not row:
            return ok(event, {"found": False, "cropName": crop_name})

        harvest_months = row["harvest_months"] or []
        current_month  = date.today().month

        return ok(event, {
            "found":           True,
            "cropName":        row["crop_name"],
            "category":        row["category"] or "",
            "harvestMonths":   harvest_months,
            "harvestMonthsKo": [MONTH_KO[m] for m in harvest_months if 1 <= m <= 12],
            "inSeasonNow":     current_month in harvest_months,
            "originRegion":    row["origin_region"] or "",
            "cookingMethod":   row["cooking_method"] or "",
            "storageMethod":   row["storage_method"] or "",
            "nutritionBrief":  row["nutrition_brief"] or "",
            # effect_brief: 의학적 효능 주장 필터 적용
            "effectBrief":     _filter_health_claims(row["effect_brief"] or ""),
        })

    except Exception as e:
        return error(event, str(e))


def _filter_health_claims(text: str) -> str:
    """
    Canva 정책 준수: DB에 저장된 효능 텍스트 중
    허위 의학적 효능 주장 표현을 완화된 표현으로 교체
    """
    replacements = {
        "암을 예방": "항산화 성분이 풍부",
        "면역력을 강화": "건강한 식생활에 도움",
        "당뇨를 예방": "혈당 관리에 관심 있는 분께 추천",
        "혈압을 낮춰": "나트륨 배출에 도움을 주는 칼륨 함유",
        "치매를 예방": "뇌 건강에 관심 있는 분께 추천",
        "다이어트에 효과": "식이섬유가 풍부",
    }
    for original, replacement in replacements.items():
        text = text.replace(original, replacement)
    return text
