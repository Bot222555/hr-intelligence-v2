#!/usr/bin/env python3
"""Keka API Incremental Sync — Pull fresh attendance + leave data for a date range.

Purpose: Fill gaps when scheduled syncs miss days. Pulls only the specified
date range (default: last 3 days) to avoid full re-sync overhead.

Usage:
    python -m scripts.keka_incremental_sync                          # last 3 days
    python -m scripts.keka_incremental_sync --from 2026-02-17 --to 2026-02-20
    python -m scripts.keka_incremental_sync --sqlite-only            # skip PG migration
    python -m scripts.keka_incremental_sync --dry-run                # auth + fetch, don't write

Requires in .env (project root):
    KEKA_API_KEY, KEKA_CLIENT_ID, KEKA_CLIENT_SECRET

Optionally:
    DATABASE_URL_SYNC  (for PostgreSQL upsert)
    KEKA_SQLITE_PATH   (custom SQLite location)
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
from dotenv import load_dotenv

# ── Path setup ────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Load .env from project root
env_path = PROJECT_ROOT / ".env"
if env_path.exists():
    load_dotenv(env_path)
else:
    # Also check workspace root
    ws_env = Path(os.path.expanduser("~/.openclaw/workspace/.env"))
    if ws_env.exists():
        load_dotenv(ws_env)

IST = timezone(timedelta(hours=5, minutes=30))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("keka_inc_sync")

# ── Token cache (shared with keka_api_sync) ──────────────────────────
TOKEN_CACHE = PROJECT_ROOT / "migration" / ".keka_token_cache.json"

# ── SQLite path resolution ────────────────────────────────────────────
SQLITE_CANDIDATES = [
    os.environ.get("KEKA_SQLITE_PATH", ""),
    str(PROJECT_ROOT / "data" / "keka.db"),
    "/Users/allfred/scripts/keka/keka_hr.db",
    "/Users/donna/.openclaw/workspace/scripts/keka/data/keka.db",
]

SQLITE_PATH: Optional[str] = None
for _p in SQLITE_CANDIDATES:
    if _p and os.path.isfile(_p):
        SQLITE_PATH = _p
        break


# ══════════════════════════════════════════════════════════════════════
# Keka API Client — lightweight, focused on incremental sync
# ══════════════════════════════════════════════════════════════════════

class KekaClient:
    """Authenticated Keka API client with rate limiting."""

    TOKEN_URL = "https://login.keka.com/connect/token"

    def __init__(self):
        self.api_key = os.getenv("KEKA_API_KEY", "")
        self.client_id = os.getenv("KEKA_CLIENT_ID", "")
        self.client_secret = os.getenv("KEKA_CLIENT_SECRET", "")
        company = os.getenv("KEKA_COMPANY", "creativefuel")
        self.base_url = f"https://{company}.keka.com/api/v1"

        self._token: Optional[str] = None
        self._token_expires: float = 0
        self._req_count = 0
        self._minute_start = time.time()

        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/json",
            "User-Agent": "HRIntelligence/2.0 IncrementalSync",
        })

        self._load_cached_token()

    # ── Credentials check ─────────────────────────────────────────────

    def check_credentials(self) -> List[str]:
        """Return list of missing credential names."""
        missing = []
        if not self.api_key:
            missing.append("KEKA_API_KEY")
        if not self.client_id:
            missing.append("KEKA_CLIENT_ID")
        if not self.client_secret:
            missing.append("KEKA_CLIENT_SECRET")
        return missing

    # ── Auth ──────────────────────────────────────────────────────────

    def _load_cached_token(self):
        if TOKEN_CACHE.exists():
            try:
                data = json.loads(TOKEN_CACHE.read_text())
                if data.get("expires_at", 0) > time.time() + 300:
                    self._token = data["access_token"]
                    self._token_expires = data["expires_at"]
                    self.session.headers["Authorization"] = f"Bearer {self._token}"
                    logger.info("Loaded cached token (expires %s)",
                                datetime.fromtimestamp(self._token_expires, IST).strftime("%H:%M"))
            except (json.JSONDecodeError, KeyError):
                pass

    def _save_cached_token(self):
        TOKEN_CACHE.write_text(json.dumps({
            "access_token": self._token,
            "expires_at": self._token_expires,
            "cached_at": datetime.now(IST).isoformat(),
        }))

    def authenticate(self):
        """Keka OAuth2 — grant_type=kekaapi, scope=kekaapi."""
        missing = self.check_credentials()
        if missing:
            raise ValueError(f"Missing Keka credentials: {', '.join(missing)}")

        logger.info("Authenticating with Keka API (%s)…", self.base_url)
        resp = requests.post(self.TOKEN_URL, data={
            "grant_type": "kekaapi",
            "scope": "kekaapi",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "api_key": self.api_key,
        }, headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        }, timeout=30)

        if resp.status_code != 200:
            raise RuntimeError(
                f"Auth failed [{resp.status_code}]: {resp.text[:500]}"
            )

        data = resp.json()
        self._token = data["access_token"]
        self._token_expires = time.time() + data.get("expires_in", 86400) - 300
        self.session.headers["Authorization"] = f"Bearer {self._token}"
        self._save_cached_token()
        logger.info("✅ Authenticated successfully (token valid ~%dh)",
                     data.get("expires_in", 0) // 3600)

    def _ensure_auth(self):
        if not self._token or time.time() >= self._token_expires:
            self.authenticate()

    # ── Rate limiting (50 calls/min, 48 to leave buffer) ─────────────

    def _rate_limit(self):
        now = time.time()
        if now - self._minute_start >= 60:
            self._req_count = 0
            self._minute_start = now

        if self._req_count >= 48:
            wait = 60 - (now - self._minute_start) + 1
            if wait > 0:
                logger.info("Rate limit pause: %.1fs", wait)
                time.sleep(wait)
            self._req_count = 0
            self._minute_start = time.time()

        self._req_count += 1
        time.sleep(0.5)

    # ── HTTP with retry ───────────────────────────────────────────────

    def get(self, path: str, params: Dict = None, retries: int = 3) -> Any:
        self._ensure_auth()
        self._rate_limit()

        url = f"{self.base_url}{path}"
        for attempt in range(1, retries + 1):
            try:
                resp = self.session.get(url, params=params, timeout=30)
                if resp.status_code == 401:
                    logger.warning("401 — re-authenticating")
                    self.authenticate()
                    resp = self.session.get(url, params=params, timeout=30)
                if resp.status_code == 429:
                    wait = int(resp.headers.get("Retry-After", 30))
                    logger.warning("429 rate-limited, waiting %ds", wait)
                    time.sleep(wait)
                    continue
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException as e:
                if attempt < retries:
                    logger.warning("Request failed (attempt %d/%d): %s", attempt, retries, e)
                    time.sleep(attempt * 3)
                    continue
                raise

    def get_paginated(self, path: str, params: Dict = None,
                      max_pages: int = 100) -> List[Dict]:
        all_data = []
        params = dict(params or {})
        params.setdefault("pageSize", 100)

        for page in range(1, max_pages + 1):
            params["pageNumber"] = page
            resp = self.get(path, params)

            data = resp.get("data", resp.get("values", []))
            if isinstance(data, list):
                all_data.extend(data)
            elif isinstance(data, dict) and "values" in data:
                all_data.extend(data["values"])

            page_info = resp.get("pageInfo", resp.get("pagination", {}))
            total_pages = page_info.get("totalPages", page_info.get("total_pages", 1))
            if page >= total_pages:
                break
            logger.info("  Page %d/%d (%d records so far)", page, total_pages, len(all_data))

        return all_data


# ══════════════════════════════════════════════════════════════════════
# SQLite storage
# ══════════════════════════════════════════════════════════════════════

def _ensure_sqlite(db_path: str) -> sqlite3.Connection:
    """Open (or create) the SQLite DB with required schema."""
    os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS attendance (
            id TEXT PRIMARY KEY, employee_id TEXT, employee_number TEXT,
            attendance_date TEXT, day_type TEXT, clock_in TEXT,
            clock_out TEXT, total_hours REAL, gross_hours REAL,
            overtime_hours REAL, status TEXT, arrival_status TEXT,
            synced_at TEXT, UNIQUE(employee_id, attendance_date)
        );
        CREATE TABLE IF NOT EXISTS leave_requests (
            id TEXT PRIMARY KEY, employee_id TEXT, employee_number TEXT,
            employee_name TEXT, from_date TEXT, to_date TEXT,
            leave_type TEXT, status TEXT, reason TEXT,
            number_of_days REAL, raw_json TEXT, synced_at TEXT
        );
        CREATE TABLE IF NOT EXISTS sync_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT, entity TEXT,
            started_at TEXT, completed_at TEXT, records_synced INTEGER,
            status TEXT, error_message TEXT, date_from TEXT, date_to TEXT
        );
    """)
    return conn


def _now_ist() -> str:
    return datetime.now(IST).isoformat()


def _date_str(val) -> Optional[str]:
    if not val:
        return None
    return str(val)[:10] if "T" in str(val) else str(val)


def _day_type_str(day_type: int) -> str:
    return {0: "WorkingDay", 1: "Holiday", 2: "WeeklyOff"}.get(day_type, f"Type{day_type}")


def _classify_arrival(clock_in_str: Optional[str]) -> str:
    if not clock_in_str:
        return "ABSENT"
    try:
        dt = datetime.fromisoformat(clock_in_str.replace("Z", "+00:00")).astimezone(IST)
        mins = dt.hour * 60 + dt.minute
        if mins <= 630:
            return "ON_TIME"
        elif mins <= 660:
            return "BUFFER"
        else:
            return "DEDUCTED"
    except Exception:
        return "ABSENT"


def _leave_status_str(status: int) -> str:
    return {0: "Pending", 1: "Approved", 2: "Rejected", 3: "Cancelled"}.get(status, f"Status{status}")


# ══════════════════════════════════════════════════════════════════════
# PostgreSQL upsert (optional)
# ══════════════════════════════════════════════════════════════════════

def _pg_available() -> bool:
    try:
        import psycopg2
        from migration.config import DATABASE_URL_SYNC
        conn = psycopg2.connect(DATABASE_URL_SYNC)
        conn.close()
        return True
    except Exception:
        return False


def _pg_upsert_attendance(records: List[Dict]) -> int:
    """Upsert attendance records into PostgreSQL attendance_records table."""
    import uuid
    import psycopg2
    from migration.config import DATABASE_URL_SYNC
    from migration.migrate_attendance import (
        _parse_datetime, _hours_to_minutes, _resolve_status, _resolve_arrival,
    )

    conn = psycopg2.connect(DATABASE_URL_SYNC)
    cur = conn.cursor()

    # Build employee Keka→PG ID map
    cur.execute("SELECT id, keka_id FROM employees WHERE keka_id IS NOT NULL")
    emp_map = {str(row[1]): row[0] for row in cur.fetchall()}

    inserted = 0
    for rec in records:
        keka_emp_id = rec.get("employee_id", "")
        pg_emp_id = emp_map.get(keka_emp_id)
        if not pg_emp_id:
            continue

        att_date = rec.get("attendance_date", "")
        if not att_date:
            continue

        cur.execute(
            """INSERT INTO attendance_records
               (id, employee_id, date, status, arrival_status,
                first_clock_in, last_clock_out,
                total_work_minutes, effective_work_minutes,
                overtime_minutes, source)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT ON CONSTRAINT uq_attendance_emp_date
               DO UPDATE SET
                   status = EXCLUDED.status,
                   arrival_status = EXCLUDED.arrival_status,
                   first_clock_in = EXCLUDED.first_clock_in,
                   last_clock_out = EXCLUDED.last_clock_out,
                   total_work_minutes = EXCLUDED.total_work_minutes,
                   effective_work_minutes = EXCLUDED.effective_work_minutes,
                   overtime_minutes = EXCLUDED.overtime_minutes,
                   updated_at = NOW()""",
            (
                str(uuid.uuid4()),
                str(pg_emp_id),
                att_date,
                _resolve_status(rec.get("status")),
                _resolve_arrival(rec.get("arrival_status")),
                _parse_datetime(rec.get("clock_in")),
                _parse_datetime(rec.get("clock_out")),
                _hours_to_minutes(rec.get("total_hours")),
                _hours_to_minutes(rec.get("gross_hours")),
                _hours_to_minutes(rec.get("overtime_hours")),
                "keka_incremental_sync",
            ),
        )
        inserted += 1

    conn.commit()
    conn.close()
    return inserted


# ══════════════════════════════════════════════════════════════════════
# Sync functions
# ══════════════════════════════════════════════════════════════════════

def sync_attendance(client: KekaClient, from_date: str, to_date: str,
                    conn: sqlite3.Connection, dry_run: bool = False) -> Tuple[int, List[Dict]]:
    """Pull attendance data for date range. Returns (count, flat_records)."""
    logger.info("📋 Fetching attendance %s → %s", from_date, to_date)
    data = client.get_paginated("/time/attendance", {
        "fromDate": from_date,
        "toDate": to_date,
    })
    logger.info("  Received %d raw records from API", len(data))

    now = _now_ist()
    flat_records = []

    for rec in data:
        emp_id = rec.get("employeeId", "")
        att_date = _date_str(rec.get("attendanceDate"))
        clock_in = rec.get("originalClockIn", {})
        clock_out = rec.get("originalClockOut", {})
        ci_str = clock_in.get("dateTime") if isinstance(clock_in, dict) else None
        co_str = clock_out.get("dateTime") if isinstance(clock_out, dict) else None

        flat = {
            "id": rec.get("id", f"{emp_id}_{att_date}"),
            "employee_id": emp_id,
            "employee_number": rec.get("employeeNumber", ""),
            "attendance_date": att_date,
            "day_type": _day_type_str(rec.get("dayType", 0)),
            "clock_in": ci_str,
            "clock_out": co_str,
            "total_hours": rec.get("totalHours", 0),
            "gross_hours": rec.get("grossHours", 0),
            "overtime_hours": rec.get("overtimeHours", 0),
            "status": rec.get("status", ""),
            "arrival_status": _classify_arrival(ci_str),
            "synced_at": now,
        }
        flat_records.append(flat)

    if dry_run:
        logger.info("  [DRY RUN] Would insert %d attendance records", len(flat_records))
        return len(flat_records), flat_records

    for flat in flat_records:
        conn.execute(
            """INSERT OR REPLACE INTO attendance
               (id, employee_id, employee_number, attendance_date, day_type,
                clock_in, clock_out, total_hours, gross_hours, overtime_hours,
                status, arrival_status, synced_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            tuple(flat.values()),
        )

    conn.execute(
        "INSERT INTO sync_log (entity, started_at, completed_at, records_synced, "
        "status, date_from, date_to) VALUES (?,?,?,?,?,?,?)",
        ("attendance_incremental", now, _now_ist(), len(flat_records),
         "success", from_date, to_date),
    )
    conn.commit()
    logger.info("  ✅ Saved %d attendance records to SQLite", len(flat_records))
    return len(flat_records), flat_records


def sync_leaves(client: KekaClient, from_date: str, to_date: str,
                conn: sqlite3.Connection, dry_run: bool = False) -> int:
    """Pull leave requests for date range."""
    logger.info("📋 Fetching leave requests %s → %s", from_date, to_date)
    data = client.get_paginated("/time/leave", {
        "fromDate": from_date,
        "toDate": to_date,
    })
    logger.info("  Received %d raw records from API", len(data))

    now = _now_ist()
    count = 0

    for lr in data:
        leave_type = lr.get("leaveType", {})
        lt_name = leave_type.get("name", "") if isinstance(leave_type, dict) else str(leave_type)
        status_val = lr.get("status")
        status = _leave_status_str(status_val) if isinstance(status_val, int) else str(status_val or "Pending")

        if not dry_run:
            conn.execute(
                """INSERT OR REPLACE INTO leave_requests
                   (id, employee_id, employee_number, employee_name, from_date,
                    to_date, leave_type, status, reason, number_of_days,
                    raw_json, synced_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    lr.get("id"),
                    lr.get("employeeId", ""),
                    lr.get("employeeNumber", ""),
                    lr.get("employeeName", ""),
                    _date_str(lr.get("fromDate")),
                    _date_str(lr.get("toDate")),
                    lt_name,
                    status,
                    lr.get("reason", ""),
                    lr.get("numberOfDays", 0),
                    json.dumps(lr),
                    now,
                ))
        count += 1

    if not dry_run:
        conn.execute(
            "INSERT INTO sync_log (entity, started_at, completed_at, records_synced, "
            "status, date_from, date_to) VALUES (?,?,?,?,?,?,?)",
            ("leave_requests_incremental", now, _now_ist(), count,
             "success", from_date, to_date),
        )
        conn.commit()
        logger.info("  ✅ Saved %d leave requests to SQLite", count)
    else:
        logger.info("  [DRY RUN] Would insert %d leave requests", count)

    return count


# ══════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Keka API Incremental Sync — fill attendance/leave gaps",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --from 2026-02-17 --to 2026-02-20          # specific date range
  %(prog)s --days 3                                     # last 3 days
  %(prog)s --from 2026-02-17 --to 2026-02-20 --dry-run # test without writing
  %(prog)s --sqlite-only                                # skip PostgreSQL
        """,
    )
    parser.add_argument("--from", dest="from_date", type=str,
                        help="Start date (YYYY-MM-DD)")
    parser.add_argument("--to", dest="to_date", type=str,
                        help="End date (YYYY-MM-DD)")
    parser.add_argument("--days", type=int, default=3,
                        help="Days back from today (default: 3, ignored if --from/--to set)")
    parser.add_argument("--sqlite-only", action="store_true",
                        help="Sync to SQLite only, skip PostgreSQL upsert")
    parser.add_argument("--dry-run", action="store_true",
                        help="Fetch from API but don't write anywhere")
    parser.add_argument("--db", type=str,
                        help="SQLite database path (overrides auto-detection)")
    args = parser.parse_args()

    # ── Resolve dates ─────────────────────────────────────────────────
    now = datetime.now()
    if args.from_date and args.to_date:
        from_date = args.from_date
        to_date = args.to_date
    else:
        to_date = now.strftime("%Y-%m-%d")
        from_date = (now - timedelta(days=args.days)).strftime("%Y-%m-%d")

    # ── Resolve SQLite path ───────────────────────────────────────────
    db_path = args.db or SQLITE_PATH or str(PROJECT_ROOT / "data" / "keka.db")

    print(f"""
{'=' * 60}
  KEKA INCREMENTAL SYNC
  Date range : {from_date} → {to_date}
  SQLite     : {db_path}
  Dry run    : {args.dry_run}
  PG upsert  : {'skip' if args.sqlite_only else 'if available'}
{'=' * 60}
""")

    # ── Credentials check ─────────────────────────────────────────────
    client = KekaClient()
    missing = client.check_credentials()
    if missing:
        print(f"\n❌ BLOCKED — Missing Keka API credentials:\n")
        for var in missing:
            print(f"   • {var}")
        print(f"""
To fix: create {PROJECT_ROOT / '.env'} with:

    KEKA_API_KEY=<your-api-key>
    KEKA_CLIENT_ID=<your-client-id>
    KEKA_CLIENT_SECRET=<your-client-secret>

Get these from Keka Admin → Settings → API → Generate API Key
(Requires Keka Global Admin role)

Alternatively, set them as environment variables before running.
""")
        sys.exit(1)

    # ── Authenticate ──────────────────────────────────────────────────
    client.authenticate()

    # ── SQLite setup ──────────────────────────────────────────────────
    conn = _ensure_sqlite(db_path) if not args.dry_run else None

    # ── Sync attendance ───────────────────────────────────────────────
    att_count, att_records = sync_attendance(
        client, from_date, to_date, conn, dry_run=args.dry_run
    )

    # ── Sync leaves ───────────────────────────────────────────────────
    leave_count = sync_leaves(
        client, from_date, to_date, conn, dry_run=args.dry_run
    )

    # ── PostgreSQL upsert ─────────────────────────────────────────────
    pg_count = 0
    if not args.sqlite_only and not args.dry_run and att_records:
        if _pg_available():
            logger.info("📊 Upserting %d attendance records to PostgreSQL…", len(att_records))
            try:
                pg_count = _pg_upsert_attendance(att_records)
                logger.info("  ✅ Upserted %d records to PostgreSQL", pg_count)
            except Exception as e:
                logger.error("  ❌ PostgreSQL upsert failed: %s", e)
        else:
            logger.info("  ℹ️  PostgreSQL not available — skipping PG upsert")

    # ── Cleanup ───────────────────────────────────────────────────────
    if conn:
        conn.close()

    # ── Summary ───────────────────────────────────────────────────────
    print(f"""
{'=' * 60}
  SYNC COMPLETE
  Attendance : {att_count} records ({from_date} → {to_date})
  Leaves     : {leave_count} records
  PostgreSQL : {pg_count} upserted
  SQLite     : {db_path}
{'=' * 60}
""")


if __name__ == "__main__":
    main()
