"""Dashboard module test suite — 15 tests covering all 5 requested endpoints
plus auth/role enforcement.

Tests exercise both the service layer (direct DB) and the HTTP API (via router).
Uses the shared conftest.py pattern with in-memory SQLite.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import patch

import pytest
from sqlalchemy import select

from backend.attendance.models import AttendanceRecord
from backend.common.constants import (
    AttendanceStatus,
    EmploymentStatus,
    LeaveStatus,
    UserRole,
)
from backend.core_hr.models import Department, Employee
from backend.dashboard.service import DashboardService
from backend.leave.models import LeaveRequest, LeaveType
from tests.conftest import (
    TestSessionFactory,
    _make_department,
    _make_employee,
    _make_location,
    create_access_token,
)


# ── Helpers ─────────────────────────────────────────────────────────


def _fixed_today() -> date:
    """A fixed 'today' for deterministic tests."""
    return date(2026, 2, 20)


async def _persist_session(db, employee_id, token):
    """Create a UserSession row matching the token so auth middleware passes."""
    from backend.auth.models import UserSession
    from backend.config import settings

    token_hash = hashlib.sha256(token.encode()).hexdigest()
    session = UserSession(
        id=uuid.uuid4(),
        employee_id=employee_id,
        token_hash=token_hash,
        expires_at=datetime.now(timezone.utc)
        + timedelta(hours=settings.JWT_EXPIRY_HOURS),
        is_revoked=False,
        created_at=datetime.now(timezone.utc),
    )
    db.add(session)
    await db.flush()


def _make_auth_headers(employee_id, role=UserRole.hr_admin):
    """Generate Bearer auth headers for a given employee/role."""
    token = create_access_token(employee_id, role=role)
    return {"Authorization": f"Bearer {token}"}, token


async def _seed_leave_types(db) -> dict[str, uuid.UUID]:
    """Create standard leave types and return {code: id} mapping."""
    types = {}
    for code, name in [
        ("SL", "Sick Leave"),
        ("CL", "Casual Leave"),
        ("EL", "Earned Leave"),
    ]:
        lt = LeaveType(
            id=uuid.uuid4(),
            code=code,
            name=name,
            default_balance=Decimal("12"),
            is_active=True,
        )
        db.add(lt)
        types[code] = lt.id
    await db.flush()
    return types


async def _seed_extra_employees(db, dept_id, loc_id, count=5):
    """Create N extra employees in the given department/location."""
    employees = []
    for i in range(count):
        data = _make_employee(
            email=f"extra{i}@creativefuel.io",
            first_name=f"Extra{i}",
            last_name="Employee",
            department_id=dept_id,
            location_id=loc_id,
        )
        emp = Employee(**data)
        db.add(emp)
        employees.append(data)
    await db.flush()
    return employees


# ═════════════════════════════════════════════════════════════════════
# 1. SUMMARY — Service Layer
# ═════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_summary_total_employees(db, test_employee, test_department, test_location):
    """Summary returns correct total_employees count."""
    # test_employee is already 1 active employee; add more
    await _seed_extra_employees(db, test_department["id"], test_location["id"], count=3)

    with patch("backend.dashboard.service._today", return_value=_fixed_today()):
        result = await DashboardService.get_summary(db)

    assert result.total_employees == 4  # 1 from fixture + 3 extras


@pytest.mark.asyncio
async def test_summary_present_today(db, test_employee):
    """Summary counts employees with checked-in attendance status."""
    today = _fixed_today()

    # Create attendance records: 1 present, 1 absent
    db.add(
        AttendanceRecord(
            employee_id=test_employee["id"],
            date=today,
            status=AttendanceStatus.present,
            source="test",
        )
    )
    await db.flush()

    with patch("backend.dashboard.service._today", return_value=today):
        result = await DashboardService.get_summary(db)

    assert result.present_today == 1


@pytest.mark.asyncio
async def test_summary_on_leave_today(db, test_employee):
    """Summary counts employees on approved leave covering today."""
    today = _fixed_today()

    leave_types = await _seed_leave_types(db)
    db.add(
        LeaveRequest(
            employee_id=test_employee["id"],
            leave_type_id=leave_types["SL"],
            start_date=today - timedelta(days=1),
            end_date=today + timedelta(days=1),
            day_details={"2026-02-19": "full_day", "2026-02-20": "full_day", "2026-02-21": "full_day"},
            total_days=Decimal("3"),
            status=LeaveStatus.approved,
        )
    )
    await db.flush()

    with patch("backend.dashboard.service._today", return_value=today):
        result = await DashboardService.get_summary(db)

    assert result.on_leave_today == 1


@pytest.mark.asyncio
async def test_summary_pending_leave_requests(db, test_employee):
    """Summary counts pending leave requests."""
    leave_types = await _seed_leave_types(db)

    for i in range(3):
        db.add(
            LeaveRequest(
                employee_id=test_employee["id"],
                leave_type_id=leave_types["CL"],
                start_date=date(2026, 3, 10 + i),
                end_date=date(2026, 3, 10 + i),
                day_details={f"2026-03-{10+i}": "full_day"},
                total_days=Decimal("1"),
                status=LeaveStatus.pending,
            )
        )
    # 1 approved (should NOT count)
    db.add(
        LeaveRequest(
            employee_id=test_employee["id"],
            leave_type_id=leave_types["CL"],
            start_date=date(2026, 3, 15),
            end_date=date(2026, 3, 15),
            day_details={"2026-03-15": "full_day"},
            total_days=Decimal("1"),
            status=LeaveStatus.approved,
        )
    )
    await db.flush()

    with patch("backend.dashboard.service._today", return_value=_fixed_today()):
        result = await DashboardService.get_summary(db)

    assert result.pending_leave_requests == 3


@pytest.mark.asyncio
async def test_summary_department_breakdown(db, test_employee, test_department, test_location):
    """Summary includes department breakdown with correct counts."""
    # Add a second department with employees
    dept2_data = _make_department(name="Design", code="DES", location_id=test_location["id"])
    db.add(Department(**dept2_data))
    await db.flush()

    for i in range(2):
        data = _make_employee(
            email=f"designer{i}@creativefuel.io",
            first_name=f"Designer{i}",
            last_name="Person",
            department_id=dept2_data["id"],
            location_id=test_location["id"],
        )
        db.add(Employee(**data))
    await db.flush()

    with patch("backend.dashboard.service._today", return_value=_fixed_today()):
        result = await DashboardService.get_summary(db)

    assert len(result.department_breakdown) == 2
    breakdown_map = {d.department_name: d.count for d in result.department_breakdown}
    assert breakdown_map[test_department["name"]] == 1  # test_employee
    assert breakdown_map["Design"] == 2


# ═════════════════════════════════════════════════════════════════════
# 2. ATTENDANCE TREND — Service Layer
# ═════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_attendance_trend_30_days(db, test_employee):
    """Attendance trend returns 30 data points with correct present count."""
    today = _fixed_today()

    # Add attendance for 5 of the last 30 days
    for i in range(5):
        db.add(
            AttendanceRecord(
                employee_id=test_employee["id"],
                date=today - timedelta(days=i),
                status=AttendanceStatus.present,
                source="test",
            )
        )
    await db.flush()

    with patch("backend.dashboard.service._today", return_value=today):
        result = await DashboardService.get_attendance_trend(db, period_days=30)

    assert result.period_days == 30
    assert len(result.data) == 30
    total_present = sum(p.present for p in result.data)
    assert total_present == 5
    assert result.averages.avg_present > 0


@pytest.mark.asyncio
async def test_attendance_trend_fills_zero_days(db, test_employee):
    """Days with no attendance records should appear with zeros."""
    today = _fixed_today()

    # Only 1 day of data
    db.add(
        AttendanceRecord(
            employee_id=test_employee["id"],
            date=today,
            status=AttendanceStatus.present,
            source="test",
        )
    )
    await db.flush()

    with patch("backend.dashboard.service._today", return_value=today):
        result = await DashboardService.get_attendance_trend(db, period_days=7)

    assert len(result.data) == 7
    zero_days = [p for p in result.data if p.present == 0]
    assert len(zero_days) == 6


# ═════════════════════════════════════════════════════════════════════
# 3. LEAVE SUMMARY — Service Layer
# ═════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_leave_summary_by_type(db, test_employee):
    """Leave summary breaks down by leave type for current month."""
    today = _fixed_today()
    leave_types = await _seed_leave_types(db)

    # 2 sick leave requests in Feb 2026
    for i in range(2):
        db.add(
            LeaveRequest(
                employee_id=test_employee["id"],
                leave_type_id=leave_types["SL"],
                start_date=date(2026, 2, 5 + i * 3),
                end_date=date(2026, 2, 5 + i * 3),
                day_details={f"2026-02-{5+i*3:02d}": "full_day"},
                total_days=Decimal("1"),
                status=LeaveStatus.approved,
            )
        )
    # 1 casual leave
    db.add(
        LeaveRequest(
            employee_id=test_employee["id"],
            leave_type_id=leave_types["CL"],
            start_date=date(2026, 2, 10),
            end_date=date(2026, 2, 11),
            day_details={"2026-02-10": "full_day", "2026-02-11": "full_day"},
            total_days=Decimal("2"),
            status=LeaveStatus.approved,
        )
    )
    # Leave in March — should NOT count
    db.add(
        LeaveRequest(
            employee_id=test_employee["id"],
            leave_type_id=leave_types["EL"],
            start_date=date(2026, 3, 5),
            end_date=date(2026, 3, 10),
            day_details={"2026-03-05": "full_day"},
            total_days=Decimal("5"),
            status=LeaveStatus.approved,
        )
    )
    await db.flush()

    with patch("backend.dashboard.service._today", return_value=today):
        result = await DashboardService.get_leave_summary(db)

    assert result.month == 2
    assert result.year == 2026
    assert result.total_requests == 3  # 2 SL + 1 CL in Feb

    type_map = {t.leave_type_code: t for t in result.by_type}
    assert type_map["SL"].request_count == 2
    assert type_map["SL"].total_days == Decimal("2")
    assert type_map["CL"].request_count == 1
    assert type_map["CL"].total_days == Decimal("2")
    assert type_map["EL"].request_count == 0  # March leave excluded


@pytest.mark.asyncio
async def test_leave_summary_empty_month(db, test_employee):
    """Leave summary returns zero counts when no leave in current month."""
    today = _fixed_today()
    await _seed_leave_types(db)

    with patch("backend.dashboard.service._today", return_value=today):
        result = await DashboardService.get_leave_summary(db)

    assert result.total_requests == 0
    assert result.total_days == Decimal("0")
    assert len(result.by_type) == 3  # All leave types listed, just zero counts


# ═════════════════════════════════════════════════════════════════════
# 4. BIRTHDAYS — Service Layer
# ═════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_birthdays_within_7_days(db, test_department, test_location):
    """Birthdays endpoint returns employees with birthdays in next 7 days."""
    today = _fixed_today()  # Feb 20, 2026

    # Employee with birthday on Feb 23 → 3 days away
    emp1_data = _make_employee(
        email="bday1@creativefuel.io",
        first_name="Birthday",
        last_name="Soon",
        department_id=test_department["id"],
        location_id=test_location["id"],
    )
    emp1 = Employee(**emp1_data)
    emp1.date_of_birth = date(1992, 2, 23)
    db.add(emp1)

    # Employee with birthday on Mar 15 → too far away
    emp2_data = _make_employee(
        email="bday2@creativefuel.io",
        first_name="Birthday",
        last_name="Far",
        department_id=test_department["id"],
        location_id=test_location["id"],
    )
    emp2 = Employee(**emp2_data)
    emp2.date_of_birth = date(1990, 3, 15)
    db.add(emp2)

    # Employee with birthday today → 0 days away
    emp3_data = _make_employee(
        email="bday3@creativefuel.io",
        first_name="Birthday",
        last_name="Today",
        department_id=test_department["id"],
        location_id=test_location["id"],
    )
    emp3 = Employee(**emp3_data)
    emp3.date_of_birth = date(1988, 2, 20)
    db.add(emp3)

    await db.flush()

    with patch("backend.dashboard.service._today", return_value=today):
        result = await DashboardService.get_upcoming_birthdays(db, days_ahead=7)

    assert result.days_ahead == 7
    assert len(result.data) == 2  # Feb 20 + Feb 23

    # Sorted by days_away
    assert result.data[0].days_away == 0  # Today
    assert result.data[1].days_away == 3  # Feb 23


@pytest.mark.asyncio
async def test_birthdays_excludes_no_dob(db, test_employee):
    """Employees without date_of_birth are excluded from birthdays."""
    today = _fixed_today()
    # test_employee has no DOB set (None by default)

    with patch("backend.dashboard.service._today", return_value=today):
        result = await DashboardService.get_upcoming_birthdays(db, days_ahead=7)

    assert len(result.data) == 0


# ═════════════════════════════════════════════════════════════════════
# 5. NEW JOINERS — Service Layer
# ═════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_new_joiners_last_30_days(db, test_department, test_location):
    """New joiners endpoint returns employees who joined recently."""
    today = _fixed_today()  # Feb 20, 2026

    # Joined 10 days ago → should appear
    emp1_data = _make_employee(
        email="new1@creativefuel.io",
        first_name="New",
        last_name="Joiner1",
        department_id=test_department["id"],
        location_id=test_location["id"],
    )
    emp1 = Employee(**emp1_data)
    emp1.date_of_joining = today - timedelta(days=10)
    db.add(emp1)

    # Joined 60 days ago → too old
    emp2_data = _make_employee(
        email="old1@creativefuel.io",
        first_name="Old",
        last_name="Employee",
        department_id=test_department["id"],
        location_id=test_location["id"],
    )
    emp2 = Employee(**emp2_data)
    emp2.date_of_joining = today - timedelta(days=60)
    db.add(emp2)

    # Joined today → should appear
    emp3_data = _make_employee(
        email="new2@creativefuel.io",
        first_name="New",
        last_name="Joiner2",
        department_id=test_department["id"],
        location_id=test_location["id"],
    )
    emp3 = Employee(**emp3_data)
    emp3.date_of_joining = today
    db.add(emp3)

    await db.flush()

    with patch("backend.dashboard.service._today", return_value=today):
        result = await DashboardService.get_new_joiners(db, days=30)

    assert result.days == 30
    assert result.count == 2
    # Sorted by date_of_joining desc → today first
    assert result.data[0].first_name == "New"
    assert result.data[0].date_of_joining == today


# ═════════════════════════════════════════════════════════════════════
# 6. API ENDPOINT TESTS (via HTTP client)
# ═════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_api_summary_requires_auth(client):
    """GET /summary without auth → 401."""
    resp = await client.get("/api/v1/dashboard/summary")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_api_summary_requires_manager_role(client, db, test_employee):
    """GET /summary with employee role → 403."""
    headers, token = _make_auth_headers(test_employee["id"], role=UserRole.employee)
    await _persist_session(db, test_employee["id"], token)
    await db.commit()

    resp = await client.get("/api/v1/dashboard/summary", headers=headers)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_api_summary_ok_for_hr_admin(client, db, test_employee):
    """GET /summary with hr_admin role → 200 with correct shape."""
    headers, token = _make_auth_headers(test_employee["id"], role=UserRole.hr_admin)
    await _persist_session(db, test_employee["id"], token)
    await db.commit()

    with patch("backend.dashboard.service._today", return_value=_fixed_today()):
        resp = await client.get("/api/v1/dashboard/summary", headers=headers)

    assert resp.status_code == 200
    data = resp.json()
    assert "total_employees" in data
    assert "present_today" in data
    assert "on_leave_today" in data
    assert "pending_leave_requests" in data
    assert "department_breakdown" in data
    assert isinstance(data["department_breakdown"], list)


@pytest.mark.asyncio
async def test_api_attendance_trend_default_30(client, db, test_employee):
    """GET /attendance-trend defaults to 30 days."""
    headers, token = _make_auth_headers(test_employee["id"], role=UserRole.manager)
    await _persist_session(db, test_employee["id"], token)
    await db.commit()

    with patch("backend.dashboard.service._today", return_value=_fixed_today()):
        resp = await client.get(
            "/api/v1/dashboard/attendance-trend", headers=headers
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["period_days"] == 30
    assert len(data["data"]) == 30


@pytest.mark.asyncio
async def test_api_leave_summary_returns_types(client, db, test_employee):
    """GET /leave-summary returns leave types even with no requests."""
    headers, token = _make_auth_headers(test_employee["id"], role=UserRole.hr_admin)
    await _persist_session(db, test_employee["id"], token)

    # Seed leave types
    await _seed_leave_types(db)
    await db.commit()

    with patch("backend.dashboard.service._today", return_value=_fixed_today()):
        resp = await client.get(
            "/api/v1/dashboard/leave-summary", headers=headers
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["month"] == 2
    assert data["year"] == 2026
    assert len(data["by_type"]) == 3


@pytest.mark.asyncio
async def test_api_birthdays_accessible_by_employee(client, db, test_employee):
    """GET /birthdays is accessible to regular employees (not just managers)."""
    headers, token = _make_auth_headers(test_employee["id"], role=UserRole.employee)
    await _persist_session(db, test_employee["id"], token)
    await db.commit()

    with patch("backend.dashboard.service._today", return_value=_fixed_today()):
        resp = await client.get("/api/v1/dashboard/birthdays", headers=headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["days_ahead"] == 7
    assert isinstance(data["data"], list)


@pytest.mark.asyncio
async def test_api_new_joiners_returns_data(client, db, test_employee, test_department, test_location):
    """GET /new-joiners returns recently joined employees."""
    headers, token = _make_auth_headers(test_employee["id"], role=UserRole.hr_admin)
    await _persist_session(db, test_employee["id"], token)

    today = _fixed_today()
    emp_data = _make_employee(
        email="newbie@creativefuel.io",
        first_name="Fresh",
        last_name="Hire",
        department_id=test_department["id"],
        location_id=test_location["id"],
    )
    emp = Employee(**emp_data)
    emp.date_of_joining = today - timedelta(days=5)
    db.add(emp)
    await db.commit()

    with patch("backend.dashboard.service._today", return_value=today):
        resp = await client.get("/api/v1/dashboard/new-joiners", headers=headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["days"] == 30
    assert data["count"] >= 1
    names = [j["first_name"] for j in data["data"]]
    assert "Fresh" in names
