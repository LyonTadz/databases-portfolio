"""Code-first data contract for the repaired maintenance schema.

Module 2, Task 3 — proves learning goal 4.

An ER diagram is documentation; a contract is executable. This file expresses the
*corrected* schema twice: once as the shape the application validates against
(Pydantic), once as the shape the database itself enforces (SQLAlchemy DDL).

Run:  uv run python module-02/contract.py
      uv run python module-02/contract.py > module-02/contract-ddl.sql
      
Which constraints live where, and why
-------------------------------------

Three categories, decided by who needs to be stopped and who can do the stopping.

MODEL ONLY (Pydantic)
    The `SN-` serial number prefix. This is a house convention, not a structural
    truth about the data — Kortmann could buy machines from a supplier who numbers
    them differently, and the rule would have to change. Changing a validator is
    an edit; changing a CHECK constraint is a schema migration against a live
    table. Format rules that may be revised belong at the application boundary.

BOTH LAYERS
    `unit_price > 0`. Pydantic catches it at the point of entry, where the error
    can name the field and the user can fix it immediately. The CHECK constraint
    catches it regardless of what did the writing. The duplication is deliberate:
    one layer is for a good error message, the other is for being certain.

DATABASE ONLY
    Every foreign key, and the composite primary key on `job_part`. These are not
    a choice — the application *cannot* enforce them honestly. To know whether
    machine_id 7 exists, Python would have to query for it, and between that query
    and the INSERT another process can delete the row. Only the database can check
    and commit in one atomic step.

The deciding question is "what else writes to this database?" The answer is always
more than you think: a maintenance script, someone in the sqlite3 shell, a second
application three years from now. Every one of those bypasses the Pydantic models
entirely. `legacy.db` is the proof — job 3 points at a machine `cnc-05` that never
existed, because `machine_name` was a TEXT column and nothing at the database layer
was checking.

Rule of thumb: validate in the model for the user's benefit, constrain in the
database for the data's.

"""
from datetime import date

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import (CheckConstraint, Column, Date, ForeignKey, Integer,
                        MetaData, Numeric, String, Table, UniqueConstraint)

# --- 1. The contract the *application* validates against (Pydantic) ---


class Machine(BaseModel):
    machine_id: int = Field(ge=1)
    serial_no: str = Field(min_length=3)
    site: str
    installed: date                      # a real date, not free text

    @field_validator("serial_no")
    @classmethod
    def serial_has_prefix(cls, v: str) -> str:
        if not v.startswith("SN-"):
            raise ValueError("serial numbers must start with 'SN-'")
        return v


class Technician(BaseModel):
    technician_id: int = Field(ge=1)
    name: str = Field(min_length=1)


class Part(BaseModel):
    part_no: str = Field(min_length=3)
    description: str = Field(min_length=1)
    unit_price: float = Field(gt=0)      # money, and it must be positive


class MaintenanceJob(BaseModel):
    job_id: int
    machine_id: int                      # a foreign key, not a name
    technician_id: int                   # likewise
    done_on: date
    part_nos: list[str] = Field(default_factory=list)   # the m:n list, modeled properly


# --- 2. The contract the *database* enforces (SQLAlchemy DDL) ---

metadata = MetaData()

machine_t = Table(
    "machine", metadata,
    Column("machine_id", Integer, primary_key=True),
    Column("serial_no", String, nullable=False),
    Column("machine_name", String, nullable=False),
    Column("site", String, nullable=False),
    Column("installed", Date, nullable=False),
    UniqueConstraint("serial_no", name="uq_machine_serial"),
)

technician_t = Table(
    "technician", metadata,
    Column("technician_id", Integer, primary_key=True),
    Column("name", String, nullable=False),
)

part_t = Table(
    "part", metadata,
    Column("part_no", String, primary_key=True),          # natural key, now enforced
    Column("description", String, nullable=False),
    Column("unit_price", Numeric(9, 2), nullable=False),   # NUMERIC, not TEXT
    CheckConstraint("unit_price > 0", name="ck_part_price_positive"),
)

maint_job_t = Table(
    "maint_job", metadata,
    Column("job_id", Integer, primary_key=True),
    Column("machine_id", Integer, ForeignKey("machine.machine_id"), nullable=False),
    Column("technician_id", Integer, ForeignKey("technician.technician_id"), nullable=False),
    Column("done_on", Date, nullable=False),
)

# the junction table that repairs the 1NF violation
job_part_t = Table(
    "job_part", metadata,
    Column("job_id", Integer, ForeignKey("maint_job.job_id"), primary_key=True),
    Column("part_no", String, ForeignKey("part.part_no"), primary_key=True),
    Column("quantity", Integer, nullable=False, default=1),
    CheckConstraint("quantity > 0", name="ck_job_part_quantity_positive"),
)


if __name__ == "__main__":
    # Emit the corrected DDL to prove the contract is buildable:
    from sqlalchemy import create_engine
    from sqlalchemy.schema import CreateTable

    engine = create_engine("sqlite://")
    metadata.create_all(engine)
    for t in (machine_t, technician_t, part_t, maint_job_t, job_part_t):
        print(str(CreateTable(t).compile(engine)).strip(), ";\n")
