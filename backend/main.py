"""HR Intelligence — FastAPI Application Factory."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.auth.router import router as auth_router
from backend.common.exceptions import register_exception_handlers
from backend.config import settings
from backend.notifications.router import router as notifications_router


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
    # TODO: app.include_router(employees_router, prefix="/api/v1/employees", tags=["employees"])
    # TODO: app.include_router(departments_router, prefix="/api/v1/departments", tags=["departments"])
    # TODO: app.include_router(attendance_router, prefix="/api/v1/attendance", tags=["attendance"])
    # TODO: app.include_router(leave_router, prefix="/api/v1/leave", tags=["leave"])
    # TODO: app.include_router(dashboard_router, prefix="/api/v1/dashboard", tags=["dashboard"])
    app.include_router(notifications_router, prefix="/api/v1/notifications", tags=["notifications"])

    return app


app = create_app()
