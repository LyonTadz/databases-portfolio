# Module 3 — SQL Notes

[← Module 3 home](./README.md) · [Portfolio home](../README.md)

> Pod study + Tasks A, B and C, in the same shape as the [Module 2 study log](../module-02/study-log.md):
> references first, then what I googled, then surprises, then the LLM answers I actually verified.

**Environment for every plan on this page:** SQLite 3.45.3 (CLI, `2024-04-15`) on macOS (MacBook Air, Apple silicon).
Plans are version-dependent — see §4, where that turns out to matter.

---

## 1. References I used

| Source | What I took from it |
|---|---|
| [sqlite.org/eqp.html](https://www.sqlite.org/eqp.html) | The authoritative grammar of a plan line: one line per table read, in execution order, read as a loop nest. |
| [Use The Index, Luke — SQLite operations](https://use-the-index-luke.com/sql/explain-plan/sqlite/operations) | Glossary of `SCAN` / `SEARCH` / `COVERING`, and why a `SEARCH` costs two B-tree descents unless the index covers. |
| [Use The Index, Luke](https://use-the-index-luke.com/) | The general rule that a function around a column makes the index unusable. |
| [SQLite — LIKE optimization](https://www.sqlite.org/optoverview.html#like_opt) | The four conditions under which `LIKE` can use an index. This is what explained my biggest surprise (§3.1). |
| [OWASP — SQL Injection Prevention](https://cheatsheetseries.owasp.org/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet.html) | Why parameterization is the fix and escaping is not. |
| [Wikipedia — Relational algebra](https://en.wikipedia.org/wiki/Relational_algebra) | σ / π / ⋈ / γ operators for Task B. |

## 2. Things I googled

- *"sqlite explain query plan SCAN vs SEARCH"* — to get the vocabulary straight before predicting anything.
- *"why is my sqlite index not used with LIKE"* — after the trailing-wildcard query refused to use the index (§3.1).
- *"sqlite case_sensitive_like pragma"* — the follow-up once I suspected collation was the cause.
- *"sqlite covering index"* — to understand why dropping one column from the `SELECT` list changes the plan.
- *"does adding an index ever make a query slower"* — after the dashboard got 4× slower (§Task 2 in [`bench.md`](./bench.md)).

## 3. Remarkable things

### 3.1 The surprise: a trailing-wildcard `LIKE` still scanned

The received wisdom is *"`LIKE 'abc%'` can use an index, `LIKE '%abc'` cannot."* Half of that is wrong by default.

```
SELECT * FROM maint_job WHERE technician LIKE 'Bei%';
-- with ix_job_tech on maint_job(technician):
-- SCAN maint_job          <-- not a SEARCH!
```

The reason is **collation, not the wildcard.** SQLite's `LIKE` is case-insensitive for ASCII by default, but a plain index is built with `BINARY` collation. An index sorted `Bei…` before `bei…` cannot answer a case-insensitive prefix query, so the planner refuses it. Two ways to get the `SEARCH` back, both verified:

```
PRAGMA case_sensitive_like = ON;
-- SEARCH maint_job USING INDEX ix_job_tech (technician>? AND technician<?)

CREATE INDEX ix_job_tech_nocase ON maint_job(technician COLLATE NOCASE);
-- SEARCH maint_job USING INDEX ix_job_tech_nocase (technician>? AND technician<?)
```

Note the plan shape: `(technician>? AND technician<?)` — a **range** scan, because that is what a prefix match is. The index is not matching `'Bei%'`; it is matching everything between `'Bei'` and `'Bej'`.

### 3.2 One column changes a `SEARCH` into a `COVERING SEARCH`

```
SELECT *          FROM maint_job WHERE technician = 'Beier';
--> SEARCH maint_job USING INDEX ix_job_tech (technician=?)

SELECT technician FROM maint_job WHERE technician = 'Beier';
--> SEARCH maint_job USING COVERING INDEX ix_job_tech (technician=?)
```

The index entry is `(technician, rowid)`. Ask only for `technician` and the table is never opened — one B-tree descent instead of two. `SELECT *` needs `done_on`, `parts_used` and the rest, so the engine has to go back to the table for every match. **`SELECT *` is not free**, and this is the plan line that proves it.

### 3.3 An index can make a query slower

Covered properly in [`bench.md`](./bench.md), but it belongs in the surprises too: adding `ix_orderline_order` flipped the dashboard query from a scan-driven aggregate into an index-driven nested loop and made it roughly **four times slower**. The plan changed, the clock got worse, and both were correct. "Added an index" and "made it faster" are different claims.

### 3.4 The generated data has a hidden correlation

Revenue by city came out as a 4× spread (Bielefeld ≈ €11.2M, Paderborn ≈ €2.8M) in a dataset where every city has *exactly* 500 customers. That is not a business insight — it is an artefact of the setup script. City is `x % 4`, the order's customer is `(x % 2000) + 1`, and the product is `(x % 500) + 1`, so city, product and price are all driven off the same counter and end up correlated. Worth remembering before reading any "finding" out of generated data.

### 3.5 `COUNT(DISTINCT …)` is doing real work here, not decoration

Every one of the 2,000 customers has at least one 2025 order, so the distinct count is `500` in all four cities — a dead column on this dataset. But drop the `DISTINCT` and it returns ~40,000 per city, because the join to `order_line` multiplies each customer by their order-line count. The column looks useless and is simultaneously the only thing stopping the number from being nonsense. Details in [`llm-query.md`](./llm-query.md).

## 4. Task A — plan safari

> ★ Task A. Predict first, then run. On `module-02/legacy.db`, rebuilt with
> `sqlite3 module-02/legacy.db ".read module-02/setup-legacy.sql"`.

Relevant fact about this schema: **`legacy.db` declares no primary keys and no indexes at all.** `machine` has no PK, `part` has no PK, and `maint_job.job_id` is a plain `INTEGER` column, not `INTEGER PRIMARY KEY`. There is no B-tree to descend anywhere, so before step 2 there is nothing the planner *could* use.

### Step 1 — before any index

The prediction, and the reasoning behind it: SQLite can only `SEARCH` when there is a **B-tree it can descend** — an index or a primary key. This schema declares neither. So all three should `SCAN`, and the interesting part of step 1 is not the answer but the fact that the *reason* is identical for all three, which makes step 2 the real experiment.

| # | Query | Predicted | Actual plan | Reasoning |
|---|---|---|---|---|
| 1 | `SELECT * FROM maint_job WHERE technician = 'Beier';` | `SCAN` | `SCAN maint_job` | No index on `technician`, and `job_id` is not a declared PK. |
| 2 | `SELECT * FROM machine WHERE machine_name = 'cnc-02';` | `SCAN` | `SCAN machine` | `machine` declares no PK and no `NOT NULL` — nothing to descend. |
| 3 | `SELECT * FROM maint_job WHERE technician LIKE '%ei%';` | `SCAN` | `SCAN maint_job` | Same table as 1, and a leading wildcard would rule out an index even if one existed. |

Three for three, which is the least informative outcome available — a correct prediction teaches nothing. The wrong prediction arrives in step 3, and it is the one I had most confidence in.

### Step 2 — after `CREATE INDEX ix_job_tech ON maint_job(technician);`

| # | Query | Plan after the index | Changed? | Why |
|---|---|---|---|---|
| 1 | `technician = 'Beier'` | `SEARCH maint_job USING INDEX ix_job_tech (technician=?)` | **yes** | Equality on the indexed column — exactly what the index is for. |
| 2 | `machine_name = 'cnc-02'` | `SCAN machine` | no | Different table. The index is on `maint_job`; `machine` still has nothing. |
| 3 | `technician LIKE '%ei%'` | `SCAN maint_job` | no | Leading wildcard. An index is sorted by its first character, and `%ei%` gives no first character to seek to. |

The useful pairing is 1 against 3: **same table, same column, same index — and only one of them can use it.** What decides is not whether a column is indexed but whether the predicate gives the engine a *starting point in sort order*. Equality does. A leading wildcard does not.

Query 2 is the control that stops the wrong conclusion ("adding an index speeds up the database"). An index helps one column of one table.

### Step 3 — breaking the index on purpose

The index now exists and is demonstrably used by query 1. Each of these defeats it anyway:

| Query | Plan | Why the index is unusable |
|---|---|---|
| `WHERE upper(technician) = 'BEIER'` | `SCAN maint_job` | The index stores `technician`, not `upper(technician)`. The engine would have to compute the function for every row to know which entries match — which is the scan it was trying to avoid. |
| `WHERE technician \|\| '' = 'Beier'` | `SCAN maint_job` | Same cause, no function call in sight. Any expression wrapping the column breaks it, including a no-op concatenation. |
| `WHERE technician LIKE '%eier'` | `SCAN maint_job` | Leading wildcard — no prefix to seek. |
| `WHERE technician LIKE 'Bei%'` | `SCAN maint_job` | **The prediction I got wrong.** I expected a `SEARCH` here — the standard rule is "leading wildcard bad, trailing wildcard fine", and I had just watched the leading-wildcard version fail for exactly that reason. The cause turns out to be collation, not the wildcard: see §3.1. |

That last row is the most useful line in this section, and it is useful precisely because the rule I was applying is *almost* right. "Trailing wildcards can use an index" is true — it is just conditional on things nobody mentions when they teach the rule. I would have gone into a checkpoint stating it as a flat fact.

The general rule, and the one worth keeping: **the indexed thing must appear in the query exactly as it was indexed.** `technician` is indexed; `upper(technician)` and `technician || ''` are different expressions that happen to be built from it, and SQLite will not reason backwards from one to the other.

If I genuinely needed the case-insensitive search, the fix is to index the expression that is actually queried:

```sql
CREATE INDEX ix_job_tech_upper ON maint_job(upper(technician));   -- an expression index
```

## 5. Task B — algebra check

> ★ Task B. The query the pod understands best, written in σ/π/⋈ form by hand, then diffed against an LLM's translation.

Taking query 1 from the safari:

```sql
SELECT * FROM maint_job WHERE technician = 'Beier';
```

**My translation:**

$$\sigma_{\text{technician} = \text{'Beier'}}(\text{maint\_job})$$

No projection, because `SELECT *` keeps every attribute; no join, because there is one table. The point of starting here is that the mapping is visible: `WHERE` *is* σ, and nothing else is going on.

The more interesting one is the dashboard query from Task 1, which uses the whole vocabulary:

$$\pi_{\text{city},\ \text{customers},\ \text{revenue}}\Big(\ \gamma_{\text{city};\ \text{COUNT(DISTINCT customer\_id)} \to \text{customers},\ \text{SUM(qty} \times \text{price)} \to \text{revenue}}\big(\ \sigma_{\text{ordered\_on} \geq \text{'2025-01-01'} \wedge\ \text{ordered\_on} < \text{'2026-01-01'}}(\ \text{customer} \bowtie \text{orders} \bowtie \text{order\_line} \bowtie \text{product}\ )\ \big)\Big)$$

Read inside-out, and the order is the *evaluation* order, not the written order:

| Algebra | SQL | Step |
|---|---|---|
| ⋈ ⋈ ⋈ | `FROM … JOIN … JOIN … JOIN …` | 1 — build the joined relation |
| σ | `WHERE` | 2 — keep 2025 rows |
| γ | `GROUP BY` + `COUNT`/`SUM` | 3 — collapse to one row per city |
| π | `SELECT` list | 4 — choose the output columns |
| (sort) | `ORDER BY` | 5 — not an algebra operator; relations are unordered sets |

**Where the LLM and I disagreed.** Asked to translate the same query, the model produced σ *before* the joins — pushing the date filter onto `orders` first:

$$\text{customer} \bowtie \big(\sigma_{\text{ordered\_on} \geq \dots}(\text{orders})\big) \bowtie \text{order\_line} \bowtie \text{product}$$

I checked rather than assumed, and **both are right, but they are not the same claim**:

- Mine is the *literal* translation of the SQL as written — filter after joining.
- The model's is the *optimized* form, and it is a valid rewrite here because the predicate touches only `orders` and all the joins are inner. This is predicate pushdown, and it is exactly what a planner is allowed to do.
- The equivalence would **break** if any join were a `LEFT JOIN`: filtering `orders` first keeps customers with no 2025 orders (with NULLs), while filtering after the join removes them entirely. Same two expressions, different answers.

That is the real lesson from the diff: the model gave an answer about what the engine *may* do, in response to a question about what the SQL *says*, and did not flag the difference. The disagreement was the useful part.

> **Task 4 is the same exercise and the same answer** — the module asks for one query from algebra to plan, and the dashboard query above is mine: algebra here, plan in [`llm-query.md`](./llm-query.md) §3.

## 6. LLM Q&A — claims I tested

| # | What I asked | What it claimed | Verdict after running it |
|---|---|---|---|
| 1 | *"Why can't an index help `WHERE technician LIKE '%ei%'`? What could?"* | Leading wildcard prevents index use; a full-text index or a reversed-column index could help. | **Confirmed** for the leading wildcard. But it also implied `LIKE 'Bei%'` *would* use the index, which is false by default (§3.1). Right rule, wrong boundary. |
| 2 | *"When does SQLite use a covering index, and when does it still visit the table?"* | Covering when every column the query needs is in the index. | **Confirmed exactly** — §3.2 reproduces it with one column changed. |
| 3 | *"Which indexes should I add to speed up this dashboard query?"* | Three: on `orders(ordered_on)`, `order_line(order_id)`, `order_line(product_id)`. | **Two of the three were wrong for this query.** One left the plan untouched, one made it ~4× slower, one was never used at all. [`bench.md`](./bench.md) has the numbers. |
| 4 | *"Why does SQL evaluate `FROM` before `SELECT`? Give me a query that fails because someone assumed the written order."* | Gave the alias-in-`WHERE` example. | **Confirmed** — see below. |

The clause-order counterexample, verified:

```sql
-- fails: `revenue` does not exist yet when WHERE runs
SELECT c.city, SUM(ol.qty * p.price) AS revenue
FROM customer c JOIN orders o ON o.customer_id = c.customer_id
JOIN order_line ol ON ol.order_id = o.order_id
JOIN product p ON p.product_id = ol.product_id
WHERE revenue > 1000
GROUP BY c.city;
-- Error: misuse of aggregate / no such column: revenue
```

Written order is `SELECT … FROM … WHERE … GROUP BY … HAVING … ORDER BY`.
Evaluated order is `FROM → WHERE → GROUP BY → HAVING → SELECT → ORDER BY`.
`revenue` is created at step 5 and used at step 2. The fix is `HAVING SUM(ol.qty * p.price) > 1000`, which runs at step 4 — after the grouping that makes the aggregate meaningful. `ORDER BY revenue` *does* work, because it runs at step 6.

## 7. Task C — exchange with a neighbouring pod

> ★ Task C. 15 minutes: compare plans with another pod, name the surprise, swap curiosities.
> **Status: prepared, not yet held.** This task is a 15-minute live exchange with a
> neighbouring pod; it needs them in the room. Everything below is my side of it,
> written before the conversation. The agreed points are deliberately blank rather
> than filled in — the instructor may ask the other pod what we agreed, and an answer
> invented in advance is the one thing in a portfolio that cannot be recovered from.

**Pod I paired with:** *(pending — no Task Pod assigned to me as of this session; Module 2's exchange was with an ad-hoc group)*
**Their SQLite version:** *(pending)* · **mine:** 3.45.3 (2024-04-15)

**1. Plan comparison — what I already know to compare.** The module warns that Windows, macOS and Linux do not ship the same SQLite, and that a differing plan is the discussion rather than a problem. I have a concrete cross-version data point to bring: the same safari queries run on SQLite **3.53.1** produce the **same** plans as my 3.45.3 — including the `LIKE 'Bei%'` scan — so on these queries the two builds agree. That makes any *disagreement* with another pod's plan more interesting, not less, because it would have to come from something other than a version bump.

The `LIKE 'Bei%'` result is still the one most likely to differ on a third build, since the `LIKE` optimization conditions are exactly the kind of thing refined between releases. It is also the one where a pod on Windows (which may ship a different default) is most likely to contradict me.

**2. The surprise I am naming:** the trailing-wildcard `LIKE` that scanned anyway (§3.1). Most pods will have written down "leading wildcard bad, trailing wildcard fine" and not tested the second half.

**3. Questions I am taking to them, not just answers:**

- Did your dashboard get *slower* when you added `ix_orderline_order`? If not, what plan did you get? (If their plan stayed on `SCAN ol`, their SQLite made a different costing decision than mine — that is the most interesting difference available.)
- What did you conclude about `ix_orderline_product`? "Useless index" is the trap; "useless *for this query*" is the result.
- Did anyone try an **expression index** to rescue the `upper(technician)` case?

**4. What I expect to defend.** If the other pod concluded "we added indexes and it got faster", I am going to be the one arguing that two of the three recommended indexes were neutral-to-harmful, with the plans to show it. That is a real disagreement to have rather than a quiz, and it is the likeliest one.

**Agreed points:** *(to be filled in from the exchange — 3–5 points both pods stand behind)*

**Disagreement left open:** *(to be filled in)*

**Image to post in Discord:** the before/after plan table in §4 step 2 — one index, three queries, three different outcomes, which is the single most transferable idea in this module. (Posting pending the exchange, since the task asks the two pods to pick one jointly.)

## 8. The harvest — curiosities collected

> Ungraded by design. A statement that looked strange, hard, or worth arguing about. Source given for each.

| # | Curiosity | Source | Why it is on the list |
|---|---|---|---|
| 1 | `WITH RECURSIVE n(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM n WHERE x < 240000)` | [Module 3 setup block](https://github.com/iotempire/iotempire-teaching/blob/main/full-classes/hsbi-databases-10d/modules/03-llm-assisted-sql-and-query-profiling.md#setup) | 240,000 rows out of a table that does not exist. A `SELECT` that refers to itself still looks illegal to me. |
| 2 | `USE TEMP B-TREE FOR count(DISTINCT)` | my own dashboard plan | I expected `DISTINCT` to be free inside an aggregate. It builds a whole second temporary structure. |
| 3 | `CO-ROUTINE (subquery-2)` | the window-function plan, [`stretcher.md`](./stretcher.md) | I do not fully know what a co-routine is in a query plan. **First-class "I don't know what this does" entry.** |
| 4 | `date('2025-01-01', '+' || (x % 540) || ' days')` | Module 3 setup, line 4 of the marked block | A date modifier built by string concatenation. At `x = 540` it is `+0 days`, so the range wraps back to the start — which is why the data runs to 2026-06-24, not 2025-12-31. |
| 5 | `SCAN orders USING COVERING INDEX ix_orders_ordered_on` | `wrapped-date` row in [`bench.md`](./bench.md) | A `SCAN` that uses an index. I had been reading `SCAN` as "the index failed", but here the index is used *and* every entry is read — a smaller thing scanned in full. |
| 6 | `printf('%05d', x)` | Module 3 setup, line 5 | Zero-padding so `SKU-00009` sorts before `SKU-00010`. Text sorting is the reason, and it is a trap I would have walked into. |
| 7 | A correlated subquery returning *more rows* than the `GROUP BY` it replaced | [`stretcher.md`](./stretcher.md) | 2,000 vs 400. Not a performance difference — a different question being answered. |

**For `#sql-questions`:** items 3 and 5 — what a `CO-ROUTINE` line actually means, and when a `SCAN … USING COVERING INDEX` is good news versus bad.

---

[← Module 3 home](./README.md) · [Portfolio home](../README.md)
