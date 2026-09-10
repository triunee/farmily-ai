# Claude Code 실행 프롬프트 — Farmily 영농일지 목업 데이터 전처리

아래 작업을 순서대로 수행해줘.

---

## 전제 파일 구조

작업 전 아래 파일들이 있는지 먼저 확인해줘.

```
data/farming_journal/
├── raw/farming_journal_raw.csv     ← 공공데이터포털 원본 CSV
└── ref/crop_data.json              ← 농식품우리누리 전처리 결과 JSON
```

없으면 즉시 멈추고 경로를 알려줘.

---

## 참고 문서

`farming_journal_preprocessing_prompt.md` 파일을 읽고 전처리 기준으로 사용해줘.
모든 매핑 규칙, 선별 기준, 출력 구조는 해당 문서를 따른다.

---

## 수행 작업

### STEP 1 — 탐색

CSV를 읽고 아래를 출력해줘.
- 전체 행 수, 컬럼명, null 비율
- 농가일련번호별 영농일지 행 수 분포 (min / mean / max / 상위 10개 농가)
- 품종명 unique 목록과 건수
- 농작업명 unique 목록과 건수

인코딩 오류 시 EUC-KR로 재시도해줘.

---

### STEP 2 — 매핑 및 선별

`farming_journal_preprocessing_prompt.md` 의 규칙대로:
1. 품종명 정규화 (완전일치 → 포함관계 → 별칭사전 순)
2. 농가주소에서 시도·시군구 추출 후 `crop_data.json`의 `origin_region`과 교차 검증
3. work_type 매핑 (수확/관수/제초/파종·모내기/경운/기타 농업활동)
4. 필수 조건 4개 + 가점 기준으로 상위 5개 농가 선별

결과를 `data/farming_journal/output/crop_region_match.csv` 로 저장해줘.

---

### STEP 3 — 중복 병합

**같은 `farmer_id + 작성일자` 조합이 여러 행인 경우 반드시 병합해줘.**

```
farm_diaries → 1행 (날짜 기준)
diary_work_blocks → N행 (작업 유형별, sort_order 0부터 순번)
```

병합 후 `data/farming_journal/output/selected_farmers.json` 으로 저장해줘.
JSON 구조는 `farming_journal_preprocessing_prompt.md` 섹션 5를 따라줘.

---

### STEP 4 — SQL 생성

`data/farming_journal/output/seed_farming_journals.sql` 을 생성해줘.

아래 순서로 INSERT문을 작성해줘. 트랜잭션(BEGIN/COMMIT)으로 감싸줘.

```
1. users
   - kakao_id: 'seed_farmer_{farmer_id}'  ← 고유 식별 가능한 mock ID
   - handle:   'seed_farmer_{farmer_id}'  ← 공개 명함 URL용, 반드시 넣어줘
   - onboarded_at: now()                  ← 온보딩 완료 처리

2. subscriptions
   - user_id만 넣으면 나머지는 DEFAULT (FREE 플랜 자동 적용)
   - users INSERT 바로 다음에 위치

3. farm_profiles
4. farm_locations
5. crops  ← color_hex 작물별로 지정 (딸기:#E63946 방울토마토:#F4813F 감귤:#F7B731 등)
6. farm_diaries  ← (farmer_id, diary_date) 기준 1행, 날씨는 null
7. diary_work_blocks  ← 작업 블록 N행, sort_order 순번

마지막에 crop_knowledge INSERT도 추가해줘.
crop_data.json의 선별된 5개 작물 데이터를 crop_knowledge 테이블에 넣어줘.
```

ON CONFLICT 처리를 모든 INSERT에 넣어줘 (멱등성 보장).

---

### STEP 5 — 검증

SQL 파일 생성 후 아래 검증 쿼리를 파일 하단에 주석으로 추가해줘.

```sql
-- 농가별 일지 건수
-- 작업 유형 분포
-- crop_knowledge × 시드 농가 작물 일치 여부
```

그리고 선별된 5개 농가 요약을 콘솔에 출력해줘:
- farmer_id / 작물 / 지역 / 일지 건수 / 작업 유형 목록 / 선별 점수

---

## 최종 출력 파일

```
data/farming_journal/output/
├── crop_region_match.csv        ← 전체 매핑 결과
├── selected_farmers.json        ← 선별 5개 농가 구조화 데이터
├── seed_farming_journals.sql    ← RDS 적재용 SQL (멱등성 보장)
└── parse_errors.csv             ← 파싱 실패 행 (있을 경우)
```

---

## 주의사항

- 파이썬 패키지 설치 필요 시 `pip install pandas python-dateutil chardet` 실행해줘
- 중간에 에러 나도 멈추지 말고 `parse_errors.csv`에 기록하고 계속 진행해줘
- SQL의 모든 문자열 값은 SQL 인젝션 방지를 위해 작은따옴표 이스케이프 처리해줘
- 선별 농가가 5개 미만이면 조건 완화 기준(`farming_journal_preprocessing_prompt.md` 섹션 9)을 적용하고 그 사실을 알려줘
