# Module 4 — Task 2: idempotent edge ingestion with UPSERT

> Task 2 · [Module 4 portfolio page](./README.md) · [`ingest.py`](./ingest.py) ·
> [`make-readings.py`](./make-readings.py)
>
> Reproduced by [`evidence.py`](./evidence.py) → [`evidence.txt`](./evidence.txt), `[§n]`; the row
> counts below come from running `ingest.py` three times in a row. **SQLite 3.53.1.**

## 1. The problem the surrogate key creates

`reading_id INTEGER PRIMARY KEY` is a surrogate: the database invents it. The gateway replaying
its buffer after a two-day outage does not know it and cannot send it, so every replayed reading
looks new. The deduplication has to happen on what the gateway *does* know — which sensor, and
when — so that pair has to become a real key:

```sql
CREATE UNIQUE INDEX ux_reading_sensor_ts ON reading(sensor_id, ts);
```

With that index in place, a plain replay fails loudly `[§6]`:

```
REJECTED  INSERT INTO reading(...) VALUES (1,'2026-03-01 08:00:00',41.7,1)
          UNIQUE constraint failed: reading.sensor_id, reading.ts
```

Which is correct but useless: the gateway cannot distinguish "already have it" from "something
is wrong", and either retries forever or drops data.

## 2. The UPSERT `[§6]`

```sql
INSERT INTO reading(sensor_id, ts, value, interval_s)
VALUES (1,'2026-03-01 08:00:00', 41.7, 1)
ON CONFLICT(sensor_id, ts) DO UPDATE SET value = excluded.value;
```

```
after UPSERT: [(1, '2026-03-01 08:00:00', 41.7)]
rows for that key: 1  <- still 1
```

Two details worth recording. The conflict target is a **unique index**, not a declared
constraint — SQLite accepts either, which is what makes this work without restructuring the
table. And `excluded` is the name of the row that was refused; it is not a table that exists
anywhere, it is bound for the duration of the statement.

`DO UPDATE` is a deliberate choice over `DO NOTHING`. A sensor that retries is usually
*correcting* itself, so last-write-wins is right for telemetry. `DO NOTHING` would be right for
an append-only event log, where the first version is the true one.

## 3. The double run `[`ingest.py`]`

[`make-readings.py`](./make-readings.py) writes 1,019 rows: 1,000 clean readings, 12 byte-identical
replays, 3 retries that correct a value, and 4 rows the schema must refuse. Then:

```
--- RUN 1 ---                          --- RUN 2 ---
csv rows            : 1019             csv rows            : 1019
accepted            : 1015             accepted            : 1015
rejected            : 4                rejected            : 4
    1 x CHECK constraint failed: interval_s > 0
    1 x CHECK constraint failed: value >= -273.15 AND value <= 5000
    1 x FOREIGN KEY constraint failed
    1 x cannot store TEXT value in REAL column reading.value
reading rows before : 0                reading rows before : 1000
reading rows after  : 1000  (delta +1000)   reading rows after : 1000  (delta +0)
duplicate natural keys: 0              duplicate natural keys: 0
alarm rows          : 240              alarm rows          : 240
audit rows          : 15               audit rows          : 1030
```

**The row count is right. `delta +0` on the second run is the proof the task asks for**, and the
arithmetic checks out exactly: 1,015 accepted − 15 that took the `DO UPDATE` path = 1,000
inserted. The four rejects are the four planted bad rows, each with the error from
[`constraints.md`](./constraints.md).

And then there is the last line.

## 4. The finding: idempotent in `reading`, not in `audit`

**The audit table grew from 15 rows to 1,030 on a run that changed no data.** A third identical
run takes it to 2,045.

| | run 1 | run 2 | run 3 |
|---|---|---|---|
| `reading` | 1,000 | 1,000 | 1,000 |
| `alarm` | 240 | 240 | 240 |
| **`audit`** | **15** | **1,030** | **2,045** |

Of those 2,045 audit rows, **2,030 have `old_value IS new_value`** — they record a change that
did not happen.

The mechanism, once I traced it: every replayed row takes the `DO UPDATE` branch, because the
key already exists. `DO UPDATE` is an `UPDATE`, so it fires `trg_reading_audit`
(`AFTER UPDATE OF value`). The trigger has no idea the new value equals the old one, so it
writes a row saying 41.5 became 41.5.

This is worse than it sounds for the edge-gateway story the module is telling. The gateway
replays its buffer after *every* outage. The `audit` table is the one table in this schema whose
entire purpose is to be a trustworthy record — and it is the one that fills with noise
proportional to the number of outages, unbounded, on the smallest disk in the plant. The
`reading` table, which everyone is watching, is fine.

What I like about this one is that neither Task 2 nor Task 3 is wrong on its own. The UPSERT is
correct. The audit trigger is correct. The defect only exists when both are present, and the
module introduces them on separate pages.

### The fix, both ways, measured

Two independent places to intervene, and I tested both `[§13]`:

```sql
-- Fix A — at the write: don't update when nothing changed.
ON CONFLICT(sensor_id, ts) DO UPDATE SET value = excluded.value
  WHERE value <> excluded.value;

-- Fix B — at the trigger: don't audit a non-change.
CREATE TRIGGER trg_reading_audit
AFTER UPDATE OF value ON reading FOR EACH ROW
WHEN OLD.value IS NOT NEW.value
BEGIN ... END;
```

| | run 1 | run 2 | run 3 | rows recording a non-change |
|---|---|---|---|---|
| as shipped | 15 | 1,030 | 2,045 | 2,030 |
| fix A (UPSERT `WHERE`) | 3 | 9 | 15 | 0 |
| fix B (trigger `WHEN`) | 3 | 9 | 15 | 0 |
| both | 3 | 9 | 15 | 0 |

Both work, both reduce the per-run growth from 1,015 rows to 6, and **combining them adds
nothing** — which told me they are the same fix applied at two layers rather than two
complementary fixes.

I would ship **fix B**. Fix A depends on every writer remembering the `WHERE` clause, which is
the same failure mode as `PRAGMA foreign_keys` in [`constraints.md`](./constraints.md) §4 — a
rule that lives in the caller is a rule that will be forgotten. Fix B lives in the schema and
cannot be bypassed by a writer that did not read this page. That is the whole argument of the
module, applied to a defect the module did not mention.

Note `IS NOT` rather than `<>` in fix B. `NULL <> NULL` is `UNKNOWN`, so a `WHEN OLD.value <>
NEW.value` guard would silently skip auditing any change involving a `NULL`. `value` is
`NOT NULL` here so it cannot bite today, but it would the moment a nullable column got the same
treatment — the same three-valued-logic trap as `CHECK` with `NULL` in
[`integrity-notes.md`](./integrity-notes.md) §4, in a different costume.

## 5. Why 6 rows per run and not 0

Even fixed, the audit table grows by 6 rows on every run, and that is not a bug — it is the test
file being honest. [`make-readings.py`](./make-readings.py) deliberately contains **two different
values for three of the same `(sensor_id, ts)` keys**: the clean reading, and a retry 0.3 higher.
Each pass writes the clean value, then the retry value, so each pass produces two genuine
changes per affected key: 3 keys × 2 = 6.

The useful statement of this is narrower than "UPSERT makes ingestion idempotent":

> UPSERT makes a replay idempotent **only if the file being replayed is internally
> consistent**. A buffer containing two values for one key cannot be idempotent under
> last-write-wins, because the last write differs depending on where you stop.

I would not have found that without putting conflicting rows in the test data on purpose, and I
put them there expecting them to be boring.

## 6. Why one statement per row

[`ingest.py`](./ingest.py) loops and executes per row rather than using one multi-row `INSERT`
or `executemany` over the whole file. The reason is in [`constraints.md`](./constraints.md) §5: a
multi-row `VALUES` list is a single statement, default conflict resolution is `ABORT`, and
`ABORT` reverts the entire statement — so one impossible temperature discards every good row
that arrived with it. Per-row execution inside a single transaction keeps the batch atomic
against a *crash* while letting individual bad rows be rejected and counted, which is why the
output above can say `rejected: 4` and name all four.

`executemany` has the same per-statement behaviour as the loop (it is a loop), and I used it in
[`trigger-bench.py`](./trigger-bench.py) where every row is known-good and the speed matters.

---

[← Task 1: constraints](./constraints.md) · [Module 4 page](./README.md) · [Task 3: triggers →](./triggers.md)
