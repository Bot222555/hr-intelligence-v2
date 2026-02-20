"""Dashboard service — read-only aggregation queries across HR modules.

All methods are static async, following the project convention.
Queries are kept efficient: COUNT/GROUP BY at DB level, no N+1.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import and_, case, distinct, extract, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from backend.attendance.models import AttendanceRecord, AttendanceRegularization
from backend.common.audit import AuditTrail
from backend.common.constants import (
    AttendanceStatus,
    EmploymentStatus,
    LeaveStatus,
    RegularizationStatus,
)
from backend.core_hr.models import Department, Employee
from backend.dashboard.schemas import (
    AttendanceTrendAverages,
    AttendanceTrendPoint,
    AttendanceTrendResponse,
    DashboardSummaryResponse,
    DepartmentHeadcountItem,
    DepartmentHeadcountResponse,
    RecentActivitiesResponse,
    RecentActivityItem,
    UpcomingBirthdayItem,
    UpcomingBirthdaysResponse,
)
from backend.leave.models import LeaveRequest


def _today() -> date:
    """Current date in IST (Asia/Kolkata)."""
    from zoneinfo import ZoneInfo

    return datetime.now(ZoneInfo("Asia/Kolkata")).date()


class DashboardService:
    """Async dashboard aggregation queries."""

    # ═════════════════════════════════════════════════════════════════
    # GET /summary
    # ═════════════════════════════════════════════════════════════════

    @staticmethod
    async def get_summary(db: AsyncSession) -> DashboardSummaryResponse:
        """Return top-level KPI metrics for the dashboard."""
        today = _today()
        month_start = today.replace(day=1)

        # Total active employees
        total_q = select(func.count(Employee.id)).where(
            Employee.is_active.is_(True),
            Employee.employment_status == EmploymentStatus.active,
        )

        # Present today (present, work_from_home, half_day, on_duty)
        present_statuses = [
            AttendanceStatus.present,
            AttendanceStatus.work_from_home,
            AttendanceStatus.half_day,
            AttendanceStatus.on_duty,
        ]
        present_q = select(func.count(AttendanceRecord.id)).where(
            AttendanceRecord.date == today,
            AttendanceRecord.status.in_(present_statuses),
        )

        # On leave today
        on_leave_q = select(func.count(AttendanceRecord.id)).where(
            AttendanceRecord.date == today,
            AttendanceRecord.status == AttendanceStatus.on_leave,
        )

        # Pending leave approvals
        pending_leave_q = select(func.count(LeaveRequest.id)).where(
            LeaveRequest.status == LeaveStatus.pending,
        )

        # Pending attendance regularizations
        pending_reg_q = select(func.count(AttendanceRegularization.id)).where(
            AttendanceRegularization.status == RegularizationStatus.pending,
        )

        # New joiners this month
        joiners_q = select(func.count(Employee.id)).where(
            Employee.is_active.is_(True),
            Employee.date_of_joining >= month_start,
            Employee.date_of_joining <= today,
        )

        # Attrition this month
        attrition_q = select(func.count(Employee.id)).where(
            or_(
                and_(
                    Employee.last_working_date >= month_start,
                    Employee.last_working_date <= today,
                ),
                and_(
                    Employee.date_of_exit >= month_start,
                    Employee.date_of_exit <= today,
                ),
            ),
        )

        # Execute all counts in parallel-ish (single round-trip each)
        results = await _multi_scalar(
            db, total_q, present_q, on_leave_q, pending_leave_q,
            pending_reg_q, joiners_q, attrition_q,
        )

        return DashboardSummaryResponse(
            total_employees=results[0] or 0,
            present_today=results[1] or 0,
            on_leave_today=results[2] or 0,
            pending_approvals=(results[3] or 0) + (results[4] or 0),
            new_joiners_this_month=results[5] or 0,
            attrition_this_month=results[6] or 0,
        )

    # ═════════════════════════════════════════════════════════════════
    # GET /attendance-trend
    # ═════════════════════════════════════════════════════════════════

    @staticmethod
    async def get_attendance_trend(
        db: AsyncSession,
        period_days: int = 7,
    ) -> AttendanceTrendResponse:
        """Return daily attendance breakdown for the last N days."""
        today = _today()
        start_date = today - timedelta(days=period_days - 1)

        present_statuses = [
            AttendanceStatus.present,
            AttendanceStatus.on_duty,
        ]

        stmt = (
            select(
                AttendanceRecord.date,
                func.count(AttendanceRecord.id).label("total"),
                func.count(
                    case(
                        (AttendanceRecord.status.in_(present_statuses), 1),
                    )
                ).label("present"),
                func.count(
                    case(
                        (AttendanceRecord.status == AttendanceStatus.absent, 1),
                    )
                ).label("absent"),
                func.count(
                    case(
                        (AttendanceRecord.status == AttendanceStatus.on_leave, 1),
                    )
                ).label("on_leave"),
                func.count(
                    case(
                        (AttendanceRecord.status == AttendanceStatus.work_from_home, 1),
                    )
                ).label("work_from_home"),
                func.count(
                    case(
                        (AttendanceRecord.status == AttendanceStatus.half_day, 1),
                    )
                ).label("half_day"),
            )
            .where(
                AttendanceRecord.date >= start_date,
                AttendanceRecord.date <= today,
            )
            .group_by(AttendanceRecord.date)
            .order_by(AttendanceRecord.date)
        )

        result = await db.execute(stmt)
        rows = result.all()

        # Build lookup for days that have data
        data_map: dict[date, AttendanceTrendPoint] = {}
        for row in rows:
            data_map[row.date] = AttendanceTrendPoint(
                date=row.date,
                present=row.present,
                absent=row.absent,
                on_leave=row.on_leave,
                work_from_home=row.work_from_home,
                half_day=row.half_day,
            )

        # Fill in missing dates with zeros
        data: list[AttendanceTrendPoint] = []
        for i in range(period_days):
            d = start_date + timedelta(days=i)
            data.append(data_map.get(d, AttendanceTrendPoint(date=d)))

        # Compute averages
        days_with_data = [p for p in data if (p.present + p.absent + p.on_leave) > 0]
        num_days = len(days_with_data) or 1

        total_present = sum(p.present + p.work_from_home + p.half_day for p in days_with_data)
        total_absent = sum(p.absent for p in days_with_data)
        total_on_leave = sum(p.on_leave for p in days_with_data)
        total_headcount = total_present + total_absent + total_on_leave

        averages = AttendanceTrendAverages(
            avg_present=round(total_present / num_days, 1),
            avg_absent=round(total_absent / num_days, 1),
            avg_on_leave=round(total_on_leave / num_days, 1),
            avg_attendance_rate=(
                round((total_present / total_headcount) * 100, 1)
                if total_headcount > 0
                else 0.0
            ),
        )

        return AttendanceTrendResponse(
            period_days=period_days,
            start_date=start_date,
            end_date=today,
            data=data,
            averages=averages,
        )

    # ═════════════════════════════════════════════════════════════════
    # GET /department-headcount
    # ═════════════════════════════════════════════════════════════════

    @staticmethod
    async def get_department_headcount(
        db: AsyncSession,
    ) -> DepartmentHeadcountResponse:
        """Return headcount per department with today's attendance snapshot."""
        today = _today()

        # Headcount per department (active employees only)
        headcount_stmt = (
            select(
                Department.id.label("department_id"),
                Department.name.label("department_name"),
                func.count(Employee.id).label("headcount"),
            )
            .outerjoin(Employee, and_(
                Employee.department_id == Department.id,
                Employee.is_active.is_(True),
                Employee.employment_status == EmploymentStatus.active,
            ))
            .where(Department.is_active.is_(True))
            .group_by(Department.id, Department.name)
            .order_by(Department.name)
        )

        headcount_result = await db.execute(headcount_stmt)
        headcount_rows = headcount_result.all()

        # Today's attendance per department
        present_statuses = [
            AttendanceStatus.present,
            AttendanceStatus.work_from_home,
            AttendanceStatus.half_day,
            AttendanceStatus.on_duty,
        ]

        attendance_stmt = (
            select(
                Employee.department_id,
                func.count(
                    case((AttendanceRecord.status.in_(present_statuses), 1))
                ).label("present_today"),
                func.count(
                    case((AttendanceRecord.status == AttendanceStatus.on_leave, 1))
                ).label("on_leave_today"),
            )
            .join(Employee, AttendanceRecord.employee_id == Employee.id)
            .where(
                AttendanceRecord.date == today,
                Employee.is_active.is_(True),
            )
            .group_by(Employee.department_id)
        )

        att_result = await db.execute(attendance_stmt)
        att_rows = att_result.all()
        att_map = {row.department_id: row for row in att_rows}

        items: list[DepartmentHeadcountItem] = []
        for row in headcount_rows:
            att = att_map.get(row.department_id)
            items.append(DepartmentHeadcountItem(
                department_id=row.department_id,
                department_name=row.department_name,
                headcount=row.headcount,
                present_today=att.present_today if att else 0,
                on_leave_today=att.on_leave_today if att else 0,
            ))

        return DepartmentHeadcountResponse(
            total_departments=len(items),
            data=items,
        )

    # ═════════════════════════════════════════════════════════════════
    # GET /upcoming-birthdays
    # ═════════════════════════════════════════════════════════════════

    @staticmethod
    async def get_upcoming_birthdays(
        db: AsyncSession,
        days_ahead: int = 30,
    ) -> UpcomingBirthdaysResponse:
        """Return employees with birthdays in the next N days.

        Uses PostgreSQL date arithmetic to find birthdays regardless of
        birth year — compares (month, day) against today + N days window.
        """
        today = _today()
        end_date = today + timedelta(days=days_ahead)

        # Build a query that computes each employee's next birthday this year/next year
        # and filters to those within the window.
        # We use a raw-ish approach with extract() for cross-year handling.

        # Birthday this year
        birthday_this_year = func.make_date(
            today.year,
            extract("month", Employee.date_of_birth).cast(sa_int()),
            extract("day", Employee.date_of_birth).cast(sa_int()),
        )

        # Birthday next year (for Dec→Jan wraparound)
        birthday_next_year = func.make_date(
            today.year + 1,
            extract("month", Employee.date_of_birth).cast(sa_int()),
            extract("day", Employee.date_of_birth).cast(sa_int()),
        )

        # Pick whichever is the upcoming one
        next_birthday = case(
            (birthday_this_year >= today, birthday_this_year),
            else_=birthday_next_year,
        )

        stmt = (
            select(
                Employee.id.label("employee_id"),
                Employee.employee_code,
                Employee.display_name,
                Employee.date_of_birth,
                Employee.profile_photo_url,
                Department.name.label("department_name"),
                next_birthday.label("birthday_date"),
            )
            .outerjoin(Department, Employee.department_id == Department.id)
            .where(
                Employee.is_active.is_(True),
                Employee.employment_status == EmploymentStatus.active,
                Employee.date_of_birth.isnot(None),
                next_birthday >= today,
                next_birthday <= end_date,
            )
            .order_by(next_birthday)
        )

        result = await db.execute(stmt)
        rows = result.all()

        items: list[UpcomingBirthdayItem] = []
        for row in rows:
            items.append(UpcomingBirthdayItem(
                employee_id=row.employee_id,
                employee_code=row.employee_code,
                display_name=row.display_name,
                department_name=row.department_name,
                date_of_birth=row.date_of_birth,
                birthday_date=row.birthday_date,
                days_away=(row.birthday_date - today).days,
                profile_photo_url=row.profile_photo_url,
            ))

        return UpcomingBirthdaysResponse(
            days_ahead=days_ahead,
            data=items,
        )

    # ═════════════════════════════════════════════════════════════════
    # GET /recent-activities
    # ═════════════════════════════════════════════════════════════════

    @staticmethod
    async def get_recent_activities(
        db: AsyncSession,
        limit: int = 20,
    ) -> RecentActivitiesResponse:
        """Return the most recent audit trail entries with human-readable descriptions."""

        # Alias for the actor employee
        Actor = aliased(Employee, flat=True)

        stmt = (
            select(
                AuditTrail.id,
                AuditTrail.action,
                AuditTrail.entity_type,
                AuditTrail.entity_id,
                AuditTrail.actor_id,
                AuditTrail.created_at,
                Actor.display_name.label("actor_name"),
                Actor.first_name.label("actor_first_name"),
                Actor.last_name.label("actor_last_name"),
            )
            .outerjoin(Actor, AuditTrail.actor_id == Actor.id)
            .order_by(AuditTrail.created_at.desc())
            .limit(limit)
        )

        result = await db.execute(stmt)
        rows = result.all()

        items: list[RecentActivityItem] = []
        for row in rows:
            actor_name = (
                row.actor_name
                or (
                    f"{row.actor_first_name} {row.actor_last_name}".strip()
                    if row.actor_first_name
                    else None
                )
            )
            description = _build_activity_description(
                action=row.action,
                entity_type=row.entity_type,
                actor_name=actor_name,
            )
            items.append(RecentActivityItem(
                id=row.id,
                action=row.action,
                entity_type=row.entity_type,
                entity_id=row.entity_id,
                actor_id=row.actor_id,
                actor_name=actor_name,
                description=description,
                created_at=row.created_at,
            ))

        return RecentActivitiesResponse(
            limit=limit,
            data=items,
        )


# ═════════════════════════════════════════════════════════════════════
# Helpers
# ═════════════════════════════════════════════════════════════════════


import sqlalchemy as sa


def sa_int():
    """Shorthand for sa.Integer for cast expressions."""
    return sa.Integer


async def _multi_scalar(db: AsyncSession, *stmts) -> list:
    """Execute multiple scalar queries and return their results in order."""
    results = []
    for stmt in stmts:
        result = await db.execute(stmt)
        results.append(result.scalar())
    return results


# Human-readable descriptions for audit trail actions
_ACTION_DESCRIPTIONS: dict[str, dict[str, str]] = {
    "create": {
        "employee": "added a new employee",
        "leave_request": "submitted a leave request",
        "attendance_record": "created an attendance record",
        "attendance_regularization": "submitted an attendance regularization",
        "department": "created a new department",
        "location": "added a new location",
        "notification": "sent a notification",
        "comp_off_grant": "requested compensatory off",
    },
    "update": {
        "employee": "updated employee details",
        "leave_request": "updated a leave request",
        "attendance_record": "updated an attendance record",
        "department": "updated department details",
        "location": "updated location details",
    },
    "approve": {
        "leave_request": "approved a leave request",
        "attendance_regularization": "approved an attendance regularization",
        "comp_off_grant": "approved a comp-off request",
    },
    "reject": {
        "leave_request": "rejected a leave request",
        "attendance_regularization": "rejected an attendance regularization",
    },
    "cancel": {
        "leave_request": "cancelled a leave request",
    },
    "delete": {
        "employee": "deactivated an employee",
    },
}


def _build_activity_description(
    action: str,
    entity_type: str,
    actor_name: Optional[str] = None,
) -> str:
    """Build a human-readable description for an audit trail entry."""
    actor = actor_name or "System"
    action_map = _ACTION_DESCRIPTIONS.get(action, {})
    verb = action_map.get(entity_type)

    if verb:
        return f"{actor} {verb}"

    # Fallback: generic description
    entity_label = entity_type.replace("_", " ")
    return f"{actor} performed '{action}' on {entity_label}"
