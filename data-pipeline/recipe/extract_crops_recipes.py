import json
from collections import defaultdict

INPUT_FILE = "raw_10000recipe.json"
OUTPUT_FILE = "crops_recipes_list.txt"

with open(INPUT_FILE, encoding="utf-8") as f:
    data = json.load(f)

# crop_name → [(tag, recipe_name), ...]
crop_map = defaultdict(list)
for item in data:
    crop = item.get("crop_name", "").strip()
    tag = item.get("tag", "").strip()
    name = item.get("recipe_name", "").strip()
    if crop:
        crop_map[crop].append((tag, name))

# 작물명 가나다 정렬
sorted_crops = sorted(crop_map.items(), key=lambda x: x[0])

lines = []
total_recipes = sum(len(v) for v in crop_map.values())
lines.append(f"=== 작물별 레시피 목록 ===")
lines.append(f"작물 수: {len(sorted_crops)}종  |  레시피 총계: {total_recipes}건")
lines.append("")

for crop, recipes in sorted_crops:
    lines.append(f"[{crop}]  ({len(recipes)}건)")
    for tag, recipe_name in recipes:
        lines.append(f"  태그: {tag:<20}  레시피: {recipe_name}")
    lines.append("")

output = "\n".join(lines)
print(output)

with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    f.write(output)

print(f"\n→ 저장 완료: {OUTPUT_FILE}")
