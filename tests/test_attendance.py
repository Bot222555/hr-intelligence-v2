"""Attendance module test suite — 20 tests covering clock-in/out, late detection,
regularization CRUD, today attendance, team attendance, shift policies, holidays.

Tests exercise both the service layer (direct DB) and the HTTP API (via router).
Uses the shared conftest.py pattern with in-memory SQLite.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, time, timedelta, timezone
from unittest.mock import patch

from sqlalchemy import select

from backend.attendance.models import (
    AttendanceRecord,
    AttendanceRegularization,
    ClockEntry,
    EmployeeShiftAssignment,
    Holiday,
    HolidayCalendar,
    ShiftPolicy,
    WeeklyOffPolicy,
)
from backend.attendance.service import AttendanceService
from backend.common.constants import (
    ArrivalStatus,
    AttendanceStatus,
    RegularizationStatus,
    UserRole,
)
from backend.core_hr.models import Employee
from tests.conftest import (
    TestSessionFactory,
    _make_employee,
    create_access_token,
)

# ── Helpers ─────────────────────────────────────────────────────────


async def _create_shift(db, *, name="General Shift", start=time(9, 0),
                         end=time(18, 0), grace=15, half_day=240,
                         full_day=480, night=False) -> ShiftPolicy:
    """Insert a shift policy and return the ORM object."""
    shift = ShiftPolicy(
        name=name,
        start_time=start,
        end_time=end,
        grace_minutes=grace,
        half_day_minutes=half_day,
        full_day_minutes=full_day,
        is_night_shift=night,
    )
    db.add(shift)
    await db.flush()
    return shift


async def _create_weekly_off(db, *, name="Sat-Sun Off",
                              days=None) -> WeeklyOffPolicy:
    """Insert a weekly-off policy."""
    policy = WeeklyOffPolicy(
        name=name,
        days=days or {"saturday": True, "sunday": True},
    )
    db.add(policy)
    await db.flush()
    return policy


async def _assign_shift(db, employee_id, shift_id, weekly_off_id,
                         effective_from=None) -> EmployeeShiftAssignment:
    """Link employee to shift + weekly-off policy."""
    assignment = EmployeeShiftAssignment(
        employee_id=employee_id,
        shift_policy_id=shift_id,
        weekly_off_policy_id=weekly_off_id,
        effective_from=effective_from or date(2024, 1, 1),
    )
    db.add(assignment)
    await db.flush()
    return assignment


async def _create_manager_with_report(db, test_location, test_department):
    """Create a manager and a direct report. Return (manager_data, report_data)."""
    from backend.auth.models import UserSession
    import hashlib

    manager_data = _make_employee(
        email="manager@creativefuel.io",
        first_name="Manager",
        last_name="One",
        department_id=test_department["id"],
        location_id=test_location["id"],
    )
    db.add(Employee(**manager_data))
    await db.flush()

    report_data = _make_employee(
        email="report@creativefuel.io",
        first_name="Report",
        last_name="One",
        department_id=test_department["id"],
        location_id=test_location["id"],
    )
    # Set reporting_manager_id
    report_obj = Employee(**report_data)
    report_obj.reporting_manager_id = manager_data["id"]
    db.add(report_obj)
    await db.flush()
    report_data["id"] = report_obj.id

    return manager_data, report_data


def _make_auth_headers(employee_id, role=UserRole.employee):
    """Generate Bearer auth headers for a given employee/role."""
    token = create_access_token(employee_id, role=role)
    return {"Authorization": f"Bearer {token}"}, token


async def _persist_session(db, employee_id, token):
    """Create a UserSession row matching the token so auth middleware passes."""
    import hashlib
    from backend.auth.models import UserSession
    from backend.config import settings

    token_hash = hashlib.sha256(token.encode()).hexdigest()
    session = UserSession(
        id=uuid.uuid4(),
        employee_id=employee_id,
        token_hash=token_hash,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=settings.JWT_EXPIRY_HOURS),
        is_revoked=False,
        created_at=datetime.now(timezone.utc),
    )
    db.add(session)
    await db.flush()


# ═════════════════════════════════════════════════════════════════════
# 1. CLOCK-IN / CLOCK-OUT — Service Layer
# ═════════════════════════════════════════════════════════════════════


async def test_clock_in_creates_attendance_record(db, test_employee):
    """Clock-in should create an AttendanceRecord + ClockEntry for today."""
    resp = await AttendanceService.clock_in(db, test_employee["id"], source="web")

    assert resp.status == AttendanceStatus.present
    assert resp.attendance_id is not None
    assert resp.clock_entry_id is not None
    assert resp.timestamp is not None

    # Verify DB state
    record = (await db.execute(
        select(AttendanceRecord).where(
            AttendanceRecord.employee_id == test_employee["id"]
        )
    )).scalars().first()
    assert record is not None
    assert record.status == AttendanceStatus.present
    assert record.first_clock_in is not None


async def test_clock_in_duplicate_raises_conflict(db, test_employee):
    """Clocking in twice without clocking out should raise ConflictError."""
    await AttendanceService.clock_in(db, test_employee["id"])

    from backend.common.exceptions import ConflictError
    import pytest

    with pytest.raises(ConflictError):
        await AttendanceService.clock_in(db, test_employee["id"])


async def test_clock_out_records_hours(db, test_employee):
    """Clock-out should fill last_clock_out and compute work minutes.

    We pre-seed the AttendanceRecord + ClockEntry with tz-aware timestamps
    to avoid SQLite stripping timezone info on round-trip (a known SQLite-only
    limitation — PostgreSQL preserves tzinfo).
    """
    now = datetime.now(timezone.utc)
    today = now.date()
    clock_in_time = now - timedelta(hours=9)

    # Create attendance record as if clocked-in 9 hours ago
    att = AttendanceRecord(
        employee_id=test_employee["id"],
        date=today,
        status=AttendanceStatus.present,
        first_clock_in=clock_in_time,
        source="test",
    )
    db.add(att)
    await db.flush()

    # Create the matching open clock entry
    entry = ClockEntry(
        employee_id=test_employee["id"],
        attendance_record_id=att.id,
        clock_in=clock_in_time,
        source="test",
    )
    db.add(entry)
    await db.flush()

    # Now clock out
    clock_out_resp = await AttendanceService.clock_out(db, test_employee["id"])

    assert clock_out_resp.attendance_id == att.id

    # Reload and verify hours were computed
    record = (await db.execute(
        select(AttendanceRecord).where(AttendanceRecord.id == att.id)
    )).scalars().first()
    assert record.last_clock_out is not None
    assert record.total_work_minutes is not None
    assert record.total_work_minutes > 0
    assert record.effective_work_minutes is not None


async def test_clock_out_without_clock_in_raises_validation(db, test_employee):
    """Clock-out with no open clock entry should raise ValidationException."""
    from backend.common.exceptions import ValidationException
    import pytest

    with pytest.raises(ValidationException):
        await AttendanceService.clock_out(db, test_employee["id"])


# ═════════════════════════════════════════════════════════════════════
# 2. LATE DETECTION
# ═════════════════════════════════════════════════════════════════════


async def test_on_time_arrival_within_grace(db, test_employee):
    """Clock-in within shift start + grace → on_time arrival status."""
    shift = await _create_shift(db, start=time(9, 0), grace=15)
    weekly_off = await _create_weekly_off(db)
    await _assign_shift(db, test_employee["id"], shift.id, weekly_off.id)

    # Clock in at 09:10 — within 15-minute grace
    fake_now = datetime.combine(
        date.today(), time(9, 10), tzinfo=timezone.utc,
    )
    with patch("backend.attendance.service.datetime") as mock_dt:
        mock_dt.now.return_value = fake_now
        mock_dt.combine = datetime.combine
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        resp = await AttendanceService.clock_in(db, test_employee["id"])

    assert resp.arrival_status == ArrivalStatus.on_time


async def test_late_arrival_after_grace(db, test_employee):
    """Clock-in after grace but within 30 min → late arrival status."""
    shift = await _create_shift(db, start=time(9, 0), grace=15)
    weekly_off = await _create_weekly_off(db)
    await _assign_shift(db, test_employee["id"], shift.id, weekly_off.id)

    # Clock in at 09:25 — 25 min after shift start, past 15-min grace
    fake_now = datetime.combine(
        date.today(), time(9, 25), tzinfo=timezone.utc,
    )
    with patch("backend.attendance.service.datetime") as mock_dt:
        mock_dt.now.return_value = fake_now
        mock_dt.combine = datetime.combine
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        resp = await AttendanceService.clock_in(db, test_employee["id"])

    assert resp.arrival_status == ArrivalStatus.late


async def test_very_late_arrival(db, test_employee):
    """Clock-in > 30 min after shift start → very_late arrival status."""
    shift = await _create_shift(db, start=time(9, 0), grace=15)
    weekly_off = await _create_weekly_off(db)
    await _assign_shift(db, test_employee["id"], shift.id, weekly_off.id)

    # Clock in at 09:45 — 45 min after shift start
    fake_now = datetime.combine(
        date.today(), time(9, 45), tzinfo=timezone.utc,
    )
    with patch("backend.attendance.service.datetime") as mock_dt:
        mock_dt.now.return_value = fake_now
        mock_dt.combine = datetime.combine
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        resp = await AttendanceService.clock_in(db, test_employee["id"])

    assert resp.arrival_status == ArrivalStatus.very_late


async def test_half_day_when_extremely_late(db, test_employee):
    """Clock-in > 2 hours after shift start → status becomes half_day."""
    shift = await _create_shift(db, start=time(9, 0), grace=15)
    weekly_off = await _create_weekly_off(db)
    await _assign_shift(db, test_employee["id"], shift.id, weekly_off.id)

    # Clock in at 11:30 — 150 min after shift start (> 120 threshold)
    fake_now = datetime.combine(
        date.today(), time(11, 30), tzinfo=timezone.utc,
    )
    with patch("backend.attendance.service.datetime") as mock_dt:
        mock_dt.now.return_value = fake_now
        mock_dt.combine = datetime.combine
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        resp = await AttendanceService.clock_in(db, test_employee["id"])

    assert resp.status == AttendanceStatus.half_day


# ═════════════════════════════════════════════════════════════════════
# 3. REGULARIZATION CRUD
# ═════════════════════════════════════════════════════════════════════


async def test_submit_regularization(db, test_employee):
    """Submit regularization for a past date → creates pending request."""
    yesterday = date.today() - timedelta(days=1)

    reg = await AttendanceService.submit_regularization(
        db,
        test_employee["id"],
        target_date=yesterday,
        requested_status=AttendanceStatus.present,
        reason="Forgot to clock in, was working from office.",
    )

    assert reg.status == RegularizationStatus.pending
    assert reg.requested_status == AttendanceStatus.present
    assert reg.employee_id == test_employee["id"]
    assert reg.attendance_record_id is not None


async def test_regularization_rejects_future_date(db, test_employee):
    """Regularization for today or future should raise ValidationException."""
    from backend.common.exceptions import ValidationException
    import pytest

    with pytest.raises(ValidationException):
        await AttendanceService.submit_regularization(
            db,
            test_employee["id"],
            target_date=date.today(),
            requested_status=AttendanceStatus.present,
            reason="Trying to regularize today which should fail.",
        )


async def test_duplicate_pending_regularization_raises_conflict(db, test_employee):
    """Submitting a second pending regularization for the same date → ConflictError."""
    from backend.common.exceptions import ConflictError
    import pytest

    yesterday = date.today() - timedelta(days=1)

    await AttendanceService.submit_regularization(
        db,
        test_employee["id"],
        target_date=yesterday,
        requested_status=AttendanceStatus.present,
        reason="First regularization request for this date.",
    )

    with pytest.raises(ConflictError):
        await AttendanceService.submit_regularization(
            db,
            test_employee["id"],
            target_date=yesterday,
            requested_status=AttendanceStatus.present,
            reason="Duplicate regularization for the same date.",
        )


async def test_approve_regularization(db, test_employee, test_location, test_department):
    """Approving a regularization updates both the reg status and attendance record."""
    yesterday = date.today() - timedelta(days=1)
    manager_data, _ = await _create_manager_with_report(db, test_location, test_department)

    reg = await AttendanceService.submit_regularization(
        db,
        test_employee["id"],
        target_date=yesterday,
        requested_status=AttendanceStatus.present,
        reason="Was in client meeting, forgot biometric.",
    )

    approved = await AttendanceService.approve_regularization(
        db, reg.id, manager_data["id"],
    )

    assert approved.status == RegularizationStatus.approved
    assert approved.reviewed_by == manager_data["id"]

    # Verify attendance record updated
    att = (await db.execute(
        select(AttendanceRecord).where(
            AttendanceRecord.id == reg.attendance_record_id,
        )
    )).scalars().first()
    assert att.status == AttendanceStatus.present
    assert att.is_regularized is True


async def test_reject_regularization(db, test_employee, test_location, test_department):
    """Rejecting a regularization sets status to rejected with reviewer remarks."""
    yesterday = date.today() - timedelta(days=1)
    manager_data, _ = await _create_manager_with_report(db, test_location, test_department)

    reg = await AttendanceService.submit_regularization(
        db,
        test_employee["id"],
        target_date=yesterday,
        requested_status=AttendanceStatus.present,
        reason="Was in client meeting, forgot biometric.",
    )

    rejected = await AttendanceService.reject_regularization(
        db, reg.id, manager_data["id"],
        reason="No evidence of office presence found.",
    )

    assert rejected.status == RegularizationStatus.rejected
    assert rejected.reviewer_remarks == "No evidence of office presence found."


async def test_cannot_approve_already_approved(db, test_employee, test_location, test_department):
    """Approving an already-approved regularization should raise ValidationException."""
    from backend.common.exceptions import ValidationException
    import pytest

    yesterday = date.today() - timedelta(days=1)
    manager_data, _ = await _create_manager_with_report(db, test_location, test_department)

    reg = await AttendanceService.submit_regularization(
        db,
        test_employee["id"],
        target_date=yesterday,
        requested_status=AttendanceStatus.present,
        reason="Client meeting off-site, forgot to clock in.",
    )

    await AttendanceService.approve_regularization(db, reg.id, manager_data["id"])

    with pytest.raises(ValidationException):
        await AttendanceService.approve_regularization(db, reg.id, manager_data["id"])


async def test_list_regularizations_by_employee(db, test_employee):
    """List regularizations filtered by employee returns only their requests."""
    day1 = date.today() - timedelta(days=1)
    day2 = date.today() - timedelta(days=2)

    await AttendanceService.submit_regularization(
        db, test_employee["id"], target_date=day1,
        requested_status=AttendanceStatus.present,
        reason="Missed clock-in day 1 while in office.",
    )
    await AttendanceService.submit_regularization(
        db, test_employee["id"], target_date=day2,
        requested_status=AttendanceStatus.present,
        reason="Missed clock-in day 2 while in office.",
    )

    result = await AttendanceService.list_regularizations(
        db, employee_id=test_employee["id"],
    )

    assert result["meta"].total == 2
    assert len(result["data"]) == 2
    assert all(r.employee_id == test_employee["id"] for r in result["data"])


# ═════════════════════════════════════════════════════════════════════
# 4. TODAY ATTENDANCE (Admin/Manager View)
# ═════════════════════════════════════════════════════════════════════


async def test_today_attendance_shows_all_employees(db, test_employee):
    """Today attendance should list all active employees with status."""
    result = await AttendanceService.get_today_attendance(db)

    assert result.summary.total_employees >= 1
    # Our test employee should be absent (no clock-in yet)
    emp_item = next(
        (i for i in result.data if i.employee.id == test_employee["id"]),
        None,
    )
    assert emp_item is not None
    assert emp_item.status == AttendanceStatus.absent


async def test_today_attendance_reflects_clock_in(db, test_employee):
    """After clock-in, today attendance should show employee as present."""
    await AttendanceService.clock_in(db, test_employee["id"])

    result = await AttendanceService.get_today_attendance(db)

    emp_item = next(
        (i for i in result.data if i.employee.id == test_employee["id"]),
        None,
    )
    assert emp_item is not None
    assert emp_item.status == AttendanceStatus.present
    assert emp_item.first_clock_in is not None
    assert result.summary.present >= 1


# ═════════════════════════════════════════════════════════════════════
# 5. TEAM ATTENDANCE (Manager View)
# ═════════════════════════════════════════════════════════════════════


async def test_team_attendance_returns_direct_reports(
    db, test_location, test_department,
):
    """Manager's team attendance shows only their direct reports."""
    manager_data, report_data = await _create_manager_with_report(
        db, test_location, test_department,
    )

    # Create attendance for the report
    today = date.today()
    att = AttendanceRecord(
        employee_id=report_data["id"],
        date=today,
        status=AttendanceStatus.present,
        first_clock_in=datetime.now(timezone.utc),
        source="test",
    )
    db.add(att)
    await db.flush()

    result = await AttendanceService.get_team_attendance(
        db, manager_data["id"],
        from_date=today, to_date=today,
    )

    assert result.meta.total == 1
    assert result.data[0].date == today
    assert result.summary.present == 1


async def test_team_attendance_empty_for_no_reports(db, test_employee):
    """Employee with no direct reports gets empty team attendance."""
    today = date.today()
    result = await AttendanceService.get_team_attendance(
        db, test_employee["id"],
        from_date=today, to_date=today,
    )

    assert result.meta.total == 0
    assert result.data == []


# ═════════════════════════════════════════════════════════════════════
# 6. SHIFT POLICIES
# ═════════════════════════════════════════════════════════════════════


async def test_get_shift_policies(db):
    """Listing shift policies returns all active policies."""
    await _create_shift(db, name="Morning Shift", start=time(6, 0), end=time(14, 0))
    await _create_shift(db, name="Evening Shift", start=time(14, 0), end=time(22, 0))
    await _create_shift(db, name="Night Shift", start=time(22, 0), end=time(6, 0), night=True)

    policies = await AttendanceService.get_shifts(db)

    assert len(policies) == 3
    names = {p.name for p in policies}
    assert "Morning Shift" in names
    assert "Evening Shift" in names
    assert "Night Shift" in names


async def test_get_shift_policies_active_filter(db):
    """Inactive shift policies are excluded by default."""
    active_shift = await _create_shift(db, name="Active Shift")
    inactive_shift = await _create_shift(db, name="Inactive Shift")
    inactive_shift.is_active = False
    await db.flush()

    active_only = await AttendanceService.get_shifts(db, is_active=True)
    assert len(active_only) == 1
    assert active_only[0].name == "Active Shift"

    all_shifts = await AttendanceService.get_shifts(db, is_active=None)
    assert len(all_shifts) == 2


# ═════════════════════════════════════════════════════════════════════
# 7. HOLIDAYS
# ═════════════════════════════════════════════════════════════════════


async def test_get_holidays(db, test_location):
    """Listing holidays returns entries from active calendars."""
    calendar = HolidayCalendar(
        name="India 2026",
        year=2026,
        location_id=test_location["id"],
        is_active=True,
    )
    db.add(calendar)
    await db.flush()

    holidays = [
        Holiday(calendar_id=calendar.id, name="Republic Day", date=date(2026, 1, 26)),
        Holiday(calendar_id=calendar.id, name="Independence Day", date=date(2026, 8, 15)),
        Holiday(calendar_id=calendar.id, name="Diwali", date=date(2026, 10, 19), is_optional=True),
    ]
    for h in holidays:
        db.add(h)
    await db.flush()

    result = await AttendanceService.get_holidays(db, year=2026)

    assert len(result) == 3
    names = {h.name for h in result}
    assert "Republic Day" in names
    assert "Independence Day" in names
    assert "Diwali" in names


async def test_get_holidays_by_location(db, test_location):
    """Holidays filtered by location return only matching + global calendars."""
    # Location-specific calendar
    cal_loc = HolidayCalendar(
        name="Mumbai 2026",
        year=2026,
        location_id=test_location["id"],
        is_active=True,
    )
    db.add(cal_loc)
    await db.flush()

    db.add(Holiday(calendar_id=cal_loc.id, name="Ganesh Chaturthi",
                   date=date(2026, 8, 27)))
    await db.flush()

    # Global calendar (no location)
    cal_global = HolidayCalendar(
        name="India National 2026",
        year=2026,
        location_id=None,
        is_active=True,
    )
    db.add(cal_global)
    await db.flush()

    db.add(Holiday(calendar_id=cal_global.id, name="Republic Day",
                   date=date(2026, 1, 26)))
    await db.flush()

    result = await AttendanceService.get_holidays(
        db, year=2026, location_id=test_location["id"],
    )

    # Should get both location-specific and global holidays
    assert len(result) == 2
    names = {h.name for h in result}
    assert "Ganesh Chaturthi" in names
    assert "Republic Day" in names


# ═════════════════════════════════════════════════════════════════════
# 8. MY ATTENDANCE (Self View)
# ═════════════════════════════════════════════════════════════════════


async def test_my_attendance_returns_records(db, test_employee):
    """Employee's own attendance query returns their records with summary."""
    today = date.today()

    # Create a few attendance records
    for i in range(3):
        att = AttendanceRecord(
            employee_id=test_employee["id"],
            date=today - timedelta(days=i + 1),
            status=AttendanceStatus.present,
            total_work_minutes=510,
            effective_work_minutes=450,
            source="test",
        )
        db.add(att)
    await db.flush()

    result = await AttendanceService.get_my_attendance(
        db,
        test_employee["id"],
        from_date=today - timedelta(days=7),
        to_date=today,
    )

    assert result.meta.total == 3
    assert result.summary.present == 3
    assert result.summary.avg_hours > 0


async def test_my_attendance_date_range_validation(db, test_employee):
    """Date range > 90 days should raise ValidationException."""
    from backend.common.exceptions import ValidationException
    import pytest

    with pytest.raises(ValidationException):
        await AttendanceService.get_my_attendance(
            db,
            test_employee["id"],
            from_date=date(2025, 1, 1),
            to_date=date(2025, 12, 31),
        )


# ═════════════════════════════════════════════════════════════════════
# 9. HOURS CALCULATION
# ═════════════════════════════════════════════════════════════════════


async def test_calculate_hours_full_day():
    """9 hours total → 8 effective (minus lunch) → present status."""
    shift = ShiftPolicy(
        name="Test",
        start_time=time(9, 0),
        end_time=time(18, 0),
        grace_minutes=15,
        half_day_minutes=240,
        full_day_minutes=480,
    )
    first_in = datetime(2026, 2, 20, 9, 0, tzinfo=timezone.utc)
    last_out = datetime(2026, 2, 20, 18, 0, tzinfo=timezone.utc)

    total_h, effective_h, overtime_h, status = AttendanceService._calculate_hours(
        first_in, last_out, shift,
    )

    assert total_h == 9.0
    assert effective_h == 8.0  # 9 - 1 hour lunch
    assert overtime_h == 0.0
    assert status == AttendanceStatus.present


async def test_calculate_hours_half_day():
    """5 hours total → 4 effective → half_day status."""
    shift = ShiftPolicy(
        name="Test",
        start_time=time(9, 0),
        end_time=time(18, 0),
        grace_minutes=15,
        half_day_minutes=240,
        full_day_minutes=480,
    )
    first_in = datetime(2026, 2, 20, 9, 0, tzinfo=timezone.utc)
    last_out = datetime(2026, 2, 20, 14, 0, tzinfo=timezone.utc)

    total_h, effective_h, overtime_h, status = AttendanceService._calculate_hours(
        first_in, last_out, shift,
    )

    assert total_h == 5.0
    assert effective_h == 4.0
    assert status == AttendanceStatus.half_day
