# Module 5 — Normalization vs. Denormalization Benchmarking Studio

[← Portfolio home](../README.md) · [Module 4](../module-04/README.md) · [Course module](https://github.com/iotempire/iotempire-teaching/blob/main/full-classes/hsbi-databases-10d/modules/05-normalization-vs-denormalization.md) · [Syllabus](https://github.com/iotempire/iotempire-teaching/blob/main/full-classes/hsbi-databases-10d/syllabus.md)

**Session 5.** The relational model and normal forms (1NF–3NF), reframed as an
empirical trade-off: build both designs, measure them, and defend where the
schema should sit for a given workload.

This is the first module run as **seven rounds instead of a pod study** — each
round has a small task, a theory box you read only when you want it, and a
two-minute exchange with a neighbouring pod. Rounds 1–4 are class work, 5–7
homework.

## 🎯 Learning Goals

By the end of this module, I can:

1. Derive **functional dependencies** from a relation and identify candidate keys.
2. Normalize a relation to **1NF, 2NF and 3NF**, explaining the anomaly each step removes.
3. **Denormalize deliberately** to speed up a hot read path, and predict what it costs on writes and storage.
4. **Measure** the trade-off: query latency, write cost and database size, before and after.
5. Decide, and *defend*, where a schema should sit on the normalization spectrum for a given workload.

### Where each goal is proven

| Goal | Evidence |
|---|---|
| 1 — FDs and candidate keys | [`normalization-notes.md`](./normalization-notes.md) §1 — eleven FD claims, each marked *domain* / *observed* / *vacuous*, each re-tested against 200,000 rows by [`evidence.py`](./evidence.py) §1 and §3.4; the minimality argument for `(job_id, part_no)` |
| 2 — 1NF/2NF/3NF and their anomalies | [`normalization-notes.md`](./normalization-notes.md) §2 — all three anomalies caused on purpose with the rows afterwards; §3 — the decomposition and the 200,000 = 200,000 lossless check |
| 3 — deliberate denormalization | [`setup.sql`](./setup.sql) §3 builds `report_jobpart`; [`price.md`](./price.md) §1 and §3 price it at 1 → 4,000 rows and 1.72× storage |
| 4 — measurement | [`benchmark.md`](./benchmark.md) — a 2×2 of index × statistics, with plans, interleaved timings and a control arm; [`price.md`](./price.md) §5 — the filled benchmark table |
| 5 — decide and defend | [`memo.md`](./memo.md) — four options priced, a staleness strategy chosen on measured numbers, and the prepared *what if* |

## What I planned to explore

Module 4 was about integrity being a property of the whole write path rather than
of the `CREATE TABLE`. This module looked like the opposite kind of work: a
benchmark with a predictable answer. Copy four columns onto a fact table, remove
three joins, read one table instead of four. The module's own framing warns that
the win will be small, so I expected to spend the afternoon confirming a modest
speed-up and writing up what it cost on writes.

What I actually wanted to find out was **how small**, because the story's 40-second
dashboard implies the joins are the problem and I had no feel for whether that is
usually true.

It is not true here, and the interesting part is not the margin. It is that
**two decisions that are not schema decisions move the result further than the
schema does** — whether anyone has run `ANALYZE`, and whether an index exists that
the planner walks without filtering. Change those and the same two queries trade
places. The schema question the module poses turns out to be, on this workload,
smaller than the operational questions nobody asked.

## The scenario

Kortmann's plant has a machine-health dashboard that asks, every 30 seconds: *for
each machine, its site, its technician, and the total cost of parts used in the
last 90 days.* Against the normalized schema repaired in Module 2 it joins four
tables and scans the whole job-part history, and on the production dataset it
takes 40 seconds — blocking the single writer while it runs.

The operations lead, **Yasmin Kaya**, asks for the classic shortcut: copy the site
and the technician onto every job row, add a total-cost column, and let the
dashboard read one table. She is right about the read and about to introduce
update anomalies. The studio's job is to build both, measure both, and make the
decision with numbers.

## Contents

| File | What it holds |
|---|---|
| [`setup.sql`](./setup.sql) | Builds `normalize.db` — the 200,000-row unnormalized table, the 3NF decomposition, the denormalized reporting table |
| [`normalization-notes.md`](./normalization-notes.md) | Rounds 1–3 — the FD list with evidence marked, two ER sketches, all three anomalies, the decomposition and its row-count check |
| [`benchmark.md`](./benchmark.md) · [`bench.py`](./bench.py) | Round 4 — the race, four configurations, both plans, the control arm, and the counter-demos |
| [`price.md`](./price.md) | Round 5 — 1 vs 4,000 rows, `dbstat` storage both ways, the index-drop experiment, the filled benchmark table |
| [`memo.md`](./memo.md) | Round 6 — the recommendation to the operations lead, the four options priced, the staleness strategy |
| [`harvest.md`](./harvest.md) | Round 7 — ten curiosities with their evidence and sources, and four unresolved questions |
| [`stretcher.md`](./stretcher.md) | ◇ The same query in DuckDB, and why the engine change beats the schema change |
| [`evidence.py`](./evidence.py) · [`evidence.txt`](./evidence.txt) | Every number, error message and row count quoted on these pages, regenerated in one command |
| [`ref05.md`](./ref05.md) | Logbook entry for this block |

## Rebuilding and reproducing

`normalize.db` is **not** committed — `.gitignore` keeps `*.db` out, so a reviewer
rebuilds it from the script. The data is generated from a `CROSS JOIN` of two
recursive counters with no randomness, so the rebuild is byte-identical.

```sh
rm -f module-05/normalize.db
sqlite3 module-05/normalize.db ".read module-05/setup.sql"
sqlite3 module-05/normalize.db "SELECT COUNT(*) FROM flat_jobpart;"   # expect 200000
```

The one result worth reproducing first is the 2×2:

```sh
uv run python module-05/bench.py            # phases 1-4, the 2x2 matrix
uv run python module-05/bench.py --wide     # the two counter-demos
```

Every other number on these pages:

```sh
uv run python module-05/evidence.py > module-05/evidence.txt
```

Both scripts leave `normalize.db` exactly as `setup.sql` builds it: `bench.py`
restores the index it drops and runs the `ANALYZE` phases on a throwaway copy,
and `evidence.py` rolls back every destructive statement.

### ⚠︎ Which SQLite produced these numbers

**Everything here was measured on SQLite 3.53.1 under Python's `sqlite3` module.**
There is no `sqlite3` CLI on the machine I ran this on, which is also why the
timings come from a Python harness instead of `.timer on` — and that turned out to
be the better tool anyway ([`benchmark.md`](./benchmark.md) §1). Same outstanding
item as Module 4: I have **3.45.3 installed locally** and have not re-run against
it.

Timings are machine-specific regardless. What is worth checking on another build
are the **plans**, and §4 of the benchmark makes them the fragile half: which index
the planner picks and which join order it chooses are cost-model decisions, and
cost models change between versions. If `SCAN report_jobpart USING INDEX
ix_report_machine` does not appear on your build, my Round 4 finding evaporates
there; if `AUTOMATIC PARTIAL COVERING INDEX` does not appear after `ANALYZE`, the
2×2 collapses to a 1×2.

```sh
sqlite3 --version
uv run python -c "import sqlite3; print(sqlite3.sqlite_version)"
```

## Headline findings

- **Denormalizing bought 5%, and two operational switches moved the answer
  further than the schema did.** In four configurations of the *same two queries*,
  the denormalized table wins one, loses one and ties two: as built 1.04×
  (a tie), index dropped **1.48×** (it wins), after one `ANALYZE` **0.74×** (the
  normalized join wins by 35%), and with both **1.05×** (a tie). The default
  state — no statistics, index present — is the single configuration where the two
  designs look equivalent, which is how an afternoon on Round 4 can end in
  "normalization is a wash". ([`benchmark.md`](./benchmark.md) §4.3)
- **One `ANALYZE`, 77 ms, makes the four-way join 1.39× faster and does nothing
  for the single-table scan.** It buys a better join order — A's plan inverts to
  drive from the 50-row `machine` table and builds an automatic covering index on
  the fly — and B has no joins to reorder. The more normalized the schema, the
  more planner statistics are worth; the denormalized query cannot be helped this
  way at all. ([`benchmark.md`](./benchmark.md) §4.1)
- **Deleting an index made a read 1.42× faster and saved 2,920 KB.**
  `ix_report_machine` is on a column the dashboard neither filters nor orders by,
  and the planner walked all 200,000 entries then fetched every row by rowid.
  `SCAN … USING INDEX` is the planner announcing it is paying for an index without
  filtering with it. ([`benchmark.md`](./benchmark.md) §3)
- **The storage penalty is 1.72×, not the 2.72× the module's query reports** —
  because that query names tables and not indexes, and both designs have them. The
  normalized side's hidden cost is almost entirely `job_part`'s primary-key index
  at **3,992 KB, larger than the 3,328 KB table it indexes**. And that
  "wasteful" index is the covering index that makes the normalized query win
  after `ANALYZE`: the expensive index earns its keep and the cheap one does not.
  ([`price.md`](./price.md) §3)
- **1 row versus 4,000, for one machine changing site — about two orders of
  magnitude in time, though the one-row minimum is at clock resolution so the
  time ratio itself is not stable.** That
  ratio is the only number on these pages that is a property of the schema rather
  than of this machine. The cost is not the 3.9 ms — it is that a 4,000-row update
  can be *partially applied*, and the end state of a half-applied one is a machine
  with two sites and no error anywhere. ([`price.md`](./price.md) §1)
- **DuckDB ran the normalized query in 8.86 ms — 4.2× faster than the best SQLite
  managed with the denormalized one.** Single-threaded it is still 11.58 ms, so
  the win is the engine and not the core count. Changing engine beats every
  schema change in this module put together, which makes denormalization the
  fourth-best option on a list of four. ([`stretcher.md`](./stretcher.md) §3.2)
- **DuckDB refused SQL that SQLite accepts, and the FD was why SQLite was
  right.** `BinderException: column "site" must appear in the GROUP BY clause`.
  SQLite allows bare columns in an aggregate query and takes the value from an
  arbitrary row — correct here *only* because `machine_id → site`. Group by
  `machine_id` and select `technician` instead and SQLite returns one technician
  per machine, silently wrong. A functional dependency was load-bearing for a
  query's **correctness**, not just for its storage.
  ([`stretcher.md`](./stretcher.md) §2)
- **`MAX` over a text price column returns 9.00 instead of 15.00, while `SUM` over
  the same column is exactly right.** Arithmetic coerces, comparison respects
  storage class. Both aggregates sit in the same `SELECT` list and look identical.
  The column is atomic, so 1NF has nothing to say about it. ([`harvest.md`](./harvest.md) §1)
- **`PRAGMA foreign_keys` set inside a transaction does not error, does not take
  effect, and reads back as `0`.** Third variant of Module 4's lesson that a rule
  living in the caller gets forgotten — here it can be set, confirmed and still
  absent. ([`normalization-notes.md`](./normalization-notes.md) §3.3)
- **My own benchmark was wrong again, in a new way.** Timing the race inside
  [`evidence.py`](./evidence.py) — which rebuilds a 200,000-row table first — moved
  the *control* arm from 75 ms to 95 ms between two phases that do not touch it,
  against a 20 ms effect. Interleaving does not help when the interference is the
  state the process starts in. A benchmark has to own its process, so the timings
  live in `bench.py` alone and `evidence.py` refuses to print a millisecond.
  ([`benchmark.md`](./benchmark.md) §1.3)

## Status

**Done**

- [x] Round 1 — FD list with evidence marked, two ER sketches, the LLM diff → [`normalization-notes.md`](./normalization-notes.md) §1
- [x] Round 2 — all three anomalies caused, with the rows afterwards → [`normalization-notes.md`](./normalization-notes.md) §2
- [x] Round 3 — the 200k build, the 3NF decomposition, 200000 = 200000, the FK pragma and the `DISTINCT` assertion → [`normalization-notes.md`](./normalization-notes.md) §3 · [`setup.sql`](./setup.sql)
- [x] Round 4 — the race in four configurations, both plans, the control arm → [`benchmark.md`](./benchmark.md) · [`bench.py`](./bench.py)
- [x] Round 4 ◇ — both counter-demos, including the one that did not work → [`benchmark.md`](./benchmark.md) §6
- [x] Round 5 — rows touched, `dbstat` storage both ways, the index drop, the filled table → [`price.md`](./price.md)
- [x] Round 6 — the memo, four options priced, staleness strategies measured → [`memo.md`](./memo.md)
- [x] Round 7 — ten curiosities with sources → [`harvest.md`](./harvest.md)
- [x] ◇ Stretcher — the DuckDB comparison → [`stretcher.md`](./stretcher.md)
- [x] [`ref05.md`](./ref05.md)

**Outstanding**

- [ ] **The seven exchanges.** Every round ends with a two-minute exchange with
      the nearest pod, and my side of all seven is written and ready
      ([Round 1](./normalization-notes.md) §1.2, [Round 2](./normalization-notes.md) §2.4,
      [Round 3](./normalization-notes.md) §3.2, [Round 4](./benchmark.md) §7,
      [Round 5](./price.md) §6, [Round 6](./memo.md) *what if*,
      [Round 7](./harvest.md) exchange). They need the other pod in the room —
      same gap as Module 2 §7, Module 3 Task C and Module 4 Task B.
- [ ] **An index on `done_on`** — the one column the dashboard actually filters on,
      and the only untested idea likely to attack the story's 40 seconds. Nothing
      in the module indexes it. ([`memo.md`](./memo.md) §2)
- [ ] **`WITHOUT ROWID` on `job_part`** — should remove most of the 3,992 KB
      duplicate-key index. ([`harvest.md`](./harvest.md) §5, §10.3)
- [ ] **Re-run on local SQLite 3.45.3** and record any plan differences. Carried
      over from Module 4 and now more consequential, because Round 4's findings
      are plan-dependent.
- [ ] **Four questions for `#sql-questions`** → [`harvest.md`](./harvest.md) §10:
      why `ANALYZE` does not talk the planner out of `ix_report_machine`; what
      exactly an `AUTOMATIC PARTIAL COVERING INDEX` is; whether `WITHOUT ROWID` is
      standard for junction tables; and how to model price history without
      breaking 3NF's one-fact-one-place promise.
- [ ] **Feedback on the rounds format**, which the module explicitly asks for and
      counts as a contribution → [`ref05.md`](./ref05.md) §"What was good" and
      §"What was difficult" are written as that feedback; needs posting to
      `#sql-questions` or saying in the Module 6a recap.

---

[← Module 4](../module-04/README.md) · [Portfolio home](../README.md)
