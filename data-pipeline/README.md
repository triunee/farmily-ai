# data-pipeline

Farmily AI 파이프라인의 시드 데이터셋을 만드는 **생성 스크립트**. 크롤·전처리·정제·SQL 생성 코드만
포함하며, **원천 데이터와 산출 데이터(CSV·대용량 JSON·SQL 덤프)는 저장소에 넣지 않는다**
(용량, 공공데이터 재배포 회피). 아래 순서로 재현한다.

## 폴더 ↔ 데이터셋

| 폴더 | 데이터셋 | 핵심 스크립트 |
|---|---|---|
| `foodnuri/` | 작물 지식 (182종) | `crawl_foodnuri2.py`, `clean_crop_data.py` |
| `recipe/` | 레시피 RAG (~1,025건) | `crawl_10000recipe_final.py`, `recover_dropped.py`, `filter_mismatch_v2.py` |
| `diary/` | 영농일지 시드 (4농가 × 36일지) | `preprocess.py`, `make_custom_selection.py`, `refine_diaries.py`, `generate_seed_sql.py` |
| `diary/` (특산물) | 지역 특산물 RAG | `generate_local_specialty_sql.py` |


## 영농일지 파이프라인

```
공공데이터 CSV (농가·영농정보, ~172k행)      ← 공공데이터포털에서 별도 취득
  → preprocess.py            → crop_region_match.csv
  → make_custom_selection.py → selected_farmers_custom.json (5농가 중간본)
  → refine_diaries.py        → selected_farmers_refined.json (4농가, 2026년, 월 3작업)
  → generate_seed_sql.py     → seed_farming_journals_v2.sql (→ ../db/seeds)
```

## 산출물 → DB 적재

| 대상 | 생성 |
|---|---|
| 영농일지 | `diary/generate_seed_sql.py` → `seed_farming_journals_v2.sql` |
| 레시피 RAG | `recipe/insert_recipes.py` / `diary/generate_sql.py` |
| 작물 지식 | `foodnuri/clean_crop_data.py` → `crop_knowledge` INSERT |
| 지역 특산물 | `diary/generate_local_specialty_sql.py` → `../db/seeds/insert_local_specialty.sql` |

스키마는 `../db/migrations/` 참고.
