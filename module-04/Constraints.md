# Module 4 — Task 1: proving the constraints work

> Task 1 · [Module 4 portfolio page](./README.md) · schema in [`setup.sql`](./setup.sql)
>
> Reproduced by [`evidence.py`](./evidence.py) → [`evidence.txt`](./evidence.txt); `[§n]` refers to
> that transcript. **SQLite 3.53.1.**

A constraint I have not watched reject something is a comment. This page is the five statements
the module asks for, three more of my own, and the one result that changed how I will write
schemas.

## 1. The valid row, and the generated column `[§4]`

```sql
INSERT INTO reading(sensor_id, ts, value, interval_s) VALUES (1,'2026-03-01 08:00:00', 41.5, 1);
SELECT value, interval_s, energy_j FROM reading;
```

```
41.5 | 1 | 41.5
```

`energy_j` is declared `GENERATED ALWAYS AS (value * interval_s) VIRTUAL` and was never
inserted. `VIRTUAL` means it is computed on read and occupies no space in the row; `STORED`
would compute it on write and keep it. The point of putting it in the schema rather than in
`ingest.py` is that there is now exactly one definition of what `energy_j` means, and a second
tool reading this file cannot disagree with the first about it.

## 2. The four rejections the module asks for `[§4]`

| # | Statement | Layer | Exact error |
|---|---|---|---|
| 1 | `VALUES (1,'…08:00:01', 9000, 1)` | semantic (domain) | `CHECK constraint failed: value >= -273.15 AND value <= 5000` |
| 2 | `VALUES (1,'…08:00:02', 'hot', 1)` | semantic (typing) | `cannot store TEXT value in REAL column reading.value` |
| 3 | `VALUES (99,'…08:00:03', 40, 1)` | referential | `FOREIGN KEY constraint failed` |
| 4 | `INSERT INTO sensor VALUES (3,'cnc-01','temp_c','degC')` | entity | `UNIQUE constraint failed: sensor.machine_id, sensor.metric` |

Three of the four messages name the thing that failed. **`FOREIGN KEY constraint failed` names
nothing** — not the table, not the column, not the value. On a table with one foreign key that
is merely terse; on a table with four it is a debugging problem, and it is the reason I would
now write `CONSTRAINT fk_reading_sensor FOREIGN KEY (sensor_id) REFERENCES sensor(sensor_id)`
rather than the inline `REFERENCES` shorthand that [`setup.sql`](./setup.sql) uses. Naming the
constraint puts the name in the message.

## 3. Three more, because the module's five do not cover the whole schema `[§4]`

| Statement | Layer | Exact error |
|---|---|---|
| `VALUES (1,'…08:00:04', 40, 0)` | semantic | `CHECK constraint failed: interval_s > 0` |
| `INSERT INTO sensor VALUES (4,'cnc-02','humidity','%')` | semantic | `CHECK constraint failed: metric IN ('temp_c','vib_rms','spindle_load')` |
| `VALUES (…, energy_j) VALUES (1,'…08:00:05', 40, 1, 99)` | — | `cannot INSERT into generated column "energy_j"` |

The third one is classified differently from all the others: it is an `OperationalError`, not an
`IntegrityError`. SQLite is saying the *statement* is malformed rather than the *data* being
bad, which is the right call — no value of `energy_j` would have been acceptable. Worth knowing
if you are catching exceptions by type in an ingest loop, because a handler that catches
`IntegrityError` and logs "bad row" will let this one crash the process instead.

`interval_s > 0` is the one that would have saved me. `energy_j = value * interval_s` divides by
nothing, but an `interval_s` of `0` means a reading that covers no time, and the generated
column would dutifully report `0.0` joules for a machine that was running. The `CHECK` is
upstream of a derived value being quietly wrong rather than obviously missing.

## 4. The headline finding: a constraint that is off by default `[§5]`

This is the one I would want to be asked about at a checkpoint.

[`setup.sql`](./setup.sql) opens with `PRAGMA foreign_keys = ON`. That pragma is **per
connection**, and it defaults to **off**. So the foreign key in the schema is enforced only for
connections that remember to ask:

```
new connection, PRAGMA foreign_keys = 0
ok       INSERT INTO reading(sensor_id,ts,value,interval_s) VALUES (99,'2026-03-01 08:30:00',40,1)
         -> orphan accepted — no sensor 99 exists
orphan rows now present: 1
```

The row the database refused in §2 lands without complaint from a second connection to the same
file, three seconds later. Nothing about the file changed — only which program opened it.

It gets worse in a way I did not anticipate. `PRAGMA foreign_key_check` **does** find the orphan
after the fact, and turning enforcement on does **not** fix or reject it:

```
PRAGMA foreign_key_check: [('reading', 1, 'sensor', 0)]
after switching it ON, foreign_key_check still: [('reading', 1, 'sensor', 0)]
REJECTED  VALUES (98,'2026-03-01 08:31:00',40,1)
          FOREIGN KEY constraint failed
```

So the constraint is not retroactive: the existing orphan stays forever, and only *new*
violations are refused. A database can be permanently inconsistent with its own declared schema
and still accept writes normally, and the only way to find out is to go and ask.

**What this means for an edge gateway with no DBA.** Every tool that touches the file is part of
the integrity boundary — the Python ingest script, a `sqlite3` shell someone opens to look
around, a DB browser GUI, a backup script that copies rows. Any one of them that forgets one
line of setup can write an orphan, and the next tool along will not notice. Of the three layers
in [`integrity-notes.md`](./integrity-notes.md) §1, referential integrity is the only one that
can be switched off by the *caller*, and that asymmetry is not visible anywhere in the `CREATE
TABLE` statement. `CHECK`, `NOT NULL`, `UNIQUE` and `STRICT` cannot be turned off this way.

The practical consequence I am taking forward: `PRAGMA foreign_keys = ON` belongs in every
connection-opening function, not in the setup script, because the setup script's connection is
the one that needs it least. [`ingest.py`](./ingest.py) issues it on line 3 of `main()` for
exactly this reason.

## 5. Statement atomicity, found by accident `[§8]`

While writing [`ingest.py`](./ingest.py) I had to choose between one multi-row `INSERT` and one
statement per row. The choice is not stylistic:

```sql
INSERT INTO reading(sensor_id,ts,value,interval_s)
VALUES (1,'2026-03-01 13:00:00', 40, 1),      -- valid
       (1,'2026-03-01 13:00:01', 9000, 1);    -- violates the domain CHECK
```

```
CHECK constraint failed: value >= -273.15 AND value <= 5000
rows stored: 0
```

**The good row is gone too.** SQLite's default conflict resolution is `ABORT`, which reverts the
whole *statement* — and a multi-row `VALUES` list is one statement. For a gateway replaying a
buffer where a handful of rows are known-bad, that is the wrong behaviour: one impossible
temperature would discard the batch it arrived in. Per-row execution inside one transaction
gives the opposite trade-off, which is what [`ingest.py`](./ingest.py) uses and why its output
counts rejects individually.

## 6. What I would change in this schema

1. **Name the foreign key** (§2), so the error message identifies it.
2. **Constrain the shape of `ts`.** It is declared `TEXT NOT NULL` and nothing else, so
   `'yesterday'` is a legal timestamp `[§12]` — and `ts` is half of the natural key the whole
   UPSERT in [`upsert.md`](./upsert.md) depends on. This is the largest hole I found in the
   schema as given, and the damage is at the entity layer rather than the semantic one: a
   malformed `ts` does not collide with the well-formed replay of the same reading, so it
   defeats the deduplication silently instead of loudly. A `GLOB` check gets most of the way
   `[§12]`:

   ```sql
   CHECK (ts GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9] [0-9][0-9]:[0-9][0-9]:[0-9][0-9]')
   ```

   It rejects `'yesterday'`, `'2026-3-1 8:00:00'` and `'2026-03-01T08:00:00'`. It also accepts
   `'2026-13-45 99:99:99'`, because `GLOB` constrains the *shape* and knows nothing about the
   calendar — so this is an improvement, not a solution, and a real date check needs
   `strftime()` or a trigger. I would rather ship the partial fix and know its limit than
   leave the column open.
3. **A per-metric range**, instead of one `CHECK (value BETWEEN -273.15 AND 5000)` shared by
   temperature, vibration and spindle load. 4,000 mm/s of vibration passes today. A `CHECK`
   cannot do this on its own, because the metric lives in `sensor` and the value lives in
   `reading`, and a `CHECK` cannot reach another table — so it is a trigger, which is
   [`triggers.md`](./triggers.md) §6.

---

[← Pod study notes](./integrity-notes.md) · [Module 4 page](./README.md) · [UPSERT →](./upsert.md)
