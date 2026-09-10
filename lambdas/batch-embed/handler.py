"""
farmily-batch-embed
recipe_embeddings / local_specialty / trend_insights 테이블의
embedding IS NULL 행을 Bedrock Titan V2로 임베딩해서 업데이트
"""
from farmily_utils import get_connection, embed, vec_str


TABLES = [
    {
        "table":      "recipe_embeddings",
        "id_col":     "id",
        "text_col":   "content",
    },
    {
        "table":      "local_specialty",
        "id_col":     "id",
        "text_col":   "content",
    },
]


def lambda_handler(event, context):
    results = {}

    with get_connection() as conn:
        for cfg in TABLES:
            table    = cfg["table"]
            id_col   = cfg["id_col"]
            text_col = cfg["text_col"]

            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT {id_col}, {text_col} FROM {table} WHERE embedding IS NULL"
                )
                rows = cur.fetchall()

            updated = 0
            errors  = 0
            for row_id, text in rows:
                if not text:
                    continue
                try:
                    vec = embed(text)
                    v   = vec_str(vec)
                    with conn.cursor() as cur:
                        cur.execute(
                            f"UPDATE {table} SET embedding = %s::vector WHERE {id_col} = %s",
                            (v, row_id)
                        )
                    conn.commit()
                    updated += 1
                except Exception as e:
                    errors += 1
                    print(f"[ERROR] {table} id={row_id}: {e}")

            results[table] = {"updated": updated, "errors": errors}
            print(f"[DONE] {table}: updated={updated}, errors={errors}")

    return {"statusCode": 200, "results": results}
