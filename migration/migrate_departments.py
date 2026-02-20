"""Migrate departments from Keka SQLite → PostgreSQL.

Also seeds Location records (Indore Office, Mumbai Office).
Returns mapping dicts for downstream migrations.
"""

import uuid
from typing import Dict, Tuple

from migration.config import get_pg_conn, get_sqlite_conn

# ── Seed locations ───────────────────────────────────────────────────
LOCATIONS = [
    {
        "name": "Indore Office",
        "city": "Indore",
        "state": "Madhya Pradesh",
        "address": "Creativefuel, Indore, MP",
        "timezone": "Asia/Kolkata",
    },
    {
        "name": "Mumbai Office",
        "city": "Mumbai",
        "state": "Maharashtra",
        "address": "Creativefuel, Mumbai, MH",
        "timezone": "Asia/Kolkata",
    },
]

# Keywords in location text → location name
_LOCATION_KEYWORDS = {
    "mumbai": "Mumbai Office",
    "bombay": "Mumbai Office",
}


def _resolve_location(location_text: str | None) -> str:
    """Map free-text location to a canonical location name (default: Indore)."""
    if location_text:
        lower = location_text.lower()
        for kw, loc_name in _LOCATION_KEYWORDS.items():
            if kw in lower:
                return loc_name
    return "Indore Office"


def seed_locations(pg) -> Dict[str, uuid.UUID]:
    """Insert seed locations; return {name: uuid} mapping."""
    cur = pg.cursor()
    loc_map: Dict[str, uuid.UUID] = {}

    for loc in LOCATIONS:
        uid = uuid.uuid4()
        cur.execute(
            """INSERT INTO locations (id, name, city, state, address, timezone)
               VALUES (%s, %s, %s, %s, %s, %s)
               ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name
               RETURNING id""",
            (str(uid), loc["name"], loc["city"], loc["state"],
             loc["address"], loc["timezone"]),
        )
        row = cur.fetchone()
        loc_map[loc["name"]] = uuid.UUID(str(row[0]))

    pg.commit()
    return loc_map


def migrate_departments() -> Tuple[Dict[str, uuid.UUID], Dict[str, uuid.UUID]]:
    """Migrate departments. Returns (dept_map, loc_map).

    dept_map: {keka_dept_id: pg_uuid}
    loc_map:  {location_name: pg_uuid}
    """
    sq = get_sqlite_conn()
    pg = get_pg_conn()

    try:
        loc_map = seed_locations(pg)
        print(f"  ✓ Seeded {len(loc_map)} locations")

        rows = sq.execute(
            "SELECT id, name, parent_id, is_archived FROM departments"
        ).fetchall()

        if not rows:
            print("  ⚠ No departments in SQLite — nothing to migrate")
            return {}, loc_map

        # Build mapping: keka_id -> new uuid
        dept_map: Dict[str, uuid.UUID] = {}
        dept_data = []
        for r in rows:
            uid = uuid.uuid4()
            dept_map[r["id"]] = uid
            dept_data.append({
                "id": uid,
                "keka_id": r["id"],
                "name": r["name"] or "Unknown",
                "parent_id": r["parent_id"],
                "is_active": not bool(r["is_archived"]),
            })

        # Also build a name -> uuid map for employee migration
        dept_name_map: Dict[str, uuid.UUID] = {}
        for d in dept_data:
            dept_name_map[d["name"].strip().lower()] = d["id"]

        # Generate short codes from names (first 3 letters uppercase, dedupe)
        seen_codes: set = set()
        for d in dept_data:
            base = "".join(c for c in d["name"] if c.isalnum())[:6].upper() or "DEPT"
            code = base
            i = 1
            while code in seen_codes:
                code = f"{base}{i}"
                i += 1
            seen_codes.add(code)
            d["code"] = code

        # Insert (parent_department_id NULL first, update after)
        cur = pg.cursor()
        default_loc = loc_map.get("Indore Office")

        for d in dept_data:
            cur.execute(
                """INSERT INTO departments (id, name, code, location_id, is_active)
                   VALUES (%s, %s, %s, %s, %s)
                   ON CONFLICT ON CONSTRAINT uq_dept_name_location
                   DO UPDATE SET code = EXCLUDED.code
                   RETURNING id""",
                (str(d["id"]), d["name"], d["code"], str(default_loc), d["is_active"]),
            )

        # Second pass: set parent_department_id
        for d in dept_data:
            if d["parent_id"] and d["parent_id"] in dept_map:
                cur.execute(
                    "UPDATE departments SET parent_department_id = %s WHERE id = %s",
                    (str(dept_map[d["parent_id"]]), str(d["id"])),
                )

        pg.commit()
        print(f"  ✓ Migrated {len(dept_data)} departments")
        return dept_map, loc_map

    finally:
        sq.close()
        pg.close()


# Also expose a name-based lookup for employee migration
def get_dept_name_map(pg_conn) -> Dict[str, uuid.UUID]:
    """Fetch {lowercase_dept_name: uuid} from PostgreSQL departments table."""
    cur = pg_conn.cursor()
    cur.execute("SELECT id, name FROM departments")
    return {row[1].strip().lower(): uuid.UUID(str(row[0])) for row in cur.fetchall()}


if __name__ == "__main__":
    dept_map, loc_map = migrate_departments()
    print(f"\nDepartments: {len(dept_map)}, Locations: {len(loc_map)}")
