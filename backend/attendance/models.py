"""Attendance ORM models: ShiftPolicy, WeeklyOffPolicy, EmployeeShiftAssignment,
HolidayCalendar, Holiday, AttendanceRecord, ClockEntry, AttendanceRegularization."""

from __future__ import annotations

import uuid
from datetime import date, datetime, time, timezone
from typing import Optional

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.common.constants import (
    ArrivalStatus,
    AttendanceStatus,
    RegularizationStatus,
)
from backend.database import Base


class ShiftPolicy(Base):
    __tablename__ = "shift_policies"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    name: Mapped[str] = mapped_column(sa.String(100), unique=True, nullable=False)
    start_time: Mapped[time] = mapped_column(sa.Time, nullable=False)
    end_time: Mapped[time] = mapped_column(sa.Time, nullable=False)
    grace_minutes: Mapped[int] = mapped_column(
        sa.Integer, default=15
    )
    half_day_minutes: Mapped[int] = mapped_column(
        sa.Integer, default=240
    )
    full_day_minutes: Mapped[int] = mapped_column(
        sa.Integer, default=480
    )
    is_night_shift: Mapped[bool] = mapped_column(
        sa.Boolean, default=False
    )
    is_active: Mapped[bool] = mapped_column(sa.Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    shift_assignments: Mapped[list[EmployeeShiftAssignment]] = relationship(
        back_populates="shift_policy"
    )
    attendance_records: Mapped[list[AttendanceRecord]] = relationship(
        back_populates="shift_policy"
    )


class WeeklyOffPolicy(Base):
    __tablename__ = "weekly_off_policies"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    name: Mapped[str] = mapped_column(sa.String(100), unique=True, nullable=False)
    days: Mapped[dict] = mapped_column(JSONB, nullable=False)
    is_active: Mapped[bool] = mapped_column(sa.Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    shift_assignments: Mapped[list[EmployeeShiftAssignment]] = relationship(
        back_populates="weekly_off_policy"
    )


class EmployeeShiftAssignment(Base):
    __tablename__ = "employee_shift_assignments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False,
    )
    shift_policy_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("shift_policies.id"), nullable=False
    )
    weekly_off_policy_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("weekly_off_policies.id"), nullable=False
    )
    effective_from: Mapped[date] = mapped_column(sa.Date, nullable=False)
    effective_to: Mapped[Optional[date]] = mapped_column(sa.Date)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    employee: Mapped["backend.core_hr.models.Employee"] = relationship(
        back_populates="shift_assignments"
    )
    shift_policy: Mapped[ShiftPolicy] = relationship(
        back_populates="shift_assignments"
    )
    weekly_off_policy: Mapped[WeeklyOffPolicy] = relationship(
        back_populates="shift_assignments"
    )


class HolidayCalendar(Base):
    __tablename__ = "holiday_calendars"
    __table_args__ = (
        sa.UniqueConstraint(
            "name", "year", "location_id", name="uq_holiday_cal_name_year_loc"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    name: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    year: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    location_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("locations.id")
    )
    is_active: Mapped[bool] = mapped_column(sa.Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    location: Mapped[Optional["backend.core_hr.models.Location"]] = relationship()
    holidays: Mapped[list[Holiday]] = relationship(
        back_populates="calendar", cascade="all, delete-orphan"
    )


class Holiday(Base):
    __tablename__ = "holidays"
    __table_args__ = (
        sa.UniqueConstraint("calendar_id", "date", name="uq_holiday_cal_date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    calendar_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("holiday_calendars.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(sa.String(150), nullable=False)
    date: Mapped[date] = mapped_column(sa.Date, nullable=False)
    is_optional: Mapped[bool] = mapped_column(
        sa.Boolean, default=False
    )
    is_restricted: Mapped[bool] = mapped_column(
        sa.Boolean, default=False
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    calendar: Mapped[HolidayCalendar] = relationship(back_populates="holidays")


class AttendanceRecord(Base):
    __tablename__ = "attendance_records"
    __table_args__ = (
        sa.UniqueConstraint("employee_id", "date", name="uq_attendance_emp_date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("employees.id"), nullable=False
    )
    date: Mapped[date] = mapped_column(sa.Date, nullable=False)
    status: Mapped[AttendanceStatus] = mapped_column(
        sa.Enum(AttendanceStatus, name="attendance_status", create_type=False),
        nullable=False,
        default="absent",
    )
    arrival_status: Mapped[Optional[ArrivalStatus]] = mapped_column(
        sa.Enum(ArrivalStatus, name="arrival_status", create_type=False)
    )
    shift_policy_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("shift_policies.id")
    )
    first_clock_in: Mapped[Optional[datetime]] = mapped_column(
        sa.DateTime(timezone=True)
    )
    last_clock_out: Mapped[Optional[datetime]] = mapped_column(
        sa.DateTime(timezone=True)
    )
    total_work_minutes: Mapped[Optional[int]] = mapped_column(sa.Integer)
    effective_work_minutes: Mapped[Optional[int]] = mapped_column(sa.Integer)
    overtime_minutes: Mapped[int] = mapped_column(
        sa.Integer, default=0
    )
    is_regularized: Mapped[bool] = mapped_column(
        sa.Boolean, default=False
    )
    source: Mapped[str] = mapped_column(sa.String(50), default="system")
    remarks: Mapped[Optional[str]] = mapped_column(sa.Text)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    employee: Mapped["backend.core_hr.models.Employee"] = relationship()
    shift_policy: Mapped[Optional[ShiftPolicy]] = relationship(
        back_populates="attendance_records"
    )
    clock_entries: Mapped[list[ClockEntry]] = relationship(
        back_populates="attendance_record", cascade="all, delete-orphan"
    )
    regularizations: Mapped[list[AttendanceRegularization]] = relationship(
        back_populates="attendance_record"
    )


class ClockEntry(Base):
    __tablename__ = "clock_entries"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("employees.id"), nullable=False
    )
    attendance_record_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("attendance_records.id", ondelete="CASCADE"),
    )
    clock_in: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False
    )
    clock_out: Mapped[Optional[datetime]] = mapped_column(
        sa.DateTime(timezone=True)
    )
    duration_minutes: Mapped[Optional[int]] = mapped_column(sa.Integer)
    source: Mapped[str] = mapped_column(sa.String(50), default="biometric")
    ip_address: Mapped[Optional[str]] = mapped_column(INET)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    employee: Mapped["backend.core_hr.models.Employee"] = relationship()
    attendance_record: Mapped[Optional[AttendanceRecord]] = relationship(
        back_populates="clock_entries"
    )


class AttendanceRegularization(Base):
    __tablename__ = "attendance_regularizations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    attendance_record_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("attendance_records.id"),
        nullable=False,
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("employees.id"), nullable=False
    )
    requested_status: Mapped[AttendanceStatus] = mapped_column(
        sa.Enum(AttendanceStatus, name="attendance_status", create_type=False),
        nullable=False,
    )
    reason: Mapped[str] = mapped_column(sa.Text, nullable=False)
    status: Mapped[RegularizationStatus] = mapped_column(
        sa.Enum(
            RegularizationStatus, name="regularization_status", create_type=False
        ),
        default="pending",
    )
    reviewed_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("employees.id")
    )
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(
        sa.DateTime(timezone=True)
    )
    reviewer_remarks: Mapped[Optional[str]] = mapped_column(sa.Text)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    attendance_record: Mapped[AttendanceRecord] = relationship(
        back_populates="regularizations"
    )
    employee: Mapped["backend.core_hr.models.Employee"] = relationship(
        foreign_keys=[employee_id]
    )
    reviewer: Mapped[Optional["backend.core_hr.models.Employee"]] = relationship(
        foreign_keys=[reviewed_by]
    )
