"""Notifications ORM model."""

from __future__ import annotations

import uuid
from datetime import datetime
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
        server_default=sa.text("uuid_generate_v4()"),
    )
    recipient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("employees.id"), nullable=False
    )
    type: Mapped[NotificationType] = mapped_column(
        sa.Enum(NotificationType, name="notification_type", create_type=False),
        server_default="info",
    )
    title: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    message: Mapped[Optional[str]] = mapped_column(sa.Text)
    link: Mapped[Optional[str]] = mapped_column(sa.String(500))
    is_read: Mapped[bool] = mapped_column(
        sa.Boolean, server_default=sa.text("FALSE")
    )
    read_at: Mapped[Optional[datetime]] = mapped_column(sa.DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("NOW()")
    )

    # Relationships
    recipient: Mapped["backend.core_hr.models.Employee"] = relationship(
        back_populates="notifications"
    )
