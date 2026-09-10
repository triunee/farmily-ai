"""
raw_10000recipe.json → insert_recipes.sql 생성기
=================================================
실행:
    python3 generate_sql.py

출력: insert_recipes.sql  (pgAdmin Query Tool에서 열어서 실행)
"""

import json
import re
import os

INPUT_FILE  = "data/raw_10000recipe.json"
OUTPUT_FILE = "db/seeds/insert_recipes.sql"


def clean_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def to_text(value):
    if value is None:
        return None
    if isinstance(value, list):
        return clean_whitespace(" ".join(value))
    return clean_whitespace(str(value))


def ingredients_to_text(ingredients: list) -> str:
    cleaned = [clean_whitespace(i) for i in ingredients if i.strip()]
    return ", ".join(cleaned)


def escape(value) -> str:
    """None → NULL, 문자열 → 작은따옴표 이스케이프"""
    if value is None:
        return "NULL"
    return "'" + str(value).replace("'", "''") + "'"


def preprocess(raw: dict) -> dict:
    ingredients_list  = raw.get("ingredients", [])
    instructions_list = raw.get("instructions", [])

    ingredients_text  = ingredients_to_text(ingredients_list)
    instructions_text = to_text(instructions_list)
    dish_name         = clean_whitespace(raw.get("tag", "")) or None
    recipe_name       = clean_whitespace(raw.get("recipe_name", ""))

    content = (
        f"요리명: {dish_name or ''}\n"
        f"레시피명: {recipe_name}\n"
        f"작물: {raw.get('crop_name', '')}\n"
        f"재료: {ingredients_text}\n"
        f"조리법: {instructions_text}\n"
        f"인분: {raw.get('servings', '')}"
    )

    return {
        "crop_name":    raw.get("crop_name"),
        "dish_name":    dish_name,
        "recipe_name":  recipe_name,
        "source":       raw.get("source", "10000recipe"),
        "servings":     raw.get("servings"),
        "cook_time":    raw.get("cook_time"),
        "ingredients":  ingredients_text,
        "instructions": instructions_text,
        "content":      content,
        "source_url":   raw.get("source_url"),
        "crawled_at":   raw.get("crawled_at"),
    }


def to_row(r: dict) -> str:
    return (
        f"({escape(r['crop_name'])}, {escape(r['dish_name'])}, {escape(r['recipe_name'])}, "
        f"{escape(r['source'])}, {escape(r['servings'])}, {escape(r['cook_time'])}, "
        f"{escape(r['ingredients'])}, {escape(r['instructions'])}, "
        f"{escape(r['content'])}, {escape(r['source_url'])}, {escape(r['crawled_at'])})"
    )


def main():
    if not os.path.exists(INPUT_FILE):
        print(f"[ERROR] {INPUT_FILE} 없음")
        return

    with open(INPUT_FILE, encoding="utf-8") as f:
        raw_data = json.load(f)
    print(f"로드: {len(raw_data)}건")

    processed = [preprocess(r) for r in raw_data]

    header = """\
INSERT INTO recipe_embeddings (
    crop_name, dish_name, recipe_name, source,
    servings, cook_time,
    ingredients, instructions,
    content,
    source_url, crawled_at
) VALUES
"""
    rows_sql = ",\n".join(to_row(r) for r in processed)
    footer = "\nON CONFLICT (crop_name, recipe_name, source) DO NOTHING;\n"

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(header)
        f.write(rows_sql)
        f.write(footer)

    print(f"✅ {OUTPUT_FILE} 생성 완료: {len(processed)}건")
    print("pgAdmin Query Tool → File > Open → insert_recipes.sql → 실행(F5)")


if __name__ == "__main__":
    main()
