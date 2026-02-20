"""Salary router — salary slips, components, CTC breakdowns.

All endpoints require authentication.
"""

import logging
import uuid as _uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth.dependencies import get_current_user, require_role
from backend.common.constants import UserRole
from backend.common.exceptions import NotFoundException
from backend.core_hr.models import Employee
from backend.database import get_db

logger = logging.getLogger(__name__)
from backend.salary.schemas import (
    CTCBreakdownOut,
    CTCComponentOut,
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
    employee: Employee = Depends(get_current_user),
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
    try:
        salary = await SalaryService.get_salary_by_employee(db, employee.id)
        return SalaryOut.model_validate(salary)
    except NotFoundException:
        # Return empty salary for employees without records
        return SalaryOut(id=_uuid.uuid4(), employee_id=employee.id)


# ── GET /my-slips ────────────────────────────────────────────────────

@router.get("/my-slips", response_model=SalaryListResponse)
async def my_salary_slips(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    employee: Employee = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List salary slips for the current user."""
    salaries, total = await SalaryService.get_salary_slips(
        db, employee_id=employee.id, page=page, page_size=page_size,
    )
    return SalaryListResponse(
        data=[SalaryOut.model_validate(s) for s in salaries],
        total=total,
        page=page,
        page_size=page_size,
    )


# ── GET /my-ctc ──────────────────────────────────────────────────────

def _enrich_ctc_breakdown(breakdown: dict) -> dict:
    """Add structured components, annual_ctc, monthly_ctc to a CTC dict."""
    from decimal import Decimal

    ctc = Decimal(str(breakdown.get("ctc", 0)))
    annual_ctc = ctc
    monthly_ctc = ctc / 12 if ctc else Decimal("0")
    components = []

    for item in breakdown.get("earnings", []):
        name = item.get("name", item.get("title", "Unknown")) if isinstance(item, dict) else str(item)
        amt = Decimal(str(item.get("amount", item.get("annual_amount", 0)))) if isinstance(item, dict) else Decimal("0")
        monthly = amt / 12 if amt else Decimal("0")
        pct = (amt / annual_ctc * 100) if annual_ctc else Decimal("0")
        components.append(CTCComponentOut(name=name, type="earning", annual_amount=amt, monthly_amount=monthly, percentage_of_ctc=pct))

    for item in breakdown.get("deductions", []):
        name = item.get("name", item.get("title", "Unknown")) if isinstance(item, dict) else str(item)
        amt = Decimal(str(item.get("amount", item.get("annual_amount", 0)))) if isinstance(item, dict) else Decimal("0")
        monthly = amt / 12 if amt else Decimal("0")
        pct = (amt / annual_ctc * 100) if annual_ctc else Decimal("0")
        components.append(CTCComponentOut(name=name, type="deduction", annual_amount=amt, monthly_amount=monthly, percentage_of_ctc=pct))

    for item in breakdown.get("contributions", []):
        name = item.get("name", item.get("title", "Unknown")) if isinstance(item, dict) else str(item)
        amt = Decimal(str(item.get("amount", item.get("annual_amount", 0)))) if isinstance(item, dict) else Decimal("0")
        monthly = amt / 12 if amt else Decimal("0")
        pct = (amt / annual_ctc * 100) if annual_ctc else Decimal("0")
        components.append(CTCComponentOut(name=name, type="employer_contribution", annual_amount=amt, monthly_amount=monthly, percentage_of_ctc=pct))

    breakdown["annual_ctc"] = annual_ctc
    breakdown["monthly_ctc"] = monthly_ctc
    breakdown["components"] = components
    return breakdown


@router.get("/my-ctc", response_model=CTCBreakdownOut)
async def my_ctc_breakdown(
    employee: Employee = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get CTC breakdown for the authenticated user."""
    breakdown = await SalaryService.get_ctc_breakdown(db, employee.id)
    return CTCBreakdownOut(**_enrich_ctc_breakdown(breakdown))


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
    except NotFoundException:
        total_earnings = 0
        total_deductions = 0
        net_pay = 0
    except Exception as e:
        logger.error(f"Salary summary error for employee {employee.id}: {e}")
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
    """List salary records for the manager's team."""
    from sqlalchemy import select as sa_select
    from backend.core_hr.models import Employee as Emp

    reports = await db.execute(
        sa_select(Emp.id).where(
            Emp.reporting_manager_id == employee.id,
            Emp.is_active.is_(True),
        )
    )
    report_ids = [r[0] for r in reports.all()]
    if not report_ids:
        return SalaryListResponse(data=[], total=0, page=page, page_size=page_size)
    salaries, total = await SalaryService.get_salary_slips(
        db, page=page, page_size=page_size,
    )
    team_salaries = [s for s in salaries if getattr(s, "employee_id", None) in report_ids]
    return SalaryListResponse(
        data=[SalaryOut.model_validate(s) for s in team_salaries],
        total=len(team_salaries),
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
    return CTCBreakdownOut(**_enrich_ctc_breakdown(breakdown))
