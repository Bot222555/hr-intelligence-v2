"""Auth service — Google OAuth exchange, JWT management, session lifecycle."""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import httpx
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth.models import RoleAssignment, UserSession
from backend.common.constants import UserRole
from backend.common.exceptions import ForbiddenException, NotFoundException
from backend.config import settings
from backend.core_hr.models import Employee

# Role priority — higher index = higher privilege
_ROLE_PRIORITY: list[UserRole] = [
    UserRole.employee,
    UserRole.manager,
    UserRole.hr_admin,
    UserRole.system_admin,
]


# ── Google OAuth ────────────────────────────────────────────────────

async def verify_google_token(code: str, redirect_uri: str) -> dict[str, Any]:
    """Exchange Google authorization code for user info.

    Returns dict with keys: email, name, picture, google_id.
    """
    async with httpx.AsyncClient(timeout=15) as client:
        # 1. Exchange code → tokens
        token_resp = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "code": code,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        token_data = token_resp.json()
        if token_resp.status_code != 200 or "access_token" not in token_data:
            raise ForbiddenException(
                detail=f"Google token exchange failed: {token_data.get('error_description', 'unknown error')}",
            )

        access_token = token_data["access_token"]

        # 2. Fetch user info
        info_resp = await client.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if info_resp.status_code != 200:
            raise ForbiddenException(detail="Failed to fetch Google user info.")

        info = info_resp.json()

    return {
        "email": info["email"],
        "name": info.get("name", ""),
        "picture": info.get("picture"),
        "google_id": info["id"],
    }


def validate_domain(email: str) -> None:
    """Ensure the email belongs to the allowed domain."""
    if not email.endswith(f"@{settings.ALLOWED_DOMAIN}"):
        raise ForbiddenException(
            detail=f"Only @{settings.ALLOWED_DOMAIN} accounts are permitted.",
        )


# ── Employee lookup ─────────────────────────────────────────────────

async def get_employee_by_email(db: AsyncSession, email: str) -> Employee:
    """Return an active employee by email, or raise 404."""
    result = await db.execute(
        select(Employee).where(Employee.email == email, Employee.is_active.is_(True)),
    )
    employee = result.scalars().first()
    if employee is None:
        raise NotFoundException(entity_type="Employee", entity_id=email)
    return employee


# ── Roles ───────────────────────────────────────────────────────────

async def get_highest_role(db: AsyncSession, employee_id: uuid.UUID) -> UserRole:
    """Return the highest active role for an employee (default: employee)."""
    result = await db.execute(
        select(RoleAssignment.role).where(
            RoleAssignment.employee_id == employee_id,
            RoleAssignment.is_active.is_(True),
        ),
    )
    roles = [row[0] for row in result.all()]
    if not roles:
        return UserRole.employee

    # Return the role with the highest priority
    best = UserRole.employee
    for role in roles:
        if _ROLE_PRIORITY.index(role) > _ROLE_PRIORITY.index(best):
            best = role
    return best


# ── JWT helpers ─────────────────────────────────────────────────────

def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _create_access_token(employee_id: uuid.UUID, role: UserRole) -> tuple[str, int]:
    """Return (encoded_jwt, expires_in_seconds)."""
    expires_in = settings.JWT_EXPIRY_HOURS * 3600
    payload = {
        "sub": str(employee_id),
        "role": role.value,
        "type": "access",
        "exp": datetime.now(timezone.utc) + timedelta(hours=settings.JWT_EXPIRY_HOURS),
    }
    token = jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
    return token, expires_in


def _create_refresh_token(employee_id: uuid.UUID) -> str:
    payload = {
        "sub": str(employee_id),
        "type": "refresh",
        "jti": uuid.uuid4().hex,  # Unique ID — ensures each refresh token is distinct
        "exp": datetime.now(timezone.utc) + timedelta(days=7),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


# ── Session management ──────────────────────────────────────────────

async def find_or_create_session(
    db: AsyncSession,
    employee: Employee,
    role: UserRole,
    ip: Optional[str],
    user_agent: Optional[str],
) -> tuple[str, str]:
    """Create JWT pair and persist session.  Returns (access_token, refresh_token)."""
    access_token, _ = _create_access_token(employee.id, role)
    refresh_token = _create_refresh_token(employee.id)

    session = UserSession(
        employee_id=employee.id,
        token_hash=_hash_token(access_token),
        refresh_token_hash=_hash_token(refresh_token),
        ip_address=ip,
        user_agent=user_agent,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=settings.JWT_EXPIRY_HOURS),
    )
    db.add(session)
    await db.flush()

    return access_token, refresh_token


# ── Refresh (with token rotation + reuse detection) ─────────────────

async def refresh_access_token(
    db: AsyncSession,
    refresh_token_str: str,
) -> tuple[str, str, int]:
    """Validate refresh token, rotate it, and issue new token pair.

    Returns (new_access_token, new_refresh_token, expires_in).

    Security: each refresh token can only be used once. If a previously
    used (revoked) refresh token is presented, ALL sessions for that user
    are revoked as a precaution against token theft.
    """
    try:
        payload = jwt.decode(
            refresh_token_str,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM],
        )
    except JWTError:
        raise ForbiddenException(detail="Invalid or expired refresh token.")

    if payload.get("type") != "refresh":
        raise ForbiddenException(detail="Invalid token type.")

    # Look up the session by refresh token hash
    refresh_hash = _hash_token(refresh_token_str)
    result = await db.execute(
        select(UserSession).where(
            UserSession.refresh_token_hash == refresh_hash,
        ),
    )
    session = result.scalars().first()

    if session is None:
        raise ForbiddenException(detail="Invalid refresh token.")

    if session.is_revoked:
        # REUSE DETECTED — a previously consumed refresh token was replayed.
        # Revoke ALL sessions for this user as a security precaution.
        await _revoke_all_user_sessions(db, session.employee_id)
        await db.commit()  # Persist revocations BEFORE raising (avoid rollback)
        raise ForbiddenException(
            detail="Refresh token reuse detected. All sessions revoked for security.",
        )

    # Invalidate the old session (consume the refresh token)
    session.is_revoked = True
    await db.flush()

    # Issue new token pair
    employee_id = uuid.UUID(payload["sub"])
    employee = await _get_active_employee(db, employee_id)
    role = await get_highest_role(db, employee.id)
    access_token, expires_in = _create_access_token(employee.id, role)
    new_refresh_token = _create_refresh_token(employee.id)

    # Persist new session with both token hashes
    new_session = UserSession(
        employee_id=employee.id,
        token_hash=_hash_token(access_token),
        refresh_token_hash=_hash_token(new_refresh_token),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=settings.JWT_EXPIRY_HOURS),
    )
    db.add(new_session)
    await db.flush()

    return access_token, new_refresh_token, expires_in


# ── Revoke ──────────────────────────────────────────────────────────

async def _revoke_all_user_sessions(
    db: AsyncSession,
    employee_id: uuid.UUID,
) -> None:
    """Revoke ALL active sessions for an employee (security measure for token reuse)."""
    result = await db.execute(
        select(UserSession).where(
            UserSession.employee_id == employee_id,
            UserSession.is_revoked.is_(False),
        ),
    )
    for session in result.scalars().all():
        session.is_revoked = True
    await db.flush()


async def revoke_session(db: AsyncSession, token_hash: str) -> None:
    """Mark a session as revoked by its token hash."""
    result = await db.execute(
        select(UserSession).where(UserSession.token_hash == token_hash),
    )
    session = result.scalars().first()
    if session:
        session.is_revoked = True
        await db.flush()


# ── Internal helpers ────────────────────────────────────────────────

async def _get_active_employee(db: AsyncSession, employee_id: uuid.UUID) -> Employee:
    result = await db.execute(
        select(Employee).where(Employee.id == employee_id, Employee.is_active.is_(True)),
    )
    employee = result.scalars().first()
    if employee is None:
        raise NotFoundException(entity_type="Employee", entity_id=str(employee_id))
    return employee
