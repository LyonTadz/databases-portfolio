PRAGMA foreign_keys = ON;

-- SQLite lets you write foreign key rules, but it ignores them by default and won't stop bad data. This command turns that protection on, but you have to run it every single time you connect to the database.

CREATE TABLE work_order (
    work_order_id INTEGER PRIMARY KEY,
    date_raised   TEXT NOT NULL
);

-- This sets up an empty table named work_order with two columns: work_order_id - A whole number that gives each row a unique ID, ensuring no two rows share the same number. And date_raised: A text column for the date, where `NOT NULL` means you are required to fill it out and cannot leave it blank.

CREATE TABLE part (
    part_id     INTEGER PRIMARY KEY,
    description TEXT NOT NULL
);

-- Same idea, for parts.

CREATE TABLE work_order_part (
    work_order_id INTEGER NOT NULL REFERENCES work_order(work_order_id),
    part_id       INTEGER NOT NULL REFERENCES part(part_id),
    PRIMARY KEY (work_order_id, part_id)
);

-- Here is the junction table: Foreign Key (REFERENCES) - Ensures that any ID you enter must match a real row in the parent table, automatically blocking invalid entries like referencing an order that doesn't exist. Composite Primary Key (PRIMARY KEY): Combines two columns so their pair must be unique, which enforces the rule that a specific part can only be listed once on the same work order while still allowing multiple different parts per order.

-- two work orders
INSERT INTO work_order VALUES (1, '2026-04-17');
INSERT INTO work_order VALUES (2, '2026-04-25');

-- two parts
INSERT INTO part VALUES (1, 'Crank');
INSERT INTO part VALUES (2, 'Bracket 3009');

-- the junction rows: order 1 uses both parts, and part 1 is reused by order 2
INSERT INTO work_order_part VALUES (1, 1);
INSERT INTO work_order_part VALUES (1, 2);
INSERT INTO work_order_part VALUES (2, 1);

-- the COUNT that demonstrates the cardinality in both directions
SELECT 'parts per order' AS direction, work_order_id AS id, COUNT(*) AS n
FROM work_order_part GROUP BY work_order_id
UNION ALL
SELECT 'orders per part', part_id, COUNT(*)
FROM work_order_part GROUP BY part_id;
