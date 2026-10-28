"""Code-first data contract for the repaired maintenance schema.

Module 2, Task 3 — proves learning goal 4.

An ER diagram is documentation; a contract is executable. This file expresses the
*corrected* schema twice: once as the shape the application validates against
(Pydantic), once as the shape the database itself enforces (SQLAlchemy DDL).

Run:  uv run python module-02/contract.py
      uv run python module-02/contract.py > module-02/contract-ddl.sql
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
