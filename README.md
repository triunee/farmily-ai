# farmily-ai

농부의 **영농일지 데이터를 소셜 미디어 콘텐츠로 자동 생성**하는 AI 파이프라인.
인스타그램 캡션·해시태그, 카드 이미지용 텍스트(textPool), 스마트스토어 상세 문구를
Bedrock(Claude) 기반 에이전트가 만들고, 카드 이미지를 렌더링해 S3에 저장한다.

이 저장소는 Farmily의 AI 파이프라인 전체를 한곳에 모은 스냅샷이다 — 현행 에이전트
컨테이너(`agent/`), 콘텐츠 생성·유틸 Lambda(`lambdas/`), 시드 데이터 생성 스크립트
(`data-pipeline/`), DB 스키마(`db/`).

---

## 전체 아키텍처 (현행)

```
[Spring Boot 백엔드]
    │  BedrockAgentClient.invoke() → POST /invocations
    ▼
[에이전트 컨테이너]  ECS Fargate(prod-cluster)
    │  bedrock_agentcore SDK의 BedrockAgentCoreApp 으로 /invocations, :8080 노출
    │  에이전트 루프는 Strands Agents SDK로 직접 구현 (관리형 런타임 아님)
    │
    ├─ ① prefetch — 핸들러에서 병렬 사전조회 (LLM 왕복 없음, ThreadPoolExecutor)
    │     ├ get_diary            영농일지 조회
    │     ├ get_crop_info        작물 정보
    │     ├ get_content_history  과거 콘텐츠 이력 (각도 비율 계산용)
    │     └ search_trend         트렌드 하이브리드 검색 (pg_trgm + pgvector)
    │
    ├─ ② Strands Agent (claude-3-5-sonnet-v2, APAC)
    │     각도(angle) 결정 → 조건부 도구만 자율 호출
    │     ├ @tool search_recipe          각도 = 레시피
    │     └ @tool search_local_specialty 각도 = 스토리텔링 / 지역강조
    │
    ├─ ③ Claude가 JSON 콘텐츠 생성 (caption · hashtags · textPool)
    │
    ▼
[farmily-card-renderer Lambda]  Puppeteer로 HTML 카드 → PNG, S3 저장
    │
    ▼
[RDS PostgreSQL 16 + pgvector]  결과 저장 · job 상태 DONE
```

### 도구 6개, 왜 4 + 2로 나눴나

6개 도구 함수는 모두 Strands `@tool` 로 정의돼 있지만 노출 방식이 다르다.

- **항상 필요한 결정적 조회 4개** (`get_diary` · `get_crop_info` · `get_content_history` ·
  `search_trend`) — LLM에 노출하지 않고 핸들러에서 `ThreadPoolExecutor` 로 **병렬 사전조회**해
  프롬프트에 주입한다. LLM 왕복이 사라져 지연·토큰이 줄어든다.
- **각도에 따라 갈리는 조건부 검색 2개** (`search_recipe` · `search_local_specialty`) — `_TOOLS`
  로 에이전트에 넘겨 Claude가 각도를 정한 뒤 필요할 때만 호출한다.

`tools.py` 의 각 함수는 Action Group Lambda를 거치지 않고 `farmily_utils.get_connection()` 으로
DB를 직접 조회한다.

---

## 콘텐츠 각도 (prompts/angles/)

Claude가 일지·이력을 보고 아래 중 하나를 골라 그 각도의 가이드(`prompts/angles/*.txt`)로 작성한다.

| 각도 | 내용 | 각도 | 내용 |
|---|---|---|---|
| `harvest` | 수확 현장 | `seasonal` | 제철 강조 |
| `nutrition` | 영양 정보 | `storage` | 보관법 |
| `purchase` | 구매 유도 | `storytelling` | 농부 스토리 |
| `recipe` | 레시피 활용 | `regional` | 지역 특산 |
| `smartstore` | 스마트스토어 상세 | | |

---

## job 진행 상태 (progress_pct)

| 단계 | status | progress |
|---|---|---|
| 요청 수신 | ANALYZING | 10% |
| Agent 초기화 완료 | ENRICHING | 30% |
| Agent 응답 완료 | GENERATING | 60% |
| DB 저장 완료 | GENERATING | 70% |
| 카드 렌더링 완료 | DONE | 100% |

---

## 디렉터리 구조

```
agent/                          에이전트 컨테이너 (현행) — ECS Fargate에서 실행
├── agent.py                    @app.entrypoint 핸들러 (BedrockAgentCoreApp) — prefetch → Strands Agent → 카드 렌더 → DB
├── tools.py                    @tool 6개 (prefetch 4 + LLM 노출 2), DB 직접 조회
├── farmily_utils.py            DB 커넥션 풀 · Bedrock 임베딩 · 입력 안전 필터
├── prompts/
│   ├── base_instruction.txt    System Prompt 기본 지침
│   └── angles/*.txt            콘텐츠 각도별 가이드 9종
├── setup_memory.py             AgentCore Memory 초기화
├── Dockerfile · requirements.txt
└── ROADMAP.md

lambdas/                        콘텐츠 생성 경로의 개별 Lambda + 유틸
├── farmily_utils.py            Python Lambda 공유 유틸 (Action Group 응답 헬퍼 포함)
├── generate-content/           레거시 오케스트레이터 — Bedrock 관리형 Agent invoke_agent 호출
├── get-diary/ get-crop-info/ get-content-history/
├── search-recipe/ search-local-specialty/ search-trend/
│                               ↑ tools.py 로 흡수되기 전의 Action Group Lambda 버전
├── batch-embed/                embedding IS NULL 행을 Titan V2로 임베딩 (배치)
├── card-renderer/              Node.js · Puppeteer HTML→PNG (node_modules·폰트 제외)
├── select-photo/               일지 사진 중 카드용 대표 이미지 선별
└── alarm-to-slack/             CloudWatch 경보 → SNS → Slack

data-pipeline/                  시드 데이터셋 생성 스크립트 (크롤·전처리·SQL 생성)
├── foodnuri/                   작물 지식 (~182종)
├── recipe/                     레시피 RAG (~1,025건)
└── diary/                      영농일지 시드 (4농가 × 36일지) · 지역 특산물 RAG
                                ※ 원천·산출 데이터 파일은 미포함, README에 재현 순서

db/
├── migrations/                 Flyway V1~V10 (pgvector 테이블 포함)
└── seeds/                      소형 seed만 (대용량은 data-pipeline 스크립트로 생성)
```

각 디렉터리에 세부 README 있음.

### 두 세대의 오케스트레이션

- **레거시**: `lambdas/generate-content` → `bedrock-agent-runtime.invoke_agent()` (관리형 Agent)
  → Action Group Lambda(`get-*`, `search-*`) → 템플릿 주입 → 카드 렌더.
- **현행**: Spring 백엔드 → `agent/` 컨테이너 (Strands + prefetch) → 카드 렌더.
  Action Group Lambda의 로직은 `agent/tools.py` 의 `@tool` 로 이관됨.

두 경로의 코드를 모두 보존해 변천 과정을 남겼다.

---

## 인프라

- **런타임**: ECS Fargate (`prod-cluster`). 컨테이너는 `bedrock_agentcore` SDK의
  `BedrockAgentCoreApp` 으로 표준 호출 인터페이스(`/invocations`, :8080)만 노출하고,
  에이전트 루프는 Strands Agents SDK로 직접 구현 (Bedrock 관리형 런타임 아님)
- **서비스 디스커버리**: Cloud Map (`farmily-agentcore.farmily.local`)
- **로그 / 메트릭**: CloudWatch Logs `/ecs/farmily-agentcore`, 커스텀 메트릭 `Farmily/AgentCore`
- **CI/CD**: GitHub Actions → ECR Push → ECS Rolling Deploy
  (`.github/workflows/deploy.yml.disabled` — 조직 인프라 전용이라 이 저장소에서는 비활성)
- **DB**: RDS PostgreSQL 16 + pgvector

### 주요 환경변수

| 변수 | 설명 |
|---|---|
| `MODEL_ID` / `AWS_REGION` | Bedrock 모델 ID · 리전 |
| `DB_HOST` / `DB_USER` / `DB_PASSWORD` (또는 `DB_PASSWORD_SECRET_ARN`) | RDS 접속 |
| `CARD_RENDERER_LAMBDA` | 카드 렌더러 Lambda 함수명 |
| `GUARDRAIL_ID` / `GUARDRAIL_VERSION` | Bedrock Guardrail (미설정 시 비활성) |
| `AGENTCORE_MEMORY_ID` | AgentCore Memory (미설정 시 비활성) |

---

## 메모

- `agent/`는 조직 레포(`urbanworkteam/AI`)에서 코드만 clean copy로 이관. 커밋 히스토리 미포함.
- 원천/산출 데이터(CSV·대용량 JSON·SQL 덤프), `node_modules`, 폰트 바이너리는 커밋하지 않는다
  (폰트는 `lambdas/card-renderer/fonts/README.md` 참고).
- 모든 설정은 환경변수로 주입한다. 하드코딩된 자격증명·계정 ID·엔드포인트 없음.
