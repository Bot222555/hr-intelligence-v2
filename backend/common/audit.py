"""Audit trail mixin, model, and async helper for recording entity changes."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


# ── Mixin for any auditable model ───────────────────────────────────

class AuditMixin:
    """
    Add ``created_at``, ``updated_at``, ``created_by``, ``updated_by``
    to any SQLAlchemy model via::

        class Employee(Base, AuditMixin):
            ...
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employees.id"),
        nullable=True,
    )
    updated_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employees.id"),
        nullable=True,
    )


# ── Immutable audit-trail table ─────────────────────────────────────

class AuditTrail(Base):
    """Immutable log of every significant data change."""

    __tablename__ = "audit_trail"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    actor_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employees.id"),
        nullable=True,
    )
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False,
    )
    old_values = Column(JSONB, nullable=True)
    new_values = Column(JSONB, nullable=True)
    ip_address = Column(INET, nullable=True)
    user_agent = Column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
    )

    __table_args__ = (
        Index("ix_audit_trail_actor_id", "actor_id"),
        Index("ix_audit_trail_entity", "entity_type", "entity_id"),
        Index("ix_audit_trail_created_at", "created_at"),
        Index("ix_audit_trail_action", "action"),
    )

    def __repr__(self) -> str:
        return (
            f"<AuditTrail {self.action} {self.entity_type}"
            f"/{self.entity_id} by {self.actor_id}>"
        )


# ── Helper to create an entry ───────────────────────────────────────

async def create_audit_entry(
    session: AsyncSession,
    *,
    action: str,
    entity_type: str,
    entity_id: uuid.UUID,
    actor_id: Optional[uuid.UUID] = None,
    old_values: Optional[dict[str, Any]] = None,
    new_values: Optional[dict[str, Any]] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> AuditTrail:
    """
    Create and flush an audit-trail entry.

    Args:
        session: Async SQLAlchemy session.
        action: create | update | delete | approve | reject | etc.
        entity_type: e.g. "employee", "leave_request".
        entity_id: UUID of the affected entity.
        actor_id: UUID of the user performing the action.
        old_values: Previous state (for updates/deletes).
        new_values: New state (for creates/updates).
        ip_address: Client IP.
        user_agent: Client user-agent string.
    """
    entry = AuditTrail(
        actor_id=actor_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        old_values=old_values,
        new_values=new_values,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    session.add(entry)
    await session.flush()
    return entry
