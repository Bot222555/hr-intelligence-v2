# Test Quality Gate Report — QG1 (Re-run)

**Date:** 2026-02-20  
**Branch:** main  
**Commit:** 5dc985a40eef581cd97a2c9f791f5ddd8395f6ff  
**Runner:** Python 3.12.12 / macOS arm64 / pytest 8.3.0 + pytest-asyncio 0.24.0  

## ⚠️ Previous Report Was Inaccurate

The prior TEST-QG1.md (commit `de0e63d`) claimed 16/16 tests passed. **This is false.** A full re-run shows **0 passed, 16 errors**. The DDL fix mentioned in that report was never applied to `tests/conftest.py`.

---

## Summary

| Metric | Value |
|--------|-------|
| Total Tests | 16 |
| Passed | 0 |
| Failed | 0 |
| Errors (setup) | **16** |
| Coverage | 40.60% (FAIL — threshold: 85%) |

**Result: ❌ ALL TESTS BROKEN — Cannot create SQLite tables**

---

## Root Cause: Single Blocking Bug

**Every test** fails at the `_setup_db` fixture (conftest.py:96) during `Base.metadata.create_all`.

### Error

```
sqlite3.OperationalError: near "(": syntax error
[SQL: CREATE TABLE locations (
    id CHAR(36) DEFAULT uuid_generate_v4() NOT NULL,
    ...
    created_at DATETIME DEFAULT NOW() NOT NULL,
    updated_at DATETIME DEFAULT NOW() NOT NULL,
    ...
)]
```

### Analysis

The test suite uses **SQLite in-memory** as a lightweight stand-in for PostgreSQL. The conftest.py handles three PG-specific type compilations for SQLite:

1. ✅ `JSONB` → `TEXT`
2. ✅ `INET` → `TEXT`
3. ✅ `PG_UUID` → `CHAR(36)`

It also registers custom SQLite functions (`NOW()`, `uuid_generate_v4()`, `gen_random_uuid()`) via `@event.listens_for(engine.sync_engine, "connect")`.

**However**, this only makes the functions callable at *query time*. SQLite's DDL parser **rejects function calls in `DEFAULT` clauses** unless they are wrapped in parentheses. The generated DDL uses:

```sql
DEFAULT uuid_generate_v4()   -- ❌ SQLite syntax error
DEFAULT NOW()                -- ❌ SQLite syntax error
```

SQLite requires:

```sql
DEFAULT (uuid_generate_v4())  -- ✅ valid
DEFAULT (CURRENT_TIMESTAMP)   -- ✅ valid
```

### Affected Models (every table)

All models use `server_default=sa.text("uuid_generate_v4()")` and `server_default=sa.text("NOW()")`:

| Model File | server_default occurrences |
|------------|---------------------------|
| `backend/core_hr/models.py` | 14 |
| `backend/attendance/models.py` | 28 |
| `backend/leave/models.py` | 18 |
| `backend/auth/models.py` | 6 |
| `backend/notifications/models.py` | 2+ (inherited) |

---

## Fix Required

Add DDL compilation overrides in `conftest.py` to intercept `server_default` text clauses. Two approaches:

### Option A: DDL Event Rewrite (recommended — no model changes)

Add a `before_create` DDL event that rewrites the CREATE TABLE SQL, wrapping bare function calls in parentheses:

```python
from sqlalchemy import event as sa_event
from sqlalchemy.schema import DDL

@sa_event.listens_for(Base.metadata, "before_create")
def _patch_server_defaults(target, connection, **kw):
    """Wrap PG function-call server_defaults in parens for SQLite."""
    for table in target.tables.values():
        for col in table.columns:
            if col.server_default is not None:
                sd = col.server_default
                if hasattr(sd, "arg") and hasattr(sd.arg, "text"):
                    txt = sd.arg.text
                    # Wrap function calls like NOW(), uuid_generate_v4()
                    if "(" in txt and not txt.startswith("("):
                        sd.arg = sa.text(f"({txt})")
```

### Option B: Custom DDL Compiler

Register a `@compiles(CreateColumn, "sqlite")` handler that rewrites DEFAULT clauses.

### Option C: Use `CURRENT_TIMESTAMP` for SQLite

Map `NOW()` → `CURRENT_TIMESTAMP` (a SQLite built-in) and `uuid_generate_v4()` → a hex expression at DDL level.

---

## Coverage Report (from partial load — no tests actually ran)

Coverage below reflects *import-time* code coverage only (models loaded, routers registered), since no test logic executed.

| Module | Stmts | Miss | Cover | Missing |
|--------|-------|------|-------|---------|
| backend/__init__.py | 1 | 0 | 100% | |
| backend/attendance/models.py | 118 | 0 | 100% | |
| backend/attendance/schemas.py | 122 | 122 | **0%** | 9-241 |
| backend/attendance/service.py | 337 | 337 | **0%** | 10-1034 |
| backend/auth/dependencies.py | 68 | 43 | 37% | 34, 39-42, 52-104, 119-126, 136-148 |
| backend/auth/models.py | 32 | 0 | 100% | |
| backend/auth/router.py | 60 | 36 | 40% | 51-100, 124-125, 136-152, 163-184 |
| backend/auth/schemas.py | 44 | 0 | 100% | |
| backend/auth/service.py | 90 | 64 | 29% | 37-67, 77-78, 87-93, etc. |
| backend/common/audit.py | 34 | 5 | 85% | 99, 133-145 |
| backend/common/constants.py | 71 | 0 | 100% | |
| backend/common/exceptions.py | 44 | 21 | 52% | 27-32, 39, 51, 71, etc. |
| backend/common/filters.py | 62 | 54 | **13%** | 24-35, 62-96, 116-137, 144 |
| backend/common/models.py | 29 | 29 | **0%** | 3-56 |
| backend/common/pagination.py | 40 | 17 | 58% | 32-34, 38, 78-101 |
| backend/config.py | 34 | 2 | 94% | 50-51 |
| backend/core_hr/models.py | 110 | 7 | 94% | 76, 140, 314-315, 319-320, 323 |
| backend/core_hr/router.py | 91 | 53 | 42% | 57-64, 93-113, etc. |
| backend/core_hr/schemas.py | 225 | 21 | 91% | 153-155, 215-221, etc. |
| backend/core_hr/service.py | 172 | 135 | **22%** | 64-91, 102-145, etc. |
| backend/database.py | 16 | 8 | 50% | 32-40 |
| backend/dependencies.py | 2 | 2 | **0%** | 3-9 |
| backend/leave/models.py | 80 | 0 | 100% | |
| backend/leave/schemas.py | 139 | 139 | **0%** | 9-287 |
| backend/leave/service.py | 413 | 413 | **0%** | 11-1319 |
| backend/main.py | 25 | 2 | 92% | 25, 57 |
| backend/notifications/models.py | 23 | 0 | 100% | |
| backend/notifications/router.py | 28 | 7 | 75% | 38, 57-58, 70-71, 83-84 |
| backend/notifications/schemas.py | 32 | 0 | 100% | |
| backend/notifications/service.py | 66 | 37 | 44% | 43-54, 66-93, etc. |
| **TOTAL** | **2616** | **1554** | **40.60%** | |

### Zero-Coverage Modules (no tests at all)

| Module | Lines | Priority |
|--------|-------|----------|
| `leave/service.py` | 413 | 🔴 Critical — leave balance engine, sandwich rules |
| `attendance/service.py` | 337 | 🔴 Critical — clock in/out, late detection |
| `attendance/schemas.py` | 122 | 🟡 High — request validation |
| `leave/schemas.py` | 139 | 🟡 High — request validation |
| `core_hr/service.py` | 172 | 🟡 High — employee/dept CRUD |
| `common/models.py` | 29 | 🟢 Low — base model mixins |
| `dependencies.py` | 2 | 🟢 Low — tiny |

---

## Failure Inventory

All 16 tests hit the same error. Categorized by test file:

### tests/test_auth.py — 15 errors

| # | Test | Error Phase |
|---|------|-------------|
| 1 | `test_google_oauth_valid_creativefuel_email` | `_setup_db` fixture |
| 2 | `test_google_oauth_non_creativefuel_email` | `_setup_db` fixture |
| 3 | `test_google_oauth_invalid_code` | `_setup_db` fixture |
| 4 | `test_jwt_generation_has_correct_claims` | `_setup_db` fixture |
| 5 | `test_jwt_expiry_check` | `_setup_db` fixture |
| 6 | `test_refresh_token_generates_new_access` | `_setup_db` fixture |
| 7 | `test_refresh_expired_token` | `_setup_db` fixture |
| 8 | `test_logout_revokes_session` | `_setup_db` fixture |
| 9 | `test_get_me_returns_current_user` | `_setup_db` fixture |
| 10 | `test_get_me_expired_token` | `_setup_db` fixture |
| 11 | `test_role_assignment_creates_role` | `_setup_db` fixture |
| 12 | `test_role_requirement_blocks_low_role` | `_setup_db` fixture |
| 13 | `test_multiple_roles_highest_used` | `_setup_db` fixture |
| 14 | `test_session_ip_recorded` | `_setup_db` fixture |
| 15 | `test_concurrent_sessions_allowed` | `_setup_db` fixture |

### tests/test_health.py — 1 error

| # | Test | Error Phase |
|---|------|-------------|
| 16 | `test_health_check` | `_setup_db` fixture |

---

## Recommendations

### Immediate (P0 — blocks all testing)

1. **Fix conftest.py DDL compatibility** — Add server_default rewriting for SQLite. The `uuid_generate_v4()` and `NOW()` function calls must be parenthesized in DDL, or mapped to SQLite-native equivalents (`CURRENT_TIMESTAMP`, hex UUID expression).

### Short-term (P1 — after DDL fix)

2. **Add tests for leave module** — 413 lines at 0% coverage; this is the most complex business logic (balance calculations, sandwich rules, approval workflows).
3. **Add tests for attendance module** — 337 lines at 0% coverage; clock-in/out logic, late detection, regularization.
4. **Add tests for core_hr service** — Employee/department CRUD at 22%.

### Medium-term (P2)

5. **Fix circular FK warning** — `departments` ↔ `employees` have a circular foreign key. Add `use_alter=True` on the FK from `departments.head_id` → `employees.id`.
6. **Set `asyncio_default_fixture_loop_scope`** in pyproject.toml to silence the pytest-asyncio deprecation.
7. **Target 85% coverage** as specified in pyproject.toml `[tool.coverage.report] fail_under = 85`.

### Meta

8. **Validate test reports** — The prior TEST-QG1.md was committed claiming 16/16 passed without actually fixing the blocking bug. All QG reports should include raw pytest output or CI artifact links.
