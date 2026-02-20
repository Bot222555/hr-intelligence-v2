"""003 – Add salary, helpdesk, expenses, and FnF tables.

Creates the four new module tables that support salary management,
helpdesk ticketing, expense claims, and Full & Final settlements.

Uses CREATE TABLE IF NOT EXISTS so the migration is safe to run even
if tables were manually created via the migration scripts.

Revision ID: 003_add_salary_helpdesk_expenses_fnf
Revises: 002_add_missing_columns
Create Date: 2026-02-20 23:00:00.000000+05:30
"""

import re

from alembic import op
import sqlalchemy as sa

# Revision identifiers
revision = "003_add_salary_helpdesk_expenses_fnf"
down_revision = "002_add_missing_columns"
branch_labels = None
depends_on = None

_SAFE_IDENT_RE = re.compile(r'^[a-z_][a-z0-9_]*$')


def _validate_identifier(name: str) -> str:
    if not _SAFE_IDENT_RE.match(name):
        raise ValueError(f"Unsafe SQL identifier: {name!r}")
    return name


def _safe_drop_table(name: str) -> None:
    _validate_identifier(name)
    op.execute(sa.text(f'DROP TABLE IF EXISTS "{name}" CASCADE'))


def upgrade() -> None:
    # ══════════════════════════════════════════════════════════════════
    # 1. salary_components
    # ══════════════════════════════════════════════════════════════════
    op.execute("""
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
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_salary_comp_keka ON salary_components(keka_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_salary_comp_identifier ON salary_components(identifier)"
    )

    # ══════════════════════════════════════════════════════════════════
    # 2. salaries
    # ══════════════════════════════════════════════════════════════════
    op.execute("""
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
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_salaries_employee ON salaries(employee_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_salaries_current ON salaries(is_current) WHERE is_current = TRUE"
    )

    # ══════════════════════════════════════════════════════════════════
    # 3. helpdesk_tickets
    # ══════════════════════════════════════════════════════════════════
    op.execute("""
        CREATE TABLE IF NOT EXISTS helpdesk_tickets (
            id               UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            keka_id          TEXT UNIQUE,
            ticket_number    VARCHAR(50),
            title            VARCHAR(500) NOT NULL,
            category         VARCHAR(200),
            status           VARCHAR(50) NOT NULL DEFAULT 'open',
            priority         VARCHAR(20) NOT NULL DEFAULT 'medium',
            raised_by_id     UUID REFERENCES employees(id),
            raised_by_name   VARCHAR(200),
            assigned_to_id   UUID REFERENCES employees(id),
            assigned_to_name VARCHAR(200),
            requested_on     TIMESTAMPTZ,
            resolved_at      TIMESTAMPTZ,
            created_at       TIMESTAMPTZ DEFAULT NOW(),
            updated_at       TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_hd_tickets_status ON helpdesk_tickets(status)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_hd_tickets_priority ON helpdesk_tickets(priority)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_hd_tickets_raised ON helpdesk_tickets(raised_by_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_hd_tickets_assigned ON helpdesk_tickets(assigned_to_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_hd_tickets_keka ON helpdesk_tickets(keka_id)"
    )

    # ══════════════════════════════════════════════════════════════════
    # 4. helpdesk_responses
    # ══════════════════════════════════════════════════════════════════
    op.execute("""
        CREATE TABLE IF NOT EXISTS helpdesk_responses (
            id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            ticket_id   UUID NOT NULL REFERENCES helpdesk_tickets(id) ON DELETE CASCADE,
            author_id   UUID REFERENCES employees(id),
            author_name VARCHAR(200),
            body        TEXT NOT NULL,
            is_internal BOOLEAN DEFAULT FALSE,
            created_at  TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_hd_responses_ticket ON helpdesk_responses(ticket_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_hd_responses_author ON helpdesk_responses(author_id)"
    )

    # ══════════════════════════════════════════════════════════════════
    # 5. expense_claims
    # ══════════════════════════════════════════════════════════════════
    op.execute("""
        CREATE TABLE IF NOT EXISTS expense_claims (
            id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            keka_id         TEXT UNIQUE,
            employee_id     UUID NOT NULL REFERENCES employees(id),
            employee_name   VARCHAR(200),
            claim_number    VARCHAR(50),
            title           VARCHAR(500) NOT NULL,
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
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_exp_claims_employee ON expense_claims(employee_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_exp_claims_status ON expense_claims(approval_status)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_exp_claims_payment ON expense_claims(payment_status)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_exp_claims_keka ON expense_claims(keka_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_exp_claims_submitted ON expense_claims(submitted_date)"
    )

    # ══════════════════════════════════════════════════════════════════
    # 6. fnf_settlements
    # ══════════════════════════════════════════════════════════════════
    op.execute("""
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
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_fnf_employee ON fnf_settlements(employee_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_fnf_status ON fnf_settlements(settlement_status)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_fnf_keka ON fnf_settlements(keka_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_fnf_lwd ON fnf_settlements(last_working_day)"
    )


def downgrade() -> None:
    _safe_drop_table("fnf_settlements")
    _safe_drop_table("expense_claims")
    _safe_drop_table("helpdesk_responses")
    _safe_drop_table("helpdesk_tickets")
    _safe_drop_table("salaries")
    _safe_drop_table("salary_components")
