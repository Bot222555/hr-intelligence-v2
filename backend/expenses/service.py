"""Expenses service layer — CRUD + approval workflow for expense claims."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.common.audit import create_audit_entry
from backend.common.exceptions import (
    ForbiddenException,
    NotFoundException,
    ValidationException,
)
from backend.expenses.models import ExpenseClaim


class ExpenseService:
    """Business logic for expense claim operations."""

    # ── Create ────────────────────────────────────────────────────────

    @staticmethod
    async def create_claim(
        db: AsyncSession,
        employee_id: uuid.UUID,
        employee_name: str,
        title: str,
        amount: float,
        currency: str = "INR",
        expenses: list | None = None,
        remarks: str | None = None,
    ) -> ExpenseClaim:
        """Create a new expense claim."""
        # Generate claim number
        count_stmt = select(func.count()).select_from(ExpenseClaim)
        total = (await db.execute(count_stmt)).scalar() or 0
        claim_number = f"EXP-{total + 1:05d}"

        claim = ExpenseClaim(
            employee_id=employee_id,
            employee_name=employee_name,
            claim_number=claim_number,
            title=title,
            amount=amount,
            currency=currency,
            expenses=expenses or [],
            approval_status="submitted",
            submitted_date=date.today(),
            remarks=remarks,
        )
        db.add(claim)
        await db.flush()

        await create_audit_entry(
            db,
            action="create",
            entity_type="expense_claim",
            entity_id=claim.id,
            actor_id=employee_id,
            new_values={
                "claim_number": claim_number,
                "title": title,
                "amount": float(amount),
            },
        )

        return claim

    # ── Read ──────────────────────────────────────────────────────────

    @staticmethod
    async def get_claim(
        db: AsyncSession,
        claim_id: uuid.UUID,
    ) -> ExpenseClaim:
        """Get a single expense claim by ID."""
        stmt = select(ExpenseClaim).where(ExpenseClaim.id == claim_id)
        result = await db.execute(stmt)
        claim = result.scalar_one_or_none()
        if not claim:
            raise NotFoundException("ExpenseClaim", str(claim_id))
        return claim

    @staticmethod
    async def list_claims(
        db: AsyncSession,
        employee_id: Optional[uuid.UUID] = None,
        approval_status: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[ExpenseClaim], int]:
        """List expense claims with optional filters."""
        stmt = select(ExpenseClaim)
        count_stmt = select(func.count()).select_from(ExpenseClaim)

        if employee_id:
            stmt = stmt.where(ExpenseClaim.employee_id == employee_id)
            count_stmt = count_stmt.where(ExpenseClaim.employee_id == employee_id)
        if approval_status:
            stmt = stmt.where(ExpenseClaim.approval_status == approval_status)
            count_stmt = count_stmt.where(
                ExpenseClaim.approval_status == approval_status
            )

        total = (await db.execute(count_stmt)).scalar() or 0

        stmt = (
            stmt.order_by(ExpenseClaim.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await db.execute(stmt)
        return list(result.scalars().all()), total

    # ── Update ────────────────────────────────────────────────────────

    @staticmethod
    async def update_claim(
        db: AsyncSession,
        claim_id: uuid.UUID,
        actor_id: uuid.UUID,
        **kwargs,
    ) -> ExpenseClaim:
        """Update an expense claim's fields (only if still pending/submitted)."""
        claim = await ExpenseService.get_claim(db, claim_id)

        if claim.approval_status not in ("pending", "submitted", "draft"):
            raise ValidationException(
                {"status": [f"Cannot update a claim with status '{claim.approval_status}'."]}
            )

        # Only the owner can edit
        if claim.employee_id != actor_id:
            raise ForbiddenException("Only the claim owner can edit this expense.")

        old_values = {}
        for field, value in kwargs.items():
            if value is not None and hasattr(claim, field):
                old_values[field] = getattr(claim, field)
                setattr(claim, field, value)

        claim.updated_at = datetime.now(timezone.utc)
        await db.flush()

        await create_audit_entry(
            db,
            action="update",
            entity_type="expense_claim",
            entity_id=claim.id,
            actor_id=actor_id,
            old_values={k: str(v) for k, v in old_values.items()},
            new_values={k: str(v) for k, v in kwargs.items() if v is not None},
        )

        return claim

    # ── Approval flow ─────────────────────────────────────────────────

    @staticmethod
    async def approve_claim(
        db: AsyncSession,
        claim_id: uuid.UUID,
        approver_id: uuid.UUID,
        remarks: str | None = None,
    ) -> ExpenseClaim:
        """Approve an expense claim."""
        claim = await ExpenseService.get_claim(db, claim_id)

        if claim.approval_status not in ("pending", "submitted"):
            raise ValidationException(
                {"status": [f"Cannot approve a claim with status '{claim.approval_status}'."]}
            )

        now = datetime.now(timezone.utc)
        old_status = claim.approval_status

        claim.approval_status = "approved"
        claim.approved_by_id = approver_id
        claim.approved_at = now
        if remarks:
            claim.remarks = remarks
        claim.updated_at = now

        await db.flush()

        await create_audit_entry(
            db,
            action="approve",
            entity_type="expense_claim",
            entity_id=claim.id,
            actor_id=approver_id,
            old_values={"approval_status": old_status},
            new_values={"approval_status": "approved"},
        )

        return claim

    @staticmethod
    async def reject_claim(
        db: AsyncSession,
        claim_id: uuid.UUID,
        approver_id: uuid.UUID,
        remarks: str | None = None,
    ) -> ExpenseClaim:
        """Reject an expense claim."""
        claim = await ExpenseService.get_claim(db, claim_id)

        if claim.approval_status not in ("pending", "submitted"):
            raise ValidationException(
                {"status": [f"Cannot reject a claim with status '{claim.approval_status}'."]}
            )

        now = datetime.now(timezone.utc)
        old_status = claim.approval_status

        claim.approval_status = "rejected"
        claim.approved_by_id = approver_id
        claim.approved_at = now
        if remarks:
            claim.remarks = remarks
        claim.updated_at = now

        await db.flush()

        await create_audit_entry(
            db,
            action="reject",
            entity_type="expense_claim",
            entity_id=claim.id,
            actor_id=approver_id,
            old_values={"approval_status": old_status},
            new_values={"approval_status": "rejected"},
        )

        return claim
