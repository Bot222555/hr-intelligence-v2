"""Enums and constants for HR Intelligence — matching PostgreSQL ENUM types."""

from __future__ import annotations

import enum


# ── Employee / Core HR ──────────────────────────────────────────────

class EmploymentStatus(str, enum.Enum):
    active = "active"
    notice_period = "notice_period"
    relieved = "relieved"
    absconding = "absconding"


class GenderType(str, enum.Enum):
    male = "male"
    female = "female"
    other = "other"
    undisclosed = "undisclosed"


class MaritalStatus(str, enum.Enum):
    single = "single"
    married = "married"
    divorced = "divorced"
    widowed = "widowed"


class BloodGroupType(str, enum.Enum):
    a_pos = "A+"
    a_neg = "A-"
    b_pos = "B+"
    b_neg = "B-"
    o_pos = "O+"
    o_neg = "O-"
    ab_pos = "AB+"
    ab_neg = "AB-"
    unknown = "unknown"


# ── Auth / Roles ────────────────────────────────────────────────────

class UserRole(str, enum.Enum):
    employee = "employee"
    manager = "manager"
    hr_admin = "hr_admin"
    system_admin = "system_admin"


# ── Leave ───────────────────────────────────────────────────────────

class LeaveStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    cancelled = "cancelled"
    revoked = "revoked"


class LeaveDayType(str, enum.Enum):
    full_day = "full_day"
    first_half = "first_half"
    second_half = "second_half"


# ── Attendance ──────────────────────────────────────────────────────

class AttendanceStatus(str, enum.Enum):
    present = "present"
    absent = "absent"
    half_day = "half_day"
    weekend = "weekend"
    holiday = "holiday"
    on_leave = "on_leave"
    work_from_home = "work_from_home"
    on_duty = "on_duty"


class ArrivalStatus(str, enum.Enum):
    on_time = "on_time"
    late = "late"
    very_late = "very_late"
    absent = "absent"


class RegularizationStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


# ── Notifications ───────────────────────────────────────────────────

class NotificationType(str, enum.Enum):
    info = "info"
    action_required = "action_required"
    approval = "approval"
    reminder = "reminder"
    alert = "alert"


# ── Role-based permissions ──────────────────────────────────────────

PERMISSIONS: dict[UserRole, list[str]] = {
    UserRole.employee: [
        "profile:read_own",
        "leave:request",
        "leave:read_own",
        "attendance:read_own",
        "notification:read_own",
    ],
    UserRole.manager: [
        "profile:read_own",
        "profile:read_team",
        "leave:request",
        "leave:read_own",
        "leave:read_team",
        "leave:approve",
        "leave:reject",
        "attendance:read_own",
        "attendance:read_team",
        "attendance:regularize_approve",
        "notification:read_own",
        "dashboard:team",
    ],
    UserRole.hr_admin: [
        "profile:read_all",
        "profile:create",
        "profile:update",
        "leave:read_all",
        "leave:approve",
        "leave:reject",
        "leave:revoke",
        "leave:configure",
        "attendance:read_all",
        "attendance:regularize_approve",
        "attendance:configure",
        "notification:read_all",
        "notification:send",
        "dashboard:hr",
        "audit:read",
    ],
    UserRole.system_admin: [
        "profile:read_all",
        "profile:create",
        "profile:update",
        "profile:delete",
        "leave:read_all",
        "leave:approve",
        "leave:reject",
        "leave:revoke",
        "leave:configure",
        "attendance:read_all",
        "attendance:regularize_approve",
        "attendance:configure",
        "notification:read_all",
        "notification:send",
        "dashboard:hr",
        "dashboard:system",
        "audit:read",
        "system:configure",
        "system:manage_users",
    ],
}

# ── Misc constants ──────────────────────────────────────────────────

DATE_FORMAT = "%d-%b-%Y"          # Indian format: 19-Feb-2026
TIMEZONE = "Asia/Kolkata"
MAX_PAGE_SIZE = 100
DEFAULT_PAGE_SIZE = 50
