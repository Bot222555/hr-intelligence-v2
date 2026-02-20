"""Dashboard Pydantic v2 schemas — response models for all dashboard endpoints."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


# ═════════════════════════════════════════════════════════════════════
# GET /summary
# ═════════════════════════════════════════════════════════════════════


class DepartmentBreakdownItem(BaseModel):
    """Employee count for a single department."""

    department_id: uuid.UUID
    department_name: str
    count: int = 0


class DashboardSummaryResponse(BaseModel):
    """Top-level KPI cards for the HR dashboard."""

    total_employees: int = Field(..., description="Active employees count")
    present_today: int = Field(..., description="Employees checked-in today")
    on_leave_today: int = Field(
        ..., description="Employees on approved leave today"
    )
    pending_leave_requests: int = Field(
        ..., description="Leave requests with status=pending"
    )
    department_breakdown: list[DepartmentBreakdownItem] = Field(
        default_factory=list,
        description="Active employee count per department",
    )


# ═════════════════════════════════════════════════════════════════════
# GET /attendance-trend
# ═════════════════════════════════════════════════════════════════════


class AttendanceTrendPoint(BaseModel):
    """Single data point in the attendance trend chart."""

    date: date
    present: int = 0
    absent: int = 0
    on_leave: int = 0
    work_from_home: int = 0
    half_day: int = 0


class AttendanceTrendAverages(BaseModel):
    """Period averages for the attendance trend."""

    avg_present: float = 0.0
    avg_absent: float = 0.0
    avg_on_leave: float = 0.0
    avg_attendance_rate: float = Field(
        0.0, description="Average attendance rate as a percentage"
    )


class AttendanceTrendResponse(BaseModel):
    """Attendance trend over a configurable period (default 30 days)."""

    period_days: int = Field(..., description="Number of days in the trend window")
    start_date: date
    end_date: date
    data: list[AttendanceTrendPoint]
    averages: AttendanceTrendAverages


# ═════════════════════════════════════════════════════════════════════
# GET /leave-summary
# ═════════════════════════════════════════════════════════════════════


class LeaveTypeSummaryItem(BaseModel):
    """Leave count/days for a single leave type in the current month."""

    leave_type_id: uuid.UUID
    leave_type_code: str
    leave_type_name: str
    request_count: int = 0
    total_days: Decimal = Decimal("0")


class LeaveSummaryResponse(BaseModel):
    """Leave breakdown by type for the current month."""

    month: int = Field(..., description="Month number (1-12)")
    year: int
    total_requests: int = 0
    total_days: Decimal = Decimal("0")
    by_type: list[LeaveTypeSummaryItem] = Field(default_factory=list)


# ═════════════════════════════════════════════════════════════════════
# GET /birthdays
# ═════════════════════════════════════════════════════════════════════


class UpcomingBirthdayItem(BaseModel):
    """Employee with an upcoming birthday."""

    model_config = ConfigDict(from_attributes=True)

    employee_id: uuid.UUID
    employee_code: str
    display_name: Optional[str] = None
    department_name: Optional[str] = None
    date_of_birth: date
    birthday_date: date = Field(..., description="The upcoming birthday date this year")
    days_away: int = Field(..., description="Days from today until the birthday")
    profile_photo_url: Optional[str] = None


class UpcomingBirthdaysResponse(BaseModel):
    """Upcoming birthdays in the next N days."""

    days_ahead: int = Field(..., description="Lookahead window in days")
    data: list[UpcomingBirthdayItem]


# ═════════════════════════════════════════════════════════════════════
# GET /new-joiners
# ═════════════════════════════════════════════════════════════════════


class NewJoinerItem(BaseModel):
    """An employee who joined recently."""

    model_config = ConfigDict(from_attributes=True)

    employee_id: uuid.UUID
    employee_code: str
    first_name: str
    last_name: str
    display_name: Optional[str] = None
    department_name: Optional[str] = None
    job_title: Optional[str] = None
    date_of_joining: date
    profile_photo_url: Optional[str] = None


class NewJoinersResponse(BaseModel):
    """Employees who joined in the last N days."""

    days: int = Field(..., description="Lookback window in days")
    count: int
    data: list[NewJoinerItem]


# ═════════════════════════════════════════════════════════════════════
# GET /department-headcount  (kept for backward compat)
# ═════════════════════════════════════════════════════════════════════


class DepartmentHeadcountItem(BaseModel):
    """Headcount for a single department."""

    department_id: uuid.UUID
    department_name: str
    headcount: int = 0
    present_today: int = 0
    on_leave_today: int = 0


class DepartmentHeadcountResponse(BaseModel):
    """Headcount breakdown by department."""

    total_departments: int
    data: list[DepartmentHeadcountItem]


# ═════════════════════════════════════════════════════════════════════
# GET /recent-activities  (kept for backward compat)
# ═════════════════════════════════════════════════════════════════════


class RecentActivityItem(BaseModel):
    """A single recent activity entry."""

    id: uuid.UUID
    action: str
    entity_type: str
    entity_id: uuid.UUID
    actor_id: Optional[uuid.UUID] = None
    actor_name: Optional[str] = None
    description: str = Field(..., description="Human-readable activity description")
    created_at: datetime


class RecentActivitiesResponse(BaseModel):
    """Recent activities across the platform."""

    limit: int
    data: list[RecentActivityItem]
