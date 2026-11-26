#!/usr/bin/env python3
"""Task 3 — what the alarm trigger costs on the ingest path.

    uv run python module-04/trigger-bench.py

The module says to time 10,000 rows "with and without the alarm trigger". Two arms
turned out not to answer the question, because the trigger has two costs that move
independently:

  * evaluating the WHEN clause, which happens on EVERY insert even when nothing
    alarms — and this WHEN clause contains a correlated subquery against `sensor`;
  * performing the alarm INSERT, which happens only on rows crossing 2.0 mm/s.

So this runs five arms at different alarm rates. Two things about the method, both
of which I got wrong first time and which changed the headline number:

  * **The arms are interleaved, not run back to back.** One full pass over all five
    arms counts as one repetition. Running an arm's repetitions consecutively lets
    anything that drifts during the run (page cache, CPU frequency, a neighbour on
    the machine) land on one arm and look like a result.
  * **The estimator is the minimum, not the median.** This was the correction that
    mattered. Measurement noise on a shared machine is one-sided: an interruption
    adds time to a run, nothing ever makes the work faster than it is. So the
    fastest observed run is the closest estimate of the real cost, and the median
    drags in whatever else the machine was doing. Repeating this script, the medians
    moved the headline between +21% and +42% while every minimum stayed inside
    0.5 ms — and at a median of 7 repetitions the 0%-alarm arm came out *slower*
    than the 1% arm, which cannot happen and is how I noticed. Medians are printed
    alongside so the gap between the two is visible.

Each measurement builds a fresh database, inserts 10,000 rows in one transaction
with executemany, and drops the audit trigger so that only the alarm trigger is
being measured.
"""
import os, pathlib, sqlite3, statistics, tempfile, time

HERE  = pathlib.Path(__file__).parent
SETUP = (HERE / "setup.sql").read_text()
N, REPS = 10_000, 15

ARMS = [("no alarm trigger at all",      False, 0.00),
        ("trigger on,   0% rows alarm",  True,  0.00),
        ("trigger on,   1% rows alarm",  True,  0.01),
        ("trigger on,  50% rows alarm",  True,  0.50),
        ("trigger on, 100% rows alarm",  True,  1.00)]


def payload(rate: float) -> list[tuple]:
    """10,000 vib_rms readings, `rate` of them above the 2.0 mm/s threshold."""
    hot = int(round(rate * 100))
    return [(2,
             f"2026-04-01 {i // 3600:02d}:{(i // 60) % 60:02d}:{i % 60:02d}",
             2.5 if (i % 100) < hot else 1.2,
             1)
            for i in range(N)]


def once(with_trigger: bool, rows: list[tuple]) -> tuple[float, int]:
    with tempfile.TemporaryDirectory() as tmp:
        con = sqlite3.connect(os.path.join(tmp, "bench.db"))
        con.executescript(SETUP)
        if not with_trigger:
            con.execute("DROP TRIGGER trg_vib_alarm")
        con.execute("DROP TRIGGER trg_reading_audit")
        con.commit()

        t0 = time.perf_counter()
        con.executemany(
            "INSERT INTO reading(sensor_id, ts, value, interval_s) VALUES (?,?,?,?)", rows)
        con.commit()
        elapsed = (time.perf_counter() - t0) * 1000

        alarms = con.execute("SELECT COUNT(*) FROM alarm").fetchone()[0]
        con.close()
        return elapsed, alarms


def main() -> None:
    rows = {rate: payload(rate) for _, _, rate in ARMS}
    times: dict[str, list[float]] = {label: [] for label, _, _ in ARMS}
    alarms: dict[str, int] = {}

    for rep in range(REPS):                      # interleaved: one pass = one rep
        for label, trg, rate in ARMS:
            ms, n = once(trg, rows[rate])
            times[label].append(ms)
            alarms[label] = n

    print(f"SQLite {sqlite3.sqlite_version} | {N:,} rows per measurement "
          f"| {REPS} interleaved repetitions\n")
    print(f"{'arm':30s} {'min':>8s} {'vs base':>8s} {'median':>9s} {'max':>8s} {'alarms':>8s}")
    print("-" * 78)
    base = min(times[ARMS[0][0]])
    for label, _, _ in ARMS:
        t = times[label]
        print(f"{label:30s} {min(t):6.1f}ms {min(t) / base:7.2f}x "
              f"{statistics.median(t):7.1f}ms {max(t):7.1f} {alarms[label]:8,d}")
    zero, full = min(times[ARMS[1][0]]), min(times[ARMS[4][0]])
    one = min(times[ARMS[2][0]])
    print(f"\nA trigger that never fires once: {(zero / base - 1) * 100:+.0f}% over baseline.")
    print(f"Going from 0% to 1% alarms:      {(one - zero):+.1f} ms "
          f"— below the resolution of this benchmark.")
    print(f"Marginal cost of one alarm:      {(full - zero) / N * 1000:.2f} us "
          f"({(full - zero):.1f} ms for {N:,} alarms).")


if __name__ == "__main__":
    main()
