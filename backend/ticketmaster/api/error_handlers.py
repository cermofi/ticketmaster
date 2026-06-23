from __future__ import annotations

import logging

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from ticketmaster.core.config import settings
from ticketmaster.services.errors import TicketMasterError

logger = logging.getLogger("ticketmaster.api")


def _request_id(request: Request) -> str | None:
    return getattr(getattr(request, "state", None), "request_id", None)


def error_payload(
    *,
    code: str,
    message: str,
    request: Request,
    details: dict | list | None = None,
) -> dict:
    return {
        "code": code,
        "message": message,
        "details": details,
        "request_id": _request_id(request),
    }


def _http_status_code(code: int) -> str:
    mapping = {
        400: "bad_request",
        401: "unauthorized",
        403: "forbidden",
        404: "not_found",
        409: "conflict",
        422: "validation_error",
        429: "rate_limit_exceeded",
        503: "service_unavailable",
    }
    return mapping.get(code, "http_error")


def _normalize_http_detail(detail) -> tuple[str, dict | list | None]:
    if isinstance(detail, str):
        return detail, None
    if isinstance(detail, list):
        return "Request validation failed", detail
    if isinstance(detail, dict):
        message = str(detail.get("message") or detail.get("detail") or "Request failed")
        return message, detail
    return "Request failed", None


async def ticketmaster_error_handler(request: Request, exc: TicketMasterError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=error_payload(
            code=exc.code,
            message=exc.message,
            request=request,
            details=exc.details,
        ),
    )


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    message, details = _normalize_http_detail(exc.detail)
    return JSONResponse(
        status_code=exc.status_code,
        content=error_payload(
            code=_http_status_code(exc.status_code),
            message=message,
            request=request,
            details=details,
        ),
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content=error_payload(
            code="validation_error",
            message="Request validation failed",
            request=request,
            details=exc.errors(),
        ),
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    request_id = _request_id(request)
    logger.exception("Unhandled error request_id=%s path=%s", request_id, request.url.path)
    message = str(exc) if settings.app_debug else "Internal server error"
    details = {"type": exc.__class__.__name__} if settings.app_debug else None
    return JSONResponse(
        status_code=500,
        content=error_payload(
            code="internal_error",
            message=message,
            request=request,
            details=details,
        ),
    )
