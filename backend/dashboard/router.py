"""Dashboard router — read-only endpoints for HR dashboard widgets.

All endpoints require authentication. Summary and department data are
accessible to managers, HR admins, and system admins. Employees can view
birthdays and their own summary via future extensions.
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
    RecentActivitiesResponse,
    UpcomingBirthdaysResponse,
)
from backend.dashboard.service import DashboardService
from backend.database import get_db

router = APIRouter()


# ── GET /summary ────────────────────────────────────────────────────

@router.get("/summary", response_model=DashboardSummaryResponse)
async def dashboard_summary(
    employee: Employee = Depends(
        require_role(UserRole.manager, UserRole.hr_admin, UserRole.system_admin)
    ),
    db: AsyncSession = Depends(get_db),
):
    """Dashboard KPI summary: employee count, present today, on leave, pending approvals."""
    return await DashboardService.get_summary(db)


# ── GET /attendance-trend ───────────────────────────────────────────

@router.get("/attendance-trend", response_model=AttendanceTrendResponse)
async def attendance_trend(
    days: int = Query(7, ge=7, le=90, description="Trend period: 7 or 30 days"),
    employee: Employee = Depends(
        require_role(UserRole.manager, UserRole.hr_admin, UserRole.system_admin)
    ),
    db: AsyncSession = Depends(get_db),
):
    """Attendance trend chart data for the last N days (default 7)."""
    return await DashboardService.get_attendance_trend(db, period_days=days)


# ── GET /department-headcount ───────────────────────────────────────

@router.get("/department-headcount", response_model=DepartmentHeadcountResponse)
async def department_headcount(
    employee: Employee = Depends(
        require_role(UserRole.manager, UserRole.hr_admin, UserRole.system_admin)
    ),
    db: AsyncSession = Depends(get_db),
):
    """Headcount breakdown by department with today's attendance snapshot."""
    return await DashboardService.get_department_headcount(db)


# ── GET /upcoming-birthdays ─────────────────────────────────────────

@router.get("/upcoming-birthdays", response_model=UpcomingBirthdaysResponse)
async def upcoming_birthdays(
    days: int = Query(30, ge=1, le=90, description="Lookahead window in days"),
    employee: Employee = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Upcoming employee birthdays within the next N days."""
    return await DashboardService.get_upcoming_birthdays(db, days_ahead=days)


# ── GET /recent-activities ──────────────────────────────────────────

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
