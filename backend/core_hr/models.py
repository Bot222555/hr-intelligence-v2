"""Core HR ORM models: Location, Department, Employee."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING, Optional

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID
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


class Location(Base):
    __tablename__ = "locations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("uuid_generate_v4()"),
    )
    name: Mapped[str] = mapped_column(sa.String(100), unique=True, nullable=False)
    city: Mapped[Optional[str]] = mapped_column(sa.String(100))
    state: Mapped[Optional[str]] = mapped_column(sa.String(100))
    address: Mapped[Optional[str]] = mapped_column(sa.Text)
    timezone: Mapped[str] = mapped_column(
        sa.String(50), server_default="Asia/Kolkata"
    )
    is_active: Mapped[bool] = mapped_column(sa.Boolean, server_default=sa.text("TRUE"))
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("NOW()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("NOW()")
    )

    # Relationships
    departments: Mapped[list[Department]] = relationship(
        back_populates="location", foreign_keys="Department.location_id"
    )
    employees: Mapped[list[Employee]] = relationship(
        back_populates="location", foreign_keys="Employee.location_id"
    )


class Department(Base):
    __tablename__ = "departments"
    __table_args__ = (
        sa.UniqueConstraint("name", "location_id", name="uq_dept_name_location"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("uuid_generate_v4()"),
    )
    name: Mapped[str] = mapped_column(sa.String(150), nullable=False)
    code: Mapped[Optional[str]] = mapped_column(sa.String(20), unique=True)
    location_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("locations.id")
    )
    parent_department_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("departments.id")
    )
    head_employee_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("employees.id", name="fk_dept_head")
    )
    is_active: Mapped[bool] = mapped_column(sa.Boolean, server_default=sa.text("TRUE"))
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("NOW()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("NOW()")
    )

    # Relationships
    location: Mapped[Optional[Location]] = relationship(
        back_populates="departments", foreign_keys=[location_id]
    )
    parent_department: Mapped[Optional[Department]] = relationship(
        remote_side=[id], foreign_keys=[parent_department_id]
    )
    head_employee: Mapped[Optional[Employee]] = relationship(
        foreign_keys=[head_employee_id],
    )
    employees: Mapped[list[Employee]] = relationship(
        back_populates="department", foreign_keys="Employee.department_id"
    )


class Employee(Base):
    __tablename__ = "employees"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("uuid_generate_v4()"),
    )
    employee_code: Mapped[str] = mapped_column(
        sa.String(20), unique=True, nullable=False
    )
    first_name: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    email: Mapped[str] = mapped_column(sa.String(255), unique=True, nullable=False)
    phone: Mapped[Optional[str]] = mapped_column(sa.String(20))
    gender: Mapped[Optional[GenderType]] = mapped_column(
        sa.Enum(GenderType, name="gender_type", create_type=False)
    )
    date_of_birth: Mapped[Optional[date]] = mapped_column(sa.Date)
    blood_group: Mapped[Optional[BloodGroupType]] = mapped_column(
        sa.Enum(BloodGroupType, name="blood_group_type", create_type=False)
    )
    marital_status: Mapped[Optional[MaritalStatus]] = mapped_column(
        sa.Enum(MaritalStatus, name="marital_status", create_type=False)
    )
    nationality: Mapped[str] = mapped_column(
        sa.String(50), server_default="Indian"
    )
    current_address: Mapped[Optional[dict]] = mapped_column(JSONB)
    permanent_address: Mapped[Optional[dict]] = mapped_column(JSONB)
    emergency_contact: Mapped[Optional[dict]] = mapped_column(JSONB)
    department_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("departments.id")
    )
    location_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("locations.id")
    )
    designation: Mapped[Optional[str]] = mapped_column(sa.String(150))
    reporting_manager_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("employees.id")
    )
    employment_status: Mapped[EmploymentStatus] = mapped_column(
        sa.Enum(EmploymentStatus, name="employment_status", create_type=False),
        server_default="active",
    )
    date_of_joining: Mapped[date] = mapped_column(sa.Date, nullable=False)
    date_of_confirmation: Mapped[Optional[date]] = mapped_column(sa.Date)
    date_of_exit: Mapped[Optional[date]] = mapped_column(sa.Date)
    probation_end_date: Mapped[Optional[date]] = mapped_column(sa.Date)
    notice_period_days: Mapped[int] = mapped_column(
        sa.Integer, server_default=sa.text("90")
    )
    profile_photo_url: Mapped[Optional[str]] = mapped_column(sa.Text)
    google_id: Mapped[Optional[str]] = mapped_column(sa.String(255), unique=True)
    is_active: Mapped[bool] = mapped_column(sa.Boolean, server_default=sa.text("TRUE"))
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("NOW()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("NOW()")
    )

    # Relationships
    department: Mapped[Optional[Department]] = relationship(
        back_populates="employees", foreign_keys=[department_id]
    )
    location: Mapped[Optional[Location]] = relationship(
        back_populates="employees", foreign_keys=[location_id]
    )
    reporting_manager: Mapped[Optional[Employee]] = relationship(
        remote_side=[id], foreign_keys=[reporting_manager_id]
    )
    sessions: Mapped[list[UserSession]] = relationship(back_populates="employee")
    role_assignments: Mapped[list[RoleAssignment]] = relationship(
        back_populates="employee",
        foreign_keys="RoleAssignment.employee_id",
    )
    leave_balances: Mapped[list[LeaveBalance]] = relationship(
        back_populates="employee"
    )
    leave_requests: Mapped[list[LeaveRequest]] = relationship(
        back_populates="employee",
        foreign_keys="LeaveRequest.employee_id",
    )
    shift_assignments: Mapped[list[EmployeeShiftAssignment]] = relationship(
        back_populates="employee"
    )
    notifications: Mapped[list[Notification]] = relationship(
        back_populates="recipient"
    )
