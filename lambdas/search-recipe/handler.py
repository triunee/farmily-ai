"""
farmily-search-recipe
레시피 검색 (pgvector 유사도)
input:  { "cropName": "딸기", "query": "당도 높을 때 어울리는 레시피" }
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from farmily_utils import (
    get_connection, parse_params, ok, error, safety_error,
    is_safe_input, embed, vec_str
)
import psycopg2.extras


def lambda_handler(event, context):
    try:
        params    = parse_params(event)
        crop_name = params.get("cropName", "")
        query     = params.get("query", crop_name + " 레시피")

        for val in [crop_name, query]:
            safe, reason = is_safe_input(val)
            if not safe:
                return safety_error(event, reason)

        q_vec = embed(query)
        v_str = vec_str(q_vec)

        with get_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                if crop_name:
                    cur.execute("""
                        SELECT recipe_name, content, source,
                               1 - (embedding <=> %s::vector) AS similarity
                        FROM recipe_embeddings
                        WHERE crop_name = %s AND embedding IS NOT NULL
                        ORDER BY embedding <=> %s::vector
                        LIMIT 5
                    """, (v_str, crop_name, v_str))
                else:
                    cur.execute("""
                        SELECT recipe_name, content, source,
                               1 - (embedding <=> %s::vector) AS similarity
                        FROM recipe_embeddings
                        WHERE embedding IS NOT NULL
                        ORDER BY embedding <=> %s::vector
                        LIMIT 5
                    """, (v_str, v_str))
                rows = cur.fetchall()

        return ok(event, {
            "cropName": crop_name,
            "query":    query,
            "count":    len(rows),
            "recipes": [
                {
                    "recipeName": r["recipe_name"],
                    "content":    r["content"],
                    "source":     r["source"],
                    "similarity": float(r["similarity"]),
                }
                for r in rows
            ],
        })

    except Exception as e:
        return error(event, str(e))
