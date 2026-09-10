# farmily-ai

Farmily 농업 콘텐츠 생성 AI 파이프라인. Bedrock 기반 에이전트 + 콘텐츠 생성 Lambda +
트렌드 수집 Step Functions + 시드 데이터 생성 스크립트.

## 구조

```
agent/            Bedrock AgentCore 컨테이너 (콘텐츠 생성 에이전트)
                  agent.py · tools.py · prompts/ · Dockerfile
lambdas/          콘텐츠 생성 경로의 개별 Lambda (에이전트 툴)
                  generate-content(오케스트레이터) · get-diary · get-crop-info
                  get-content-history · search-recipe · search-local-specialty
                  search-trend · batch-embed · card-renderer · select-photo · alarm-to-slack
trend-pipeline/   Step Functions: 트렌드 일일 수집·요약 (collectors/ → aggregate-report/)
data-pipeline/    시드 데이터셋 생성 스크립트 (크롤·전처리·SQL 생성). 데이터 파일 미포함
db/               PostgreSQL(+pgvector) 마이그레이션 / seed
```

각 디렉터리에 세부 README 있음.

## 메모

- `agent/`는 조직 레포(`urbanworkteam/AI`)에서 코드만 clean copy로 이관. 커밋 히스토리 미포함.
- `.github/workflows/deploy.yml.disabled` — 원본의 ECS 자동 배포 CI. 조직 인프라 전용이라
  확장자를 바꿔 비활성화(참고용 보존). 내부 경로는 `agent/` 이동을 반영하지 않은 상태.
- 원천/산출 데이터(CSV·대용량 JSON·SQL 덤프)와 `node_modules`는 커밋하지 않는다.
- 모든 설정은 환경변수로 주입. 하드코딩된 자격증명·계정 ID·엔드포인트 없음.
