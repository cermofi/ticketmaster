from __future__ import annotations

import logging
import time
import uuid
from threading import Event, Thread

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from ticketmaster.api.error_handlers import (
    http_exception_handler,
    ticketmaster_error_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from ticketmaster.api.routes import router
from ticketmaster.core.config import settings
from ticketmaster.core.database import SessionLocal
from ticketmaster.services import gitlab_delivery_tracking
from ticketmaster.services.errors import TicketMasterError


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("ticketmaster.api")
_gitlab_sync_stop_event: Event | None = None
_gitlab_sync_thread: Thread | None = None

app = FastAPI(
    title="TicketMaster API",
    version="0.1.0",
    openapi_url="/api/openapi.json",
    docs_url=None,
    redoc_url=None,
)

app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(settings.trusted_hosts))
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_context_middleware(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
    request.state.request_id = request_id
    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = round((time.perf_counter() - start) * 1000, 2)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    logger.info(
        "request method=%s path=%s status=%s duration_ms=%s request_id=%s client=%s",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
        request_id,
        request.client.host if request.client else "-",
    )
    return response


app.add_exception_handler(TicketMasterError, ticketmaster_error_handler)
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)

app.include_router(router, prefix="/api")


def _run_gitlab_delivery_tracking_loop(stop_event: Event) -> None:
    interval_seconds = max(settings.gitlab_sync_interval_seconds, 15)
    while not stop_event.is_set():
        try:
            with SessionLocal() as db:
                run = gitlab_delivery_tracking.sync_delivery_issues(db, triggered_by="scheduler")
                db.commit()
            logger.info(
                "gitlab delivery tracking sync status=%s total=%s resolved=%s missing=%s failed=%s",
                run.status,
                run.total_issues,
                run.resolved_targets,
                run.missing_targets,
                run.failed_targets,
            )
        except Exception:
            # Background sync must never take down API process.
            logger.exception("gitlab delivery tracking background sync failed")
        if stop_event.wait(interval_seconds):
            break


@app.on_event("startup")
def start_gitlab_delivery_tracking_worker() -> None:
    global _gitlab_sync_stop_event, _gitlab_sync_thread
    if not gitlab_delivery_tracking.sync_enabled():
        logger.info("gitlab delivery tracking sync worker disabled by configuration")
        return
    if _gitlab_sync_thread and _gitlab_sync_thread.is_alive():
        return
    _gitlab_sync_stop_event = Event()
    _gitlab_sync_thread = Thread(
        target=_run_gitlab_delivery_tracking_loop,
        args=(_gitlab_sync_stop_event,),
        name="gitlab-delivery-sync",
        daemon=True,
    )
    _gitlab_sync_thread.start()
    logger.info(
        "gitlab delivery tracking sync worker started interval_seconds=%s",
        settings.gitlab_sync_interval_seconds,
    )


@app.on_event("shutdown")
def stop_gitlab_delivery_tracking_worker() -> None:
    global _gitlab_sync_stop_event, _gitlab_sync_thread
    if _gitlab_sync_stop_event is not None:
        _gitlab_sync_stop_event.set()
    if _gitlab_sync_thread and _gitlab_sync_thread.is_alive():
        _gitlab_sync_thread.join(timeout=5)
    _gitlab_sync_stop_event = None
    _gitlab_sync_thread = None
