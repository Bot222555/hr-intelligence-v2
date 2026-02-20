"""Core HR router — Employee, Department, Location API endpoints.

Provides CRUD operations for the core HR module with role-based access control.

Routes:
    /employees              — List, create employees
    /employees/org-chart    — Organisation hierarchy
    /employees/{id}         — Get, update employee
    /employees/{id}/direct-reports — Manager's direct reports
    /departments            — List departments
    /departments/{id}       — Department detail
    /locations              — List locations
    /locations/{id}         — Location detail
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth.dependencies import get_current_user, require_role
from backend.common.constants import UserRole
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
