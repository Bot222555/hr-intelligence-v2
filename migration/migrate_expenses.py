"""Migrate expense claims from Keka SQLite → PostgreSQL.

Creates expense_claims table in PostgreSQL if it doesn't exist, then upserts
data with proper employee ID mapping.

SQLite source table:
  - expense_claims (id, employee_id, employee_name, claim_number, title,
                    amount, currency, payment_status, approval_status,
                    expenses_json, submitted_date)
"""

import json
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from migration.config import get_pg_conn, get_sqlite_conn


# ── PostgreSQL DDL ────────────────────────────────────────────────────

CREATE_EXPENSE_CLAIMS_SQL = """
CREATE TABLE IF NOT EXISTS expense_claims (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    keka_id         TEXT UNIQUE,
    employee_id     UUID NOT NULL REFERENCES employees(id),
    employee_name   VARCHAR(200),
    claim_number    VARCHAR(50),
    title           VARCHAR(500),
    amount          NUMERIC(12,2) NOT NULL DEFAULT 0,
    currency        VARCHAR(10) DEFAULT 'INR',
    payment_status  VARCHAR(50),
    approval_status VARCHAR(50) NOT NULL DEFAULT 'pending',
    expenses        JSONB DEFAULT '[]',
    submitted_date  DATE,
    approved_by_id  UUID REFERENCES employees(id),
    approved_at     TIMESTAMPTZ,
    paid_at         TIMESTAMPTZ,
    remarks         TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_exp_claims_employee ON expense_claims(employee_id);
CREATE INDEX IF NOT EXISTS idx_exp_claims_status ON expense_claims(approval_status);
CREATE INDEX IF NOT EXISTS idx_exp_claims_payment ON expense_claims(payment_status);
CREATE INDEX IF NOT EXISTS idx_exp_claims_keka ON expense_claims(keka_id);
CREATE INDEX IF NOT EXISTS idx_exp_claims_submitted ON expense_claims(submitted_date);
"""


def _ensure_tables(pg):
    """Create expense_claims table if it doesn't exist."""
    cur = pg.cursor()
    cur.execute(CREATE_EXPENSE_CLAIMS_SQL)
    pg.commit()


def _parse_date(val: Any) -> Optional[str]:
    if not val:
        return None
    s = str(val).strip()
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f",
                "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(s[:19] if "T" in s else s, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _normalize_status(status: str) -> str:
    """Normalize approval status values."""
    s = (status or "pending").strip().lower()
    mapping = {
        "approved": "approved",
        "pending": "pending",
        "rejected": "rejected",
        "cancelled": "cancelled",
        "canceled": "cancelled",
        "paid": "paid",
        "submitted": "submitted",
        "draft": "draft",
    }
    return mapping.get(s, "pending")


def migrate_expenses(emp_map: Dict[str, uuid.UUID]) -> int:
    """Migrate expense claims from SQLite → PostgreSQL.

    Args:
        emp_map: {keka_employee_id: pg_employee_uuid}

    Returns:
        Number of records migrated.
    """
    sq = get_sqlite_conn()
    pg = get_pg_conn()

    try:
        _ensure_tables(pg)
        cur = pg.cursor()

        rows = sq.execute(
            """SELECT id, employee_id, employee_name, claim_number, title,
                      amount, currency, payment_status, approval_status,
                      expenses_json, submitted_date
               FROM expense_claims"""
        ).fetchall()

        count = 0
        skipped = 0

        for r in rows:
            pg_emp_id = emp_map.get(r["employee_id"])
            if not pg_emp_id:
                skipped += 1
                continue

            expenses = r["expenses_json"] or "[]"
            try:
                json.loads(expenses)
            except (json.JSONDecodeError, TypeError):
                expenses = "[]"

            cur.execute(
                """INSERT INTO expense_claims
                   (id, keka_id, employee_id, employee_name, claim_number,
                    title, amount, currency, payment_status, approval_status,
                    expenses, submitted_date)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (keka_id) DO UPDATE
                   SET amount = EXCLUDED.amount,
                       payment_status = EXCLUDED.payment_status,
                       approval_status = EXCLUDED.approval_status,
                       expenses = EXCLUDED.expenses,
                       updated_at = NOW()""",
                (
                    str(uuid.uuid4()), r["id"],
                    str(pg_emp_id), r["employee_name"],
                    r["claim_number"], r["title"],
                    float(r["amount"] or 0),
                    r["currency"] or "INR",
                    r["payment_status"] or "",
                    _normalize_status(r["approval_status"]),
                    expenses,
                    _parse_date(r["submitted_date"]),
                ),
            )
            count += 1

        pg.commit()
        print(f"  ✓ Migrated {count} expense claims ({skipped} skipped — no employee match)")
        return count

    finally:
        sq.close()
        pg.close()


if __name__ == "__main__":
    from migration.migrate_departments import migrate_departments
    from migration.migrate_employees import migrate_employees

    dept_map, loc_map = migrate_departments()
    emp_map = migrate_employees(dept_map, loc_map)
    count = migrate_expenses(emp_map)
    print(f"\nExpense claims migrated: {count}")
