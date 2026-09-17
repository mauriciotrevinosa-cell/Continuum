"""User controls for the Studio's Continue shelf.

Hide is presentation-only and preserves progress. Reset deliberately removes
saved progress for the matching series+medium (reading or watching). Both are
addressed by the opaque unit key already returned in the progress view; no
filesystem path crosses the API boundary.
"""

from __future__ import annotations

from typing import Annotated

from continuum_db.session import session_scope
from continuum_library.progress import hide_continue_group, reset_continue_group
from continuum_library.validation import CatalogInputError, CatalogNotFoundError
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

router = APIRouter(prefix="/catalog/progress", tags=["catalog"])
# unit_key_for() deliberately stores a truncated SHA-256: 40 lowercase hex chars.
_UNIT_KEY = r"^[0-9a-f]{40}$"
_PROJECT_KEY = r"^[a-z0-9][a-z0-9-]{0,79}$"


class ContinueActionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    unit_key: Annotated[str, Field(pattern=_UNIT_KEY)]
    project_key: Annotated[str | None, Field(pattern=_PROJECT_KEY)] = None


def _detail(exc: CatalogInputError | CatalogNotFoundError) -> dict[str, object]:
    return {
        "error": exc.code,
        "message": exc.user_message,
        "remediation": exc.remediation,
    }


@router.post("/hide")
def hide_continue(request: Request, body: ContinueActionIn) -> dict[str, object]:
    try:
        with session_scope(request.app.state.settings) as session:
            return hide_continue_group(
                session,
                unit_key=body.unit_key,
                project_key=body.project_key,
            )
    except CatalogNotFoundError as exc:
        raise HTTPException(status_code=404, detail=_detail(exc)) from None
    except CatalogInputError as exc:
        raise HTTPException(status_code=422, detail=_detail(exc)) from None


@router.post("/reset")
def reset_continue(request: Request, body: ContinueActionIn) -> dict[str, object]:
    try:
        with session_scope(request.app.state.settings) as session:
            return reset_continue_group(
                session,
                unit_key=body.unit_key,
                project_key=body.project_key,
            )
    except CatalogNotFoundError as exc:
        raise HTTPException(status_code=404, detail=_detail(exc)) from None
    except CatalogInputError as exc:
        raise HTTPException(status_code=422, detail=_detail(exc)) from None
