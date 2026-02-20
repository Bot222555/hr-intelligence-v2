"""Common module — shared utilities for HR Intelligence v2.0."""

from backend.common.audit import AuditMixin, AuditTrail, create_audit_entry
from backend.common.constants import (
    DATE_FORMAT,
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    PERMISSIONS,
    TIMEZONE,
    ArrivalStatus,
    AttendanceStatus,
    BloodGroupType,
    EmploymentStatus,
    GenderType,
    LeaveDayType,
    LeaveStatus,
    MaritalStatus,
    NotificationType,
    RegularizationStatus,
    UserRole,
)
from backend.common.exceptions import (
    AppException,
    ConflictError,
    DuplicateException,
    ForbiddenException,
    NotFoundException,
    ValidationException,
    register_exception_handlers,
)
from backend.common.filters import apply_filters, apply_search, apply_sorting
from backend.common.pagination import (
    PaginatedResponse,
    PaginationMeta,
    PaginationParams,
    paginate,
)

__all__ = [
    # Audit
    "AuditMixin",
    "AuditTrail",
    "create_audit_entry",
    # Constants / Enums
    "ArrivalStatus",
    "AttendanceStatus",
    "BloodGroupType",
    "EmploymentStatus",
    "GenderType",
    "LeaveDayType",
    "LeaveStatus",
    "MaritalStatus",
    "NotificationType",
    "RegularizationStatus",
    "UserRole",
    "PERMISSIONS",
    "DATE_FORMAT",
    "TIMEZONE",
    "DEFAULT_PAGE_SIZE",
    "MAX_PAGE_SIZE",
    # Exceptions
    "AppException",
    "ConflictError",
    "DuplicateException",
    "ForbiddenException",
    "NotFoundException",
    "ValidationException",
    "register_exception_handlers",
    # Filters
    "apply_filters",
    "apply_search",
    "apply_sorting",
    # Pagination
    "PaginatedResponse",
    "PaginationMeta",
    "PaginationParams",
    "paginate",
]
