"""
1,2위(딸기/키위) 유지 + 3,4,5위를 지역 특산 농가로 교체
  3위: 부여 방울토마토 (farmer_id=4843)
  4위: 철원 파프리카   (farmer_id=9437)
  5위: 나주 배        (farmer_id=3059)
"""
import json, re, pandas as pd
from pathlib import Path

BASE = Path(__file__).parent
CSV_PATH = BASE / "한국농수산식품유통공사_농가 및 영농 정보_20241231.csv"
CROP_JSON = BASE / "crop_data.json"
OUT_DIR = BASE / "data/farming_journal/output"

# ── 기존 1,2위 유지 ───────────────────────────────────────────────────────────
with open(OUT_DIR / "selected_farmers.json", encoding="utf-8") as f:
    existing = json.load(f)
keep = [f for f in existing if f["rank"] in (1, 2)]

# ── CSV 로드 ──────────────────────────────────────────────────────────────────
df = pd.read_csv(CSV_PATH, encoding="euc-kr")
df.columns = df.columns.str.strip()

# ── crop_knowledge 로드 ───────────────────────────────────────────────────────
with open(CROP_JSON, encoding="utf-8") as f:
    crop_knowledge = json.load(f)

ck_lookup = {item["crop_name"]: item for item in crop_knowledge}

# ── 신규 3개 농가 정의 ─────────────────────────────────────────────────────────
NEW_TARGETS = [
    {"rank": 3, "farmer_id": 4843,  "crop_name": "방울토마토", "region_kw": "부여"},
    {"rank": 4, "farmer_id": 9437,  "crop_name": "파프리카",   "region_kw": "철원"},
    {"rank": 5, "farmer_id": 3059,  "crop_name": "배",         "region_kw": "나주"},
]

SIDO_ABBR = {
    "충청남도": "충남", "충청북도": "충북", "경상남도": "경남", "경상북도": "경북",
    "전라남도": "전남", "전라북도": "전북", "강원도": "강원", "경기도": "경기",
    "제주특별자치도": "제주",
}

WORK_TYPE_MAP = [
    (["수확작업", "딸기따기", "방울토마토따기", "수확", "따기", "채취", "출하"], "수확"),
    (["가지치기", "적엽", "순따기", "순지르기", "적아", "정지", "전지", "전정", "도장지"], "기타 농업활동"),
    (["파종", "모내기", "정식", "이식", "육묘"], "파종·모내기"),
    (["관수", "물주기", "물관리", "급수"], "관수"),
    (["제초", "김매기", "풀베기", "잡초"], "제초"),
    (["경운", "로터리", "쟁기"], "경운"),
]

def normalize_work_type(농작업명):
    if not isinstance(농작업명, str):
        return "기타 농업활동", ""
    detail = re.sub(r"^기타작업\|", "", 농작업명).strip()
    for keywords, wtype in WORK_TYPE_MAP:
        if any(k in 농작업명 for k in keywords):
            return wtype, detail
    return "기타 농업활동", detail

def parse_date(val):
    if not isinstance(val, str):
        return "2024-01-01"
    val = val.strip()
    m = re.match(r"(\d{4})-(\d{2})$", val)
    if m:
        return f"{m.group(1)}-{m.group(2)}-01"
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", val)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return "2024-01-01"

def extract_region(address):
    if not isinstance(address, str):
        return ""
    tokens = address.split()
    return " ".join(tokens[:2]) if len(tokens) >= 2 else address

# ── 신규 농가 데이터 구성 ─────────────────────────────────────────────────────
new_farmers = []
for target in NEW_TARGETS:
    fid = target["farmer_id"]
    crop = target["crop_name"]

    rows = df[df["농가일련번호"] == fid]
    if rows.empty:
        print(f"⚠ farmer_id={fid} 데이터 없음")
        continue

    address = rows["농가주소"].iloc[0]
    region = extract_region(address)

    # 날짜별 일지 묶기
    diary_map = {}
    for _, row in rows.iterrows():
        key = str(row["작성일시"])
        if key not in diary_map:
            diary_map[key] = []
        diary_map[key].append(row)

    farm_diaries = []
    work_type_set = set()
    for date_raw, drows in sorted(diary_map.items()):
        diary_date = parse_date(date_raw)
        생육 = next(
            (str(r["생육상황명"]) for r in drows
             if pd.notna(r.get("생육상황명")) and str(r.get("생육상황명", "")).strip()),
            None
        )
        memo = f"생육상황: {생육}" if 생육 else None
        work_blocks = []
        for sort_i, r in enumerate(drows):
            wname = r["농작업명"] if pd.notna(r.get("농작업명")) else ""
            wt, wd = normalize_work_type(wname)
            work_type_set.add(wt)
            work_blocks.append({
                "sort_order": sort_i,
                "work_type": wt,
                "detail": wd or wname,
            })
        farm_diaries.append({
            "diary_date": diary_date,
            "memo": memo,
            "diary_work_blocks": work_blocks,
        })

    ck = ck_lookup.get(crop, {})

    new_farmers.append({
        "farmer_id": int(fid),
        "rank": target["rank"],
        "address": address,
        "region": region,
        "crop_name": crop,
        "crop_origin_raw": crop,
        "origin_region": ck.get("origin_region", ""),
        "selection_score": None,  # 수동 지정
        "diary_count": len(farm_diaries),
        "work_types": list(work_type_set),
        "crop_knowledge": {
            "crop_name": ck.get("crop_name", crop),
            "origin_region": ck.get("origin_region", ""),
            "season_month": ck.get("season_month"),
            "harvest_months": ck.get("harvest_months", []),
        },
        "farm_diaries": farm_diaries,
    })
    print(f"  rank{target['rank']} farmer_id={fid} | {crop} | {region} | 일지 {len(farm_diaries)}개 | 작업: {work_type_set}")

# ── 최종 병합 (1,2위 + 신규 3,4,5위) ─────────────────────────────────────────
final = sorted(keep + new_farmers, key=lambda x: x["rank"])

out_path = OUT_DIR / "selected_farmers_custom.json"
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(final, f, ensure_ascii=False, indent=2)
print(f"\n→ {out_path} 저장 완료")

# ── 요약 출력 ─────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("최종 선별 5개 농가")
print("=" * 60)
for f in final:
    score = f["selection_score"] if f["selection_score"] else "수동지정"
    print(f"[{f['rank']}위] farmer_id={f['farmer_id']} | {f['crop_name']} | {f['region']} | 일지 {f['diary_count']}개 | 점수:{score}")
    print(f"      작업유형: {', '.join(f['work_types'])}")
