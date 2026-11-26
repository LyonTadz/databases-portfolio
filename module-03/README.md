# Module 3 — LLM-Assisted SQL & Query Profiling

[← Portfolio home](../README.md) · [Module 2](../module-02/README.md) · [Course module](https://github.com/iotempire/iotempire-teaching/blob/main/full-classes/hsbi-databases-10d/modules/03-llm-assisted-sql-and-query-profiling.md) · [Syllabus](https://github.com/iotempire/iotempire-teaching/blob/main/full-classes/hsbi-databases-10d/syllabus.md)

**Session 3.** Standard SQL (DQL), relational algebra, and query optimization — reframed around the modern reality: you generate SQL with an LLM and then have to prove it correct, fast, and safe.

## 🎯 Learning Goals

By the end of this module, I can:

1. Build complex **DQL** queries: joins, aggregation with `GROUP BY`/`HAVING`, subqueries, and window functions.
2. Read **`EXPLAIN QUERY PLAN`** as *primary evidence* — tell a `SCAN` from a `SEARCH`, and a table lookup from a covering index.
3. **Benchmark** the effect of an index, and explain when the planner ignores one.
4. Generate a query with an **LLM**, then verify it: correctness, performance, and edge cases.
5. **Prevent SQL injection** with bound parameters, and demonstrate why string concatenation is exploitable.

### Where each goal is proven

| Goal | Evidence |
|---|---|
| 1 — complex DQL | [`llm-query.md`](./llm-query.md) (4-table join + `GROUP BY` + `COUNT(DISTINCT)`), [`stretcher.md`](./stretcher.md) (correlated subquery and window function) |
| 2 — read a plan | [`sql-notes.md`](./sql-notes.md) §4 — the same index used by one query and ignored by three others, with the reason for each |
| 3 — benchmark an index | [`bench.md`](./bench.md) — before/after table, including an index that made the query **4× slower** |
| 4 — verify an LLM | [`llm-query.md`](./llm-query.md) §4 and [`sql-notes.md`](./sql-notes.md) §6 — four model claims tested, two wrong |
| 5 — prevent injection | [`injection.md`](./injection.md) + [`injection_demo.py`](./injection_demo.py) |

## What I plan to explore

Module 2 was someone else's mistake — a schema built badly in 2011 and left alone. The defects were ugly but they were *visible* once you went looking: text where a foreign key should be, a comma-separated list in a column. This module is the opposite problem. The SQL an LLM writes looks correct, and it mostly is correct, so there is nothing obvious to find by reading it.

What I actually want to find out is whether I can tell the difference between a query that is right and a query that merely runs — and whether the model's confidence tracks its accuracy at all. My instinct going in is that I will be able to check the *query* and will have no way of checking the *advice about the query*, which is the part I would otherwise take on trust.

## The scenario

Frachtflow, a logistics startup, runs order tracking on a local SQLite file. Their workflow is to describe a report to an LLM, paste the SQL in, and ship it if the number looks about right. It worked until a customer-service report quietly returned the wrong late orders for a month, and a customer name containing an apostrophe took the order page down.

Both failures have the same root: nobody profiled or parameterized the generated SQL. This module is about being the person who does.

## Contents

| File | What it holds |
|---|---|
| [`setup.sql`](./setup.sql) | Builds `warehouse.db` — 2,000 customers, 500 products, 60,000 orders, 240,000 order lines |
| [`sql-notes.md`](./sql-notes.md) | Pod study + Tasks A/B/C — references, surprises, the plan safari, the algebra check, the curiosity harvest |
| [`llm-query.md`](./llm-query.md) | Task 1 — the prompt, the LLM's SQL, the predicted plan, the actual plan, the correctness verdict |
| [`bench.py`](./bench.py) · [`bench.md`](./bench.md) | Task 2 — index benchmark: median of 5 runs per cell, plans before and after, with the negative results |
| [`injection_demo.py`](./injection_demo.py) · [`injection.md`](./injection.md) | Task 3 — the injection drill and the escaping-vs-parameterizing answer |
| [`stretcher.md`](./stretcher.md) | Task 5 — correlated subquery and window-function rewrites, compared on plan and clock |
| [`evidence.py`](./evidence.py) · [`evidence.txt`](./evidence.txt) | Every plan and timing on these pages, regenerated in one command on this machine |

## Rebuilding and reproducing

`warehouse.db` is **not** committed — `.gitignore` keeps `*.db` out. From the repository root:

```sh
sqlite3 module-03/warehouse.db ".read module-03/setup.sql"
sqlite3 module-03/warehouse.db "SELECT 'orders', COUNT(*) FROM orders UNION ALL SELECT 'lines', COUNT(*) FROM order_line;"
```

Expected: `60000` orders and `240000` lines. Lower means the script stopped early — delete the file and run it again.

Task A also needs `module-02/legacy.db`:

```sh
sqlite3 module-02/legacy.db ".read module-02/setup-legacy.sql"
```

Then regenerate every plan and timing quoted in these notes:

```sh
uv run python module-03/evidence.py > module-03/evidence.txt
uv run python module-03/bench.py
```

**SQLite version used for every plan on these pages:** `3.45.3 (2024-04-15)`

Plans are version-dependent, which is the point of Task C — see [`sql-notes.md`](./sql-notes.md) §7.

## Headline findings

- **An index made the dashboard query ~4× slower.** `ix_orderline_order` flipped a scan-driven aggregate into an index-driven nested loop. Every line of the slower plan is a `SEARCH`. ([`bench.md`](./bench.md) §3)
- **A trailing-wildcard `LIKE 'Bei%'` still scanned**, with the index in place. The cause is collation, not the wildcard — SQLite's `LIKE` is case-insensitive by default and a `BINARY` index cannot serve it. ([`sql-notes.md`](./sql-notes.md) §3.1)
- **Of the three indexes the LLM recommended, none helped the query it was asked about.** One was neutral, one was harmful, one was never used. ([`bench.md`](./bench.md) §6)
- **A "rewrite" changed the answer.** The correlated-subquery version of the late-orders report returns 2,000 rows where the `GROUP BY` returns 400 — and the model did not mention it. ([`stretcher.md`](./stretcher.md))

## Status

**Done**

- [x] Task A — plan safari: predict, run, index, break it → [`sql-notes.md`](./sql-notes.md) §4
- [x] Task B — algebra check, including where the LLM's translation differed → [`sql-notes.md`](./sql-notes.md) §5
- [x] Task 1 — LLM query, predicted plan, actual plan, correctness verdict → [`llm-query.md`](./llm-query.md)
- [x] Task 2 — index benchmark with both negative results → [`bench.md`](./bench.md) · [`bench.py`](./bench.py)
- [x] Task 3 — injection drill + escaping-vs-parameterizing answer → [`injection.md`](./injection.md) · [`injection_demo.py`](./injection_demo.py)
- [x] Task 4 — one query from algebra to plan → [`sql-notes.md`](./sql-notes.md) §5 + [`llm-query.md`](./llm-query.md) §3
- [x] Task 5 (stretcher) — correlated subquery and window-function rewrites → [`stretcher.md`](./stretcher.md)
- [x] The harvest — curiosities with sources → [`sql-notes.md`](./sql-notes.md) §8
- [x] [`Reflections/ref03.md`](../Reflections/ref03.md)

**Outstanding**

- [ ] **Task C** — 15-minute plan comparison with a neighbouring pod → [`sql-notes.md`](./sql-notes.md) §7. Prepared in full; needs the other pod in the room. No Task Pod assigned to me as of this session.
- [ ] Regenerate [`evidence.txt`](./evidence.txt) on this machine after any change to the setup or the queries.

---

[← Module 2](../module-02/README.md) · [Portfolio home](../README.md)
