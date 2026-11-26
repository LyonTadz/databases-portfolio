# Module 5 · Round 4 — Race it: normalized vs. denormalized

[← Module 5 home](./README.md) · [Rounds 1–3](./normalization-notes.md) · [Round 5 — writes and storage](./price.md)

The question Yasmin Kaya asked: *for each machine, show its site, its
technician's name, and the total cost of parts used in the last 90 days.* Two
designs answer it. This page is what they cost.

**Harness:** [`bench.py`](./bench.py) · **engine:** SQLite 3.53.1 · **21
interleaved repetitions per arm** · 200,000 fact rows, 35.4 MB database.

> ### The headline, before the tables
>
> I measured the same two queries in four configurations, changing nothing about
> either schema. The denormalized table wins one, loses one, and ties two:
>
> | | `ix_report_machine` present | index dropped |
> |---|---|---|
> | **no planner statistics** | 1.04× — a tie | **1.48× — denormalized wins** |
> | **after one `ANALYZE`** | **0.74× — normalized wins** | 1.05× — a tie |
>
> Two operational decisions — whether an index exists, and whether anyone ever
> ran `ANALYZE` — move the answer further than the schema design does. With both
> set sensibly, **the four-way join and the single-table scan are the same
> speed**, and the whole denormalization buys 5%.
>
> Nothing in either `CREATE TABLE` statement tells you any of this.

---

## 1 · How this is measured, and why not with `.timer on`

The module says to run `.timer on` in the `sqlite3` shell. I used a Python
harness instead, for the reason Module 4 beat into me: **two numbers from two
consecutive runs are a coin flip.** In Module 4 the same trigger benchmark gave
me +22% and then +31% on consecutive runs, and once produced a result that was
arithmetically impossible. The fix there was interleaving the arms and estimating
with the minimum, and both are built into [`bench.py`](./bench.py):

- **Warm first, measure second.** One untimed pass over every arm before any
  timing. A cold scan pays for page-cache misses, and whichever query runs second
  inherits a warm cache. Measuring cold-then-warm is measuring the order of my
  commands.
- **Interleave.** One repetition is one pass over *all* arms, so drift during the
  run lands on every arm instead of on whichever one it was running at the time.
- **Report the minimum, and the median next to it.** Noise here is one-sided —
  an interruption adds time, nothing ever subtracts it — so the minimum is the
  best estimate of "the query with nothing else happening". On this machine the
  minimum and the maximum of one arm can be 27 ms apart, which is larger than the
  effect I am trying to measure.

### 1.1 The control that convinced me the measurement works

Arm A — the four-way join — is **identical in phases 1 and 2**. Nothing about it
changes when I drop an index on a different table. So its numbers are a free
control:

| Arm A, the same query | min | median | max |
|---|---|---|---|
| Phase 1 | **55.3 ms** | 56.1 ms | 82.3 ms |
| Phase 2 | **55.8 ms** | 57.0 ms | 59.8 ms |

The minima agree to **0.5 ms** across two separate phases. The maxima differ by
**22.5 ms** — more than the entire effect of dropping the index. That is the case
for the estimator in one table: the thing that should not move did not move, *if
you look at the minimum*. A mean over this data would have been dominated by the
excursions.

### 1.2 Run-to-run stability

Five consecutive runs of `bench.py`, each a fresh process against the same
database:

| | r1 | r2 | r3 | r4 | r5 |
|---|---|---|---|---|---|
| Phase 1 — A/B | 1.02× | 1.03× | 1.03× | 1.04× | 1.04× |
| Phase 2 — A/B | 1.48× | 1.47× | 1.46× | 1.47× | 1.48× |
| Phase 3 — A/B | — | — | 0.73× | 0.74× | 0.74× |
| B with index ÷ without | 1.44× | 1.42× | 1.43× | 1.44× | 1.42× |

Every conclusion on this page rests on ratios that move by ≤0.02 between runs.
The absolute milliseconds are machine-specific and nobody should expect to
reproduce 55.3 ms; the ratios are the result.

### 1.3 The measurement mistake I made anyway, in the other script

[`evidence.py`](./evidence.py) regenerates every other number in this module, so
my first instinct was to put the race in there too. The output was nonsense:
**arm A's minimum moved from 75 ms to 95 ms between two phases that do not touch
arm A at all.** The effect I am measuring is about 20 ms, and the noise was 20 ms.

The cause is that `evidence.py` rebuilds a 200,000-row table and runs eleven
dependency checks across it before reaching the race — so the process is busy and
the page cache is churning, and the timings measure that. Interleaving does not
save you, because the interference is not drift *within* the race; it is the
state the process is in when the race starts.

So the timings live in `bench.py` alone, which does nothing else, and
`evidence.py` prints plans and equality checks and explicitly declines to print a
millisecond. **A benchmark has to own its process.** That is the third distinct
way I have got a benchmark wrong in this course, and the first where the fix was
organisational rather than statistical.

---

## 2 · Phase 1 — the schema as built

```sql
-- A) normalized: a four-way join
SELECT m.machine_id, m.site, j.technician, SUM(p.part_price) AS cost
FROM job j
JOIN machine m   ON m.machine_id = j.machine_id
JOIN job_part jp ON jp.job_id = j.job_id
JOIN part p      ON p.part_no = jp.part_no
WHERE j.done_on >= date('2026-03-01')
GROUP BY m.machine_id, j.technician;

-- B) denormalized: a single-table scan
SELECT machine_id, site, technician, SUM(part_price) AS cost
FROM report_jobpart
WHERE done_on >= date('2026-03-01')
GROUP BY machine_id, technician;
```

| Arm | min (ms) | median (ms) | max (ms) |
|---|---|---|---|
| A — normalized, 4-way join | 55.3 | 56.1 | 82.3 |
| B — denormalized, 1 table | **53.3** | 54.7 | 79.2 |

**A is 1.04× B.** Both return **350 rows** totalling **722,610.0**, and
[`bench.py`](./bench.py) checks row-for-row that the answers match, so this is a
like-for-like comparison of two designs and not of two questions.

A 4% win is not a win. If I had run A once and B once, in either order, I could
have come out of Round 4 with "denormalization is 1.5× faster" or
"denormalization is slower" — both are inside the max/min spread of a single arm.

### 2.1 The plans, which say why

```
A — normalized
    SCAN jp
    SEARCH j USING INTEGER PRIMARY KEY (rowid=?)
    SEARCH m USING INDEX sqlite_autoindex_machine_1 (machine_id=?)
    SEARCH p USING INDEX sqlite_autoindex_part_1 (part_no=?)
    USE TEMP B-TREE FOR GROUP BY

B — denormalized
    SCAN report_jobpart USING INDEX ix_report_machine
    USE TEMP B-TREE FOR GROUP BY
```

Read A's plan as a loop: scan 200,000 rows of `job_part`, and for each one do
three indexed lookups. 600,000 B-tree probes. That sounds expensive and is not,
because the tables being probed are 20,000, 50 and 10 rows — the whole of
`machine` and `part` is **4 KB each** ([Round 5](./price.md) §2), so those probes
never leave the page cache.

Read B's plan and the surprise is the word **`USING INDEX`** on a query with no
`WHERE` clause on `machine_id` and no `ORDER BY`. SQLite chose to walk
`ix_report_machine` end to end and then fetch each row from the table by rowid —
200,000 index entries plus 200,000 scattered row fetches, instead of one
sequential pass. The index filters nothing. It is pure overhead, chosen because
walking it supplies rows already ordered by `machine_id` and so looked cheaper
than sorting for the `GROUP BY`.

Which makes Phase 2 obvious in hindsight and was not obvious in advance.

---

## 3 · Phase 2 — the same race with `ix_report_machine` dropped

```sql
DROP INDEX ix_report_machine;
```

| Arm | min (ms) | median (ms) | max (ms) |
|---|---|---|---|
| A — normalized, 4-way join | 55.8 | 57.0 | 59.8 |
| B — denormalized, no index | **37.6** | 38.3 | 39.9 |

```
B — denormalized, no index
    SCAN report_jobpart
    USE TEMP B-TREE FOR GROUP BY
```

- **A is now 1.48× B.** The denormalized design finally wins.
- **B alone: 53.3 ms → 37.6 ms, a 1.42× speed-up from deleting an index.**

Deleting an index made a query 29% faster, and the index was not even on a column
the query filters. That generalises past normalization entirely: **an index is a
cost on every read that does not use it to skip rows.** `SCAN … USING INDEX` is
the planner telling you it is paying for an index without filtering with it — in
a plan, the word to look for is `SEARCH`, not `SCAN`, because `SEARCH` is the one
that skips rows.

I did not predict this. I found it because Phase 1's 4% was too small to believe
and the plan had a word in it I did not expect — the same route by which every
real finding in Module 4 turned up.

**The index is not useless, it is useless *here*.** `ix_report_machine` would pay
for itself on `WHERE machine_id = 'cnc-02'`, which is exactly what
[Round 5](./price.md) does to the report table, 4,000 rows at a time. So the
dashboard wants the index gone and the maintenance path wants it present, on the
same table. That tension is in [the memo](./memo.md).

---

## 4 · Phases 3 and 4 — one `ANALYZE` reverses the result

This started as a throwaway line in my answer to the exchange question ("maybe
their planner has statistics mine doesn't") and turned into the main finding of
the round. `ANALYZE` collects table and index cardinalities into `sqlite_stat1`
so the planner costs its options with real numbers instead of built-in guesses.
It took **77 ms** on this database and wrote six rows:

```
flat_jobpart     ix_flat_machine                200000 4000
job              None                           20000
job_part         sqlite_autoindex_job_part_1    200000 10 1
machine          sqlite_autoindex_machine_1     50 1
part             sqlite_autoindex_part_1        10 1
report_jobpart   ix_report_machine              200000 4000
```

Read `job_part`'s row: *200,000 rows, 10 per `job_id`, 1 per `(job_id, part_no)`.*
That is the planner learning that a job has ten parts — the fact I established by
hand in [Round 3](./normalization-notes.md) §3.2.

### 4.1 Phase 3 — statistics, index still present

| Arm | min (ms) | median (ms) | max (ms) |
|---|---|---|---|
| A — normalized, 4-way join | **39.8** | 42.0 | 71.7 |
| B — denormalized, 1 table | 53.7 | 55.6 | 93.7 |

**A/B = 0.74×. The normalized design is now 1.35× faster than the denormalized
one.** A got 1.39× faster; B did not move at all (53.3 → 53.7 ms, inside the
noise). The plans say why:

```
A — normalized, after ANALYZE
    SCAN m USING INDEX sqlite_autoindex_machine_1
    SEARCH j USING AUTOMATIC PARTIAL COVERING INDEX (machine_id=?)
    SEARCH jp USING COVERING INDEX sqlite_autoindex_job_part_1 (job_id=?)
    SEARCH p USING INDEX sqlite_autoindex_part_1 (part_no=?)
    USE TEMP B-TREE FOR GROUP BY

B — denormalized, after ANALYZE
    SCAN report_jobpart USING INDEX ix_report_machine     <- unchanged
```

A's join order inverted. Before: start from the 200,000-row `job_part` and probe
outwards. After: **start from `machine`, which has 50 rows**, and work inwards —
and build an `AUTOMATIC PARTIAL COVERING INDEX` on `job` on the fly to do it. The
`COVERING INDEX` on `job_part` is the other half: the primary-key index already
holds both columns, so SQLite reads the index and never touches the table.

That last part is worth stopping on. In [Round 5](./price.md) §3 I find that
`job_part`'s primary-key index costs **3,992 KB — more than the 3,328 KB table it
indexes**, and it looks like pure overhead. Here that same index is what lets A
beat B. The expensive index is paying for itself; the cheap-looking one on the
report table is not.

B's plan is identical before and after, which is the part I would not have
guessed: **statistics did nothing for the denormalized query.** There is only one
table, so there is no join order to get right, and the one bad decision — walking
`ix_report_machine` — survives having real cardinalities available. The planner
knows the index has 4,000 rows per `machine_id` and still prefers it to a sort.

### 4.2 Phase 4 — statistics, index dropped

| Arm | min (ms) | median (ms) | max (ms) |
|---|---|---|---|
| A — normalized, 4-way join | 38.9 | 39.9 | 68.8 |
| B — denormalized, no index | **37.0** | 38.4 | 65.5 |

**A/B = 1.05×.** Both designs properly configured, and they are **the same
speed** — 38.9 ms against 37.0 ms on a 200,000-row aggregation.

### 4.3 The 2×2, and what it means

Minima in milliseconds:

| | `ix_report_machine` present | index dropped | what the index does |
|---|---|---|---|
| **A, no statistics** | 55.3 | 55.8 | nothing — different table |
| **A, after `ANALYZE`** | 39.8 | 38.9 | nothing — different table |
| **B, no statistics** | 53.3 | 37.6 | **costs 1.42×** |
| **B, after `ANALYZE`** | 53.7 | 37.0 | **costs 1.45×** |
| *what `ANALYZE` does* | A: **1.39× faster** · B: nothing | A: **1.43× faster** · B: nothing | |

Each of the two levers moves exactly one arm:

- **`ANALYZE` helps the normalized design and does nothing for the denormalized
  one.** It buys a better *join order*, and B has no joins. The more normalized
  the schema, the more statistics are worth.
- **Dropping the index helps the denormalized design and does nothing for the
  normalized one.** The index is on the report table, and A does not read it.

So the two designs are not just two schemas — they have **different operational
requirements**, and each is slow in the configuration that suits the other. The
default state of this database (no statistics, index present) is the one
configuration where they look equivalent, which is how a pod could spend an
afternoon on Round 4 and conclude that normalization is a wash.

**And in the best configuration for each, denormalization buys 5%.** That number
is the memo's whole argument: the 40-second dashboard in the story is not going to
be fixed by copying columns, because 95% of the cost is the scan and the group-by,
which both designs pay.

---

## 5 · So why is the join almost free here?

Denormalization removes a join. If removing it buys 4%, the join was costing
about 4%. The sizes say why:

| Table joined in A | Rows | Size | Fits in cache? |
|---|---|---|---|
| `job_part` (scanned) | 200,000 | 3,328 KB | the scan is the real work |
| `job` | 20,000 | 640 KB | yes |
| `machine` | 50 | 4 KB | trivially |
| `part` | 10 | 4 KB | trivially |

The dimensions are three orders of magnitude smaller than the fact table. A
B-tree probe into a 4 KB resident table is a handful of comparisons in cache;
600,000 of those is a few milliseconds, against a 200,000-row scan and a
350-group temporary B-tree that cost fifty.

Meanwhile B's single table is **2.7× the bytes** of the normalized tables it
replaces ([Round 5](./price.md)), because site, technician and price are repeated
on every one of 200,000 rows. **Denormalization trades bytes for probes.** Here
the probes were nearly free and the bytes were not, so the trade was close to a
wash — and once the index added *more* probes on top of the extra bytes, it went
negative.

The one sentence I want out of this round: **denormalization pays when the join
is the expensive part, not when the table is merely smaller** — and whether the
join is expensive is a property of the *data distribution and the planner's
information*, not of the schema.

---

## 6 · ◇ Making the join hurt — the counter-demo, and where it stops working

```sh
uv run python module-05/bench.py --wide
```

Both experiments run against a **copy** of the database, deleted afterwards, so
`normalize.db` stays as `setup.sql` built it.

### 6.1 Two more dimensions — the module's optional try

Adds `vendor` (10 rows) and `site_dim` (2 rows), widens the report table to carry
`region` and `vendor`, and races a **six-join A** against the wide B. Both return
**3,500 rows** totalling **722,610.0**, verified with `EXCEPT` in both directions
(0 rows each way).

| Arm | min (ms) | median (ms) |
|---|---|---|
| A — 6 joins | 94.0 | 99.3 |
| B — one wide table (14,536 KB) | **65.8** | 67.9 |

**A is 1.43× B.** Rebuilding the report table drops `ix_report_machine`, and this
runs without statistics, so the fair comparison is Phase 2:

| Comparison | A/B |
|---|---|
| Narrow, index dropped (§3) | **1.48×** |
| Wide, two extra dimensions (§6.1) | **1.43×** |

Adding two dimensions did **not** widen B's advantage on this machine. It made
*both* sides slower — A by 38 ms, B by 28 ms — and left the ratio marginally
worse. The module's own numbers (A 30 → 45 ms, B flat at 29 ms) show B's absolute
time holding while A's grows; mine show B's growing too, because the extra columns
add bytes to all 200,000 rows and the table goes from 10,832 KB to 14,536 KB.

The direction the module describes is real; the mechanism cuts both ways.
**Denormalizing a dimension removes a probe and adds a column to every row**, and
which effect dominates depends on how wide the column is against how expensive
the probe was. `vendor` has 10 rows and `site_dim` has 2 — the demo adds *more*
joins, not more expensive ones.

### 6.2 One more try: a dimension big enough to matter

So I tested what the demo is reaching for — a dimension with real cardinality.
`job_meta`, one row per job (**20,000 rows**, three text columns), joined per fact
row, with `shift` and `line` added to the group-by:

| Arm | min (ms) | median (ms) |
|---|---|---|
| A — 6 joins incl. a 20,000-row dimension | 256.3 | 268.5 |
| B — one table, 19,712 KB | **195.1** | 202.4 |

**1.31× — the ratio got worse again**, and this run is not clean evidence either
way: adding `shift` and `line` to the grouping took the result from 3,500 rows to
**68,580**, so the temporary B-tree for the `GROUP BY` now dominates both arms and
dilutes the difference between the designs. I changed two things at once, which is
the mistake, and I am reporting it rather than quietly dropping it.

### 6.3 What four experiments actually establish

I am leaving the negative results in rather than tuning until the numbers agree
with the handout. The defensible claim is narrower than "denormalization wins when
joins get expensive":

**On 200,000 cache-resident rows in SQLite, I could not construct a case where
denormalization bought more than about 1.5×, and with statistics collected it
bought 1.05×.** Every dimension I added was small enough to stay in cache, and
every widening cost bytes on all 200,000 rows. To get a large win the join would
have to spill — a dimension of millions of rows, or a working set past RAM — which
is past what this lab builds.

So the finding is about the *shape* of the trade, which the module is right about,
and the *magnitude* on this workload, which is: **single-digit percent, once both
designs are configured properly.** That points straight at
[the stretcher](./stretcher.md): if 5% is what denormalizing buys, a **6× change
of engine** is a different conversation entirely.

---

## 7 · Reproducing this

```sh
rm -f module-05/normalize.db
sqlite3 module-05/normalize.db ".read module-05/setup.sql"
uv run python module-05/bench.py            # §2–4, the 2x2
uv run python module-05/bench.py --wide     # + §6
```

`bench.py` restores `ix_report_machine` before it exits (Round 5 drops it on
purpose and needs it to exist first), runs the `ANALYZE` phases on a throwaway
copy so no `sqlite_stat1` is left behind, and deletes the copy.

### ⚠︎ Which SQLite produced these numbers

**Everything on this page was measured on SQLite 3.53.1 under Python's `sqlite3`
module, not on the 3.45.3 I have installed locally** — the same outstanding item
as [Module 4](../module-04/README.md). Timings are machine-specific regardless;
what is worth checking against another build are the **plans** and the **ratios**,
and §4 makes the plans the more fragile half. Which index the planner picks and
which join order it chooses are cost-model decisions, and cost models change
between versions. If `SCAN report_jobpart USING INDEX ix_report_machine` does not
appear on another build, §3 evaporates there; if `AUTOMATIC PARTIAL COVERING
INDEX` does not appear after `ANALYZE`, §4 does.

```sh
sqlite3 --version
uv run python -c "import sqlite3; print(sqlite3.sqlite_version)"
```

**Exchange — "did you get the same plan? If not, why?"** My answer: compare B's
plan, not A's, and look for whether the planner chose `USING INDEX
ix_report_machine`. If a neighbour's B beats their A by much more than 4% in
phase 1, I would bet on that line being absent — a different SQLite version, or
they ran `ANALYZE`. And then the follow-up I would actually want to ask them:
*did you run `ANALYZE` before or after you decided which design was faster?*
Because on this database that one command is the difference between
"denormalization wins by 48%" and "normalization wins by 35%", and it is not a
schema decision at all.

---

[← Rounds 1–3](./normalization-notes.md) · [Module 5 home](./README.md) · [Next: Round 5 — writes and storage →](./price.md)
