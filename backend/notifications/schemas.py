"""Notification Pydantic schemas for request / response validation."""


import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from backend.common.constants import NotificationType
from backend.common.pagination import PaginationMeta


# ── Internal (used by service, not exposed via API) ─────────────────

class NotificationCreate(BaseModel):
    """Used internally to create notifications from other modules."""

    recipient_id: uuid.UUID
    type: NotificationType = NotificationType.info
    title: str
    message: str
    action_url: Optional[str] = None
    entity_type: Optional[str] = None
    entity_id: Optional[uuid.UUID] = None


# ── Responses ───────────────────────────────────────────────────────

class NotificationResponse(BaseModel):
    """Single notification in API responses."""

    id: uuid.UUID
    type: NotificationType
    title: str
    message: str
    action_url: Optional[str] = None
    entity_type: Optional[str] = None
    entity_id: Optional[uuid.UUID] = None
    is_read: bool
    read_at: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class NotificationListMeta(PaginationMeta):
    """Extends standard pagination meta with unread count."""

    unread: int


class NotificationListResponse(BaseModel):
    """Paginated list of notifications with unread count in meta."""

    data: list[NotificationResponse]
    meta: NotificationListMeta
