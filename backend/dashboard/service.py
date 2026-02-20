"""Dashboard service — read-only aggregation queries across HR modules.

All methods are static async, following the project convention.
Queries are kept efficient: COUNT/GROUP BY at DB level, no N+1.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

import sqlalchemy as sa
from sqlalchemy import and_, case, distinct, extract, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from backend.attendance.models import AttendanceRecord, AttendanceRegularization
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
    DepartmentBreakdownItem,
    DepartmentHeadcountItem,
    DepartmentHeadcountResponse,
    LeaveSummaryResponse,
    LeaveTypeSummaryItem,
    NewJoinerItem,
    NewJoinersResponse,
    RecentActivitiesResponse,
    RecentActivityItem,
    UpcomingBirthdayItem,
    UpcomingBirthdaysResponse,
)
from backend.leave.models import LeaveRequest, LeaveType


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
        """Return top-level KPI metrics for the dashboard.

        Returns:
            - total_employees: count of active employees
            - present_today: attendance records with checked-in status today
            - on_leave_today: approved leave requests covering today
            - pending_leave_requests: leave requests with status=pending
            - department_breakdown: employee count per department
        """
        today = _today()

        # Total active employees
        total_q = select(func.count(Employee.id)).where(
            Employee.is_active.is_(True),
            Employee.employment_status == EmploymentStatus.active,
        )

        # Present today (checked-in statuses: present, work_from_home, half_day, on_duty)
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

        # On leave today — from approved leave requests where today is in range
        on_leave_q = select(func.count(distinct(LeaveRequest.employee_id))).where(
            LeaveRequest.status == LeaveStatus.approved,
            LeaveRequest.start_date <= today,
            LeaveRequest.end_date >= today,
        )

        # Pending leave requests
        pending_leave_q = select(func.count(LeaveRequest.id)).where(
            LeaveRequest.status == LeaveStatus.pending,
        )

        # Execute scalar queries
        results = await _multi_scalar(
            db, total_q, present_q, on_leave_q, pending_leave_q,
        )

        # Department breakdown — active employees per department
        dept_q = (
            select(
                Department.id.label("department_id"),
                Department.name.label("department_name"),
                func.count(Employee.id).label("count"),
            )
            .outerjoin(
                Employee,
                and_(
                    Employee.department_id == Department.id,
                    Employee.is_active.is_(True),
                    Employee.employment_status == EmploymentStatus.active,
                ),
            )
            .where(Department.is_active.is_(True))
            .group_by(Department.id, Department.name)
            .order_by(Department.name)
        )
        dept_result = await db.execute(dept_q)
        dept_rows = dept_result.all()

        department_breakdown = [
            DepartmentBreakdownItem(
                department_id=row.department_id,
                department_name=row.department_name,
                count=row.count,
            )
            for row in dept_rows
        ]

        return DashboardSummaryResponse(
            total_employees=results[0] or 0,
            present_today=results[1] or 0,
            on_leave_today=results[2] or 0,
            pending_leave_requests=results[3] or 0,
            department_breakdown=department_breakdown,
        )

    # ═════════════════════════════════════════════════════════════════
    # GET /attendance-trend
    # ═════════════════════════════════════════════════════════════════

    @staticmethod
    async def get_attendance_trend(
        db: AsyncSession,
        period_days: int = 30,
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

        total_present = sum(
            p.present + p.work_from_home + p.half_day for p in days_with_data
        )
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
    # GET /leave-summary
    # ═════════════════════════════════════════════════════════════════

    @staticmethod
    async def get_leave_summary(db: AsyncSession) -> LeaveSummaryResponse:
        """Return leave type breakdown (sick, casual, earned, etc.) for current month.

        Counts approved + pending leave requests whose date range overlaps
        the current calendar month.
        """
        today = _today()
        month_start = today.replace(day=1)
        # Last day of current month
        if today.month == 12:
            month_end = date(today.year + 1, 1, 1) - timedelta(days=1)
        else:
            month_end = date(today.year, today.month + 1, 1) - timedelta(days=1)

        stmt = (
            select(
                LeaveType.id.label("leave_type_id"),
                LeaveType.code.label("leave_type_code"),
                LeaveType.name.label("leave_type_name"),
                func.count(LeaveRequest.id).label("request_count"),
                func.coalesce(func.sum(LeaveRequest.total_days), 0).label(
                    "total_days"
                ),
            )
            .outerjoin(
                LeaveRequest,
                and_(
                    LeaveRequest.leave_type_id == LeaveType.id,
                    LeaveRequest.status.in_(
                        [LeaveStatus.approved, LeaveStatus.pending]
                    ),
                    LeaveRequest.start_date <= month_end,
                    LeaveRequest.end_date >= month_start,
                ),
            )
            .where(LeaveType.is_active.is_(True))
            .group_by(LeaveType.id, LeaveType.code, LeaveType.name)
            .order_by(LeaveType.name)
        )

        result = await db.execute(stmt)
        rows = result.all()

        by_type = []
        grand_requests = 0
        grand_days = Decimal("0")

        for row in rows:
            item = LeaveTypeSummaryItem(
                leave_type_id=row.leave_type_id,
                leave_type_code=row.leave_type_code,
                leave_type_name=row.leave_type_name,
                request_count=row.request_count,
                total_days=row.total_days,
            )
            by_type.append(item)
            grand_requests += row.request_count
            grand_days += Decimal(str(row.total_days))

        return LeaveSummaryResponse(
            month=today.month,
            year=today.year,
            total_requests=grand_requests,
            total_days=grand_days,
            by_type=by_type,
        )

    # ═════════════════════════════════════════════════════════════════
    # GET /birthdays
    # ═════════════════════════════════════════════════════════════════

    @staticmethod
    async def get_upcoming_birthdays(
        db: AsyncSession,
        days_ahead: int = 7,
    ) -> UpcomingBirthdaysResponse:
        """Return employees with birthdays in the next N days.

        Uses month/day comparison to handle year-end wraparound.
        For SQLite compat (tests), we load all employees with DOB and
        filter in Python. For production (PostgreSQL), this is still
        efficient given typical company sizes (< 10k employees).
        """
        today = _today()
        end_date = today + timedelta(days=days_ahead)

        # Load active employees with DOB set
        stmt = (
            select(
                Employee.id.label("employee_id"),
                Employee.employee_code,
                Employee.display_name,
                Employee.date_of_birth,
                Employee.profile_photo_url,
                Department.name.label("department_name"),
            )
            .outerjoin(Department, Employee.department_id == Department.id)
            .where(
                Employee.is_active.is_(True),
                Employee.employment_status == EmploymentStatus.active,
                Employee.date_of_birth.isnot(None),
            )
        )

        result = await db.execute(stmt)
        rows = result.all()

        items: list[UpcomingBirthdayItem] = []
        for row in rows:
            dob = row.date_of_birth
            # Compute next birthday
            try:
                birthday_this_year = dob.replace(year=today.year)
            except ValueError:
                # Feb 29 in a non-leap year → use Feb 28
                birthday_this_year = date(today.year, 2, 28)

            if birthday_this_year < today:
                try:
                    birthday_next_year = dob.replace(year=today.year + 1)
                except ValueError:
                    birthday_next_year = date(today.year + 1, 2, 28)
                next_birthday = birthday_next_year
            else:
                next_birthday = birthday_this_year

            if today <= next_birthday <= end_date:
                items.append(
                    UpcomingBirthdayItem(
                        employee_id=row.employee_id,
                        employee_code=row.employee_code,
                        display_name=row.display_name,
                        department_name=row.department_name,
                        date_of_birth=row.date_of_birth,
                        birthday_date=next_birthday,
                        days_away=(next_birthday - today).days,
                        profile_photo_url=row.profile_photo_url,
                    )
                )

        # Sort by days_away
        items.sort(key=lambda x: x.days_away)

        return UpcomingBirthdaysResponse(
            days_ahead=days_ahead,
            data=items,
        )

    # ═════════════════════════════════════════════════════════════════
    # GET /new-joiners
    # ═════════════════════════════════════════════════════════════════

    @staticmethod
    async def get_new_joiners(
        db: AsyncSession,
        days: int = 30,
    ) -> NewJoinersResponse:
        """Return employees who joined in the last N days."""
        today = _today()
        since = today - timedelta(days=days)

        stmt = (
            select(
                Employee.id.label("employee_id"),
                Employee.employee_code,
                Employee.first_name,
                Employee.last_name,
                Employee.display_name,
                Employee.job_title,
                Employee.date_of_joining,
                Employee.profile_photo_url,
                Department.name.label("department_name"),
            )
            .outerjoin(Department, Employee.department_id == Department.id)
            .where(
                Employee.is_active.is_(True),
                Employee.employment_status == EmploymentStatus.active,
                Employee.date_of_joining >= since,
                Employee.date_of_joining <= today,
            )
            .order_by(Employee.date_of_joining.desc())
        )

        result = await db.execute(stmt)
        rows = result.all()

        items = [
            NewJoinerItem(
                employee_id=row.employee_id,
                employee_code=row.employee_code,
                first_name=row.first_name,
                last_name=row.last_name,
                display_name=row.display_name,
                department_name=row.department_name,
                job_title=row.job_title,
                date_of_joining=row.date_of_joining,
                profile_photo_url=row.profile_photo_url,
            )
            for row in rows
        ]

        return NewJoinersResponse(
            days=days,
            count=len(items),
            data=items,
        )

    # ═════════════════════════════════════════════════════════════════
    # GET /department-headcount  (kept for backward compat)
    # ═════════════════════════════════════════════════════════════════

    @staticmethod
    async def get_department_headcount(
        db: AsyncSession,
    ) -> DepartmentHeadcountResponse:
        """Return headcount per department with today's attendance snapshot."""
        today = _today()

        headcount_stmt = (
            select(
                Department.id.label("department_id"),
                Department.name.label("department_name"),
                func.count(Employee.id).label("headcount"),
            )
            .outerjoin(
                Employee,
                and_(
                    Employee.department_id == Department.id,
                    Employee.is_active.is_(True),
                    Employee.employment_status == EmploymentStatus.active,
                ),
            )
            .where(Department.is_active.is_(True))
            .group_by(Department.id, Department.name)
            .order_by(Department.name)
        )

        headcount_result = await db.execute(headcount_stmt)
        headcount_rows = headcount_result.all()

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
                    case(
                        (AttendanceRecord.status == AttendanceStatus.on_leave, 1)
                    )
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
            items.append(
                DepartmentHeadcountItem(
                    department_id=row.department_id,
                    department_name=row.department_name,
                    headcount=row.headcount,
                    present_today=att.present_today if att else 0,
                    on_leave_today=att.on_leave_today if att else 0,
                )
            )

        return DepartmentHeadcountResponse(
            total_departments=len(items),
            data=items,
        )

    # ═════════════════════════════════════════════════════════════════
    # GET /recent-activities  (kept for backward compat)
    # ═════════════════════════════════════════════════════════════════

    @staticmethod
    async def get_recent_activities(
        db: AsyncSession,
        limit: int = 20,
    ) -> RecentActivitiesResponse:
        """Return the most recent audit trail entries."""
        from backend.common.audit import AuditTrail

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
            actor_name = row.actor_name or (
                f"{row.actor_first_name} {row.actor_last_name}".strip()
                if row.actor_first_name
                else None
            )
            description = _build_activity_description(
                action=row.action,
                entity_type=row.entity_type,
                actor_name=actor_name,
            )
            items.append(
                RecentActivityItem(
                    id=row.id,
                    action=row.action,
                    entity_type=row.entity_type,
                    entity_id=row.entity_id,
                    actor_id=row.actor_id,
                    actor_name=actor_name,
                    description=description,
                    created_at=row.created_at,
                )
            )

        return RecentActivitiesResponse(limit=limit, data=items)


# ═════════════════════════════════════════════════════════════════════
# Helpers
# ═════════════════════════════════════════════════════════════════════


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

    entity_label = entity_type.replace("_", " ")
    return f"{actor} performed '{action}' on {entity_label}"
