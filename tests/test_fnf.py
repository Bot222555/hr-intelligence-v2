"""FnF (Full & Final) module test suite — 12 tests covering settlement
queries, summaries, and API endpoints.

Tests exercise both the service layer (direct DB) and the HTTP API (via router).
Uses the shared conftest.py pattern with in-memory SQLite.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select

from backend.common.constants import UserRole
from backend.config import settings
from backend.core_hr.models import Employee
from backend.fnf.models import FnFSettlement
from backend.fnf.service import FnFService
from tests.conftest import (
    TestSessionFactory,
    _make_employee,
    create_access_token,
)


# ── Helpers ─────────────────────────────────────────────────────────


async def _create_settlement(
    db, employee_id, *,
    status="pending",
    termination_type="resignation",
    total_earnings=100000,
    total_deductions=20000,
    net_settlement=80000,
    last_working_day=None,
) -> FnFSettlement:
    """Insert an FnF settlement record."""
    settlement = FnFSettlement(
        employee_id=employee_id,
        employee_number="CF-001",
        termination_type=termination_type,
        last_working_day=last_working_day or date(2026, 1, 31),
        no_of_pay_days=25,
        settlement_status=status,
        total_earnings=total_earnings,
        total_deductions=total_deductions,
        net_settlement=net_settlement,
        settlement_details={"gratuity": 50000, "leave_encashment": 30000},
    )
    db.add(settlement)
    await db.flush()
    return settlement


def _make_auth_headers(employee_id, role=UserRole.hr_admin):
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
# 1. SETTLEMENT QUERIES — Service Layer
# ═════════════════════════════════════════════════════════════════════


async def test_get_settlement_by_id(db, test_employee):
    """get_settlement returns the correct settlement."""
    settlement = await _create_settlement(db, test_employee["id"])

    fetched = await FnFService.get_settlement(db, settlement.id)
    assert fetched.id == settlement.id
    assert fetched.employee_id == test_employee["id"]
    assert float(fetched.net_settlement) == 80000


async def test_get_settlement_not_found(db):
    """get_settlement raises NotFoundException for unknown ID."""
    from backend.common.exceptions import NotFoundException
    with pytest.raises(NotFoundException):
        await FnFService.get_settlement(db, uuid.uuid4())


async def test_get_by_employee(db, test_employee):
    """get_by_employee returns settlement for a specific employee."""
    await _create_settlement(db, test_employee["id"])

    settlement = await FnFService.get_by_employee(db, test_employee["id"])
    assert settlement.employee_id == test_employee["id"]


async def test_get_by_employee_not_found(db, test_employee):
    """get_by_employee raises NotFoundException when no settlement exists."""
    from backend.common.exceptions import NotFoundException
    with pytest.raises(NotFoundException):
        await FnFService.get_by_employee(db, test_employee["id"])


async def test_list_settlements_all(db, test_employee, test_department, test_location):
    """list_settlements returns all settlements."""
    await _create_settlement(db, test_employee["id"])

    emp2_data = _make_employee(
        email="exited@creativefuel.io",
        first_name="Exited",
        department_id=test_department["id"],
        location_id=test_location["id"],
    )
    db.add(Employee(**emp2_data))
    await db.flush()
    await _create_settlement(db, emp2_data["id"], status="completed")

    settlements, total = await FnFService.list_settlements(db)
    assert total == 2
    assert len(settlements) == 2


async def test_list_settlements_filter_by_status(db, test_employee, test_department, test_location):
    """list_settlements filters by settlement_status."""
    await _create_settlement(db, test_employee["id"], status="pending")

    emp2_data = _make_employee(
        email="exited2@creativefuel.io",
        department_id=test_department["id"],
        location_id=test_location["id"],
    )
    db.add(Employee(**emp2_data))
    await db.flush()
    await _create_settlement(db, emp2_data["id"], status="completed")

    pending, total = await FnFService.list_settlements(db, settlement_status="pending")
    assert total == 1
    assert pending[0].settlement_status == "pending"


async def test_list_settlements_filter_by_termination_type(db, test_employee):
    """list_settlements filters by termination_type."""
    await _create_settlement(db, test_employee["id"], termination_type="resignation")

    results, total = await FnFService.list_settlements(
        db, termination_type="resignation",
    )
    assert total == 1
    assert results[0].termination_type == "resignation"


async def test_list_settlements_pagination(db, test_employee, test_department, test_location):
    """list_settlements respects page and page_size."""
    emps = []
    for i in range(4):
        emp_data = _make_employee(
            email=f"exit{i}@creativefuel.io",
            first_name=f"Exit{i}",
            department_id=test_department["id"],
            location_id=test_location["id"],
        )
        db.add(Employee(**emp_data))
        await db.flush()
        emps.append(emp_data)

    for emp in emps:
        await _create_settlement(db, emp["id"])

    page1, total = await FnFService.list_settlements(db, page=1, page_size=2)
    assert total == 4
    assert len(page1) == 2

    page2, _ = await FnFService.list_settlements(db, page=2, page_size=2)
    assert len(page2) == 2


# ═════════════════════════════════════════════════════════════════════
# 2. SUMMARY
# ═════════════════════════════════════════════════════════════════════


async def test_get_summary(db, test_employee, test_department, test_location):
    """get_summary returns correct aggregate statistics."""
    await _create_settlement(
        db, test_employee["id"],
        status="pending", net_settlement=80000,
    )

    emp2_data = _make_employee(
        email="exit.sum@creativefuel.io",
        department_id=test_department["id"],
        location_id=test_location["id"],
    )
    db.add(Employee(**emp2_data))
    await db.flush()
    await _create_settlement(
        db, emp2_data["id"],
        status="completed", net_settlement=120000,
    )

    summary = await FnFService.get_summary(db)
    assert summary["total_settlements"] == 2
    assert summary["pending"] == 1
    assert summary["completed"] == 1
    assert summary["total_net_amount"] == 200000.0


async def test_get_summary_empty(db):
    """get_summary returns zeros when no settlements exist."""
    summary = await FnFService.get_summary(db)
    assert summary["total_settlements"] == 0
    assert summary["pending"] == 0
    assert summary["completed"] == 0


# ═════════════════════════════════════════════════════════════════════
# 3. API ENDPOINTS
# ═════════════════════════════════════════════════════════════════════


async def test_api_fnf_requires_hr_role(client, db, test_employee, auth_headers):
    """FnF endpoints require HR/Admin role — employee gets 403."""
    resp = await client.get("/api/v1/fnf/", headers=auth_headers)
    assert resp.status_code == 403


async def test_api_fnf_list_with_hr_role(client, db, test_employee, test_department, test_location):
    """GET /api/v1/fnf/ with HR role returns settlements."""
    await _create_settlement(db, test_employee["id"])

    headers, token = _make_auth_headers(test_employee["id"], role=UserRole.hr_admin)
    await _persist_session(db, test_employee["id"], token)
    await db.commit()

    resp = await client.get("/api/v1/fnf/", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1


async def test_fnf_model_repr(db, test_employee):
    """FnFSettlement __repr__ works."""
    settlement = await _create_settlement(db, test_employee["id"])
    r = repr(settlement)
    assert "FnFSettlement" in r
    assert "pending" in r
