"""Salary service layer — query salary data, components, CTC breakdowns."""

from __future__ import annotations

import uuid
from typing import Optional, Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.common.exceptions import NotFoundException
from backend.salary.models import Salary, SalaryComponent


class SalaryService:
    """Business logic for salary operations."""

    # ── Salary Components ─────────────────────────────────────────────

    @staticmethod
    async def get_components(
        db: AsyncSession,
        is_active: Optional[bool] = True,
    ) -> list[SalaryComponent]:
        """List all salary components."""
        stmt = select(SalaryComponent)
        if is_active is not None:
            stmt = stmt.where(SalaryComponent.is_active == is_active)
        stmt = stmt.order_by(SalaryComponent.title)
        result = await db.execute(stmt)
        return list(result.scalars().all())

    # ── Employee Salary ───────────────────────────────────────────────

    @staticmethod
    async def get_salary_by_employee(
        db: AsyncSession,
        employee_id: uuid.UUID,
    ) -> Salary:
        """Get current salary for an employee."""
        stmt = (
            select(Salary)
            .where(Salary.employee_id == employee_id, Salary.is_current == True)
        )
        result = await db.execute(stmt)
        salary = result.scalar_one_or_none()
        if not salary:
            raise NotFoundException("Salary", str(employee_id))
        return salary

    @staticmethod
    async def get_salary_slips(
        db: AsyncSession,
        employee_id: Optional[uuid.UUID] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[Salary], int]:
        """List salary slips with optional employee filter."""
        stmt = select(Salary).where(Salary.is_current == True)
        count_stmt = select(func.count()).select_from(Salary).where(Salary.is_current == True)

        if employee_id:
            stmt = stmt.where(Salary.employee_id == employee_id)
            count_stmt = count_stmt.where(Salary.employee_id == employee_id)

        # Total count
        total = (await db.execute(count_stmt)).scalar() or 0

        # Paginate
        stmt = stmt.offset((page - 1) * page_size).limit(page_size)
        result = await db.execute(stmt)
        return list(result.scalars().all()), total

    @staticmethod
    async def get_ctc_breakdown(
        db: AsyncSession,
        employee_id: uuid.UUID,
    ) -> dict:
        """Get detailed CTC breakdown for an employee."""
        stmt = (
            select(Salary)
            .where(Salary.employee_id == employee_id, Salary.is_current == True)
        )
        result = await db.execute(stmt)
        salary = result.scalar_one_or_none()
        if not salary:
            raise NotFoundException("Salary", str(employee_id))

        return {
            "employee_id": salary.employee_id,
            "ctc": salary.ctc,
            "gross_pay": salary.gross_pay,
            "net_pay": salary.net_pay,
            "earnings": salary.earnings or [],
            "deductions": salary.deductions or [],
            "contributions": salary.contributions or [],
        }
