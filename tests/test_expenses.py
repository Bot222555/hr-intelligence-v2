"""Expenses module test suite — 15 tests covering expense claim CRUD,
approval workflow, and API endpoints.

Tests exercise both the service layer (direct DB) and the HTTP API (via router).
Uses the shared conftest.py pattern with in-memory SQLite.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from backend.common.constants import UserRole
from backend.config import settings
from backend.core_hr.models import Employee
from backend.expenses.models import ExpenseClaim
from backend.expenses.service import ExpenseService
from tests.conftest import (
    TestSessionFactory,
    _make_employee,
    create_access_token,
)


# ── Helpers ─────────────────────────────────────────────────────────


async def _create_claim(db, employee_id, *, title="Business lunch",
                         amount=1500, status="submitted") -> ExpenseClaim:
    """Insert an expense claim directly."""
    count_stmt = select(ExpenseClaim)
    total = len((await db.execute(count_stmt)).scalars().all())
    claim = ExpenseClaim(
        employee_id=employee_id,
        employee_name="Test User",
        claim_number=f"EXP-{total + 1:05d}",
        title=title,
        amount=amount,
        currency="INR",
        approval_status=status,
        submitted_date=date.today(),
        expenses=[{"description": title, "amount": amount}],
    )
    db.add(claim)
    await db.flush()
    return claim


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
# 1. EXPENSE CLAIM CRUD — Service Layer
# ═════════════════════════════════════════════════════════════════════


async def test_create_expense_claim(db, test_employee):
    """Creating an expense claim generates claim number and sets correct fields."""
    claim = await ExpenseService.create_claim(
        db,
        employee_id=test_employee["id"],
        employee_name="Test User",
        title="Client dinner",
        amount=3500,
        currency="INR",
        expenses=[{"description": "Dinner at restaurant", "amount": 3500}],
        remarks="Client entertainment",
    )
    assert claim.title == "Client dinner"
    assert float(claim.amount) == 3500
    assert claim.approval_status == "submitted"
    assert claim.claim_number.startswith("EXP-")
    assert claim.submitted_date == date.today()


async def test_get_claim_by_id(db, test_employee):
    """Getting a claim by ID returns the correct claim."""
    claim = await _create_claim(db, test_employee["id"])
    fetched = await ExpenseService.get_claim(db, claim.id)
    assert fetched.id == claim.id
    assert fetched.title == "Business lunch"


async def test_get_claim_not_found(db):
    """Getting a non-existent claim raises NotFoundException."""
    from backend.common.exceptions import NotFoundException
    with pytest.raises(NotFoundException):
        await ExpenseService.get_claim(db, uuid.uuid4())


async def test_list_claims_all(db, test_employee):
    """list_claims returns all claims."""
    await _create_claim(db, test_employee["id"], title="Claim 1")
    await _create_claim(db, test_employee["id"], title="Claim 2", amount=2000)

    claims, total = await ExpenseService.list_claims(db)
    assert total == 2
    assert len(claims) == 2


async def test_list_claims_filter_by_employee(db, test_employee, test_department, test_location):
    """list_claims filters by employee_id."""
    await _create_claim(db, test_employee["id"], title="My claim")

    emp2_data = _make_employee(
        email="emp2@creativefuel.io",
        department_id=test_department["id"],
        location_id=test_location["id"],
    )
    db.add(Employee(**emp2_data))
    await db.flush()
    await _create_claim(db, emp2_data["id"], title="Other claim")

    my_claims, total = await ExpenseService.list_claims(
        db, employee_id=test_employee["id"],
    )
    assert total == 1
    assert my_claims[0].title == "My claim"


async def test_list_claims_filter_by_status(db, test_employee):
    """list_claims filters by approval_status."""
    await _create_claim(db, test_employee["id"], title="Submitted", status="submitted")
    await _create_claim(db, test_employee["id"], title="Approved", status="approved")

    submitted, total = await ExpenseService.list_claims(
        db, approval_status="submitted",
    )
    assert total == 1
    assert submitted[0].approval_status == "submitted"


# ═════════════════════════════════════════════════════════════════════
# 2. UPDATE EXPENSE CLAIMS
# ═════════════════════════════════════════════════════════════════════


async def test_update_claim_title(db, test_employee):
    """Updating a submitted claim's title works."""
    claim = await _create_claim(db, test_employee["id"])

    updated = await ExpenseService.update_claim(
        db, claim.id, actor_id=test_employee["id"],
        title="Updated business lunch",
    )
    assert updated.title == "Updated business lunch"


async def test_update_approved_claim_fails(db, test_employee):
    """Updating an approved claim raises ValidationException."""
    from backend.common.exceptions import ValidationException

    claim = await _create_claim(db, test_employee["id"], status="approved")

    with pytest.raises(ValidationException):
        await ExpenseService.update_claim(
            db, claim.id, actor_id=test_employee["id"],
            title="Should fail",
        )


async def test_update_claim_by_non_owner_fails(db, test_employee, test_department, test_location):
    """Updating a claim by someone other than the owner raises ForbiddenException."""
    from backend.common.exceptions import ForbiddenException

    claim = await _create_claim(db, test_employee["id"])

    other_data = _make_employee(
        email="other@creativefuel.io",
        department_id=test_department["id"],
        location_id=test_location["id"],
    )
    db.add(Employee(**other_data))
    await db.flush()

    with pytest.raises(ForbiddenException):
        await ExpenseService.update_claim(
            db, claim.id, actor_id=other_data["id"],
            title="Not my claim",
        )


# ═════════════════════════════════════════════════════════════════════
# 3. APPROVAL WORKFLOW
# ═════════════════════════════════════════════════════════════════════


async def test_approve_claim(db, test_employee, test_department, test_location):
    """Approving a submitted claim sets approval status and approver."""
    claim = await _create_claim(db, test_employee["id"])

    manager_data = _make_employee(
        email="manager@creativefuel.io",
        first_name="Manager",
        department_id=test_department["id"],
        location_id=test_location["id"],
    )
    db.add(Employee(**manager_data))
    await db.flush()

    approved = await ExpenseService.approve_claim(
        db, claim.id, approver_id=manager_data["id"],
        remarks="Looks good",
    )
    assert approved.approval_status == "approved"
    assert approved.approved_by_id == manager_data["id"]
    assert approved.approved_at is not None
    assert approved.remarks == "Looks good"


async def test_reject_claim(db, test_employee, test_department, test_location):
    """Rejecting a submitted claim sets approval status to rejected."""
    claim = await _create_claim(db, test_employee["id"])

    manager_data = _make_employee(
        email="manager2@creativefuel.io",
        department_id=test_department["id"],
        location_id=test_location["id"],
    )
    db.add(Employee(**manager_data))
    await db.flush()

    rejected = await ExpenseService.reject_claim(
        db, claim.id, approver_id=manager_data["id"],
        remarks="Missing receipt",
    )
    assert rejected.approval_status == "rejected"
    assert rejected.remarks == "Missing receipt"


async def test_approve_already_approved_fails(db, test_employee, test_department, test_location):
    """Approving an already-approved claim raises ValidationException."""
    from backend.common.exceptions import ValidationException

    claim = await _create_claim(db, test_employee["id"], status="approved")

    manager_data = _make_employee(
        email="mgr3@creativefuel.io",
        department_id=test_department["id"],
        location_id=test_location["id"],
    )
    db.add(Employee(**manager_data))
    await db.flush()

    with pytest.raises(ValidationException):
        await ExpenseService.approve_claim(db, claim.id, manager_data["id"])


# ═════════════════════════════════════════════════════════════════════
# 4. API ENDPOINTS
# ═════════════════════════════════════════════════════════════════════


async def test_api_create_expense(client, db, test_employee, auth_headers):
    """POST /api/v1/expenses/ creates a new expense claim."""
    resp = await client.post(
        "/api/v1/expenses/",
        json={"title": "API expense", "amount": "2500.00"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == "API expense"
    assert data["claim_number"].startswith("EXP-")


async def test_api_my_expenses(client, db, test_employee, auth_headers):
    """GET /api/v1/expenses/my-expenses returns current user's claims."""
    await _create_claim(db, test_employee["id"])
    await db.commit()

    resp = await client.get("/api/v1/expenses/my-expenses", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1


async def test_api_expenses_requires_auth(client):
    """Expenses endpoints return 401 without auth."""
    resp = await client.get("/api/v1/expenses/")
    assert resp.status_code == 401
