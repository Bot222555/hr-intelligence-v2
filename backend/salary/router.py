"""Salary router — salary slips, components, CTC breakdowns.

All endpoints require authentication.
"""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth.dependencies import get_current_user, require_role
from backend.common.constants import UserRole
from backend.core_hr.models import Employee
from backend.database import get_db
from backend.salary.schemas import (
    CTCBreakdownOut,
    SalaryComponentListResponse,
    SalaryComponentOut,
    SalaryListResponse,
    SalaryOut,
)
from backend.salary.service import SalaryService

router = APIRouter(prefix="", tags=["salary"])


# ── GET /components ──────────────────────────────────────────────────

@router.get("/components", response_model=SalaryComponentListResponse)
async def list_components(
    is_active: Optional[bool] = Query(True),
    employee: Employee = Depends(
        require_role(UserRole.hr_admin, UserRole.system_admin)
    ),
    db: AsyncSession = Depends(get_db),
):
    """List all salary components (HR/Admin only)."""
    components = await SalaryService.get_components(db, is_active=is_active)
    return SalaryComponentListResponse(
        data=[SalaryComponentOut.model_validate(c) for c in components],
        total=len(components),
    )


# ── GET /my-salary ───────────────────────────────────────────────────

@router.get("/my-salary", response_model=SalaryOut)
async def my_salary(
    employee: Employee = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the authenticated user's current salary."""
    salary = await SalaryService.get_salary_by_employee(db, employee.id)
    return SalaryOut.model_validate(salary)


# ── GET /my-ctc ──────────────────────────────────────────────────────

@router.get("/my-ctc", response_model=CTCBreakdownOut)
async def my_ctc_breakdown(
    employee: Employee = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get CTC breakdown for the authenticated user."""
    breakdown = await SalaryService.get_ctc_breakdown(db, employee.id)
    return CTCBreakdownOut(**breakdown)


# ── GET /slips ───────────────────────────────────────────────────────

@router.get("/slips", response_model=SalaryListResponse)
async def list_salary_slips(
    employee_id: Optional[uuid.UUID] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    employee: Employee = Depends(
        require_role(UserRole.hr_admin, UserRole.system_admin)
    ),
    db: AsyncSession = Depends(get_db),
):
    """List salary slips (HR/Admin only). Optionally filter by employee."""
    salaries, total = await SalaryService.get_salary_slips(
        db, employee_id=employee_id, page=page, page_size=page_size,
    )
    return SalaryListResponse(
        data=[SalaryOut.model_validate(s) for s in salaries],
        total=total,
        page=page,
        page_size=page_size,
    )


# ── GET /summary ──────────────────────────────────────────────────────

@router.get("/summary")
async def salary_summary(
    employee: Employee = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Current month total earnings, deductions, and net pay for the user."""
    try:
        salary = await SalaryService.get_salary_by_employee(db, employee.id)
        total_earnings = float(getattr(salary, "gross_earnings", 0) or getattr(salary, "basic_salary", 0) or 0)
        total_deductions = float(getattr(salary, "total_deductions", 0) or 0)
        net_pay = float(getattr(salary, "net_salary", 0) or 0)
    except Exception:
        total_earnings = 0
        total_deductions = 0
        net_pay = 0
    return {
        "total_earnings": total_earnings,
        "total_deductions": total_deductions,
        "net_pay": net_pay,
    }


# ── GET /team ────────────────────────────────────────────────────────

@router.get("/team")
async def team_salary(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    employee: Employee = Depends(
        require_role(UserRole.manager, UserRole.hr_admin, UserRole.system_admin)
    ),
    db: AsyncSession = Depends(get_db),
):
    """List salary records for the manager's team (or all for HR/Admin)."""
    try:
        salaries, total = await SalaryService.get_salary_slips(
            db, manager_id=employee.id, page=page, page_size=page_size,
        )
    except TypeError:
        # Service doesn't support manager_id — fall back to all slips
        salaries, total = await SalaryService.get_salary_slips(
            db, page=page, page_size=page_size,
        )
    return SalaryListResponse(
        data=[SalaryOut.model_validate(s) for s in salaries],
        total=total,
        page=page,
        page_size=page_size,
    )


# ── GET /{employee_id}/ctc ──────────────────────────────────────────

@router.get("/{employee_id}/ctc", response_model=CTCBreakdownOut)
async def employee_ctc_breakdown(
    employee_id: uuid.UUID,
    employee: Employee = Depends(
        require_role(UserRole.manager, UserRole.hr_admin, UserRole.system_admin)
    ),
    db: AsyncSession = Depends(get_db),
):
    """Get CTC breakdown for a specific employee (Manager/HR only)."""
    breakdown = await SalaryService.get_ctc_breakdown(db, employee_id)
    return CTCBreakdownOut(**breakdown)
