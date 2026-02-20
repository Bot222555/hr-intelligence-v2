"""Dashboard router — read-only endpoints for HR dashboard widgets.

All endpoints require authentication. Summary, trend, and leave data are
accessible to managers, HR admins, and system admins. Birthdays are
visible to all authenticated employees.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth.dependencies import get_current_user, require_role
from backend.common.constants import UserRole
from backend.core_hr.models import Employee
from backend.dashboard.schemas import (
    AttendanceTrendResponse,
    DashboardSummaryResponse,
    DepartmentHeadcountResponse,
    LeaveSummaryResponse,
    NewJoinersResponse,
    RecentActivitiesResponse,
    UpcomingBirthdaysResponse,
)
from backend.dashboard.service import DashboardService
from backend.database import get_db

router = APIRouter()


# ── GET /summary ────────────────────────────────────────────────────

@router.get("/summary", response_model=DashboardSummaryResponse)
async def dashboard_summary(
    employee: Employee = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Dashboard KPI summary: employee count, present today, on leave,
    pending leave requests, department breakdown."""
    return await DashboardService.get_summary(db)


# ── GET /attendance-trend ───────────────────────────────────────────

@router.get("/attendance-trend", response_model=AttendanceTrendResponse)
async def attendance_trend(
    days: int = Query(30, ge=7, le=90, description="Trend period in days (default 30)"),
    employee: Employee = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Daily attendance count for the last N days (default 30)."""
    return await DashboardService.get_attendance_trend(db, period_days=days)


# ── GET /leave-summary ─────────────────────────────────────────────

@router.get("/leave-summary", response_model=LeaveSummaryResponse)
async def leave_summary(
    employee: Employee = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Leave type breakdown (sick, casual, earned, etc.) for the current month."""
    return await DashboardService.get_leave_summary(db)


# ── GET /birthdays ──────────────────────────────────────────────────

@router.get("/birthdays", response_model=UpcomingBirthdaysResponse)
async def upcoming_birthdays(
    days: int = Query(7, ge=1, le=90, description="Lookahead window in days (default 7)"),
    employee: Employee = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Upcoming employee birthdays within the next N days (default 7)."""
    return await DashboardService.get_upcoming_birthdays(db, days_ahead=days)


# ── GET /new-joiners ────────────────────────────────────────────────

@router.get("/new-joiners", response_model=NewJoinersResponse)
async def new_joiners(
    days: int = Query(30, ge=1, le=90, description="Lookback window in days (default 30)"),
    employee: Employee = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Employees who joined in the last N days (default 30)."""
    return await DashboardService.get_new_joiners(db, days=days)


# ── GET /department-headcount (backward compat) ─────────────────────

@router.get("/department-headcount", response_model=DepartmentHeadcountResponse)
async def department_headcount(
    employee: Employee = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Headcount breakdown by department with today's attendance snapshot."""
    return await DashboardService.get_department_headcount(db)


# ── GET /recent-activities (backward compat) ────────────────────────

@router.get("/recent-activities", response_model=RecentActivitiesResponse)
async def recent_activities(
    limit: int = Query(20, ge=1, le=50, description="Number of recent activities"),
    employee: Employee = Depends(
        require_role(UserRole.hr_admin, UserRole.system_admin)
    ),
    db: AsyncSession = Depends(get_db),
):
    """Recent platform activities from the audit trail."""
    return await DashboardService.get_recent_activities(db, limit=limit)
