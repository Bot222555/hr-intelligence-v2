"""Admin router — CRUD for leave types, shift policies, holidays, roles.

All endpoints require system_admin or hr_admin role.
"""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.admin.schemas import (
    HolidayCreate,
    HolidayOut,
    HolidayUpdate,
    LeaveTypeCreate,
    LeaveTypeOut,
    LeaveTypeUpdate,
    EmployeeRoleOut,
    RoleAssignRequest,
    ShiftPolicyCreate,
    ShiftPolicyOut,
    ShiftPolicyUpdate,
)
from backend.admin.service import AdminService
from backend.auth.dependencies import require_role
from backend.common.constants import UserRole
from backend.core_hr.models import Employee
from backend.database import get_db

router = APIRouter(prefix="", tags=["admin"])

_admin_dep = require_role(UserRole.system_admin, UserRole.hr_admin)


# ═══════════════════════════════════════════════════════════════════
# LEAVE TYPES
# ═══════════════════════════════════════════════════════════════════

@router.get("/leave-types", response_model=list[LeaveTypeOut])
async def list_leave_types(
    _user: Employee = Depends(_admin_dep),
    db: AsyncSession = Depends(get_db),
):
    """List all leave types (active + inactive)."""
    return await AdminService.list_leave_types(db)


@router.post("/leave-types", response_model=LeaveTypeOut, status_code=201)
async def create_leave_type(
    body: LeaveTypeCreate,
    _user: Employee = Depends(_admin_dep),
    db: AsyncSession = Depends(get_db),
):
    """Create a new leave type."""
    return await AdminService.create_leave_type(db, body)


@router.put("/leave-types/{leave_type_id}", response_model=LeaveTypeOut)
async def update_leave_type(
    leave_type_id: uuid.UUID,
    body: LeaveTypeUpdate,
    _user: Employee = Depends(_admin_dep),
    db: AsyncSession = Depends(get_db),
):
    """Update an existing leave type."""
    return await AdminService.update_leave_type(db, leave_type_id, body)


# ═══════════════════════════════════════════════════════════════════
# SHIFT POLICIES
# ═══════════════════════════════════════════════════════════════════

@router.get("/shift-policies", response_model=list[ShiftPolicyOut])
async def list_shift_policies(
    _user: Employee = Depends(_admin_dep),
    db: AsyncSession = Depends(get_db),
):
    """List all shift policies."""
    return await AdminService.list_shift_policies(db)


@router.post("/shift-policies", response_model=ShiftPolicyOut, status_code=201)
async def create_shift_policy(
    body: ShiftPolicyCreate,
    _user: Employee = Depends(_admin_dep),
    db: AsyncSession = Depends(get_db),
):
    """Create a new shift policy."""
    return await AdminService.create_shift_policy(db, body)


@router.put("/shift-policies/{policy_id}", response_model=ShiftPolicyOut)
async def update_shift_policy(
    policy_id: uuid.UUID,
    body: ShiftPolicyUpdate,
    _user: Employee = Depends(_admin_dep),
    db: AsyncSession = Depends(get_db),
):
    """Update an existing shift policy."""
    return await AdminService.update_shift_policy(db, policy_id, body)


# ═══════════════════════════════════════════════════════════════════
# HOLIDAYS
# ═══════════════════════════════════════════════════════════════════

@router.get("/holidays", response_model=list[HolidayOut])
async def list_holidays(
    year: Optional[int] = Query(default=None, ge=2020, le=2030),
    _user: Employee = Depends(_admin_dep),
    db: AsyncSession = Depends(get_db),
):
    """List holidays, optionally filtered by year."""
    return await AdminService.list_holidays(db, year)


@router.post("/holidays", response_model=HolidayOut, status_code=201)
async def create_holiday(
    body: HolidayCreate,
    _user: Employee = Depends(_admin_dep),
    db: AsyncSession = Depends(get_db),
):
    """Create a new holiday."""
    return await AdminService.create_holiday(db, body)


@router.put("/holidays/{holiday_id}", response_model=HolidayOut)
async def update_holiday(
    holiday_id: uuid.UUID,
    body: HolidayUpdate,
    _user: Employee = Depends(_admin_dep),
    db: AsyncSession = Depends(get_db),
):
    """Update an existing holiday."""
    return await AdminService.update_holiday(db, holiday_id, body)


@router.delete("/holidays/{holiday_id}", status_code=204)
async def delete_holiday(
    holiday_id: uuid.UUID,
    _user: Employee = Depends(_admin_dep),
    db: AsyncSession = Depends(get_db),
):
    """Delete a holiday."""
    await AdminService.delete_holiday(db, holiday_id)


# ═══════════════════════════════════════════════════════════════════
# ROLES
# ═══════════════════════════════════════════════════════════════════

@router.get("/roles", response_model=list[EmployeeRoleOut])
async def list_roles(
    _user: Employee = Depends(_admin_dep),
    db: AsyncSession = Depends(get_db),
):
    """List all active employees with their roles."""
    return await AdminService.list_roles(db)


@router.put("/roles", response_model=EmployeeRoleOut)
async def assign_role(
    body: RoleAssignRequest,
    _user: Employee = Depends(_admin_dep),
    db: AsyncSession = Depends(get_db),
):
    """Assign a role to an employee."""
    return await AdminService.assign_role(db, body)


# ═══════════════════════════════════════════════════════════════════
# SEED
# ═══════════════════════════════════════════════════════════════════

@router.post("/holidays/seed-2026", status_code=201)
async def seed_holidays_2026(
    _user: Employee = Depends(_admin_dep),
    db: AsyncSession = Depends(get_db),
):
    """Seed 2026 Indian national holidays into the default calendar."""
    count = await AdminService.seed_holidays_2026(db)
    return {"message": f"Seeded {count} new holidays for 2026.", "created": count}
