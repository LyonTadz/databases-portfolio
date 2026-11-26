# Module 4 — Task 4: access control without a server

> Task 4 · [Module 4 portfolio page](./README.md)
>
> Reproduced by [`evidence.py`](./evidence.py) → [`evidence.txt`](./evidence.txt), `[§11]`.
> **SQLite 3.53.1.**

SQLite has no `CREATE ROLE` and no `GRANT`. There is no user to grant anything *to*: the library
runs inside whichever process opened the file, with that process's privileges. So DCL does not
map onto a weaker version of itself — it moves somewhere else entirely, into three mechanisms
that live at different layers and are not interchangeable.

## 1. The view — a safe subset

```sql
CREATE VIEW machine_health AS
    SELECT s.machine_id, s.metric, MAX(r.value) AS peak, COUNT(*) AS n
    FROM sensor s JOIN reading r USING(sensor_id)
    GROUP BY s.machine_id, s.metric;
```

```
machine_health view: [('cnc-01', 'temp_c', 41.5, 1), ('cnc-01', 'vib_rms', 2.4, 1)]
```

The view is created in [`setup.sql`](./setup.sql) while the file is still writable — the module's
note about ordering here is worth heeding, because `chmod 444` first means no `CREATE VIEW`
afterwards.

A plain view is also not writable `[§11]`:

```
REJECTED  INSERT INTO machine_health VALUES ('cnc-09','temp_c',1,1)
          cannot modify machine_health because it is a view
```

## 2. The file — `chmod 444`

```sh
chmod 444 module-04/edge.db
```

Verified as an unprivileged user `[§15]`. This arm needed one extra step: the environment I
generated the evidence in runs as **root**, and root ignores file permissions, so a `DELETE`
there succeeds and proves nothing. [`evidence.py`](./evidence.py) checks `os.geteuid()` and, when
it is 0, re-runs the write from a child process dropped to an unprivileged account:

```
file mode: 444    euid: 0
running as root, which ignores file permissions — dropping privileges to test
(child euid 65534)
SELECT: 1 row(s)
DELETE: OperationalError: attempt to write a readonly database
```

On a normal account it is the two lines the module gives and no fuss. The detour is worth
recording because "I ran `chmod 444` and the write failed" is a conclusion I could have reached
without the permission mattering at all.

Reads work, writes do not. This is the strongest of the three and the only one the holder of the
connection cannot undo — because undoing it requires permission on the *file*, not on the
database.

One caveat I found while testing and have only partly chased down. SQLite's journal and WAL
files live beside the database, so a read-only database file is not automatically a readable
database: in WAL mode a reader normally needs write access to the `-wal` and `-shm` files. My
test read a WAL-mode database fine at mode `444`, but only because the WAL had been checkpointed
away by a clean close and no `-wal` file was present. I have not tested the case where a gateway
is killed mid-write and leaves a stranded `-wal` behind, which is exactly the case an edge
device makes likely. **Open question**, in §5.

## 3. The connection — `mode=ro` and `PRAGMA query_only`

```sh
sqlite3 "file:module-04/edge.db?mode=ro" "SELECT COUNT(*) FROM reading;"
sqlite3 "file:module-04/edge.db?mode=ro" "DELETE FROM reading;"   # must fail
```

```
mode=ro SELECT: 2 rows
REJECTED  DELETE FROM reading
          attempt to write a readonly database
```

`PRAGMA query_only = ON` produces the identical error — and then this `[§11]`:

```
REJECTED  DELETE FROM reading        (query_only = ON)
          attempt to write a readonly database
ok        DELETE FROM reading        (after PRAGMA query_only = OFF)
```

**`PRAGMA query_only` is advisory.** Whoever can set it can unset it, in one statement, on the
same connection. It protects against a mistake inside your own code; it is not a control over
anyone else. `mode=ro` is set when the connection is opened and cannot be changed afterwards, so
it is meaningfully stronger — but it is still chosen by the *caller*, which puts it in the same
category as `PRAGMA foreign_keys` in [`constraints.md`](./constraints.md) §4: a rule the
untrusted party gets to opt into.

## 4. The finding: the view is not a boundary `[§11]`

I had assumed handing someone the view was the SQLite equivalent of granting `SELECT` on it. It
is not, and the difference is the whole answer to the comparison question.

A reader on a `mode=ro` connection — the most restricted reader in this whole exercise — can do
all of this:

```
via the view : [('cnc-01', 'temp_c', 41.5, 1), ('cnc-01', 'vib_rms', 2.4, 1)]
base table   : [(1, 1, 41.5), (2, 2, 2.4)]
alarm table  : 1 rows
whole schema : ['sensor', 'reading', 'alarm', 'audit', 'machine_health']
```

The view aggregated away the individual readings; the reader simply queried `reading` instead.
It also enumerated every table in the file out of `sqlite_master`, including the ones nobody
mentioned to it.

**There is no `GRANT`, so there is nothing to `REVOKE`.** Access in SQLite is all-or-nothing per
*file*: a reader who can open it can read every table, every index, every trigger body and the
full DDL. A view is a convenience for the report writer — fewer joins to get wrong, one
definition of "peak" — and not a restriction on the reader. I had the two confused, and the
confusion is the sort that produces a confident wrong answer about a system's security.

## 5. How this differs with a PostgreSQL server, and when file permissions are enough

On PostgreSQL the control is inside the database and it is per-identity and per-object:

```sql
CREATE ROLE report_reader LOGIN;
REVOKE ALL ON reading FROM report_reader;
GRANT SELECT ON machine_health TO report_reader;
```

Now the view genuinely is a boundary. `report_reader` connects over the network, authenticates
as itself, and gets an error on `SELECT * FROM reading` — the server decides, per statement,
what this identity may see, and can go finer still with column privileges and row-level
security. Crucially the reader never touches the storage: they talk to a process that owns the
files and mediates every request.

**Why file permissions are acceptable at Wittkamp's edge gateway.** Everyone who can open
`edge.db` is already on the box, the box is in the plant, and the data is the plant's own
telemetry. The trust boundary is the gateway itself, and it is enforced by Linux — users,
groups, and the fact that the file is on a machine in a locked room. Access control inside
SQLite would be adding a second, weaker lock inside a door that is already locked. And the
module's premise cuts the same way: fewer knobs, but a far smaller attack surface. There is no
listener, no authentication code, no network-reachable query parser, no `pg_hba.conf` to get
wrong. The two days of data the plant lost were lost to a cloud dependency, not to a missing
`GRANT`.

**Why it is unacceptable for a multi-tenant web app.** Three reasons, in the order they would
hurt:

1. **The tenants are not users of the operating system.** Ten thousand customers cannot be ten
   thousand Unix accounts, and they do not have shell access to be restricted — they arrive
   through one application process, as one OS user, and file permissions cannot distinguish
   between them. The only thing left to enforce "tenant A cannot see tenant B" is application
   code, and application code is where that bug lives.
2. **The granularity is wrong.** File permissions are per file. Multi-tenant isolation is
   per row, sometimes per column. `chmod` has nothing to say about `WHERE tenant_id = ?`, which
   is why PostgreSQL grew row-level security and SQLite has no equivalent.
3. **A compromise is total.** Any SQL injection or path traversal that reaches the file yields
   every table in it — §4 above, as a security property. With a server the same injection is
   still bounded by what that role was granted.

The honest summary: **file-permission access control works when the set of principals is the set
of OS users and the trust boundary is the machine.** The edge gateway satisfies both. A
multi-tenant web app satisfies neither, and a per-tenant SQLite file — which is a real pattern —
only moves the problem to whoever decides which file to open.

### Open question for `#sql-questions`

In WAL mode, what is the accepted way to serve read-only clients from a database file they
cannot write to? The documented options I found are checkpointing and closing cleanly so no
`-wal` remains, or opening with `immutable=1` — but `immutable=1` is a promise that the file is
not changing, which is false on a live gateway, and the documentation warns of undefined
behaviour if you lie. For a gateway that is still ingesting while a report reader queries it, I
do not see how both can be true at once, and this feels like something with a standard answer I
have not found. (§2.)

---

[← Task 3: triggers](./triggers.md) · [Module 4 page](./README.md) · [Task 5: stretcher →](./stretcher.md)
