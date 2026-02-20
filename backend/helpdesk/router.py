"""Helpdesk router — CRUD tickets, responses, status updates.

All endpoints require authentication.
"""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth.dependencies import get_current_user, require_role
from backend.common.constants import UserRole
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
    await db.commit()
    return TicketOut.model_validate(ticket)


# ── GET / ────────────────────────────────────────────────────────────

@router.get("/", response_model=TicketListResponse)
async def list_tickets(
    status: Optional[str] = Query(None),
    priority: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    raised_by_id: Optional[uuid.UUID] = Query(None),
    assigned_to_id: Optional[uuid.UUID] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    employee: Employee = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List helpdesk tickets with optional filters."""
    tickets, total = await HelpdeskService.list_tickets(
        db,
        status=status,
        priority=priority,
        category=category,
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
    category: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    employee: Employee = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List tickets raised by the current user."""
    tickets, total = await HelpdeskService.list_tickets(
        db,
        status=status,
        category=category,
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
    employee: Employee = Depends(
        require_role(UserRole.manager, UserRole.hr_admin, UserRole.system_admin)
    ),
    db: AsyncSession = Depends(get_db),
):
    """Summary stats for all helpdesk tickets (Manager/HR/Admin only)."""
    from sqlalchemy import case, func, select
    from backend.helpdesk.models import HelpdeskTicket

    stmt = select(
        func.count().label("total"),
        func.sum(case((HelpdeskTicket.status == "open", 1), else_=0)).label("open_count"),
        func.sum(case((HelpdeskTicket.status == "in_progress", 1), else_=0)).label("in_progress"),
        func.sum(case((HelpdeskTicket.status == "resolved", 1), else_=0)).label("resolved"),
        func.sum(case((HelpdeskTicket.status == "closed", 1), else_=0)).label("closed"),
    )
    result = await db.execute(stmt)
    row = result.one()
    return {
        "total_tickets": row.total,
        "open_count": row.open_count,
        "in_progress_count": row.in_progress,
        "resolved_count": row.resolved,
        "closed_count": row.closed,
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
    # Authorization: only ticket owner, assignee, or hr_admin/system_admin
    ticket = await HelpdeskService.get_ticket(db, ticket_id)
    user_role = getattr(employee, "role", None) or getattr(employee, "user_role", None)
    is_owner = ticket.raised_by_id == employee.id
    is_assignee = ticket.assigned_to_id == employee.id
    is_admin = user_role in (UserRole.hr_admin, UserRole.system_admin)
    if not (is_owner or is_assignee or is_admin):
        raise HTTPException(status_code=403, detail="Not authorized to update this ticket")

    update_data = body.model_dump(exclude_unset=True)
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
