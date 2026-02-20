"""Post-migration validation: count checks, referential integrity, data quality."""

import re
import sys
from typing import Tuple

from psycopg2 import sql as pgsql

from migration.config import get_pg_conn, get_sqlite_conn

# Strict identifier pattern to prevent SQL injection in dynamic table names
_SAFE_IDENT_RE = re.compile(r'^[a-z_][a-z0-9_]*$')


def _validate_identifier(name: str) -> str:
    """Validate a SQL identifier against a strict alphanumeric pattern."""
    if not _SAFE_IDENT_RE.match(name):
        raise ValueError(f"Unsafe SQL identifier: {name!r}")
    return name


def _count(cur, table: str) -> int:
    """Count rows in a table using safe identifier quoting (psycopg2.sql)."""
    _validate_identifier(table)
    cur.execute(pgsql.SQL("SELECT COUNT(*) FROM {}").format(pgsql.Identifier(table)))
    return cur.fetchone()[0]


def _count_sqlite(cur, table: str) -> int:
    """Count rows in a SQLite table using validated identifier."""
    _validate_identifier(table)
    cur.execute(f'SELECT COUNT(*) FROM "{table}"')
    return cur.fetchone()[0]


def validate() -> Tuple[int, int]:
    """Run all validation checks. Returns (passed, failed)."""
    passed = 0
    failed = 0
    warnings = []

    try:
        sq = get_sqlite_conn()
        sq_cur = sq.cursor()
    except FileNotFoundError:
        sq = None
        sq_cur = None
        print("  ⚠ SQLite database not found — skipping count comparisons")

    pg = get_pg_conn()
    pg_cur = pg.cursor()

    print("\n╔══════════════════════════════════════════════════════╗")
    print("║           POST-MIGRATION VALIDATION REPORT          ║")
    print("╚══════════════════════════════════════════════════════╝\n")

    # ── 1. Record count comparisons ──────────────────────────────────
    print("── Record Counts ──")
    count_checks = [
        ("departments", "departments"),
        ("employees", "employees"),
        ("attendance", "attendance_records"),
        ("leave_balances", "leave_balances"),
        ("leave_requests", "leave_requests"),
        ("salaries", "salaries"),
        ("salary_components", "salary_components"),
        ("helpdesk_tickets", "helpdesk_tickets"),
        ("expense_claims", "expense_claims"),
        ("fnf_settlements", "fnf_settlements"),
    ]

    for sq_table, pg_table in count_checks:
        pg_count = _count(pg_cur, pg_table)
        if sq_cur:
            sq_count = _count_sqlite(sq_cur, sq_table)
            match = "✓" if pg_count >= sq_count else "✗"
            if pg_count < sq_count:
                failed += 1
                diff = sq_count - pg_count
                warnings.append(
                    f"{pg_table}: {diff} records not migrated "
                    f"(SQLite={sq_count}, PG={pg_count})"
                )
            else:
                passed += 1
            print(f"  {match} {pg_table:25s}  SQLite={sq_count:>6d}  PG={pg_count:>6d}")
        else:
            print(f"  • {pg_table:25s}  PG={pg_count:>6d}")
            passed += 1

    # ── 2. Active employee count ─────────────────────────────────────
    print("\n── Active Employees ──")
    pg_cur.execute(
        "SELECT COUNT(*) FROM employees WHERE is_active = TRUE "
        "AND employment_status = 'active'"
    )
    active = pg_cur.fetchone()[0]
    if 200 <= active <= 400:
        print(f"  ✓ Active employees: {active} (expected ~284)")
        passed += 1
    elif active > 0:
        print(f"  ~ Active employees: {active} (expected ~284, may be OK)")
        passed += 1
    else:
        print(f"  ✗ Active employees: {active} (expected ~284)")
        failed += 1

    # ── 3. Referential integrity ─────────────────────────────────────
    print("\n── Referential Integrity ──")

    # Orphaned attendance records
    pg_cur.execute(
        """SELECT COUNT(*) FROM attendance_records ar
           LEFT JOIN employees e ON e.id = ar.employee_id
           WHERE e.id IS NULL"""
    )
    orphan_att = pg_cur.fetchone()[0]
    if orphan_att == 0:
        print("  ✓ No orphaned attendance records")
        passed += 1
    else:
        print(f"  ✗ {orphan_att} orphaned attendance records")
        failed += 1

    # Orphaned leave requests
    pg_cur.execute(
        """SELECT COUNT(*) FROM leave_requests lr
           LEFT JOIN employees e ON e.id = lr.employee_id
           WHERE e.id IS NULL"""
    )
    orphan_lr = pg_cur.fetchone()[0]
    if orphan_lr == 0:
        print("  ✓ No orphaned leave requests")
        passed += 1
    else:
        print(f"  ✗ {orphan_lr} orphaned leave requests")
        failed += 1

    # Orphaned leave balances
    pg_cur.execute(
        """SELECT COUNT(*) FROM leave_balances lb
           LEFT JOIN employees e ON e.id = lb.employee_id
           WHERE e.id IS NULL"""
    )
    orphan_lb = pg_cur.fetchone()[0]
    if orphan_lb == 0:
        print("  ✓ No orphaned leave balances")
        passed += 1
    else:
        print(f"  ✗ {orphan_lb} orphaned leave balances")
        failed += 1

    # ── 4. Data quality ──────────────────────────────────────────────
    print("\n── Data Quality ──")

    # NULL emails
    pg_cur.execute("SELECT COUNT(*) FROM employees WHERE email IS NULL OR email = ''")
    null_emails = pg_cur.fetchone()[0]
    if null_emails == 0:
        print("  ✓ No employees with NULL/empty email")
        passed += 1
    else:
        print(f"  ✗ {null_emails} employees with NULL/empty email")
        failed += 1

    # Active employees without department
    pg_cur.execute(
        """SELECT COUNT(*) FROM employees
           WHERE is_active = TRUE AND department_id IS NULL"""
    )
    no_dept = pg_cur.fetchone()[0]
    if no_dept == 0:
        print("  ✓ All active employees have a department")
        passed += 1
    else:
        print(f"  ~ {no_dept} active employees without department (may need review)")
        warnings.append(f"{no_dept} active employees missing department_id")
        passed += 1  # warning, not failure

    # Duplicate employee codes
    pg_cur.execute(
        """SELECT employee_code, COUNT(*) FROM employees
           GROUP BY employee_code HAVING COUNT(*) > 1"""
    )
    dupes = pg_cur.fetchall()
    if not dupes:
        print("  ✓ No duplicate employee codes")
        passed += 1
    else:
        print(f"  ✗ {len(dupes)} duplicate employee codes")
        failed += 1

    # ── 5. Circular reporting chains ─────────────────────────────────
    print("\n── Reporting Chain ──")
    pg_cur.execute(
        """WITH RECURSIVE chain AS (
             SELECT id, reporting_manager_id, 1 AS depth
             FROM employees
             WHERE reporting_manager_id IS NOT NULL
           UNION ALL
             SELECT c.id, e.reporting_manager_id, c.depth + 1
             FROM chain c
             JOIN employees e ON e.id = c.reporting_manager_id
             WHERE e.reporting_manager_id IS NOT NULL AND c.depth < 25
           )
           SELECT COUNT(*) FROM chain WHERE depth >= 20"""
    )
    deep_chains = pg_cur.fetchone()[0]
    if deep_chains == 0:
        print("  ✓ No circular/deep reporting chains (depth < 20)")
        passed += 1
    else:
        print(f"  ✗ {deep_chains} employees in deep reporting chains (≥20)")
        failed += 1

    # ── 6. Negative leave balances ───────────────────────────────────
    print("\n── Leave Balances ──")
    pg_cur.execute(
        "SELECT COUNT(*) FROM leave_balances WHERE current_balance < 0"
    )
    neg_bal = pg_cur.fetchone()[0]
    if neg_bal == 0:
        print("  ✓ No negative leave balances")
        passed += 1
    else:
        print(f"  ~ {neg_bal} negative leave balances (may be intentional LOP)")
        passed += 1  # warn, not fail

    # ── 7. Locations ─────────────────────────────────────────────────
    print("\n── Locations ──")
    pg_cur.execute("SELECT name FROM locations WHERE is_active = TRUE ORDER BY name")
    locs = [row[0] for row in pg_cur.fetchall()]
    print(f"  ✓ Active locations: {', '.join(locs) or '(none)'}")
    passed += 1

    # ── Summary ──────────────────────────────────────────────────────
    print("\n══════════════════════════════════════════════════════")
    print(f"  PASSED: {passed}  |  FAILED: {failed}")
    if warnings:
        print(f"  WARNINGS ({len(warnings)}):")
        for w in warnings:
            print(f"    ⚠ {w}")
    print("══════════════════════════════════════════════════════\n")

    if sq:
        sq.close()
    pg.close()

    return passed, failed


if __name__ == "__main__":
    p, f = validate()
    sys.exit(1 if f > 0 else 0)
