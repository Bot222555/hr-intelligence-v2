# Code Review Report — HR Intelligence v2

**Reviewer:** Automated Code Review (QG1)  
**Date:** 2026-02-20  
**Scope:** Full backend review — auth, core_hr, attendance, leave, notifications, migration, common, config  
**Commit:** main branch (HEAD)

---

## Executive Summary

The HR Intelligence v2 backend is a well-structured FastAPI application with async SQLAlchemy, Google OAuth, JWT-based sessions, role-based access control (RBAC), and comprehensive modules for Core HR, Attendance, Leave, and Notifications. The codebase shows strong architectural fundamentals: proper separation of concerns (router → service → model), Pydantic v2 schema validation, RFC 7807 error responses, comprehensive audit trails, and a clean test setup.

**Overall quality: Good** — the codebase is significantly above average for its stage. However, there are several security issues, missing hardening measures, and code-quality improvements that should be addressed before production deployment.

### Summary of Findings

| Severity | Count | Key Areas |
|----------|-------|-----------|
| 🔴 Critical | 3 | JWT secret default, SQL injection in migration validation, missing rate limiting on auth |
| 🟠 High | 7 | Refresh token not session-bound, CORS wildcard headers, no CSRF protection, missing attendance/leave routers, duplicate AuditTrail model, no password for DB default, token not invalidated on refresh |
| 🟡 Medium | 10 | Missing security headers, no request size limits, pagination unbounded, employer status not enum-validated, missing DB indexes, no session cleanup, inconsistent error codes, SQL echo in dev |
| 🔵 Low | 8 | Dead code, missing docstrings in some schemas, TODO items, test coverage gaps |

---

## 🔴 Critical Issues

### CRIT-1: Hardcoded JWT Secret Default — Authentication Bypass Risk

**File:** `backend/config.py:23`  
**Severity:** 🔴 Critical

The JWT secret has a hardcoded default value that will be used if the environment variable is not set:

```python
JWT_SECRET: str = "dev-secret-change-in-production"
```

If this default leaks (it's in the repo) or is accidentally used in production, **any attacker can forge valid JWTs** for any user/role including `system_admin`.

**Recommendation:**
```python
JWT_SECRET: str = ""  # No default — must fail loudly if not configured

# Add a startup validation:
@model_validator(mode="after")
def _validate_secrets(self):
    if self.ENVIRONMENT == "production" and self.JWT_SECRET in ("", "dev-secret-change-in-production"):
        raise ValueError("JWT_SECRET must be set for production!")
    return self
```

---

### CRIT-2: SQL Injection in Migration Validation Script

**File:** `migration/validate.py:13`  
**Severity:** 🔴 Critical

```python
def _count(cur, table: str) -> int:
    cur.execute(f"SELECT COUNT(*) FROM {table}")  # noqa: S608
    return cur.fetchone()[0]
```

The `table` parameter is interpolated directly into SQL via f-string. While currently only called with hardcoded table names from `count_checks`, the `noqa: S608` suppression shows awareness but the function is still a ticking time bomb — any future caller passing user input would create a SQL injection vector.

**Recommendation:** Use identifier quoting:
```python
from psycopg2 import sql

def _count(cur, table: str) -> int:
    cur.execute(sql.SQL("SELECT COUNT(*) FROM {}").format(sql.Identifier(table)))
    return cur.fetchone()[0]
```

---

### CRIT-3: No Rate Limiting on Authentication Endpoints

**File:** `backend/auth/router.py` (entire file), `backend/main.py`  
**Severity:** 🔴 Critical

There is **zero rate limiting** on any endpoint, particularly:
- `POST /api/v1/auth/google` — OAuth login
- `POST /api/v1/auth/refresh` — Token refresh
- `POST /api/v1/auth/logout` — Logout

An attacker could:
1. Brute-force token refresh with stolen refresh tokens
2. Flood the OAuth endpoint causing Google API rate limit exhaustion (DoS)
3. Create unlimited sessions (no session cap per user)

**Recommendation:** Add `slowapi` or a custom middleware:
```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@router.post("/google")
@limiter.limit("10/minute")
async def google_auth(request: Request, ...):
    ...
```

---

## 🟠 High Severity Issues

### HIGH-1: Refresh Token Not Bound to Session — Token Reuse Attack

**File:** `backend/auth/service.py:107-130`  
**Severity:** 🟠 High

The refresh token is a standalone JWT with no server-side binding:

```python
def _create_refresh_token(employee_id: uuid.UUID) -> str:
    payload = {
        "sub": str(employee_id),
        "type": "refresh",
        "exp": datetime.now(timezone.utc) + timedelta(days=7),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
```

The `refresh_access_token` function (line 133) validates the JWT signature and expiry but does **not** check if the refresh token was revoked or already used. After logout (which only revokes the access token's session), the refresh token remains valid for 7 days.

**Attack scenario:** Steal a refresh token → victim logs out → attacker uses refresh token to get new access token.

**Recommendation:** Store a hash of the refresh token in `UserSession` and verify it during refresh. Revoke the refresh token on logout. Implement refresh token rotation (issue new refresh token on each refresh, invalidate the old one).

---

### HIGH-2: CORS Allows All Methods and All Headers

**File:** `backend/main.py:44-49`  
**Severity:** 🟠 High

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

While `allow_origins` is configurable, `allow_methods=["*"]` and `allow_headers=["*"]` are overly permissive. Combined with `allow_credentials=True`, this weakens CORS protection. A misconfigured `CORS_ORIGINS` (e.g., `["*"]`) would completely disable CORS.

**Recommendation:**
```python
allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
allow_headers=["Authorization", "Content-Type", "Accept"],
```

---

### HIGH-3: No CSRF Protection for Cookie-Based Flows

**File:** `backend/auth/router.py`, `backend/main.py`  
**Severity:** 🟠 High

While the app uses Bearer tokens (not cookies) for auth, there's no CSRF protection middleware. If the frontend ever stores tokens in cookies (common for HTTP-only secure cookies), the app would be vulnerable to CSRF attacks.

**Recommendation:** Add CSRF token middleware or explicitly document that tokens must never be stored in cookies without SameSite/CSRF protection.

---

### HIGH-4: Attendance and Leave Routers Not Registered

**File:** `backend/main.py:59-60`  
**Severity:** 🟠 High

```python
# TODO: app.include_router(attendance_router, prefix="/api/v1/attendance", tags=["attendance"])
# TODO: app.include_router(leave_router, prefix="/api/v1/leave", tags=["leave"])
```

The attendance and leave modules have **complete service layers** with business logic, but the router files are **placeholders** (empty). This means:
1. The attendance clock-in/out, regularization, today's view are all inaccessible via API
2. The leave application, approval, balance, calendar endpoints don't exist
3. All the comprehensive service code is dead code in production

**Recommendation:** Implement the routers or at minimum stub them out so the service layer is accessible.

---

### HIGH-5: Duplicate AuditTrail Model Definition

**File:** `backend/common/audit.py:47-96` and `backend/common/models.py:12-38`  
**Severity:** 🟠 High

The `AuditTrail` model is defined **twice**:
1. In `backend/common/audit.py` (line 47) — used by `create_audit_entry()`
2. In `backend/common/models.py` (line 12) — with slightly different column definitions

The `audit.py` version uses `gen_random_uuid()` as server default, `String(50)` for action/entity_type, and has proper indexes. The `models.py` version uses `uuid_generate_v4()`, `String(100)`, and has a relationship to Employee. SQLAlchemy will raise a `Table already defined` error or one will shadow the other depending on import order.

**Recommendation:** Remove the `AuditTrail` from `backend/common/models.py` and keep only the canonical version in `audit.py`. If both are needed, consolidate them.

---

### HIGH-6: Database Default Credentials in Code

**File:** `backend/config.py:11-12`, `migration/config.py:34-37`  
**Severity:** 🟠 High

```python
# config.py
DATABASE_URL: str = "postgresql+asyncpg://hr_app:password@localhost:5432/hr_intelligence"

# migration/config.py
DATABASE_URL_SYNC = os.environ.get(
    "DATABASE_URL_SYNC",
    "postgresql://hr_app:password@localhost:5432/hr_intelligence",
)
```

Hardcoded database credentials (`hr_app:password`) as defaults. While intended for development, these could easily leak into production.

**Recommendation:** Use empty defaults and fail explicitly in production, similar to CRIT-1.

---

### HIGH-7: Access Token Not Invalidated on Refresh

**File:** `backend/auth/service.py:133-155`  
**Severity:** 🟠 High

When `refresh_access_token` is called, a new access token and session are created, but the **old access token session is not revoked**. This means:
- An attacker who steals an access token can use it even after the legitimate user refreshes
- Sessions accumulate indefinitely in the `user_sessions` table

**Recommendation:** Accept the old access token hash as a parameter and revoke the corresponding session when issuing a new one.

---

## 🟡 Medium Severity Issues

### MED-1: No Security Headers Middleware

**File:** `backend/main.py`  
**Severity:** 🟡 Medium

Missing security headers that should be set on all responses:
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `Strict-Transport-Security` (for HTTPS)
- `X-XSS-Protection: 0` (prefer CSP)
- `Content-Security-Policy`

**Recommendation:** Add a security headers middleware:
```python
@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response
```

---

### MED-2: Pagination page_size Potentially Unbounded

**File:** `backend/common/pagination.py`  
**Severity:** 🟡 Medium

While `MAX_PAGE_SIZE = 100` is defined in constants, I need to verify it's enforced in PaginationParams. If the pagination class doesn't cap `page_size`, a client could request `page_size=999999` and dump entire tables.

The `MAX_PAGE_SIZE` and `DEFAULT_PAGE_SIZE` constants exist in `backend/common/constants.py` but should be enforced via Pydantic validators in PaginationParams.

---

### MED-3: Employee `employment_status` Not Enum-Validated in Schema

**File:** `backend/core_hr/schemas.py:126, 168`  
**Severity:** 🟡 Medium

```python
class EmployeeCreate(BaseModel):
    ...
    # employment_status is not in Create — good, it's set by the system

class EmployeeUpdate(BaseModel):
    employment_status: Optional[str] = None  # ← accepts any string!
```

The `employment_status` field accepts any string, but the database expects specific enum values (`active`, `notice_period`, `relieved`, `absconding`). While the Employee model stores this as a plain string (not SQLAlchemy Enum), invalid values would corrupt data.

**Recommendation:** Use the `EmploymentStatus` enum from constants:
```python
from backend.common.constants import EmploymentStatus
employment_status: Optional[EmploymentStatus] = None
```

---

### MED-4: SQL Echo Enabled in Development Mode

**File:** `backend/database.py:10`  
**Severity:** 🟡 Medium

```python
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.ENVIRONMENT == "development",
    ...
)
```

SQL echo logs all queries including parameters. In development, this could leak sensitive data to logs (employee PII, tokens, etc.).

**Recommendation:** Use `echo=False` or at minimum `echo="debug"` which requires explicit log level configuration.

---

### MED-5: No Session Cleanup / Expiry Mechanism

**File:** `backend/auth/models.py` (UserSession table)  
**Severity:** 🟡 Medium

Expired and revoked sessions are never cleaned up. The `user_sessions` table will grow indefinitely. With 24h token expiry and no cleanup:
- 284 active employees × multiple sessions per day = thousands of orphaned rows per month

**Recommendation:** Add a periodic cleanup task (e.g., cron or background task):
```sql
DELETE FROM user_sessions WHERE expires_at < NOW() - INTERVAL '7 days';
```

---

### MED-6: `get_employee` Called Twice in `create_employee` Router

**File:** `backend/core_hr/router.py:113-118`  
**Severity:** 🟡 Medium

```python
async def create_employee(...):
    employee = await EmployeeService.create_employee(db, body, actor_id=current_user.id)
    detail = await EmployeeService.get_employee(db, employee.id)  # ← redundant DB query
    return {"data": detail.model_dump(mode="json"), ...}
```

After creating the employee, the code immediately does a full `get_employee` with eager loading. This is a redundant query — the just-created employee object could be enriched directly.

**Recommendation:** Return the created employee directly or use the already-loaded data.

---

### MED-7: Migration Scripts Use psycopg2 Directly Without Connection Pooling

**File:** `migration/config.py:35-38`, all `migration/migrate_*.py`  
**Severity:** 🟡 Medium

Migration scripts create raw psycopg2 connections. While acceptable for one-time migrations, they lack:
- Connection pooling
- Retry logic
- Timeout configuration
- Transaction isolation level specification

**Recommendation:** For production migrations, use a connection pool and add timeouts.

---

### MED-8: `_count` in validate.py Uses f-string for Multiple Queries

**File:** `migration/validate.py:73, 83, 88, 93, 122, 137`  
**Severity:** 🟡 Medium

Beyond the `_count` function, `validate.py` has raw SQL queries built with string interpolation in several places. While all current inputs are hardcoded, this pattern is fragile.

---

### MED-9: Attendance Summary Loads All Records Twice

**File:** `backend/attendance/service.py:273-289`  
**Severity:** 🟡 Medium

```python
# Paginate
result = await db.execute(query.offset(offset).limit(page_size))
records = result.scalars().all()

# For summary, load all records in range (not just current page)
all_result = await db.execute(
    select(AttendanceRecord).where(...)
)
all_records = all_result.scalars().all()
```

The summary recalculates by loading **all** records in the date range separately from the paginated query. For large date ranges with many employees, this is inefficient.

**Recommendation:** Compute summary statistics using aggregate SQL queries (COUNT, AVG, SUM with CASE) instead of loading all records into Python.

---

### MED-10: Leave Approval Authority Check Queries DB Every Time

**File:** `backend/leave/service.py:278-290`  
**Severity:** 🟡 Medium

```python
# Check if approver is HR admin (via role assignments)
from backend.auth.models import RoleAssignment
from backend.common.constants import UserRole

hr_check = await db.execute(
    select(RoleAssignment).where(
        RoleAssignment.employee_id == approver_id,
        RoleAssignment.role == UserRole.hr_admin,
        RoleAssignment.is_active.is_(True),
    )
)
```

This DB query for HR role check happens on every approval/rejection call. The role is already available in the JWT token payload and `request.state.user_role` (set by `get_current_user`). However, since the leave service doesn't have access to the request context, it re-queries. This is a design coupling issue — the router should pass the role down.

---

## 🔵 Low Severity Issues

### LOW-1: Placeholder Module Files

**Files:** `backend/dashboard/*.py`, `backend/attendance/router.py`, `backend/leave/router.py`  
**Severity:** 🔵 Low

Multiple files contain only placeholder docstrings. The dashboard module is entirely empty. While understandable for phased development, these should either be implemented or clearly marked as future work.

---

### LOW-2: Missing `__init__.py` Exports

**Files:** Various `__init__.py` files  
**Severity:** 🔵 Low

Most `__init__.py` files are empty. While Python 3 handles this fine with relative imports, explicit `__all__` exports would improve IDE support and documentation.

---

### LOW-3: Inconsistent `display_name` Computation

**Files:** `backend/core_hr/models.py`, `backend/core_hr/schemas.py` (multiple schemas)  
**Severity:** 🔵 Low

`display_name` is computed in multiple places:
1. `Employee.ensure_display_name()` method on the model
2. `@model_validator(mode="before")` in `EmployeeSummary`, `EmployeeListItem`, `EmployeeDetail`
3. `EmployeeCreate._auto_display_name()` validator

This scattered logic creates maintenance burden. Any change to the display name format needs updates in 4+ places.

**Recommendation:** Centralize display_name computation into a single utility function.

---

### LOW-4: Tests Only Cover Auth Module

**Files:** `tests/test_auth.py`, `tests/test_health.py`  
**Severity:** 🔵 Low

Only 16 tests exist (15 auth + 1 health check). No tests for:
- Core HR CRUD operations
- Attendance clock-in/out logic
- Leave application/approval workflow
- Notification CRUD
- Pagination/filtering
- RBAC edge cases

**Recommendation:** Add test suites for each module, particularly the business-critical leave balance and attendance calculation logic.

---

### LOW-5: `alembic/env.py` Missing from Review Scope

**Severity:** 🔵 Low  

The Alembic env.py should be reviewed for proper async configuration and migration strategy.

---

### LOW-6: `CompOffGrant` Approval Has No Status Field

**File:** `backend/leave/models.py:121-147`  
**Severity:** 🔵 Low

The `CompOffGrant` model uses `granted_by IS NOT NULL` as the approval indicator (checked in `leave/service.py:588`). This is fragile — a proper status enum (pending/approved/rejected) would be cleaner and support rejection workflows.

---

### LOW-7: Import Inside Function Bodies

**File:** `backend/leave/service.py:278-279, 336-337`  
**Severity:** 🔵 Low

```python
# Inside approve_leave:
from backend.auth.models import RoleAssignment
from backend.common.constants import UserRole
```

These imports are inside function bodies to avoid circular imports. While functional, this is a code smell indicating tight coupling between modules.

**Recommendation:** Restructure to pass role information from the router layer rather than querying it in the service layer.

---

### LOW-8: Docker Compose Exposes Postgres Port

**File:** `docker-compose.prod.yml` (if ports are mapped)  
**Severity:** 🔵 Low

Ensure the production Docker Compose does not expose PostgreSQL port 5432 to the host network.

---

## Positive Observations ✅

1. **Excellent schema validation** — Pydantic v2 with proper Field constraints (min_length, max_length, ge, le)
2. **Comprehensive audit trail** — Every mutation is logged with before/after values
3. **RFC 7807 error responses** — Consistent, standard error format
4. **Proper async SQLAlchemy** — No blocking DB calls, proper session management with rollback
5. **Well-designed RBAC** — Role hierarchy, permission-based checks, properly separated
6. **Clean migration scripts** — Two-pass employee migration handles circular manager references
7. **Good test infrastructure** — SQLite test fixtures with PG type compilation, proper factory pattern
8. **Thorough leave system** — Sandwich rule, half-day support, weekend/holiday exclusion, balance computation
9. **Session-based JWT** — Token hashes stored server-side, enabling revocation
10. **Proper eager loading** — `selectinload` used consistently to avoid N+1 queries

---

## Recommended Priority Actions

### Immediate (Pre-Production)
1. **Fix JWT secret default** (CRIT-1) — Require environment variable
2. **Add rate limiting** (CRIT-3) — At minimum on auth endpoints
3. **Bind refresh tokens to sessions** (HIGH-1) — Prevent token reuse after logout
4. **Fix CORS configuration** (HIGH-2) — Restrict methods and headers
5. **Add security headers** (MED-1) — Basic HTTP hardening

### Short-Term (Sprint)
6. **Implement attendance and leave routers** (HIGH-4) — Currently dead code
7. **Remove duplicate AuditTrail** (HIGH-5) — Will cause runtime errors
8. **Add session cleanup** (MED-5) — Prevent table bloat
9. **Validate employment_status** (MED-3) — Use enum in schema

### Medium-Term (Backlog)
10. **Expand test coverage** (LOW-4) — Particularly leave balance and attendance calculations
11. **Optimize attendance summary** (MED-9) — Use aggregate queries
12. **Centralize display_name** (LOW-3) — Single source of truth
13. **Fix SQL injection pattern** (CRIT-2) — Use parameterized identifiers in migration

---

*Report generated by automated code review. All file:line references are approximate and should be verified against the current HEAD.*
