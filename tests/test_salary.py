"""Salary module test suite — 15 tests covering components, salary CRUD,
CTC breakdowns, and API endpoints.

Tests exercise both the service layer (direct DB) and the HTTP API (via router).
Uses the shared conftest.py pattern with in-memory SQLite.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select

from backend.common.constants import UserRole
from backend.config import settings
from backend.core_hr.models import Employee
from backend.salary.models import Salary, SalaryComponent
from backend.salary.service import SalaryService
from tests.conftest import (
    TestSessionFactory,
    _make_employee,
    create_access_token,
)


# ── Helpers ─────────────────────────────────────────────────────────


async def _create_salary_component(db, *, title="Basic Pay",
                                    identifier="basic",
                                    component_type="earning") -> SalaryComponent:
    """Insert a salary component and return the ORM object."""
    comp = SalaryComponent(
        title=title,
        identifier=identifier,
        component_type=component_type,
    )
    db.add(comp)
    await db.flush()
    return comp


async def _create_salary(db, employee_id, *, ctc=600000, gross=500000,
                          net=450000, is_current=True) -> Salary:
    """Insert a salary record."""
    salary = Salary(
        employee_id=employee_id,
        ctc=ctc,
        gross_pay=gross,
        net_pay=net,
        earnings=[{"component": "Basic", "amount": 250000}],
        deductions=[{"component": "PF", "amount": 21600}],
        contributions=[{"component": "Employer PF", "amount": 21600}],
        variables=[],
        is_current=is_current,
    )
    db.add(salary)
    await db.flush()
    return salary


def _make_auth_headers(employee_id, role=UserRole.employee):
    token = create_access_token(employee_id, role=role)
    return {"Authorization": f"Bearer {token}"}, token


async def _persist_session(db, employee_id, token):
    from backend.auth.models import UserSession
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
# 1. SALARY COMPONENTS
# ═════════════════════════════════════════════════════════════════════


async def test_get_components_returns_all_active(db):
    """get_components returns all active salary components."""
    await _create_salary_component(db, title="Basic Pay", identifier="basic")
    await _create_salary_component(db, title="HRA", identifier="hra")
    await _create_salary_component(db, title="PF", identifier="pf", component_type="deduction")

    components = await SalaryService.get_components(db)
    assert len(components) == 3
    titles = {c.title for c in components}
    assert "Basic Pay" in titles
    assert "HRA" in titles
    assert "PF" in titles


async def test_get_components_filters_inactive(db):
    """Inactive components are excluded when filtering by is_active=True."""
    active = await _create_salary_component(db, title="Active Comp", identifier="active")
    inactive = await _create_salary_component(db, title="Inactive Comp", identifier="inactive")
    inactive.is_active = False
    await db.flush()

    active_only = await SalaryService.get_components(db, is_active=True)
    assert len(active_only) == 1
    assert active_only[0].title == "Active Comp"


async def test_get_components_all(db):
    """is_active=None returns all components including inactive."""
    await _create_salary_component(db, title="Comp A", identifier="a")
    inactive = await _create_salary_component(db, title="Comp B", identifier="b")
    inactive.is_active = False
    await db.flush()

    all_comps = await SalaryService.get_components(db, is_active=None)
    assert len(all_comps) == 2


# ═════════════════════════════════════════════════════════════════════
# 2. SALARY RECORDS — Service Layer
# ═════════════════════════════════════════════════════════════════════


async def test_get_salary_by_employee(db, test_employee):
    """get_salary_by_employee returns the current salary."""
    await _create_salary(db, test_employee["id"])

    salary = await SalaryService.get_salary_by_employee(db, test_employee["id"])
    assert salary.employee_id == test_employee["id"]
    assert salary.is_current is True
    assert float(salary.ctc) == 600000


async def test_get_salary_not_found_raises(db, test_employee):
    """get_salary_by_employee raises NotFoundException when no salary exists."""
    from backend.common.exceptions import NotFoundException

    with pytest.raises(NotFoundException):
        await SalaryService.get_salary_by_employee(db, test_employee["id"])


async def test_get_salary_slips_paginated(db, test_employee, test_department, test_location):
    """get_salary_slips returns paginated results."""
    await _create_salary(db, test_employee["id"])

    # Create another employee with salary
    emp2_data = _make_employee(
        email="emp2@creativefuel.io",
        first_name="Second",
        department_id=test_department["id"],
        location_id=test_location["id"],
    )
    db.add(Employee(**emp2_data))
    await db.flush()
    # Create a separate salary for emp2 (not is_current to avoid unique constraint)
    sal2 = Salary(
        employee_id=emp2_data["id"],
        ctc=800000,
        gross_pay=700000,
        net_pay=600000,
        is_current=True,
    )
    db.add(sal2)
    await db.flush()

    slips, total = await SalaryService.get_salary_slips(db, page=1, page_size=10)
    assert total == 2
    assert len(slips) == 2


async def test_get_salary_slips_filtered_by_employee(db, test_employee):
    """get_salary_slips filters by employee_id."""
    await _create_salary(db, test_employee["id"])

    slips, total = await SalaryService.get_salary_slips(
        db, employee_id=test_employee["id"],
    )
    assert total == 1
    assert slips[0].employee_id == test_employee["id"]


# ═════════════════════════════════════════════════════════════════════
# 3. CTC BREAKDOWN
# ═════════════════════════════════════════════════════════════════════


async def test_ctc_breakdown_returns_all_components(db, test_employee):
    """CTC breakdown includes earnings, deductions, contributions."""
    await _create_salary(db, test_employee["id"])

    breakdown = await SalaryService.get_ctc_breakdown(db, test_employee["id"])
    assert breakdown["employee_id"] == test_employee["id"]
    assert float(breakdown["ctc"]) == 600000
    assert float(breakdown["gross_pay"]) == 500000
    assert float(breakdown["net_pay"]) == 450000
    assert len(breakdown["earnings"]) == 1
    assert len(breakdown["deductions"]) == 1


async def test_ctc_breakdown_not_found(db, test_employee):
    """CTC breakdown raises NotFoundException when no salary exists."""
    from backend.common.exceptions import NotFoundException

    with pytest.raises(NotFoundException):
        await SalaryService.get_ctc_breakdown(db, test_employee["id"])


# ═════════════════════════════════════════════════════════════════════
# 4. API ENDPOINTS
# ═════════════════════════════════════════════════════════════════════


async def test_api_my_salary(client, db, test_employee, auth_headers):
    """GET /api/v1/salary/my-salary returns current salary."""
    await _create_salary(db, test_employee["id"])
    await db.commit()

    resp = await client.get("/api/v1/salary/my-salary", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["employee_id"] == str(test_employee["id"])
    assert float(data["ctc"]) == 600000


async def test_api_my_ctc(client, db, test_employee, auth_headers):
    """GET /api/v1/salary/my-ctc returns CTC breakdown."""
    await _create_salary(db, test_employee["id"])
    await db.commit()

    resp = await client.get("/api/v1/salary/my-ctc", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["employee_id"] == str(test_employee["id"])
    assert "earnings" in data
    assert "deductions" in data


async def test_api_salary_requires_auth(client):
    """Salary endpoints return 401 without auth."""
    resp = await client.get("/api/v1/salary/my-salary")
    assert resp.status_code == 401


async def test_salary_component_model_repr(db):
    """SalaryComponent __repr__ works."""
    comp = await _create_salary_component(db, title="Test Comp", identifier="test")
    assert "Test Comp" in repr(comp)


async def test_salary_model_repr(db, test_employee):
    """Salary __repr__ works."""
    sal = await _create_salary(db, test_employee["id"])
    assert "600000" in repr(sal) or str(test_employee["id"]) in repr(sal)
