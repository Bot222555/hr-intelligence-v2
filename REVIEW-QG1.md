# REVIEW-QG1.md — Quality Gate 1: Full Backend Code Review

**Reviewer:** Vision 📊 (AI Code Reviewer)
**Date:** 2026-02-20
**Scope:** All 44 Python files in `backend/` + `migration/` scripts
**Commit:** HEAD at time of review

---

## Executive Summary

The HR Intelligence v2 backend is a well-structured FastAPI application with solid architectural foundations: async SQLAlchemy 2.0, Pydantic v2, proper RBAC with role hierarchy, RFC 7807 error responses, and comprehensive audit trailing. The codebase demonstrates strong engineering discipline in module organization and separation of concerns.

However, this review uncovered **4 Critical**, **7 High**, **12 Medium**, and **10 Low** severity findings that must be addressed before production deployment.

---

## Findings by Severity

---

### 🔴 CRITICAL (Must Fix Before Deploy)

#### C-1: SQL Injection via `text()` in Sorting — ORDER BY Injection

**Files:**
- `backend/common/pagination.py:73-74`
- `backend/common/filters.py:30-32`

**Finding:** When a sort column name is not found as a model attribute, the code falls back to raw `text()` interpolation:

```python
# pagination.py:73-74
direction = "DESC" if descending else "ASC"
query = query.order_by(text(f"{col_name} {direction}"))
```

```python
# filters.py:30-32
direction = "DESC" if descending else "ASC"
return query.order_by(text(f"{col_name} {direction}"))
```

`col_name` comes directly from the user-supplied `sort` query parameter (e.g., `?sort=-some_column`). An attacker can inject arbitrary SQL:

```
GET /api/v1/employees?sort=1;DROP TABLE employees--
```

**Impact:** Full SQL injection — arbitrary read/write/delete on the database.

**Fix:** Remove the `text()` fallback entirely. If the column is not found on the model, raise a `ValidationException` or silently ignore the sort:

```python
if model is not None and hasattr(model, col_name):
    col = getattr(model, col_name)
    query = query.order_by(col.desc() if descending else col.asc())
# else: silently ignore unknown sort column, or raise ValidationException
```

---

#### C-2: Hardcoded JWT Secret with Weak Default

**File:** `backend/config.py:24`

```python
JWT_SECRET: str = "dev-secret-change-in-production"
```

**Finding:** The JWT signing secret has a hardcoded default value. If the `.env` file is missing or `JWT_SECRET` is not set, the application will silently use this publicly-known secret. Any attacker can forge valid JWTs for any user and role (including `system_admin`).

**Impact:** Complete authentication bypass — full system takeover.

**Fix:** Remove the default value and make it a required field. Validate at startup:

```python
JWT_SECRET: str  # No default — will fail to start if not set

@model_validator(mode="after")
def validate_secrets(self):
    if self.ENVIRONMENT == "production" and self.JWT_SECRET == "dev-secret-change-in-production":
        raise ValueError("JWT_SECRET must be changed in production")
    return self
```

---

#### C-3: Duplicate `AuditTrail` Model — ORM Conflict / Table Mapping Ambiguity

**Files:**
- `backend/common/audit.py:51-100` — Defines `AuditTrail` model with `__tablename__ = "audit_trail"`
- `backend/common/models.py:15-41` — Defines **another** `AuditTrail` model with `__tablename__ = "audit_trail"`

**Finding:** Two separate ORM classes map to the same database table `audit_trail`. They have slightly different column definitions (e.g., `id` uses `gen_random_uuid()` in one and `uuid_generate_v4()` in the other; `action` is `String(50)` vs `String(100)`). Both are imported via `backend/common/__init__.py`, which imports from `audit.py`.

SQLAlchemy will raise a runtime error or silently use one definition depending on import order, leading to:
- Unpredictable ORM behavior
- Schema drift between code and database
- Potential data corruption if the wrong model is used

**Impact:** Application crash on startup, or silent data integrity issues.

**Fix:** Delete the duplicate in `common/models.py` and keep only the one in `common/audit.py` (which is the canonical version used by `create_audit_entry()`). Update any imports from `common/models.py` accordingly.

---

#### C-4: Refresh Token Not Tied to Session — Token Replay / Session Bypass

**File:** `backend/auth/service.py:117-149`

**Finding:** During `find_or_create_session()`, only the **access token hash** is stored in the `user_sessions` table. The **refresh token** is not tracked:

```python
session = UserSession(
    employee_id=employee.id,
    token_hash=_hash_token(access_token),  # Only access token tracked
    ...
)
```

During `refresh_access_token()` (line 138), the refresh token is validated purely by JWT signature — there is no server-side revocation check. Even after `logout` (which revokes the access token session), the refresh token remains valid for 7 days.

**Attack scenario:**
1. User logs in → gets access_token + refresh_token
2. User logs out → access token session revoked
3. Attacker uses the refresh_token → gets a new valid access_token
4. Attacker has full access for 7 more days

**Impact:** Logout does not actually revoke access. Stolen refresh tokens cannot be invalidated.

**Fix:** Store the refresh token hash alongside (or instead of) the access token hash in `UserSession`. On refresh, verify the refresh token's session is not revoked. On logout, revoke both.

---

### 🟠 HIGH (Fix Before Production)

#### H-1: CORS Wildcard Methods and Headers

**File:** `backend/main.py:43-49`

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

**Finding:** `allow_credentials=True` combined with `allow_methods=["*"]` and `allow_headers=["*"]` is overly permissive. While `allow_origins` is configurable, the wildcard methods/headers expand the attack surface for CSRF-like attacks via preflight bypass.

**Impact:** Potential cross-origin attack vector when combined with credentials.

**Fix:** Restrict to the methods and headers actually used:

```python
allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
allow_headers=["Authorization", "Content-Type"],
```

---

#### H-2: IDOR in Employee Profile — Manager Access Check Fetches Data Before Authz

**File:** `backend/core_hr/router.py:111-126`

```python
if is_manager:
    # Managers can view their direct reports
    detail = await EmployeeService.get_employee(db, employee_id)  # Fetches FIRST
    if detail.reporting_manager and detail.reporting_manager.id == current_user.id:
        return {...}  # Then checks
    raise ForbiddenException(...)
```

**Finding:** The full employee profile is loaded from the database **before** verifying the manager relationship. While the data isn't returned in the error case, it's still fetched and exists in memory. More critically, the authorization check uses `detail.reporting_manager.id` — but `reporting_manager` could be `None`, which would cause an `AttributeError` crash instead of a clean 403.

**Impact:** Unhandled exception on valid requests; information leakage via timing side-channel.

**Fix:** Check reporting relationship via a direct query first, or guard the None case:

```python
if is_manager:
    # Check relationship before fetching
    report_check = await db.execute(
        select(Employee.reporting_manager_id)
        .where(Employee.id == employee_id)
    )
    mgr_id = report_check.scalar()
    if mgr_id != current_user.id:
        raise ForbiddenException(...)
    detail = await EmployeeService.get_employee(db, employee_id)
```

---

#### H-3: No Rate Limiting on Authentication Endpoints

**Files:**
- `backend/auth/router.py:41` — `/google` endpoint
- `backend/auth/router.py:84` — `/refresh` endpoint

**Finding:** No rate limiting on login (`POST /auth/google`) or token refresh (`POST /auth/refresh`). An attacker can brute-force or flood these endpoints without restriction.

**Impact:** Credential stuffing, token brute-forcing, DoS on auth infrastructure and Google OAuth.

**Fix:** Add `slowapi` or a custom rate limiter middleware. Recommended: 10 req/min per IP on `/auth/google`, 30 req/min on `/refresh`.

---

#### H-4: `get_db()` Auto-Commits on Success — Unintended Side Effects

**File:** `backend/database.py:31-39`

```python
async def get_db() -> AsyncSession:
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()  # Auto-commits after every request
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
```

**Finding:** The database dependency auto-commits after every request handler completes successfully. This means:
1. Read-only endpoints (GET) trigger unnecessary commits
2. If a handler calls `flush()` for intermediate checks but doesn't intend to persist, the data gets committed anyway
3. Half-completed multi-step operations get committed if no exception is raised

**Impact:** Data integrity risk in complex multi-step operations; unnecessary DB load on read endpoints.

**Fix:** Require explicit commits in service layer, or use `session.begin()` context manager:

```python
async def get_db() -> AsyncSession:
    async with async_session_factory() as session:
        yield session
        # No auto-commit — services must explicitly commit
```

---

#### H-5: ILIKE Search Without Input Sanitization — Wildcard Injection

**File:** `backend/common/filters.py:60-62`

```python
if key.endswith("__ilike"):
    col = _get_column(model, key.removesuffix("__ilike"))
    if col is not None:
        conditions.append(col.ilike(f"%{value}%"))
```

**Finding:** User input is directly interpolated into a `LIKE` pattern without escaping `%` and `_` metacharacters. An attacker can craft patterns like `%_%_%_%` that force expensive sequential scans.

**Impact:** Performance-based DoS via expensive LIKE queries; potential data enumeration.

**Fix:** Escape `%` and `_` in the search value:

```python
escaped = value.replace("%", r"\%").replace("_", r"\_")
conditions.append(col.ilike(f"%{escaped}%", escape="\\"))
```

---

#### H-6: Leave Approval Auth Check Missing L2 Manager Consistency with Rejection

**Files:**
- `backend/leave/service.py:320-338` — `approve_leave()` allows L2 manager
- `backend/leave/service.py:372-386` — `reject_leave()` does NOT allow L2 manager

```python
# approve_leave — allows L2
is_l2 = employee.l2_manager_id == approver_id
if not (is_manager or is_l2 or is_hr): raise

# reject_leave — L2 NOT checked
if not (is_manager or is_hr): raise
```

**Finding:** The L2 manager can approve leave but cannot reject it. This is an inconsistent authorization policy that could be a logic bug or an intentional design choice — but it's undocumented and likely unintended.

**Impact:** L2 managers can approve but not reject, creating a broken workflow.

**Fix:** Either add `is_l2` check to `reject_leave()` for consistency, or document the design decision explicitly.

---

#### H-7: Hardcoded Database Password in Default Config

**File:** `backend/config.py:13-14`

```python
DATABASE_URL: str = "postgresql+asyncpg://hr_app:password@localhost:5432/hr_intelligence"
DATABASE_URL_SYNC: str = "postgresql://hr_app:password@localhost:5432/hr_intelligence"
```

**Finding:** Database credentials are hardcoded as default values. Combined with C-2, if the `.env` file is misconfigured, the application connects with known credentials.

**Impact:** Database access with known credentials if `.env` is missing.

**Fix:** Remove default values for production-sensitive config; validate at startup.

---

### 🟡 MEDIUM (Fix Before Beta / First Users)

#### M-1: No Input Validation on JSONB Fields (Address, Emergency Contact)

**File:** `backend/core_hr/schemas.py:138-140`

```python
current_address: Optional[dict[str, Any]] = None
permanent_address: Optional[dict[str, Any]] = None
emergency_contact: Optional[dict[str, Any]] = None
```

**Finding:** Address and emergency contact fields accept `dict[str, Any]` — any arbitrary JSON structure is accepted and stored. An attacker could inject massive nested payloads (MB of JSON) or malicious content.

**Impact:** Storage abuse, potential XSS if rendered unescaped in frontend, data inconsistency.

**Fix:** Use the defined `AddressSchema` and `EmergencyContactSchema` (already defined at lines 17-33 of the same file but not used):

```python
current_address: Optional[AddressSchema] = None
permanent_address: Optional[AddressSchema] = None
emergency_contact: Optional[EmergencyContactSchema] = None
```

---

#### M-2: No Session Cleanup / Expiry Garbage Collection

**Files:**
- `backend/auth/models.py` — `UserSession` has `expires_at` and `is_revoked`
- `backend/main.py:22-27` — TODOs for startup/shutdown

**Finding:** Expired and revoked sessions accumulate indefinitely in the `user_sessions` table. There is no background task, cron job, or lifecycle hook to clean them up. Also, on each refresh, a NEW session row is created (line 143 of `service.py`), so session rows grow linearly with every token refresh.

**Impact:** Unbounded table growth; degraded auth performance over time.

**Fix:** Add a periodic cleanup task (via FastAPI `lifespan`, a cron job, or a DB trigger) that deletes sessions where `expires_at < NOW()` or `is_revoked = TRUE`.

---

#### M-3: Attendance Summary Loads ALL Records in Range (N+1 Variant)

**File:** `backend/attendance/service.py:295-302`

```python
# For summary, load all records in range (not just current page)
all_result = await db.execute(
    select(AttendanceRecord).where(
        AttendanceRecord.employee_id == employee_id,
        ...
    )
)
all_records = all_result.scalars().all()
```

**Finding:** To compute the summary, the service loads ALL attendance records for the date range into Python memory (up to 90 days × N employees for team view). This is done **in addition** to the paginated query, effectively doubling the DB load.

Same pattern in `get_team_attendance()` at line 380.

**Impact:** Memory and DB performance degradation; potential OOM with large teams.

**Fix:** Compute summary via aggregate SQL queries instead of loading all rows:

```python
summary = await db.execute(
    select(
        func.count().filter(AttendanceRecord.status == AttendanceStatus.present).label("present"),
        func.count().filter(AttendanceRecord.status == AttendanceStatus.absent).label("absent"),
        ...
    ).where(...)
)
```

---

#### M-4: `_get_column()` Returns Any Attribute, Not Just Columns

**File:** `backend/common/filters.py:112-114`

```python
def _get_column(model: Any, name: str) -> Optional[InstrumentedAttribute]:
    return getattr(model, name, None)
```

**Finding:** This returns ANY attribute of the model class, including methods, relationships, and internal attributes — not just mapped columns. If a user passes `sort=sessions` or `filter=direct_reports`, it could cause unexpected behavior or SQLAlchemy errors.

**Impact:** Unexpected query errors or information leakage.

**Fix:** Validate that the attribute is actually a mapped column:

```python
from sqlalchemy import inspect as sa_inspect

def _get_column(model, name):
    mapper = sa_inspect(model, raiseerr=False)
    if mapper and name in mapper.columns:
        return getattr(model, name, None)
    return None
```

---

#### M-5: Attendance Router is a Placeholder — Service Has No API Exposure

**Files:**
- `backend/attendance/router.py` — Contains only: `"""attendance — router.py placeholder."""`
- `backend/attendance/service.py` — 600+ lines of fully implemented business logic
- `backend/main.py:63` — Route registration is commented out

**Finding:** The entire attendance module (clock in/out, regularization, admin views) is fully implemented in the service layer but has NO API endpoints. The router is a placeholder and the registration in `main.py` is commented out.

Same issue with:
- `backend/leave/router.py` — placeholder
- `backend/dashboard/router.py` — placeholder

**Impact:** 60%+ of the backend functionality is unreachable. This is not a bug per se, but a significant completeness gap.

**Fix:** Implement the routers for attendance and leave modules, then uncomment the registrations in `main.py`.

---

#### M-6: SQL Echo Enabled in Development — Log Injection Risk

**File:** `backend/database.py:11`

```python
echo=settings.ENVIRONMENT == "development",
```

**Finding:** SQL echo logs every query to stdout, including parameter values. This can leak sensitive data (emails, personal info, tokens) into log files.

**Impact:** Sensitive data leakage via application logs.

**Fix:** Use `echo="debug"` (which only logs when the debug logger is enabled) or disable entirely. Never log query parameters.

---

#### M-7: `WeeklyOffPolicy.days` Accepts Arbitrary JSON

**File:** `backend/attendance/models.py:57`

```python
days: Mapped[dict] = mapped_column(JSONB, nullable=False)
```

**Finding:** The `days` column accepts any JSON value. The service layer (`leave/service.py:83-97`) tries to handle both `list` and `dict` formats, but there's no schema validation at the model or API level.

**Impact:** Invalid data in `days` column causes runtime errors in leave calculation.

**Fix:** Add Pydantic validation when creating/updating weekly off policies.

---

#### M-8: No Timezone Normalization — `datetime.now(timezone.utc)` vs Server Time

**Files:**
- `backend/attendance/service.py:227` — `now = datetime.now(timezone.utc)`
- `backend/common/constants.py:108` — `TIMEZONE = "Asia/Kolkata"`

**Finding:** The attendance service uses UTC for all timestamps (`datetime.now(timezone.utc)`), but attendance is inherently local (shift times, clock-in/out). The shift policy stores times without timezone info (`sa.Time`). When comparing `clock_in_time` (UTC) against `shift.start_time` (local), the arrival status calculation at line 206 will be wrong by +5:30 hours.

**Impact:** Incorrect late/on-time status for all employees. Every employee will appear 5.5 hours early or late depending on direction.

**Fix:** Convert to IST (`Asia/Kolkata`) before comparing against shift times, or store all shift times in UTC.

---

#### M-9: `CompOffCreate.work_date_not_future` Uses `date.today()` — Timezone Unaware

**File:** `backend/leave/schemas.py:171-176`

```python
@field_validator("work_date")
@classmethod
def work_date_not_future(cls, v: date) -> date:
    from datetime import date as _date
    if v > _date.today():
        raise ValueError("work_date cannot be in the future.")
    return v
```

**Finding:** `date.today()` returns the server's local date, which may differ from the user's local date (IST). An employee submitting a comp-off near midnight could be incorrectly rejected or allowed.

**Impact:** Edge-case validation errors near midnight; inconsistent behavior across timezones.

**Fix:** Use timezone-aware comparison with `Asia/Kolkata`.

---

#### M-10: Migration Scripts Have Hardcoded Paths

**File:** `migration/config.py:11-15`

```python
_SQLITE_CANDIDATES = [
    os.environ.get("KEKA_SQLITE_PATH", ""),
    "/Users/allfred/scripts/keka/keka_hr.db",
    "/Users/donna/.openclaw/workspace/scripts/keka/data/keka.db",
    "/Users/allfred/scripts/keka/data/keka.db",
]
```

**Finding:** Migration config contains hardcoded paths referencing specific user home directories on specific machines.

**Impact:** Migration fails on any machine that isn't `allfred` or `donna`. Minor security issue — exposes internal infrastructure paths.

**Fix:** Remove hardcoded paths; rely solely on the `KEKA_SQLITE_PATH` environment variable.

---

#### M-11: No Request Body Size Limit

**File:** `backend/main.py` — No body size middleware configured

**Finding:** FastAPI does not impose a request body size limit by default. Combined with M-1 (arbitrary JSON in JSONB fields), an attacker can send multi-MB request bodies.

**Impact:** Memory exhaustion DoS.

**Fix:** Add a body size limit middleware or use a reverse proxy (nginx) with `client_max_body_size`.

---

#### M-12: Leave Balance Race Condition on Concurrent Requests

**File:** `backend/leave/service.py:267-280`

```python
# Check sufficient balance
balance = bal_result.scalars().first()
pending = await LeaveService._get_pending_days(...)
available = balance.current_balance - pending
if total_days > available:
    raise ValidationException(...)
# ... later ...
db.add(leave_request)
await db.flush()
```

**Finding:** The balance check and leave request creation are not atomic. Two concurrent leave requests from the same employee could both pass the balance check before either is committed, resulting in negative balance.

**Impact:** Employees can overdraw leave balance via concurrent requests.

**Fix:** Use `SELECT ... FOR UPDATE` on the balance row, or add a database-level CHECK constraint on `current_balance >= 0`.

---

### 🟢 LOW (Improve When Convenient)

#### L-1: Unused Import in `auth/router.py`

**File:** `backend/auth/router.py:5`

```python
import hashlib
import uuid  # ← uuid is imported but never used in this file
```

Line 6: `uuid` is imported but never referenced.

Also at line 8: `from sqlalchemy import func, select` — `func` and `select` are imported but not used directly in the router (they're used via service).

---

#### L-2: `EmployeeUpdate.employment_status` and Enum Fields Are `Optional[str]` Not Enum

**File:** `backend/core_hr/schemas.py:158`

```python
employment_status: Optional[str] = None
```

**Finding:** Several fields that map to PostgreSQL enums are typed as `Optional[str]` in the schema, bypassing Pydantic validation. Invalid enum values will only be caught at the database level, producing a 500 instead of a 422.

Also applies to: `gender`, `blood_group`, `marital_status` in both `EmployeeCreate` and `EmployeeUpdate`.

**Fix:** Use the enum types directly: `Optional[EmploymentStatus]`, `Optional[GenderType]`, etc.

---

#### L-3: `get_employee` in Router Calls Service Twice for Manager Case

**File:** `backend/core_hr/router.py:117-126`

```python
if is_manager:
    detail = await EmployeeService.get_employee(db, employee_id)  # Call 1
    if detail.reporting_manager and ...:
        return {"data": detail.model_dump(...)}
    raise ForbiddenException(...)

detail = await EmployeeService.get_employee(db, employee_id)  # Call 2
```

**Finding:** For HR admins or self-access, `get_employee()` is called once. But for managers with valid access, it's already called in the auth check. For non-managers who aren't HR, the first call is wasted. Consider restructuring to call once.

---

#### L-4: `AppSetting` Model Defined but Never Used

**File:** `backend/common/models.py:44-58`

**Finding:** `AppSetting` ORM model is defined but never referenced anywhere in the codebase.

---

#### L-5: Inconsistent `__init__.py` Exports

**Files:**
- `backend/common/__init__.py` — Exports everything (70+ symbols)
- `backend/core_hr/__init__.py` — Exports only models
- `backend/auth/__init__.py` — Empty
- `backend/leave/__init__.py` — Empty
- `backend/attendance/__init__.py` — Empty
- `backend/notifications/__init__.py` — Only a docstring

**Finding:** Module `__init__.py` files are inconsistent. Some export everything, some nothing. This makes import patterns unpredictable.

---

#### L-6: No Logging Framework — Only SQL Echo and Print Statements

**Files:**
- `backend/database.py:11` — SQL echo to stdout
- `migration/*.py` — Uses `print()` statements

**Finding:** The application has no structured logging (no `logging.getLogger`, no `structlog`, no correlation IDs). Debugging in production will be extremely difficult.

**Fix:** Add structured logging with `structlog` or Python's `logging` module with JSON formatter.

---

#### L-7: `EmployeeSummary` / `EmployeeListItem` / `EmployeeDetail` All Duplicate `_build_display_name`

**File:** `backend/core_hr/schemas.py:185, 215, 264`

**Finding:** The same `_build_display_name` model validator is copy-pasted across three schema classes. This violates DRY.

**Fix:** Extract to a base class or mixin:

```python
class DisplayNameMixin(BaseModel):
    @model_validator(mode="before")
    @classmethod
    def _build_display_name(cls, data): ...
```

---

#### L-8: `ensure_display_name()` Called Imperatively Instead of Declaratively

**File:** `backend/core_hr/models.py:266-269`

```python
def ensure_display_name(self) -> None:
    if not self.display_name:
        self.display_name = f"{self.first_name} {self.last_name}".strip()
```

**Finding:** This method must be called manually before serialization. It's easily forgotten (and is indeed called inconsistently — sometimes in service, sometimes in schema validators). Consider using a SQLAlchemy `@validates` or `before_flush` event.

---

#### L-9: No Health Check for Database or Redis Connectivity

**File:** `backend/main.py:55-60`

```python
@app.get("/api/v1/health")
async def health_check():
    return {"status": "healthy", ...}
```

**Finding:** The health check always returns "healthy" regardless of database or Redis connectivity. A load balancer using this endpoint will route traffic to a node that can't serve requests.

**Fix:** Add actual connectivity checks:

```python
async def health_check(db: AsyncSession = Depends(get_db)):
    await db.execute(text("SELECT 1"))
    return {"status": "healthy", "db": "connected", ...}
```

---

#### L-10: Missing Test Coverage for Critical Paths

**File:** `tests/` — Only `test_auth.py`, `test_health.py`, `conftest.py`

**Finding:** The test suite only covers health check and basic auth. No tests exist for:
- RBAC enforcement (role hierarchy, permission checks)
- Employee CRUD with access control
- Leave application with balance validation
- Attendance clock in/out
- Notification delivery
- Pagination, filtering, search
- Edge cases (concurrent requests, timezone boundaries)

**Impact:** No automated safety net for regressions.

---

## Missing Security Controls

| Control | Status |
|---------|--------|
| Rate limiting | ❌ Missing |
| Request body size limit | ❌ Missing |
| CSRF protection | ⚠️ Relies on SameSite cookies (JWT Bearer mitigates) |
| Input sanitization (XSS) | ⚠️ No HTML encoding on JSONB fields |
| SQL injection protection | ❌ ORDER BY injection via `text()` |
| Secrets management | ❌ Hardcoded defaults |
| Session cleanup | ❌ No expiry garbage collection |
| Structured logging | ❌ Missing |
| Error masking (500s) | ⚠️ No generic exception handler — stack traces may leak |

---

## Architecture Observations (Non-Blocking)

1. **Well-designed module boundaries** — Each domain (auth, core_hr, leave, attendance, notifications) has clean model/schema/service/router separation.

2. **Good RBAC foundation** — Role hierarchy with permission-based checks is properly implemented. The `require_role()` and `require_permission()` dependency pattern is clean.

3. **Audit trail is comprehensive** — Every significant mutation creates an audit entry with old/new values, actor, IP, and user-agent.

4. **Pagination pattern is reusable** — The `paginate()` helper with `PaginationParams` dependency is well-designed.

5. **60% of the backend is unrouted** — Attendance, leave, and dashboard modules need routers before the system is functional.

---

## Recommended Priority Order

1. **Immediate (before any deployment):** C-1, C-2, C-3, C-4
2. **Before production:** H-1 through H-7
3. **Before beta users:** M-1, M-3, M-8, M-12
4. **Sprint backlog:** Remaining Medium and Low items

---

*End of review — Vision 📊*
