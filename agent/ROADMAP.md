# AgentCore Instruction 전환 계획

> 작성일: 2026-06-18  
> 최종 업데이트: 2026-06-18  
> 목적: agent_instruction.txt를 SOP 형식으로 전환 + Guardrails 이전 + textPool 확장성 확보 + 헤드라인 규칙 추가

---

## ⚠️ 작업 전 필수 주의사항

### AWS CLI
- 이 프로젝트의 모든 AWS CLI 명령은 반드시 `--profile farmily`를 붙여야 함
- 빠뜨리면 다른 계정으로 실행되어 권한 오류 또는 잘못된 리소스에 접근함
- AWS 계정 ID: `851957594139` (8로 시작) — 명령 결과에 다른 계정 ID가 보이면 즉시 중단하고 사용자에게 확인할 것

### Docker 빌드
- 반드시 `--platform linux/amd64 --provenance=false` 플래그 사용
- ECR URI: `851957594139.dkr.ecr.ap-northeast-2.amazonaws.com/farmily-agentcore:latest`

### Git
- `git pull` 시 항상 `--rebase` 사용

### 작업 디렉토리

| 항목 | 경로 |
|---|---|
| AgentCore | `farmily-lambda/farmily-agentcore/` |
| 백엔드 | `back/` |
| Frontend-web | `Frontend-web/` |
| Terraform | `Infra/Desktop/VPC/environments/prod/` |

---

## 전체 우선순위 요약

> CI/CD · Dockerfile · CloudFront · Instruction 개선을 모두 포함한 실행 순서

| 우선순위 | 작업 | 소요 | 상태 |
|---|---|---|---|
| **P0** | Dockerfile HEALTHCHECK `/health` → `/ping` | 즉시 | 대기 |
| **P1** | AgentCore CI/CD 구성 (GitHub 레포 + IAM + 워크플로우) | 1~2시간 | 대기 |
| **P2** | CloudFront 연동 확인 | 테스트만 | ✅ 코드 완료 |
| **P3-A** | Instruction PHASE 4 + 5 (헤드라인 규칙 + 톤앤매너) | 반나절 | 대기 |
| **P3-B** | Instruction PHASE 1 (Guardrails) | 반나절 | 대기 |
| **P3-C** | Instruction PHASE 2 (SOP 전환) | 1일 | P3-B 완료 후 |
| **P3-D** | Instruction PHASE 3 (파일 분리) | 반나절 | P3-C 완료 후 |
| **P4** | AgentCore Terraform 업데이트 (`agentcore.tf` import + apply) | 반나절 | 대기 |
| **P5** | 카드 뉴스 농민폰 저장 (다운로드 URL API + 프론트 갤러리 저장) | 반나절 | 대기 |
| **P6** | QR 코드 발급 (프로필 공유용) | 반나절~1일 | 대기 |

---

## 변경 범위 요약

| 항목 | 현재 | 변경 후 |
|---|---|---|
| 안전 규칙 | instruction.txt 상단 하드코딩 | Guardrails로 이전, instruction에서 제거 |
| 절차 구조 | 규칙 나열 (마크다운 섹션) | SOP (STEP 1~6, IF/ELSE 명시) |
| 각도별 textPool 가이드 | 8개 각도 × 10필드 전체 하드코딩 | 공통 스키마 + 각도 레지스트리 분리 |
| 헤드라인 작성 규칙 | 없음 | 10글자 룰 + 의미 단위 줄바꿈 추가 |
| 톤앤매너 가이드 | 플랫폼 규칙 2줄 | 전용 섹션으로 강화 |

---

## PHASE 1 — Guardrails 설정

### 1-1. Bedrock 콘솔에서 Guardrail 생성

현재 `## [콘텐츠 안전 규칙 — 최우선]` 섹션 내용을 Guardrails로 이전합니다.

| Guardrails 기능 | 적용 내용 |
|---|---|
| 콘텐츠 필터 | 혐오·차별, 폭력, 성적 표현, 사기·기만 차단 |
| 거부 주제 | "의학적 효능 주장" (암 예방, 당뇨 치료 등) |
| 거부 주제 | "정치·종교적 주장" |
| 거부 주제 | "원산지 허위·미보유 인증 주장" |
| 거부 주제 | "농산물 홍보와 무관한 콘텐츠 요청" |
| 단어 필터 | 명시적 금지 표현 목록 |

### 1-2. agent.py 수정

```python
# 변경 전
_model = BedrockModel(model_id=MODEL_ID, region_name=REGION)

# 변경 후
_model = BedrockModel(
    model_id=MODEL_ID,
    region_name=REGION,
    guardrail_id=os.environ.get("GUARDRAIL_ID"),
    guardrail_version=os.environ.get("GUARDRAIL_VERSION", "1"),
    guardrail_trace="enabled",
)
```

### 1-3. 환경변수 추가

```
GUARDRAIL_ID      = {Bedrock 콘솔에서 발급된 ID}
GUARDRAIL_VERSION = 1
```

ECS 태스크 정의 및 EKS 파드 yaml 양쪽에 추가합니다.

### 1-4. instruction.txt에서 안전 규칙 섹션 제거

`## [콘텐츠 안전 규칙 — 최우선]` 블록 전체 삭제합니다.
- 토큰 절약
- 중복 제거 (Guardrails가 인프라 레벨에서 강제 차단)

---

## PHASE 2 — SOP 절차 전환

### 2-1. instruction.txt 구조 재편

```
[현재]                          [변경 후]
## [콘텐츠 안전 규칙]      →   Guardrails로 이전, 삭제
## [도구 사용 규칙]        →   PART 2 SOP STEP 2~3으로 통합
## [콘텐츠 유형 비율 규칙] →   PART 2 SOP STEP 4으로 통합
## [각도 결정 규칙 — COT]  →   PART 2 SOP STEP 4으로 통합
## [AgentCore Memory 활용] →   PART 2 SOP STEP 4 안에 포함
## [각도별 textPool 가이드]→   PART 3 별도 파일로 분리
## [CTA 방향 가이드]       →   PART 3 톤앤매너 섹션으로 통합
## [영양·효능 표현 가이드] →   PART 3 톤앤매너 섹션으로 통합
## [플랫폼 규칙]           →   PART 3 톤앤매너 섹션으로 통합
## [출력 형식]             →   PART 4 출력 형식으로 유지
```

### 2-2. SOP 절차 구조

```
PART 1. 역할 정의 (3줄 이내)
PART 2. SOP 실행 절차
PART 3. 톤앤매너 가이드 (신규 강화)
PART 4. 출력 형식 (JSON 스키마)
```

### 2-3. SOP 절차 상세 (PART 2)

```
STEP 1: 일지 조회
  IF diaryIds 비어있음
    → get_diary() [최근 일지 1건]
  ELSE
    → FOR EACH id in diaryIds: get_diary(diary_id=id)
  여러 일지 조회 시 날짜 흐름·작업 변화·감정 변화를 연결해 스토리텔링에 활용

STEP 2: 필수 도구 호출 (순서 고정, 항상 실행)
  → get_crop_info()
  → get_content_history()
  → search_trend()

STEP 3: 각도 결정
  3-1. usedAngles 비율 확인
       IF 정보형 < 4건  → 정보형 각도 우선
       IF 공감형 < 3건  → 공감형 각도 우선
       IF 신뢰형 < 2건  → 신뢰형 각도 우선
       IF 판매형 연속 2회 이상 → 판매형 제외
  3-2. 비율 균형 시 Memory 선호도 참고
       /preferences/{actorId} → 선호 각도에 가중치
       /facts/{actorId}       → 지역·작물 맥락 보강
  3-3. 트렌드 결과로 최종 각도 확정
  우선순위: 비율 규칙 > Memory 선호도 > 트렌드

STEP 4: 조건부 도구 호출
  IF 각도 == 레시피
    → search_recipe()
  IF 각도 == 스토리텔링 OR 지역강조
    → search_local_specialty()

STEP 5: textPool 생성
  → PART 3 각도별 가이드 참고
  → 헤드라인 작성 규칙 반드시 준수

STEP 6: JSON 반환
  → PART 4 출력 형식 참고
  → 다른 텍스트 없이 JSON만 출력
```

---

## PHASE 3 — textPool 확장성 확보

### 3-1. 현재 문제

각도가 추가될 때마다 instruction.txt가 선형으로 늘어납니다.

```
현재: 8개 각도 × 10필드 = 80줄 하드코딩
템플릿 추가 시: 각도당 10줄씩 증가 → 토큰 낭비 + 유지보수 어려움
```

### 3-2. 해결 방향: 공통 스키마 + 각도 레지스트리 분리

**공통 textPool 스키마 (instruction.txt에 유지)**

각도와 무관하게 항상 동일한 필드 구조만 정의합니다.

```
textPool 필드 정의:
- mainTitle1 / mainTitle2 / mainTitle3 : 카드별 제목, 반드시 서로 다르게
- subTitle    : 한 줄 요약
- category    : 2~5자 카테고리 태그
- body1 / body2 : 본문 단락 (각 2~3줄)
- highlight1 / highlight2 : 키워드 (한 단어~짧은 구)
- closing     : 마무리 문구 한 줄
- handle      : 입력값 그대로
- cta         : 15자 이내 행동 유도 문구
```

**각도별 가이드는 별도 파일로 분리**

```
prompts/
  base_instruction.txt       ← PART 1~2~3~4 (SOP + 톤앤매너 + 출력형식)
  angles/
    recipe.txt               ← 레시피 각도 가이드
    storage.txt              ← 보관법 각도 가이드
    nutrition.txt            ← 영양 각도 가이드
    seasonal.txt             ← 제철 강조 각도 가이드
    harvest.txt              ← 수확 현장 각도 가이드
    storytelling.txt         ← 스토리텔링 각도 가이드
    regional.txt             ← 지역 강조 각도 가이드
    purchase.txt             ← 구매 유도 각도 가이드
```

**agent.py에서 런타임 조합**

```python
# STEP 3에서 각도 결정 후 해당 가이드만 주입
BASE_PROMPT = open("prompts/base_instruction.txt").read()

ANGLE_GUIDES = {
    "레시피":     open("prompts/angles/recipe.txt").read(),
    "보관법":     open("prompts/angles/storage.txt").read(),
    "영양":       open("prompts/angles/nutrition.txt").read(),
    "제철강조":   open("prompts/angles/seasonal.txt").read(),
    "수확현장":   open("prompts/angles/harvest.txt").read(),
    "스토리텔링": open("prompts/angles/storytelling.txt").read(),
    "지역강조":   open("prompts/angles/regional.txt").read(),
    "구매유도":   open("prompts/angles/purchase.txt").read(),
}
```

> 단, Strands Agent는 요청마다 새 인스턴스를 생성하므로,
> 각도 결정을 사전에 할 수 없는 구조입니다.
> 현실적 대안은 아래 두 가지입니다.

**대안 A — 2-pass 방식 (각도 먼저 결정 후 주입)**

```python
# 1차 호출: 각도만 결정
angle_agent = Agent(model=_model, system_prompt=ANGLE_DECISION_PROMPT)
angle = angle_agent(agent_input)  # "레시피" 반환

# 2차 호출: 해당 각도 가이드 포함한 풀 프롬프트로 생성
full_prompt = BASE_PROMPT + "\n\n" + ANGLE_GUIDES[angle]
content_agent = Agent(model=_model, tools=_TOOLS, system_prompt=full_prompt)
result = content_agent(agent_input)
```

**대안 B — 현재 구조 유지 + 각도 파일만 분리 관리 (권장)**

```python
# instruction.txt = base + 전체 각도 가이드 조합 (현재와 동일)
# 단, 각도 파일을 별도 관리하여 추가·수정이 쉽게
SYSTEM_PROMPT = BASE_PROMPT + "\n\n".join(ANGLE_GUIDES.values())
```

템플릿이 추가되어도 `prompts/angles/`에 파일 하나 추가하면 끝.
instruction.txt 본문은 건드리지 않아도 됩니다.

---

## PHASE 4 — 헤드라인 작성 규칙 추가

instruction.txt의 `textPool 작성 규칙` 섹션에 아래 내용을 추가합니다.

### 추가 위치

`PART 3 톤앤매너 가이드` 또는 `textPool 작성 규칙` 섹션 상단

### 추가 내용

```
■ 헤드라인 작성 규칙 (mainTitle1 / mainTitle2 / mainTitle3 공통 적용)

[글자 수]
- 한 줄 최대 10글자 (이모지 포함)
- 초과 시 반드시 줄바꿈

[줄바꿈 규칙]
- 줄바꿈은 반드시 의미 단위로 끊는다
- 단어 중간 절대 금지
- 줄바꿈이 필요하면 \n으로 명시

나쁜 예: "도시농부의 특별한 하우스 수\n박 이야기"  ← 단어 중간 분리
좋은 예: "도시농부의\n특별한 수박 이야기"          ← 의미 단위 분리

[검증 절차]
줄바꿈 전 작성 후, \n으로 나눈 각 조각이 10글자 이하인지 확인한 뒤 출력합니다.
```

---

## PHASE 5 — 톤앤매너 가이드 강화

현재 `## [플랫폼 규칙]` 2줄을 아래 전용 섹션으로 교체합니다.

### 추가할 내용 (초안)

```
■ 전체 톤앤매너

- 농민의 실제 목소리: 과장·광고 문체 금지, 현장감 있는 구어체
- 신뢰 우선: 판매 강요 없이 공감·정보로 먼저 신뢰를 쌓는다
- 수치 활용: 수확량·당도·온도 등 구체적 수치를 적극 활용
- 감성적 짧은 문장: 한 문장에 한 생각, 긴 수식어 지양

■ 이모지 사용 규칙

- 전체 2~4개 (단락마다 넣지 말 것)
- 농업·자연 관련 이모지 권장 (🌱🍓🌾🥕 등)
- 제목 끝에 관련 이모지 1개 포함

■ 금지 표현

- "최고", "1등", "독보적" 등 근거 없는 최상급 표현
- "지금 바로 구매", "한정 수량" 등 압박성 판매 문구 (판매형 각도 제외)
- 의학적 효능 직접 주장 (Guardrails에서도 차단)
- 경쟁 농장·브랜드 비교 표현

■ 플랫폼별 규칙

인스타그램:
- 감성적, 짧은 문장, 이모지 절제
- 해시태그 10개 이내
- instagramCaption 최소 350자, 단락 4~7개

스마트스토어:
- 현재 미구현 → instagram 형식으로 생성, platform 필드에 "smartstore" 명시
- 추후 정보 중심·신뢰감·구체적 수치 강조 형식으로 확장 예정
```

---

## 작업 순서 및 의존성

```
PHASE 1  Guardrails 생성 + agent.py 환경변수 추가
  └─ 완료 조건: Guardrail 트리거 시 응답 차단 확인

PHASE 2  instruction.txt SOP 전환
  └─ 의존: PHASE 1 완료 후 안전 규칙 섹션 제거
  └─ 완료 조건: STEP 순서대로 도구 호출 확인

PHASE 3  textPool 파일 분리 (대안 B)
  └─ 의존: PHASE 2 완료 후 base 분리
  └─ 완료 조건: 각도 파일 추가 시 instruction 본문 수정 불필요

PHASE 4  헤드라인 규칙 추가
  └─ 의존: PHASE 2 (SOP 전환) 완료 후 PART 3에 추가
  └─ 완료 조건: mainTitle 출력 시 줄당 10글자 이하 유지

PHASE 5  톤앤매너 강화
  └─ 의존: PHASE 2와 병행 가능
  └─ 완료 조건: 금지 표현 미출력, 이모지 규칙 준수 확인
```

---

## 완료 후 파일 구조

```
farmily-agentcore/
  agent.py                        ← GUARDRAIL_ID 환경변수 추가
  prompts/
    base_instruction.txt          ← PART 1~4 (SOP + 톤앤매너 + 출력형식)
    angles/
      recipe.txt
      storage.txt
      nutrition.txt
      seasonal.txt
      harvest.txt
      storytelling.txt
      regional.txt
      purchase.txt
  agent_instruction.txt           ← 기존 파일 (백업 유지)
```

---

## 최종 실행 계획

### P0 — Dockerfile HEALTHCHECK 수정 (즉시)

ECS 태스크 정의의 헬스체크는 `/ping`인데 Dockerfile은 `/health`로 불일치.
CI/CD 파이프라인 연결 전에 반드시 수정해야 매 배포 시 올바른 상태 유지됨.

```dockerfile
# 변경 전
HEALTHCHECK CMD curl -f http://localhost:8080/health || exit 1

# 변경 후
HEALTHCHECK CMD curl -f http://localhost:8080/ping || exit 1
```

완료 조건: Dockerfile 수정 → 빌드 + 배포 → ECS 헬스체크 HEALTHY 확인

---

### P1 — AgentCore CI/CD 구성

#### 1-1. GitHub 레포 생성

- 조직: `urbanworkteam`, 레포명: `AgentCore`
- 현재 `farmily-lambda/farmily-agentcore/` 파일들을 루트로 이동

#### 1-2. IAM Role 생성 (AWS 콘솔)

```
이름:    farmily-cicd-agentcore-role
신뢰 관계:
  - token.actions.githubusercontent.com (OIDC)
  - 조건: repo:urbanworkteam/AgentCore:*

권한 정책 (인라인):
  ECR:
    - ecr:GetAuthorizationToken
    - ecr:BatchCheckLayerAvailability
    - ecr:GetDownloadUrlForLayer
    - ecr:BatchGetImage
    - ecr:InitiateLayerUpload
    - ecr:UploadLayerPart
    - ecr:CompleteLayerUpload
    - ecr:PutImage
    Resource: arn:aws:ecr:ap-northeast-2:851957594139:repository/farmily-agentcore

  ECS:
    - ecs:DescribeTaskDefinition
    - ecs:RegisterTaskDefinition
    - ecs:UpdateService
    - ecs:DescribeServices
    Resource: *

  IAM PassRole:
    - iam:PassRole
    Resource:
      - arn:aws:iam::851957594139:role/farmily-agentcore-execution-role
      - arn:aws:iam::851957594139:role/farmily-agentcore-task-role
```

#### 1-3. GitHub Secrets / Variables

| 종류 | 이름 | 값 |
|---|---|---|
| Secret | `AWS_ROLE_ARN` | farmily-cicd-agentcore-role 의 ARN |
| Secret | `AWS_ACCOUNT_ID` | `851957594139` |
| Secret | `SLACK_WEBHOOK_URL` | 기존 것 재사용 |
| Variable | `AWS_REGION` | `ap-northeast-2` |

#### 1-4. `.github/workflows/deploy.yml` 구조

```yaml
on:
  push:
    branches: [main]      # ci + 빌드 + prod 배포
  pull_request:
    branches: [main]      # ci만

jobs:
  ci:
    # pytest (또는 생략 — 초기엔 pass-through)

  push-image:
    needs: ci
    if: github.ref == 'refs/heads/main'
    # aws-actions/configure-aws-credentials (OIDC)
    # docker build --platform linux/amd64 --provenance=false
    # 태그: prod-<sha>, latest
    # ECR push

  deploy-prod:
    needs: push-image
    # aws-actions/amazon-ecs-render-task-definition
    # aws-actions/amazon-ecs-deploy-task-definition
    # cluster: prod-cluster, service: farmily-agentcore-service
    # wait-for-service-stability: true
    # Circuit Breaker 활성화 → 실패 시 자동 롤백
    # 완료 후 Slack 알림
```

완료 조건: `main` push 시 ECR 이미지 업데이트 + ECS 서비스 자동 재배포 확인

---

### P2 — CloudFront 연동 확인 (코드 변경 없음)

백엔드 코드 및 ECS 환경변수 이미 완료된 상태:

| 항목 | 상태 |
|---|---|
| `S3Service.toDisplayUrl()` — CDN URL 변환 로직 | ✅ 구현 완료 |
| `AiResultService` — 카드 이미지 전체 키 변환 | ✅ `Arrays.stream(...).map(s3Service::toDisplayUrl)` |
| `AiHistoryService` — 썸네일 키 변환 | ✅ `s3Service.toDisplayUrl(keys[0])` |
| ECS 환경변수 `CDN_BASE_URL` | ✅ `https://d3kn4x06d72wh.cloudfront.net` |

확인 작업: 콘텐츠 생성 후 `/api/ai/result/{jobId}` 응답의 `cardImageUrls`가 CloudFront 도메인인지 확인

---

### P3-A — Instruction PHASE 4 + 5 (헤드라인 + 톤앤매너, 병행 가능)

- `agent_instruction.txt` 파일만 수정 → 배포만 하면 즉시 적용
- CI/CD 구성 완료 후 main push 한 번으로 반영
- 콘텐츠 품질 개선 중 가장 빠른 효과

완료 조건:
- mainTitle 출력 시 줄당 10글자 이하
- 금지 표현 미출력, 이모지 2~4개 범위 유지

---

### P3-B — Instruction PHASE 1 (Guardrails)

- Bedrock 콘솔에서 Guardrail 생성 (10~20분)
- `agent.py` 환경변수 `GUARDRAIL_ID`, `GUARDRAIL_VERSION` 추가
- ECS 태스크 정의 환경변수 추가 → 재배포
- `agent_instruction.txt` 안전 규칙 섹션 제거 (토큰 절약)

완료 조건: 금지 주제 입력 시 Guardrail이 차단 응답 반환 확인

---

### P3-C — Instruction PHASE 2 (SOP 전환)

- 의존: P3-B 완료 후 안전 규칙 섹션 제거 가능
- `agent_instruction.txt` 전체 구조 재편 (PART 1~4 + SOP STEP 1~6)
- 가장 큰 작업 — 기존 instruction 백업 유지 후 진행

완료 조건: Claude 응답에서 STEP 순서대로 도구 호출 확인 (get_diary → get_crop_info → get_content_history → search_trend)

---

### P3-D — Instruction PHASE 3 (파일 분리)

- 의존: P3-C 완료 후 base 구조 확정 시
- `prompts/` 디렉토리 생성 + 각도별 파일 분리
- `agent.py` 프롬프트 로드 방식 변경

완료 조건: 새 각도 추가 시 `prompts/angles/` 파일 추가만으로 반영되는지 확인

---

### P4 — AgentCore Terraform 업데이트

현재 `Infra/Desktop/VPC/environments/prod/main.tf`에는 `agentcore` SG만 정의됨.
나머지 리소스(IAM 역할, CloudWatch, Cloud Map, ECS 태스크 정의, ECS 서비스)는 콘솔로 생성됐으나 Terraform 미반영.

**작업 순서:**

1. `Infra/Desktop/VPC/environments/prod/agentcore.tf` 파일 생성  
   → `agentcore-terraform-guide.md` 섹션 5 내용 기반

2. `terraform import` 실행 (`agentcore-terraform-guide.md` 섹션 6 명령어)

   ```bash
   # environments/prod/ 디렉토리에서 실행
   terraform import aws_iam_role.agentcore_execution farmily-agentcore-execution-role
   terraform import aws_iam_role.agentcore_task farmily-agentcore-task-role
   terraform import aws_iam_role_policy.agentcore_task_policy farmily-agentcore-task-role:farmily-agentcore-task-policy
   terraform import aws_cloudwatch_log_group.agentcore /ecs/farmily-agentcore
   terraform import aws_service_discovery_private_dns_namespace.farmily ns-ogane3a6tfd7phgb
   terraform import aws_service_discovery_service.agentcore srv-clkjfikhj5k4z6ph
   terraform import aws_ecs_task_definition.agentcore farmily-agentcore
   terraform import aws_ecs_service.agentcore prod-cluster/farmily-agentcore-service
   ```

3. `terraform plan` → drift 확인 → `terraform apply`

4. `main.tf`의 `aws_security_group.agentcore` 인라인 블록을 `agentcore.tf`로 이동 고려  
   (현재 main.tf에 있는 SG를 분리하면 관련 리소스가 한 파일에 모임)

완료 조건: `terraform plan` 결과 no changes (또는 의도된 태그 추가만)

---

### P5 — 카드 뉴스 농민폰 저장

**현재 상태:**
- `POST /api/v1/ai/contents/{jobId}/downloads` — API 존재, 카운트 미구현 (TODO 주석)
- `S3Service.presignGet()` — presigned GET URL 생성 가능
- `S3Service.toDisplayUrl()` — CloudFront URL 반환 (CDN_BASE_URL 설정 시)

**구현 방향:**

`d3kn4x06d72wh.cloudfront.net` 배포가 `farmily-s3-bucket`을 오리진으로 서빙 중.  
CloudFront에 서명 요구(trusted_key_groups/trusted_signers) 없음 → **공개 접근 가능**.  
백엔드 추가 API 불필요. 기존 `GET /{jobId}/result` 응답의 `cardImageUrls`(CloudFront URL)를 그대로 사용.

**프론트엔드 (React Native / Expo):**

```js
// cardImageUrls는 기존 result API 응답에 이미 포함 (CloudFront URL)
import * as MediaLibrary from 'expo-media-library';
import * as FileSystem from 'expo-file-system';

for (const url of cardImageUrls) {
  const filename = url.split('/').pop();
  const fileUri = FileSystem.documentDirectory + filename;
  await FileSystem.downloadAsync(url, fileUri);
  await MediaLibrary.saveToLibraryAsync(fileUri);
}
```

기존 `POST /{jobId}/downloads` 엔드포인트에서 다운로드 카운트 기록 구현 추가.

완료 조건: 카드 이미지 생성 후 기기 갤러리에 저장 확인

---

### P6 — QR 코드 발급

**용도:** 농민 공개 프로필 페이지 공유 (`https://farmily.info/@{handle}`)

**구현 방향: 프론트엔드 라이브러리로 렌더링 (백엔드 불필요)**

QR 타겟 URL이 `farmily.info/@{handle}`로 고정이므로 handle만 있으면 생성 가능.

**앱 (React Native):**
```js
import QRCode from 'react-native-qrcode-svg';

<QRCode value={`https://farmily.info/@${handle}`} size={200} />
```
갤러리 저장 필요 시 `getRef()` → SVG → PNG 변환 후 `expo-media-library` 사용.

**Front-web ProfilePage:**
```js
import { QRCodeSVG } from 'qrcode.react';

<QRCodeSVG value={`https://farmily.info/@${handle}`} size={160} />
```
소비자가 명함 페이지에서도 QR 확인·저장 가능.

완료 조건: QR 스캔 시 `farmily.info/@{handle}` 프로필 페이지 이동 확인

---

### 전체 순서 요약

```
[P0] Dockerfile /ping 수정 + 빌드 배포
  ↓
[P1] CI/CD 구성 (레포 → IAM → Secrets → deploy.yml)
  ↓
[P2] CloudFront 연동 테스트 (변경 없음, 확인만)
  ↓
[P3-A] Instruction PHASE 4+5 (instruction.txt 수정 → CI/CD로 배포)
  ↓
[P3-B] Instruction PHASE 1 (Guardrails 생성 + agent.py 수정)
  ↓
[P3-C] Instruction PHASE 2 (SOP 전환)
  ↓
[P3-D] Instruction PHASE 3 (파일 분리)

[P4] AgentCore Terraform import + apply (독립적, P1 이후 언제든 가능)

[P5] 카드 뉴스 농민폰 저장 (독립적, S3 공개 여부 확인 후 진행)

[P6] QR 코드 발급 (독립적, 구현 방식 확정 후 진행)
```
