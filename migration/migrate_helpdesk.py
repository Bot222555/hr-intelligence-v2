"""Migrate helpdesk tickets and responses from Keka SQLite → PostgreSQL.

Creates helpdesk tables in PostgreSQL if they don't exist, then upserts data
with proper employee ID mapping.

SQLite source tables:
  - helpdesk_tickets (id, ticket_number, title, category, status, priority, ...)
  - helpdesk_responses (id, ticket_id, author_id, body, is_internal, created_at)
"""

import json
import uuid
from datetime import datetime
from typing import Dict, Optional, Tuple

from migration.config import get_pg_conn, get_sqlite_conn


# ── PostgreSQL DDL ────────────────────────────────────────────────────

CREATE_HELPDESK_TICKETS_SQL = """
CREATE TABLE IF NOT EXISTS helpdesk_tickets (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    keka_id         TEXT UNIQUE,
    ticket_number   VARCHAR(50),
    title           VARCHAR(500) NOT NULL,
    category        VARCHAR(200),
    status          VARCHAR(50) NOT NULL DEFAULT 'open',
    priority        VARCHAR(20) NOT NULL DEFAULT 'medium',
    raised_by_id    UUID REFERENCES employees(id),
    raised_by_name  VARCHAR(200),
    assigned_to_id  UUID REFERENCES employees(id),
    assigned_to_name VARCHAR(200),
    requested_on    TIMESTAMPTZ,
    resolved_at     TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_hd_tickets_status ON helpdesk_tickets(status);
CREATE INDEX IF NOT EXISTS idx_hd_tickets_priority ON helpdesk_tickets(priority);
CREATE INDEX IF NOT EXISTS idx_hd_tickets_raised ON helpdesk_tickets(raised_by_id);
CREATE INDEX IF NOT EXISTS idx_hd_tickets_assigned ON helpdesk_tickets(assigned_to_id);
CREATE INDEX IF NOT EXISTS idx_hd_tickets_keka ON helpdesk_tickets(keka_id);
"""

CREATE_HELPDESK_RESPONSES_SQL = """
CREATE TABLE IF NOT EXISTS helpdesk_responses (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    ticket_id       UUID NOT NULL REFERENCES helpdesk_tickets(id) ON DELETE CASCADE,
    author_id       UUID REFERENCES employees(id),
    author_name     VARCHAR(200),
    body            TEXT NOT NULL,
    is_internal     BOOLEAN DEFAULT FALSE,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_hd_responses_ticket ON helpdesk_responses(ticket_id);
CREATE INDEX IF NOT EXISTS idx_hd_responses_author ON helpdesk_responses(author_id);
"""


def _ensure_tables(pg):
    """Create helpdesk tables if they don't exist."""
    cur = pg.cursor()
    cur.execute(CREATE_HELPDESK_TICKETS_SQL)
    cur.execute(CREATE_HELPDESK_RESPONSES_SQL)
    pg.commit()


def _parse_timestamp(val) -> Optional[str]:
    """Parse various date formats to ISO string."""
    if not val:
        return None
    s = str(val).strip()
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f",
                "%Y-%m-%dT%H:%M:%S%z"):
        try:
            return datetime.strptime(s[:26], fmt).isoformat()
        except ValueError:
            continue
    return s[:26] if len(s) >= 10 else None


# Build a name-to-UUID lookup from employees for "raised_by" / "assigned_to"
def _build_name_to_id(sq) -> Dict[str, str]:
    """Build {display_name.lower(): keka_id} from SQLite employees."""
    rows = sq.execute("SELECT id, display_name FROM employees WHERE display_name IS NOT NULL").fetchall()
    return {r["display_name"].strip().lower(): r["id"] for r in rows if r["display_name"]}


def migrate_helpdesk(emp_map: Dict[str, uuid.UUID]) -> Tuple[int, int]:
    """Migrate helpdesk tickets and responses.

    Args:
        emp_map: {keka_employee_id: pg_employee_uuid}

    Returns:
        (ticket_count, response_count)
    """
    sq = get_sqlite_conn()
    pg = get_pg_conn()

    try:
        _ensure_tables(pg)
        cur = pg.cursor()

        # Build name lookup for "raised_by" text field
        name_map = _build_name_to_id(sq)

        # ── Migrate tickets ──────────────────────────────────────────
        ticket_rows = sq.execute(
            """SELECT id, ticket_number, title, category, status, priority,
                      raised_by, assigned_to, requested_on
               FROM helpdesk_tickets"""
        ).fetchall()

        ticket_count = 0
        keka_to_pg_ticket: Dict[str, uuid.UUID] = {}

        for r in ticket_rows:
            keka_id = r["id"]
            pg_ticket_id = uuid.uuid4()

            # Try to resolve raised_by name → employee UUID
            raised_name = (r["raised_by"] or "").strip()
            raised_by_id = None
            if raised_name:
                keka_emp_id = name_map.get(raised_name.lower())
                if keka_emp_id:
                    raised_by_id = emp_map.get(keka_emp_id)

            # Try to resolve assigned_to name → employee UUID
            assigned_name = (r["assigned_to"] or "").strip()
            assigned_to_id = None
            if assigned_name:
                keka_emp_id = name_map.get(assigned_name.lower())
                if keka_emp_id:
                    assigned_to_id = emp_map.get(keka_emp_id)

            status = (r["status"] or "open").lower()
            if status not in ("open", "in_progress", "resolved", "closed", "waiting"):
                status = "open"

            priority = (r["priority"] or "medium").lower()
            if priority not in ("low", "medium", "high", "critical", "urgent"):
                priority = "medium"

            cur.execute(
                """INSERT INTO helpdesk_tickets
                   (id, keka_id, ticket_number, title, category, status, priority,
                    raised_by_id, raised_by_name, assigned_to_id, assigned_to_name,
                    requested_on)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (keka_id) DO UPDATE
                   SET title = EXCLUDED.title,
                       category = EXCLUDED.category,
                       status = EXCLUDED.status,
                       priority = EXCLUDED.priority,
                       assigned_to_id = EXCLUDED.assigned_to_id,
                       assigned_to_name = EXCLUDED.assigned_to_name,
                       updated_at = NOW()""",
                (
                    str(pg_ticket_id), keka_id,
                    r["ticket_number"], r["title"] or "No title",
                    r["category"], status, priority,
                    str(raised_by_id) if raised_by_id else None, raised_name,
                    str(assigned_to_id) if assigned_to_id else None, assigned_name,
                    _parse_timestamp(r["requested_on"]),
                ),
            )
            keka_to_pg_ticket[keka_id] = pg_ticket_id
            ticket_count += 1

        pg.commit()
        print(f"  ✓ Migrated {ticket_count} helpdesk tickets")

        # ── Migrate responses ────────────────────────────────────────
        # Re-fetch PG ticket IDs (in case of upsert conflicts)
        cur.execute("SELECT id, keka_id FROM helpdesk_tickets WHERE keka_id IS NOT NULL")
        for row in cur.fetchall():
            keka_to_pg_ticket[row[1]] = uuid.UUID(str(row[0]))

        try:
            resp_rows = sq.execute(
                """SELECT id, ticket_id, author_id, body, is_internal, created_at
                   FROM helpdesk_responses"""
            ).fetchall()
        except Exception:
            resp_rows = []
            print("  ⚠ No helpdesk_responses table in SQLite")

        resp_count = 0
        for r in resp_rows:
            pg_ticket_id = keka_to_pg_ticket.get(r["ticket_id"])
            if not pg_ticket_id:
                continue

            author_pg_id = emp_map.get(r["author_id"]) if r["author_id"] else None

            cur.execute(
                """INSERT INTO helpdesk_responses
                   (id, ticket_id, author_id, body, is_internal, created_at)
                   VALUES (%s, %s, %s, %s, %s, %s)
                   ON CONFLICT DO NOTHING""",
                (
                    str(uuid.uuid4()), str(pg_ticket_id),
                    str(author_pg_id) if author_pg_id else None,
                    r["body"],
                    bool(r["is_internal"]),
                    _parse_timestamp(r["created_at"]),
                ),
            )
            resp_count += 1

        pg.commit()
        print(f"  ✓ Migrated {resp_count} helpdesk responses")
        return ticket_count, resp_count

    finally:
        sq.close()
        pg.close()


if __name__ == "__main__":
    from migration.migrate_departments import migrate_departments
    from migration.migrate_employees import migrate_employees

    dept_map, loc_map = migrate_departments()
    emp_map = migrate_employees(dept_map, loc_map)
    tickets, responses = migrate_helpdesk(emp_map)
    print(f"\nHelpdesk tickets: {tickets}, Responses: {responses}")
