"""Expenses router — CRUD + approval workflow for expense claims.

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
from backend.expenses.schemas import (
    ExpenseApproveRequest,
    ExpenseCreate,
    ExpenseListResponse,
    ExpenseOut,
    ExpenseUpdate,
)
from backend.expenses.service import ExpenseService

router = APIRouter(prefix="", tags=["expenses"])


# ── POST / ───────────────────────────────────────────────────────────

@router.post("/", response_model=ExpenseOut, status_code=201)
async def create_expense(
    body: ExpenseCreate,
    employee: Employee = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Submit a new expense claim."""
    claim = await ExpenseService.create_claim(
        db,
        employee_id=employee.id,
        employee_name=getattr(employee, "display_name", None)
        or f"{employee.first_name} {employee.last_name}".strip(),
        title=body.title,
        amount=float(body.amount),
        currency=body.currency,
        expenses=body.expenses,
        remarks=body.remarks,
    )
    await db.commit()
    return ExpenseOut.model_validate(claim)


# ── GET / ────────────────────────────────────────────────────────────

@router.get("/", response_model=ExpenseListResponse)
async def list_expenses(
    employee_id: Optional[uuid.UUID] = Query(None),
    approval_status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    employee: Employee = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List expense claims with optional filters."""
    claims, total = await ExpenseService.list_claims(
        db,
        employee_id=employee_id,
        approval_status=approval_status,
        page=page,
        page_size=page_size,
    )
    return ExpenseListResponse(
        data=[ExpenseOut.model_validate(c) for c in claims],
        total=total,
        page=page,
        page_size=page_size,
    )


# ── GET /my-expenses ─────────────────────────────────────────────────

@router.get("/my-expenses", response_model=ExpenseListResponse)
async def my_expenses(
    approval_status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    employee: Employee = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List expense claims for the current user."""
    claims, total = await ExpenseService.list_claims(
        db,
        employee_id=employee.id,
        approval_status=approval_status,
        page=page,
        page_size=page_size,
    )
    return ExpenseListResponse(
        data=[ExpenseOut.model_validate(c) for c in claims],
        total=total,
        page=page,
        page_size=page_size,
    )


# ── GET /{claim_id} ──────────────────────────────────────────────────

@router.get("/{claim_id}", response_model=ExpenseOut)
async def get_expense(
    claim_id: uuid.UUID,
    employee: Employee = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific expense claim."""
    claim = await ExpenseService.get_claim(db, claim_id)
    return ExpenseOut.model_validate(claim)


# ── PATCH /{claim_id} ────────────────────────────────────────────────

@router.patch("/{claim_id}", response_model=ExpenseOut)
async def update_expense(
    claim_id: uuid.UUID,
    body: ExpenseUpdate,
    employee: Employee = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update an expense claim (only if pending/submitted)."""
    update_data = body.model_dump(exclude_unset=True)
    # Convert Decimal to float for ORM
    if "amount" in update_data and update_data["amount"] is not None:
        update_data["amount"] = float(update_data["amount"])
    claim = await ExpenseService.update_claim(
        db, claim_id, actor_id=employee.id, **update_data,
    )
    await db.commit()
    return ExpenseOut.model_validate(claim)


# ── POST /{claim_id}/approve ─────────────────────────────────────────

@router.post("/{claim_id}/approve", response_model=ExpenseOut)
async def approve_expense(
    claim_id: uuid.UUID,
    body: ExpenseApproveRequest = ExpenseApproveRequest(),
    employee: Employee = Depends(
        require_role(UserRole.manager, UserRole.hr_admin, UserRole.system_admin)
    ),
    db: AsyncSession = Depends(get_db),
):
    """Approve an expense claim (Manager/HR only)."""
    claim = await ExpenseService.approve_claim(
        db, claim_id, approver_id=employee.id, remarks=body.remarks,
    )
    await db.commit()
    return ExpenseOut.model_validate(claim)


# ── POST /{claim_id}/reject ──────────────────────────────────────────

@router.post("/{claim_id}/reject", response_model=ExpenseOut)
async def reject_expense(
    claim_id: uuid.UUID,
    body: ExpenseApproveRequest = ExpenseApproveRequest(),
    employee: Employee = Depends(
        require_role(UserRole.manager, UserRole.hr_admin, UserRole.system_admin)
    ),
    db: AsyncSession = Depends(get_db),
):
    """Reject an expense claim (Manager/HR only)."""
    claim = await ExpenseService.reject_claim(
        db, claim_id, approver_id=employee.id, remarks=body.remarks,
    )
    await db.commit()
    return ExpenseOut.model_validate(claim)
