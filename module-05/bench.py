#!/usr/bin/env python3
"""Module 5 · Round 4 — the normalized/denormalized race, measured properly.

Run from the repository root, after setup.sql has built the database:

    uv run python module-05/bench.py            # the main race
    uv run python module-05/bench.py --wide     # + Round 4's optional try

Why this is a script and not a `.timer on` transcript
-----------------------------------------------------
Module 4 taught me that two numbers from two consecutive runs are a coin flip.
Two habits from that module are built in here:

  * **Interleave the arms.** One repetition is one pass over *all* arms, so
    anything that drifts during the run (another process, thermal throttling,
    the page cache warming) lands on every arm instead of on whichever one
    happened to run while it drifted.
  * **Estimate with the minimum, not the mean.** Noise here is one-sided: an
    interruption only ever adds time. The minimum is the closest thing to "the
    cost of the query with nothing else happening". The median is printed too,
    so you can see how far apart they are.

The cache is warmed before any timing: one untimed pass over every arm. A cold
first scan pays for page-cache misses and whichever query runs second inherits
a warm cache — that alone is enough to invert the result.
"""

import os
import shutil
import sqlite3
import statistics
import sys
import time

DB = os.path.join(os.path.dirname(__file__), "normalize.db")
REPS = 21

# --- the two designs, answering the same question ---------------------------

A_NORMALIZED = """
SELECT m.machine_id, m.site, j.technician, SUM(p.part_price) AS cost
FROM job j
JOIN machine m   ON m.machine_id = j.machine_id
JOIN job_part jp ON jp.job_id = j.job_id
JOIN part p      ON p.part_no = jp.part_no
WHERE j.done_on >= date('2026-03-01')
GROUP BY m.machine_id, j.technician
"""

B_DENORMALIZED = """
SELECT machine_id, site, technician, SUM(part_price) AS cost
FROM report_jobpart
WHERE done_on >= date('2026-03-01')
GROUP BY machine_id, technician
"""


def time_once(con, sql):
    """Milliseconds to run the query and consume every row it returns."""
    t0 = time.perf_counter()
    rows = con.execute(sql).fetchall()
    return (time.perf_counter() - t0) * 1000.0, rows


def race(con, arms, reps=REPS):
    """Interleaved timing. arms is a list of (label, sql). Returns (samples, rows)."""
    for _label, sql in arms:          # warm the cache, throw the numbers away
        con.execute(sql).fetchall()

    samples = {label: [] for label, _ in arms}
    shapes = {}
    for _ in range(reps):
        for label, sql in arms:
            ms, rows = time_once(con, sql)
            samples[label].append(ms)
            shapes[label] = rows
    return samples, shapes


def report(samples):
    width = max(len(l) for l in samples)
    print(f"  {'arm'.ljust(width)}   min(ms)  median(ms)   max(ms)")
    for label, xs in samples.items():
        print(f"  {label.ljust(width)}  {min(xs):7.1f}  {statistics.median(xs):9.1f}  {max(xs):8.1f}")
    mins = {l: min(xs) for l, xs in samples.items()}
    fastest = min(mins, key=mins.get)
    for label, m in mins.items():
        if label != fastest:
            print(f"  -> {label} is {m / mins[fastest]:.2f}x the minimum of {fastest}")


def plan(sql, db=None):
    """A fresh connection per plan: python's sqlite3 caches prepared statements,
    so asking the *same* connection for the same EXPLAIN after a DDL change
    hands back the plan it compiled before the change."""
    with sqlite3.connect(db or DB) as c:
        return [r[-1] for r in c.execute("EXPLAIN QUERY PLAN " + sql).fetchall()]


def equal_results(a, b):
    """Same question, same answer? Compare as multisets of rounded rows."""
    norm = lambda rows: sorted((r[0], r[2] if len(r) == 4 else r[1], round(r[-1], 4)) for r in rows)
    return norm(a) == norm(b)


# --- the optional try: make the join expensive ------------------------------

WIDE_SETUP = """
CREATE TABLE vendor(part_no TEXT PRIMARY KEY, vendor TEXT NOT NULL, country TEXT NOT NULL);
INSERT INTO vendor SELECT part_no, 'vendor-' || (rowid % 12),
       CASE rowid % 3 WHEN 0 THEN 'DE' WHEN 1 THEN 'CN' ELSE 'US' END FROM part;

CREATE TABLE site_dim(site TEXT PRIMARY KEY, region TEXT NOT NULL, manager TEXT NOT NULL);
INSERT INTO site_dim SELECT site, 'region-' || (row_number() OVER () % 5),
       'mgr-' || row_number() OVER () FROM (SELECT DISTINCT site FROM machine);

DROP TABLE IF EXISTS report_jobpart;
CREATE TABLE report_jobpart AS
SELECT j.job_id, m.machine_id, m.site, sd.region, j.technician, jp.part_no,
       p.part_price, v.vendor, j.done_on
FROM job j
JOIN machine m   ON m.machine_id = j.machine_id
JOIN site_dim sd ON sd.site = m.site
JOIN job_part jp ON jp.job_id = j.job_id
JOIN part p      ON p.part_no = jp.part_no
JOIN vendor v    ON v.part_no = p.part_no;
"""

A_SIX = """
SELECT m.machine_id, m.site, sd.region, j.technician, v.vendor, SUM(p.part_price) AS cost
FROM job j
JOIN machine m   ON m.machine_id = j.machine_id
JOIN site_dim sd ON sd.site = m.site
JOIN job_part jp ON jp.job_id = j.job_id
JOIN part p      ON p.part_no = jp.part_no
JOIN vendor v    ON v.part_no = p.part_no
WHERE j.done_on >= date('2026-03-01')
GROUP BY m.machine_id, m.site, sd.region, j.technician, v.vendor
"""

B_WIDE = """
SELECT machine_id, site, region, technician, vendor, SUM(part_price) AS cost
FROM report_jobpart
WHERE done_on >= date('2026-03-01')
GROUP BY machine_id, site, region, technician, vendor
"""

# a dimension with real cardinality: one row per job, not per site or per part
BIG_SETUP = """
CREATE TABLE job_meta(job_id INTEGER PRIMARY KEY, shift TEXT NOT NULL,
                      line TEXT NOT NULL, order_ref TEXT NOT NULL);
INSERT INTO job_meta SELECT job_id, 'shift-' || (job_id % 3), 'line-' || (job_id % 17),
       'ORD-' || printf('%06d', job_id) FROM job;

DROP TABLE IF EXISTS report_wide2;
CREATE TABLE report_wide2 AS
SELECT j.job_id, m.machine_id, m.site, sd.region, j.technician, jp.part_no, p.part_price,
       v.vendor, jm.shift, jm.line, jm.order_ref, j.done_on
FROM job j
JOIN machine m   ON m.machine_id = j.machine_id
JOIN site_dim sd ON sd.site = m.site
JOIN job_part jp ON jp.job_id = j.job_id
JOIN part p      ON p.part_no = jp.part_no
JOIN vendor v    ON v.part_no = p.part_no
JOIN job_meta jm ON jm.job_id = j.job_id;
"""

A_BIG = """
SELECT m.machine_id, m.site, sd.region, j.technician, v.vendor, jm.shift, jm.line,
       SUM(p.part_price) AS cost
FROM job j
JOIN machine m   ON m.machine_id = j.machine_id
JOIN site_dim sd ON sd.site = m.site
JOIN job_part jp ON jp.job_id = j.job_id
JOIN part p      ON p.part_no = jp.part_no
JOIN vendor v    ON v.part_no = p.part_no
JOIN job_meta jm ON jm.job_id = j.job_id
WHERE j.done_on >= date('2026-03-01')
GROUP BY m.machine_id, m.site, sd.region, j.technician, v.vendor, jm.shift, jm.line
"""

B_BIG = """
SELECT machine_id, site, region, technician, vendor, shift, line, SUM(part_price) AS cost
FROM report_wide2
WHERE done_on >= date('2026-03-01')
GROUP BY machine_id, site, region, technician, vendor, shift, line
"""


def wide_experiments():
    """Round 4's optional try, on a COPY so normalize.db is left untouched.

    Both variants are run against the same copy: `vendor` and `site_dim` are
    small dimensions (10 and 2 rows), `job_meta` is a large one (20,000).
    """
    copy = DB.replace("normalize.db", "normalize-wide.db")
    shutil.copy(DB, copy)
    con = sqlite3.connect(copy, isolation_level=None)
    try:
        con.executescript(WIDE_SETUP)
        print("== Optional try A · two SMALL dimensions (vendor 10 rows, site_dim 2) ==")
        print("   note: rebuilding report_jobpart drops ix_report_machine, so this is")
        print("   compared against phase 2 above, not phase 1.")
        s, shapes = race(con, [("A 6 joins          ", A_SIX),
                               ("B one wide table   ", B_WIDE)])
        report(s)
        ra, rb = shapes["A 6 joins          "], shapes["B one wide table   "]
        print(f"\n  rows: A={len(ra)} B={len(rb)}   "
              f"total: A={sum(r[-1] for r in ra):.1f} B={sum(r[-1] for r in rb):.1f}")
        for direction, sql in (("A EXCEPT B", f"SELECT * FROM ({A_SIX}) EXCEPT SELECT * FROM ({B_WIDE})"),
                               ("B EXCEPT A", f"SELECT * FROM ({B_WIDE}) EXCEPT SELECT * FROM ({A_SIX})")):
            print(f"  {direction}: {len(con.execute(sql).fetchall())} rows")
        wide_b = con.execute("SELECT SUM(pgsize) FROM dbstat "
                             "WHERE name='report_jobpart'").fetchone()[0]
        print(f"  wide report_jobpart: {wide_b / 1024:.1f} KB "
              f"(the narrow one was 10832.0 KB)")

        con.executescript(BIG_SETUP)
        print("\n== Optional try B · one LARGE dimension (job_meta, 20,000 rows) ==")
        s2, shapes2 = race(con, [("A 6 joins + 20k dim", A_BIG),
                                 ("B one table        ", B_BIG)])
        report(s2)
        rb2 = shapes2["B one table        "]
        print(f"\n  rows returned: {len(rb2)}  <- the GROUP BY grew from 3,500 to this,")
        print("  so both arms now pay a much bigger temp B-tree and the difference")
        print("  between the designs is diluted. Not clean evidence either way.")
        big_b = con.execute("SELECT SUM(pgsize) FROM dbstat "
                            "WHERE name='report_wide2'").fetchone()[0]
        print(f"  report_wide2: {big_b / 1024:.1f} KB")
    finally:
        con.close()
        os.remove(copy)
        print(f"\n{os.path.basename(copy)} removed; normalize.db untouched.")


def main():
    if not os.path.exists(DB):
        sys.exit(f"{DB} missing — build it first with setup.sql")

    con = sqlite3.connect(DB)
    print(f"SQLite {sqlite3.sqlite_version}  ·  {REPS} interleaved repetitions per arm")
    print(f"database: {os.path.getsize(DB) / 1024 / 1024:.1f} MB\n")

    arms = [("A normalized (4-way join)", A_NORMALIZED),
            ("B denormalized (1 table) ", B_DENORMALIZED)]

    print("== Phase 1 · as built, ix_report_machine present ==")
    samples, shapes = race(con, arms)
    report(samples)
    a_rows = shapes["A normalized (4-way join)"]
    b_rows = shapes["B denormalized (1 table) "]
    print(f"\n  rows returned: A = {len(a_rows)}, B = {len(b_rows)}")
    print(f"  same answer:   {equal_results(a_rows, b_rows)}")
    print(f"  total cost:    A = {sum(r[-1] for r in a_rows):.1f}, "
          f"B = {sum(r[-1] for r in b_rows):.1f}")

    print("\n  query plans")
    for label, sql in arms:
        print(f"    {label.strip()}")
        for line in plan(sql):
            print(f"      {line}")

    print("\n== Phase 2 · same race with ix_report_machine dropped ==")
    con.execute("DROP INDEX IF EXISTS ix_report_machine")
    samples2, _ = race(con, arms)
    report(samples2)
    print("\n  B's plan without the index")
    for line in plan(B_DENORMALIZED):
        print(f"      {line}")

    b_with = min(samples["B denormalized (1 table) "])
    b_without = min(samples2["B denormalized (1 table) "])
    print(f"\n  B with index {b_with:.1f} ms -> without {b_without:.1f} ms "
          f"({b_with / b_without:.2f}x)")

    # leave the database as setup.sql built it: Round 5 drops this index on purpose
    con.execute("CREATE INDEX IF NOT EXISTS ix_report_machine ON report_jobpart(machine_id)")
    con.commit()
    con.close()
    print("\nix_report_machine restored.")

    # --- phases 3 and 4: the same races, with planner statistics -------------
    # On a copy, because ANALYZE writes a sqlite_stat1 table into the database
    # and I want normalize.db to stay exactly as setup.sql builds it.
    copy = DB.replace("normalize.db", "normalize-analyzed.db")
    shutil.copy(DB, copy)
    acon = sqlite3.connect(copy, isolation_level=None)
    try:
        t0 = time.perf_counter()
        acon.execute("ANALYZE")
        print(f"\n== ANALYZE ({(time.perf_counter() - t0) * 1000:.0f} ms) ==")
        for tbl, idx, stat in acon.execute(
                "SELECT tbl, idx, stat FROM sqlite_stat1 ORDER BY tbl"):
            print(f"  {tbl:<16} {str(idx):<30} {stat}")

        print("\n== Phase 3 · statistics collected, ix_report_machine present ==")
        s3, _ = race(acon, arms)
        report(s3)
        print("\n  plans after ANALYZE")
        for label, sql in arms:
            print(f"    {label.strip()}")
            for line in plan(sql, copy):
                print(f"      {line}")

        print("\n== Phase 4 · statistics collected, ix_report_machine dropped ==")
        acon.execute("DROP INDEX ix_report_machine")
        s4, _ = race(acon, arms)
        report(s4)
        print("\n  plans")
        for label, sql in arms:
            print(f"    {label.strip()}")
            for line in plan(sql, copy):
                print(f"      {line}")

        print("\n== The 2x2, minima in ms ==")
        print(f"  {'':<22}{'index':>10}{'no index':>11}")
        for name, with_i, without_i in (
                ("A  no statistics", samples, samples2),
                ("A  ANALYZE'd    ", s3, s4)):
            print(f"  {name:<22}{min(with_i[arms[0][0]]):>10.1f}"
                  f"{min(without_i[arms[0][0]]):>11.1f}")
        for name, with_i, without_i in (
                ("B  no statistics", samples, samples2),
                ("B  ANALYZE'd    ", s3, s4)):
            print(f"  {name:<22}{min(with_i[arms[1][0]]):>10.1f}"
                  f"{min(without_i[arms[1][0]]):>11.1f}")
        print("\n  A/B ratios (>1 means the denormalized table wins)")
        for name, smp in (("no statistics, index   ", samples),
                          ("no statistics, no index", samples2),
                          ("ANALYZE'd, index       ", s3),
                          ("ANALYZE'd, no index    ", s4)):
            r = min(smp[arms[0][0]]) / min(smp[arms[1][0]])
            verdict = "denormalized wins" if r > 1.05 else (
                "NORMALIZED wins" if r < 0.95 else "a tie")
            print(f"    {name}  {r:.2f}x   {verdict}")
    finally:
        acon.close()
        os.remove(copy)
        print(f"\n{os.path.basename(copy)} removed; normalize.db untouched.")

    if "--wide" in sys.argv:
        print()
        wide_experiments()


if __name__ == "__main__":
    main()
