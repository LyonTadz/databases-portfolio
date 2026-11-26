# Module 4 — Data Integrity, Constraints & Edge Triggers

[← Portfolio home](../README.md) · [Module 3](../module-03/README.md) · [Course module](https://github.com/iotempire/iotempire-teaching/blob/main/full-classes/hsbi-databases-10d/modules/04-integrity-constraints-and-triggers.md) · [Syllabus](https://github.com/iotempire/iotempire-teaching/blob/main/full-classes/hsbi-databases-10d/syllabus.md)

**Session 4.** Standard SQL (DDL/DML/DCL), data integrity, and triggers — reframed as integrity
enforced **at the edge**, next to the data, with no server and no DBA to fix a bad row.

## 🎯 Learning Goals

By the end of this module, I can:

1. Create tables with the full constraint toolkit: `NOT NULL`, `UNIQUE`, `CHECK`, `PRIMARY KEY`, `FOREIGN KEY`, and `STRICT` typing.
2. Use **generated columns** to derive values at the engine instead of in application code.
3. Write **triggers** that enforce domain rules and maintain audit/rollup tables automatically.
4. Use **DML** correctly — including `UPSERT` (`ON CONFLICT`) for idempotent edge ingestion.
5. Reason about **access control (DCL)**: who may read or write, and how server `GRANT`s map onto an embedded, local-first world.

### Where each goal is proven

| Goal | Evidence |
|---|---|
| 1 — constraint toolkit | [`constraints.md`](./constraints.md) §2–3 — eight rejections with exact errors; [`integrity-notes.md`](./integrity-notes.md) §3 — the same junk rows against an unconstrained and a constrained table |
| 2 — generated columns | [`constraints.md`](./constraints.md) §1 — `energy_j` computed from a row that never supplied it, and §3 — it cannot be written to |
| 3 — triggers | [`triggers.md`](./triggers.md) §2 (firing), §3 (measured cost), §5 (the gap they leave); [`stretcher.md`](./stretcher.md) (`BEFORE`, `INSTEAD OF`, `RAISE(ABORT)`) |
| 4 — DML and UPSERT | [`upsert.md`](./upsert.md) + [`ingest.py`](./ingest.py) — double run with `delta +0`, and the table it is *not* idempotent in |
| 5 — access control | [`access-control.md`](./access-control.md) — view, `chmod 444`, `mode=ro`, `PRAGMA query_only`, and the PostgreSQL comparison |

## What I planned to explore

Module 3 was about not trusting SQL that an LLM wrote. This one looked, going in, like the
easiest module so far: constraints are declarative, you write them in the `CREATE TABLE`, and
either the row goes in or it does not. Nothing to profile, nothing to benchmark, nothing to
verify.

What I actually wanted to find out was whether "the database refuses garbage" survives contact
with a real ingest path, because the module's own framing invites the question — there is no
backend to re-validate and no DBA to fix a row, so the constraints are the whole defence. My
guess was that I would find the schema solid and the interesting part would be writing the
triggers.

The guess was wrong in a specific way. Every constraint in the handout's schema works exactly as
documented. **Three of the four defects I found are in the spaces between the tasks** — Task 2's
UPSERT interacting with Task 3's triggers — where nothing is individually incorrect. That turned
out to be the actual subject of the module.

## The scenario

Wittkamp's machine shop lost two days of telemetry to a two-day internet outage. The fix is
local-first: an edge gateway writes readings straight into a SQLite file next to the machines,
and the data never leaves the plant unless someone decides it should.

That raises the stakes on integrity rather than lowering them. A disconnected sensor reporting
9,000 °C has to be refused by the database itself. A spindle crossing a vibration threshold has
to raise an alarm the moment the row lands. And a gateway replaying its buffer after the network
comes back must not duplicate what it already sent — which is where most of this module's
interesting failures live.

## Contents

| File | What it holds |
|---|---|
| [`setup.sql`](./setup.sql) | Builds `edge.db` — `STRICT` tables, generated column, constraints, both triggers, the report view |
| [`integrity-notes.md`](./integrity-notes.md) | Pod study, Tasks A/B — the three layers, the acceptance test, `CHECK` with `NULL`, what `STRICT` still lets through |
| [`constraints.md`](./constraints.md) | Task 1 — eight rejections with exact error messages, the generated column, and the constraint that is off by default |
| [`ingest.py`](./ingest.py) · [`make-readings.py`](./make-readings.py) · [`upsert.md`](./upsert.md) | Task 2 — replay-safe ingestion, the double-run proof, and the table it does not protect |
| [`triggers.md`](./triggers.md) · [`trigger-bench.py`](./trigger-bench.py) | Task 3 — alarm and audit triggers, their measured cost, and the alarm they fail to raise |
| [`access-control.md`](./access-control.md) | Task 4 — view, file permissions, read-only connections, and the PostgreSQL comparison |
| [`stretcher.md`](./stretcher.md) | Task 5 — `BEFORE INSERT`, the phantom alarm, `INSTEAD OF` on a view |
| [`evidence.py`](./evidence.py) · [`evidence.txt`](./evidence.txt) | Every error message and row count quoted on these pages, regenerated in one command |
| [`../Reflections/ref04.md`](../Reflections/ref04.md) | Logbook entry for this block |

## Rebuilding and reproducing

`edge.db` and `readings.csv` are **not** committed — `.gitignore` keeps `*.db` and `*.csv` out,
so a reviewer rebuilds both from the scripts. From the repository root:

```sh
rm -f module-04/edge.db
sqlite3 module-04/edge.db ".read module-04/setup.sql"
sqlite3 module-04/edge.db "SELECT COUNT(*) FROM sensor;"        # expect 2
```

Then the Task 2 double run, which is the one result worth reproducing first:

```sh
uv run python module-04/make-readings.py     # writes readings.csv — 1019 rows
uv run python module-04/ingest.py            # first run:  delta +1000
uv run python module-04/ingest.py            # second run: delta +0, audit +1015
```

Every error message and count quoted on these pages:

```sh
uv run python module-04/evidence.py > module-04/evidence.txt
uv run python module-04/trigger-bench.py
```

### ⚠︎ Which SQLite produced these numbers

**Everything in [`evidence.txt`](./evidence.txt) and the benchmark table in
[`triggers.md`](./triggers.md) §3 was generated on SQLite 3.53.1, not on the 3.45.3 I have
installed locally.** Both are well past the versions these features need (`STRICT` is 3.37+,
generated columns 3.31+, `UPSERT` 3.24+), so I expect the behaviour to match — but the exact
*wording* of a constraint error is not part of SQLite's compatibility promise, and Module 3 Task
C already taught me that version differences are the first suspect when two machines disagree.

So this is an outstanding item rather than a footnote: re-running `evidence.py` on 3.45.3 either
confirms the transcript or turns up a real version difference, and both are worth having.
Checking takes one command:

```sh
sqlite3 --version
uv run python -c "import sqlite3; print(sqlite3.sqlite_version)"   # the one evidence.py uses
```

## Headline findings

- **The ingest is idempotent in `reading` and not in `audit`.** Three identical runs of
  [`ingest.py`](./ingest.py) leave `reading` at exactly 1,000 rows and take `audit` from 15 rows
  to 2,045 — **2,030 of which record a change that did not happen**, because `ON CONFLICT … DO
  UPDATE` is an `UPDATE` and fires the audit trigger even when the value is unchanged. The one
  table whose purpose is to be trustworthy is the one that fills with noise, proportional to the
  number of outages. ([`upsert.md`](./upsert.md) §4)
- **A reading corrected across the alarm threshold never alarms.** Ingest 1.5 mm/s, replay it as
  3.4 mm/s, and the database holds 3.4 with **zero alarm rows** — the alarm trigger is `AFTER
  INSERT` and the replay took the `DO UPDATE` path. Neither idempotence fix closes it; it needs a
  companion `AFTER UPDATE` trigger, made edge-triggered with `OLD.value <= 2.0` so replays do not
  spam it. ([`triggers.md`](./triggers.md) §5)
- **A trigger that never fires once still costs about 30%.** The fixed cost is the `WHEN`
  clause's correlated subquery, run on all 10,000 rows; the marginal cost of an actual alarm is
  0.67 µs, so 0% and 1% alarm rates are indistinguishable. Almost the entire cost is paid by the
  rows that do nothing. ([`triggers.md`](./triggers.md) §3)
- **`STRICT` is weaker than its name.** A `STRICT` `REAL` column accepts `'41.5'`, `' 41.5 '` and
  `'4e1'` — any text that converts losslessly — and stores them as numbers with no trace they
  arrived as strings. It refuses `'41.5abc'`. The rule is losslessness, not type, and it runs
  both ways: `2.7` into an `INTEGER` column is refused while `2.0` is accepted.
  ([`integrity-notes.md`](./integrity-notes.md) §5)
- **The foreign key is off unless the caller asks.** `PRAGMA foreign_keys` is per connection and
  defaults to off, so a second connection writes the orphan the first one refused. Worse, it is
  not retroactive: `PRAGMA foreign_key_check` finds the orphan afterwards, and switching
  enforcement on leaves it there forever while refusing new ones. Of the three integrity layers,
  referential is the only one the *caller* can disable, and nothing in the `CREATE TABLE` says
  so. ([`constraints.md`](./constraints.md) §4)
- **A view is not a security boundary.** A reader on the most restricted connection available
  (`mode=ro`) read the `machine_health` view, then read the raw `reading` table the view
  aggregates away, then listed every table in the file out of `sqlite_master`. There is no
  `GRANT`, so there is nothing to `REVOKE`: access is all-or-nothing per file.
  ([`access-control.md`](./access-control.md) §4)
- **`BEFORE INSERT` + `OR IGNORE` produces an alarm about a row that was never stored** — 9,000
  mm/s of vibration in the `alarm` table with no matching reading, because `OR IGNORE` suppresses
  the constraint violation so the trigger's work is never rolled back. And `NEW.reading_id` is
  `-1` in a `BEFORE` trigger, not `NULL`: a plausible-looking integer that joins to nothing.
  ([`stretcher.md`](./stretcher.md) §2–3)
- **My first benchmark was wrong, and the impossible result is what caught it.** Seven
  repetitions per arm run back to back, reported as medians, gave +22% and then +31% for the same
  headline on consecutive runs — and once put the 0%-alarm arm *faster* than the 1% arm, which
  cannot happen. Interleaving the arms and estimating with the minimum rather than the median
  fixed it: the minima hold within half a millisecond across every run.
  ([`triggers.md`](./triggers.md) §3)

## Status

**Done**

- [x] Task A — acceptance test, the three layers, `CHECK` with `NULL`, the plausible-but-wrong value → [`integrity-notes.md`](./integrity-notes.md)
- [x] Setup script — `STRICT` tables, generated column, full constraint set → [`setup.sql`](./setup.sql)
- [x] Task 1 — every rejection with its exact error message, plus three of my own → [`constraints.md`](./constraints.md)
- [x] Task 2 — `UPSERT` SQL, `ingest.py`, double-run row-count proof → [`upsert.md`](./upsert.md)
- [x] Task 3 — trigger DDL, the rows they produced, trigger-cost measurement → [`triggers.md`](./triggers.md) · [`trigger-bench.py`](./trigger-bench.py)
- [x] Task 4 — `chmod`/`mode=ro`/`query_only`, the `machine_health` view, PostgreSQL comparison → [`access-control.md`](./access-control.md)
- [x] Task 5 (stretcher) — `BEFORE INSERT` variant and `INSTEAD OF` on a view → [`stretcher.md`](./stretcher.md)
- [x] [`Reflections/ref04.md`](../Reflections/ref04.md)

**Outstanding**

- [ ] **Re-run [`evidence.py`](./evidence.py) on local SQLite 3.45.3** and replace
      [`evidence.txt`](./evidence.txt), or record the differences if there are any. See the
      version warning above.
- [ ] **Task B** — the 10-minute exchange with a neighbouring pod → [`integrity-notes.md`](./integrity-notes.md) §6.
      Prepared in full (my surprising-acceptance answer, my hardest-constraint answer, and an
      open question); needs the other pod in the room. Same gap as Module 2 §7 and Module 3 Task C.
- [ ] Two open questions for `#sql-questions`: whether `PRAGMA foreign_key_check` on startup is
      the accepted practice for an embedded database ([`integrity-notes.md`](./integrity-notes.md) §6),
      and how to serve read-only clients from a WAL-mode database they cannot write to
      ([`access-control.md`](./access-control.md) §5).

---

[← Module 3](../module-03/README.md) · [Portfolio home](../README.md)
