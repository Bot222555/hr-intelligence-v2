"""FnF service layer — read-only operations for Full & Final settlements."""

from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.common.exceptions import NotFoundException
from backend.fnf.models import FnFSettlement


class FnFService:
    """Business logic for FnF settlement operations (read-only)."""

    @staticmethod
    async def get_settlement(
        db: AsyncSession,
        settlement_id: uuid.UUID,
    ) -> FnFSettlement:
        """Get a single FnF settlement by ID."""
        stmt = select(FnFSettlement).where(FnFSettlement.id == settlement_id)
        result = await db.execute(stmt)
        settlement = result.scalar_one_or_none()
        if not settlement:
            raise NotFoundException("FnFSettlement", str(settlement_id))
        return settlement

    @staticmethod
    async def get_by_employee(
        db: AsyncSession,
        employee_id: uuid.UUID,
    ) -> FnFSettlement:
        """Get FnF settlement for a specific employee."""
        stmt = select(FnFSettlement).where(
            FnFSettlement.employee_id == employee_id,
        )
        result = await db.execute(stmt)
        settlement = result.scalar_one_or_none()
        if not settlement:
            raise NotFoundException("FnFSettlement", f"employee={employee_id}")
        return settlement

    @staticmethod
    async def list_settlements(
        db: AsyncSession,
        settlement_status: Optional[str] = None,
        termination_type: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[FnFSettlement], int]:
        """List FnF settlements with optional filters."""
        stmt = select(FnFSettlement)
        count_stmt = select(func.count()).select_from(FnFSettlement)

        if settlement_status:
            stmt = stmt.where(FnFSettlement.settlement_status == settlement_status)
            count_stmt = count_stmt.where(
                FnFSettlement.settlement_status == settlement_status
            )
        if termination_type:
            stmt = stmt.where(FnFSettlement.termination_type == termination_type)
            count_stmt = count_stmt.where(
                FnFSettlement.termination_type == termination_type
            )

        total = (await db.execute(count_stmt)).scalar() or 0

        stmt = (
            stmt.order_by(FnFSettlement.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await db.execute(stmt)
        return list(result.scalars().all()), total

    @staticmethod
    async def get_summary(db: AsyncSession) -> dict:
        """Get aggregate FnF statistics."""
        total_stmt = select(func.count()).select_from(FnFSettlement)
        total = (await db.execute(total_stmt)).scalar() or 0

        pending_stmt = select(func.count()).select_from(FnFSettlement).where(
            FnFSettlement.settlement_status == "pending"
        )
        pending = (await db.execute(pending_stmt)).scalar() or 0

        completed_stmt = select(func.count()).select_from(FnFSettlement).where(
            FnFSettlement.settlement_status == "completed"
        )
        completed = (await db.execute(completed_stmt)).scalar() or 0

        net_stmt = select(func.sum(FnFSettlement.net_settlement)).select_from(
            FnFSettlement
        )
        total_net = (await db.execute(net_stmt)).scalar() or 0

        return {
            "total_settlements": total,
            "pending": pending,
            "completed": completed,
            "total_net_amount": float(total_net),
        }
