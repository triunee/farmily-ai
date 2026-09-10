"""
farmily-get-content-history
콘텐츠 히스토리 조회 (중복 각도 방지)
input:  { "userId": "...", "cropName": "딸기", "limit": "5" }
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from farmily_utils import (
    get_connection, parse_params, ok, error, safety_error, is_safe_input
)
import psycopg2.extras


def lambda_handler(event, context):
    try:
        params    = parse_params(event)
        user_id   = params.get("userId", "")
        crop_name = params.get("cropName", "")
        limit     = min(int(params.get("limit", 5)), 20)  # 최대 20건 제한

        for val in [user_id, crop_name]:
            safe, reason = is_safe_input(val)
            if not safe:
                return safety_error(event, reason)

        with get_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""
                    SELECT cj.id, cj.platform, cj.created_at,
                           COALESCE(cr.meta->>'angle', '') AS angle
                    FROM content_jobs cj
                    LEFT JOIN content_results cr ON cr.job_id = cj.id
                    JOIN crops c ON c.id = cj.crop_id
                    WHERE cj.user_id = %s
                      AND c.name = %s
                      AND cj.status = 'DONE'
                    ORDER BY cj.created_at DESC
                    LIMIT %s
                """, (user_id, crop_name, limit))
                rows = cur.fetchall()

        history     = [
            {
                "jobId":    str(r["id"]),
                "angle":    r["angle"] or "",
                "platform": r["platform"] or "",
                "createdAt": str(r["created_at"]),
            }
            for r in rows
        ]
        used_angles = list({h["angle"] for h in history if h["angle"]})

        return ok(event, {
            "count":      len(history),
            "history":    history,
            "usedAngles": used_angles,
        })

    except Exception as e:
        return error(event, str(e))
