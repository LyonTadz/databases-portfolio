"""Run the Module 2 audit queries against legacy.db and print each with its result.

Usage:  uv run python module-02/run-audit.py
The sqlite3 CLI does the same job; this script exists so the output is
reproducible in one command and lands in audit-results.txt.
"""
import sqlite3
import sys
import time
from pathlib import Path

DB = Path(__file__).parent / "legacy.db"

QUERIES = [
    ("Cardinality: how many parts hide in each parts_used list?", """
SELECT job_id, parts_used,
       CASE WHEN parts_used IS NULL THEN 0
            ELSE LENGTH(parts_used) - LENGTH(REPLACE(parts_used, ',', '')) + 1
       END AS n_parts
FROM maint_job;
"""),
    ("Cardinality: distinct machines named in jobs vs rows in machine", """
SELECT (SELECT COUNT(*) FROM machine)                      AS machine_rows,
       (SELECT COUNT(DISTINCT machine_name) FROM machine)  AS distinct_machine_names,
       (SELECT COUNT(DISTINCT machine_name) FROM maint_job) AS names_used_by_jobs;
"""),
    ("Cardinality: jobs per machine (is it really 1:n?)", """
SELECT machine_name, COUNT(*) AS jobs
FROM maint_job GROUP BY machine_name ORDER BY jobs DESC;
"""),
    ("Is technician an entity or an attribute? (count distinct)", """
SELECT technician, COUNT(*) AS jobs
FROM maint_job GROUP BY technician ORDER BY jobs DESC;
"""),
    ("Defect 1: orphan maintenance jobs (machine_name not in machine)", """
SELECT m.job_id, m.machine_name
FROM maint_job m
LEFT JOIN machine x ON m.machine_name = x.machine_name
WHERE x.machine_name IS NULL;
"""),
    ("Defect 2: duplicate natural keys in part", """
SELECT part_no, COUNT(*) AS copies
FROM part GROUP BY part_no HAVING COUNT(*) > 1;
"""),
    ("Defect 3: unit_price stored as text - numeric comparison fails silently", """
SELECT part_no, unit_price FROM part WHERE unit_price < '15';
"""),
    ("Defect 3b: the same comparison done correctly, for contrast", """
SELECT part_no, unit_price FROM part WHERE CAST(unit_price AS REAL) < 15.0;
"""),
    ("Defect 4: installed dates that are not dates", """
SELECT machine_name, installed FROM machine
WHERE installed NOT GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]';
"""),
    ("Defect 5: naive join on the comma list silently loses multi-part jobs", """
SELECT j.job_id, p.description
FROM maint_job j
JOIN part p ON p.part_no = j.parts_used;
"""),
]


def main() -> int:
    if not DB.exists():
        print(f"missing {DB} - rebuild it first:\n"
              f"  sqlite3 module-02/legacy.db < module-02/setup-legacy.sql", file=sys.stderr)
        return 1
    conn = sqlite3.connect(DB)
    for title, sql in QUERIES:
        print("=" * 72)
        print(title)
        print("=" * 72)
        print(sql.strip())
        start = time.perf_counter()
        cur = conn.execute(sql)
        rows = cur.fetchall()
        elapsed = (time.perf_counter() - start) * 1000
        headers = [d[0] for d in cur.description]
        print()
        if not rows:
            print("  (no rows)")
        else:
            print("  " + " | ".join(headers))
            print("  " + "-+-".join("-" * len(h) for h in headers))
            for r in rows:
                print("  " + " | ".join("NULL" if v is None else str(v) for v in r))
        print(f"\n  {len(rows)} row(s), {elapsed:.3f} ms\n")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
