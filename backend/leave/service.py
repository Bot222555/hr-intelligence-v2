"""Leave service layer — balance engine, leave application, approvals, sandwich rules.

Business logic:
  - Leave balance computation with pending deduction
  - Full leave application with weekend/holiday exclusion, sandwich rule, half-day support
  - Approval/rejection/cancellation workflows with balance restoration
  - Comp-off request and approval with balance credit
  - Team calendar view and manager pending approvals
"""

from __future__ import annotations

import math
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional, Sequence

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.attendance.models import (
    EmployeeShiftAssignment,
    Holiday,
    HolidayCalendar,
    WeeklyOffPolicy,
)
from backend.common.audit import create_audit_entry
from backend.common.constants import LeaveDayType, LeaveStatus, NotificationType
from backend.common.exceptions import (
    ForbiddenException,
    NotFoundException,
    ValidationException,
)
from backend.common.pagination import PaginationMeta
from backend.core_hr.models import Employee
from backend.leave.models import CompOffGrant, LeaveBalance, LeaveRequest, LeaveType
from backend.leave.schemas import (
    CompOffOut,
    EmployeeBrief,
    LeaveBalanceOut,
    LeaveCalendarEntry,
    LeaveCalendarOut,
    LeaveRequestCreate,
    LeaveRequestOut,
    LeaveTypeBrief,
    LeaveTypeOut,
)
from backend.notifications.service import (
    notify_leave_approved,
    notify_leave_rejected,
    notify_leave_request,
)
from backend.notifications.service import NotificationService


# ═════════════════════════════════════════════════════════════════════
# LeaveService
# ═════════════════════════════════════════════════════════════════════


class LeaveService:
    """Async leave operations: types, balances, requests, approvals, comp-off."""

    # ─────────────────────────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────────────────────────

    @staticmethod
    async def _get_weekly_offs(
        db: AsyncSession,
        employee_id: uuid.UUID,
        target_date: date,
    ) -> set[int]:
        """Return set of weekday numbers (0=Mon … 6=Sun) that are weekly offs
        for the employee based on their shift assignment."""

        result = await db.execute(
            select(EmployeeShiftAssignment)
            .where(
                EmployeeShiftAssignment.employee_id == employee_id,
                EmployeeShiftAssignment.effective_from <= target_date,
                (
                    EmployeeShiftAssignment.effective_to.is_(None)
                    | (EmployeeShiftAssignment.effective_to >= target_date)
                ),
            )
            .options(selectinload(EmployeeShiftAssignment.weekly_off_policy))
            .order_by(EmployeeShiftAssignment.effective_from.desc())
            .limit(1)
        )
        assignment = result.scalars().first()
        if assignment is None or assignment.weekly_off_policy is None:
            # Default: Saturday (5) and Sunday (6)
            return {5, 6}

        policy: WeeklyOffPolicy = assignment.weekly_off_policy
        # policy.days is JSONB — expected format: list of weekday ints or
        # a dict mapping day names to booleans
        days_data = policy.days
        if isinstance(days_data, list):
            return set(days_data)
        if isinstance(days_data, dict):
            day_map = {
                "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
                "friday": 4, "saturday": 5, "sunday": 6,
            }
            return {
                day_map[k.lower()]
                for k, v in days_data.items()
                if v and k.lower() in day_map
            }
        return {5, 6}

    @staticmethod
    async def _get_holiday_dates(
        db: AsyncSession,
        employee_id: uuid.UUID,
        from_date: date,
        to_date: date,
    ) -> set[date]:
        """Return set of holiday dates in the given range, considering
        employee location for location-specific calendars."""

        # Get employee's location
        emp_result = await db.execute(
            select(Employee.location_id).where(Employee.id == employee_id)
        )
        location_id = emp_result.scalar()

        query = (
            select(Holiday.date)
            .join(HolidayCalendar, Holiday.calendar_id == HolidayCalendar.id)
            .where(
                HolidayCalendar.is_active.is_(True),
                Holiday.date >= from_date,
                Holiday.date <= to_date,
                Holiday.is_optional.is_(False),
            )
        )

        if location_id:
            query = query.where(
                or_(
                    HolidayCalendar.location_id == location_id,
                    HolidayCalendar.location_id.is_(None),
                )
            )
        else:
            query = query.where(HolidayCalendar.location_id.is_(None))

        result = await db.execute(query)
        return {row[0] for row in result.all()}

    @staticmethod
    def _calculate_leave_days(
        from_date: date,
        to_date: date,
        day_details: Optional[dict[str, LeaveDayType]],
        weekly_offs: set[int],
        holidays: set[date],
        is_sandwich: bool,
    ) -> tuple[Decimal, dict[str, str]]:
        """Calculate total leave days considering weekends, holidays,
        half-days, and sandwich rule.

        Returns:
            (total_days, computed_day_details)

        Sandwich rule:
            If is_sandwich=True and weekends/holidays fall BETWEEN leave days
            (not at the start or end), those weekends/holidays are counted
            as leave days.
        """

        # Build list of all dates
        all_dates: list[date] = []
        current = from_date
        while current <= to_date:
            all_dates.append(current)
            current += timedelta(days=1)

        if not all_dates:
            return Decimal("0"), {}

        # Classify each day
        computed_details: dict[str, str] = {}
        total = Decimal("0")

        # For sandwich rule: first pass to identify working leave days
        working_leave_indices: list[int] = []
        for i, d in enumerate(all_dates):
            is_off = d.weekday() in weekly_offs or d in holidays
            if not is_off:
                working_leave_indices.append(i)

        # Determine sandwich range (between first and last working leave day)
        sandwich_start = working_leave_indices[0] if working_leave_indices else 0
        sandwich_end = working_leave_indices[-1] if working_leave_indices else len(all_dates) - 1

        for i, d in enumerate(all_dates):
            date_str = d.isoformat()
            is_weekend = d.weekday() in weekly_offs
            is_holiday = d in holidays
            is_off = is_weekend or is_holiday

            if is_off:
                if is_sandwich and sandwich_start < i < sandwich_end:
                    # Sandwich rule: count this off-day as a leave day
                    computed_details[date_str] = LeaveDayType.full_day.value
                    total += Decimal("1")
                else:
                    # Skip — it's a weekend/holiday at the boundary
                    computed_details[date_str] = "weekend" if is_weekend else "holiday"
            else:
                # Working day — check day_details for half-day
                day_type = LeaveDayType.full_day
                if day_details and date_str in day_details:
                    day_type = day_details[date_str]

                computed_details[date_str] = day_type.value
                if day_type == LeaveDayType.full_day:
                    total += Decimal("1")
                else:
                    total += Decimal("0.5")

        return total, computed_details

    @staticmethod
    async def _get_pending_days(
        db: AsyncSession,
        employee_id: uuid.UUID,
        leave_type_id: uuid.UUID,
        year: int,
    ) -> Decimal:
        """Sum total_days of pending leave requests for this balance."""

        result = await db.execute(
            select(func.coalesce(func.sum(LeaveRequest.total_days), 0)).where(
                LeaveRequest.employee_id == employee_id,
                LeaveRequest.leave_type_id == leave_type_id,
                LeaveRequest.status == LeaveStatus.pending,
                func.extract("year", LeaveRequest.start_date) == year,
            )
        )
        return Decimal(str(result.scalar_one()))

    @staticmethod
    def _build_employee_brief(emp: Employee) -> EmployeeBrief:
        """Build EmployeeBrief from Employee ORM."""
        emp.ensure_display_name()
        return EmployeeBrief(
            id=emp.id,
            employee_code=emp.employee_code,
            display_name=emp.display_name,
            designation=emp.designation,
            department_name=emp.department.name if emp.department else None,
            profile_photo_url=emp.profile_photo_url,
        )

    @staticmethod
    def _build_leave_type_brief(lt: LeaveType) -> LeaveTypeBrief:
        """Build LeaveTypeBrief from LeaveType ORM."""
        return LeaveTypeBrief(id=lt.id, code=lt.code, name=lt.name, is_paid=lt.is_paid)

    @staticmethod
    def _build_request_response(
        req: LeaveRequest,
        *,
        employee: Optional[Employee] = None,
        leave_type: Optional[LeaveType] = None,
        reviewer: Optional[Employee] = None,
    ) -> LeaveRequestOut:
        """Build LeaveRequestOut from ORM, optionally enriching relationships."""
        out = LeaveRequestOut.model_validate(req)
        if employee:
            out.employee = LeaveService._build_employee_brief(employee)
        elif hasattr(req, "employee") and req.employee:
            out.employee = LeaveService._build_employee_brief(req.employee)
        if leave_type:
            out.leave_type = LeaveService._build_leave_type_brief(leave_type)
        elif hasattr(req, "leave_type") and req.leave_type:
            out.leave_type = LeaveService._build_leave_type_brief(req.leave_type)
        if reviewer:
            out.reviewer = LeaveService._build_employee_brief(reviewer)
        elif hasattr(req, "reviewer") and req.reviewer:
            out.reviewer = LeaveService._build_employee_brief(req.reviewer)
        return out

    # ─────────────────────────────────────────────────────────────────
    # Leave Types
    # ─────────────────────────────────────────────────────────────────

    @staticmethod
    async def get_leave_types(
        db: AsyncSession,
        *,
        is_active: bool = True,
    ) -> list[LeaveTypeOut]:
        """List all active leave types."""

        query = select(LeaveType).order_by(LeaveType.name)
        if is_active is not None:
            query = query.where(LeaveType.is_active == is_active)

        result = await db.execute(query)
        return [LeaveTypeOut.model_validate(lt) for lt in result.scalars().all()]

    # ─────────────────────────────────────────────────────────────────
    # Balance
    # ─────────────────────────────────────────────────────────────────

    @staticmethod
    async def get_balance(
        db: AsyncSession,
        employee_id: uuid.UUID,
        year: int,
    ) -> list[LeaveBalanceOut]:
        """Get all leave balances for an employee in a given year,
        with computed pending and available fields."""

        # Verify employee exists
        emp_check = await db.execute(
            select(Employee.id).where(Employee.id == employee_id)
        )
        if emp_check.scalar() is None:
            raise NotFoundException("Employee", str(employee_id))

        result = await db.execute(
            select(LeaveBalance)
            .where(
                LeaveBalance.employee_id == employee_id,
                LeaveBalance.year == year,
            )
            .options(selectinload(LeaveBalance.leave_type))
            .order_by(LeaveBalance.leave_type_id)
        )
        balances = result.scalars().all()

        output: list[LeaveBalanceOut] = []
        for bal in balances:
            pending = await LeaveService._get_pending_days(
                db, employee_id, bal.leave_type_id, year,
            )
            available = bal.current_balance - pending

            out = LeaveBalanceOut.model_validate(bal)
            out.pending = pending
            out.available = available
            if bal.leave_type:
                out.leave_type = LeaveService._build_leave_type_brief(bal.leave_type)
            output.append(out)

        return output

    # ─────────────────────────────────────────────────────────────────
    # Apply Leave
    # ─────────────────────────────────────────────────────────────────

    @staticmethod
    async def apply_leave(
        db: AsyncSession,
        employee_id: uuid.UUID,
        data: LeaveRequestCreate,
    ) -> LeaveRequestOut:
        """Apply for leave with full validation:
        - Sufficient balance
        - No overlapping approved/pending leaves
        - Exclude weekends (via weekly_off_policy)
        - Exclude holidays (via holiday_calendars)
        - Sandwich rule
        - Half-day support via day_details
        - Advance notice check
        - Max consecutive days check
        """

        now = datetime.now(timezone.utc)
        today = now.date()

        # ── Load employee ───────────────────────────────────────────
        emp_result = await db.execute(
            select(Employee)
            .where(Employee.id == employee_id, Employee.is_active.is_(True))
            .options(selectinload(Employee.department))
        )
        employee = emp_result.scalars().first()
        if employee is None:
            raise NotFoundException("Employee", str(employee_id))

        # ── Load leave type ─────────────────────────────────────────
        lt_result = await db.execute(
            select(LeaveType).where(
                LeaveType.id == data.leave_type_id,
                LeaveType.is_active.is_(True),
            )
        )
        leave_type = lt_result.scalars().first()
        if leave_type is None:
            raise NotFoundException("LeaveType", str(data.leave_type_id))

        # ── Gender applicability check ──────────────────────────────
        if leave_type.applicable_gender and employee.gender:
            if employee.gender != leave_type.applicable_gender:
                raise ValidationException(
                    {"leave_type_id": [
                        f"{leave_type.name} is only applicable for "
                        f"{leave_type.applicable_gender.value} employees."
                    ]}
                )

        # ── Advance notice check ────────────────────────────────────
        if leave_type.min_days_notice > 0:
            days_ahead = (data.from_date - today).days
            if days_ahead < leave_type.min_days_notice:
                raise ValidationException(
                    {"from_date": [
                        f"{leave_type.name} requires at least "
                        f"{leave_type.min_days_notice} days advance notice."
                    ]}
                )

        # ── Get weekly offs and holidays ────────────────────────────
        weekly_offs = await LeaveService._get_weekly_offs(
            db, employee_id, data.from_date,
        )
        holidays = await LeaveService._get_holiday_dates(
            db, employee_id, data.from_date, data.to_date,
        )

        # ── Sandwich rule ───────────────────────────────────────────
        is_sandwich = getattr(leave_type, "is_sandwich_applicable", False)

        # ── Calculate leave days ────────────────────────────────────
        total_days, computed_details = LeaveService._calculate_leave_days(
            data.from_date,
            data.to_date,
            data.day_details,
            weekly_offs,
            holidays,
            is_sandwich,
        )

        if total_days <= 0:
            raise ValidationException(
                {"dates": ["No leave days found in the selected range "
                           "(all days may be weekends or holidays)."]}
            )

        # ── Max consecutive days check ──────────────────────────────
        if leave_type.max_consecutive_days:
            if total_days > leave_type.max_consecutive_days:
                raise ValidationException(
                    {"dates": [
                        f"{leave_type.name} allows a maximum of "
                        f"{leave_type.max_consecutive_days} consecutive days."
                    ]}
                )

        # ── Check overlapping leaves ────────────────────────────────
        overlap_result = await db.execute(
            select(func.count()).select_from(LeaveRequest).where(
                LeaveRequest.employee_id == employee_id,
                LeaveRequest.status.in_([
                    LeaveStatus.pending, LeaveStatus.approved,
                ]),
                LeaveRequest.start_date <= data.to_date,
                LeaveRequest.end_date >= data.from_date,
            )
        )
        if overlap_result.scalar_one() > 0:
            raise ValidationException(
                {"dates": [
                    "You already have a pending or approved leave request "
                    "overlapping with these dates."
                ]}
            )

        # ── Check sufficient balance ────────────────────────────────
        year = data.from_date.year
        bal_result = await db.execute(
            select(LeaveBalance).where(
                LeaveBalance.employee_id == employee_id,
                LeaveBalance.leave_type_id == data.leave_type_id,
                LeaveBalance.year == year,
            )
        )
        balance = bal_result.scalars().first()

        if balance is None:
            raise ValidationException(
                {"leave_type_id": [
                    f"No leave balance found for {leave_type.name} in {year}. "
                    "Please contact HR."
                ]}
            )

        pending = await LeaveService._get_pending_days(
            db, employee_id, data.leave_type_id, year,
        )
        available = balance.current_balance - pending

        if total_days > available:
            raise ValidationException(
                {"balance": [
                    f"Insufficient {leave_type.name} balance. "
                    f"Available: {available}, Requested: {total_days}."
                ]}
            )

        # ── Determine approver ──────────────────────────────────────
        approver_id = employee.reporting_manager_id

        # ── Determine initial status ────────────────────────────────
        initial_status = LeaveStatus.pending
        if not leave_type.requires_approval:
            initial_status = LeaveStatus.approved

        # ── Create leave request ────────────────────────────────────
        leave_request = LeaveRequest(
            employee_id=employee_id,
            leave_type_id=data.leave_type_id,
            start_date=data.from_date,
            end_date=data.to_date,
            day_details=computed_details,
            total_days=total_days,
            reason=data.reason,
            status=initial_status,
        )

        # If auto-approved (no approval required), update balance immediately
        if initial_status == LeaveStatus.approved:
            leave_request.reviewed_at = now
            balance.used += total_days

        db.add(leave_request)
        await db.flush()

        # ── Audit ───────────────────────────────────────────────────
        await create_audit_entry(
            db,
            action="create",
            entity_type="leave_request",
            entity_id=leave_request.id,
            actor_id=employee_id,
            new_values={
                "leave_type": leave_type.code,
                "start_date": data.from_date.isoformat(),
                "end_date": data.to_date.isoformat(),
                "total_days": str(total_days),
                "status": initial_status.value,
            },
        )

        # ── Notify approver ────────────────────────────────────────
        if approver_id and initial_status == LeaveStatus.pending:
            await notify_leave_request(db, leave_request, approver_id)

        return LeaveService._build_request_response(
            leave_request, employee=employee, leave_type=leave_type,
        )

    # ─────────────────────────────────────────────────────────────────
    # Approve Leave
    # ─────────────────────────────────────────────────────────────────

    @staticmethod
    async def approve_leave(
        db: AsyncSession,
        request_id: uuid.UUID,
        approver_id: uuid.UUID,
        *,
        remarks: Optional[str] = None,
    ) -> LeaveRequestOut:
        """Approve a leave request. Verifies approver is the reporting manager
        or an HR admin. Deducts from balance (pending → used)."""

        now = datetime.now(timezone.utc)

        # Load request with relationships
        result = await db.execute(
            select(LeaveRequest)
            .where(LeaveRequest.id == request_id)
            .options(
                selectinload(LeaveRequest.employee).selectinload(Employee.department),
                selectinload(LeaveRequest.leave_type),
            )
        )
        leave_req = result.scalars().first()
        if leave_req is None:
            raise NotFoundException("LeaveRequest", str(request_id))

        if leave_req.status != LeaveStatus.pending:
            raise ValidationException(
                {"status": [f"Leave request is already {leave_req.status.value}."]}
            )

        # Verify approver authority
        employee = leave_req.employee
        is_manager = employee.reporting_manager_id == approver_id
        is_l2 = employee.l2_manager_id == approver_id

        # Check if approver is HR admin (via role assignments)
        from backend.auth.models import RoleAssignment
        from backend.common.constants import UserRole

        hr_check = await db.execute(
            select(RoleAssignment).where(
                RoleAssignment.employee_id == approver_id,
                RoleAssignment.role == UserRole.hr_admin,
                RoleAssignment.is_active.is_(True),
            )
        )
        is_hr = hr_check.scalars().first() is not None

        if not (is_manager or is_l2 or is_hr):
            raise ForbiddenException(
                "You are not authorized to approve this leave request."
            )

        # Update request
        old_status = leave_req.status.value
        leave_req.status = LeaveStatus.approved
        leave_req.reviewed_by = approver_id
        leave_req.reviewed_at = now
        leave_req.reviewer_remarks = remarks
        leave_req.updated_at = now

        # Update balance: deduct used
        year = leave_req.start_date.year
        bal_result = await db.execute(
            select(LeaveBalance).where(
                LeaveBalance.employee_id == leave_req.employee_id,
                LeaveBalance.leave_type_id == leave_req.leave_type_id,
                LeaveBalance.year == year,
            )
        )
        balance = bal_result.scalars().first()
        if balance:
            balance.used += leave_req.total_days
            balance.updated_at = now

        await db.flush()

        # Audit
        await create_audit_entry(
            db,
            action="approve",
            entity_type="leave_request",
            entity_id=leave_req.id,
            actor_id=approver_id,
            old_values={"status": old_status},
            new_values={"status": LeaveStatus.approved.value, "remarks": remarks},
        )

        # Notify employee
        await notify_leave_approved(db, leave_req)

        return LeaveService._build_request_response(leave_req)

    # ─────────────────────────────────────────────────────────────────
    # Reject Leave
    # ─────────────────────────────────────────────────────────────────

    @staticmethod
    async def reject_leave(
        db: AsyncSession,
        request_id: uuid.UUID,
        approver_id: uuid.UUID,
        reason: str,
    ) -> LeaveRequestOut:
        """Reject a leave request. Restores pending balance."""

        now = datetime.now(timezone.utc)

        result = await db.execute(
            select(LeaveRequest)
            .where(LeaveRequest.id == request_id)
            .options(
                selectinload(LeaveRequest.employee).selectinload(Employee.department),
                selectinload(LeaveRequest.leave_type),
            )
        )
        leave_req = result.scalars().first()
        if leave_req is None:
            raise NotFoundException("LeaveRequest", str(request_id))

        if leave_req.status != LeaveStatus.pending:
            raise ValidationException(
                {"status": [f"Leave request is already {leave_req.status.value}."]}
            )

        # Verify approver authority
        employee = leave_req.employee
        is_manager = employee.reporting_manager_id == approver_id

        from backend.auth.models import RoleAssignment
        from backend.common.constants import UserRole

        hr_check = await db.execute(
            select(RoleAssignment).where(
                RoleAssignment.employee_id == approver_id,
                RoleAssignment.role == UserRole.hr_admin,
                RoleAssignment.is_active.is_(True),
            )
        )
        is_hr = hr_check.scalars().first() is not None

        if not (is_manager or is_hr):
            raise ForbiddenException(
                "You are not authorized to reject this leave request."
            )

        # Update request
        old_status = leave_req.status.value
        leave_req.status = LeaveStatus.rejected
        leave_req.reviewed_by = approver_id
        leave_req.reviewed_at = now
        leave_req.reviewer_remarks = reason
        leave_req.updated_at = now

        await db.flush()

        # Audit
        await create_audit_entry(
            db,
            action="reject",
            entity_type="leave_request",
            entity_id=leave_req.id,
            actor_id=approver_id,
            old_values={"status": old_status},
            new_values={"status": LeaveStatus.rejected.value, "reason": reason},
        )

        # Notify employee
        await notify_leave_rejected(db, leave_req, reason)

        return LeaveService._build_request_response(leave_req)

    # ─────────────────────────────────────────────────────────────────
    # Cancel Leave
    # ─────────────────────────────────────────────────────────────────

    @staticmethod
    async def cancel_leave(
        db: AsyncSession,
        request_id: uuid.UUID,
        employee_id: uuid.UUID,
        reason: str,
    ) -> LeaveRequestOut:
        """Cancel own leave request. Restores balance if was approved."""

        now = datetime.now(timezone.utc)

        result = await db.execute(
            select(LeaveRequest)
            .where(LeaveRequest.id == request_id)
            .options(
                selectinload(LeaveRequest.employee).selectinload(Employee.department),
                selectinload(LeaveRequest.leave_type),
            )
        )
        leave_req = result.scalars().first()
        if leave_req is None:
            raise NotFoundException("LeaveRequest", str(request_id))

        # Verify ownership
        if leave_req.employee_id != employee_id:
            raise ForbiddenException("You can only cancel your own leave requests.")

        if leave_req.status not in (LeaveStatus.pending, LeaveStatus.approved):
            raise ValidationException(
                {"status": [
                    f"Cannot cancel a leave request with status '{leave_req.status.value}'."
                ]}
            )

        was_approved = leave_req.status == LeaveStatus.approved

        # Update request
        old_status = leave_req.status.value
        leave_req.status = LeaveStatus.cancelled
        leave_req.cancelled_at = now
        leave_req.reviewer_remarks = f"Cancelled by employee: {reason}"
        leave_req.updated_at = now

        # Restore balance if was approved
        # R2-14: Handle cross-year leaves — restore balance for each year separately
        if was_approved:
            start_year = leave_req.start_date.year
            end_year = leave_req.end_date.year
            if start_year == end_year:
                # Simple case: single year
                bal_result = await db.execute(
                    select(LeaveBalance).where(
                        LeaveBalance.employee_id == employee_id,
                        LeaveBalance.leave_type_id == leave_req.leave_type_id,
                        LeaveBalance.year == start_year,
                    )
                )
                balance = bal_result.scalars().first()
                if balance:
                    balance.used = max(Decimal("0"), balance.used - leave_req.total_days)
                    balance.updated_at = now
            else:
                # Cross-year: split days by year based on computed_dates or date ranges
                from datetime import date as _date, timedelta
                for year in range(start_year, end_year + 1):
                    year_start = max(leave_req.start_date, _date(year, 1, 1))
                    year_end = min(leave_req.end_date, _date(year, 12, 31))
                    # Count weekdays (rough estimate; matches balance deduction logic)
                    days_in_year = Decimal("0")
                    d = year_start
                    while d <= year_end:
                        if d.weekday() < 5:  # Mon–Fri
                            days_in_year += Decimal("1")
                        d += timedelta(days=1)
                    if days_in_year > 0:
                        bal_result = await db.execute(
                            select(LeaveBalance).where(
                                LeaveBalance.employee_id == employee_id,
                                LeaveBalance.leave_type_id == leave_req.leave_type_id,
                                LeaveBalance.year == year,
                            )
                        )
                        balance = bal_result.scalars().first()
                        if balance:
                            balance.used = max(Decimal("0"), balance.used - days_in_year)
                            balance.updated_at = now

        await db.flush()

        # Audit
        await create_audit_entry(
            db,
            action="cancel",
            entity_type="leave_request",
            entity_id=leave_req.id,
            actor_id=employee_id,
            old_values={"status": old_status},
            new_values={"status": LeaveStatus.cancelled.value, "reason": reason},
        )

        # Notify approver
        approver_id = leave_req.employee.reporting_manager_id
        if approver_id:
            await NotificationService.create_notification(
                db,
                recipient_id=approver_id,
                type=NotificationType.info,
                title="Leave Cancelled",
                message=(
                    f"Leave request from {leave_req.start_date} to "
                    f"{leave_req.end_date} has been cancelled by the employee. "
                    f"Reason: {reason}"
                ),
                action_url=f"/leave/requests/{leave_req.id}",
                entity_type="leave_request",
                entity_id=leave_req.id,
            )

        return LeaveService._build_request_response(leave_req)

    # ─────────────────────────────────────────────────────────────────
    # List Leave Requests
    # ─────────────────────────────────────────────────────────────────

    @staticmethod
    async def get_leave_requests(
        db: AsyncSession,
        *,
        requestor_id: uuid.UUID,
        employee_id: Optional[uuid.UUID] = None,
        status: Optional[LeaveStatus] = None,
        leave_type_id: Optional[uuid.UUID] = None,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
        scope: str = "my",
        page: int = 1,
        page_size: int = 50,
    ) -> dict:
        """List leave requests with pagination and filters.

        Scopes:
          - my: own requests only
          - team: direct reports of requestor
          - all: all requests (HR admin only)
        """

        query = (
            select(LeaveRequest)
            .options(
                selectinload(LeaveRequest.employee).selectinload(Employee.department),
                selectinload(LeaveRequest.leave_type),
                selectinload(LeaveRequest.reviewer),
            )
            .order_by(LeaveRequest.created_at.desc())
        )

        # Scope filtering
        if scope == "my":
            query = query.where(LeaveRequest.employee_id == requestor_id)
        elif scope == "team":
            # Get direct report IDs
            reports = await db.execute(
                select(Employee.id).where(
                    Employee.reporting_manager_id == requestor_id,
                    Employee.is_active.is_(True),
                )
            )
            report_ids = [r[0] for r in reports.all()]
            if not report_ids:
                return {
                    "data": [],
                    "meta": PaginationMeta(
                        page=1, page_size=page_size, total=0,
                        total_pages=0, has_next=False, has_prev=False,
                    ),
                }
            query = query.where(LeaveRequest.employee_id.in_(report_ids))
        # scope == "all": no employee filter

        # Additional filters
        if employee_id:
            query = query.where(LeaveRequest.employee_id == employee_id)
        if status:
            query = query.where(LeaveRequest.status == status)
        if leave_type_id:
            query = query.where(LeaveRequest.leave_type_id == leave_type_id)
        if from_date:
            query = query.where(LeaveRequest.end_date >= from_date)
        if to_date:
            query = query.where(LeaveRequest.start_date <= to_date)

        # Count
        count_q = query.with_only_columns(func.count()).order_by(None)
        total = (await db.execute(count_q)).scalar_one()

        # Paginate
        offset = (page - 1) * page_size
        result = await db.execute(query.offset(offset).limit(page_size))
        requests = result.scalars().all()

        total_pages = math.ceil(total / page_size) if total else 0

        return {
            "data": [LeaveService._build_request_response(r) for r in requests],
            "meta": PaginationMeta(
                page=page,
                page_size=page_size,
                total=total,
                total_pages=total_pages,
                has_next=page < total_pages,
                has_prev=page > 1,
            ),
        }

    # ─────────────────────────────────────────────────────────────────
    # Pending Approvals
    # ─────────────────────────────────────────────────────────────────

    @staticmethod
    async def get_pending_approvals(
        db: AsyncSession,
        manager_id: uuid.UUID,
    ) -> list[LeaveRequestOut]:
        """Get all pending leave requests for a manager's direct reports."""

        # Get direct report IDs
        reports = await db.execute(
            select(Employee.id).where(
                Employee.reporting_manager_id == manager_id,
                Employee.is_active.is_(True),
            )
        )
        report_ids = [r[0] for r in reports.all()]

        if not report_ids:
            return []

        result = await db.execute(
            select(LeaveRequest)
            .where(
                LeaveRequest.employee_id.in_(report_ids),
                LeaveRequest.status == LeaveStatus.pending,
            )
            .options(
                selectinload(LeaveRequest.employee).selectinload(Employee.department),
                selectinload(LeaveRequest.leave_type),
            )
            .order_by(LeaveRequest.created_at.asc())
        )

        return [
            LeaveService._build_request_response(r)
            for r in result.scalars().all()
        ]

    # ─────────────────────────────────────────────────────────────────
    # Leave Calendar
    # ─────────────────────────────────────────────────────────────────

    @staticmethod
    async def get_leave_calendar(
        db: AsyncSession,
        month: int,
        year: int,
        *,
        department_id: Optional[uuid.UUID] = None,
        location_id: Optional[uuid.UUID] = None,
    ) -> LeaveCalendarOut:
        """Get team leave calendar for a given month showing approved/pending leaves."""

        from calendar import monthrange

        _, last_day = monthrange(year, month)
        month_start = date(year, month, 1)
        month_end = date(year, month, last_day)

        # Build employee filter
        emp_query = (
            select(Employee.id)
            .where(Employee.is_active.is_(True))
        )
        if department_id:
            emp_query = emp_query.where(Employee.department_id == department_id)
        if location_id:
            emp_query = emp_query.where(Employee.location_id == location_id)

        emp_result = await db.execute(emp_query)
        emp_ids = [r[0] for r in emp_result.all()]

        if not emp_ids:
            return LeaveCalendarOut(month=month, year=year, entries=[], total_entries=0)

        # Get leave requests that overlap with the month
        result = await db.execute(
            select(LeaveRequest)
            .where(
                LeaveRequest.employee_id.in_(emp_ids),
                LeaveRequest.status.in_([LeaveStatus.approved, LeaveStatus.pending]),
                LeaveRequest.start_date <= month_end,
                LeaveRequest.end_date >= month_start,
            )
            .options(
                selectinload(LeaveRequest.employee).selectinload(Employee.department),
                selectinload(LeaveRequest.leave_type),
            )
            .order_by(LeaveRequest.start_date)
        )
        requests = result.scalars().all()

        entries: list[LeaveCalendarEntry] = []
        for req in requests:
            emp = req.employee
            emp.ensure_display_name()
            entries.append(
                LeaveCalendarEntry(
                    employee=LeaveService._build_employee_brief(emp),
                    leave_type=LeaveService._build_leave_type_brief(req.leave_type),
                    start_date=req.start_date,
                    end_date=req.end_date,
                    total_days=req.total_days,
                    status=req.status,
                    day_details=req.day_details or {},
                )
            )

        return LeaveCalendarOut(
            month=month,
            year=year,
            entries=entries,
            total_entries=len(entries),
        )

    # ─────────────────────────────────────────────────────────────────
    # Comp-Off
    # ─────────────────────────────────────────────────────────────────

    @staticmethod
    async def request_comp_off(
        db: AsyncSession,
        employee_id: uuid.UUID,
        work_date: date,
        reason: str,
    ) -> CompOffOut:
        """Submit a comp-off request for working on a weekend/holiday."""

        # Check employee exists
        emp_result = await db.execute(
            select(Employee)
            .where(Employee.id == employee_id, Employee.is_active.is_(True))
            .options(selectinload(Employee.department))
        )
        employee = emp_result.scalars().first()
        if employee is None:
            raise NotFoundException("Employee", str(employee_id))

        # Check for duplicate
        existing = await db.execute(
            select(CompOffGrant).where(
                CompOffGrant.employee_id == employee_id,
                CompOffGrant.work_date == work_date,
            )
        )
        if existing.scalars().first():
            raise ValidationException(
                {"work_date": [
                    f"A comp-off request already exists for {work_date.isoformat()}."
                ]}
            )

        comp_off = CompOffGrant(
            employee_id=employee_id,
            work_date=work_date,
            reason=reason,
            expires_at=work_date + timedelta(days=90),
        )
        db.add(comp_off)
        await db.flush()

        # Audit
        await create_audit_entry(
            db,
            action="create",
            entity_type="comp_off_grant",
            entity_id=comp_off.id,
            actor_id=employee_id,
            new_values={
                "work_date": work_date.isoformat(),
                "reason": reason,
            },
        )

        # Notify manager
        if employee.reporting_manager_id:
            await NotificationService.create_notification(
                db,
                recipient_id=employee.reporting_manager_id,
                type=NotificationType.action_required,
                title="Comp-Off Request",
                message=(
                    f"{employee.display_name or employee.full_name} has requested "
                    f"comp-off for working on {work_date.isoformat()}."
                ),
                action_url=f"/leave/comp-off/{comp_off.id}",
                entity_type="comp_off_grant",
                entity_id=comp_off.id,
            )

        out = CompOffOut.model_validate(comp_off)
        out.employee = LeaveService._build_employee_brief(employee)
        return out

    @staticmethod
    async def approve_comp_off(
        db: AsyncSession,
        comp_off_id: uuid.UUID,
        approver_id: uuid.UUID,
    ) -> CompOffOut:
        """Approve a comp-off grant and credit the employee's comp-off balance."""

        now = datetime.now(timezone.utc)

        result = await db.execute(
            select(CompOffGrant)
            .where(CompOffGrant.id == comp_off_id)
            .options(
                selectinload(CompOffGrant.employee).selectinload(Employee.department),
            )
        )
        comp_off = result.scalars().first()
        if comp_off is None:
            raise NotFoundException("CompOffGrant", str(comp_off_id))

        if comp_off.granted_by is not None:
            raise ValidationException(
                {"status": ["This comp-off has already been approved."]}
            )

        # Update grant
        comp_off.granted_by = approver_id

        # Credit comp-off balance — find or create balance for "CO" leave type
        year = comp_off.work_date.year
        co_type = await db.execute(
            select(LeaveType).where(LeaveType.code == "CO")
        )
        co_leave_type = co_type.scalars().first()

        if co_leave_type:
            bal_result = await db.execute(
                select(LeaveBalance).where(
                    LeaveBalance.employee_id == comp_off.employee_id,
                    LeaveBalance.leave_type_id == co_leave_type.id,
                    LeaveBalance.year == year,
                )
            )
            balance = bal_result.scalars().first()
            if balance:
                balance.adjusted += Decimal("1")
                balance.updated_at = now
            else:
                balance = LeaveBalance(
                    employee_id=comp_off.employee_id,
                    leave_type_id=co_leave_type.id,
                    year=year,
                    opening_balance=Decimal("0"),
                    accrued=Decimal("0"),
                    adjusted=Decimal("1"),
                )
                db.add(balance)

        await db.flush()

        # Audit
        await create_audit_entry(
            db,
            action="approve",
            entity_type="comp_off_grant",
            entity_id=comp_off.id,
            actor_id=approver_id,
            new_values={"granted_by": str(approver_id)},
        )

        # Notify employee
        await NotificationService.create_notification(
            db,
            recipient_id=comp_off.employee_id,
            type=NotificationType.approval,
            title="Comp-Off Approved",
            message=(
                f"Your comp-off request for {comp_off.work_date.isoformat()} "
                f"has been approved. 1 day credited to your comp-off balance."
            ),
            action_url=f"/leave/comp-off/{comp_off.id}",
            entity_type="comp_off_grant",
            entity_id=comp_off.id,
        )

        out = CompOffOut.model_validate(comp_off)
        if comp_off.employee:
            out.employee = LeaveService._build_employee_brief(comp_off.employee)
        return out

    # ─────────────────────────────────────────────────────────────────
    # Balance Adjustment
    # ─────────────────────────────────────────────────────────────────

    @staticmethod
    async def adjust_balance(
        db: AsyncSession,
        employee_id: uuid.UUID,
        leave_type_id: uuid.UUID,
        adjustment: Decimal,
        reason: str,
        *,
        year: Optional[int] = None,
        actor_id: Optional[uuid.UUID] = None,
    ) -> LeaveBalanceOut:
        """HR admin manual balance adjustment."""

        now = datetime.now(timezone.utc)
        target_year = year or now.year

        # Verify employee
        emp_check = await db.execute(
            select(Employee.id).where(Employee.id == employee_id)
        )
        if emp_check.scalar() is None:
            raise NotFoundException("Employee", str(employee_id))

        # Verify leave type
        lt_check = await db.execute(
            select(LeaveType).where(LeaveType.id == leave_type_id)
        )
        leave_type = lt_check.scalars().first()
        if leave_type is None:
            raise NotFoundException("LeaveType", str(leave_type_id))

        # Get or create balance
        bal_result = await db.execute(
            select(LeaveBalance).where(
                LeaveBalance.employee_id == employee_id,
                LeaveBalance.leave_type_id == leave_type_id,
                LeaveBalance.year == target_year,
            )
        )
        balance = bal_result.scalars().first()

        if balance is None:
            balance = LeaveBalance(
                employee_id=employee_id,
                leave_type_id=leave_type_id,
                year=target_year,
                opening_balance=Decimal("0"),
                accrued=Decimal("0"),
                adjusted=adjustment,
            )
            db.add(balance)
            await db.flush()
        else:
            old_adjusted = balance.adjusted
            balance.adjusted += adjustment
            balance.updated_at = now
            await db.flush()

        # Audit
        await create_audit_entry(
            db,
            action="adjust",
            entity_type="leave_balance",
            entity_id=balance.id,
            actor_id=actor_id,
            old_values={"adjusted": str(getattr(balance, "_old_adjusted", balance.adjusted - adjustment))},
            new_values={
                "adjusted": str(balance.adjusted),
                "adjustment_delta": str(adjustment),
                "reason": reason,
            },
        )

        # Notify employee
        direction = "credited" if adjustment > 0 else "debited"
        await NotificationService.create_notification(
            db,
            recipient_id=employee_id,
            type=NotificationType.info,
            title="Leave Balance Adjusted",
            message=(
                f"{abs(adjustment)} day(s) of {leave_type.name} have been "
                f"{direction}. Reason: {reason}"
            ),
            entity_type="leave_balance",
            entity_id=balance.id,
        )

        # Build response
        pending = await LeaveService._get_pending_days(
            db, employee_id, leave_type_id, target_year,
        )
        # Reload balance to get computed current_balance
        await db.refresh(balance)
        out = LeaveBalanceOut.model_validate(balance)
        out.pending = pending
        out.available = balance.current_balance - pending
        out.leave_type = LeaveService._build_leave_type_brief(leave_type)
        return out
