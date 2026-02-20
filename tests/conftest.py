"""Shared test fixtures — async DB, client, auth helpers, factories.

Reusable across all test modules (auth, core_hr, attendance, leave, etc.).
Uses SQLite + aiosqlite for fast isolated tests without PostgreSQL.
"""

from __future__ import annotations

import os

# Set test JWT_SECRET before any other import touches pydantic-settings
os.environ.setdefault("JWT_SECRET", "test-secret-for-ci-do-not-use-in-production")

import hashlib
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import AsyncGenerator
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from jose import jwt
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from backend.common.constants import UserRole
from backend.config import settings
from backend.database import Base, get_db
from backend.main import create_app

# Import ALL model modules so SQLAlchemy can resolve cross-module relationships
# (e.g. Employee → LeaveBalance, Notification, etc.)
import backend.auth.models  # noqa: F401
import backend.core_hr.models  # noqa: F401
import backend.leave.models  # noqa: F401
import backend.attendance.models  # noqa: F401
import backend.notifications.models  # noqa: F401
import backend.dashboard.models  # noqa: F401
import backend.salary.models  # noqa: F401
import backend.helpdesk.models  # noqa: F401
import backend.expenses.models  # noqa: F401
import backend.fnf.models  # noqa: F401

# ── SQLite compat: compile PG-specific types to TEXT/BLOB ───────────

from sqlalchemy.dialects.postgresql import INET, JSONB, UUID as PG_UUID
from sqlalchemy.ext.compiler import compiles


@compiles(JSONB, "sqlite")
def _jsonb_sqlite(element, compiler, **kw):
    return "TEXT"


@compiles(INET, "sqlite")
def _inet_sqlite(element, compiler, **kw):
    return "TEXT"


@compiles(PG_UUID, "sqlite")
def _uuid_sqlite(element, compiler, **kw):
    return "CHAR(36)"


# ── Test database (SQLite in-memory) ────────────────────────────────

TEST_DATABASE_URL = "sqlite+aiosqlite://"

engine = create_async_engine(
    TEST_DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)


# Register PG-compatible functions for SQLite
@event.listens_for(engine.sync_engine, "connect")
def _register_sqlite_functions(dbapi_conn, connection_record):
    """Register NOW() and uuid_generate_v4() as SQLite custom functions."""
    dbapi_conn.create_function(
        "NOW", 0, lambda: datetime.now(timezone.utc).isoformat(),
    )
    dbapi_conn.create_function(
        "uuid_generate_v4", 0, lambda: str(uuid.uuid4()),
    )
    dbapi_conn.create_function(
        "gen_random_uuid", 0, lambda: str(uuid.uuid4()),
    )

TestSessionFactory = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False,
)


@pytest.fixture(autouse=True)
async def _setup_db():
    """Create all tables before each test, drop after."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """Reset rate limiter storage between tests to prevent cross-test interference."""
    from backend.common.rate_limit import limiter
    try:
        # Clear the in-memory storage used by slowapi/limits
        if hasattr(limiter, '_storage'):
            limiter._storage.reset()
    except Exception:
        pass
    yield


async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
    async with TestSessionFactory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ── FastAPI test client ─────────────────────────────────────────────

@pytest.fixture
async def app():
    """Create a fresh app instance with DB dependency overridden."""
    application = create_app()
    application.dependency_overrides[get_db] = _override_get_db
    yield application
    application.dependency_overrides.clear()


@pytest.fixture
async def client(app) -> AsyncGenerator[AsyncClient, None]:
    """Async HTTP client wired to the test app."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac


# ── Database session (for direct DB operations in tests) ────────────

@pytest.fixture
async def db() -> AsyncGenerator[AsyncSession, None]:
    async with TestSessionFactory() as session:
        yield session
        await session.commit()


# ── Model factories ─────────────────────────────────────────────────

def _make_location(
    *,
    name: str = "Mumbai HQ",
    city: str = "Mumbai",
    state: str = "Maharashtra",
) -> dict:
    return dict(
        id=uuid.uuid4(),
        name=name,
        city=city,
        state=state,
        timezone="Asia/Kolkata",
        is_active=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def _make_department(
    *,
    name: str = "Engineering",
    code: str = "ENG",
    location_id: uuid.UUID | None = None,
) -> dict:
    return dict(
        id=uuid.uuid4(),
        name=name,
        code=code,
        location_id=location_id,
        is_active=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def _make_employee(
    *,
    email: str = "test.user@creativefuel.io",
    first_name: str = "Test",
    last_name: str = "User",
    department_id: uuid.UUID | None = None,
    location_id: uuid.UUID | None = None,
) -> dict:
    return dict(
        id=uuid.uuid4(),
        employee_code=f"CF-{uuid.uuid4().hex[:6].upper()}",
        first_name=first_name,
        last_name=last_name,
        email=email,
        date_of_joining=date(2024, 1, 15),
        employment_status="active",
        nationality="Indian",
        notice_period_days=90,
        department_id=department_id,
        location_id=location_id,
        is_active=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


@pytest.fixture
async def test_location(db) -> dict:
    """Insert a test location and return its data dict."""
    from backend.core_hr.models import Location

    data = _make_location()
    db.add(Location(**data))
    await db.flush()
    return data


@pytest.fixture
async def test_department(db, test_location) -> dict:
    """Insert a test department linked to test_location."""
    from backend.core_hr.models import Department

    data = _make_department(location_id=test_location["id"])
    db.add(Department(**data))
    await db.flush()
    return data


@pytest.fixture
async def test_employee(db, test_department, test_location) -> dict:
    """Insert an active employee with department + location."""
    from backend.core_hr.models import Employee

    data = _make_employee(
        department_id=test_department["id"],
        location_id=test_location["id"],
    )
    db.add(Employee(**data))
    await db.flush()
    return data


# ── Auth helpers ────────────────────────────────────────────────────

def create_access_token(
    employee_id: uuid.UUID,
    role: UserRole = UserRole.employee,
    expired: bool = False,
) -> str:
    """Generate a JWT access token for testing."""
    if expired:
        exp = datetime.now(timezone.utc) - timedelta(hours=1)
    else:
        exp = datetime.now(timezone.utc) + timedelta(hours=settings.JWT_EXPIRY_HOURS)
    payload = {
        "sub": str(employee_id),
        "role": role.value,
        "type": "access",
        "exp": exp,
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(
    employee_id: uuid.UUID,
    expired: bool = False,
) -> str:
    """Generate a JWT refresh token for testing (with unique jti)."""
    if expired:
        exp = datetime.now(timezone.utc) - timedelta(days=1)
    else:
        exp = datetime.now(timezone.utc) + timedelta(days=7)
    payload = {
        "sub": str(employee_id),
        "type": "refresh",
        "jti": uuid.uuid4().hex,
        "exp": exp,
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


@pytest.fixture
async def auth_headers(db, test_employee) -> dict[str, str]:
    """Return Bearer auth headers with a valid session persisted in the DB."""
    from backend.auth.models import UserSession

    token = create_access_token(test_employee["id"])
    token_hash = hashlib.sha256(token.encode()).hexdigest()

    session = UserSession(
        id=uuid.uuid4(),
        employee_id=test_employee["id"],
        token_hash=token_hash,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=settings.JWT_EXPIRY_HOURS),
        is_revoked=False,
        created_at=datetime.now(timezone.utc),
    )
    db.add(session)
    await db.flush()

    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def mock_google_oauth():
    """Patch verify_google_token to return a fake Creativefuel user."""

    def _mock(email: str = "test.user@creativefuel.io", name: str = "Test User"):
        google_info = {
            "email": email,
            "name": name,
            "picture": "https://lh3.googleusercontent.com/fake",
            "google_id": f"google-{uuid.uuid4().hex[:12]}",
        }
        return patch(
            "backend.auth.router.verify_google_token",
            new_callable=AsyncMock,
            return_value=google_info,
        )

    return _mock
