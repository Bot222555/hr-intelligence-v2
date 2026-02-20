"""Migrate employees from Keka SQLite → PostgreSQL.

Two-pass approach:
  1. INSERT all employees (reporting_manager_id = NULL)
  2. UPDATE reporting_manager_id via keka_id mapping
"""

import json
import uuid
from datetime import date, datetime
from typing import Any, Dict, Optional

from migration.config import get_pg_conn, get_sqlite_conn
from migration.migrate_departments import get_dept_name_map

# ── Enum mappings ────────────────────────────────────────────────────

GENDER_MAP_INT = {0: "undisclosed", 1: "male", 2: "female", 3: "other"}
GENDER_MAP_STR = {"male": "male", "female": "female", "other": "other"}

# employment_status can be INTEGER or TEXT in Keka exports
EMPLOYMENT_STATUS_INT = {0: "active", 1: "active", 2: "notice_period", 3: "relieved"}
EMPLOYMENT_STATUS_STR = {
    "working": "active",
    "active": "active",
    "relieved": "relieved",
    "notice period": "notice_period",
    "absconding": "absconding",
}

MARITAL_STATUS_INT = {0: "single", 1: "married", 2: "divorced", 3: "widowed"}
MARITAL_STATUS_STR = {
    "single": "single", "married": "married",
    "divorced": "divorced", "widowed": "widowed",
    "unmarried": "single",
}

BLOOD_GROUP_MAP = {
    "A+": "A+", "A-": "A-", "B+": "B+", "B-": "B-",
    "O+": "O+", "O-": "O-", "AB+": "AB+", "AB-": "AB-",
    "A Positive": "A+", "A Negative": "A-",
    "B Positive": "B+", "B Negative": "B-",
    "O Positive": "O+", "O Negative": "O-",
    "AB Positive": "AB+", "AB Negative": "AB-",
}


def _parse_date(val: Any) -> Optional[date]:
    """Parse an ISO-ish date string; return None on failure."""
    if not val:
        return None
    if isinstance(val, date):
        return val
    s = str(val).strip()
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f",
                "%Y-%m-%dT%H:%M:%SZ", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(s[:19] if "T" in s else s, fmt).date()
        except ValueError:
            continue
    return None


def _resolve_gender(val: Any) -> str:
    if val is None:
        return "undisclosed"
    if isinstance(val, int):
        return GENDER_MAP_INT.get(val, "undisclosed")
    return GENDER_MAP_STR.get(str(val).lower(), "undisclosed")


def _resolve_employment_status(val: Any) -> str:
    if val is None:
        return "active"
    if isinstance(val, int):
        return EMPLOYMENT_STATUS_INT.get(val, "active")
    return EMPLOYMENT_STATUS_STR.get(str(val).strip().lower(), "active")


def _resolve_marital_status(val: Any) -> Optional[str]:
    if val is None:
        return None
    if isinstance(val, int):
        return MARITAL_STATUS_INT.get(val)
    return MARITAL_STATUS_STR.get(str(val).strip().lower())


def _resolve_blood_group(val: Any) -> Optional[str]:
    if not val:
        return None
    return BLOOD_GROUP_MAP.get(str(val).strip(), "unknown")


def _build_address_jsonb(addr: Any) -> Optional[dict]:
    """Convert Keka address (dict or string) to a JSONB-safe dict."""
    if not addr:
        return None
    if isinstance(addr, str):
        return {"raw": addr}
    if isinstance(addr, dict):
        return {
            "line1": addr.get("addressLine1", addr.get("line1", "")),
            "line2": addr.get("addressLine2", addr.get("line2", "")),
            "city": addr.get("city", ""),
            "state": addr.get("state", ""),
            "country": addr.get("country", "India"),
            "zip": addr.get("zipCode", addr.get("zip", addr.get("pinCode", ""))),
        }
    return None


def _build_emergency_contact(raw: dict) -> Optional[dict]:
    """Extract first emergency contact from Keka raw_json."""
    relations = raw.get("relations") or raw.get("emergencyContacts") or []
    if not relations:
        return None
    r = relations[0] if isinstance(relations, list) else relations
    return {
        "name": r.get("name", r.get("fullName", "")),
        "relation": r.get("relation", r.get("relationship", "")),
        "phone": r.get("phone", r.get("mobilePhone", r.get("phoneNumber", ""))),
    }


def _location_keywords_lookup(loc_text: str | None) -> str:
    """Map free-text location → canonical location name."""
    if loc_text and "mumbai" in loc_text.lower():
        return "Mumbai Office"
    return "Indore Office"


def migrate_employees(
    dept_map: Dict[str, uuid.UUID],
    loc_map: Dict[str, uuid.UUID],
) -> Dict[str, uuid.UUID]:
    """Migrate all employees. Returns {keka_employee_id: pg_uuid}."""
    sq = get_sqlite_conn()
    pg = get_pg_conn()

    try:
        # Build name-based dept lookup from PG
        dept_name_map = get_dept_name_map(pg)

        rows = sq.execute(
            """SELECT id, employee_number, first_name, last_name, display_name,
                      email, gender, date_of_birth, joining_date, exit_date,
                      employment_status, department, location, job_title,
                      reports_to_id, is_active, profile_picture_url, raw_json
               FROM employees"""
        ).fetchall()

        if not rows:
            print("  ⚠ No employees in SQLite — nothing to migrate")
            return {}

        emp_map: Dict[str, uuid.UUID] = {}  # keka_id -> new uuid
        inserts = []
        manager_updates = []  # (new_uuid, keka_reports_to_id)
        skipped = 0

        for r in rows:
            keka_id = r["id"]
            uid = uuid.uuid4()
            emp_map[keka_id] = uid

            # Parse raw_json for extended fields
            raw: dict = {}
            if r["raw_json"]:
                try:
                    raw = json.loads(r["raw_json"])
                except (json.JSONDecodeError, TypeError):
                    pass

            # Resolve department
            dept_text = (r["department"] or "").strip().lower()
            dept_uuid = dept_name_map.get(dept_text)
            if not dept_uuid and dept_text:
                # Try partial match
                for k, v in dept_name_map.items():
                    if dept_text in k or k in dept_text:
                        dept_uuid = v
                        break

            # Resolve location
            loc_name = _location_keywords_lookup(r["location"])
            loc_uuid = loc_map.get(loc_name, loc_map.get("Indore Office"))

            # Names — fallback to display_name split
            first_name = r["first_name"]
            last_name = r["last_name"]
            if not first_name and r["display_name"]:
                parts = r["display_name"].strip().split(None, 1)
                first_name = parts[0]
                last_name = parts[1] if len(parts) > 1 else ""
            first_name = first_name or "Unknown"
            last_name = last_name or ""

            # Email — required; skip if missing
            email = r["email"]
            if not email:
                print(f"  ⚠ Skipping employee {keka_id} ({first_name}): no email")
                skipped += 1
                continue

            # Employment status + is_active
            emp_status = _resolve_employment_status(r["employment_status"])
            is_active = bool(r["is_active"]) if r["is_active"] is not None else (
                emp_status == "active"
            )

            # Date of joining — required
            doj = _parse_date(r["joining_date"])
            if not doj:
                doj = date(2020, 1, 1)  # safe fallback
                print(f"  ⚠ Employee {email}: no joining_date, defaulting to 2020-01-01")

            rec = {
                "id": str(uid),
                "employee_code": r["employee_number"] or f"KEKA-{keka_id[:8]}",
                "first_name": first_name,
                "last_name": last_name,
                "email": email,
                "phone": raw.get("mobilePhone") or raw.get("phone"),
                "gender": _resolve_gender(r["gender"]),
                "date_of_birth": _parse_date(r["date_of_birth"]),
                "blood_group": _resolve_blood_group(raw.get("bloodGroup")),
                "marital_status": _resolve_marital_status(raw.get("maritalStatus")),
                "current_address": _build_address_jsonb(raw.get("currentAddress")),
                "permanent_address": _build_address_jsonb(raw.get("permanentAddress")),
                "emergency_contact": _build_emergency_contact(raw),
                "department_id": str(dept_uuid) if dept_uuid else None,
                "location_id": str(loc_uuid) if loc_uuid else None,
                "designation": r["job_title"],
                "employment_status": emp_status,
                "date_of_joining": doj,
                "date_of_exit": _parse_date(r["exit_date"]),
                "probation_end_date": _parse_date(raw.get("probationEndDate")),
                "profile_photo_url": r["profile_picture_url"],
                "is_active": is_active,
            }
            inserts.append(rec)

            if r["reports_to_id"]:
                manager_updates.append((uid, r["reports_to_id"]))

        # ── Pass 1: INSERT all employees ─────────────────────────────
        cur = pg.cursor()
        for rec in inserts:
            cur.execute(
                """INSERT INTO employees
                   (id, employee_code, first_name, last_name, email, phone,
                    gender, date_of_birth, blood_group, marital_status,
                    current_address, permanent_address, emergency_contact,
                    department_id, location_id, designation,
                    employment_status, date_of_joining, date_of_exit,
                    probation_end_date, profile_photo_url, is_active)
                   VALUES (
                    %(id)s, %(employee_code)s, %(first_name)s, %(last_name)s,
                    %(email)s, %(phone)s, %(gender)s, %(date_of_birth)s,
                    %(blood_group)s, %(marital_status)s,
                    %(current_address)s, %(permanent_address)s,
                    %(emergency_contact)s, %(department_id)s, %(location_id)s,
                    %(designation)s, %(employment_status)s, %(date_of_joining)s,
                    %(date_of_exit)s, %(probation_end_date)s,
                    %(profile_photo_url)s, %(is_active)s
                   )
                   ON CONFLICT (email) DO NOTHING""",
                {
                    **rec,
                    "current_address": json.dumps(rec["current_address"])
                        if rec["current_address"] else None,
                    "permanent_address": json.dumps(rec["permanent_address"])
                        if rec["permanent_address"] else None,
                    "emergency_contact": json.dumps(rec["emergency_contact"])
                        if rec["emergency_contact"] else None,
                },
            )
        pg.commit()

        # ── Pass 2: UPDATE reporting_manager_id ──────────────────────
        updated_mgr = 0
        for emp_uuid, keka_mgr_id in manager_updates:
            mgr_uuid = emp_map.get(keka_mgr_id)
            if mgr_uuid:
                cur.execute(
                    "UPDATE employees SET reporting_manager_id = %s WHERE id = %s",
                    (str(mgr_uuid), str(emp_uuid)),
                )
                updated_mgr += 1
            else:
                print(f"  ⚠ Manager {keka_mgr_id} not found for employee {emp_uuid}")
        pg.commit()

        print(f"  ✓ Migrated {len(inserts)} employees ({skipped} skipped)")
        print(f"  ✓ Set {updated_mgr} reporting manager relationships")
        return emp_map

    finally:
        sq.close()
        pg.close()


if __name__ == "__main__":
    # Standalone: requires departments migrated first
    from migration.migrate_departments import migrate_departments

    dept_map, loc_map = migrate_departments()
    emp_map = migrate_employees(dept_map, loc_map)
    print(f"\nEmployees migrated: {len(emp_map)}")
