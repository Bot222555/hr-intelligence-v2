"""Generic pagination utilities for SQLAlchemy async queries."""


import math
from typing import Any, Generic, Optional, Sequence, TypeVar

from fastapi import Query
from pydantic import BaseModel
from sqlalchemy import Select, func, text
from sqlalchemy.ext.asyncio import AsyncSession

T = TypeVar("T")


# ── FastAPI dependency ──────────────────────────────────────────────

class PaginationParams:
    """Inject via ``Depends(PaginationParams)`` on any list endpoint."""

    def __init__(
        self,
        page: int = Query(default=1, ge=1, description="Page number (1-indexed)"),
        page_size: int = Query(
            default=50, ge=1, le=100, description="Items per page (max 100)",
        ),
        sort: Optional[str] = Query(
            default=None,
            description='Sort field; prefix "-" for DESC (e.g. "-joining_date")',
        ),
    ) -> None:
        self.page = page
        self.page_size = page_size
        self.sort = sort

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


# ── Pydantic response models ───────────────────────────────────────

class PaginationMeta(BaseModel):
    """Metadata block embedded in every paginated response."""

    page: int
    page_size: int
    total: int
    total_pages: int
    has_next: bool
    has_prev: bool


class PaginatedResponse(BaseModel, Generic[T]):
    """Standard envelope: ``{"data": [...], "meta": {...}}``."""

    data: Sequence[T]
    meta: PaginationMeta


# ── SQLAlchemy helper ───────────────────────────────────────────────

async def paginate(
    session: AsyncSession,
    query: Select,
    params: PaginationParams,
    *,
    model: Any = None,
) -> PaginatedResponse:
    """
    Execute *query* with LIMIT/OFFSET derived from *params* and return
    a ``PaginatedResponse`` with data + meta.

    If *model* is provided, sort columns are resolved as model attributes;
    otherwise a text() fallback is used (caller must ensure the name is safe).
    """
    # ── sorting ─────────────────────────────────────────────────────
    if params.sort:
        descending = params.sort.startswith("-")
        col_name = params.sort.lstrip("-")
        if model is not None and hasattr(model, col_name):
            col = getattr(model, col_name)
            query = query.order_by(col.desc() if descending else col.asc())
        else:
            direction = "DESC" if descending else "ASC"
            query = query.order_by(text(f"{col_name} {direction}"))

    # ── total count (strip ORDER BY for efficiency) ─────────────────
    count_q = query.with_only_columns(func.count()).order_by(None)
    total: int = (await session.execute(count_q)).scalar_one()

    # ── paginated rows ──────────────────────────────────────────────
    rows = (
        await session.execute(
            query.offset(params.offset).limit(params.page_size)
        )
    ).scalars().all()

    total_pages = math.ceil(total / params.page_size) if total else 0

    return PaginatedResponse(
        data=rows,
        meta=PaginationMeta(
            page=params.page,
            page_size=params.page_size,
            total=total,
            total_pages=total_pages,
            has_next=params.page < total_pages,
            has_prev=params.page > 1,
        ),
    )
