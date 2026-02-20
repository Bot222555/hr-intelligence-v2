"""Helpdesk Pydantic v2 schemas — request/response validation."""

import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


# ═════════════════════════════════════════════════════════════════════
# Embedded
# ═════════════════════════════════════════════════════════════════════


class EmployeeBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    display_name: Optional[str] = None


# ═════════════════════════════════════════════════════════════════════
# Responses
# ═════════════════════════════════════════════════════════════════════


class ResponseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    ticket_id: uuid.UUID
    author_id: Optional[uuid.UUID] = None
    author_name: Optional[str] = None
    body: str
    is_internal: bool = False
    created_at: Optional[datetime] = None


class ResponseCreate(BaseModel):
    body: str = Field(..., min_length=1, max_length=5000)
    is_internal: bool = False


# ═════════════════════════════════════════════════════════════════════
# Tickets
# ═════════════════════════════════════════════════════════════════════


class TicketOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    ticket_number: Optional[str] = None
    title: str
    category: Optional[str] = None
    status: str = "open"
    priority: str = "medium"
    raised_by_id: Optional[uuid.UUID] = None
    raised_by_name: Optional[str] = None
    assigned_to_id: Optional[uuid.UUID] = None
    assigned_to_name: Optional[str] = None
    requested_on: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    responses: List[ResponseOut] = []


class TicketCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    category: Optional[str] = Field(None, max_length=200)
    priority: str = Field("medium", pattern="^(low|medium|high|critical|urgent)$")


class TicketUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=500)
    category: Optional[str] = None
    status: Optional[str] = Field(
        None, pattern="^(open|in_progress|resolved|closed|waiting)$"
    )
    priority: Optional[str] = Field(
        None, pattern="^(low|medium|high|critical|urgent)$"
    )
    assigned_to_id: Optional[uuid.UUID] = None


class TicketListResponse(BaseModel):
    data: List[TicketOut]
    total: int
    page: int = 1
    page_size: int = 50
