#!/usr/bin/env python3
"""Fresh Keka API Sync → SQLite → PostgreSQL pipeline.

Authenticates with Keka OAuth2, pulls all data endpoints, updates the
SQLite backup, then triggers the full migration to PostgreSQL.

Usage:
    python -m migration.keka_api_sync                 # sync all + migrate
    python -m migration.keka_api_sync --sync-only     # sync to SQLite only
    python -m migration.keka_api_sync --entity employees  # single entity
    python -m migration.keka_api_sync --status        # show sync status

Requires:
    KEKA_API_KEY, KEKA_CLIENT_ID, KEKA_CLIENT_SECRET in .env (project root or workspace root)
"""

import argparse
import json
import logging
import os
import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from dotenv import load_dotenv

# ── Path setup ────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
WORKSPACE_ROOT = Path(os.path.expanduser("~/.openclaw/workspace"))

# Load .env from project root, then workspace
for env_path in [PROJECT_ROOT / ".env", WORKSPACE_ROOT / ".env"]:
    if env_path.exists():
        load_dotenv(env_path)

from migration.config import SQLITE_PATH, get_sqlite_conn

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("keka_sync")

IST = timezone(timedelta(hours=5, minutes=30))

# ── Token cache ───────────────────────────────────────────────────────
TOKEN_CACHE = Path(__file__).resolve().parent / ".keka_token_cache.json"


class KekaApiSyncer:
    """Sync all Keka API data into SQLite."""

    TOKEN_URL = "https://login.keka.com/connect/token"

    def __init__(self, sqlite_path: str = None):
        self.api_key = os.getenv("KEKA_API_KEY", "")
        self.client_id = os.getenv("KEKA_CLIENT_ID", "")
        self.client_secret = os.getenv("KEKA_CLIENT_SECRET", "")
        self.company = os.getenv("KEKA_COMPANY", "creativefuel")
        self.base_url = f"https://{self.company}.keka.com/api/v1"

        self._token: Optional[str] = None
        self._token_expires: float = 0
        self._request_count = 0
        self._minute_start = time.time()

        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/json",
            "User-Agent": "Mozilla",
        })

        self.db_path = sqlite_path or SQLITE_PATH
        if not self.db_path:
            raise FileNotFoundError("No SQLite database path configured")

        self._load_cached_token()
        self._ensure_schema()

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
                                datetime.fromtimestamp(self._token_expires).isoformat())
            except (json.JSONDecodeError, KeyError):
                pass

    def _save_cached_token(self):
        TOKEN_CACHE.write_text(json.dumps({
            "access_token": self._token,
            "expires_at": self._token_expires,
            "cached_at": datetime.now().isoformat(),
        }))

    def authenticate(self):
        """OAuth2 authentication with Keka API."""
        missing = []
        if not self.api_key:
            missing.append("KEKA_API_KEY")
        if not self.client_id:
            missing.append("KEKA_CLIENT_ID")
        if not self.client_secret:
            missing.append("KEKA_CLIENT_SECRET")
        if missing:
            raise ValueError(f"Missing credentials: {', '.join(missing)}")

        logger.info("Authenticating with Keka API...")
        resp = requests.post(self.TOKEN_URL, data={
            "grant_type": "kekaapi",
            "scope": "kekaapi",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "api_key": self.api_key,
        }, headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "User-Agent": "Mozilla",
        }, timeout=30)

        if resp.status_code != 200:
            raise RuntimeError(f"Auth failed [{resp.status_code}]: {resp.text}")

        data = resp.json()
        self._token = data["access_token"]
        self._token_expires = time.time() + data.get("expires_in", 86400) - 300
        self.session.headers["Authorization"] = f"Bearer {self._token}"
        self._save_cached_token()
        logger.info("Authenticated successfully")

    def _ensure_auth(self):
        if not self._token or time.time() >= self._token_expires:
            self.authenticate()

    # ── Rate limiting ─────────────────────────────────────────────────

    def _rate_limit(self):
        """Enforce 50 calls/minute rate limit."""
        now = time.time()
        if now - self._minute_start >= 60:
            self._request_count = 0
            self._minute_start = now

        if self._request_count >= 48:  # leave 2-call buffer
            wait = 60 - (now - self._minute_start) + 1
            if wait > 0:
                logger.info("Rate limit: waiting %.1fs", wait)
                time.sleep(wait)
            self._request_count = 0
            self._minute_start = time.time()

        self._request_count += 1
        time.sleep(0.5)  # min 500ms between requests

    # ── HTTP ──────────────────────────────────────────────────────────

    def _get(self, path: str, params: Dict = None, retries: int = 3) -> Any:
        """GET with retry and rate limiting."""
        self._ensure_auth()
        self._rate_limit()

        url = f"{self.base_url}{path}"
        for attempt in range(1, retries + 1):
            try:
                resp = self.session.get(url, params=params, timeout=30)
                if resp.status_code == 401:
                    self.authenticate()
                    resp = self.session.get(url, params=params, timeout=30)
                if resp.status_code == 429:
                    wait = int(resp.headers.get("Retry-After", 30))
                    logger.warning("Rate limited, waiting %ds", wait)
                    time.sleep(wait)
                    continue
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException as e:
                if attempt < retries:
                    time.sleep(attempt * 3)
                    continue
                raise

    def _get_paginated(self, path: str, params: Dict = None,
                       max_pages: int = 100) -> List[Dict]:
        """Fetch all pages from a paginated endpoint."""
        all_data = []
        params = dict(params or {})
        params.setdefault("pageSize", 100)

        for page in range(1, max_pages + 1):
            params["pageNumber"] = page
            resp = self._get(path, params)

            data = resp.get("data", resp.get("values", []))
            if isinstance(data, list):
                all_data.extend(data)
            elif isinstance(data, dict) and "values" in data:
                all_data.extend(data["values"])

            # Check if more pages
            page_info = resp.get("pageInfo", resp.get("pagination", {}))
            total_pages = page_info.get("totalPages", page_info.get("total_pages", 1))
            if page >= total_pages:
                break

        return all_data

    # ── SQLite schema ─────────────────────────────────────────────────

    def _ensure_schema(self):
        conn = sqlite3.connect(self.db_path)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS employees (
                id TEXT PRIMARY KEY, employee_number TEXT, first_name TEXT,
                last_name TEXT, display_name TEXT, email TEXT, gender INTEGER,
                date_of_birth TEXT, joining_date TEXT, exit_date TEXT,
                employment_status INTEGER, department TEXT, location TEXT,
                entity TEXT, job_title TEXT, reports_to_id TEXT,
                reports_to_name TEXT, l2_manager_id TEXT, l2_manager_name TEXT,
                is_active BOOLEAN, profile_picture_url TEXT, raw_json TEXT,
                synced_at TEXT
            );
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
            CREATE TABLE IF NOT EXISTS leave_balances (
                id INTEGER PRIMARY KEY AUTOINCREMENT, employee_id TEXT,
                employee_name TEXT, leave_type TEXT, balance REAL,
                used REAL, synced_at TEXT, UNIQUE(employee_id, leave_type)
            );
            CREATE TABLE IF NOT EXISTS departments (
                id TEXT PRIMARY KEY, name TEXT, parent_id TEXT,
                is_archived BOOLEAN, synced_at TEXT
            );
            CREATE TABLE IF NOT EXISTS helpdesk_tickets (
                id TEXT PRIMARY KEY, ticket_number TEXT, title TEXT,
                category TEXT, status TEXT, priority TEXT,
                raised_by TEXT, assigned_to TEXT, requested_on TEXT,
                synced_at TEXT
            );
            CREATE TABLE IF NOT EXISTS salaries (
                employee_id TEXT PRIMARY KEY, employee_number TEXT,
                ctc REAL, gross REAL, net_pay REAL,
                earnings_json TEXT, deductions_json TEXT,
                contributions_json TEXT, variables_json TEXT,
                synced_at TEXT
            );
            CREATE TABLE IF NOT EXISTS salary_components (
                id TEXT PRIMARY KEY, identifier TEXT, title TEXT,
                accounting_code TEXT, synced_at TEXT
            );
            CREATE TABLE IF NOT EXISTS expense_claims (
                id TEXT PRIMARY KEY, employee_id TEXT, employee_name TEXT,
                claim_number TEXT, title TEXT, amount REAL,
                currency TEXT, payment_status TEXT, approval_status TEXT,
                expenses_json TEXT, submitted_date TEXT, synced_at TEXT
            );
            CREATE TABLE IF NOT EXISTS fnf_settlements (
                id TEXT PRIMARY KEY, employee_id TEXT, employee_number TEXT,
                termination_type TEXT, last_working_day TEXT,
                no_of_pay_days REAL, raw_json TEXT, synced_at TEXT
            );
            CREATE TABLE IF NOT EXISTS helpdesk_responses (
                id INTEGER PRIMARY KEY AUTOINCREMENT, ticket_id TEXT NOT NULL,
                author_id TEXT NOT NULL, body TEXT NOT NULL,
                is_internal BOOLEAN DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (ticket_id) REFERENCES helpdesk_tickets(id)
            );
            CREATE TABLE IF NOT EXISTS sync_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT, entity TEXT,
                started_at TEXT, completed_at TEXT, records_synced INTEGER,
                status TEXT, error_message TEXT, date_from TEXT, date_to TEXT
            );
            CREATE TABLE IF NOT EXISTS last_sync_meta (
                key TEXT PRIMARY KEY, value TEXT, updated_at TEXT
            );
        """)
        conn.close()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _now_ist(self) -> str:
        return datetime.now(IST).isoformat()

    def _log_sync(self, conn, entity: str, count: int, status: str = "success",
                  error: str = None, date_from: str = None, date_to: str = None):
        now = self._now_ist()
        conn.execute(
            "INSERT INTO sync_log (entity, started_at, completed_at, records_synced, "
            "status, error_message, date_from, date_to) VALUES (?,?,?,?,?,?,?,?)",
            (entity, now, now, count, status, error, date_from, date_to))
        conn.execute(
            "INSERT OR REPLACE INTO last_sync_meta (key, value, updated_at) VALUES (?,?,?)",
            (entity, json.dumps({"records_synced": count, "last_sync": now, "status": status}), now))
        conn.commit()

    # ── Helper for extracting employee group info ─────────────────────

    @staticmethod
    def _extract_group(emp: dict, group_type: int) -> Optional[str]:
        for g in emp.get("groups", []):
            if g.get("groupType") == group_type:
                return g.get("title")
        return None

    @staticmethod
    def _date_str(val) -> Optional[str]:
        if not val:
            return None
        return str(val)[:10] if "T" in str(val) else str(val)

    @staticmethod
    def _leave_status_str(status: int) -> str:
        return {0: "Pending", 1: "Approved", 2: "Rejected", 3: "Cancelled"}.get(status, f"Status{status}")

    @staticmethod
    def _ticket_status_str(status: int) -> str:
        return {0: "Open", 1: "InProgress", 2: "Resolved", 3: "Closed"}.get(status, f"Status{status}")

    @staticmethod
    def _priority_str(p: int) -> str:
        return {0: "Low", 1: "Medium", 2: "High", 3: "Critical"}.get(p, f"P{p}")

    @staticmethod
    def _day_type_str(day_type: int) -> str:
        return {0: "WorkingDay", 1: "Holiday", 2: "WeeklyOff"}.get(day_type, f"Type{day_type}")

    @staticmethod
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

    # ── Sync: Employees ───────────────────────────────────────────────

    def sync_employees(self) -> int:
        logger.info("Syncing employees...")
        data = self._get_paginated("/hris/employees")
        conn = self._conn()
        now = self._now_ist()
        count = 0
        for emp in data:
            emp_id = emp.get("id", "")
            conn.execute(
                """INSERT OR REPLACE INTO employees
                   (id, employee_number, first_name, last_name, display_name,
                    email, gender, date_of_birth, joining_date, exit_date,
                    employment_status, department, location, entity, job_title,
                    reports_to_id, reports_to_name, l2_manager_id, l2_manager_name,
                    is_active, profile_picture_url, raw_json, synced_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    emp_id,
                    emp.get("employeeNumber", ""),
                    emp.get("firstName", ""),
                    emp.get("lastName", ""),
                    emp.get("displayName", ""),
                    emp.get("email", ""),
                    emp.get("gender"),
                    self._date_str(emp.get("dateOfBirth")),
                    self._date_str(emp.get("joiningDate")),
                    self._date_str(emp.get("lastWorkingDate") or emp.get("exitDate")),
                    emp.get("employmentStatus"),
                    self._extract_group(emp, 4) or emp.get("department", {}).get("name", ""),
                    self._extract_group(emp, 2) or emp.get("location", {}).get("name", ""),
                    self._extract_group(emp, 1) or "",
                    emp.get("jobTitle", ""),
                    (emp.get("reportingTo") or {}).get("id", ""),
                    (emp.get("reportingTo") or {}).get("displayName", ""),
                    (emp.get("l2Manager") or {}).get("id", ""),
                    (emp.get("l2Manager") or {}).get("displayName", ""),
                    emp.get("isActive", True),
                    emp.get("profilePictureUrl", ""),
                    json.dumps(emp),
                    now,
                ))
            count += 1
        conn.commit()
        self._log_sync(conn, "employees", count)
        conn.close()
        logger.info("Synced %d employees", count)
        return count

    # ── Sync: Departments ─────────────────────────────────────────────

    def sync_departments(self) -> int:
        logger.info("Syncing departments...")
        data = self._get_paginated("/hris/departments")
        conn = self._conn()
        now = self._now_ist()
        count = 0
        for dept in data:
            conn.execute(
                "INSERT OR REPLACE INTO departments (id, name, parent_id, is_archived, synced_at) "
                "VALUES (?,?,?,?,?)",
                (dept.get("id"), dept.get("name"), dept.get("parentId"),
                 dept.get("isArchived", False), now))
            count += 1
        conn.commit()
        self._log_sync(conn, "departments", count)
        conn.close()
        logger.info("Synced %d departments", count)
        return count

    # ── Sync: Attendance ──────────────────────────────────────────────

    def sync_attendance(self, from_date: str, to_date: str) -> int:
        logger.info("Syncing attendance %s → %s...", from_date, to_date)
        data = self._get_paginated("/time/attendance", {
            "fromDate": from_date,
            "toDate": to_date,
        })
        conn = self._conn()
        now = self._now_ist()
        count = 0
        for rec in data:
            emp_id = rec.get("employeeId", "")
            att_date = self._date_str(rec.get("attendanceDate"))
            clock_in = rec.get("originalClockIn", {})
            clock_out = rec.get("originalClockOut", {})
            ci_str = clock_in.get("dateTime") if isinstance(clock_in, dict) else None
            co_str = clock_out.get("dateTime") if isinstance(clock_out, dict) else None

            conn.execute(
                """INSERT OR REPLACE INTO attendance
                   (id, employee_id, employee_number, attendance_date, day_type,
                    clock_in, clock_out, total_hours, gross_hours, overtime_hours,
                    status, arrival_status, synced_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    rec.get("id", f"{emp_id}_{att_date}"),
                    emp_id,
                    rec.get("employeeNumber", ""),
                    att_date,
                    self._day_type_str(rec.get("dayType", 0)),
                    ci_str,
                    co_str,
                    rec.get("totalHours", 0),
                    rec.get("grossHours", 0),
                    rec.get("overtimeHours", 0),
                    rec.get("status", ""),
                    self._classify_arrival(ci_str),
                    now,
                ))
            count += 1
        conn.commit()
        self._log_sync(conn, "attendance", count, date_from=from_date, date_to=to_date)
        conn.close()
        logger.info("Synced %d attendance records", count)
        return count

    # ── Sync: Leave Requests ──────────────────────────────────────────

    def sync_leaves(self, from_date: str, to_date: str) -> int:
        logger.info("Syncing leave requests %s → %s...", from_date, to_date)
        data = self._get_paginated("/time/leave", {
            "fromDate": from_date,
            "toDate": to_date,
        })
        conn = self._conn()
        now = self._now_ist()
        count = 0
        for lr in data:
            leave_type = lr.get("leaveType", {})
            lt_name = leave_type.get("name", "") if isinstance(leave_type, dict) else str(leave_type)
            status_val = lr.get("status")
            status = self._leave_status_str(status_val) if isinstance(status_val, int) else str(status_val or "Pending")

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
                    self._date_str(lr.get("fromDate")),
                    self._date_str(lr.get("toDate")),
                    lt_name,
                    status,
                    lr.get("reason", ""),
                    lr.get("numberOfDays", 0),
                    json.dumps(lr),
                    now,
                ))
            count += 1
        conn.commit()
        self._log_sync(conn, "leave_requests", count, date_from=from_date, date_to=to_date)
        conn.close()
        logger.info("Synced %d leave requests", count)
        return count

    # ── Sync: Leave Balances ──────────────────────────────────────────

    def sync_leave_balances(self) -> int:
        logger.info("Syncing leave balances...")
        data = self._get_paginated("/time/leavebalance")
        conn = self._conn()
        now = self._now_ist()
        count = 0
        for lb in data:
            emp_id = lb.get("employeeId", "")
            emp_name = lb.get("employeeName", "")
            for bal in lb.get("leaveTypeBalances", [lb]):
                lt_name = bal.get("leaveTypeName", bal.get("leaveType", ""))
                if isinstance(lt_name, dict):
                    lt_name = lt_name.get("name", "")
                conn.execute(
                    """INSERT OR REPLACE INTO leave_balances
                       (employee_id, employee_name, leave_type, balance, used, synced_at)
                       VALUES (?,?,?,?,?,?)""",
                    (emp_id, emp_name, lt_name,
                     bal.get("balance", 0), bal.get("used", 0), now))
                count += 1
        conn.commit()
        self._log_sync(conn, "leave_balances", count)
        conn.close()
        logger.info("Synced %d leave balances", count)
        return count

    # ── Sync: Salaries ────────────────────────────────────────────────

    def sync_salaries(self) -> int:
        logger.info("Syncing salaries...")
        data = self._get_paginated("/payroll/salaries")
        conn = self._conn()
        now = self._now_ist()
        count = 0
        for sal in data:
            emp_id = sal.get("employeeId", sal.get("id", ""))
            conn.execute(
                """INSERT OR REPLACE INTO salaries
                   (employee_id, employee_number, ctc, gross, net_pay,
                    earnings_json, deductions_json, contributions_json,
                    variables_json, synced_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (
                    emp_id,
                    sal.get("employeeNumber", ""),
                    sal.get("ctc", 0),
                    sal.get("grossPay", sal.get("gross", 0)),
                    sal.get("netPay", sal.get("net_pay", 0)),
                    json.dumps(sal.get("earnings", [])),
                    json.dumps(sal.get("deductions", [])),
                    json.dumps(sal.get("contributions", [])),
                    json.dumps(sal.get("variables", [])),
                    now,
                ))
            count += 1
        conn.commit()
        self._log_sync(conn, "salaries", count)
        conn.close()
        logger.info("Synced %d salary records", count)
        return count

    # ── Sync: Salary Components ───────────────────────────────────────

    def sync_salary_components(self) -> int:
        logger.info("Syncing salary components...")
        data = self._get_paginated("/payroll/salarycomponents")
        conn = self._conn()
        now = self._now_ist()
        count = 0
        for comp in data:
            conn.execute(
                "INSERT OR REPLACE INTO salary_components (id, identifier, title, accounting_code, synced_at) "
                "VALUES (?,?,?,?,?)",
                (comp.get("id"), comp.get("identifier", ""),
                 comp.get("title", ""), comp.get("accountingCode", ""), now))
            count += 1
        conn.commit()
        self._log_sync(conn, "salary_components", count)
        conn.close()
        logger.info("Synced %d salary components", count)
        return count

    # ── Sync: Expense Claims ──────────────────────────────────────────

    def sync_expenses(self) -> int:
        logger.info("Syncing expense claims...")
        data = self._get_paginated("/finance/expenseclaims")
        conn = self._conn()
        now = self._now_ist()
        count = 0
        for exp in data:
            conn.execute(
                """INSERT OR REPLACE INTO expense_claims
                   (id, employee_id, employee_name, claim_number, title,
                    amount, currency, payment_status, approval_status,
                    expenses_json, submitted_date, synced_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    exp.get("id"),
                    exp.get("employeeId", ""),
                    exp.get("employeeName", ""),
                    exp.get("claimNumber", ""),
                    exp.get("title", ""),
                    exp.get("totalAmount", exp.get("amount", 0)),
                    exp.get("currency", "INR"),
                    exp.get("paymentStatus", ""),
                    exp.get("approvalStatus", ""),
                    json.dumps(exp.get("expenses", [])),
                    self._date_str(exp.get("submittedDate")),
                    now,
                ))
            count += 1
        conn.commit()
        self._log_sync(conn, "expense_claims", count)
        conn.close()
        logger.info("Synced %d expense claims", count)
        return count

    # ── Sync: Helpdesk ────────────────────────────────────────────────

    def sync_helpdesk(self) -> int:
        logger.info("Syncing helpdesk tickets...")
        data = self._get_paginated("/helpdesk/tickets")
        conn = self._conn()
        now = self._now_ist()
        count = 0
        for t in data:
            status_val = t.get("status")
            status = self._ticket_status_str(status_val) if isinstance(status_val, int) else str(status_val or "Open")
            priority_val = t.get("priority")
            priority = self._priority_str(priority_val) if isinstance(priority_val, int) else str(priority_val or "Medium")

            conn.execute(
                """INSERT OR REPLACE INTO helpdesk_tickets
                   (id, ticket_number, title, category, status, priority,
                    raised_by, assigned_to, requested_on, synced_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (
                    t.get("id"),
                    t.get("ticketNumber", ""),
                    t.get("title", t.get("subject", "")),
                    t.get("category", {}).get("name", "") if isinstance(t.get("category"), dict) else str(t.get("category", "")),
                    status,
                    priority,
                    t.get("raisedBy", t.get("requestedBy", {}).get("displayName", "")) if isinstance(t.get("requestedBy"), dict) else str(t.get("raisedBy", "")),
                    t.get("assignedTo", {}).get("displayName", "") if isinstance(t.get("assignedTo"), dict) else str(t.get("assignedTo", "")),
                    self._date_str(t.get("requestedOn", t.get("createdAt"))),
                    now,
                ))
            count += 1
        conn.commit()
        self._log_sync(conn, "helpdesk_tickets", count)
        conn.close()
        logger.info("Synced %d helpdesk tickets", count)
        return count

    # ── Sync: FnF ─────────────────────────────────────────────────────

    def sync_fnf(self) -> int:
        logger.info("Syncing FnF settlements...")
        data = self._get_paginated("/payroll/fnf")
        conn = self._conn()
        now = self._now_ist()
        count = 0
        for f in data:
            conn.execute(
                """INSERT OR REPLACE INTO fnf_settlements
                   (id, employee_id, employee_number, termination_type,
                    last_working_day, no_of_pay_days, raw_json, synced_at)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (
                    f.get("id"),
                    f.get("employeeId", ""),
                    f.get("employeeNumber", ""),
                    f.get("terminationType", ""),
                    self._date_str(f.get("lastWorkingDay")),
                    f.get("noOfPayDays", 0),
                    json.dumps(f),
                    now,
                ))
            count += 1
        conn.commit()
        self._log_sync(conn, "fnf_settlements", count)
        conn.close()
        logger.info("Synced %d FnF settlements", count)
        return count

    # ── Sync All ──────────────────────────────────────────────────────

    def sync_all(self, days_back: int = 365) -> Dict[str, Any]:
        """Sync all entities from Keka API."""
        now = datetime.now()
        from_date = (now - timedelta(days=days_back)).strftime("%Y-%m-%d")
        to_date = now.strftime("%Y-%m-%d")

        results = {}
        entities = [
            ("employees", lambda: self.sync_employees()),
            ("departments", lambda: self.sync_departments()),
            ("attendance", lambda: self.sync_attendance(from_date, to_date)),
            ("leave_requests", lambda: self.sync_leaves(from_date, to_date)),
            ("leave_balances", lambda: self.sync_leave_balances()),
            ("salaries", lambda: self.sync_salaries()),
            ("salary_components", lambda: self.sync_salary_components()),
            ("expense_claims", lambda: self.sync_expenses()),
            ("helpdesk_tickets", lambda: self.sync_helpdesk()),
            ("fnf_settlements", lambda: self.sync_fnf()),
        ]

        for name, sync_fn in entities:
            try:
                count = sync_fn()
                results[name] = count
                logger.info("✅ %s: %d records", name, count)
            except Exception as e:
                results[name] = f"ERROR: {e}"
                logger.error("❌ %s: %s", name, e)

        return results

    # ── Status ────────────────────────────────────────────────────────

    def show_status(self):
        conn = self._conn()
        rows = conn.execute(
            "SELECT key, value FROM last_sync_meta ORDER BY key"
        ).fetchall()
        if not rows:
            print("No sync history found. Run a sync first.")
            return
        print(f"\n{'Entity':<25} {'Last Sync':<28} {'Records':<10} {'Status'}")
        print("-" * 80)
        for row in rows:
            info = json.loads(row["value"])
            print(f"{row['key']:<25} {info.get('last_sync', 'never'):<28} "
                  f"{info.get('records_synced', '?'):<10} {info.get('status', '?')}")
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="Keka API Sync → SQLite → PostgreSQL")
    parser.add_argument("--sync-only", action="store_true", help="Sync to SQLite only, skip PG migration")
    parser.add_argument("--entity", type=str, help="Sync a specific entity")
    parser.add_argument("--status", action="store_true", help="Show sync status")
    parser.add_argument("--days", type=int, default=365, help="Days of history to sync (default: 365)")
    args = parser.parse_args()

    syncer = KekaApiSyncer()

    if args.status:
        syncer.show_status()
        return

    if args.entity:
        entity = args.entity.lower()
        now = datetime.now()
        from_date = (now - timedelta(days=args.days)).strftime("%Y-%m-%d")
        to_date = now.strftime("%Y-%m-%d")

        sync_map = {
            "employees": syncer.sync_employees,
            "departments": syncer.sync_departments,
            "attendance": lambda: syncer.sync_attendance(from_date, to_date),
            "leaves": lambda: syncer.sync_leaves(from_date, to_date),
            "leave_balances": syncer.sync_leave_balances,
            "salaries": syncer.sync_salaries,
            "salary_components": syncer.sync_salary_components,
            "expenses": syncer.sync_expenses,
            "helpdesk": syncer.sync_helpdesk,
            "fnf": syncer.sync_fnf,
        }
        if entity not in sync_map:
            print(f"Unknown entity: {entity}. Options: {', '.join(sync_map.keys())}")
            sys.exit(1)
        count = sync_map[entity]() if callable(sync_map[entity]) else sync_map[entity]()
        print(f"✅ Synced {count} {entity} records")
    else:
        print(f"\n{'=' * 55}")
        print("  KEKA API → SQLITE FRESH SYNC")
        print(f"{'=' * 55}\n")
        results = syncer.sync_all(days_back=args.days)
        print(f"\n{'Entity':<25} {'Records'}")
        print("-" * 40)
        for entity, count in results.items():
            status = "✅" if isinstance(count, int) else "❌"
            print(f"  {status} {entity:<23} {count}")

    if not args.sync_only:
        print(f"\n{'=' * 55}")
        print("  SQLITE → POSTGRESQL MIGRATION")
        print(f"{'=' * 55}\n")
        from migration.migrate_all import run_migration
        run_migration()


if __name__ == "__main__":
    main()
