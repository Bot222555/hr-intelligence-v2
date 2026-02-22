#!/usr/bin/env python3
"""Keka Sync — Scheduled cron wrapper for all HR data types.

Designed to run every 30 minutes during business hours:
    */30 8-20 * * 1-6

Syncs ALL data types:
  - employees      (full refresh each run)
  - departments    (full refresh each run)
  - attendance     (last 3 days rolling window)
  - leave          (last 7 days rolling window)
  - salary         (full refresh, hourly — skips if <60m since last)
  - helpdesk       (full refresh each run)
  - expenses       (full refresh, hourly)
  - fnf            (full refresh, hourly)
  - leave_balances (full refresh, hourly)

Usage:
    python scripts/sync_keka.py                # full sync (cron default)
    python scripts/sync_keka.py --entity employees  # single entity
    python scripts/sync_keka.py --status       # show last sync times
    python scripts/sync_keka.py --dry-run      # fetch only, no writes

Requires .env at project root or /opt/hr-intelligence/.env:
    KEKA_API_KEY, KEKA_CLIENT_ID, KEKA_CLIENT_SECRET
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ── Path setup ────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

# Load .env from project root
for env_candidate in [
    PROJECT_ROOT / ".env",
    Path("/opt/hr-intelligence/.env"),
    Path(os.path.expanduser("~/.openclaw/workspace/.env")),
]:
    if env_candidate.exists():
        load_dotenv(env_candidate)
        break

IST = timezone(timedelta(hours=5, minutes=30))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("sync_keka")

# ── Import the syncer ────────────────────────────────────────────────
try:
    from migration.keka_api_sync import KekaApiSyncer
except ImportError as e:
    logger.error("Cannot import KekaApiSyncer: %s", e)
    logger.error("Ensure you run from the project root or have the migration package.")
    sys.exit(1)


# ══════════════════════════════════════════════════════════════════════
# Sync orchestrator — knows which entities to sync and frequency
# ══════════════════════════════════════════════════════════════════════

# Entities that run every 30 minutes (each cron tick)
FREQUENT_ENTITIES = ["employees", "departments", "attendance", "leave_requests"]

# Entities that run hourly (skip if last sync < 60 min ago)
HOURLY_ENTITIES = [
    "salaries", "salary_components", "leave_balances",
    "expense_claims", "helpdesk_tickets", "fnf_settlements",
]

ALL_ENTITIES = FREQUENT_ENTITIES + HOURLY_ENTITIES


def _should_sync_hourly(syncer: KekaApiSyncer, entity: str) -> bool:
    """Check if an hourly entity needs syncing (>55 min since last sync)."""
    try:
        conn = syncer._conn()
        row = conn.execute(
            "SELECT value FROM last_sync_meta WHERE key = ?", (entity,)
        ).fetchone()
        conn.close()
        if not row:
            return True
        info = json.loads(row["value"])
        last_sync = info.get("last_sync", "")
        if not last_sync:
            return True
        last_dt = datetime.fromisoformat(last_sync)
        elapsed = (datetime.now(IST) - last_dt).total_seconds()
        return elapsed > 55 * 60  # 55 minutes
    except Exception:
        return True


def run_sync(
    syncer: KekaApiSyncer,
    entities: list[str] | None = None,
    dry_run: bool = False,
    days_back: int = 365,
) -> dict[str, int | str]:
    """Run sync for specified entities (or all). Returns entity→count map."""
    now = datetime.now()
    att_from = (now - timedelta(days=3)).strftime("%Y-%m-%d")
    leave_from = (now - timedelta(days=7)).strftime("%Y-%m-%d")
    full_from = (now - timedelta(days=days_back)).strftime("%Y-%m-%d")
    to_date = now.strftime("%Y-%m-%d")

    entity_map = {
        "employees": syncer.sync_employees,
        "departments": syncer.sync_departments,
        "attendance": lambda: syncer.sync_attendance(att_from, to_date),
        "leave_requests": lambda: syncer.sync_leaves(leave_from, to_date),
        "leave_balances": syncer.sync_leave_balances,
        "salaries": syncer.sync_salaries,
        "salary_components": syncer.sync_salary_components,
        "expense_claims": syncer.sync_expenses,
        "helpdesk_tickets": syncer.sync_helpdesk,
        "fnf_settlements": syncer.sync_fnf,
    }

    targets = entities or ALL_ENTITIES
    results: dict[str, int | str] = {}

    for entity in targets:
        if entity not in entity_map:
            logger.warning("Unknown entity: %s — skipping", entity)
            results[entity] = "UNKNOWN"
            continue

        # Skip hourly entities if not due
        if not entities and entity in HOURLY_ENTITIES:
            if not _should_sync_hourly(syncer, entity):
                logger.info("⏭  %s — skipped (synced <1h ago)", entity)
                results[entity] = "SKIPPED"
                continue

        try:
            if dry_run:
                logger.info("[DRY RUN] Would sync %s", entity)
                results[entity] = "DRY_RUN"
            else:
                fn = entity_map[entity]
                count = fn()
                results[entity] = count
                logger.info("✅ %s: %d records", entity, count)
        except Exception as e:
            results[entity] = f"ERROR: {e}"
            logger.error("❌ %s: %s", entity, e)

    return results


def run_pg_migration():
    """Trigger SQLite → PostgreSQL migration after sync."""
    try:
        from migration.migrate_all import run_migration
        logger.info("🔄 Running SQLite → PostgreSQL migration...")
        run_migration()
        logger.info("✅ PostgreSQL migration complete")
        return True
    except Exception as e:
        logger.error("❌ PostgreSQL migration failed: %s", e)
        return False


# ══════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Keka Sync — scheduled cron wrapper for all HR data types",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Cron schedule (recommended):
    */30 8-20 * * 1-6    (every 30 min, 8AM-8PM, Mon-Sat IST)

Install in crontab:
    crontab -e
    */30 8-20 * * 1-6 cd /opt/hr-intelligence && /usr/bin/python3 scripts/sync_keka.py >> /var/log/keka-sync.log 2>&1

Data types synced:
    employees, departments      — every 30 min
    attendance (3-day window)   — every 30 min
    leave requests (7-day)      — every 30 min
    salaries, expenses, helpdesk, fnf, leave_balances — hourly
""",
    )
    parser.add_argument("--entity", type=str, help="Sync a single entity")
    parser.add_argument("--status", action="store_true", help="Show last sync times")
    parser.add_argument("--dry-run", action="store_true", help="Fetch from API but don't write")
    parser.add_argument("--sync-only", action="store_true", help="Skip PostgreSQL migration")
    parser.add_argument("--days", type=int, default=365, help="Days of history (default: 365)")
    parser.add_argument("--all-entities", action="store_true",
                        help="Force sync all entities regardless of hourly skip")
    args = parser.parse_args()

    # ── Credentials check ─────────────────────────────────────────────
    required_vars = ["KEKA_API_KEY", "KEKA_CLIENT_ID", "KEKA_CLIENT_SECRET"]
    missing = [v for v in required_vars if not os.getenv(v)]
    if missing and not args.status:
        logger.error("Missing Keka credentials: %s", ", ".join(missing))
        logger.error("Set in .env: %s", PROJECT_ROOT / ".env")
        sys.exit(1)

    # ── Init syncer ───────────────────────────────────────────────────
    try:
        syncer = KekaApiSyncer()
    except FileNotFoundError as e:
        logger.error("SQLite DB not found: %s", e)
        logger.error("Run the initial migration first or set KEKA_SQLITE_PATH")
        sys.exit(1)

    # ── Status mode ───────────────────────────────────────────────────
    if args.status:
        syncer.show_status()
        return

    # ── Sync ──────────────────────────────────────────────────────────
    start_time = time.time()
    now_ist = datetime.now(IST).strftime("%Y-%m-%d %H:%M IST")

    print(f"""
{'=' * 60}
  KEKA SYNC — {now_ist}
  Entity     : {args.entity or 'ALL'}
  Dry run    : {args.dry_run}
  PG migrate : {'skip' if args.sync_only else 'yes'}
{'=' * 60}
""")

    # Authenticate
    if not args.dry_run:
        syncer.authenticate()

    # Run sync
    entities = [args.entity] if args.entity else (ALL_ENTITIES if args.all_entities else None)
    results = run_sync(syncer, entities=entities, dry_run=args.dry_run, days_back=args.days)

    # ── PostgreSQL migration ──────────────────────────────────────────
    if not args.sync_only and not args.dry_run:
        run_pg_migration()

    # ── Summary ───────────────────────────────────────────────────────
    elapsed = time.time() - start_time
    synced = sum(1 for v in results.values() if isinstance(v, int))
    errors = sum(1 for v in results.values() if isinstance(v, str) and v.startswith("ERROR"))
    skipped = sum(1 for v in results.values() if v == "SKIPPED")

    print(f"""
{'=' * 60}
  SYNC COMPLETE — {elapsed:.1f}s elapsed
  Synced  : {synced} entities
  Skipped : {skipped} (not due yet)
  Errors  : {errors}
{'=' * 60}
""")

    for entity, result in results.items():
        if isinstance(result, int):
            print(f"  ✅ {entity:<25} {result} records")
        elif result == "SKIPPED":
            print(f"  ⏭  {entity:<25} skipped (hourly)")
        elif isinstance(result, str) and result.startswith("ERROR"):
            print(f"  ❌ {entity:<25} {result}")
        else:
            print(f"  ℹ️  {entity:<25} {result}")

    if errors > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
