"""Auth ORM models: UserSession, RoleAssignment."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.common.constants import UserRole
from backend.database import Base


class UserSession(Base):
    __tablename__ = "user_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False,
    )
    token_hash: Mapped[str] = mapped_column(sa.String(512), nullable=False)
    ip_address: Mapped[Optional[str]] = mapped_column(INET)
    user_agent: Mapped[Optional[str]] = mapped_column(sa.Text)
    device_info: Mapped[Optional[dict]] = mapped_column(JSONB)
    expires_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False
    )
    is_revoked: Mapped[bool] = mapped_column(
        sa.Boolean, server_default=sa.text("FALSE")
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )

    # Relationships
    employee: Mapped["backend.core_hr.models.Employee"] = relationship(
        back_populates="sessions"
    )


class RoleAssignment(Base):
    __tablename__ = "role_assignments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[UserRole] = mapped_column(
        sa.Enum(UserRole, name="user_role", create_type=False), nullable=False
    )
    assigned_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("employees.id")
    )
    assigned_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
    revoked_at: Mapped[Optional[datetime]] = mapped_column(
        sa.DateTime(timezone=True)
    )
    is_active: Mapped[bool] = mapped_column(
        sa.Boolean, server_default=sa.text("TRUE")
    )

    # Relationships
    employee: Mapped["backend.core_hr.models.Employee"] = relationship(
        back_populates="role_assignments", foreign_keys=[employee_id]
    )
    assigner: Mapped[Optional["backend.core_hr.models.Employee"]] = relationship(
        foreign_keys=[assigned_by]
    )
