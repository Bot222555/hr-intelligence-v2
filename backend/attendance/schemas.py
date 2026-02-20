"""Attendance Pydantic v2 schemas — request / response validation.

Naming conventions:
  - *Create / *Request  → request bodies (write)
  - *Response / *Detail → response bodies (read)
  - *Summary / *ListItem → compact read representations
"""


import uuid
from datetime import date, datetime, time
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from backend.common.constants import (
    ArrivalStatus,
    AttendanceStatus,
    RegularizationStatus,
)
from backend.common.pagination import PaginationMeta


# ═════════════════════════════════════════════════════════════════════
# Clock in / out
# ═════════════════════════════════════════════════════════════════════


class ClockInRequest(BaseModel):
    """Payload for clocking in."""

    source: str = Field(
        default="web",
        max_length=50,
        description="Clock source: web, mobile, biometric, kiosk",
    )
    latitude: Optional[float] = Field(None, ge=-90, le=90)
    longitude: Optional[float] = Field(None, ge=-180, le=180)


class ClockOutRequest(BaseModel):
    """Payload for clocking out."""

    source: str = Field(
        default="web",
        max_length=50,
        description="Clock source: web, mobile, biometric, kiosk",
    )
    latitude: Optional[float] = Field(None, ge=-90, le=90)
    longitude: Optional[float] = Field(None, ge=-180, le=180)


class ClockResponse(BaseModel):
    """Response after a clock-in or clock-out action."""

    model_config = ConfigDict(from_attributes=True)

    clock_entry_id: uuid.UUID
    attendance_id: uuid.UUID
    timestamp: datetime
    status: AttendanceStatus
    arrival_status: Optional[ArrivalStatus] = None


# ═════════════════════════════════════════════════════════════════════
# Attendance record
# ═════════════════════════════════════════════════════════════════════


class ShiftBrief(BaseModel):
    """Minimal shift info embedded in attendance responses."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    start_time: time
    end_time: time


class AttendanceRecordResponse(BaseModel):
    """Single attendance record for a day."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    date: date
    first_clock_in: Optional[datetime] = None
    last_clock_out: Optional[datetime] = None
    total_hours: Optional[float] = None
    effective_hours: Optional[float] = None
    overtime_hours: float = 0.0
    status: AttendanceStatus
    arrival_status: Optional[ArrivalStatus] = None
    shift: Optional[ShiftBrief] = None
    is_regularized: bool = False
    source: str = "system"
    remarks: Optional[str] = None


class AttendanceSummary(BaseModel):
    """Aggregated attendance summary for a date range."""

    present: int = 0
    absent: int = 0
    half_day: int = 0
    late: int = 0
    very_late: int = 0
    avg_hours: float = 0.0
    total_overtime: float = 0.0


class AttendanceListResponse(BaseModel):
    """Paginated attendance list with summary statistics."""

    data: list[AttendanceRecordResponse]
    meta: PaginationMeta
    summary: AttendanceSummary


# ═════════════════════════════════════════════════════════════════════
# Today's attendance (admin / manager view)
# ═════════════════════════════════════════════════════════════════════


class EmployeeBrief(BaseModel):
    """Minimal employee info in attendance views."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    employee_code: str
    display_name: Optional[str] = None
    designation: Optional[str] = None
    department_name: Optional[str] = None
    profile_photo_url: Optional[str] = None


class TodayAttendanceItem(BaseModel):
    """Single employee's attendance for today."""

    employee: EmployeeBrief
    status: AttendanceStatus = AttendanceStatus.absent
    arrival_status: Optional[ArrivalStatus] = None
    first_clock_in: Optional[datetime] = None
    last_clock_out: Optional[datetime] = None
    total_hours: Optional[float] = None
    shift_name: Optional[str] = None


class TodaySummary(BaseModel):
    """Summary counts for today's attendance dashboard."""

    total_employees: int = 0
    present: int = 0
    absent: int = 0
    on_leave: int = 0
    work_from_home: int = 0
    not_clocked_in_yet: int = 0


class TodayAttendanceResponse(BaseModel):
    """Today's attendance with items and summary."""

    data: list[TodayAttendanceItem]
    summary: TodaySummary


# ═════════════════════════════════════════════════════════════════════
# Regularization
# ═════════════════════════════════════════════════════════════════════


class RegularizationCreate(BaseModel):
    """Request to regularize an attendance record."""

    date: date
    requested_status: AttendanceStatus = AttendanceStatus.present
    requested_clock_in: Optional[datetime] = None
    requested_clock_out: Optional[datetime] = None
    reason: str = Field(..., min_length=10, max_length=500)


class RegularizationResponse(BaseModel):
    """Regularization request details."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    attendance_record_id: uuid.UUID
    employee_id: uuid.UUID
    requested_status: AttendanceStatus
    reason: str
    status: RegularizationStatus
    reviewed_by: Optional[uuid.UUID] = None
    reviewed_at: Optional[datetime] = None
    reviewer_remarks: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class RegularizationRejectRequest(BaseModel):
    """Payload for rejecting a regularization request."""

    reason: str = Field(..., min_length=5, max_length=500)


# ═════════════════════════════════════════════════════════════════════
# Shift policy & holidays
# ═════════════════════════════════════════════════════════════════════


class ShiftPolicyResponse(BaseModel):
    """Full shift policy representation."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    start_time: time
    end_time: time
    grace_minutes: int
    half_day_minutes: int
    full_day_minutes: int
    is_night_shift: bool
    is_active: bool
    created_at: datetime


class HolidayResponse(BaseModel):
    """Single holiday entry."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    date: date
    is_optional: bool = False
    is_restricted: bool = False
    calendar_id: uuid.UUID
