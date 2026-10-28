# Module 1 — Reflection

[← Module 1](./README.md) · [Portfolio home](../README.md)

Logbook entry for this teaching block, answering the four questions from the
[syllabus](https://github.com/iotempire/iotempire-teaching/blob/main/full-classes/hsbi-databases-10d/syllabus.md#reflection-format).

---

## 1. What worked?

The telemetry pipeline worked end to end: generate the readings, load them into
SQLite with bound parameters, and query them. 172,800 rows across three machines,
and the three queries came back in 54 ms, 44 ms and 6 ms, on a laptop, with no
server running and nothing crossing a network.

[`run-shell-tour.sh`](./run-shell-tour.sh) also worked, and it is the piece I am most
pleased with, because it makes the shell tour reproducible rather than a transcript I
happened to capture once. Anyone can run it and get the same `shell-tour.txt`.

## 2. What broke?

Two things, and both were my own.

I ran `uv init` in my home directory instead of the repository. That scattered project
files where they did not belong and had to be cleaned up and redone properly. It was
not a subtle mistake, I had simply not checked which directory I was in before
running a command that creates things.

I also renamed `README.md` to `LyonsPortfolio.md` early on (I thought it was customizable), 
which quietly broke the repository's front page: GitHub shows `README.md` on the folder 
view, and with no file by that name there was nothing to show. My commit history still 
has the rename and the rename-back in it.

The subtler failure was in Task 4. The obvious way to capture the shell tour is to
turn on `.timer` and redirect the session with `.output`. But `.timer` prints its
"Run Time:" line to the shell's own stdout, not into the file `.output` opened. So the
capture succeeds, the file looks complete, and the timing data, the entire point of
the exercise, is silently missing. Piping the whole session through `tee` catches it.
That one stuck with me because nothing failed; the output was just quietly incomplete.

## 3. How did my mental model shift?

I came into this module wanting to know whether "you don't need a server" survives
contact with a dataset bigger than a toy, because my first real project was a
production line simulator whose data lived in memory and vanished when the game
closed.

The measurement answered it more bluntly than I expected. 172,800 rows, queried in
tens of milliseconds, with no daemon, no port, no connection string, and no network
hop. I had assumed a "real" database meant a server, and that SQLite was the thing you
used before you were serious. What actually distinguishes them is where the database
engine runs — in my process, or in someone else's — and for a local application there
is no reason to pay for the second one.

The other shift was smaller but more practical: a tool can succeed and still not do
what you asked. `.timer` with `.output` taught me that before any query did.

## 4. How did I verify AI suggestions?

Frankly less than I should have in this module. Task 7, the LLM SQL profiling task,
is still outstanding, and that is the task built specifically for this question.

What I did do: when I was told that `.output` silently drops `.timer` output, I did
not take it on trust — I ran the capture both ways and compared the files. The timing
line is present with `tee` and absent with `.output`, and that is why
[`run-shell-tour.sh`](./run-shell-tour.sh) is written the way it is, with the reason
recorded in its header comment rather than just the fix.

I also checked reproducibility rather than assuming it: my generated telemetry and
query results matched the reference run exactly, which is weaker than verifying a
claim but at least confirms the pipeline is deterministic.

Carrying into Module 2: do Task 7 properly, and treat a fluent answer as a claim to
test rather than a result.
