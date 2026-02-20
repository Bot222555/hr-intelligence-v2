"""Expenses Pydantic v2 schemas — request/response validation."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict, Field


# ═════════════════════════════════════════════════════════════════════
# Embedded
# ═════════════════════════════════════════════════════════════════════


class EmployeeBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    display_name: Optional[str] = None


# ═════════════════════════════════════════════════════════════════════
# Expense Claim
# ═════════════════════════════════════════════════════════════════════


class ExpenseCreate(BaseModel):
    """Create a new expense claim."""

    title: str = Field(..., min_length=1, max_length=500)
    amount: Decimal = Field(..., gt=0, max_digits=12, decimal_places=2)
    currency: str = Field("INR", max_length=10)
    expenses: List[Any] = Field(default_factory=list)
    remarks: Optional[str] = Field(None, max_length=2000)


class ExpenseUpdate(BaseModel):
    """Update an existing expense claim."""

    title: Optional[str] = Field(None, min_length=1, max_length=500)
    amount: Optional[Decimal] = Field(None, gt=0, max_digits=12, decimal_places=2)
    currency: Optional[str] = Field(None, max_length=10)
    expenses: Optional[List[Any]] = None
    remarks: Optional[str] = Field(None, max_length=2000)


class ExpenseOut(BaseModel):
    """Full expense claim representation."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    employee_id: uuid.UUID
    employee_name: Optional[str] = None
    claim_number: Optional[str] = None
    title: str
    amount: Decimal = Decimal("0")
    currency: str = "INR"
    payment_status: Optional[str] = None
    approval_status: str = "pending"
    expenses: List[Any] = []
    submitted_date: Optional[date] = None
    approved_by_id: Optional[uuid.UUID] = None
    approved_at: Optional[datetime] = None
    paid_at: Optional[datetime] = None
    remarks: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ExpenseApproveRequest(BaseModel):
    """Payload for approving/rejecting an expense claim."""

    remarks: Optional[str] = Field(None, max_length=2000)


class ExpenseListResponse(BaseModel):
    data: List[ExpenseOut]
    total: int
    page: int = 1
    page_size: int = 50
