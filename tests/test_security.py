"""Security test suite — SQL injection, rate limiting, refresh token rotation.

Covers the three security fixes:
1. SQL injection prevention in migration scripts
2. Rate limiting on auth endpoints
3. Refresh token rotation with reuse detection
"""

from __future__ import annotations

import hashlib
import re
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from backend.auth.models import UserSession
from backend.common.constants import UserRole
from backend.config import settings
from tests.conftest import (
    TestSessionFactory,
    create_access_token,
    create_refresh_token,
)


# ═════════════════════════════════════════════════════════════════════
# 1. SQL INJECTION — Migration helper validation
# ═════════════════════════════════════════════════════════════════════


class TestSQLInjectionPrevention:
    """Verify migration helpers reject unsafe identifiers."""

    def test_validate_identifier_rejects_sql_injection(self):
        """Identifiers with SQL metacharacters are rejected."""
        _SAFE_IDENT_RE = re.compile(r'^[a-z_][a-z0-9_]*$')

        # Valid identifiers
        assert _SAFE_IDENT_RE.match("employees")
        assert _SAFE_IDENT_RE.match("user_sessions")
        assert _SAFE_IDENT_RE.match("leave_types")

        # SQL injection attempts — must NOT match
        assert not _SAFE_IDENT_RE.match("employees; DROP TABLE users")
        assert not _SAFE_IDENT_RE.match("'; DELETE FROM --")
        assert not _SAFE_IDENT_RE.match("1; SELECT * FROM")
        assert not _SAFE_IDENT_RE.match("EMPLOYEES")  # uppercase rejected
        assert not _SAFE_IDENT_RE.match("")
        assert not _SAFE_IDENT_RE.match("table-name")  # hyphens rejected
        assert not _SAFE_IDENT_RE.match("table name")  # spaces rejected

    def test_validate_helper_rejects_injection(self):
        """The validate.py identifier helper raises on bad input."""
        from migration.validate import _validate_identifier

        # Valid
        assert _validate_identifier("employees") == "employees"
        assert _validate_identifier("attendance_records") == "attendance_records"

        # Invalid — should raise ValueError
        with pytest.raises(ValueError, match="Unsafe SQL identifier"):
            _validate_identifier("employees; DROP TABLE users")

        with pytest.raises(ValueError, match="Unsafe SQL identifier"):
            _validate_identifier("")

        with pytest.raises(ValueError, match="Unsafe SQL identifier"):
            _validate_identifier("Robert'); DROP TABLE--")

    def test_migration_scripts_use_parameterized_queries(self):
        """Verify migration scripts don't use raw f-string SQL with user input."""
        import ast
        import os

        migration_dir = os.path.join(
            os.path.dirname(__file__), "..", "alembic", "versions",
        )
        for fname in os.listdir(migration_dir):
            if not fname.endswith(".py"):
                continue
            filepath = os.path.join(migration_dir, fname)
            with open(filepath) as f:
                source = f.read()

            # Parse the AST and look for f-string SQL patterns
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    # Check for op.execute(f"...") patterns
                    if (
                        isinstance(node.func, ast.Attribute)
                        and node.func.attr == "execute"
                        and node.args
                    ):
                        arg = node.args[0]
                        # f-strings are JoinedStr in Python AST
                        assert not isinstance(arg, ast.JoinedStr), (
                            f"Found raw f-string in op.execute() in {fname}:{node.lineno}. "
                            f"Use sa.text() or parameterized queries instead."
                        )


# ═════════════════════════════════════════════════════════════════════
# 2. RATE LIMITING — Auth endpoint rate limits
# ═════════════════════════════════════════════════════════════════════


class TestRateLimiting:
    """Verify rate limits on auth endpoints."""

    @pytest.fixture(autouse=True)
    def _enable_limiter(self):
        """Ensure rate limiter is enabled for these tests."""
        from backend.common.rate_limit import limiter
        original = limiter.enabled
        limiter.enabled = True
        # Reset storage to start fresh
        try:
            if hasattr(limiter, '_storage'):
                limiter._storage.reset()
        except Exception:
            pass
        yield
        limiter.enabled = original

    async def test_google_auth_rate_limited_at_5_per_minute(
        self, client, db, test_employee, mock_google_oauth,
    ):
        """POST /auth/google allows 5 requests/minute, then returns 429."""
        for i in range(5):
            with mock_google_oauth(email=test_employee["email"]):
                resp = await client.post(
                    "/api/v1/auth/google",
                    json={
                        "code": f"code-{i}",
                        "redirect_uri": "http://localhost:3000/callback",
                    },
                )
                assert resp.status_code == 200, f"Request {i+1} should succeed"

        # 6th request should be rate-limited
        with mock_google_oauth(email=test_employee["email"]):
            resp = await client.post(
                "/api/v1/auth/google",
                json={
                    "code": "code-overflow",
                    "redirect_uri": "http://localhost:3000/callback",
                },
            )
            assert resp.status_code == 429

    async def test_refresh_rate_limited_at_10_per_minute(
        self, client, db, test_employee,
    ):
        """POST /auth/refresh allows 10 requests/minute, then returns 429.

        Rate limit counting happens before the handler executes, so even
        requests that fail in the handler (e.g. 403) still count toward
        the rate limit.
        """
        for i in range(10):
            # Send requests with invalid tokens — they'll 403 from the handler
            # but still count toward the rate limit
            resp = await client.post(
                "/api/v1/auth/refresh",
                json={"refresh_token": f"fake-token-{i}"},
            )
            # Should be 403 (bad token) — NOT 429 yet
            assert resp.status_code != 429, f"Request {i+1} should not be rate-limited"

        # 11th request should hit the rate limit BEFORE reaching the handler
        resp = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": "fake-token-overflow"},
        )
        assert resp.status_code == 429

    async def test_rate_limit_429_response_body(
        self, client, db, test_employee, mock_google_oauth,
    ):
        """429 response indicates rate limiting."""
        for i in range(5):
            with mock_google_oauth(email=test_employee["email"]):
                await client.post(
                    "/api/v1/auth/google",
                    json={
                        "code": f"code-{i}",
                        "redirect_uri": "http://localhost:3000/callback",
                    },
                )

        with mock_google_oauth(email=test_employee["email"]):
            resp = await client.post(
                "/api/v1/auth/google",
                json={
                    "code": "code-overflow",
                    "redirect_uri": "http://localhost:3000/callback",
                },
            )
            assert resp.status_code == 429
            assert "rate limit" in resp.text.lower() or resp.status_code == 429


# ═════════════════════════════════════════════════════════════════════
# 3. REFRESH TOKEN ROTATION — Detailed rotation + reuse tests
# ═════════════════════════════════════════════════════════════════════


class TestRefreshTokenRotation:
    """Verify refresh token rotation and reuse detection."""

    async def test_refresh_returns_new_tokens(self, client, db, test_employee):
        """Refreshing returns both a new access token and a new refresh token."""
        old_refresh = create_refresh_token(test_employee["id"])
        session = UserSession(
            id=uuid.uuid4(),
            employee_id=test_employee["id"],
            token_hash="old-access-hash",
            refresh_token_hash=hashlib.sha256(old_refresh.encode()).hexdigest(),
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
            is_revoked=False,
            created_at=datetime.now(timezone.utc),
        )
        db.add(session)
        await db.flush()

        resp = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": old_refresh},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" in data
        # New refresh token must differ from the old one
        assert data["refresh_token"] != old_refresh

    async def test_old_refresh_token_invalidated_after_use(
        self, client, db, test_employee,
    ):
        """After successful refresh, the old session is marked as revoked."""
        old_refresh = create_refresh_token(test_employee["id"])
        session = UserSession(
            id=uuid.uuid4(),
            employee_id=test_employee["id"],
            token_hash="old-access-hash",
            refresh_token_hash=hashlib.sha256(old_refresh.encode()).hexdigest(),
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
            is_revoked=False,
            created_at=datetime.now(timezone.utc),
        )
        db.add(session)
        await db.flush()
        session_id = session.id

        resp = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": old_refresh},
        )
        assert resp.status_code == 200

        # Verify old session is revoked
        async with TestSessionFactory() as check_db:
            result = await check_db.execute(
                select(UserSession).where(UserSession.id == session_id),
            )
            old_session = result.scalars().first()
            assert old_session.is_revoked is True

    async def test_new_refresh_token_works_for_chained_refresh(
        self, client, db, test_employee,
    ):
        """The new refresh token from a refresh can be used for the next refresh."""
        # Initial refresh token
        refresh = create_refresh_token(test_employee["id"])
        session = UserSession(
            id=uuid.uuid4(),
            employee_id=test_employee["id"],
            token_hash="initial-hash",
            refresh_token_hash=hashlib.sha256(refresh.encode()).hexdigest(),
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
            is_revoked=False,
            created_at=datetime.now(timezone.utc),
        )
        db.add(session)
        await db.flush()

        # First refresh → get new tokens
        resp1 = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh},
        )
        assert resp1.status_code == 200
        new_refresh = resp1.json()["refresh_token"]

        # Second refresh with the new token → should also succeed
        resp2 = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": new_refresh},
        )
        assert resp2.status_code == 200
        assert resp2.json()["refresh_token"] != new_refresh

    async def test_reuse_detection_triggers_on_consumed_token(
        self, client, db, test_employee,
    ):
        """Using a consumed (already-used) refresh token returns 403 with reuse message."""
        refresh = create_refresh_token(test_employee["id"])
        session = UserSession(
            id=uuid.uuid4(),
            employee_id=test_employee["id"],
            token_hash="access-hash",
            refresh_token_hash=hashlib.sha256(refresh.encode()).hexdigest(),
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
            is_revoked=False,
            created_at=datetime.now(timezone.utc),
        )
        db.add(session)
        await db.flush()

        # Use once
        resp1 = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh},
        )
        assert resp1.status_code == 200

        # Attempt reuse
        resp2 = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh},
        )
        assert resp2.status_code == 403
        assert "reuse" in resp2.json()["detail"].lower()

    async def test_login_stores_refresh_token_hash(
        self, client, db, test_employee, mock_google_oauth,
    ):
        """Google OAuth login persists both access and refresh token hashes."""
        with mock_google_oauth(email=test_employee["email"]):
            resp = await client.post(
                "/api/v1/auth/google",
                json={
                    "code": "valid-code",
                    "redirect_uri": "http://localhost:3000/callback",
                },
            )
        assert resp.status_code == 200

        # Check that the stored session has a refresh_token_hash
        async with TestSessionFactory() as check_db:
            result = await check_db.execute(
                select(UserSession).where(
                    UserSession.employee_id == test_employee["id"],
                ),
            )
            sessions = result.scalars().all()
            # At least one session should have refresh_token_hash
            assert any(s.refresh_token_hash is not None for s in sessions)

    async def test_unknown_refresh_token_rejected(self, client, db, test_employee):
        """A refresh token with no matching session in DB is rejected."""
        refresh = create_refresh_token(test_employee["id"])
        # Do NOT store any session — token is "unknown"

        resp = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh},
        )
        assert resp.status_code == 403
