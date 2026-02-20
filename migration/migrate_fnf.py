"""Migrate Full & Final (FnF) settlements from Keka SQLite → PostgreSQL.

Creates fnf_settlements table in PostgreSQL if it doesn't exist, then upserts
data with proper employee ID mapping.

SQLite source table:
  - fnf_settlements (id, employee_id, employee_number, termination_type,
                     last_working_day, no_of_pay_days, raw_json)
"""

import json
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from migration.config import get_pg_conn, get_sqlite_conn


# ── PostgreSQL DDL ────────────────────────────────────────────────────

CREATE_FNF_SETTLEMENTS_SQL = """
CREATE TABLE IF NOT EXISTS fnf_settlements (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    keka_id             TEXT UNIQUE,
    employee_id         UUID NOT NULL REFERENCES employees(id),
    employee_number     VARCHAR(50),
    termination_type    VARCHAR(100),
    last_working_day    DATE,
    no_of_pay_days      NUMERIC(8,2) DEFAULT 0,
    settlement_status   VARCHAR(50) DEFAULT 'pending',
    total_earnings      NUMERIC(12,2) DEFAULT 0,
    total_deductions    NUMERIC(12,2) DEFAULT 0,
    net_settlement      NUMERIC(12,2) DEFAULT 0,
    settlement_details  JSONB DEFAULT '{}',
    processed_at        TIMESTAMPTZ,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_fnf_employee ON fnf_settlements(employee_id);
CREATE INDEX IF NOT EXISTS idx_fnf_status ON fnf_settlements(settlement_status);
CREATE INDEX IF NOT EXISTS idx_fnf_keka ON fnf_settlements(keka_id);
CREATE INDEX IF NOT EXISTS idx_fnf_lwd ON fnf_settlements(last_working_day);
"""


def _ensure_tables(pg):
    """Create fnf_settlements table if it doesn't exist."""
    cur = pg.cursor()
    cur.execute(CREATE_FNF_SETTLEMENTS_SQL)
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


def _extract_financials(raw_json_str: str) -> Dict:
    """Extract financial details from raw Keka FnF JSON."""
    try:
        data = json.loads(raw_json_str) if raw_json_str else {}
    except (json.JSONDecodeError, TypeError):
        data = {}

    return {
        "total_earnings": float(data.get("totalEarnings", data.get("total_earnings", 0)) or 0),
        "total_deductions": float(data.get("totalDeductions", data.get("total_deductions", 0)) or 0),
        "net_settlement": float(data.get("netSettlement", data.get("net_settlement", 0)) or 0),
        "status": data.get("settlementStatus", data.get("status", "pending")),
    }


def migrate_fnf(emp_map: Dict[str, uuid.UUID]) -> int:
    """Migrate FnF settlements from SQLite → PostgreSQL.

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
            """SELECT id, employee_id, employee_number, termination_type,
                      last_working_day, no_of_pay_days, raw_json
               FROM fnf_settlements"""
        ).fetchall()

        count = 0
        skipped = 0

        for r in rows:
            pg_emp_id = emp_map.get(r["employee_id"])
            if not pg_emp_id:
                skipped += 1
                continue

            raw_json = r["raw_json"] or "{}"
            financials = _extract_financials(raw_json)

            # Validate raw_json
            try:
                details = json.loads(raw_json)
            except (json.JSONDecodeError, TypeError):
                details = {}

            status = financials.get("status", "pending")
            if status not in ("pending", "processing", "completed", "on_hold", "cancelled"):
                status = "pending"

            cur.execute(
                """INSERT INTO fnf_settlements
                   (id, keka_id, employee_id, employee_number, termination_type,
                    last_working_day, no_of_pay_days, settlement_status,
                    total_earnings, total_deductions, net_settlement,
                    settlement_details)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (keka_id) DO UPDATE
                   SET termination_type = EXCLUDED.termination_type,
                       no_of_pay_days = EXCLUDED.no_of_pay_days,
                       settlement_status = EXCLUDED.settlement_status,
                       total_earnings = EXCLUDED.total_earnings,
                       total_deductions = EXCLUDED.total_deductions,
                       net_settlement = EXCLUDED.net_settlement,
                       settlement_details = EXCLUDED.settlement_details,
                       updated_at = NOW()""",
                (
                    str(uuid.uuid4()), r["id"],
                    str(pg_emp_id), r["employee_number"],
                    r["termination_type"],
                    _parse_date(r["last_working_day"]),
                    float(r["no_of_pay_days"] or 0),
                    status,
                    financials["total_earnings"],
                    financials["total_deductions"],
                    financials["net_settlement"],
                    json.dumps(details),
                ),
            )
            count += 1

        pg.commit()
        print(f"  ✓ Migrated {count} FnF settlements ({skipped} skipped — no employee match)")
        return count

    finally:
        sq.close()
        pg.close()


if __name__ == "__main__":
    from migration.migrate_departments import migrate_departments
    from migration.migrate_employees import migrate_employees

    dept_map, loc_map = migrate_departments()
    emp_map = migrate_employees(dept_map, loc_map)
    count = migrate_fnf(emp_map)
    print(f"\nFnF settlements migrated: {count}")
