# Module 5 · Round 7 — Harvest: the curiosities I collected

[← Round 6 memo](./memo.md) · [Module 5 home](./README.md) · [Stretcher](./stretcher.md)

Round 7 is collection, not explanation: scan the material, mark what looked
strange or worth arguing about, swap lists with the nearest pod. Every item below
has the evidence that made me notice it and a source for the part I had to look
up. The ones I could not resolve are in §10, for `#sql-questions`.

---

## 1 · `printf('%.2f', …)` stores money as text, and `MAX` gets it wrong

The build writes prices with `printf`, so `flat_jobpart.part_price` has **text**
affinity. The decomposition `CAST`s them to `REAL`. Both columns hold the same ten
prices, 6.00 to 15.00:

| Query | On the TEXT column | On the REAL column |
|---|---|---|
| `SUM(part_price)` | 2,100,000.0 | 2,100,000.0 |
| `MAX(part_price)` | **9.00** | **15.0** |
| `ORDER BY part_price LIMIT 5` | 10.00, 11.00, 12.00, 13.00, 14.00 | 6.0, 7.0, 8.0, 9.0, 10.0 |

**`SUM` coerced the text and gave the right answer. `MAX` compared strings and
gave a wrong one**, because `'9.00' > '15.00'` lexicographically. Had the module
asked for the most expensive part instead of the total cost, the unnormalized
table would have answered 9.00 and nothing would have errored.

What makes it dangerous is the asymmetry: the aggregate that converts and the
aggregate that does not sit in the same `SELECT` list and look identical. The
rule is SQLite's type affinity — arithmetic coerces, comparison respects storage
class, and a text value sorts after every number.

*Source:* [SQLite datatypes & type affinity](https://www.sqlite.org/datatype3.html)
(§3 on affinity, §4 on comparison and storage classes).

**This is why 1NF's "atomic values" is not the whole story.** The column is atomic
— one value per cell — and still wrong, because atomicity says nothing about
type. The `TEXT` price is a defect that no normal form catches.

---

## 2 · The `CROSS JOIN` that makes 200,000 rows out of two counters, and its dead code

```sql
WITH RECURSIVE j(n) AS (SELECT 1 UNION ALL SELECT n+1 FROM j WHERE n < 20000),
               p(k) AS (SELECT 1 UNION ALL SELECT k+1 FROM p WHERE k < 10)
INSERT INTO flat_jobpart SELECT … FROM j CROSS JOIN p;
```

Two recursive CTEs and a `CROSS JOIN`: 20,000 × 10 = 200,000 rows, in 1.2 s, with
no random number anywhere — which is why a reviewer rebuilding the database gets
byte-identical data.

The curiosity is the dead code. `'P-' || printf('%04d', (k % 40) + 1)` looks like
it generates 40 part numbers; `k` only runs to 10, so `k % 40` is `k`, and the
catalogue is `P-0002` … `P-0011` — **ten parts, and not starting at `P-0001`**.
That is the answer to Round 3's exchange question, and I did not spot it by
reading; I spotted it because `SELECT COUNT(*) FROM part` said 10.

Second-order consequence worth having: **every job uses every part**, which is why
`job_part`'s composite primary key never collides, and why the "10 parts per job"
and "10 parts in the catalogue" are the same 10.

---

## 3 · An index that makes a query slower

`SCAN report_jobpart USING INDEX ix_report_machine` on a query with no `WHERE` on
`machine_id` and no `ORDER BY`. Dropping the index made it **1.42× faster** and
saved 2,920 KB ([Round 4](./benchmark.md) §3).

The mental model I had — "indexes make reads faster, writes slower" — is wrong in
a specific way: an index helps a read only if it lets the engine *skip rows*.
Here it supplies rows in `machine_id` order (saving a sort for the `GROUP BY`) at
the cost of 200,000 index entries plus 200,000 scattered rowid lookups, and the
trade is bad. In a plan, **`SEARCH` skips rows and `SCAN` does not**, so
`SCAN … USING INDEX` is the planner announcing it is paying for an index it is not
filtering with.

*Source:* [Use The Index, Luke](https://use-the-index-luke.com/) — the chapter on
clustering and the "index-only scan" is the formal version of this;
[SQLite query optimizer overview](https://www.sqlite.org/optoverview.html) §9 on
covering indexes.

---

## 4 · `ANALYZE` reverses which schema design wins

The biggest surprise in the module, and it is not about normalization at all.
One `ANALYZE` (77 ms) writes six rows into `sqlite_stat1`, and the normalized
query goes from 55.3 ms to 39.8 ms while the denormalized one does not move —
flipping the verdict from "denormalized wins by 48%" to "normalized wins by 35%"
([Round 4](./benchmark.md) §4).

Two things in the new plan I had to look up:

- **`SEARCH j USING AUTOMATIC PARTIAL COVERING INDEX (machine_id=?)`** — SQLite
  built an index *during the statement*, used it, and threw it away. It exists
  only for that statement, is never written to disk, and is only visible to the
  one connection.
- **The join order inverted.** Before statistics it drove from the 200,000-row
  `job_part`; after, from the 50-row `machine`.

*Source:* [SQLite query optimizer overview](https://www.sqlite.org/optoverview.html)
— §14 "Automatic Query-Time Indexes" (the cost rule: an automatic index is built
only if the lookup is expected to run more than log N times), §7 "Joins" and §8
"Choosing Between Multiple Indexes" (why statistics change join order). Note the
exact phrase "automatic partial covering index" is not in the documentation — it
is the plan combining §14's automatic index with §9's covering index and
`PARTIAL`; that combination is the thing I would still like named properly (§10).

**And the uncomfortable half:** statistics did nothing for the denormalized query.
A single table has no join order to get right, so the one thing that would help it
— not walking that index — is the one thing the planner would not reconsider.

---

## 5 · The module's `dbstat` query under-counts both designs

The storage comparison names tables only, and gets **2.72×**. Add the indexes each
design actually has on disk and it is **1.72×** ([Round 5](./price.md) §3).

The hidden cost is almost all one object: **`job_part`'s primary-key index is
3,992 KB — larger than the 3,328 KB table it indexes.** A `PRIMARY KEY (job_id,
part_no)` on a rowid table stores both columns in the index *and* both columns
plus a rowid in the table, so a pure junction table pays for its key twice.
`WITHOUT ROWID` would merge the two into one B-tree.

And the twist: that "wasteful" index is the `COVERING INDEX` that makes the
normalized query win in §4. **The expensive index earns its keep and the cheap one
does not**, which is the opposite of how I would have ranked them by size.

*Source:* [the `dbstat` virtual table](https://www.sqlite.org/dbstat.html) ·
[`WITHOUT ROWID` tables](https://www.sqlite.org/withoutrowid.html).

---

## 6 · `PRAGMA foreign_keys` is a no-op inside a transaction, silently

Set it inside an open transaction and it does not error, does not take effect, and
**reads back as `0`** ([Round 3](./normalization-notes.md) §3.3). My first attempt
at the enforcement test had an implicit transaction open from an earlier insert —
Python's `sqlite3` opens one for you unless `isolation_level=None` — so I measured
"foreign keys are off even when they are on" and believed it for a while.

This is the third variant of Module 4's lesson that a rule living in the caller
gets forgotten. Here it is worse than forgotten: it can be **set, confirmed, and
still absent**.

*Source:* [`PRAGMA foreign_keys`](https://www.sqlite.org/pragma.html#pragma_foreign_keys)
— "this pragma is a no-op within a transaction".

---

## 7 · `SELECT DISTINCT` in the decomposition is an assertion

`INSERT INTO job SELECT DISTINCT job_id, machine_id, technician, done_on` assumes
`job_id → technician`. Feed it one job with two technicians and the primary key
refuses it — **and the whole 20,000-row load rolls back**, because the
`INSERT … SELECT` is one statement and therefore one transaction
([Round 3](./normalization-notes.md) §3.4).

Both halves are interesting. The refusal is the decomposition checking my model.
The all-or-nothing rollback is the operational cost of finding out this way: one
contradictory row in a 200,000-row extract loads nothing, with an error naming the
constraint but not the row. The fix is to run the acceptance test *first*:

```sql
SELECT job_id, COUNT(DISTINCT technician) AS n
FROM flat_jobpart GROUP BY job_id HAVING n > 1;
```

---

## 8 · DuckDB refuses SQL that SQLite accepts, and SQLite was relying on an FD

```
BinderException: column "site" must appear in the GROUP BY clause
```

`SELECT m.machine_id, m.site, j.technician, SUM(...) … GROUP BY m.machine_id,
j.technician` runs fine in SQLite and is rejected by DuckDB
([stretcher](./stretcher.md) §2). SQLite allows **bare columns** in an aggregate
query and takes the value from an arbitrary input row of each group.

It is correct here *only* because `machine_id → site`, the functional dependency
from Round 1 — so the arbitrary row has the right value no matter which one it
is. Nothing in the SQL records that. Group by `machine_id` and select
`technician` and SQLite returns one technician per machine with no warning.

*Source:* [SQLite `SELECT`](https://www.sqlite.org/lang_select.html) §2.5 "Bare
columns in an aggregate query" — the value comes from an arbitrary row, the
choice can change between invocations, and on an empty aggregate it can be any
value at all, including one found nowhere in the tables. The documentation notes
most other engines reject this and that SQLite treats it as a deliberate
extension.

**So the strict engine caught an undocumented dependency assumption.** That is the
module's theme arriving sideways: the FD was load-bearing for a query's
correctness, not just for its storage.

---

## 9 · A single-valued column is determined by everything

In the five-row extract `site` is `'Gütersloh'` in every row, so **every**
dependency `X → site` holds — vacuously, for any `X`, including the empty set
([Round 3](./normalization-notes.md) §1.1, item 9). I did not notice this by
looking at the rows; I noticed it when an FD-checking function reported that
`technician → site` and `part_no → site` both held.

It is the cleanest possible illustration of the module's warning that an LLM will
promote an accident in five rows into a dependency — except the trap works on
humans and on code as well, and the data cannot tell you which side of the line
it is on. `SELECT COUNT(DISTINCT col)` before trusting any FD into `col` is a
cheap guard.

Related, and the one that survived: `part_price → part_no` is an accident in five
rows, and it is **still true at 200,000 rows**, because the generator gave all ten
parts distinct prices. The other two accidents broke at scale; this one did not.
**Volume is evidence, not proof.**

---

## 10 · Unresolved — for `#sql-questions`

1. **Why does `ANALYZE` not talk SQLite out of `ix_report_machine`?** After
   statistics the planner knows the index has 4,000 rows per `machine_id` and
   still walks it for a query with no `machine_id` predicate, where a plain scan
   is 1.45× faster. Is the sort it avoids being over-valued, or is a
   `GROUP BY`-ordering benefit simply not costed? (Module 5, [Round 4](./benchmark.md) §4.1)
2. **What exactly is an `AUTOMATIC PARTIAL COVERING INDEX`?** The three modifiers
   are documented separately and the combination is not. In particular: what makes
   it *partial*, and is the partial predicate derivable from the plan?
   (Module 5, §4 above)
3. **Is `WITHOUT ROWID` the standard advice for a pure junction table?** It should
   remove most of `job_part`'s 3,992 KB duplicate key index. If so, why is it not
   the default for a table whose primary key is all of its columns?
   (Module 5, §5 above)
4. **How should price history be modelled here?** `part_no → part_price` assumes a
   part has one price forever, so every historical cost is silently restated at
   today's price — in *both* designs
   ([Round 1](./normalization-notes.md) §1.3). Is the normal-form answer a
   `part_price(part_no, valid_from, price)` table, and does that break 3NF's
   promise that one fact lives in one place?

---

## Exchange — "I collected these, which did you find?"

The three I expect to be shared: the `TEXT` price (§1), the 10-parts-not-40
surprise (§2), and `dbstat`.

The two I expect to be mine alone, because both need an experiment the module
does not ask for: **`ANALYZE` reversing the verdict** (§4) and **the index making
the read slower** (§3) — the second is in the module's own notes as something to
find, but only as a note, and finding it is what made me look for the first.

The one I most want a second opinion on is §9: whether "the FD holds at 200,000
rows" counts as evidence at all, given that one of my three accidents survived
the scale-up unchanged.

---

[← Round 6 memo](./memo.md) · [Module 5 home](./README.md) · [Next: the stretcher →](./stretcher.md)
