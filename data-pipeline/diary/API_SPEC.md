# REST API 명세서

> Base URL: `/api/v1`. 모든 응답은 [공통 응답 포맷](./CONVENTIONS.md#1-응답-포맷)을 따릅니다. 인증이 필요한 엔드포인트는 `🔒` 표시. 소비자 공개 엔드포인트는 `🌐` 표시. 각 엔드포인트 끝에 요구사항 ID를 명시합니다.

---

## 0. 공통 규약

### Auth 헤더
```
Authorization: Bearer <accessJwt>
X-Trace-Id: <uuid>          # 클라이언트 발급, 서버 그대로 로깅
Accept-Language: ko-KR
```

### 페이지네이션 (cursor 기반 권장)
```
GET /xxx?cursor=<opaque>&limit=20
→ data: [...], nextCursor: "...", hasMore: true
```

### 에러 코드 (예시)
| code | HTTP | 의미 |
| --- | --- | --- |
| `UNAUTHENTICATED` | 401 | 토큰 없음/만료 |
| `INVALID_TOKEN` | 401 | 토큰 위변조 |
| `FORBIDDEN` | 403 | 권한 없음 |
| `NOT_RESOURCE_OWNER` | 403 | 본인 자원 아님 |
| `NOT_FOUND` | 404 | 리소스 없음 |
| `VALIDATION_ERROR` | 422 | 필드 검증 실패 |
| `CREDIT_EXHAUSTED` | 402 | AI 크레딧 소진 |
| `PLAN_LIMIT_EXCEEDED` | 402 | 플랜 한도 초과 |
| `PAYMENT_FAILED` | 402 | 결제 실패 |
| `EXTERNAL_API_ERROR` | 502 | 외부 API 오류 (날씨/PG/카카오 등) |

---

## 1. 인증 (Member 1)

### 1.1 카카오 로그인 — `AUTH-001`
```
POST /api/v1/auth/kakao
Body: { "code": "<kakao auth code>", "redirectUri": "<>" }
Response: {
  "accessToken": "...",
  "refreshToken": "...",
  "expiresIn": 900,
  "isNewUser": true,           // true면 클라이언트가 온보딩으로 라우팅
  "user": { "id": 1, "name": null, "handle": null }
}
```

### 1.2 토큰 갱신
```
POST /api/v1/auth/refresh
Body: { "refreshToken": "..." }
Response: { accessToken, refreshToken, expiresIn }
```
> Refresh는 회전(rotation) — 응답한 새 refresh로 교체, 이전 것은 즉시 무효화.

### 1.3 로그아웃 🔒 — `AUTH-002`
```
POST /api/v1/auth/logout
Body: { "refreshToken": "..." }
Response: { "success": true }
```

### 1.4 회원 탈퇴 🔒 — `AUTH-003`
```
POST /api/v1/auth/withdraw
Body: { "reason": "..." }     # 옵션
Response: { "purgeAt": "2026-06-28T..." }  # 30일 후 영구삭제 일시
```

### 1.5 탈퇴 취소 🔒 (추천 추가)
```
POST /api/v1/auth/withdraw/cancel
Response: { "success": true }
```
> 30일 유예 기간 중 복귀 가능. (요구사항 외 추천)

---

## 2. 마이페이지 / 내 계정 / 재배 작물 (Member 1)

### 2.1 마이페이지 메인 🔒 — `MYPAGE-001`
```
GET /api/v1/mypage
Response: {
  "account": { "name": "김논산", "phone": "010-1234-5678", "email": "nonsan@farm.kr" },
  "crops": { "count": 2, "preview": ["딸기", "방울토마토"] },
  "subscription": {
    "plan": "FREE",
    "creditsUsed": 3,
    "creditsLimit": 5,
    "resetAt": "2026-06-01T00:00:00+09:00"
  }
}
```

### 2.2 내 계정 수정 🔒 — `AUTH-004`
```
PATCH /api/v1/mypage/account
Body: { "name": "...", "email": "..." }
```
> **전화번호는 카카오 OAuth scope에서 받아오는 값이므로 수정 불가** (Q2 결정 부수효과). 마이페이지에 표시만 함. 카카오 계정에서 변경 시 다음 로그인에서 동기화.

### 2.3 ~~비밀번호 변경~~ — Q2 결정: 제거
카카오 OAuth만 지원하므로 자체 비밀번호 없음. 본 엔드포인트는 만들지 않음.

### 2.4 온보딩 — `AUTH-005` (Q3, Q11 반영)
```
POST /api/v1/onboarding
Body: {
  "handle": "kang-strawberry",              // 영문 농장명, [a-z0-9-]{3,30}. Q3
  "farmDisplayName": "강씨네 딸기농장",      // 한글 농장 표시명 (명함 헤더용)
  "region": "충남 논산",
  "farmingMethod": "친환경 재배",
  "crops": [{ "name": "딸기" }, { "name": "방울토마토" }],
  "farmLocation": {                          // Q11: 농장 위치 필수
    "label": "1번 농장",
    "address": "충남 논산시 연무읍 안심리 123"
  }
}
Response: { "user": {...}, "farmProfile": {...}, "crops": [...], "farmLocation": {...} }

Errors:
  422 HANDLE_INVALID_FORMAT  — 영문/숫자/하이픈 외 문자 포함
  409 HANDLE_TAKEN           — 다른 사용자가 이미 사용 중
  422 FARM_LOCATION_REQUIRED — Q11: 농장 위치 미입력
```

> 온보딩 미완료 사용자가 `/onboarding` 외 인증 필요 API 호출 시 `403 ONBOARDING_REQUIRED`.

### 2.4.1 handle 중복 확인 🔒 (온보딩 보조)
```
GET /api/v1/onboarding/handle/check?handle=kang-strawberry
Response: { "available": true|false, "suggestions": ["kang-strawberry-2","..."] }
```

### 2.5 재배 작물 — `MYPAGE-002`
```
GET    /api/v1/crops           🔒  목록
POST   /api/v1/crops           🔒  { name, colorHex?, stage? }
PATCH  /api/v1/crops/{id}      🔒  { name?, colorHex?, stage? }
DELETE /api/v1/crops/{id}      🔒  소프트 삭제 (과거 일지 보존)
```

---

## 3. 농민 프로필 / 명함 (Member 2)

### 3.1 내 명함 조회 🔒 — `PROF-001`
```
GET /api/v1/me/profile
Response: {
  "farm": {
    "farmName": "강씨네 딸기농장",
    "region": "충남 논산",
    "farmingMethod": "친환경 재배",
    "backgroundImageUrl": "...",
    "avatarImageUrl": "...",
    "story": { "text": "...", "imageUrls": [...] }
  },
  "salesChannels": [
    { "channel": "SMARTSTORE", "url": "..." },
    { "channel": "INSTAGRAM", "url": "..." },
    { "channel": "DAANGN", "url": "..." }
  ],
  "blocks": [
    { "id": 1, "blockType": "CROP_INTRO", "sortOrder": 0, "visible": true, "payload": {} },
    { "id": 2, "blockType": "STORY",      "sortOrder": 1, "visible": true, "payload": {} },
    { "id": 3, "blockType": "CALENDAR",   "sortOrder": 2, "visible": true, "payload": {} },
    { "id": 4, "blockType": "TEXT",       "sortOrder": 3, "visible": false, "payload": { "body": "..." } },
    { "id": 5, "blockType": "DIVIDER",    "sortOrder": 4, "visible": true, "payload": {} }
  ]
}
```

### 3.2 명함 편집 🔒 — `PROF-002`
```
PATCH /api/v1/me/profile
Body: {
  "farm": { "farmName": "...", "region": "...", "farmingMethod": "..." },
  "backgroundImageKey": "s3://...",
  "avatarImageKey": "s3://...",
  "story": { "text": "...", "imageKeys": [...] },
  "salesChannels": [ { "channel": "SMARTSTORE", "url": "..." }, ... ]
}
```

### 3.3 명함 블록 재정렬/토글 🔒 (목업 페이지 3, **CSV 일부 반영**)
```
PUT /api/v1/me/profile/blocks
Body: [
  { "id": 1, "sortOrder": 0, "visible": true,  "payload": null },
  { "id": 3, "sortOrder": 1, "visible": false, "payload": null },
  { "id": 4, "sortOrder": 2, "visible": true,  "payload": { "body": "안녕하세요" } }
]
```
```
POST   /api/v1/me/profile/blocks   { blockType: "TEXT", payload: { body } }   # 블록 추가
DELETE /api/v1/me/profile/blocks/{id}                                          # 블록 삭제
```

### 3.4 명함 달력 (영농일지 색상 태그) 🔒 — `PROF-003`
```
GET /api/v1/me/profile/calendar?year=2026&month=5
Response: {
  "days": [
    { "date": "2026-05-07", "tags": [{ "crop": "딸기", "color": "#FF5A5A", "workType": "IRRIGATION" }] },
    { "date": "2026-05-13", "tags": [...] }
  ]
}
```

### 3.5 달력 날짜 인라인 카드 🔒 — `PROF-003`/`DIARY-003`
```
GET /api/v1/me/profile/calendar/{date}
Response: {
  "weather": { "main": "맑음", "tempMax": 24, "tempMin": 12 },
  "diaries": [
    { "id": 11, "crop": "딸기", "workTypes": ["HARVEST"], "memo": "...", "editable": true }
  ]
}
```

### 3.6 판매처 링크 → 외부 이동 — `PROF-004`
> 별도 API 불필요. 클라이언트가 `url`을 그대로 `Linking.openURL` 처리. 클릭 추적이 필요하면 ↓

(추천) 클릭 트래킹:
```
POST /api/v1/me/profile/sales-channels/{id}/click   { source: "PROFILE" }
```

### 3.7 네비게이션 바 — `PROF-005`
> 클라이언트 전용. 서버 API 없음. (단, "현재 사용자가 농민인지/소비자인지" 판단을 위해 `GET /me`)

### 3.8 미리보기 모드 🔒 (목업 페이지 2, **CSV 미반영**)
```
GET /api/v1/me/profile/preview
→ 자기 자신의 명함을 소비자 시점으로 응답 (== 3.9와 동일 스키마)
```

### 3.9 소비자 명함 조회 🌐 — `CONS-001`
```
GET /api/v1/public/farms/{handle}
Response: 3.1 응답에서 편집 버튼 관련 필드 제외 + 본인 식별 필드 제외
```
```
GET /api/v1/public/farms/{handle}/calendar?year=&month=
GET /api/v1/public/farms/{handle}/calendar/{date}
→ 소비자 공개 뷰. visible=false 블록은 미반환.
```

핸들 유효성 검사:
```
GET /api/v1/public/farms/{handle}/exists → { exists: true|false }
```

---

## 4. 영농일지 / 농장 위치 / 날씨 (Member 3)

### 4.1 영농일지 달력 🔒 — `DIARY-001`
```
GET /api/v1/diaries/calendar?year=2026&month=5
Response: 3.4와 동일 구조 (작물별 색상 태그 + 작업 유형 뱃지)
```

### 4.2 일지 단건 조회 🔒 — `DIARY-003`
```
GET /api/v1/diaries/{id}
Response: {
  "id": 11,
  "date": "2026-05-22",
  "farmLocation": { "id": 1, "label": "1번 농장" },
  "crop": { "id": 5, "name": "딸기", "colorHex": "#FF5A5A" },
  "weather": { "main": "맑음", "tempMax": 24, "tempMin": 12, "precipitationMm": 0, "humidityPct": 45, "source": "AUTO" },
  "workBlocks": [
    { "id": 21, "workType": "HARVEST",    "detail": "올해 첫 딸기 수확 시작" },
    { "id": 22, "workType": "IRRIGATION", "detail": "점적관수 30분" }
  ],
  "memo": "...",
  "photos": [{ "id": 31, "url": "...", "sortOrder": 0 }],
  "createdAt": "...", "updatedAt": "..."
}
```

### 4.3 일지 작성 🔒 — `DIARY-002`
```
POST /api/v1/diaries
Body: {
  "date": "2026-05-22",
  "farmLocationId": 1,
  "cropId": 5,
  "weather": { "source": "AUTO" }  // AUTO면 서버가 농장 위치 기반 자동 채움. MANUAL이면 main/tempMax/tempMin 등 명시
  "workBlocks": [
    { "workType": "HARVEST", "detail": "..." },
    { "workType": "IRRIGATION", "detail": "..." }
  ],
  "memo": "...",
  "photoKeys": ["s3://...", "..."]   // ≤5
}
Response: { id, ...4.2 응답 }
```

### 4.4 일지 수정 🔒 — `DIARY-003`
```
PATCH /api/v1/diaries/{id}
Body: 4.3과 동일 (부분 업데이트 허용)
```

### 4.5 일지 삭제 🔒 — `DIARY-005`
```
DELETE /api/v1/diaries/{id}
Response: { "success": true }
- 소프트 삭제. AI 콘텐츠 생성 결과는 영향 없음(이미 생성된 콘텐츠 유지).
```

### 4.6 작업 유형 마스터 🔒 (목업 페이지 8)
```
GET /api/v1/diaries/work-types
Response: [
  { "code": "TILLAGE",       "label": "경운",         "icon": "🌱" },
  { "code": "IRRIGATION",    "label": "관수",         "icon": "💧" },
  { "code": "SEEDING",       "label": "파종·모내기",  "icon": "🌾" },
  { "code": "WEEDING",       "label": "제초",         "icon": "✂️" },
  { "code": "HARVEST",       "label": "수확",         "icon": "🧺" },
  { "code": "OTHER_FARMING", "label": "기타 농업활동","icon": "🚜" },
  { "code": "DAILY",         "label": "하루 일상",    "icon": "🙂" }
]
```

### 4.7 농장 위치 🔒 (목업 페이지 17, **CSV 미반영**)
```
GET    /api/v1/farm-locations
POST   /api/v1/farm-locations    { label, address }   # 서버가 지오코딩 + KMA 격자 자동 계산
PATCH  /api/v1/farm-locations/{id}
DELETE /api/v1/farm-locations/{id}
```

### 4.8 날씨 자동 조회 🔒 — `DIARY-006`
```
GET /api/v1/weather?farmLocationId=1&date=2026-05-22
Response: { main, tempMax, tempMin, precipitationMm, humidityPct, source: "KMA" }
- 캐시 1시간. 격자 X/Y는 farm_locations에 미리 저장.
- 미래 날짜는 단기예보, 과거는 ASOS 관측값.
```

### 4.9 일지 저장 완료 화면 — `DIARY-004`
> 별도 API 불필요. `POST /diaries`의 응답 + 클라이언트 UI 처리.

---

## 5. AI 콘텐츠 생성 (Member 4)

### 5.1 콘텐츠 생성 요청 🔒 — `AI-001`/`AI-002`/`AI-007`
```
POST /api/v1/ai/contents
Body: {
  "platform": "INSTAGRAM" | "SMARTSTORE",
  "cropId": 5,
  "diaryIds": [11, 9, 7] | null,        // null이면 "일지 없이 생성"
  "keywords": "친환경 재배",
  "extraPhotoKeys": ["s3://..."]        // ≤3
}
Response: { "jobId": 101, "status": "QUEUED", "creditsRemaining": 2 }

Errors:
  402 CREDIT_EXHAUSTED → 클라이언트가 플랜 업그레이드 안내
```

### 5.2 콘텐츠 생성 상태 폴링/SSE 🔒 — `AI-003`
```
GET /api/v1/ai/contents/{jobId}
Response: {
  "id": 101,
  "status": "ANALYZING" | "ENRICHING" | "GENERATING" | "DONE" | "FAILED" | "REFUNDED",
  "progressPct": 35,
  "steps": [
    { "key": "ANALYZE_DIARY",   "label": "영농일지 데이터 분석", "done": true },
    { "key": "FETCH_SEASON",    "label": "제철 정보 조회",       "done": true },
    { "key": "GENERATE_CONTENT","label": "콘텐츠 생성 중",       "done": false }
  ],
  "failureReason": null
}

SSE: GET /api/v1/ai/contents/{jobId}/stream  → 같은 페이로드 push
```

### 5.3 콘텐츠 결과 (인스타그램) 🔒 — `AI-004`
```
GET /api/v1/ai/contents/{jobId}/result
Response (INSTAGRAM):
{
  "platform": "INSTAGRAM",
  "cardImageUrls": ["...", "...", "..."],   // 카드뉴스 N장
  "caption": "올해 첫 수확...",
  "hashtags": ["#친환경딸기","#논산딸기","#수확시작","#farmily"]
}
```

### 5.4 캡션/해시태그 편집 🔒 — `AI-004`
```
PATCH /api/v1/ai/contents/{jobId}/result
Body: { "caption": "...", "hashtags": [...] }
```

### 5.5 결과 저장(다운로드 카운트) 🔒
```
POST /api/v1/ai/contents/{jobId}/downloads { kind: "CARD" | "STORE_IMAGE" }
```
> 이미지 자체는 CDN URL로 클라가 직접 다운로드. 이 API는 통계용 카운터.

### 5.6 콘텐츠 결과 (스마트스토어) 🔒 — `AI-005`
```
GET /api/v1/ai/contents/{jobId}/result
Response (SMARTSTORE):
{
  "platform": "SMARTSTORE",
  "cardImageUrls": ["..."]   // 스마트스토어 상세페이지 형식 한 장 또는 여러 섹션
}
```

### 5.7 재생성 🔒 — `AI-006` (Q7 결정)
```
POST /api/v1/ai/contents/{jobId}/regenerate
Body: { "keywords": "...", "extraPhotoKeys": [...] }
Response: { "jobId": 102, "status": "QUEUED", "creditsCharged": false }

정책:
- 같은 원본 job 으로부터 분기한 재생성은 24시간 이내 최대 3회 무료.
- 4회째 또는 24시간 경과 후엔 크레딧 1 차감.
- 재생성 횟수/타임아웃은 응답에 포함:
  "regeneration": { "count": 1, "freeRemaining": 2, "windowEndsAt": "..." }
```

### 5.8 콘텐츠 이력 🔒 — `AI-008`
```
GET /api/v1/ai/contents?platform=INSTAGRAM&cursor=&limit=20
Response: {
  "data": [
    { "id": 101, "platform": "INSTAGRAM", "createdAt": "...", "thumbnailUrl": "...", "caption": "..." }
  ],
  "nextCursor": "...", "hasMore": true
}
```

### 5.9 크레딧 조회 🔒 — `AI-007`
```
GET /api/v1/credits
Response: { "plan": "FREE", "creditsRemaining": 2, "creditsLimit": 5, "resetAt": "..." }
```

---

## 6. 구독 / 결제 (Member 5)

### 6.1 구독 조회 🔒 — `SUB-001`
```
GET /api/v1/subscription
Response: {
  "plan": "FREE",
  "status": "ACTIVE",
  "currentPeriodEnd": "...",
  "autoRenew": false,
  "creditsRemaining": 2,
  "creditsLimit": 5
}
```

### 6.2 결제 내역 🔒 — `SUB-001`
```
GET /api/v1/subscription/payments?cursor=&limit=20
Response: { data: [{ id, plan, amount, status, paidAt, receiptUrl }], nextCursor, hasMore }
```

### 6.3 플랜 목록 🔒 — `SUB-002` (Q8 반영: 시즌패스 표기만)
```
GET /api/v1/subscription/plans
Response: [
  { "code": "FREE",        "name": "Free",     "price": 0,     "period": "MONTHLY",  "creditsLimit": 5,        "features": [...], "disabled": false },
  { "code": "ALL_IN_ONE",  "name": "올인원",   "price": 14900, "period": "MONTHLY",  "creditsLimit": 50,       "features": [...], "recommended": true, "disabled": false },
  { "code": "SEASON_PASS", "name": "시즌 패스","price": 32900, "period": "3_MONTHS", "creditsLimit": null,     "features": ["수확 시즌 집중 사용 플랜"], "disabled": true, "comingSoon": true }
]
```
> 시즌 패스는 UI에 표기만 하고 `disabled: true`로 결제 버튼 비활성. 클라이언트는 "준비 중" 라벨.

### 6.4 결제 시작 🔒 — `SUB-003` (Q14: 포트원)
```
POST /api/v1/subscription/checkout
Body: { "plan": "ALL_IN_ONE" }
Response: {
  "checkoutId": "...",
  "merchantUid": "farmily-...-{checkoutId}",   // 포트원 주문번호
  "pgProvider": "html5_inicis",                 // 또는 "kakaopay", "tosspay" — 클라이언트에서 선택
  "amount": 14900,
  "buyer": { "name": "...", "email": "..." }
}
```

### 6.5 결제 검증 (클라이언트 콜백) 🔒
```
POST /api/v1/subscription/checkout/{checkoutId}/confirm
Body: { "impUid": "imp_...", "merchantUid": "..." }
Response: { "subscription": {...}, "payment": {...} }
- 서버가 포트원 REST API(`GET /payments/{imp_uid}`)로 실제 승인 금액·상태 확인 후에만 ACTIVE 전환.
- impUid + merchantUid + 금액 모두 일치해야 통과.
```

### 6.6 PG 웹훅 (포트원)
```
POST /api/v1/webhooks/payments
Headers: { (포트원 WebhookV2 형식) }
Body: { "imp_uid": "...", "merchant_uid": "...", "status": "paid|failed|cancelled" }
- 자동 결제/결제 실패 시 포트원이 호출. 서버가 포트원 API 재조회로 검증 후 status 반영.
- 결제 실패 시 status=GRACE 전이 (Q10: 7일 후 강등).
```

### 6.7 구독 취소 🔒
```
POST /api/v1/subscription/cancel
Response: { "status": "CANCELED", "validUntil": "..." }
- 즉시 해지가 아니라 currentPeriodEnd까지 유지.
```

---

## 7. 알림 (Member 5)

### 7.1 푸시 토큰 등록 🔒
```
POST /api/v1/push-tokens
Body: { "platform": "IOS"|"ANDROID", "token": "..." }
DELETE /api/v1/push-tokens   { token }
```

### 7.2 알림 설정 🔒 — `NOTI-001`
```
GET   /api/v1/notification-settings
PATCH /api/v1/notification-settings
Body: { "pushEnabled": true, "trendPushEnabled": true, "marketingPushEnabled": false }
```

### 7.3 알림 발송 (내부) — Q13 결정 반영
- 외부 API 아님.
- **NOTI-001 트리거**: 매일 **18:00 (Asia/Seoul) 스케줄러** 가 다음 조건 사용자를 조회 → FCM 푸시:
  - 알림 설정 `pushEnabled=true` 그리고
  - 오늘 영농일지 작성 0건 (`farm_diaries.diary_date = today AND deleted_at IS NULL` 없음)
  - 활성 사용자(최근 30일 내 접속)
- 푸시 본문: "오늘 영농일지를 작성하지 않으셨어요! 영농일지를 기반으로 AI 콘텐츠를 작성해보세요"
- 클라이언트 클릭 시 영농일지 작성 화면 deep link.

---

## 8. 공통 / 업로드 (Member 5)

### 8.1 Presigned URL 🔒
```
POST /api/v1/uploads/presign
Body: { "kind": "diary"|"profile_bg"|"profile_avatar"|"story"|"content_extra", "ext": "jpg", "sizeBytes": 1234567 }
Response: {
  "uploadUrl": "https://...",   // S3 또는 호환 스토리지 presigned PUT
  "key": "users/123/diary/2026/05/abc.jpg",
  "publicUrl": "https://cdn.farmily.kr/.../abc.jpg",
  "expiresIn": 300
}
```

### 8.2 현재 사용자 🔒
```
GET /api/v1/me
Response: { id, name, handle, plan, onboarded }
```

### 8.3 헬스 체크 🌐
```
GET /api/v1/health
Response: { status: "UP", deps: { db: "UP", cache: "UP", pg: "UP" } }
```

---

## 9. 요구사항 ID ↔ 엔드포인트 매핑

| 요구사항 | 엔드포인트 | 담당 |
| --- | --- | --- |
| AUTH-001 | 1.1 | M1 |
| AUTH-002 | 1.3 | M1 |
| AUTH-003 | 1.4, 1.5 | M1 |
| AUTH-004 | 2.2 | M1 |
| AUTH-005 | 2.4 | M1 |
| MYPAGE-001 | 2.1 | M1 |
| MYPAGE-002 | 2.5 | M1 |
| PROF-001 | 3.1 | M2 |
| PROF-002 | 3.2, 3.3 | M2 |
| PROF-003 | 3.4, 3.5 | M2 |
| PROF-004 | 3.6 | M2 |
| PROF-005 | 3.7 (클라) | M2 |
| CONS-001 | 3.8, 3.9 | M2 |
| DIARY-001 | 4.1 | M3 |
| DIARY-002 | 4.3 | M3 |
| DIARY-003 | 4.2, 4.4 | M3 |
| DIARY-004 | 4.9 (클라) | M3 |
| DIARY-005 | 4.5 | M3 |
| DIARY-006 | 4.8 | M3 |
| (신규) 농장위치 | 4.7 | M3 |
| AI-001 | 5.1 | M4 |
| AI-002 | 5.1 | M4 |
| AI-003 | 5.2 | M4 |
| AI-004 | 5.3, 5.4, 5.5 | M4 |
| AI-005 | 5.6, 5.5 | M4 |
| AI-006 | 5.7 | M4 |
| AI-007 | 5.1, 5.9 | M4 |
| AI-008 | 5.8 | M4 |
| SUB-001 | 6.1, 6.2 | M5 |
| SUB-002 | 6.3 | M5 |
| SUB-003 | 6.4, 6.5, 6.6, 6.7 | M5 |
| NOTI-001 | 7.1, 7.2, 7.3 | M5 |
