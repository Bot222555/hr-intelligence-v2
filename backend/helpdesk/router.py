"""Helpdesk router — CRUD tickets, responses, status updates.

All endpoints require authentication.
"""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from fastapi import Request as _Request

from backend.auth.dependencies import get_current_user, require_role
from backend.auth.models import RoleAssignment
from backend.common.constants import UserRole
from backend.common.exceptions import ForbiddenException
from backend.core_hr.models import Employee
from backend.database import get_db
import math

from backend.helpdesk.schemas import (
    PaginationMeta,
    ResponseCreate,
    ResponseOut,
    TicketCreate,
    TicketListResponse,
    TicketOut,
    TicketUpdate,
)


def _build_meta(total: int, page: int, page_size: int) -> PaginationMeta:
    total_pages = max(1, math.ceil(total / page_size)) if page_size else 1
    return PaginationMeta(
        page=page,
        page_size=page_size,
        total=total,
        total_pages=total_pages,
        has_next=page < total_pages,
        has_prev=page > 1,
    )
from backend.helpdesk.service import HelpdeskService

router = APIRouter(prefix="", tags=["helpdesk"])


async def _is_hr_or_admin(db: AsyncSession, employee_id: uuid.UUID) -> bool:
    """Check if the employee has hr_admin or system_admin role."""
    from sqlalchemy import select as _sel
    result = await db.execute(
        _sel(RoleAssignment).where(
            RoleAssignment.employee_id == employee_id,
            RoleAssignment.role.in_([UserRole.hr_admin, UserRole.system_admin]),
            RoleAssignment.is_active.is_(True),
        )
    )
    return result.scalars().first() is not None


# ── POST / ───────────────────────────────────────────────────────────

@router.post("/", response_model=TicketOut, status_code=201)
async def create_ticket(
    body: TicketCreate,
    employee: Employee = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new helpdesk ticket."""
    ticket = await HelpdeskService.create_ticket(
        db,
        employee_id=employee.id,
        employee_name=employee.display_name or f"{employee.first_name} {employee.last_name}",
        title=body.title,
        category=body.category,
        priority=body.priority,
    )
    # R2-11: If description is provided, add it as the first response on the ticket
    if body.description:
        await HelpdeskService.add_response(
            db,
            ticket_id=ticket.id,
            author_id=employee.id,
            author_name=employee.display_name or f"{employee.first_name} {employee.last_name}",
            body=body.description,
            is_internal=False,
        )
        await db.refresh(ticket, ["responses"])
    await db.commit()
    return TicketOut.model_validate(ticket)


# ── GET / ────────────────────────────────────────────────────────────

@router.get("/", response_model=TicketListResponse)
async def list_tickets(
    request: _Request,
    status: Optional[str] = Query(None),
    priority: Optional[str] = Query(None),
    raised_by_id: Optional[uuid.UUID] = Query(None),
    assigned_to_id: Optional[uuid.UUID] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    employee: Employee = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List helpdesk tickets with optional filters."""
    # R2-12 + R2-13: Non-HR users can only see their own tickets or tickets assigned to them
    is_hr = await _is_hr_or_admin(db, employee.id)
    if not is_hr:
        # R2-13: Prevent IDOR via raised_by_id filter
        if raised_by_id and raised_by_id != employee.id:
            raise ForbiddenException("Cannot view another employee's tickets.")
        # R2-12: Default to own tickets for regular employees
        if not raised_by_id and not assigned_to_id:
            raised_by_id = employee.id
    tickets, total = await HelpdeskService.list_tickets(
        db,
        status=status,
        priority=priority,
        raised_by_id=raised_by_id,
        assigned_to_id=assigned_to_id,
        page=page,
        page_size=page_size,
    )
    return TicketListResponse(
        data=[TicketOut.model_validate(t) for t in tickets],
        meta=_build_meta(total, page, page_size),
        total=total,
        page=page,
        page_size=page_size,
    )


# ── GET /my-tickets ──────────────────────────────────────────────────

@router.get("/my-tickets", response_model=TicketListResponse)
async def my_tickets(
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    employee: Employee = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List tickets raised by the current user."""
    tickets, total = await HelpdeskService.list_tickets(
        db,
        status=status,
        raised_by_id=employee.id,
        page=page,
        page_size=page_size,
    )
    return TicketListResponse(
        data=[TicketOut.model_validate(t) for t in tickets],
        meta=_build_meta(total, page, page_size),
        total=total,
        page=page,
        page_size=page_size,
    )


# ── GET /summary ──────────────────────────────────────────────────────

@router.get("/summary")
async def helpdesk_summary(
    employee: Employee = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Summary stats for helpdesk tickets visible to the current user."""
    # R2-22: For non-HR users, only count their own tickets
    is_hr = await _is_hr_or_admin(db, employee.id)
    filter_kwargs = {} if is_hr else {"raised_by_id": employee.id}
    tickets, total = await HelpdeskService.list_tickets(
        db, page=1, page_size=10000, **filter_kwargs,
    )
    open_count = 0
    in_progress_count = 0
    resolved_count = 0
    closed_count = 0
    for t in tickets:
        status = str(getattr(t, "status", "")).lower()
        if status == "open":
            open_count += 1
        elif status == "in_progress":
            in_progress_count += 1
        elif status == "resolved":
            resolved_count += 1
        elif status == "closed":
            closed_count += 1
    return {
        "total_tickets": total,
        "open_count": open_count,
        "in_progress_count": in_progress_count,
        "resolved_count": resolved_count,
        "closed_count": closed_count,
    }


# ── GET /{ticket_id} ─────────────────────────────────────────────────

@router.get("/{ticket_id}", response_model=TicketOut)
async def get_ticket(
    ticket_id: uuid.UUID,
    employee: Employee = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific ticket with all responses."""
    ticket = await HelpdeskService.get_ticket(db, ticket_id)
    # R2-06: Ownership / role check
    if ticket.raised_by_id != employee.id and ticket.assigned_to_id != employee.id:
        is_hr = await _is_hr_or_admin(db, employee.id)
        if not is_hr:
            raise ForbiddenException("You don't have access to this ticket.")
    return TicketOut.model_validate(ticket)


# ── PATCH /{ticket_id} ───────────────────────────────────────────────

@router.patch("/{ticket_id}", response_model=TicketOut)
async def update_ticket(
    ticket_id: uuid.UUID,
    body: TicketUpdate,
    employee: Employee = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a ticket (title, category, status, priority, assignee)."""
    # R2-06: Ownership / role check before update
    ticket = await HelpdeskService.get_ticket(db, ticket_id)
    if ticket.raised_by_id != employee.id and ticket.assigned_to_id != employee.id:
        is_hr = await _is_hr_or_admin(db, employee.id)
        if not is_hr:
            raise ForbiddenException("You don't have access to this ticket.")

    # R2-28: Validate status transitions
    update_data = body.model_dump(exclude_unset=True)
    if "status" in update_data:
        VALID_TRANSITIONS = {
            "open": ["in_progress", "closed", "waiting"],
            "in_progress": ["resolved", "closed", "waiting"],
            "waiting": ["in_progress", "resolved", "closed"],
            "resolved": ["closed", "open"],
            "closed": [],
        }
        old_status = ticket.status
        new_status = update_data["status"]
        if new_status not in VALID_TRANSITIONS.get(old_status, []):
            from backend.common.exceptions import ValidationException
            raise ValidationException(
                {"status": [f"Cannot transition from '{old_status}' to '{new_status}'."]}
            )

    ticket = await HelpdeskService.update_ticket(db, ticket_id, **update_data)
    await db.commit()
    return TicketOut.model_validate(ticket)


# ── DELETE /{ticket_id} ──────────────────────────────────────────────

@router.delete("/{ticket_id}", status_code=204)
async def delete_ticket(
    ticket_id: uuid.UUID,
    employee: Employee = Depends(
        require_role(UserRole.hr_admin, UserRole.system_admin)
    ),
    db: AsyncSession = Depends(get_db),
):
    """Delete a ticket (HR/Admin only)."""
    await HelpdeskService.delete_ticket(db, ticket_id)
    await db.commit()


# ── POST /{ticket_id}/responses ───────────────────────────────────────

@router.post("/{ticket_id}/responses", response_model=ResponseOut, status_code=201)
async def add_response(
    ticket_id: uuid.UUID,
    body: ResponseCreate,
    employee: Employee = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Add a response/comment to a ticket."""
    response = await HelpdeskService.add_response(
        db,
        ticket_id=ticket_id,
        author_id=employee.id,
        author_name=employee.display_name or f"{employee.first_name} {employee.last_name}",
        body=body.body,
        is_internal=body.is_internal,
    )
    await db.commit()
    return ResponseOut.model_validate(response)


# ── GET /{ticket_id}/responses ────────────────────────────────────────

@router.get("/{ticket_id}/responses", response_model=list[ResponseOut])
async def list_responses(
    ticket_id: uuid.UUID,
    employee: Employee = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all responses for a ticket."""
    responses = await HelpdeskService.list_responses(db, ticket_id)
    return [ResponseOut.model_validate(r) for r in responses]
