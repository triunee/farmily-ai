"""
local_specialty_rag.json → insert_local_specialty.sql 생성기
=============================================================
실행:
    python3 generate_local_specialty_sql.py

출력: insert_local_specialty.sql  (pgAdmin Query Tool에서 열어서 실행)
"""

import json
import os

INPUT_FILE  = "data/local_specialty_rag.json"
OUTPUT_FILE = "db/seeds/insert_local_specialty.sql"


def escape(value) -> str:
    if value is None:
        return "NULL"
    return "'" + str(value).replace("'", "''") + "'"


def to_row(r: dict) -> str:
    return (
        f"({escape(r.get('crop_name'))}, {escape(r.get('local_name'))}, "
        f"{escape(r.get('region'))}, {escape(r.get('source', '지역N문화'))}, "
        f"{escape(r.get('content'))}, {escape(r.get('source_url'))})"
    )


def main():
    if not os.path.exists(INPUT_FILE):
        print(f"[ERROR] {INPUT_FILE} 없음")
        return

    with open(INPUT_FILE, encoding="utf-8") as f:
        data = json.load(f)
    print(f"로드: {len(data)}건")

    header = """\
INSERT INTO local_specialty (
    crop_name, local_name, region, source,
    content, source_url
) VALUES
"""
    rows_sql = ",\n".join(to_row(r) for r in data)
    footer = "\nON CONFLICT (crop_name, region) DO NOTHING;\n"

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(header)
        f.write(rows_sql)
        f.write(footer)

    print(f"✅ {OUTPUT_FILE} 생성 완료: {len(data)}건")
    print("pgAdmin Query Tool → File > Open → insert_local_specialty.sql → 실행(F5)")


if __name__ == "__main__":
    main()
