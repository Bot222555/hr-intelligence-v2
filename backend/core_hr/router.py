"""Core HR router — Employee, Department, Location API endpoints.

Provides CRUD operations for the core HR module with role-based access control.

Routes:
    /employees              — List, create employees
    /employees/org-chart    — Organisation hierarchy
    /employees/{id}         — Get, update employee
    /employees/{id}/profile — Full employee profile (with attendance + leave data)
    /employees/{id}/direct-reports — Manager's direct reports
    /departments            — List departments
    /departments/{id}       — Department detail
    /locations              — List locations
    /locations/{id}         — Location detail
"""


import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.attendance.models import AttendanceRecord
from backend.auth.dependencies import get_current_user, require_role
from backend.common.constants import ArrivalStatus, UserRole
from backend.common.exceptions import ForbiddenException
from backend.common.pagination import PaginationParams
from backend.core_hr.models import Employee
from backend.core_hr.schemas import (
    DepartmentResponse,
    EmployeeCreate,
    EmployeeDetail,
    EmployeeListItem,
    EmployeeSummary,
    EmployeeUpdate,
    LocationResponse,
    OrgChartNode,
)
from backend.core_hr.service import DepartmentService, EmployeeService, LocationService
from backend.database import get_db
from backend.leave.models import LeaveBalance, LeaveRequest, LeaveType


# ═════════════════════════════════════════════════════════════════════
# Routers
# ═════════════════════════════════════════════════════════════════════

employees_router = APIRouter(prefix="", tags=["employees"])
departments_router = APIRouter(prefix="", tags=["departments"])
locations_router = APIRouter(prefix="", tags=["locations"])


# ── Helper: check role level ────────────────────────────────────────

def _is_at_least(request: Request, role: UserRole) -> bool:
    """Return True if the current user's role is >= the given role in hierarchy."""
    user_role: UserRole = request.state.user_role
    hierarchy = {
        UserRole.system_admin: 4,
        UserRole.hr_admin: 3,
        UserRole.manager: 2,
        UserRole.employee: 1,
    }
    return hierarchy.get(user_role, 0) >= hierarchy.get(role, 0)


# ═════════════════════════════════════════════════════════════════════
# Employee Endpoints
# ═════════════════════════════════════════════════════════════════════


# ── GET /employees — List employees ─────────────────────────────────

@employees_router.get("")
async def list_employees(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: Employee = Depends(get_current_user),
    pagination: PaginationParams = Depends(),
    search: Optional[str] = Query(None, description="Search by name, email, or employee code"),
    department_id: Optional[uuid.UUID] = Query(None, description="Filter by department"),
    location_id: Optional[uuid.UUID] = Query(None, description="Filter by location"),
    employment_status: Optional[str] = Query(None, description="Filter by status (active, notice_period, relieved, absconding)"),
    reports_to_id: Optional[uuid.UUID] = Query(None, description="Filter by reporting manager"),
    joining_date_from: Optional[date] = Query(None, description="Joining date range start"),
    joining_date_to: Optional[date] = Query(None, description="Joining date range end"),
):
    """List employees with pagination, search, and filtering.

    - **employee**: sees limited fields (list items)
    - **hr_admin+**: sees all fields
    """
    result = await EmployeeService.list_employees(
        db,
        pagination,
        search=search,
        department_id=department_id,
        location_id=location_id,
        employment_status=employment_status,
        reporting_manager_id=reports_to_id,
    )

    # Serialize data based on role
    is_hr = _is_at_least(request, UserRole.hr_admin)
    if is_hr:
        items = [EmployeeListItem.model_validate(emp) for emp in result.data]
    else:
        # Limited fields for regular employees
        items = [
            EmployeeSummary.model_validate(emp) for emp in result.data
        ]

    return {
        "data": [item.model_dump(mode="json") for item in items],
        "meta": result.meta.model_dump(),
    }


# ── GET /employees/org-chart — Organisation hierarchy ──────────────
# NOTE: This MUST be defined before /employees/{employee_id} to avoid
# path parameter conflict.

@employees_router.get("/org-chart")
async def get_org_chart(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: Employee = Depends(get_current_user),
    root_id: Optional[uuid.UUID] = Query(None, description="Start from this employee; omit for full tree"),
    max_depth: int = Query(5, ge=1, le=10, description="Maximum tree depth"),
):
    """Build the organisational hierarchy tree.

    Returns a recursive tree of ``OrgChartNode`` objects.
    """
    nodes = await EmployeeService.build_org_chart(db, root_id, max_depth=max_depth)
    return {
        "data": [node.model_dump(mode="json") for node in nodes],
        "message": "Organisation chart retrieved successfully.",
    }


# ── GET /employees/{id} — Full employee profile ────────────────────

@employees_router.get("/{employee_id}")
async def get_employee(
    employee_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: Employee = Depends(get_current_user),
):
    """Retrieve the full employee profile.

    Access rules:
    - **employee**: own profile only
    - **manager**: own + direct reports
    - **hr_admin+**: any employee
    """
    # Access control
    is_hr = _is_at_least(request, UserRole.hr_admin)
    is_manager = _is_at_least(request, UserRole.manager)
    is_own = current_user.id == employee_id

    if not is_hr and not is_own:
        if is_manager:
            # Managers can view their direct reports
            detail = await EmployeeService.get_employee(db, employee_id)
            if detail.reporting_manager and detail.reporting_manager.id == current_user.id:
                return {
                    "data": detail.model_dump(mode="json"),
                    "message": "Employee profile retrieved successfully.",
                }
            raise ForbiddenException(
                detail="You can only view your own profile or your direct reports.",
            )
        raise ForbiddenException(
            detail="You can only view your own profile.",
        )

    detail = await EmployeeService.get_employee(db, employee_id)
    return {
        "data": detail.model_dump(mode="json"),
        "message": "Employee profile retrieved successfully.",
    }


# ── POST /employees — Create employee ──────────────────────────────

@employees_router.post("", status_code=201)
async def create_employee(
    body: EmployeeCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Employee = Depends(require_role(UserRole.hr_admin)),
):
    """Create a new employee record. Requires **hr_admin** role or above.

    Auto-generates ``display_name`` from first + last name if not provided.
    """
    employee = await EmployeeService.create_employee(
        db,
        body,
        actor_id=current_user.id,
    )

    detail = await EmployeeService.get_employee(db, employee.id)
    return {
        "data": detail.model_dump(mode="json"),
        "message": "Employee created successfully.",
    }


# ── PUT /employees/{id} — Update employee ──────────────────────────

@employees_router.put("/{employee_id}")
async def update_employee(
    employee_id: uuid.UUID,
    body: EmployeeUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: Employee = Depends(get_current_user),
):
    """Update an employee record (partial update).

    Access rules:
    - **employee**: own profile, limited fields only (personal_email, phone,
      current_address, permanent_address, emergency_contact, profile_photo_url)
    - **hr_admin+**: any employee, all fields
    """
    is_hr = _is_at_least(request, UserRole.hr_admin)
    is_own = current_user.id == employee_id

    if not is_hr and not is_own:
        raise ForbiddenException(
            detail="You can only update your own profile.",
        )

    # Restrict fields for non-HR users
    if not is_hr and is_own:
        allowed_fields = {
            "personal_email",
            "phone",
            "current_address",
            "permanent_address",
            "emergency_contact",
            "profile_photo_url",
        }
        provided = body.model_dump(exclude_unset=True)
        disallowed = set(provided.keys()) - allowed_fields
        if disallowed:
            raise ForbiddenException(
                detail=f"You are not allowed to update: {', '.join(sorted(disallowed))}. "
                       f"Only these fields can be self-updated: {', '.join(sorted(allowed_fields))}.",
            )

    employee = await EmployeeService.update_employee(
        db,
        employee_id,
        body,
        actor_id=current_user.id,
    )

    detail = await EmployeeService.get_employee(db, employee.id)
    return {
        "data": detail.model_dump(mode="json"),
        "message": "Employee updated successfully.",
    }


# ── GET /employees/{id}/profile — Rich employee profile ─────────────

@employees_router.get("/{employee_id}/profile")
async def get_employee_profile(
    employee_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: Employee = Depends(get_current_user),
):
    """Retrieve a comprehensive employee profile with attendance, leave, and team data.

    Returns:
    - Personal & employment info (full detail)
    - Attendance summary (present days, avg check-in, late count this month)
    - Recent attendance (last 7 days)
    - Leave balances (all types with used/remaining)
    - Recent leave requests (last 5)
    - Team members (if the employee is a manager)

    Access rules:
    - **employee**: own profile only
    - **manager**: own + direct reports
    - **hr_admin+**: any employee
    """
    # ── Access control ──────────────────────────────────────────
    is_hr = _is_at_least(request, UserRole.hr_admin)
    is_manager = _is_at_least(request, UserRole.manager)
    is_own = current_user.id == employee_id

    if not is_hr and not is_own:
        if is_manager:
            detail = await EmployeeService.get_employee(db, employee_id)
            if not (detail.reporting_manager and detail.reporting_manager.id == current_user.id):
                raise ForbiddenException(
                    detail="You can only view your own profile or your direct reports.",
                )
        else:
            raise ForbiddenException(
                detail="You can only view your own profile.",
            )

    # ── Employee detail ─────────────────────────────────────────
    detail = await EmployeeService.get_employee(db, employee_id)

    # ── Attendance: this month summary ──────────────────────────
    today = date.today()
    month_start = today.replace(day=1)

    attendance_records_result = await db.execute(
        select(AttendanceRecord)
        .where(
            AttendanceRecord.employee_id == employee_id,
            AttendanceRecord.date >= month_start,
            AttendanceRecord.date <= today,
        )
        .order_by(AttendanceRecord.date.desc())
    )
    month_records = attendance_records_result.scalars().all()

    present_days = sum(
        1 for r in month_records if r.status.value in ("present", "work_from_home", "on_duty")
    )
    half_days = sum(1 for r in month_records if r.status.value == "half_day")
    late_count = sum(
        1 for r in month_records
        if r.arrival_status and r.arrival_status.value in ("late", "very_late")
    )

    # Average check-in time
    clock_in_times = [
        r.first_clock_in for r in month_records if r.first_clock_in is not None
    ]
    avg_check_in: Optional[str] = None
    if clock_in_times:
        # Convert to IST for display
        ist = timezone(timedelta(hours=5, minutes=30))
        total_minutes = 0
        for t in clock_in_times:
            ist_time = t.astimezone(ist)
            total_minutes += ist_time.hour * 60 + ist_time.minute
        avg_minutes = total_minutes // len(clock_in_times)
        avg_h, avg_m = divmod(avg_minutes, 60)
        period = "AM" if avg_h < 12 else "PM"
        display_h = avg_h if avg_h <= 12 else avg_h - 12
        if display_h == 0:
            display_h = 12
        avg_check_in = f"{display_h}:{avg_m:02d} {period}"

    attendance_summary = {
        "present_days": present_days,
        "half_days": half_days,
        "late_count": late_count,
        "avg_check_in": avg_check_in,
        "total_working_days": sum(
            1 for r in month_records
            if r.status.value not in ("weekend", "holiday")
        ),
    }

    # ── Attendance: recent 7 days ───────────────────────────────
    seven_days_ago = today - timedelta(days=6)
    recent_attendance_result = await db.execute(
        select(AttendanceRecord)
        .where(
            AttendanceRecord.employee_id == employee_id,
            AttendanceRecord.date >= seven_days_ago,
            AttendanceRecord.date <= today,
        )
        .order_by(AttendanceRecord.date.desc())
    )
    recent_attendance_records = recent_attendance_result.scalars().all()
    recent_attendance = [
        {
            "date": r.date.isoformat(),
            "status": r.status.value,
            "arrival_status": r.arrival_status.value if r.arrival_status else None,
            "first_clock_in": r.first_clock_in.isoformat() if r.first_clock_in else None,
            "last_clock_out": r.last_clock_out.isoformat() if r.last_clock_out else None,
            "total_work_minutes": r.total_work_minutes,
        }
        for r in recent_attendance_records
    ]

    # ── Leave balances ──────────────────────────────────────────
    current_year = today.year
    balances_result = await db.execute(
        select(LeaveBalance)
        .where(
            LeaveBalance.employee_id == employee_id,
            LeaveBalance.year == current_year,
        )
        .options(selectinload(LeaveBalance.leave_type))
    )
    balances = balances_result.scalars().all()
    leave_balances = [
        {
            "leave_type": {
                "id": str(b.leave_type.id),
                "code": b.leave_type.code,
                "name": b.leave_type.name,
                "is_paid": b.leave_type.is_paid,
            } if b.leave_type else None,
            "opening_balance": float(b.opening_balance),
            "accrued": float(b.accrued),
            "used": float(b.used),
            "carry_forwarded": float(b.carry_forwarded),
            "adjusted": float(b.adjusted),
            "current_balance": float(b.current_balance),
        }
        for b in balances
    ]

    # ── Recent leave requests (last 5) ──────────────────────────
    leave_requests_result = await db.execute(
        select(LeaveRequest)
        .where(LeaveRequest.employee_id == employee_id)
        .options(selectinload(LeaveRequest.leave_type))
        .order_by(LeaveRequest.created_at.desc())
        .limit(5)
    )
    leave_requests = leave_requests_result.scalars().all()
    recent_leaves = [
        {
            "id": str(lr.id),
            "leave_type": {
                "id": str(lr.leave_type.id),
                "code": lr.leave_type.code,
                "name": lr.leave_type.name,
            } if lr.leave_type else None,
            "start_date": lr.start_date.isoformat(),
            "end_date": lr.end_date.isoformat(),
            "total_days": float(lr.total_days),
            "status": lr.status.value,
            "reason": lr.reason,
            "created_at": lr.created_at.isoformat(),
        }
        for lr in leave_requests
    ]

    # ── Team members (if manager) ───────────────────────────────
    team_members = []
    direct_reports = await EmployeeService.get_direct_reports(db, employee_id)
    for member in direct_reports:
        member.ensure_display_name()
        team_members.append({
            "id": str(member.id),
            "employee_code": member.employee_code,
            "display_name": member.display_name or member.full_name,
            "designation": member.designation,
            "department": member.department.name if member.department else None,
            "profile_photo_url": member.profile_photo_url,
            "email": member.email,
        })

    # ── Attendance: full month daily data for calendar ──────────
    month_attendance = [
        {
            "date": r.date.isoformat(),
            "status": r.status.value,
            "arrival_status": r.arrival_status.value if r.arrival_status else None,
            "first_clock_in": r.first_clock_in.isoformat() if r.first_clock_in else None,
            "last_clock_out": r.last_clock_out.isoformat() if r.last_clock_out else None,
            "total_work_minutes": r.total_work_minutes,
        }
        for r in month_records
    ]

    # ── Build response ──────────────────────────────────────────
    return {
        "data": {
            "employee": detail.model_dump(mode="json"),
            "attendance_summary": attendance_summary,
            "recent_attendance": recent_attendance,
            "month_attendance": month_attendance,
            "leave_balances": leave_balances,
            "recent_leaves": recent_leaves,
            "team_members": team_members,
        },
        "message": "Employee profile retrieved successfully.",
    }


# ── GET /employees/{id}/direct-reports — Direct reports ─────────────

@employees_router.get("/{employee_id}/direct-reports")
async def get_direct_reports(
    employee_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: Employee = Depends(get_current_user),
):
    """List the direct reports of a given manager.

    - **employee/manager**: own direct reports only
    - **hr_admin+**: any manager's direct reports
    """
    is_hr = _is_at_least(request, UserRole.hr_admin)
    if not is_hr and current_user.id != employee_id:
        raise ForbiddenException(
            detail="You can only view your own direct reports.",
        )

    reports = await EmployeeService.get_direct_reports(db, employee_id)
    items = [EmployeeListItem.model_validate(emp) for emp in reports]
    return {
        "data": [item.model_dump(mode="json") for item in items],
        "message": f"Found {len(items)} direct report(s).",
    }


# ═════════════════════════════════════════════════════════════════════
# Department Endpoints
# ═════════════════════════════════════════════════════════════════════


# ── GET /departments — List departments ─────────────────────────────

@departments_router.get("")
async def list_departments(
    db: AsyncSession = Depends(get_db),
    current_user: Employee = Depends(get_current_user),
):
    """List all active departments with employee counts."""
    departments = await DepartmentService.list_departments(db)
    return {
        "data": [dept.model_dump(mode="json") for dept in departments],
        "message": f"Found {len(departments)} department(s).",
    }


# ── GET /departments/{id} — Department detail ──────────────────────

@departments_router.get("/{department_id}")
async def get_department(
    department_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Employee = Depends(get_current_user),
):
    """Retrieve a single department with employee count and enrichments."""
    dept = await DepartmentService.get_department(db, department_id)
    return {
        "data": dept.model_dump(mode="json"),
        "message": "Department retrieved successfully.",
    }


# ── GET /departments/{id}/members — Paginated employee list ────

@departments_router.get("/{department_id}/members")
async def list_department_members(
    department_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Employee = Depends(get_current_user),
    pagination: PaginationParams = Depends(),
    search: Optional[str] = Query(None, description="Search by name, email, or employee code"),
    employment_status: Optional[str] = Query(None, description="Filter by status"),
):
    """Paginated list of employees belonging to a department."""
    # Verify department exists
    await DepartmentService.get_department(db, department_id)

    result = await EmployeeService.list_employees(
        db,
        pagination,
        department_id=department_id,
        search=search,
        employment_status=employment_status,
    )

    items = [EmployeeListItem.model_validate(emp) for emp in result.data]
    return {
        "data": [item.model_dump(mode="json") for item in items],
        "meta": result.meta.model_dump(),
        "message": f"Found {result.meta.total} member(s) in department.",
    }


# ═════════════════════════════════════════════════════════════════════
# Location Endpoints
# ═════════════════════════════════════════════════════════════════════


# ── GET /locations — List locations ─────────────────────────────────

@locations_router.get("")
async def list_locations(
    db: AsyncSession = Depends(get_db),
    current_user: Employee = Depends(get_current_user),
):
    """List all active locations."""
    locations = await LocationService.list_locations(db)
    return {
        "data": [loc.model_dump(mode="json") for loc in locations],
        "message": f"Found {len(locations)} location(s).",
    }


# ── GET /locations/{id} — Location detail ──────────────────────────

@locations_router.get("/{location_id}")
async def get_location(
    location_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Employee = Depends(get_current_user),
):
    """Retrieve a single location."""
    location = await LocationService.get_location(db, location_id)
    return {
        "data": location.model_dump(mode="json"),
        "message": "Location retrieved successfully.",
    }
