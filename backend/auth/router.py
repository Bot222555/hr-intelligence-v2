"""Auth router — Google OAuth, token refresh, logout, current user profile."""

from __future__ import annotations

import hashlib
import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.auth.dependencies import get_current_user
from backend.auth.schemas import (
    GoogleAuthRequest,
    MeResponse,
    RefreshRequest,
    RefreshResponse,
    TokenResponse,
    UserInfo,
    DeptBrief,
    LocationBrief,
)
from backend.auth.service import (
    find_or_create_session,
    get_employee_by_email,
    get_highest_role,
    refresh_access_token,
    revoke_session,
    validate_domain,
    verify_google_token,
)
from backend.common.audit import create_audit_entry
from backend.common.constants import PERMISSIONS, UserRole
from backend.config import settings
from backend.core_hr.models import Employee
from backend.database import get_db

router = APIRouter(prefix="", tags=["auth"])


# ── POST /google — Google OAuth callback ────────────────────────────

@router.post("/google", response_model=TokenResponse)
async def google_auth(
    body: GoogleAuthRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    # 1. Exchange code for Google user info
    google_info = await verify_google_token(body.code, body.redirect_uri)

    # 2. Domain gate
    validate_domain(google_info["email"])

    # 3. Find employee
    employee = await get_employee_by_email(db, google_info["email"])

    # Update google_id / profile_photo_url if missing
    if not employee.google_id:
        employee.google_id = google_info["google_id"]
    if not employee.profile_photo_url and google_info.get("picture"):
        employee.profile_photo_url = google_info["picture"]
    await db.flush()

    # 4. Eager-load department + location for the response
    emp_result = await db.execute(
        select(Employee)
        .where(Employee.id == employee.id)
        .options(
            selectinload(Employee.department),
            selectinload(Employee.location),
        ),
    )
    employee = emp_result.scalars().first()

    # 5. Highest role
    role = await get_highest_role(db, employee.id)

    # 6. Create session (JWT pair)
    ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    access_token, refresh_token = await find_or_create_session(
        db, employee, role, ip, user_agent,
    )
    expires_in = settings.JWT_EXPIRY_HOURS * 3600

    # 7. Audit trail
    await create_audit_entry(
        db,
        action="login",
        entity_type="user_session",
        entity_id=employee.id,
        actor_id=employee.id,
        new_values={"ip": ip, "user_agent": user_agent},
        ip_address=ip,
        user_agent=user_agent,
    )

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=expires_in,
        user=UserInfo(
            id=employee.id,
            employee_number=employee.employee_code,
            display_name=f"{employee.first_name} {employee.last_name}",
            email=employee.email,
            role=role.value,
            profile_picture_url=employee.profile_photo_url,
            department=employee.department.name if employee.department else "",
            location=employee.location.name if employee.location else "",
        ),
    )


# ── POST /refresh — Issue new access token ─────────────────────────

@router.post("/refresh", response_model=RefreshResponse)
async def refresh_token(
    body: RefreshRequest,
    db: AsyncSession = Depends(get_db),
):
    new_access, expires_in = await refresh_access_token(db, body.refresh_token)
    return RefreshResponse(access_token=new_access, expires_in=expires_in)


# ── POST /logout — Revoke current session ──────────────────────────

@router.post("/logout")
async def logout(
    request: Request,
    employee: Employee = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    auth_header = request.headers.get("Authorization", "")
    token = auth_header.removeprefix("Bearer ")
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    await revoke_session(db, token_hash)

    # Audit trail
    await create_audit_entry(
        db,
        action="logout",
        entity_type="user_session",
        entity_id=employee.id,
        actor_id=employee.id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    return {"message": "Logged out successfully"}


# ── GET /me — Current user profile ─────────────────────────────────

@router.get("/me", response_model=MeResponse)
async def me(
    request: Request,
    employee: Employee = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    role: UserRole = request.state.user_role
    permissions = PERMISSIONS.get(role, [])

    # Count direct reports
    result = await db.execute(
        select(func.count()).select_from(Employee).where(
            Employee.reporting_manager_id == employee.id,
            Employee.is_active.is_(True),
        ),
    )
    direct_reports_count = result.scalar() or 0

    # Department / Location may already be loaded by get_current_user
    dept = None
    if employee.department:
        dept = DeptBrief(id=employee.department.id, name=employee.department.name)

    loc = None
    if employee.location:
        loc = LocationBrief(id=employee.location.id, name=employee.location.name)

    return MeResponse(
        id=employee.id,
        employee_number=employee.employee_code,
        display_name=f"{employee.first_name} {employee.last_name}",
        email=employee.email,
        role=role.value,
        permissions=permissions,
        profile_picture_url=employee.profile_photo_url,
        department=dept,
        location=loc,
        direct_reports_count=direct_reports_count,
    )
