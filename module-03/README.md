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

## What I plan to explore

<!-- your own paragraph — see note below -->

## The scenario

Frachtflow, a logistics startup, runs order tracking on a local SQLite file. Their workflow is to describe a report to an LLM, paste the SQL in, and ship it if the number looks about right. It worked until a customer-service report quietly returned the wrong late orders for a month, and a customer name containing an apostrophe took the order page down.

Both failures have the same root: nobody profiled or parameterized the generated SQL. This module is about being the person who does.

## Contents

| File | What it holds |
|---|---|
| [`setup.sql`](./setup.sql) | Builds `warehouse.db` — 2,000 customers, 500 products, 60,000 orders, 240,000 order lines |
| [`sql-notes.md`](./sql-notes.md) | Tasks A/B/C — plan safari predictions vs. reality, algebra check, pod swap, curiosity harvest |
| [`llm-query.md`](./llm-query.md) | Task 1 — the prompt, the LLM's SQL, my predicted plan, the actual plan, correctness verdict |
| [`bench.py`](./bench.py) · [`bench.md`](./bench.md) | Task 2 — index benchmark: median of 3 runs per cell, plans before and after |
| [`injection_demo.py`](./injection_demo.py) | Task 3 — the injection drill and the escaping-vs-parameterizing answer |

## Rebuilding the database

`warehouse.db` is **not** committed — `.gitignore` keeps `*.db` out. Rebuild it from the repo root:

```sh
sqlite3 module-03/warehouse.db ".read module-03/setup.sql"
```

Check it loaded:

```sh
sqlite3 module-03/warehouse.db "SELECT 'orders', COUNT(*) FROM orders UNION ALL SELECT 'lines', COUNT(*) FROM order_line;"
```

Expected: `60000` orders and `240000` lines. Lower means the script stopped early — delete the file and run it again.

Task A also uses `module-02/legacy.db`; rebuild instructions are in [Module 2](../module-02/README.md#rebuilding-the-database).

**SQLite version used for every plan on this page:** `<paste sqlite3 --version here>`

## Status

- [ ] Task A — plan safari (predict, run, index, break it) → `sql-notes.md`
- [ ] Task B — algebra check → `sql-notes.md`
- [ ] Task C — compare plans with a neighbouring pod → `sql-notes.md`
- [ ] Task 1 — LLM query + plan verification → `llm-query.md`
- [ ] Task 2 — index benchmark, including the negative result → `bench.md`
- [ ] Task 3 — injection drill → `injection_demo.py`
- [ ] Task 4 — one query from algebra to plan
- [ ] Task 5 (stretcher) — window function rewrite
- [ ] [`Reflections/ref03.md`](../Reflections/ref03.md)

---

[← Module 2](../module-02/README.md) · [Portfolio home](../README.md)
