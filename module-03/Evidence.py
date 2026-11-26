"""Module 3 — regenerate every plan and timing in this folder on THIS machine.

Everything in sql-notes.md, llm-query.md, bench.md and stretcher.md is backed by
output from a run of this script. Re-running it here proves the claims hold on my
SQLite build, not just on the one they were first observed on — which matters,
because Task C is about exactly that difference.

Usage, from the repository root:

    uv run python module-03/evidence.py > module-03/evidence.txt
    python3 module-03/evidence.py > module-03/evidence.txt     # without uv

Needs module-02/legacy.db and module-03/warehouse.db to exist:

    sqlite3 module-02/legacy.db  ".read module-02/setup-legacy.sql"
    sqlite3 module-03/warehouse.db ".read module-03/setup.sql"
"""

import sqlite3
import statistics
import sys
import time
from pathlib import Path

HERE = Path(__file__).parent
LEGACY = HERE.parent / "module-02" / "legacy.db"
WAREHOUSE = HERE / "warehouse.db"
REPEATS = 5


def rule(title):
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}")


def plan(conn, sql):
    return [row[3] for row in conn.execute("EXPLAIN QUERY PLAN " + sql)]


def show(conn, label, sql, timed=False):
    print(f"\n  {label}")
    print(f"    {' '.join(sql.split())[:100]}")
    if timed:
        t = []
        for _ in range(REPEATS):
            s = time.perf_counter()
            conn.execute(sql).fetchall()
            t.append((time.perf_counter() - s) * 1000)
        print(f"    median {statistics.median(t):.2f} ms over {REPEATS} runs")
    for line in plan(conn, sql):
        print(f"    | {line}")


def task_a():
    rule("TASK A — plan safari on module-02/legacy.db")
    if not LEGACY.exists():
        print("  SKIPPED — legacy.db not found. Rebuild it with:")
        print('  sqlite3 module-02/legacy.db ".read module-02/setup-legacy.sql"')
        return
    conn = sqlite3.connect(LEGACY)
    conn.execute("DROP INDEX IF EXISTS ix_job_tech")
    conn.execute("DROP INDEX IF EXISTS ix_job_tech_nocase")

    queries = [
        ("A1 equality on technician", "SELECT * FROM maint_job WHERE technician = 'Beier'"),
        ("A2 equality on machine_name", "SELECT * FROM machine WHERE machine_name = 'cnc-02'"),
        ("A3 leading wildcard LIKE", "SELECT * FROM maint_job WHERE technician LIKE '%ei%'"),
    ]

    print("\n-- STEP 1: before any index --")
    for label, sql in queries:
        show(conn, label, sql)

    conn.execute("CREATE INDEX ix_job_tech ON maint_job(technician)")
    print("\n-- STEP 2: after CREATE INDEX ix_job_tech ON maint_job(technician) --")
    for label, sql in queries:
        show(conn, label, sql)

    print("\n-- STEP 3: defeating the index on purpose --")
    for label, sql in [
        ("D1 function wrap", "SELECT * FROM maint_job WHERE upper(technician) = 'BEIER'"),
        ("D2 concat wrap", "SELECT * FROM maint_job WHERE technician || '' = 'Beier'"),
        ("D3 leading wildcard", "SELECT * FROM maint_job WHERE technician LIKE '%eier'"),
        ("D4 TRAILING wildcard (the surprise)", "SELECT * FROM maint_job WHERE technician LIKE 'Bei%'"),
        ("D5 covering index (control)", "SELECT technician FROM maint_job WHERE technician = 'Beier'"),
    ]:
        show(conn, label, sql)

    print("\n-- STEP 3b: why D4 scanned — collation, not the wildcard --")
    like = "SELECT * FROM maint_job WHERE technician LIKE 'Bei%'"
    conn.execute("PRAGMA case_sensitive_like = ON")
    show(conn, "with PRAGMA case_sensitive_like = ON", like)
    conn.execute("PRAGMA case_sensitive_like = OFF")
    conn.execute("CREATE INDEX ix_job_tech_nocase ON maint_job(technician COLLATE NOCASE)")
    show(conn, "with a COLLATE NOCASE index", like)

    conn.execute("DROP INDEX IF EXISTS ix_job_tech_nocase")
    conn.close()


DASHBOARD = """
SELECT c.city, COUNT(DISTINCT c.customer_id) AS customers,
       SUM(ol.qty * p.price) AS revenue
FROM customer c
JOIN orders o      ON o.customer_id = c.customer_id
JOIN order_line ol ON ol.order_id = o.order_id
JOIN product p     ON p.product_id = ol.product_id
WHERE o.ordered_on >= '2025-01-01' AND o.ordered_on < '2026-01-01'
GROUP BY c.city ORDER BY revenue DESC"""


def task_1(conn):
    rule("TASK 1 — the LLM's dashboard query, profiled")
    show(conn, "dashboard (baseline, no indexes)", DASHBOARD, timed=True)
    print("\n  result:")
    for city, n, rev in conn.execute(DASHBOARD):
        print(f"    {city:12s} {n:5d}  {rev:>14,.2f}")
    print("\n  correctness probes:")
    naive = """SELECT c.city, COUNT(c.customer_id) FROM customer c
               JOIN orders o ON o.customer_id=c.customer_id
               JOIN order_line ol ON ol.order_id=o.order_id
               WHERE o.ordered_on>='2025-01-01' AND o.ordered_on<'2026-01-01'
               GROUP BY c.city"""
    print("    COUNT without DISTINCT (the fan-out error):")
    for city, n in conn.execute(naive):
        print(f"      {city:12s} {n:>8,}")
    noorders = conn.execute(
        "SELECT COUNT(*) FROM customer c WHERE NOT EXISTS"
        " (SELECT 1 FROM orders o WHERE o.customer_id=c.customer_id)").fetchone()[0]
    print(f"    customers with no orders at all (dropped by the inner join): {noorders}")
    n2025 = conn.execute("SELECT COUNT(*) FROM orders WHERE ordered_on>='2025-01-01'"
                         " AND ordered_on<'2026-01-01'").fetchone()[0]
    total = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
    print(f"    orders inside the 2025 filter: {n2025:,} of {total:,}"
          f" ({100*n2025/total:.0f}% — too many for an index to pay off)")


def task_2(conn):
    rule("TASK 2 — index benchmark, one index at a time")
    queries = {
        "dashboard": DASHBOARD,
        "single-day": """SELECT o.order_id, o.ordered_on, c.name FROM orders o
                         JOIN customer c ON c.customer_id=o.customer_id
                         WHERE o.ordered_on = '2026-02-14'""",
        "by-product": "SELECT SUM(ol.qty) FROM order_line ol WHERE ol.product_id = 42",
        "wrapped-date": "SELECT COUNT(*) FROM orders WHERE date(ordered_on) = '2026-02-14'",
    }
    steps = [
        ("baseline (no indexes)", []),
        ("+ ix_orders_ordered_on", ["CREATE INDEX ix_orders_ordered_on ON orders(ordered_on)"]),
        ("+ ix_orderline_order", ["CREATE INDEX ix_orderline_order ON order_line(order_id)"]),
        ("+ ix_orderline_product", ["CREATE INDEX ix_orderline_product ON order_line(product_id)"]),
    ]
    for name in ("ix_orders_ordered_on", "ix_orderline_order", "ix_orderline_product"):
        conn.execute(f"DROP INDEX IF EXISTS {name}")

    table = {}
    for label, stmts in steps:
        for s in stmts:
            conn.execute(s)
        print(f"\n-- {label} --")
        table[label] = {}
        for qname, sql in queries.items():
            t = []
            for _ in range(REPEATS):
                s0 = time.perf_counter()
                conn.execute(sql).fetchall()
                t.append((time.perf_counter() - s0) * 1000)
            table[label][qname] = statistics.median(t)
            print(f"\n  {qname}: {statistics.median(t):.2f} ms")
            for line in plan(conn, sql):
                print(f"    | {line}")

    print("\n-- SUMMARY (median ms) — paste this into bench.md --\n")
    print(f"| {'step':<24} | " + " | ".join(f"{q:>12}" for q in queries) + " |")
    print(f"|{'-'*26}|" + "|".join("-" * 14 for _ in queries) + "|")
    for label in table:
        print(f"| {label:<24} | " + " | ".join(f"{table[label][q]:>12.2f}" for q in queries) + " |")

    for name in ("ix_orders_ordered_on", "ix_orderline_order", "ix_orderline_product"):
        conn.execute(f"DROP INDEX IF EXISTS {name}")


def task_5(conn):
    rule("TASK 5 (stretcher) — GROUP BY vs correlated subquery vs window function")
    variants = {
        "GROUP BY (original)": """SELECT c.customer_id, c.name, COUNT(*) AS late_orders
            FROM orders o JOIN customer c ON c.customer_id=o.customer_id
            WHERE o.status='late' GROUP BY c.customer_id, c.name ORDER BY late_orders DESC""",
        "correlated subquery": """SELECT c.customer_id, c.name,
            (SELECT COUNT(*) FROM orders o WHERE o.customer_id=c.customer_id
             AND o.status='late') AS late_orders
            FROM customer c ORDER BY late_orders DESC""",
        "window function": """SELECT DISTINCT c.customer_id, c.name,
            COUNT(*) OVER (PARTITION BY c.customer_id) AS late_orders
            FROM orders o JOIN customer c ON c.customer_id=o.customer_id
            WHERE o.status='late' ORDER BY late_orders DESC""",
    }
    for label, sql in variants.items():
        rows = conn.execute(sql).fetchall()
        t = []
        for _ in range(REPEATS):
            s0 = time.perf_counter()
            conn.execute(sql).fetchall()
            t.append((time.perf_counter() - s0) * 1000)
        print(f"\n  {label}: {len(rows)} rows, median {statistics.median(t):.2f} ms")
        for line in plan(conn, sql):
            print(f"    | {line}")
    zero = conn.execute(
        "SELECT COUNT(*) FROM customer c WHERE NOT EXISTS (SELECT 1 FROM orders o"
        " WHERE o.customer_id=c.customer_id AND o.status='late')").fetchone()[0]
    print(f"\n  customers with ZERO late orders: {zero}"
          "  <- why the subquery returns 2000 rows and the GROUP BY returns 400")


def main():
    print(f"SQLite {sqlite3.sqlite_version} · Python {sys.version.split()[0]} · {sys.platform}")
    print(f"{REPEATS} runs per timing, median reported")
    task_a()
    if not WAREHOUSE.exists():
        rule("TASKS 1, 2, 5 — SKIPPED")
        print('  warehouse.db not found. Build it with:')
        print('  sqlite3 module-03/warehouse.db ".read module-03/setup.sql"')
        return
    conn = sqlite3.connect(WAREHOUSE)
    task_1(conn)
    task_2(conn)
    task_5(conn)
    conn.close()
    rule("DONE")
    print("  Every plan above came from THIS machine's SQLite build.")


if __name__ == "__main__":
    main()
