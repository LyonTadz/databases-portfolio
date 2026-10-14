# Module 1 — Introduction & Local-First Foundations

[← Portfolio home](../README.md) · [Course module](https://github.com/iotempire/iotempire-teaching/blob/main/full-classes/hsbi-databases-10d/modules/01-introduction-and-local-first.md) · [Module index](https://github.com/iotempire/iotempire-teaching/blob/main/full-classes/hsbi-databases-10d/modules/00-index.md) · [Syllabus](https://github.com/iotempire/iotempire-teaching/blob/main/full-classes/hsbi-databases-10d/syllabus.md)

## 🎯 Learning Goals

By the end of this module, I can:

1. Explain how this class works — the CBL/PBL philosophy, the portfolio-based **project work** assessment, and the "moving bar" of a first-time course.
2. Set up my personal GitHub portfolio from the course template, with a clean first commit and a `.gitignore` that keeps databases and secrets out of Git.
3. Set up the entire toolchain reproducibly with **`uv`** — one fixed Python plus SQLite, DuckDB, Datasette, and more — and verify it.
4. Explain — with a measurement, not a slide — the difference between an **embedded** database and a **client/server** database, and why most local apps should not run a server.
5. Load real rows into SQLite and query them from Python using **bound parameters**.
6. Take a first LLM-generated query, run it, and begin the habit that defines this course: **verify before you trust**.

## What I plan to explore

A production line simulator was my first real project, and its data lived in
memory and vanished when the game closed. I want to find out what it would have
taken to persist that properly — and whether the "you don't need a server" claim
survives contact with a dataset bigger than a toy.

## Progress

| Task | Deliverable | Status |
|---|---|:---:|
| 1 | Pod, portfolio repo, this page | ✅ done (pod pending) |
| 2 | Commit history + interlinks | interlinks done, pod link pending |
| 3 | `uv` toolchain + `uv-check.py` output | not started |
| 4 | `shell-tour.txt`, `tour.sql` | not started |
| 5 | `sql-island.md` | not started |
| 6 | `generate_telemetry.py`, `load_telemetry.py`, query results | not started |
| 7 | `llm-sql.md` — prompt, SQL, query plan, verification | not started |
| — | `reflection.md` | not started |

## Task 4 - most useful dot-command

<I found .mode column most useful because the default pipe-separated output (cnc-01|1.2) is unreadable the moment a query returns more than two columns — and it turns out .mode column also switches headers on by itself, so one command does the work I thought needed two.>

## Pod

- Me: [Lyon Andres Dabu Tadeo](../README.md)
- Pod mates: to be confirmed with the instructor
