"""
farmily-get-diary
영농일지 조회
input:  { "userId": "...", "diaryId": "..." }
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from farmily_utils import (
    get_connection, parse_params, ok, error, safety_error, is_safe_input
)
import psycopg2.extras


def lambda_handler(event, context):
    try:
        params   = parse_params(event)
        user_id  = params.get("userId", "")
        diary_id = params.get("diaryId", "")

        # 입력값 안전 검사
        for val in [user_id, diary_id]:
            safe, reason = is_safe_input(val)
            if not safe:
                return safety_error(event, reason)

        with get_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                if diary_id:
                    cur.execute("""
                        SELECT fd.id, fd.diary_date,
                               c.name AS crop,
                               fd.weather_main, fd.memo,
                               COALESCE(
                                 json_agg(DISTINCT dwb.work_type)
                                 FILTER (WHERE dwb.work_type IS NOT NULL), '[]'
                               ) AS work_types
                        FROM farm_diaries fd
                        LEFT JOIN crops c ON c.id = fd.crop_id
                        LEFT JOIN diary_work_blocks dwb ON dwb.diary_id = fd.id
                        WHERE fd.id = %s AND fd.user_id = %s
                          AND fd.deleted_at IS NULL
                        GROUP BY fd.id, c.name
                    """, (diary_id, user_id))
                else:
                    cur.execute("""
                        SELECT fd.id, fd.diary_date,
                               c.name AS crop,
                               fd.weather_main, fd.memo,
                               COALESCE(
                                 json_agg(DISTINCT dwb.work_type)
                                 FILTER (WHERE dwb.work_type IS NOT NULL), '[]'
                               ) AS work_types
                        FROM farm_diaries fd
                        LEFT JOIN crops c ON c.id = fd.crop_id
                        LEFT JOIN diary_work_blocks dwb ON dwb.diary_id = fd.id
                        WHERE fd.user_id = %s AND fd.deleted_at IS NULL
                        GROUP BY fd.id, c.name
                        ORDER BY fd.diary_date DESC
                        LIMIT 1
                    """, (user_id,))
                row = cur.fetchone()

        if not row:
            return ok(event, {"found": False, "message": "영농일지 없음"})

        return ok(event, {
            "found":          True,
            "diaryId":        str(row["id"]),
            "date":           str(row["diary_date"]),
            "crop":           row["crop"] or "",
            "weatherSummary": row["weather_main"] or "",
            "memo":           row["memo"] or "",
            "workTypes":      row["work_types"] if isinstance(row["work_types"], list) else [],
        })

    except Exception as e:
        return error(event, str(e))
