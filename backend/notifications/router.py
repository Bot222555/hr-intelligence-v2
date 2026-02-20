"""Notification endpoints — list, mark read, unread count."""


import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth.dependencies import get_current_user
from backend.common.constants import NotificationType
from backend.common.pagination import PaginationParams
from backend.core_hr.models import Employee
from backend.database import get_db
from backend.notifications.schemas import (
    NotificationListResponse,
    NotificationResponse,
)
from backend.notifications.service import NotificationService

router = APIRouter(prefix="", tags=["notifications"])


# ── GET / — list current user's notifications ───────────────────────

@router.get("", response_model=NotificationListResponse)
async def list_notifications(
    is_read: Optional[bool] = Query(default=None, description="Filter by read status"),
    type: Optional[NotificationType] = Query(
        default=None, alias="type", description="Filter by notification type"
    ),
    pagination: PaginationParams = Depends(),
    employee: Employee = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List notifications for the authenticated user (paginated)."""
    return await NotificationService.get_notifications(
        db,
        employee_id=employee.id,
        pagination=pagination,
        is_read=is_read,
        notification_type=type,
    )


# ── GET /unread-count — badge count ─────────────────────────────────
# NOTE: This route MUST be registered before /{notification_id}/read
# to avoid FastAPI treating "unread-count" as a UUID path parameter.

@router.get("/unread-count")
async def unread_count(
    employee: Employee = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return the number of unread notifications (for header badge)."""
    count = await NotificationService.get_unread_count(db, employee.id)
    return {"data": {"count": count}}


# ── PUT /read-all — bulk mark all as read ───────────────────────────
# NOTE: This route MUST be registered before /{notification_id}/read.

@router.put("/read-all")
async def mark_all_read(
    employee: Employee = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark all unread notifications as read for the authenticated user."""
    count = await NotificationService.mark_all_read(db, employee.id)
    return {"message": "All notifications marked as read", "data": {"count": count}}


# ── PUT /{notification_id}/read — mark single as read ───────────────

@router.put("/{notification_id}/read")
async def mark_read(
    notification_id: uuid.UUID,
    employee: Employee = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark a single notification as read."""
    notification = await NotificationService.mark_read(db, notification_id, employee.id)
    return {
        "message": "Notification marked as read",
        "data": NotificationResponse.model_validate(notification),
    }
