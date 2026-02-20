"""Migrate attendance records from Keka SQLite → PostgreSQL.

Maps to the attendance_records table with proper enum values and
minutes-based durations.
"""

import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from migration.config import get_pg_conn, get_sqlite_conn

# ── Status mappings ──────────────────────────────────────────────────

ATTENDANCE_STATUS_MAP = {
    "present": "present",
    "absent": "absent",
    "weeklyoff": "weekend",
    "weekly off": "weekend",
    "holiday": "holiday",
    "leave": "on_leave",
    "halfday": "half_day",
    "half day": "half_day",
    "workfromhome": "work_from_home",
    "work from home": "work_from_home",
    "wfh": "work_from_home",
    "onduty": "on_duty",
    "on duty": "on_duty",
}

ARRIVAL_STATUS_MAP = {
    "ontime": "on_time",
    "on time": "on_time",
    "late": "late",
    "verylate": "very_late",
    "very late": "very_late",
    "absent": "absent",
}


def _parse_datetime(val: Any) -> Optional[datetime]:
    """Parse clock-in/out datetime strings."""
    if not val:
        return None
    s = str(val).strip()
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f",
                "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%d %H:%M:%S.%f"):
        try:
            return datetime.strptime(s[:26], fmt)
        except ValueError:
            continue
    return None


def _hours_to_minutes(hours: Any) -> Optional[int]:
    """Convert hours (float) to minutes (int)."""
    if hours is None:
        return None
    try:
        return int(float(hours) * 60)
    except (ValueError, TypeError):
        return None


def _resolve_status(val: Any) -> str:
    if not val:
        return "absent"
    return ATTENDANCE_STATUS_MAP.get(str(val).strip().lower(), "present")


def _resolve_arrival(val: Any) -> Optional[str]:
    if not val:
        return None
    return ARRIVAL_STATUS_MAP.get(str(val).strip().lower())


def migrate_attendance(emp_map: Dict[str, uuid.UUID]) -> int:
    """Migrate attendance records. Returns count of inserted records."""
    sq = get_sqlite_conn()
    pg = get_pg_conn()

    try:
        rows = sq.execute(
            """SELECT employee_id, attendance_date, clock_in, clock_out,
                      total_hours, gross_hours, overtime_hours,
                      status, arrival_status
               FROM attendance"""
        ).fetchall()

        if not rows:
            print("  ⚠ No attendance records in SQLite — nothing to migrate")
            return 0

        cur = pg.cursor()
        batch = []
        skipped = 0

        for r in rows:
            keka_emp_id = r["employee_id"]
            pg_emp_id = emp_map.get(keka_emp_id)
            if not pg_emp_id:
                skipped += 1
                continue

            att_date = r["attendance_date"]
            if not att_date:
                skipped += 1
                continue

            # Parse date (just the date part)
            try:
                if "T" in str(att_date):
                    att_date = str(att_date)[:10]
            except Exception:
                skipped += 1
                continue

            batch.append((
                str(uuid.uuid4()),               # id
                str(pg_emp_id),                   # employee_id
                att_date,                         # date
                _resolve_status(r["status"]),     # status
                _resolve_arrival(r["arrival_status"]),  # arrival_status
                _parse_datetime(r["clock_in"]),   # first_clock_in
                _parse_datetime(r["clock_out"]),  # last_clock_out
                _hours_to_minutes(r["total_hours"]),     # total_work_minutes
                _hours_to_minutes(r["gross_hours"]),     # effective_work_minutes
                _hours_to_minutes(r["overtime_hours"]),  # overtime_minutes
                "keka_migration",                 # source
            ))

        # Batch insert
        BATCH_SIZE = 500
        inserted = 0
        for i in range(0, len(batch), BATCH_SIZE):
            chunk = batch[i : i + BATCH_SIZE]
            cur.executemany(
                """INSERT INTO attendance_records
                   (id, employee_id, date, status, arrival_status,
                    first_clock_in, last_clock_out,
                    total_work_minutes, effective_work_minutes,
                    overtime_minutes, source)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT ON CONSTRAINT uq_attendance_emp_date DO NOTHING""",
                chunk,
            )
            inserted += cur.rowcount
            pg.commit()

        print(f"  ✓ Migrated {inserted} attendance records ({skipped} skipped)")
        return inserted

    finally:
        sq.close()
        pg.close()


if __name__ == "__main__":
    from migration.migrate_departments import migrate_departments
    from migration.migrate_employees import migrate_employees

    dept_map, loc_map = migrate_departments()
    emp_map = migrate_employees(dept_map, loc_map)
    count = migrate_attendance(emp_map)
    print(f"\nAttendance records migrated: {count}")
