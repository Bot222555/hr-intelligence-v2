"""Salary Pydantic v2 schemas — request/response validation."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict, Field


# ═════════════════════════════════════════════════════════════════════
# Salary Component
# ═════════════════════════════════════════════════════════════════════


class SalaryComponentOut(BaseModel):
    """Salary component definition."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    identifier: Optional[str] = None
    title: str
    accounting_code: Optional[str] = None
    component_type: str = "earning"
    is_active: bool = True


class SalaryComponentListResponse(BaseModel):
    data: List[SalaryComponentOut]
    total: int


# ═════════════════════════════════════════════════════════════════════
# Employee Brief (embedded)
# ═════════════════════════════════════════════════════════════════════


class EmployeeBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    employee_code: Optional[str] = None
    display_name: Optional[str] = None
    designation: Optional[str] = None
    department_name: Optional[str] = None


# ═════════════════════════════════════════════════════════════════════
# Salary
# ═════════════════════════════════════════════════════════════════════


class SalaryOut(BaseModel):
    """Full salary representation."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    employee_id: uuid.UUID
    ctc: Decimal = Decimal("0")
    gross_pay: Decimal = Decimal("0")
    net_pay: Decimal = Decimal("0")
    earnings: List[Any] = []
    deductions: List[Any] = []
    contributions: List[Any] = []
    variables: List[Any] = []
    effective_date: Optional[date] = None
    pay_period: Optional[str] = None
    is_current: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class CTCComponentOut(BaseModel):
    """Structured CTC component for frontend display."""

    name: str
    type: str = "earning"  # earning | deduction | employer_contribution
    annual_amount: Decimal = Decimal("0")
    monthly_amount: Decimal = Decimal("0")
    percentage_of_ctc: Decimal = Decimal("0")


class CTCBreakdownOut(BaseModel):
    """CTC breakdown response."""

    employee_id: uuid.UUID
    employee_name: Optional[str] = None
    annual_ctc: Decimal = Decimal("0")
    monthly_ctc: Decimal = Decimal("0")
    ctc: Decimal = Decimal("0")
    gross_pay: Decimal = Decimal("0")
    net_pay: Decimal = Decimal("0")
    components: List[CTCComponentOut] = []
    earnings: List[Any] = []
    deductions: List[Any] = []
    contributions: List[Any] = []


class SalaryListResponse(BaseModel):
    data: List[SalaryOut]
    total: int
    page: int = 1
    page_size: int = 50
