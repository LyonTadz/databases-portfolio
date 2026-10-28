# Module 2 — Data Contracts & Reading Legacy Schemas (ERD Audits)

[← Portfolio home](../README.md) · [Module 1](../module-01/README.md) · [Course module](https://github.com/iotempire/iotempire-teaching/blob/main/full-classes/hsbi-databases-10d/modules/02-data-contracts-and-legacy-schemas.md) · [Syllabus](https://github.com/iotempire/iotempire-teaching/blob/main/full-classes/hsbi-databases-10d/syllabus.md)

**Session 2.** Conceptual data modeling and requirements analysis — approached the way engineers actually meet them: you inherit a schema that already exists and have to reconstruct what it *means*.

## 🎯 Learning Goals

By the end of this module, I can:

1. Reconstruct an **ER/EER model** — entities, attributes, keys, relationships, cardinalities — from an undocumented SQL schema.
2. Identify **integrity defects** — missing foreign keys, orphan rows, redundant data, normalization violations — with queries, not intuition.
3. Distinguish an **entity relationship** from an attribute, and a **surrogate key** from a natural key, and justify the choice.
4. Express a schema as a **code-first data contract** (Pydantic / SQLAlchemy) that an application can enforce.
5. Write the **requirements the schema forgot** — the business rules nobody encoded.

## What I plan to explore

While Module 1 involved designing a schema from scratch for my own telemetry, this module goes in reverse: figuring out the meaning behind a pre-built schema from someone else. My simulator lost data because it lacked persistence, whereas Kortmann’s plant has the opposite issue—15 years of maintenance history trapped in a format nobody can query. Ultimately, I want to find out whether I would have caught these schema defects on my own, or if it takes dealing with someone else's mess to spot them.

## The scenario

A plastics injection-molding plant runs a maintenance tool built in 2011. It works, so nobody touched it — until a simple question (*"which parts did we replace on this machine last year, and how often?"*) took a specialist an afternoon to answer. The schema is TEXT columns with no relationships: a job points at a machine by *name*, prices are stored as text, and the parts used in a job live in one comma-separated string.

My job is to audit it, reconstruct the ER model it should have had, prove the defects with queries, and write a contract the next application can rely on.

## Contents

| File | What it holds |
|---|---|
| [`study-log.md`](./study-log.md) | Task A/B/C — references, searches, findings, LLM Q&A with verification, ER sketches, pod agreement |
| [`setup-legacy.sql`](./setup-legacy.sql) | The flawed schema + seed rows, so a reviewer can rebuild `legacy.db` |
| [`er-audit.md`](./er-audit.md) | Task 1 — entity list, reconstructed ER diagram, cardinalities proven by counts |
| [`contract.py`](./contract.py) | Task 3 — Pydantic + SQLAlchemy data contract and the corrected DDL |
| [`reflection.md`](./reflection.md) | Logbook entry for this block |
| `img/` | Sketches and diagram screenshots |

## Rebuilding the database

`legacy.db` is **not** committed — it is generated, and `.gitignore` keeps `*.db` out of the repo. Rebuild it from the script:

```sh
sqlite3 module-02/legacy.db < module-02/setup-legacy.sql
```

Check it loaded:

```sh
sqlite3 module-02/legacy.db "SELECT COUNT(*) FROM machine; SELECT COUNT(*) FROM part; SELECT COUNT(*) FROM maint_job;"
```

Four rows in each — including, deliberately, one duplicate part and one job referencing a machine that does not exist.

## Status

**Done**

- [x] Task A — pod study → [`study-log.md`](./study-log.md) §1–§5
- [x] Task B — four sketches from written descriptions + `CREATE TABLE`/`COUNT` proof → [`study-log.md`](./study-log.md) §6, [`task-b-proof.sql`](./task-b-proof.sql)
- [x] Task C — pod-pair exchange → [`study-log.md`](./study-log.md) §7 (neighbouring pod's names still to add)
- [x] Task 1 — reconstruct the ER model → [`er-audit.md`](./er-audit.md) §1–§4
- [x] Task 2 — five integrity defects proven with queries → [`er-audit.md`](./er-audit.md) §5

**Outstanding**

- [ ] Task 3 — contract built and emitting DDL; model-vs-database note outstanding
- [ ] Goal 5 — [`requirements-forgotten.md`](./requirements-forgotten.md) written; summary outstanding
- [ ] `reflection.md` — logbook entry for this block

---

[← Module 1](../module-01/README.md) · [Portfolio home](../README.md)
