"""Migrate salary records and salary components from Keka SQLite → PostgreSQL.

Creates salary tables in PostgreSQL if they don't exist, then upserts data
with proper employee ID mapping.

SQLite source tables:
  - salaries (employee_id, employee_number, ctc, gross, net_pay, earnings_json, ...)
  - salary_components (id, identifier, title, accounting_code)
"""

import json
import uuid
from datetime import datetime
from typing import Dict, Tuple

from migration.config import get_pg_conn, get_sqlite_conn


# ── PostgreSQL DDL ────────────────────────────────────────────────────

CREATE_SALARY_COMPONENTS_SQL = """
CREATE TABLE IF NOT EXISTS salary_components (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    keka_id         TEXT UNIQUE,
    identifier      VARCHAR(100),
    title           VARCHAR(200) NOT NULL,
    accounting_code VARCHAR(100),
    component_type  VARCHAR(50) DEFAULT 'earning',
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_salary_comp_keka ON salary_components(keka_id);
CREATE INDEX IF NOT EXISTS idx_salary_comp_identifier ON salary_components(identifier);
"""

CREATE_SALARIES_SQL = """
CREATE TABLE IF NOT EXISTS salaries (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    employee_id     UUID NOT NULL REFERENCES employees(id),
    ctc             NUMERIC(12,2) DEFAULT 0,
    gross_pay       NUMERIC(12,2) DEFAULT 0,
    net_pay         NUMERIC(12,2) DEFAULT 0,
    earnings        JSONB DEFAULT '[]',
    deductions      JSONB DEFAULT '[]',
    contributions   JSONB DEFAULT '[]',
    variables       JSONB DEFAULT '[]',
    effective_date  DATE,
    pay_period      VARCHAR(20),
    is_current      BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(employee_id, is_current)
);
CREATE INDEX IF NOT EXISTS idx_salaries_employee ON salaries(employee_id);
CREATE INDEX IF NOT EXISTS idx_salaries_current ON salaries(is_current) WHERE is_current = TRUE;
"""


def _ensure_tables(pg):
    """Create salary tables if they don't exist."""
    cur = pg.cursor()
    cur.execute(CREATE_SALARY_COMPONENTS_SQL)
    cur.execute(CREATE_SALARIES_SQL)
    pg.commit()


def migrate_salary_components() -> int:
    """Migrate salary components from SQLite → PostgreSQL."""
    sq = get_sqlite_conn()
    pg = get_pg_conn()

    try:
        _ensure_tables(pg)
        cur = pg.cursor()

        rows = sq.execute("SELECT id, identifier, title, accounting_code FROM salary_components").fetchall()
        count = 0

        for r in rows:
            cur.execute(
                """INSERT INTO salary_components
                   (id, keka_id, identifier, title, accounting_code)
                   VALUES (%s, %s, %s, %s, %s)
                   ON CONFLICT (keka_id) DO UPDATE
                   SET identifier = EXCLUDED.identifier,
                       title = EXCLUDED.title,
                       accounting_code = EXCLUDED.accounting_code,
                       updated_at = NOW()""",
                (str(uuid.uuid4()), r["id"], r["identifier"],
                 r["title"], r["accounting_code"]),
            )
            count += 1

        pg.commit()
        print(f"  ✓ Migrated {count} salary components")
        return count

    finally:
        sq.close()
        pg.close()


def migrate_salaries(emp_map: Dict[str, uuid.UUID]) -> int:
    """Migrate salary records from SQLite → PostgreSQL.

    Args:
        emp_map: {keka_employee_id: pg_employee_uuid}
    """
    sq = get_sqlite_conn()
    pg = get_pg_conn()

    try:
        _ensure_tables(pg)
        cur = pg.cursor()

        rows = sq.execute(
            """SELECT employee_id, employee_number, ctc, gross, net_pay,
                      earnings_json, deductions_json, contributions_json,
                      variables_json
               FROM salaries"""
        ).fetchall()

        count = 0
        skipped = 0

        for r in rows:
            pg_emp_id = emp_map.get(r["employee_id"])
            if not pg_emp_id:
                skipped += 1
                continue

            earnings = r["earnings_json"] or "[]"
            deductions = r["deductions_json"] or "[]"
            contributions = r["contributions_json"] or "[]"
            variables = r["variables_json"] or "[]"

            # Validate JSON
            try:
                json.loads(earnings)
                json.loads(deductions)
                json.loads(contributions)
                json.loads(variables)
            except (json.JSONDecodeError, TypeError):
                earnings = "[]"
                deductions = "[]"
                contributions = "[]"
                variables = "[]"

            cur.execute(
                """INSERT INTO salaries
                   (id, employee_id, ctc, gross_pay, net_pay,
                    earnings, deductions, contributions, variables,
                    is_current)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE)
                   ON CONFLICT (employee_id, is_current) DO UPDATE
                   SET ctc = EXCLUDED.ctc,
                       gross_pay = EXCLUDED.gross_pay,
                       net_pay = EXCLUDED.net_pay,
                       earnings = EXCLUDED.earnings,
                       deductions = EXCLUDED.deductions,
                       contributions = EXCLUDED.contributions,
                       variables = EXCLUDED.variables,
                       updated_at = NOW()""",
                (
                    str(uuid.uuid4()), str(pg_emp_id),
                    float(r["ctc"] or 0), float(r["gross"] or 0),
                    float(r["net_pay"] or 0),
                    earnings, deductions, contributions, variables,
                ),
            )
            count += 1

        pg.commit()
        print(f"  ✓ Migrated {count} salary records ({skipped} skipped — no employee match)")
        return count

    finally:
        sq.close()
        pg.close()


if __name__ == "__main__":
    from migration.migrate_departments import migrate_departments
    from migration.migrate_employees import migrate_employees

    dept_map, loc_map = migrate_departments()
    emp_map = migrate_employees(dept_map, loc_map)

    comp_count = migrate_salary_components()
    sal_count = migrate_salaries(emp_map)
    print(f"\nSalary components: {comp_count}, Salary records: {sal_count}")
