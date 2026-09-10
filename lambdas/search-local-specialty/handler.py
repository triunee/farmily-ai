"""
farmily-search-local-specialty
지역 특산물 스토리 검색 (pgvector 유사도)
input:  { "cropName": "딸기", "query": "논산 딸기 지역 스토리" }
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
        query     = params.get("query", crop_name + " 지역 특산물 스토리")

        for val in [crop_name, query]:
            safe, reason = is_safe_input(val)
            if not safe:
                return safety_error(event, reason)

        q_vec = embed(query)
        v_str = vec_str(q_vec)

        with get_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""
                    SELECT local_name, region, content,
                           1 - (embedding <=> %s::vector) AS similarity
                    FROM local_specialty
                    WHERE crop_name = %s
                    ORDER BY embedding <=> %s::vector
                    LIMIT 3
                """, (v_str, crop_name, v_str))
                rows = cur.fetchall()

        return ok(event, {
            "cropName": crop_name,
            "count":    len(rows),
            "specialties": [
                {
                    "localName":  r["local_name"] or "",
                    "region":     r["region"] or "",
                    "content":    r["content"],
                    "similarity": float(r["similarity"]),
                }
                for r in rows
            ],
        })

    except Exception as e:
        return error(event, str(e))
