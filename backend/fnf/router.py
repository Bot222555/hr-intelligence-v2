"""FnF router — Full & Final settlement queries.

All endpoints require HR/Admin authentication.
"""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth.dependencies import get_current_user, require_role
from backend.common.constants import UserRole
from backend.core_hr.models import Employee
from backend.database import get_db
from backend.fnf.schemas import FnFListResponse, FnFOut, FnFSummary
from backend.fnf.service import FnFService

router = APIRouter(prefix="", tags=["fnf"])


# ── GET / ────────────────────────────────────────────────────────────

@router.get("/", response_model=FnFListResponse)
async def list_settlements(
    settlement_status: Optional[str] = Query(None),
    termination_type: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    employee: Employee = Depends(
        require_role(UserRole.hr_admin, UserRole.system_admin)
    ),
    db: AsyncSession = Depends(get_db),
):
    """List all FnF settlements (HR/Admin only)."""
    settlements, total = await FnFService.list_settlements(
        db,
        settlement_status=settlement_status,
        termination_type=termination_type,
        page=page,
        page_size=page_size,
    )
    return FnFListResponse(
        data=[FnFOut.model_validate(s) for s in settlements],
        total=total,
        page=page,
        page_size=page_size,
    )


# ── GET /summary ─────────────────────────────────────────────────────

@router.get("/summary", response_model=FnFSummary)
async def fnf_summary(
    employee: Employee = Depends(
        require_role(UserRole.hr_admin, UserRole.system_admin)
    ),
    db: AsyncSession = Depends(get_db),
):
    """Get FnF settlement summary statistics."""
    data = await FnFService.get_summary(db)
    return FnFSummary(**data)


# ── GET /{settlement_id} ─────────────────────────────────────────────

@router.get("/{settlement_id}", response_model=FnFOut)
async def get_settlement(
    settlement_id: uuid.UUID,
    employee: Employee = Depends(
        require_role(UserRole.hr_admin, UserRole.system_admin)
    ),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific FnF settlement by ID."""
    settlement = await FnFService.get_settlement(db, settlement_id)
    return FnFOut.model_validate(settlement)


# ── GET /employee/{employee_id} ──────────────────────────────────────

@router.get("/employee/{employee_id}", response_model=FnFOut)
async def get_employee_settlement(
    employee_id: uuid.UUID,
    employee: Employee = Depends(
        require_role(UserRole.hr_admin, UserRole.system_admin)
    ),
    db: AsyncSession = Depends(get_db),
):
    """Get FnF settlement for a specific employee."""
    settlement = await FnFService.get_by_employee(db, employee_id)
    return FnFOut.model_validate(settlement)
