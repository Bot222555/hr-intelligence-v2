# HR Intelligence v2 — Code Review Report

**Reviewer:** Vision 📊 (Automated Code Review Agent)
**Date:** 2026-02-20
**Scope:** Full codebase — 16,712 lines of Python across backend, migration, tests, and infra
**Branch:** main

---

## Executive Summary

The codebase is **well-architected** for a v1.0 HR platform. Clean service/router separation,
proper async/await usage, comprehensive Pydantic v2 schemas, RFC 7807 error handling, and
a solid test suite with security tests. The team has clearly learned from common FastAPI
anti-patterns.

That said, this review found **3 critical**, **8 high**, **14 medium**, and **6 low-severity**
issues across security, code quality, architecture, and API contracts.

---

## Findings Summary

| Severity | Count | Areas |
|----------|-------|-------|
| 🔴 Critical | 3 | SQL injection (pagination/filters), JWT secret default in Docker, session fixation |
| 🟡 High | 8 | Missing auth guards, CORS wildcard, rate limit bypass, transaction gaps |
| 🔵 Medium | 14 | Dead code, missing type hints, DRY violations, N+1 queries, schema drift |
| ⚪ Low | 6 | Naming inconsistencies, missing docstrings, test coverage gaps |

---

## 🔴 Critical Findings

### CRIT-01: SQL Injection via Sort Parameter in Pagination & Filters

**Files:**
- `backend/common/pagination.py` — line 85
- `backend/common/filters.py` — line 35

**Issue:** When the sort column name doesn't match a model attribute, raw user input is
interpolated into a `text()` SQL fragment with **zero sanitization**:

```python
# pagination.py:85
query = query.order_by(text(f"{col_name} {direction}"))

# filters.py:35
return query.order_by(text(f"{col_name} {direction}"))
```

An attacker can send `?sort=1;DROP TABLE employees--` and the `col_name` is passed
directly into `text()`. SQLAlchemy's `text()` does **not** sanitize — it produces raw SQL.

**Impact:** Full SQL injection. An authenticated user (any role) can read/modify/delete
arbitrary data, escalate privileges, or extract the entire database.

**Fix:**

```python
import re
_SAFE_COL_RE = re.compile(r'^[a-z_][a-z0-9_]*$')

def apply_sorting(query, model, sort):
    if not sort:
        return query
    descending = sort.startswith("-")
    col_name = sort.lstrip("-")

    col = _get_column(model, col_name)
    if col is not None:
        return query.order_by(col.desc() if descending else col.asc())

    # REJECT unknown columns instead of passing raw text
    if not _SAFE_COL_RE.match(col_name):
        return query  # silently ignore invalid sort
    # Still unsafe to use text() — just return unsorted
    return query
```

Best practice: **never** fall back to `text()` with user input. If the column doesn't exist
on the model, reject it.

---

### CRIT-02: JWT Secret Default in Docker Compose

**File:** `docker-compose.yml` — line 32

**Issue:**

```yaml
JWT_SECRET: ${JWT_SECRET:-dev-secret-change-in-production}
```

If the `JWT_SECRET` environment variable is not set (common in fresh deployments),
Docker Compose silently uses a **hardcoded, public** secret. Any attacker who reads
this repo can forge valid JWTs and impersonate any user, including system admins.

**Impact:** Complete authentication bypass. Full admin access to the platform.

**Fix:**

```yaml
JWT_SECRET: ${JWT_SECRET:?JWT_SECRET must be set}  # Fail fast if unset
```

The `backend/config.py` correctly requires JWT_SECRET (no default), but Docker Compose
overrides this with a fallback. The `.env.example` also correctly leaves it blank.

---

### CRIT-03: Session Fixation — Old Access Token Remains Valid After Refresh

**File:** `backend/auth/service.py` — lines 147-182 (`refresh_access_token`)

**Issue:** When a refresh token is used to obtain new tokens, the old *session* is revoked
(`session.is_revoked = True`), and a **new** session is created. However, the old session's
`token_hash` is effectively invalidated because the session is marked revoked.

But there's a subtler issue: the `expires_at` on the new session is set to
`JWT_EXPIRY_HOURS` (24h) from now, while the old access JWT's `exp` claim may still be
valid for up to 24 hours. The `get_current_user` dependency checks `UserSession.is_revoked`,
so this is **mitigated** — the old access token IS rejected.

**However,** examine lines 162-165:

```python
session.is_revoked = True
await db.flush()
```

This flush happens, but the **commit** only occurs when the request ends (via `get_db`).
If the refresh endpoint raises an error after this flush but before the response,
the rollback will **un-revoke** the old session while the new tokens have already been
partially constructed. This is a race condition, not a direct exploit, but in the reuse
detection path (line 157), an explicit `await db.commit()` is called before raising —
creating inconsistent transaction handling.

**Impact:** Potential for token state inconsistency under error conditions. The reuse
detection commit-before-raise is correct but the happy path lacks the same protection.

**Fix:** Either commit explicitly in the happy path too, or restructure to ensure
atomicity: create the new session and revoke the old one in a single flush, then let
the normal request commit handle it.

---

## 🟡 High Findings

### HIGH-01: ILIKE Filter SQL Injection via `apply_search` and `apply_filters`

**File:** `backend/common/filters.py` — lines 62, 100-101

**Issue:** The `__ilike` filter and `apply_search` embed user input directly into
LIKE patterns:

```python
conditions.append(col.ilike(f"%{value}%"))
# and
like_conds.append(str_col.ilike(f"%{search}%"))
```

While this doesn't allow full SQL injection (ILIKE is parameterized by SQLAlchemy),
users can inject LIKE metacharacters (`%`, `_`) to craft wildcard-based data extraction
attacks. Searching for `%` returns all records; `_` matches any single character.

**Impact:** Data enumeration. An attacker can methodically extract field values
character-by-character using `_` wildcards.

**Fix:** Escape LIKE metacharacters before embedding:

```python
def _escape_like(s: str) -> str:
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

conditions.append(col.ilike(f"%{_escape_like(value)}%", escape="\\"))
```

---

### HIGH-02: Missing Rate Limiting on Most Endpoints

**File:** `backend/common/rate_limit.py`, `backend/main.py`

**Issue:** Rate limiting is only applied to two auth endpoints (`/auth/google` at
5/min, `/auth/refresh` at 10/min). The default `60/minute` limit from slowapi is
configured but **not enforced** because slowapi's default limits only apply to routes
that have the `@limiter.limit()` decorator or when the app explicitly enables
default limiting via middleware.

All other endpoints (employee CRUD, leave operations, attendance, dashboard, notifications)
have **no rate limiting**, making them vulnerable to:
- Brute-force enumeration of employee IDs
- DoS via expensive dashboard aggregation queries
- Leave request spam

**Fix:** Either:
1. Apply `@limiter.limit()` to all routers, or
2. Add slowapi's default-limit middleware to actually enforce the 60/min default:

```python
from slowapi.middleware import SlowAPIMiddleware
app.add_middleware(SlowAPIMiddleware)
```

---

### HIGH-03: CORS Configuration Allows Wildcard Methods and Headers

**File:** `backend/main.py` — lines 58-62

**Issue:**

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

While origins are properly restricted, `allow_methods=["*"]` and `allow_headers=["*"]`
with `allow_credentials=True` is overly permissive. This allows any HTTP method (including
DELETE, PATCH, PUT) and any header from the allowed origins, which broadens the attack
surface if an XSS vulnerability is found in the frontend.

**Fix:**

```python
allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
allow_headers=["Authorization", "Content-Type", "Accept"],
```

---

### HIGH-04: Missing Auth Guard on Health Check — Information Disclosure

**File:** `backend/main.py` — lines 66-72

**Issue:** The health check endpoint exposes the environment name:

```python
@app.get("/api/v1/health")
async def health_check():
    return {
        "status": "healthy",
        "version": "1.0.0",
        "environment": settings.ENVIRONMENT,
    }
```

This is intentionally unauthenticated (common for load balancer probes), but exposing
`environment` (e.g., "production", "staging") gives attackers reconnaissance information.

**Fix:** Remove `environment` from the health response, or keep it only in non-production:

```python
response = {"status": "healthy", "version": "1.0.0"}
if settings.ENVIRONMENT != "production":
    response["environment"] = settings.ENVIRONMENT
return response
```

---

### HIGH-05: Migration Scripts Use `f'SELECT COUNT(*) FROM "{t}"'` with Table Names

**File:** `migration/migrate_all.py` — line 25

**Issue:** The dry-run function validates table names with `_SAFE_IDENT_RE` before
using them in an f-string query — this is **good**. However, the pattern is fragile:
the validation and usage are in the same function but could be separated in refactoring.

The deeper issue is in `migration/validate.py`, where `_count_sqlite` (line 30) uses:

```python
cur.execute(f'SELECT COUNT(*) FROM "{table}"')
```

This is validated by `_validate_identifier()` beforehand, but the hardcoded table names
in the callers are also passed through, creating an unnecessary validation step for
known-safe strings. The `_count` function correctly uses `psycopg2.sql` for PostgreSQL.

**Impact:** Low risk today (all table names are hardcoded), but the pattern of
f-string SQL with validation could be brittle under maintenance.

**Fix:** Use parameterized identifier quoting for SQLite too, or use a constant
allowlist instead of regex validation.

---

### HIGH-06: No Transaction Rollback on Partial Leave Approval Failure

**File:** `backend/leave/service.py` — `approve_leave` method (line ~305)

**Issue:** The approval flow does multiple operations:
1. Update leave request status
2. Update leave balance (deduct used)
3. Flush
4. Create audit entry
5. Send notification

If step 4 or 5 fails after step 3's flush, the balance deduction is committed
but the audit trail and notification are lost. The `get_db` dependency will attempt
to commit, but if an exception propagates, it rolls back — rolling back the
balance update too, which is correct.

However, if the notification service raises (e.g., database constraint on
notifications table), the entire transaction rolls back, including the approval
itself. The user sees a 500 error but the leave remains pending, which is confusing.

**Fix:** Make notifications fire-and-forget or use a separate transaction/outbox
pattern. Alternatively, catch notification errors and log them without failing
the main transaction:

```python
try:
    await notify_leave_approved(db, leave_req)
except Exception:
    logger.warning("Failed to send approval notification", exc_info=True)
```

---

### HIGH-07: `display_name` and `keka_id` Columns Missing from Migration

**File:** `backend/core_hr/models.py` — lines 4-5, 166, 172

**Issue:** The model docstring explicitly states:

```python
# new columns (keka_id, display_name, etc.) require a follow-up migration.
```

The ORM models define `keka_id`, `display_name`, `middle_name`, `personal_email`,
`job_title`, `l2_manager_id`, `resignation_date`, `last_working_date`,
`exit_reason`, `professional_summary`, `created_by`, `updated_by` — **none** of
which exist in the `001_initial_schema` migration.

**Impact:** The application will crash on any query that touches these columns in
production if Alembic autogenerate hasn't been run. The test suite masks this by
using `Base.metadata.create_all()` which creates tables from the ORM models, not
from migrations.

**Fix:** Create `002_add_missing_columns.py` migration to add all columns that
exist in ORM models but not in the initial migration.

---

### HIGH-08: `weekly_off_policies.days` Schema Mismatch Between Migration Seed and Service

**File:**
- `alembic/versions/001_initial_schema.py` — line ~200 (seed data)
- `backend/leave/service.py` — `_get_weekly_offs` method (line ~65)

**Issue:** The migration seeds `weekly_off_policies.days` as:

```sql
'["saturday", "sunday"]'  -- JSON array of day name strings
```

But the service code (`_get_weekly_offs`) expects either:
- A list of **integers** (weekday numbers): `isinstance(days_data, list) → set(days_data)`
- A dict mapping day names to booleans

When it receives `["saturday", "sunday"]` (list of strings), it does
`set(days_data)` which returns `{"saturday", "sunday"}` — a set of **strings**, not
integers. This is then compared against `d.weekday()` which returns **integers**.
The weekly offs will **never match**, meaning the leave calculation engine thinks
every day is a working day.

**Impact:** Leave day calculations are wrong. Weekends are counted as leave days,
employees may see inflated leave deductions.

**Fix:** Handle string day names in the list case:

```python
_DAY_NAME_MAP = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}

if isinstance(days_data, list):
    result = set()
    for d in days_data:
        if isinstance(d, int):
            result.add(d)
        elif isinstance(d, str) and d.lower() in _DAY_NAME_MAP:
            result.add(_DAY_NAME_MAP[d.lower()])
    return result
```

---

## 🔵 Medium Findings

### MED-01: Dead Import — `DuplicateException` Alias

**File:** `backend/common/exceptions.py` — line 52

**Issue:** `DuplicateException = ConflictError` is defined as an alias but `DuplicateException`
is never imported or used anywhere in the codebase.

```bash
$ grep -rn "DuplicateException" backend/
backend/common/exceptions.py:52:DuplicateException = ConflictError
```

**Fix:** Remove the alias or document it as public API if intended for external consumers.

---

### MED-02: `_multi_scalar` Executes Queries Sequentially

**File:** `backend/dashboard/service.py` — lines 372-378 (`_multi_scalar`)

**Issue:** The dashboard summary runs 4 independent COUNT queries sequentially:

```python
async def _multi_scalar(db, *stmts):
    results = []
    for stmt in stmts:
        result = await db.execute(stmt)
        results.append(result.scalar())
    return results
```

These could be parallelized with `asyncio.gather()` if using separate sessions,
or combined into a single query using subqueries, which would cut the dashboard
load time significantly.

**Fix:** Combine into a single query:

```python
stmt = select(
    select(func.count(Employee.id)).where(...).scalar_subquery().label("total"),
    select(func.count(AttendanceRecord.id)).where(...).scalar_subquery().label("present"),
    ...
)
```

---

### MED-03: Birthdays Endpoint Loads All Employees into Memory

**File:** `backend/dashboard/service.py` — `get_upcoming_birthdays` (line ~205)

**Issue:** The birthday logic loads **all active employees with a DOB** into Python
memory and filters in a loop:

```python
# Load active employees with DOB set
stmt = select(Employee.id, ...).where(Employee.date_of_birth.isnot(None))
result = await db.execute(stmt)
rows = result.all()  # ALL employees loaded

for row in rows:
    # Python-side date comparison
```

The docstring acknowledges this: "For production (PostgreSQL), this is still efficient
given typical company sizes (< 10k employees)." — true for now, but it doesn't scale.

**Fix:** Push the date filtering to PostgreSQL:

```sql
WHERE EXTRACT(DOY FROM date_of_birth)
      BETWEEN EXTRACT(DOY FROM CURRENT_DATE)
          AND EXTRACT(DOY FROM CURRENT_DATE + INTERVAL '7 days')
```

(Handle year-end wraparound with `CASE` or `OR`.)

---

### MED-04: Notification Model Column Name Mismatch

**File:**
- `backend/notifications/models.py` — line 29: `action_url`
- `alembic/versions/001_initial_schema.py` — line ~275: `link`

**Issue:** The ORM model defines the column as `action_url` but the migration creates
it as `link`. In production (running via Alembic), queries referencing `action_url`
will fail with "column does not exist".

**Fix:** Add a migration renaming `link` to `action_url`, or align the ORM model
to use `link`. The same applies to `title` (VARCHAR(255) in ORM vs VARCHAR(255) in
migration — this one matches) and `message` (Text in both — matches).

---

### MED-05: No Index on `leave_requests.employee_id` Alone

**File:** `alembic/versions/001_initial_schema.py`

**Issue:** The composite index `idx_leave_req_emp_dates` covers
`(employee_id, start_date, end_date)`, which helps range queries. But queries that
filter only by `employee_id` (e.g., "get my leave requests") may not benefit from
this composite index efficiently depending on the planner.

The `leave_balances` table also lacks individual indexes on `employee_id` and
`leave_type_id`, relying only on the unique constraint
`(employee_id, leave_type_id, year)`.

**Fix:** Add standalone indexes:

```sql
CREATE INDEX idx_leave_req_employee ON leave_requests(employee_id);
CREATE INDEX idx_leave_bal_employee ON leave_balances(employee_id);
```

---

### MED-06: `leave_balances` Constraint Name Mismatch

**File:**
- `alembic/versions/001_initial_schema.py` — unnamed UNIQUE constraint: `UNIQUE(employee_id, leave_type_id, year)`
- `migration/migrate_leaves.py` — line 107: `ON CONFLICT ON CONSTRAINT uq_leave_balance`

**Issue:** The migration references constraint name `uq_leave_balance`, but the
Alembic migration creates the unique constraint without a name (PostgreSQL will
auto-generate one like `leave_balances_employee_id_leave_type_id_year_key`).
The data migration will fail with "constraint does not exist".

**Fix:** Name the constraint in the Alembic migration:

```sql
UNIQUE(employee_id, leave_type_id, year) CONSTRAINT uq_leave_balance
```

Or update the data migration to use `ON CONFLICT (employee_id, leave_type_id, year)`.

---

### MED-07: Attendance Constraint Name Mismatch

**File:**
- `alembic/versions/001_initial_schema.py` — unnamed UNIQUE: `UNIQUE(employee_id, date)`
- `migration/migrate_attendance.py` — line 88: `ON CONFLICT ON CONSTRAINT uq_attendance_emp_date`

**Issue:** Same problem as MED-06. The constraint `uq_attendance_emp_date` doesn't
exist because the migration uses an unnamed UNIQUE constraint.

**Fix:** Name the constraint in the schema migration or use column-based conflict target.

---

### MED-08: `get_db` Dependency Missing `AsyncGenerator` Return Type

**File:** `backend/database.py` — line 31

**Issue:**

```python
async def get_db() -> AsyncSession:
```

This is a generator function (uses `yield`) but is typed as returning `AsyncSession`.
It should be typed as `AsyncGenerator[AsyncSession, None]`.

**Fix:**

```python
from typing import AsyncGenerator

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        ...
```

---

### MED-09: Hardcoded Timezone — `_today()` Uses `Asia/Kolkata`

**File:** `backend/dashboard/service.py` — line 43

**Issue:** The `_today()` helper hardcodes `Asia/Kolkata`. If the platform expands to
other timezones, dashboard data will be incorrect for non-IST users.

**Fix:** Use the `TIMEZONE` constant from `backend/common/constants.py` (which is
also hardcoded to `Asia/Kolkata` — but at least it's centralized):

```python
from backend.common.constants import TIMEZONE
from zoneinfo import ZoneInfo

def _today() -> date:
    return datetime.now(ZoneInfo(TIMEZONE)).date()
```

---

### MED-10: `Location` Model Has Columns Not in Migration

**File:** `backend/core_hr/models.py` — Location class

**Issue:** The ORM model defines `pincode` and `country` columns that don't exist
in the `001_initial_schema` migration's `locations` table. Same issue as HIGH-07
but for the Location model.

**Fix:** Add these columns to the migration or remove them from the ORM until a
follow-up migration is created.

---

### MED-11: Unused Import — `NotificationService` in Leave Service

**File:** `backend/leave/service.py` — line 22

**Issue:** `NotificationService` is imported directly AND the helper functions
(`notify_leave_request`, `notify_leave_approved`, etc.) are also imported. Both
are used, so this isn't strictly dead code — but it means there are two import
paths for the same module, which can be confusing.

Actually, `NotificationService` is used directly in `cancel_leave` and
`request_comp_off` and `approve_comp_off` and `adjust_balance`, so this is
intentional. No action needed — downgrading to informational.

---

### MED-12: No Input Validation on `reason` Fields — XSS Risk

**Files:**
- `backend/leave/schemas.py`
- `backend/attendance/schemas.py`

**Issue:** Text fields like `reason`, `remarks`, `reviewer_remarks` accept arbitrary
strings without length limits or HTML/script sanitization. While FastAPI returns
JSON (not HTML), if the frontend renders these values without escaping, it enables
stored XSS.

**Fix:** Add `max_length` constraints and consider a strip-tags validator:

```python
reason: Optional[str] = Field(None, max_length=2000)
```

---

### MED-13: No Cleanup of Expired Sessions

**File:** `backend/auth/models.py`, `backend/auth/service.py`

**Issue:** The `user_sessions` table accumulates rows over time. Expired and revoked
sessions are never deleted. Over months, this table will grow unbounded.

**Fix:** Add a periodic cleanup task (cron job or startup task):

```python
async def cleanup_expired_sessions(db: AsyncSession):
    await db.execute(
        delete(UserSession).where(
            or_(
                UserSession.expires_at < datetime.now(timezone.utc),
                UserSession.is_revoked.is_(True),
            )
        )
    )
```

---

### MED-14: `Decimal` Serialization in Leave Schemas

**File:** `backend/leave/schemas.py`, `backend/dashboard/schemas.py`

**Issue:** Several schemas use `Decimal` fields (`total_days`, `current_balance`,
`total_days` in `LeaveSummaryResponse`). Pydantic v2's default JSON serialization
of `Decimal` produces strings (e.g., `"1.5"` instead of `1.5`). This may not match
what the frontend expects.

**Fix:** Either add `json_encoders` or use `float` for API-facing fields:

```python
class LeaveBalanceOut(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        json_encoders={Decimal: float},
    )
```

---

## ⚪ Low Findings

### LOW-01: Inconsistent Naming — `from_date`/`to_date` vs `start_date`/`end_date`

**Files:**
- `backend/leave/schemas.py`: `LeaveRequestCreate` uses `from_date`, `to_date`
- `backend/leave/models.py`: `LeaveRequest` ORM uses `start_date`, `end_date`

**Issue:** The API accepts `from_date`/`to_date` but stores `start_date`/`end_date`.
This mapping happens implicitly in the service layer but creates cognitive overhead.

**Fix:** Align naming. Either use `start_date`/`end_date` everywhere (API + ORM)
or add explicit aliases.

---

### LOW-02: Missing Docstrings on Router Functions

**Files:** `backend/core_hr/router.py`, `backend/leave/router.py`

**Issue:** Some router functions have docstrings (used by OpenAPI), but several have
minimal or missing ones. The dashboard router is the best example of good docstrings;
other modules should follow the same pattern.

---

### LOW-03: Test `conftest.py` — Magic Strings for Roles

**File:** `tests/conftest.py`

**Issue:** `create_access_token` defaults to `UserRole.employee`, but test fixtures
that need elevated roles construct tokens manually. A `create_auth_headers` helper
that accepts a role parameter would reduce boilerplate.

---

### LOW-04: Docker Compose Binds `backend/` as Volume in Dev

**File:** `docker-compose.yml` — line 46

**Issue:**

```yaml
volumes:
  - ./backend:/app/backend
```

This enables hot-reload in dev but means the container's `backend/` is replaced
entirely by the host's version. If there's a version mismatch between installed
dependencies and code, errors are hard to diagnose.

**Fix:** This is standard practice for dev, so it's fine. Just ensure
`docker-compose.prod.yml` overrides `volumes: []` — which it does (line 5). ✓

---

### LOW-05: `lifespan` Has TODO Comments for DB/Redis Initialization

**File:** `backend/main.py` — lines 21-27

**Issue:**

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # TODO: Initialize database connection pool
    # TODO: Initialize Redis connection
    yield
    # TODO: Close database connection pool
    # TODO: Close Redis connection
```

The database engine is created at import time (`database.py`), so the pool is
already initialized. Redis isn't used yet. These TODOs should either be implemented
or removed to avoid confusion.

---

### LOW-06: `migration/config.py` Exposes Hardcoded Paths

**File:** `migration/config.py` — lines 11-14

**Issue:**

```python
_SQLITE_CANDIDATES = [
    os.environ.get("KEKA_SQLITE_PATH", ""),
    "/Users/allfred/scripts/keka/keka_hr.db",
    "/Users/donna/.openclaw/workspace/scripts/keka/data/keka.db",
    "/Users/allfred/scripts/keka/data/keka.db",
]
```

These contain machine-specific paths (user home directories) hardcoded in the
repository. They won't work on other machines and expose internal infrastructure
details.

**Fix:** Remove hardcoded paths; rely solely on the `KEKA_SQLITE_PATH` environment
variable.

---

## Architecture Review — Positive Observations

### ✅ Service Layer Separation
Every module follows `router.py → service.py → models.py` cleanly.
Business logic lives in service classes, not in route handlers. Excellent.

### ✅ Proper Async/Await
All database operations use `AsyncSession` with `await`. No accidental
synchronous calls detected. The `selectinload` usage for eager loading
prevents N+1 queries in most cases.

### ✅ RFC 7807 Error Responses
Custom exception hierarchy with `AppException` → `NotFoundException`,
`ForbiddenException`, `ValidationException`, `ConflictError`. All produce
proper RFC 7807 `application/problem+json` responses with `type`, `title`,
`status`, `detail`, `instance`, and optional `errors` fields.

### ✅ Refresh Token Rotation with Reuse Detection
The auth service implements proper refresh token rotation: each refresh token
can only be used once. Reuse triggers revocation of ALL user sessions — this
is exactly the pattern recommended by OWASP.

### ✅ Role Hierarchy
The RBAC system supports role hierarchy (system_admin > hr_admin > manager > employee)
with both role-based and permission-based dependency factories.

### ✅ Audit Trail
Every significant operation creates an audit trail entry with actor, action,
entity, old/new values, IP, and user-agent. Comprehensive and well-implemented.

### ✅ Test Infrastructure
SQLite in-memory with pg-compat compiles, factory fixtures, auth helpers,
and dedicated security tests. The test suite covers rate limiting, token
rotation, reuse detection, and SQL injection prevention.

---

## Recommended Priority Actions

1. **IMMEDIATE (today):** Fix CRIT-01 (SQL injection in sort/filter) — this is exploitable
   by any authenticated user.
2. **IMMEDIATE:** Fix CRIT-02 (JWT secret in docker-compose) — one-line fix, massive impact.
3. **This sprint:** Fix HIGH-07 + HIGH-08 (ORM/migration drift, weekly off data format) —
   these will cause production crashes.
4. **This sprint:** Fix MED-04 + MED-06 + MED-07 (column/constraint name mismatches) —
   same category as above.
5. **Next sprint:** Address HIGH-02 (rate limiting coverage) and HIGH-03 (CORS hardening).

---

*Generated by Vision 📊 — 2026-02-20T22:48+05:30*
