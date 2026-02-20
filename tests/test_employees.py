"""Employee module test suite — CRUD, search, pagination, department filter,
validation errors, deactivation, and profile updates.

Tests exercise the service layer and the HTTP API (via router).
Uses the shared conftest.py pattern with in-memory SQLite.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth.models import UserSession
from backend.common.constants import GenderType, UserRole
from backend.common.exceptions import (
    ConflictError,
    NotFoundException,
    ValidationException,
)
from backend.config import settings
from backend.core_hr.models import Department, Employee, Location
from backend.core_hr.service import EmployeeService
from tests.conftest import (
    TestSessionFactory,
    _make_department,
    _make_employee,
    _make_location,
    create_access_token,
)


# ── Helpers ─────────────────────────────────────────────────────────


async def _seed_location(db: AsyncSession, **kwargs) -> Location:
    data = _make_location(**kwargs)
    loc = Location(**data)
    db.add(loc)
    await db.flush()
    return loc


async def _seed_department(
    db: AsyncSession, location_id: uuid.UUID, **kwargs
) -> Department:
    data = _make_department(location_id=location_id, **kwargs)
    dept = Department(**data)
    db.add(dept)
    await db.flush()
    return dept


async def _seed_employee(
    db: AsyncSession,
    department_id: uuid.UUID,
    location_id: uuid.UUID,
    **kwargs,
) -> Employee:
    data = _make_employee(department_id=department_id, location_id=location_id, **kwargs)
    emp = Employee(**data)
    db.add(emp)
    await db.flush()
    return emp


async def _make_auth_headers(db: AsyncSession, employee_id: uuid.UUID, role=UserRole.employee):
    """Create a token + DB session and return auth headers."""
    token = create_access_token(employee_id, role=role)
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
    return {"Authorization": f"Bearer {token}"}


# ═════════════════════════════════════════════════════════════════════
# 1. EMPLOYEE CREATION — Service Layer
# ═════════════════════════════════════════════════════════════════════


class TestEmployeeCreate:
    """Tests for employee creation via service layer."""

    async def test_create_employee_basic(self, db: AsyncSession):
        """Create an employee with minimal valid data."""
        loc = await _seed_location(db)
        dept = await _seed_department(db, loc.id)
        emp = await _seed_employee(db, dept.id, loc.id)

        assert emp.id is not None
        assert emp.is_active is True
        assert emp.department_id == dept.id
        assert emp.location_id == loc.id

    async def test_create_employee_with_all_fields(self, db: AsyncSession):
        """Create an employee with all optional fields filled."""
        loc = await _seed_location(db)
        dept = await _seed_department(db, loc.id)

        emp = Employee(
            id=uuid.uuid4(),
            employee_code="CF-FULL01",
            first_name="Full",
            last_name="Fields",
            email="full.fields@creativefuel.io",
            date_of_joining=date(2024, 6, 1),
            employment_status="active",
            nationality="Indian",
            notice_period_days=90,
            department_id=dept.id,
            location_id=loc.id,
            gender=GenderType.female,
            designation="Senior Engineer",
            date_of_birth=date(1995, 3, 15),
            personal_email="personal@gmail.com",
            phone="+919876543210",
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(emp)
        await db.flush()

        result = await db.execute(select(Employee).where(Employee.id == emp.id))
        saved = result.scalars().first()
        assert saved is not None
        assert saved.gender == GenderType.female
        assert saved.designation == "Senior Engineer"
        assert saved.phone == "+919876543210"

    async def test_create_multiple_employees_unique_codes(self, db: AsyncSession):
        """Multiple employees get unique employee codes."""
        loc = await _seed_location(db)
        dept = await _seed_department(db, loc.id)

        emp1 = await _seed_employee(db, dept.id, loc.id, email="e1@creativefuel.io", first_name="One")
        emp2 = await _seed_employee(db, dept.id, loc.id, email="e2@creativefuel.io", first_name="Two")
        emp3 = await _seed_employee(db, dept.id, loc.id, email="e3@creativefuel.io", first_name="Three")

        codes = {emp1.employee_code, emp2.employee_code, emp3.employee_code}
        assert len(codes) == 3  # All unique

    async def test_create_employee_with_reporting_manager(self, db: AsyncSession):
        """Employee created with a reporting manager reference."""
        loc = await _seed_location(db)
        dept = await _seed_department(db, loc.id)

        mgr = await _seed_employee(
            db, dept.id, loc.id,
            email="mgr@creativefuel.io",
            first_name="Manager",
        )

        data = _make_employee(
            department_id=dept.id,
            location_id=loc.id,
            email="report@creativefuel.io",
            first_name="Report",
        )
        report = Employee(**data)
        report.reporting_manager_id = mgr.id
        db.add(report)
        await db.flush()

        assert report.reporting_manager_id == mgr.id


# ═════════════════════════════════════════════════════════════════════
# 2. EMPLOYEE RETRIEVAL
# ═════════════════════════════════════════════════════════════════════


class TestEmployeeRetrieval:
    """Tests for getting employees by ID, listing, and search."""

    async def test_get_employee_by_id(self, db: AsyncSession):
        """Retrieve an employee by their UUID."""
        loc = await _seed_location(db)
        dept = await _seed_department(db, loc.id)
        emp = await _seed_employee(db, dept.id, loc.id)

        result = await db.execute(select(Employee).where(Employee.id == emp.id))
        found = result.scalars().first()
        assert found is not None
        assert found.id == emp.id
        assert found.email == "test.user@creativefuel.io"

    async def test_get_nonexistent_employee(self, db: AsyncSession):
        """Querying a non-existent employee ID returns None."""
        result = await db.execute(
            select(Employee).where(Employee.id == uuid.uuid4())
        )
        assert result.scalars().first() is None

    async def test_list_all_employees(self, db: AsyncSession):
        """List all employees returns complete set."""
        loc = await _seed_location(db)
        dept = await _seed_department(db, loc.id)

        for i in range(5):
            await _seed_employee(
                db, dept.id, loc.id,
                email=f"emp{i}@creativefuel.io",
                first_name=f"Emp{i}",
            )

        result = await db.execute(select(Employee))
        employees = result.scalars().all()
        assert len(employees) == 5

    async def test_filter_employees_by_department(self, db: AsyncSession):
        """Filter employees by department_id returns only matching."""
        loc = await _seed_location(db)
        dept_eng = await _seed_department(db, loc.id, name="Engineering", code="ENG")
        dept_hr = await _seed_department(db, loc.id, name="HR", code="HR")

        await _seed_employee(db, dept_eng.id, loc.id, email="eng1@creativefuel.io", first_name="Eng1")
        await _seed_employee(db, dept_eng.id, loc.id, email="eng2@creativefuel.io", first_name="Eng2")
        await _seed_employee(db, dept_hr.id, loc.id, email="hr1@creativefuel.io", first_name="Hr1")

        result = await db.execute(
            select(Employee).where(Employee.department_id == dept_eng.id)
        )
        eng_employees = result.scalars().all()
        assert len(eng_employees) == 2
        assert all(e.department_id == dept_eng.id for e in eng_employees)

    async def test_filter_employees_by_active_status(self, db: AsyncSession):
        """Filter by is_active returns only active or inactive employees."""
        loc = await _seed_location(db)
        dept = await _seed_department(db, loc.id)

        active = await _seed_employee(db, dept.id, loc.id, email="active@creativefuel.io", first_name="Active")
        inactive = await _seed_employee(db, dept.id, loc.id, email="inactive@creativefuel.io", first_name="Inactive")
        inactive.is_active = False
        await db.flush()

        result = await db.execute(
            select(Employee).where(Employee.is_active.is_(True))
        )
        active_list = result.scalars().all()
        assert len(active_list) == 1
        assert active_list[0].first_name == "Active"

    async def test_search_employee_by_name(self, db: AsyncSession):
        """Search by first_name with LIKE query."""
        loc = await _seed_location(db)
        dept = await _seed_department(db, loc.id)

        await _seed_employee(db, dept.id, loc.id, email="alice@creativefuel.io", first_name="Alice")
        await _seed_employee(db, dept.id, loc.id, email="bob@creativefuel.io", first_name="Bob")
        await _seed_employee(db, dept.id, loc.id, email="alison@creativefuel.io", first_name="Alison")

        result = await db.execute(
            select(Employee).where(Employee.first_name.ilike("ali%"))
        )
        matches = result.scalars().all()
        assert len(matches) == 2
        assert all(m.first_name.startswith("Ali") for m in matches)

    async def test_search_employee_by_email(self, db: AsyncSession):
        """Search employees by email domain."""
        loc = await _seed_location(db)
        dept = await _seed_department(db, loc.id)

        await _seed_employee(db, dept.id, loc.id, email="findme@creativefuel.io", first_name="FindMe")
        await _seed_employee(db, dept.id, loc.id, email="other@creativefuel.io", first_name="Other")

        result = await db.execute(
            select(Employee).where(Employee.email.ilike("%findme%"))
        )
        matches = result.scalars().all()
        assert len(matches) == 1
        assert matches[0].first_name == "FindMe"

    async def test_search_employee_by_employee_code(self, db: AsyncSession):
        """Search by employee code prefix."""
        loc = await _seed_location(db)
        dept = await _seed_department(db, loc.id)

        emp = await _seed_employee(db, dept.id, loc.id)
        code = emp.employee_code

        result = await db.execute(
            select(Employee).where(Employee.employee_code == code)
        )
        found = result.scalars().first()
        assert found is not None
        assert found.id == emp.id


# ═════════════════════════════════════════════════════════════════════
# 3. PAGINATION
# ═════════════════════════════════════════════════════════════════════


class TestEmployeePagination:
    """Tests for employee list pagination."""

    async def test_pagination_page_size(self, db: AsyncSession):
        """Paginating with limit returns correct number of results."""
        loc = await _seed_location(db)
        dept = await _seed_department(db, loc.id)

        for i in range(15):
            await _seed_employee(
                db, dept.id, loc.id,
                email=f"page{i}@creativefuel.io",
                first_name=f"Page{i}",
            )

        result = await db.execute(
            select(Employee).limit(5)
        )
        page1 = result.scalars().all()
        assert len(page1) == 5

    async def test_pagination_offset(self, db: AsyncSession):
        """Offset pagination returns different sets."""
        loc = await _seed_location(db)
        dept = await _seed_department(db, loc.id)

        for i in range(10):
            await _seed_employee(
                db, dept.id, loc.id,
                email=f"off{i}@creativefuel.io",
                first_name=f"Off{i}",
            )

        result1 = await db.execute(
            select(Employee).order_by(Employee.email).limit(5).offset(0)
        )
        page1 = result1.scalars().all()

        result2 = await db.execute(
            select(Employee).order_by(Employee.email).limit(5).offset(5)
        )
        page2 = result2.scalars().all()

        page1_ids = {e.id for e in page1}
        page2_ids = {e.id for e in page2}
        assert page1_ids.isdisjoint(page2_ids)
        assert len(page1) == 5
        assert len(page2) == 5

    async def test_pagination_beyond_total(self, db: AsyncSession):
        """Requesting page beyond total returns empty."""
        loc = await _seed_location(db)
        dept = await _seed_department(db, loc.id)

        await _seed_employee(db, dept.id, loc.id)

        result = await db.execute(
            select(Employee).limit(10).offset(100)
        )
        assert len(result.scalars().all()) == 0


# ═════════════════════════════════════════════════════════════════════
# 4. EMPLOYEE UPDATE
# ═════════════════════════════════════════════════════════════════════


class TestEmployeeUpdate:
    """Tests for updating employee profiles."""

    async def test_update_designation(self, db: AsyncSession):
        """Update employee's designation."""
        loc = await _seed_location(db)
        dept = await _seed_department(db, loc.id)
        emp = await _seed_employee(db, dept.id, loc.id)

        emp.designation = "Lead Engineer"
        await db.flush()

        await db.refresh(emp)
        assert emp.designation == "Lead Engineer"

    async def test_update_department(self, db: AsyncSession):
        """Move employee to a different department."""
        loc = await _seed_location(db)
        dept1 = await _seed_department(db, loc.id, name="Engineering", code="ENG")
        dept2 = await _seed_department(db, loc.id, name="Product", code="PRD")

        emp = await _seed_employee(db, dept1.id, loc.id)
        assert emp.department_id == dept1.id

        emp.department_id = dept2.id
        await db.flush()

        await db.refresh(emp)
        assert emp.department_id == dept2.id

    async def test_update_reporting_manager(self, db: AsyncSession):
        """Change an employee's reporting manager."""
        loc = await _seed_location(db)
        dept = await _seed_department(db, loc.id)

        mgr1 = await _seed_employee(db, dept.id, loc.id, email="mgr1@creativefuel.io", first_name="MgrOne")
        mgr2 = await _seed_employee(db, dept.id, loc.id, email="mgr2@creativefuel.io", first_name="MgrTwo")

        emp_data = _make_employee(department_id=dept.id, location_id=loc.id, email="worker@creativefuel.io")
        emp = Employee(**emp_data)
        emp.reporting_manager_id = mgr1.id
        db.add(emp)
        await db.flush()

        emp.reporting_manager_id = mgr2.id
        await db.flush()

        await db.refresh(emp)
        assert emp.reporting_manager_id == mgr2.id

    async def test_deactivate_employee(self, db: AsyncSession):
        """Deactivate an employee sets is_active to False."""
        loc = await _seed_location(db)
        dept = await _seed_department(db, loc.id)
        emp = await _seed_employee(db, dept.id, loc.id)

        emp.is_active = False
        await db.flush()

        await db.refresh(emp)
        assert emp.is_active is False

    async def test_update_personal_details(self, db: AsyncSession):
        """Update phone and personal email."""
        loc = await _seed_location(db)
        dept = await _seed_department(db, loc.id)
        emp = await _seed_employee(db, dept.id, loc.id)

        emp.phone = "+919999999999"
        emp.personal_email = "personal@gmail.com"
        await db.flush()

        await db.refresh(emp)
        assert emp.phone == "+919999999999"
        assert emp.personal_email == "personal@gmail.com"


# ═════════════════════════════════════════════════════════════════════
# 5. VALIDATION ERRORS
# ═════════════════════════════════════════════════════════════════════


class TestEmployeeValidation:
    """Tests for data integrity and validation edge cases."""

    async def test_employee_display_name_generation(self, db: AsyncSession):
        """ensure_display_name() generates first + last name."""
        loc = await _seed_location(db)
        dept = await _seed_department(db, loc.id)
        emp = await _seed_employee(
            db, dept.id, loc.id,
            first_name="Rahul",
            last_name="Sharma",
        )

        emp.ensure_display_name()
        assert emp.display_name is not None
        assert "Rahul" in emp.display_name

    async def test_employee_full_name_property(self, db: AsyncSession):
        """full_name property returns first + last."""
        loc = await _seed_location(db)
        dept = await _seed_department(db, loc.id)
        emp = await _seed_employee(
            db, dept.id, loc.id,
            first_name="Priya",
            last_name="Patel",
        )

        assert emp.full_name == "Priya Patel"

    async def test_employee_without_department(self, db: AsyncSession):
        """Employee can exist without a department (nullable FK)."""
        loc = await _seed_location(db)

        emp_data = _make_employee(department_id=None, location_id=loc.id)
        emp = Employee(**emp_data)
        db.add(emp)
        await db.flush()

        await db.refresh(emp)
        assert emp.department_id is None

    async def test_employee_without_location(self, db: AsyncSession):
        """Employee can exist without a location (nullable FK)."""
        emp_data = _make_employee(department_id=None, location_id=None)
        emp = Employee(**emp_data)
        db.add(emp)
        await db.flush()

        await db.refresh(emp)
        assert emp.location_id is None

    async def test_employee_gender_enum_values(self, db: AsyncSession):
        """All gender enum values can be assigned."""
        loc = await _seed_location(db)
        dept = await _seed_department(db, loc.id)

        for i, gender in enumerate(GenderType):
            emp_data = _make_employee(
                department_id=dept.id,
                location_id=loc.id,
                email=f"gender{i}@creativefuel.io",
                first_name=f"Gender{i}",
            )
            emp = Employee(**emp_data)
            emp.gender = gender
            db.add(emp)
        await db.flush()

        result = await db.execute(select(Employee))
        all_emps = result.scalars().all()
        genders = {e.gender for e in all_emps if e.gender is not None}
        assert len(genders) == len(GenderType)


# ═════════════════════════════════════════════════════════════════════
# 6. API ENDPOINT TESTS
# ═════════════════════════════════════════════════════════════════════


# ═════════════════════════════════════════════════════════════════════
# 7. SERVICE LAYER TESTS
# ═════════════════════════════════════════════════════════════════════


class TestEmployeeServiceLayer:
    """Tests that exercise EmployeeService methods directly for coverage."""

    async def test_service_get_employee(self, db: AsyncSession):
        """EmployeeService.get_employee returns EmployeeDetail."""
        loc = await _seed_location(db)
        dept = await _seed_department(db, loc.id)
        emp = await _seed_employee(db, dept.id, loc.id)

        detail = await EmployeeService.get_employee(db, emp.id)
        assert detail.email == "test.user@creativefuel.io"
        assert detail.direct_reports_count == 0

    async def test_service_get_employee_not_found(self, db: AsyncSession):
        """EmployeeService.get_employee raises NotFoundException."""
        from backend.common.exceptions import NotFoundException
        with pytest.raises(NotFoundException):
            await EmployeeService.get_employee(db, uuid.uuid4())

    async def test_service_get_employee_with_reports(self, db: AsyncSession):
        """EmployeeService.get_employee counts direct reports."""
        loc = await _seed_location(db)
        dept = await _seed_department(db, loc.id)
        mgr = await _seed_employee(
            db, dept.id, loc.id,
            email="mgr@creativefuel.io",
            first_name="Manager",
        )

        for i in range(3):
            emp_data = _make_employee(
                department_id=dept.id,
                location_id=loc.id,
                email=f"report{i}@creativefuel.io",
                first_name=f"Report{i}",
            )
            emp_obj = Employee(**emp_data)
            emp_obj.reporting_manager_id = mgr.id
            db.add(emp_obj)
        await db.flush()

        detail = await EmployeeService.get_employee(db, mgr.id)
        assert detail.direct_reports_count == 3

    async def test_service_get_direct_reports(self, db: AsyncSession):
        """EmployeeService.get_direct_reports returns list of employees."""
        loc = await _seed_location(db)
        dept = await _seed_department(db, loc.id)
        mgr = await _seed_employee(
            db, dept.id, loc.id,
            email="mgr2@creativefuel.io",
            first_name="Mgr2",
        )

        for i in range(2):
            emp_data = _make_employee(
                department_id=dept.id,
                location_id=loc.id,
                email=f"dr{i}@creativefuel.io",
                first_name=f"DR{i}",
            )
            emp_obj = Employee(**emp_data)
            emp_obj.reporting_manager_id = mgr.id
            db.add(emp_obj)
        await db.flush()

        reports = await EmployeeService.get_direct_reports(db, mgr.id)
        assert len(reports) == 2

    async def test_service_list_employees_paginated(self, db: AsyncSession):
        """EmployeeService.list_employees returns PaginatedResponse with correct page_size."""
        from backend.common.pagination import PaginationParams

        loc = await _seed_location(db)
        dept = await _seed_department(db, loc.id)

        for i in range(8):
            await _seed_employee(
                db, dept.id, loc.id,
                email=f"list{i}@creativefuel.io",
                first_name=f"List{i}",
            )

        params = PaginationParams(page=1, page_size=5, sort=None)
        result = await EmployeeService.list_employees(db, params)
        assert result.meta.page_size == 5
        assert len(result.data) == 5  # page_size limit applied

    async def test_service_list_employees_filter_department(self, db: AsyncSession):
        """EmployeeService.list_employees filters by department_id."""
        from backend.common.pagination import PaginationParams

        loc = await _seed_location(db)
        dept1 = await _seed_department(db, loc.id, name="Dept1", code="D1")
        dept2 = await _seed_department(db, loc.id, name="Dept2", code="D2")

        for i in range(3):
            await _seed_employee(
                db, dept1.id, loc.id,
                email=f"d1e{i}@creativefuel.io",
                first_name=f"D1E{i}",
            )
        await _seed_employee(
            db, dept2.id, loc.id,
            email="d2e@creativefuel.io",
            first_name="D2E",
        )

        params = PaginationParams(page=1, page_size=50, sort=None)
        result = await EmployeeService.list_employees(
            db, params, department_id=dept1.id,
        )
        assert result.meta.total == 3

    async def test_service_list_employees_filter_active(self, db: AsyncSession):
        """EmployeeService.list_employees filters by is_active."""
        from backend.common.pagination import PaginationParams

        loc = await _seed_location(db)
        dept = await _seed_department(db, loc.id)

        active_emp = await _seed_employee(
            db, dept.id, loc.id,
            email="act@creativefuel.io",
            first_name="Active",
        )
        inactive_emp = await _seed_employee(
            db, dept.id, loc.id,
            email="inact@creativefuel.io",
            first_name="Inactive",
        )
        inactive_emp.is_active = False
        await db.flush()

        params = PaginationParams(page=1, page_size=50, sort=None)
        result = await EmployeeService.list_employees(
            db, params, is_active=True,
        )
        assert result.meta.total == 1

    async def test_service_create_employee(self, db: AsyncSession):
        """EmployeeService.create_employee creates and returns Employee."""
        from backend.core_hr.schemas import EmployeeCreate

        loc = await _seed_location(db)
        dept = await _seed_department(db, loc.id)

        data = EmployeeCreate(
            employee_code="CF-SVC001",
            first_name="Service",
            last_name="Test",
            email="svctest@creativefuel.io",
            date_of_joining=date(2025, 1, 1),
            employment_status="active",
            nationality="Indian",
            notice_period_days=90,
            department_id=dept.id,
            location_id=loc.id,
        )

        emp = await EmployeeService.create_employee(db, data, actor_id=None)
        assert emp.id is not None
        assert emp.email == "svctest@creativefuel.io"

    async def test_service_create_employee_duplicate_email(self, db: AsyncSession):
        """EmployeeService.create_employee raises ConflictError on duplicate email."""
        from backend.core_hr.schemas import EmployeeCreate
        from backend.common.exceptions import ConflictError

        loc = await _seed_location(db)
        dept = await _seed_department(db, loc.id)

        data = EmployeeCreate(
            employee_code="CF-DUP001",
            first_name="Dup",
            last_name="One",
            email="dup@creativefuel.io",
            date_of_joining=date(2025, 1, 1),
            employment_status="active",
            nationality="Indian",
            notice_period_days=90,
            department_id=dept.id,
            location_id=loc.id,
        )

        await EmployeeService.create_employee(db, data, actor_id=None)

        data2 = EmployeeCreate(
            employee_code="CF-DUP002",
            first_name="Dup",
            last_name="Two",
            email="dup@creativefuel.io",
            date_of_joining=date(2025, 1, 1),
            employment_status="active",
            nationality="Indian",
            notice_period_days=90,
            department_id=dept.id,
            location_id=loc.id,
        )

        with pytest.raises(ConflictError):
            await EmployeeService.create_employee(db, data2, actor_id=None)

    async def test_service_update_employee(self, db: AsyncSession):
        """EmployeeService.update_employee partially updates fields."""
        from backend.core_hr.schemas import EmployeeUpdate

        loc = await _seed_location(db)
        dept = await _seed_department(db, loc.id)
        emp = await _seed_employee(db, dept.id, loc.id)

        update_data = EmployeeUpdate(designation="CTO")
        updated = await EmployeeService.update_employee(
            db, emp.id, update_data, actor_id=None,
        )
        assert updated.designation == "CTO"

    async def test_service_update_employee_not_found(self, db: AsyncSession):
        """EmployeeService.update_employee raises NotFoundException."""
        from backend.core_hr.schemas import EmployeeUpdate
        from backend.common.exceptions import NotFoundException

        with pytest.raises(NotFoundException):
            await EmployeeService.update_employee(
                db, uuid.uuid4(), EmployeeUpdate(designation="Ghost"), actor_id=None,
            )

    async def test_service_update_employee_name_recomputes_display(self, db: AsyncSession):
        """Updating first_name triggers display_name recomputation."""
        from backend.core_hr.schemas import EmployeeUpdate

        loc = await _seed_location(db)
        dept = await _seed_department(db, loc.id)
        emp = await _seed_employee(db, dept.id, loc.id, first_name="OldName")

        update_data = EmployeeUpdate(first_name="NewName")
        updated = await EmployeeService.update_employee(
            db, emp.id, update_data, actor_id=None,
        )
        assert "NewName" in (updated.display_name or updated.first_name)


class TestDepartmentServiceLayer:
    """Tests for DepartmentService methods."""

    async def test_service_list_departments(self, db: AsyncSession):
        """DepartmentService.list_departments returns list with counts."""
        from backend.core_hr.service import DepartmentService

        loc = await _seed_location(db)
        dept = await _seed_department(db, loc.id, name="TestDept", code="TD")

        # Add an employee
        await _seed_employee(db, dept.id, loc.id)

        result = await DepartmentService.list_departments(db)
        assert len(result) == 1
        assert result[0].employee_count == 1

    async def test_service_get_department(self, db: AsyncSession):
        """DepartmentService.get_department returns department with count."""
        from backend.core_hr.service import DepartmentService

        loc = await _seed_location(db)
        dept = await _seed_department(db, loc.id)

        result = await DepartmentService.get_department(db, dept.id)
        assert result.name == "Engineering"

    async def test_service_get_department_not_found(self, db: AsyncSession):
        """DepartmentService.get_department raises NotFoundException."""
        from backend.core_hr.service import DepartmentService
        from backend.common.exceptions import NotFoundException

        with pytest.raises(NotFoundException):
            await DepartmentService.get_department(db, uuid.uuid4())

    async def test_service_list_departments_active_filter(self, db: AsyncSession):
        """DepartmentService.list_departments with is_active=None returns all."""
        from backend.core_hr.service import DepartmentService

        loc = await _seed_location(db)
        active_dept = await _seed_department(db, loc.id, name="Active", code="ACT")
        inactive_dept = await _seed_department(db, loc.id, name="Inactive", code="INA")
        inactive_dept.is_active = False
        await db.flush()

        result = await DepartmentService.list_departments(db, is_active=None)
        assert len(result) == 2


class TestLocationServiceLayer:
    """Tests for LocationService methods."""

    async def test_service_list_locations(self, db: AsyncSession):
        """LocationService.list_locations returns all active locations."""
        from backend.core_hr.service import LocationService

        loc = await _seed_location(db)

        result = await LocationService.list_locations(db)
        assert len(result) >= 1
        assert result[0].name == "Mumbai HQ"

    async def test_service_get_location(self, db: AsyncSession):
        """LocationService.get_location returns single location."""
        from backend.core_hr.service import LocationService

        loc = await _seed_location(db)

        result = await LocationService.get_location(db, loc.id)
        assert result.name == "Mumbai HQ"

    async def test_service_get_location_not_found(self, db: AsyncSession):
        """LocationService.get_location raises NotFoundException."""
        from backend.core_hr.service import LocationService
        from backend.common.exceptions import NotFoundException

        with pytest.raises(NotFoundException):
            await LocationService.get_location(db, uuid.uuid4())


class TestEmployeeAPI:
    """HTTP API tests for employee endpoints."""

    async def test_list_employees_endpoint(self, client, auth_headers, test_employee):
        """GET /api/v1/employees returns employee list."""
        resp = await client.get("/api/v1/employees", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data or isinstance(data, list)

    async def test_get_employee_by_id_endpoint(self, client, auth_headers, test_employee):
        """GET /api/v1/employees/{id} returns specific employee."""
        emp_id = str(test_employee["id"])
        resp = await client.get(f"/api/v1/employees/{emp_id}", headers=auth_headers)
        assert resp.status_code == 200

    async def test_get_employee_unauthorized(self, client, test_employee):
        """GET /api/v1/employees/{id} without auth returns 401/403."""
        emp_id = str(test_employee["id"])
        resp = await client.get(f"/api/v1/employees/{emp_id}")
        assert resp.status_code in (401, 403)
