"""Health and readiness (acceptance 110.2).

``/health`` answers "is this process alive and how is it configured" and
must work with the database down -- otherwise it cannot help diagnose a
database problem.

``/ready`` answers "can this process actually serve requests", which does
require the database.

Neither ever includes a credential. The database URL is absent from both in
every form (acceptance 110.13).
"""

from __future__ import annotations

from typing import Any

from continuum_db.session import database_is_reachable
from fastapi import APIRouter, Request, Response, status

from continuum_api.schemas import HealthResponse, ReadyResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health(request: Request) -> HealthResponse:
    """Liveness. Deliberately does not touch the database."""
    settings = request.app.state.settings
    storage = request.app.state.storage
    providers = request.app.state.providers

    from continuum_api.main import VERSION

    return HealthResponse(
        version=VERSION,
        api_host=settings.api_host,
        production_profile=settings.production_profile.value,
        storage=storage.summary(),
        providers=providers.summary(),
    )


@router.get("/ready", response_model=ReadyResponse)
def ready(request: Request, response: Response) -> ReadyResponse:
    """Readiness. 503 when a required dependency is down."""
    settings = request.app.state.settings
    storage = request.app.state.storage

    reachable, detail = database_is_reachable(settings)
    storage_healthy = storage.healthy
    is_ready = reachable and storage_healthy

    if not is_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    database: dict[str, Any] = {"reachable": reachable, "detail": detail}
    return ReadyResponse(
        ready=is_ready,
        database=database,
        storage_healthy=storage_healthy,
        detail=None if is_ready else "Start the database with: docker compose up -d db",
    )
