"""
selected_farmers_custom.json 기반 정제 v3
- 나주 배(farmer_id=3059) 제거
- 월별 중요 작업 3개 선별 (작업 유형 다양성 우선)
- 각 작업을 월 내 랜덤한 날짜로 분리 (초·중·말 3구간에서 각 1개)
- 2024 → 2026년 변경
- 메모: 계절·작물·월 맥락에 맞는 실감나는 농민 일지 스타일
- 2026-06-07 이전 날짜: Open-Meteo 실제 날씨 (없으면 계절 합성값)
- farm_diaries 스키마 호환 구조 출력
"""
import json, random, calendar, urllib.request, urllib.parse
from pathlib import Path

BASE = Path(__file__).parent
IN_PATH  = BASE / "data/farming_journal/output/selected_farmers_custom.json"
OUT_PATH = BASE / "data/farming_journal/output/selected_farmers_refined.json"

TODAY = "2026-06-07"

WORK_PRIORITY = {
    "수확":        6,
    "파종·모내기":  5,
    "관수":        4,
    "경운":        3,
    "제초":        2,
    "기타 농업활동": 1,
}

FARMER_COORDS = {
    7569: (36.19, 127.10),  # 논산 딸기
    9746: (34.77, 127.08),  # 보성 키위
    4843: (36.27, 126.91),  # 부여 방울토마토
    9437: (38.15, 127.31),  # 철원 파프리카
}

REGION_TEMP_DELTA = {
    7569:  0.0,
    9746: +3.0,
    4843: -0.5,
    9437: -5.0,
}

SEASONAL_BASE = {
     1: ("맑음",    3.5,  -5.5,  0.5, 55),
     2: ("구름조금",  6.0,  -3.0,  1.0, 58),
     3: ("구름많음", 12.0,   2.5,  3.0, 60),
     4: ("구름조금", 18.5,   8.0,  4.5, 62),
     5: ("맑음",   24.0,  13.5,  4.0, 65),
     6: ("비",     27.5,  19.0, 13.0, 80),
     7: ("비",     30.5,  23.0, 20.0, 87),
     8: ("구름많음", 31.0,  23.5, 16.0, 83),
     9: ("맑음",   25.5,  15.5,  6.5, 73),
    10: ("맑음",   18.0,   7.5,  2.0, 65),
    11: ("구름조금", 10.5,   1.5,  2.5, 65),
    12: ("맑음",    4.5,  -3.0,  0.8, 58),
}

# 계절·작물별 실감나는 농민 일지 스타일 메모
# 키: (월, 월, ...) 튜플 → 해당 월에 자연스러운 내용
MEMO_POOL = {
    "딸기": {
        (12, 1, 2): [
            "새벽 6시에 하우스 들어가 수확 시작했다. 오늘따라 딸기 색이 참 곱게 물들었다. 아내랑 둘이서 세 시간 만에 끝냈는데 상품이 잘 나와서 기분이 좋다.",
            "어젯밤 기온이 많이 떨어졌다. 하우스 보온 커튼 이중으로 내렸는데 다행히 동해 피해는 없었다. 설 전에 물량 맞추느라 하루하루가 바쁘다.",
            "수확량이 예년보다 20%쯤 많은 것 같다. 색도 균일하고 크기도 좋다. 올겨울 날씨가 딸기하기 딱 맞게 맞아줬다.",
            "진딧물이 조금 보여서 오전에 방제 작업을 했다. 잡고 보니 얼마 없었지만 이 시기엔 빠른 대처가 중요하다. 수확량은 꾸준히 나오고 있다.",
            "수확하고 선별하고 포장까지 하니 오후 3시가 됐다. 허리가 아프지만 출하할 때마다 보람을 느낀다.",
            "찬 바람이 세게 불었다. 하우스 측창 단속 잘 됐는지 다시 확인했다. 딸기는 추울수록 달아진다고 하는데 오늘 보니 정말 그런 것 같다.",
        ],
        (3, 4): [
            "수확이 이제 끝물에 접어들었다. 알이 작아졌지만 맛은 여전히 달다. 이번 시즌 큰 병 없이 마무리된 것 같아 다행이다.",
            "포기가 많이 지쳤다. 수확량이 줄면서 선별 비율도 낮아졌다. 슬슬 포기 정리 준비를 해야겠다.",
            "마지막 수확을 마쳤다. 올 시즌도 별 탈 없이 끝났다. 하우스 정리하면서 잠깐 뿌듯함이 느껴졌다.",
            "동생 가족이 도와주러 왔다. 포기 정리하고 잔재물 치우는 데 하루가 꼬박 걸렸다. 저녁에 막걸리 한 잔으로 마무리.",
        ],
        (5, 6): [
            "런너에서 자묘를 받기 시작했다. 올해는 모주 상태가 좋아서 자묘가 튼튼하게 나온다. 다음 시즌을 준비하는 느낌이 든다.",
            "장마가 시작됐다. 하우스 배수 상태 확인하고 환기 관리에 신경 쓰고 있다. 자묘는 잘 크고 있어서 걱정은 없다.",
            "오늘 자묘 수가 충분히 확보됐다. 이제 포트에 옮겨 심는 일만 남았다. 8월 말 정식을 목표로 잘 키워봐야겠다.",
        ],
        (7, 8): [
            "무더위가 기승이다. 자묘가 열에 약해서 차광망을 설치했다. 하루에 두 번씩 물 주는 게 일과가 됐다.",
            "차광막을 추가로 쳤다. 자묘 잎이 타는 것 같아 걱정이 됐는데 오후에 보니 다시 살아났다. 여름을 잘 버텨줘야 한다.",
            "자묘 활착률이 80% 정도 된다. 나머지도 살아날 것 같다. 8월 하순 정식까지 시간이 조금 남았다.",
        ],
        (9, 10): [
            "오늘 정식을 마쳤다. 허리가 끊어질 것 같지만 활착만 잘 되면 된다. 올해 정식이 작년보다 사흘 늦어졌다.",
            "비 예보가 있어서 정식을 서둘렀다. 아내와 일꾼 한 명이 도와줘서 하루 만에 끝낼 수 있었다. 내년 봄이 벌써 기대된다.",
            "정식 일주일째. 활착 상태가 예상보다 좋다. 새 잎이 올라오는 걸 보니 마음이 놓인다.",
        ],
        (11,): [
            "첫 꽃이 피기 시작했다. 이 시기 야간 온도 관리가 가장 중요해서 보온 커튼을 꼼꼼히 내렸다.",
            "하우스 안 온도가 낮으면 화아분화가 늦어진다. 야간 가온기 점검하고 온도 로거 수치 확인했다.",
            "꽃이 점점 많아지고 있다. 적화 작업 시작 시기를 가늠 중이다. 이 시기 날씨가 올겨울 수확량을 결정하는 것 같다.",
        ],
    },

    "키위": {
        (1, 2): [
            "겨울전정 작업 중이다. 올해 가지 상태가 좋아서 전정이 수월하다. 일꾼 두 명이 도와줘서 예상보다 빨리 끝났다.",
            "전정 가지가 많이 나왔다. 솎아주면서 수세 균형을 맞추는 게 핵심이다. 매년 하는 일인데 여전히 신경이 많이 쓰인다.",
            "오늘 전정을 마무리했다. 내년에 신초가 어떻게 나올지 벌써 기대된다. 전정을 잘한 해가 수확량도 많더라.",
            "전정 후 수세 회복을 위해 퇴비를 추가로 넣었다. 땅이 차가워도 미생물이 살아있다는 걸 믿어야 한다.",
        ],
        (3, 4): [
            "신초가 예년보다 1주일쯤 빠르게 올라오고 있다. 봄 기온이 높아서 그런 것 같다. 유인 작업 준비를 서둘러야겠다.",
            "꽃이 피기 시작했다. 인공수분 타이밍을 잡는 게 관건이다. 날씨가 맑아야 수분이 잘 되는데 비 예보가 걱정된다.",
            "수분 작업 3일째다. 아들이 주말에 내려와서 도와줬다. 덕분에 큰밭까지 한 번에 끝낼 수 있었다.",
            "수정이 잘 됐는지 확인하는 중이다. 아직 확신은 없지만 꽃 상태가 좋았으니 기대해본다.",
        ],
        (5, 6): [
            "착과 상태가 좋다. 열매가 너무 많이 달려서 오늘부터 적과 시작했다. 솎아줘야 남은 과실이 굵어진다.",
            "적과 작업이 며칠째 이어지고 있다. 손가락이 아프지만 이 과정이 있어야 좋은 과실이 나온다.",
            "나뭇가지가 처질 정도로 과실이 달렸다. 지주 보강 작업을 추가로 했다. 비대 속도가 빠르다.",
        ],
        (7, 8): [
            "봉지씌우기를 마무리했다. 생각보다 시간이 오래 걸렸지만 병해 예방을 위해 꼭 필요한 작업이다.",
            "장마 기간이라 병해 걱정이 앞선다. 약제 살포하고 배수로 점검했다. 봉지 씌운 덕에 마음이 조금 놓인다.",
            "과실 비대가 빠르게 진행 중이다. 올해 크기가 유난히 크게 자라는 것 같다. 수확이 기대된다.",
        ],
        (9, 10): [
            "드디어 수확을 시작했다. 올해 키위 크기가 예년보다 크고 당도가 좋다. 수확하면서 절로 웃음이 났다.",
            "수확 물량이 많아서 일꾼을 추가로 불렀다. 저장고에 들어가는 과실 상태가 마음에 든다.",
            "수확 마지막 날이다. 올해 생산량이 작년보다 10% 이상 늘었다. 힘든 한 해였지만 보람이 있다.",
        ],
        (11, 12): [
            "저장고에서 에틸렌 후숙 처리 중이다. 후숙 타이밍을 잘 맞춰야 당도가 살아난다.",
            "출하 전 선별 작업. 상품 비율이 높게 나와서 다행이다. 다음 시즌 준비도 슬슬 생각해야겠다.",
            "올 시즌이 마무리됐다. 몸은 고단하지만 과수원 보면서 내년 계획을 세우는 게 낙이다.",
            "수확 끝나고 시비 작업 마쳤다. 내년 봄을 위한 밑거름이다. 나무들이 잘 쉬어줬으면 한다.",
        ],
    },

    "방울토마토": {
        (12, 1, 2): [
            "새벽 기온이 영하로 떨어졌지만 하우스 안은 따뜻하다. 방울토마토 착색이 균일하게 잘 되고 있다. 오늘 선별하고 나니 상품 비율이 90%가 넘는다.",
            "야간 가온기가 말썽을 부렸다. 새벽에 알람 듣고 일어나 수리하느라 진땀 뺐다. 다행히 토마토 피해는 없었다.",
            "수확한 방울토마토 포장하고 출하 준비 마쳤다. 오늘따라 색이 특히 예뻐서 사진도 찍었다.",
            "하우스 보온 커튼 점검했다. 찬바람이 조금 새는 곳이 있어서 테이프로 막았다. 작은 것 하나가 수확량 차이를 만든다.",
        ],
        (3, 4): [
            "낮 기온이 올라오면서 환기 관리가 중요해졌다. 아직 수확이 잘 되고 있어서 마음은 편하다.",
            "봄이 오니 착색 속도가 빨라졌다. 수확 주기를 조금 앞당겼다. 상품성이 더 좋아진 것 같다.",
            "가격이 조금 내려갔지만 물량이 많이 나오고 있다. 이럴 때 품질 관리를 더 철저히 해야 한다.",
            "줄기 유인 작업 했다. 잘 뻗어주고 있어서 기분이 좋다. 열매가 고르게 달리려면 유인을 꼼꼼히 해줘야 한다.",
        ],
        (5, 6): [
            "낮 최고 기온이 30도 가까이 올라갔다. 환기창 최대로 열고 차광막 추가로 쳤다. 열과 발생이 걱정된다.",
            "장마가 시작되면서 흰가루병이 조금 보인다. 예방 차원에서 약제 살포했다. 습도 관리가 관건이다.",
            "고온으로 수정이 잘 안 되는 것 같다. 적심하고 화방 관리에 집중하고 있다. 여름을 잘 버텨야 한다.",
        ],
        (7, 8): [
            "장마가 길어지고 있다. 습도가 높아서 병해 걱정이 앞선다. 환기를 최대한 하고 있지만 역부족인 것 같다.",
            "무더위가 기승이다. 오전에만 수확하고 오후엔 하우스 관리에 집중했다. 체력 소모가 심하다.",
            "잿빛곰팡이 초기 증상이 보인다. 감염된 잎 바로 제거하고 약제 살포했다. 빠른 대처가 중요하다.",
        ],
        (9, 10): [
            "가을 작기 정식을 마쳤다. 묘 상태가 좋아서 활착이 빠를 것 같다. 겨울 수확을 기대해본다.",
            "여름을 잘 버텨준 덕에 가을 수확이 이어지고 있다. 선선한 날씨에 착색이 더 균일해졌다.",
            "선선해지니 일하기 훨씬 수월하다. 착과가 늘어나는 게 눈에 보인다. 이 맛에 농사짓는다.",
        ],
        (11, 12): [
            "겨울 하우스 보온 작업 완료했다. 이중 커튼까지 쳤으니 이번 겨울은 든든하다.",
            "초기 생육 상태가 좋다. 새 줄기가 빠르게 올라오고 있어서 기대가 된다. 내년 1~2월 수확이 기대된다.",
            "정식한 지 두 주 됐다. 활착은 잘 됐는데 이제 첫 화방 관리를 신경 써야 할 시기다.",
        ],
    },

    "파프리카": {
        (12, 1, 2): [
            "철원 겨울은 역시 다르다. 밖은 영하 15도인데 하우스 안은 따뜻하다. 파프리카 색이 고르게 잘 들고 있다.",
            "야간 보온 커튼 이중으로 내렸다. 가온비가 많이 나오지만 이 시기를 잘 버텨야 봄에 생산량이 살아난다.",
            "수확한 파프리카 선별 작업. 수출용 규격에 맞춰야 해서 선별 기준이 까다롭다. 그래도 상품 비율이 잘 나왔다.",
            "하우스 보일러 점검 맡겼다. 이 시기에 보일러 고장 나면 큰일이라 미리미리 관리하는 게 답이다.",
        ],
        (3, 4): [
            "봄이 오면서 파프리카 생육이 눈에 띄게 빨라졌다. 수확량도 늘어나고 착색도 더 균일해진다.",
            "기온이 올라가면서 환경 제어가 바빠졌다. CO2 시비 농도 조절하고 관비량 조금 늘렸다.",
            "봄 수확이 한창이다. 날이 좋으니 파프리카 색깔이 더 선명하다. 출하하면서 뿌듯하다.",
        ],
        (5, 6): [
            "낮 기온이 하우스 안에서 40도까지 올라갔다. 차광과 환기를 최대한 열었다. 파프리카가 고온에 민감해서 걱정이다.",
            "착과율이 떨어지기 시작했다. 고온 때문인 것 같다. 야간 온도를 낮춰주는 게 최선이다.",
            "여름 버티기가 시작됐다. 관비 횟수 늘리고 EC 낮춰서 뿌리 부담 줄이는 중이다.",
        ],
        (7, 8): [
            "장마 기간 중 습도 관리가 핵심이다. 잿빛곰팡이 예방 약제 살포했다. 환기창을 최대한 열어두고 있다.",
            "무더위와의 싸움이다. 이 시기만 버티면 가을에 생산량이 회복된다. 물 관리를 더 세심하게 하고 있다.",
            "여름에 파프리카 키우는 게 매년 힘들다. 그래도 올해는 병 발생이 덜해서 그나마 낫다.",
        ],
        (9, 10): [
            "선선해지면서 파프리카 착색이 좋아졌다. 빨간색이 특히 예쁘게 물들고 있다.",
            "가을 수확이 한창이다. 수출 물량 맞추느라 선별이 바쁘다. 올해 품질이 좋아서 바이어 반응이 좋다.",
            "드디어 여름을 넘겼다. 가을 수확량이 늘어나는 게 보인다. 이제부터가 진짜 시작이다.",
        ],
        (11, 12): [
            "새 작기 시작. 파프리카 정식 마치고 활착 상태 확인 중이다. 초기 뿌리 발달이 중요한 시기다.",
            "겨울이 시작되면서 보온 커튼 점검했다. 철원은 타 지역보다 보온에 신경을 두 배는 써야 한다.",
            "정식 후 첫 열매가 달리기 시작했다. 착과 상태가 균일해서 기대가 된다.",
        ],
    },
}


def get_memo(crop_name, month, rng, used_memos):
    """계절·작물에 맞는 메모를 중복 없이 선택"""
    crop_pool = MEMO_POOL.get(crop_name, {})
    for month_tuple, memos in crop_pool.items():
        if month in month_tuple:
            unused = [m for m in memos if m not in used_memos]
            chosen = rng.choice(unused if unused else memos)
            used_memos.add(chosen)
            return chosen
    all_memos = [m for memos in crop_pool.values() for m in memos]
    return rng.choice(all_memos) if all_memos else "오늘도 무사히 작업 마쳤다."


# ── 작업 선별 ─────────────────────────────────────────────────────────────────

def pick_top3(work_blocks):
    def score(b):
        return (WORK_PRIORITY.get(b["work_type"], 1),
                1 if b.get("detail", "").strip() else 0)

    sorted_blocks = sorted(work_blocks, key=score, reverse=True)
    selected, seen_types, seen_details = [], set(), set()

    for b in sorted_blocks:
        if len(selected) >= 3: break
        wt, det = b["work_type"], b.get("detail", "").strip()
        if wt not in seen_types and (not det or det not in seen_details):
            seen_types.add(wt)
            if det: seen_details.add(det)
            selected.append(b)

    if len(selected) < 3:
        for b in sorted_blocks:
            if len(selected) >= 3: break
            det = b.get("detail", "").strip()
            if b not in selected and (not det or det not in seen_details):
                if det: seen_details.add(det)
                selected.append(b)

    if len(selected) < 3:
        for b in sorted_blocks:
            if len(selected) >= 3: break
            if b not in selected: selected.append(b)

    return selected[:3]


# ── 날짜 랜덤화 ───────────────────────────────────────────────────────────────

def random_dates_in_month(year, month, n, rng):
    max_day = calendar.monthrange(year, month)[1]
    seg = max_day // n
    days = []
    for i in range(n):
        start = i * seg + 1
        end = (i + 1) * seg if i < n - 1 else max_day
        days.append(rng.randint(start, end))
    return sorted(days)


# ── 날씨 데이터 ───────────────────────────────────────────────────────────────

def wmo_to_weather_main(code):
    if code is None: return None
    code = int(code)
    if code == 0:           return "맑음"
    if code == 1:           return "구름조금"
    if code == 2:           return "구름많음"
    if code == 3:           return "흐림"
    if code in (45, 48):    return "안개"
    if 51 <= code <= 67:    return "비"
    if 71 <= code <= 77:    return "눈"
    if 80 <= code <= 82:    return "비"
    if code in (85, 86):    return "눈"
    if code >= 95:          return "뇌우"
    return "구름많음"


def fetch_weather_api(farmer_id):
    lat, lon = FARMER_COORDS.get(farmer_id, (37.5, 127.0))
    params = urllib.parse.urlencode({
        "latitude":   lat,
        "longitude":  lon,
        "start_date": "2026-01-01",
        "end_date":   TODAY,
        "daily":      "temperature_2m_max,temperature_2m_min,precipitation_sum,"
                      "relative_humidity_2m_mean,weathercode",
        "timezone":   "Asia/Seoul",
    })
    url = f"https://archive-api.open-meteo.com/v1/archive?{params}"
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            daily = json.loads(resp.read())["daily"]
        result = {}
        for i, dt in enumerate(daily["time"]):
            def _f(v): return round(float(v), 1) if v is not None else None
            def _i(v): return int(v) if v is not None else None
            result[dt] = {
                "weather_main":     wmo_to_weather_main(daily["weathercode"][i]),
                "temp_max":         _f(daily["temperature_2m_max"][i]),
                "temp_min":         _f(daily["temperature_2m_min"][i]),
                "precipitation_mm": _f(daily["precipitation_sum"][i]),
                "humidity_pct":     _i(daily["relative_humidity_2m_mean"][i]),
            }
        return result
    except Exception as e:
        print(f"    ⚠ API 오류: {e}")
        return {}


def synthetic_weather(farmer_id, diary_date, rng):
    month = int(diary_date[5:7])
    base_wm, base_tmax, base_tmin, base_prec, base_hum = SEASONAL_BASE[month]
    delta = REGION_TEMP_DELTA.get(farmer_id, 0.0)
    tmax = round(base_tmax + delta + rng.uniform(-2.0, 2.0), 1)
    tmin = round(base_tmin + delta + rng.uniform(-2.0, 2.0), 1)
    prec = round(max(0.0, base_prec + rng.uniform(-base_prec * 0.6, base_prec * 0.8)), 1)
    hum  = min(100, max(30, int(base_hum + rng.randint(-12, 12))))
    wm = base_wm
    if prec < 0.3 and wm == "비":
        wm = rng.choice(["구름많음", "흐림"])
    return {"weather_main": wm, "temp_max": tmax, "temp_min": tmin,
            "precipitation_mm": prec, "humidity_pct": hum}


# ── 농가 정제 ─────────────────────────────────────────────────────────────────

def refine_farmer(farmer, rng):
    farmer_id = farmer["farmer_id"]
    crop_name = farmer["crop_name"]

    print(f"  날씨 조회: {crop_name} (farmer_id={farmer_id})...")
    weather_map = fetch_weather_api(farmer_id)
    print(f"    → API {len(weather_map)}일 수집" if weather_map else "    → API 실패, 합성값 사용")

    used_memos = set()
    refined_diaries = []

    for diary in farmer["farm_diaries"]:
        year_month = diary["diary_date"][:7].replace("2024", "2026")
        year, month = int(year_month[:4]), int(year_month[5:7])

        top3 = pick_top3(diary["diary_work_blocks"])
        days = random_dates_in_month(year, month, len(top3), rng)
        month_memo = get_memo(crop_name, month, rng, used_memos)

        for i, (block, day) in enumerate(zip(top3, days)):
            diary_date = f"{year_month}-{day:02d}"
            is_past = diary_date <= TODAY

            if is_past:
                w = weather_map.get(diary_date) or synthetic_weather(farmer_id, diary_date, rng)
            else:
                w = {"weather_main": None, "temp_max": None,
                     "temp_min": None, "precipitation_mm": None, "humidity_pct": None}

            refined_diaries.append({
                "diary_date":       diary_date,
                "memo":             month_memo if i == 0 else None,
                "weather_main":     w["weather_main"],
                "temp_max":         w["temp_max"],
                "temp_min":         w["temp_min"],
                "precipitation_mm": w["precipitation_mm"],
                "humidity_pct":     w["humidity_pct"],
                "diary_work_blocks": [{
                    "sort_order": 0,
                    "work_type":  block["work_type"],
                    "detail":     block.get("detail", ""),
                }],
            })

    return {
        "farmer_id":       farmer_id,
        "rank":            farmer["rank"],
        "address":         farmer["address"],
        "region":          farmer["region"],
        "crop_name":       crop_name,
        "origin_region":   farmer.get("origin_region", ""),
        "selection_score": farmer.get("selection_score"),
        "diary_count":     len(refined_diaries),
        "work_types":      farmer["work_types"],
        "crop_knowledge":  farmer["crop_knowledge"],
        "farm_diaries":    refined_diaries,
    }


# ── 실행 ─────────────────────────────────────────────────────────────────────

rng = random.Random(2026)

with open(IN_PATH, encoding="utf-8") as f:
    farmers = json.load(f)

farmers = [f for f in farmers if f["farmer_id"] != 3059]
print(f"농가 수: {len(farmers)}개 (나주 배 제거 후)\n")

refined = []
for farmer in farmers:
    print(f"[{farmer['rank']}위] {farmer['crop_name']} (farmer_id={farmer['farmer_id']})")
    refined.append(refine_farmer(farmer, rng))
    print()

with open(OUT_PATH, "w", encoding="utf-8") as f:
    json.dump(refined, f, ensure_ascii=False, indent=2)

print(f"→ {OUT_PATH} 저장 완료\n")
print("=" * 65)
for f in refined:
    past    = [d for d in f["farm_diaries"] if d["diary_date"] <= TODAY]
    future  = [d for d in f["farm_diaries"] if d["diary_date"] >  TODAY]
    w_filled = sum(1 for d in past if d.get("weather_main"))
    print(f"[{f['rank']}위] {f['crop_name']} | 일지 {f['diary_count']}개 "
          f"| 날씨 {w_filled}/{len(past)}건 (미래 {len(future)}건 null)")
    for d in f["farm_diaries"][:3]:
        wb   = d["diary_work_blocks"][0]
        memo = (d.get("memo") or "")[:30]
        print(f"  {d['diary_date']}: [{wb['work_type']}] | 메모: {memo}...")
    print()
