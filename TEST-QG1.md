# Test Quality Gate Report — QG1

**Date:** 2026-02-20
**Branch:** main
**Commit:** c886bb35533ec24115f812c6283da4e9d3648a52

## Summary

| Metric | Value |
|--------|-------|
| Total Tests | 16 |
| Passed | 16 |
| Failed | 0 |
| Errors | 0 |
| Coverage | 43% |

## Failed Tests

_None — all 16 tests passed._

## Coverage Breakdown (per-module)

| Module | Stmts | Miss | Cover |
|--------|-------|------|-------|
| backend/__init__.py | 1 | 0 | 100% |
| backend/attendance/models.py | 118 | 0 | 100% |
| backend/attendance/schemas.py | 122 | 122 | 0% |
| backend/attendance/service.py | 337 | 337 | 0% |
| backend/auth/dependencies.py | 68 | 27 | 60% |
| backend/auth/models.py | 32 | 0 | 100% |
| backend/auth/router.py | 60 | 25 | 58% |
| backend/auth/schemas.py | 44 | 0 | 100% |
| backend/auth/service.py | 90 | 38 | 58% |
| backend/common/audit.py | 34 | 2 | 94% |
| backend/common/constants.py | 71 | 0 | 100% |
| backend/common/exceptions.py | 44 | 10 | 77% |
| backend/common/filters.py | 62 | 54 | 13% |
| backend/common/models.py | 29 | 29 | 0% |
| backend/common/pagination.py | 40 | 17 | 58% |
| backend/config.py | 34 | 2 | 94% |
| backend/core_hr/models.py | 110 | 7 | 94% |
| backend/core_hr/router.py | 91 | 53 | 42% |
| backend/core_hr/schemas.py | 225 | 21 | 91% |
| backend/core_hr/service.py | 172 | 135 | 22% |
| backend/database.py | 16 | 8 | 50% |
| backend/dependencies.py | 2 | 2 | 0% |
| backend/leave/models.py | 80 | 0 | 100% |
| backend/leave/schemas.py | 139 | 139 | 0% |
| backend/leave/service.py | 413 | 413 | 0% |
| backend/main.py | 25 | 1 | 96% |
| backend/notifications/models.py | 23 | 0 | 100% |
| backend/notifications/router.py | 28 | 7 | 75% |
| backend/notifications/schemas.py | 32 | 0 | 100% |
| backend/notifications/service.py | 66 | 37 | 44% |
| **TOTAL** | **2616** | **1486** | **43%** |

## Notes

### Setup Issues Fixed

- **SQLite DDL compatibility:** The `conftest.py` already compiles PG types (JSONB, INET, PG_UUID) to SQLite equivalents, but `server_default=text("uuid_generate_v4()")` and `server_default=text("NOW()")` caused `sqlite3.OperationalError: near "(": syntax error` during table creation. SQLite DDL does not support bare function calls in `DEFAULT` clauses — they must be wrapped in parentheses: `DEFAULT (uuid_generate_v4())`. A pre-`create_all` patch was added to conftest to wrap function-call defaults in parens.

### Coverage Analysis

- **Coverage is 43%, well below the 85% fail-under threshold.** This is expected — the project currently only has tests for `auth` and `health` modules.
- **Zero coverage modules** (no tests exist): `attendance/service`, `attendance/schemas`, `leave/service`, `leave/schemas`, `core_hr/service`, `common/models`, `common/filters`, `dependencies`.
- **Well-covered modules** (≥90%): models (auto-covered via imports), `common/audit` (94%), `config` (94%), `core_hr/schemas` (91%), `main` (96%).
- **Priority areas for new tests:** `leave/service.py` (413 lines, 0%), `attendance/service.py` (337 lines, 0%), `core_hr/service.py` (172 lines, 22%).

### Warnings

- 16 SAWarnings about circular foreign key dependency between `departments` ↔ `employees` tables (needs `use_alter=True` on the FK).
- `pytest-asyncio` deprecation warning about `asyncio_default_fixture_loop_scope` being unset.
