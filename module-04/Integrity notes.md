# Module 4 — Pod study notes: integrity has layers

> Tasks A and B · [Module 4 portfolio page](./README.md) · [Course module](https://github.com/iotempire/iotempire-teaching/blob/main/full-classes/hsbi-databases-10d/modules/04-integrity-constraints-and-triggers.md)
>
> Every error message and row on this page is reproduced by
> [`evidence.py`](./evidence.py) → [`evidence.txt`](./evidence.txt). Section numbers in
> brackets, like `[§3]`, point at that transcript.

## 1. The three layers, and the mechanism for each

| Layer | Question it answers | SQL mechanism | What it cannot do |
|---|---|---|---|
| **Entity** | Is every row identifiable and complete? | `PRIMARY KEY`, `NOT NULL`, `UNIQUE` | Say anything about whether the value is *sensible* |
| **Referential** | Do relationships point at things that exist? | `FOREIGN KEY` + `ON DELETE`/`ON UPDATE` | Fire at all, if `PRAGMA foreign_keys` is off — see §4 |
| **Semantic (domain)** | Does the value make sense? | `CHECK`, generated columns, triggers | Compare against *other rows*; a `CHECK` sees only its own row |

The last column is the part I had to work out by running things, and it is the part I would
want to be asked about. The division of labour is strict: `UNIQUE (machine_id, metric)` has no
opinion about whether `metric` is a real metric, and `CHECK (metric IN (...))` has no opinion
about whether two sensors claim the same one. Both defects are "bad data" in plain English and
they are caught by different machinery.

**The rule a `CHECK` can never express.** A `CHECK` constraint is evaluated against a single
row, so it cannot say "no more than one open maintenance job per machine" or "this reading must
not be older than the previous reading for this sensor". Anything that needs to look at another
row needs a trigger. That is the dividing line between Task A and Task 3, and it is the answer
to the LLM question the module suggests asking.

## 2. The acceptance test: what an unconstrained table accepts `[§1]`

The module's three junk rows all land. I added five more to see where the floor actually is,
and there isn't one:

| What I inserted | Stored as | Verdict |
|---|---|---|
| `(1,'temp_c',9000)` | `9000.0` real | a 9,000 °C spindle |
| `(1,'temp_c','hot')` | `'hot'` **text** | in a column declared `REAL` |
| `(2,'bogus',-500)` | `-500.0` real | metric that does not exist, below absolute zero |
| `(NULL,NULL,NULL)` | three nulls | a reading that identifies nothing |
| `('x','temp_c','9000')` | `'x'` **text** in `INTEGER`, `9000.0` real | sensor id is a letter |
| `(1,'temp_c',9e999)` | `inf` real | **infinity** |
| `(2.7,'temp_c',1)` | `2.7` **real** in `INTEGER` | fractional sensor id |
| `(1,'temp_c',X'0001')` | **blob** | two raw bytes as a temperature |

Eight of eight accepted, no warnings. The declared types are documentation, not rules: SQLite's
default type affinity converts when it can and shrugs when it cannot.

**Most surprising to me: `inf`.** I expected text-in-a-REAL-column to be the headline, because
that is the one the handout leads with. But `'hot'` at least *looks* wrong the moment a human
reads the table. `inf` is a legitimate IEEE-754 float, `typeof()` reports it as `real`, and a
`STRICT` `REAL NOT NULL` column accepts it without complaint `[§2c]` — the only thing that stops
it is the range `CHECK`, and that works only because infinity compares greater than 5000, which
I tested rather than assumed.

What it does once it is in there `[§2c]`:

```
SUM, AVG, MAX, MIN over (inf, 41.5):  (inf, inf, inf, 41.5)
```

One loose sensor and every aggregate over that column is `inf` for the entire plant — except
`MIN`, which keeps working and so makes the dashboard look partly alive. The `CHECK` is the only
layer standing between a disconnected cable and a plant-wide report of infinity.

## 3. The same table, shipped properly

```sql
CREATE TABLE t_strict(
    sensor_id INTEGER NOT NULL,
    metric    TEXT    NOT NULL CHECK (metric IN ('temp_c','vib_rms','spindle_load')),
    value     REAL    NOT NULL CHECK (value BETWEEN -273.15 AND 5000),
    PRIMARY KEY (sensor_id, metric)
) STRICT;
```

Re-running the eight inserts one at a time, with the layer that caught each and the exact
message `[§3, §4]`:

All eight junk rows are now refused — none of them needed a second constraint, and each was
caught by a different mechanism than I would have guessed from reading it `[§2b]`:

| Row | Rejected by | Layer | Exact error |
|---|---|---|---|
| `(1,'temp_c',9000)` | `CHECK` | semantic | `CHECK constraint failed: value BETWEEN -273.15 AND 5000` |
| `(1,'temp_c','hot')` | `STRICT` | semantic (typing) | `cannot store TEXT value in REAL column t_strict.value` |
| `(2,'bogus',-500)` | `CHECK` | semantic | `CHECK constraint failed: metric IN ('temp_c','vib_rms','spindle_load')` |
| `(NULL,NULL,NULL)` | `NOT NULL` | **entity** | `NOT NULL constraint failed: t_strict.sensor_id` |
| `('x','temp_c','9000')` | `STRICT` | semantic (typing) | `cannot store TEXT value in INTEGER column t_strict.sensor_id` |
| `(1,'temp_c',9e999)` | `CHECK` | semantic | `CHECK constraint failed: value BETWEEN -273.15 AND 5000` |
| `(2.7,'temp_c',1)` | `STRICT` | semantic (typing) | `cannot store REAL value in INTEGER column t_strict.sensor_id` |
| `(1,'temp_c',X'0001')` | `STRICT` | semantic (typing) | `cannot store BLOB value in REAL column t_strict.value` |

Then two more of my own, to reach the entity layer properly:

| Row | Rejected by | Layer | Exact error |
|---|---|---|---|
| `(1,'temp_c',42.0)` after a good `(1,'temp_c',41.5)` | `PRIMARY KEY` | entity | `UNIQUE constraint failed: t_strict.sensor_id, t_strict.metric` |
| `(99,'2026-03-01 08:00:03',40,1)` into `reading` | `FOREIGN KEY` | referential | `FOREIGN KEY constraint failed` |

Three things I did not expect in that table. **`('x','temp_c','9000')` fails on `sensor_id`, not
on `value`** — `'9000'` would have been accepted as a number (§5), so the row dies on the column
I was not watching. **`(2.7,'temp_c',1)` is refused** with `cannot store REAL value in INTEGER
column`, but `(2.0,'temp_c',...)` is **accepted** `[§2b]` — so `STRICT`'s rule is not "no
conversions", it is "no *lossy* conversions", and it applies in both directions. And the
all-`NULL` row dies on `sensor_id` at the **entity** layer, not on `value`, purely because of
column order — which makes the error message a poor guide to how broken the row really was.

Two notes on the error messages themselves, because they are evidence and not decoration:

- The `CHECK` messages quote the **constraint expression**, not the column. A table with three
  unnamed `CHECK`s is debuggable from the message alone. `FOREIGN KEY constraint failed` quotes
  nothing at all — not the table, not the column, not the value. With several foreign keys on
  one table you cannot tell from the message which one failed, which is an argument for naming
  constraints (`CONSTRAINT fk_reading_sensor FOREIGN KEY ...`) that I did not previously see
  the point of.
- Writing a generated column raises `cannot INSERT into generated column "energy_j"` and is an
  `OperationalError`, not an `IntegrityError` `[§4]`. SQLite classifies it as a malformed
  statement rather than bad data, which is right: the statement is wrong on its face.

## 4. Follow-up one: what `CHECK` does with `NULL` `[§2]`

`NULL` **passes**. A nullable column with `CHECK (v BETWEEN -273.15 AND 5000)` accepts `NULL`
without complaint.

```
ok       INSERT INTO n VALUES (NULL)
ok       INSERT INTO n VALUES (40.0)
REJECTED INSERT INTO n VALUES (9000.0)
         CHECK constraint failed: v BETWEEN -273.15 AND 5000
```

The reason is three-valued logic: `NULL BETWEEN -273.15 AND 5000` evaluates to `UNKNOWN`, not
`FALSE`, and a `CHECK` rejects a row **only on `FALSE`**. "Not provably in range" is treated as
permission.

This matters more than it looks. A `CHECK` is not a validity guarantee, it is a guarantee *for
rows where the value is present*. `NOT NULL` is a separate constraint that has to be asked for
separately, and the two are not interchangeable — the schema in [`setup.sql`](./setup.sql) only
gets away with its range check because `value` is also `NOT NULL`. The general lesson, which I
think generalises past SQLite: **a constraint on a nullable column is conditional.**

## 5. Follow-up two: which constraint still lets a plausible-but-wrong value through

This is the question I expected to answer with a shrug and it produced the best finding of the
pod study `[§3]`.

**`STRICT` does not mean what the name says.** A `STRICT` table accepts a `TEXT` value into a
`REAL` column whenever the text is losslessly convertible to a number:

```
REJECTED  value = 'hot'       cannot store TEXT value in REAL column reading.value
ok        value = '41.5'      stored as real 41.5
ok        value = ' 41.5 '    stored as real 41.5      <- leading and trailing spaces
ok        value = '4e1'       stored as real 40.0      <- scientific notation
REJECTED  value = '41.5abc'   cannot store TEXT value in REAL column reading.value
REJECTED  value = X'41'       cannot store BLOB value in REAL column reading.value
```

So `STRICT` filters *unparseable* text, not *textual* input. `typeof(value)` afterwards returns
`real` — the conversion is silent and leaves no trace that the row arrived as a string.

I take two things from this. First, it is genuinely useful: a CSV reader hands you strings for
everything, so this is the behaviour that makes [`ingest.py`](./ingest.py) work at all without a
casting layer — all 1,015 accepted rows in that script arrive as `TEXT` from `csv.DictReader`
and land as numbers. Second, it is the hole in my mental model of the module's own claim. The
handout says `STRICT` means `'abc'` can never land in a `REAL` column, and that is true; what
is also true and unstated is that `'4e1'` can, and becomes `40.0`.

**The plausible-but-wrong value none of these constraints catch.** `value = 41.5` for a sensor
whose cable has come loose and is reporting its last good reading forever. It is in range, it is
the right type, it is a real number from a real sensor, and it is wrong. Every constraint on the
table passes it, because detecting it requires comparing against *the previous row* for the same
sensor — `CHECK` cannot see other rows (§1). That is a trigger's job, and it is the clearest
argument I have found for why the three layers are not enough on their own.

## 6. Task B — share with another pod

**Status: prepared, not yet held.** The three agreed points below are what I would bring; the
pod exchange needs the other pod in the room, same as Module 2 §7 and Module 3 Task C.

What I would read out as the most surprising thing an unconstrained table accepted: **`inf`**,
for the reasons in §2 — it is the one that survives the type system and the eye.

What I would put to the other pod as the hardest constraint to get right, and my answer:

1. **`CHECK` with `NULL`** — not hard to write, easy to believe you have covered a case you
   have not. See §4.
2. **`STRICT` with numbers** — hardest in the sense that matters, because it *looks* like it
   succeeded. See §5.
3. **`UNIQUE` over two columns** — the one I got wrong first. `UNIQUE (machine_id, metric)` is
   a single constraint on the pair; `UNIQUE (machine_id), UNIQUE (metric)` is two constraints
   and forbids a second machine from ever having a `temp_c` sensor. Both are one line of DDL
   and they are not close to equivalent.

My vote for hardest is **`STRICT` with numbers**, because the other two fail loudly the first
time you test them and that one does not fail at all.

### Open question for `#sql-questions`

`PRAGMA foreign_key_check` reports a pre-existing orphan row long after the fact `[§5]`, and
turning `PRAGMA foreign_keys = ON` afterwards does **not** reject or revisit it — the orphan
simply stays, and only *new* violations are refused. So a database can be permanently
inconsistent with its own declared foreign keys and still accept writes normally. Is running
`PRAGMA foreign_key_check` on gateway startup the accepted practice for an embedded database,
or is there a way to make the constraint retroactive that I have not found? I could not answer
this from the SQLite documentation on [foreign key support](https://sqlite.org/foreignkeys.html).

---

[← Module 4 page](./README.md) · [Constraint evidence →](./constraints.md)
