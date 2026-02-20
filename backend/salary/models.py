"""Salary ORM models: SalaryComponent, Salary.

SQLAlchemy 2.0 async-compatible models.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base


class SalaryComponent(Base):
    """Salary component definition (e.g., Basic, HRA, PF)."""

    __tablename__ = "salary_components"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    keka_id: Mapped[Optional[str]] = mapped_column(
        sa.String(100), unique=True, nullable=True,
    )
    identifier: Mapped[Optional[str]] = mapped_column(sa.String(100))
    title: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    accounting_code: Mapped[Optional[str]] = mapped_column(sa.String(100))
    component_type: Mapped[str] = mapped_column(
        sa.String(50), default="earning",
    )
    is_active: Mapped[bool] = mapped_column(sa.Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc),
    )

    def __repr__(self) -> str:
        return f"<SalaryComponent {self.title!r}>"


class Salary(Base):
    """Employee salary record."""

    __tablename__ = "salaries"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("employees.id"),
        nullable=False,
    )
    ctc: Mapped[float] = mapped_column(
        sa.Numeric(12, 2), default=0,
    )
    gross_pay: Mapped[float] = mapped_column(
        sa.Numeric(12, 2), default=0,
    )
    net_pay: Mapped[float] = mapped_column(
        sa.Numeric(12, 2), default=0,
    )
    earnings: Mapped[Optional[list]] = mapped_column(
        JSONB, default=list,
    )
    deductions: Mapped[Optional[list]] = mapped_column(
        JSONB, default=list,
    )
    contributions: Mapped[Optional[list]] = mapped_column(
        JSONB, default=list,
    )
    variables: Mapped[Optional[list]] = mapped_column(
        JSONB, default=list,
    )
    effective_date: Mapped[Optional[datetime]] = mapped_column(
        sa.Date, nullable=True,
    )
    pay_period: Mapped[Optional[str]] = mapped_column(sa.String(20))
    is_current: Mapped[bool] = mapped_column(sa.Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    employee = relationship("Employee", foreign_keys=[employee_id], lazy="joined")

    __table_args__ = (
        sa.UniqueConstraint("employee_id", "is_current", name="uq_salary_employee_current"),
    )

    def __repr__(self) -> str:
        return f"<Salary employee_id={self.employee_id} ctc={self.ctc}>"
