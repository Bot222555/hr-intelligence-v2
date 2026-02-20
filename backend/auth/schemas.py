"""Auth Pydantic schemas for request / response validation."""


import uuid
from typing import Optional

from pydantic import BaseModel, EmailStr


# ── Requests ────────────────────────────────────────────────────────

class GoogleAuthRequest(BaseModel):
    code: str
    redirect_uri: str


class RefreshRequest(BaseModel):
    refresh_token: str


# ── Embedded / Shared ──────────────────────────────────────────────

class UserInfo(BaseModel):
    id: uuid.UUID
    employee_number: str
    display_name: str
    email: str
    role: str
    profile_picture_url: Optional[str] = None
    department: str
    location: str


class DeptBrief(BaseModel):
    id: uuid.UUID
    name: str


class LocationBrief(BaseModel):
    id: uuid.UUID
    name: str


# ── Responses ───────────────────────────────────────────────────────

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserInfo


class RefreshResponse(BaseModel):
    access_token: str
    expires_in: int


class MeResponse(BaseModel):
    id: uuid.UUID
    employee_number: str
    display_name: str
    email: str
    role: str
    permissions: list[str]
    profile_picture_url: Optional[str] = None
    department: Optional[DeptBrief] = None
    location: Optional[LocationBrief] = None
    direct_reports_count: int
