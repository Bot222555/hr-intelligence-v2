"""HR Intelligence — FastAPI Application Factory."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from backend.attendance.router import router as attendance_router
from backend.auth.router import router as auth_router
from backend.common.exceptions import register_exception_handlers
from backend.common.rate_limit import limiter
from backend.config import settings
from backend.dashboard.router import router as dashboard_router
from backend.core_hr.router import (
    departments_router,
    employees_router,
    locations_router,
)
from backend.expenses.router import router as expenses_router
from backend.fnf.router import router as fnf_router
from backend.helpdesk.router import router as helpdesk_router
from backend.leave.router import router as leave_router
from backend.notifications.router import router as notifications_router
from backend.salary.router import router as salary_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown events."""
    # Startup
    # TODO: Initialize database connection pool
    # TODO: Initialize Redis connection
    yield
    # Shutdown
    # TODO: Close database connection pool
    # TODO: Close Redis connection


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="HR Intelligence",
        description="Creativefuel Custom HR Platform — Phase 1: Core HR + Attendance + Leave",
        version="1.0.0",
        docs_url="/api/docs" if settings.ENVIRONMENT != "production" else None,
        redoc_url="/api/redoc" if settings.ENVIRONMENT != "production" else None,
        lifespan=lifespan,
    )

    # Exception handlers (RFC 7807)
    register_exception_handlers(app)

    # Rate limiting (slowapi)
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Health check (no auth)
    @app.get("/api/v1/health", tags=["system"])
    async def health_check():
        return {
            "status": "healthy",
            "version": "1.0.0",
            "environment": settings.ENVIRONMENT,
        }

    # Register routers
    app.include_router(auth_router, prefix="/api/v1/auth", tags=["auth"])
    app.include_router(employees_router, prefix="/api/v1/employees", tags=["employees"])
    app.include_router(departments_router, prefix="/api/v1/departments", tags=["departments"])
    app.include_router(locations_router, prefix="/api/v1/locations", tags=["locations"])
    app.include_router(attendance_router, prefix="/api/v1/attendance", tags=["attendance"])
    app.include_router(leave_router, prefix="/api/v1/leave", tags=["leave"])
    app.include_router(dashboard_router, prefix="/api/v1/dashboard", tags=["dashboard"])
    app.include_router(notifications_router, prefix="/api/v1/notifications", tags=["notifications"])
    app.include_router(salary_router, prefix="/api/v1/salary", tags=["salary"])
    app.include_router(helpdesk_router, prefix="/api/v1/helpdesk", tags=["helpdesk"])
    app.include_router(expenses_router, prefix="/api/v1/expenses", tags=["expenses"])
    app.include_router(fnf_router, prefix="/api/v1/fnf", tags=["fnf"])

    return app


app = create_app()
