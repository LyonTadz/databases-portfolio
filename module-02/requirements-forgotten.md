# Module 2 — The Requirements the Schema Forgot

[← Module 2](./README.md) · [ER audit](./er-audit.md) · [Portfolio home](../README.md)

Proves **learning goal 5**: *write the requirements the schema forgot — the business rules nobody encoded.*

> **Why this file exists.** The module's suggested-evidence checklist has an entry for every
> learning goal except this one. Goal 5 has no suggested artifact, so working task-by-task
> would skip it. This is the deliberate home for it.

An integrity *defect* (goal 2) is a rule the schema tried to express and got wrong. A forgotten
*requirement* is a rule the schema never attempted at all — it lives only in Anke Reuter's head,
and the database cannot tell you when it is broken.

---

## 1. Rules that are checkable but unenforced

These can be expressed in SQL today. Nothing stops them being violated tomorrow.

### R1 — A job cannot be performed before its machine was installed

Tested against the current data:

```sql
SELECT j.job_id, j.done_on, m.machine_name, m.installed,
       CASE WHEN m.installed GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'
            THEN CASE WHEN j.done_on < m.installed THEN 'VIOLATION' ELSE 'ok' END
            ELSE 'UNCHECKABLE' END AS verdict
FROM maint_job j LEFT JOIN machine m ON j.machine_name = m.machine_name;
```

```
  job_id | done_on    | machine_name | installed  | verdict
  -------+------------+--------------+------------+-------------
  1      | 2026-01-08 | cnc-01       | 2019-03-11 | ok
  2      | 2026-02-14 | cnc-02       | 2019-03-11 | ok
  3      | 2026-02-20 | NULL         | NULL       | UNCHECKABLE
  4      | 2026-03-01 | cnc-01       | 2019-03-11 | ok
```

**Finding — and this is the point of the whole file.** No row violates R1 today, which is
precisely why nobody noticed the rule is unenforced. A rule that happens to hold is
indistinguishable from a rule the database guarantees, right up until the day it isn't.

Note also that job 3 comes back `UNCHECKABLE` — the orphan row from defect 1 means the rule
*cannot even be evaluated* for that job. One unenforced foreign key takes an unrelated business
rule down with it.

### R2 — A job cannot be dated in the future

Nothing in the schema prevents `done_on = '2099-01-01'`. With `done_on` as TEXT, nothing
prevents `'tomorrow'` either.

### R3 — A part's unit price must be positive

Already added as `CHECK (unit_price > 0)` in [`contract.py`](./contract.py). Impossible to
express while the column is TEXT.

### R4 — A machine's serial number must match the house format

Every `serial_no` in the data starts with `SN-`. That is a convention, not a constraint. The
Pydantic validator in `contract.py` enforces it at the application boundary — which raises the
question in §4 of the audit about where enforcement belongs.

### R5 — `site` must be a real site

`'Gütersloh'` and `'Bielefeld'` are free text. A typo (`'Guetersloh'`, `'Gütersloh '`) creates a
third site silently, and any report grouped by site is then wrong. This wants a lookup table, or
at minimum a `CHECK`.

<!-- Add any you find yourself. One per heading, same shape: the rule, and why the
     schema cannot currently express it. -->

## 2. Rules the schema has no vocabulary for

These cannot be written as a constraint at all, because the schema is missing the *concept*. This
is the more serious category — it needs new entities or attributes, not just rules.

### R6 — A decommissioned machine must not accept new jobs

**The schema has no lifecycle state.** There is no `status`, no `decommissioned_on`, no
`active` flag. A machine exists forever from the database's point of view. So this rule cannot
be enforced, cannot be queried, and cannot even be *stated* against the current model.

Anke's original question was *"which parts did we replace on this machine in the last year"* —
a question about a machine still in service. The schema cannot distinguish a running machine
from one sold for scrap in 2014.

### R7 — Quantity of a part used in a job

`parts_used = 'P-1001,P-1002'` can say *which* parts. It cannot say **how many** of each. If a
job replaced three bearings, that fact has nowhere to live — not in the list, not on
`maint_job`, nowhere.

This is why the repaired `job_part` junction in [`contract.py`](./contract.py) carries a
`quantity` column. The m:n relationship has an attribute of its own, and a comma-separated
string is structurally incapable of holding it.

### R8 — A technician must be qualified for the work

Nothing records certifications, and `technician` is not even an entity, so there is nowhere to
attach them. In a plant with safety-critical machinery this is the kind of rule an auditor asks
about.

### R9 — Who entered this row, and when?

No `created_at`, no `created_by`. For warranty claims and audit trails, "when was this recorded"
is different from "when was the work done" — and the schema records neither the former nor any
notion of who is responsible for a row.

<!-- Add any you find. The test for this section: could you write the rule as a
     CHECK constraint today? If not, it belongs here, not in §1. -->

## 3. The requirement behind the whole module

Anke Reuter's question — *"which parts did we replace on this machine in the last year, and how
often?"* — is itself a **requirement the schema forgot to support**. Every defect in the audit is
downstream of nobody having written that question down before designing the tables:

| Her question needs | The schema gives |
|---|---|
| "this machine" — a reliable identity | a TEXT name with no constraint, and one orphan |
| "which parts" — a queryable relationship | a comma-separated string |
| "how often" — a count per part | no quantity anywhere |
| "in the last year" — real dates | TEXT, including the literal value `unknown` |

Four requirements, four failures, one unanswerable question. That is requirements analysis done
backwards from a schema — which is what this module is actually teaching.

## 4. My summary

<!-- Three or four sentences, your words. The useful framing for the checkpoint:
     which of these would you fix first, and why that one? -->
