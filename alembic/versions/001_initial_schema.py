"""001 – Initial schema: all tables, indexes, enums, seed data.

Revision ID: 001_initial_schema
Revises:
Create Date: 2026-02-20 15:07:00.000000+05:30
"""

from alembic import op
import sqlalchemy as sa

# Revision identifiers
revision = "001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ENUM_TYPES: list[tuple[str, list[str]]] = [
    ("employment_status", ["active", "notice_period", "relieved", "absconding"]),
    ("gender_type", ["male", "female", "other", "undisclosed"]),
    ("marital_status", ["single", "married", "divorced", "widowed"]),
    ("user_role", ["employee", "manager", "hr_admin", "system_admin"]),
    ("leave_status", ["pending", "approved", "rejected", "cancelled", "revoked"]),
    ("leave_day_type", ["full_day", "first_half", "second_half"]),
    (
        "attendance_status",
        [
            "present",
            "absent",
            "half_day",
            "weekend",
            "holiday",
            "on_leave",
            "work_from_home",
            "on_duty",
        ],
    ),
    ("arrival_status", ["on_time", "late", "very_late", "absent"]),
    ("regularization_status", ["pending", "approved", "rejected"]),
    (
        "notification_type",
        ["info", "action_required", "approval", "reminder", "alert"],
    ),
    (
        "blood_group_type",
        ["A+", "A-", "B+", "B-", "O+", "O-", "AB+", "AB-", "unknown"],
    ),
]


def _create_enum(name: str, values: list[str]) -> None:
    vals = ", ".join(f"'{v}'" for v in values)
    op.execute(f"CREATE TYPE {name} AS ENUM ({vals})")


def _drop_enum(name: str) -> None:
    op.execute(f"DROP TYPE IF EXISTS {name}")


# ---------------------------------------------------------------------------
# UPGRADE
# ---------------------------------------------------------------------------


def upgrade() -> None:
    # ── Extensions ────────────────────────────────────────────────────────
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "pg_trgm"')

    # ── Enum types ────────────────────────────────────────────────────────
    for name, values in ENUM_TYPES:
        _create_enum(name, values)

    # ── 1. locations ──────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE locations (
            id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            name        VARCHAR(100) NOT NULL UNIQUE,
            city        VARCHAR(100),
            state       VARCHAR(100),
            address     TEXT,
            timezone    VARCHAR(50) DEFAULT 'Asia/Kolkata',
            is_active   BOOLEAN DEFAULT TRUE,
            created_at  TIMESTAMPTZ DEFAULT NOW(),
            updated_at  TIMESTAMPTZ DEFAULT NOW()
        )
    """)

    # ── 2. departments ────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE departments (
            id                   UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            name                 VARCHAR(150) NOT NULL,
            code                 VARCHAR(20) UNIQUE,
            location_id          UUID REFERENCES locations(id),
            parent_department_id UUID REFERENCES departments(id),
            head_employee_id     UUID,  -- FK added after employees table
            is_active            BOOLEAN DEFAULT TRUE,
            created_at           TIMESTAMPTZ DEFAULT NOW(),
            updated_at           TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE(name, location_id)
        )
    """)

    # ── 3. employees ──────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE employees (
            id                   UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            employee_code        VARCHAR(20)  NOT NULL UNIQUE,
            first_name           VARCHAR(100) NOT NULL,
            last_name            VARCHAR(100) NOT NULL,
            email                VARCHAR(255) NOT NULL UNIQUE,
            phone                VARCHAR(20),
            gender               gender_type,
            date_of_birth        DATE,
            blood_group          blood_group_type,
            marital_status       marital_status,
            nationality          VARCHAR(50) DEFAULT 'Indian',
            current_address      JSONB,
            permanent_address    JSONB,
            emergency_contact    JSONB,
            department_id        UUID REFERENCES departments(id),
            location_id          UUID REFERENCES locations(id),
            designation          VARCHAR(150),
            reporting_manager_id UUID REFERENCES employees(id),
            employment_status    employment_status DEFAULT 'active',
            date_of_joining      DATE NOT NULL,
            date_of_confirmation DATE,
            date_of_exit         DATE,
            probation_end_date   DATE,
            notice_period_days   INTEGER DEFAULT 90,
            profile_photo_url    TEXT,
            google_id            VARCHAR(255) UNIQUE,
            is_active            BOOLEAN DEFAULT TRUE,
            created_at           TIMESTAMPTZ DEFAULT NOW(),
            updated_at           TIMESTAMPTZ DEFAULT NOW()
        )
    """)

    # Deferred FK: departments.head_employee_id → employees.id
    op.execute("""
        ALTER TABLE departments
            ADD CONSTRAINT fk_dept_head
            FOREIGN KEY (head_employee_id) REFERENCES employees(id)
    """)

    # ── 4. user_sessions ──────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE user_sessions (
            id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            employee_id  UUID NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
            token_hash   VARCHAR(512) NOT NULL,
            ip_address   INET,
            user_agent   TEXT,
            device_info  JSONB,
            expires_at   TIMESTAMPTZ NOT NULL,
            is_revoked   BOOLEAN DEFAULT FALSE,
            created_at   TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX idx_user_sessions_employee ON user_sessions(employee_id)")
    op.execute("CREATE INDEX idx_user_sessions_token    ON user_sessions(token_hash)")
    op.execute("CREATE INDEX idx_user_sessions_expires  ON user_sessions(expires_at)")

    # ── 5. role_assignments ───────────────────────────────────────────────
    op.execute("""
        CREATE TABLE role_assignments (
            id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            employee_id UUID NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
            role        user_role NOT NULL,
            assigned_by UUID REFERENCES employees(id),
            assigned_at TIMESTAMPTZ DEFAULT NOW(),
            revoked_at  TIMESTAMPTZ,
            is_active   BOOLEAN DEFAULT TRUE
        )
    """)
    op.execute("""
        CREATE UNIQUE INDEX uq_role_active
            ON role_assignments(employee_id, role)
            WHERE is_active = TRUE
    """)

    # ── 6. holiday_calendars ──────────────────────────────────────────────
    op.execute("""
        CREATE TABLE holiday_calendars (
            id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            name        VARCHAR(100) NOT NULL,
            year        INTEGER NOT NULL,
            location_id UUID REFERENCES locations(id),
            is_active   BOOLEAN DEFAULT TRUE,
            created_at  TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE(name, year, location_id)
        )
    """)

    # ── 7. holidays ───────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE holidays (
            id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            calendar_id   UUID NOT NULL REFERENCES holiday_calendars(id) ON DELETE CASCADE,
            name          VARCHAR(150) NOT NULL,
            date          DATE NOT NULL,
            is_optional   BOOLEAN DEFAULT FALSE,
            is_restricted BOOLEAN DEFAULT FALSE,
            created_at    TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE(calendar_id, date)
        )
    """)

    # ── 8. shift_policies ─────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE shift_policies (
            id               UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            name             VARCHAR(100) NOT NULL UNIQUE,
            start_time       TIME NOT NULL,
            end_time         TIME NOT NULL,
            grace_minutes    INTEGER DEFAULT 15,
            half_day_minutes INTEGER DEFAULT 240,
            full_day_minutes INTEGER DEFAULT 480,
            is_night_shift   BOOLEAN DEFAULT FALSE,
            is_active        BOOLEAN DEFAULT TRUE,
            created_at       TIMESTAMPTZ DEFAULT NOW(),
            updated_at       TIMESTAMPTZ DEFAULT NOW()
        )
    """)

    # ── 9. weekly_off_policies ────────────────────────────────────────────
    op.execute("""
        CREATE TABLE weekly_off_policies (
            id         UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            name       VARCHAR(100) NOT NULL UNIQUE,
            days       JSONB NOT NULL,
            is_active  BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)

    # ── 10. employee_shift_assignments ────────────────────────────────────
    op.execute("""
        CREATE TABLE employee_shift_assignments (
            id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            employee_id         UUID NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
            shift_policy_id     UUID NOT NULL REFERENCES shift_policies(id),
            weekly_off_policy_id UUID NOT NULL REFERENCES weekly_off_policies(id),
            effective_from      DATE NOT NULL,
            effective_to        DATE,
            created_at          TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE INDEX idx_emp_shift_eff
            ON employee_shift_assignments(employee_id, effective_from)
    """)

    # ── 11. attendance_records ────────────────────────────────────────────
    op.execute("""
        CREATE TABLE attendance_records (
            id                     UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            employee_id            UUID NOT NULL REFERENCES employees(id),
            date                   DATE NOT NULL,
            status                 attendance_status NOT NULL DEFAULT 'absent',
            arrival_status         arrival_status,
            shift_policy_id        UUID REFERENCES shift_policies(id),
            first_clock_in         TIMESTAMPTZ,
            last_clock_out         TIMESTAMPTZ,
            total_work_minutes     INTEGER,
            effective_work_minutes INTEGER,
            overtime_minutes       INTEGER DEFAULT 0,
            is_regularized         BOOLEAN DEFAULT FALSE,
            source                 VARCHAR(50) DEFAULT 'system',
            remarks                TEXT,
            created_at             TIMESTAMPTZ DEFAULT NOW(),
            updated_at             TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE(employee_id, date)
        )
    """)
    op.execute("CREATE INDEX idx_attendance_date   ON attendance_records(date)")
    op.execute("CREATE INDEX idx_attendance_status ON attendance_records(status)")

    # ── 12. clock_entries ─────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE clock_entries (
            id                   UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            employee_id          UUID NOT NULL REFERENCES employees(id),
            attendance_record_id UUID REFERENCES attendance_records(id) ON DELETE CASCADE,
            clock_in             TIMESTAMPTZ NOT NULL,
            clock_out            TIMESTAMPTZ,
            duration_minutes     INTEGER,
            source               VARCHAR(50) DEFAULT 'biometric',
            ip_address           INET,
            created_at           TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE INDEX idx_clock_emp_in
            ON clock_entries(employee_id, clock_in)
    """)

    # ── 13. attendance_regularizations ────────────────────────────────────
    op.execute("""
        CREATE TABLE attendance_regularizations (
            id                   UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            attendance_record_id UUID NOT NULL REFERENCES attendance_records(id),
            employee_id          UUID NOT NULL REFERENCES employees(id),
            requested_status     attendance_status NOT NULL,
            reason               TEXT NOT NULL,
            status               regularization_status DEFAULT 'pending',
            reviewed_by          UUID REFERENCES employees(id),
            reviewed_at          TIMESTAMPTZ,
            reviewer_remarks     TEXT,
            created_at           TIMESTAMPTZ DEFAULT NOW(),
            updated_at           TIMESTAMPTZ DEFAULT NOW()
        )
    """)

    # ── 14. leave_types ───────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE leave_types (
            id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            code                VARCHAR(10)  NOT NULL UNIQUE,
            name                VARCHAR(100) NOT NULL,
            description         TEXT,
            default_balance     NUMERIC(5,1) DEFAULT 0,
            max_carry_forward   NUMERIC(5,1) DEFAULT 0,
            is_paid             BOOLEAN DEFAULT TRUE,
            requires_approval   BOOLEAN DEFAULT TRUE,
            min_days_notice     INTEGER DEFAULT 0,
            max_consecutive_days INTEGER,
            is_active           BOOLEAN DEFAULT TRUE,
            applicable_gender   gender_type,
            created_at          TIMESTAMPTZ DEFAULT NOW(),
            updated_at          TIMESTAMPTZ DEFAULT NOW()
        )
    """)

    # ── 15. leave_balances ────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE leave_balances (
            id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            employee_id     UUID NOT NULL REFERENCES employees(id),
            leave_type_id   UUID NOT NULL REFERENCES leave_types(id),
            year            INTEGER NOT NULL,
            opening_balance NUMERIC(5,1) DEFAULT 0,
            accrued         NUMERIC(5,1) DEFAULT 0,
            used            NUMERIC(5,1) DEFAULT 0,
            carry_forwarded NUMERIC(5,1) DEFAULT 0,
            adjusted        NUMERIC(5,1) DEFAULT 0,
            current_balance NUMERIC(5,1) GENERATED ALWAYS AS
                (opening_balance + accrued + carry_forwarded + adjusted - used) STORED,
            updated_at      TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE(employee_id, leave_type_id, year)
        )
    """)

    # ── 16. leave_requests ────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE leave_requests (
            id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            employee_id     UUID NOT NULL REFERENCES employees(id),
            leave_type_id   UUID NOT NULL REFERENCES leave_types(id),
            start_date      DATE NOT NULL,
            end_date        DATE NOT NULL,
            day_details     JSONB NOT NULL,
            total_days      NUMERIC(5,1) NOT NULL,
            reason          TEXT,
            status          leave_status DEFAULT 'pending',
            reviewed_by     UUID REFERENCES employees(id),
            reviewed_at     TIMESTAMPTZ,
            reviewer_remarks TEXT,
            cancelled_at    TIMESTAMPTZ,
            created_at      TIMESTAMPTZ DEFAULT NOW(),
            updated_at      TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE INDEX idx_leave_req_emp_dates
            ON leave_requests(employee_id, start_date, end_date)
    """)
    op.execute("CREATE INDEX idx_leave_req_status ON leave_requests(status)")

    # ── 17. comp_off_grants ───────────────────────────────────────────────
    op.execute("""
        CREATE TABLE comp_off_grants (
            id               UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            employee_id      UUID NOT NULL REFERENCES employees(id),
            work_date        DATE NOT NULL,
            reason           TEXT NOT NULL,
            granted_by       UUID REFERENCES employees(id),
            expires_at       DATE,
            is_used          BOOLEAN DEFAULT FALSE,
            leave_request_id UUID REFERENCES leave_requests(id),
            created_at       TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE(employee_id, work_date)
        )
    """)

    # ── 18. notifications ─────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE notifications (
            id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            recipient_id UUID NOT NULL REFERENCES employees(id),
            type         notification_type DEFAULT 'info',
            title        VARCHAR(255) NOT NULL,
            message      TEXT,
            link         VARCHAR(500),
            is_read      BOOLEAN DEFAULT FALSE,
            read_at      TIMESTAMPTZ,
            created_at   TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE INDEX idx_notif_recipient_read
            ON notifications(recipient_id, is_read)
    """)
    op.execute("CREATE INDEX idx_notif_created ON notifications(created_at)")

    # ── 19. audit_trail ───────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE audit_trail (
            id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            actor_id    UUID REFERENCES employees(id),
            action      VARCHAR(100) NOT NULL,
            entity_type VARCHAR(100) NOT NULL,
            entity_id   UUID NOT NULL,
            old_values  JSONB,
            new_values  JSONB,
            ip_address  INET,
            user_agent  TEXT,
            created_at  TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE INDEX idx_audit_entity
            ON audit_trail(entity_type, entity_id)
    """)
    op.execute("CREATE INDEX idx_audit_actor   ON audit_trail(actor_id)")
    op.execute("CREATE INDEX idx_audit_created ON audit_trail(created_at)")

    # ── 20. app_settings ──────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE app_settings (
            key         VARCHAR(100) PRIMARY KEY,
            value       JSONB NOT NULL,
            description TEXT,
            updated_at  TIMESTAMPTZ DEFAULT NOW(),
            updated_by  UUID REFERENCES employees(id)
        )
    """)

    # ══════════════════════════════════════════════════════════════════════
    # SEED DATA
    # ══════════════════════════════════════════════════════════════════════

    # Locations
    op.execute("""
        INSERT INTO locations (name, city, state, address) VALUES
        ('Creativefuel Indore', 'Indore', 'Madhya Pradesh', 'Creativefuel HQ, Indore'),
        ('Creativefuel Mumbai', 'Mumbai', 'Maharashtra', 'Creativefuel Office, Mumbai')
    """)

    # Weekly-off policies
    op.execute("""
        INSERT INTO weekly_off_policies (name, days) VALUES
        ('Standard (Sat-Sun)', '["saturday", "sunday"]'),
        ('Saturday Alternate', '["sunday"]')
    """)

    # Leave types
    op.execute("""
        INSERT INTO leave_types
            (code, name, description, default_balance, max_carry_forward,
             is_paid, requires_approval, min_days_notice, max_consecutive_days,
             applicable_gender)
        VALUES
            ('CL', 'Casual Leave',    'For personal/urgent work',                     12, 0, TRUE, TRUE,  0,    3,   NULL),
            ('PL', 'Privilege Leave',  'Earned/privilege leave',                       15, 5, TRUE, TRUE,  7,   15,   NULL),
            ('SL', 'Sick Leave',       'Medical leave with certificate for 3+ days',   12, 0, TRUE, TRUE,  0,    7,   NULL),
            ('CO', 'Comp Off',         'Compensatory off for extra work days',          0, 0, TRUE, TRUE,  1,    1,   NULL),
            ('ML', 'Maternity Leave',  'Maternity leave as per policy',               182, 0, TRUE, TRUE, 30,  182,   'female'),
            ('UL', 'Unpaid Leave',     'Leave without pay',                             0, 0, FALSE,TRUE,  0, NULL,   NULL)
    """)

    # Shift policy
    op.execute("""
        INSERT INTO shift_policies
            (name, start_time, end_time, grace_minutes, half_day_minutes, full_day_minutes)
        VALUES
            ('General Shift', '09:30', '18:30', 15, 240, 480)
    """)

    # App settings
    op.execute("""
        INSERT INTO app_settings (key, value, description) VALUES
        ('fiscal_year_start',                     '"april"',  'Month when fiscal year begins'),
        ('leave_cycle_start',                     '"january"','Month when leave cycle resets'),
        ('auto_mark_absent_time',                 '"11:00"',  'Time after which absent is auto-marked'),
        ('attendance_regularization_window_days',  '7',       'Days within which regularization can be requested'),
        ('max_clock_entries_per_day',              '10',      'Maximum clock in/out pairs per day')
    """)


# ---------------------------------------------------------------------------
# DOWNGRADE
# ---------------------------------------------------------------------------


def downgrade() -> None:
    # Drop tables in reverse dependency order
    tables = [
        "app_settings",
        "audit_trail",
        "notifications",
        "comp_off_grants",
        "leave_requests",
        "leave_balances",
        "leave_types",
        "attendance_regularizations",
        "clock_entries",
        "attendance_records",
        "employee_shift_assignments",
        "weekly_off_policies",
        "shift_policies",
        "holidays",
        "holiday_calendars",
        "role_assignments",
        "user_sessions",
    ]
    for t in tables:
        op.execute(f"DROP TABLE IF EXISTS {t} CASCADE")

    # Drop deferred FK before dropping employees / departments
    op.execute(
        "ALTER TABLE departments DROP CONSTRAINT IF EXISTS fk_dept_head"
    )
    op.execute("DROP TABLE IF EXISTS employees CASCADE")
    op.execute("DROP TABLE IF EXISTS departments CASCADE")
    op.execute("DROP TABLE IF EXISTS locations CASCADE")

    # Drop enum types
    for name, _ in reversed(ENUM_TYPES):
        _drop_enum(name)

    # Drop extensions
    op.execute('DROP EXTENSION IF EXISTS "pg_trgm"')
    op.execute('DROP EXTENSION IF EXISTS "uuid-ossp"')
