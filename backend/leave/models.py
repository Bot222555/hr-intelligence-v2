"""Leave ORM models: LeaveType, LeaveBalance, LeaveRequest, CompOffGrant."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.common.constants import GenderType, LeaveStatus
from backend.database import Base


class LeaveType(Base):
    __tablename__ = "leave_types"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    code: Mapped[str] = mapped_column(sa.String(10), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(sa.Text)
    default_balance: Mapped[Decimal] = mapped_column(
        sa.Numeric(5, 1), server_default=sa.text("0")
    )
    max_carry_forward: Mapped[Decimal] = mapped_column(
        sa.Numeric(5, 1), server_default=sa.text("0")
    )
    is_paid: Mapped[bool] = mapped_column(sa.Boolean, server_default=sa.text("TRUE"))
    requires_approval: Mapped[bool] = mapped_column(
        sa.Boolean, server_default=sa.text("TRUE")
    )
    min_days_notice: Mapped[int] = mapped_column(
        sa.Integer, server_default=sa.text("0")
    )
    max_consecutive_days: Mapped[Optional[int]] = mapped_column(sa.Integer)
    is_active: Mapped[bool] = mapped_column(sa.Boolean, server_default=sa.text("TRUE"))
    applicable_gender: Mapped[Optional[GenderType]] = mapped_column(
        sa.Enum(GenderType, name="gender_type", create_type=False)
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )

    # Relationships
    balances: Mapped[list[LeaveBalance]] = relationship(back_populates="leave_type")
    requests: Mapped[list[LeaveRequest]] = relationship(back_populates="leave_type")


class LeaveBalance(Base):
    __tablename__ = "leave_balances"
    __table_args__ = (
        sa.UniqueConstraint(
            "employee_id", "leave_type_id", "year", name="uq_leave_balance"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("employees.id"), nullable=False
    )
    leave_type_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("leave_types.id"), nullable=False
    )
    year: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    opening_balance: Mapped[Decimal] = mapped_column(
        sa.Numeric(5, 1), server_default=sa.text("0")
    )
    accrued: Mapped[Decimal] = mapped_column(
        sa.Numeric(5, 1), server_default=sa.text("0")
    )
    used: Mapped[Decimal] = mapped_column(
        sa.Numeric(5, 1), server_default=sa.text("0")
    )
    carry_forwarded: Mapped[Decimal] = mapped_column(
        sa.Numeric(5, 1), server_default=sa.text("0")
    )
    adjusted: Mapped[Decimal] = mapped_column(
        sa.Numeric(5, 1), server_default=sa.text("0")
    )
    # current_balance is a GENERATED ALWAYS column — read-only in ORM
    current_balance: Mapped[Decimal] = mapped_column(
        sa.Numeric(5, 1),
        sa.Computed("opening_balance + accrued + carry_forwarded + adjusted - used"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )

    # Relationships
    employee: Mapped["backend.core_hr.models.Employee"] = relationship(
        back_populates="leave_balances"
    )
    leave_type: Mapped[LeaveType] = relationship(back_populates="balances")


class LeaveRequest(Base):
    __tablename__ = "leave_requests"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("employees.id"), nullable=False
    )
    leave_type_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("leave_types.id"), nullable=False
    )
    start_date: Mapped[date] = mapped_column(sa.Date, nullable=False)
    end_date: Mapped[date] = mapped_column(sa.Date, nullable=False)
    day_details: Mapped[dict] = mapped_column(JSONB, nullable=False)
    total_days: Mapped[Decimal] = mapped_column(sa.Numeric(5, 1), nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(sa.Text)
    status: Mapped[LeaveStatus] = mapped_column(
        sa.Enum(LeaveStatus, name="leave_status", create_type=False),
        server_default="pending",
    )
    reviewed_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("employees.id")
    )
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(
        sa.DateTime(timezone=True)
    )
    reviewer_remarks: Mapped[Optional[str]] = mapped_column(sa.Text)
    cancelled_at: Mapped[Optional[datetime]] = mapped_column(
        sa.DateTime(timezone=True)
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )

    # Relationships
    employee: Mapped["backend.core_hr.models.Employee"] = relationship(
        back_populates="leave_requests", foreign_keys=[employee_id]
    )
    reviewer: Mapped[Optional["backend.core_hr.models.Employee"]] = relationship(
        foreign_keys=[reviewed_by]
    )
    leave_type: Mapped[LeaveType] = relationship(back_populates="requests")
    comp_off_grants: Mapped[list[CompOffGrant]] = relationship(
        back_populates="leave_request"
    )


class CompOffGrant(Base):
    __tablename__ = "comp_off_grants"
    __table_args__ = (
        sa.UniqueConstraint("employee_id", "work_date", name="uq_comp_off_emp_date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("employees.id"), nullable=False
    )
    work_date: Mapped[date] = mapped_column(sa.Date, nullable=False)
    reason: Mapped[str] = mapped_column(sa.Text, nullable=False)
    granted_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("employees.id")
    )
    expires_at: Mapped[Optional[date]] = mapped_column(sa.Date)
    is_used: Mapped[bool] = mapped_column(sa.Boolean, server_default=sa.text("FALSE"))
    leave_request_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("leave_requests.id")
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )

    # Relationships
    employee: Mapped["backend.core_hr.models.Employee"] = relationship(
        foreign_keys=[employee_id]
    )
    granter: Mapped[Optional["backend.core_hr.models.Employee"]] = relationship(
        foreign_keys=[granted_by]
    )
    leave_request: Mapped[Optional[LeaveRequest]] = relationship(
        back_populates="comp_off_grants"
    )
