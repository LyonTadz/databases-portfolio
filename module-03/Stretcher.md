# Task 5 (Stretcher) — Window functions and a subquery rewrite

[← Module 3 home](./README.md) · [Benchmark](./bench.md) · [SQL notes](./sql-notes.md)

**Environment:** SQLite `<paste your sqlite3 --version>`, `module-03/warehouse.db`. Medians of 5 runs.

---

## The starting report — late orders per customer

```sql
SELECT c.customer_id, c.name, COUNT(*) AS late_orders
FROM orders o
JOIN customer c ON c.customer_id = o.customer_id
WHERE o.status = 'late'
GROUP BY c.customer_id, c.name
ORDER BY late_orders DESC;
```

```
SCAN o
SEARCH c USING INTEGER PRIMARY KEY (rowid=?)
USE TEMP B-TREE FOR GROUP BY
USE TEMP B-TREE FOR ORDER BY
```

**400 rows · 4.36 ms.**

## Rewrite 1 — correlated subquery

```sql
SELECT c.customer_id, c.name,
       (SELECT COUNT(*) FROM orders o
        WHERE o.customer_id = c.customer_id AND o.status = 'late') AS late_orders
FROM customer c
ORDER BY late_orders DESC;
```

```
SCAN c
CORRELATED SCALAR SUBQUERY 1
SCAN o
USE TEMP B-TREE FOR ORDER BY
```

**2,000 rows · 2,644.12 ms.**

Two things went wrong, and only one of them is about speed.

**It answers a different question.** 2,000 rows, not 400. The `GROUP BY` version can only produce a row for a customer who *has* a late order, because the rows it groups come from `orders`. The subquery version starts from `customer` and asks about each one, so the 1,600 customers with **zero** late orders come back with `late_orders = 0`. Neither is wrong — but swapping one for the other as a "rewrite" silently changes the report, and nothing in the SQL announces it.

**It is 600× slower.** `CORRELATED SCALAR SUBQUERY 1` followed by `SCAN o` means: for each of the 2,000 customers, scan all 60,000 orders. That is 120 million row reads to answer a question the `GROUP BY` answers in one 60,000-row pass. The word `CORRELATED` in a plan is the warning — it means the inner query depends on the outer row and therefore cannot be run once and reused.

## Rewrite 2 — window function

```sql
SELECT DISTINCT c.customer_id, c.name,
       COUNT(*) OVER (PARTITION BY c.customer_id) AS late_orders
FROM orders o
JOIN customer c ON c.customer_id = o.customer_id
WHERE o.status = 'late'
ORDER BY late_orders DESC;
```

```
CO-ROUTINE (subquery-2)
CO-ROUTINE (subquery-3)
SCAN o
SEARCH c USING INTEGER PRIMARY KEY (rowid=?)
USE TEMP B-TREE FOR ORDER BY
SCAN (subquery-3)
SCAN (subquery-2)
USE TEMP B-TREE FOR DISTINCT
USE TEMP B-TREE FOR ORDER BY
```

**400 rows · 10.46 ms** — and the result set is **identical** to the `GROUP BY` version, verified row for row.

But look at the plan: nine lines instead of four, two `CO-ROUTINE`s, and **four** temporary B-trees where the original needed two. The cost is structural. A window function does not collapse rows — it computes a value *alongside* every row and leaves all of them standing. So this query produces one row per late order (about 12,000 of them), attaches the per-customer count to each, and then needs `DISTINCT` to throw the duplicates away again. The `GROUP BY` never materializes them in the first place.

## Comparison

| | rows | median | plan lines | temp B-trees |
|---|---:|---:|---:|---:|
| `GROUP BY` | 400 | **4.36 ms** | 4 | 2 |
| correlated subquery | 2,000 | 2,644.12 ms | 4 | 1 |
| window function | 400 | 10.46 ms | 9 | 4 |

## What I take from this

**`GROUP BY` wins, and it is not close.** It is the fastest, the shortest, and the only one of the three whose plan I can read at a glance.

**The window function is not the wrong tool — it is the wrong tool *here*.** `COUNT(*) OVER (PARTITION BY …)` exists so you can keep the detail rows *and* have the aggregate: "show me each late order, and how many that customer has in total". The moment I add `DISTINCT` to throw the detail away, I am paying for a feature I then discard. The `DISTINCT` is the smell.

**Which one did the LLM reach for by default?** Asked to "rewrite this report", it produced the **window-function** version unprompted, described it as "more modern and efficient", and did not mention that it is 2.4× slower here or that the `DISTINCT` is doing cleanup work. Asked specifically for a subquery version, it produced the correlated one **without flagging that the row count changes** — which is the more serious miss, because a timing regression shows up in testing and a silently different report does not.

That is the Frachtflow failure in miniature: the wrong list of late orders, returned for a month, by a query that ran fine.

---

[← Module 3 home](./README.md) · [Benchmark](./bench.md)
