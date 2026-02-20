"""Notifications ORM model — matches the notifications table from TASK-02 migration."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.common.constants import NotificationType
from backend.database import Base


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    recipient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False,
    )
    type: Mapped[NotificationType] = mapped_column(
        sa.Enum(NotificationType, name="notification_type", create_type=False),
        default="info",
    )
    title: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    message: Mapped[str] = mapped_column(sa.Text, nullable=False)
    action_url: Mapped[Optional[str]] = mapped_column(sa.String(500))
    entity_type: Mapped[Optional[str]] = mapped_column(sa.String(50))
    entity_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True))
    is_read: Mapped[bool] = mapped_column(
        sa.Boolean, default=False,
    )
    read_at: Mapped[Optional[datetime]] = mapped_column(sa.DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    recipient: Mapped["backend.core_hr.models.Employee"] = relationship(
        back_populates="notifications",
    )
