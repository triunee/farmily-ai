# farmily-ai

Farmily 농업 콘텐츠 생성 AI 파이프라인. Bedrock 기반 에이전트 + 콘텐츠 생성 Lambda + 트렌드 수집 Step Functions.

## 구조

```
agent/            Bedrock AgentCore 컨테이너 (콘텐츠 생성 에이전트)
                  agent.py · tools.py · prompts/ · Dockerfile
lambdas/          콘텐츠 생성 경로의 개별 Lambda (에이전트 툴)  ── 이관 예정
                  generate-content · get-diary · get-crop-info · get-content-history
                  search-recipe · search-local-specialty · search-trend · batch-embed
                  card-renderer · select-photo · alarm-to-slack
trend-pipeline/   Step Functions: 트렌드 일일 수집·요약 파이프라인  ── 이관 예정
                  collectors/ (datalab-keywords · recipe-trends · youtube-trending)
                  aggregate-report/
db/               스키마 마이그레이션 / seed  ── 이관 예정
```

## 메모

- `agent/`는 조직 레포(`urbanworkteam/AI`)에서 코드만 clean copy로 이관한 것. 커밋 히스토리는 미포함.
- `.github/workflows/deploy.yml.disabled` — 원본의 ECS 자동 배포 CI. 조직 인프라 전용이라 확장자를 바꿔 비활성화(참고용 보존). 경로는 `agent/` 이동 반영 안 된 상태.
