# Reflection 4 — Data Integrity, Constraints & Edge Triggers

> Module 4 · Session 4 · [Module 4 portfolio page](../module-04/README.md)

## Take-away — what I want to remember, and my advice

**Every constraint in this module's schema works exactly as documented, and the schema still has
four defects.** Three of them live in the space between two tasks: the UPSERT from Task 2 and the
triggers from Task 3 are each correct on their own page, and wrong together. A replayed reading
takes the `DO UPDATE` branch, which fires the audit trigger (so three identical ingest runs write
2,030 audit rows recording changes that did not happen) and does *not* fire the alarm trigger (so
a reading corrected from 1.5 to 3.4 mm/s crosses the alarm threshold with nobody told).

That is the thing I want to remember, because it is not what I thought the module was about. I
expected to learn which constraint catches which bad row. The real lesson is that **integrity is
a property of the whole write path, not of the `CREATE TABLE` statement** — and that the write
path includes which conflict clause the caller chose, which pragmas the connection set, and which
trigger the engine happened to fire. None of that is visible in the DDL.

The second thing, smaller but more immediately useful: **a rule that lives in the caller is a
rule that will be forgotten.** `PRAGMA foreign_keys` is off by default and per connection, so the
orphan row one connection refuses, the next one accepts. I hit the same shape three more times —
`PRAGMA query_only` can be switched off by whoever switched it on, `ON CONFLICT … WHERE` has to
be remembered at every call site, `INSERT OR IGNORE` is one word away from suppressing a
constraint. Each time, the fix that survives is the one inside the schema. When I had a genuine
choice between fixing the audit bloat at the UPSERT or at the trigger, and measured that both
work identically, I picked the trigger for exactly this reason.

**My advice to someone starting this module:** do Task 2 and Task 3, then go back and run Task
2's ingest script *twice more* with Task 3's triggers in place. Every interesting thing I found
is in that second run. The tasks are written to be done in order and ticked off, and all three
composition defects are invisible if you do that.

## What was good

Writing [`evidence.py`](../module-04/evidence.py) before writing any prose. By the end it was 15
sections and every error message, row count and multiple on my six pages comes out of it, so
"re-check everything after changing the schema" is one command. This is the habit I picked up
from `bench.py` in Module 3 and it paid off faster here — I changed `setup.sql` three times while
writing, and each time I regenerated instead of hand-checking which quotes had gone stale. The
one in Module 3 I built because the module asked for benchmarks. This one I built because I
wanted it.

Deliberately putting bad rows in the test data. [`make-readings.py`](../module-04/make-readings.py)
plants 12 byte-identical replays, 3 corrected retries and 4 rows the schema must refuse, and I
added the conflicting retries expecting them to be boring. They produced the sharpest statement
in the module: UPSERT makes a replay idempotent *only if the file being replayed is internally
consistent*, because under last-write-wins a buffer holding two values for one key gives a
different answer depending on where you stop. I would not have found that with clean test data,
and clean test data is what I would have written a month ago.

## What was difficult, where I struggled

**The trigger benchmark, and not for the reason I expected.** The module asks for a timing with
and without the alarm trigger. I ran it, got a number, and could not say what it meant — the
trigger has a fixed cost (the `WHEN` clause, evaluated on every row) and a variable one (the
alarm insert, only on rows that cross the threshold), and two arms cannot separate them. Five
arms at different alarm rates could.

Then the measurement itself turned out to be wrong. Seven repetitions per arm, each arm's
repetitions run back to back, reported as medians: I ran the script twice as a sanity check and
got **+22% and then +31%** for the same headline figure. A third run put the 0%-alarm arm
*faster* than the 1% arm. That is impossible — 100 extra inserts cannot make 10,000 inserts
quicker — and the impossibility is the only reason I noticed, because +22% and +31% are both
perfectly respectable-looking numbers I would have published without a second thought.

Two fixes, and I think both generalise. **Interleave the arms**, so one pass over all five counts
as one repetition; running an arm's repetitions consecutively lets anything that drifts during
the run land on one arm and look like a result. **Estimate with the minimum, not the median**,
because measurement noise here is one-sided — an interruption adds time to a run and nothing ever
makes the work faster than it is, so the fastest observed run is the closest estimate of the real
cost. After both changes the minima held within half a millisecond across every run, while the
medians kept moving the answer by 15 percentage points.

This is Module 3's lesson arriving from a different direction. There it was: write down the plans
that did not change, so you can tell a real improvement from noise. Here the noise was hiding
*inside* a single number that looked fine.

**The part I would not want to be asked about cold** is why `OR IGNORE` leaves the phantom alarm
behind when the default does not. I can state it — `ABORT` reverts the whole statement including
trigger effects, `OR IGNORE` suppresses the violation so the statement succeeds and the trigger's
insert is never rolled back — and I arrived at it by testing the default first, concluding
`BEFORE` was merely untidy, and only trying `OR IGNORE` because I was looking for a way to make
it misbehave. I would rather have predicted it.

## Good or fun struggling / exploration

**`STRICT` is weaker than its name, and finding that out was the best hour of the module.** The
handout says a `STRICT` table means `'abc'` can never land in a `REAL` column, which is true. I
went looking for the plausible-but-wrong value that still gets through, expecting to answer with
a shrug about sensor drift, and found that `'41.5'`, `' 41.5 '` and `'4e1'` are all accepted into
a `STRICT` `REAL` column and stored as numbers, with `typeof()` afterwards reporting `real` and
no trace that they arrived as text. `'41.5abc'` is refused.

So the rule is not "no conversions", it is "no *lossy* conversions" — and it runs both ways:
`2.7` into an `INTEGER` column is refused, `2.0` is accepted. What I like about this is that the
rule I was taught is almost right, exactly like the `LIKE 'Bei%'` collation thing in Module 3. It
is conditional on something nobody mentions, and I would have stated it as a flat fact at a
checkpoint. It is also *useful* rather than just a gotcha: it is why
[`ingest.py`](../module-04/ingest.py) works at all without a casting layer, since
`csv.DictReader` hands you strings for everything.

The other one I enjoyed: **`NEW.reading_id` is `-1` in a `BEFORE INSERT` trigger, not `NULL`.** I
had assumed `NULL` and `NULL` would be the honest answer — detectable, propagates through
arithmetic, refused by a `NOT NULL` column. `-1` is a plausible-looking integer that joins to
nothing, so an audit table built on a `BEFORE` trigger would look completely healthy and every
join out of it would return nothing, discovered months later by whoever first asks "which reading
did this change?". Which is the only question that table exists to answer.

**Still not sure about:** WAL mode and read-only readers. A read-only database file in WAL mode
normally needs write access to the `-wal` and `-shm` files, so a reader who cannot write to the
directory cannot read it either. My test read a WAL database fine at mode `444` — but only
because a clean close had checkpointed the WAL away and there was no `-wal` file left. I have not
tested the case an edge device makes likely: a gateway killed mid-write leaving a stranded
`-wal`. The documented options are `immutable=1` or checkpointing before handing the file over,
and `immutable=1` is a promise that the file is not changing, which is false on a live gateway.
Going on the list as an honest "I don't know how both can be true at once".

## Show stoppers — anything to raise with peers or instructors

**Two genuine questions, both of which I would rather ask than guess at:**

1. `PRAGMA foreign_key_check` reports a pre-existing orphan long after the fact, and turning
   `PRAGMA foreign_keys = ON` afterwards does not reject or revisit it — the orphan stays
   forever while new violations are refused. So a database can be permanently inconsistent with
   its own declared foreign keys and still accept writes normally. Is running
   `PRAGMA foreign_key_check` at gateway startup the accepted practice for an embedded database,
   or is there a way to make the constraint retroactive that I have not found? The SQLite
   [foreign key documentation](https://sqlite.org/foreignkeys.html) did not settle it for me.
2. The WAL read-only question above.

**Task B is outstanding and I cannot do it alone.** It needs ten minutes with a neighbouring pod.
I have prepared all of it — my answer for the most surprising thing an unconstrained table
accepted (`inf`, which survives `STRICT` and the eye, and poisons every aggregate except `MIN`),
my answer for the hardest constraint to get right (`STRICT` with numbers, because the other two
candidates fail loudly the first time you test them and that one does not fail at all), and
question 1 above to put to them. This is the same gap as Module 2 §7 and Module 3 Task C, and
that is now three sessions running.

**One thing I should flag about my own evidence:** everything in
[`evidence.txt`](../module-04/evidence.txt) was generated on **SQLite 3.53.1**, and I have 3.45.3
installed locally. Both are well past the versions these features need, so I expect the behaviour
to match — but the exact wording of a constraint error is not part of SQLite's compatibility
promise, and Module 3 Task C already taught me that a version difference is the first suspect
when two machines disagree. Re-running `evidence.py` locally either confirms the transcript or
turns up a real difference, and it is on the outstanding list for that reason rather than as a
footnote.

## Interaction with peers and instructors

<!-- One or two sentences. Who did you actually work with this session? Still the
     ad-hoc group from Module 2 (Rayan and Aron), or has a Task Pod been assigned? -->

## Help and extra work

<!-- Factual — these are yours to fill in. One line each is fine, and "nobody, I
     worked alone this session" is a legitimate answer to the first two. -->

- **Who helped me, and was it valuable:**
- **Who I helped, or gave feedback to:**
- **Did I present, implement, make a PR, or fix something crucial for the class:**
