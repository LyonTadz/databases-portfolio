-- Module 5 — Normalization vs. Denormalization Benchmarking Studio
-- Builds module-05/normalize.db from nothing: the unnormalized 200k-row table,
-- the 3NF decomposition, and the deliberately denormalized reporting table.
--
--   rm -f module-05/normalize.db
--   sqlite3 module-05/normalize.db ".read module-05/setup.sql"
--
-- Every number quoted on the Module 5 pages comes from this file plus
-- evidence.py. Nothing here is random: the data is generated from a CROSS JOIN
-- over two counters, so a reviewer rebuilding it gets the same rows I did.

-- ---------------------------------------------------------------------------
-- 1 · The unnormalized table (Round 3)
-- ---------------------------------------------------------------------------
-- Three defects on purpose:
--   site       — transitive dependency  machine_id -> site   (breaks 3NF)
--   part_price — partial dependency     part_no    -> price  (breaks 2NF)
--   part_price is TEXT, so money is stored as characters     (breaks typing)

DROP TABLE IF EXISTS flat_jobpart;
CREATE TABLE flat_jobpart (
    job_id      INTEGER,
    machine_id  TEXT,
    site        TEXT,           -- transitive dependency machine_id -> site
    technician  TEXT,
    part_no     TEXT,
    part_price  TEXT,           -- partial dependency part_no -> part_price, and TEXT!
    done_on     TEXT
);

-- ~200k rows: 20k jobs x exactly 10 parts
WITH RECURSIVE j(n) AS (SELECT 1 UNION ALL SELECT n+1 FROM j WHERE n < 20000),
               p(k) AS (SELECT 1 UNION ALL SELECT k+1 FROM p WHERE k < 10)
INSERT INTO flat_jobpart
SELECT n,
       'cnc-' || printf('%02d', (n % 50) + 1),
       CASE (n % 50) WHEN 0 THEN 'Bielefeld' ELSE 'Gütersloh' END,
       'tech-' || (n % 7),
       'P-' || printf('%04d', (k % 40) + 1),
       printf('%.2f', 5 + (k % 40)),
       date('2026-01-01', '+' || (n % 90) || ' days')
FROM j CROSS JOIN p;

CREATE INDEX ix_flat_machine ON flat_jobpart(machine_id);

-- ---------------------------------------------------------------------------
-- 2 · The 3NF decomposition (Round 3)
-- ---------------------------------------------------------------------------
-- machine  <- machine_id -> site        (the transitive dependency, stored once)
-- part     <- part_no    -> part_price  (the partial dependency, stored once,
--                                        and CAST to REAL on the way in)
-- job      <- job_id     -> machine, technician, done_on
-- job_part <- the many-to-many that is left once the facts above are extracted

DROP TABLE IF EXISTS job_part;
DROP TABLE IF EXISTS job;
DROP TABLE IF EXISTS part;
DROP TABLE IF EXISTS machine;

CREATE TABLE machine(machine_id TEXT PRIMARY KEY, site TEXT NOT NULL);
CREATE TABLE part(part_no TEXT PRIMARY KEY, part_price REAL NOT NULL);
CREATE TABLE job(job_id INTEGER PRIMARY KEY, machine_id TEXT NOT NULL
                 REFERENCES machine(machine_id), technician TEXT NOT NULL, done_on TEXT NOT NULL);
CREATE TABLE job_part(job_id INTEGER REFERENCES job(job_id),
                      part_no TEXT REFERENCES part(part_no),
                      PRIMARY KEY (job_id, part_no));

INSERT INTO machine SELECT DISTINCT machine_id, site FROM flat_jobpart;
INSERT INTO part    SELECT DISTINCT part_no, CAST(part_price AS REAL) FROM flat_jobpart;
INSERT INTO job     SELECT DISTINCT job_id, machine_id, technician, done_on FROM flat_jobpart;
INSERT INTO job_part SELECT DISTINCT job_id, part_no FROM flat_jobpart;

-- ---------------------------------------------------------------------------
-- 3 · The deliberately denormalized reporting table (Round 4)
-- ---------------------------------------------------------------------------
-- What the operations lead asked for: site, technician and price copied onto
-- every fact row, so the dashboard reads one table.

DROP TABLE IF EXISTS report_jobpart;
CREATE TABLE report_jobpart AS
SELECT j.job_id, m.machine_id, m.site, j.technician, jp.part_no,
       p.part_price, j.done_on
FROM job j
JOIN machine m  ON m.machine_id = j.machine_id
JOIN job_part jp ON jp.job_id = j.job_id
JOIN part p     ON p.part_no = jp.part_no;
CREATE INDEX ix_report_machine ON report_jobpart(machine_id);
