# Module 4 — Task 5 (stretcher): break your own alarm

> Task 5 · [Module 4 portfolio page](./README.md)
>
> Reproduced by [`evidence.py`](./evidence.py) → [`evidence.txt`](./evidence.txt), `[§n]`.
> **SQLite 3.53.1.**

The task is to switch the alarm trigger to `BEFORE INSERT`, observe the difference, and document
why `AFTER` was the right default. I expected to find a timing curiosity. I found two concrete
failures, one of which only appears under a conflict-resolution clause the module never mentions.

## 1. The variant

Same trigger, `BEFORE` instead of `AFTER`, with the `reason` column repurposed to report what
the trigger can see of the row it is firing about:

```sql
DROP TRIGGER trg_vib_alarm;

CREATE TRIGGER trg_vib_alarm_before
BEFORE INSERT ON reading FOR EACH ROW
WHEN NEW.value > 2.0 AND (SELECT metric FROM sensor WHERE sensor_id = NEW.sensor_id) = 'vib_rms'
BEGIN
    INSERT INTO alarm(sensor_id, ts, value, reason)
    VALUES (NEW.sensor_id, NEW.ts, NEW.value,
            'BEFORE: NEW.reading_id=' || COALESCE(CAST(NEW.reading_id AS TEXT),'NULL') ||
            ' NEW.energy_j='  || COALESCE(CAST(NEW.energy_j AS TEXT),'NULL'));
END;
```

## 2. First failure: `NEW.reading_id` is wrong, and not in the way I guessed `[§9]`

```
ok       INSERT INTO reading(sensor_id,ts,value,interval_s) VALUES (2,'2026-03-01 10:00:00',2.7,1)
alarm written by the BEFORE trigger: [('BEFORE: NEW.reading_id=-1 NEW.energy_j=2.7',)]
the row it describes:                [(1, 2.7)]
```

The alarm says the reading is `-1`. The reading is `1`.

`reading_id` is `INTEGER PRIMARY KEY`, so it is an alias for the rowid and SQLite assigns it
during the insert. A `BEFORE INSERT` trigger runs beforehand, so there is nothing to report —
and SQLite reports **`-1`**, not `NULL`. I had assumed `NULL`, and `NULL` would at least be
honest: it is detectable, it propagates through arithmetic, and a `NOT NULL` column would refuse
it. `-1` is a plausible-looking integer that silently joins to nothing.

That is fatal for the audit trigger specifically. `audit.reading_id` exists to point at the row
that changed; built on a `BEFORE` trigger, every single audit row would point at `-1`, the audit
table would look completely healthy, and every join from it would return nothing. The failure
would surface the first time someone asked "which reading did this change?" — which is the only
question the table exists to answer, and probably months later.

`NEW.energy_j` **is** available and correct (`2.7`), which surprised me in the other direction.
The generated column is computed from `value` and `interval_s`, both of which are supplied by
the statement, so SQLite can evaluate it without having stored the row. The rule is not "`NEW`
is incomplete in a `BEFORE` trigger" — it is specifically the engine-assigned key that is
missing, because that is the one value the engine has not decided yet.

## 3. Second failure: the phantom alarm `[§9]`

With the default conflict resolution, a `BEFORE` trigger is safe against a row that fails
validation afterwards:

```
REJECTED  INSERT INTO reading(...) VALUES (2,'2026-03-01 10:00:01',9000,1)
          CHECK constraint failed: value >= -273.15 AND value <= 5000
alarms after the failed insert: 1  readings: 1    <- ABORT reverted the trigger too
```

The alarm the trigger had already written was rolled back with the statement. `ABORT` reverts
everything the statement did, trigger effects included, so my first attempt at this section
concluded that `BEFORE` was merely untidy rather than unsafe.

Then I tried the conflict clause a bulk ingest actually uses:

```
ok        INSERT OR IGNORE INTO reading(...) VALUES (2,'2026-03-01 10:00:02',9000,1)
alarms: 2  readings: 1
the phantom: [(2, 9000.0, 'BEFORE: NEW.reading_id=-1 NEW.energy_j=9000.0')]
```

**An alarm for 9,000 mm/s of vibration, about a reading the database refused to store.** `OR
IGNORE` suppresses the constraint violation and lets the statement succeed, so the `BEFORE`
trigger's insert is never rolled back — the alarm survives its own cause. The `reading` table is
correct and the `alarm` table is now lying, in the direction that gets someone called out to a
machine that is fine.

This is why `OR IGNORE` matters rather than being an exotic detail: skipping known-bad rows is
exactly what you reach for when ingesting a gateway's replay buffer, and it is one word away
from the statement in [`ingest.py`](./ingest.py). With the `AFTER` trigger the same statement
produces no alarm at all, because the trigger never runs for a row that was not inserted.

## 4. What `BEFORE` can do that `AFTER` cannot `[§10]`

`BEFORE` is not merely the worse option — it is the only one that can **reject**:

```sql
CREATE TRIGGER trg_reject
BEFORE INSERT ON reading FOR EACH ROW
WHEN NEW.value > 2.0 AND (SELECT metric FROM sensor WHERE sensor_id = NEW.sensor_id) = 'vib_rms'
BEGIN
    SELECT RAISE(ABORT, 'vibration over limit: row refused, not merely alarmed');
END;
```

```
REJECTED  INSERT INTO reading(...) VALUES (2,'2026-03-01 10:02:00',2.7,1)
          vibration over limit: row refused, not merely alarmed
```

An `AFTER` trigger cannot do this usefully — the row is already in. So the choice is not a
timing preference, it is a question about what the rule *is*:

| The rule is… | Trigger | Why |
|---|---|---|
| "record that this happened" (alarm, audit, rollup) | **`AFTER`** | needs the assigned key, and must not fire for rows that were never stored |
| "this must not be stored" (validation a `CHECK` cannot express) | **`BEFORE`** with `RAISE(ABORT)` | rejecting after the fact is not rejecting |

Both appear in this module. The alarm and audit triggers are the first kind, and `AFTER` is
right. The per-metric range check in [`triggers.md`](./triggers.md) §6 is the second kind, and
has to be `BEFORE` — which is the one place I would overrule the module's own default.

A vibration alarm is clearly the first kind and not the second: 2.7 mm/s is a real measurement
that must be kept, precisely *because* it is alarming. Refusing it would destroy the evidence.
That sentence is the actual answer to "why was `AFTER` the right default here", and it has
nothing to do with triggers — it is about what telemetry is for.

## 5. `INSTEAD OF` on the view `[§11]`

A plain view is not writable at all:

```
REJECTED  INSERT INTO machine_health VALUES ('cnc-09','temp_c',1,1)
          cannot modify machine_health because it is a view
```

`INSTEAD OF` is how a view becomes writable — it replaces the write with whatever the trigger
body does. Here there is no sensible translation (`machine_health` is a `GROUP BY` aggregate, so
a row of it corresponds to no single row of `reading`), which makes it a good place to improve
the error message instead:

```sql
CREATE TRIGGER trg_health_ro
INSTEAD OF INSERT ON machine_health FOR EACH ROW
BEGIN
    SELECT RAISE(ABORT, 'machine_health is a report view; write to reading instead');
END;
```

```
REJECTED  INSERT INTO machine_health VALUES ('cnc-09','temp_c',1,1)
          machine_health is a report view; write to reading instead
```

Worth being clear-eyed about what that is: **documentation, not a control.** It turns a generic
message into a useful one for whoever wrote the wrong statement. It does not stop them, because
they can write to `reading` directly — see [`access-control.md`](./access-control.md) §4, where
the same reader turned out to be able to read every table in the file regardless of the view.
An `INSTEAD OF` trigger is a better error message on a door that was never locked.

## 6. What I would take to a different database

The two defects in §2 and §3 are both instances of one thing: **a `BEFORE` trigger writes
durable data while the row it describes is still hypothetical.** The key is not assigned, the
constraints have not been checked, and whether the row will exist depends on a conflict clause
chosen by the caller. Anything the trigger records about that row is a prediction.

I would expect the specific symptoms to differ elsewhere — PostgreSQL's `BEFORE` triggers return
`NEW` and can modify it, which is a genuinely different model — but the ordering question is the
same everywhere, and I now think the useful phrasing is: *is this rule about the row, or about
the fact that the row happened?* Only the second kind can wait, and only the first kind can say
no.

---

[← Task 4: access control](./access-control.md) · [Module 4 page](./README.md)
