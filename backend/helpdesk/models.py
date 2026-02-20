"""Helpdesk ORM models: HelpdeskTicket, HelpdeskResponse.

SQLAlchemy 2.0 async-compatible models.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base


class HelpdeskTicket(Base):
    """Helpdesk support ticket."""

    __tablename__ = "helpdesk_tickets"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    keka_id: Mapped[Optional[str]] = mapped_column(
        sa.String(200), unique=True, nullable=True,
    )
    ticket_number: Mapped[Optional[str]] = mapped_column(sa.String(50))
    title: Mapped[str] = mapped_column(sa.String(500), nullable=False)
    category: Mapped[Optional[str]] = mapped_column(sa.String(200))
    status: Mapped[str] = mapped_column(
        sa.String(50), nullable=False, default="open",
    )
    priority: Mapped[str] = mapped_column(
        sa.String(20), nullable=False, default="medium",
    )
    raised_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("employees.id"), nullable=True,
    )
    raised_by_name: Mapped[Optional[str]] = mapped_column(sa.String(200))
    assigned_to_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("employees.id"), nullable=True,
    )
    assigned_to_name: Mapped[Optional[str]] = mapped_column(sa.String(200))
    requested_on: Mapped[Optional[datetime]] = mapped_column(
        sa.DateTime(timezone=True),
    )
    resolved_at: Mapped[Optional[datetime]] = mapped_column(
        sa.DateTime(timezone=True),
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    raised_by = relationship("Employee", foreign_keys=[raised_by_id], lazy="joined")
    assigned_to = relationship("Employee", foreign_keys=[assigned_to_id], lazy="joined")
    responses: Mapped[list[HelpdeskResponse]] = relationship(
        back_populates="ticket", cascade="all, delete-orphan",
        order_by="HelpdeskResponse.created_at",
    )

    def __repr__(self) -> str:
        return f"<HelpdeskTicket #{self.ticket_number} '{self.title[:30]}'>"


class HelpdeskResponse(Base):
    """Response/comment on a helpdesk ticket."""

    __tablename__ = "helpdesk_responses"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    ticket_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("helpdesk_tickets.id", ondelete="CASCADE"),
        nullable=False,
    )
    author_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("employees.id"), nullable=True,
    )
    author_name: Mapped[Optional[str]] = mapped_column(sa.String(200))
    body: Mapped[str] = mapped_column(sa.Text, nullable=False)
    is_internal: Mapped[bool] = mapped_column(sa.Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    ticket: Mapped[HelpdeskTicket] = relationship(back_populates="responses")
    author = relationship("Employee", foreign_keys=[author_id], lazy="joined")

    def __repr__(self) -> str:
        return f"<HelpdeskResponse ticket={self.ticket_id}>"
