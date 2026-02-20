"""Core HR Pydantic v2 schemas — request / response validation.

Naming conventions:
  - *Create / *Update  → request bodies (write)
  - *Response / *Detail → response bodies (read)
  - *Summary / *ListItem → compact read representations
"""


import uuid
from datetime import date, datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator


# ═════════════════════════════════════════════════════════════════════
# Shared / embedded
# ═════════════════════════════════════════════════════════════════════


class AddressSchema(BaseModel):
    """Reusable address block (stored as JSONB)."""

    line1: Optional[str] = None
    line2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    pincode: Optional[str] = None
    country: Optional[str] = None


class EmergencyContactSchema(BaseModel):
    """Emergency contact block (stored as JSONB)."""

    name: Optional[str] = None
    relationship: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None


# ═════════════════════════════════════════════════════════════════════
# Location
# ═════════════════════════════════════════════════════════════════════


class LocationResponse(BaseModel):
    """Full location representation."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    pincode: Optional[str] = None
    country: str = "India"
    timezone: str = "Asia/Kolkata"
    is_active: bool = True
    created_at: datetime
    updated_at: datetime


class LocationBrief(BaseModel):
    """Minimal location info embedded in other responses."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    city: Optional[str] = None


# ═════════════════════════════════════════════════════════════════════
# Department
# ═════════════════════════════════════════════════════════════════════


class DepartmentResponse(BaseModel):
    """Full department representation."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    keka_id: Optional[str] = None
    name: str
    code: Optional[str] = None
    description: Optional[str] = None
    parent_department_id: Optional[uuid.UUID] = None
    head_employee_id: Optional[uuid.UUID] = None
    location_id: Optional[uuid.UUID] = None
    is_active: bool = True
    created_at: datetime
    updated_at: datetime
    # Enriched fields (set by service layer)
    employee_count: int = 0
    location: Optional[LocationBrief] = None
    head_employee_name: Optional[str] = None


class DepartmentBrief(BaseModel):
    """Minimal department info embedded in other responses."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    code: Optional[str] = None


# ═════════════════════════════════════════════════════════════════════
# Employee — write schemas
# ═════════════════════════════════════════════════════════════════════


class EmployeeCreate(BaseModel):
    """Payload for creating a new employee."""

    employee_code: str = Field(..., min_length=1, max_length=20)
    keka_id: Optional[str] = None
    first_name: str = Field(..., min_length=1, max_length=100)
    middle_name: Optional[str] = Field(None, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    display_name: Optional[str] = Field(None, max_length=255)
    email: EmailStr
    personal_email: Optional[EmailStr] = None
    phone: Optional[str] = Field(None, max_length=20)
    gender: Optional[str] = None
    date_of_birth: Optional[date] = None
    blood_group: Optional[str] = None
    marital_status: Optional[str] = None
    nationality: str = "Indian"
    current_address: Optional[dict[str, Any]] = None
    permanent_address: Optional[dict[str, Any]] = None
    emergency_contact: Optional[dict[str, Any]] = None
    department_id: Optional[uuid.UUID] = None
    location_id: Optional[uuid.UUID] = None
    job_title: Optional[str] = Field(None, max_length=200)
    designation: Optional[str] = Field(None, max_length=150)
    reporting_manager_id: Optional[uuid.UUID] = None
    l2_manager_id: Optional[uuid.UUID] = None
    date_of_joining: date
    date_of_confirmation: Optional[date] = None
    probation_end_date: Optional[date] = None
    notice_period_days: int = 90
    profile_photo_url: Optional[str] = None
    professional_summary: Optional[str] = None

    @model_validator(mode="after")
    def _auto_display_name(self) -> "EmployeeCreate":
        if not self.display_name:
            self.display_name = f"{self.first_name} {self.last_name}".strip()
        return self


class EmployeeUpdate(BaseModel):
    """Partial-update payload for an employee (all fields optional)."""

    first_name: Optional[str] = Field(None, min_length=1, max_length=100)
    middle_name: Optional[str] = Field(None, max_length=100)
    last_name: Optional[str] = Field(None, min_length=1, max_length=100)
    display_name: Optional[str] = Field(None, max_length=255)
    personal_email: Optional[EmailStr] = None
    phone: Optional[str] = Field(None, max_length=20)
    gender: Optional[str] = None
    date_of_birth: Optional[date] = None
    blood_group: Optional[str] = None
    marital_status: Optional[str] = None
    nationality: Optional[str] = None
    current_address: Optional[dict[str, Any]] = None
    permanent_address: Optional[dict[str, Any]] = None
    emergency_contact: Optional[dict[str, Any]] = None
    department_id: Optional[uuid.UUID] = None
    location_id: Optional[uuid.UUID] = None
    job_title: Optional[str] = Field(None, max_length=200)
    designation: Optional[str] = Field(None, max_length=150)
    reporting_manager_id: Optional[uuid.UUID] = None
    l2_manager_id: Optional[uuid.UUID] = None
    employment_status: Optional[str] = None
    date_of_confirmation: Optional[date] = None
    probation_end_date: Optional[date] = None
    resignation_date: Optional[date] = None
    last_working_date: Optional[date] = None
    date_of_exit: Optional[date] = None
    exit_reason: Optional[str] = None
    notice_period_days: Optional[int] = None
    profile_photo_url: Optional[str] = None
    professional_summary: Optional[str] = None
    is_active: Optional[bool] = None


# ═════════════════════════════════════════════════════════════════════
# Employee — read schemas
# ═════════════════════════════════════════════════════════════════════


class EmployeeSummary(BaseModel):
    """Minimal employee reference (manager links, department head, etc.)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    employee_code: str
    display_name: Optional[str] = None
    email: str
    designation: Optional[str] = None
    profile_photo_url: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def _build_display_name(cls, data: Any) -> Any:
        """Compute display_name from first/last name if not set."""
        if hasattr(data, "__dict__"):
            # ORM object
            if not getattr(data, "display_name", None):
                first = getattr(data, "first_name", "") or ""
                last = getattr(data, "last_name", "") or ""
                data.display_name = f"{first} {last}".strip()
        return data


class EmployeeListItem(BaseModel):
    """Compact employee row for paginated list endpoints."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    employee_code: str
    first_name: str
    last_name: str
    display_name: Optional[str] = None
    email: str
    phone: Optional[str] = None
    designation: Optional[str] = None
    job_title: Optional[str] = None
    employment_status: str
    date_of_joining: date
    is_active: bool
    department: Optional[DepartmentBrief] = None
    location: Optional[LocationBrief] = None
    profile_photo_url: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def _build_display_name(cls, data: Any) -> Any:
        if hasattr(data, "__dict__"):
            if not getattr(data, "display_name", None):
                first = getattr(data, "first_name", "") or ""
                last = getattr(data, "last_name", "") or ""
                data.display_name = f"{first} {last}".strip()
        return data


class EmployeeDetail(BaseModel):
    """Full employee profile — returned by GET /employees/{id}."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    keka_id: Optional[str] = None
    employee_code: str
    first_name: str
    middle_name: Optional[str] = None
    last_name: str
    display_name: Optional[str] = None
    email: str
    personal_email: Optional[str] = None
    phone: Optional[str] = None
    gender: Optional[str] = None
    date_of_birth: Optional[date] = None
    blood_group: Optional[str] = None
    marital_status: Optional[str] = None
    nationality: str = "Indian"
    current_address: Optional[dict[str, Any]] = None
    permanent_address: Optional[dict[str, Any]] = None
    emergency_contact: Optional[dict[str, Any]] = None
    department: Optional[DepartmentBrief] = None
    location: Optional[LocationBrief] = None
    job_title: Optional[str] = None
    designation: Optional[str] = None
    reporting_manager: Optional[EmployeeSummary] = None
    l2_manager: Optional[EmployeeSummary] = None
    employment_status: str
    date_of_joining: date
    date_of_confirmation: Optional[date] = None
    probation_end_date: Optional[date] = None
    resignation_date: Optional[date] = None
    last_working_date: Optional[date] = None
    date_of_exit: Optional[date] = None
    exit_reason: Optional[str] = None
    notice_period_days: int = 90
    profile_photo_url: Optional[str] = None
    professional_summary: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    direct_reports_count: int = 0

    @model_validator(mode="before")
    @classmethod
    def _build_display_name(cls, data: Any) -> Any:
        if hasattr(data, "__dict__"):
            if not getattr(data, "display_name", None):
                first = getattr(data, "first_name", "") or ""
                last = getattr(data, "last_name", "") or ""
                data.display_name = f"{first} {last}".strip()
        return data


# ═════════════════════════════════════════════════════════════════════
# Org chart
# ═════════════════════════════════════════════════════════════════════


class OrgChartNode(BaseModel):
    """Recursive node for org-chart tree rendering."""

    id: uuid.UUID
    employee_code: str
    display_name: str
    designation: Optional[str] = None
    department: Optional[str] = None
    profile_photo_url: Optional[str] = None
    children: list["OrgChartNode"] = Field(default_factory=list)


# Rebuild model to support recursive reference
OrgChartNode.model_rebuild()
