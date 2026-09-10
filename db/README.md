# db

PostgreSQL 16 (+ pgvector) 스키마.

## migrations/

Flyway 네이밍(`V<n>__<설명>.sql`). 순서대로 적용.

| 버전 | 내용 |
|---|---|
| V1 | 초기 스키마 (users·farms·diaries·content_jobs 등) |
| V2 | checkouts |
| V3 | notification_logs |
| V4 | auth_sessions.ip → varchar |
| V5 | crop_knowledge |
| V6 | pgvector 테이블 (recipe_embeddings 등) |
| V7 | local_specialty |
| V9 | trend_reports |
| V10 | trend_reports 신호(trend_signals) 확장 |

> V8은 결번.

## seeds/

`insert_local_specialty.sql`만 포함(소형). 나머지 시드는 **대용량 데이터라 저장소에서 제외**했다:

| 시드 | 생성 방법 |
|---|---|
| `insert_recipes.sql` (~2.5MB) | `../data-pipeline/recipe/insert_recipes.py` |
| `insert_crop_knowledge.sql` (~480KB) | `../data-pipeline/foodnuri/clean_crop_data.py` |
| `seed_farming_journals_v2.sql` (~200KB) | `../data-pipeline/diary/generate_seed_sql.py` |
