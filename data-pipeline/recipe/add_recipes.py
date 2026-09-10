"""지정 URL 레시피를 raw_10000recipe.json에 추가"""
import requests
from bs4 import BeautifulSoup
import json
import re
from datetime import datetime, timezone

OUTPUT_FILE = "raw_10000recipe.json"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9",
}

TARGETS = [
    {"url": "https://www.10000recipe.com/recipe/6838428", "crop_name": "감"},
    {"url": "https://www.10000recipe.com/recipe/7064821", "crop_name": "감"},
]


def parse_recipe(url: str, crop_name: str):
    res = requests.get(url, headers=HEADERS, timeout=10)
    if res.status_code != 200:
        print(f"[ERROR] {res.status_code} — {url}")
        return None

    soup = BeautifulSoup(res.text, "html.parser")
    recipe_id = url.rstrip("/").split("/")[-1]

    title_el = soup.select_one(".view2_summary h3")
    if not title_el:
        print(f"[ERROR] 제목 없음 — {url}")
        return None
    recipe_name = title_el.text.strip()

    info_els = soup.select(".view2_summary_info1, .view2_summary_info2")
    servings  = info_els[0].text.strip() if len(info_els) > 0 else None
    cook_time = info_els[1].text.strip() if len(info_els) > 1 else None

    ingredients = []
    for ing in soup.select(".ingre_list_name"):
        name = ing.text.strip()
        if not name:
            continue
        amount_el = ing.find_next_sibling()
        amount = amount_el.text.strip() if amount_el else ""
        ingredients.append(f"{name} {amount}".strip())
    if not ingredients:
        for ing in soup.select(".ingre_list li"):
            text = ing.text.strip()
            if text:
                ingredients.append(text)

    instructions = []
    for step in soup.select(".view_step_cont .media-body"):
        text = re.sub(r"\s+", " ", step.text.strip())
        if text:
            instructions.append(text)

    # tag: 페이지 내 태그 영역에서 첫 번째 태그 사용, 없으면 레시피명 앞부분
    tag_el = soup.select_one(".view2_tag a")
    tag = tag_el.text.strip() if tag_el else recipe_name.split()[0]

    recipe = {
        "recipe_id":   recipe_id,
        "recipe_name": recipe_name,
        "tag":         tag,
        "crop_name":   crop_name,
        "servings":    servings,
        "cook_time":   cook_time,
        "ingredients": ingredients,
        "instructions": instructions,
        "source":      "10000recipe",
        "source_url":  url,
        "crawled_at":  datetime.now(timezone.utc).isoformat(),
    }
    ingredients_text = ", ".join(ingredients)
    instructions_text = " ".join(instructions)
    recipe["content"] = (
        f"레시피명: {recipe_name}\n"
        f"작물: {crop_name}\n"
        f"재료: {ingredients_text}\n"
        f"조리법: {instructions_text}\n"
        f"인분: {servings or ''}"
    )
    return recipe


def main():
    with open(OUTPUT_FILE, encoding="utf-8") as f:
        data = json.load(f)
    existing_ids = {r["recipe_id"] for r in data}

    added = 0
    for target in TARGETS:
        url, crop_name = target["url"], target["crop_name"]
        recipe_id = url.rstrip("/").split("/")[-1]

        if recipe_id in existing_ids:
            print(f"[DUP]  {recipe_id} 이미 존재 — 건너뜀")
            continue

        print(f"[FETCH] {url}")
        recipe = parse_recipe(url, crop_name)
        if not recipe:
            continue

        data.append(recipe)
        existing_ids.add(recipe_id)
        added += 1
        print(f"[OK]   {recipe['recipe_name']}  (태그: {recipe['tag']})")

    if added:
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"\n저장 완료: {OUTPUT_FILE}  (+{added}건, 총 {len(data)}건)")
    else:
        print("\n추가된 항목 없음")


if __name__ == "__main__":
    main()
