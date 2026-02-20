"""Admin service — CRUD for leave types, shift policies, holidays, roles."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.admin.schemas import (
    HolidayCreate,
    HolidayUpdate,
    LeaveTypeCreate,
    LeaveTypeUpdate,
    RoleAssignRequest,
    ShiftPolicyCreate,
    ShiftPolicyUpdate,
)
from backend.attendance.models import Holiday, HolidayCalendar, ShiftPolicy
from backend.auth.models import RoleAssignment
from backend.auth.service import get_highest_role
from backend.common.constants import UserRole
from backend.core_hr.models import Employee
from backend.leave.models import LeaveType


class AdminService:
    """Static service class for admin operations."""

    # ── Leave Types ─────────────────────────────────────────────────

    @staticmethod
    async def list_leave_types(db: AsyncSession) -> list[LeaveType]:
        result = await db.execute(
            select(LeaveType).order_by(LeaveType.code)
        )
        return list(result.scalars().all())

    @staticmethod
    async def create_leave_type(db: AsyncSession, data: LeaveTypeCreate) -> LeaveType:
        # Check unique code
        existing = await db.execute(
            select(LeaveType).where(LeaveType.code == data.code.upper())
        )
        if existing.scalars().first():
            raise HTTPException(status_code=409, detail=f"Leave type code '{data.code}' already exists.")

        lt = LeaveType(
            code=data.code.upper(),
            name=data.name,
            description=data.description,
            default_balance=data.default_balance,
            max_carry_forward=data.max_carry_forward,
            is_paid=data.is_paid,
            requires_approval=data.requires_approval,
            min_days_notice=data.min_days_notice,
            max_consecutive_days=data.max_consecutive_days,
            applicable_gender=data.applicable_gender,
        )
        db.add(lt)
        await db.flush()
        await db.refresh(lt)
        return lt

    @staticmethod
    async def update_leave_type(
        db: AsyncSession, leave_type_id: uuid.UUID, data: LeaveTypeUpdate
    ) -> LeaveType:
        result = await db.execute(
            select(LeaveType).where(LeaveType.id == leave_type_id)
        )
        lt = result.scalars().first()
        if not lt:
            raise HTTPException(status_code=404, detail="Leave type not found.")

        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(lt, key, value)
        lt.updated_at = datetime.now(timezone.utc)

        await db.flush()
        await db.refresh(lt)
        return lt

    # ── Shift Policies ──────────────────────────────────────────────

    @staticmethod
    async def list_shift_policies(db: AsyncSession) -> list[ShiftPolicy]:
        result = await db.execute(
            select(ShiftPolicy).order_by(ShiftPolicy.name)
        )
        return list(result.scalars().all())

    @staticmethod
    async def create_shift_policy(db: AsyncSession, data: ShiftPolicyCreate) -> ShiftPolicy:
        existing = await db.execute(
            select(ShiftPolicy).where(ShiftPolicy.name == data.name)
        )
        if existing.scalars().first():
            raise HTTPException(status_code=409, detail=f"Shift policy '{data.name}' already exists.")

        sp = ShiftPolicy(
            name=data.name,
            start_time=data.start_time,
            end_time=data.end_time,
            grace_minutes=data.grace_minutes,
            half_day_minutes=data.half_day_minutes,
            full_day_minutes=data.full_day_minutes,
            is_night_shift=data.is_night_shift,
        )
        db.add(sp)
        await db.flush()
        await db.refresh(sp)
        return sp

    @staticmethod
    async def update_shift_policy(
        db: AsyncSession, policy_id: uuid.UUID, data: ShiftPolicyUpdate
    ) -> ShiftPolicy:
        result = await db.execute(
            select(ShiftPolicy).where(ShiftPolicy.id == policy_id)
        )
        sp = result.scalars().first()
        if not sp:
            raise HTTPException(status_code=404, detail="Shift policy not found.")

        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(sp, key, value)
        sp.updated_at = datetime.now(timezone.utc)

        await db.flush()
        await db.refresh(sp)
        return sp

    # ── Holidays ────────────────────────────────────────────────────

    @staticmethod
    async def _get_or_create_calendar(
        db: AsyncSession, year: int
    ) -> HolidayCalendar:
        """Get or create the default holiday calendar for a year."""
        result = await db.execute(
            select(HolidayCalendar).where(
                HolidayCalendar.name == "Default",
                HolidayCalendar.year == year,
                HolidayCalendar.location_id.is_(None),
            )
        )
        cal = result.scalars().first()
        if cal:
            return cal

        cal = HolidayCalendar(name="Default", year=year, is_active=True)
        db.add(cal)
        await db.flush()
        await db.refresh(cal)
        return cal

    @staticmethod
    async def list_holidays(
        db: AsyncSession, year: Optional[int] = None
    ) -> list[dict]:
        query = (
            select(Holiday)
            .join(HolidayCalendar)
            .order_by(Holiday.date)
        )
        if year:
            query = query.where(HolidayCalendar.year == year)

        result = await db.execute(query)
        holidays = result.scalars().all()

        return [
            {
                "id": h.id,
                "name": h.name,
                "date": h.date,
                "type": "optional" if h.is_optional else ("restricted" if h.is_restricted else "national"),
                "is_active": True,  # Holiday model doesn't have is_active, treat all as active
                "calendar_id": h.calendar_id,
            }
            for h in holidays
        ]

    @staticmethod
    async def create_holiday(db: AsyncSession, data: HolidayCreate) -> dict:
        year = data.date.year
        cal = await AdminService._get_or_create_calendar(db, year)

        h = Holiday(
            calendar_id=cal.id,
            name=data.name,
            date=data.date,
            is_optional=(data.type == "optional"),
            is_restricted=(data.type == "restricted"),
        )
        db.add(h)
        await db.flush()
        await db.refresh(h)

        return {
            "id": h.id,
            "name": h.name,
            "date": h.date,
            "type": data.type,
            "is_active": True,
            "calendar_id": h.calendar_id,
        }

    @staticmethod
    async def update_holiday(
        db: AsyncSession, holiday_id: uuid.UUID, data: HolidayUpdate
    ) -> dict:
        result = await db.execute(
            select(Holiday).where(Holiday.id == holiday_id)
        )
        h = result.scalars().first()
        if not h:
            raise HTTPException(status_code=404, detail="Holiday not found.")

        if data.name is not None:
            h.name = data.name
        if data.date is not None:
            h.date = data.date
        if data.type is not None:
            h.is_optional = (data.type == "optional")
            h.is_restricted = (data.type == "restricted")

        await db.flush()
        await db.refresh(h)

        return {
            "id": h.id,
            "name": h.name,
            "date": h.date,
            "type": "optional" if h.is_optional else ("restricted" if h.is_restricted else "national"),
            "is_active": True,
            "calendar_id": h.calendar_id,
        }

    @staticmethod
    async def delete_holiday(db: AsyncSession, holiday_id: uuid.UUID) -> None:
        result = await db.execute(
            select(Holiday).where(Holiday.id == holiday_id)
        )
        h = result.scalars().first()
        if not h:
            raise HTTPException(status_code=404, detail="Holiday not found.")
        await db.delete(h)
        await db.flush()

    # ── Role Management ─────────────────────────────────────────────

    @staticmethod
    async def list_roles(db: AsyncSession) -> list[dict]:
        result = await db.execute(
            select(Employee)
            .where(Employee.is_active.is_(True))
            .options(selectinload(Employee.department))
            .order_by(Employee.display_name)
        )
        employees = result.scalars().all()

        out = []
        for e in employees:
            role = await get_highest_role(db, e.id)
            out.append({
                "employee_id": e.id,
                "employee_number": e.employee_number,
                "display_name": e.display_name,
                "email": e.email,
                "role": role.value,
                "department": e.department.name if e.department else None,
            })
        return out

    @staticmethod
    async def assign_role(db: AsyncSession, data: RoleAssignRequest) -> dict:
        result = await db.execute(
            select(Employee)
            .where(Employee.id == data.employee_id, Employee.is_active.is_(True))
            .options(selectinload(Employee.department))
        )
        emp = result.scalars().first()
        if not emp:
            raise HTTPException(status_code=404, detail="Employee not found.")

        new_role = UserRole(data.role)

        # Deactivate all existing role assignments
        existing = await db.execute(
            select(RoleAssignment).where(
                RoleAssignment.employee_id == data.employee_id,
                RoleAssignment.is_active.is_(True),
            )
        )
        for ra in existing.scalars().all():
            ra.is_active = False
            ra.revoked_at = datetime.now(timezone.utc)

        # Create new role assignment
        if new_role != UserRole.employee:
            assignment = RoleAssignment(
                employee_id=data.employee_id,
                role=new_role,
                is_active=True,
            )
            db.add(assignment)

        await db.flush()

        return {
            "employee_id": emp.id,
            "employee_number": emp.employee_number,
            "display_name": emp.display_name,
            "email": emp.email,
            "role": new_role.value,
            "department": emp.department.name if emp.department else None,
        }

    # ── Seed 2026 Indian Holidays ───────────────────────────────────

    @staticmethod
    async def seed_holidays_2026(db: AsyncSession) -> int:
        """Seed 2026 Indian national holidays. Returns count of newly created holidays."""
        holidays_data = [
            ("2026-01-26", "Republic Day", False, False),
            ("2026-03-10", "Maha Shivaratri", False, False),
            ("2026-03-17", "Holi", False, False),
            ("2026-03-31", "Id-ul-Fitr (Eid)", False, False),
            ("2026-04-02", "Ram Navami", False, False),
            ("2026-04-03", "Good Friday", False, False),
            ("2026-04-14", "Dr. Ambedkar Jayanti", False, False),
            ("2026-05-01", "May Day", False, False),
            ("2026-05-25", "Buddha Purnima", False, False),
            ("2026-06-07", "Eid ul-Adha (Bakrid)", False, False),
            ("2026-07-07", "Muharram", False, False),
            ("2026-08-15", "Independence Day", False, False),
            ("2026-08-22", "Janmashtami", False, False),
            ("2026-09-05", "Milad-un-Nabi", False, False),
            ("2026-10-02", "Mahatma Gandhi Jayanti", False, False),
            ("2026-10-20", "Dussehra (Vijaya Dashami)", False, False),
            ("2026-11-08", "Diwali", False, False),
            ("2026-11-10", "Govardhan Puja", False, False),
            ("2026-11-12", "Bhai Dooj", False, False),
            ("2026-11-19", "Guru Nanak Jayanti", False, False),
            ("2026-12-25", "Christmas", False, False),
            # Restricted holidays
            ("2026-01-14", "Makar Sankranti / Pongal", False, True),
            ("2026-02-19", "Shivaji Jayanti", False, True),
            ("2026-04-13", "Baisakhi / Vishu", False, True),
            ("2026-08-21", "Onam", False, True),
            ("2026-10-21", "Durga Puja / Navratri", False, True),
            ("2026-11-02", "Karva Chauth", True, False),
            ("2026-11-07", "Diwali Eve (Choti Diwali)", True, False),
        ]

        cal = await AdminService._get_or_create_calendar(db, 2026)
        created = 0

        for date_str, name, is_optional, is_restricted in holidays_data:
            d = date.fromisoformat(date_str)
            existing = await db.execute(
                select(Holiday).where(
                    Holiday.calendar_id == cal.id,
                    Holiday.date == d,
                )
            )
            if existing.scalars().first():
                continue

            h = Holiday(
                calendar_id=cal.id,
                name=name,
                date=d,
                is_optional=is_optional,
                is_restricted=is_restricted,
            )
            db.add(h)
            created += 1

        await db.flush()
        return created
