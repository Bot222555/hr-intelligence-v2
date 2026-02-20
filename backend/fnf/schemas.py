"""FnF Pydantic v2 schemas — request/response validation."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict


# ═════════════════════════════════════════════════════════════════════
# FnF Settlement
# ═════════════════════════════════════════════════════════════════════


class FnFSettlementOut(BaseModel):
    """Full FnF settlement representation."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    employee_id: uuid.UUID
    employee_number: Optional[str] = None
    termination_type: Optional[str] = None
    last_working_day: Optional[date] = None
    no_of_pay_days: Decimal = Decimal("0")
    settlement_status: str = "pending"
    total_earnings: Decimal = Decimal("0")
    total_deductions: Decimal = Decimal("0")
    net_settlement: Decimal = Decimal("0")
    settlement_details: Dict[str, Any] = {}
    processed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class FnFSettlementListResponse(BaseModel):
    data: List[FnFSettlementOut]
    total: int
    page: int = 1
    page_size: int = 50
