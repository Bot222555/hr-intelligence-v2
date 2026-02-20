"""Custom exceptions and RFC 7807 Problem Detail error handlers."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

BASE_ERROR_URI = "https://hr.cfai.in/errors"


# ── Exception hierarchy ─────────────────────────────────────────────

class AppException(Exception):
    """Base for all application exceptions → RFC 7807 JSON."""

    def __init__(
        self,
        status_code: int,
        error_type: str,
        title: str,
        detail: str,
        errors: Optional[dict[str, Any]] = None,
    ) -> None:
        self.status_code = status_code
        self.error_type = error_type
        self.title = title
        self.detail = detail
        self.errors = errors
        super().__init__(detail)


class NotFoundException(AppException):
    """404 — entity not found."""

    def __init__(self, entity_type: str, entity_id: Any) -> None:
        super().__init__(
            status_code=404,
            error_type="not-found",
            title=f"{entity_type} Not Found",
            detail=f"{entity_type} with id '{entity_id}' does not exist.",
        )


class ConflictError(AppException):
    """409 — unique-constraint / duplicate."""

    def __init__(self, field: str, value: Any) -> None:
        super().__init__(
            status_code=409,
            error_type="conflict",
            title="Conflict",
            detail=f"An entry with {field}='{value}' already exists.",
            errors={field: [f"'{value}' is already in use."]},
        )


# Keep the alias used elsewhere in the codebase
DuplicateException = ConflictError


class ForbiddenException(AppException):
    """403 — insufficient permissions."""

    def __init__(
        self,
        detail: str = "You do not have permission to perform this action.",
    ) -> None:
        super().__init__(
            status_code=403,
            error_type="forbidden",
            title="Forbidden",
            detail=detail,
        )


class ValidationException(AppException):
    """422 — business-logic validation failures."""

    def __init__(self, errors: dict[str, list[str]]) -> None:
        super().__init__(
            status_code=422,
            error_type="validation-error",
            title="Validation Error",
            detail="One or more fields failed validation.",
            errors=errors,
        )


# ── RFC 7807 builder ────────────────────────────────────────────────

def _build_problem_detail(exc: AppException, request: Request) -> dict[str, Any]:
    body: dict[str, Any] = {
        "type": f"{BASE_ERROR_URI}/{exc.error_type}",
        "title": exc.title,
        "status": exc.status_code,
        "detail": exc.detail,
        "instance": str(request.url.path),
    }
    if exc.errors:
        body["errors"] = exc.errors
    return body


# ── FastAPI handlers ────────────────────────────────────────────────

async def _handle_app_exception(
    request: Request,
    exc: AppException,
) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=_build_problem_detail(exc, request),
        media_type="application/problem+json",
    )


async def _handle_validation_error(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    field_errors: dict[str, list[str]] = {}
    for err in exc.errors():
        loc = err.get("loc", ())
        name = (
            ".".join(str(p) for p in loc[1:])
            if len(loc) > 1
            else str(loc[0]) if loc else "unknown"
        )
        field_errors.setdefault(name, []).append(err.get("msg", "Invalid value"))

    return JSONResponse(
        status_code=422,
        content={
            "type": f"{BASE_ERROR_URI}/validation-error",
            "title": "Validation Error",
            "status": 422,
            "detail": "Request validation failed.",
            "instance": str(request.url.path),
            "errors": field_errors,
        },
        media_type="application/problem+json",
    )


# ── Registration helper (called from main.py) ──────────────────────

def register_exception_handlers(app: FastAPI) -> None:
    """Attach all custom exception handlers to the FastAPI app."""
    app.add_exception_handler(AppException, _handle_app_exception)          # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, _handle_validation_error)  # type: ignore[arg-type]
