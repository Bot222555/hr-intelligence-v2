"""Core HR ORM models: Location, Department, Employee.

SQLAlchemy 2.0 async-compatible models with Mapped[] annotations.
Column names match the PostgreSQL schema defined in 001_initial_schema;
new columns (keka_id, display_name, etc.) require a follow-up migration.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING, Optional

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.common.constants import (
    BloodGroupType,
    EmploymentStatus,
    GenderType,
    MaritalStatus,
)
from backend.database import Base

if TYPE_CHECKING:
    from backend.attendance.models import EmployeeShiftAssignment
    from backend.auth.models import RoleAssignment, UserSession
    from backend.leave.models import LeaveBalance, LeaveRequest
    from backend.notifications.models import Notification


# ═════════════════════════════════════════════════════════════════════
# Location
# ═════════════════════════════════════════════════════════════════════


class Location(Base):
    """Office location / work-site."""

    __tablename__ = "locations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    name: Mapped[str] = mapped_column(sa.String(100), unique=True, nullable=False)
    address: Mapped[Optional[str]] = mapped_column(sa.Text)
    city: Mapped[Optional[str]] = mapped_column(sa.String(100))
    state: Mapped[Optional[str]] = mapped_column(sa.String(100))
    pincode: Mapped[Optional[str]] = mapped_column(sa.String(10))
    country: Mapped[str] = mapped_column(sa.String(100), server_default="India")
    timezone: Mapped[str] = mapped_column(
        sa.String(50), server_default="Asia/Kolkata",
    )
    is_active: Mapped[bool] = mapped_column(
        sa.Boolean, server_default=sa.text("TRUE"),
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(),
    )

    # ── Relationships ───────────────────────────────────────────────
    departments: Mapped[list[Department]] = relationship(
        back_populates="location", foreign_keys="Department.location_id",
    )
    employees: Mapped[list[Employee]] = relationship(
        back_populates="location", foreign_keys="Employee.location_id",
    )

    def __repr__(self) -> str:
        return f"<Location {self.name!r}>"


# ═════════════════════════════════════════════════════════════════════
# Department
# ═════════════════════════════════════════════════════════════════════


class Department(Base):
    """Organisational department (supports hierarchy via parent_department_id)."""

    __tablename__ = "departments"
    __table_args__ = (
        sa.UniqueConstraint("name", "location_id", name="uq_dept_name_location"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    keka_id: Mapped[Optional[str]] = mapped_column(sa.String(100), unique=True)
    name: Mapped[str] = mapped_column(sa.String(150), nullable=False)
    code: Mapped[Optional[str]] = mapped_column(sa.String(20), unique=True)
    description: Mapped[Optional[str]] = mapped_column(sa.Text)
    parent_department_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("departments.id"),
    )
    head_employee_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("employees.id", name="fk_dept_head"),
    )
    location_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("locations.id"),
    )
    is_active: Mapped[bool] = mapped_column(
        sa.Boolean, server_default=sa.text("TRUE"),
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(),
    )

    # ── Relationships ───────────────────────────────────────────────
    location: Mapped[Optional[Location]] = relationship(
        back_populates="departments", foreign_keys=[location_id],
    )
    parent_department: Mapped[Optional[Department]] = relationship(
        remote_side=[id], foreign_keys=[parent_department_id],
    )
    children: Mapped[list[Department]] = relationship(
        back_populates="parent_department",
        foreign_keys=[parent_department_id],
    )
    head_employee: Mapped[Optional[Employee]] = relationship(
        foreign_keys=[head_employee_id],
    )
    employees: Mapped[list[Employee]] = relationship(
        back_populates="department", foreign_keys="Employee.department_id",
    )

    def __repr__(self) -> str:
        return f"<Department {self.name!r} ({self.code})>"


# ═════════════════════════════════════════════════════════════════════
# Employee
# ═════════════════════════════════════════════════════════════════════


class Employee(Base):
    """Core employee record — central entity for the HR platform."""

    __tablename__ = "employees"

    # ── Primary key ─────────────────────────────────────────────────
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # ── Identifiers ─────────────────────────────────────────────────
    keka_id: Mapped[Optional[str]] = mapped_column(
        sa.String(100), unique=True,
    )
    employee_code: Mapped[str] = mapped_column(
        sa.String(20), unique=True, nullable=False,
    )

    # ── Name ────────────────────────────────────────────────────────
    first_name: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    middle_name: Mapped[Optional[str]] = mapped_column(sa.String(100))
    last_name: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    display_name: Mapped[Optional[str]] = mapped_column(sa.String(255))

    # ── Contact ─────────────────────────────────────────────────────
    email: Mapped[str] = mapped_column(
        sa.String(255), unique=True, nullable=False,
    )
    personal_email: Mapped[Optional[str]] = mapped_column(sa.String(255))
    phone: Mapped[Optional[str]] = mapped_column(sa.String(20))

    # ── Demographics ────────────────────────────────────────────────
    gender: Mapped[Optional[GenderType]] = mapped_column(
        sa.Enum(GenderType, name="gender_type", create_type=False),
    )
    date_of_birth: Mapped[Optional[date]] = mapped_column(sa.Date)
    blood_group: Mapped[Optional[BloodGroupType]] = mapped_column(
        sa.Enum(BloodGroupType, name="blood_group_type", create_type=False),
    )
    marital_status: Mapped[Optional[MaritalStatus]] = mapped_column(
        sa.Enum(MaritalStatus, name="marital_status", create_type=False),
    )
    nationality: Mapped[str] = mapped_column(
        sa.String(50), server_default="Indian",
    )

    # ── Address / Emergency ─────────────────────────────────────────
    current_address: Mapped[Optional[dict]] = mapped_column(JSONB)
    permanent_address: Mapped[Optional[dict]] = mapped_column(JSONB)
    emergency_contact: Mapped[Optional[dict]] = mapped_column(JSONB)

    # ── Org hierarchy ───────────────────────────────────────────────
    department_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("departments.id"),
    )
    location_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("locations.id"),
    )
    job_title: Mapped[Optional[str]] = mapped_column(sa.String(200))
    designation: Mapped[Optional[str]] = mapped_column(sa.String(150))
    reporting_manager_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("employees.id"),
    )
    l2_manager_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("employees.id"),
    )

    # ── Employment lifecycle ────────────────────────────────────────
    employment_status: Mapped[EmploymentStatus] = mapped_column(
        sa.Enum(EmploymentStatus, name="employment_status", create_type=False),
        server_default="active",
    )
    date_of_joining: Mapped[date] = mapped_column(sa.Date, nullable=False)
    date_of_confirmation: Mapped[Optional[date]] = mapped_column(sa.Date)
    probation_end_date: Mapped[Optional[date]] = mapped_column(sa.Date)
    resignation_date: Mapped[Optional[date]] = mapped_column(sa.Date)
    last_working_date: Mapped[Optional[date]] = mapped_column(sa.Date)
    date_of_exit: Mapped[Optional[date]] = mapped_column(sa.Date)
    exit_reason: Mapped[Optional[str]] = mapped_column(sa.Text)
    notice_period_days: Mapped[int] = mapped_column(
        sa.Integer, server_default=sa.text("90"),
    )

    # ── Profile ─────────────────────────────────────────────────────
    profile_photo_url: Mapped[Optional[str]] = mapped_column(sa.Text)
    professional_summary: Mapped[Optional[str]] = mapped_column(sa.Text)

    # ── External IDs ────────────────────────────────────────────────
    google_id: Mapped[Optional[str]] = mapped_column(
        sa.String(255), unique=True,
    )

    # ── Status / Timestamps ─────────────────────────────────────────
    is_active: Mapped[bool] = mapped_column(
        sa.Boolean, server_default=sa.text("TRUE"),
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(),
    )
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("employees.id", name="fk_employee_created_by"),
    )
    updated_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("employees.id", name="fk_employee_updated_by"),
    )

    # ── Relationships ───────────────────────────────────────────────

    # Org hierarchy
    department: Mapped[Optional[Department]] = relationship(
        back_populates="employees", foreign_keys=[department_id],
    )
    location: Mapped[Optional[Location]] = relationship(
        back_populates="employees", foreign_keys=[location_id],
    )
    reporting_manager: Mapped[Optional[Employee]] = relationship(
        remote_side=[id], foreign_keys=[reporting_manager_id],
    )
    direct_reports: Mapped[list[Employee]] = relationship(
        back_populates="reporting_manager",
        foreign_keys=[reporting_manager_id],
    )
    l2_manager: Mapped[Optional[Employee]] = relationship(
        remote_side=[id], foreign_keys=[l2_manager_id],
    )

    # Auth
    sessions: Mapped[list["UserSession"]] = relationship(
        back_populates="employee",
    )
    role_assignments: Mapped[list["RoleAssignment"]] = relationship(
        back_populates="employee",
        foreign_keys="RoleAssignment.employee_id",
    )

    # Leave
    leave_balances: Mapped[list["LeaveBalance"]] = relationship(
        back_populates="employee",
    )
    leave_requests: Mapped[list["LeaveRequest"]] = relationship(
        back_populates="employee",
        foreign_keys="LeaveRequest.employee_id",
    )

    # Attendance
    shift_assignments: Mapped[list["EmployeeShiftAssignment"]] = relationship(
        back_populates="employee",
    )

    # Notifications
    notifications: Mapped[list["Notification"]] = relationship(
        back_populates="recipient",
    )

    # ── Helpers ─────────────────────────────────────────────────────

    @property
    def full_name(self) -> str:
        """Build display name from name parts."""
        parts = [self.first_name, self.middle_name, self.last_name]
        return " ".join(p for p in parts if p)

    def ensure_display_name(self) -> None:
        """Set display_name if not explicitly provided."""
        if not self.display_name:
            self.display_name = f"{self.first_name} {self.last_name}".strip()

    def __repr__(self) -> str:
        return (
            f"<Employee {self.employee_code} "
            f"{self.first_name} {self.last_name}>"
        )
