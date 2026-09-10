"""
Farmily 영농일지 목업 데이터 전처리
CSV(EUC-KR) → crop_region_match.csv / selected_farmers.json / seed_farming_journals.sql
"""
import json
import re
import sys
import pandas as pd
from pathlib import Path

# ── 경로 설정 ──────────────────────────────────────────────────────────────────
BASE = Path(__file__).parent
CSV_PATH = BASE / "한국농수산식품유통공사_농가 및 영농 정보_20241231.csv"
CROP_JSON = BASE / "crop_data.json"
OUT_DIR = BASE / "data/farming_journal/output"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ── 파싱 오류 수집 ──────────────────────────────────────────────────────────────
parse_errors = []

# ──────────────────────────────────────────────────────────────────────────────
# STEP 1 — CSV 로드
# ──────────────────────────────────────────────────────────────────────────────
print("=" * 60)
print("STEP 1 — CSV 로드")
try:
    df = pd.read_csv(CSV_PATH, encoding="euc-kr")
except Exception:
    df = pd.read_csv(CSV_PATH, encoding="utf-8")
df.columns = df.columns.str.strip()
print(f"전체 행 수: {len(df)}")
print(f"컬럼명: {list(df.columns)}")
print("\nnull 비율:")
print(df.isnull().mean().round(3))
counts = df.groupby("농가일련번호").size()
print(f"\n농가일련번호별 행 수: min={counts.min()} / mean={counts.mean():.1f} / max={counts.max()}")
print("상위 10개 농가:")
print(counts.sort_values(ascending=False).head(10))
print("\n품종 unique 목록:")
print(df["품종"].value_counts())
print("\n농작업명 unique 목록 (상위 30):")
print(df["농작업명"].value_counts().head(30))

# ──────────────────────────────────────────────────────────────────────────────
# STEP 2 — crop_knowledge 로드 및 관련 작물 필터
# ──────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("STEP 2 — 매핑 및 선별")

with open(CROP_JSON, encoding="utf-8") as f:
    crop_knowledge = json.load(f)

# CSV 품종 목록
csv_crop_names = set(df["품종"].dropna().unique())

# ── crop_knowledge → ck_map 동적 구축 ─────────────────────────────────────────
# key: CSV에 나타나는 품종명(정규화 기준)  value: crop_knowledge 항목
ck_map = {}

# 1차: 완전일치 (crop_name == csv 품종명) + origin_region 있는 것만
for item in crop_knowledge:
    ck_name = item.get("crop_name", "")
    if ck_name in csv_crop_names and ck_name not in ck_map:
        if item.get("origin_region"):
            ck_map[ck_name] = item

# 2차: 포함관계 (예: "단감" ↔ "감") — 아직 매핑 안 된 CSV 품종 대상
for item in crop_knowledge:
    ck_name = item.get("crop_name", "")
    if not item.get("origin_region"):
        continue
    for csv_crop in csv_crop_names:
        if csv_crop in ck_map:
            continue
        if len(ck_name) >= 2 and (ck_name in csv_crop or csv_crop in ck_name):
            ck_map[csv_crop] = item

print(f"crop_knowledge 매칭 작물 수: {len(ck_map)}종")
for k, v in sorted(ck_map.items()):
    print(f"  {k}: origin_region={v.get('origin_region', '')[:40]}")


def normalize_crop(품종):
    """CSV 품종명 → ck_map 키(정규화 작물명). 매칭 없으면 None."""
    if not isinstance(품종, str):
        return None
    품종 = 품종.strip()
    if 품종 in ck_map:
        return 품종
    # 포함관계
    for canonical in ck_map:
        if len(canonical) >= 2 and (canonical in 품종 or 품종 in canonical):
            return canonical
    return None


# 도/시 약어 정규화
SIDO_ABBR = {
    "충청남도": "충남", "충청북도": "충북", "경상남도": "경남", "경상북도": "경북",
    "전라남도": "전남", "전라북도": "전북", "강원도": "강원", "경기도": "경기",
    "제주특별자치도": "제주", "제주도": "제주",
}


def is_region_match(farm_address, origin_region):
    if not isinstance(farm_address, str) or not isinstance(origin_region, str):
        return False
    # 주소 약어화 (도 → 약어)
    addr_norm = farm_address
    for long, short in SIDO_ABBR.items():
        addr_norm = addr_norm.replace(long, short)
    # "등" 같은 불필요 단어 제거, 쉼표·공백으로 분리
    origin_clean = origin_region.replace("등", "").replace("·", ",").replace("/", ",")
    regions = [r.strip() for r in origin_clean.split(",")]
    for region in regions:
        region_norm = region
        for long, short in SIDO_ABBR.items():
            region_norm = region_norm.replace(long, short)
        tokens = [t for t in region_norm.split() if len(t) >= 2]
        if any(t in addr_norm for t in tokens):
            return True
    return False


# 주소 유효성 확인 (시도 수준 이상)
VALID_PREFIXES = [
    "서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종",
    "경기", "강원", "충북", "충남", "충청", "전북", "전남", "전라",
    "경북", "경남", "경상", "제주",
]


def has_valid_address(addr):
    if not isinstance(addr, str):
        return False
    return any(addr.startswith(p) or p in addr[:6] for p in VALID_PREFIXES)


# 작업유형 매핑
WORK_TYPE_MAP = [
    (["수확작업", "딸기따기", "방울토마토따기", "수확", "따기", "채취", "수확작", "출하"], "수확"),
    (["가지치기", "적엽", "순따기", "순지르기", "적아", "정지", "전지", "전정"], "기타 농업활동"),
    (["파종", "모내기", "정식", "이식", "육묘", "파종작업"], "파종·모내기"),
    (["관수", "물주기", "물관리", "급수", "수분관리"], "관수"),
    (["제초", "김매기", "풀베기", "제초작업", "잡초"], "제초"),
    (["경운", "로터리", "쟁기", "갈기", "흙갈기"], "경운"),
]


def normalize_work_type(농작업명):
    if not isinstance(농작업명, str):
        return "기타 농업활동", ""
    # 기타작업| 접두사 제거
    detail = re.sub(r"^기타작업\|", "", 농작업명).strip()
    for keywords, wtype in WORK_TYPE_MAP:
        if any(k in 농작업명 for k in keywords):
            return wtype, detail
    return "기타 농업활동", detail


# 스토리텔링 점수
STORY_SCORE = {
    "수확": 5, "기타 농업활동": 3, "파종·모내기": 3,
    "관수": 2, "제초": 1, "경운": 1,
}

# 매핑 작업
rows_out = []
for idx, row in df.iterrows():
    try:
        품종 = str(row.get("품종", "")).strip()
        주소 = str(row.get("농가주소", "")).strip()
        작업명 = str(row.get("농작업명", "")).strip() if pd.notna(row.get("농작업명")) else ""

        crop_norm = normalize_crop(품종)
        if crop_norm is None:
            continue

        if not has_valid_address(주소):
            continue

        # crop_knowledge origin_region 가져오기
        ck = ck_map.get(crop_norm)
        origin = ck.get("origin_region", "") if ck else ""

        region_match = is_region_match(주소, origin)
        work_type, work_detail = normalize_work_type(작업명)
        story_score = STORY_SCORE.get(work_type, 1)

        rows_out.append({
            "영농일지일련번호": row["영농일지일련번호"],
            "농가일련번호": row["농가일련번호"],
            "작성일시": row["작성일시"],
            "농가주소": 주소,
            "품종원본": 품종,
            "품종정규화": crop_norm,
            "생육상황명": row.get("생육상황명", ""),
            "농작업명원본": 작업명,
            "work_type": work_type,
            "work_detail": work_detail,
            "origin_region": origin,
            "region_match": region_match,
            "story_score": story_score,
        })
    except Exception as e:
        parse_errors.append({"idx": idx, "error": str(e), "row": str(row.to_dict())[:200]})

df_mapped = pd.DataFrame(rows_out)
print(f"\n매핑 결과 행 수: {len(df_mapped)}")
print(f"  지역-작물 매칭: {df_mapped['region_match'].sum()}")

# 저장
df_mapped.to_csv(OUT_DIR / "crop_region_match.csv", index=False, encoding="utf-8-sig")
print(f"→ crop_region_match.csv 저장 완료")

# ──────────────────────────────────────────────────────────────────────────────
# STEP 3 — 농가 선별 및 JSON 생성
# ──────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("STEP 3 — 중복 병합 및 5개 농가 선별")

# 필수 조건: 지역-작물 매칭
df_matched = df_mapped[df_mapped["region_match"]].copy()
print(f"지역 매칭 통과 행: {len(df_matched)}")

# 농가일련번호별 전체 작업 수집 (병합용)
farmer_all = {}
for _, row in df_matched.iterrows():
    fid = row["농가일련번호"]
    if fid not in farmer_all:
        farmer_all[fid] = []
    farmer_all[fid].append(row)

# 농가별 대표 점수 계산 (최고 story_score + 작업 다양성 + 일지 수)
farmer_scores = {}
for fid, rows in farmer_all.items():
    crop = rows[0]["품종정규화"]
    best_score = max(r["story_score"] for r in rows)
    unique_works = len(set(r["work_type"] for r in rows))
    diary_count = len(set((r["농가일련번호"], r["작성일시"]) for r in rows))
    total = best_score * 3 + unique_works + diary_count
    farmer_scores[fid] = {
        "score": total,
        "crop": crop,
        "best_score": best_score,
        "diary_count": diary_count,
        "unique_works": unique_works,
        "rows": rows,
    }

# ── 작물 다양성 우선 선별 ───────────────────────────────────────────────────────
# 각 작물에서 최고 점수 농가 1명씩 뽑은 뒤, 5개 미만이면 점수 순으로 채움

# 작물별 최고 점수 농가
best_per_crop = {}
for fid, info in farmer_scores.items():
    crop = info["crop"]
    if crop not in best_per_crop or info["score"] > best_per_crop[crop][1]["score"]:
        best_per_crop[crop] = (fid, info)

# 작물별 대표 1명 — 점수 내림차순 정렬
diverse_candidates = sorted(best_per_crop.values(), key=lambda x: x[1]["score"], reverse=True)

top5 = list(diverse_candidates[:5])
used_fids = {fid for fid, _ in top5}

# 5개 미만이면 남은 농가 점수 순으로 보충
if len(top5) < 5:
    remaining = sorted(
        [(fid, info) for fid, info in farmer_scores.items() if fid not in used_fids],
        key=lambda x: x[1]["score"], reverse=True,
    )
    for item in remaining:
        if len(top5) >= 5:
            break
        top5.append(item)
        used_fids.add(item[0])

if len(top5) < 5:
    print(f"⚠ 경고: 선별 농가 {len(top5)}개 (5개 미만).")

print("\n선별된 농가:")
for fid, info in top5:
    sample = info["rows"][0]
    print(f"  농가 {fid} | {sample['품종정규화']} | {sample['농가주소'][:20]} | 일지:{info['diary_count']} | 점수:{info['score']}")

# JSON 구조 생성 (섹션 5 기준)
def parse_date(val):
    if not isinstance(val, str):
        return "2024-01-01"
    val = val.strip()
    # YYYY-MM
    m = re.match(r"(\d{4})-(\d{2})$", val)
    if m:
        return f"{m.group(1)}-{m.group(2)}-01"
    # YYYY-MM-DD
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", val)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return "2024-01-01"


def extract_region(address):
    if not isinstance(address, str):
        return ""
    tokens = address.split()
    return " ".join(tokens[:2]) if len(tokens) >= 2 else address


selected_farmers = []
for rank, (fid, info) in enumerate(top5, start=1):
    rows_list = info["rows"]
    # 대표 행 (최고 story_score 기준)
    best_row = max(rows_list, key=lambda r: r["story_score"])

    # 날짜+농가 조합으로 일지 묶기
    diary_map = {}
    for r in rows_list:
        key = (str(r["농가일련번호"]), str(r["작성일시"]))
        if key not in diary_map:
            diary_map[key] = []
        diary_map[key].append(r)

    farm_diaries = []
    for (_, date_raw), drows in diary_map.items():
        diary_date = parse_date(date_raw)
        생육 = next((r["생육상황명"] for r in drows if pd.notna(r["생육상황명"]) and str(r["생육상황명"]).strip()), None)
        memo = f"생육상황: {생육}" if 생육 else None
        work_blocks = []
        for sort_i, r in enumerate(drows):
            work_blocks.append({
                "sort_order": sort_i,
                "work_type": r["work_type"],
                "detail": r["work_detail"] or r["농작업명원본"],
            })
        farm_diaries.append({
            "diary_date": diary_date,
            "memo": memo,
            "diary_work_blocks": work_blocks,
        })

    ck = ck_map.get(best_row["품종정규화"], {})
    selected_farmers.append({
        "farmer_id": int(fid),
        "rank": rank,
        "address": best_row["농가주소"],
        "region": extract_region(best_row["농가주소"]),
        "crop_name": best_row["품종정규화"],
        "crop_origin_raw": best_row["품종원본"],
        "origin_region": best_row["origin_region"],
        "selection_score": info["score"],
        "diary_count": info["diary_count"],
        "work_types": list(set(r["work_type"] for r in rows_list)),
        "crop_knowledge": {
            "crop_name": ck.get("crop_name", ""),
            "origin_region": ck.get("origin_region", ""),
            "season_month": ck.get("season_month"),
            "harvest_months": ck.get("harvest_months", []),
        },
        "farm_diaries": sorted(farm_diaries, key=lambda d: d["diary_date"]),
    })

with open(OUT_DIR / "selected_farmers.json", "w", encoding="utf-8") as f:
    json.dump(selected_farmers, f, ensure_ascii=False, indent=2)
print(f"→ selected_farmers.json 저장 완료")

# ──────────────────────────────────────────────────────────────────────────────
# STEP 4 — SQL 생성
# ──────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("STEP 4 — SQL 생성")

# 작물별 색상 — 고정값 우선, 나머지는 팔레트 순환
CROP_COLORS_FIXED = {
    "딸기": "#E63946",
    "방울토마토": "#F4813F",
    "감귤": "#F7B731",
    "사과": "#C0392B",
    "포도": "#8E44AD",
    "배": "#F0C040",
    "복숭아": "#FFB6C1",
    "파프리카": "#E67E22",
    "키위": "#27AE60",
    "아스파라거스": "#2ECC71",
    "참외": "#F9CA24",
    "토마토": "#E74C3C",
    "쌀": "#BDC3C7",
    "무": "#ECF0F1",
    "배추": "#82C341",
}
_PALETTE = ["#2BA651", "#3498DB", "#9B59B6", "#1ABC9C", "#F39C12"]
_palette_idx = [0]


def get_crop_color(crop):
    if crop in CROP_COLORS_FIXED:
        return CROP_COLORS_FIXED[crop]
    color = _PALETTE[_palette_idx[0] % len(_PALETTE)]
    _palette_idx[0] += 1
    return color


def esc(val) -> str:
    """SQL 인젝션 방지 — 작은따옴표 이스케이프"""
    if val is None:
        return "NULL"
    return "'" + str(val).replace("'", "''") + "'"


sql_lines = [
    "-- ============================================================",
    "-- Farmily 영농일지 시드 데이터 (멱등성 보장)",
    "-- 생성 기준: 공공데이터포털 농가 및 영농 정보 20241231",
    "-- ============================================================",
    "",
    "BEGIN;",
    "",
]

# 1. users + subscriptions
for f in selected_farmers:
    fid = f["farmer_id"]
    kakao_id = f"seed_farmer_{fid}"
    handle = f"seed_farmer_{fid}"
    farm_name = f"{f['region']} {f['crop_name']} 농장".replace("'", "''")
    sql_lines += [
        f"-- ===== 농가 {f['rank']}: farmer_id={fid} ({f['crop_name']}, {f['region']}) =====",
        f"INSERT INTO users (kakao_id, name, handle, onboarded_at)",
        f"  VALUES ({esc(kakao_id)}, {esc(farm_name)}, {esc(handle)}, now())",
        f"  ON CONFLICT (kakao_id) DO UPDATE",
        f"    SET handle=EXCLUDED.handle, onboarded_at=EXCLUDED.onboarded_at, updated_at=now();",
        "",
        f"INSERT INTO subscriptions (user_id)",
        f"  SELECT id FROM users WHERE kakao_id={esc(kakao_id)}",
        f"  ON CONFLICT (user_id) DO NOTHING;",
        "",
    ]

# 2. farm_profiles
for f in selected_farmers:
    fid = f["farmer_id"]
    kakao_id = f"seed_farmer_{fid}"
    farm_name = f"{f['region']} {f['crop_name']} 농장".replace("'", "''")
    region = f["region"].replace("'", "''")
    sql_lines += [
        f"INSERT INTO farm_profiles (user_id, farm_name, region)",
        f"  SELECT id, {esc(farm_name)}, {esc(region)} FROM users WHERE kakao_id={esc(kakao_id)}",
        f"  ON CONFLICT (user_id) DO UPDATE",
        f"    SET farm_name=EXCLUDED.farm_name, region=EXCLUDED.region, updated_at=now();",
        "",
    ]

# 3. farm_locations
for f in selected_farmers:
    fid = f["farmer_id"]
    kakao_id = f"seed_farmer_{fid}"
    address = f["address"].replace("'", "''")
    sql_lines += [
        f"INSERT INTO farm_locations (user_id, label, address)",
        f"  SELECT id, '본농장', {esc(address)} FROM users WHERE kakao_id={esc(kakao_id)}",
        f"  ON CONFLICT DO NOTHING;",
        "",
    ]

# 4. crops
for f in selected_farmers:
    fid = f["farmer_id"]
    kakao_id = f"seed_farmer_{fid}"
    crop = f["crop_name"]
    color = get_crop_color(crop)
    sql_lines += [
        f"INSERT INTO crops (user_id, name, color_hex)",
        f"  SELECT id, {esc(crop)}, {esc(color)} FROM users WHERE kakao_id={esc(kakao_id)}",
        f"  ON CONFLICT DO NOTHING;",
        "",
    ]

# 5. farm_diaries + diary_work_blocks
for f in selected_farmers:
    fid = f["farmer_id"]
    kakao_id = f"seed_farmer_{fid}"
    crop = f["crop_name"]
    for diary in f["farm_diaries"]:
        diary_date = diary["diary_date"]
        memo_sql = esc(diary["memo"]) if diary.get("memo") else "NULL"
        sql_lines += [
            f"WITH _u AS (SELECT id FROM users WHERE kakao_id={esc(kakao_id)}),",
            f"     _loc AS (SELECT id FROM farm_locations WHERE user_id=(SELECT id FROM _u) LIMIT 1),",
            f"     _crop AS (SELECT id FROM crops WHERE user_id=(SELECT id FROM _u) AND name={esc(crop)} AND deleted_at IS NULL LIMIT 1),",
            f"     _diary AS (",
            f"       INSERT INTO farm_diaries (user_id, farm_location_id, diary_date, crop_id, weather_source, memo)",
            f"       SELECT (SELECT id FROM _u), (SELECT id FROM _loc), {esc(diary_date)}::DATE,",
            f"              (SELECT id FROM _crop), 'MANUAL', {memo_sql}",
            f"       ON CONFLICT (user_id, farm_location_id, diary_date) WHERE deleted_at IS NULL",
            f"       DO UPDATE SET memo=EXCLUDED.memo, updated_at=now()",
            f"       RETURNING id",
            f"     )",
        ]
        for wb in diary["diary_work_blocks"]:
            wt = wb["work_type"].replace("'", "''")
            wd = wb["detail"].replace("'", "''") if wb.get("detail") else ""
            sql_lines.append(
                f"INSERT INTO diary_work_blocks (diary_id, work_type, detail, sort_order)"
                f" SELECT id, {esc(wt)}, {esc(wd)}, {wb['sort_order']} FROM _diary"
                f" ON CONFLICT DO NOTHING;"
            )
        sql_lines.append("")

# 6. crop_knowledge — 선별 5개 농가 작물
inserted_ck = set()
sql_lines += [
    "-- ===== crop_knowledge (선별 농가 작물) =====",
]
for f in selected_farmers:
    crop = f["crop_name"]
    if crop in inserted_ck:
        continue
    inserted_ck.add(crop)
    ck = ck_map.get(crop, {})
    if not ck:
        continue
    harvest = "{" + ",".join(str(m) for m in ck.get("harvest_months", [])) + "}"
    sql_lines += [
        f"INSERT INTO crop_knowledge",
        f"  (crop_name, category, season_month, harvest_months, production_period,",
        f"   origin_region, cooking_method, storage_method, nutrition_brief,",
        f"   effect_brief, purchase_tip, source_url, crawled_at)",
        f"VALUES (",
        f"  {esc(ck.get('crop_name'))},",
        f"  {esc(ck.get('category'))},",
        f"  {ck.get('season_month') or 'NULL'},",
        f"  '{harvest}',",
        f"  {esc(ck.get('production_period'))},",
        f"  {esc(ck.get('origin_region'))},",
        f"  {esc(ck.get('cooking_method'))},",
        f"  {esc(ck.get('storage_method'))},",
        f"  {esc(ck.get('nutrition_brief'))},",
        f"  {esc(ck.get('effect_brief'))},",
        f"  {esc(ck.get('purchase_tip'))},",
        f"  {esc(ck.get('source_url'))},",
        f"  {esc(ck.get('crawled_at'))}::TIMESTAMPTZ",
        f")",
        f"ON CONFLICT (crop_name) DO UPDATE SET",
        f"  origin_region=EXCLUDED.origin_region,",
        f"  updated_at=now();",
        "",
    ]

sql_lines += ["COMMIT;", ""]

# ──────────────────────────────────────────────────────────────────────────────
# STEP 5 — 검증 쿼리 (주석)
# ──────────────────────────────────────────────────────────────────────────────
sql_lines += [
    "-- ============================================================",
    "-- 검증 쿼리",
    "-- ============================================================",
    "",
    "-- 1. 농가별 일지 건수",
    "-- SELECT u.kakao_id, u.name, COUNT(fd.id) AS diary_count",
    "--   FROM users u",
    "--   LEFT JOIN farm_diaries fd ON fd.user_id = u.id AND fd.deleted_at IS NULL",
    "--  WHERE u.kakao_id LIKE 'seed_farmer_%'",
    "--  GROUP BY u.id ORDER BY diary_count DESC;",
    "",
    "-- 2. 작업 유형 분포",
    "-- SELECT dwb.work_type, COUNT(*) AS cnt",
    "--   FROM diary_work_blocks dwb",
    "--   JOIN farm_diaries fd ON fd.id = dwb.diary_id",
    "--   JOIN users u ON u.id = fd.user_id",
    "--  WHERE u.kakao_id LIKE 'seed_farmer_%'",
    "--  GROUP BY dwb.work_type ORDER BY cnt DESC;",
    "",
    "-- 3. crop_knowledge × 시드 농가 작물 일치 여부",
    "-- SELECT c.name AS crop, ck.origin_region, ck.season_month",
    "--   FROM crops c",
    "--   JOIN users u ON u.id = c.user_id",
    "--   LEFT JOIN crop_knowledge ck ON ck.crop_name = c.name",
    "--  WHERE u.kakao_id LIKE 'seed_farmer_%' AND c.deleted_at IS NULL",
    "--  ORDER BY c.name;",
]

sql_text = "\n".join(sql_lines)
(OUT_DIR / "seed_farming_journals.sql").write_text(sql_text, encoding="utf-8")
print(f"→ seed_farming_journals.sql 저장 완료 ({len(sql_lines)}줄)")

# parse_errors.csv
if parse_errors:
    pd.DataFrame(parse_errors).to_csv(OUT_DIR / "parse_errors.csv", index=False, encoding="utf-8-sig")
    print(f"→ parse_errors.csv 저장 ({len(parse_errors)}건)")
else:
    pd.DataFrame(columns=["idx", "error", "row"]).to_csv(
        OUT_DIR / "parse_errors.csv", index=False, encoding="utf-8-sig"
    )
    print("→ parse_errors.csv 저장 (오류 없음)")

# ──────────────────────────────────────────────────────────────────────────────
# STEP 5 — 콘솔 요약
# ──────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("선별된 5개 농가 요약")
print("=" * 60)
for f in selected_farmers:
    print(f"[농가 {f['rank']}]")
    print(f"  farmer_id   : {f['farmer_id']}")
    print(f"  작물        : {f['crop_name']}")
    print(f"  지역        : {f['region']}")
    print(f"  일지 건수   : {f['diary_count']}")
    print(f"  작업 유형   : {', '.join(f['work_types'])}")
    print(f"  선별 점수   : {f['selection_score']}")
    print()

print("=" * 60)
print("최종 출력 파일:")
for p in ["crop_region_match.csv", "selected_farmers.json", "seed_farming_journals.sql", "parse_errors.csv"]:
    fp = OUT_DIR / p
    size = fp.stat().st_size if fp.exists() else 0
    print(f"  {p} ({size:,} bytes)")
