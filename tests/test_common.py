"""Tests for common utilities — filters, pagination, and models.

Exercises the apply_filters, apply_sorting, apply_search, and pagination
functions to boost coverage on backend/common/*.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.common.filters import apply_filters, apply_sorting, _get_column
from backend.common.pagination import PaginationParams, paginate
from backend.core_hr.models import Department, Employee, Location
from tests.conftest import (
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


async def _seed_department(db: AsyncSession, location_id, **kwargs) -> Department:
    data = _make_department(location_id=location_id, **kwargs)
    dept = Department(**data)
    db.add(dept)
    await db.flush()
    return dept


async def _seed_employee(db: AsyncSession, dept_id, loc_id, **kwargs) -> Employee:
    data = _make_employee(department_id=dept_id, location_id=loc_id, **kwargs)
    emp = Employee(**data)
    db.add(emp)
    await db.flush()
    return emp


# ═════════════════════════════════════════════════════════════════════
# FILTER TESTS
# ═════════════════════════════════════════════════════════════════════


class TestApplyFilters:
    """Tests for apply_filters utility."""

    async def test_filter_by_equality(self, db: AsyncSession):
        """apply_filters with simple equality filter."""
        loc = await _seed_location(db)
        dept = await _seed_department(db, loc.id)
        await _seed_employee(db, dept.id, loc.id, first_name="Alice", email="alice@creativefuel.io")
        await _seed_employee(db, dept.id, loc.id, first_name="Bob", email="bob@creativefuel.io")

        query = select(Employee)
        query = apply_filters(query, Employee, {"first_name": "Alice"})
        result = await db.execute(query)
        employees = result.scalars().all()
        assert len(employees) == 1
        assert employees[0].first_name == "Alice"

    async def test_filter_none_values_skipped(self, db: AsyncSession):
        """None values in filter dict are ignored."""
        loc = await _seed_location(db)
        dept = await _seed_department(db, loc.id)
        await _seed_employee(db, dept.id, loc.id, email="x@creativefuel.io")

        query = select(Employee)
        query = apply_filters(query, Employee, {"first_name": None, "is_active": True})
        result = await db.execute(query)
        employees = result.scalars().all()
        assert len(employees) == 1

    async def test_filter_by_ilike(self, db: AsyncSession):
        """apply_filters with __ilike suffix for case-insensitive search."""
        loc = await _seed_location(db)
        dept = await _seed_department(db, loc.id)
        await _seed_employee(db, dept.id, loc.id, first_name="Alexander", email="alex@creativefuel.io")
        await _seed_employee(db, dept.id, loc.id, first_name="Bobby", email="bobby@creativefuel.io")

        query = select(Employee)
        query = apply_filters(query, Employee, {"first_name__ilike": "alex"})
        result = await db.execute(query)
        employees = result.scalars().all()
        assert len(employees) == 1
        assert employees[0].first_name == "Alexander"

    async def test_filter_by_from_to_range(self, db: AsyncSession):
        """apply_filters with __from and __to for date range."""
        loc = await _seed_location(db)
        dept = await _seed_department(db, loc.id)

        emp1_data = _make_employee(department_id=dept.id, location_id=loc.id, email="e1@creativefuel.io", first_name="E1")
        emp1 = Employee(**emp1_data)
        emp1.date_of_joining = date(2024, 1, 1)
        db.add(emp1)

        emp2_data = _make_employee(department_id=dept.id, location_id=loc.id, email="e2@creativefuel.io", first_name="E2")
        emp2 = Employee(**emp2_data)
        emp2.date_of_joining = date(2025, 6, 1)
        db.add(emp2)

        emp3_data = _make_employee(department_id=dept.id, location_id=loc.id, email="e3@creativefuel.io", first_name="E3")
        emp3 = Employee(**emp3_data)
        emp3.date_of_joining = date(2026, 1, 1)
        db.add(emp3)
        await db.flush()

        query = select(Employee)
        query = apply_filters(query, Employee, {
            "date_of_joining__from": date(2025, 1, 1),
            "date_of_joining__to": date(2025, 12, 31),
        })
        result = await db.execute(query)
        employees = result.scalars().all()
        assert len(employees) == 1
        assert employees[0].first_name == "E2"

    async def test_filter_by_in(self, db: AsyncSession):
        """apply_filters with __in suffix for IN clause."""
        loc = await _seed_location(db)
        dept = await _seed_department(db, loc.id)
        await _seed_employee(db, dept.id, loc.id, first_name="Alice", email="a@creativefuel.io")
        await _seed_employee(db, dept.id, loc.id, first_name="Bob", email="b@creativefuel.io")
        await _seed_employee(db, dept.id, loc.id, first_name="Charlie", email="c@creativefuel.io")

        query = select(Employee)
        query = apply_filters(query, Employee, {
            "first_name__in": ["Alice", "Charlie"],
        })
        result = await db.execute(query)
        employees = result.scalars().all()
        assert len(employees) == 2
        names = {e.first_name for e in employees}
        assert names == {"Alice", "Charlie"}

    async def test_filter_nonexistent_column_ignored(self, db: AsyncSession):
        """Filtering on a non-existent column is silently ignored."""
        loc = await _seed_location(db)
        dept = await _seed_department(db, loc.id)
        await _seed_employee(db, dept.id, loc.id, email="safe@creativefuel.io")

        query = select(Employee)
        query = apply_filters(query, Employee, {"nonexistent_field": "value"})
        result = await db.execute(query)
        assert len(result.scalars().all()) == 1  # No error, no filter applied


class TestApplySorting:
    """Tests for apply_sorting utility."""

    async def test_sort_ascending(self, db: AsyncSession):
        """apply_sorting with ascending sort."""
        loc = await _seed_location(db)
        dept = await _seed_department(db, loc.id)
        await _seed_employee(db, dept.id, loc.id, first_name="Charlie", email="c@creativefuel.io")
        await _seed_employee(db, dept.id, loc.id, first_name="Alice", email="a@creativefuel.io")
        await _seed_employee(db, dept.id, loc.id, first_name="Bob", email="b@creativefuel.io")

        query = select(Employee)
        query = apply_sorting(query, Employee, "first_name")
        result = await db.execute(query)
        employees = result.scalars().all()
        assert [e.first_name for e in employees] == ["Alice", "Bob", "Charlie"]

    async def test_sort_descending(self, db: AsyncSession):
        """apply_sorting with descending sort (prefix '-')."""
        loc = await _seed_location(db)
        dept = await _seed_department(db, loc.id)
        await _seed_employee(db, dept.id, loc.id, first_name="Charlie", email="c@creativefuel.io")
        await _seed_employee(db, dept.id, loc.id, first_name="Alice", email="a@creativefuel.io")
        await _seed_employee(db, dept.id, loc.id, first_name="Bob", email="b@creativefuel.io")

        query = select(Employee)
        query = apply_sorting(query, Employee, "-first_name")
        result = await db.execute(query)
        employees = result.scalars().all()
        assert [e.first_name for e in employees] == ["Charlie", "Bob", "Alice"]

    async def test_sort_none_no_op(self, db: AsyncSession):
        """apply_sorting with None sort is a no-op."""
        query = select(Employee)
        sorted_q = apply_sorting(query, Employee, None)
        # Should return the same query (no error)
        assert sorted_q is query

    async def test_sort_nonexistent_column_fallback(self, db: AsyncSession):
        """apply_sorting with non-existent column falls back to text()."""
        loc = await _seed_location(db)
        dept = await _seed_department(db, loc.id)
        await _seed_employee(db, dept.id, loc.id, email="fb@creativefuel.io")

        query = select(Employee)
        # This uses text() fallback — may fail at execution on some DBs
        # but the function itself shouldn't raise
        sorted_q = apply_sorting(query, Employee, "nonexistent_field")
        assert sorted_q is not query  # Modified


class TestGetColumn:
    """Tests for _get_column helper."""

    def test_get_existing_column(self):
        """_get_column returns the attribute for existing columns."""
        col = _get_column(Employee, "first_name")
        assert col is not None

    def test_get_nonexistent_column(self):
        """_get_column returns None for non-existent columns."""
        col = _get_column(Employee, "totally_fake_column")
        assert col is None


class TestPagination:
    """Tests for pagination helper."""

    async def test_paginate_with_sort(self, db: AsyncSession):
        """paginate() with sort parameter applies ORDER BY."""
        loc = await _seed_location(db)
        dept = await _seed_department(db, loc.id)

        for i in range(5):
            await _seed_employee(
                db, dept.id, loc.id,
                first_name=f"P{i}", email=f"p{i}@creativefuel.io",
            )

        query = select(Employee)
        params = PaginationParams(page=1, page_size=3, sort="-first_name")
        result = await paginate(db, query, params, model=Employee)
        assert len(result.data) == 3
        assert result.meta.page == 1
        assert result.meta.page_size == 3

    async def test_paginate_page_2(self, db: AsyncSession):
        """paginate() page 2 returns remaining items."""
        loc = await _seed_location(db)
        dept = await _seed_department(db, loc.id)

        for i in range(5):
            await _seed_employee(
                db, dept.id, loc.id,
                first_name=f"Q{i}", email=f"q{i}@creativefuel.io",
            )

        query = select(Employee)
        params = PaginationParams(page=2, page_size=3, sort=None)
        result = await paginate(db, query, params, model=Employee)
        assert len(result.data) == 2  # 5 total, page 2 at size 3 = 2
        assert result.meta.has_prev is True

    async def test_paginate_empty_result(self, db: AsyncSession):
        """paginate() with no matching rows returns empty data."""
        query = select(Employee).where(Employee.first_name == "ZZZ_NONEXISTENT")
        params = PaginationParams(page=1, page_size=10, sort=None)
        result = await paginate(db, query, params, model=Employee)
        assert len(result.data) == 0
        assert result.meta.total == 0
        assert result.meta.total_pages == 0
