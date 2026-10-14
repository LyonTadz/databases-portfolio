#!/bin/sh
# Module 1, Task 4 — produce shell-tour.txt and tour.sql reproducibly.
#
# `.timer on` prints "Run Time:" to the shell's own stdout, NOT into a file
# opened with `.output` — so the obvious capture loses the timing line.
# Piping the whole session through `tee` catches everything; `.echo on`
# makes the commands appear too, so it reads like a real session.
#
# Run from the repository root:  sh module-01/run-shell-tour.sh

set -e
cd "$(dirname "$0")/.."

rm -f module-01/tour.db module-01/shell-tour.txt module-01/tour.sql

sqlite3 module-01/tour.db <<'SQL'
CREATE TABLE reading(machine TEXT, vib REAL);
INSERT INTO reading VALUES ('cnc-01', 1.2), ('cnc-02', 2.4), ('cnc-01', 0.9);
SQL

{
  echo "### Module 1, Task 4 — sqlite3 shell tour"
  echo "### $(sqlite3 --version)"
  echo
  echo "## tour.db — the throwaway database from the workbook"
  sqlite3 module-01/tour.db <<'SQL' 2>&1
.echo on
.headers on
.mode column
.tables
.schema reading
.timer on
SELECT machine, max(vib) AS peak FROM reading GROUP BY machine;
SQL

  if [ -f module-01/telemetry.db ]; then
    echo
    echo "## telemetry.db (172,800 rows) — a timing that is actually visible"
    sqlite3 module-01/telemetry.db <<'SQL' 2>&1
.echo on
.headers on
.mode column
.timer on
SELECT machine, max(vib_rms) AS peak FROM readings GROUP BY machine;
SQL
  else
    echo
    echo "## (telemetry.db not built yet — re-run this after Task 6"
    echo "##  for a timing above 0.000s)"
  fi
} | tee module-01/shell-tour.txt

sqlite3 module-01/tour.db <<'SQL'
.output module-01/tour.sql
.dump
SQL

echo
echo "wrote module-01/shell-tour.txt and module-01/tour.sql"
