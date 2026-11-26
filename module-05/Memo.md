# Module 5 · Round 6 — Recommendation to the operations lead

[← Round 5 price](./price.md) · [Module 5 home](./README.md) · [Round 7 harvest](./harvest.md)

---

## The memo

**To:** Yasmin Kaya, Operations Lead
**From:** Lyon Tadeo
**Re:** The machine-health dashboard — measured before and after denormalizing
**Date:** November 2026

Yasmin — I built both designs you asked about and measured them, and the copy
does not buy what we hoped: on 200,000 job-part rows the denormalized
`report_jobpart` answers the dashboard query in **37.0 ms against 38.9 ms** for
the four-way join, a **5% gain**, in exchange for **1.72× the storage** and
turning a one-row site correction into a **4,000-row write**. Two changes that are
not schema changes beat it outright: running `ANALYZE` once (**77 ms**, no schema
change) makes the normalized query **1.39× faster**, and dropping
`ix_report_machine` — which the planner was walking without using it to filter —
makes the reporting query **1.42× faster while freeing 2,920 KB**. So my
recommendation is to **keep the transactional tables in 3NF and serve the
dashboard from them**, after those two one-line changes, rather than maintain a
second copy of the facts. If the dashboard is still too slow once we are on the
production dataset, the next step should be a **columnar read path** (DuckDB ran
the same normalized query in **8.86 ms — 4.2× faster than the best the
denormalized table managed in SQLite**), not more duplication. If you do want the
report table anyway — and there is a fair case for it, because it is the one
design that stays fast without the team having to remember to `ANALYZE` — then
**rebuild it on a schedule rather than maintaining it with triggers**: a full
rebuild of all 200,000 rows takes **172 ms**, which is a 0.57% duty cycle against
a 30-second refresh, whereas keeping it correct with triggers needs roughly
**eight** of them (`site` comes from `machine`, `part_price` from `part`,
`technician` from `job`, the fact from `job_part`, each with its own INSERT,
UPDATE and DELETE paths) and Module 4 already showed me that an `AFTER INSERT`
trigger silently skips the `ON CONFLICT DO UPDATE` path — so a corrected reading
would never reach the copy. Whatever we choose, the **transactional tables must
stay at 3NF**, because that is what makes a site correction one row that cannot
be half-applied; a denormalized copy is a *cache*, and the moment we let the
dashboard's table be the place a fact is edited we have bought the update anomaly
back at 4,000 rows a time.

---

## Supporting detail

Everything above comes from [`bench.py`](./bench.py) and
[`evidence.py`](./evidence.py); the pages are [Round 4](./benchmark.md),
[Round 5](./price.md) and [the stretcher](./stretcher.md).

### 1 · The four options, priced

| Option | Gain on the dashboard | What it costs | Reversible? |
|---|---|---|---|
| `ANALYZE` once | **1.39×** on the normalized query | 77 ms, one command, 6 rows in `sqlite_stat1` | `DROP TABLE sqlite_stat1` |
| Drop `ix_report_machine` | **1.42×** on the report query | −2,920 KB (a *saving*); slows the 4,000-row maintenance update | `CREATE INDEX` |
| Columnar read path (DuckDB) | **4.2×** vs the best SQLite number | a second engine in the stack; Module 6a | yes |
| Denormalize (`report_jobpart`) | **1.05×** | 1.72× storage; 1 → 4,000 rows per site change; staleness forever | only by deleting it |

The ordering is the memo's argument. The option the story reaches for first is
the only one that is both the least effective and the only one that gives
something up permanently.

### 2 · Why "the dashboard takes 40 seconds" is not fixed by this

The story's 40 seconds is on the production dataset, and my lab is 200,000 rows
at ~38 ms. The reason that extrapolation does not favour denormalizing is in
[Round 4](./benchmark.md) §5: **95% of the cost here is the scan and the
`GROUP BY`, which both designs pay identically.** Copying columns onto fact rows
removes the joins, and the joins are 5%. At production scale the scan grows and
the joins stay cache-resident — so if anything the denormalized share of the
saving gets *smaller*, not larger, until the dimensions themselves stop fitting in
memory.

What would actually attack the 40 seconds: narrowing the scan (an index on
`done_on`, which is the column the dashboard filters on and which nothing in this
module indexes — **the experiment I have not run**), pre-aggregating by day
instead of copying columns, or the columnar path. All three reduce rows touched.
Denormalizing does not reduce rows touched by one.

### 3 · The staleness strategies, measured

**Scheduled rebuild — my recommendation if the table is wanted.**
`CREATE TABLE … AS SELECT` over 200,000 rows: **115 ms**, plus **57 ms** for the
index — **172 ms** total. Against a 30-second refresh that is a **0.57% duty
cycle**. It is also *self-correcting*: every rebuild re-derives the copy from the
3NF tables, so no drift can accumulate, and the verification is one query —
`report_jobpart EXCEPT the join` must return **0 rows** ([`evidence.py`](./evidence.py)
§6b.4 checks exactly this).

**Triggers — cheap per row, structurally wrong here.** A maintenance trigger on
`job_part` costs **1.38 µs → 3.92 µs per insert (2.83×)**, which is nothing in
absolute terms. The objection is coverage, not cost: `report_jobpart` copies
columns out of **four** tables, so correctness needs a trigger on each for every
verb that can change a copied column — about eight. And Module 4 produced the
exact failure this invites: an `AFTER INSERT` trigger does not fire when an
`UPSERT` takes the `DO UPDATE` branch, so the replayed, corrected row updates
`job_part` and never reaches the copy. Eight triggers to avoid a 172 ms rebuild is
a bad trade, and the failure mode is silent.

**Materialized view — does not exist here.** `CREATE MATERIALIZED VIEW` is a
syntax error in SQLite. A plain `VIEW` re-runs its `SELECT` on every read, so it
is the normalized query with a nicer name: zero staleness and zero speed-up. On
this course's local-first stack, "materialized view" means "a table you rebuild
yourself", which is the scheduled rebuild above.

### 4 · The tension I could not resolve, and would flag in the meeting

`ix_report_machine` makes the dashboard **1.42× slower** and the 4,000-row
maintenance update much faster — on the same table. There is no configuration
that is best for both. My answer is to drop it, because the dashboard runs every
30 seconds and a machine moves site maybe twice a year, and under a scheduled
rebuild the maintenance update does not happen at all (the copy is replaced, not
edited). But that answer depends on the refresh strategy, and if we kept the table
and edited it in place I would keep the index and accept the slower dashboard.

### 5 · What I would need before committing to any of this

- **Measure on production volume.** Every ratio here is from 200,000
  cache-resident rows. The crossover I could not reach in the lab
  ([Round 4](./benchmark.md) §6.3) is exactly where production might sit.
- **An index on `done_on`.** Untested and the most likely real win, since it is
  the only predicate in the query.
- **Decide about price history.** [Round 1](./normalization-notes.md) §1.3:
  normalizing `part_price` into `part` assumes a part has one price forever. The
  moment a supplier price changes, every historical cost on this dashboard is
  silently restated at today's price — in **both** designs. That is a correctness
  bug we have not fixed and it is worth more than 5%.

---

## Exchange — the *what if* I prepared for

**"What if the dashboard has to refresh every second instead of every 30?"**
A 172 ms rebuild becomes a 17% duty cycle against SQLite's single writer, which
is no longer acceptable — rebuilding would block writes a sixth of the time. At
that point I would stop rebuilding and go to the columnar path: 8.86 ms leaves
plenty of headroom at 1 Hz without any copy at all. The second-choice answer is
incremental maintenance, and that is when the eight triggers start to be worth
their risk — but only with the `EXCEPT` check from §3 running as a scheduled
audit, because Module 4's lesson is that the trigger you forget is the one that
matters.

---

[← Round 5](./price.md) · [Module 5 home](./README.md) · [Next: Round 7 — harvest →](./harvest.md)
