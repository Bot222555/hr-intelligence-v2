"""FnF (Full & Final Settlement) ORM models: FnFSettlement.

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


class FnFSettlement(Base):
    """Full & Final settlement record for exited employees."""

    __tablename__ = "fnf_settlements"

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
    employee_number: Mapped[Optional[str]] = mapped_column(sa.String(50))
    termination_type: Mapped[Optional[str]] = mapped_column(sa.String(100))
    last_working_day: Mapped[Optional[date]] = mapped_column(sa.Date)
    no_of_pay_days: Mapped[float] = mapped_column(
        sa.Numeric(8, 2), default=0,
    )
    settlement_status: Mapped[str] = mapped_column(
        sa.String(50), default="pending",
    )
    total_earnings: Mapped[float] = mapped_column(
        sa.Numeric(12, 2), default=0,
    )
    total_deductions: Mapped[float] = mapped_column(
        sa.Numeric(12, 2), default=0,
    )
    net_settlement: Mapped[float] = mapped_column(
        sa.Numeric(12, 2), default=0,
    )
    settlement_details: Mapped[Optional[dict]] = mapped_column(
        JSONB, default=dict,
    )
    processed_at: Mapped[Optional[datetime]] = mapped_column(
        sa.DateTime(timezone=True),
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    employee = relationship("Employee", foreign_keys=[employee_id], lazy="joined")

    def __repr__(self) -> str:
        return (
            f"<FnFSettlement emp={self.employee_number} "
            f"status={self.settlement_status} net=₹{self.net_settlement}>"
        )
