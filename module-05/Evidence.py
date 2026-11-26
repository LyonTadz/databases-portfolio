#!/usr/bin/env python3
"""Module 5 — every number, error message and row count quoted on these pages.

    uv run python module-05/evidence.py > module-05/evidence.txt

It rebuilds `module-05/normalize.db` from `setup.sql` first, so the output is a
transcript of one clean run rather than of whatever state the database happened
to be in. The destructive parts (Round 5's updates, the index drop) run inside
transactions that are rolled back, or restore what they changed, so the database
is left exactly as `setup.sql` builds it.

Habit carried over from Module 4: write the generator before the prose. Anything
quoted on a page that is not in here is a number I cannot defend.
"""

import os
import sqlite3
import statistics
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(HERE, "normalize.db")
SETUP = os.path.join(HERE, "setup.sql")
REPS = 9


def h(title):
    print(f"\n{'=' * 78}\n{title}\n{'=' * 78}")


def sub(title):
    print(f"\n-- {title} " + "-" * max(0, 74 - len(title)))


def rows(cur):
    return cur.fetchall()


# ---------------------------------------------------------------------------
# 0 · environment
# ---------------------------------------------------------------------------
h("0 · ENVIRONMENT")
print(f"python           {sys.version.split()[0]}")
print(f"sqlite3 module   {sqlite3.sqlite_version}")
try:
    cli = subprocess.run(["sqlite3", "--version"], capture_output=True, text=True, timeout=10)
    print(f"sqlite3 CLI      {cli.stdout.strip() or '(no output)'}")
except (FileNotFoundError, subprocess.TimeoutExpired):
    print("sqlite3 CLI      not installed — every timing below is from this module, "
          "not from `.timer on`")
try:
    import duckdb
    print(f"duckdb           {duckdb.__version__}")
except ImportError:
    print("duckdb           not installed — the stretcher section will be skipped")

# ---------------------------------------------------------------------------
# 1 · Round 1 — the five-row extract, and every FD claim tested
# ---------------------------------------------------------------------------
h("1 · ROUND 1 — FUNCTIONAL DEPENDENCIES IN THE FIVE-ROW EXTRACT")

FLAT5 = """
CREATE TABLE flat5(
  job_id INTEGER, machine_id TEXT, site TEXT,
  technician TEXT, part_no TEXT, part_price REAL
);
INSERT INTO flat5 VALUES
  (1,'cnc-01','Gütersloh','tech-0','P-0001',6.00),
  (1,'cnc-01','Gütersloh','tech-0','P-0002',7.00),
  (2,'cnc-02','Gütersloh','tech-1','P-0001',6.00),
  (2,'cnc-02','Gütersloh','tech-1','P-0003',8.50),
  (3,'cnc-01','Gütersloh','tech-0','P-0003',8.50);
"""

five = sqlite3.connect(":memory:", isolation_level=None)
five.executescript(FLAT5)


def fd_holds(con, table, lhs, rhs):
    """Does lhs -> rhs hold *in this data*? Returns (holds, counterexamples)."""
    left = ", ".join(lhs)
    sql = (f"SELECT {left}, COUNT(DISTINCT {rhs}) AS n FROM {table} "
           f"GROUP BY {left} HAVING n > 1")
    bad = con.execute(sql).fetchall()
    return (not bad), bad


sub("does it hold in the data? (data cannot tell you WHY — that column is mine)")
CLAIMS = [
    (["job_id"], "machine_id", "domain"),
    (["job_id"], "technician", "domain (modelling decision)"),
    (["machine_id"], "site", "domain"),
    (["part_no"], "part_price", "domain, with a caveat: no price history"),
    (["job_id", "part_no"], "machine_id", "candidate key"),
    (["job_id", "part_no"], "part_price", "candidate key"),
    (["machine_id"], "technician", "OBSERVED ONLY — accident of 5 rows"),
    (["technician"], "machine_id", "OBSERVED ONLY — same accident, reversed"),
    (["part_price"], "part_no", "OBSERVED ONLY — 3 distinct prices for 3 parts"),
    (["technician"], "site", "OBSERVED, VACUOUSLY — site has one value"),
    (["part_no"], "site", "OBSERVED, VACUOUSLY"),
]
for lhs, rhs, why in CLAIMS:
    ok, bad = fd_holds(five, "flat5", lhs, rhs)
    mark = "holds    " if ok else "VIOLATED "
    print(f"  {mark} {' + '.join(lhs):>18} -> {rhs:<11}  {why}")
    for b in bad:
        print(f"              counterexample: {b}")

sub("why 'site' makes every FD into it true")
print("  distinct sites in the extract:",
      rows(five.execute("SELECT COUNT(DISTINCT site) FROM flat5"))[0][0])
print("  -> a single-valued column is determined by everything, including the empty set.")

sub("candidate key check: is (job_id, part_no) minimal?")
for lhs in (["job_id"], ["part_no"], ["job_id", "part_no"]):
    ok, bad = fd_holds(five, "flat5", lhs, "part_price")
    note = "" if ok else (f"  e.g. {lhs[0]}={bad[0][0]} has {bad[0][-1]} different prices")
    print(f"  {' + '.join(lhs):>18} -> part_price : "
          f"{'unique' if ok else 'NOT unique'}{note}")

# ---------------------------------------------------------------------------
# 2 · Round 2 — the three anomalies
# ---------------------------------------------------------------------------
h("2 · ROUND 2 — THE THREE ANOMALIES")

sub("2.1 update anomaly: move cnc-01 to Bielefeld")
cur = five.execute("UPDATE flat5 SET site='Bielefeld' WHERE machine_id='cnc-01'")
print(f"  UPDATE … WHERE machine_id='cnc-01'          -> {cur.rowcount} rows touched "
      f"for ONE fact about ONE machine")
five.execute("UPDATE flat5 SET site='Gütersloh' WHERE machine_id='cnc-01'")

print("  now the same update, interrupted after two rows:")
cur = five.execute("UPDATE flat5 SET site='Bielefeld' "
                   "WHERE machine_id='cnc-01' AND job_id=1")
print(f"  UPDATE … AND job_id=1                       -> {cur.rowcount} rows")
print("  SELECT DISTINCT site WHERE machine_id='cnc-01' ->",
      [r[0] for r in rows(five.execute(
          "SELECT DISTINCT site FROM flat5 WHERE machine_id='cnc-01' ORDER BY site"))])
print("  one machine, two sites, no error raised.")
for r in rows(five.execute("SELECT * FROM flat5 ORDER BY job_id, part_no")):
    print("     ", r)
five.execute("UPDATE flat5 SET site='Gütersloh' WHERE machine_id='cnc-01'")

sub("2.2 insert anomaly: record a part no job has used")
five.execute("INSERT INTO flat5(part_no, part_price) VALUES ('P-0009', 12.00)")
print("  INSERT INTO flat5(part_no, part_price) …     -> accepted:",
      rows(five.execute("SELECT * FROM flat5 WHERE part_no='P-0009'"))[0])
print("  rows in table now:", rows(five.execute("SELECT COUNT(*) FROM flat5"))[0][0],
      "| of which job_id IS NULL:",
      rows(five.execute("SELECT COUNT(*) FROM flat5 WHERE job_id IS NULL"))[0][0])
print("  -> COUNT(*) is no longer 'parts used'. Every query needs job_id IS NOT NULL.")
five.execute("DELETE FROM flat5 WHERE part_no='P-0009'")

sub("2.3 delete anomaly: delete the last job that used a part")
print("  P-0002 price before      :",
      [r[0] for r in rows(five.execute(
          "SELECT DISTINCT part_price FROM flat5 WHERE part_no='P-0002'"))])
print("  jobs using P-0002        :",
      rows(five.execute("SELECT COUNT(*) FROM flat5 WHERE part_no='P-0002'"))[0][0])
cur = five.execute("DELETE FROM flat5 WHERE job_id=1")
print(f"  DELETE FROM flat5 WHERE job_id=1            -> {cur.rowcount} rows deleted")
print("  P-0002 price after       :",
      [r[0] for r in rows(five.execute(
          "SELECT DISTINCT part_price FROM flat5 WHERE part_no='P-0002'"))] or "(no rows)")
print("  P-0002 exists anywhere   :",
      rows(five.execute("SELECT COUNT(*) FROM flat5 WHERE part_no='P-0002'"))[0][0])
print("  -> deleting a JOB destroyed a PART. No error, permanently less informed.")
five.close()

# ---------------------------------------------------------------------------
# 3 · Round 3 — build and decompose
# ---------------------------------------------------------------------------
h("3 · ROUND 3 — THE 200k BUILD AND THE 3NF DECOMPOSITION")

if os.path.exists(DB):
    os.remove(DB)
con = sqlite3.connect(DB, isolation_level=None)
t0 = time.perf_counter()
con.executescript(open(SETUP, encoding="utf-8").read())
build_s = time.perf_counter() - t0
print(f"  rebuilt {os.path.relpath(DB, os.path.dirname(HERE))} from setup.sql "
      f"in {build_s:.2f} s")

sub("3.1 the integrity check the module asks for")
flat_rows, norm_rows = rows(con.execute(
    "SELECT (SELECT COUNT(*) FROM flat_jobpart), (SELECT COUNT(*) FROM job_part)"))[0]
print(f"  flat_rows = {flat_rows}   normalized_rows = {norm_rows}   "
      f"{'LOSSLESS' if flat_rows == norm_rows else 'MISMATCH!'}")

sub("3.2 what the decomposition produced")
for t in ("flat_jobpart", "machine", "part", "job", "job_part", "report_jobpart"):
    print(f"  {t:<16} {rows(con.execute(f'SELECT COUNT(*) FROM {t}'))[0][0]:>7} rows")
print("  distinct machines :", rows(con.execute("SELECT COUNT(*) FROM machine"))[0][0])
print("  sites             :", rows(con.execute(
    "SELECT site, COUNT(*) FROM machine GROUP BY site ORDER BY site")))
print("  technicians       :", rows(con.execute(
    "SELECT COUNT(DISTINCT technician) FROM job"))[0][0])
print("  done_on           :", rows(con.execute(
    "SELECT MIN(done_on), MAX(done_on), COUNT(DISTINCT done_on) FROM job"))[0])

sub("3.3 why `part` has 10 rows and not 40")
print("  the catalogue:", [r[0] for r in rows(con.execute(
    "SELECT part_no FROM part ORDER BY part_no"))])
print("  prices       :", [r[0] for r in rows(con.execute(
    "SELECT part_price FROM part ORDER BY part_price"))])
print("  -> the inner counter k runs 1..10, so (k % 40) + 1 is just k + 1:")
print("     P-0002 .. P-0011, and the '% 40' never fires. Prices are 5 + k.")

sub("3.4 every FD claim re-tested against all 200,000 rows")
for lhs, rhs, why in [(["job_id"], "machine_id", "domain"),
                      (["job_id"], "technician", "domain"),
                      (["machine_id"], "site", "domain"),
                      (["part_no"], "part_price", "domain"),
                      (["machine_id"], "technician", "observed only in 5 rows"),
                      (["technician"], "machine_id", "observed only in 5 rows"),
                      (["part_price"], "part_no", "observed only in 5 rows")]:
    ok, bad = fd_holds(con, "flat_jobpart", lhs, rhs)
    print(f"  {'holds    ' if ok else 'VIOLATED '} {' + '.join(lhs):>12} -> {rhs:<11}"
          f"  (claimed: {why})")
print("  -> two of the three 'observed only' FDs are violated at scale, as predicted.")
print("     part_price -> part_no SURVIVES, because the generator gave all ten parts")
print("     distinct prices. It is still not a domain fact: it holds by accident at")
print("     200,000 rows exactly as it did at 5. Volume did not settle the question.")

sub("3.5 PRAGMA foreign_keys — default, enforcement, and the silent no-op")
print("  PRAGMA foreign_keys (default)        :",
      rows(con.execute("PRAGMA foreign_keys"))[0][0])
con.execute("INSERT INTO job_part VALUES (999999,'P-9999')")
print("  dangling INSERT with the pragma off  : accepted")
print("  PRAGMA foreign_key_check reports     :",
      len(rows(con.execute("PRAGMA foreign_key_check"))),
      "violations (one row dangling in two directions)")
con.execute("DELETE FROM job_part WHERE job_id=999999")

con.execute("PRAGMA foreign_keys=ON")
print("  PRAGMA foreign_keys=ON, in autocommit:",
      rows(con.execute("PRAGMA foreign_keys"))[0][0])
try:
    con.execute("INSERT INTO job_part VALUES (999999,'P-9999')")
    print("  dangling INSERT with the pragma on   : ACCEPTED (!)")
    con.execute("DELETE FROM job_part WHERE job_id=999999")
except sqlite3.IntegrityError as e:
    print(f"  dangling INSERT with the pragma on   : {type(e).__name__}: {e}")

con.execute("PRAGMA foreign_keys=OFF")
con.execute("BEGIN")
con.execute("PRAGMA foreign_keys=ON")                  # silently does nothing
print("  inside an open transaction, the same pragma reads back:",
      rows(con.execute("PRAGMA foreign_keys"))[0][0], "<- it did not take effect")
try:
    con.execute("INSERT INTO job_part VALUES (999998,'P-9998')")
    print("  and the dangling INSERT is accepted  : the pragma is a no-op in a transaction")
except sqlite3.IntegrityError as e:
    print("  refused:", e)
con.execute("ROLLBACK")
con.execute("PRAGMA foreign_keys=ON")
print("  does the decomposition still load with enforcement on? parents are inserted")
print("  before children in setup.sql, so yes — job_part rows:",
      rows(con.execute("SELECT COUNT(*) FROM job_part"))[0][0])
con.execute("PRAGMA foreign_keys=OFF")

sub("3.6 what SELECT DISTINCT is asserting: one job, one technician")
probe = sqlite3.connect(":memory:", isolation_level=None)
probe.executescript("""
CREATE TABLE flat(job_id INTEGER, machine_id TEXT, technician TEXT, done_on TEXT);
INSERT INTO flat VALUES (1,'cnc-01','tech-0','2026-01-02'),
                        (1,'cnc-01','tech-0','2026-01-02'),
                        (1,'cnc-01','tech-3','2026-01-02');
CREATE TABLE job(job_id INTEGER PRIMARY KEY, machine_id TEXT, technician TEXT, done_on TEXT);
""")
print("  a second technician on job 1 -> DISTINCT would produce",
      rows(probe.execute("SELECT COUNT(*) FROM (SELECT DISTINCT job_id, machine_id,"
                         " technician, done_on FROM flat)"))[0][0], "job rows")
try:
    probe.execute("INSERT INTO job SELECT DISTINCT job_id, machine_id, technician,"
                  " done_on FROM flat")
    print("  accepted (!)")
except sqlite3.IntegrityError as e:
    print(f"  INSERT INTO job SELECT DISTINCT …  -> {type(e).__name__}: {e}")
print("  job rows after the failure:",
      rows(probe.execute("SELECT COUNT(*) FROM job"))[0][0],
      "<- the whole 20,000-row load rolls back, not just the bad row")
print("  the acceptance test that should run FIRST:")
print("    SELECT job_id, COUNT(DISTINCT technician) n FROM flat_jobpart"
      " GROUP BY job_id HAVING n > 1;")
print("  on this data it returns:",
      len(rows(con.execute("SELECT job_id, COUNT(DISTINCT technician) n "
                           "FROM flat_jobpart GROUP BY job_id HAVING n > 1"))), "rows")
probe.close()

# ---------------------------------------------------------------------------
# 4 · Round 4 — the race
# ---------------------------------------------------------------------------
h("4 · ROUND 4 — PLANS AND EQUALITY (timings live in bench.py)")

A = """
SELECT m.machine_id, m.site, j.technician, SUM(p.part_price) AS cost
FROM job j
JOIN machine m   ON m.machine_id = j.machine_id
JOIN job_part jp ON jp.job_id = j.job_id
JOIN part p      ON p.part_no = jp.part_no
WHERE j.done_on >= date('2026-03-01')
GROUP BY m.machine_id, j.technician
"""
B = """
SELECT machine_id, site, technician, SUM(part_price) AS cost
FROM report_jobpart
WHERE done_on >= date('2026-03-01')
GROUP BY machine_id, technician
"""


def plan_of(sql):
    with sqlite3.connect(DB) as c:          # fresh connection: statements are cached
        return [r[-1] for r in c.execute("EXPLAIN QUERY PLAN " + sql)]


def race(con, arms, reps=REPS):
    for _, sql in arms:
        con.execute(sql).fetchall()         # warm the cache
    out = {label: [] for label, _ in arms}
    for _ in range(reps):
        for label, sql in arms:
            t = time.perf_counter()
            con.execute(sql).fetchall()
            out[label].append((time.perf_counter() - t) * 1000)
    return out


arms = [("A normalized", A), ("B denormalized", B)]
print("  NO TIMINGS ON THIS PAGE. bench.py is the only harness that reports")
print("  milliseconds, and the reason is a result in itself: when I timed the same")
print("  two queries from inside this script — which rebuilds a 200k table and runs")
print("  dependency checks over it first — arm A's minimum moved from 75 ms to 95 ms")
print("  between two phases that do not touch arm A at all. The effect being measured")
print("  is 20 ms. Timing inside a process that is also doing other work measures the")
print("  other work. Run bench.py on its own; across three consecutive runs it gives")
print("  phase-1 ratios of 1.02-1.04, phase-2 of 1.46-1.48, and — after one ANALYZE —")
print("  0.73-0.75, i.e. the NORMALIZED design winning. See benchmark.md section 4.")
print("  What belongs here is everything that is NOT a clock reading:")

sub("4.1 the two designs return the same answer")
ra, rb = rows(con.execute(A)), rows(con.execute(B))
norm = lambda rs: sorted((r[0], r[2], round(r[3], 4)) for r in rs)
print(f"  rows: A={len(ra)}  B={len(rb)}")
print(f"  total cost: A={sum(r[-1] for r in ra):.1f}  B={sum(r[-1] for r in rb):.1f}")
print(f"  row-for-row identical: {norm(ra) == norm(rb)}")
print("  -> a like-for-like comparison of two designs, not of two questions.")

sub("4.2 the plans, with ix_report_machine present")
for label, sql in arms:
    print(f"  {label}:")
    for line in plan_of(sql):
        print(f"      {line}")
print("  note B: SCAN ... USING INDEX on a query with no WHERE on machine_id and no")
print("  ORDER BY. The index filters nothing; it walks all 200,000 entries and then")
print("  fetches every row by rowid. In a plan, SEARCH skips rows and SCAN does not.")

sub("4.3 the plan after dropping the index — the whole Round 4 finding")
con.execute("DROP INDEX ix_report_machine")
print("  B denormalized, no index:")
for line in plan_of(B):
    print(f"      {line}")
ra2, rb2 = rows(con.execute(A)), rows(con.execute(B))
print(f"  same answer still: {norm(ra2) == norm(rb2)}  ({len(rb2)} rows, "
      f"{sum(r[-1] for r in rb2):.1f})")
con.execute("CREATE INDEX ix_report_machine ON report_jobpart(machine_id)")
print("  index restored.")

sub("4.4 why the join is nearly free: the size of what A probes")
for t in ("job_part", "job", "machine", "part"):
    n = rows(con.execute(f"SELECT COUNT(*) FROM {t}"))[0][0]
    b = rows(con.execute("SELECT SUM(pgsize) FROM dbstat WHERE name=?", (t,)))[0][0] or 0
    print(f"  {t:<10} {n:>7} rows   {b / 1024:9.1f} KB")
print("  the dimensions are 4 KB each and permanently in cache, so A's 600,000")
print("  B-tree probes cost almost nothing. The scan and the GROUP BY cost everything.")

# ---------------------------------------------------------------------------
# 5 · Round 5 — writes and storage
# ---------------------------------------------------------------------------
h("5 · ROUND 5 — WHAT THE COPY COSTS ON WRITES AND ON DISK")

sub("5.1 one machine changes site — rows touched")
print("  cnc-02 appears in: machine",
      rows(con.execute("SELECT COUNT(*) FROM machine WHERE machine_id='cnc-02'"))[0][0],
      "row | job",
      rows(con.execute("SELECT COUNT(*) FROM job WHERE machine_id='cnc-02'"))[0][0],
      "rows | report_jobpart",
      rows(con.execute("SELECT COUNT(*) FROM report_jobpart "
                       "WHERE machine_id='cnc-02'"))[0][0], "rows")
updates = [("UPDATE machine        SET site=…", "UPDATE machine SET site='Bielefeld' "
            "WHERE machine_id='cnc-02'"),
           ("UPDATE report_jobpart SET site=…", "UPDATE report_jobpart SET "
            "site='Bielefeld' WHERE machine_id='cnc-02'")]
measured = {}
for label, sql in updates:
    runs = []
    rowcount = None
    for _ in range(REPS):                   # each attempt in its own transaction,
        con.execute("BEGIN")                # rolled back, so every run starts equal
        t = time.perf_counter()
        cur = con.execute(sql)
        runs.append((time.perf_counter() - t) * 1000)
        rowcount = cur.rowcount
        con.execute("ROLLBACK")
    measured[label] = (rowcount, min(runs))
    print(f"  {label:<34} {rowcount:>5} rows   min {min(runs):7.2f} ms   "
          f"median {statistics.median(runs):7.2f} ms   ({REPS} runs, each rolled back)")
r1, m1 = measured["UPDATE machine        SET site=…"]
r2, m2 = measured["UPDATE report_jobpart SET site=…"]
print(f"  ratio: {r2 // r1}x the rows, {m2 / m1:.0f}x the time")
print("  the row count is the number that scales; the milliseconds are this machine.")
print("  (all rolled back — the database is left exactly as setup.sql built it)")

sub("5.2 storage, per object, from dbstat")
per = rows(con.execute("SELECT name, SUM(pgsize) FROM dbstat GROUP BY name ORDER BY 2 DESC"))
for name, b in per:
    print(f"  {name:<30} {b:>10} bytes   {b / 1024:9.1f} KB")

NORM_T = ("job", "job_part", "part", "machine")
NORM_I = ("sqlite_autoindex_job_part_1", "sqlite_autoindex_part_1",
          "sqlite_autoindex_machine_1")
size = dict(per)
nt = sum(size.get(n, 0) for n in NORM_T)
ni = sum(size.get(n, 0) for n in NORM_I)
dt = size.get("report_jobpart", 0)
di = size.get("ix_report_machine", 0)

sub("5.3 the comparison the module asks for, and the one it leaves out")
print("  the module's query names tables only:")
print(f"    normalized   (job+job_part+part+machine)      {nt:>10} bytes "
      f"{nt / 1024:9.1f} KB")
print(f"    denormalized (report_jobpart)                 {dt:>10} bytes "
      f"{dt / 1024:9.1f} KB   ratio {dt / nt:.2f}x")
print("  but an index is storage too, and both designs have one:")
print(f"    normalized   + its implicit PK indexes        {nt + ni:>10} bytes "
      f"{(nt + ni) / 1024:9.1f} KB")
print(f"    denormalized + ix_report_machine              {dt + di:>10} bytes "
      f"{(dt + di) / 1024:9.1f} KB   ratio {(dt + di) / (nt + ni):.2f}x")
print(f"  job_part's PRIMARY KEY (job_id, part_no) costs {size.get('sqlite_autoindex_job_part_1', 0) / 1024:.1f} KB")
print(f"  on its own — more than the {size.get('job_part', 0) / 1024:.1f} KB table it indexes, because the index")
print("  stores both columns and the table stores both columns plus a rowid.")
print(f"  whole database file: {os.path.getsize(DB) / 1024 / 1024:.1f} MB "
      f"(of which flat_jobpart + its index = "
      f"{(size.get('flat_jobpart', 0) + size.get('ix_flat_machine', 0)) / 1024 / 1024:.1f} MB,")
print("  kept only so the build is reproducible — a production database would drop it)")

# ---------------------------------------------------------------------------
# 6 · Round 7 — the curiosities, with evidence
# ---------------------------------------------------------------------------
h("6 · ROUND 7 — HARVEST: THE CURIOSITIES, EACH WITH ITS EVIDENCE")

sub("6.1 money stored as TEXT: SUM is fine, MAX is wrong")
print("  typeof(flat_jobpart.part_price) :",
      rows(con.execute("SELECT typeof(part_price) FROM flat_jobpart LIMIT 1"))[0][0])
print("  typeof(part.part_price)         :",
      rows(con.execute("SELECT typeof(part_price) FROM part LIMIT 1"))[0][0])
print("  SUM over TEXT                   :",
      rows(con.execute("SELECT SUM(part_price) FROM flat_jobpart"))[0][0])
print("  SUM over REAL (same facts)      :",
      rows(con.execute("SELECT SUM(p.part_price) FROM job_part jp "
                       "JOIN part p ON p.part_no=jp.part_no"))[0][0])
print("  MAX over TEXT                   :",
      rows(con.execute("SELECT MAX(part_price) FROM flat_jobpart"))[0][0],
      "  <- WRONG: string order, '9.00' > '15.00'")
print("  MAX over REAL                   :",
      rows(con.execute("SELECT MAX(part_price) FROM part"))[0][0])
print("  ORDER BY the TEXT column        :",
      [r[0] for r in rows(con.execute("SELECT DISTINCT part_price FROM flat_jobpart "
                                      "ORDER BY part_price LIMIT 5"))])
print("  ORDER BY the REAL column        :",
      [r[0] for r in rows(con.execute("SELECT part_price FROM part "
                                      "ORDER BY part_price LIMIT 5"))])
print("  -> aggregation coerced the text and gave the right total; comparison did not.")

sub("6.2 the CROSS JOIN that makes 200,000 rows out of two counters")
print("  20000 jobs x 10 parts =", 20000 * 10,
      "| actual:", rows(con.execute("SELECT COUNT(*) FROM flat_jobpart"))[0][0])
print("  every job uses every part, which is why job_part's composite PK never collides:")
print("    distinct (job_id, part_no) pairs:",
      rows(con.execute("SELECT COUNT(*) FROM (SELECT DISTINCT job_id, part_no "
                       "FROM flat_jobpart)"))[0][0])

sub("6.3 how much of the report table is duplicated bytes")
print("  rows for one machine (cnc-02):",
      rows(con.execute("SELECT COUNT(*) FROM report_jobpart "
                       "WHERE machine_id='cnc-02'"))[0][0])
print("  distinct site values for it  :",
      rows(con.execute("SELECT COUNT(DISTINCT site) FROM report_jobpart "
                       "WHERE machine_id='cnc-02'"))[0][0])
print("  -> one fact, stored 4,000 times. 3NF stores it once.")

# ---------------------------------------------------------------------------
# 6b · Round 6 — the three ways of keeping a denormalized copy fresh
# ---------------------------------------------------------------------------
h("6b · ROUND 6 — COST OF EACH STALENESS STRATEGY")

# Everything in this section creates and drops 200,000-row tables, which leaves
# free pages behind and grows the file even after a DROP. So it runs on a copy:
# otherwise `evidence.py` would hand back a 51 MB database and the 35.4 MB in
# section 5.3 would stop being reproducible.
con.close()
WORK = DB.replace("normalize.db", "normalize-staleness.db")
import shutil as _shutil
_shutil.copy(DB, WORK)
con = sqlite3.connect(WORK, isolation_level=None)
print(f"  (running on a throwaway copy; {os.path.basename(DB)} is not touched)")

REPORT_BUILD = """
CREATE TABLE report_rebuild AS
SELECT j.job_id, m.machine_id, m.site, j.technician, jp.part_no,
       p.part_price, j.done_on
FROM job j
JOIN machine m   ON m.machine_id = j.machine_id
JOIN job_part jp ON jp.job_id = j.job_id
JOIN part p      ON p.part_no = jp.part_no
"""

sub("6b.1 scheduled rebuild — how long a full rebuild of 200,000 rows takes")
builds, idxs = [], []
for _ in range(7):
    con.execute("DROP TABLE IF EXISTS report_rebuild")
    t = time.perf_counter()
    con.execute(REPORT_BUILD)
    builds.append((time.perf_counter() - t) * 1000)
    t = time.perf_counter()
    con.execute("CREATE INDEX ix_rebuild ON report_rebuild(machine_id)")
    idxs.append((time.perf_counter() - t) * 1000)
    con.execute("DROP INDEX ix_rebuild")
con.execute("DROP TABLE IF EXISTS report_rebuild")
print(f"  CREATE TABLE … AS SELECT (200,000 rows)  min {min(builds):6.0f} ms   "
      f"median {statistics.median(builds):6.0f} ms")
print(f"  CREATE INDEX on the result               min {min(idxs):6.0f} ms   "
      f"median {statistics.median(idxs):6.0f} ms")
print(f"  full rebuild from scratch                min {min(builds) + min(idxs):6.0f} ms")
print(f"  -> against a dashboard that refreshes every 30 s, a full rebuild is a")
print(f"     {(min(builds) + min(idxs)) / 30000 * 100:.2f}% duty cycle. The copy can simply be rebuilt.")

sub("6b.2 trigger-maintained copy — per-insert overhead")
con.execute("DROP TABLE IF EXISTS rep_t")
con.execute("CREATE TABLE rep_t AS SELECT * FROM report_jobpart WHERE 0")
TRG = """CREATE TRIGGER trg_rep AFTER INSERT ON job_part BEGIN
  INSERT INTO rep_t SELECT j.job_id, m.machine_id, m.site, j.technician,
         NEW.part_no, p.part_price, j.done_on
  FROM job j JOIN machine m ON m.machine_id = j.machine_id
             JOIN part p    ON p.part_no = NEW.part_no
  WHERE j.job_id = NEW.job_id;
END"""


def insert_batch(with_trigger, n=300):
    con.execute("DROP TRIGGER IF EXISTS trg_rep")
    if with_trigger:
        con.execute(TRG)
    con.execute("DELETE FROM job_part WHERE job_id >= 900000")
    con.execute("DELETE FROM job WHERE job_id >= 900000")
    con.execute("DELETE FROM rep_t")
    ids = range(900000, 900000 + n)
    con.execute("BEGIN")
    for i in ids:
        con.execute("INSERT INTO job VALUES (?,'cnc-02','tech-1','2026-03-15')", (i,))
    con.execute("COMMIT")
    con.execute("BEGIN")
    t = time.perf_counter()
    for i in ids:
        con.execute("INSERT INTO job_part VALUES (?,'P-0002')", (i,))
    elapsed = (time.perf_counter() - t) * 1000
    con.execute("COMMIT")
    return elapsed / n


costs = {}
for label, flag in (("without trigger", False), ("with trigger   ", True)):
    runs = [insert_batch(flag) for _ in range(5)]
    costs[label] = min(runs)
    print(f"  {label}  {min(runs) * 1000:6.2f} us per job_part insert "
          f"(min of 5 batches of 300)")
print(f"  overhead: {costs['with trigger   '] / costs['without trigger']:.2f}x, "
      f"i.e. {(costs['with trigger   '] - costs['without trigger']) * 1000:.2f} us per row")
print(f"  rows the trigger wrote: {rows(con.execute('SELECT COUNT(*) FROM rep_t'))[0][0]}")
print("  -> cheap per insert. The problem is not the cost, it is the coverage:")

sub("6b.3 why one trigger is not enough — what the copy depends on")
print("  report_jobpart denormalizes columns from FOUR tables:")
print("    job_part -> the fact itself      (INSERT / DELETE)")
print("    job      -> technician, done_on  (INSERT / UPDATE / DELETE)")
print("    machine  -> site                 (UPDATE)")
print("    part     -> part_price           (UPDATE)")
print("  so keeping it correct needs a trigger on each, for each DML verb that can")
print("  change a copied column. A trigger on job_part alone cannot see a site")
print("  change at all — Round 5 measured that update as 4,000 rows in the copy.")
print("  Module 4 found the matching failure directly: an AFTER INSERT trigger does")
print("  not fire on the ON CONFLICT DO UPDATE path, so a corrected row silently")
print("  skips maintenance. ~8 triggers to keep one copy fresh, against a sub-200 ms")
print("  rebuild (see 6b.1), is the whole argument for the rebuild.")
con.execute("DROP TRIGGER IF EXISTS trg_rep")
con.execute("DROP TABLE IF EXISTS rep_t")
con.execute("DELETE FROM job_part WHERE job_id >= 900000")
con.execute("DELETE FROM job WHERE job_id >= 900000")

sub("6b.4 materialized views in SQLite")
try:
    con.execute("CREATE MATERIALIZED VIEW mv AS SELECT 1")
    print("  CREATE MATERIALIZED VIEW: accepted (!)")
except sqlite3.OperationalError as e:
    print(f"  CREATE MATERIALIZED VIEW -> OperationalError: {e}")
print("  SQLite has plain views only: a VIEW re-runs its SELECT on every read, so it")
print("  is the normalized query with a nicer name — zero staleness, zero speed-up.")
print("  'Materialized view' in this module means 'a table you rebuild yourself'.")
print("  verification that the copy and the join agree, which any strategy needs:")
diff = rows(con.execute("""
SELECT COUNT(*) FROM (
  SELECT job_id, machine_id, site, technician, part_no, part_price, done_on
  FROM report_jobpart
  EXCEPT
  SELECT j.job_id, m.machine_id, m.site, j.technician, jp.part_no, p.part_price, j.done_on
  FROM job j JOIN machine m ON m.machine_id=j.machine_id
             JOIN job_part jp ON jp.job_id=j.job_id
             JOIN part p ON p.part_no=jp.part_no)"""))[0][0]
print(f"    report_jobpart EXCEPT the join -> {diff} rows "
      f"({'in sync' if diff == 0 else 'STALE'})")

con.close()
os.remove(WORK)
print(f"\n  {os.path.basename(WORK)} removed. {os.path.basename(DB)} is still "
      f"{os.path.getsize(DB) / 1024 / 1024:.1f} MB, as setup.sql built it.")

# ---------------------------------------------------------------------------
# 7 · Stretcher — DuckDB
# ---------------------------------------------------------------------------
h("7 · STRETCHER — THE SAME QUERY IN DUCKDB")
try:
    import csv
    import duckdb
except ImportError:
    print("  duckdb not installed — skipped")
else:
    tmp = os.path.join(HERE, "_duck_csv")
    os.makedirs(tmp, exist_ok=True)
    src = sqlite3.connect(DB)
    tables = ("job", "job_part", "part", "machine", "report_jobpart")
    for t in tables:
        cur = src.execute(f"SELECT * FROM {t}")
        with open(os.path.join(tmp, f"{t}.csv"), "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow([d[0] for d in cur.description])
            w.writerows(cur)
    src.close()
    print("  loaded via CSV, not ATTACH: duckdb's sqlite_scanner extension could not be")
    print("  downloaded in my sandbox. `ATTACH '…/normalize.db' (TYPE sqlite)` is the")
    print("  one-liner to use if your machine can reach extensions.duckdb.org.")

    d = duckdb.connect()
    for t in tables:
        d.execute(f"CREATE TABLE {t} AS SELECT * FROM "
                  f"read_csv_auto('{os.path.join(tmp, t + '.csv')}')")
    print(f"  duckdb {duckdb.__version__}, threads =",
          d.execute("SELECT current_setting('threads')").fetchone()[0])
    print("  done_on arrived as:", d.execute("SELECT typeof(done_on) FROM job "
                                             "LIMIT 1").fetchone()[0],
          "— read_csv_auto inferred a real DATE, SQLite had TEXT")

    # Two edits are needed, and the second one is a finding in itself:
    #   1. date('…') -> DATE '…'
    #   2. DuckDB REFUSES a bare `site` / `m.site` in the select list when it is
    #      not in the GROUP BY. SQLite accepts it silently and picks a value.
    #      machine_id -> site, so adding it changes no row; a column without
    #      such a dependency would have been a silent wrong answer in SQLite.
    DA = (A.replace("date('2026-03-01')", "DATE '2026-03-01'")
           .replace("GROUP BY m.machine_id, j.technician",
                    "GROUP BY m.machine_id, m.site, j.technician"))
    DBq = (B.replace("date('2026-03-01')", "DATE '2026-03-01'")
            .replace("GROUP BY machine_id, technician",
                     "GROUP BY machine_id, site, technician"))
    print("  NOTE: both queries needed GROUP BY ... , site added for DuckDB:")
    print("    SQLite accepts a bare non-aggregated column and picks a value;")
    print("    DuckDB raises BinderException: column \"site\" must appear in the")
    print("    GROUP BY clause. Safe here only because machine_id -> site.")
    for sql in (DA, DBq):
        d.execute(sql).fetchall()
    ds = {"duckdb A (4-way join)": [], "duckdb B (1 table)": []}
    for _ in range(REPS):
        for label, sql in (("duckdb A (4-way join)", DA), ("duckdb B (1 table)", DBq)):
            t = time.perf_counter()
            d.execute(sql).fetchall()
            ds[label].append((time.perf_counter() - t) * 1000)
    for label, xs in ds.items():
        print(f"  {label:<24} min {min(xs):6.2f} ms   median {statistics.median(xs):6.2f} ms")
    print(f"  A / B in duckdb = "
          f"{min(ds['duckdb A (4-way join)']) / min(ds['duckdb B (1 table)']):.2f}x")
    rd = d.execute(DA).fetchall()
    print(f"  rows {len(rd)}, total {sum(r[-1] for r in rd):.1f} "
          f"— same answer as SQLite")
    d.execute("SET threads=1")
    for sql in (DA, DBq):
        d.execute(sql).fetchall()
    one = {"A": [], "B": []}
    for _ in range(REPS):
        for label, sql in (("A", DA), ("B", DBq)):
            t = time.perf_counter()
            d.execute(sql).fetchall()
            one[label].append((time.perf_counter() - t) * 1000)
    print(f"  threads=1: A min {min(one['A']):.2f} ms, B min {min(one['B']):.2f} ms, "
          f"ratio {min(one['A']) / min(one['B']):.2f}x")
    print("  -> the win is the engine, not the core count.")
    d.close()
    for t in tables:
        os.remove(os.path.join(tmp, f"{t}.csv"))
    os.rmdir(tmp)

print(f"\n{'=' * 78}")
print(f"END — {os.path.basename(DB)} is {os.path.getsize(DB) / 1024 / 1024:.1f} MB, "
      f"exactly as setup.sql builds it")
print("=" * 78)
