-- Module 4 — Data Integrity, Constraints & Edge Triggers
-- Builds Module04/edge.db: the Wittkamp edge-gateway telemetry store.
--
-- Rebuild from the repository root:
--     rm -f module-04/edge.db
--     sqlite3 module-04/edge.db ".read module-04/setup.sql"
--
-- Every table is STRICT, so a declared type is a real constraint and not a
-- suggestion. Foreign keys are enabled PER CONNECTION and are OFF by default,
-- which is the single most important line in this file.

PRAGMA foreign_keys = ON;

DROP TRIGGER IF EXISTS trg_vib_alarm;
DROP TRIGGER IF EXISTS trg_reading_audit;
DROP VIEW  IF EXISTS machine_health;
DROP TABLE IF EXISTS audit;
DROP TABLE IF EXISTS alarm;
DROP TABLE IF EXISTS reading;
DROP TABLE IF EXISTS sensor;

-- ---------------------------------------------------------------- entities --

CREATE TABLE sensor(
    sensor_id   INTEGER PRIMARY KEY,
    machine_id  TEXT    NOT NULL,
    metric      TEXT    NOT NULL CHECK (metric IN ('temp_c','vib_rms','spindle_load')),
    unit        TEXT    NOT NULL,
    UNIQUE (machine_id, metric)          -- one sensor per machine per metric
) STRICT;

CREATE TABLE reading(
    reading_id  INTEGER PRIMARY KEY,
    sensor_id   INTEGER NOT NULL REFERENCES sensor(sensor_id),
    ts          TEXT    NOT NULL,
    value       REAL    NOT NULL,
    interval_s  INTEGER NOT NULL CHECK (interval_s > 0),
    energy_j    REAL    GENERATED ALWAYS AS (value * interval_s) VIRTUAL,
    CHECK (value >= -273.15 AND value <= 5000)   -- physically impossible values
) STRICT;

-- Natural key for the telemetry stream. A gateway replaying its buffer after an
-- outage sends the same (sensor_id, ts) again; this index is what makes that
-- collide instead of duplicating, and is what the UPSERT in Task 2 targets.
CREATE UNIQUE INDEX ux_reading_sensor_ts ON reading(sensor_id, ts);

-- ------------------------------------------------- derived / integrity side --

CREATE TABLE alarm(
    alarm_id  INTEGER PRIMARY KEY,
    sensor_id INTEGER NOT NULL REFERENCES sensor(sensor_id),
    ts        TEXT    NOT NULL,
    value     REAL    NOT NULL,
    reason    TEXT    NOT NULL
) STRICT;

CREATE TABLE audit(
    audit_id   INTEGER PRIMARY KEY,
    reading_id INTEGER NOT NULL,
    old_value  REAL,
    new_value  REAL,
    changed_at TEXT NOT NULL DEFAULT (datetime('now'))
) STRICT;

-- Semantic rule the application cannot forget: vibration over 2.0 mm/s alarms
-- at the moment the row lands.
CREATE TRIGGER trg_vib_alarm
AFTER INSERT ON reading
FOR EACH ROW
WHEN NEW.value > 2.0
     AND (SELECT metric FROM sensor WHERE sensor_id = NEW.sensor_id) = 'vib_rms'
BEGIN
    INSERT INTO alarm(sensor_id, ts, value, reason)
    VALUES (NEW.sensor_id, NEW.ts, NEW.value, 'vibration over 2.0 mm/s');
END;

-- Immutable trail of every corrected value.
CREATE TRIGGER trg_reading_audit
AFTER UPDATE OF value ON reading
FOR EACH ROW
BEGIN
    INSERT INTO audit(reading_id, old_value, new_value)
    VALUES (NEW.reading_id, OLD.value, NEW.value);
END;

-- Task 4: the safe subset handed to report readers instead of a GRANT.
CREATE VIEW machine_health AS
    SELECT s.machine_id, s.metric, MAX(r.value) AS peak, COUNT(*) AS n
    FROM sensor s JOIN reading r USING(sensor_id)
    GROUP BY s.machine_id, s.metric;

-- ------------------------------------------------------------------- seed ---

INSERT INTO sensor VALUES
    (1,'cnc-01','temp_c','degC'),
    (2,'cnc-01','vib_rms','mm/s');
