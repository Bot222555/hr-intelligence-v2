"""Expenses ORM models: ExpenseClaim.

SQLAlchemy 2.0 async-compatible models.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Optional

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base


class ExpenseClaim(Base):
    """Employee expense claim / reimbursement request."""

    __tablename__ = "expense_claims"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    keka_id: Mapped[Optional[str]] = mapped_column(
        sa.String(200), unique=True, nullable=True,
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("employees.id"),
        nullable=False,
    )
    employee_name: Mapped[Optional[str]] = mapped_column(sa.String(200))
    claim_number: Mapped[Optional[str]] = mapped_column(sa.String(50))
    title: Mapped[str] = mapped_column(sa.String(500), nullable=False)
    amount: Mapped[float] = mapped_column(
        sa.Numeric(12, 2), nullable=False, default=0,
    )
    currency: Mapped[str] = mapped_column(
        sa.String(10), default="INR",
    )
    payment_status: Mapped[Optional[str]] = mapped_column(sa.String(50))
    approval_status: Mapped[str] = mapped_column(
        sa.String(50), nullable=False, default="pending",
    )
    expenses: Mapped[Optional[list]] = mapped_column(
        JSONB, default=list,
    )
    submitted_date: Mapped[Optional[date]] = mapped_column(sa.Date)
    approved_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("employees.id"), nullable=True,
    )
    approved_at: Mapped[Optional[datetime]] = mapped_column(
        sa.DateTime(timezone=True),
    )
    paid_at: Mapped[Optional[datetime]] = mapped_column(
        sa.DateTime(timezone=True),
    )
    remarks: Mapped[Optional[str]] = mapped_column(sa.Text)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    employee = relationship(
        "Employee", foreign_keys=[employee_id], lazy="joined",
    )
    approved_by = relationship(
        "Employee", foreign_keys=[approved_by_id], lazy="joined",
    )

    def __repr__(self) -> str:
        return f"<ExpenseClaim #{self.claim_number} '{self.title[:30]}' ₹{self.amount}>"
