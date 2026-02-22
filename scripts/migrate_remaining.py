#!/usr/bin/env python3
"""Migrate remaining empty tables from Keka API → SQLite → PostgreSQL.

Targets tables that are currently empty in PostgreSQL:
  - salaries / salary_components
  - helpdesk_tickets
  - expense_claims
  - fnf_settlements
  - holidays

Also re-runs the leave type fix to recover 736+ previously dropped balances.

Usage:
    python scripts/migrate_remaining.py              # full pipeline
    python scripts/migrate_remaining.py --sync-only  # Keka API → SQLite only
    python scripts/migrate_remaining.py --migrate-only  # SQLite → PG only
    python scripts/migrate_remaining.py --holidays   # Keka holidays → PG
    python scripts/migrate_remaining.py --status     # show current counts

Requires KEKA_API_KEY, KEKA_CLIENT_ID, KEKA_CLIENT_SECRET in .env
"""

import argparse
import json
import logging
import os
import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ── Path setup ────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

WORKSPACE_ROOT = Path(os.path.expanduser("~/.openclaw/workspace"))
for env_path in [PROJECT_ROOT / ".env", WORKSPACE_ROOT / ".env"]:
    if env_path.exists():
        load_dotenv(env_path)

from migration.config import get_pg_conn, get_sqlite_conn, SQLITE_PATH

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("migrate_remaining")

IST = timezone(timedelta(hours=5, minutes=30))


# ═════════════════════════════════════════════════════════════════════
# Step 1: Keka API Sync (for entities with empty tables)
# ═════════════════════════════════════════════════════════════════════

def sync_from_keka():
    """Sync salaries, helpdesk, expenses, FnF, holidays from Keka API → SQLite."""
    from migration.keka_api_sync import KekaApiSyncer

    syncer = KekaApiSyncer()
    results = {}

    entities = [
        ("salaries", syncer.sync_salaries),
        ("salary_components", syncer.sync_salary_components),
        ("helpdesk_tickets", syncer.sync_helpdesk),
        ("expense_claims", syncer.sync_expenses),
        ("fnf_settlements", syncer.sync_fnf),
        ("leave_balances", syncer.sync_leave_balances),
    ]

    for name, sync_fn in entities:
        try:
            count = sync_fn()
            results[name] = count
            logger.info("✅ %s: %d records", name, count)
        except Exception as e:
            results[name] = f"ERROR: {e}"
            logger.error("❌ %s: %s", name, e)

    # Sync holidays separately (custom endpoint)
    try:
        count = sync_holidays_from_keka(syncer)
        results["holidays"] = count
        logger.info("✅ holidays: %d records", count)
    except Exception as e:
        results["holidays"] = f"ERROR: {e}"
        logger.error("❌ holidays: %s", e)

    return results


def sync_holidays_from_keka(syncer=None) -> int:
    """Sync holidays from Keka API → SQLite."""
    import sqlite3

    if syncer is None:
        from migration.keka_api_sync import KekaApiSyncer
        syncer = KekaApiSyncer()

    logger.info("Syncing holidays from Keka API...")

    # Ensure holidays table exists in SQLite
    conn = sqlite3.connect(SQLITE_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS holidays (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            date TEXT NOT NULL,
            type TEXT DEFAULT 'public',
            is_optional BOOLEAN DEFAULT 0,
            applicable_locations TEXT,
            synced_at TEXT
        )
    """)
    conn.commit()

    now = datetime.now(IST).isoformat()

    # Try different Keka holiday endpoints
    data = []
    for path in ["/time/holidays", "/hris/holidays", "/holidays"]:
        try:
            result = syncer._get_paginated(path)
            if result:
                data = result
                logger.info("Found holidays at %s", path)
                break
        except Exception:
            continue

    if not data:
        # Try year-specific endpoint
        year = datetime.now().year
        for path in [f"/time/holidays?year={year}", f"/hris/holidays?year={year}"]:
            try:
                result = syncer._get(path.split("?")[0], {"year": year})
                if isinstance(result, list):
                    data = result
                elif isinstance(result, dict):
                    data = result.get("data", result.get("values", []))
                if data:
                    logger.info("Found holidays at %s", path)
                    break
            except Exception:
                continue

    count = 0
    for h in data:
        h_id = h.get("id", str(uuid.uuid4()))
        h_name = h.get("name", h.get("title", ""))
        h_date = h.get("date", h.get("holidayDate", ""))
        if isinstance(h_date, str) and "T" in h_date:
            h_date = h_date[:10]
        h_type = h.get("type", h.get("holidayType", "public"))
        if isinstance(h_type, int):
            h_type = {0: "public", 1: "restricted", 2: "optional"}.get(h_type, "public")
        is_optional = h.get("isOptional", h_type in ("restricted", "optional"))
        locations = json.dumps(h.get("applicableLocations", []))

        conn.execute(
            """INSERT OR REPLACE INTO holidays
               (id, name, date, type, is_optional, applicable_locations, synced_at)
               VALUES (?,?,?,?,?,?,?)""",
            (h_id, h_name, h_date, h_type, is_optional, locations, now),
        )
        count += 1

    conn.commit()
    conn.close()
    logger.info("Synced %d holidays to SQLite", count)
    return count


# ═════════════════════════════════════════════════════════════════════
# Step 2: SQLite → PostgreSQL Migration
# ═════════════════════════════════════════════════════════════════════

def get_employee_map() -> Dict[str, uuid.UUID]:
    """Build {keka_id → pg_uuid} map from employees table."""
    pg = get_pg_conn()
    cur = pg.cursor()
    cur.execute("SELECT id, keka_id FROM employees WHERE keka_id IS NOT NULL")
    result = {}
    for row in cur.fetchall():
        result[str(row[1])] = uuid.UUID(str(row[0]))
    pg.close()
    return result


def migrate_salaries_to_pg(emp_map: Dict[str, uuid.UUID]) -> int:
    """Migrate salary records from SQLite → PostgreSQL."""
    from migration.migrate_salaries import migrate_salaries
    try:
        return migrate_salaries(emp_map)
    except Exception as e:
        logger.error("Salary migration error: %s", e)
        return 0


def migrate_helpdesk_to_pg(emp_map: Dict[str, uuid.UUID]) -> int:
    """Migrate helpdesk tickets from SQLite → PostgreSQL."""
    from migration.migrate_helpdesk import migrate_helpdesk
    try:
        return migrate_helpdesk(emp_map)
    except Exception as e:
        logger.error("Helpdesk migration error: %s", e)
        return 0


def migrate_expenses_to_pg(emp_map: Dict[str, uuid.UUID]) -> int:
    """Migrate expense claims from SQLite → PostgreSQL."""
    from migration.migrate_expenses import migrate_expenses
    try:
        return migrate_expenses(emp_map)
    except Exception as e:
        logger.error("Expense migration error: %s", e)
        return 0


def migrate_fnf_to_pg(emp_map: Dict[str, uuid.UUID]) -> int:
    """Migrate FnF settlements from SQLite → PostgreSQL."""
    from migration.migrate_fnf import migrate_fnf
    try:
        return migrate_fnf(emp_map)
    except Exception as e:
        logger.error("FnF migration error: %s", e)
        return 0


def migrate_holidays_to_pg() -> int:
    """Migrate holidays from SQLite → PostgreSQL."""
    import sqlite3

    sq = get_sqlite_conn()
    pg = get_pg_conn()
    cur = pg.cursor()

    # Ensure holidays table exists in PG
    cur.execute("""
        CREATE TABLE IF NOT EXISTS holidays (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name VARCHAR(255) NOT NULL,
            date DATE NOT NULL,
            type VARCHAR(50) DEFAULT 'public',
            is_optional BOOLEAN DEFAULT FALSE,
            applicable_locations JSONB DEFAULT '[]'::jsonb,
            year INTEGER,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE(name, date)
        )
    """)
    pg.commit()

    try:
        rows = sq.execute("SELECT * FROM holidays").fetchall()
    except sqlite3.OperationalError:
        logger.warning("No holidays table in SQLite")
        sq.close()
        pg.close()
        return 0

    count = 0
    for r in rows:
        h_date = r["date"]
        h_name = r["name"]
        h_type = r["type"] or "public"
        is_optional = bool(r["is_optional"])
        locations = r.get("applicable_locations", "[]")
        year = None
        if h_date:
            try:
                year = int(h_date[:4])
            except (ValueError, TypeError):
                pass

        cur.execute(
            """INSERT INTO holidays (name, date, type, is_optional, applicable_locations, year)
               VALUES (%s, %s, %s, %s, %s::jsonb, %s)
               ON CONFLICT (name, date) DO UPDATE
               SET type = EXCLUDED.type,
                   is_optional = EXCLUDED.is_optional,
                   applicable_locations = EXCLUDED.applicable_locations""",
            (h_name, h_date, h_type, is_optional, locations, year),
        )
        count += 1

    pg.commit()
    sq.close()
    pg.close()
    logger.info("Migrated %d holidays to PostgreSQL", count)
    return count


def fix_leave_types_and_remigrate(emp_map: Dict[str, uuid.UUID]) -> Tuple[int, int, int]:
    """Add missing leave types and re-migrate previously dropped balances."""
    from migration.fix_leave_types import fix_leave_types
    try:
        return fix_leave_types(emp_map)
    except Exception as e:
        logger.error("Leave type fix error: %s", e)
        return 0, 0, 0


# ═════════════════════════════════════════════════════════════════════
# Status
# ═════════════════════════════════════════════════════════════════════

def show_status():
    """Show current record counts in PostgreSQL tables."""
    pg = get_pg_conn()
    cur = pg.cursor()

    tables = [
        "employees", "departments", "leave_types", "leave_balances",
        "leave_requests", "salaries", "salary_components",
        "helpdesk_tickets", "expense_claims", "fnf_settlements",
    ]

    # Check if holidays table exists
    cur.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables
            WHERE table_name = 'holidays'
        )
    """)
    if cur.fetchone()[0]:
        tables.append("holidays")

    print(f"\n{'Table':<25} {'Count':>10}")
    print("─" * 40)
    for table in tables:
        try:
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            count = cur.fetchone()[0]
            status = "⚠️  EMPTY" if count == 0 else ""
            print(f"  {table:<23} {count:>8}  {status}")
        except Exception:
            print(f"  {table:<23} {'N/A':>8}  (table missing)")
            pg.rollback()

    pg.close()


# ═════════════════════════════════════════════════════════════════════
# Main
# ═════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Migrate remaining data: Keka API → SQLite → PostgreSQL"
    )
    parser.add_argument("--sync-only", action="store_true",
                        help="Only sync from Keka API to SQLite")
    parser.add_argument("--migrate-only", action="store_true",
                        help="Only migrate from SQLite to PostgreSQL")
    parser.add_argument("--holidays", action="store_true",
                        help="Sync and migrate holidays only")
    parser.add_argument("--fix-leaves", action="store_true",
                        help="Fix leave type mapping and re-migrate")
    parser.add_argument("--status", action="store_true",
                        help="Show current PostgreSQL table counts")
    args = parser.parse_args()

    if args.status:
        show_status()
        return

    print(f"\n{'═' * 60}")
    print("  HR INTELLIGENCE v2 — REMAINING DATA MIGRATION")
    print(f"{'═' * 60}\n")

    # ── Step 1: Sync from Keka API ────────────────────────────────
    if not args.migrate_only:
        print(f"\n{'─' * 40}")
        print("  STEP 1: Keka API → SQLite Sync")
        print(f"{'─' * 40}\n")

        if args.holidays:
            count = sync_holidays_from_keka()
            print(f"  Holidays synced: {count}")
        else:
            results = sync_from_keka()
            print(f"\n  {'Entity':<25} {'Records'}")
            print("  " + "─" * 40)
            for entity, count in results.items():
                status = "✅" if isinstance(count, int) else "❌"
                print(f"  {status} {entity:<23} {count}")

        if args.sync_only:
            print("\n  Done (sync only mode).")
            return

    # ── Step 2: SQLite → PostgreSQL ───────────────────────────────
    print(f"\n{'─' * 40}")
    print("  STEP 2: SQLite → PostgreSQL Migration")
    print(f"{'─' * 40}\n")

    emp_map = get_employee_map()
    if not emp_map:
        logger.error("No employee mapping found — run employee migration first")
        sys.exit(1)
    print(f"  Employee map: {len(emp_map)} employees")

    results = {}

    if args.holidays:
        results["holidays"] = migrate_holidays_to_pg()
    elif args.fix_leaves:
        types, bal, req = fix_leave_types_and_remigrate(emp_map)
        results["leave_types_added"] = types
        results["leave_balances"] = bal
        results["leave_requests"] = req
    else:
        # Migrate all remaining entities
        results["salaries"] = migrate_salaries_to_pg(emp_map)
        results["helpdesk"] = migrate_helpdesk_to_pg(emp_map)
        results["expenses"] = migrate_expenses_to_pg(emp_map)
        results["fnf"] = migrate_fnf_to_pg(emp_map)
        results["holidays"] = migrate_holidays_to_pg()

        # Fix leave types and re-migrate dropped balances
        types, bal, req = fix_leave_types_and_remigrate(emp_map)
        results["leave_types_added"] = types
        results["leave_balances_recovered"] = bal
        results["leave_requests_recovered"] = req

    print(f"\n{'─' * 40}")
    print("  RESULTS")
    print(f"{'─' * 40}")
    for key, count in results.items():
        status = "✅" if isinstance(count, int) and count >= 0 else "❌"
        print(f"  {status} {key:<30} {count}")

    # Show final status
    print()
    show_status()

    print(f"\n{'═' * 60}")
    print("  MIGRATION COMPLETE")
    print(f"{'═' * 60}\n")


if __name__ == "__main__":
    main()
