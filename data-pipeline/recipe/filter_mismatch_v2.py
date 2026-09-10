"""
재료-작물 미매칭 필터 v2
- backup964(이미 매칭된 것) + recovered_dropped(복구본) = 전체 1069
- 매칭 기준:
    (1) 작물명이 재료에 포함 (띄어쓰기 무시)  ex) 상황버섯 ↔ "상황 버섯"
    (2) 별칭/허용변형 매핑에 해당하는 단어가 재료에 포함
        ex) 감귤→귤, 청포도→포도, 서리태→검은콩, 마늘종→마늘쫑(오타)
- 미매칭(작물과 무관한 레시피)은 삭제하고 별도 파일로 목록 기록
    ex) 기장→소고기장조림, 살구→삼겹살구이, 무→콩나물무침
"""
import json, re
from collections import defaultdict

BACKUP   = "raw_10000recipe.backup964.json"
RECOVER  = "recovered_dropped.json"
OUT_JSON = "raw_10000recipe.json"
MISMATCH_TXT  = "mismatch_recipes.txt"
MISMATCH_JSON = "mismatch_recipes.json"

# 작물명 → 재료에 등장하면 '매칭'으로 인정할 별칭/허용변형 목록
ALIAS_MAP = {
    "감귤":      ["귤"],
    "마늘종":    ["마늘쫑", "마늘쪽"],
    "샐러리":    ["셀러리"],
    "솔부추":    ["영양부추", "부추"],
    "서리태":    ["검은콩", "검정콩", "흑태"],
    "백태":      ["흰콩", "메주콩", "콩"],
    "적채":      ["적양배추", "자색양배추"],
    "강낭콩":    ["강남콩", "흰강낭콩", "흰강남콩"],
    "방풍나물":  ["방풍", "방풀나물"],
    "고추냉이":  ["와사비"],
    "얼갈이배추": ["얼갈이"],
    "유채나물":  ["유채"],
    "시금치":    ["섬초", "포항초"],
    "들깨":      ["들깻가루", "들깨가루"],
    "숙주나물":  ["숙주"],
    "완두콩":    ["완두"],
    "방울양배추": ["미니양배추", "다다기양배추", "방울다다기"],
    "애플망고":  ["망고"],
    "포도":      ["청포도", "거봉", "샤인머스캣"],   # 허용 변형
    "산딸기":    ["딸기"],                          # 허용 변형
    "총각무":    ["알타리무", "알타리", "총각김치"],
    "느타리버섯": ["느타리"],
    "새송이버섯": ["새송이"],
    "양송이버섯": ["양송이"],
    "노루궁뎅이버섯": ["노루궁뎅이"],
    "가지버섯":  ["가지"],                          # 검색 합성어 → 가지요리
    "참깨":      ["통깨", "흰깨", "깨소금"],
    "깻잎":      ["깨순", "깻순"],
    "고구마순":  ["고구마줄기", "고구마대", "고구마 순"],
    "인삼":      ["수삼", "홍삼"],
}

# 재료엔 작물명이 없지만 레시피명 자체가 그 작물 요리인 경우 → 유지 (이름 기준)
# (단순 부분일치로는 '삼겹살구이⊃살구' 같은 오매칭이 살아나므로 직접 검토해 선별)
KEEP_OVERRIDE = {
    ("미나리", "미나리김밥"),
    ("상추", "상추튀김"),
    ("아로니아", "아로니아밥"),
    ("앵두", "앵두잼"),
    ("야콘", "야콘떡만두국"),
    ("체리", "체리타르트"),
    ("인삼", "인삼차"),
    ("인삼", "인삼떡갈비"),
    ("포도", "청포도타르트"),
    ("아스파라거스", "아스파라거스샐러드"),
    ("감귤", "양상추감귤샐러드"),
    ("파프리카", "파프리카잡채"),
    ("강황", "계란강황볶음밥"),
}


def norm(s: str) -> str:
    """공백 제거"""
    return re.sub(r"\s+", "", s)


def is_match(crop: str, ingredients: list) -> bool:
    crop = crop.strip()
    ing_norm = norm(" ".join(ingredients))
    # (1) 작물명 직접 포함 (띄어쓰기 무시)
    if norm(crop) in ing_norm:
        return True
    # (2) 별칭/허용변형
    for alias in ALIAS_MAP.get(crop, []):
        if norm(alias) in ing_norm:
            return True
    return False


def main():
    with open(BACKUP, encoding="utf-8") as f:
        kept_already = json.load(f)
    with open(RECOVER, encoding="utf-8") as f:
        recovered = json.load(f)

    # 전체 합치기 (recipe_id 중복 제거)
    combined = {r["recipe_id"]: r for r in kept_already}
    for r in recovered:
        combined.setdefault(r["recipe_id"], r)
    all_recipes = list(combined.values())

    keep, drop = [], []
    for r in all_recipes:
        crop = r.get("crop_name", "")
        if is_match(crop, r.get("ingredients", [])) or (crop, r.get("tag", "")) in KEEP_OVERRIDE:
            keep.append(r)
        else:
            drop.append(r)

    # ── 결과 저장 ──
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(keep, f, ensure_ascii=False, indent=2)
    with open(MISMATCH_JSON, "w", encoding="utf-8") as f:
        json.dump(drop, f, ensure_ascii=False, indent=2)

    # ── 미매칭 목록 텍스트 ──
    by_crop = defaultdict(list)
    for r in drop:
        by_crop[r["crop_name"]].append(r)

    lines = ["=== 미매칭(삭제) 레시피 목록 ===",
             f"전체 {len(all_recipes)}건  |  유지 {len(keep)}건  |  삭제 {len(drop)}건",
             ""]
    for crop in sorted(by_crop):
        recs = by_crop[crop]
        lines.append(f"[{crop}]  {len(recs)}건")
        for r in recs:
            ing = ", ".join(r["ingredients"][:5])
            lines.append(f"  - {r['recipe_name']}")
            lines.append(f"    태그: {r['tag']}  |  재료: {ing}")
        lines.append("")
    report = "\n".join(lines)
    with open(MISMATCH_TXT, "w", encoding="utf-8") as f:
        f.write(report)

    print(report)
    print(f"→ 유지: {OUT_JSON} ({len(keep)}건)")
    print(f"→ 미매칭 목록: {MISMATCH_TXT} / {MISMATCH_JSON} ({len(drop)}건)")


if __name__ == "__main__":
    main()
