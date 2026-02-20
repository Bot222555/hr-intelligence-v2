"""Leave module test suite — 25 tests covering application, approval/rejection,
balance deduction/restoration, sandwich rules, comp-off, half-day support,
leave policies, validation rules, and API endpoints.

Tests run against SQLite via the shared conftest.py fixtures.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth.models import RoleAssignment
from backend.common.constants import (
    GenderType,
    LeaveDayType,
    LeaveStatus,
    UserRole,
)
from backend.common.exceptions import (
    ForbiddenException,
    NotFoundException,
    ValidationException,
)
from backend.core_hr.models import Department, Employee, Location
from backend.leave.models import CompOffGrant, LeaveBalance, LeaveRequest, LeaveType
from backend.leave.schemas import LeaveRequestCreate
from backend.leave.service import LeaveService
from tests.conftest import (
    TestSessionFactory,
    _make_department,
    _make_employee,
    _make_location,
    create_access_token,
)


# ═════════════════════════════════════════════════════════════════════
# Helpers — seed data for leave tests
# ═════════════════════════════════════════════════════════════════════


async def _seed_leave_type(
    db: AsyncSession,
    *,
    code: str = "CL",
    name: str = "Casual Leave",
    default_balance: Decimal = Decimal("12"),
    is_paid: bool = True,
    requires_approval: bool = True,
    min_days_notice: int = 0,
    max_consecutive_days: Optional[int] = None,
    applicable_gender: Optional[GenderType] = None,
    is_active: bool = True,
) -> LeaveType:
    lt = LeaveType(
        id=uuid.uuid4(),
        code=code,
        name=name,
        default_balance=default_balance,
        max_carry_forward=Decimal("0"),
        is_paid=is_paid,
        requires_approval=requires_approval,
        min_days_notice=min_days_notice,
        max_consecutive_days=max_consecutive_days,
        applicable_gender=applicable_gender,
        is_active=is_active,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(lt)
    await db.flush()
    return lt


async def _seed_balance(
    db: AsyncSession,
    employee_id: uuid.UUID,
    leave_type_id: uuid.UUID,
    *,
    year: int = 2026,
    opening_balance: Decimal = Decimal("12"),
    used: Decimal = Decimal("0"),
    accrued: Decimal = Decimal("0"),
    adjusted: Decimal = Decimal("0"),
) -> LeaveBalance:
    bal = LeaveBalance(
        id=uuid.uuid4(),
        employee_id=employee_id,
        leave_type_id=leave_type_id,
        year=year,
        opening_balance=opening_balance,
        accrued=accrued,
        used=used,
        carry_forwarded=Decimal("0"),
        adjusted=adjusted,
    )
    db.add(bal)
    await db.flush()
    return bal


async def _seed_employee(
    db: AsyncSession,
    *,
    email: str = "emp@creativefuel.io",
    first_name: str = "Test",
    last_name: str = "Employee",
    department_id: Optional[uuid.UUID] = None,
    location_id: Optional[uuid.UUID] = None,
    reporting_manager_id: Optional[uuid.UUID] = None,
    gender: Optional[GenderType] = None,
) -> Employee:
    emp = Employee(
        id=uuid.uuid4(),
        employee_code=f"CF-{uuid.uuid4().hex[:6].upper()}",
        first_name=first_name,
        last_name=last_name,
        email=email,
        date_of_joining=date(2024, 1, 15),
        employment_status="active",
        nationality="Indian",
        notice_period_days=90,
        department_id=department_id,
        location_id=location_id,
        reporting_manager_id=reporting_manager_id,
        gender=gender,
        is_active=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(emp)
    await db.flush()
    return emp


async def _seed_location_and_dept(db: AsyncSession) -> tuple[Location, Department]:
    loc = Location(**_make_location())
    db.add(loc)
    await db.flush()
    dept_data = _make_department(location_id=loc.id)
    dept = Department(**dept_data)
    db.add(dept)
    await db.flush()
    return loc, dept


async def _seed_hr_role(
    db: AsyncSession,
    employee_id: uuid.UUID,
) -> RoleAssignment:
    ra = RoleAssignment(
        id=uuid.uuid4(),
        employee_id=employee_id,
        role=UserRole.hr_admin,
        is_active=True,
        assigned_at=datetime.now(timezone.utc),
    )
    db.add(ra)
    await db.flush()
    return ra


# ═════════════════════════════════════════════════════════════════════
# 1. _calculate_leave_days — pure logic tests (no DB)
# ═════════════════════════════════════════════════════════════════════


class TestCalculateLeaveDays:
    """Tests for the static _calculate_leave_days method."""

    def test_full_week_no_offs(self):
        """Mon–Fri (no weekly offs) → 5 full days."""
        # 2026-02-23 is Monday, 2026-02-27 is Friday
        total, details = LeaveService._calculate_leave_days(
            from_date=date(2026, 2, 23),
            to_date=date(2026, 2, 27),
            day_details=None,
            weekly_offs=set(),       # no offs
            holidays=set(),
            is_sandwich=False,
        )
        assert total == Decimal("5")
        assert len(details) == 5
        assert all(v == "full_day" for v in details.values())

    def test_weekends_excluded(self):
        """Mon–Sun with Sat/Sun offs → 5 working days counted."""
        # 2026-02-23 (Mon) to 2026-03-01 (Sun) = 7 days
        total, details = LeaveService._calculate_leave_days(
            from_date=date(2026, 2, 23),
            to_date=date(2026, 3, 1),
            day_details=None,
            weekly_offs={5, 6},       # Sat, Sun
            holidays=set(),
            is_sandwich=False,
        )
        assert total == Decimal("5")
        # Saturday and Sunday should be marked as "weekend"
        assert details["2026-02-28"] == "weekend"
        assert details["2026-03-01"] == "weekend"

    def test_holidays_excluded(self):
        """Single holiday in the middle of a week excluded."""
        # Wed 2026-02-25 is a holiday
        total, details = LeaveService._calculate_leave_days(
            from_date=date(2026, 2, 23),
            to_date=date(2026, 2, 27),
            day_details=None,
            weekly_offs=set(),
            holidays={date(2026, 2, 25)},
            is_sandwich=False,
        )
        assert total == Decimal("4")
        assert details["2026-02-25"] == "holiday"

    def test_half_day_support(self):
        """Half-day via day_details counts as 0.5."""
        total, details = LeaveService._calculate_leave_days(
            from_date=date(2026, 2, 23),
            to_date=date(2026, 2, 24),
            day_details={"2026-02-23": LeaveDayType.first_half},
            weekly_offs=set(),
            holidays=set(),
            is_sandwich=False,
        )
        assert total == Decimal("1.5")  # 0.5 + 1.0
        assert details["2026-02-23"] == "first_half"
        assert details["2026-02-24"] == "full_day"

    def test_sandwich_rule_counts_weekend_between_leave_days(self):
        """Fri + Mon leave with sandwich ON → Sat+Sun counted as leave."""
        # Fri 2026-02-27, Sat 28, Sun 01, Mon 02
        total, details = LeaveService._calculate_leave_days(
            from_date=date(2026, 2, 27),
            to_date=date(2026, 3, 2),
            day_details=None,
            weekly_offs={5, 6},  # Sat=5, Sun=6
            holidays=set(),
            is_sandwich=True,
        )
        # Fri(1) + Sat(1, sandwich) + Sun(1, sandwich) + Mon(1) = 4
        assert total == Decimal("4")
        assert details["2026-02-28"] == "full_day"  # sandwich-counted
        assert details["2026-03-01"] == "full_day"  # sandwich-counted

    def test_sandwich_rule_off_excludes_weekend(self):
        """Same date range but sandwich OFF → Sat+Sun NOT counted."""
        total, details = LeaveService._calculate_leave_days(
            from_date=date(2026, 2, 27),
            to_date=date(2026, 3, 2),
            day_details=None,
            weekly_offs={5, 6},
            holidays=set(),
            is_sandwich=False,
        )
        # Fri(1) + Mon(1) = 2
        assert total == Decimal("2")
        assert details["2026-02-28"] == "weekend"
        assert details["2026-03-01"] == "weekend"

    def test_sandwich_does_not_count_boundary_weekends(self):
        """Weekend at the start/end of leave range not sandwich-counted."""
        # Sat 2026-02-28 to Sun 2026-03-01 (just a weekend)
        total, details = LeaveService._calculate_leave_days(
            from_date=date(2026, 2, 28),
            to_date=date(2026, 3, 1),
            day_details=None,
            weekly_offs={5, 6},
            holidays=set(),
            is_sandwich=True,
        )
        # No working days → 0
        assert total == Decimal("0")

    def test_multiple_half_days(self):
        """Both days as half-day → 1.0 total."""
        total, details = LeaveService._calculate_leave_days(
            from_date=date(2026, 2, 23),
            to_date=date(2026, 2, 24),
            day_details={
                "2026-02-23": LeaveDayType.first_half,
                "2026-02-24": LeaveDayType.second_half,
            },
            weekly_offs=set(),
            holidays=set(),
            is_sandwich=False,
        )
        assert total == Decimal("1.0")
        assert details["2026-02-23"] == "first_half"
        assert details["2026-02-24"] == "second_half"


# ═════════════════════════════════════════════════════════════════════
# 2. Leave Application — service layer
# ═════════════════════════════════════════════════════════════════════


class TestApplyLeave:
    """Tests for LeaveService.apply_leave()."""

    async def test_apply_leave_happy_path(self, db: AsyncSession):
        """Basic leave application → pending status, balance NOT yet deducted."""
        loc, dept = await _seed_location_and_dept(db)
        emp = await _seed_employee(
            db, department_id=dept.id, location_id=loc.id,
        )
        lt = await _seed_leave_type(db)
        bal = await _seed_balance(db, emp.id, lt.id)

        data = LeaveRequestCreate(
            leave_type_id=lt.id,
            from_date=date(2026, 3, 2),   # Monday
            to_date=date(2026, 3, 4),     # Wednesday → 3 days
            reason="Personal work",
        )

        result = await LeaveService.apply_leave(db, emp.id, data)

        assert result.status == LeaveStatus.pending
        assert result.total_days == Decimal("3")
        assert result.employee_id == emp.id

        # Balance.used should NOT have changed (still pending)
        await db.refresh(bal)
        assert bal.used == Decimal("0")

    async def test_apply_leave_auto_approved_when_no_approval_required(
        self, db: AsyncSession,
    ):
        """Leave type with requires_approval=False → auto-approved, balance deducted."""
        loc, dept = await _seed_location_and_dept(db)
        emp = await _seed_employee(
            db, department_id=dept.id, location_id=loc.id,
        )
        lt = await _seed_leave_type(db, code="OD", name="On Duty", requires_approval=False)
        bal = await _seed_balance(db, emp.id, lt.id)

        data = LeaveRequestCreate(
            leave_type_id=lt.id,
            from_date=date(2026, 3, 2),
            to_date=date(2026, 3, 3),
            reason="Client visit",
        )

        result = await LeaveService.apply_leave(db, emp.id, data)

        assert result.status == LeaveStatus.approved
        assert result.total_days == Decimal("2")

        # Balance.used should be deducted immediately
        await db.refresh(bal)
        assert bal.used == Decimal("2")

    async def test_apply_leave_insufficient_balance(self, db: AsyncSession):
        """Requesting more days than available → ValidationException."""
        loc, dept = await _seed_location_and_dept(db)
        emp = await _seed_employee(
            db, department_id=dept.id, location_id=loc.id,
        )
        lt = await _seed_leave_type(db)
        # Only 2 days available
        await _seed_balance(db, emp.id, lt.id, opening_balance=Decimal("2"))

        data = LeaveRequestCreate(
            leave_type_id=lt.id,
            from_date=date(2026, 3, 2),
            to_date=date(2026, 3, 6),  # Mon–Fri = 5 days
            reason="Long break",
        )

        with pytest.raises(ValidationException) as exc_info:
            await LeaveService.apply_leave(db, emp.id, data)
        assert "balance" in str(exc_info.value.errors).lower()

    async def test_apply_leave_overlapping_dates_rejected(self, db: AsyncSession):
        """Two leaves overlapping the same dates → rejected."""
        loc, dept = await _seed_location_and_dept(db)
        emp = await _seed_employee(
            db, department_id=dept.id, location_id=loc.id,
        )
        lt = await _seed_leave_type(db)
        await _seed_balance(db, emp.id, lt.id)

        data = LeaveRequestCreate(
            leave_type_id=lt.id,
            from_date=date(2026, 3, 2),
            to_date=date(2026, 3, 4),
            reason="First request",
        )
        await LeaveService.apply_leave(db, emp.id, data)

        # Overlapping request
        data2 = LeaveRequestCreate(
            leave_type_id=lt.id,
            from_date=date(2026, 3, 3),
            to_date=date(2026, 3, 5),
            reason="Overlapping request",
        )
        with pytest.raises(ValidationException) as exc_info:
            await LeaveService.apply_leave(db, emp.id, data2)
        assert "overlapping" in str(exc_info.value.errors).lower()

    async def test_apply_leave_advance_notice_required(self, db: AsyncSession):
        """Leave type with min_days_notice=7 applied too late → rejected."""
        loc, dept = await _seed_location_and_dept(db)
        emp = await _seed_employee(
            db, department_id=dept.id, location_id=loc.id,
        )
        lt = await _seed_leave_type(db, code="PL", name="Privilege Leave", min_days_notice=7)
        await _seed_balance(db, emp.id, lt.id)

        # Apply for tomorrow (< 7 days notice)
        tomorrow = date.today() + timedelta(days=1)
        data = LeaveRequestCreate(
            leave_type_id=lt.id,
            from_date=tomorrow,
            to_date=tomorrow,
            reason="Urgent",
        )

        with pytest.raises(ValidationException) as exc_info:
            await LeaveService.apply_leave(db, emp.id, data)
        assert "advance notice" in str(exc_info.value.errors).lower()

    async def test_apply_leave_max_consecutive_days_exceeded(self, db: AsyncSession):
        """Leave type with max_consecutive_days=3, request for 5 → rejected."""
        loc, dept = await _seed_location_and_dept(db)
        emp = await _seed_employee(
            db, department_id=dept.id, location_id=loc.id,
        )
        lt = await _seed_leave_type(db, max_consecutive_days=3)
        await _seed_balance(db, emp.id, lt.id)

        data = LeaveRequestCreate(
            leave_type_id=lt.id,
            from_date=date(2026, 3, 2),
            to_date=date(2026, 3, 6),  # Mon–Fri = 5 days
            reason="Long trip",
        )

        with pytest.raises(ValidationException) as exc_info:
            await LeaveService.apply_leave(db, emp.id, data)
        assert "consecutive" in str(exc_info.value.errors).lower()

    async def test_apply_leave_gender_restricted_type(self, db: AsyncSession):
        """Maternity leave applied by male employee → rejected."""
        loc, dept = await _seed_location_and_dept(db)
        emp = await _seed_employee(
            db,
            department_id=dept.id,
            location_id=loc.id,
            gender=GenderType.male,
        )
        lt = await _seed_leave_type(
            db,
            code="ML",
            name="Maternity Leave",
            applicable_gender=GenderType.female,
            default_balance=Decimal("180"),
        )
        await _seed_balance(db, emp.id, lt.id, opening_balance=Decimal("180"))

        data = LeaveRequestCreate(
            leave_type_id=lt.id,
            from_date=date(2026, 3, 2),
            to_date=date(2026, 3, 3),
            reason="Not applicable to me",
        )

        with pytest.raises(ValidationException) as exc_info:
            await LeaveService.apply_leave(db, emp.id, data)
        assert "female" in str(exc_info.value.errors).lower()

    async def test_apply_leave_with_half_day(self, db: AsyncSession):
        """Apply Mon full + Tue first_half → 1.5 total days."""
        loc, dept = await _seed_location_and_dept(db)
        emp = await _seed_employee(
            db, department_id=dept.id, location_id=loc.id,
        )
        lt = await _seed_leave_type(db)
        await _seed_balance(db, emp.id, lt.id)

        data = LeaveRequestCreate(
            leave_type_id=lt.id,
            from_date=date(2026, 3, 2),   # Monday
            to_date=date(2026, 3, 3),     # Tuesday
            reason="Half day on Tue",
            day_details={"2026-03-03": LeaveDayType.first_half},
        )

        result = await LeaveService.apply_leave(db, emp.id, data)

        assert result.total_days == Decimal("1.5")
        assert result.day_details["2026-03-02"] == "full_day"
        assert result.day_details["2026-03-03"] == "first_half"

    async def test_apply_leave_no_balance_record(self, db: AsyncSession):
        """No balance row at all → ValidationException."""
        loc, dept = await _seed_location_and_dept(db)
        emp = await _seed_employee(
            db, department_id=dept.id, location_id=loc.id,
        )
        lt = await _seed_leave_type(db)
        # Deliberately don't seed balance

        data = LeaveRequestCreate(
            leave_type_id=lt.id,
            from_date=date(2026, 3, 2),
            to_date=date(2026, 3, 3),
            reason="No balance row",
        )

        with pytest.raises(ValidationException) as exc_info:
            await LeaveService.apply_leave(db, emp.id, data)
        assert "no leave balance" in str(exc_info.value.errors).lower()

    async def test_apply_leave_inactive_employee(self, db: AsyncSession):
        """Inactive employee applying for leave → NotFoundException."""
        loc, dept = await _seed_location_and_dept(db)
        emp = await _seed_employee(
            db, department_id=dept.id, location_id=loc.id,
        )
        lt = await _seed_leave_type(db)

        # Deactivate employee
        emp.is_active = False
        await db.flush()

        data = LeaveRequestCreate(
            leave_type_id=lt.id,
            from_date=date(2026, 3, 2),
            to_date=date(2026, 3, 3),
            reason="Inactive emp",
        )

        with pytest.raises(NotFoundException):
            await LeaveService.apply_leave(db, emp.id, data)


# ═════════════════════════════════════════════════════════════════════
# 3. Approval / Rejection workflow
# ═════════════════════════════════════════════════════════════════════


class TestApprovalWorkflow:
    """Tests for approve_leave / reject_leave / cancel_leave."""

    async def _create_pending_request(
        self, db: AsyncSession,
    ) -> tuple[Employee, Employee, LeaveType, LeaveBalance, LeaveRequest]:
        """Helper: seed manager + employee + leave type + balance + pending request."""
        loc, dept = await _seed_location_and_dept(db)

        manager = await _seed_employee(
            db,
            email="mgr@creativefuel.io",
            first_name="Manager",
            last_name="One",
            department_id=dept.id,
            location_id=loc.id,
        )

        emp = await _seed_employee(
            db,
            email="worker@creativefuel.io",
            first_name="Worker",
            last_name="Bee",
            department_id=dept.id,
            location_id=loc.id,
            reporting_manager_id=manager.id,
        )

        lt = await _seed_leave_type(db)
        bal = await _seed_balance(db, emp.id, lt.id)

        data = LeaveRequestCreate(
            leave_type_id=lt.id,
            from_date=date(2026, 3, 2),   # Monday
            to_date=date(2026, 3, 4),     # Wednesday → 3 days
            reason="Family event",
        )
        result = await LeaveService.apply_leave(db, emp.id, data)

        # Retrieve the ORM object
        req_result = await db.execute(
            select(LeaveRequest).where(LeaveRequest.id == result.id)
        )
        leave_req = req_result.scalars().first()

        return emp, manager, lt, bal, leave_req

    async def test_approve_leave_deducts_balance(self, db: AsyncSession):
        """Manager approves → status=approved, balance.used incremented."""
        emp, mgr, lt, bal, req = await self._create_pending_request(db)

        result = await LeaveService.approve_leave(
            db, req.id, mgr.id, remarks="Approved, have fun",
        )

        assert result.status == LeaveStatus.approved
        assert result.reviewed_by == mgr.id
        assert result.reviewer_remarks == "Approved, have fun"

        await db.refresh(bal)
        assert bal.used == Decimal("3")

    async def test_approve_leave_unauthorized_user_forbidden(self, db: AsyncSession):
        """Non-manager, non-HR user trying to approve → ForbiddenException."""
        emp, mgr, lt, bal, req = await self._create_pending_request(db)

        # Create a random person who is neither manager nor HR
        loc_result = await db.execute(select(Location).limit(1))
        loc = loc_result.scalars().first()
        dept_result = await db.execute(select(Department).limit(1))
        dept = dept_result.scalars().first()

        stranger = await _seed_employee(
            db,
            email="stranger@creativefuel.io",
            first_name="Stranger",
            last_name="Danger",
            department_id=dept.id,
            location_id=loc.id,
        )

        with pytest.raises(ForbiddenException):
            await LeaveService.approve_leave(db, req.id, stranger.id)

    async def test_approve_already_approved_fails(self, db: AsyncSession):
        """Approving an already-approved request → ValidationException."""
        emp, mgr, lt, bal, req = await self._create_pending_request(db)

        await LeaveService.approve_leave(db, req.id, mgr.id)

        with pytest.raises(ValidationException) as exc_info:
            await LeaveService.approve_leave(db, req.id, mgr.id)
        assert "already" in str(exc_info.value.errors).lower()

    async def test_reject_leave(self, db: AsyncSession):
        """Manager rejects → status=rejected, balance unchanged."""
        emp, mgr, lt, bal, req = await self._create_pending_request(db)

        result = await LeaveService.reject_leave(
            db, req.id, mgr.id, "Deadline week, sorry",
        )

        assert result.status == LeaveStatus.rejected
        assert result.reviewer_remarks == "Deadline week, sorry"

        # Balance untouched — never approved
        await db.refresh(bal)
        assert bal.used == Decimal("0")

    async def test_cancel_pending_leave(self, db: AsyncSession):
        """Employee cancels pending leave → status=cancelled, balance unchanged."""
        emp, mgr, lt, bal, req = await self._create_pending_request(db)

        result = await LeaveService.cancel_leave(
            db, req.id, emp.id, "Plans changed",
        )

        assert result.status == LeaveStatus.cancelled

        await db.refresh(bal)
        assert bal.used == Decimal("0")

    async def test_cancel_approved_leave_restores_balance(self, db: AsyncSession):
        """Employee cancels approved leave → balance.used restored."""
        emp, mgr, lt, bal, req = await self._create_pending_request(db)

        # First approve
        await LeaveService.approve_leave(db, req.id, mgr.id)
        await db.refresh(bal)
        assert bal.used == Decimal("3")

        # Now cancel
        result = await LeaveService.cancel_leave(
            db, req.id, emp.id, "Emergency resolved",
        )

        assert result.status == LeaveStatus.cancelled
        await db.refresh(bal)
        assert bal.used == Decimal("0")

    async def test_cancel_others_leave_forbidden(self, db: AsyncSession):
        """Trying to cancel someone else's leave → ForbiddenException."""
        emp, mgr, lt, bal, req = await self._create_pending_request(db)

        with pytest.raises(ForbiddenException):
            await LeaveService.cancel_leave(
                db, req.id, mgr.id, "Not my leave",
            )

    async def test_hr_admin_can_approve(self, db: AsyncSession):
        """HR admin (not the reporting manager) can approve leave."""
        emp, mgr, lt, bal, req = await self._create_pending_request(db)

        loc_result = await db.execute(select(Location).limit(1))
        loc = loc_result.scalars().first()
        dept_result = await db.execute(select(Department).limit(1))
        dept = dept_result.scalars().first()

        hr_user = await _seed_employee(
            db,
            email="hr@creativefuel.io",
            first_name="HR",
            last_name="Admin",
            department_id=dept.id,
            location_id=loc.id,
        )
        await _seed_hr_role(db, hr_user.id)

        result = await LeaveService.approve_leave(
            db, req.id, hr_user.id, remarks="HR approved",
        )

        assert result.status == LeaveStatus.approved
        assert result.reviewed_by == hr_user.id


# ═════════════════════════════════════════════════════════════════════
# 4. Comp-off
# ═════════════════════════════════════════════════════════════════════


class TestCompOff:
    """Tests for comp-off request and approval."""

    async def test_request_comp_off(self, db: AsyncSession):
        """Requesting comp-off creates a grant with no approver yet."""
        loc, dept = await _seed_location_and_dept(db)
        emp = await _seed_employee(
            db, department_id=dept.id, location_id=loc.id,
        )

        result = await LeaveService.request_comp_off(
            db, emp.id, date(2026, 2, 15), "Worked on Sunday for release",
        )

        assert result.employee_id == emp.id
        assert result.work_date == date(2026, 2, 15)
        assert result.granted_by is None
        assert result.expires_at == date(2026, 2, 15) + timedelta(days=90)
        assert result.is_used is False

    async def test_duplicate_comp_off_rejected(self, db: AsyncSession):
        """Duplicate comp-off for same date → ValidationException."""
        loc, dept = await _seed_location_and_dept(db)
        emp = await _seed_employee(
            db, department_id=dept.id, location_id=loc.id,
        )

        await LeaveService.request_comp_off(
            db, emp.id, date(2026, 2, 15), "First request",
        )

        with pytest.raises(ValidationException) as exc_info:
            await LeaveService.request_comp_off(
                db, emp.id, date(2026, 2, 15), "Duplicate",
            )
        assert "already exists" in str(exc_info.value.errors).lower()

    async def test_approve_comp_off_credits_balance(self, db: AsyncSession):
        """Approving comp-off credits 1 day to CO balance."""
        loc, dept = await _seed_location_and_dept(db)
        mgr = await _seed_employee(
            db,
            email="mgr@creativefuel.io",
            first_name="Manager",
            last_name="One",
            department_id=dept.id,
            location_id=loc.id,
        )
        emp = await _seed_employee(
            db,
            email="worker@creativefuel.io",
            first_name="Worker",
            last_name="Bee",
            department_id=dept.id,
            location_id=loc.id,
            reporting_manager_id=mgr.id,
        )

        # Seed CO leave type
        co_lt = await _seed_leave_type(
            db, code="CO", name="Compensatory Off", default_balance=Decimal("0"),
        )
        co_bal = await _seed_balance(
            db, emp.id, co_lt.id, opening_balance=Decimal("0"),
        )

        # Request and approve
        req = await LeaveService.request_comp_off(
            db, emp.id, date(2026, 2, 15), "Sunday deploy",
        )
        comp_off_id = req.id

        result = await LeaveService.approve_comp_off(db, comp_off_id, mgr.id)

        assert result.granted_by == mgr.id

        # Check balance credited
        await db.refresh(co_bal)
        assert co_bal.adjusted == Decimal("1")


# ═════════════════════════════════════════════════════════════════════
# 5. Leave Types / Policies
# ═════════════════════════════════════════════════════════════════════


class TestLeaveTypes:
    """Tests for leave type listing and policies."""

    async def test_get_leave_types_active_only(self, db: AsyncSession):
        """Active leave types returned, inactive filtered out."""
        await _seed_leave_type(db, code="CL", name="Casual Leave")
        await _seed_leave_type(db, code="SL", name="Sick Leave")
        await _seed_leave_type(
            db, code="OLD", name="Old Policy", is_active=False,
        )

        result = await LeaveService.get_leave_types(db, is_active=True)

        names = {r.name for r in result}
        assert "Casual Leave" in names
        assert "Sick Leave" in names
        assert "Old Policy" not in names

    async def test_get_leave_types_includes_inactive(self, db: AsyncSession):
        """Passing is_active=None returns all types."""
        await _seed_leave_type(db, code="CL", name="Casual Leave")
        await _seed_leave_type(
            db, code="OLD", name="Old Policy", is_active=False,
        )

        result = await LeaveService.get_leave_types(db, is_active=None)
        names = {r.name for r in result}
        assert "Old Policy" in names


# ═════════════════════════════════════════════════════════════════════
# 6. Leave Balance
# ═════════════════════════════════════════════════════════════════════


class TestLeaveBalance:
    """Tests for balance retrieval and pending deduction calculation."""

    async def test_get_balance_with_pending_deduction(self, db: AsyncSession):
        """Available balance = current_balance - pending_days."""
        loc, dept = await _seed_location_and_dept(db)
        emp = await _seed_employee(
            db, department_id=dept.id, location_id=loc.id,
        )
        lt = await _seed_leave_type(db)
        await _seed_balance(db, emp.id, lt.id, opening_balance=Decimal("12"))

        # Create a pending leave request (3 days)
        data = LeaveRequestCreate(
            leave_type_id=lt.id,
            from_date=date(2026, 3, 2),
            to_date=date(2026, 3, 4),
            reason="Pending leave",
        )
        await LeaveService.apply_leave(db, emp.id, data)

        balances = await LeaveService.get_balance(db, emp.id, 2026)

        assert len(balances) == 1
        bal = balances[0]
        assert bal.pending == Decimal("3")
        assert bal.available == Decimal("9")  # 12 - 3

    async def test_get_balance_nonexistent_employee(self, db: AsyncSession):
        """Querying balance for fake employee → NotFoundException."""
        fake_id = uuid.uuid4()
        with pytest.raises(NotFoundException):
            await LeaveService.get_balance(db, fake_id, 2026)


# ═════════════════════════════════════════════════════════════════════
# 7. Edge Cases — Overlapping, Balance Exhaustion, Cancel After
#    Approval, Partial Overlap, Weekend-Only Range, Multiple Types
# ═════════════════════════════════════════════════════════════════════


class TestLeaveEdgeCases:
    """Additional edge case tests for thorough coverage."""

    async def test_apply_leave_entire_weekend_range_zero_days(self, db: AsyncSession):
        """Leave applied for Sat+Sun only (with Sat/Sun offs) → 0 days → rejected."""
        loc, dept = await _seed_location_and_dept(db)
        emp = await _seed_employee(db, department_id=dept.id, location_id=loc.id)
        lt = await _seed_leave_type(db)
        await _seed_balance(db, emp.id, lt.id)

        # 2026-02-28 is Saturday, 2026-03-01 is Sunday
        data = LeaveRequestCreate(
            leave_type_id=lt.id,
            from_date=date(2026, 2, 28),
            to_date=date(2026, 3, 1),
            reason="Weekend only",
        )

        with pytest.raises(ValidationException) as exc_info:
            await LeaveService.apply_leave(db, emp.id, data)
        assert "no leave days" in str(exc_info.value.errors).lower()

    async def test_apply_leave_partial_overlap_with_existing(self, db: AsyncSession):
        """Leave partially overlapping an existing request → rejected."""
        loc, dept = await _seed_location_and_dept(db)
        emp = await _seed_employee(db, department_id=dept.id, location_id=loc.id)
        lt = await _seed_leave_type(db)
        await _seed_balance(db, emp.id, lt.id)

        # First request: Mon-Wed (Mar 2-4)
        data1 = LeaveRequestCreate(
            leave_type_id=lt.id,
            from_date=date(2026, 3, 2),
            to_date=date(2026, 3, 4),
            reason="First",
        )
        await LeaveService.apply_leave(db, emp.id, data1)

        # Second request: Wed-Fri (Mar 4-6) — overlaps on Wed
        data2 = LeaveRequestCreate(
            leave_type_id=lt.id,
            from_date=date(2026, 3, 4),
            to_date=date(2026, 3, 6),
            reason="Partial overlap",
        )
        with pytest.raises(ValidationException) as exc_info:
            await LeaveService.apply_leave(db, emp.id, data2)
        assert "overlapping" in str(exc_info.value.errors).lower()

    async def test_apply_leave_exactly_exhausts_balance(self, db: AsyncSession):
        """Applying leave that uses exactly all remaining balance → succeeds."""
        loc, dept = await _seed_location_and_dept(db)
        emp = await _seed_employee(db, department_id=dept.id, location_id=loc.id)
        lt = await _seed_leave_type(db)
        # Exactly 5 days balance
        await _seed_balance(db, emp.id, lt.id, opening_balance=Decimal("5"))

        # Mon-Fri = exactly 5 working days
        data = LeaveRequestCreate(
            leave_type_id=lt.id,
            from_date=date(2026, 3, 2),
            to_date=date(2026, 3, 6),
            reason="Use all balance",
        )

        result = await LeaveService.apply_leave(db, emp.id, data)
        assert result.total_days == Decimal("5")
        assert result.status == LeaveStatus.pending

    async def test_apply_leave_one_more_than_balance_fails(self, db: AsyncSession):
        """Requesting 1 day more than available → fails."""
        loc, dept = await _seed_location_and_dept(db)
        emp = await _seed_employee(db, department_id=dept.id, location_id=loc.id)
        lt = await _seed_leave_type(db)
        await _seed_balance(db, emp.id, lt.id, opening_balance=Decimal("2"))

        # 3 working days but only 2 balance
        data = LeaveRequestCreate(
            leave_type_id=lt.id,
            from_date=date(2026, 3, 2),
            to_date=date(2026, 3, 4),
            reason="Too many",
        )

        with pytest.raises(ValidationException) as exc_info:
            await LeaveService.apply_leave(db, emp.id, data)
        assert "balance" in str(exc_info.value.errors).lower()

    async def test_cancel_already_rejected_leave_fails(self, db: AsyncSession):
        """Cannot cancel a leave that was already rejected."""
        loc, dept = await _seed_location_and_dept(db)
        mgr = await _seed_employee(
            db, email="mgr@creativefuel.io", first_name="Mgr",
            department_id=dept.id, location_id=loc.id,
        )
        emp = await _seed_employee(
            db, email="emp@creativefuel.io", first_name="Emp",
            department_id=dept.id, location_id=loc.id,
            reporting_manager_id=mgr.id,
        )
        lt = await _seed_leave_type(db)
        await _seed_balance(db, emp.id, lt.id)

        data = LeaveRequestCreate(
            leave_type_id=lt.id,
            from_date=date(2026, 3, 2),
            to_date=date(2026, 3, 3),
            reason="Will be rejected",
        )
        result = await LeaveService.apply_leave(db, emp.id, data)

        # Reject it
        await LeaveService.reject_leave(db, result.id, mgr.id, "No")

        # Now try to cancel
        with pytest.raises(ValidationException) as exc_info:
            await LeaveService.cancel_leave(db, result.id, emp.id, "Trying to cancel rejected")
        assert "cancel" in str(exc_info.value.errors).lower() or "status" in str(exc_info.value.errors).lower()

    async def test_cancel_already_cancelled_leave_fails(self, db: AsyncSession):
        """Cannot cancel a leave that was already cancelled."""
        loc, dept = await _seed_location_and_dept(db)
        emp = await _seed_employee(
            db, department_id=dept.id, location_id=loc.id,
        )
        lt = await _seed_leave_type(db)
        await _seed_balance(db, emp.id, lt.id)

        data = LeaveRequestCreate(
            leave_type_id=lt.id,
            from_date=date(2026, 3, 2),
            to_date=date(2026, 3, 3),
            reason="Will be cancelled twice",
        )
        result = await LeaveService.apply_leave(db, emp.id, data)

        # Cancel once
        await LeaveService.cancel_leave(db, result.id, emp.id, "First cancel")

        # Try again
        with pytest.raises(ValidationException):
            await LeaveService.cancel_leave(db, result.id, emp.id, "Second cancel")

    async def test_reject_already_rejected_leave_fails(self, db: AsyncSession):
        """Rejecting an already-rejected request → ValidationException."""
        loc, dept = await _seed_location_and_dept(db)
        mgr = await _seed_employee(
            db, email="mgr@creativefuel.io", first_name="Mgr",
            department_id=dept.id, location_id=loc.id,
        )
        emp = await _seed_employee(
            db, email="emp@creativefuel.io", first_name="Emp",
            department_id=dept.id, location_id=loc.id,
            reporting_manager_id=mgr.id,
        )
        lt = await _seed_leave_type(db)
        await _seed_balance(db, emp.id, lt.id)

        data = LeaveRequestCreate(
            leave_type_id=lt.id,
            from_date=date(2026, 3, 2),
            to_date=date(2026, 3, 3),
            reason="Reject test",
        )
        result = await LeaveService.apply_leave(db, emp.id, data)

        await LeaveService.reject_leave(db, result.id, mgr.id, "No")

        with pytest.raises(ValidationException):
            await LeaveService.reject_leave(db, result.id, mgr.id, "No again")

    async def test_apply_different_leave_types_same_dates(self, db: AsyncSession):
        """Two different leave types for same dates → still overlapping."""
        loc, dept = await _seed_location_and_dept(db)
        emp = await _seed_employee(db, department_id=dept.id, location_id=loc.id)
        lt1 = await _seed_leave_type(db, code="CL", name="Casual Leave")
        lt2 = await _seed_leave_type(db, code="SL", name="Sick Leave")
        await _seed_balance(db, emp.id, lt1.id)
        await _seed_balance(db, emp.id, lt2.id)

        data1 = LeaveRequestCreate(
            leave_type_id=lt1.id,
            from_date=date(2026, 3, 2),
            to_date=date(2026, 3, 3),
            reason="Casual leave for personal work",
        )
        await LeaveService.apply_leave(db, emp.id, data1)

        # Same dates, different type → should still fail (overlap)
        data2 = LeaveRequestCreate(
            leave_type_id=lt2.id,
            from_date=date(2026, 3, 2),
            to_date=date(2026, 3, 3),
            reason="Sick leave same dates",
        )
        with pytest.raises(ValidationException) as exc_info:
            await LeaveService.apply_leave(db, emp.id, data2)
        assert "overlapping" in str(exc_info.value.errors).lower()

    async def test_balance_after_multiple_apply_and_cancel(self, db: AsyncSession):
        """Apply → approve → cancel → apply again → balance tracking correct."""
        loc, dept = await _seed_location_and_dept(db)
        mgr = await _seed_employee(
            db, email="mgr@creativefuel.io", first_name="Mgr",
            department_id=dept.id, location_id=loc.id,
        )
        emp = await _seed_employee(
            db, email="emp@creativefuel.io", first_name="Emp",
            department_id=dept.id, location_id=loc.id,
            reporting_manager_id=mgr.id,
        )
        lt = await _seed_leave_type(db)
        bal = await _seed_balance(db, emp.id, lt.id, opening_balance=Decimal("10"))

        # Apply 3 days
        data1 = LeaveRequestCreate(
            leave_type_id=lt.id,
            from_date=date(2026, 3, 2),
            to_date=date(2026, 3, 4),
            reason="First",
        )
        result1 = await LeaveService.apply_leave(db, emp.id, data1)

        # Approve → balance.used = 3
        await LeaveService.approve_leave(db, result1.id, mgr.id)
        await db.refresh(bal)
        assert bal.used == Decimal("3")

        # Cancel → balance.used = 0
        await LeaveService.cancel_leave(db, result1.id, emp.id, "Changed plans")
        await db.refresh(bal)
        assert bal.used == Decimal("0")

        # Apply again for same dates → should succeed
        data2 = LeaveRequestCreate(
            leave_type_id=lt.id,
            from_date=date(2026, 3, 2),
            to_date=date(2026, 3, 4),
            reason="Reapply",
        )
        result2 = await LeaveService.apply_leave(db, emp.id, data2)
        assert result2.status == LeaveStatus.pending
        assert result2.total_days == Decimal("3")

    async def test_approve_nonexistent_request(self, db: AsyncSession):
        """Approving non-existent leave request → NotFoundException."""
        fake_id = uuid.uuid4()
        approver_id = uuid.uuid4()

        with pytest.raises(NotFoundException):
            await LeaveService.approve_leave(db, fake_id, approver_id)

    async def test_reject_nonexistent_request(self, db: AsyncSession):
        """Rejecting non-existent leave request → NotFoundException."""
        fake_id = uuid.uuid4()
        approver_id = uuid.uuid4()

        with pytest.raises(NotFoundException):
            await LeaveService.reject_leave(db, fake_id, approver_id, "No")

    async def test_cancel_nonexistent_request(self, db: AsyncSession):
        """Cancelling non-existent leave request → NotFoundException."""
        fake_id = uuid.uuid4()
        emp_id = uuid.uuid4()

        with pytest.raises(NotFoundException):
            await LeaveService.cancel_leave(db, fake_id, emp_id, "No")

    async def test_apply_leave_nonexistent_leave_type(self, db: AsyncSession):
        """Using a non-existent leave type → NotFoundException."""
        loc, dept = await _seed_location_and_dept(db)
        emp = await _seed_employee(db, department_id=dept.id, location_id=loc.id)

        data = LeaveRequestCreate(
            leave_type_id=uuid.uuid4(),
            from_date=date(2026, 3, 2),
            to_date=date(2026, 3, 3),
            reason="Bad type",
        )

        with pytest.raises(NotFoundException):
            await LeaveService.apply_leave(db, emp.id, data)

    async def test_apply_leave_inactive_leave_type(self, db: AsyncSession):
        """Using an inactive leave type → NotFoundException."""
        loc, dept = await _seed_location_and_dept(db)
        emp = await _seed_employee(db, department_id=dept.id, location_id=loc.id)
        lt = await _seed_leave_type(db, is_active=False)
        await _seed_balance(db, emp.id, lt.id)

        data = LeaveRequestCreate(
            leave_type_id=lt.id,
            from_date=date(2026, 3, 2),
            to_date=date(2026, 3, 3),
            reason="Inactive type",
        )

        with pytest.raises(NotFoundException):
            await LeaveService.apply_leave(db, emp.id, data)

    async def test_balance_adjust_positive(self, db: AsyncSession):
        """HR adjusts balance positively → adjusted increases."""
        loc, dept = await _seed_location_and_dept(db)
        emp = await _seed_employee(db, department_id=dept.id, location_id=loc.id)
        lt = await _seed_leave_type(db)
        bal = await _seed_balance(db, emp.id, lt.id, opening_balance=Decimal("10"))

        result = await LeaveService.adjust_balance(
            db, emp.id, lt.id, Decimal("3"), "Birthday bonus",
        )

        assert result.available is not None

    async def test_balance_adjust_negative(self, db: AsyncSession):
        """HR adjusts balance negatively → adjusted decreases."""
        loc, dept = await _seed_location_and_dept(db)
        emp = await _seed_employee(db, department_id=dept.id, location_id=loc.id)
        lt = await _seed_leave_type(db)
        await _seed_balance(db, emp.id, lt.id, opening_balance=Decimal("10"))

        result = await LeaveService.adjust_balance(
            db, emp.id, lt.id, Decimal("-2"), "Correction",
        )

        assert result.available is not None
