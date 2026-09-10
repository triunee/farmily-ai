"""
만개의레시피 테스트 크롤링
==========================
A급(시금치), B급(우엉), C급(솔부추) 각 1개씩 테스트
결과를 raw_test.json 으로 저장

실행:
    pip install requests beautifulsoup4
    python3 crawl_test.py
"""

import requests
from bs4 import BeautifulSoup
import json
import time
import re
from datetime import datetime

# ──────────────────────────────────────────
# 설정
# ──────────────────────────────────────────
OUTPUT_FILE = "raw_test.json"
BASE_URL = "https://www.10000recipe.com"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Referer": "https://www.10000recipe.com/",
}

# 테스트 작물: A급 / B급 / C급 각 1개
TEST_CROPS = [
    {"crop_name": "시금치", "tier": "A", "max_tags": 5},  # A급이지만 테스트라 5개만
    {"crop_name": "우엉",   "tier": "B", "max_tags": 5},
    {"crop_name": "솔부추", "tier": "C", "max_tags": 5},
]


# ──────────────────────────────────────────
# 크롤링 함수
# ──────────────────────────────────────────

def safe_get(url: str) -> requests.Response | None:
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        if res.status_code == 200:
            return res
        print(f"  [WARN] {res.status_code} — {url}")
    except Exception as e:
        print(f"  [ERROR] {e}")
    return None


def crawl_related_tags(crop_name: str) -> list[str]:
    """작물명 검색 → 관련 태그 목록 수집"""
    url = f"{BASE_URL}/recipe/list.html?q={crop_name}&order=reco"
    res = safe_get(url)
    if not res:
        return []

    soup = BeautifulSoup(res.text, "html.parser")
    tag_area = soup.select_one("div.s_category_tag ul.tag_cont")
    if not tag_area:
        print(f"  [WARN] 태그 영역 없음")
        return []

    tags = [a.text.strip() for a in tag_area.select("li a") if a.text.strip()]
    return tags


def crawl_top_recipe(tag: str, crop_name: str) -> dict | None:
    """태그 검색 → 추천순 1위 레시피 수집"""

    # 1) 목록 페이지 — 추천순 1위 레시피 ID 추출
    list_url = f"{BASE_URL}/recipe/list.html?q={tag}&order=reco"
    res = safe_get(list_url)
    if not res:
        return None

    soup = BeautifulSoup(res.text, "html.parser")
    first = soup.select_one(
        "ul.common_sp_list_ul li.common_sp_list_li a.common_sp_link"
    )
    if not first:
        return None

    recipe_path = first.get("href", "")
    if not recipe_path.startswith("/recipe/"):
        return None

    recipe_id = recipe_path.replace("/recipe/", "").strip()
    recipe_url = f"{BASE_URL}/recipe/{recipe_id}"
    time.sleep(0.7)

    # 2) 상세 페이지 파싱
    res2 = safe_get(recipe_url)
    if not res2:
        return None

    soup2 = BeautifulSoup(res2.text, "html.parser")

    # 레시피명
    title_el = soup2.select_one(".view2_summary h3")
    if not title_el:
        return None
    recipe_name = title_el.text.strip()

    # 인분 / 조리시간 / 난이도
    info_els = soup2.select(
        ".view2_summary_info1, .view2_summary_info2, .view2_summary_info3"
    )
    servings   = info_els[0].text.strip() if len(info_els) > 0 else None
    cook_time  = info_els[1].text.strip() if len(info_els) > 1 else None
    difficulty = info_els[2].text.strip() if len(info_els) > 2 else None

    # 재료 목록
    ingredients = []
    for ing in soup2.select(".ingre_list_name"):
        name = ing.text.strip()
        if name:
            amount_el = ing.find_next_sibling()
            amount = amount_el.text.strip() if amount_el else ""
            ingredients.append(f"{name} {amount}".strip())

    if not ingredients:
        for ing in soup2.select(".ingre_list li"):
            text = ing.text.strip()
            if text:
                ingredients.append(text)

    # 조리 단계 — media-body 기준으로 순서대로 추출
    instructions = []
    for step in soup2.select(".view_step_cont .media-body"):
        text = re.sub(r"\s+", " ", step.text.strip())
        if text:
            instructions.append(text)

    # 품질 필터
    if len(instructions) < 2:
        print(f"    [SKIP] 조리단계 부족({len(instructions)}): {recipe_name}")
        return None
    if len(ingredients) < 2:
        print(f"    [SKIP] 재료 부족({len(ingredients)}): {recipe_name}")
        return None

    # 카테고리
    cat_el = soup2.select_one(".view2_summary .view_tag a")
    category = cat_el.text.strip() if cat_el else None

    # 추천수
    reco_el = soup2.select_one(".view_cate_favori")
    recommend_count = 0
    if reco_el:
        reco_text = re.sub(r"\D", "", reco_el.text)
        recommend_count = int(reco_text) if reco_text else 0

    return {
        "recipe_id":       recipe_id,
        "recipe_name":     recipe_name,
        "tag":             tag,
        "crop_name":       crop_name,
        "category":        category,
        "servings":        servings,
        "cook_time":       cook_time,
        "difficulty":      difficulty,
        "ingredients":     ingredients,
        "instructions":    instructions,
        "recommend_count": recommend_count,
        "source":          "10000recipe",
        "source_url":      recipe_url,
        "crawled_at":      datetime.utcnow().isoformat() + "+00:00",
    }


# ──────────────────────────────────────────
# 메인
# ──────────────────────────────────────────

def main():
    all_recipes = []

    for crop_info in TEST_CROPS:
        crop_name = crop_info["crop_name"]
        tier      = crop_info["tier"]
        max_tags  = crop_info["max_tags"]

        print(f"\n{'='*50}")
        print(f"[{tier}급] {crop_name} — 최대 {max_tags}개 태그 테스트")
        print(f"{'='*50}")

        # Step1: 태그 수집
        tags = crawl_related_tags(crop_name)
        if not tags:
            print(f"  → 태그 없음")
            continue

        tags = tags[:max_tags]
        print(f"  수집된 태그: {tags}")
        time.sleep(1)

        # Step2: 태그별 레시피 수집
        crop_recipes = []
        for tag in tags:
            print(f"\n  태그: [{tag}]")
            recipe = crawl_top_recipe(tag, crop_name)
            if recipe:
                crop_recipes.append(recipe)
                print(f"  ✅ {recipe['recipe_name']}")
                print(f"     재료 {len(recipe['ingredients'])}개: {recipe['ingredients'][:3]}...")
                print(f"     조리 {len(recipe['instructions'])}단계")
                print(f"     추천수: {recipe['recommend_count']}")
            else:
                print(f"  ❌ 수집 실패")
            time.sleep(1)

        print(f"\n  → {crop_name}: {len(crop_recipes)}개 수집")
        all_recipes.extend(crop_recipes)
        time.sleep(1.5)

    # 저장
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(all_recipes, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*50}")
    print(f"✅ 테스트 완료: 총 {len(all_recipes)}개 → {OUTPUT_FILE}")
    print(f"{'='*50}")

    # 결과 요약
    print("\n[수집 결과 요약]")
    for r in all_recipes:
        print(f"  - [{r['crop_name']}] {r['recipe_name']} "
              f"(재료 {len(r['ingredients'])}개, "
              f"조리 {len(r['instructions'])}단계, "
              f"추천 {r['recommend_count']})")


if __name__ == "__main__":
    main()