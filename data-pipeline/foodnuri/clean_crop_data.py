# clean_crop_data.py

import json
import re

INPUT  = "crop_data.json"
OUTPUT = "crop_data_clean.json"

# 숫자/날짜 필드는 정제 제외
SKIP_FIELDS = {"season_month", "harvest_months", "production_period",
               "source_url", "crawled_at", "crop_name", "category"}

def clean_field(text):
    if not text:
        return text

    # 케이스 1: p 태그 없이 - 구분자 한 덩어리
    if "-" in text:
        parts = re.split(r"-(?=\S)", text)
        sentences = []
        for part in parts:
            part = part.strip()
            if not part or len(part) <= 1:
                continue
            if not part.endswith("."):
                part = part + "."
            sentences.append(part)
        if sentences:
            return " ".join(sentences)

    # 케이스 2: 줄 단위 정제
    lines = text.splitlines()
    cleaned = []
    for line in lines:
        line = line.strip().lstrip("-").strip()
        if not line or len(line) <= 1:
            continue
        if not line.endswith("."):
            line = line + "."
        cleaned.append(line)
    return " ".join(cleaned) if cleaned else text

# 실행
with open(INPUT, encoding="utf-8") as f:
    items = json.load(f)

print(f"총 {len(items)}건 정제 시작...\n")

for item in items:
    for field, value in item.items():
        if field in SKIP_FIELDS:
            continue
        if isinstance(value, str):
            item[field] = clean_field(value)

with open(OUTPUT, "w", encoding="utf-8") as f:
    json.dump(items, f, ensure_ascii=False, indent=2)

print(f"정제 완료 → {OUTPUT}")

# 샘플 확인 (첫 3건)
print("\n[샘플 확인]")
for item in items[:3]:
    print(f"\n작물명: {item['crop_name']}")
    print(f"  효능: {item['effect_brief'][:80]}...")
    print(f"  영양: {item['nutrition_brief'][:80]}...")