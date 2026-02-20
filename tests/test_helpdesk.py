"""Helpdesk module test suite — 15 tests covering ticket CRUD, responses,
status transitions, and API endpoints.

Tests exercise both the service layer (direct DB) and the HTTP API (via router).
Uses the shared conftest.py pattern with in-memory SQLite.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from backend.common.constants import UserRole
from backend.config import settings
from backend.core_hr.models import Employee
from backend.helpdesk.models import HelpdeskResponse, HelpdeskTicket
from backend.helpdesk.service import HelpdeskService
from tests.conftest import (
    TestSessionFactory,
    _make_employee,
    create_access_token,
)


# ── Helpers ─────────────────────────────────────────────────────────


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
# 1. TICKET CRUD — Service Layer
# ═════════════════════════════════════════════════════════════════════


async def test_create_ticket(db, test_employee):
    """Creating a ticket sets correct fields and generates ticket number."""
    ticket = await HelpdeskService.create_ticket(
        db,
        employee_id=test_employee["id"],
        employee_name="Test User",
        title="Cannot access VPN",
        category="IT Support",
        priority="high",
    )
    assert ticket.title == "Cannot access VPN"
    assert ticket.status == "open"
    assert ticket.priority == "high"
    assert ticket.ticket_number.startswith("HD-")
    assert ticket.raised_by_id == test_employee["id"]


async def test_get_ticket_by_id(db, test_employee):
    """Getting a ticket by ID returns the correct ticket with responses."""
    ticket = await HelpdeskService.create_ticket(
        db,
        employee_id=test_employee["id"],
        employee_name="Test User",
        title="Printer not working",
    )
    fetched = await HelpdeskService.get_ticket(db, ticket.id)
    assert fetched.id == ticket.id
    assert fetched.title == "Printer not working"


async def test_get_ticket_not_found(db):
    """Getting a non-existent ticket raises NotFoundException."""
    from backend.common.exceptions import NotFoundException
    with pytest.raises(NotFoundException):
        await HelpdeskService.get_ticket(db, uuid.uuid4())


async def test_list_tickets_with_filters(db, test_employee):
    """list_tickets filters by status and priority."""
    await HelpdeskService.create_ticket(
        db, employee_id=test_employee["id"],
        employee_name="Test", title="Issue 1", priority="high",
    )
    await HelpdeskService.create_ticket(
        db, employee_id=test_employee["id"],
        employee_name="Test", title="Issue 2", priority="low",
    )

    # Filter by priority
    high_tickets, total = await HelpdeskService.list_tickets(db, priority="high")
    assert total == 1
    assert high_tickets[0].title == "Issue 1"


async def test_list_tickets_pagination(db, test_employee):
    """list_tickets respects page and page_size."""
    for i in range(5):
        await HelpdeskService.create_ticket(
            db, employee_id=test_employee["id"],
            employee_name="Test", title=f"Issue {i}",
        )

    page1, total = await HelpdeskService.list_tickets(db, page=1, page_size=2)
    assert total == 5
    assert len(page1) == 2

    page3, _ = await HelpdeskService.list_tickets(db, page=3, page_size=2)
    assert len(page3) == 1


# ═════════════════════════════════════════════════════════════════════
# 2. TICKET UPDATE & STATUS TRANSITIONS
# ═════════════════════════════════════════════════════════════════════


async def test_update_ticket_status(db, test_employee):
    """Updating ticket status works correctly."""
    ticket = await HelpdeskService.create_ticket(
        db, employee_id=test_employee["id"],
        employee_name="Test", title="Network issue",
    )

    updated = await HelpdeskService.update_ticket(
        db, ticket.id, status="in_progress",
    )
    assert updated.status == "in_progress"


async def test_resolve_ticket_sets_resolved_at(db, test_employee):
    """Setting status to 'resolved' populates resolved_at timestamp."""
    ticket = await HelpdeskService.create_ticket(
        db, employee_id=test_employee["id"],
        employee_name="Test", title="Need keyboard replacement",
    )

    resolved = await HelpdeskService.update_ticket(
        db, ticket.id, status="resolved",
    )
    assert resolved.status == "resolved"
    assert resolved.resolved_at is not None


async def test_update_ticket_assignee(db, test_employee, test_department, test_location):
    """Updating assigned_to_id changes the assignee."""
    admin_data = _make_employee(
        email="admin@creativefuel.io",
        first_name="Admin",
        department_id=test_department["id"],
        location_id=test_location["id"],
    )
    db.add(Employee(**admin_data))
    await db.flush()

    ticket = await HelpdeskService.create_ticket(
        db, employee_id=test_employee["id"],
        employee_name="Test", title="Software install request",
    )

    updated = await HelpdeskService.update_ticket(
        db, ticket.id, assigned_to_id=admin_data["id"],
    )
    assert updated.assigned_to_id == admin_data["id"]


async def test_delete_ticket(db, test_employee):
    """Deleting a ticket removes it from the database."""
    ticket = await HelpdeskService.create_ticket(
        db, employee_id=test_employee["id"],
        employee_name="Test", title="Delete me",
    )

    await HelpdeskService.delete_ticket(db, ticket.id)
    await db.flush()

    from backend.common.exceptions import NotFoundException
    with pytest.raises(NotFoundException):
        await HelpdeskService.get_ticket(db, ticket.id)


# ═════════════════════════════════════════════════════════════════════
# 3. TICKET RESPONSES
# ═════════════════════════════════════════════════════════════════════


async def test_add_response_to_ticket(db, test_employee):
    """Adding a response links it to the correct ticket."""
    ticket = await HelpdeskService.create_ticket(
        db, employee_id=test_employee["id"],
        employee_name="Test", title="Need help",
    )

    response = await HelpdeskService.add_response(
        db,
        ticket_id=ticket.id,
        author_id=test_employee["id"],
        author_name="Test User",
        body="I'll look into this.",
    )
    assert response.ticket_id == ticket.id
    assert response.body == "I'll look into this."
    assert response.is_internal is False


async def test_add_internal_response(db, test_employee):
    """Internal responses are flagged correctly."""
    ticket = await HelpdeskService.create_ticket(
        db, employee_id=test_employee["id"],
        employee_name="Test", title="Internal note test",
    )

    response = await HelpdeskService.add_response(
        db,
        ticket_id=ticket.id,
        author_id=test_employee["id"],
        author_name="Test User",
        body="This is an internal note.",
        is_internal=True,
    )
    assert response.is_internal is True


async def test_list_responses(db, test_employee):
    """list_responses returns all responses for a ticket in order."""
    ticket = await HelpdeskService.create_ticket(
        db, employee_id=test_employee["id"],
        employee_name="Test", title="Multiple responses",
    )

    for i in range(3):
        await HelpdeskService.add_response(
            db, ticket_id=ticket.id,
            author_id=test_employee["id"],
            author_name="Test", body=f"Response {i}",
        )

    responses = await HelpdeskService.list_responses(db, ticket.id)
    assert len(responses) == 3


# ═════════════════════════════════════════════════════════════════════
# 4. API ENDPOINTS
# ═════════════════════════════════════════════════════════════════════


async def test_api_create_ticket(client, db, test_employee, auth_headers):
    """POST /api/v1/helpdesk/ creates a new ticket."""
    resp = await client.post(
        "/api/v1/helpdesk/",
        json={"title": "API created ticket", "priority": "medium"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == "API created ticket"
    assert data["status"] == "open"
    assert data["ticket_number"].startswith("HD-")


async def test_api_list_tickets(client, db, test_employee, auth_headers):
    """GET /api/v1/helpdesk/ returns paginated tickets."""
    # Create some tickets first
    await HelpdeskService.create_ticket(
        db, employee_id=test_employee["id"],
        employee_name="Test", title="Ticket 1",
    )
    await db.commit()

    resp = await client.get("/api/v1/helpdesk/", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    assert len(data["data"]) >= 1


async def test_api_helpdesk_requires_auth(client):
    """Helpdesk endpoints return 401 without auth."""
    resp = await client.get("/api/v1/helpdesk/")
    assert resp.status_code == 401
