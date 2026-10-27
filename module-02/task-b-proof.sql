PRAGMA foreign_keys = ON;

CREATE TABLE work_order (
    work_order_id INTEGER PRIMARY KEY,
    date_raised   TEXT NOT NULL
);

CREATE TABLE part (
    part_id     INTEGER PRIMARY KEY,
    description TEXT NOT NULL
);

CREATE TABLE work_order_part (
    work_order_id INTEGER NOT NULL REFERENCES work_order(work_order_id),
    part_id       INTEGER NOT NULL REFERENCES part(part_id),
    PRIMARY KEY (work_order_id, part_id)
);
