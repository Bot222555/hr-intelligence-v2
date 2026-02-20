"""Dashboard models — no new tables needed.

The dashboard module is a read-only aggregation layer that queries across
existing tables: Employee, AttendanceRecord, LeaveRequest, Department,
Notification, and AuditTrail.

This file re-exports the models used by the dashboard service for clarity
and to keep the import graph consistent with other modules.
"""

from backend.attendance.models import AttendanceRecord, Holiday, HolidayCalendar
from backend.common.audit import AuditTrail
from backend.core_hr.models import Department, Employee, Location
from backend.leave.models import LeaveRequest
from backend.notifications.models import Notification

__all__ = [
    "AttendanceRecord",
    "AuditTrail",
    "Department",
    "Employee",
    "Holiday",
    "HolidayCalendar",
    "LeaveRequest",
    "Location",
    "Notification",
]
