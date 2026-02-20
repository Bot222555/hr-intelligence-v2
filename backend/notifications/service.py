"""Notification service — CRUD operations and cross-module helper dispatchers."""

from __future__ import annotations

import math
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.common.constants import NotificationType
from backend.common.exceptions import ForbiddenException, NotFoundException
from backend.common.pagination import PaginationParams
from backend.notifications.models import Notification
from backend.notifications.schemas import (
    NotificationListMeta,
    NotificationListResponse,
    NotificationResponse,
)


# ── Core service ────────────────────────────────────────────────────


class NotificationService:
    """Async notification operations."""

    @staticmethod
    async def create_notification(
        db: AsyncSession,
        *,
        recipient_id: uuid.UUID,
        type: NotificationType = NotificationType.info,
        title: str,
        message: str,
        action_url: Optional[str] = None,
        entity_type: Optional[str] = None,
        entity_id: Optional[uuid.UUID] = None,
    ) -> Notification:
        """Create a new notification and flush to DB."""
        notification = Notification(
            recipient_id=recipient_id,
            type=type,
            title=title,
            message=message,
            action_url=action_url,
            entity_type=entity_type,
            entity_id=entity_id,
        )
        db.add(notification)
        await db.flush()
        return notification

    @staticmethod
    async def get_notifications(
        db: AsyncSession,
        employee_id: uuid.UUID,
        pagination: PaginationParams,
        *,
        is_read: Optional[bool] = None,
        notification_type: Optional[NotificationType] = None,
    ) -> NotificationListResponse:
        """Return paginated notifications for an employee, newest first."""
        query = (
            select(Notification)
            .where(Notification.recipient_id == employee_id)
            .order_by(Notification.created_at.desc())
        )

        if is_read is not None:
            query = query.where(Notification.is_read == is_read)
        if notification_type is not None:
            query = query.where(Notification.type == notification_type)

        # Total count (with filters applied)
        count_q = query.with_only_columns(func.count()).order_by(None)
        total: int = (await db.execute(count_q)).scalar_one()

        # Paginated rows
        rows = (
            await db.execute(
                query.offset(pagination.offset).limit(pagination.page_size)
            )
        ).scalars().all()

        total_pages = math.ceil(total / pagination.page_size) if total else 0

        # Unread count (always unfiltered — for the badge)
        unread = await NotificationService.get_unread_count(db, employee_id)

        return NotificationListResponse(
            data=[NotificationResponse.model_validate(n) for n in rows],
            meta=NotificationListMeta(
                page=pagination.page,
                page_size=pagination.page_size,
                total=total,
                total_pages=total_pages,
                has_next=pagination.page < total_pages,
                has_prev=pagination.page > 1,
                unread=unread,
            ),
        )

    @staticmethod
    async def mark_read(
        db: AsyncSession,
        notification_id: uuid.UUID,
        employee_id: uuid.UUID,
    ) -> Notification:
        """Mark a single notification as read. Verifies ownership."""
        result = await db.execute(
            select(Notification).where(Notification.id == notification_id)
        )
        notification = result.scalars().first()

        if notification is None:
            raise NotFoundException("Notification", notification_id)

        if notification.recipient_id != employee_id:
            raise ForbiddenException("You can only mark your own notifications as read.")

        notification.is_read = True
        notification.read_at = datetime.now(timezone.utc)
        await db.flush()
        return notification

    @staticmethod
    async def mark_all_read(
        db: AsyncSession,
        employee_id: uuid.UUID,
    ) -> int:
        """Bulk-mark all unread notifications as read. Returns count updated."""
        now = datetime.now(timezone.utc)
        result = await db.execute(
            update(Notification)
            .where(
                Notification.recipient_id == employee_id,
                Notification.is_read.is_(False),
            )
            .values(is_read=True, read_at=now)
        )
        await db.flush()
        return result.rowcount  # type: ignore[return-value]

    @staticmethod
    async def get_unread_count(
        db: AsyncSession,
        employee_id: uuid.UUID,
    ) -> int:
        """Return the number of unread notifications for an employee."""
        result = await db.execute(
            select(func.count())
            .select_from(Notification)
            .where(
                Notification.recipient_id == employee_id,
                Notification.is_read.is_(False),
            )
        )
        return result.scalar_one()


# ── Cross-module helper dispatchers ─────────────────────────────────
# These are designed to be imported by leave / attendance services.
# They accept the ORM object directly to avoid tight schema coupling.


async def notify_leave_request(
    db: AsyncSession,
    leave_request,  # backend.leave.models.LeaveRequest
    approver_id: uuid.UUID,
) -> Notification:
    """Notify the approver that a new leave request needs review."""
    return await NotificationService.create_notification(
        db,
        recipient_id=approver_id,
        type=NotificationType.action_required,
        title="New Leave Request",
        message=(
            f"A leave request from {leave_request.start_date} to "
            f"{leave_request.end_date} ({leave_request.total_days} day(s)) "
            f"requires your approval."
        ),
        action_url=f"/leave/requests/{leave_request.id}",
        entity_type="leave_request",
        entity_id=leave_request.id,
    )


async def notify_leave_approved(
    db: AsyncSession,
    leave_request,  # backend.leave.models.LeaveRequest
) -> Notification:
    """Notify the employee that their leave request was approved."""
    return await NotificationService.create_notification(
        db,
        recipient_id=leave_request.employee_id,
        type=NotificationType.approval,
        title="Leave Request Approved",
        message=(
            f"Your leave request from {leave_request.start_date} to "
            f"{leave_request.end_date} has been approved."
        ),
        action_url=f"/leave/requests/{leave_request.id}",
        entity_type="leave_request",
        entity_id=leave_request.id,
    )


async def notify_leave_rejected(
    db: AsyncSession,
    leave_request,  # backend.leave.models.LeaveRequest
    reason: str,
) -> Notification:
    """Notify the employee that their leave request was rejected."""
    return await NotificationService.create_notification(
        db,
        recipient_id=leave_request.employee_id,
        type=NotificationType.alert,
        title="Leave Request Rejected",
        message=(
            f"Your leave request from {leave_request.start_date} to "
            f"{leave_request.end_date} was rejected. Reason: {reason}"
        ),
        action_url=f"/leave/requests/{leave_request.id}",
        entity_type="leave_request",
        entity_id=leave_request.id,
    )


async def notify_regularization_request(
    db: AsyncSession,
    regularization,  # backend.attendance.models.AttendanceRegularization
    approver_id: uuid.UUID,
) -> Notification:
    """Notify the approver that an attendance regularization needs review."""
    return await NotificationService.create_notification(
        db,
        recipient_id=approver_id,
        type=NotificationType.action_required,
        title="Attendance Regularization Request",
        message=(
            f"An attendance regularization request has been submitted "
            f"and requires your approval."
        ),
        action_url=f"/attendance/regularizations/{regularization.id}",
        entity_type="attendance_regularization",
        entity_id=regularization.id,
    )


async def notify_regularization_approved(
    db: AsyncSession,
    regularization,  # backend.attendance.models.AttendanceRegularization
) -> Notification:
    """Notify the employee that their regularization was approved."""
    return await NotificationService.create_notification(
        db,
        recipient_id=regularization.employee_id,
        type=NotificationType.approval,
        title="Regularization Approved",
        message="Your attendance regularization request has been approved.",
        action_url=f"/attendance/regularizations/{regularization.id}",
        entity_type="attendance_regularization",
        entity_id=regularization.id,
    )


async def notify_regularization_rejected(
    db: AsyncSession,
    regularization,  # backend.attendance.models.AttendanceRegularization
    reason: str,
) -> Notification:
    """Notify the employee that their regularization was rejected."""
    return await NotificationService.create_notification(
        db,
        recipient_id=regularization.employee_id,
        type=NotificationType.alert,
        title="Regularization Rejected",
        message=(
            f"Your attendance regularization request was rejected. "
            f"Reason: {reason}"
        ),
        action_url=f"/attendance/regularizations/{regularization.id}",
        entity_type="attendance_regularization",
        entity_id=regularization.id,
    )
