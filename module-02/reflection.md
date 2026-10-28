# Module 2 — Reflection

[← Module 2](./README.md) · [Portfolio home](../README.md)

Logbook entry for this teaching block, answering the four questions from the
[syllabus](https://github.com/iotempire/iotempire-teaching/blob/main/full-classes/hsbi-databases-10d/syllabus.md#reflection-format).

---

## 1. What worked?

The audit itself worked, and more importantly it is reproducible. Anyone can rebuild `legacy.db` from [`setup-legacy.sql`](./setup-legacy.sql), run [`run-audit.py`](./run-audit.py), and get exactly the numbers I quote in [`er-audit.md`](./er-audit.md). That mattered more to me than getting the answers right, because it means my findings are checkable rather than claimed.

The Task B proof also worked first time. I wrote the schema for my m:n sketch, inserted rows where one part appears in two orders, and the `COUNT` showed many in both directions at once — which a 1:n could never produce. Then both constraints actually fired when I tried to break them: the composite primary key rejected a duplicate `(1, 1)` pair, and the foreign key rejected a work order that did not exist. Seeing a constraint refuse bad data is a different kind of confidence from reading that it would.

## 2. What broke?

My own markdown broke first. I wrote my two sketch images as `[text](file)` instead of `![text](file)` and they rendered as blue hyperlinks rather than diagrams. The whole point of that section is that someone can look at them. One missing character.

I also linked to files I had not committed yet, so `er-audit.md` pointed at `audit-results.txt` and `run-audit.py` for several hours while neither existed in the repo. The file looked finished and was full of dead links.

And my Task B test data was dated 2028 (changed to 2026 now). The schema accepted it without complaint, which violates R2 in my own [`requirements-forgotten.md`](./requirements-forgotten.md), a job cannot be dated in the future. I wrote the rule down and then broke it myself in the next file, which is a reasonable demonstration of why unenforced rules do not hold.

The thing that unsettled me most was not a crash. `SELECT ... WHERE unit_price < '15'` returned one row. The same question asked numerically returned three. No error, no warning. The cheapest part in the catalogue was silently excluded from a query asking for cheap parts, because in text ordering `'9.90'` sorts after `'15'`. The same thing happened with `UNION` versus `UNION ALL`: plain `UNION` decided two of my rows were duplicates and deleted half my proof.

## 3. How did my mental model shift?

Module 1 ran forwards. I generated telemetry and designed a schema to hold it. This module ran backwards: I was handed a schema and had to work out what it was supposed to mean. I expected that to be easier, since the hard design decisions were already made. It was harder, because every decision had to be recovered from evidence instead of chosen.

Two things changed in how I think about constraints. First, I noticed while doing Task B that `UNIQUE` is what *makes* the machine–nameplate relationship 1:1, and its *absence* is what *permits* machine–sensors to be 1:n. The same constraint doing opposite jobs depending on where you put it was not how I had been thinking about it.

Second, I had assumed a primary key just has to be unique. Working through `Machine` and `Part` convinced me it has to be **stable**, because everything else points at it. That is why I ended up choosing differently for the two: `serial_no` is unique but can be re-stamped, so it gets `UNIQUE` and a surrogate takes over identity; `part_no` is unique *and* stable, so it can do both jobs itself.

The broader shift is that I no longer read a query returning rows as a query that worked. The naive join on `parts_used` lost one job, double-counted another, returned three confident rows, and reported success. I now assume a result is wrong until I know why it is right.

## 4. How did I verify AI suggestions?

Three times, with different methods.

Aron (not my pod partner) generated a school-system ER diagram with ChatGPT and shared it. It was well drawn and used Chen notation correctly, so it looked authoritative. I checked each relationship's cardinality against what the entity names implied and found `enrolls in` labelled 1:N when student enrolment is many-to-many. I also found `Person`, `Staff` and `Teacher` modelled as three separate entities with three separate IDs, when Staff and Teacher are roles a Person fills — an inheritance case, not three tables joined by relationships. The diagram being confident and tidy is exactly what made the errors easy to miss.

Second, Claude gave me an ER sketch for a Task B description that included a `site` attribute. The description never mentions a site. Turns out it had been carried over from the `legacy.db` schema we had been working on. I caught it by tracing every attribute in the sketch back to a word in the original sentence, and anything that could not be traced was either my own deliberate invention or contamination. I have used that check on every sketch since.

Third, Claude added a `quantity` column to the junction table that the module's own starter code does not have. Rather than accept or reject it, I worked out what it was for: a comma-separated list can say *which* parts a job used but never *how many*, so the attribute has nowhere to live until the relationship becomes a table. I kept it, but because I could justify it, not because it was suggested.

What I would take into the next module: an AI answer that is fluent is not an AI answer that is checked, and the fluent ones are the dangerous ones. 👀
