#!/usr/bin/env python3
"""Generate module-04/readings.csv — the gateway's replay buffer.

readings.csv is NOT committed (.gitignore keeps *.csv out), so this script is
the recipe a reviewer runs to rebuild it:

    uv run python module-04/make-readings.py

It writes 1,000 readings for the two seeded sensors, deliberately including:
  * 12 exact duplicate (sensor_id, ts) pairs, as a gateway replay produces;
  * 3 duplicates whose value differs, as a sensor retry produces;
  * 4 rows the database must refuse (impossible temperature, text value,
    zero interval, unknown sensor), so the ingest loop's error handling is
    exercised rather than assumed.
"""
import csv, pathlib

OUT = pathlib.Path(__file__).with_name("readings.csv")
rows = []

# 1,000 well-formed readings: sensor 1 = temp_c, sensor 2 = vib_rms.
for i in range(1000):
    sid = 1 if i % 2 == 0 else 2
    ts = f"2026-03-02 {i // 3600 + 6:02d}:{(i // 60) % 60:02d}:{i % 60:02d}"
    value = round(38.0 + (i % 70) / 10.0, 2) if sid == 1 else round(0.8 + (i % 25) / 10.0, 2)
    rows.append((sid, ts, value, 1))

# 12 byte-identical replays, and 3 retries that correct the value.
replays = rows[100:112]
retries = [(sid, ts, round(v + 0.3, 2), iv) for sid, ts, v, iv in rows[200:203]]

# 4 rows the schema must reject.
bad = [
    (1, "2026-03-02 23:00:00", 9000,    1),   # domain CHECK
    (1, "2026-03-02 23:00:01", "hot",   1),   # STRICT typing
    (1, "2026-03-02 23:00:02", 40.0,    0),   # CHECK interval_s > 0
    (99, "2026-03-02 23:00:03", 40.0,   1),   # referential integrity
]

with OUT.open("w", newline="") as fh:
    w = csv.writer(fh)
    w.writerow(["sensor_id", "ts", "value", "interval_s"])
    w.writerows(rows + replays + retries + bad)

print(f"{OUT.name}: {len(rows) + len(replays) + len(retries) + len(bad)} data rows "
      f"({len(rows)} clean, {len(replays)} exact replays, {len(retries)} corrected retries, {len(bad)} invalid)")
