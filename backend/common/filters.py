"""Generic filtering, sorting, and full-text search utilities."""

from __future__ import annotations

from typing import Any, Optional, Sequence

from sqlalchemy import Select, String, and_, cast, func, or_, text
from sqlalchemy.orm import InstrumentedAttribute


# ── Sorting ─────────────────────────────────────────────────────────

def apply_sorting(
    query: Select,
    model: Any,
    sort: Optional[str],
) -> Select:
    """
    Parse a sort string like ``"-joining_date"`` and apply ORDER BY.

    * Leading ``-`` → DESC; otherwise ASC.
    * Falls back to text() if the column is not found on *model*.
    """
    if not sort:
        return query

    descending = sort.startswith("-")
    col_name = sort.lstrip("-")

    col = _get_column(model, col_name)
    if col is not None:
        return query.order_by(col.desc() if descending else col.asc())

    direction = "DESC" if descending else "ASC"
    return query.order_by(text(f"{col_name} {direction}"))


# ── Generic filtering ──────────────────────────────────────────────

def apply_filters(
    query: Select,
    model: Any,
    filters: dict[str, Any],
) -> Select:
    """
    Apply a dict of filter parameters to a SQLAlchemy ``Select``.

    Key suffixes determine the operator:

    ============  ==================
    Suffix        Operator
    ============  ==================
    (none)        ``==``
    ``__ilike``   case-insensitive LIKE (wraps ``%…%``)
    ``__from``    ``>=``
    ``__to``      ``<=``
    ``__in``      ``IN (…)``
    ============  ==================

    ``None`` values are silently skipped.
    """
    conditions: list = []

    for key, value in filters.items():
        if value is None:
            continue

        if key.endswith("__ilike"):
            col = _get_column(model, key.removesuffix("__ilike"))
            if col is not None:
                conditions.append(col.ilike(f"%{value}%"))

        elif key.endswith("__from"):
            col = _get_column(model, key.removesuffix("__from"))
            if col is not None:
                conditions.append(col >= value)

        elif key.endswith("__to"):
            col = _get_column(model, key.removesuffix("__to"))
            if col is not None:
                conditions.append(col <= value)

        elif key.endswith("__in"):
            col = _get_column(model, key.removesuffix("__in"))
            if col is not None:
                conditions.append(col.in_(value))

        else:
            col = _get_column(model, key)
            if col is not None:
                conditions.append(col == value)

    if conditions:
        query = query.where(and_(*conditions))

    return query


# ── Full-text / trigram search ──────────────────────────────────────

def apply_search(
    query: Select,
    model: Any,
    search: Optional[str],
    columns: Sequence[str],
    *,
    threshold: float = 0.3,
) -> Select:
    """
    Apply ``pg_trgm`` similarity search across *columns*.

    Requires the ``pg_trgm`` extension in PostgreSQL.
    Results are filtered by *threshold* **or** ILIKE and ordered by
    best similarity first.
    """
    if not search or not search.strip():
        return query

    search = search.strip()
    sim_exprs: list = []
    like_conds: list = []

    for name in columns:
        col = _get_column(model, name)
        if col is None:
            continue
        str_col = cast(col, String)
        sim_exprs.append(func.similarity(str_col, search))
        like_conds.append(str_col.ilike(f"%{search}%"))

    if not sim_exprs:
        return query

    max_sim = func.greatest(*sim_exprs)
    query = query.where(or_(max_sim >= threshold, *like_conds))
    query = query.order_by(max_sim.desc())
    return query


# ── Internal helper ─────────────────────────────────────────────────

def _get_column(model: Any, name: str) -> Optional[InstrumentedAttribute]:
    """Safely retrieve a mapped column attribute by name."""
    return getattr(model, name, None)
