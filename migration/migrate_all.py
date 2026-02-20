#!/usr/bin/env python3
"""Orchestrator: run all Keka → PostgreSQL migrations in order.

Usage:
    python -m migration.migrate_all              # full migration
    python -m migration.migrate_all --dry-run    # read-only, show counts
    python -m migration.migrate_all --validate   # validation only
"""

import argparse
import sys
import time

from migration.config import SQLITE_PATH, get_sqlite_conn


def run_dry(sqlite_path: str):
    """Dry-run: show SQLite record counts without touching PostgreSQL."""
    import re
    import sqlite3

    # Allowlist of valid table names for safe querying
    _SAFE_IDENT_RE = re.compile(r'^[a-z_][a-z0-9_]*$')

    print("\n🔍 DRY RUN — reading SQLite only, no writes\n")
    conn = sqlite3.connect(sqlite_path)
    cur = conn.cursor()

    tables = ["departments", "employees", "attendance",
              "leave_balances", "leave_requests"]
    for t in tables:
        if not _SAFE_IDENT_RE.match(t):
            raise ValueError(f"Unsafe table identifier: {t!r}")
        try:
            cur.execute(f'SELECT COUNT(*) FROM "{t}"')
            count = cur.fetchone()[0]
            print(f"  {t:25s}  {count:>6d} rows")
        except sqlite3.OperationalError:
            print(f"  {t:25s}  (table not found)")
    conn.close()
    print("\n✓ Dry run complete — no data was written\n")


def run_migration():
    """Execute the full migration pipeline."""
    from migration.migrate_attendance import migrate_attendance
    from migration.migrate_departments import migrate_departments
    from migration.migrate_employees import migrate_employees
    from migration.migrate_leaves import migrate_leaves
    from migration.validate import validate

    t0 = time.time()

    print("\n" + "=" * 55)
    print("  KEKA → POSTGRESQL MIGRATION")
    print("=" * 55)
    print(f"  SQLite: {SQLITE_PATH}")
    print()

    # Step 1: Departments + Locations
    print("▶ Step 1/4: Departments & Locations")
    dept_map, loc_map = migrate_departments()

    # Step 2: Employees
    print("\n▶ Step 2/4: Employees")
    emp_map = migrate_employees(dept_map, loc_map)

    # Step 3: Leave Balances & Requests
    print("\n▶ Step 3/4: Leave Data")
    bal_count, req_count = migrate_leaves(emp_map)

    # Step 4: Attendance
    print("\n▶ Step 4/4: Attendance Records")
    att_count = migrate_attendance(emp_map)

    elapsed = time.time() - t0
    print(f"\n✅ Migration complete in {elapsed:.1f}s")
    print(f"   Departments: {len(dept_map)}")
    print(f"   Locations:   {len(loc_map)}")
    print(f"   Employees:   {len(emp_map)}")
    print(f"   Leave Bal:   {bal_count}")
    print(f"   Leave Req:   {req_count}")
    print(f"   Attendance:  {att_count}")

    # Validate
    print("\n▶ Running post-migration validation...")
    passed, failed = validate()

    return failed


def main():
    parser = argparse.ArgumentParser(
        description="Keka SQLite → PostgreSQL migration"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show SQLite counts without writing to PostgreSQL",
    )
    parser.add_argument(
        "--validate", action="store_true",
        help="Run validation only (no migration)",
    )
    args = parser.parse_args()

    if args.validate:
        from migration.validate import validate
        _, failed = validate()
        sys.exit(1 if failed > 0 else 0)

    if args.dry_run:
        if not SQLITE_PATH:
            print("❌ SQLite database not found")
            sys.exit(1)
        run_dry(SQLITE_PATH)
        sys.exit(0)

    if not SQLITE_PATH:
        print("❌ SQLite database not found — cannot migrate")
        sys.exit(1)

    failed = run_migration()
    sys.exit(1 if failed > 0 else 0)


if __name__ == "__main__":
    main()
