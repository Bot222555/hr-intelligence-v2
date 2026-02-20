"""Notification module test suite — create, mark read, bulk mark, pagination,
filtering by type, and auto-creation from leave/attendance events.

Uses the shared conftest.py pattern with in-memory SQLite.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.common.constants import NotificationType
from backend.core_hr.models import Employee
from backend.notifications.models import Notification
from backend.notifications.service import NotificationService
from tests.conftest import (
    TestSessionFactory,
    _make_employee,
    _make_department,
    _make_location,
)


# ── Helpers ─────────────────────────────────────────────────────────


async def _seed_employee(db: AsyncSession, **kwargs) -> Employee:
    from backend.core_hr.models import Location, Department

    # Generate unique location name to avoid UNIQUE constraint
    unique_suffix = uuid.uuid4().hex[:8]
    loc_name = kwargs.pop("loc_name", f"Office-{unique_suffix}")
    loc_city = kwargs.pop("city", "Mumbai")
    loc_data = _make_location(name=loc_name, city=loc_city)
    loc = Location(**loc_data)
    db.add(loc)
    await db.flush()

    dept_data = _make_department(location_id=loc.id, name=f"Dept-{unique_suffix}", code=f"D{unique_suffix[:4].upper()}")
    dept = Department(**dept_data)
    db.add(dept)
    await db.flush()

    emp_data = _make_employee(
        department_id=dept.id,
        location_id=loc.id,
        **{k: v for k, v in kwargs.items() if k in ("email", "first_name", "last_name")},
    )
    emp = Employee(**emp_data)
    db.add(emp)
    await db.flush()
    return emp


async def _create_notification(
    db: AsyncSession,
    recipient_id: uuid.UUID,
    *,
    type: NotificationType = NotificationType.info,
    title: str = "Test Notification",
    message: str = "Test message body",
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
) -> Notification:
    """Create a notification directly via the service."""
    return await NotificationService.create_notification(
        db,
        recipient_id=recipient_id,
        type=type,
        title=title,
        message=message,
        entity_type=entity_type,
        entity_id=entity_id,
    )


# ═════════════════════════════════════════════════════════════════════
# 1. NOTIFICATION CREATION
# ═════════════════════════════════════════════════════════════════════


class TestNotificationCreate:
    """Tests for creating notifications."""

    async def test_create_basic_notification(self, db: AsyncSession):
        """Create a simple info notification."""
        emp = await _seed_employee(db, email="n1@creativefuel.io", first_name="NotifUser")

        notif = await _create_notification(db, emp.id)

        assert notif.id is not None
        assert notif.recipient_id == emp.id
        assert notif.type == NotificationType.info
        assert notif.title == "Test Notification"
        assert notif.message == "Test message body"
        assert notif.is_read is False

    async def test_create_action_required_notification(self, db: AsyncSession):
        """Create an action_required notification with entity reference."""
        emp = await _seed_employee(db, email="n2@creativefuel.io", first_name="ActionUser")
        entity_id = uuid.uuid4()

        notif = await _create_notification(
            db, emp.id,
            type=NotificationType.action_required,
            title="Leave Approval Needed",
            message="A team member has requested leave",
            entity_type="leave_request",
            entity_id=entity_id,
        )

        assert notif.type == NotificationType.action_required
        assert notif.entity_type == "leave_request"
        assert notif.entity_id == entity_id

    async def test_create_approval_notification(self, db: AsyncSession):
        """Create an approval notification."""
        emp = await _seed_employee(db, email="n3@creativefuel.io", first_name="ApprovalUser")

        notif = await _create_notification(
            db, emp.id,
            type=NotificationType.approval,
            title="Leave Approved",
            message="Your leave has been approved",
        )

        assert notif.type == NotificationType.approval

    async def test_create_multiple_notifications_for_user(self, db: AsyncSession):
        """Create multiple notifications for the same user."""
        emp = await _seed_employee(db, email="n4@creativefuel.io", first_name="MultiUser")

        for i in range(5):
            await _create_notification(
                db, emp.id,
                title=f"Notification {i}",
                message=f"Message {i}",
            )

        result = await db.execute(
            select(func.count()).select_from(Notification).where(
                Notification.recipient_id == emp.id
            )
        )
        assert result.scalar_one() == 5


# ═════════════════════════════════════════════════════════════════════
# 2. MARK READ
# ═════════════════════════════════════════════════════════════════════


class TestNotificationMarkRead:
    """Tests for marking notifications as read."""

    async def test_mark_single_notification_read(self, db: AsyncSession):
        """Mark a single notification as read."""
        emp = await _seed_employee(db, email="r1@creativefuel.io", first_name="ReadUser")
        notif = await _create_notification(db, emp.id)

        assert notif.is_read is False

        # Mark as read
        notif.is_read = True
        notif.read_at = datetime.now(timezone.utc)
        await db.flush()

        await db.refresh(notif)
        assert notif.is_read is True
        assert notif.read_at is not None

    async def test_mark_already_read_notification(self, db: AsyncSession):
        """Marking an already-read notification is idempotent."""
        emp = await _seed_employee(db, email="r2@creativefuel.io", first_name="RereadUser")
        notif = await _create_notification(db, emp.id)

        # Mark read twice
        notif.is_read = True
        notif.read_at = datetime.now(timezone.utc)
        await db.flush()

        first_read_at = notif.read_at

        notif.is_read = True
        await db.flush()

        assert notif.is_read is True
        assert notif.read_at == first_read_at  # Unchanged


# ═════════════════════════════════════════════════════════════════════
# 3. BULK MARK READ
# ═════════════════════════════════════════════════════════════════════


class TestNotificationBulkMark:
    """Tests for bulk marking notifications as read."""

    async def test_bulk_mark_all_as_read(self, db: AsyncSession):
        """Mark all notifications for a user as read."""
        emp = await _seed_employee(db, email="b1@creativefuel.io", first_name="BulkUser")

        for i in range(5):
            await _create_notification(db, emp.id, title=f"Bulk {i}")

        # Bulk update
        from sqlalchemy import update

        await db.execute(
            update(Notification)
            .where(
                Notification.recipient_id == emp.id,
                Notification.is_read.is_(False),
            )
            .values(is_read=True, read_at=datetime.now(timezone.utc))
        )
        await db.flush()

        result = await db.execute(
            select(func.count()).select_from(Notification).where(
                Notification.recipient_id == emp.id,
                Notification.is_read.is_(False),
            )
        )
        assert result.scalar_one() == 0

    async def test_bulk_mark_does_not_affect_other_users(self, db: AsyncSession):
        """Bulk marking for user A doesn't affect user B's notifications."""
        emp_a = await _seed_employee(db, email="ba@creativefuel.io", first_name="UserA")
        emp_b = await _seed_employee(db, email="bb@creativefuel.io", first_name="UserB")

        await _create_notification(db, emp_a.id, title="A's notification")
        await _create_notification(db, emp_b.id, title="B's notification")

        # Mark A's as read
        from sqlalchemy import update

        await db.execute(
            update(Notification)
            .where(Notification.recipient_id == emp_a.id)
            .values(is_read=True)
        )
        await db.flush()

        # B's should still be unread
        result = await db.execute(
            select(Notification).where(
                Notification.recipient_id == emp_b.id,
            )
        )
        b_notif = result.scalars().first()
        assert b_notif.is_read is False


# ═════════════════════════════════════════════════════════════════════
# 4. PAGINATION & FILTERING
# ═════════════════════════════════════════════════════════════════════


class TestNotificationPagination:
    """Tests for notification list pagination and filtering."""

    async def test_paginate_notifications(self, db: AsyncSession):
        """Paginate notifications with limit/offset."""
        emp = await _seed_employee(db, email="p1@creativefuel.io", first_name="PageUser")

        for i in range(12):
            await _create_notification(db, emp.id, title=f"Page {i}")

        result = await db.execute(
            select(Notification)
            .where(Notification.recipient_id == emp.id)
            .order_by(Notification.created_at.desc())
            .limit(5)
        )
        page1 = result.scalars().all()
        assert len(page1) == 5

        result2 = await db.execute(
            select(Notification)
            .where(Notification.recipient_id == emp.id)
            .order_by(Notification.created_at.desc())
            .limit(5)
            .offset(10)
        )
        page3 = result2.scalars().all()
        assert len(page3) == 2  # 12 total, offset 10 → 2 remaining

    async def test_filter_unread_notifications(self, db: AsyncSession):
        """Filter to only unread notifications."""
        emp = await _seed_employee(db, email="f1@creativefuel.io", first_name="FilterUser")

        n1 = await _create_notification(db, emp.id, title="Unread 1")
        n2 = await _create_notification(db, emp.id, title="Read 1")
        n3 = await _create_notification(db, emp.id, title="Unread 2")

        # Mark n2 as read
        n2.is_read = True
        await db.flush()

        result = await db.execute(
            select(Notification).where(
                Notification.recipient_id == emp.id,
                Notification.is_read.is_(False),
            )
        )
        unread = result.scalars().all()
        assert len(unread) == 2

    async def test_filter_by_notification_type(self, db: AsyncSession):
        """Filter notifications by type."""
        emp = await _seed_employee(db, email="ft@creativefuel.io", first_name="TypeFilter")

        await _create_notification(db, emp.id, type=NotificationType.info, title="Info")
        await _create_notification(db, emp.id, type=NotificationType.approval, title="Approval")
        await _create_notification(db, emp.id, type=NotificationType.action_required, title="Action")

        result = await db.execute(
            select(Notification).where(
                Notification.recipient_id == emp.id,
                Notification.type == NotificationType.info,
            )
        )
        info_only = result.scalars().all()
        assert len(info_only) == 1
        assert info_only[0].title == "Info"

    async def test_count_unread_notifications(self, db: AsyncSession):
        """Count unread notifications for badge display."""
        emp = await _seed_employee(db, email="cnt@creativefuel.io", first_name="CountUser")

        for i in range(7):
            await _create_notification(db, emp.id, title=f"N{i}")

        # Mark 3 as read
        result = await db.execute(
            select(Notification)
            .where(Notification.recipient_id == emp.id)
            .limit(3)
        )
        for n in result.scalars().all():
            n.is_read = True
        await db.flush()

        count_result = await db.execute(
            select(func.count()).select_from(Notification).where(
                Notification.recipient_id == emp.id,
                Notification.is_read.is_(False),
            )
        )
        assert count_result.scalar_one() == 4


# ═════════════════════════════════════════════════════════════════════
# 5. SERVICE METHOD TESTS — get_notifications, mark_read, mark_all_read,
#    get_unread_count, and cross-module notification dispatchers
# ═════════════════════════════════════════════════════════════════════


class TestNotificationServiceMethods:
    """Tests that exercise NotificationService methods directly for coverage."""

    async def test_get_notifications_paginated(self, db: AsyncSession):
        """NotificationService.get_notifications returns paginated response."""
        from backend.common.pagination import PaginationParams

        emp = await _seed_employee(db, email="svc1@creativefuel.io", first_name="SvcUser")

        for i in range(8):
            await _create_notification(db, emp.id, title=f"Svc Notif {i}")

        result = await NotificationService.get_notifications(
            db, emp.id, PaginationParams(page=1, page_size=5),
        )
        assert len(result.data) == 5
        assert result.meta.total == 8
        assert result.meta.has_next is True
        assert result.meta.unread == 8

    async def test_get_notifications_filter_unread(self, db: AsyncSession):
        """get_notifications with is_read=False filters correctly."""
        from backend.common.pagination import PaginationParams

        emp = await _seed_employee(db, email="svc2@creativefuel.io", first_name="FilterSvc")

        n1 = await _create_notification(db, emp.id, title="Unread")
        n2 = await _create_notification(db, emp.id, title="Read")
        n2.is_read = True
        await db.flush()

        result = await NotificationService.get_notifications(
            db, emp.id, PaginationParams(page=1, page_size=50),
            is_read=False,
        )
        assert result.meta.total == 1
        assert result.data[0].title == "Unread"

    async def test_get_notifications_filter_by_type(self, db: AsyncSession):
        """get_notifications with notification_type filters correctly."""
        from backend.common.pagination import PaginationParams

        emp = await _seed_employee(db, email="svc3@creativefuel.io", first_name="TypeSvc")

        await _create_notification(db, emp.id, type=NotificationType.info, title="Info")
        await _create_notification(db, emp.id, type=NotificationType.approval, title="Approved")

        result = await NotificationService.get_notifications(
            db, emp.id, PaginationParams(page=1, page_size=50),
            notification_type=NotificationType.approval,
        )
        assert result.meta.total == 1
        assert result.data[0].title == "Approved"

    async def test_service_mark_read(self, db: AsyncSession):
        """NotificationService.mark_read marks a notification as read."""
        emp = await _seed_employee(db, email="svc4@creativefuel.io", first_name="MarkSvc")
        notif = await _create_notification(db, emp.id, title="ToMark")

        updated = await NotificationService.mark_read(db, notif.id, emp.id)
        assert updated.is_read is True
        assert updated.read_at is not None

    async def test_service_mark_read_not_found(self, db: AsyncSession):
        """mark_read raises NotFoundException for non-existent notification."""
        from backend.common.exceptions import NotFoundException

        emp = await _seed_employee(db, email="svc5@creativefuel.io", first_name="NotFound")
        with pytest.raises(NotFoundException):
            await NotificationService.mark_read(db, uuid.uuid4(), emp.id)

    async def test_service_mark_read_wrong_owner(self, db: AsyncSession):
        """mark_read raises ForbiddenException when not the recipient."""
        from backend.common.exceptions import ForbiddenException

        emp1 = await _seed_employee(db, email="svc6@creativefuel.io", first_name="Owner")
        emp2 = await _seed_employee(db, email="svc7@creativefuel.io", first_name="Other")
        notif = await _create_notification(db, emp1.id, title="Private")

        with pytest.raises(ForbiddenException):
            await NotificationService.mark_read(db, notif.id, emp2.id)

    async def test_service_mark_all_read(self, db: AsyncSession):
        """NotificationService.mark_all_read marks all unread as read."""
        emp = await _seed_employee(db, email="svc8@creativefuel.io", first_name="MarkAll")

        for i in range(5):
            await _create_notification(db, emp.id, title=f"Bulk {i}")

        count = await NotificationService.mark_all_read(db, emp.id)
        assert count == 5

        unread = await NotificationService.get_unread_count(db, emp.id)
        assert unread == 0

    async def test_service_get_unread_count(self, db: AsyncSession):
        """NotificationService.get_unread_count returns correct count."""
        emp = await _seed_employee(db, email="svc9@creativefuel.io", first_name="CountSvc")

        for i in range(4):
            await _create_notification(db, emp.id, title=f"N{i}")

        count = await NotificationService.get_unread_count(db, emp.id)
        assert count == 4


class TestNotificationDispatchers:
    """Tests for cross-module notification dispatcher functions."""

    async def test_notify_leave_request(self, db: AsyncSession):
        """notify_leave_request creates an action_required notification."""
        from backend.notifications.service import notify_leave_request
        from types import SimpleNamespace

        emp = await _seed_employee(db, email="disp1@creativefuel.io", first_name="Disp")
        approver = await _seed_employee(db, email="disp2@creativefuel.io", first_name="Approver")

        leave_req = SimpleNamespace(
            id=uuid.uuid4(),
            employee_id=emp.id,
            start_date="2026-03-01",
            end_date="2026-03-03",
            total_days=3,
        )

        notif = await notify_leave_request(db, leave_req, approver.id)
        assert notif.type == NotificationType.action_required
        assert notif.recipient_id == approver.id
        assert "Leave Request" in notif.title

    async def test_notify_leave_approved(self, db: AsyncSession):
        """notify_leave_approved creates an approval notification."""
        from backend.notifications.service import notify_leave_approved
        from types import SimpleNamespace

        emp = await _seed_employee(db, email="disp3@creativefuel.io", first_name="Employee")

        leave_req = SimpleNamespace(
            id=uuid.uuid4(),
            employee_id=emp.id,
            start_date="2026-03-01",
            end_date="2026-03-03",
        )

        notif = await notify_leave_approved(db, leave_req)
        assert notif.type == NotificationType.approval
        assert notif.recipient_id == emp.id

    async def test_notify_leave_rejected(self, db: AsyncSession):
        """notify_leave_rejected creates an alert notification."""
        from backend.notifications.service import notify_leave_rejected
        from types import SimpleNamespace

        emp = await _seed_employee(db, email="disp4@creativefuel.io", first_name="Rejected")

        leave_req = SimpleNamespace(
            id=uuid.uuid4(),
            employee_id=emp.id,
            start_date="2026-03-01",
            end_date="2026-03-03",
        )

        notif = await notify_leave_rejected(db, leave_req, "Budget constraints")
        assert notif.type == NotificationType.alert
        assert "rejected" in notif.title.lower()

    async def test_notify_regularization_request(self, db: AsyncSession):
        """notify_regularization_request creates an action_required notification."""
        from backend.notifications.service import notify_regularization_request
        from types import SimpleNamespace

        approver = await _seed_employee(db, email="disp5@creativefuel.io", first_name="RegApprover")

        reg = SimpleNamespace(
            id=uuid.uuid4(),
            employee_id=uuid.uuid4(),
        )

        notif = await notify_regularization_request(db, reg, approver.id)
        assert notif.type == NotificationType.action_required
        assert "Regularization" in notif.title

    async def test_notify_regularization_approved(self, db: AsyncSession):
        """notify_regularization_approved creates an approval notification."""
        from backend.notifications.service import notify_regularization_approved
        from types import SimpleNamespace

        emp = await _seed_employee(db, email="disp6@creativefuel.io", first_name="RegEmp")

        reg = SimpleNamespace(
            id=uuid.uuid4(),
            employee_id=emp.id,
        )

        notif = await notify_regularization_approved(db, reg)
        assert notif.type == NotificationType.approval

    async def test_notify_regularization_rejected(self, db: AsyncSession):
        """notify_regularization_rejected creates an alert notification."""
        from backend.notifications.service import notify_regularization_rejected
        from types import SimpleNamespace

        emp = await _seed_employee(db, email="disp7@creativefuel.io", first_name="RegRej")

        reg = SimpleNamespace(
            id=uuid.uuid4(),
            employee_id=emp.id,
        )

        notif = await notify_regularization_rejected(db, reg, "Invalid request")
        assert notif.type == NotificationType.alert
        assert "Rejected" in notif.title
