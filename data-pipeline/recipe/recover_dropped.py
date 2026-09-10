"""
직전 필터에서 삭제된 105건을 (작물, 태그)로 재수집 → recovered_dropped.json
태그 추천순 1위 레시피의 전체 재료/조리법을 복원한다.
"""
import requests
from bs4 import BeautifulSoup
import json, re, time
from datetime import datetime, timezone

BASE_URL = "https://www.10000recipe.com"
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/120.0.0.0 Safari/537.36"),
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Referer": "https://www.10000recipe.com/",
}

# (작물, 태그) — 직전 mismatch 리포트에서 추출
DROPPED = [
    ("가지버섯","가지버섯볶음"),("가지버섯","가지버섯푸실리파스타"),("가지버섯","가지버섯무침"),
    ("가지버섯","가지버섯솥밥"),("가지버섯","가지버섯구이샐러드"),
    ("감귤","생크림감귤컵케이크"),("감귤","감귤라떼"),("감귤","감귤쉬폰케이크"),("감귤","양상추감귤샐러드"),
    ("강낭콩","강낭콩쉐이크"),
    ("강황","강황밥"),("강황","강황우유"),("강황","계란강황볶음밥"),("강황","LA갈비강황크림리조또"),("강황","강황두부구이"),
    ("고구마순","고구마순들깨볶음"),("고구마순","고구마순고등어조림"),
    ("고추냉이","고추냉이오이무침"),("고추냉이","양파무고추냉이무침"),("고추냉이","고추냉이백김치"),
    ("구기자","구기자메추리알장조림"),
    ("기장","소고기장조림"),("기장","돼지고기장조림"),("기장","쇠고기장조림"),("기장","메추리알소고기장조림"),("기장","메추리알돼지고기장조림"),
    ("깻잎","깻잎볶음"),
    ("노루궁뎅이버섯","노루궁뎅이버섯백숙"),("노루궁뎅이버섯","노루궁뎅이버섯샐러드"),
    ("느타리버섯","느타리버섯볶음"),
    ("능이버섯","능이버섯국"),("능이버섯","소고기능이버섯볶음"),
    ("대두","근대두부된장국"),
    ("들깨","들깨칼국수"),
    ("마","꼬마김밥"),
    ("마늘종","마늘종볶음"),
    ("무","콩나물무침"),("무","도토리묵무침"),("무","골뱅이무침"),("무","꼬막무침"),
    ("미나리","미나리김밥"),
    ("밀","밀푀유나베"),("밀","메밀소바"),("밀","밀크티"),
    ("방울양배추","방울양배추카나페"),
    ("방풍나물","방풍나물장아찌"),
    ("배","뚝배기불고기"),("배","뚝배기계란찜"),
    ("백태","백태콩"),
    ("산딸기","산딸기샐러드"),("산딸기","산딸기요거트아이스크림"),
    ("살구","삼겹살구이"),("살구","통삼겹살구이"),("살구","닭가슴살구이"),("살구","닭다리살구이"),
    ("살구","고추장삼겹살구이"),("살구","목살구이"),("살구","된장삼겹살구이"),("살구","돼지목살구이"),("살구","닭목살구이"),
    ("삼채","삼채무침"),("삼채","삼채전"),
    ("상추","상추튀김"),
    ("상황버섯","상황버섯삼계탕"),
    ("새송이버섯","새송이버섯조림"),
    ("샐러리","샐러리장아찌"),("샐러리","샐러리피클"),
    ("서리태","서리태콩자반"),("서리태","서리태볶음"),
    ("솔부추","솔부추무침"),
    ("숙주나물","숙주나물무침"),("숙주나물","숙주나물비건잡채"),
    ("순무","엄나무순무침"),("순무","오가피순무침"),
    ("시금치","시금치겉절이"),
    ("아로니아","아로니아밥"),
    ("아스파라거스","아스파라거스샐러드"),
    ("애플망고","애플망고케일주스"),("애플망고","애플망고손질법"),
    ("앵두","앵두잼"),
    ("야콘","야콘떡만두국"),
    ("양송이버섯","양송이버섯덮밥"),("양송이버섯","양송이버섯크림파스타"),
    ("양파","참치양파볶음"),
    ("얼갈이배추","얼갈이배추된장국"),("얼갈이배추","얼갈이배추된장무침"),
    ("오디","오디머핀"),("오디","오디아이스크림"),
    ("완두콩","완두콩국수"),
    ("울외","울외장아찌무침"),
    ("유채나물","유채나물된장무침"),
    ("인삼","인삼차"),("인삼","와인삼겹살"),("인삼","인삼떡갈비"),
    ("자두","감자두부전"),("자두","감자두부조림"),
    ("적채","적채피클"),
    ("조","두부조림"),
    ("참깨","오이참깨무침"),
    ("체리","체리타르트"),
    ("총각무","총각무김치"),("총각무","총각무지짐"),
    ("치커리","시금치커리볶음"),
    ("파프리카","파프리카잡채"),
    ("포도","청포도타르트"),
]


def safe_get(url, retries=3):
    for i in range(retries):
        try:
            r = requests.get(url, headers=HEADERS, timeout=10)
            if r.status_code == 200:
                return r
        except Exception as e:
            print(f"  [ERR] {i+1}/{retries} {e}")
            time.sleep(2)
    return None


def fetch_by_tag(tag, crop):
    """태그 추천순 1위 → 상세 (품질필터 없이 전체 복원)"""
    res = safe_get(f"{BASE_URL}/recipe/list.html?q={tag}&order=reco")
    if not res:
        return None
    soup = BeautifulSoup(res.text, "html.parser")
    first = soup.select_one("ul.common_sp_list_ul li.common_sp_list_li a.common_sp_link")
    if not first:
        return None
    path = first.get("href", "")
    if not path.startswith("/recipe/"):
        return None
    rid = path.replace("/recipe/", "").strip()
    url = f"{BASE_URL}/recipe/{rid}"
    time.sleep(0.6)

    res2 = safe_get(url)
    if not res2:
        return None
    s = BeautifulSoup(res2.text, "html.parser")

    title_el = s.select_one(".view2_summary h3")
    recipe_name = title_el.text.strip() if title_el else ""

    info = s.select(".view2_summary_info1, .view2_summary_info2")
    servings  = info[0].text.strip() if len(info) > 0 else None
    cook_time = info[1].text.strip() if len(info) > 1 else None

    ingredients = []
    for ing in s.select(".ingre_list_name"):
        name = ing.text.strip()
        if not name:
            continue
        amt_el = ing.find_next_sibling()
        amt = amt_el.text.strip() if amt_el else ""
        ingredients.append(f"{name} {amt}".strip())
    if not ingredients:
        for ing in s.select(".ingre_list li"):
            t = ing.text.strip()
            if t:
                ingredients.append(t)

    instructions = []
    for step in s.select(".view_step_cont .media-body"):
        t = re.sub(r"\s+", " ", step.text.strip())
        if t:
            instructions.append(t)

    rec = {
        "recipe_id": rid, "recipe_name": recipe_name, "tag": tag, "crop_name": crop,
        "servings": servings, "cook_time": cook_time,
        "ingredients": ingredients, "instructions": instructions,
        "source": "10000recipe", "source_url": url,
        "crawled_at": datetime.now(timezone.utc).isoformat(),
    }
    rec["content"] = (
        f"레시피명: {recipe_name}\n작물: {crop}\n"
        f"재료: {', '.join(ingredients)}\n"
        f"조리법: {' '.join(instructions)}\n인분: {servings or ''}"
    )
    return rec


def main():
    recovered, failed = [], []
    n = len(DROPPED)
    for i, (crop, tag) in enumerate(DROPPED, 1):
        print(f"[{i:3d}/{n}] {crop} / {tag}", end="  ")
        rec = fetch_by_tag(tag, crop)
        if rec:
            recovered.append(rec)
            print(f"→ {rec['recipe_name'][:30]} (재료 {len(rec['ingredients'])})")
        else:
            failed.append((crop, tag))
            print("→ [실패]")
        time.sleep(0.8)
        if i % 20 == 0:
            with open("recovered_dropped.json", "w", encoding="utf-8") as f:
                json.dump(recovered, f, ensure_ascii=False, indent=2)
            print(f"  💾 중간 저장 ({len(recovered)}건)")

    with open("recovered_dropped.json", "w", encoding="utf-8") as f:
        json.dump(recovered, f, ensure_ascii=False, indent=2)

    print(f"\n복구 완료: {len(recovered)}/{n}건 → recovered_dropped.json")
    if failed:
        print(f"실패 {len(failed)}건: {failed}")


if __name__ == "__main__":
    main()
