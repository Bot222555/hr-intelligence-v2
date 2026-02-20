"""Admin Pydantic schemas — leave types, shift policies, holidays, role assignment."""

from __future__ import annotations

import uuid
from datetime import date, time
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field


# ── Leave Type Schemas ──────────────────────────────────────────────

class LeaveTypeCreate(BaseModel):
    code: str = Field(..., min_length=1, max_length=10)
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    default_balance: Decimal = Field(default=Decimal("0"), ge=0)
    max_carry_forward: Decimal = Field(default=Decimal("0"), ge=0)
    is_paid: bool = True
    requires_approval: bool = True
    min_days_notice: int = Field(default=0, ge=0)
    max_consecutive_days: Optional[int] = Field(default=None, ge=1)
    applicable_gender: Optional[str] = None


class LeaveTypeUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    description: Optional[str] = None
    default_balance: Optional[Decimal] = Field(default=None, ge=0)
    max_carry_forward: Optional[Decimal] = Field(default=None, ge=0)
    is_paid: Optional[bool] = None
    requires_approval: Optional[bool] = None
    min_days_notice: Optional[int] = Field(default=None, ge=0)
    max_consecutive_days: Optional[int] = Field(default=None, ge=1)
    is_active: Optional[bool] = None
    applicable_gender: Optional[str] = None


class LeaveTypeOut(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    description: Optional[str]
    default_balance: Decimal
    max_carry_forward: Decimal
    is_paid: bool
    requires_approval: bool
    min_days_notice: int
    max_consecutive_days: Optional[int]
    is_active: bool
    applicable_gender: Optional[str]

    model_config = {"from_attributes": True}


# ── Shift Policy Schemas ───────────────────────────────────────────

class ShiftPolicyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    start_time: time
    end_time: time
    grace_minutes: int = Field(default=15, ge=0, le=120)
    half_day_minutes: int = Field(default=240, ge=60)
    full_day_minutes: int = Field(default=480, ge=120)
    is_night_shift: bool = False


class ShiftPolicyUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    grace_minutes: Optional[int] = Field(default=None, ge=0, le=120)
    half_day_minutes: Optional[int] = Field(default=None, ge=60)
    full_day_minutes: Optional[int] = Field(default=None, ge=120)
    is_night_shift: Optional[bool] = None
    is_active: Optional[bool] = None


class ShiftPolicyOut(BaseModel):
    id: uuid.UUID
    name: str
    start_time: time
    end_time: time
    grace_minutes: int
    half_day_minutes: int
    full_day_minutes: int
    is_night_shift: bool
    is_active: bool

    model_config = {"from_attributes": True}


# ── Holiday Schemas ─────────────────────────────────────────────────

class HolidayCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=150)
    date: date
    type: str = Field(default="national", pattern="^(national|restricted|optional)$")
    is_active: bool = True


class HolidayUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=150)
    date: Optional[date] = None
    type: Optional[str] = Field(default=None, pattern="^(national|restricted|optional)$")
    is_active: Optional[bool] = None


class HolidayOut(BaseModel):
    id: uuid.UUID
    name: str
    date: date
    type: str  # national / restricted / optional
    is_active: bool
    calendar_id: uuid.UUID

    model_config = {"from_attributes": True}


# ── Role Management Schemas ─────────────────────────────────────────

class EmployeeRoleOut(BaseModel):
    employee_id: uuid.UUID
    employee_number: str
    display_name: str
    email: str
    role: str
    department: Optional[str] = None

    model_config = {"from_attributes": True}


class RoleAssignRequest(BaseModel):
    employee_id: uuid.UUID
    role: str = Field(..., pattern="^(employee|manager|hr_admin|system_admin)$")
