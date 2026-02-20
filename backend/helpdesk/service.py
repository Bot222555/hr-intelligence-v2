"""Helpdesk service layer — CRUD for tickets and responses."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.common.exceptions import ForbiddenException, NotFoundException
from backend.helpdesk.models import HelpdeskResponse, HelpdeskTicket


class HelpdeskService:
    """Business logic for helpdesk operations."""

    # ── Tickets ───────────────────────────────────────────────────────

    @staticmethod
    async def create_ticket(
        db: AsyncSession,
        employee_id: uuid.UUID,
        employee_name: str,
        title: str,
        category: Optional[str] = None,
        priority: str = "medium",
    ) -> HelpdeskTicket:
        """Create a new helpdesk ticket."""
        # Generate ticket number
        count_stmt = select(func.count()).select_from(HelpdeskTicket)
        total = (await db.execute(count_stmt)).scalar() or 0
        ticket_number = f"HD-{total + 1:05d}"

        ticket = HelpdeskTicket(
            ticket_number=ticket_number,
            title=title,
            category=category,
            status="open",
            priority=priority,
            raised_by_id=employee_id,
            raised_by_name=employee_name,
            requested_on=datetime.now(timezone.utc),
        )
        db.add(ticket)
        await db.flush()
        await db.refresh(ticket, ["responses"])
        return ticket

    @staticmethod
    async def get_ticket(
        db: AsyncSession,
        ticket_id: uuid.UUID,
    ) -> HelpdeskTicket:
        """Get a ticket by ID with responses."""
        stmt = (
            select(HelpdeskTicket)
            .options(selectinload(HelpdeskTicket.responses))
            .where(HelpdeskTicket.id == ticket_id)
        )
        result = await db.execute(stmt)
        ticket = result.scalar_one_or_none()
        if not ticket:
            raise NotFoundException(f"Ticket {ticket_id} not found")
        return ticket

    @staticmethod
    async def list_tickets(
        db: AsyncSession,
        status: Optional[str] = None,
        priority: Optional[str] = None,
        raised_by_id: Optional[uuid.UUID] = None,
        assigned_to_id: Optional[uuid.UUID] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[HelpdeskTicket], int]:
        """List tickets with optional filters."""
        stmt = select(HelpdeskTicket).options(
            selectinload(HelpdeskTicket.responses)
        )
        count_stmt = select(func.count()).select_from(HelpdeskTicket)

        if status:
            stmt = stmt.where(HelpdeskTicket.status == status)
            count_stmt = count_stmt.where(HelpdeskTicket.status == status)
        if priority:
            stmt = stmt.where(HelpdeskTicket.priority == priority)
            count_stmt = count_stmt.where(HelpdeskTicket.priority == priority)
        if raised_by_id:
            stmt = stmt.where(HelpdeskTicket.raised_by_id == raised_by_id)
            count_stmt = count_stmt.where(HelpdeskTicket.raised_by_id == raised_by_id)
        if assigned_to_id:
            stmt = stmt.where(HelpdeskTicket.assigned_to_id == assigned_to_id)
            count_stmt = count_stmt.where(HelpdeskTicket.assigned_to_id == assigned_to_id)

        total = (await db.execute(count_stmt)).scalar() or 0

        stmt = (
            stmt.order_by(HelpdeskTicket.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await db.execute(stmt)
        return list(result.scalars().unique().all()), total

    @staticmethod
    async def update_ticket(
        db: AsyncSession,
        ticket_id: uuid.UUID,
        **kwargs,
    ) -> HelpdeskTicket:
        """Update a ticket's fields."""
        ticket = await HelpdeskService.get_ticket(db, ticket_id)

        for field, value in kwargs.items():
            if value is not None and hasattr(ticket, field):
                setattr(ticket, field, value)

        ticket.updated_at = datetime.now(timezone.utc)

        if kwargs.get("status") == "resolved" and not ticket.resolved_at:
            ticket.resolved_at = datetime.now(timezone.utc)

        await db.flush()
        await db.refresh(ticket, ["responses"])
        return ticket

    @staticmethod
    async def delete_ticket(
        db: AsyncSession,
        ticket_id: uuid.UUID,
    ) -> None:
        """Delete a ticket."""
        ticket = await HelpdeskService.get_ticket(db, ticket_id)
        await db.delete(ticket)

    # ── Responses ─────────────────────────────────────────────────────

    @staticmethod
    async def add_response(
        db: AsyncSession,
        ticket_id: uuid.UUID,
        author_id: uuid.UUID,
        author_name: str,
        body: str,
        is_internal: bool = False,
    ) -> HelpdeskResponse:
        """Add a response to a ticket."""
        # Verify ticket exists
        await HelpdeskService.get_ticket(db, ticket_id)

        response = HelpdeskResponse(
            ticket_id=ticket_id,
            author_id=author_id,
            author_name=author_name,
            body=body,
            is_internal=is_internal,
        )
        db.add(response)
        await db.flush()
        return response

    @staticmethod
    async def list_responses(
        db: AsyncSession,
        ticket_id: uuid.UUID,
    ) -> list[HelpdeskResponse]:
        """List all responses for a ticket."""
        stmt = (
            select(HelpdeskResponse)
            .where(HelpdeskResponse.ticket_id == ticket_id)
            .order_by(HelpdeskResponse.created_at)
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())
