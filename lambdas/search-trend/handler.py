"""
farmily-search-trend
트렌드 검색 (pgvector 유사도)
input:  { "query": "친환경 딸기 마케팅", "days": "7" }
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
        params = parse_params(event)
        query  = params.get("query", "농산물 트렌드")
        days   = min(int(params.get("days", 7)), 90)  # 최대 90일 제한

        safe, reason = is_safe_input(query)
        if not safe:
            return safety_error(event, reason)

        q_vec = embed(query)
        v_str = vec_str(q_vec)

        with get_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""
                    SELECT content, target_age, keyword, trend_date,
                           1 - (embedding <=> %s::vector) AS similarity
                    FROM trend_insights
                    WHERE trend_date >= CURRENT_DATE - INTERVAL '%s days'
                    ORDER BY embedding <=> %s::vector
                    LIMIT 5
                """, (v_str, days, v_str))
                rows = cur.fetchall()

        return ok(event, {
            "query":  query,
            "days":   days,
            "count":  len(rows),
            "trends": [
                {
                    "content":    r["content"],
                    "targetAge":  r["target_age"] or "전연령대",
                    "keyword":    r["keyword"] or "",
                    "trendDate":  str(r["trend_date"]),
                    "similarity": float(r["similarity"]),
                }
                for r in rows
            ],
        })

    except Exception as e:
        return error(event, str(e))
