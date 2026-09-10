"""
만개의레시피 최종 크롤링 스크립트
====================================
- crop_knowledge 182개 작물 기준 검색
- A/B/C 등급별 태그 상한 20/10/5개
- 태그별 추천순 1위 레시피 수집
- 중간 저장 (10건마다) → 중단 후 재시작 가능
- 결과: raw_10000recipe.json

실행:
    pip install requests beautifulsoup4
    python crawl_10000recipe_final.py

예상 소요 시간: 1~2시간
예상 수집량: 약 900~975건
"""

import requests
from bs4 import BeautifulSoup
import json
import time
import re
import os
from datetime import datetime

# ────────────────────────────────────────
# 설정
# ────────────────────────────────────────
OUTPUT_FILE   = "raw_10000recipe.json"
CROP_DATA_FILE = "crop_data.json"
BASE_URL = "https://www.10000recipe.com"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
    "Referer": "https://www.10000recipe.com/",
}

# 등급별 태그 수집 상한
MAX_TAGS = {"A": 20, "B": 10, "C": 5}

# ────────────────────────────────────────
# 작물 등급 분류
# ────────────────────────────────────────
TIER_A = {
    "배추", "무", "양파", "마늘", "고추", "감자", "고구마",
    "대파", "파", "당근", "시금치", "깻잎", "상추", "오이",
    "호박", "토마토", "콩", "두부", "가지", "부추",
}
TIER_B = {
    "딸기", "사과", "배", "복숭아", "수박", "참외", "포도",
    "브로콜리", "양배추", "방울토마토", "파프리카", "셀러리",
    "아스파라거스", "쑥갓", "열무", "우엉", "연근", "도라지",
    "고구마순", "미나리", "취나물", "냉이", "쑥", "두릅",
    "감귤", "레몬", "자두", "살구", "체리", "블루베리",
    "고추냉이", "생강", "강황", "더덕", "파프리카",
}

def get_tier(crop_name: str) -> str:
    if crop_name in TIER_A:
        return "A"
    elif crop_name in TIER_B:
        return "B"
    return "C"


# ────────────────────────────────────────
# 유틸
# ────────────────────────────────────────
def safe_get(url: str, retries: int = 3) -> requests.Response | None:
    for attempt in range(retries):
        try:
            res = requests.get(url, headers=HEADERS, timeout=10)
            if res.status_code == 200:
                return res
            print(f"  [WARN] {res.status_code} — {url}")
        except Exception as e:
            print(f"  [ERROR] 시도 {attempt+1}/{retries} — {e}")
            time.sleep(2)
    return None


def build_content(recipe: dict) -> str:
    """RAG용 통합 텍스트 생성"""
    ingredients_text = ", ".join(recipe.get("ingredients", []))
    instructions_text = " ".join(recipe.get("instructions", []))
    return (
        f"레시피명: {recipe['recipe_name']}\n"
        f"작물: {recipe['crop_name']}\n"
        f"재료: {ingredients_text}\n"
        f"조리법: {instructions_text}\n"
        f"인분: {recipe.get('servings', '')}"
    )


# ────────────────────────────────────────
# 크롤링 함수
# ────────────────────────────────────────
def crawl_related_tags(crop_name: str) -> list[str]:
    """
    작물명 검색 → 관련 태그 목록
    <div class="s_category_tag">
      <ul class="tag_cont">
        <li><a href="/recipe/list.html?q=우엉조림">우엉조림</a>
    """
    url = f"{BASE_URL}/recipe/list.html?q={crop_name}&order=reco"
    res = safe_get(url)
    if not res:
        return []

    soup = BeautifulSoup(res.text, "html.parser")
    tag_area = soup.select_one("div.s_category_tag ul.tag_cont")
    if not tag_area:
        return []

    return [a.text.strip() for a in tag_area.select("li a") if a.text.strip()]


def crawl_top_recipe(tag: str, crop_name: str) -> dict | None:
    """
    태그 검색 → 추천순 1위 레시피 상세 수집
    목록: <ul class="common_sp_list_ul">
            <li class="common_sp_list_li">
              <a href="/recipe/6838648" class="common_sp_link">
    상세: stepDiv1~N / media-body
    """
    # 1) 목록 — 추천순 1위 recipe_id 추출
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

    recipe_id  = recipe_path.replace("/recipe/", "").strip()
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

    # 인분 / 조리시간
    info_els = soup2.select(
        ".view2_summary_info1, .view2_summary_info2"
    )
    servings  = info_els[0].text.strip() if len(info_els) > 0 else None
    cook_time = info_els[1].text.strip() if len(info_els) > 1 else None

    # 재료 목록
    ingredients = []
    for ing in soup2.select(".ingre_list_name"):
        name = ing.text.strip()
        if not name:
            continue
        amount_el = ing.find_next_sibling()
        amount = amount_el.text.strip() if amount_el else ""
        ingredients.append(f"{name} {amount}".strip())

    if not ingredients:
        for ing in soup2.select(".ingre_list li"):
            text = ing.text.strip()
            if text:
                ingredients.append(text)

    # 조리 단계 — stepDiv1~N 순서대로, media-body 텍스트 추출
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

    recipe = {
        "recipe_id":    recipe_id,
        "recipe_name":  recipe_name,
        "tag":          tag,
        "crop_name":    crop_name,
        "servings":     servings,
        "cook_time":    cook_time,
        "ingredients":  ingredients,
        "instructions": instructions,
        "source":       "10000recipe",
        "source_url":   recipe_url,
        "crawled_at":   datetime.utcnow().isoformat() + "+00:00",
    }
    recipe["content"] = build_content(recipe)
    return recipe


# ────────────────────────────────────────
# 메인
# ────────────────────────────────────────
def load_crop_names() -> list[str]:
    if not os.path.exists(CROP_DATA_FILE):
        print(f"[ERROR] {CROP_DATA_FILE} 없음 — 같은 폴더에 위치시켜 주세요.")
        return []
    with open(CROP_DATA_FILE, encoding="utf-8") as f:
        return [d["crop_name"] for d in json.load(f)]


def load_existing() -> dict:
    """기존 수집 결과 로드 (재시작 지원)"""
    if not os.path.exists(OUTPUT_FILE):
        return {}
    with open(OUTPUT_FILE, encoding="utf-8") as f:
        return {r["recipe_id"]: r for r in json.load(f)}


def save(collected: dict):
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(list(collected.values()), f, ensure_ascii=False, indent=2)


def print_summary(collected: dict):
    """등급별 수집 현황 출력"""
    tier_count = {"A": 0, "B": 0, "C": 0}
    crop_count: dict[str, int] = {}
    for r in collected.values():
        tier = get_tier(r["crop_name"])
        tier_count[tier] += 1
        crop_count[r["crop_name"]] = crop_count.get(r["crop_name"], 0) + 1

    print("\n" + "="*60)
    print(f"{'등급':<6} {'수집수':>6} {'목표':>6}")
    print("-"*60)
    a_cnt, b_cnt = len(TIER_A & set(crop_count)), len(TIER_B & set(crop_count))
    print(f"{'A급':<6} {tier_count['A']:>6} {'~'+str(len(TIER_A)*20):>6}")
    print(f"{'B급':<6} {tier_count['B']:>6} {'~'+str(len(TIER_B)*10):>6}")
    print(f"{'C급':<6} {tier_count['C']:>6} {'~670':>6}")
    print("-"*60)
    print(f"{'합계':<6} {sum(tier_count.values()):>6} {'~975':>6}")
    print("="*60)

    print("\n[작물별 수집 수 상위 20]")
    for crop, cnt in sorted(crop_count.items(), key=lambda x: -x[1])[:20]:
        tier = get_tier(crop)
        print(f"  {tier}급 {crop:<12} {cnt}개")


def main():
    crop_names = load_crop_names()
    if not crop_names:
        return

    collected = load_existing()
    total = len(crop_names)

    print(f"총 {total}개 작물 크롤링 시작")
    print(f"기존 수집: {len(collected)}건\n")

    for idx, crop_name in enumerate(crop_names, 1):
        tier     = get_tier(crop_name)
        max_tags = MAX_TAGS[tier]

        print(f"[{idx:3d}/{total}] [{tier}급] {crop_name} (태그 최대 {max_tags}개)")

        tags = crawl_related_tags(crop_name)
        if not tags:
            print(f"  → 태그 없음, 건너뜀")
            time.sleep(1)
            continue

        tags = tags[:max_tags]
        print(f"  태그 {len(tags)}개: {tags[:5]}{'...' if len(tags)>5 else ''}")

        crop_ok = 0
        for tag in tags:
            time.sleep(1)
            recipe = crawl_top_recipe(tag, crop_name)
            if not recipe:
                print(f"    [SKIP] {tag}")
                continue
            if recipe["recipe_id"] in collected:
                print(f"    [DUP]  {tag} ({recipe['recipe_name']})")
                continue

            collected[recipe["recipe_id"]] = recipe
            crop_ok += 1
            print(f"    [OK]   {tag} → {recipe['recipe_name']}")

            if len(collected) % 10 == 0:
                save(collected)
                print(f"  💾 중간 저장 ({len(collected)}건)")

        print(f"  → {crop_name}: {crop_ok}개 수집\n")
        time.sleep(1.5)

    save(collected)

    print(f"\n✅ 크롤링 완료: 총 {len(collected)}건 → {OUTPUT_FILE}")
    print_summary(collected)


if __name__ == "__main__":
    main()