# **Personal Portfolio for the Databases Class**

Hochschule Bielefeld (HSBI), Campus Gütersloh · Industrial Engineering · Databases class · Winter 2026/27 · Prof. Dr. Ulrich Norbisrath

This repository is my coursework for Databases — Local-First Edition: a local-first, measurement-driven databases course built on SQLite and DuckDB, where the assessed skill is not writing SQL from memory but verifying what an AI wrote.

Everything I build for this class is documented here. Where a pod mate did a task, I link their repository and describe in one sentence what I understood them to have done.

## **Personal Profile & Expectations**

Programming experience and languages: Python only. In my first semester I built a production line simulator game with Pygame — my first real project, and the reason I have any sense of how program state and simulated time fit together. Nothing in any other language yet.

Prior SQL: None. Starting from zero here.

Databases I have used: None directly. The closest thing is a Fandom wiki I built [here](https://shinkais-purpose.fandom.com) — not a database, but it did teach me something about structuring information so other people can find it, and about writing in markup with interlinks rather than prose.

Python: Yes; see above. Comfortable enough to read and modify code, less practised at designing something from scratch.

Command line: Limited.

Git / GitHub: First used it for the Pygame project. I know the basic commit-and-push loop; branching, conflicts and reviewing someone else's history are new territory.

Have I built a web app or run a server? No, neither.

### What I expect from this class

Honestly, I came in without a clear answer to this. My working guess, which I *expect* to revise:

- Build SQL from nothing to useful — not memorising syntax, but getting to the point where I can pull the data I actually want out of a schema I did not design.
- Learn to design a schema that does not corrupt itself — ER modelling and normalisation, so data anomalies are prevented by structure rather than caught by hand later.
- Understand the trade-offs well enough to argue them — relational vs. non-relational, normalised vs. denormalised, embedded vs. server. I want to be able to defend the choice with a measurement, not a preference.
- Come out with a project I can point at. The production line simulator is currently the only thing I have built that I would show anyone; I would like a second.

---

## 🎯 Learning Goals

By the end of this module, I can:
1. Explain how this class works — the CBL/PBL philosophy, the portfolio-based **project work** assessment, and the "moving bar" of a first-time course.
2. Set up my personal GitHub portfolio from the course template, with a clean first commit and a `.gitignore` that keeps databases and secrets out of Git.
3. Set up the entire toolchain reproducibly with **`uv`** — one fixed Python plus SQLite, DuckDB, Datasette, and more — on Windows, macOS, or Linux, and verify it.
4. Explain — with a measurement, not a slide — the difference between an **embedded** database and a **client/server** database, and why most local apps should not run a server.
5. Load real rows into SQLite and query them from Python using **bound parameters**.
6. Take a first LLM-generated query, run it, and begin the habit that defines this course: **verify before I trust**.

---

Author: Lyon Andres Dabu Tadeo

My partner is <replace these pointy brackets with their full name>, [portfolio link](https://github.com/partner/iot-portfolio)

In my team for the final project, I also had the following members:
- <replace these pointy brackets with their full name>, [portfolio link](https://github.com/partner/iot-portfolio)
- <replace these pointy brackets with their full name>, [portfolio link](https://github.com/partner/iot-portfolio)

Our team final project repository is [here](https://github.com/somewhere/final-iot-project)

My personal profile and expectations, you can find [here](Module01/README.md#task-personal-profile).

## Table of Contents

- [Module 1: IoT Introduction](Module01/README.md), 
  [Reflection 1](Reflections/ref01.md)
- [Module 2: Hardware and Basic Electronics](Module02/README.md),
  [Reflection 2](Reflections/ref02.md), [Reflection 3](Reflections/ref03.md)
- ...

## Miscellanious

- [Hardware in my/our possession](Hardware/README.md)
