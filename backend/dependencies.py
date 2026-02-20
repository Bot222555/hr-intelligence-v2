"""Shared FastAPI dependencies — re-exported from auth module."""

from backend.auth.dependencies import (  # noqa: F401
    get_current_user,
    require_permission,
    require_role,
)

__all__ = ["get_current_user", "require_role", "require_permission"]
