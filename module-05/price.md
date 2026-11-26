# Module 5 · Round 5 — Price it: what the copy costs on writes and on disk

[← Round 4 benchmark](./benchmark.md) · [Module 5 home](./README.md) · [Round 6 — the memo](./memo.md)

[Round 4](./benchmark.md) measured what the denormalized table buys. This is the
other side of the ledger. All numbers from [`evidence.py`](./evidence.py) §5 —
see [`evidence.txt`](./evidence.txt).

> **The number that scales: 1 row versus 4,000.** Everything else on this page is
> a property of this machine; that ratio is a property of the schema.

---

## 1 · One machine changes site

The module is explicit that timing a single-row insert is pointless — both
designs do that in well under a millisecond. The cost of denormalization is
**changing a duplicated fact**.

`cnc-02` appears in the database three times over:

| Table | Rows mentioning `cnc-02` |
|---|---|
| `machine` | **1** |
| `job` | 400 |
| `report_jobpart` | **4,000** |

```sql
UPDATE machine        SET site = 'Bielefeld' WHERE machine_id = 'cnc-02';
UPDATE report_jobpart SET site = 'Bielefeld' WHERE machine_id = 'cnc-02';
```

| Statement | Rows changed | min (ms) | median (ms) |
|---|---|---|---|
| `UPDATE machine` | **1** | 0.02 | 0.02 |
| `UPDATE report_jobpart` | **4,000** | 3.89 | 3.94 |

**4,000× the rows, and roughly two orders of magnitude the time.** Nine
repetitions each, every one inside its own transaction and rolled back, so each
run starts from the same state and the minimum is the estimator — same method as
[Round 4](./benchmark.md) §1.

I am deliberately not quoting a precise time ratio. The one-row update's minimum
is **0.02 ms**, which is at the resolution of the clock I am measuring with, so
the ratio it produces is unstable — consecutive runs of
[`evidence.py`](./evidence.py) gave me 178× and 204× for timings that barely
moved. The row count is exact and the time ratio is not, which is the whole
reason the next section argues for reporting the former.

### 1.1 Two honest caveats about those milliseconds

**These are warm, uncommitted numbers.** Each attempt runs in a transaction that
is rolled back, so after the first run the pages are in cache and **no run pays
for a commit** — no WAL append, no fsync. A real `UPDATE` of 4,000 rows commits,
and on a plant gateway with a cheap SSD the durability cost could easily exceed
the 3.89 ms of row work. So the measured gap understates the real one rather
than overstating it.

**But the time is not the point.** 3.89 ms is not a problem anybody would notice.
The problem is what [Round 2](./normalization-notes.md) §2.1 showed by hand: a
4,000-row update is a change that can be **partially applied**, and the end state
of a half-applied one is a machine with two sites and no error anywhere. A 1-row
update has no half. That is why I would put the row count in the memo and leave
the milliseconds out of it.

Scale it out of the lab: Kortmann has 50 machines over 90 days. On the production
dataset the story describes — years of history — one machine's site change is a
six-figure row count, and at that size it is also a lock the single writer holds
while the dashboard waits.

---

## 2 · Storage, per object

`dbstat` gives bytes per table and per index:

| Object | Bytes | KB |
|---|---|---|
| `flat_jobpart` | 11,890,688 | 11,612.0 |
| `report_jobpart` | 11,091,968 | **10,832.0** |
| `sqlite_autoindex_job_part_1` | 4,087,808 | 3,992.0 |
| `job_part` | 3,407,872 | 3,328.0 |
| `ix_report_machine` | 2,990,080 | 2,920.0 |
| `ix_flat_machine` | 2,990,080 | 2,920.0 |
| `job` | 655,360 | 640.0 |
| `part` · `machine` · each autoindex · `sqlite_schema` | 4,096 each | 4.0 each |

`dbstat` is present in this build. If it is missing in yours, keep the row counts
from §1 — the module is right that the storage number is a bonus and the row
count is the lesson.

---

## 3 · The comparison the module asks for, and the one it leaves out

The module's query names the four tables and the one table:

| Design | Bytes | KB | Ratio |
|---|---|---|---|
| Normalized — `job` + `job_part` + `part` + `machine` | 4,071,424 | 3,976.0 | 1× |
| Denormalized — `report_jobpart` | 11,091,968 | 10,832.0 | **2.72×** |

2.72× matches what the module predicts, and I would have stopped there if I had
not just spent Round 4 learning that an index is not free. **An index is storage
too, and both designs have one:**

| Design | Tables | Indexes | Total KB | Ratio |
|---|---|---|---|---|
| Normalized + its implicit PK indexes | 3,976.0 | 4,000.0 | **7,976.0** | 1× |
| Denormalized + `ix_report_machine` | 10,832.0 | 2,920.0 | **13,752.0** | **1.72×** |

**The headline 2.72× is an artefact of which objects the query names.** Count what
is actually on disk for each design and denormalization costs 1.72×, not 2.72× —
still a real cost, 5.6 MB against 7.8 MB, but a different claim.

The normalized side's hidden storage is almost all one object:
**`job_part`'s primary key costs 3,992 KB — more than the 3,328 KB table it
indexes.** A `PRIMARY KEY (job_id, part_no)` on a rowid table stores both columns
in the index *and* both columns plus a rowid in the table, so the junction table
pays for itself twice. `WITHOUT ROWID` would collapse the two into one B-tree and
remove most of that 3,992 KB — which is the experiment I have not run, and the
obvious next one.

That index looks like pure overhead until you read [Round 4](./benchmark.md) §4.1,
where it is the `COVERING INDEX` that lets the normalized query beat the
denormalized one after `ANALYZE`. **The 3,992 KB is what A's speed is made of.**

### 3.1 The whole file

The database is **35.4 MB**, of which **14.2 MB is `flat_jobpart` and its
index** — the unnormalized table I decomposed in Round 3. It is kept only so the
build is reproducible; a production database would drop it after the migration,
which would take the file to roughly 21 MB. Worth saying out loud because
"normalizing saved disk" and "the file got smaller" are not the same claim: the
file got *bigger*, because I now store the data three ways.

---

## 4 · Dropping the index on purpose

The module asks for this and I had already found it the other way round in
[Round 4](./benchmark.md) §3:

```sql
DROP INDEX ix_report_machine;
```

**The dashboard query goes from 53.3 ms to 37.6 ms — 1.42× faster with less
storage.** The planner was walking the whole index and then fetching every row
from the table, which costs more than one sequential scan.

So on a pure read workload the right answer is to delete the index: faster *and*
2,920 KB smaller. But §1 is the counter-argument on the same table —
`UPDATE report_jobpart … WHERE machine_id = 'cnc-02'` is exactly the query shape
`ix_report_machine` exists for, and without it that 4,000-row update becomes a
200,000-row scan to *find* the 4,000 rows.

I measured both sides rather than guessing which matters more, and that is the
one place in this module where the two halves of the trade-off land on the same
object: **the index makes the dashboard 42% slower and the maintenance path
much faster, and you cannot have both.** For a dashboard that runs every 30
seconds against a site change that happens twice a year, the index should go.
That is a workload argument, not a schema argument, and it is in
[the memo](./memo.md).

---

## 5 · The filled benchmark table

The module's table, with every number I measured. Dashboard timings are the
minima from [Round 4](./benchmark.md); "best" means the configuration that suits
that design (statistics collected, and for the report table no index).

| Design | Dashboard query — as built | Dashboard query — best config | Rows changed by one site update | Storage (KB) | Redundancy? |
|---|---|---|---|---|---|
| **Normalized (3NF)** | 55.3 ms | **38.9 ms** | **1** | 7,976 | none |
| **Denormalized (report)** | 53.3 ms | **37.0 ms** | **4,000** | 13,752 | site / technician / price repeated on every row |

Read the row that matters: **in the best configuration for each, the
denormalized table is 5% faster, costs 1.72× the storage, and turns a 1-row
write into a 4,000-row one.**

"As built" is the column a pod would fill in if it stopped after Phase 1, and it
says 4%. Neither column supports the shortcut.

---

## 6 · Exchange — "guess my query timings before I show you"

What I would tell a neighbour first: **two storage numbers (7,976 KB and
13,752 KB) and two row counts (1 and 4,000)**, then ask them to guess the
timings. The guess I expect is "the denormalized one is several times faster,"
because that is what the storage and row-count ratios imply and what the story
primes you for. The answer is 5%.

And then the question I would ask back, which is the one I got wrong myself:
*which number did you change to make it faster — the schema, or something else?*
On this database `ANALYZE` and one `DROP INDEX` move the result further than the
schema does.

---

[← Round 4](./benchmark.md) · [Module 5 home](./README.md) · [Next: Round 6 — the memo →](./memo.md)
