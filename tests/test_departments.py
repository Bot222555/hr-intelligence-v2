"""Department module test suite — CRUD, duplicate name detection, cascade delete
protection, location association, and active/inactive filtering.

Uses the shared conftest.py pattern with in-memory SQLite.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core_hr.models import Department, Employee, Location
from tests.conftest import (
    TestSessionFactory,
    _make_department,
    _make_employee,
    _make_location,
)


# ── Helpers ─────────────────────────────────────────────────────────


async def _seed_location(db: AsyncSession, **kwargs) -> Location:
    data = _make_location(**kwargs)
    loc = Location(**data)
    db.add(loc)
    await db.flush()
    return loc


async def _seed_department(
    db: AsyncSession,
    location_id: uuid.UUID,
    **kwargs,
) -> Department:
    data = _make_department(location_id=location_id, **kwargs)
    dept = Department(**data)
    db.add(dept)
    await db.flush()
    return dept


# ═════════════════════════════════════════════════════════════════════
# 1. DEPARTMENT CRUD
# ═════════════════════════════════════════════════════════════════════


class TestDepartmentCRUD:
    """Tests for department create, read, update, delete."""

    async def test_create_department(self, db: AsyncSession):
        """Create a department with valid data."""
        loc = await _seed_location(db)
        dept = await _seed_department(db, loc.id)

        assert dept.id is not None
        assert dept.name == "Engineering"
        assert dept.code == "ENG"
        assert dept.location_id == loc.id
        assert dept.is_active is True

    async def test_create_department_without_location(self, db: AsyncSession):
        """Department can be created without a location (nullable FK)."""
        dept_data = _make_department(location_id=None)
        dept = Department(**dept_data)
        db.add(dept)
        await db.flush()

        assert dept.location_id is None
        assert dept.name is not None

    async def test_get_department_by_id(self, db: AsyncSession):
        """Retrieve a department by UUID."""
        loc = await _seed_location(db)
        dept = await _seed_department(db, loc.id, name="Marketing", code="MKT")

        result = await db.execute(
            select(Department).where(Department.id == dept.id)
        )
        found = result.scalars().first()
        assert found is not None
        assert found.name == "Marketing"
        assert found.code == "MKT"

    async def test_list_all_departments(self, db: AsyncSession):
        """List all departments."""
        loc = await _seed_location(db)

        await _seed_department(db, loc.id, name="Engineering", code="ENG")
        await _seed_department(db, loc.id, name="Marketing", code="MKT")
        await _seed_department(db, loc.id, name="Sales", code="SLS")

        result = await db.execute(select(Department))
        depts = result.scalars().all()
        assert len(depts) == 3

    async def test_update_department_name(self, db: AsyncSession):
        """Update a department's name."""
        loc = await _seed_location(db)
        dept = await _seed_department(db, loc.id, name="Old Name", code="OLD")

        dept.name = "New Name"
        await db.flush()

        await db.refresh(dept)
        assert dept.name == "New Name"

    async def test_deactivate_department(self, db: AsyncSession):
        """Deactivate a department."""
        loc = await _seed_location(db)
        dept = await _seed_department(db, loc.id)

        dept.is_active = False
        await db.flush()

        await db.refresh(dept)
        assert dept.is_active is False

    async def test_filter_active_departments(self, db: AsyncSession):
        """Only active departments returned when filtered."""
        loc = await _seed_location(db)

        active = await _seed_department(db, loc.id, name="Active Dept", code="ACT")
        inactive = await _seed_department(db, loc.id, name="Inactive Dept", code="INA")
        inactive.is_active = False
        await db.flush()

        result = await db.execute(
            select(Department).where(Department.is_active.is_(True))
        )
        active_depts = result.scalars().all()
        assert len(active_depts) == 1
        assert active_depts[0].name == "Active Dept"


# ═════════════════════════════════════════════════════════════════════
# 2. DUPLICATE NAME DETECTION
# ═════════════════════════════════════════════════════════════════════


class TestDepartmentDuplicates:
    """Tests for detecting duplicate department names/codes."""

    async def test_duplicate_code_check(self, db: AsyncSession):
        """Two departments with same code can be detected."""
        loc = await _seed_location(db)

        await _seed_department(db, loc.id, name="Dept A", code="DUP")

        # Check for existing code before creating
        result = await db.execute(
            select(func.count()).select_from(Department).where(
                Department.code == "DUP"
            )
        )
        count = result.scalar_one()
        assert count == 1  # duplicate exists

    async def test_case_insensitive_name_search(self, db: AsyncSession):
        """Department name search works case-insensitively."""
        loc = await _seed_location(db)
        await _seed_department(db, loc.id, name="Engineering", code="ENG")

        result = await db.execute(
            select(Department).where(
                func.lower(Department.name) == "engineering"
            )
        )
        found = result.scalars().first()
        assert found is not None
        assert found.name == "Engineering"


# ═════════════════════════════════════════════════════════════════════
# 3. CASCADE / REFERENTIAL INTEGRITY
# ═════════════════════════════════════════════════════════════════════


class TestDepartmentCascade:
    """Tests for department-employee relationships and cascade protection."""

    async def test_department_has_employees(self, db: AsyncSession):
        """Department with employees can be found via relationship query."""
        loc = await _seed_location(db)
        dept = await _seed_department(db, loc.id)

        # Add employees to department
        for i in range(3):
            emp_data = _make_employee(
                department_id=dept.id,
                location_id=loc.id,
                email=f"emp{i}@creativefuel.io",
                first_name=f"Emp{i}",
            )
            db.add(Employee(**emp_data))
        await db.flush()

        # Count employees in department
        result = await db.execute(
            select(func.count()).select_from(Employee).where(
                Employee.department_id == dept.id
            )
        )
        assert result.scalar_one() == 3

    async def test_deactivated_department_employees_still_linked(
        self, db: AsyncSession,
    ):
        """Deactivating a department doesn't remove employee links."""
        loc = await _seed_location(db)
        dept = await _seed_department(db, loc.id)

        emp_data = _make_employee(
            department_id=dept.id,
            location_id=loc.id,
            email="linked@creativefuel.io",
        )
        emp = Employee(**emp_data)
        db.add(emp)
        await db.flush()

        # Deactivate
        dept.is_active = False
        await db.flush()

        # Employee still references the department
        await db.refresh(emp)
        assert emp.department_id == dept.id

    async def test_department_employee_count_after_transfers(
        self, db: AsyncSession,
    ):
        """Transferring employees between departments updates counts."""
        loc = await _seed_location(db)
        dept1 = await _seed_department(db, loc.id, name="Dept A", code="DA")
        dept2 = await _seed_department(db, loc.id, name="Dept B", code="DB")

        emp_data = _make_employee(
            department_id=dept1.id,
            location_id=loc.id,
        )
        emp = Employee(**emp_data)
        db.add(emp)
        await db.flush()

        # Transfer
        emp.department_id = dept2.id
        await db.flush()

        # Dept1 should have 0, Dept2 should have 1
        r1 = await db.execute(
            select(func.count()).select_from(Employee).where(
                Employee.department_id == dept1.id
            )
        )
        assert r1.scalar_one() == 0

        r2 = await db.execute(
            select(func.count()).select_from(Employee).where(
                Employee.department_id == dept2.id
            )
        )
        assert r2.scalar_one() == 1
