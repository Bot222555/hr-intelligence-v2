"""Core HR service layer — async CRUD + business logic.

Uses:
  - ``paginate()`` from backend.common.pagination
  - ``apply_filters / apply_search`` from backend.common.filters
  - ``create_audit_entry`` from backend.common.audit
  - ``NotFoundException / ConflictError`` from backend.common.exceptions
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional, Sequence

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.common.audit import create_audit_entry
from backend.common.exceptions import ConflictError, NotFoundException
from backend.common.filters import apply_filters, apply_search
from backend.common.pagination import PaginatedResponse, PaginationParams, paginate
from backend.core_hr.models import Department, Employee, Location
from backend.core_hr.schemas import (
    DepartmentBrief,
    DepartmentResponse,
    EmployeeCreate,
    EmployeeDetail,
    EmployeeListItem,
    EmployeeSummary,
    EmployeeUpdate,
    LocationBrief,
    LocationResponse,
    OrgChartNode,
)


# ═════════════════════════════════════════════════════════════════════
# EmployeeService
# ═════════════════════════════════════════════════════════════════════


class EmployeeService:
    """Async CRUD operations for employees."""

    # ── List (paginated, searchable, filterable) ────────────────────

    @staticmethod
    async def list_employees(
        db: AsyncSession,
        pagination: PaginationParams,
        *,
        search: Optional[str] = None,
        department_id: Optional[uuid.UUID] = None,
        location_id: Optional[uuid.UUID] = None,
        employment_status: Optional[str] = None,
        is_active: Optional[bool] = None,
        reporting_manager_id: Optional[uuid.UUID] = None,
    ) -> PaginatedResponse:
        """Return a paginated, filtered, searchable employee list."""

        query = (
            select(Employee)
            .options(
                selectinload(Employee.department),
                selectinload(Employee.location),
            )
        )

        # Filters
        filters: dict[str, Any] = {
            "department_id": department_id,
            "location_id": location_id,
            "employment_status": employment_status,
            "is_active": is_active,
            "reporting_manager_id": reporting_manager_id,
        }
        query = apply_filters(query, Employee, filters)

        # Full-text search across name / email / employee_code
        if search:
            query = apply_search(
                query,
                Employee,
                search,
                ["first_name", "last_name", "email", "employee_code", "display_name"],
            )

        return await paginate(db, query, pagination, model=Employee)

    # ── Get single ──────────────────────────────────────────────────

    @staticmethod
    async def get_employee(
        db: AsyncSession,
        employee_id: uuid.UUID,
    ) -> EmployeeDetail:
        """Load full employee detail including relationships."""

        result = await db.execute(
            select(Employee)
            .where(Employee.id == employee_id)
            .options(
                selectinload(Employee.department),
                selectinload(Employee.location),
                selectinload(Employee.reporting_manager),
                selectinload(Employee.l2_manager),
            )
        )
        employee = result.scalars().first()
        if employee is None:
            raise NotFoundException("Employee", str(employee_id))

        # Count direct reports
        count_result = await db.execute(
            select(func.count())
            .select_from(Employee)
            .where(
                Employee.reporting_manager_id == employee.id,
                Employee.is_active.is_(True),
            )
        )
        direct_reports_count = count_result.scalar() or 0

        # Build response; ensure display_name
        employee.ensure_display_name()

        detail = EmployeeDetail.model_validate(employee)
        detail.direct_reports_count = direct_reports_count

        # Enrich nested relationships
        if employee.department:
            detail.department = DepartmentBrief.model_validate(employee.department)
        if employee.location:
            detail.location = LocationBrief.model_validate(employee.location)
        if employee.reporting_manager:
            detail.reporting_manager = EmployeeSummary.model_validate(
                employee.reporting_manager,
            )
        if employee.l2_manager:
            detail.l2_manager = EmployeeSummary.model_validate(employee.l2_manager)

        return detail

    # ── Create ──────────────────────────────────────────────────────

    @staticmethod
    async def create_employee(
        db: AsyncSession,
        data: EmployeeCreate,
        *,
        actor_id: Optional[uuid.UUID] = None,
    ) -> Employee:
        """Create a new employee record."""

        # Auto-generate display_name if missing
        if not data.display_name:
            data.display_name = f"{data.first_name} {data.last_name}".strip()

        employee = Employee(
            **data.model_dump(),
            created_by=actor_id,
            updated_by=actor_id,
        )

        db.add(employee)
        try:
            await db.flush()
        except IntegrityError as exc:
            await db.rollback()
            err = str(exc.orig)
            if "employee_code" in err or "employees_employee_code_key" in err:
                raise ConflictError("employee_code", data.employee_code)
            if "email" in err or "employees_email_key" in err:
                raise ConflictError("email", data.email)
            raise

        # Audit
        await create_audit_entry(
            db,
            action="create",
            entity_type="employee",
            entity_id=employee.id,
            actor_id=actor_id,
            new_values=data.model_dump(mode="json"),
        )

        return employee

    # ── Update ──────────────────────────────────────────────────────

    @staticmethod
    async def update_employee(
        db: AsyncSession,
        employee_id: uuid.UUID,
        data: EmployeeUpdate,
        *,
        actor_id: Optional[uuid.UUID] = None,
    ) -> Employee:
        """Partial-update an existing employee."""

        result = await db.execute(
            select(Employee).where(Employee.id == employee_id),
        )
        employee = result.scalars().first()
        if employee is None:
            raise NotFoundException("Employee", str(employee_id))

        # Capture old values for audit
        changes = data.model_dump(exclude_unset=True)
        if not changes:
            return employee

        old_values: dict[str, Any] = {}
        for field, value in changes.items():
            old_val = getattr(employee, field, None)
            # Serialize enums for audit
            if hasattr(old_val, "value"):
                old_val = old_val.value
            old_values[field] = old_val
            setattr(employee, field, value)

        # Re-compute display_name if name parts changed
        if any(k in changes for k in ("first_name", "last_name", "middle_name")):
            employee.ensure_display_name()

        employee.updated_at = datetime.now(timezone.utc)
        employee.updated_by = actor_id

        try:
            await db.flush()
        except IntegrityError as exc:
            await db.rollback()
            err = str(exc.orig)
            if "email" in err:
                raise ConflictError("email", changes.get("email", ""))
            raise

        # Audit
        await create_audit_entry(
            db,
            action="update",
            entity_type="employee",
            entity_id=employee.id,
            actor_id=actor_id,
            old_values=old_values,
            new_values=changes,
        )

        return employee

    # ── Direct reports ──────────────────────────────────────────────

    @staticmethod
    async def get_direct_reports(
        db: AsyncSession,
        manager_id: uuid.UUID,
    ) -> Sequence[Employee]:
        """Return active direct reports for a manager."""

        result = await db.execute(
            select(Employee)
            .where(
                Employee.reporting_manager_id == manager_id,
                Employee.is_active.is_(True),
            )
            .options(
                selectinload(Employee.department),
                selectinload(Employee.location),
            )
            .order_by(Employee.first_name, Employee.last_name)
        )
        return result.scalars().all()

    # ── Org chart ───────────────────────────────────────────────────

    @staticmethod
    async def build_org_chart(
        db: AsyncSession,
        root_id: Optional[uuid.UUID] = None,
        *,
        max_depth: int = 5,
    ) -> list[OrgChartNode]:
        """Build a recursive org-chart tree.

        If *root_id* is provided the tree starts from that employee;
        otherwise all employees without a reporting manager become roots.
        """

        # Load all active employees with department
        result = await db.execute(
            select(Employee)
            .where(Employee.is_active.is_(True))
            .options(selectinload(Employee.department))
            .order_by(Employee.first_name, Employee.last_name)
        )
        all_employees = result.scalars().all()

        # Index by id
        emp_map: dict[uuid.UUID, Employee] = {e.id: e for e in all_employees}

        # Children lookup: manager_id → [employee, ...]
        children_map: dict[Optional[uuid.UUID], list[Employee]] = {}
        for emp in all_employees:
            children_map.setdefault(emp.reporting_manager_id, []).append(emp)

        def _build_node(emp: Employee, depth: int) -> OrgChartNode:
            emp.ensure_display_name()
            node = OrgChartNode(
                id=emp.id,
                employee_code=emp.employee_code,
                display_name=emp.display_name or emp.full_name,
                designation=emp.designation,
                department=emp.department.name if emp.department else None,
                profile_photo_url=emp.profile_photo_url,
            )
            if depth < max_depth:
                for child in children_map.get(emp.id, []):
                    node.children.append(_build_node(child, depth + 1))
            return node

        # Determine root(s)
        if root_id:
            root_emp = emp_map.get(root_id)
            if root_emp is None:
                raise NotFoundException("Employee", str(root_id))
            return [_build_node(root_emp, 0)]

        # All top-level employees (no manager)
        roots = children_map.get(None, [])
        return [_build_node(r, 0) for r in roots]


# ═════════════════════════════════════════════════════════════════════
# DepartmentService
# ═════════════════════════════════════════════════════════════════════


class DepartmentService:
    """Async read operations for departments."""

    @staticmethod
    async def list_departments(
        db: AsyncSession,
        *,
        is_active: Optional[bool] = True,
        include_employee_count: bool = True,
    ) -> list[DepartmentResponse]:
        """Return all departments with optional employee count."""

        query = (
            select(Department)
            .options(
                selectinload(Department.location),
                selectinload(Department.head_employee),
            )
            .order_by(Department.name)
        )
        if is_active is not None:
            query = query.where(Department.is_active == is_active)

        result = await db.execute(query)
        departments = result.scalars().all()

        # Batch-fetch employee counts
        emp_counts: dict[uuid.UUID, int] = {}
        if include_employee_count:
            count_result = await db.execute(
                select(
                    Employee.department_id,
                    func.count(Employee.id).label("cnt"),
                )
                .where(Employee.is_active.is_(True))
                .group_by(Employee.department_id)
            )
            emp_counts = {row[0]: row[1] for row in count_result.all() if row[0]}

        responses: list[DepartmentResponse] = []
        for dept in departments:
            resp = DepartmentResponse.model_validate(dept)
            resp.employee_count = emp_counts.get(dept.id, 0)
            if dept.location:
                resp.location = LocationBrief.model_validate(dept.location)
            if dept.head_employee:
                head = dept.head_employee
                resp.head_employee_name = (
                    f"{head.first_name} {head.last_name}".strip()
                )
            responses.append(resp)

        return responses

    @staticmethod
    async def get_department(
        db: AsyncSession,
        department_id: uuid.UUID,
    ) -> DepartmentResponse:
        """Load a single department with enrichments."""

        result = await db.execute(
            select(Department)
            .where(Department.id == department_id)
            .options(
                selectinload(Department.location),
                selectinload(Department.head_employee),
                selectinload(Department.children),
            )
        )
        dept = result.scalars().first()
        if dept is None:
            raise NotFoundException("Department", str(department_id))

        # Employee count for this department
        count_result = await db.execute(
            select(func.count())
            .select_from(Employee)
            .where(
                Employee.department_id == department_id,
                Employee.is_active.is_(True),
            )
        )
        emp_count = count_result.scalar() or 0

        resp = DepartmentResponse.model_validate(dept)
        resp.employee_count = emp_count
        if dept.location:
            resp.location = LocationBrief.model_validate(dept.location)
        if dept.head_employee:
            head = dept.head_employee
            resp.head_employee_name = (
                f"{head.first_name} {head.last_name}".strip()
            )

        return resp


# ═════════════════════════════════════════════════════════════════════
# LocationService
# ═════════════════════════════════════════════════════════════════════


class LocationService:
    """Async read operations for locations."""

    @staticmethod
    async def list_locations(
        db: AsyncSession,
        *,
        is_active: Optional[bool] = True,
    ) -> list[LocationResponse]:
        """Return all locations."""

        query = select(Location).order_by(Location.name)
        if is_active is not None:
            query = query.where(Location.is_active == is_active)

        result = await db.execute(query)
        locations = result.scalars().all()
        return [LocationResponse.model_validate(loc) for loc in locations]

    @staticmethod
    async def get_location(
        db: AsyncSession,
        location_id: uuid.UUID,
    ) -> LocationResponse:
        """Load a single location."""

        result = await db.execute(
            select(Location).where(Location.id == location_id),
        )
        location = result.scalars().first()
        if location is None:
            raise NotFoundException("Location", str(location_id))

        return LocationResponse.model_validate(location)
