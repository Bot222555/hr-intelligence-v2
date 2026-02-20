"""Attendance router — clock in/out, daily records, regularization, shifts, holidays.

All endpoints require authentication. Manager/HR-specific endpoints enforce role checks.
"""


import uuid
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from backend.attendance.schemas import (
    AttendanceListResponse,
    ClockInRequest,
    ClockOutRequest,
    ClockResponse,
    HolidayResponse,
    RegularizationCreate,
    RegularizationRejectRequest,
    RegularizationResponse,
    ShiftPolicyResponse,
    TodayAttendanceResponse,
)
from backend.attendance.service import AttendanceService
from backend.auth.dependencies import get_current_user, require_role
from backend.common.constants import (
    AttendanceStatus,
    RegularizationStatus,
    UserRole,
)
from backend.core_hr.models import Employee
from backend.database import get_db

router = APIRouter(prefix="", tags=["attendance"])


# ── POST /clock-in ──────────────────────────────────────────────────

@router.post("/clock-in", response_model=ClockResponse)
async def clock_in(
    body: ClockInRequest,
    request: Request,
    employee: Employee = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Record a clock-in event for the current user."""
    ip = request.client.host if request.client else None
    return await AttendanceService.clock_in(
        db,
        employee.id,
        source=body.source,
        ip_address=ip,
        latitude=body.latitude,
        longitude=body.longitude,
    )


# ── POST /clock-out ─────────────────────────────────────────────────

@router.post("/clock-out", response_model=ClockResponse)
async def clock_out(
    body: ClockOutRequest,
    request: Request,
    employee: Employee = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Record a clock-out event for the current user."""
    ip = request.client.host if request.client else None
    return await AttendanceService.clock_out(
        db,
        employee.id,
        source=body.source,
        ip_address=ip,
        latitude=body.latitude,
        longitude=body.longitude,
    )


# ── GET /my-attendance ──────────────────────────────────────────────

@router.get("/my-attendance", response_model=AttendanceListResponse)
async def my_attendance(
    from_date: date = Query(..., description="Start date (inclusive)"),
    to_date: date = Query(..., description="End date (inclusive)"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    employee: Employee = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the authenticated user's attendance records with summary."""
    return await AttendanceService.get_my_attendance(
        db,
        employee.id,
        from_date,
        to_date,
        page=page,
        page_size=page_size,
    )


# ── GET /today ──────────────────────────────────────────────────────

@router.get("/today", response_model=TodayAttendanceResponse)
async def today_attendance(
    department_id: Optional[uuid.UUID] = Query(None),
    location_id: Optional[uuid.UUID] = Query(None),
    status: Optional[AttendanceStatus] = Query(None),
    employee: Employee = Depends(
        require_role(UserRole.manager, UserRole.hr_admin, UserRole.system_admin)
    ),
    db: AsyncSession = Depends(get_db),
):
    """Get today's attendance for all employees (manager / HR view)."""
    return await AttendanceService.get_today_attendance(
        db,
        department_id=department_id,
        location_id=location_id,
        status_filter=status,
    )


# ── GET /team ───────────────────────────────────────────────────────

@router.get("/team", response_model=AttendanceListResponse)
async def team_attendance(
    from_date: date = Query(..., description="Start date (inclusive)"),
    to_date: date = Query(..., description="End date (inclusive)"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    employee: Employee = Depends(
        require_role(UserRole.manager, UserRole.hr_admin, UserRole.system_admin)
    ),
    db: AsyncSession = Depends(get_db),
):
    """Get attendance records for the manager's direct reports."""
    return await AttendanceService.get_team_attendance(
        db,
        employee.id,
        from_date,
        to_date,
        page=page,
        page_size=page_size,
    )


# ── POST /regularization ────────────────────────────────────────────

@router.post("/regularization", response_model=RegularizationResponse)
async def submit_regularization(
    body: RegularizationCreate,
    employee: Employee = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Submit a regularization request for a past attendance record."""
    return await AttendanceService.submit_regularization(
        db,
        employee.id,
        target_date=body.date,
        requested_status=body.requested_status,
        requested_clock_in=body.requested_clock_in,
        requested_clock_out=body.requested_clock_out,
        reason=body.reason,
    )


# ── GET /regularizations ────────────────────────────────────────────

@router.get("/regularizations")
async def list_regularizations(
    status: Optional[RegularizationStatus] = Query(None),
    employee_id: Optional[uuid.UUID] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    employee: Employee = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List regularization requests.

    Employees see their own; managers/HR see filtered results.
    """
    request_state = getattr(employee, "_sa_instance_state", None)
    # Default to own regularizations for non-manager roles
    target_employee_id = employee_id or employee.id
    return await AttendanceService.list_regularizations(
        db,
        status_filter=status,
        employee_id=target_employee_id,
        page=page,
        page_size=page_size,
    )


# ── PUT /regularizations/{id}/approve ────────────────────────────────

@router.put("/regularizations/{regularization_id}/approve", response_model=RegularizationResponse)
async def approve_regularization(
    regularization_id: uuid.UUID,
    employee: Employee = Depends(
        require_role(UserRole.manager, UserRole.hr_admin, UserRole.system_admin)
    ),
    db: AsyncSession = Depends(get_db),
):
    """Approve a pending regularization request."""
    return await AttendanceService.approve_regularization(
        db, regularization_id, employee.id,
    )


# ── PUT /regularizations/{id}/reject ─────────────────────────────────

@router.put("/regularizations/{regularization_id}/reject", response_model=RegularizationResponse)
async def reject_regularization(
    regularization_id: uuid.UUID,
    body: RegularizationRejectRequest,
    employee: Employee = Depends(
        require_role(UserRole.manager, UserRole.hr_admin, UserRole.system_admin)
    ),
    db: AsyncSession = Depends(get_db),
):
    """Reject a pending regularization request with a reason."""
    return await AttendanceService.reject_regularization(
        db, regularization_id, employee.id, reason=body.reason,
    )


# ── GET /policies (shift policies) ──────────────────────────────────

@router.get("/policies", response_model=list[ShiftPolicyResponse])
async def get_policies(
    is_active: Optional[bool] = Query(True),
    employee: Employee = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List attendance/shift policies."""
    return await AttendanceService.get_shifts(db, is_active=is_active)


# ── GET /shifts ─────────────────────────────────────────────────────

@router.get("/shifts", response_model=list[ShiftPolicyResponse])
async def get_shifts(
    is_active: Optional[bool] = Query(True),
    employee: Employee = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all shift policies."""
    return await AttendanceService.get_shifts(db, is_active=is_active)


# ── GET /holidays ───────────────────────────────────────────────────

@router.get("/holidays", response_model=list[HolidayResponse])
async def get_holidays(
    year: Optional[int] = Query(None),
    location_id: Optional[uuid.UUID] = Query(None),
    employee: Employee = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List holidays, optionally filtered by year and location."""
    return await AttendanceService.get_holidays(
        db, year=year, location_id=location_id,
    )
