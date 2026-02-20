"""Leave router — apply, approve/reject, balances, policies, comp-off, holidays.

All endpoints require authentication. Manager/HR-specific endpoints enforce role checks.
"""


import uuid
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.attendance.service import AttendanceService
from backend.auth.dependencies import get_current_user, require_role
from backend.common.constants import LeaveStatus, UserRole
from backend.core_hr.models import Employee
from backend.database import get_db
from backend.leave.schemas import (
    CompOffCreate,
    CompOffOut,
    LeaveApproveRequest,
    LeaveBalanceOut,
    LeaveCancelRequest,
    LeaveRejectRequest,
    LeaveRequestCreate,
    LeaveRequestOut,
    LeaveTypeOut,
)
from backend.leave.service import LeaveService

router = APIRouter(prefix="", tags=["leave"])


# ── POST /apply ─────────────────────────────────────────────────────

@router.post("/apply", response_model=LeaveRequestOut)
async def apply_leave(
    body: LeaveRequestCreate,
    employee: Employee = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Apply for leave. Validates balance, overlap, notice period, and sandwich rules."""
    return await LeaveService.apply_leave(db, employee.id, body)


# ── GET /my-leaves ──────────────────────────────────────────────────

@router.get("/my-leaves")
async def my_leaves(
    status: Optional[LeaveStatus] = Query(None),
    leave_type_id: Optional[uuid.UUID] = Query(None),
    from_date: Optional[date] = Query(None),
    to_date: Optional[date] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    employee: Employee = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the authenticated user's leave requests with pagination."""
    return await LeaveService.get_leave_requests(
        db,
        requestor_id=employee.id,
        status=status,
        leave_type_id=leave_type_id,
        from_date=from_date,
        to_date=to_date,
        scope="my",
        page=page,
        page_size=page_size,
    )


# ── GET /team-leaves ────────────────────────────────────────────────

@router.get("/team-leaves")
async def team_leaves(
    status: Optional[LeaveStatus] = Query(None),
    employee_id: Optional[uuid.UUID] = Query(None),
    leave_type_id: Optional[uuid.UUID] = Query(None),
    from_date: Optional[date] = Query(None),
    to_date: Optional[date] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    employee: Employee = Depends(
        require_role(UserRole.manager, UserRole.hr_admin, UserRole.system_admin)
    ),
    db: AsyncSession = Depends(get_db),
):
    """Get leave requests for the manager's direct reports (team view)."""
    return await LeaveService.get_leave_requests(
        db,
        requestor_id=employee.id,
        employee_id=employee_id,
        status=status,
        leave_type_id=leave_type_id,
        from_date=from_date,
        to_date=to_date,
        scope="team",
        page=page,
        page_size=page_size,
    )


# ── PUT /{id}/approve ───────────────────────────────────────────────

@router.put("/{request_id}/approve", response_model=LeaveRequestOut)
async def approve_leave(
    request_id: uuid.UUID,
    body: LeaveApproveRequest,
    employee: Employee = Depends(
        require_role(UserRole.manager, UserRole.hr_admin, UserRole.system_admin)
    ),
    db: AsyncSession = Depends(get_db),
):
    """Approve a pending leave request. Deducts from balance."""
    return await LeaveService.approve_leave(
        db, request_id, employee.id, remarks=body.remarks,
    )


# ── PUT /{id}/reject ────────────────────────────────────────────────

@router.put("/{request_id}/reject", response_model=LeaveRequestOut)
async def reject_leave(
    request_id: uuid.UUID,
    body: LeaveRejectRequest,
    employee: Employee = Depends(
        require_role(UserRole.manager, UserRole.hr_admin, UserRole.system_admin)
    ),
    db: AsyncSession = Depends(get_db),
):
    """Reject a pending leave request."""
    return await LeaveService.reject_leave(
        db, request_id, employee.id, body.reason,
    )


# ── GET /balances ───────────────────────────────────────────────────

@router.get("/balances", response_model=list[LeaveBalanceOut])
async def get_balances(
    year: Optional[int] = Query(None, description="Leave year; defaults to current year"),
    employee: Employee = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the authenticated user's leave balances for a given year."""
    from datetime import datetime, timezone as tz

    target_year = year or datetime.now(tz.utc).year
    return await LeaveService.get_balance(db, employee.id, target_year)


# ── GET /policies ───────────────────────────────────────────────────

@router.get("/policies", response_model=list[LeaveTypeOut])
async def get_policies(
    is_active: Optional[bool] = Query(True),
    employee: Employee = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List available leave types / policies."""
    return await LeaveService.get_leave_types(db, is_active=is_active)


# ── GET /holidays ───────────────────────────────────────────────────

@router.get("/holidays")
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


# ── POST /comp-off ──────────────────────────────────────────────────

@router.post("/comp-off", response_model=CompOffOut)
async def request_comp_off(
    body: CompOffCreate,
    employee: Employee = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Submit a compensatory off request for working on a weekend/holiday."""
    return await LeaveService.request_comp_off(
        db, employee.id, body.work_date, body.reason,
    )
