"""Expenses router — CRUD + approval workflow for expense claims.

All endpoints require authentication.
"""

import os
import uuid
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
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
from backend.config import settings
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
    from_date: Optional[date] = Query(None),
    to_date: Optional[date] = Query(None),
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
    if from_date or to_date:
        from datetime import datetime as dt
        filtered = []
        for c in claims:
            c_date = getattr(c, "created_at", None)
            if c_date is None:
                filtered.append(c)
                continue
            c_day = c_date.date() if isinstance(c_date, dt) else c_date
            if from_date and c_day < from_date:
                continue
            if to_date and c_day > to_date:
                continue
            filtered.append(c)
        claims = filtered
        total = len(claims)
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
    from sqlalchemy import case, func, select
    from backend.expenses.models import ExpenseClaim

    stmt = select(
        func.count().label("total"),
        func.coalesce(func.sum(ExpenseClaim.amount), 0).label("total_amount"),
        func.sum(case((ExpenseClaim.approval_status.in_(["pending", "submitted", "draft"]), 1), else_=0)).label("pending"),
        func.sum(case((ExpenseClaim.approval_status == "approved", 1), else_=0)).label("approved"),
        func.sum(case((ExpenseClaim.approval_status == "rejected", 1), else_=0)).label("rejected"),
    ).where(ExpenseClaim.employee_id == employee.id)
    result = await db.execute(stmt)
    row = result.one()
    return {
        "total_claims": row.total,
        "total_amount": float(row.total_amount),
        "pending_count": row.pending,
        "approved_count": row.approved,
        "rejected_count": row.rejected,
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
        return ExpenseListResponse(
            data=[],
            meta=_build_meta(0, page, page_size),
            total=0,
            page=page,
            page_size=page_size,
        )
    claims, total = await ExpenseService.list_claims(
        db,
        approval_status=approval_status,
        page=page,
        page_size=page_size,
    )
    team_claims = [c for c in claims if c.employee_id in report_ids]
    return ExpenseListResponse(
        data=[ExpenseOut.model_validate(c) for c in team_claims],
        meta=_build_meta(len(team_claims), page, page_size),
        total=len(team_claims),
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
    # MIME type validation
    allowed_types = {"image/jpeg", "image/png", "image/gif", "application/pdf"}
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail=f"File type '{file.content_type}' not allowed. Accepted: JPEG, PNG, GIF, PDF.",
        )

    contents = await file.read()

    # Size validation (10 MB max)
    max_size = 10 * 1024 * 1024
    if len(contents) > max_size:
        raise HTTPException(status_code=400, detail="File too large. Maximum size is 10 MB.")

    upload_dir = os.path.join(settings.UPLOAD_DIR, "receipts")
    os.makedirs(upload_dir, exist_ok=True)

    # Use UUID-only filename (no original filename) to prevent path traversal
    ext = os.path.splitext(file.filename or "")[1] if file.filename else ""
    safe_name = f"{uuid.uuid4().hex}{ext}"
    file_path = os.path.join(upload_dir, safe_name)

    with open(file_path, "wb") as f:
        f.write(contents)

    return {"url": f"/uploads/receipts/{safe_name}", "filename": safe_name}


# ── GET /{claim_id} ──────────────────────────────────────────────────

@router.get("/{claim_id}", response_model=ExpenseOut)
async def get_expense(
    claim_id: uuid.UUID,
    request: Request,
    employee: Employee = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific expense claim."""
    claim = await ExpenseService.get_claim(db, claim_id)
    # Authorization: only owner or hr_admin/system_admin
    if claim.employee_id != employee.id:
        user_role = getattr(request.state, "user_role", None)
        if user_role not in (UserRole.hr_admin, UserRole.system_admin):
            raise HTTPException(status_code=403, detail="Not authorized to view this expense claim")
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
