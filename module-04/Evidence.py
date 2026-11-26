#!/usr/bin/env python3
"""Regenerate every error message, row count and number quoted in module-04/*.md.

    uv run python module-04/evidence.py > module-04/evidence.txt

Nothing in the Module 4 write-ups is typed by hand: if a page quotes an error,
this script produced it. Re-run it after any change to setup.sql, and after
moving to a different SQLite version -- the exact wording of several of these
messages is version-dependent, which is the point of recording the version in
the header.

Each experiment builds its own throwaway database so the sections are
independent and can be read in any order.
"""
import os, pathlib, sqlite3, sys, tempfile

HERE  = pathlib.Path(__file__).parent
SETUP = (HERE / "setup.sql").read_text()


def head(n: str, title: str) -> None:
    print(f"\n{'=' * 78}\n§{n}  {title}\n{'=' * 78}")


class Lab:
    """A fresh edge.db in a temporary directory."""

    def __init__(self, foreign_keys: bool = True, script: str | None = None):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self._tmp.name, "edge.db")
        self.con = sqlite3.connect(self.path)
        self.con.executescript(SETUP)
        if script:
            self.con.executescript(script)
        if foreign_keys:
            self.con.execute("PRAGMA foreign_keys = ON")
        self.con.commit()

    def reopen(self, uri: str | None = None) -> sqlite3.Connection:
        """A *new* connection — pragmas reset to their defaults, which is the point."""
        return (sqlite3.connect(uri, uri=True) if uri else sqlite3.connect(self.path))

    def __enter__(self): return self
    def __exit__(self, *exc): self.con.close(); self._tmp.cleanup()


def attempt(con: sqlite3.Connection, sql: str, args=(), note: str = "") -> None:
    label = " ".join(sql.split())
    if args:
        label += "   -- " + ", ".join(repr(a) for a in args)
    label = (label[:98] + "…") if len(label) > 99 else label
    try:
        con.execute(sql, args)
        con.commit()
        print(f"  ok       {label}")
    except sqlite3.Error as exc:
        print(f"  REJECTED {label}")
        print(f"           {type(exc).__name__}: {exc}")
    if note:
        print(f"           -> {note}")


def q(con: sqlite3.Connection, sql: str):
    return con.execute(sql).fetchall()


# ---------------------------------------------------------------------------
print(f"Module 4 evidence — generated against SQLite {sqlite3.sqlite_version}")
print("Regenerate: uv run python module-04/evidence.py > module-04/evidence.txt")

head("1", "An unconstrained table accepts anything (Task A acceptance test)")
mem = sqlite3.connect(":memory:")
mem.execute("CREATE TABLE t(sensor_id INTEGER, metric TEXT, value REAL)")
junk = [(1, "temp_c", 9000), (1, "temp_c", "hot"), (2, "bogus", -500),
        (None, None, None), ("x", "temp_c", "9000"), (1, "temp_c", float("inf")),
        (2.7, "temp_c", 1), (1, "temp_c", b"\x00\x01")]
for r in junk:
    try:
        mem.execute("INSERT INTO t VALUES (?,?,?)", r)
    except sqlite3.Error as exc:
        print(f"  REJECTED {r!r}: {exc}")
print("  rowid | sensor_id (type) | metric | value (type)")
for row in q(mem, "SELECT rowid, sensor_id, typeof(sensor_id), metric, value, typeof(value) FROM t"):
    print(f"  {row[0]:5d} | {row[1]!r:>8} ({row[2]:>7}) | {row[3]!r:>8} | {row[4]!r:>10} ({row[5]})")
print(f"  rows accepted: {q(mem, 'SELECT COUNT(*) FROM t')[0][0]} of {len(junk)} — nothing complained")

head("2", "CHECK and NULL")
mem.execute("CREATE TABLE n(v REAL CHECK (v BETWEEN -273.15 AND 5000))")
for v in (None, 40.0, 9000.0):
    attempt(mem, "INSERT INTO n VALUES (?)", (v,))
print("  CHECK yields UNKNOWN for NULL, and only FALSE rejects a row.")

head("2b", "The same eight rows against the table I would actually ship")
mem.executescript("""
CREATE TABLE t_strict(
    sensor_id INTEGER NOT NULL,
    metric    TEXT    NOT NULL CHECK (metric IN ('temp_c','vib_rms','spindle_load')),
    value     REAL    NOT NULL CHECK (value BETWEEN -273.15 AND 5000),
    PRIMARY KEY (sensor_id, metric)
) STRICT;""")
for lit in ["(1,'temp_c',9000)", "(1,'temp_c','hot')", "(2,'bogus',-500)",
            "(NULL,NULL,NULL)", "('x','temp_c','9000')", "(1,'temp_c',9e999)",
            "(2.7,'temp_c',1)", "(1,'temp_c',X'0001')",
            "(1,'temp_c',41.5)", "(1,'temp_c',42.0)", "(2.0,'vib_rms',1.2)"]:
    attempt(mem, f"INSERT INTO t_strict VALUES {lit}")
print(f"  accepted: {q(mem, 'SELECT COUNT(*) FROM t_strict')[0][0]} of 11")
print("  -> 2.7 into INTEGER is refused but 2.0 is accepted: the rule is losslessness,")
print("     not textual form. Same rule that lets '41.5' into a REAL column (§3).")

head("2c", "What infinity does once it is in the table")
mem.executescript("CREATE TABLE inf_demo(v REAL NOT NULL) STRICT;")
attempt(mem, "INSERT INTO inf_demo VALUES (9e999)", note="STRICT accepts inf: it is a valid REAL")
attempt(mem, "INSERT INTO inf_demo VALUES (41.5)")
print(f"  typeof: {q(mem, 'SELECT v, typeof(v) FROM inf_demo LIMIT 1')}")
print(f"  SUM, AVG, MAX, MIN over (inf, 41.5): {q(mem, 'SELECT SUM(v), AVG(v), MAX(v), MIN(v) FROM inf_demo')[0]}")
print("  -> one loose sensor poisons every aggregate except MIN. Only the CHECK stops it.")

head("3", "STRICT is weaker than its name: lossless text→REAL conversion")
with Lab() as lab:
    for i, v in enumerate(["'hot'", "'41.5'", "' 41.5 '", "'4e1'", "'41.5abc'", "X'41'", "NULL"]):
        attempt(lab.con, f"INSERT INTO reading(sensor_id,ts,value,interval_s) "
                         f"VALUES (1,'2026-03-01 07:00:{i:02d}',{v},1)")
    print("  what actually landed:")
    for row in q(lab.con, "SELECT ts, value, typeof(value) FROM reading ORDER BY ts"):
        print(f"    {row[0]}  {row[1]!r:>8}  stored as {row[2]}")

head("4", "Task 1 — the five constraint rejections, plus three of my own")
with Lab() as lab:
    attempt(lab.con, "INSERT INTO reading(sensor_id,ts,value,interval_s) VALUES (1,'2026-03-01 08:00:00',41.5,1)")
    print(f"           -> generated column: {q(lab.con, 'SELECT value, interval_s, energy_j FROM reading')}")
    attempt(lab.con, "INSERT INTO reading(sensor_id,ts,value,interval_s) VALUES (1,'2026-03-01 08:00:01',9000,1)",
            note="semantic / domain integrity")
    attempt(lab.con, "INSERT INTO reading(sensor_id,ts,value,interval_s) VALUES (1,'2026-03-01 08:00:02','hot',1)",
            note="STRICT typing")
    attempt(lab.con, "INSERT INTO reading(sensor_id,ts,value,interval_s) VALUES (99,'2026-03-01 08:00:03',40,1)",
            note="referential integrity")
    attempt(lab.con, "INSERT INTO sensor VALUES (3,'cnc-01','temp_c','degC')",
            note="entity integrity")
    attempt(lab.con, "INSERT INTO reading(sensor_id,ts,value,interval_s) VALUES (1,'2026-03-01 08:00:04',40,0)",
            note="mine: interval_s > 0")
    attempt(lab.con, "INSERT INTO sensor VALUES (4,'cnc-02','humidity','%')",
            note="mine: metric not in the enumeration")
    attempt(lab.con, "INSERT INTO reading(sensor_id,ts,value,interval_s,energy_j) VALUES (1,'2026-03-01 08:00:05',40,1,99)",
            note="mine: a generated column is not writable")

head("5", "PRAGMA foreign_keys is per connection and OFF by default")
with Lab() as lab:
    fresh = lab.reopen()
    print(f"  new connection, PRAGMA foreign_keys = {q(fresh, 'PRAGMA foreign_keys')[0][0]}")
    attempt(fresh, "INSERT INTO reading(sensor_id,ts,value,interval_s) VALUES (99,'2026-03-01 08:30:00',40,1)",
            note="orphan accepted — no sensor 99 exists")
    print(f"  orphan rows now present: {q(fresh, 'SELECT COUNT(*) FROM reading WHERE sensor_id NOT IN (SELECT sensor_id FROM sensor)')[0][0]}")
    print(f"  PRAGMA foreign_key_check: {q(fresh, 'PRAGMA foreign_key_check')}")
    fresh.execute("PRAGMA foreign_keys = ON")
    print(f"  after switching it ON, foreign_key_check still: {q(fresh, 'PRAGMA foreign_key_check')}")
    attempt(fresh, "INSERT INTO reading(sensor_id,ts,value,interval_s) VALUES (98,'2026-03-01 08:31:00',40,1)",
            note="new orphans are refused, but the existing one is never revisited")
    fresh.close()

head("6", "Task 2 — UPSERT, and which triggers each path fires")
with Lab() as lab:
    c = lab.con
    c.execute("INSERT INTO reading(sensor_id,ts,value,interval_s) VALUES (1,'2026-03-01 08:00:00',41.5,1)")
    c.commit()
    attempt(c, "INSERT INTO reading(sensor_id,ts,value,interval_s) VALUES (1,'2026-03-01 08:00:00',41.7,1)",
            note="a plain replay collides with ux_reading_sensor_ts")
    c.execute("""INSERT INTO reading(sensor_id,ts,value,interval_s) VALUES (1,'2026-03-01 08:00:00',41.7,1)
                 ON CONFLICT(sensor_id,ts) DO UPDATE SET value = excluded.value""")
    c.commit()
    print(f"  after UPSERT: {q(c, 'SELECT reading_id, ts, value FROM reading')}")
    print(f"  rows for that key: {q(c, 'SELECT COUNT(*) FROM reading WHERE sensor_id=1')[0][0]}  <- still 1")
    print(f"  audit rows: {q(c, 'SELECT audit_id, reading_id, old_value, new_value FROM audit')}")
    print("  -> DO UPDATE fires AFTER UPDATE OF value, so the replay was audited.")
    print("  does DO UPDATE fire the AFTER INSERT alarm trigger?")
    for v in (1.5, 3.4):
        c.execute("""INSERT INTO reading(sensor_id,ts,value,interval_s) VALUES (2,'2026-03-01 09:00:00',?,1)
                     ON CONFLICT(sensor_id,ts) DO UPDATE SET value = excluded.value""", (v,))
        c.commit()
        print(f"    value={v}: reading={q(c, 'SELECT value FROM reading WHERE sensor_id=2')[0][0]}  "
              f"alarms={q(c, 'SELECT COUNT(*) FROM alarm')[0][0]}")
    print("  -> NO. A correction that crosses the threshold on the update path never alarms.")

head("7", "Task 3 — the triggers firing as designed")
with Lab() as lab:
    c = lab.con
    c.execute("INSERT INTO reading(sensor_id,ts,value,interval_s) VALUES (2,'2026-03-01 09:00:00',2.7,1)")
    c.commit()
    print(f"  alarm: {q(c, 'SELECT * FROM alarm')}")
    c.execute("UPDATE reading SET value = 1.4 WHERE sensor_id = 2")
    c.commit()
    print(f"  audit: {q(c, 'SELECT audit_id, reading_id, old_value, new_value FROM audit')}")
    print(f"  alarm count after the UPDATE: {q(c, 'SELECT COUNT(*) FROM alarm')[0][0]}")

head("8", "Statement atomicity — one bad row reverts the whole statement")
with Lab() as lab:
    attempt(lab.con, """INSERT INTO reading(sensor_id,ts,value,interval_s)
                        VALUES (1,'2026-03-01 13:00:00',40,1),(1,'2026-03-01 13:00:01',9000,1)""")
    print(f"  rows stored: {q(lab.con, 'SELECT COUNT(*) FROM reading')[0][0]}  <- 0: the good row went too")

head("9", "Task 5 — BEFORE INSERT, and the phantom alarm")
BEFORE = """
DROP TRIGGER trg_vib_alarm;
CREATE TRIGGER trg_vib_alarm_before
BEFORE INSERT ON reading FOR EACH ROW
WHEN NEW.value > 2.0 AND (SELECT metric FROM sensor WHERE sensor_id = NEW.sensor_id) = 'vib_rms'
BEGIN
    INSERT INTO alarm(sensor_id, ts, value, reason)
    VALUES (NEW.sensor_id, NEW.ts, NEW.value,
            'BEFORE: NEW.reading_id=' || COALESCE(CAST(NEW.reading_id AS TEXT),'NULL') ||
            ' NEW.energy_j='  || COALESCE(CAST(NEW.energy_j AS TEXT),'NULL'));
END;"""
with Lab(script=BEFORE) as lab:
    c = lab.con
    attempt(c, "INSERT INTO reading(sensor_id,ts,value,interval_s) VALUES (2,'2026-03-01 10:00:00',2.7,1)")
    print(f"  alarm written by the BEFORE trigger: {q(c, 'SELECT reason FROM alarm')}")
    print(f"  the row it describes:                {q(c, 'SELECT reading_id, value FROM reading')}")
    print("  -> NEW.reading_id is -1 in a BEFORE trigger: the key is not assigned yet.")
    attempt(c, "INSERT INTO reading(sensor_id,ts,value,interval_s) VALUES (2,'2026-03-01 10:00:01',9000,1)",
            note="alarms first, then fails the domain CHECK")
    print(f"  alarms after the failed insert: {q(c, 'SELECT COUNT(*) FROM alarm')[0][0]}  "
          f"readings: {q(c, 'SELECT COUNT(*) FROM reading')[0][0]}   <- ABORT reverted the trigger too")
    attempt(c, "INSERT OR IGNORE INTO reading(sensor_id,ts,value,interval_s) VALUES (2,'2026-03-01 10:00:02',9000,1)",
            note="OR IGNORE swallows the violation and the statement 'succeeds'")
    print(f"  alarms: {q(c, 'SELECT COUNT(*) FROM alarm')[0][0]}  "
          f"readings: {q(c, 'SELECT COUNT(*) FROM reading')[0][0]}")
    print(f"  the phantom: {q(c, 'SELECT alarm_id, value, reason FROM alarm ORDER BY alarm_id DESC LIMIT 1')}")
    print("  -> an alarm at 9000 mm/s about a reading the database refused to store.")

head("10", "Task 5 — a BEFORE trigger can reject; an AFTER trigger cannot")
with Lab(script="""CREATE TRIGGER trg_reject BEFORE INSERT ON reading FOR EACH ROW
WHEN NEW.value > 2.0 AND (SELECT metric FROM sensor WHERE sensor_id = NEW.sensor_id) = 'vib_rms'
BEGIN SELECT RAISE(ABORT, 'vibration over limit: row refused, not merely alarmed'); END;""") as lab:
    attempt(lab.con, "INSERT INTO reading(sensor_id,ts,value,interval_s) VALUES (2,'2026-03-01 10:02:00',2.7,1)")

head("11", "Task 4 — access control without a server")
with Lab() as lab:
    lab.con.execute("INSERT INTO reading(sensor_id,ts,value,interval_s) VALUES (1,'2026-03-01 14:00:00',41.5,1)")
    lab.con.execute("INSERT INTO reading(sensor_id,ts,value,interval_s) VALUES (2,'2026-03-01 14:00:00',2.4,1)")
    lab.con.commit()
    print(f"  machine_health view: {q(lab.con, 'SELECT * FROM machine_health')}")
    ro = lab.reopen(uri=f"file:{lab.path}?mode=ro")
    print(f"  mode=ro SELECT: {q(ro, 'SELECT COUNT(*) FROM reading')[0][0]} rows")
    attempt(ro, "DELETE FROM reading")
    print("  the same reader can also read every base table and the whole schema:")
    print(f"    reading   : {q(ro, 'SELECT reading_id, sensor_id, value FROM reading')}")
    print(f"    alarm     : {q(ro, 'SELECT COUNT(*) FROM alarm')[0][0]} rows")
    schema_sql = "SELECT name FROM sqlite_master WHERE type IN ('table','view')"
    print(f"    schema    : {[r[0] for r in q(ro, schema_sql)]}")
    print("  -> the view is a convenience, not a boundary: there is no GRANT to revoke.")
    ro.close()
    qo = lab.reopen()
    qo.execute("PRAGMA query_only = ON")
    attempt(qo, "DELETE FROM reading", note="PRAGMA query_only is advisory: the holder can switch it off again")
    qo.execute("PRAGMA query_only = OFF")
    attempt(qo, "DELETE FROM reading", note="…and here it is, switched off")
    qo.close()
    attempt(lab.con, "INSERT INTO machine_health VALUES ('cnc-09','temp_c',1,1)",
            note="a plain view is not writable at all")

head("12", "The two schema gaps from constraints.md §6, and fixes that close them")
gap = sqlite3.connect(":memory:")
gap.executescript(SETUP)
gap.commit()
attempt(gap, "INSERT INTO reading(sensor_id,ts,value,interval_s) VALUES (2,'2026-03-01 09:00:00',4000,1)",
        note="gap 1: 4,000 mm/s of vibration passes the shared range CHECK")
print(f"  …and it raised an alarm: {q(gap, 'SELECT value, reason FROM alarm')}")
attempt(gap, "INSERT INTO reading(sensor_id,ts,value,interval_s) VALUES (1,'yesterday',41.5,1)",
        note="gap 2: ts is TEXT NOT NULL and nothing else")

print("\n  fix for gap 2 — CHECK the shape of ts with GLOB:")
shape = sqlite3.connect(":memory:")
shape.executescript("""CREATE TABLE r(ts TEXT NOT NULL CHECK (
    ts GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9] [0-9][0-9]:[0-9][0-9]:[0-9][0-9]'));""")
for t in ("2026-03-01 08:00:00", "yesterday", "2026-3-1 8:00:00",
          "2026-03-01T08:00:00", "2026-13-45 99:99:99"):
    attempt(shape, "INSERT INTO r VALUES (?)", (t,))
print("  -> GLOB constrains the shape, not the calendar: 2026-13-45 99:99:99 is 'well-formed'.")
print("     A real date check needs strftime(), or a trigger.")

print("\n  fix for gap 1 — a BEFORE trigger reaching into sensor for a per-metric range:")
pm = sqlite3.connect(":memory:")
pm.executescript(SETUP)
pm.executescript("""
CREATE TRIGGER trg_metric_range
BEFORE INSERT ON reading FOR EACH ROW
WHEN NEW.value NOT BETWEEN
       (SELECT CASE metric WHEN 'temp_c' THEN -273.15 ELSE 0.0 END
          FROM sensor WHERE sensor_id = NEW.sensor_id)
   AND (SELECT CASE metric WHEN 'temp_c' THEN 1500.0 WHEN 'vib_rms' THEN 50.0 ELSE 150.0 END
          FROM sensor WHERE sensor_id = NEW.sensor_id)
BEGIN
    SELECT RAISE(ABORT, 'value out of range for this metric');
END;""")
pm.commit()
for sid, v in ((1, 41.5), (1, 4000), (2, 1.2), (2, 4000), (2, -1)):
    attempt(pm, "INSERT INTO reading(sensor_id,ts,value,interval_s) VALUES (?,?,?,1)",
            (sid, f"2026-03-01 1{sid}:00:{abs(int(v)) % 60:02d}", v))
print("  -> a trigger can do what a CHECK cannot: read another table.")

head("13", "Task 2 — the audit table is not idempotent, and two fixes that make it so")
# The same row pattern make-readings.py writes, built inline so this section does
# not depend on readings.csv existing.
clean   = [(1 if i % 2 == 0 else 2,
            f"2026-03-02 {i // 3600 + 6:02d}:{(i // 60) % 60:02d}:{i % 60:02d}",
            round(38.0 + (i % 70) / 10.0, 2) if i % 2 == 0 else round(0.8 + (i % 25) / 10.0, 2),
            1) for i in range(1000)]
replays = clean[100:112]                                             # byte-identical
retries = [(a, b, round(c + 0.3, 2), d) for a, b, c, d in clean[200:203]]   # corrected
BATCH   = clean + replays + retries

UPSERT_PLAIN = ("INSERT INTO reading(sensor_id,ts,value,interval_s) VALUES (?,?,?,?) "
                "ON CONFLICT(sensor_id,ts) DO UPDATE SET value = excluded.value")
UPSERT_GUARD = UPSERT_PLAIN + " WHERE value <> excluded.value"
TRIGGER_GUARD = """
DROP TRIGGER trg_reading_audit;
CREATE TRIGGER trg_reading_audit
AFTER UPDATE OF value ON reading FOR EACH ROW
WHEN OLD.value IS NOT NEW.value
BEGIN
    INSERT INTO audit(reading_id, old_value, new_value)
    VALUES (NEW.reading_id, OLD.value, NEW.value);
END;"""

print(f"  {'arm':38s} {'run 1':>18s} {'run 2':>18s} {'run 3':>18s}   non-changes")
print(f"  {'':38s} {'reading/audit':>18s} {'reading/audit':>18s} {'reading/audit':>18s}")
print("  " + "-" * 98)
for label, upsert, guard in [("as shipped",                   UPSERT_PLAIN, False),
                             ("fix A — WHERE on the UPSERT",  UPSERT_GUARD, False),
                             ("fix B — WHEN on the trigger",  UPSERT_PLAIN, True),
                             ("both fixes",                   UPSERT_GUARD, True)]:
    with Lab(script=(TRIGGER_GUARD if guard else None)) as lab:
        cells = []
        for _ in range(3):
            with lab.con:
                for row in BATCH:
                    lab.con.execute(upsert, row)
            cells.append(f"{q(lab.con, 'SELECT COUNT(*) FROM reading')[0][0]:5,d}/"
                         f"{q(lab.con, 'SELECT COUNT(*) FROM audit')[0][0]:<6,d}")
        noop = q(lab.con, "SELECT COUNT(*) FROM audit WHERE old_value IS new_value")[0][0]
        print(f"  {label:38s} {cells[0]:>18s} {cells[1]:>18s} {cells[2]:>18s}   {noop:6,d}")
print("  -> 'as shipped' writes 1,015 audit rows per replay, almost all recording a non-change.")
print("     Both fixes reduce that to 6, and combining them adds nothing: same fix, two layers.")
print("     The residual 6/run is the test file itself holding two values for three keys.")

head("14", "Task 2 — the alarm hole: a correction that never alarms")
for label, upsert in (("plain UPSERT", UPSERT_PLAIN), ("fix A", UPSERT_GUARD)):
    with Lab() as lab:
        lab.con.execute(upsert, (2, "2026-03-01 11:00:00", 1.5, 1))
        lab.con.execute(upsert, (2, "2026-03-01 11:00:00", 3.4, 1))
        lab.con.commit()
        print(f"  {label:12s} stored value {q(lab.con, 'SELECT value FROM reading')[0][0]} "
              f"(> 2.0 threshold), alarms = {q(lab.con, 'SELECT COUNT(*) FROM alarm')[0][0]}")
print("  -> neither fix closes it: the alarm trigger is AFTER INSERT and this took DO UPDATE.")
print("  an AFTER UPDATE companion trigger does close it, without duplicating on further replays:")
with Lab(script="""
CREATE TRIGGER trg_vib_alarm_upd
AFTER UPDATE OF value ON reading FOR EACH ROW
WHEN NEW.value > 2.0 AND OLD.value <= 2.0
     AND (SELECT metric FROM sensor WHERE sensor_id = NEW.sensor_id) = 'vib_rms'
BEGIN
    INSERT INTO alarm(sensor_id, ts, value, reason)
    VALUES (NEW.sensor_id, NEW.ts, NEW.value, 'vibration over 2.0 mm/s (on correction)');
END;""") as lab:
    for v in (1.5, 3.4, 3.4, 4.0):
        lab.con.execute(UPSERT_PLAIN, (2, "2026-03-01 11:00:00", v, 1))
        lab.con.commit()
        print(f"    ingest value {v}: alarms = {q(lab.con, 'SELECT COUNT(*) FROM alarm')[0][0]}")
    print(f"    {q(lab.con, 'SELECT value, reason FROM alarm')}")
    print("  -> OLD.value <= 2.0 makes it edge-triggered: it fires on the crossing, not on"
          " every replay above the line.")

head("15", "Task 4 — chmod 444 at the file level")
# On a normal account this is a two-line test. It needs care only when the script
# runs as root, because root ignores file permissions -- so in that case the write
# is attempted from a child process that has dropped to an unprivileged user.
CHILD = """
import sqlite3, os, sys
print(f"  (child euid {os.geteuid()})")
con = sqlite3.connect(sys.argv[1])
print(f"  SELECT: {con.execute('SELECT COUNT(*) FROM reading').fetchone()[0]} row(s)")
try:
    con.execute("DELETE FROM reading")
    con.commit()
    print("  DELETE: ok -- NOT blocked")
except sqlite3.Error as exc:
    print(f"  DELETE: {type(exc).__name__}: {exc}")
"""

with Lab() as lab:
    lab.con.execute("INSERT INTO reading(sensor_id,ts,value,interval_s) VALUES (1,'2026-03-01 14:00:00',41.5,1)")
    lab.con.commit()
    lab.con.close()
    os.chmod(lab.path, 0o444)
    print(f"  file mode: {oct(os.stat(lab.path).st_mode)[-3:]}    euid: {os.geteuid()}")

    if os.geteuid() != 0:
        con = sqlite3.connect(lab.path)
        print(f"  SELECT: {con.execute('SELECT COUNT(*) FROM reading').fetchone()[0]} row(s)")
        attempt(con, "DELETE FROM reading")
        con.close()
    else:
        print("  running as root, which ignores file permissions — dropping privileges to test")
        import pwd, subprocess
        runner = pathlib.Path(lab.path).with_name("ro_check.py")
        runner.write_text(CHILD)
        os.chmod(pathlib.Path(lab.path).parent, 0o755)
        os.chmod(runner, 0o644)
        try:
            user = pwd.getpwnam("nobody")
            done = subprocess.run([sys.executable, "-I", str(runner), lab.path],
                                  user=user.pw_uid, group=user.pw_gid,
                                  capture_output=True, text=True, timeout=60)
            print(done.stdout.rstrip() or "  (no output)")
            if done.stderr.strip():
                print("  child stderr:", done.stderr.strip().splitlines()[-1])
        except (KeyError, OSError, subprocess.SubprocessError) as exc:
            print(f"  could not drop privileges here ({type(exc).__name__}: {exc});"
                  " run this arm on a normal account")
    os.chmod(lab.path, 0o644)
    print("  -> reads work, writes do not — and unlike PRAGMA query_only the holder of")
    print("     the connection cannot lift it: that needs permission on the file.")

print("\n" + "=" * 78)
print("end of evidence")
