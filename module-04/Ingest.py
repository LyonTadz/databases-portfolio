#!/usr/bin/env python3
"""Task 2 — idempotent edge ingestion.

Reads module-04/readings.csv and UPSERTs it into module-04/edge.db. Running it
twice on the same file must not change the row count: that is the whole point.

    sqlite3 module-04/edge.db ".read module-04/setup.sql"
    uv run python module-04/make-readings.py
    uv run python module-04/ingest.py          # first run
    uv run python module-04/ingest.py          # second run — counts must match

Three things here are deliberate and were not obvious to me before this module:

1. ``PRAGMA foreign_keys = ON`` is issued on *this* connection. It is off by
   default and it is per-connection, so a script that forgets it silently
   accepts orphan readings. Module04/constraints.md §5 has the proof.
2. The UPSERT targets ``(sensor_id, ts)`` — the natural key of the telemetry
   stream — not ``reading_id``, which is an arbitrary surrogate the gateway
   does not know.
3. Rows are inserted one statement at a time inside a single transaction, not
   with a single multi-row statement. A multi-row INSERT is atomic per
   *statement*: one bad row reverts all of them. Per-row execution lets the
   four known-bad rows be rejected individually and counted, which is what an
   edge gateway with no DBA actually needs.
"""
import csv, pathlib, sqlite3, sys

HERE = pathlib.Path(__file__).parent
DB   = HERE / "edge.db"
CSV  = HERE / "readings.csv"

UPSERT = """
INSERT INTO reading(sensor_id, ts, value, interval_s)
VALUES (?, ?, ?, ?)
ON CONFLICT(sensor_id, ts) DO UPDATE SET value = excluded.value
"""


def main() -> int:
    if not DB.exists():
        sys.exit(f"{DB} missing — run: sqlite3 {DB} \".read {HERE/'setup.sql'}\"")
    if not CSV.exists():
        sys.exit(f"{CSV} missing — run: uv run python {HERE/'make-readings.py'}")

    with CSV.open(newline="") as fh:
        rows = [(r["sensor_id"], r["ts"], r["value"], r["interval_s"])
                for r in csv.DictReader(fh)]

    con = sqlite3.connect(DB)
    con.execute("PRAGMA foreign_keys = ON")          # per connection, off by default
    before = con.execute("SELECT COUNT(*) FROM reading").fetchone()[0]

    accepted = rejected = 0
    errors: dict[str, int] = {}
    with con:                                        # one transaction for the batch
        for row in rows:
            try:
                con.execute(UPSERT, row)
                accepted += 1
            except sqlite3.Error as exc:
                rejected += 1
                errors[str(exc)] = errors.get(str(exc), 0) + 1

    after = con.execute("SELECT COUNT(*) FROM reading").fetchone()[0]
    alarms = con.execute("SELECT COUNT(*) FROM alarm").fetchone()[0]
    audits = con.execute("SELECT COUNT(*) FROM audit").fetchone()[0]
    dupes = con.execute(
        "SELECT COUNT(*) FROM (SELECT sensor_id, ts FROM reading "
        "GROUP BY sensor_id, ts HAVING COUNT(*) > 1)").fetchone()[0]

    print(f"csv rows            : {len(rows)}")
    print(f"accepted            : {accepted}")
    print(f"rejected            : {rejected}")
    for msg, n in sorted(errors.items()):
        print(f"    {n} x {msg}")
    print(f"reading rows before : {before}")
    print(f"reading rows after  : {after}   (delta {after - before:+d})")
    print(f"duplicate natural keys: {dupes}   <- must be 0")
    print(f"alarm rows          : {alarms}")
    print(f"audit rows          : {audits}")
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
