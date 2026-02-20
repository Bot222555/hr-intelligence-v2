"""Migrate leave balances and leave requests from Keka SQLite → PostgreSQL.

Reads leave_type UUIDs from PG (seeded separately), then maps Keka
leave data using type names.
"""

import json
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, Optional, Tuple

from migration.config import get_pg_conn, get_sqlite_conn

# ── Leave type name normalization ────────────────────────────────────
# Maps common Keka leave type strings → leave_types.code in PG
LEAVE_TYPE_ALIASES = {
    "casual leave": "CL",
    "cl": "CL",
    "privilege leave": "PL",
    "earned leave": "PL",
    "pl": "PL",
    "el": "PL",
    "comp off": "CO",
    "compensatory off": "CO",
    "co": "CO",
    "maternity leave": "ML",
    "ml": "ML",
    "sick leave": "SL",
    "sl": "SL",
    "unpaid leave": "UL",
    "loss of pay": "UL",
    "lop": "UL",
    "lwp": "UL",
    "ul": "UL",
    "paternity leave": "PL",  # fallback
    "bereavement leave": "CL",  # fallback
    "optional holiday": "CL",  # fallback
}

# Leave request status mapping
LEAVE_STATUS_MAP = {
    "approved": "approved",
    "pending": "pending",
    "rejected": "rejected",
    "cancelled": "cancelled",
    "canceled": "cancelled",
    "revoked": "revoked",
}


def _get_leave_type_map(pg) -> Dict[str, uuid.UUID]:
    """Fetch {code: uuid} from leave_types table."""
    cur = pg.cursor()
    cur.execute("SELECT id, code, name FROM leave_types")
    result = {}
    for row in cur.fetchall():
        lt_id = uuid.UUID(str(row[0]))
        result[row[1].upper()] = lt_id
        result[row[2].strip().lower()] = lt_id
    return result


def _resolve_leave_type(
    type_name: str | None, lt_map: Dict[str, uuid.UUID]
) -> Optional[uuid.UUID]:
    """Map Keka leave type name → leave_type UUID."""
    if not type_name:
        return None
    key = type_name.strip().lower()

    # Direct match by code
    upper = key.upper()
    if upper in lt_map:
        return lt_map[upper]

    # Alias lookup
    code = LEAVE_TYPE_ALIASES.get(key)
    if code and code in lt_map:
        return lt_map[code]

    # Partial match
    for alias, c in LEAVE_TYPE_ALIASES.items():
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
    from datetime import timedelta
    while current <= to_date and remaining > 0:
        if remaining >= 1:
            details.append({"date": current.isoformat(), "type": "full_day"})
            remaining -= 1
        else:
            details.append({"date": current.isoformat(), "type": "first_half"})
            remaining = 0
        current += timedelta(days=1)
    return details


def migrate_leaves(emp_map: Dict[str, uuid.UUID]) -> Tuple[int, int]:
    """Migrate leave balances and requests. Returns (balance_count, request_count)."""
    sq = get_sqlite_conn()
    pg = get_pg_conn()

    try:
        lt_map = _get_leave_type_map(pg)
        if not lt_map:
            print("  ⚠ No leave_types in PostgreSQL — run seed first")
            return 0, 0

        cur = pg.cursor()
        current_year = datetime.now().year

        # ── Migrate leave_balances ───────────────────────────────────
        bal_rows = sq.execute(
            "SELECT employee_id, leave_type, balance, used FROM leave_balances"
        ).fetchall()

        bal_count = 0
        bal_skipped = 0
        for r in bal_rows:
            pg_emp_id = emp_map.get(r["employee_id"])
            if not pg_emp_id:
                bal_skipped += 1
                continue

            lt_id = _resolve_leave_type(r["leave_type"], lt_map)
            if not lt_id:
                print(f"  ⚠ Unknown leave type '{r['leave_type']}' — skipping balance")
                bal_skipped += 1
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
        print(f"  ✓ Migrated {bal_count} leave balances ({bal_skipped} skipped)")

        # ── Migrate leave_requests ───────────────────────────────────
        req_rows = sq.execute(
            """SELECT id, employee_id, from_date, to_date, leave_type,
                      status, reason, number_of_days
               FROM leave_requests"""
        ).fetchall()

        req_count = 0
        req_skipped = 0
        for r in req_rows:
            pg_emp_id = emp_map.get(r["employee_id"])
            if not pg_emp_id:
                req_skipped += 1
                continue

            lt_id = _resolve_leave_type(r["leave_type"], lt_map)
            if not lt_id:
                print(f"  ⚠ Unknown leave type '{r['leave_type']}' — skipping request")
                req_skipped += 1
                continue

            start = _parse_date(r["from_date"])
            end = _parse_date(r["to_date"])
            if not start or not end:
                req_skipped += 1
                continue

            num_days = float(r["number_of_days"] or 1)
            status = LEAVE_STATUS_MAP.get(
                str(r["status"] or "pending").strip().lower(), "pending"
            )

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
        print(f"  ✓ Migrated {req_count} leave requests ({req_skipped} skipped)")
        return bal_count, req_count

    finally:
        sq.close()
        pg.close()


if __name__ == "__main__":
    from migration.migrate_departments import migrate_departments
    from migration.migrate_employees import migrate_employees

    dept_map, loc_map = migrate_departments()
    emp_map = migrate_employees(dept_map, loc_map)
    bal, req = migrate_leaves(emp_map)
    print(f"\nLeave balances: {bal}, Leave requests: {req}")
