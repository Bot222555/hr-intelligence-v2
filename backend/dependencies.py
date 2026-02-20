"""Shared FastAPI dependencies."""

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db


async def get_current_user(request: Request, db: AsyncSession = Depends(get_db)):
    """Extract and validate the current user from JWT token.
    
    TODO: Implement after auth module is built.
    """
    raise NotImplementedError("Auth module not yet implemented")


async def require_role(*roles: str):
    """Factory for role-based access control dependency.
    
    Usage: Depends(require_role("hr_admin", "system_admin"))
    
    TODO: Implement after auth module is built.
    """
    raise NotImplementedError("Auth module not yet implemented")
