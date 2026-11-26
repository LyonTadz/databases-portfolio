# Module 4 — Task 3: triggers for alarms and audit

> Task 3 · [Module 4 portfolio page](./README.md) · DDL in [`setup.sql`](./setup.sql) ·
> benchmark in [`trigger-bench.py`](./trigger-bench.py)
>
> Reproduced by [`evidence.py`](./evidence.py) → [`evidence.txt`](./evidence.txt), `[§n]`.
> **SQLite 3.53.1.**

## 1. The two triggers

```sql
-- A semantic rule the application cannot forget.
CREATE TRIGGER trg_vib_alarm
AFTER INSERT ON reading
FOR EACH ROW
WHEN NEW.value > 2.0
     AND (SELECT metric FROM sensor WHERE sensor_id = NEW.sensor_id) = 'vib_rms'
BEGIN
    INSERT INTO alarm(sensor_id, ts, value, reason)
    VALUES (NEW.sensor_id, NEW.ts, NEW.value, 'vibration over 2.0 mm/s');
END;

-- An immutable trail of every corrected value.
CREATE TRIGGER trg_reading_audit
AFTER UPDATE OF value ON reading
FOR EACH ROW
BEGIN
    INSERT INTO audit(reading_id, old_value, new_value)
    VALUES (NEW.reading_id, OLD.value, NEW.value);
END;
```

The `WHEN` clause on the first one is doing something a `CHECK` cannot: it reads `sensor` to find
out what the number *means* before deciding whether 2.7 is alarming. 2.7 °C is a cold workshop;
2.7 mm/s is a bearing starting to go. This is the clearest example I have of why the semantic
layer needs triggers and not just `CHECK` constraints — a `CHECK` on `reading` cannot see
`sensor`, so it cannot ask the question.

## 2. Them firing `[§7]`

```sql
INSERT INTO reading(sensor_id, ts, value, interval_s) VALUES (2,'2026-03-01 09:00:00', 2.7, 1);
UPDATE reading SET value = 1.4 WHERE sensor_id = 2;
```

```
alarm: [(1, 2, '2026-03-01 09:00:00', 2.7, 'vibration over 2.0 mm/s')]
audit: [(1, 1, 2.7, 1.4)]
alarm count after the UPDATE: 1
```

Nothing in either statement mentions `alarm` or `audit`. That is the whole point: a writer that
has never read this file still cannot insert a 2.7 mm/s reading without raising an alarm, and
cannot correct a value without leaving a trail.

Note the alarm count stays at **1** after the `UPDATE`. The alarm trigger is `AFTER INSERT`, so
the update path does not touch it. That looks like a detail and it is §5.

## 3. What the alarm trigger costs [`trigger-bench.py`](./trigger-bench.py)

The module says to time 10,000 rows with and without the trigger. I ran that, got a number, and
could not interpret it — because the trigger has two costs that move independently: evaluating
the `WHEN` clause, which happens on **every** insert, and performing the alarm `INSERT`, which
happens only on rows that cross the threshold. Two arms cannot separate them, so I ran five.

10,000 rows per measurement, `executemany` in one transaction, 15 interleaved repetitions, audit
trigger dropped so only the alarm trigger is measured:

| arm | min | vs baseline | median | max | alarm rows |
|---|---|---|---|---|---|
| no alarm trigger at all | 12.6 ms | 1.00× | 13.4 ms | 18.8 | 0 |
| trigger on, **0%** of rows alarm | 16.2 ms | **1.29×** | 18.0 ms | 27.9 | 0 |
| trigger on, 1% of rows alarm | 17.0 ms | 1.36× | 19.6 ms | 28.2 | 100 |
| trigger on, 50% of rows alarm | 19.5 ms | 1.55× | 22.2 ms | 33.3 | 5,000 |
| trigger on, 100% of rows alarm | 22.9 ms | 1.82× | 26.2 ms | 36.4 | 10,000 |

**A trigger that never fires once still costs about 30%.** That is the line I would defend, and
it is the answer to the module's hint that a trigger on a hot ingest path is a design decision
rather than a free lunch. Across repeated runs of the script the figure sits between +29% and
+37%; I would not quote it tighter than "about a third".

That fixed cost is the `WHEN` clause: a correlated subquery against `sensor`, executed once per
row, 10,000 times, to answer a question whose answer never changes. The variable part is cheap
by comparison — the marginal cost of an actual alarm is **0.67 µs**, so going from 0% to 1%
alarms is +0.9 ms, which is inside this benchmark's noise. **Almost the entire cost of this
trigger is paid by the rows that do nothing.**

### The methodology mattered more than the result

My first version ran 7 repetitions per arm, each arm's repetitions back to back, and reported
medians. I ran the script twice to check and got **+22% and then +31%** for the same headline
number. A third run put the 0%-alarm arm *faster* than the 1% arm, which cannot be true — 100
extra inserts cannot make 10,000 inserts quicker — and that impossibility is what told me the
measurement was broken rather than the schema being interesting.

Two changes fixed it, and both are general:

- **Interleave the arms.** One pass over all five arms is one repetition. Running an arm's
  repetitions consecutively lets anything that drifts during the run land on one arm and look
  like a finding.
- **Estimate with the minimum, not the median.** Measurement noise here is one-sided: an
  interruption adds time to a run, and nothing ever makes the work faster than it actually is.
  So the fastest observed run is the closest estimate of the true cost, and the median drags in
  whatever else the machine was doing. The table above shows why: every `max` is 40–70% above
  its own `min`, the medians moved the headline by 15 percentage points between runs, and the
  minima stayed inside half a millisecond across every run I did.

This is the Module 3 lesson arriving again from a different direction. There I learned to write
down the plans that did not change, so I could tell a real improvement from noise. Here the
same problem was hiding inside a single number that looked perfectly respectable.

### What I would try next, and have not

- **Reorder the `WHEN` clause.** `NEW.value > 2.0` is a comparison on a value already in hand;
  the subquery is a B-tree lookup. Putting the cheap test first should let SQLite skip the
  subquery on every row below the threshold. I do not know whether SQLite already reorders this
  internally and I am not going to claim it does — the clause is written in the module's order
  in [`setup.sql`](./setup.sql), and this is the first thing I would measure.
- **Denormalise `metric` onto `reading`.** Then the `WHEN` clause is two local comparisons and
  no subquery at all, at the cost of a duplicated column that can disagree with `sensor`. That
  trade-off is Module 5's subject, and it is more interesting to arrive at it from a trigger
  benchmark than from a schema diagram.

### On the honesty of these numbers

12.6 ms for 10,000 inserts is roughly 790,000 rows a second, which is not a plausible figure for
a gateway on an OpenWrt router. It is a database file on fast storage, written inside one
transaction, which is SQLite's best case and nothing like the real thing. The **ratios** are
what I would carry over. The absolute numbers belong to this machine and to **SQLite 3.53.1**,
not to the 3.45.3 I have locally — anyone re-running
[`trigger-bench.py`](./trigger-bench.py) should expect different milliseconds and similar
multiples.

## 4. The audit table is not idempotent `[§13]`

Covered in full in [`upsert.md`](./upsert.md) §4, because it only appears when Task 2 and Task 3
are both present. In one line: `ON CONFLICT ... DO UPDATE` is an `UPDATE`, so a replayed reading
fires `trg_reading_audit` even when the value is unchanged, and three identical ingest runs take
`audit` from 15 rows to 2,045 — 2,030 of which record a change that did not happen. The fix is a
`WHEN OLD.value IS NOT NEW.value` guard on the trigger.

## 5. The alarm hole `[§14]`

This is the finding I am most pleased with, and it needed both tasks to see.

`trg_vib_alarm` is `AFTER INSERT`. A replayed reading takes the `DO UPDATE` path. So:

```
ingest 1.5 mm/s  (below threshold)  -> alarms 0
replay corrects it to 3.4 mm/s      -> alarms 0      <- stored value is 3.4
```

**A reading that arrives benign and is corrected to a value above the alarm threshold never
alarms.** The database holds 3.4 mm/s, the audit trail correctly records 1.5 → 3.4, and nobody
is told. Neither of the idempotence fixes in §4 closes it — I checked, because I assumed one
would `[§14]`.

This is not a contrived case. The whole premise of Task 2 is that the gateway retries and
corrects after an outage, and a sensor that was misreporting low during the outage and reports
correctly on the retry is exactly the failure a vibration alarm exists to catch.

The fix is a companion trigger on the update path, made edge-triggered so replays do not spam it
`[§14]`:

```sql
CREATE TRIGGER trg_vib_alarm_upd
AFTER UPDATE OF value ON reading FOR EACH ROW
WHEN NEW.value > 2.0 AND OLD.value <= 2.0
     AND (SELECT metric FROM sensor WHERE sensor_id = NEW.sensor_id) = 'vib_rms'
BEGIN
    INSERT INTO alarm(sensor_id, ts, value, reason)
    VALUES (NEW.sensor_id, NEW.ts, NEW.value, 'vibration over 2.0 mm/s (on correction)');
END;
```

```
ingest 1.5: alarms 0
ingest 3.4: alarms 1      <- the crossing
ingest 3.4: alarms 1      <- replay, no duplicate
ingest 4.0: alarms 1      <- still above the line, not a new crossing
```

`OLD.value <= 2.0` is what makes it fire on the **transition** rather than on the state. Without
it, every replay of an already-alarming reading would add another alarm row and the
idempotence problem from §4 would reappear in `alarm` instead of `audit`.

The general lesson, which I think is the real content of this module: **`AFTER INSERT` and
`AFTER UPDATE` are two different rules, and a domain rule like "tell someone when vibration
exceeds 2.0" needs both.** Writing it once and reading it back felt complete. It covered one of
the two ways a row can come to hold that value.

## 6. The per-metric range check `[§12]`

`CHECK (value BETWEEN -273.15 AND 5000)` is shared by temperature, vibration and spindle load,
so **4,000 mm/s of vibration is a legal reading** in the schema as given — and it raises an
alarm rather than being refused, so it reaches the operator as a plausible-looking emergency
instead of as a rejected row `[§12]`. A `CHECK` cannot fix this: the limit depends on `metric`,
which lives in `sensor`.

A `BEFORE INSERT` trigger can, because it can read another table:

```sql
CREATE TRIGGER trg_metric_range
BEFORE INSERT ON reading FOR EACH ROW
WHEN NEW.value NOT BETWEEN
       (SELECT CASE metric WHEN 'temp_c' THEN -273.15 ELSE 0.0 END
          FROM sensor WHERE sensor_id = NEW.sensor_id)
   AND (SELECT CASE metric WHEN 'temp_c' THEN 1500.0 WHEN 'vib_rms' THEN 50.0 ELSE 150.0 END
          FROM sensor WHERE sensor_id = NEW.sensor_id)
BEGIN
    SELECT RAISE(ABORT, 'value out of range for this metric');
END;
```

Tested `[§12]`: temperature 41.5 passes, temperature 4,000 is refused, vibration 1.2 passes,
vibration 4,000 is refused, vibration −1 is refused. This is also the only place in the module
where `BEFORE` is clearly the right choice rather than the wrong one — see
[`stretcher.md`](./stretcher.md) — because rejecting a row is the one thing an `AFTER` trigger
cannot do.

Two more `WHEN` subqueries per insert is a real cost on the ingest path (§3). A better design
puts the limits in a table (`metric_limit(metric, lo, hi)`) and joins once, rather than hard-coding
a `CASE` in trigger DDL that has to be dropped and recreated to change a threshold. I have not
built that; it is the first thing I would do if this were real.

---

[← Task 2: UPSERT](./upsert.md) · [Module 4 page](./README.md) · [Task 4: access control →](./access-control.md)
