# lambdas

콘텐츠 생성 경로의 개별 Lambda. `generate-content`가 오케스트레이터이고, `get-*`/`search-*`는
Bedrock Agent의 Action Group 툴로 호출된다. `farmily_utils.py`는 모든 Python Lambda가
공유하는 유틸(DB 연결·Bedrock 임베딩·입력 안전 필터·Action Group 응답 헬퍼)로,
각 핸들러가 `sys.path`에 상위 디렉터리를 추가해 import한다. 배포 시에는 함수별 패키지에
이 파일을 동봉한다.

| 폴더 | 런타임 | 역할 |
|---|---|---|
| `generate-content/` | Python | 오케스트레이터. job 발급 → Bedrock Agent invoke → 템플릿에 textPool 주입 → S3/DB 저장 → 렌더 Lambda 호출 |
| `get-diary/` | Python | 영농일지 조회 |
| `get-crop-info/` | Python | 작물 정보 + pgvector 유사도 검색 |
| `get-content-history/` | Python | 과거 생성 콘텐츠 이력 조회 |
| `search-recipe/` | Python | 레시피 RAG 검색 |
| `search-local-specialty/` | Python | 지역 특산물 RAG 검색 |
| `search-trend/` | Python | `trend_reports`/`trend_insights` 조회 (트라이그램 + 벡터 하이브리드). `../trend-pipeline`이 적재한 데이터를 읽는다 |
| `batch-embed/` | Python | `recipe_embeddings`/`local_specialty`/`trend_insights`의 `embedding IS NULL` 행을 Titan V2로 임베딩 |
| `card-renderer/` | Node.js | Puppeteer로 HTML 카드 → PNG 렌더. `node_modules`·폰트 바이너리는 제외 — `fonts/README.md` 보고 폰트 받고 배포 시 `npm i` |
| `select-photo/` | Python | 일지 사진 중 카드용 대표 이미지 선별 |
| `alarm-to-slack/` | Python | CloudWatch 경보 → SNS → Slack Webhook 포맷 변환 |

설정은 전부 환경변수(`os.environ`)로 주입한다. 하드코딩된 자격증명·엔드포인트 없음.
