"""
selected_farmers_refined.json → seed_farming_journals_v2.sql 생성

INSERT 순서 (FK 의존성):
  users → subscriptions → farm_profiles → farm_locations → crops
  → farm_diaries → diary_work_blocks (DELETE+INSERT 멱등)
"""
import json
from pathlib import Path

BASE     = Path(__file__).parent
IN_PATH  = BASE / "data/farming_journal/output/selected_farmers_refined.json"
OUT_PATH = BASE / "data/farming_journal/output/seed_farming_journals_v2.sql"

CROP_COLOR = {
    "딸기":     "#E63946",
    "키위":     "#27AE60",
    "방울토마토": "#FF6B6B",
    "파프리카":  "#E67E22",
}


def esc(v):
    """None → NULL, 문자열 → 이스케이프된 SQL 리터럴"""
    if v is None:
        return "NULL"
    return "'" + str(v).replace("'", "''") + "'"


def num(v):
    """None → NULL, 숫자 → 그대로"""
    return "NULL" if v is None else str(v)


with open(IN_PATH, encoding="utf-8") as f:
    farmers = json.load(f)

L = []

def w(*args):
    L.append(" ".join(str(a) for a in args))

# ── 헤더 ─────────────────────────────────────────────────────────────────────
w("-- ============================================================")
w("-- Farmily 영농일지 시드 데이터 v2 (멱등성 보장)")
w("-- 기준: selected_farmers_refined.json")
w("-- 농가:", ", ".join(f"{f['crop_name']}({f['region']})" for f in farmers))
w("-- 일지:", sum(len(f["farm_diaries"]) for f in farmers), "건")
w("-- ============================================================")
w("")
w("BEGIN;")
w("")

# ── 1. users ──────────────────────────────────────────────────────────────────
w("-- =============================================================")
w("-- 1. users")
w("-- =============================================================")
for f in farmers:
    kid  = f"seed_farmer_{f['farmer_id']}"
    name = f"{f['address']} {f['crop_name']} 농장"
    w(f"INSERT INTO users (kakao_id, name, handle, onboarded_at)")
    w(f"  VALUES ({esc(kid)}, {esc(name)}, {esc(kid)}, now())")
    w(f"  ON CONFLICT (kakao_id) DO UPDATE")
    w(f"    SET name=EXCLUDED.name, handle=EXCLUDED.handle,")
    w(f"        onboarded_at=EXCLUDED.onboarded_at, updated_at=now();")
    w("")

# ── 2. subscriptions ──────────────────────────────────────────────────────────
w("-- =============================================================")
w("-- 2. subscriptions")
w("-- =============================================================")
for f in farmers:
    kid = f"seed_farmer_{f['farmer_id']}"
    w(f"INSERT INTO subscriptions (user_id)")
    w(f"  SELECT id FROM users WHERE kakao_id={esc(kid)}")
    w(f"  ON CONFLICT (user_id) DO NOTHING;")
    w("")

# ── 3. farm_profiles ──────────────────────────────────────────────────────────
w("-- =============================================================")
w("-- 3. farm_profiles")
w("-- =============================================================")
for f in farmers:
    kid       = f"seed_farmer_{f['farmer_id']}"
    farm_name = f"{f['address']} {f['crop_name']} 농장"
    region    = f["region"]
    w(f"INSERT INTO farm_profiles (user_id, farm_name, region)")
    w(f"  SELECT id, {esc(farm_name)}, {esc(region)}")
    w(f"  FROM users WHERE kakao_id={esc(kid)}")
    w(f"  ON CONFLICT (user_id) DO UPDATE")
    w(f"    SET farm_name=EXCLUDED.farm_name, region=EXCLUDED.region, updated_at=now();")
    w("")

# ── 4. farm_locations (NOT EXISTS로 중복 방지) ────────────────────────────────
w("-- =============================================================")
w("-- 4. farm_locations")
w("-- =============================================================")
for f in farmers:
    kid     = f"seed_farmer_{f['farmer_id']}"
    address = f["address"]
    w(f"INSERT INTO farm_locations (user_id, label, address)")
    w(f"  SELECT u.id, '본농장', {esc(address)}")
    w(f"  FROM users u")
    w(f"  WHERE u.kakao_id={esc(kid)}")
    w(f"    AND NOT EXISTS (SELECT 1 FROM farm_locations fl WHERE fl.user_id=u.id);")
    w("")

# ── 5. crops ──────────────────────────────────────────────────────────────────
w("-- =============================================================")
w("-- 5. crops")
w("-- =============================================================")
for f in farmers:
    kid       = f"seed_farmer_{f['farmer_id']}"
    crop_name = f["crop_name"]
    color     = CROP_COLOR.get(crop_name, "#2BA651")
    w(f"INSERT INTO crops (user_id, name, color_hex)")
    w(f"  SELECT id, {esc(crop_name)}, {esc(color)}")
    w(f"  FROM users WHERE kakao_id={esc(kid)}")
    w(f"  ON CONFLICT (user_id, name) WHERE deleted_at IS NULL DO NOTHING;")
    w("")

# ── 6. farm_diaries + diary_work_blocks ──────────────────────────────────────
w("-- =============================================================")
w("-- 6. farm_diaries + diary_work_blocks")
w("--    멱등: farm_diaries ON CONFLICT DO UPDATE,")
w("--          diary_work_blocks DELETE → INSERT")
w("-- =============================================================")
for f in farmers:
    fid       = f["farmer_id"]
    kid       = f"seed_farmer_{fid}"
    crop_name = f["crop_name"]

    w("")
    w(f"-- [{f['rank']}위] {crop_name} | {f['region']} | farmer_id={fid}")
    w(f"-- 일지 {f['diary_count']}건")

    for diary in f["farm_diaries"]:
        diary_date   = diary["diary_date"]
        memo         = diary.get("memo")
        weather_main = diary.get("weather_main")
        temp_max     = diary.get("temp_max")
        temp_min     = diary.get("temp_min")
        prec         = diary.get("precipitation_mm")
        hum          = diary.get("humidity_pct")
        wsrc         = "AUTO" if weather_main else "MANUAL"

        wb          = diary["diary_work_blocks"][0]
        work_type   = wb["work_type"]
        detail      = wb.get("detail", "")

        w(f"WITH")
        w(f"  _u    AS (SELECT id FROM users        WHERE kakao_id={esc(kid)}),")
        w(f"  _loc  AS (SELECT id FROM farm_locations WHERE user_id=(SELECT id FROM _u) LIMIT 1),")
        w(f"  _crop AS (SELECT id FROM crops          WHERE user_id=(SELECT id FROM _u)")
        w(f"                                             AND name={esc(crop_name)} AND deleted_at IS NULL LIMIT 1),")
        w(f"  _diary AS (")
        w(f"    INSERT INTO farm_diaries")
        w(f"      (user_id, farm_location_id, diary_date, crop_id,")
        w(f"       weather_main, temp_max, temp_min, precipitation_mm, humidity_pct,")
        w(f"       weather_source, memo)")
        w(f"    VALUES (")
        w(f"      (SELECT id FROM _u), (SELECT id FROM _loc),")
        w(f"      {esc(diary_date)}, (SELECT id FROM _crop),")
        w(f"      {esc(weather_main)}, {num(temp_max)}, {num(temp_min)}, {num(prec)}, {num(hum)},")
        w(f"      {esc(wsrc)}, {esc(memo)}")
        w(f"    )")
        w(f"    ON CONFLICT (user_id, farm_location_id, diary_date) WHERE deleted_at IS NULL")
        w(f"    DO UPDATE SET")
        w(f"      weather_main     = {esc(weather_main)},")
        w(f"      temp_max         = {num(temp_max)},")
        w(f"      temp_min         = {num(temp_min)},")
        w(f"      precipitation_mm = {num(prec)},")
        w(f"      humidity_pct     = {num(hum)},")
        w(f"      memo             = {esc(memo)},")
        w(f"      updated_at       = now()")
        w(f"    RETURNING id")
        w(f"  ),")
        w(f"  _del AS (DELETE FROM diary_work_blocks WHERE diary_id=(SELECT id FROM _diary))")
        w(f"INSERT INTO diary_work_blocks (diary_id, work_type, detail, sort_order)")
        w(f"  SELECT id, {esc(work_type)}, {esc(detail)}, 0 FROM _diary;")
        w("")

# ── 푸터 ─────────────────────────────────────────────────────────────────────
w("COMMIT;")
w("")
w(f"-- 완료: 농가 {len(farmers)}개 |",
  f"일지 {sum(len(f['farm_diaries']) for f in farmers)}건 |",
  f"작업블록 {sum(len(d['diary_work_blocks']) for f in farmers for d in f['farm_diaries'])}건")

OUT_PATH.write_text("\n".join(L), encoding="utf-8")
print(f"→ {OUT_PATH}")
print(f"  농가 {len(farmers)}개")
print(f"  일지 {sum(len(f['farm_diaries']) for f in farmers)}건")
print(f"  작업블록 {sum(len(d['diary_work_blocks']) for f in farmers for d in f['farm_diaries'])}건")
print(f"  파일 크기 {OUT_PATH.stat().st_size // 1024} KB")
