"""
만개레시피 크롤링 데이터 → PostgreSQL INSERT
=============================================
- raw_10000recipe.json 읽어서 recipe_embeddings 테이블에 INSERT
- embedding, main_crops 제외 (추후 추가 예정)
- 중복은 ON CONFLICT DO NOTHING으로 처리

실행:
    pip install psycopg2-binary
    python3 insert_recipes.py
"""

import json
import re
import os
import psycopg2
from psycopg2.extras import execute_values

INPUT_FILE = "raw_10000recipe.json"

DB_CONFIG = {
    "host":     "localhost",
    "port":     5432,
    "dbname":   "farmily",
    "user":     "farmily",
    "password": "farmily",
}

# ────────────────────────────────────────
# 전처리 함수
# ────────────────────────────────────────
def clean_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def to_text(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, list):
        return clean_whitespace(" ".join(value))
    return clean_whitespace(str(value))


def ingredients_to_text(ingredients: list) -> str:
    cleaned = [clean_whitespace(i) for i in ingredients if i.strip()]
    return ", ".join(cleaned)


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


# ────────────────────────────────────────
# INSERT
# ────────────────────────────────────────
INSERT_SQL = """
INSERT INTO recipe_embeddings (
    crop_name, dish_name, recipe_name, source,
    servings, cook_time,
    ingredients, instructions,
    content,
    source_url, crawled_at
) VALUES %s
ON CONFLICT (crop_name, recipe_name, source) DO NOTHING
"""

def insert_recipes(recipes: list, conn):
    cur = conn.cursor()
    rows = []
    for r in recipes:
        rows.append((
            r["crop_name"],
            r["dish_name"],
            r["recipe_name"],
            r["source"],
            r["servings"],
            r["cook_time"],
            r["ingredients"],
            r["instructions"],
            r["content"],
            r["source_url"],
            r["crawled_at"],
        ))
    execute_values(cur, INSERT_SQL, rows)
    conn.commit()
    cur.close()
    return len(rows)


# ────────────────────────────────────────
# 메인
# ────────────────────────────────────────
def main():
    if not os.path.exists(INPUT_FILE):
        print(f"[ERROR] {INPUT_FILE} 없음")
        return

    with open(INPUT_FILE, encoding="utf-8") as f:
        raw_data = json.load(f)
    print(f"로드: {len(raw_data)}건")

    processed = [preprocess(r) for r in raw_data]
    print(f"전처리 완료: {len(processed)}건")

    conn = psycopg2.connect(**DB_CONFIG)
    print("DB 연결 완료")

    inserted = insert_recipes(processed, conn)
    conn.close()

    print(f"\n✅ INSERT 완료: {inserted}건 → recipe_embeddings")
    print("\n확인 쿼리:")
    print("  SELECT COUNT(*) FROM recipe_embeddings;")
    print("  SELECT crop_name, dish_name, recipe_name FROM recipe_embeddings LIMIT 10;")


if __name__ == "__main__":
    main()