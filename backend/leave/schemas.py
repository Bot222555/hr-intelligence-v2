"""Leave Pydantic v2 schemas — request / response validation.

Naming conventions:
  - *Create / *Request  → request bodies (write)
  - *Response / *Out    → response bodies (read)
  - *Brief              → compact embedded representations
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.common.constants import LeaveDayType, LeaveStatus


# ═════════════════════════════════════════════════════════════════════
# Embedded / shared
# ═════════════════════════════════════════════════════════════════════


class EmployeeBrief(BaseModel):
    """Minimal employee info embedded in leave responses."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    employee_code: str
    display_name: Optional[str] = None
    designation: Optional[str] = None
    department_name: Optional[str] = None
    profile_photo_url: Optional[str] = None


class LeaveTypeBrief(BaseModel):
    """Minimal leave type info embedded in leave responses."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    name: str
    is_paid: bool = True


# ═════════════════════════════════════════════════════════════════════
# Leave Type
# ═════════════════════════════════════════════════════════════════════


class LeaveTypeOut(BaseModel):
    """Full leave type representation."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    name: str
    description: Optional[str] = None
    default_balance: Decimal
    max_carry_forward: Decimal
    is_paid: bool = True
    requires_approval: bool = True
    min_days_notice: int = 0
    max_consecutive_days: Optional[int] = None
    is_active: bool = True
    applicable_gender: Optional[str] = None
    created_at: datetime
    updated_at: datetime


# ═════════════════════════════════════════════════════════════════════
# Leave Balance
# ═════════════════════════════════════════════════════════════════════


class LeaveBalanceOut(BaseModel):
    """Balance for a single leave type with computed available field."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    employee_id: uuid.UUID
    leave_type_id: uuid.UUID
    year: int
    opening_balance: Decimal
    accrued: Decimal
    used: Decimal
    carry_forwarded: Decimal
    adjusted: Decimal
    current_balance: Decimal

    # Computed fields — filled by service, not from ORM
    pending: Decimal = Decimal("0")
    available: Decimal = Decimal("0")

    leave_type: Optional[LeaveTypeBrief] = None


# ═════════════════════════════════════════════════════════════════════
# Leave Request — Create
# ═════════════════════════════════════════════════════════════════════


class LeaveRequestCreate(BaseModel):
    """Payload for applying a leave request."""

    leave_type_id: uuid.UUID
    from_date: date = Field(..., description="Leave start date (inclusive)")
    to_date: date = Field(..., description="Leave end date (inclusive)")
    reason: Optional[str] = Field(
        None, min_length=5, max_length=1000, description="Reason for leave"
    )
    day_details: Optional[dict[str, LeaveDayType]] = Field(
        default=None,
        description=(
            "Per-day detail: date string (YYYY-MM-DD) → full_day | first_half | second_half. "
            "Dates not listed default to full_day."
        ),
    )

    @model_validator(mode="after")
    def validate_dates(self) -> "LeaveRequestCreate":
        if self.from_date > self.to_date:
            raise ValueError("from_date must be on or before to_date.")
        if (self.to_date - self.from_date).days > 365:
            raise ValueError("Leave request cannot span more than 365 days.")
        return self


# ═════════════════════════════════════════════════════════════════════
# Leave Request — Response
# ═════════════════════════════════════════════════════════════════════


class LeaveRequestOut(BaseModel):
    """Full leave request response."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    employee_id: uuid.UUID
    leave_type_id: uuid.UUID
    start_date: date
    end_date: date
    day_details: dict
    total_days: Decimal
    reason: Optional[str] = None
    status: LeaveStatus
    reviewed_by: Optional[uuid.UUID] = None
    reviewed_at: Optional[datetime] = None
    reviewer_remarks: Optional[str] = None
    cancelled_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    # Enriched by service
    employee: Optional[EmployeeBrief] = None
    leave_type: Optional[LeaveTypeBrief] = None
    reviewer: Optional[EmployeeBrief] = None


# ═════════════════════════════════════════════════════════════════════
# Leave Approve / Reject / Cancel
# ═════════════════════════════════════════════════════════════════════


class LeaveApproveRequest(BaseModel):
    """Payload for approving a leave request."""

    remarks: Optional[str] = Field(None, max_length=500)


class LeaveRejectRequest(BaseModel):
    """Payload for rejecting a leave request."""

    reason: str = Field(..., min_length=5, max_length=500)


class LeaveCancelRequest(BaseModel):
    """Payload for cancelling a leave request."""

    reason: str = Field(..., min_length=5, max_length=500)


# ═════════════════════════════════════════════════════════════════════
# Comp Off
# ═════════════════════════════════════════════════════════════════════


class CompOffCreate(BaseModel):
    """Payload for requesting compensatory off."""

    work_date: date = Field(..., description="Date the employee worked (weekend/holiday)")
    reason: str = Field(..., min_length=5, max_length=500)

    @field_validator("work_date")
    @classmethod
    def work_date_not_future(cls, v: date) -> date:
        from datetime import date as _date

        if v > _date.today():
            raise ValueError("work_date cannot be in the future.")
        return v


class CompOffOut(BaseModel):
    """Comp-off grant response."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    employee_id: uuid.UUID
    work_date: date
    reason: str
    granted_by: Optional[uuid.UUID] = None
    expires_at: Optional[date] = None
    is_used: bool = False
    leave_request_id: Optional[uuid.UUID] = None
    created_at: datetime

    employee: Optional[EmployeeBrief] = None
    granter: Optional[EmployeeBrief] = None


# ═════════════════════════════════════════════════════════════════════
# Balance Adjustment
# ═════════════════════════════════════════════════════════════════════


class BalanceAdjustRequest(BaseModel):
    """HR admin balance adjustment payload."""

    leave_type_id: uuid.UUID
    adjustment: Decimal = Field(
        ..., description="Positive to credit, negative to debit"
    )
    reason: str = Field(..., min_length=5, max_length=500)
    year: Optional[int] = Field(
        None, description="Target year; defaults to current year"
    )


# ═════════════════════════════════════════════════════════════════════
# Leave Calendar
# ═════════════════════════════════════════════════════════════════════


class LeaveCalendarEntry(BaseModel):
    """Single entry in the team leave calendar."""

    employee: EmployeeBrief
    leave_type: LeaveTypeBrief
    start_date: date
    end_date: date
    total_days: Decimal
    status: LeaveStatus
    day_details: dict


class LeaveCalendarOut(BaseModel):
    """Team leave calendar view for a given month."""

    month: int
    year: int
    entries: list[LeaveCalendarEntry]
    total_entries: int = 0


# ═════════════════════════════════════════════════════════════════════
# Leave Request Filters
# ═════════════════════════════════════════════════════════════════════


class LeaveRequestFilters(BaseModel):
    """Query filters for listing leave requests."""

    employee_id: Optional[uuid.UUID] = None
    status: Optional[LeaveStatus] = None
    leave_type_id: Optional[uuid.UUID] = None
    from_date: Optional[date] = None
    to_date: Optional[date] = None
    scope: str = Field(
        default="my",
        description="my = own requests, team = direct reports, all = everyone (HR admin)",
    )
