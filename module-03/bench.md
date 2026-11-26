# Task 2 — Index benchmark: prove it or disprove it

[← Module 3 home](./README.md) · [Task 1](./llm-query.md) · [SQL notes](./sql-notes.md)

**Method:** [`bench.py`](./bench.py) — each query run 5 times, median reported, `EXPLAIN QUERY PLAN` captured at every step. Indexes added **one at a time**, never as a batch. The script drops and recreates them itself, so the numbers stay comparable between runs.

**Environment:** SQLite `<paste your sqlite3 --version>`, macOS. Timings are from Python's `sqlite3` driver, not the `sqlite3` CLI's `.timer` — the two report different numbers for the same query, so they are not comparable across tools. Only compare rows within this table.

---

## 1. What the LLM recommended

Asked to optimize the Task 1 dashboard query, the model returned three indexes:

```sql
CREATE INDEX ix_orders_ordered_on  ON orders(ordered_on);
CREATE INDEX ix_orderline_order    ON order_line(order_id);
CREATE INDEX ix_orderline_product  ON order_line(product_id);
```

Plausible reasoning: the first serves the `WHERE`, the other two serve the joins. Tested one at a time, **two of the three are wrong for this query and one of them is actively harmful.**

## 2. The numbers

Median of 5 runs, in milliseconds:

| Step | dashboard | single-day | by-product | wrapped-date |
|---|---:|---:|---:|---:|
| baseline (no indexes) | 84.23 | 1.65 | 5.49 | 3.52 |
| `+ ix_orders_ordered_on` | 68.97 | **0.07** | 5.42 | 3.37 |
| `+ ix_orderline_order` | **297.08** | 0.07 | 5.35 | 3.40 |
| `+ ix_orderline_product` | 298.48 | 0.08 | **0.55** | 3.34 |

The four queries:

- **dashboard** — the Task 1 revenue-by-city query.
- **single-day** — `WHERE o.ordered_on = '2026-02-14'` joined to `customer` (111 matching rows).
- **by-product** — `SELECT SUM(ol.qty) FROM order_line WHERE product_id = 42`.
- **wrapped-date** — `WHERE date(ordered_on) = '2026-02-14'`, the negative control.

## 3. Step by step, with the plans

### Baseline

```
dashboard:    SCAN ol → 3 × SEARCH … INTEGER PRIMARY KEY → 3 × USE TEMP B-TREE
single-day:   SCAN o
              SEARCH c USING INTEGER PRIMARY KEY (rowid=?)
```

`SCAN o` reads all 60,000 orders to find 111.

### `+ ix_orders_ordered_on` — one query transformed, one untouched

**single-day: 1.65 ms → 0.07 ms, a ~23× speedup, and the plan proves why:**

```
SEARCH o USING INDEX ix_orders_ordered_on (ordered_on=?)
SEARCH c USING INTEGER PRIMARY KEY (rowid=?)
```

`SCAN orders` became `SEARCH orders USING INDEX`. This is the unambiguous case: a tiny slice of a large table, a plan you can point at, and an order-of-magnitude result.

**dashboard: plan completely unchanged.** Still `SCAN ol`. The timing moved 84 → 69 ms, which looks like an improvement and is **not a result** — the plan is identical, so nothing the engine does has changed. The module's rule applies directly: *a timing change with no plan change is usually noise*. I am recording it as noise, not a 18% win.

Why the index does nothing here: the dashboard reads 40,575 of 60,000 orders — two thirds of the table. An index is for finding a *small* fraction. Below roughly 10–20% selectivity the planner correctly decides that scanning is cheaper than 40,000 index descents plus 40,000 table fetches.

### `+ ix_orderline_order` — the index that made it four times slower

**dashboard: 68.97 ms → 297.08 ms.** This is the most valuable number on the page, and the plan explains it completely:

```
SEARCH o USING INDEX ix_orders_ordered_on (ordered_on>? AND ordered_on<?)
SEARCH c USING INTEGER PRIMARY KEY (rowid=?)
SEARCH ol USING INDEX ix_orderline_order (order_id=?)
SEARCH p USING INTEGER PRIMARY KEY (rowid=?)
USE TEMP B-TREE FOR GROUP BY
USE TEMP B-TREE FOR count(DISTINCT)
USE TEMP B-TREE FOR ORDER BY
```

**The whole loop nest inverted.** Before, `order_line` was the outer loop and everything else was a rowid lookup. Now `orders` is the outer loop — and `ix_orders_ordered_on`, which did nothing in the previous step, has suddenly become usable, because the new index made an orders-driven plan viable.

Having both indexes lets the planner choose: scan 240,000 order lines once, or seek into `order_line` 40,575 times. It picked the second. Each seek is two B-tree descents (index entry, then table row) and they land in random physical order, so the sequential 240,000-row read is replaced by ~243,000 scattered ones. Sequential beats random, and the clock says so by a factor of four.

**Every line of that plan is a `SEARCH`. Not one `SCAN` left. And it is four times slower.** `SEARCH` is not a synonym for "good" — it means the engine used an index, not that using it was wise.

### `+ ix_orderline_product` — never used by this query at all

**dashboard: 297.08 → 298.48 ms** (noise), and the plan is byte-identical. The index is simply absent from it.

The reason is in the plan's fourth line: `SEARCH p USING INTEGER PRIMARY KEY (rowid=?)`. The query reaches `product` through `order_line.product_id = product.product_id`, and `product_id` is `INTEGER PRIMARY KEY` — the rowid. There is nothing left to optimize on that side.

## 4. "Useless index" was the wrong conclusion

The right conclusion is **"useless *for this query*"**, and the proof is the `by-product` column:

```sql
SELECT SUM(ol.qty) FROM order_line ol WHERE ol.product_id = 42;
```

| | plan | median |
|---|---|---:|
| without the index | `SCAN ol` | 5.49 ms |
| with `ix_orderline_product` | `SEARCH ol USING INDEX ix_orderline_product (product_id=?)` | **0.55 ms** |

A 10× speedup from the exact index that did nothing a paragraph earlier. Same index, same table, same data — different query. **An index is not a property of a table; it is a relationship between a table and a predicate.**

## 5. The second negative: a function defeats the index

```sql
SELECT COUNT(*) FROM orders WHERE date(ordered_on) = '2026-02-14';
```

Even with `ix_orders_ordered_on` in place:

```
SCAN orders USING COVERING INDEX ix_orders_ordered_on
```

3.52 → 3.34 ms. No real change, and still a `SCAN`.

This plan line is worth a second look, because it is **not** the same as the bare `SCAN orders` from baseline — and it is not a success either. The engine cannot *seek* with `date(ordered_on)`, because the index stores `ordered_on`, not the function applied to it. But every value it needs happens to live in the index, so it walks the whole index instead of the whole table: a full scan over a smaller structure. Still linear. Still every row.

Compare `WHERE ordered_on = '2026-02-14'` — the single-day query, 0.07 ms with a real `SEARCH`. **Same column, same index, same answer; a 48× difference caused by one function call** that looked like harmless date hygiene.

## 6. Conclusions

1. **The plan and the clock answer different questions, and the interesting cases are where they disagree.** `ix_orders_ordered_on` improved the dashboard's time by 18% while changing nothing — noise. `ix_orderline_order` changed the plan dramatically and made it worse — a real result.
2. **Aggregate-heavy queries are not index problems.** The dashboard must touch 240,000 order lines no matter what. Indexes help you *avoid* reading rows; a query defined as "read everything and add it up" has nothing to avoid. If it genuinely needed to be faster, the move would be a summary table or a materialized aggregate, not another index.
3. **Of the LLM's three recommendations, one helped a query I had not asked about, one was neutral-then-harmful, and one was inert for this query.** Taking the list on trust would have left the dashboard four times slower with three indexes to maintain — slower writes, bigger file, worse. This is the entire point of the module.
4. **`SEARCH` is not the goal.** The slowest plan I measured is made entirely of `SEARCH` lines.

## 7. Reproducing this

```sh
sqlite3 module-03/warehouse.db ".read module-03/setup.sql"
uv run python module-03/bench.py
```

`bench.py` resets the indexes before it starts, so the baseline row is a true baseline on every run.

---

[← Module 3 home](./README.md) · [Task 1](./llm-query.md)
