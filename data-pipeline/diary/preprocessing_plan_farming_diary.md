# 농식품 우리누리 영농일지 데이터 전처리 계획

> 출처: [data.go.kr — 농식품 우리누리 영농일지 데이터](https://www.data.go.kr/data/15087366/fileData.do)  
> 목적: 공공 영농일지 CSV → Farmily DB 시드 데이터로 변환  
> 기준 문서: `V1__init_schema.sql`, `V5__create_crop_knowledge.sql`, `Farmily_기획안_v2_4.md`

---

## 1. 전처리 목표

공공 영농일지 데이터에서 **`crop_knowledge` 테이블의 `origin_region` + `crop_name`이 일치하는 작물**을 재배하는 농가를 선별하여, Farmily의 핵심 가치인 **"영농일지 기반 스토리텔링"** 에 활용 가능한 5개 농가의 시드 데이터를 생성한다.

### 선별 기준 (AND 조건)

| 기준 | 설명 |
|---|---|
| ① 지역-작물 일치 | 농가 주소의 시/도·군 정보가 `crop_knowledge.origin_region`과 매칭 |
| ② 스토리텔링 가능성 | 작업 유형(`농작업명`)이 수확·가지치기·적엽 등 **계절적 의미**를 지닌 작업 |
| ③ DB 스키마 매핑 가능 | `farm_diaries` + `diary_work_blocks` 필드로 온전히 변환 가능 |
| ④ 중복 농가 배제 | 동일 `농가일련번호` 내 중복 일지 행 제거 후 대표 1건 선택 |
| ⑤ 주소 정보 충분 | `농가주소`가 시/도 수준 이상의 주소 포함 (단순 번지만 있는 경우 제외) |

---

## 2. 원본 CSV 컬럼 → Farmily DB 매핑 테이블

| CSV 컬럼명 | Farmily 테이블.컬럼 | 처리 방식 |
|---|---|---|
| `영농일지일련번호` | `farm_diaries.id` (참고용) | 시드에서는 신규 IDENTITY 사용 |
| `농가일련번호` | `users.id` (가상 매핑 키) | 농가 단위로 user 레코드 1건 생성 |
| `작성일시` | `farm_diaries.diary_date` | `YYYY-MM` → `YYYY-MM-01` (일 미제공 시 1일로 보정) |
| `농가주소` | `farm_locations.address` + `farm_profiles.region` | 시/도·군 파싱 후 region 추출 |
| `분류` | `crops.name` 보조 분류 (참고용) | DB 저장 불필요, 매핑 검증에만 사용 |
| `품종` | `crops.name` | 정규화 후 crops 테이블 INSERT |
| `생육상황명` | `farm_diaries.memo` 일부 | "생육상황: {값}" 형태로 memo에 포함 |
| `농작업명` | `diary_work_blocks.work_type` + `detail` | 아래 §3 작업유형 매핑 참고 |

---

## 3. 작업유형(농작업명) 정규화 매핑

`diary_work_blocks.work_type`은 Farmily 앱의 6종 고정값으로 매핑한다.

| CSV `농작업명` | `work_type` 매핑값 | `detail` 처리 |
|---|---|---|
| 수확작업, 딸기따기, 방울토마토따기 등 | `수확` | 원본 작업명을 detail에 보존 |
| 가지치기, 적엽 | `기타 농업활동` | 원본 작업명을 detail에 보존 |
| 파종, 모내기 관련 | `파종·모내기` | 원본 작업명을 detail에 보존 |
| 관수, 물주기 관련 | `관수` | 원본 작업명을 detail에 보존 |
| 제초, 김매기 관련 | `제초` | 원본 작업명을 detail에 보존 |
| 경운, 로터리 관련 | `경운` | 원본 작업명을 detail에 보존 |
| 그 외 | `기타 농업활동` | 원본 작업명을 detail에 보존 |

---

## 4. crop_knowledge 기반 지역-작물 매칭 로직

```python
# 매칭 기준: crop_knowledge.origin_region이 농가주소에 포함되는지 확인
# 예시 레코드 (농식품우리누리 크롤링 기준)
#   crop_name="딸기",      origin_region="충남 논산, 경남 진주"
#   crop_name="방울토마토", origin_region="충남 부여, 전남 광양"
#   crop_name="감귤",      origin_region="제주"

def is_region_match(farm_address: str, origin_region: str) -> bool:
    """
    origin_region은 쉼표로 구분된 복수 지역 문자열일 수 있음.
    farm_address의 앞 2개 행정구역 토큰과 교집합 검사.
    """
    regions = [r.strip() for r in origin_region.split(",")]
    for region in regions:
        # 시/도 단위 + 시/군 단위 모두 검사 (e.g. "충남" or "충청남도 부여군")
        tokens = region.replace("충청남도", "충남").replace("경상남도", "경남") \
                       .replace("전라남도", "전남").replace("경상북도", "경북").split()
        if any(token in farm_address for token in tokens):
            return True
    return False
```

---

## 5. 선별 대상 5개 농가 기준 시나리오

아래는 CSV 예시 데이터(이미지 기준)와 `crop_knowledge` 예상 데이터를 교차 분석한 **농가 선별 시나리오**다.  
실제 CSV 다운로드 후 동일 로직으로 검증하여 최종 5건을 확정한다.

| 후보 농가 | 농가일련번호 | 주소(요약) | 작물 | 매칭 origin_region | 대표 작업 | 스토리텔링 포인트 |
|---|---|---|---|---|---|---|
| A농가 | 4843 | 충청남도 부여군 세도면 | 방울토마토 | 충남 부여 | 수확작업 | 부여 방울토마토 첫 수확, 생육상황 "양호" — 당도·신선도 강조 콘텐츠 |
| B농가 | 11149 | 경상남도 진주시 금곡면 | 딸기 | 경남 진주 | 가지치기 | 진주 딸기 생육 관리, 가지치기 시기 스토리 |
| C농가 | 1390 | 충남/경남(원내리) | 딸기 | 경남 진주 | 적엽 | 딸기 잎 정리 — 햇빛 관리·당도 높이는 과정 스토리 |
| D농가 | 1210 | 경상남도 진주시 대곡면 | 딸기 | 경남 진주 | 딸기따기 | 진주 설향딸기 직접 수확 현장감 콘텐츠 |
| E농가 | 1418 | 경상남도 진주시 수곡면 | 딸기 | 경남 진주 | 딸기따기 | 수곡면 딸기 수확, 원외길 농장 위치 스토리 |

> **주의**: 농가일련번호 4843의 방울토마토 행은 영농일지일련번호 2366146/2366147 각 2건씩 중복됨. 중복 제거 후 일련번호 기준 최신 1건만 사용.

---

## 6. 전처리 스크립트 구성 (`preprocess_farming_diary.py`)

```
preprocess_farming_diary/
├── preprocess_farming_diary.py   # 메인 전처리 실행 파일
├── mapper.py                     # 작업유형 정규화, 주소 파싱
├── region_matcher.py             # crop_knowledge 지역-작물 매칭
├── crop_knowledge_mock.json      # 로컬 테스트용 crop_knowledge 목업
├── output/
│   ├── selected_farms.json       # 선별된 5개 농가 원본 데이터
│   └── seed_insert.sql           # Farmily DB INSERT SQL
└── README.md
```

---

## 7. 전처리 단계별 실행 계획

### Step 1. CSV 로드 및 인코딩 처리

```python
import pandas as pd

df = pd.read_csv("farming_diary.csv", encoding="cp949")  # 공공데이터 기본 인코딩
# 컬럼명 공백 제거
df.columns = df.columns.str.strip()
print(df.shape)  # 전체 행 수 확인
```

### Step 2. 중복 행 제거

```python
# 동일 농가+일지일련번호 기준 중복 제거 (영농일지일련번호가 같으면 동일 일지)
df_dedup = df.drop_duplicates(subset=["영농일지일련번호"])
print(f"중복 제거 전: {len(df)}, 제거 후: {len(df_dedup)}")
```

### Step 3. 주소 유효성 필터

```python
# 시/도 수준 주소가 없는 행 제거 (예: "원내리 531-2"만 있는 경우 — 지역 매칭 불가)
VALID_PREFIXES = ["서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종",
                  "경기", "강원", "충북", "충남", "충청", "전북", "전남", "전라",
                  "경북", "경남", "경상", "제주"]
df_valid = df_dedup[df_dedup["농가주소"].apply(
    lambda x: any(x.startswith(p) for p in VALID_PREFIXES)
)]
print(f"주소 유효 행: {len(df_valid)}")
```

### Step 4. crop_knowledge 기반 지역-작물 매칭

```python
import json
from region_matcher import is_region_match

with open("crop_knowledge_mock.json") as f:
    crop_knowledge = json.load(f)  # [{crop_name, origin_region}, ...]

# crop_knowledge에 있는 작물명 목록
ck_map = {item["crop_name"]: item["origin_region"] for item in crop_knowledge}

def check_match(row):
    crop = row["품종"]
    # 품종명 정규화 (예: "방울토마토" → "방울토마토", "설향딸기" → "딸기")
    for ck_crop, origin in ck_map.items():
        if ck_crop in crop or crop in ck_crop:
            return is_region_match(row["농가주소"], origin)
    return False

df_matched = df_valid[df_valid.apply(check_match, axis=1)]
print(f"지역-작물 매칭 행: {len(df_matched)}")
```

### Step 5. 스토리텔링 점수 산정 및 5개 농가 선별

```python
# 스토리텔링 우선순위: 수확 > 가지치기/적엽 > 관수 > 기타
STORYTELLING_PRIORITY = {
    "수확작업": 5, "딸기따기": 5, "방울토마토따기": 5,
    "가지치기": 4, "적엽": 4,
    "파종": 3, "모내기": 3,
    "관수": 2, "제초": 1
}

df_matched["story_score"] = df_matched["농작업명"].map(
    lambda x: STORYTELLING_PRIORITY.get(x, 1)
)

# 농가별 대표 일지 선택 (story_score 높은 것 우선, 동점이면 최신 일지)
df_top = (
    df_matched
    .sort_values(["story_score", "작성일시"], ascending=[False, False])
    .drop_duplicates(subset=["농가일련번호"])
    .head(5)
)

df_top.to_json("output/selected_farms.json", orient="records", force_ascii=False, indent=2)
print(df_top[["농가일련번호", "농가주소", "품종", "농작업명", "story_score"]])
```

### Step 6. Farmily DB INSERT SQL 생성

```python
# 선별된 5개 농가 → seed_insert.sql 생성
# 생성 순서: users → farm_profiles → farm_locations → crops → farm_diaries → diary_work_blocks

from mapper import normalize_work_type, parse_region, parse_date

lines = ["-- Farmily 시드 데이터 — 농식품 우리누리 영농일지 기반", "-- 생성일: AUTO\n"]

for i, row in enumerate(df_top.itertuples(), start=1):
    user_id = 9000 + i  # 시드용 임시 ID (운영 DB에서는 IDENTITY 사용)
    farm_name = f"{parse_region(row.농가주소)} {row.품종} 농장"
    region = parse_region(row.농가주소)
    diary_date = parse_date(row.작성일시)
    work_type, detail = normalize_work_type(row.농작업명)
    memo = f"생육상황: {row.생육상황명}" if row.생육상황명 else None

    lines += [
        f"-- ===== 농가 {i}: 농가일련번호 {row.농가일련번호} =====",
        f"INSERT INTO users (id, kakao_id, name, plan) OVERRIDING SYSTEM VALUE",
        f"  VALUES ({user_id}, 'seed_kakao_{row.농가일련번호}', '{farm_name}', 'FREE');",
        f"INSERT INTO farm_profiles (user_id, farm_name, region)",
        f"  VALUES ({user_id}, '{farm_name}', '{region}');",
        f"INSERT INTO farm_locations (user_id, label, address)",
        f"  VALUES ({user_id}, '본농장', '{row.농가주소}');",
        f"INSERT INTO crops (user_id, name) VALUES ({user_id}, '{row.품종}');",
        f"-- farm_diaries: diary_date={diary_date}, weather_source=MANUAL",
        f"WITH new_diary AS (",
        f"  INSERT INTO farm_diaries (user_id, farm_location_id, diary_date, crop_id,",
        f"    weather_source, memo)",
        f"  SELECT {user_id},",
        f"    (SELECT id FROM farm_locations WHERE user_id={user_id} LIMIT 1),",
        f"    '{diary_date}'::DATE,",
        f"    (SELECT id FROM crops WHERE user_id={user_id} AND name='{row.품종}' LIMIT 1),",
        f"    'MANUAL',",
        f"    {repr(memo) if memo else 'NULL'}",
        f"  RETURNING id",
        f")",
        f"INSERT INTO diary_work_blocks (diary_id, work_type, detail, sort_order)",
        f"  SELECT id, '{work_type}', '{detail}', 0 FROM new_diary;",
        ""
    ]

with open("output/seed_insert.sql", "w", encoding="utf-8") as f:
    f.write("\n".join(lines))

print("seed_insert.sql 생성 완료")
```

---

## 8. 기대 출력물 예시 (`selected_farms.json`)

```json
[
  {
    "농가일련번호": 4843,
    "농가주소": "충청남도 부여군 세도면 망개로 63",
    "품종": "방울토마토",
    "농작업명": "수확작업",
    "생육상황명": "양호",
    "작성일시": "2024-01",
    "매칭_crop_knowledge": {
      "crop_name": "방울토마토",
      "origin_region": "충남 부여"
    },
    "farmily_mapping": {
      "farm_profiles.region": "충청남도 부여군",
      "crops.name": "방울토마토",
      "diary_work_blocks.work_type": "수확",
      "diary_work_blocks.detail": "수확작업",
      "farm_diaries.memo": "생육상황: 양호"
    },
    "storytelling_point": "부여 방울토마토 1월 수확 — 겨울 온실 재배, 생육 양호 → 당도·신선도 강조 콘텐츠로 활용 가능"
  }
]
```

---

## 9. 검증 체크리스트 (Claude Code 실행 전 확인)

- [ ] CSV 파일명 및 인코딩 확인 (`cp949` vs `utf-8-sig`)
- [ ] `crop_knowledge_mock.json`에 방울토마토·딸기 등 주요 작물 `origin_region` 포함 여부
- [ ] 선별된 5개 농가가 서로 다른 `농가일련번호`인지 확인
- [ ] `diary_date` 변환 시 `YYYY-MM` 형식 → `YYYY-MM-01` 보정 적용 여부
- [ ] `seed_insert.sql`의 외래키 참조 순서 (`users` → `farm_locations` → `crops` → `farm_diaries` → `diary_work_blocks`) 준수 여부
- [ ] 동일 `user_id + farm_location_id + diary_date` 조합의 UNIQUE 제약(`uq_diaries_user_loc_date_alive`) 위반 없는지 확인

---

## 10. 스토리텔링 활용 방향 (Farmily AI 콘텐츠 생성 연계)

선별된 5개 농가 데이터는 Farmily의 **영농일지 → AI 콘텐츠 생성** 파이프라인의 시드로 동작한다.

| 농가 유형 | 작업 | AI 콘텐츠 각도 예시 |
|---|---|---|
| 충남 부여 방울토마토 수확 | 수확작업 | "1월 온실 방울토마토 수확 시작, 생육상황 양호 — 겨울에도 싱싱한 이유" |
| 경남 진주 딸기 가지치기 | 기타 농업활동 | "딸기 가지치기의 비밀 — 이 과정이 당도를 결정합니다" |
| 경남 진주 딸기 적엽 | 기타 농업활동 | "잎을 솎아내야 딸기가 달아요 — 진주 딸기 농가의 손길" |
| 경남 진주 딸기따기 (2건) | 수확 | "논산·진주산 딸기 수확 현장 — 당일 수확 당일 발송" |

> `crop_knowledge.origin_region` 일치 데이터이므로 **산지 스토리텔링** (예: "진주 딸기는 왜 맛있을까요?") 및 **제철 캘린더 콘텐츠** 자동 생성에 바로 활용 가능.
