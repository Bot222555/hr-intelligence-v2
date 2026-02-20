"""Auth module test suite — 15 tests covering OAuth, JWT, sessions, RBAC."""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

from jose import jwt
from sqlalchemy import select

from backend.auth.models import RoleAssignment, UserSession
from backend.common.constants import PERMISSIONS, UserRole
from backend.config import settings
from tests.conftest import (
    TestSessionFactory,
    create_access_token,
    create_refresh_token,
)


# ── Google OAuth ────────────────────────────────────────────────────


async def test_google_oauth_valid_creativefuel_email(
    client, db, test_employee, mock_google_oauth,
):
    """Valid @creativefuel.io code → 200 with access + refresh tokens."""
    with mock_google_oauth(email=test_employee["email"]):
        resp = await client.post(
            "/api/v1/auth/google",
            json={"code": "valid-auth-code", "redirect_uri": "http://localhost:3000/callback"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"
    assert data["user"]["email"] == test_employee["email"]


async def test_google_oauth_non_creativefuel_email(
    client, db, mock_google_oauth,
):
    """Non-creativefuel domain → 403 forbidden."""
    with mock_google_oauth(email="outsider@gmail.com"):
        resp = await client.post(
            "/api/v1/auth/google",
            json={"code": "some-code", "redirect_uri": "http://localhost:3000/callback"},
        )
    assert resp.status_code == 403
    assert "creativefuel" in resp.json()["detail"].lower()


async def test_google_oauth_invalid_code(client):
    """Google rejects the authorization code → 403."""
    from backend.common.exceptions import ForbiddenException

    with patch(
        "backend.auth.router.verify_google_token",
        new_callable=AsyncMock,
        side_effect=ForbiddenException(detail="Google token exchange failed: invalid_grant"),
    ):
        resp = await client.post(
            "/api/v1/auth/google",
            json={"code": "bad-code", "redirect_uri": "http://localhost:3000/callback"},
        )
    assert resp.status_code == 403


# ── JWT tokens ──────────────────────────────────────────────────────


async def test_jwt_generation_has_correct_claims(
    client, db, test_employee, mock_google_oauth,
):
    """Access token JWT contains sub, role, type, exp claims."""
    with mock_google_oauth(email=test_employee["email"]):
        resp = await client.post(
            "/api/v1/auth/google",
            json={"code": "valid-code", "redirect_uri": "http://localhost:3000/callback"},
        )
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    assert payload["sub"] == str(test_employee["id"])
    assert payload["role"] == UserRole.employee.value
    assert payload["type"] == "access"
    assert "exp" in payload


async def test_jwt_expiry_check(client, db, test_employee):
    """Expired access token → 401 on /me."""
    expired_token = create_access_token(test_employee["id"], expired=True)

    # Persist a session row so the only rejection reason is expiry
    async with TestSessionFactory() as session:
        s = UserSession(
            id=uuid.uuid4(),
            employee_id=test_employee["id"],
            token_hash=hashlib.sha256(expired_token.encode()).hexdigest(),
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
            is_revoked=False,
            created_at=datetime.now(timezone.utc),
        )
        session.add(s)
        await session.commit()

    resp = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {expired_token}"},
    )
    assert resp.status_code == 401


# ── Refresh ─────────────────────────────────────────────────────────


async def test_refresh_token_generates_new_access(
    client, db, test_employee,
):
    """Valid refresh token → 200 with new access_token."""
    refresh = create_refresh_token(test_employee["id"])
    resp = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["expires_in"] == settings.JWT_EXPIRY_HOURS * 3600


async def test_refresh_expired_token(client, db, test_employee):
    """Expired refresh token → 403."""
    expired_refresh = create_refresh_token(test_employee["id"], expired=True)
    resp = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": expired_refresh},
    )
    assert resp.status_code == 403


# ── Logout ──────────────────────────────────────────────────────────


async def test_logout_revokes_session(client, db, test_employee, auth_headers):
    """POST /logout revokes the session; subsequent /me returns 401."""
    # Logout
    resp = await client.post("/api/v1/auth/logout", headers=auth_headers)
    assert resp.status_code == 200

    # Token should now be rejected
    resp2 = await client.get("/api/v1/auth/me", headers=auth_headers)
    assert resp2.status_code == 401


# ── GET /me ─────────────────────────────────────────────────────────


async def test_get_me_returns_current_user(
    client, db, test_employee, auth_headers,
):
    """Authenticated /me returns user profile + permissions."""
    resp = await client.get("/api/v1/auth/me", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["email"] == test_employee["email"]
    assert data["display_name"] == f"{test_employee['first_name']} {test_employee['last_name']}"
    assert data["role"] == UserRole.employee.value
    assert isinstance(data["permissions"], list)
    assert set(data["permissions"]) == set(PERMISSIONS[UserRole.employee])


async def test_get_me_expired_token(client, db, test_employee):
    """Expired token on /me → 401."""
    expired = create_access_token(test_employee["id"], expired=True)
    resp = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {expired}"},
    )
    assert resp.status_code == 401


# ── RBAC / Roles ────────────────────────────────────────────────────


async def test_role_assignment_creates_role(db, test_employee):
    """Inserting a RoleAssignment record persists correctly."""
    ra = RoleAssignment(
        id=uuid.uuid4(),
        employee_id=test_employee["id"],
        role=UserRole.hr_admin,
        is_active=True,
        assigned_at=datetime.now(timezone.utc),
    )
    db.add(ra)
    await db.flush()

    result = await db.execute(
        select(RoleAssignment).where(
            RoleAssignment.employee_id == test_employee["id"],
        ),
    )
    rows = result.scalars().all()
    assert len(rows) == 1
    assert rows[0].role == UserRole.hr_admin
    assert rows[0].is_active is True


async def test_role_requirement_blocks_low_role(
    client, db, test_employee, auth_headers,
):
    """Employee role cannot access an hr_admin-protected endpoint.

    We register a temporary route that requires hr_admin, then verify
    an employee-role token gets 403.
    """
    from backend.auth.dependencies import require_role

    @client._transport.app.get("/api/v1/test-hr-only")  # type: ignore[union-attr]
    async def _hr_only(emp=_depends_hr_admin):
        return {"ok": True}

    resp = await client.get("/api/v1/test-hr-only", headers=auth_headers)
    assert resp.status_code == 403


# Helper: dependency for the role test above
from fastapi import Depends as _Depends
from backend.auth.dependencies import require_role as _require_role

_depends_hr_admin = _Depends(_require_role(UserRole.hr_admin))


async def test_multiple_roles_highest_used(
    client, db, test_employee, test_department, test_location, mock_google_oauth,
):
    """User with employee + hr_admin roles → gets hr_admin permissions on login."""
    # Assign hr_admin role
    ra = RoleAssignment(
        id=uuid.uuid4(),
        employee_id=test_employee["id"],
        role=UserRole.hr_admin,
        is_active=True,
        assigned_at=datetime.now(timezone.utc),
    )
    db.add(ra)
    await db.flush()

    # Login via Google OAuth
    with mock_google_oauth(email=test_employee["email"]):
        resp = await client.post(
            "/api/v1/auth/google",
            json={"code": "valid-code", "redirect_uri": "http://localhost:3000/callback"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["user"]["role"] == UserRole.hr_admin.value


# ── Session management ──────────────────────────────────────────────


async def test_session_ip_recorded(
    client, db, test_employee, mock_google_oauth,
):
    """Login creates a UserSession with the client IP stored."""
    with mock_google_oauth(email=test_employee["email"]):
        resp = await client.post(
            "/api/v1/auth/google",
            json={"code": "valid-code", "redirect_uri": "http://localhost:3000/callback"},
        )
    assert resp.status_code == 200

    # Check session in DB
    async with TestSessionFactory() as session:
        result = await session.execute(
            select(UserSession).where(
                UserSession.employee_id == test_employee["id"],
            ),
        )
        user_session = result.scalars().first()
    assert user_session is not None
    # httpx ASGI transport reports the client as the test host
    assert user_session.ip_address is not None or user_session.ip_address == ""


async def test_concurrent_sessions_allowed(
    client, db, test_employee, mock_google_oauth,
):
    """Same user can have multiple active sessions simultaneously."""
    tokens = []
    for _ in range(2):
        with mock_google_oauth(email=test_employee["email"]):
            resp = await client.post(
                "/api/v1/auth/google",
                json={"code": f"code-{uuid.uuid4().hex[:8]}", "redirect_uri": "http://localhost:3000/callback"},
            )
        assert resp.status_code == 200
        tokens.append(resp.json()["access_token"])

    # Both tokens should work for /me
    for token in tokens:
        resp = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["email"] == test_employee["email"]
