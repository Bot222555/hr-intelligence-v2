"""Attendance service layer — clock in/out, late detection, regularization.

Business logic:
  - Clock in/out with shift-aware arrival status
  - Hours calculation with lunch break deduction
  - Attendance regularization workflow (submit → approve/reject)
  - Read operations for self, team, and admin views
"""

from __future__ import annotations

import math
import uuid
from datetime import date, datetime, time, timedelta, timezone
from typing import Optional, Sequence

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.attendance.models import (
    AttendanceRecord,
    AttendanceRegularization,
    ClockEntry,
    EmployeeShiftAssignment,
    Holiday,
    HolidayCalendar,
    ShiftPolicy,
)
from backend.attendance.schemas import (
    AttendanceListResponse,
    AttendanceRecordResponse,
    AttendanceSummary,
    ClockResponse,
    EmployeeBrief,
    HolidayResponse,
    RegularizationResponse,
    ShiftBrief,
    ShiftPolicyResponse,
    TodayAttendanceItem,
    TodayAttendanceResponse,
    TodaySummary,
)
from backend.common.audit import create_audit_entry
from backend.common.constants import (
    ArrivalStatus,
    AttendanceStatus,
    RegularizationStatus,
)
from backend.common.exceptions import (
    ConflictError,
    NotFoundException,
    ValidationException,
)
from backend.common.pagination import PaginationMeta
from backend.core_hr.models import Employee

# ── Constants ───────────────────────────────────────────────────────

LATE_THRESHOLD_MINUTES = 30
VERY_LATE_THRESHOLD_MINUTES = 60
HALF_DAY_THRESHOLD_MINUTES = 120
LUNCH_BREAK_HOURS = 1.0
MAX_DATE_RANGE_DAYS = 90


# ═════════════════════════════════════════════════════════════════════
# AttendanceService
# ═════════════════════════════════════════════════════════════════════


class AttendanceService:
    """Async attendance operations: clock, read, regularize."""

    # ── Helpers ─────────────────────────────────────────────────────

    @staticmethod
    async def _get_shift_for_employee(
        db: AsyncSession,
        employee_id: uuid.UUID,
        target_date: date,
    ) -> Optional[ShiftPolicy]:
        """Resolve the active shift policy for an employee on a given date."""

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
            .options(selectinload(EmployeeShiftAssignment.shift_policy))
            .order_by(EmployeeShiftAssignment.effective_from.desc())
            .limit(1)
        )
        assignment = result.scalars().first()
        return assignment.shift_policy if assignment else None

    @staticmethod
    def _determine_arrival_status(
        clock_in_time: datetime,
        shift: Optional[ShiftPolicy],
    ) -> ArrivalStatus:
        """Compare clock-in time against shift start + grace to determine arrival status."""

        if shift is None:
            return ArrivalStatus.on_time

        shift_start = datetime.combine(
            clock_in_time.date(),
            shift.start_time,
            tzinfo=clock_in_time.tzinfo,
        )
        grace_end = shift_start + timedelta(minutes=shift.grace_minutes)
        diff_minutes = (clock_in_time - shift_start).total_seconds() / 60

        if clock_in_time <= grace_end:
            return ArrivalStatus.on_time
        if diff_minutes <= LATE_THRESHOLD_MINUTES:
            return ArrivalStatus.late
        if diff_minutes <= VERY_LATE_THRESHOLD_MINUTES:
            return ArrivalStatus.very_late
        return ArrivalStatus.very_late

    @staticmethod
    def _calculate_hours(
        first_in: datetime,
        last_out: datetime,
        shift: Optional[ShiftPolicy],
    ) -> tuple[float, float, float, AttendanceStatus]:
        """Calculate total, effective, overtime hours and determine attendance status.

        Returns:
            (total_hours, effective_hours, overtime_hours, status)
        """

        total_seconds = (last_out - first_in).total_seconds()
        total_hours = round(total_seconds / 3600, 2)
        effective_hours = round(max(0, total_hours - LUNCH_BREAK_HOURS), 2)

        min_hours_full_day = (shift.full_day_minutes / 60) if shift else 8.0
        min_hours_half_day = (shift.half_day_minutes / 60) if shift else 4.0

        overtime_hours = round(max(0, effective_hours - min_hours_full_day), 2)

        if effective_hours < min_hours_half_day:
            status = AttendanceStatus.absent
        elif effective_hours < min_hours_full_day:
            status = AttendanceStatus.half_day
        else:
            status = AttendanceStatus.present

        return total_hours, effective_hours, overtime_hours, status

    @staticmethod
    def _build_record_response(
        record: AttendanceRecord,
    ) -> AttendanceRecordResponse:
        """Convert an ORM AttendanceRecord to a response schema."""

        total_hours = (
            round(record.total_work_minutes / 60, 2)
            if record.total_work_minutes is not None
            else None
        )
        effective_hours = (
            round(record.effective_work_minutes / 60, 2)
            if record.effective_work_minutes is not None
            else None
        )
        overtime_hours = round(record.overtime_minutes / 60, 2) if record.overtime_minutes else 0.0

        shift_brief = None
        if record.shift_policy:
            shift_brief = ShiftBrief(
                id=record.shift_policy.id,
                name=record.shift_policy.name,
                start_time=record.shift_policy.start_time,
                end_time=record.shift_policy.end_time,
            )

        return AttendanceRecordResponse(
            id=record.id,
            date=record.date,
            first_clock_in=record.first_clock_in,
            last_clock_out=record.last_clock_out,
            total_hours=total_hours,
            effective_hours=effective_hours,
            overtime_hours=overtime_hours,
            status=record.status,
            arrival_status=record.arrival_status,
            shift=shift_brief,
            is_regularized=record.is_regularized,
            source=record.source,
            remarks=record.remarks,
        )

    @staticmethod
    def _build_summary(records: Sequence[AttendanceRecord]) -> AttendanceSummary:
        """Aggregate attendance statistics from a list of records."""

        present = absent = half_day = late = very_late = 0
        total_effective_hours = 0.0
        total_overtime = 0.0
        hours_count = 0

        for r in records:
            if r.status == AttendanceStatus.present:
                present += 1
            elif r.status == AttendanceStatus.absent:
                absent += 1
            elif r.status == AttendanceStatus.half_day:
                half_day += 1

            if r.arrival_status == ArrivalStatus.late:
                late += 1
            elif r.arrival_status == ArrivalStatus.very_late:
                very_late += 1

            if r.effective_work_minutes is not None:
                total_effective_hours += r.effective_work_minutes / 60
                hours_count += 1
            if r.overtime_minutes:
                total_overtime += r.overtime_minutes / 60

        avg_hours = round(total_effective_hours / hours_count, 2) if hours_count else 0.0

        return AttendanceSummary(
            present=present,
            absent=absent,
            half_day=half_day,
            late=late,
            very_late=very_late,
            avg_hours=avg_hours,
            total_overtime=round(total_overtime, 2),
        )

    @staticmethod
    def _validate_date_range(from_date: date, to_date: date) -> None:
        """Ensure date range is valid and within MAX_DATE_RANGE_DAYS."""

        if from_date > to_date:
            raise ValidationException(
                {"date_range": ["from_date must be before or equal to to_date."]}
            )
        if (to_date - from_date).days > MAX_DATE_RANGE_DAYS:
            raise ValidationException(
                {"date_range": [f"Date range cannot exceed {MAX_DATE_RANGE_DAYS} days."]}
            )

    # ── Clock in ────────────────────────────────────────────────────

    @staticmethod
    async def clock_in(
        db: AsyncSession,
        employee_id: uuid.UUID,
        *,
        source: str = "web",
        ip_address: Optional[str] = None,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
    ) -> ClockResponse:
        """Record a clock-in event. Creates or updates today's AttendanceRecord."""

        now = datetime.now(timezone.utc)
        today = now.date()

        # Check for existing open clock entry (already clocked in, not out)
        existing_open = await db.execute(
            select(ClockEntry).where(
                ClockEntry.employee_id == employee_id,
                func.date(ClockEntry.clock_in) == today,
                ClockEntry.clock_out.is_(None),
            )
        )
        if existing_open.scalars().first():
            raise ConflictError("clock_in", "Already clocked in today without clocking out.")

        # Get or create attendance record for today
        result = await db.execute(
            select(AttendanceRecord)
            .where(
                AttendanceRecord.employee_id == employee_id,
                AttendanceRecord.date == today,
            )
            .options(selectinload(AttendanceRecord.shift_policy))
        )
        attendance = result.scalars().first()

        # Resolve shift
        shift = await AttendanceService._get_shift_for_employee(db, employee_id, today)

        if attendance is None:
            attendance = AttendanceRecord(
                employee_id=employee_id,
                date=today,
                status=AttendanceStatus.present,
                shift_policy_id=shift.id if shift else None,
                first_clock_in=now,
                source=source,
            )
            db.add(attendance)
            await db.flush()

        # Determine arrival status only on first clock-in of the day
        if attendance.first_clock_in is None or attendance.first_clock_in == now:
            arrival = AttendanceService._determine_arrival_status(now, shift)
            attendance.first_clock_in = now
            attendance.arrival_status = arrival
            attendance.status = AttendanceStatus.present

            # If > half_day_threshold late, mark half_day
            if shift:
                shift_start = datetime.combine(today, shift.start_time, tzinfo=now.tzinfo)
                diff_minutes = (now - shift_start).total_seconds() / 60
                if diff_minutes > HALF_DAY_THRESHOLD_MINUTES:
                    attendance.status = AttendanceStatus.half_day
        else:
            arrival = attendance.arrival_status

        # Create clock entry
        clock_entry = ClockEntry(
            employee_id=employee_id,
            attendance_record_id=attendance.id,
            clock_in=now,
            source=source,
            ip_address=ip_address,
        )
        db.add(clock_entry)
        await db.flush()

        # Audit
        await create_audit_entry(
            db,
            action="clock_in",
            entity_type="attendance_record",
            entity_id=attendance.id,
            actor_id=employee_id,
            new_values={
                "clock_entry_id": str(clock_entry.id),
                "source": source,
                "timestamp": now.isoformat(),
            },
            ip_address=ip_address,
        )

        return ClockResponse(
            clock_entry_id=clock_entry.id,
            attendance_id=attendance.id,
            timestamp=now,
            status=attendance.status,
            arrival_status=arrival,
        )

    # ── Clock out ───────────────────────────────────────────────────

    @staticmethod
    async def clock_out(
        db: AsyncSession,
        employee_id: uuid.UUID,
        *,
        source: str = "web",
        ip_address: Optional[str] = None,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
    ) -> ClockResponse:
        """Record a clock-out event. Updates today's AttendanceRecord with hours."""

        now = datetime.now(timezone.utc)
        today = now.date()

        # Find the open clock entry
        result = await db.execute(
            select(ClockEntry).where(
                ClockEntry.employee_id == employee_id,
                func.date(ClockEntry.clock_in) == today,
                ClockEntry.clock_out.is_(None),
            ).order_by(ClockEntry.clock_in.desc()).limit(1)
        )
        clock_entry = result.scalars().first()
        if clock_entry is None:
            raise ValidationException(
                {"clock_out": ["No open clock-in found for today. Please clock in first."]}
            )

        # Update clock entry
        clock_entry.clock_out = now
        clock_entry.duration_minutes = int(
            (now - clock_entry.clock_in).total_seconds() / 60
        )

        # Load attendance record
        att_result = await db.execute(
            select(AttendanceRecord)
            .where(
                AttendanceRecord.employee_id == employee_id,
                AttendanceRecord.date == today,
            )
            .options(selectinload(AttendanceRecord.shift_policy))
        )
        attendance = att_result.scalars().first()
        if attendance is None:
            raise NotFoundException("AttendanceRecord", f"{employee_id}/{today}")

        # Update attendance record
        attendance.last_clock_out = now

        # Resolve shift for hours calculation
        shift = attendance.shift_policy
        if shift is None:
            shift = await AttendanceService._get_shift_for_employee(
                db, employee_id, today,
            )

        # Calculate hours
        if attendance.first_clock_in:
            total_h, effective_h, overtime_h, status = AttendanceService._calculate_hours(
                attendance.first_clock_in, now, shift,
            )
            attendance.total_work_minutes = int(round(total_h * 60))
            attendance.effective_work_minutes = int(round(effective_h * 60))
            attendance.overtime_minutes = int(round(overtime_h * 60))

            # Don't downgrade status if arrival was already marked (e.g., half_day from late arrival)
            if attendance.status != AttendanceStatus.half_day or status == AttendanceStatus.absent:
                attendance.status = status

        attendance.updated_at = now
        await db.flush()

        # Audit
        await create_audit_entry(
            db,
            action="clock_out",
            entity_type="attendance_record",
            entity_id=attendance.id,
            actor_id=employee_id,
            new_values={
                "clock_entry_id": str(clock_entry.id),
                "source": source,
                "timestamp": now.isoformat(),
                "total_work_minutes": attendance.total_work_minutes,
                "effective_work_minutes": attendance.effective_work_minutes,
            },
            ip_address=ip_address,
        )

        return ClockResponse(
            clock_entry_id=clock_entry.id,
            attendance_id=attendance.id,
            timestamp=now,
            status=attendance.status,
            arrival_status=attendance.arrival_status,
        )

    # ── My attendance ───────────────────────────────────────────────

    @staticmethod
    async def get_my_attendance(
        db: AsyncSession,
        employee_id: uuid.UUID,
        from_date: date,
        to_date: date,
        *,
        page: int = 1,
        page_size: int = 50,
    ) -> AttendanceListResponse:
        """Get own attendance records with summary. Max 90-day range."""

        AttendanceService._validate_date_range(from_date, to_date)

        query = (
            select(AttendanceRecord)
            .where(
                AttendanceRecord.employee_id == employee_id,
                AttendanceRecord.date >= from_date,
                AttendanceRecord.date <= to_date,
            )
            .options(selectinload(AttendanceRecord.shift_policy))
            .order_by(AttendanceRecord.date.desc())
        )

        # Count
        count_q = select(func.count()).select_from(AttendanceRecord).where(
            AttendanceRecord.employee_id == employee_id,
            AttendanceRecord.date >= from_date,
            AttendanceRecord.date <= to_date,
        )
        total = (await db.execute(count_q)).scalar_one()

        # Paginate
        offset = (page - 1) * page_size
        result = await db.execute(query.offset(offset).limit(page_size))
        records = result.scalars().all()

        # For summary, load all records in range (not just current page)
        all_result = await db.execute(
            select(AttendanceRecord).where(
                AttendanceRecord.employee_id == employee_id,
                AttendanceRecord.date >= from_date,
                AttendanceRecord.date <= to_date,
            )
        )
        all_records = all_result.scalars().all()

        total_pages = math.ceil(total / page_size) if total else 0

        return AttendanceListResponse(
            data=[AttendanceService._build_record_response(r) for r in records],
            meta=PaginationMeta(
                page=page,
                page_size=page_size,
                total=total,
                total_pages=total_pages,
                has_next=page < total_pages,
                has_prev=page > 1,
            ),
            summary=AttendanceService._build_summary(all_records),
        )

    # ── Today's attendance (admin view) ─────────────────────────────

    @staticmethod
    async def get_today_attendance(
        db: AsyncSession,
        *,
        department_id: Optional[uuid.UUID] = None,
        location_id: Optional[uuid.UUID] = None,
        status_filter: Optional[AttendanceStatus] = None,
    ) -> TodayAttendanceResponse:
        """Get today's attendance for all employees with summary counts."""

        today = datetime.now(timezone.utc).date()

        # Build employee query
        emp_query = (
            select(Employee)
            .where(Employee.is_active.is_(True))
            .options(selectinload(Employee.department))
        )
        if department_id:
            emp_query = emp_query.where(Employee.department_id == department_id)
        if location_id:
            emp_query = emp_query.where(Employee.location_id == location_id)

        emp_result = await db.execute(emp_query.order_by(Employee.first_name))
        employees = emp_result.scalars().all()
        emp_ids = [e.id for e in employees]

        # Load today's attendance records
        att_result = await db.execute(
            select(AttendanceRecord)
            .where(
                AttendanceRecord.date == today,
                AttendanceRecord.employee_id.in_(emp_ids),
            )
            .options(selectinload(AttendanceRecord.shift_policy))
        )
        att_map = {r.employee_id: r for r in att_result.scalars().all()}

        # Build response items
        items: list[TodayAttendanceItem] = []
        summary = TodaySummary(total_employees=len(employees))

        for emp in employees:
            record = att_map.get(emp.id)
            dept_name = emp.department.name if emp.department else None

            emp_brief = EmployeeBrief(
                id=emp.id,
                employee_code=emp.employee_code,
                display_name=getattr(emp, "display_name", None)
                or f"{emp.first_name} {emp.last_name}".strip(),
                designation=emp.designation,
                department_name=dept_name,
                profile_photo_url=emp.profile_photo_url,
            )

            if record is None:
                att_status = AttendanceStatus.absent
                arrival = None
                first_in = None
                last_out = None
                total_h = None
                shift_name = None
                summary.not_clocked_in_yet += 1
                summary.absent += 1
            else:
                att_status = record.status
                arrival = record.arrival_status
                first_in = record.first_clock_in
                last_out = record.last_clock_out
                total_h = (
                    round(record.total_work_minutes / 60, 2)
                    if record.total_work_minutes
                    else None
                )
                shift_name = record.shift_policy.name if record.shift_policy else None

                if att_status == AttendanceStatus.present:
                    summary.present += 1
                elif att_status == AttendanceStatus.absent:
                    summary.absent += 1
                elif att_status == AttendanceStatus.on_leave:
                    summary.on_leave += 1
                elif att_status == AttendanceStatus.work_from_home:
                    summary.work_from_home += 1
                    summary.present += 1
                elif att_status == AttendanceStatus.half_day:
                    summary.present += 1

            # Apply status filter if provided
            if status_filter and att_status != status_filter:
                continue

            items.append(
                TodayAttendanceItem(
                    employee=emp_brief,
                    status=att_status,
                    arrival_status=arrival,
                    first_clock_in=first_in,
                    last_clock_out=last_out,
                    total_hours=total_h,
                    shift_name=shift_name,
                )
            )

        return TodayAttendanceResponse(data=items, summary=summary)

    # ── Team attendance (manager view) ──────────────────────────────

    @staticmethod
    async def get_team_attendance(
        db: AsyncSession,
        manager_id: uuid.UUID,
        from_date: date,
        to_date: date,
        *,
        page: int = 1,
        page_size: int = 50,
    ) -> AttendanceListResponse:
        """Get attendance records for a manager's direct reports."""

        AttendanceService._validate_date_range(from_date, to_date)

        # Get direct report IDs
        reports_result = await db.execute(
            select(Employee.id).where(
                Employee.reporting_manager_id == manager_id,
                Employee.is_active.is_(True),
            )
        )
        report_ids = [r[0] for r in reports_result.all()]

        if not report_ids:
            return AttendanceListResponse(
                data=[],
                meta=PaginationMeta(
                    page=1, page_size=page_size, total=0,
                    total_pages=0, has_next=False, has_prev=False,
                ),
                summary=AttendanceSummary(),
            )

        query = (
            select(AttendanceRecord)
            .where(
                AttendanceRecord.employee_id.in_(report_ids),
                AttendanceRecord.date >= from_date,
                AttendanceRecord.date <= to_date,
            )
            .options(selectinload(AttendanceRecord.shift_policy))
            .order_by(AttendanceRecord.date.desc())
        )

        count_q = select(func.count()).select_from(AttendanceRecord).where(
            AttendanceRecord.employee_id.in_(report_ids),
            AttendanceRecord.date >= from_date,
            AttendanceRecord.date <= to_date,
        )
        total = (await db.execute(count_q)).scalar_one()

        offset = (page - 1) * page_size
        result = await db.execute(query.offset(offset).limit(page_size))
        records = result.scalars().all()

        # Summary across full range
        all_result = await db.execute(
            select(AttendanceRecord).where(
                AttendanceRecord.employee_id.in_(report_ids),
                AttendanceRecord.date >= from_date,
                AttendanceRecord.date <= to_date,
            )
        )
        all_records = all_result.scalars().all()

        total_pages = math.ceil(total / page_size) if total else 0

        return AttendanceListResponse(
            data=[AttendanceService._build_record_response(r) for r in records],
            meta=PaginationMeta(
                page=page,
                page_size=page_size,
                total=total,
                total_pages=total_pages,
                has_next=page < total_pages,
                has_prev=page > 1,
            ),
            summary=AttendanceService._build_summary(all_records),
        )

    # ── Single employee attendance (HR/admin view) ──────────────────

    @staticmethod
    async def get_employee_attendance(
        db: AsyncSession,
        employee_id: uuid.UUID,
        from_date: date,
        to_date: date,
        *,
        page: int = 1,
        page_size: int = 50,
    ) -> AttendanceListResponse:
        """Get attendance records for a specific employee (admin view)."""

        AttendanceService._validate_date_range(from_date, to_date)

        # Verify employee exists
        emp_result = await db.execute(
            select(Employee.id).where(Employee.id == employee_id)
        )
        if emp_result.scalars().first() is None:
            raise NotFoundException("Employee", str(employee_id))

        return await AttendanceService.get_my_attendance(
            db, employee_id, from_date, to_date,
            page=page, page_size=page_size,
        )

    # ── Regularization: submit ──────────────────────────────────────

    @staticmethod
    async def submit_regularization(
        db: AsyncSession,
        employee_id: uuid.UUID,
        *,
        target_date: date,
        requested_status: AttendanceStatus = AttendanceStatus.present,
        requested_clock_in: Optional[datetime] = None,
        requested_clock_out: Optional[datetime] = None,
        reason: str,
    ) -> RegularizationResponse:
        """Submit a regularization request for a past attendance record."""

        today = datetime.now(timezone.utc).date()
        if target_date >= today:
            raise ValidationException(
                {"date": ["Regularization can only be submitted for past dates."]}
            )

        # Get or create attendance record
        result = await db.execute(
            select(AttendanceRecord).where(
                AttendanceRecord.employee_id == employee_id,
                AttendanceRecord.date == target_date,
            )
        )
        attendance = result.scalars().first()

        if attendance is None:
            # Create a record for the date (employee had no clock activity)
            shift = await AttendanceService._get_shift_for_employee(
                db, employee_id, target_date,
            )
            attendance = AttendanceRecord(
                employee_id=employee_id,
                date=target_date,
                status=AttendanceStatus.absent,
                shift_policy_id=shift.id if shift else None,
                source="regularization",
            )
            db.add(attendance)
            await db.flush()

        # Check for existing pending regularization
        existing = await db.execute(
            select(AttendanceRegularization).where(
                AttendanceRegularization.attendance_record_id == attendance.id,
                AttendanceRegularization.employee_id == employee_id,
                AttendanceRegularization.status == RegularizationStatus.pending,
            )
        )
        if existing.scalars().first():
            raise ConflictError(
                "regularization",
                f"Pending regularization already exists for {target_date}",
            )

        regularization = AttendanceRegularization(
            attendance_record_id=attendance.id,
            employee_id=employee_id,
            requested_status=requested_status,
            reason=reason,
            status=RegularizationStatus.pending,
        )
        db.add(regularization)
        await db.flush()

        # Audit
        await create_audit_entry(
            db,
            action="create",
            entity_type="attendance_regularization",
            entity_id=regularization.id,
            actor_id=employee_id,
            new_values={
                "date": target_date.isoformat(),
                "requested_status": requested_status.value,
                "reason": reason,
            },
        )

        return RegularizationResponse.model_validate(regularization)

    # ── Regularization: approve ─────────────────────────────────────

    @staticmethod
    async def approve_regularization(
        db: AsyncSession,
        regularization_id: uuid.UUID,
        approver_id: uuid.UUID,
    ) -> RegularizationResponse:
        """Approve a regularization request and update the attendance record."""

        result = await db.execute(
            select(AttendanceRegularization)
            .where(AttendanceRegularization.id == regularization_id)
            .options(selectinload(AttendanceRegularization.attendance_record))
        )
        reg = result.scalars().first()
        if reg is None:
            raise NotFoundException("AttendanceRegularization", str(regularization_id))

        if reg.status != RegularizationStatus.pending:
            raise ValidationException(
                {"status": [f"Regularization is already {reg.status.value}."]}
            )

        now = datetime.now(timezone.utc)

        # Update regularization
        old_status = reg.status.value
        reg.status = RegularizationStatus.approved
        reg.reviewed_by = approver_id
        reg.reviewed_at = now
        reg.updated_at = now

        # Update the attendance record
        attendance = reg.attendance_record
        attendance.status = reg.requested_status
        attendance.is_regularized = True
        attendance.updated_at = now

        await db.flush()

        # Audit
        await create_audit_entry(
            db,
            action="approve",
            entity_type="attendance_regularization",
            entity_id=reg.id,
            actor_id=approver_id,
            old_values={"status": old_status},
            new_values={"status": RegularizationStatus.approved.value},
        )

        return RegularizationResponse.model_validate(reg)

    # ── Regularization: reject ──────────────────────────────────────

    @staticmethod
    async def reject_regularization(
        db: AsyncSession,
        regularization_id: uuid.UUID,
        approver_id: uuid.UUID,
        reason: str,
    ) -> RegularizationResponse:
        """Reject a regularization request."""

        result = await db.execute(
            select(AttendanceRegularization).where(
                AttendanceRegularization.id == regularization_id,
            )
        )
        reg = result.scalars().first()
        if reg is None:
            raise NotFoundException("AttendanceRegularization", str(regularization_id))

        if reg.status != RegularizationStatus.pending:
            raise ValidationException(
                {"status": [f"Regularization is already {reg.status.value}."]}
            )

        now = datetime.now(timezone.utc)
        old_status = reg.status.value

        reg.status = RegularizationStatus.rejected
        reg.reviewed_by = approver_id
        reg.reviewed_at = now
        reg.reviewer_remarks = reason
        reg.updated_at = now

        await db.flush()

        # Audit
        await create_audit_entry(
            db,
            action="reject",
            entity_type="attendance_regularization",
            entity_id=reg.id,
            actor_id=approver_id,
            old_values={"status": old_status},
            new_values={
                "status": RegularizationStatus.rejected.value,
                "reviewer_remarks": reason,
            },
        )

        return RegularizationResponse.model_validate(reg)

    # ── Regularization: list ────────────────────────────────────────

    @staticmethod
    async def list_regularizations(
        db: AsyncSession,
        *,
        status_filter: Optional[RegularizationStatus] = None,
        employee_id: Optional[uuid.UUID] = None,
        approver_id: Optional[uuid.UUID] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> dict:
        """List regularization requests with filters and pagination."""

        query = select(AttendanceRegularization).order_by(
            AttendanceRegularization.created_at.desc()
        )

        if status_filter:
            query = query.where(AttendanceRegularization.status == status_filter)
        if employee_id:
            query = query.where(AttendanceRegularization.employee_id == employee_id)
        if approver_id:
            query = query.where(AttendanceRegularization.reviewed_by == approver_id)

        # Count
        count_q = select(func.count()).select_from(AttendanceRegularization)
        if status_filter:
            count_q = count_q.where(AttendanceRegularization.status == status_filter)
        if employee_id:
            count_q = count_q.where(AttendanceRegularization.employee_id == employee_id)
        if approver_id:
            count_q = count_q.where(AttendanceRegularization.reviewed_by == approver_id)

        total = (await db.execute(count_q)).scalar_one()

        offset = (page - 1) * page_size
        result = await db.execute(query.offset(offset).limit(page_size))
        records = result.scalars().all()

        total_pages = math.ceil(total / page_size) if total else 0

        return {
            "data": [RegularizationResponse.model_validate(r) for r in records],
            "meta": PaginationMeta(
                page=page,
                page_size=page_size,
                total=total,
                total_pages=total_pages,
                has_next=page < total_pages,
                has_prev=page > 1,
            ),
        }

    # ── Shift policies ──────────────────────────────────────────────

    @staticmethod
    async def get_shifts(
        db: AsyncSession,
        *,
        is_active: Optional[bool] = True,
    ) -> list[ShiftPolicyResponse]:
        """List all shift policies."""

        query = select(ShiftPolicy).order_by(ShiftPolicy.name)
        if is_active is not None:
            query = query.where(ShiftPolicy.is_active == is_active)

        result = await db.execute(query)
        shifts = result.scalars().all()
        return [ShiftPolicyResponse.model_validate(s) for s in shifts]

    # ── Holidays ────────────────────────────────────────────────────

    @staticmethod
    async def get_holidays(
        db: AsyncSession,
        *,
        year: Optional[int] = None,
        location_id: Optional[uuid.UUID] = None,
    ) -> list[HolidayResponse]:
        """List holidays, optionally filtered by year and location."""

        query = (
            select(Holiday)
            .join(HolidayCalendar, Holiday.calendar_id == HolidayCalendar.id)
            .where(HolidayCalendar.is_active.is_(True))
            .order_by(Holiday.date)
        )

        if year is not None:
            query = query.where(HolidayCalendar.year == year)
        if location_id is not None:
            query = query.where(
                (HolidayCalendar.location_id == location_id)
                | (HolidayCalendar.location_id.is_(None))
            )

        result = await db.execute(query)
        holidays = result.scalars().all()
        return [HolidayResponse.model_validate(h) for h in holidays]
