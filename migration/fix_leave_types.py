"""Fix missing leave types and re-migrate skipped leave records.

Adds missing leave types to PostgreSQL:
  - Privileged Leave → maps to PL (already exists, add alias)
  - Special Leave → new type SPL
  - Miscarriage Leave → new type MCL

Then re-runs leave balance and leave request migration for records that
were previously skipped due to unresolvable leave types.
"""

import json
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, Optional, Tuple

from migration.config import get_pg_conn, get_sqlite_conn


# ── New leave types to insert ─────────────────────────────────────────

NEW_LEAVE_TYPES = [
    {
        "code": "SPL",
        "name": "Special Leave",
        "description": "Special leave for extraordinary circumstances",
        "default_balance": 0,
        "max_carry_forward": 0,
        "is_paid": True,
        "requires_approval": True,
        "min_days_notice": 0,
        "max_consecutive_days": 30,
        "applicable_gender": None,
    },
    {
        "code": "MCL",
        "name": "Miscarriage Leave",
        "description": "Leave following miscarriage as per policy",
        "default_balance": 42,
        "max_carry_forward": 0,
        "is_paid": True,
        "requires_approval": True,
        "min_days_notice": 0,
        "max_consecutive_days": 42,
        "applicable_gender": "female",
    },
    {
        "code": "WFH",
        "name": "Work From Home",
        "description": "Work from home / remote working day",
        "default_balance": 0,
        "max_carry_forward": 0,
        "is_paid": True,
        "requires_approval": True,
        "min_days_notice": 0,
        "max_consecutive_days": None,
        "applicable_gender": None,
    },
    {
        "code": "OH",
        "name": "Optional Holiday",
        "description": "Optional / restricted / floating holiday",
        "default_balance": 2,
        "max_carry_forward": 0,
        "is_paid": True,
        "requires_approval": True,
        "min_days_notice": 1,
        "max_consecutive_days": 1,
        "applicable_gender": None,
    },
    {
        "code": "BL",
        "name": "Bereavement Leave",
        "description": "Leave for family bereavement",
        "default_balance": 5,
        "max_carry_forward": 0,
        "is_paid": True,
        "requires_approval": True,
        "min_days_notice": 0,
        "max_consecutive_days": 5,
        "applicable_gender": None,
    },
    {
        "code": "MRL",
        "name": "Marriage Leave",
        "description": "Leave for own marriage",
        "default_balance": 3,
        "max_carry_forward": 0,
        "is_paid": True,
        "requires_approval": True,
        "min_days_notice": 7,
        "max_consecutive_days": 15,
        "applicable_gender": None,
    },
    {
        "code": "PTL",
        "name": "Paternity Leave",
        "description": "Paternity leave for new fathers",
        "default_balance": 5,
        "max_carry_forward": 0,
        "is_paid": True,
        "requires_approval": True,
        "min_days_notice": 7,
        "max_consecutive_days": 15,
        "applicable_gender": "male",
    },
    {
        "code": "EL",
        "name": "Earned Leave",
        "description": "Earned / annual leave accrued over service",
        "default_balance": 15,
        "max_carry_forward": 30,
        "is_paid": True,
        "requires_approval": True,
        "min_days_notice": 3,
        "max_consecutive_days": None,
        "applicable_gender": None,
    },
    {
        "code": "LOP",
        "name": "Loss of Pay",
        "description": "Unpaid leave / loss of pay",
        "default_balance": 0,
        "max_carry_forward": 0,
        "is_paid": False,
        "requires_approval": True,
        "min_days_notice": 0,
        "max_consecutive_days": None,
        "applicable_gender": None,
    },
]

# Extended alias map including the previously missing types
EXTENDED_LEAVE_ALIASES = {
    # Casual Leave
    "casual leave": "CL",
    "cl": "CL",
    "casual": "CL",
    "half day": "CL",
    "short leave": "CL",
    "birthday leave": "CL",
    "birthday off": "CL",
    "emergency leave": "CL",
    # Sick Leave
    "sick leave": "SL",
    "sl": "SL",
    "sick": "SL",
    "medical leave": "SL",
    # Privilege / Earned Leave
    "privilege leave": "PL",
    "privileged leave": "PL",
    "pl": "PL",
    "earned leave": "EL",
    "el": "EL",
    "annual leave": "EL",
    # Comp Off
    "comp off": "CO",
    "compensatory off": "CO",
    "compensatory leave": "CO",
    "comp-off": "CO",
    "compoff": "CO",
    "co": "CO",
    # Maternity Leave
    "maternity leave": "ML",
    "ml": "ML",
    "maternity": "ML",
    # Paternity Leave
    "paternity leave": "PTL",
    "paternity": "PTL",
    "ptl": "PTL",
    # Loss of Pay / Unpaid
    "unpaid leave": "LOP",
    "loss of pay": "LOP",
    "lop": "LOP",
    "lwp": "LOP",
    "leave without pay": "LOP",
    "ul": "LOP",
    "sabbatical": "LOP",
    "sabbatical leave": "LOP",
    # Work From Home
    "work from home": "WFH",
    "wfh": "WFH",
    "remote work": "WFH",
    "remote working": "WFH",
    # Optional / Restricted Holiday
    "optional holiday": "OH",
    "restricted holiday": "OH",
    "oh": "OH",
    "rh": "OH",
    "floating holiday": "OH",
    # Bereavement Leave
    "bereavement leave": "BL",
    "bereavement": "BL",
    "bl": "BL",
    # Marriage Leave
    "marriage leave": "MRL",
    "mrl": "MRL",
    "wedding leave": "MRL",
    # Special Leave
    "special leave": "SPL",
    "spl": "SPL",
    "study leave": "SPL",
    # Miscarriage / Child Care Leave
    "miscarriage leave": "MCL",
    "mcl": "MCL",
    "menstrual leave": "MCL",
    "menstrual/child care leave": "MCL",
    "period leave": "MCL",
    "child care leave": "MCL",
}


def _get_leave_type_map(pg) -> Dict[str, uuid.UUID]:
    """Fetch {code: uuid} and {name.lower(): uuid} from leave_types table."""
    cur = pg.cursor()
    cur.execute("SELECT id, code, name FROM leave_types")
    result = {}
    for row in cur.fetchall():
        lt_id = uuid.UUID(str(row[0]))
        result[row[1].upper()] = lt_id
        result[row[2].strip().lower()] = lt_id
    return result


def _resolve_leave_type(
    type_name: str, lt_map: Dict[str, uuid.UUID]
) -> Optional[uuid.UUID]:
    """Map Keka leave type name → leave_type UUID using extended aliases."""
    if not type_name:
        return None
    key = type_name.strip().lower()
    upper = key.upper()
    if upper in lt_map:
        return lt_map[upper]
    code = EXTENDED_LEAVE_ALIASES.get(key)
    if code and code in lt_map:
        return lt_map[code]
    for alias, c in EXTENDED_LEAVE_ALIASES.items():
        if alias in key or key in alias:
            if c in lt_map:
                return lt_map[c]
    return None


def _parse_date(val: Any) -> Optional[date]:
    if not val:
        return None
    s = str(val).strip()
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f",
                "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(s[:19] if "T" in s else s, fmt).date()
        except ValueError:
            continue
    return None


def _build_day_details(from_date: date, to_date: date, num_days: float) -> list:
    """Build day_details JSONB array for leave requests."""
    details = []
    current = from_date
    remaining = num_days
    while current <= to_date and remaining > 0:
        if remaining >= 1:
            details.append({"date": current.isoformat(), "type": "full_day"})
            remaining -= 1
        else:
            details.append({"date": current.isoformat(), "type": "first_half"})
            remaining = 0
        current += timedelta(days=1)
    return details


def add_missing_leave_types() -> int:
    """Insert missing leave types into PostgreSQL."""
    pg = get_pg_conn()
    cur = pg.cursor()
    added = 0

    for lt in NEW_LEAVE_TYPES:
        cur.execute("SELECT id FROM leave_types WHERE code = %s", (lt["code"],))
        if cur.fetchone():
            print(f"  ⏭ Leave type '{lt['code']}' ({lt['name']}) already exists")
            continue

        cur.execute(
            """INSERT INTO leave_types
               (code, name, description, default_balance, max_carry_forward,
                is_paid, requires_approval, min_days_notice, max_consecutive_days,
                applicable_gender)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                lt["code"], lt["name"], lt["description"],
                lt["default_balance"], lt["max_carry_forward"],
                lt["is_paid"], lt["requires_approval"],
                lt["min_days_notice"], lt["max_consecutive_days"],
                lt["applicable_gender"],
            ),
        )
        added += 1
        print(f"  ✓ Added leave type '{lt['code']}' ({lt['name']})")

    pg.commit()
    pg.close()
    return added


def remigrate_skipped_leaves(emp_map: Dict[str, uuid.UUID]) -> Tuple[int, int]:
    """Re-migrate leave balances and requests that were previously skipped.

    Only processes records that don't already exist in PostgreSQL.
    """
    sq = get_sqlite_conn()
    pg = get_pg_conn()

    try:
        lt_map = _get_leave_type_map(pg)
        if not lt_map:
            print("  ⚠ No leave_types in PostgreSQL — run seed first")
            return 0, 0

        cur = pg.cursor()
        current_year = datetime.now().year

        # ── Re-migrate leave_balances ────────────────────────────────
        bal_rows = sq.execute(
            "SELECT employee_id, leave_type, balance, used FROM leave_balances"
        ).fetchall()

        bal_count = 0
        bal_still_skipped = 0
        for r in bal_rows:
            pg_emp_id = emp_map.get(r["employee_id"])
            if not pg_emp_id:
                continue

            lt_id = _resolve_leave_type(r["leave_type"], lt_map)
            if not lt_id:
                bal_still_skipped += 1
                if r["leave_type"]:
                    print(f"  ⚠ Still unmapped leave type: '{r['leave_type']}'")
                continue

            opening = float(r["balance"] or 0)
            used = float(r["used"] or 0)

            cur.execute(
                """INSERT INTO leave_balances
                   (id, employee_id, leave_type_id, year, opening_balance, used)
                   VALUES (%s, %s, %s, %s, %s, %s)
                   ON CONFLICT ON CONSTRAINT uq_leave_balance DO UPDATE
                   SET opening_balance = EXCLUDED.opening_balance,
                       used = EXCLUDED.used""",
                (str(uuid.uuid4()), str(pg_emp_id), str(lt_id),
                 current_year, opening, used),
            )
            bal_count += 1

        pg.commit()
        print(f"  ✓ Re-migrated {bal_count} leave balances ({bal_still_skipped} still unmapped)")

        # ── Re-migrate leave_requests ────────────────────────────────
        req_rows = sq.execute(
            """SELECT id, employee_id, from_date, to_date, leave_type,
                      status, reason, number_of_days
               FROM leave_requests"""
        ).fetchall()

        req_count = 0
        req_still_skipped = 0
        for r in req_rows:
            pg_emp_id = emp_map.get(r["employee_id"])
            if not pg_emp_id:
                continue

            lt_id = _resolve_leave_type(r["leave_type"], lt_map)
            if not lt_id:
                req_still_skipped += 1
                continue

            start = _parse_date(r["from_date"])
            end = _parse_date(r["to_date"])
            if not start or not end:
                continue

            num_days = float(r["number_of_days"] or 1)
            status_raw = str(r["status"] or "pending").strip().lower()
            status_map = {
                "approved": "approved", "pending": "pending",
                "rejected": "rejected", "cancelled": "cancelled",
                "canceled": "cancelled", "revoked": "revoked",
            }
            status = status_map.get(status_raw, "pending")

            day_details = _build_day_details(start, end, num_days)

            cur.execute(
                """INSERT INTO leave_requests
                   (id, employee_id, leave_type_id, start_date, end_date,
                    day_details, total_days, reason, status)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT DO NOTHING""",
                (
                    str(uuid.uuid4()), str(pg_emp_id), str(lt_id),
                    start, end, json.dumps(day_details), num_days,
                    r["reason"], status,
                ),
            )
            req_count += 1

        pg.commit()
        print(f"  ✓ Re-migrated {req_count} leave requests ({req_still_skipped} still unmapped)")
        return bal_count, req_count

    finally:
        sq.close()
        pg.close()


def fix_leave_types(emp_map: Dict[str, uuid.UUID]) -> Tuple[int, int, int]:
    """Full fix: add missing types, then re-migrate skipped records.

    Returns:
        (types_added, balances_migrated, requests_migrated)
    """
    print("\n  Adding missing leave types...")
    types_added = add_missing_leave_types()

    print("\n  Re-migrating previously skipped leave records...")
    bal, req = remigrate_skipped_leaves(emp_map)

    return types_added, bal, req


if __name__ == "__main__":
    from migration.migrate_departments import migrate_departments
    from migration.migrate_employees import migrate_employees

    dept_map, loc_map = migrate_departments()
    emp_map = migrate_employees(dept_map, loc_map)
    types, bal, req = fix_leave_types(emp_map)
    print(f"\nLeave types added: {types}")
    print(f"Leave balances re-migrated: {bal}")
    print(f"Leave requests re-migrated: {req}")
