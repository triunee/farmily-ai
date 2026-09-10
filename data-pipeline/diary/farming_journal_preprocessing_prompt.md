# 영농일기 데이터셋 생성 기준
# farming_journal_preprocessing_prompt.md

> 참조 파일: `claude_code_prompt.md`  
> 대상 DB: Farmily PostgreSQL 스키마 (`V1__init_schema.sql` ~ `V7__create_local_specialty.sql`)  
> 입력 원본: `data/farming_journal/raw/farming_journal_raw.csv` (공공데이터포털)  
> 참조 지식: `data/farming_journal/ref/crop_data.json` (농식품우리누리 크롤링)

---

## 1. 전처리 목표

공공 영농일지 CSV에서 **Farmily DB `crop_knowledge` 테이블의 `origin_region` + `crop_name`이 일치하는 작물**을 재배하는 농가를 선별하여, **5개 농가**의 시드 INSERT SQL을 생성한다.

생성된 시드 데이터는 Farmily의 "영농일지 기반 AI 콘텐츠 생성" 파이프라인의 입력으로 사용된다.

---

## 2. CSV 컬럼 → Farmily DB 매핑 테이블

| CSV 컬럼명 | Farmily 테이블.컬럼 | 처리 방식 |
|---|---|---|
| `영농일지일련번호` | (참고용) | 시드에서는 IDENTITY 자동 생성, 원본 번호는 보존하지 않음 |
| `농가일련번호` | `users.kakao_id`, `users.handle` | `seed_farmer_{농가일련번호}` 형태로 mock ID 생성 |
| `작성일시` | `farm_diaries.diary_date` | §6 날짜 정규화 참고 |
| `농가주소` | `farm_locations.address` / `farm_profiles.region` | §7 주소 파싱 참고 |
| `품종` | `crops.name` | §3 품종명 정규화 참고 |
| `분류` | (참고용) | crop_data.json 매핑 검증에만 사용, DB 저장 불필요 |
| `생육상황명` | `farm_diaries.memo` | `"생육상황: {값}"` 형태로 memo에 포함 |
| `농작업명` | `diary_work_blocks.work_type` + `detail` | §4 작업유형 매핑 참고 |

### 생성 컬럼 (CSV에 없음)

| Farmily 컬럼 | 값 / 규칙 |
|---|---|
| `users.plan` | `'FREE'` 고정 |
| `users.onboarded_at` | `now()` |
| `crops.color_hex` | §8 작물별 색상표 참고 |
| `farm_diaries.weather_source` | `'MANUAL'` 고정 (날씨 데이터 없음) |
| `farm_diaries.weather_main` / `temp_*` / `humidity_pct` | `NULL` |
| `diary_work_blocks.sort_order` | 동일 일지 내 작업 순번, 0부터 시작 |

---

## 3. 품종명 정규화 (3단계)

CSV `품종` 컬럼의 값을 `crop_data.json`의 `crop_name`에 매핑한다.  
아래 순서로 매핑을 시도하고, 첫 번째로 성공한 결과를 채택한다.

### 단계 1 — 완전 일치 (exact match)

```python
if csv_품종 == ck_crop_name:
    return ck_crop_name
```

### 단계 2 — 포함 관계 (substring match)

```python
# CSV 품종이 crop_knowledge 이름을 포함하거나, 역방향도 검사
if ck_crop_name in csv_품종 or csv_품종 in ck_crop_name:
    return ck_crop_name
```

예시: `"설향딸기"` → `"딸기"` / `"대추방울토마토"` → `"방울토마토"`

### 단계 3 — 별칭 사전 (alias dict)

완전·포함 일치 실패 시 아래 사전을 사용한다.

```python
ALIAS = {
    # 딸기 계열
    "설향": "딸기", "죠향": "딸기", "금실": "딸기",
    "매향": "딸기", "킹스베리": "딸기", "장희": "딸기",
    # 토마토 계열
    "방울": "방울토마토", "미니토마토": "방울토마토",
    "완숙토마토": "토마토", "일반토마토": "토마토",
    # 감귤 계열
    "천혜향": "감귤", "레드향": "감귤", "한라봉": "감귤",
    "황금향": "감귤", "청견": "감귤",
    # 기타
    "쌈채소": "상추", "적상추": "상추", "청상추": "상추",
    "배추": "배추", "알배추": "배추",
}

for alias_key, target in ALIAS.items():
    if alias_key in csv_품종:
        return target
```

### 매핑 실패 처리

3단계 모두 실패 시 해당 행을 `parse_errors.csv`에 기록하고 건너뛴다.

```
parse_errors.csv 컬럼: 영농일지일련번호, 농가일련번호, 원본_품종명, 실패_단계, 사유
```

---

## 4. 작업유형(농작업명) 정규화 매핑

`diary_work_blocks.work_type`은 Farmily 앱의 **6종 고정값** 중 하나로 매핑한다.  
원본 `농작업명`은 반드시 `detail` 컬럼에 보존한다.

| CSV `농작업명` 키워드 | `work_type` 매핑값 | 우선순위 |
|---|---|---|
| 수확, 따기, 채취, picking | `수확` | 1 (가장 높음) |
| 파종, 이식, 정식, 모내기, 이앙 | `파종·모내기` | 2 |
| 관수, 물주기, 급수, 점적 | `관수` | 3 |
| 제초, 김매기, 풀뽑기 | `제초` | 4 |
| 경운, 로터리, 쟁기, 갈기 | `경운` | 5 |
| 가지치기, 적엽, 전정, 순치기, 적과, 유인 | `기타 농업활동` | 6 |
| 그 외 모든 작업 | `기타 농업활동` | 7 (기본값) |

매핑 로직:

```python
WORK_MAP = [
    (["수확", "따기", "채취", "picking"],  "수확"),
    (["파종", "이식", "정식", "모내기", "이앙"], "파종·모내기"),
    (["관수", "물주기", "급수", "점적"],   "관수"),
    (["제초", "김매기", "풀뽑기"],         "제초"),
    (["경운", "로터리", "쟁기"],           "경운"),
]

def normalize_work_type(농작업명: str) -> tuple[str, str]:
    for keywords, work_type in WORK_MAP:
        if any(kw in 농작업명 for kw in keywords):
            return work_type, 농작업명
    return "기타 농업활동", 농작업명
```

---

## 5. 선별 농가 JSON 출력 구조 (selected_farmers.json)

`data/farming_journal/output/selected_farmers.json` 의 최종 구조.  
농가 단위 배열이며 각 항목 내 `farm_diaries`는 날짜 기준 1건, `diary_work_blocks`는 N건이다.

```json
[
  {
    "farmer_id": "4843",
    "source_farmer_seq": 4843,
    "farm_name": "충청남도 부여군 방울토마토 농장",
    "region": "충청남도 부여군",
    "address": "충청남도 부여군 세도면 망개로 63",
    "crop_name": "방울토마토",
    "crop_color_hex": "#F4813F",
    "selection_score": 9,
    "matched_crop_knowledge": {
      "crop_name": "방울토마토",
      "origin_region": "충남 부여, 전남 광양"
    },
    "farm_diaries": [
      {
        "diary_date": "2024-01-01",
        "weather_source": "MANUAL",
        "memo": "생육상황: 양호",
        "diary_work_blocks": [
          {
            "sort_order": 0,
            "work_type": "수확",
            "detail": "수확작업"
          }
        ]
      }
    ]
  }
]
```

### 필드 규칙

| 필드 | 규칙 |
|---|---|
| `farmer_id` | `농가일련번호`를 문자열로 변환 |
| `farm_name` | `"{region} {crop_name} 농장"` 형태로 자동 생성 |
| `diary_date` | §6 날짜 정규화 결과 (`YYYY-MM-DD`) |
| `selection_score` | §6 선별 점수 합산 결과 |
| `diary_work_blocks` | 같은 날짜의 작업이 여러 건이면 `sort_order` 0부터 순번 부여 |

---

## 6. 농가 선별 기준 — 필수 4개 조건 + 가점

### 필수 조건 (AND, 4개 모두 충족해야 통과)

| # | 조건명 | 판단 기준 |
|---|---|---|
| ① | 지역-작물 일치 | 농가 주소의 시/도·시군 토큰이 `crop_data.json`의 `origin_region`과 교집합 존재 (§7 매핑 로직 참고) |
| ② | 품종명 정규화 성공 | §3의 3단계 중 하나 이상에서 매핑 성공 |
| ③ | DB 스키마 매핑 가능 | `diary_date`가 유효 날짜로 변환 가능 + `농작업명`이 work_type 6종 중 하나로 매핑 가능 |
| ④ | 주소 유효성 | `농가주소`가 광역시도 명칭(서울·부산·대구·인천·광주·대전·울산·세종·경기·강원·충북·충남·전북·전남·경북·경남·제주) 중 하나로 시작 |

### 가점 기준 (점수 합산 후 상위 5개 선별)

| 가점 항목 | 점수 |
|---|---|
| `work_type` = `수확` | +3 |
| `work_type` = `파종·모내기` | +2 |
| `work_type` = `관수` or `제초` or `경운` | +1 |
| `work_type` = `기타 농업활동` | +0 |
| 생육상황명 값 존재 (NULL/빈문자 아님) | +2 |
| 영농일지 건수 ≥ 3건 (해당 농가 기준) | +2 |
| 영농일지 건수 ≥ 10건 | +1 (추가) |
| `origin_region` 완전 일치 (시+군 모두) | +2 |
| `origin_region` 시/도 단위만 일치 | +1 |
| 작업유형 다양성 ≥ 2종 | +1 |

동점일 경우 **`작성일시` 최신 순**으로 우선 선택한다.  
최종 5개 농가는 반드시 서로 다른 `농가일련번호`여야 한다.

---

## 7. 주소 파싱 — 시도·시군구 추출 로직

```python
# 광역시도 약칭 → 정식명칭 정규화
SIDO_NORMALIZE = {
    "충남": "충청남도", "충북": "충청북도",
    "경남": "경상남도", "경북": "경상북도",
    "전남": "전라남도", "전북": "전라북도",
    "강원": "강원도", "경기": "경기도", "제주": "제주특별자치도",
}

def parse_region(address: str) -> str:
    """
    '충청남도 부여군 세도면 망개로 63' → '충청남도 부여군'
    앞 2개 행정구역 토큰(시도 + 시군구)만 추출한다.
    """
    tokens = address.strip().split()
    if len(tokens) >= 2:
        return f"{tokens[0]} {tokens[1]}"
    return tokens[0] if tokens else ""

def is_region_match(farm_address: str, origin_region: str) -> tuple[bool, int]:
    """
    Returns: (is_match, score)
      score=2 : 시도+시군구 모두 일치
      score=1 : 시도만 일치
      score=0 : 불일치
    """
    regions = [r.strip() for r in origin_region.split(",")]
    for region in regions:
        # 약칭을 정식명칭으로 변환
        for abbr, full in SIDO_NORMALIZE.items():
            region = region.replace(abbr, full)
        tokens = region.split()
        full_match = all(t in farm_address for t in tokens)
        if full_match:
            return True, 2
        sido_match = tokens and tokens[0] in farm_address
        if sido_match:
            return True, 1
    return False, 0
```

---

## 8. 날짜 정규화

CSV `작성일시`는 `YYYY-MM` 또는 `YYYY-MM-DD` 형태로 제공된다.

```python
from datetime import datetime

def parse_date(raw: str) -> str:
    """YYYY-MM → YYYY-MM-01, YYYY-MM-DD → 그대로 반환"""
    raw = str(raw).strip()
    if len(raw) == 7:          # YYYY-MM
        return f"{raw}-01"
    if len(raw) == 10:         # YYYY-MM-DD
        datetime.strptime(raw, "%Y-%m-%d")  # 유효성 검사
        return raw
    raise ValueError(f"날짜 형식 불명: {raw}")
```

파싱 실패 시 `parse_errors.csv`에 기록하고 해당 행 건너뜀.

---

## 9. 작물별 color_hex 지정표

`crops.color_hex`는 작물 유형별로 아래 값을 고정 사용한다.

| 작물명 (정규화 후) | `color_hex` |
|---|---|
| 딸기 | `#E63946` |
| 방울토마토 | `#F4813F` |
| 토마토 | `#E05C4B` |
| 감귤 | `#F7B731` |
| 레드향 | `#F4A332` |
| 사과 | `#D62828` |
| 배 | `#A8D8A8` |
| 포도 | `#7B2D8B` |
| 복숭아 | `#FFB347` |
| 상추 | `#57CC99` |
| 배추 | `#80C675` |
| 고추 | `#C0392B` |
| 오이 | `#52B788` |
| 기본값 (미분류) | `#2BA651` |

---

## 9. 조건 완화 기준 (선별 농가 5개 미만 시)

필수 4개 조건 통과 후 5개 미만이 선별된 경우, 아래 순서로 조건을 단계적으로 완화한다.

### 완화 단계 1 — 주소 유효성 완화

광역시도 시작 요건을 **시/군/구** 수준으로 확장한다.  
예: `"세도면 망개로 63"`처럼 시도 명칭 없이 시작하는 주소도 포함.

```python
# 조건 ④ 완화: 행정구역 접미사가 포함된 주소도 허용
ADMIN_SUFFIXES = ["시", "군", "구", "면", "읍", "동", "리"]
is_valid = any(suf in address[:10] for suf in ADMIN_SUFFIXES)
```

### 완화 단계 2 — 지역-작물 일치 완화

`origin_region` 완전·시도 일치를 모두 포함하되, **동일 `crop_name`을 가진 다른 지역 농가**도 추가한다.  
단, 같은 crop_name을 가진 농가가 3개 초과 시 최신 일지 순으로 3개만 선택.

### 완화 단계 3 — 작물 범위 확장

`crop_data.json`에 없는 작물(`품종명 정규화 실패`)도 허용한다.  
이 경우 `matched_crop_knowledge`를 `null`로 설정하고 SQL에는 포함시키되, 주석으로 표시한다.

### 단계 적용 후 기록 의무

완화 기준 적용 시 콘솔에 반드시 출력한다:

```
[WARN] 선별 농가 {n}개 — 완화 단계 {k} 적용 ({사유})
```

---

## 10. 중복 병합 규칙

### 케이스 A — 같은 `농가일련번호 + 작성일시`가 다른 `영농일지일련번호`

→ `farm_diaries` 1행으로 병합 (날짜 기준)  
→ 각 영농일지의 `농작업명`을 별도 `diary_work_blocks` 행으로 추가  
→ `sort_order`는 `영농일지일련번호` 오름차순으로 0부터 부여

### 케이스 B — 완전 중복 (모든 컬럼 동일)

→ `영농일지일련번호`가 더 작은 행을 대표로 선택하고 나머지 삭제

```python
# 중복 제거 순서
df = df.drop_duplicates()                              # B: 완전 중복
df = df.sort_values("영농일지일련번호")               # A: 날짜 병합 준비
grouped = df.groupby(["농가일련번호", "작성일시"])    # A: 날짜 기준 그룹화
```

---

## 11. SQL INSERT 규칙

### 테이블 INSERT 순서 (외래키 의존 순)

```
1. users
2. subscriptions
3. farm_profiles
4. farm_locations
5. crops
6. farm_diaries
7. diary_work_blocks
8. crop_knowledge  ← 선별 5개 작물에 해당하는 레코드
```

### ON CONFLICT 처리 (멱등성 보장)

| 테이블 | CONFLICT 키 | 처리 |
|---|---|---|
| `users` | `kakao_id` | `DO NOTHING` |
| `subscriptions` | `user_id` | `DO NOTHING` |
| `farm_profiles` | `user_id` | `DO NOTHING` |
| `farm_locations` | `(user_id, label)` | `DO NOTHING` |
| `crops` | `(user_id, name)` WHERE `deleted_at IS NULL` | `DO NOTHING` |
| `farm_diaries` | `(user_id, farm_location_id, diary_date)` WHERE `deleted_at IS NULL` | `DO NOTHING` |
| `diary_work_blocks` | `(diary_id, sort_order)` | `DO UPDATE SET work_type=EXCLUDED.work_type, detail=EXCLUDED.detail` |
| `crop_knowledge` | `(crop_name, season_month)` | `DO NOTHING` |

### SQL 보안 규칙

- 모든 문자열 값의 작은따옴표(`'`)는 `''`로 이스케이프
- 주소, 농장명, 메모 등 자유 텍스트는 파이썬 `str.replace("'", "''")` 적용 후 삽입
- 날짜는 `'YYYY-MM-DD'::DATE` 형태로 명시

---

## 12. 최종 검증 쿼리 (SQL 파일 하단 주석으로 포함)

```sql
-- ===== 검증 쿼리 =====

-- 1. 농가별 일지 건수
SELECT u.kakao_id, COUNT(fd.id) AS diary_count
FROM users u
JOIN farm_diaries fd ON fd.user_id = u.id
WHERE u.kakao_id LIKE 'seed_farmer_%'
GROUP BY u.kakao_id
ORDER BY diary_count DESC;

-- 2. 작업 유형 분포
SELECT dwb.work_type, COUNT(*) AS cnt
FROM diary_work_blocks dwb
JOIN farm_diaries fd ON fd.id = dwb.diary_id
JOIN users u ON u.id = fd.user_id
WHERE u.kakao_id LIKE 'seed_farmer_%'
GROUP BY dwb.work_type
ORDER BY cnt DESC;

-- 3. crop_knowledge × 시드 농가 작물 일치 여부
SELECT c.name AS crop_name, ck.origin_region, ck.season_month
FROM crops c
JOIN users u ON u.id = c.user_id
LEFT JOIN crop_knowledge ck ON ck.crop_name = c.name
WHERE u.kakao_id LIKE 'seed_farmer_%';
```
