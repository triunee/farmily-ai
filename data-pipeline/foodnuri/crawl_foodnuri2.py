# crawl_foodnuri.py
# Python 3.11 / pip install requests beautifulsoup4

import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse, parse_qs
from datetime import datetime, timezone
import json
import time

BASE_URL = "https://www.foodnuri.go.kr"
LIST_URL = BASE_URL + "/portal/bbs/B0000283/list.do"
OUTPUT   = "crop_data.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}

# ── source_url에서 selectMonth 추출 ──────────────────────────
def parse_season_month(url):
    params = parse_qs(urlparse(url).query)
    month  = params.get("selectMonth", [None])[0]
    return int(month) if month else None

# ── 월별농식품 "01,02,03" → [1, 2, 3] ───────────────────────
def parse_harvest_months(month_str):
    if not month_str:
        return []
    return [
        int(m.strip())
        for m in month_str.split(",")
        if m.strip().isdigit()
    ]

# ── 텍스트 공통 정제 (- 기호 제거 + 마침표 정규화) ──────────
def clean_text(text):
    """줄 단위 - 기호 제거 + 마침표 정규화"""
    lines = text.splitlines()
    cleaned = []
    for line in lines:
        line = line.strip()
        if not line or line == "-":
            continue
        line = line.lstrip("-").strip()
        if len(line) <= 1:
            continue
        if not line.endswith("."):
            line = line + "."
        cleaned.append(line)
    return " ".join(cleaned)

# ── 텍스트 필드 파싱 (페이지 구조별 3가지 케이스) ────────────
def parse_text_field(dd):
    """
    페이지마다 구조가 달라 3가지 케이스 처리:
    1. p 태그로 분리된 경우  → p 단위 파싱
    2. - 구분자 한 덩어리    → - 기준으로 split
    3. 일반 텍스트           → 줄 단위 파싱
    """
    paragraphs = dd.select("p")

    if paragraphs:
        # 케이스 1: p 태그 단위 파싱
        sentences = []
        for p in paragraphs:
            text = re.sub(r"^-+\s*", "", p.get_text(separator="").strip())
            if not text or len(text) <= 1:
                continue
            if not text.endswith("."):
                text = text + "."
            sentences.append(text)
        if sentences:
            return " ".join(sentences)
        # sentences 비면 케이스 2,3으로 계속 진행 (fix: 문제 2)

    # 케이스 2: - 구분자로 한 덩어리인 경우
    raw = dd.get_text(separator="").strip()
    if "-" in raw:
        # fix: 문제 1 — 마침표 뒤 - 도 분리되도록 패턴 수정
        parts = re.split(r"\.?-(?=\S)", raw)
        sentences = []
        for part in parts:
            part = part.strip()
            if not part or len(part) <= 1:
                continue
            if not part.endswith("."):
                part = part + "."
            sentences.append(part)
        if sentences:
            return " ".join(sentences)

    # 케이스 3: 일반 텍스트 fallback
    return clean_text(dd.get_text(separator="\n"))

# ── 영양 필드: 표 제거 후 parse_text_field 적용 ──────────────
def parse_nutrition(dd):
    """영양 필드: 표 제거 후 parse_text_field 적용"""
    for table in dd.select("table"):
        table.decompose()
    for tag in dd.select("p.title, strong, h4, a"):
        tag.decompose()
    return parse_text_field(dd)

# ── 상세 페이지 파싱 ─────────────────────────────────────────
def crawl_detail(detail_url, index, total):
    print(f"    [{index}/{total}] 상세 접속 중... ", end="", flush=True)

    try:
        res = requests.get(detail_url, headers=HEADERS, timeout=10)
        res.raise_for_status()
    except Exception as e:
        print(f"❌ 오류: {e}")
        return None

    soup = BeautifulSoup(res.text, "html.parser")
    view = soup.select_one("div.view.type3")
    if not view:
        print("❌ view 영역 없음")
        return None

    # 작물명
    h2        = view.select_one("h2.subject")
    crop_name = h2.text.strip() if h2 else None

    # dl/dt/dd 전체 파싱
    # 숫자/날짜/분류 필드는 정제 제외
    SKIP_CLEAN_KEYS = {"월별", "월별농식품", "생산시기", "분류", "주요산지"}

    data = {}
    for dl in view.select("dl"):
        dt = dl.select_one("dt")
        dd = dl.select_one("dd")
        if not dt or not dd:
            continue
        key = dt.get_text(strip=True).replace("\n", "").replace(" ", "")
        if key == "영양":
            val = parse_nutrition(dd)
        elif key in SKIP_CLEAN_KEYS:
            val = dd.get_text(separator=" ").strip()
        else:
            val = parse_text_field(dd)
        data[key] = val

    # 분류 정제 ("농산물 > 채소류" → "채소류")  fix: 문제 3
    category = data.get("분류", "")
    if ">" in category:
        category = category.split(">")[-1].strip()

    print(f"✓ {crop_name}")
    return {
        "crop_name":         crop_name,
        "category":          category,
        "season_month":      parse_season_month(detail_url),
        "harvest_months":    parse_harvest_months(data.get("월별농식품", "")),
        "production_period": data.get("생산시기", ""),
        "origin_region":     data.get("주요산지", ""),
        "cooking_method":    data.get("조리법", ""),
        "storage_method":    data.get("손질과보관법", ""),
        "nutrition_brief":   data.get("영양", ""),
        "effect_brief":      data.get("효능", ""),
        "purchase_tip":      data.get("구입요령", ""),
        "source_url":        detail_url,
        "crawled_at":        datetime.now(timezone.utc).isoformat(),
    }

# ── 월별 목록 순회 ───────────────────────────────────────────
def crawl_month(month):
    results = []
    page    = 1

    while True:
        params = {
            "menuNo":      "300063",
            "selectMonth": month,
            "searchCnd":   "",
            "searchWrd":   "",
            "deleteCd":    "0",
            "pageIndex":   page
        }

        print(f"\n  [{month}월 - 페이지 {page}] 목록 요청 중...")

        try:
            res = requests.get(LIST_URL, params=params, headers=HEADERS, timeout=10)
            res.raise_for_status()
        except Exception as e:
            print(f"  ❌ 목록 요청 실패: {e}")
            break

        soup  = BeautifulSoup(res.text, "html.parser")
        links = soup.select("div.boxs a.name")

        if not links:
            print(f"  링크 없음 → {month}월 종료")
            break

        print(f"  → {len(links)}건 발견")

        for i, link in enumerate(links, start=1):
            detail_url = BASE_URL + link["href"]
            item = crawl_detail(detail_url, i, len(links))
            if item and item["crop_name"]:
                results.append(item)
            time.sleep(1)

        # 다음 페이지 링크 존재 여부로 마지막 페이지 판단
        next_page_link = soup.select_one(f"a[href*='pageIndex={page + 1}']")
        if not next_page_link:
            print(f"  → {month}월 마지막 페이지 완료")
            break

        page += 1
        time.sleep(1)

    return results

# ── 전체 실행 ─────────────────────────────────────────────────
if __name__ == "__main__":
    all_results = []
    seen_crops  = set()   # 월별 중복 작물 제거용

    print("=" * 50)
    print("  foodnuri 제철농식품 크롤링 시작 (1~12월)")
    print("=" * 50)

    for month in range(1, 13):
        print(f"\n{'─' * 50}")
        print(f"  {month}월 수집 시작")
        print(f"{'─' * 50}")

        items = crawl_month(month)

        # 중복 작물 제거
        new_items = []
        for item in items:
            if item["crop_name"] not in seen_crops:
                seen_crops.add(item["crop_name"])
                new_items.append(item)
            else:
                print(f"  ⚠ 중복 스킵: {item['crop_name']}")

        all_results.extend(new_items)
        print(f"\n  {month}월 완료 — 신규 {len(new_items)}건 (누적 {len(all_results)}건)")

        time.sleep(2)

    # JSON 저장
    print("\n" + "=" * 50)
    print(f"  전체 수집 완료: 총 {len(all_results)}건")
    print("=" * 50)

    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)

    print(f"\n  저장 완료 → {OUTPUT}")
    print("\n  수집된 작물 목록:")
    for item in all_results:
        print(
            f"    - {item['crop_name']}"
            f" ({item['category']})"
            f" | 대표제철: {item['season_month']}월"
            f" | 제철범위: {item['harvest_months']}"
            f" | 생산: {item['production_period']}"
        )