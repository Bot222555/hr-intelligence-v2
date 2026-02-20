"""Auth dependencies — JWT validation, RBAC enforcement."""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Callable

from fastapi import Depends, Request
from fastapi.exceptions import HTTPException
from jose import ExpiredSignatureError, JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.auth.models import UserSession
from backend.common.constants import PERMISSIONS, UserRole
from backend.common.exceptions import ForbiddenException
from backend.config import settings
from backend.core_hr.models import Employee
from backend.database import get_db

# Role hierarchy — each role implicitly includes lower roles
_ROLE_HIERARCHY: dict[UserRole, set[UserRole]] = {
    UserRole.system_admin: {UserRole.system_admin, UserRole.hr_admin, UserRole.manager, UserRole.employee},
    UserRole.hr_admin: {UserRole.hr_admin, UserRole.manager, UserRole.employee},
    UserRole.manager: {UserRole.manager, UserRole.employee},
    UserRole.employee: {UserRole.employee},
}


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _extract_bearer(request: Request) -> str:
    """Extract Bearer token from Authorization header."""
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header.")
    return auth_header[7:]


# ── Core dependency ─────────────────────────────────────────────────

async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Employee:
    """Validate JWT, verify session, return the authenticated Employee."""
    token = _extract_bearer(request)

    # Decode JWT
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM],
        )
    except ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired.")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token.")

    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid token type.")

    # Verify session exists, not revoked, not expired
    token_hash = _hash_token(token)
    result = await db.execute(
        select(UserSession).where(
            UserSession.token_hash == token_hash,
            UserSession.is_revoked.is_(False),
            UserSession.expires_at > datetime.now(timezone.utc),
        ),
    )
    session = result.scalars().first()
    if session is None:
        raise HTTPException(status_code=401, detail="Session invalid or expired.")

    # Load employee with department + location eager-loaded
    employee_id = uuid.UUID(payload["sub"])
    emp_result = await db.execute(
        select(Employee)
        .where(Employee.id == employee_id, Employee.is_active.is_(True))
        .options(
            selectinload(Employee.department),
            selectinload(Employee.location),
        ),
    )
    employee = emp_result.scalars().first()
    if employee is None:
        raise HTTPException(status_code=401, detail="User account is inactive or not found.")

    # Attach role to request state for downstream use
    role_str = payload.get("role", UserRole.employee.value)
    try:
        role = UserRole(role_str)
    except ValueError:
        role = UserRole.employee
    request.state.user_role = role

    return employee


# ── Role-based dependency ───────────────────────────────────────────

def require_role(*allowed_roles: UserRole) -> Callable:
    """Return a FastAPI dependency that enforces role membership.

    Respects hierarchy — e.g. system_admin can access manager endpoints.
    """

    async def _check(
        request: Request,
        employee: Employee = Depends(get_current_user),
    ) -> Employee:
        user_role: UserRole = request.state.user_role
        # Expand the user role via hierarchy
        effective_roles = _ROLE_HIERARCHY.get(user_role, {user_role})
        if not effective_roles.intersection(set(allowed_roles)):
            raise ForbiddenException(
                detail=f"Role '{user_role.value}' is not permitted. Required: {[r.value for r in allowed_roles]}.",
            )
        return employee

    return _check


# ── Permission-based dependency ─────────────────────────────────────

def require_permission(permission: str) -> Callable:
    """Return a FastAPI dependency that enforces a specific permission string."""

    async def _check(
        request: Request,
        employee: Employee = Depends(get_current_user),
    ) -> Employee:
        user_role: UserRole = request.state.user_role
        role_permissions = PERMISSIONS.get(user_role, [])
        if permission not in role_permissions:
            raise ForbiddenException(
                detail=f"Permission '{permission}' is not granted to role '{user_role.value}'.",
            )
        return employee

    return _check
