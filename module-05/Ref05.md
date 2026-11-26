# Reflection 5 — Normalization vs. Denormalization Benchmarking Studio

> Module 5 · Session 5 · [Module 5 portfolio page](../module-05/README.md)

## Take-away — what I want to remember, and my advice

**The module asks which schema design is faster, and on this workload the schema
is not the variable that decides it.** I measured the same two queries in four
configurations without changing a line of either schema: the denormalized table
wins by 48%, loses by 35%, or ties, depending on whether an index exists and
whether anyone has run `ANALYZE`. In the best configuration for each design,
denormalizing buys **5%** — in exchange for 1.72× the storage and a one-row site
correction becoming a 4,000-row write.

That is the thing I want to remember, and it is not what I came in expecting.
I thought the lesson would be "denormalization is a trade: read speed for write
cost and redundancy", which is true and is what the handout teaches. What I
actually learned is that **the trade is much smaller than the operational
decisions sitting on top of it**, and that those decisions are invisible in the
DDL. `ANALYZE` is 77 ms and one word; it made the four-way join 1.39× faster and
did nothing at all for the single-table scan, because what it buys is a better
join order and the denormalized query has no joins to reorder. Deleting an index
made a read 1.42× faster *and* freed 2,920 KB. Neither is a schema change and
both are bigger than the schema change.

The second thing, and the one I would actually say in a meeting:
**denormalization pays when the join is the expensive part, not when the table is
merely smaller.** Here the dimensions are 50 rows, 10 rows and 20,000 rows — 4 KB
each for two of them — so 600,000 B-tree probes into permanently cached pages
cost about 4% of the query, and the scan and the `GROUP BY` cost the rest. Both
designs pay the scan and the group-by identically. So the story's 40-second
dashboard will not be fixed by copying columns, because copying columns does not
reduce rows touched by one.

This also connects to Module 4 more directly than I expected. There, integrity
turned out to be a property of the whole write path rather than of the
`CREATE TABLE`. Here, **performance turns out to be a property of the whole
configuration rather than of the schema.** Twice now the artefact the module
puts in front of me — the constraint set, the normal form — has been correct and
not the thing that determined the outcome.

**My advice to someone starting this module:** do Round 4 exactly as written,
then run `ANALYZE` and do it again. Six words of SQL, and it reverses the
headline. Everything I found worth writing down came from refusing to accept
Phase 1's 4% as the answer — it was too small to be the result the module was
set up to produce, and chasing *why* it was small is what produced the index
finding, the statistics finding, and the storage-accounting finding. A pod that
gets 4%, writes "the difference is small on 200,000 rows, which is itself a
finding" (which the handout offers them), and moves to Round 5 will have done the
task and missed the module.

## What was good

**Writing [`evidence.py`](../module-05/evidence.py) before the prose, again.** This
is the third module where I have done it and the first where it paid off before
I wrote a word: the FD-checking function
(`fd_holds(con, table, lhs, rhs)` — group by the left side, count distinct right
sides, having > 1) was three lines, and running it over all eleven of my Round 1
dependency claims immediately reported two I had not thought about.
`technician → site` and `part_no → site` both "hold", because `site` has exactly
one value in the five-row extract — so **every** dependency into a single-valued
column is vacuously true. I would not have caught that by reading five rows, and
the module's warning about an LLM promoting an accident into a dependency turns
out to apply to a human with a `GROUP BY` just as well.

The same function then re-tested every claim against 200,000 rows, which produced
the better half of the finding: two of my three "observed only" accidents broke at
scale, and one — `part_price → part_no` — survived, because the generator gave all
ten parts distinct prices. **Volume is evidence, not proof.** That is a sharper
statement than anything I had before I automated the check, and it came out of
writing the tool rather than out of thinking harder.

**Being made to prove the decomposition instead of trusting it.** `200000 =
200000` is a single comparison and it is the only thing standing between "I split
the table along its dependencies" and "I split the table". I also tested what the
`SELECT DISTINCT` in the decomposition is quietly asserting, by adding one row
giving a job a second technician: the primary key refuses it, and the whole
20,000-row load rolls back. The refusal is the schema checking my model. That is
the one moment in this course so far where a constraint has told me something
about my *understanding* rather than about my data.

**The rounds format, which I want to say something about because the module asks.**
It worked better than the pod study for me. The theory boxes are short enough that
reading one does not become the activity, and "read it only when the task makes
you want it" meant I read 2NF-vs-3NF *after* seeing the two bad arrows in my own
ER sketch, which is the right order. What I would cut: nothing from Rounds 1–4.
What I would add: Round 4 should say "now run `ANALYZE` and do it again" as a
required step, not leave it to a pod to wonder. It is six words and it changes the
conclusion, and a student who never runs it comes away believing a result that
the handout's own framing already doubts.

## What was difficult, where I struggled

**Getting a benchmark wrong for a third time, in a new way.** Module 4 taught me
to interleave the arms and estimate with the minimum, and I did both. It did not
save me, because I put the race inside
[`evidence.py`](../module-05/evidence.py) — which rebuilds a 200,000-row table and
runs eleven dependency checks across it first. The output was nonsense: **arm A's
minimum moved from 75 ms to 95 ms between two phases that do not touch arm A at
all**, against an effect size of 20 ms.

What took me a while to see is that interleaving cannot help here. Interleaving
protects against drift *during* the race; this was the state the process was in
*before* the race — a churning page cache and a busy allocator. Both arms were
equally affected, so the ratio was not obviously broken, and the only reason I
caught it was the control arm. **A benchmark has to own its process.** The fix was
organisational rather than statistical, which is a new category of mistake for me:
the first two were about estimators, this one was about where the code lives.
Timings now live in [`bench.py`](../module-05/bench.py) alone, which does nothing
else, and `evidence.py` prints plans and equality checks and explicitly refuses to
print a millisecond.

**Deciding what to do about the counter-demo that did not work.** The module's
optional try adds two dimensions and predicts the denormalized table will pull
ahead. On my machine it did not: both arms got slower and the ratio went from
1.48× to 1.43×. I then built a third experiment with a 20,000-row dimension, and
it got *worse* again — 1.31× — except that one is not clean evidence, because
adding two columns to the `GROUP BY` took the result from 3,500 rows to 68,580 and
the temporary B-tree started to dominate both arms. I changed two things at once.

I spent a while wanting to tune this until it agreed with the handout, and the
honest write-up was harder than the experiment: the module's *direction* is right
(denormalizing removes a probe), but the mechanism cuts both ways (it also adds a
column to every one of 200,000 rows), and which wins depends on the width of the
column against the cost of the probe. `vendor` has 10 rows and `site_dim` has 2 —
the demo adds *more* joins, not more expensive ones. What I can defend is narrow:
on 200,000 cache-resident rows in SQLite I could not construct a case where
denormalizing bought more than about 1.5×. I left all three negative results in.

**Storage accounting, which I nearly got wrong in the module's favour.** The
handout's `dbstat` query names four tables against one table and reports 2.72×. I
had written that number down before noticing that Round 4 had just spent an
afternoon teaching me that an index is not free — and both designs have indexes.
Counting them, it is 1.72×. Then the part that genuinely surprised me:
`job_part`'s primary-key index is **3,992 KB, larger than the 3,328 KB table it
indexes**, because a rowid table with a composite primary key stores both columns
twice. And that same index is the `COVERING INDEX` that makes the normalized query
win after `ANALYZE`. **The expensive index earns its keep and the cheap one does
not**, which is the reverse of how I would have ranked them by size.

## Good or fun struggling / exploration

**The `ANALYZE` experiment started as a throwaway sentence.** Writing my answer to
Round 4's exchange question ("did you get the same plan? if not, why?"), I listed
the reasons a neighbour's plan might differ and wrote "or they ran `ANALYZE` and
gave the planner statistics I never collected" — as a hypothetical. Then I
realised I could just run it, and it reversed the module's headline. The best
twenty minutes of the module came out of taking my own speculative sentence
literally. I have started treating "the experiment I have not run" as a to-do
list rather than a hedge, and there are three more on
[`harvest.md`](../module-05/harvest.md) §10.

**Reading a query plan properly for the first time.** `SCAN report_jobpart USING
INDEX ix_report_machine` on a query with no `WHERE` on `machine_id` and no
`ORDER BY` made no sense to me, and sitting with it is what produced the rule I
will actually keep: **`SEARCH` skips rows and `SCAN` does not**, so
`SCAN … USING INDEX` is the planner announcing it is paying for an index it is not
filtering with. After `ANALYZE` the normalized plan changed shape completely —
driving from the 50-row `machine` table, building an automatic index on `job`
during the statement, reading `job_part` from its primary key without touching the
table — and I could read what each line was doing. Three modules ago
`EXPLAIN QUERY PLAN` output was noise I pasted into a file because the task asked
for it.

**The DuckDB comparison refusing my SQL.** `BinderException: column "site" must
appear in the GROUP BY clause` for a query SQLite runs happily. SQLite allows bare
columns in an aggregate query and takes the value from an arbitrary row of each
group — which is correct here *only* because `machine_id → site`. The functional
dependency from Round 1 was load-bearing for the query's **correctness**, not just
for its storage, and nothing in the SQL said so. The module's subject matter
arrived from a direction the module does not mention, via an error message from a
different engine. Group by `machine_id` and select `technician` and SQLite would
have returned one technician per machine, silently wrong.

**`MAX` over a text price column returning 9.00.** `SUM` over the same column is
exactly right, because arithmetic coerces and comparison respects storage class.
Both aggregates sit in the same `SELECT` list and look identical. Had the module
asked for the most expensive part instead of the total cost, the unnormalized
table would have lied and nothing would have errored. The column is atomic, so
1NF has nothing to say about it — which is a useful limit on what the normal forms
are *for*.

## Show stoppers — anything to raise with peers or instructors

**The `done_on` index nobody builds.** The dashboard's only predicate is
`WHERE j.done_on >= date('2026-03-01')`, and nothing in this module indexes
`done_on` — not `setup.sql`, not the report table, not the optional tries. Both
designs scan everything and then filter. It is the most obvious thing to try
against the story's 40 seconds and the module never mentions it. I have it as
outstanding rather than done, because adding it would change every number on
[`benchmark.md`](../module-05/benchmark.md) and I would rather re-measure the whole
2×2 than bolt a fifth configuration onto the end.

**Four questions for `#sql-questions`** ([`harvest.md`](../module-05/harvest.md) §10),
of which two I would actually like answered:

1. **Why does `ANALYZE` not talk SQLite out of `ix_report_machine`?** After
   statistics the planner knows the index holds 4,000 rows per `machine_id`, and
   it still walks it for a query with no `machine_id` predicate, where a plain
   scan is 1.45× faster. Is the avoided sort being over-valued, or is the
   `GROUP BY`-ordering benefit simply not costed?
2. **How should price history be modelled here?** `part_no → part_price` assumes a
   part has one price forever. The moment a supplier renegotiates, every
   historical cost on this dashboard is silently restated at today's price — in
   **both** designs. That is a correctness bug worth more than the 5% the whole
   module is arguing about, and the obvious fix
   (`part_price(part_no, valid_from, price)`) seems to put the price of a given
   job in two places at once, which is what 3NF is supposed to prevent. This is
   the same shape as Module 2's "requirements the schema forgot", and I would like
   to know whether temporal data is a genuine exception to one-fact-one-place or
   whether I am modelling it wrong.

**A process note, not a complaint.** The exchanges are the only synchronisation in
this format and I have none of them. My side of all seven is written, but they
need the other pod in the room, and this is now the fourth module in a row with
the same gap (Module 2 §7, Module 3 Task C, Module 4 Task B). The rounds format
makes it more visible than the pod study did, because each round ends in one. If
the exchanges are where the assessment-for-feedback happens, I have been doing a
different course.

## Interaction with peers and instructors

None this block beyond the written preparation. See the note above.

## Help and extra work

Used an LLM for Round 1's FD diff as the module directs, and the disagreement was
worth having: it promoted `machine_id → technician` from three rows into a
dependency (my call, and I was right), and it stated `part_no → part_price` as a
flat domain fact without the price-history caveat — where it was mostly right and
stopped one question short, which is how I found the modelling gap that is now
question 2 above.

Extra work beyond the rounds: the `ANALYZE` phases and the 2×2 matrix (not asked
for), the third counter-demo with a high-cardinality dimension (not asked for, and
inconclusive), the storage re-accounting with indexes included, and measuring all
three staleness strategies rather than just naming one in the memo — the full
rebuild at 172 ms is what made the recommendation defensible instead of a
preference.
