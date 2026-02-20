"""002 – Add columns present in ORM models but missing from 001_initial_schema.

Fixes schema drift that caused production crashes: locations.pincode,
departments.keka_id, employees.display_name, etc. were defined in
SQLAlchemy models but never created in the database.

Uses ADD COLUMN IF NOT EXISTS (PostgreSQL 9.6+) so the migration is
safe to run even if some columns were manually added in production.

Revision ID: 002_add_missing_columns
Revises: 001_initial_schema
Create Date: 2026-02-20 22:50:00.000000+05:30
"""

from alembic import op
import sqlalchemy as sa

# Revision identifiers
revision = "002_add_missing_columns"
down_revision = "001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ══════════════════════════════════════════════════════════════════
    # locations — missing: pincode, country
    # ══════════════════════════════════════════════════════════════════
    op.execute("""
        ALTER TABLE locations
            ADD COLUMN IF NOT EXISTS pincode VARCHAR(10),
            ADD COLUMN IF NOT EXISTS country VARCHAR(100) DEFAULT 'India'
    """)

    # ══════════════════════════════════════════════════════════════════
    # departments — missing: keka_id, description
    # ══════════════════════════════════════════════════════════════════
    op.execute("""
        ALTER TABLE departments
            ADD COLUMN IF NOT EXISTS keka_id VARCHAR(100),
            ADD COLUMN IF NOT EXISTS description TEXT
    """)
    # Add UNIQUE constraint on keka_id (only if it doesn't already exist)
    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'uq_departments_keka_id'
            ) THEN
                ALTER TABLE departments
                    ADD CONSTRAINT uq_departments_keka_id UNIQUE (keka_id);
            END IF;
        END $$
    """)

    # ══════════════════════════════════════════════════════════════════
    # employees — missing: keka_id, middle_name, display_name,
    #   personal_email, job_title, l2_manager_id, resignation_date,
    #   last_working_date, exit_reason, professional_summary,
    #   created_by, updated_by
    # ══════════════════════════════════════════════════════════════════
    op.execute("""
        ALTER TABLE employees
            ADD COLUMN IF NOT EXISTS keka_id              VARCHAR(100),
            ADD COLUMN IF NOT EXISTS middle_name           VARCHAR(100),
            ADD COLUMN IF NOT EXISTS display_name          VARCHAR(255),
            ADD COLUMN IF NOT EXISTS personal_email        VARCHAR(255),
            ADD COLUMN IF NOT EXISTS job_title             VARCHAR(200),
            ADD COLUMN IF NOT EXISTS l2_manager_id         UUID,
            ADD COLUMN IF NOT EXISTS resignation_date      DATE,
            ADD COLUMN IF NOT EXISTS last_working_date     DATE,
            ADD COLUMN IF NOT EXISTS exit_reason           TEXT,
            ADD COLUMN IF NOT EXISTS professional_summary  TEXT,
            ADD COLUMN IF NOT EXISTS created_by            UUID,
            ADD COLUMN IF NOT EXISTS updated_by            UUID
    """)

    # UNIQUE constraint on employees.keka_id
    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'uq_employees_keka_id'
            ) THEN
                ALTER TABLE employees
                    ADD CONSTRAINT uq_employees_keka_id UNIQUE (keka_id);
            END IF;
        END $$
    """)

    # Foreign keys for self-referential columns
    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'fk_employee_l2_manager'
            ) THEN
                ALTER TABLE employees
                    ADD CONSTRAINT fk_employee_l2_manager
                    FOREIGN KEY (l2_manager_id) REFERENCES employees(id);
            END IF;
        END $$
    """)
    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'fk_employee_created_by'
            ) THEN
                ALTER TABLE employees
                    ADD CONSTRAINT fk_employee_created_by
                    FOREIGN KEY (created_by) REFERENCES employees(id);
            END IF;
        END $$
    """)
    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'fk_employee_updated_by'
            ) THEN
                ALTER TABLE employees
                    ADD CONSTRAINT fk_employee_updated_by
                    FOREIGN KEY (updated_by) REFERENCES employees(id);
            END IF;
        END $$
    """)

    # ══════════════════════════════════════════════════════════════════
    # notifications — rename link → action_url, add entity_type,
    #   entity_id
    # ══════════════════════════════════════════════════════════════════

    # Rename link → action_url (safe: only runs if 'link' exists)
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'notifications' AND column_name = 'link'
            ) AND NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'notifications' AND column_name = 'action_url'
            ) THEN
                ALTER TABLE notifications RENAME COLUMN link TO action_url;
            END IF;
        END $$
    """)

    op.execute("""
        ALTER TABLE notifications
            ADD COLUMN IF NOT EXISTS entity_type VARCHAR(50),
            ADD COLUMN IF NOT EXISTS entity_id   UUID
    """)


def downgrade() -> None:
    # ── notifications ─────────────────────────────────────────────────
    op.execute("ALTER TABLE notifications DROP COLUMN IF EXISTS entity_id")
    op.execute("ALTER TABLE notifications DROP COLUMN IF EXISTS entity_type")
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'notifications' AND column_name = 'action_url'
            ) AND NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'notifications' AND column_name = 'link'
            ) THEN
                ALTER TABLE notifications RENAME COLUMN action_url TO link;
            END IF;
        END $$
    """)

    # ── employees ─────────────────────────────────────────────────────
    op.execute("ALTER TABLE employees DROP CONSTRAINT IF EXISTS fk_employee_updated_by")
    op.execute("ALTER TABLE employees DROP CONSTRAINT IF EXISTS fk_employee_created_by")
    op.execute("ALTER TABLE employees DROP CONSTRAINT IF EXISTS fk_employee_l2_manager")
    op.execute("ALTER TABLE employees DROP CONSTRAINT IF EXISTS uq_employees_keka_id")
    op.execute("ALTER TABLE employees DROP COLUMN IF EXISTS updated_by")
    op.execute("ALTER TABLE employees DROP COLUMN IF EXISTS created_by")
    op.execute("ALTER TABLE employees DROP COLUMN IF EXISTS professional_summary")
    op.execute("ALTER TABLE employees DROP COLUMN IF EXISTS exit_reason")
    op.execute("ALTER TABLE employees DROP COLUMN IF EXISTS last_working_date")
    op.execute("ALTER TABLE employees DROP COLUMN IF EXISTS resignation_date")
    op.execute("ALTER TABLE employees DROP COLUMN IF EXISTS l2_manager_id")
    op.execute("ALTER TABLE employees DROP COLUMN IF EXISTS job_title")
    op.execute("ALTER TABLE employees DROP COLUMN IF EXISTS personal_email")
    op.execute("ALTER TABLE employees DROP COLUMN IF EXISTS display_name")
    op.execute("ALTER TABLE employees DROP COLUMN IF EXISTS middle_name")
    op.execute("ALTER TABLE employees DROP COLUMN IF EXISTS keka_id")

    # ── departments ───────────────────────────────────────────────────
    op.execute("ALTER TABLE departments DROP CONSTRAINT IF EXISTS uq_departments_keka_id")
    op.execute("ALTER TABLE departments DROP COLUMN IF EXISTS description")
    op.execute("ALTER TABLE departments DROP COLUMN IF EXISTS keka_id")

    # ── locations ─────────────────────────────────────────────────────
    op.execute("ALTER TABLE locations DROP COLUMN IF EXISTS country")
    op.execute("ALTER TABLE locations DROP COLUMN IF EXISTS pincode")
