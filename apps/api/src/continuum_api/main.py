"""FastAPI application factory (ADR-0004 section 8, ADR-0006).

Two rules are enforced structurally here, not by convention:

* **Loopback only** (A-03). Phase 0 has no authentication, so a non-loopback
  bind is rejected by configuration validation before the server starts.
  There is deliberately no dormant "bind to LAN if auth exists" path,
  because auth does not exist yet and a dormant path is the thing someone
  enables later without the security decision that should accompany it.
* **No filesystem path parameters** (F-50). Every route addresses jobs and
  workers by id. A ``GET /files?path=...`` endpoint is a directory-traversal
  machine regardless of validation, and it will be proposed because it is
  convenient.

The API **enqueues and reads**. It never executes durable work: that is the
worker's job, in a separate OS process, coordinating only through PostgreSQL
(ADR-0002 section 12). There is no API-to-worker channel at all.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from continuum_config import Settings, get_settings
from continuum_observability import configure_logging, correlation_scope, get_logger
from continuum_providers import build_default_registry
from continuum_storage import build_storage
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse

from continuum_api.routers import health, jobs, workers

__all__ = ["create_app"]

log = get_logger("continuum.api")

VERSION = "0.1.0-phase0"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    configure_logging(settings.log_level)

    storage = build_storage(settings, create=True)
    app.state.storage = storage
    app.state.providers = build_default_registry()

    for warning in storage.sync_warnings:
        # Not fatal: the user may knowingly accept it. But the failure mode
        # (placeholder files that stat() as real, conflict-copy duplicates)
        # is very hard to diagnose from its symptoms, so it must be loud.
        log.warning("storage root is inside a cloud-sync folder", extra={"detail": warning.message})

    log.info(
        "api starting",
        extra={
            "host": settings.api_host,
            "port": settings.api_port,
            "profile": settings.production_profile.value,
            "vault_protection": storage.vault_protection.status.value,
        },
    )
    yield
    log.info("api stopping")


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or get_settings()

    app = FastAPI(
        title="Continuum API",
        version=VERSION,
        summary="Phase 0 foundation: health, durable jobs, workers.",
        lifespan=lifespan,
    )
    app.state.settings = resolved

    # Restricted to the configured web origin; never a wildcard.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[resolved.web_origin],
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["content-type", "x-correlation-id"],
    )

    @app.middleware("http")
    async def _correlate(request: Request, call_next):  # type: ignore[no-untyped-def]
        """Continue an inbound trace, or start one.

        The id is later copied onto the durable job row, because a ContextVar
        cannot cross the process boundary into the worker (F-71).
        """
        inbound = request.headers.get("x-correlation-id")
        with correlation_scope(inbound) as correlation_id:
            response = await call_next(request)
            response.headers["x-correlation-id"] = correlation_id
            return response

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        """Never leak internals to the client; the detail goes to the log."""
        log.exception("unhandled API error", extra={"path": request.url.path})
        return JSONResponse(
            status_code=500,
            content={"error": "internal_error", "message": "An internal error occurred."},
        )

    app.include_router(health.router)
    app.include_router(jobs.router)
    app.include_router(workers.router)
    return app
