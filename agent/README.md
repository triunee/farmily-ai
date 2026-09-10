# Farmily AI

농부 소셜 미디어 콘텐츠 자동 생성 AI 에이전트. 영농일지 데이터를 기반으로 인스타그램 캡션, 해시태그, 카드 이미지용 텍스트를 생성합니다.

---

## 아키텍처

```
[Spring Boot 백엔드]
    └→ ECS Fargate 컨테이너 (BedrockAgentCoreApp HTTP 하니스, port 8080)
         │
         ├─ ① prefetch — 핸들러에서 병렬 사전조회 (LLM 왕복 없음)
         │     ├→ get_diary            # 영농일지 조회
         │     ├→ get_crop_info        # 작물 정보 조회
         │     ├→ get_content_history  # 콘텐츠 이력 (각도 비율 계산용)
         │     └→ search_trend         # 트렌드 하이브리드 검색 (pg_trgm + pgvector)
         │
         └─ ② Strands Agent (claude-3-5-sonnet-v2 APAC) — 각도 결정 후 조건부 도구만 호출
               ├→ @tool search_recipe          # 레시피 검색 (각도=레시피)
               └→ @tool search_local_specialty # 지역 특산물 (각도=스토리텔링/지역강조)
                     └→ farmily-card-renderer (Lambda) # 카드 이미지 생성
```

> 6개 도구 함수는 모두 `@tool` 로 정의돼 있으나, **항상 필요한 결정적 조회 4개**(get_diary·get_crop_info·get_content_history·search_trend)는 LLM에 노출하지 않고 핸들러에서 `ThreadPoolExecutor` 로 **병렬 사전조회(prefetch)** 해 왕복을 제거한다. **각도에 따라 갈리는 조건부 검색 2개**(search_recipe·search_local_specialty)만 `_TOOLS` 로 에이전트에 넘겨 LLM이 자율 호출한다.
>
> 컨테이너는 `bedrock_agentcore` SDK의 `BedrockAgentCoreApp` 으로 표준 호출 인터페이스(`/invocations`, :8080)를 노출하며, **ECS Fargate** 에서 실행된다. 에이전트 루프는 Strands Agents SDK로 직접 구현한다.

---

## 폴더 구조

```
farmily-agentcore/
├── agent.py              # 메인 엔트리포인트 (@app.entrypoint)
├── tools.py              # @tool 함수 6개 (prefetch 4 + LLM 노출 2)
├── farmily_utils.py      # DB 연결 등 공통 유틸
├── prompts/
│   ├── base_instruction.txt      # System Prompt 기본 지침
│   └── angles/                   # 콘텐츠 각도별 가이드
│       ├── harvest.txt           # 수확 현장
│       ├── nutrition.txt         # 영양 정보
│       ├── purchase.txt          # 구매 유도
│       ├── recipe.txt            # 레시피 활용
│       ├── regional.txt          # 지역 특산
│       ├── seasonal.txt          # 제철 강조
│       ├── storage.txt           # 보관법
│       └── storytelling.txt      # 농부 스토리
├── requirements.txt
├── Dockerfile
└── .github/
    └── workflows/
        └── deploy.yml            # CI/CD (PR 오픈 → CI, main 머지 → 빌드+ECS 배포)
```

---

## 주요 흐름

1. Spring Boot가 `BedrockAgentClient.invoke()` 로 에이전트 컨테이너의 `/invocations` 엔드포인트 호출
2. `handler()` 에서 DB 컨텍스트 조회 + 결정적 도구 4개를 병렬 prefetch
3. prefetch 결과를 주입해 Strands Agent 실행 → 각도 결정 후 조건부 도구(레시피/지역)만 호출
4. Claude가 JSON 형식의 콘텐츠(caption, hashtags, textPool) 생성
5. `farmily-card-renderer` Lambda 호출 → 카드 이미지 S3 저장
6. DB에 결과 저장 후 `DONE(100%)` 상태 업데이트

---

## 진행 상태 (progress_pct)

| 단계 | 상태 | progress |
|------|------|----------|
| 요청 수신 | ANALYZING | 10% |
| Agent 초기화 완료 | ENRICHING | 30% |
| Agent 응답 완료 | GENERATING | 60% |
| DB 저장 완료 | GENERATING | 70% |
| 카드 렌더링 완료 | DONE | 100% |

---

## 환경변수

| 변수 | 설명 |
|------|------|
| `MODEL_ID` | Bedrock 모델 ID |
| `AWS_REGION` | AWS 리전 |
| `DB_HOST` / `DB_USER` / `DB_PASSWORD` | RDS 접속 정보 |
| `CARD_RENDERER_LAMBDA` | 카드 렌더러 Lambda 함수명 |
| `GUARDRAIL_ID` / `GUARDRAIL_VERSION` | Bedrock Guardrail |
| `AGENTCORE_MEMORY_ID` | AgentCore Memory ID (미설정 시 비활성) |
| `PYTHONUNBUFFERED` | `1` 고정 — CloudWatch 로그 즉시 전송 |

---

## 인프라

- **런타임**: ECS Fargate (`prod-cluster`) — `BedrockAgentCoreApp` 하니스로 패키징한 Strands 에이전트 컨테이너
- **서비스 디스커버리**: Cloud Map (`farmily-agentcore.farmily.local`)
- **로그**: CloudWatch Logs `/ecs/farmily-agentcore`
- **모니터링**: CloudWatch 커스텀 메트릭 `Farmily/AgentCore` 네임스페이스
- **CI/CD**: GitHub Actions → ECR Push → ECS Rolling Deploy
