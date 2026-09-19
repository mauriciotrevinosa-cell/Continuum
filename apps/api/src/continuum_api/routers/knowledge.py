"""Visual Knowledge routes (M3): the external-resource registry.

A registry document is metadata only (ids, web URLs, license summaries); the
import validates it strictly and refuses anything that looks like a local path.
Decisions about a resource (access, license acceptance, allowed uses, intake
binding) are a person's and are recorded with optimistic concurrency.
"""

from __future__ import annotations

from typing import Annotated, Any

from continuum_core.knowledge import AccessState, KnowledgeUse
from continuum_library.resources import ExternalResources, resource_view
from fastapi import APIRouter, Request
from fastapi import Path as PathParam
from pydantic import BaseModel, ConfigDict, Field

from continuum_api.routers.library import StrictBody, catalog_scope

router = APIRouter(tags=["visual-knowledge"])

ResourceKey = Annotated[str, PathParam(pattern=r"^[a-z0-9][a-z0-9._-]{1,79}$")]


class RegistryEntryIn(BaseModel):
    """One registry entry. Extra fields are kept: the registry is metadata, and
    the service validates ids, web-only URLs and the absence of local paths."""

    model_config = ConfigDict(extra="allow")

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{1,79}$")
    urls: list[str] = Field(default_factory=list, max_length=20)


class RegistryIn(StrictBody):
    """A ``continuum.external-dataset-registry`` document, e.g. the committed
    ``docs/creative/visual_knowledge/dataset_registry_v0.1.json``."""

    model_config = ConfigDict(extra="allow")

    schema_: str = Field(alias="schema", max_length=80)
    entries: list[RegistryEntryIn] = Field(min_length=1, max_length=500)


class DecisionIn(StrictBody):
    row_version: int = Field(ge=1)
    access_state: AccessState | None = None
    accept_license: bool | None = None
    acceptance_note: str | None = Field(default=None, max_length=2000)
    allowed_uses: list[KnowledgeUse] | None = Field(default=None, max_length=5)
    intake_root_key: str | None = Field(default=None, pattern=r"^intake:[a-z0-9-]{1,57}$")
    clear_intake_root: bool = False
    notes: str | None = Field(default=None, max_length=8000)


def _intake_roots(request: Request) -> dict[str, str]:
    """Configured intake roots: key -> collection name. Never their paths."""
    settings = request.app.state.settings
    return {key: value[0] for key, value in settings.intake_root_map().items()}


def _listing(request: Request, resources: ExternalResources) -> dict[str, Any]:
    counts = resources.item_counts()
    return {
        "resources": [
            resource_view(row, counts.get(row.intake_root_key or "", 0)) for row in resources.all()
        ],
        "intake_roots": [
            {"key": key, "collection": collection}
            for key, collection in sorted(_intake_roots(request).items())
        ],
        "uses": [use.value for use in KnowledgeUse],
        "access_states": [state.value for state in AccessState],
    }


@router.get("/library/external-resources")
def list_resources(request: Request) -> dict[str, Any]:
    """Every registered dataset, annotation set, model and tool, with its decisions."""
    with catalog_scope(request) as catalog:
        return _listing(request, ExternalResources(catalog.session))


@router.post("/library/external-resources/import")
def import_resources(request: Request, body: RegistryIn) -> dict[str, Any]:
    """Import a registry document. Never grants a training use; never widens a decision."""
    document = body.model_dump(by_alias=True)
    with catalog_scope(request) as catalog:
        resources = ExternalResources(catalog.session)
        summary = resources.import_registry(document)
        return {"summary": summary.as_dict(), **_listing(request, resources)}


@router.post("/library/external-resources/{key}/decision")
def decide_resource(request: Request, key: ResourceKey, body: DecisionIn) -> dict[str, Any]:
    """Record a person's decision about one resource."""
    with catalog_scope(request) as catalog:
        resources = ExternalResources(catalog.session)
        row = resources.decide(
            key,
            body.row_version,
            access_state=body.access_state,
            accept_license=body.accept_license,
            acceptance_note=body.acceptance_note,
            allowed_uses=body.allowed_uses,
            intake_root_key=body.intake_root_key,
            clear_intake_root=body.clear_intake_root,
            notes=body.notes,
            known_intake_roots=frozenset(_intake_roots(request)),
        )
        catalog.session.flush()
        counts = resources.item_counts()
        return resource_view(row, counts.get(row.intake_root_key or "", 0))
