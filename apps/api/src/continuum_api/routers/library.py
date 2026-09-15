"""Reference vault routes: characters, outfits, visual modes, references, inbox.

Every route addresses records by id (F-50). Held media is referenced by its
opaque media id plus a unit (page index, PDF page, video instant); the server
resolves it read-only and records a content-derived locator. File intake takes
the raw request body with metadata in query parameters - no path, no filename
parameter, and bytes land only under the writable library root.

Links are stored, never fetched.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Annotated, Any

from continuum_core import ContinuumError, InvalidLocatorError, NormalizedRegion
from continuum_core.references import (
    AssetMedium,
    CandidateStatus,
    CharacterAspect,
    CharacterOrigin,
    DescriptorFacet,
    IntakeKind,
    ModeScope,
    ModeTrigger,
    OutfitKind,
    PanelSourceRole,
    ProjectStanding,
    ReferenceClass,
    ReferenceOrigin,
    ReferenceUse,
    SubjectKind,
    TechniqueFacet,
    VisualModeCategory,
)
from continuum_db.models import CatalogEntry, CatalogUnit, CharacterProfile
from continuum_db.session import session_scope
from continuum_imaging import UnsupportedImageError, preview
from continuum_library import (
    MAX_UPLOAD_IMAGE_BYTES,
    MAX_UPLOAD_VIDEO_BYTES,
    AcceptSpec,
    CandidateDefaults,
    CatalogConflictError,
    CatalogInputError,
    CatalogNotFoundError,
    CharacterLink,
    DescriptorSpec,
    FileIntake,
    PanelSourceSpec,
    ReferenceCatalog,
    ReferenceInbox,
    ReferenceSpec,
    StandingSpec,
    TechniqueLink,
    UrlEntry,
    candidate_view,
    character_summary,
    character_vault,
    reference_view,
    style_vault,
    visual_mode_view,
)
from continuum_production.character_models import CharacterModels
from continuum_storage import SourceChangedError, SourceUnavailableError
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi import Path as PathParam
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select
from starlette.responses import Response

router = APIRouter(tags=["library"])

ProjectId = Annotated[str, PathParam(pattern=r"^[a-z0-9][a-z0-9-]{0,79}$")]


# ---------------------------------------------------------------------------
# Plumbing
# ---------------------------------------------------------------------------
@contextmanager
def catalog_scope(request: Request) -> Iterator[ReferenceCatalog]:
    state = request.app.state
    with session_scope(state.settings) as session:
        try:
            yield ReferenceCatalog(session, sources=state.sources, derived=state.storage.derived)
        except CatalogNotFoundError as exc:
            session.rollback()
            raise HTTPException(status_code=404, detail=_detail(exc)) from None
        except (CatalogConflictError, SourceChangedError) as exc:
            session.rollback()
            raise HTTPException(status_code=409, detail=_detail(exc)) from None
        except SourceUnavailableError as exc:
            session.rollback()
            raise HTTPException(status_code=404, detail=_detail(exc)) from None
        except (CatalogInputError, InvalidLocatorError, UnsupportedImageError, ValueError) as exc:
            session.rollback()
            detail = _detail(exc) if isinstance(exc, ContinuumError) else {"message": str(exc)}
            raise HTTPException(status_code=422, detail=detail) from None


def _detail(exc: ContinuumError) -> dict[str, Any]:
    return {"error": exc.code, "message": exc.user_message, "remediation": exc.remediation}


async def _body(request: Request, limit: int) -> bytes:
    declared = request.headers.get("content-length")
    if declared is not None and declared.isdigit() and int(declared) > limit:
        raise HTTPException(
            status_code=413, detail={"message": f"At most {limit // (1024 * 1024)} MB."}
        )
    data = await request.body()
    if len(data) > limit:
        raise HTTPException(
            status_code=413, detail={"message": f"At most {limit // (1024 * 1024)} MB."}
        )
    if not data:
        raise HTTPException(status_code=422, detail={"message": "The request has no file content."})
    return data


async def _in_thread[T](func: Callable[[], T]) -> T:
    return await run_in_threadpool(func)


def _csv(value: str | None) -> list[str]:
    return [part.strip() for part in (value or "").split(",") if part.strip()]


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------
class StrictBody(BaseModel):
    """Request bodies name exactly their fields; anything else is refused."""

    model_config = ConfigDict(extra="forbid")


class RegionIn(StrictBody):
    x: float
    y: float
    width: float
    height: float

    def region(self) -> NormalizedRegion:
        return NormalizedRegion(self.x, self.y, self.width, self.height)


class CharacterLinkIn(StrictBody):
    character_id: uuid.UUID
    aspect: CharacterAspect
    outfit_id: uuid.UUID | None = None
    preferred: bool = False
    notes: str = ""


class TechniqueLinkIn(StrictBody):
    facet: TechniqueFacet
    visual_mode_id: uuid.UUID | None = None
    notes: str = ""


class DescriptorIn(StrictBody):
    facet: DescriptorFacet
    value: str


class StandingIn(StrictBody):
    project_key: str
    standing: ProjectStanding
    character_id: uuid.UUID | None = None
    notes: str = ""


class PanelSourceIn(StrictBody):
    project_key: str
    episode: str
    page: int
    role: PanelSourceRole
    chapter: int | None = None
    panel: int | None = None
    notes: str = ""


class ReferenceSpecIn(StrictBody):
    reference_class: ReferenceClass
    origin: ReferenceOrigin = ReferenceOrigin.SOURCE
    label: str = ""
    notes: str = ""
    favorite: bool = False
    region: RegionIn | None = None
    source_url: str | None = None
    creator_handle: str | None = None
    uses: list[ReferenceUse] = Field(default_factory=list)
    characters: list[CharacterLinkIn] = Field(default_factory=list)
    techniques: list[TechniqueLinkIn] = Field(default_factory=list)
    descriptors: list[DescriptorIn] = Field(default_factory=list)
    standings: list[StandingIn] = Field(default_factory=list)
    panel_sources: list[PanelSourceIn] = Field(default_factory=list)

    def spec(self) -> ReferenceSpec:
        return ReferenceSpec(
            reference_class=self.reference_class,
            origin=self.origin,
            label=self.label,
            notes=self.notes,
            favorite=self.favorite,
            region=self.region.region() if self.region else None,
            source_url=self.source_url,
            creator_handle=self.creator_handle,
            uses=tuple(self.uses),
            characters=tuple(CharacterLink(**c.model_dump()) for c in self.characters),
            techniques=tuple(TechniqueLink(**t.model_dump()) for t in self.techniques),
            descriptors=tuple(DescriptorSpec(**d.model_dump()) for d in self.descriptors),
            standings=tuple(StandingSpec(**s.model_dump()) for s in self.standings),
            panel_sources=tuple(PanelSourceSpec(**p.model_dump()) for p in self.panel_sources),
        )


class FromSourceIn(StrictBody):
    media_id: str = Field(pattern=r"^m1_[0-9a-f]{32}$")
    page_index: int | None = Field(default=None, ge=0, le=100_000)
    pdf_page: int | None = Field(default=None, ge=1, le=100_000)
    spec: ReferenceSpecIn


class VersionIn(StrictBody):
    row_version: int = Field(ge=1)


class ChangesIn(VersionIn):
    changes: dict[str, Any]


class CharacterIn(StrictBody):
    display_name: str
    subject_kind: SubjectKind = SubjectKind.CHARACTER
    #: SOURCE_WORK, or PROJECT_ORIGINAL with the project and its design documents.
    origin: CharacterOrigin = CharacterOrigin.SOURCE_WORK
    project_key: str | None = Field(default=None, pattern=r"^[a-z0-9][a-z0-9-]{0,79}$")
    design_documents: list[str] = Field(default_factory=list, max_length=20)
    source_label: str = ""
    summary: str = ""
    scale_notes: str = ""
    distinguishing_marks: str = ""
    posture_notes: str = ""
    notes: str = ""


class CharacterResolveIn(CharacterIn):
    snapshot: dict[str, Any] | None = None
    snapshot_project_key: str | None = Field(default=None, pattern=r"^[a-z0-9][a-z0-9-]{0,79}$")


class OutfitIn(StrictBody):
    name: str
    kind: OutfitKind = OutfitKind.SOURCE_DEFAULT
    project_key: str | None = None
    era: str = ""
    season_weather: str = ""
    condition: str = ""
    notes: str = ""


class VisualModeIn(StrictBody):
    name: str
    category: VisualModeCategory
    description: str = ""
    notes: str = ""


class AssignmentIn(StrictBody):
    visual_mode_id: uuid.UUID
    scope: ModeScope
    trigger: ModeTrigger = ModeTrigger.DIRECTORIAL
    episode: str | None = None
    scene: int | None = None
    page_from: int | None = None
    page_to: int | None = None
    panel: int | None = None
    event_label: str | None = None
    character_id: uuid.UUID | None = None
    notes: str = ""


class UsesIn(StrictBody):
    uses: list[ReferenceUse]


class PreferredIn(StrictBody):
    preferred: bool


class UrlEntryIn(StrictBody):
    url: str
    creator_handle: str | None = None
    notes: str = ""
    tags: list[str] = Field(default_factory=list)


class DefaultsIn(StrictBody):
    origin: ReferenceOrigin = ReferenceOrigin.FAN_ART
    suggested_class: ReferenceClass | None = None
    intended_uses: list[ReferenceUse] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    notes: str = ""

    def defaults(self) -> CandidateDefaults:
        return CandidateDefaults(
            origin=self.origin,
            suggested_class=self.suggested_class,
            intended_uses=tuple(self.intended_uses),
            tags=tuple(self.tags),
            notes=self.notes,
        )


class UrlBatchIn(StrictBody):
    label: str = ""
    entries: list[UrlEntryIn] = Field(max_length=500)
    defaults: DefaultsIn = Field(default_factory=DefaultsIn)

    @field_validator("entries")
    @classmethod
    def _not_empty(cls, value: list[UrlEntryIn]) -> list[UrlEntryIn]:
        if not value:
            raise ValueError("at least one link")
        return value


class BulkUpdateIn(StrictBody):
    ids: list[uuid.UUID] = Field(min_length=1, max_length=500)
    changes: dict[str, Any]


class AcceptIn(VersionIn):
    reference_class: ReferenceClass | None = None
    origin: ReferenceOrigin | None = None
    uses: list[ReferenceUse] | None = None
    label: str | None = None
    notes: str | None = None
    spec: ReferenceSpecIn | None = None

    def accept_spec(self) -> AcceptSpec:
        return AcceptSpec(
            reference_class=self.reference_class,
            origin=self.origin,
            uses=tuple(self.uses) if self.uses is not None else None,
            label=self.label,
            notes=self.notes,
            base=self.spec.spec() if self.spec else None,
        )


class BulkAcceptIn(StrictBody):
    ids: list[uuid.UUID] = Field(min_length=1, max_length=500)
    reference_class: ReferenceClass | None = None
    origin: ReferenceOrigin | None = None
    uses: list[ReferenceUse] | None = None
    spec: ReferenceSpecIn | None = None


# ---------------------------------------------------------------------------
# Characters and outfits
# ---------------------------------------------------------------------------
@router.get("/library/characters")
def list_characters(
    request: Request, subject_kind: SubjectKind | None = None
) -> list[dict[str, Any]]:
    with catalog_scope(request) as catalog:
        return [character_summary(c) for c in catalog.list_characters(subject_kind)]


@router.post("/library/characters", status_code=201)
def create_character(request: Request, body: CharacterIn) -> dict[str, Any]:
    with catalog_scope(request) as catalog:
        return character_summary(catalog.create_character(**body.model_dump()))


@router.get("/library/character-roster")
def character_roster(request: Request) -> dict[str, Any]:
    """Maintained from catalogued holdings and existing character profiles."""
    with catalog_scope(request) as catalog:
        held = catalog.session.execute(
            select(
                CatalogUnit.series_key,
                CatalogUnit.series_title,
                CatalogUnit.material_class,
                func.count(CatalogUnit.id),
            )
            .where(CatalogUnit.series_title.is_not(None))
            .group_by(CatalogUnit.series_key, CatalogUnit.series_title, CatalogUnit.material_class)
        ).all()
        profiles = catalog.list_characters()
        families: dict[str, dict[str, Any]] = {}
        for key, title, medium, count in held:
            family_key = str(title).strip().casefold()
            family = families.setdefault(
                family_key,
                {
                    "key": str(key or title),
                    "title": str(title),
                    "aliases": [],
                    "availability": {},
                    "characters": [],
                },
            )
            family["availability"][medium.value] = int(count)
        catalog_entries = catalog.session.execute(
            select(CatalogEntry.series_title, CatalogEntry.facts).where(
                CatalogEntry.series_title.is_not(None)
            )
        ).all()
        for title, facts in catalog_entries:
            found_family = families.get(str(title).strip().casefold())
            if found_family is None:
                continue
            aliases = (facts or {}).get("aliases") or []
            found_family["aliases"] = sorted(
                set(found_family["aliases"])
                | {str(alias) for alias in aliases if str(alias).strip()}
            )
        for character in profiles:
            label = character.source_label.strip()
            if not label:
                continue
            family_key = label.casefold()
            family = families.setdefault(
                family_key,
                {
                    "key": label,
                    "title": label,
                    "aliases": [],
                    "availability": {},
                    "characters": [],
                },
            )
            family["characters"].append(character_summary(character))
        rows = sorted(families.values(), key=lambda item: item["title"].casefold())
        return {"families": rows}


@router.post("/library/characters/resolve")
def resolve_character(request: Request, body: CharacterResolveIn) -> dict[str, Any]:
    """Reuse a matching profile or create one; optionally preserve an intake snapshot."""
    with catalog_scope(request) as catalog:
        values = body.model_dump(exclude={"snapshot", "snapshot_project_key"})
        existing = (
            catalog.session.execute(
                select(CharacterProfile)
                .where(
                    CharacterProfile.removed_at.is_(None),
                    func.lower(CharacterProfile.display_name) == body.display_name.strip().lower(),
                    func.lower(CharacterProfile.source_label) == body.source_label.strip().lower(),
                )
                .order_by(CharacterProfile.created_at)
            )
            .scalars()
            .first()
        )
        character = existing or catalog.create_character(**values)
        result = character_summary(character)
        result["reused"] = existing is not None
        result["snapshot"] = body.snapshot
        if body.snapshot and body.snapshot_project_key:
            models = CharacterModels(catalog.session)
            model = models.create(
                body.snapshot_project_key,
                character.id,
                name=f"{character.display_name} project snapshot",
                created_from={"kind": "intake_snapshot", "snapshot": body.snapshot},
            )
            result["production_model_id"] = str(model.id)
        return result


@router.get("/library/characters/{character_id}")
def get_character_vault(request: Request, character_id: uuid.UUID) -> dict[str, Any]:
    with catalog_scope(request) as catalog:
        return character_vault(catalog, character_id)


@router.post("/library/characters/{character_id}/update")
def update_character(request: Request, character_id: uuid.UUID, body: ChangesIn) -> dict[str, Any]:
    with catalog_scope(request) as catalog:
        return character_summary(
            catalog.update_character(character_id, body.row_version, **body.changes)
        )


@router.post("/library/characters/{character_id}/remove")
def remove_character(request: Request, character_id: uuid.UUID, body: VersionIn) -> dict[str, str]:
    with catalog_scope(request) as catalog:
        catalog.remove_character(character_id, body.row_version)
        return {"removed": str(character_id)}


@router.post("/library/characters/{character_id}/outfits", status_code=201)
def create_outfit(request: Request, character_id: uuid.UUID, body: OutfitIn) -> dict[str, Any]:
    with catalog_scope(request) as catalog:
        outfit = catalog.create_outfit(character_id, **body.model_dump())
        return {"id": str(outfit.id), "row_version": outfit.row_version, "name": outfit.name}


@router.post("/library/outfits/{outfit_id}/update")
def update_outfit(request: Request, outfit_id: uuid.UUID, body: ChangesIn) -> dict[str, Any]:
    with catalog_scope(request) as catalog:
        outfit = catalog.update_outfit(outfit_id, body.row_version, **body.changes)
        return {"id": str(outfit.id), "row_version": outfit.row_version, "name": outfit.name}


@router.post("/library/outfits/{outfit_id}/remove")
def remove_outfit(request: Request, outfit_id: uuid.UUID, body: VersionIn) -> dict[str, str]:
    with catalog_scope(request) as catalog:
        catalog.remove_outfit(outfit_id, body.row_version)
        return {"removed": str(outfit_id)}


# ---------------------------------------------------------------------------
# Visual modes (Style Vault) and project scopes
# ---------------------------------------------------------------------------
@router.get("/library/visual-modes")
def get_style_vault(request: Request) -> dict[str, Any]:
    with catalog_scope(request) as catalog:
        return style_vault(catalog)


@router.post("/library/visual-modes", status_code=201)
def create_visual_mode(request: Request, body: VisualModeIn) -> dict[str, Any]:
    with catalog_scope(request) as catalog:
        return visual_mode_view(catalog.create_visual_mode(**body.model_dump()))


@router.post("/library/visual-modes/{visual_mode_id}/update")
def update_visual_mode(
    request: Request, visual_mode_id: uuid.UUID, body: ChangesIn
) -> dict[str, Any]:
    with catalog_scope(request) as catalog:
        return visual_mode_view(
            catalog.update_visual_mode(visual_mode_id, body.row_version, **body.changes)
        )


@router.post("/library/visual-modes/{visual_mode_id}/remove")
def remove_visual_mode(
    request: Request, visual_mode_id: uuid.UUID, body: VersionIn
) -> dict[str, str]:
    with catalog_scope(request) as catalog:
        catalog.remove_visual_mode(visual_mode_id, body.row_version)
        return {"removed": str(visual_mode_id)}


def _assignment(a: Any) -> dict[str, Any]:
    return {
        "id": str(a.id),
        "project_key": a.project_key,
        "visual_mode_id": str(a.visual_mode_id),
        "scope": a.scope.value,
        "trigger": a.trigger.value,
        "episode": a.episode,
        "scene": a.scene,
        "page_from": a.page_from,
        "page_to": a.page_to,
        "panel": a.panel,
        "event_label": a.event_label,
        "character_id": str(a.character_id) if a.character_id else None,
        "notes": a.notes,
    }


@router.get("/projects/{project_id}/visual-modes")
def list_assignments(
    request: Request, project_id: ProjectId, episode: str | None = None
) -> list[dict[str, Any]]:
    with catalog_scope(request) as catalog:
        return [_assignment(a) for a in catalog.assignments(project_id, episode=episode)]


@router.post("/projects/{project_id}/visual-modes", status_code=201)
def assign_visual_mode(
    request: Request, project_id: ProjectId, body: AssignmentIn
) -> dict[str, Any]:
    with catalog_scope(request) as catalog:
        return _assignment(catalog.assign_visual_mode(project_id, **body.model_dump()))


@router.post("/projects/{project_id}/visual-modes/{assignment_id}/remove")
def remove_assignment(
    request: Request, project_id: ProjectId, assignment_id: uuid.UUID
) -> dict[str, str]:
    with catalog_scope(request) as catalog:
        catalog.remove_assignment(assignment_id)
        return {"removed": str(assignment_id)}


@router.get("/projects/{project_id}/panel-sources")
def list_panel_sources(
    request: Request,
    project_id: ProjectId,
    episode: str | None = None,
    page: Annotated[int | None, Query(ge=1)] = None,
) -> list[dict[str, Any]]:
    with catalog_scope(request) as catalog:
        rows = catalog.panel_sources(project_id, episode=episode, page=page)
        return [
            {
                "id": str(r.id),
                "episode": r.episode,
                "chapter": r.chapter,
                "page": r.page,
                "panel": r.panel,
                "role": r.role.value,
                "notes": r.notes,
                "reference": reference_view(
                    catalog, catalog.reference(r.reference_id), with_source=False
                ),
            }
            for r in rows
        ]


# ---------------------------------------------------------------------------
# References
# ---------------------------------------------------------------------------
@router.get("/library/references")
def list_references(
    request: Request,
    character_id: uuid.UUID | None = None,
    aspect: CharacterAspect | None = None,
    outfit_id: uuid.UUID | None = None,
    visual_mode_id: uuid.UUID | None = None,
    facet: TechniqueFacet | None = None,
    use: ReferenceUse | None = None,
    reference_class: ReferenceClass | None = None,
    origin: ReferenceOrigin | None = None,
    project_key: str | None = None,
    standing: ProjectStanding | None = None,
    content_hash: Annotated[str | None, Query(pattern=r"^[0-9a-f]{64}$")] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[dict[str, Any]]:
    with catalog_scope(request) as catalog:
        items = catalog.list_references(
            character_id=character_id,
            aspect=aspect,
            outfit_id=outfit_id,
            visual_mode_id=visual_mode_id,
            facet=facet,
            use=use,
            reference_class=reference_class,
            origin=origin,
            project_key=project_key,
            standing=standing,
            locator_hash=content_hash,
            limit=limit,
            offset=offset,
        )
        return [reference_view(catalog, item, with_source=False) for item in items]


@router.post("/library/references/from-source", status_code=201)
def add_reference_from_source(request: Request, body: FromSourceIn) -> dict[str, Any]:
    with catalog_scope(request) as catalog:
        item = catalog.add_from_source(
            body.media_id, body.spec.spec(), page_index=body.page_index, pdf_page=body.pdf_page
        )
        return reference_view(catalog, item)


@router.get("/library/references/{reference_id}")
def get_reference(request: Request, reference_id: uuid.UUID) -> dict[str, Any]:
    with catalog_scope(request) as catalog:
        return reference_view(catalog, catalog.reference(reference_id, include_removed=True))


@router.get("/library/references/{reference_id}/image")
def reference_image(request: Request, reference_id: uuid.UUID, crop: bool = True) -> Response:
    with catalog_scope(request) as catalog:
        image = catalog.reference_image(reference_id, crop=crop)
    return Response(
        content=image.data,
        media_type=image.mime,
        headers={"Cache-Control": "private, max-age=600", "X-Content-Type-Options": "nosniff"},
    )


@router.post("/library/references/{reference_id}/update")
def update_reference(request: Request, reference_id: uuid.UUID, body: ChangesIn) -> dict[str, Any]:
    with catalog_scope(request) as catalog:
        item = catalog.update_reference(reference_id, body.row_version, **body.changes)
        return reference_view(catalog, item, with_source=False)


@router.post("/library/references/{reference_id}/remove")
def remove_reference(request: Request, reference_id: uuid.UUID, body: VersionIn) -> dict[str, str]:
    with catalog_scope(request) as catalog:
        catalog.remove_reference(reference_id, body.row_version)
        return {"removed": str(reference_id)}


@router.post("/library/references/{reference_id}/uses")
def set_uses(request: Request, reference_id: uuid.UUID, body: UsesIn) -> dict[str, Any]:
    with catalog_scope(request) as catalog:
        return {"uses": [u.use.value for u in catalog.set_uses(reference_id, body.uses)]}


@router.post("/library/references/{reference_id}/characters", status_code=201)
def link_character(
    request: Request, reference_id: uuid.UUID, body: CharacterLinkIn
) -> dict[str, Any]:
    with catalog_scope(request) as catalog:
        link = catalog.link_character(reference_id, CharacterLink(**body.model_dump()))
        return {"link_id": str(link.id), "preferred": link.preferred}


@router.post("/library/reference-characters/{link_id}/preferred")
def set_preferred(request: Request, link_id: uuid.UUID, body: PreferredIn) -> dict[str, Any]:
    with catalog_scope(request) as catalog:
        link = catalog.set_preferred(link_id, body.preferred)
        return {"link_id": str(link.id), "preferred": link.preferred}


@router.post("/library/reference-characters/{link_id}/remove")
def unlink_character(request: Request, link_id: uuid.UUID) -> dict[str, str]:
    with catalog_scope(request) as catalog:
        catalog.unlink_character(link_id)
        return {"removed": str(link_id)}


@router.post("/library/references/{reference_id}/techniques", status_code=201)
def link_technique(
    request: Request, reference_id: uuid.UUID, body: TechniqueLinkIn
) -> dict[str, Any]:
    with catalog_scope(request) as catalog:
        link = catalog.link_technique(reference_id, TechniqueLink(**body.model_dump()))
        return {"link_id": str(link.id)}


@router.post("/library/reference-techniques/{link_id}/remove")
def unlink_technique(request: Request, link_id: uuid.UUID) -> dict[str, str]:
    with catalog_scope(request) as catalog:
        catalog.unlink_technique(link_id)
        return {"removed": str(link_id)}


@router.post("/library/references/{reference_id}/descriptors", status_code=201)
def add_descriptor(request: Request, reference_id: uuid.UUID, body: DescriptorIn) -> dict[str, Any]:
    """User tags only. Analysis descriptors are written by analyzers, not this route."""
    with catalog_scope(request) as catalog:
        row = catalog.add_descriptor(reference_id, DescriptorSpec(**body.model_dump()))
        return {"id": str(row.id), "origin": row.origin.value}


@router.post("/library/reference-descriptors/{descriptor_id}/remove")
def remove_descriptor(request: Request, descriptor_id: uuid.UUID) -> dict[str, str]:
    with catalog_scope(request) as catalog:
        catalog.remove_descriptor(descriptor_id)
        return {"removed": str(descriptor_id)}


@router.post("/library/references/{reference_id}/standings", status_code=201)
def set_standing(request: Request, reference_id: uuid.UUID, body: StandingIn) -> dict[str, Any]:
    with catalog_scope(request) as catalog:
        row = catalog.set_standing(reference_id, StandingSpec(**body.model_dump()))
        return {"id": str(row.id), "standing": row.standing.value}


@router.post("/library/reference-standings/{standing_id}/remove")
def remove_standing(request: Request, standing_id: uuid.UUID) -> dict[str, str]:
    with catalog_scope(request) as catalog:
        catalog.remove_standing(standing_id)
        return {"removed": str(standing_id)}


@router.post("/library/references/{reference_id}/panel-sources", status_code=201)
def add_panel_source(
    request: Request, reference_id: uuid.UUID, body: PanelSourceIn
) -> dict[str, Any]:
    with catalog_scope(request) as catalog:
        row = catalog.add_panel_source(reference_id, PanelSourceSpec(**body.model_dump()))
        return {"id": str(row.id), "role": row.role.value}


@router.post("/library/panel-sources/{panel_source_id}/remove")
def remove_panel_source(request: Request, panel_source_id: uuid.UUID) -> dict[str, str]:
    with catalog_scope(request) as catalog:
        catalog.remove_panel_source(panel_source_id)
        return {"removed": str(panel_source_id)}


# ---------------------------------------------------------------------------
# Reference Inbox
# ---------------------------------------------------------------------------
def _defaults_from_query(
    origin: ReferenceOrigin,
    suggested_class: ReferenceClass | None,
    uses: str | None,
    tags: str | None,
    notes: str,
) -> CandidateDefaults:
    return CandidateDefaults(
        origin=origin,
        suggested_class=suggested_class,
        intended_uses=tuple(ReferenceUse(u) for u in _csv(uses)),
        tags=tuple(_csv(tags)),
        notes=notes,
    )


@router.get("/library/inbox")
def get_inbox(
    request: Request,
    status: CandidateStatus | None = CandidateStatus.INBOX,
    batch_id: uuid.UUID | None = None,
    kind: IntakeKind | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, Any]:
    with catalog_scope(request) as catalog:
        inbox = ReferenceInbox(catalog)
        return {
            "candidates": [
                candidate_view(c)
                for c in inbox.candidates(
                    status=status, batch_id=batch_id, kind=kind, limit=limit, offset=offset
                )
            ],
            "batches": [
                {
                    "id": str(batch.id),
                    "kind": batch.kind.value,
                    "label": batch.label,
                    "created_at": batch.created_at.isoformat(),
                    "counts": counts,
                }
                for batch, counts in inbox.batches()
            ],
        }


@router.post("/library/inbox/urls", status_code=201)
def add_urls(request: Request, body: UrlBatchIn) -> dict[str, Any]:
    with catalog_scope(request) as catalog:
        result = ReferenceInbox(catalog).add_urls(
            [UrlEntry(e.url, e.creator_handle, e.notes, tuple(e.tags)) for e in body.entries],
            label=body.label,
            defaults=body.defaults.defaults(),
        )
        return {
            "batch_id": str(result.batch.id),
            "created": [candidate_view(c) for c in result.created],
            "skipped": result.skipped,
        }


@router.post("/library/inbox/batches", status_code=201)
def create_batch(request: Request, kind: IntakeKind, label: str = "") -> dict[str, Any]:
    with catalog_scope(request) as catalog:
        batch = ReferenceInbox(catalog).create_batch(kind, label=label)
        return {"id": str(batch.id), "kind": batch.kind.value, "label": batch.label}


def _intake_view(result: FileIntake, response: Response) -> dict[str, Any]:
    """201 with the new candidate, or 200 naming what already holds these bytes."""
    response.status_code = 200 if result.duplicate else 201
    return {
        "candidate": candidate_view(result.candidate) if result.candidate else None,
        "duplicate": result.duplicate,
        "duplicate_of": candidate_view(result.duplicate_of) if result.duplicate_of else None,
        "duplicate_reference_id": (
            str(result.duplicate_reference_id) if result.duplicate_reference_id else None
        ),
    }


@router.post("/library/inbox/files", status_code=201)
async def add_file(
    request: Request,
    response: Response,
    kind: IntakeKind,
    batch_id: uuid.UUID | None = None,
    label: Annotated[str, Query(max_length=300)] = "",
    source_url: str | None = None,
    creator_handle: str | None = None,
    origin: ReferenceOrigin = ReferenceOrigin.FAN_ART,
    suggested_class: ReferenceClass | None = None,
    uses: str | None = None,
    tags: str | None = None,
    notes: str = "",
) -> dict[str, Any]:
    """One image, clip or screenshot. ``kind`` is a hint: the bytes decide what it
    is, installers and documents are refused, exact duplicates are named."""
    # The largest allowance; the library applies the per-kind limit by content.
    data = await _body(request, MAX_UPLOAD_VIDEO_BYTES)

    def work() -> dict[str, Any]:
        with catalog_scope(request) as catalog:
            result = ReferenceInbox(catalog).add_file(
                data,
                kind,
                batch_id=batch_id,
                display_name=label,
                source_url=source_url,
                creator_handle=creator_handle,
                defaults=_defaults_from_query(origin, suggested_class, uses, tags, notes),
            )
            return _intake_view(result, response)

    return await _in_thread(work)


@router.post("/library/inbox/frames", status_code=201)
async def add_held_frame(
    request: Request,
    response: Response,
    time_ms: Annotated[int, Query(ge=0, le=86_400_000)],
    media_id: Annotated[str | None, Query(pattern=r"^m1_[0-9a-f]{32}$")] = None,
    member_id: uuid.UUID | None = None,
    batch_id: uuid.UUID | None = None,
    origin: ReferenceOrigin = ReferenceOrigin.SOURCE,
    suggested_class: ReferenceClass | None = None,
    uses: str | None = None,
    tags: str | None = None,
    notes: str = "",
) -> dict[str, Any]:
    """A frame the viewer captured from held video, or from a video inside an archive."""
    if (media_id is None) == (member_id is None):
        raise HTTPException(
            status_code=422, detail={"message": "Name a video or an archived video."}
        )
    data = await _body(request, MAX_UPLOAD_IMAGE_BYTES)

    def work() -> dict[str, Any]:
        with catalog_scope(request) as catalog:
            defaults = _defaults_from_query(origin, suggested_class, uses, tags, notes)
            inbox = ReferenceInbox(catalog)
            if member_id is not None:
                result = inbox.add_member_frame(
                    member_id, time_ms, data, batch_id=batch_id, defaults=defaults
                )
            else:
                result = inbox.add_held_frame(
                    str(media_id), time_ms, data, batch_id=batch_id, defaults=defaults
                )
            return _intake_view(result, response)

    return await _in_thread(work)


@router.get("/library/inbox/candidates/{candidate_id}")
def get_candidate(request: Request, candidate_id: uuid.UUID) -> dict[str, Any]:
    with catalog_scope(request) as catalog:
        return candidate_view(ReferenceInbox(catalog).candidate(candidate_id))


@router.get("/library/inbox/candidates/{candidate_id}/content")
def candidate_content(request: Request, candidate_id: uuid.UUID) -> Response:
    """An image candidate as a bounded preview; a clip as its own bytes."""
    with catalog_scope(request) as catalog:
        inbox = ReferenceInbox(catalog)
        data, medium = inbox.candidate_bytes(inbox.candidate(candidate_id))
    headers = {"Cache-Control": "private, max-age=600", "X-Content-Type-Options": "nosniff"}
    if medium is AssetMedium.VIDEO:
        mime = "video/webm" if data[:4] == b"\x1a\x45\xdf\xa3" else "video/mp4"
        return Response(content=data, media_type=mime, headers=headers)
    image = preview(data)
    return Response(content=image.data, media_type=image.mime, headers=headers)


@router.post("/library/inbox/candidates/{candidate_id}/clip-frame", status_code=201)
async def add_clip_frame(
    request: Request,
    response: Response,
    candidate_id: uuid.UUID,
    time_ms: Annotated[int, Query(ge=0, le=86_400_000)],
) -> dict[str, Any]:
    data = await _body(request, MAX_UPLOAD_IMAGE_BYTES)

    def work() -> dict[str, Any]:
        with catalog_scope(request) as catalog:
            result = ReferenceInbox(catalog).add_clip_frame(candidate_id, time_ms, data)
            return _intake_view(result, response)

    return await _in_thread(work)


@router.post("/library/inbox/candidates/{candidate_id}/attach")
async def attach_image(
    request: Request, candidate_id: uuid.UUID, row_version: Annotated[int, Query(ge=1)]
) -> dict[str, Any]:
    data = await _body(request, MAX_UPLOAD_IMAGE_BYTES)

    def work() -> dict[str, Any]:
        with catalog_scope(request) as catalog:
            return candidate_view(
                ReferenceInbox(catalog).attach_image(candidate_id, row_version, data)
            )

    return await _in_thread(work)


@router.post("/library/inbox/candidates/{candidate_id}/update")
def update_candidate(request: Request, candidate_id: uuid.UUID, body: ChangesIn) -> dict[str, Any]:
    with catalog_scope(request) as catalog:
        return candidate_view(
            ReferenceInbox(catalog).update(candidate_id, body.row_version, **body.changes)
        )


@router.post("/library/inbox/bulk-update")
def bulk_update(request: Request, body: BulkUpdateIn) -> dict[str, int]:
    with catalog_scope(request) as catalog:
        return {"updated": ReferenceInbox(catalog).bulk_update(body.ids, **body.changes)}


@router.post("/library/inbox/candidates/{candidate_id}/dismiss")
def dismiss_candidate(request: Request, candidate_id: uuid.UUID, body: VersionIn) -> dict[str, Any]:
    with catalog_scope(request) as catalog:
        return candidate_view(ReferenceInbox(catalog).dismiss(candidate_id, body.row_version))


@router.post("/library/inbox/candidates/{candidate_id}/restore")
def restore_candidate(request: Request, candidate_id: uuid.UUID, body: VersionIn) -> dict[str, Any]:
    with catalog_scope(request) as catalog:
        return candidate_view(ReferenceInbox(catalog).restore(candidate_id, body.row_version))


@router.post("/library/inbox/candidates/{candidate_id}/accept", status_code=201)
def accept_candidate(request: Request, candidate_id: uuid.UUID, body: AcceptIn) -> dict[str, Any]:
    with catalog_scope(request) as catalog:
        item = ReferenceInbox(catalog).accept(candidate_id, body.row_version, body.accept_spec())
        return reference_view(catalog, item)


@router.post("/library/inbox/bulk-accept")
def bulk_accept(request: Request, body: BulkAcceptIn) -> dict[str, Any]:
    with catalog_scope(request) as catalog:
        accepted, skipped = ReferenceInbox(catalog).bulk_accept(
            body.ids,
            AcceptSpec(
                reference_class=body.reference_class,
                origin=body.origin,
                uses=tuple(body.uses) if body.uses is not None else None,
                base=body.spec.spec() if body.spec else None,
            ),
        )
        return {
            "accepted": [reference_view(catalog, item, with_source=False) for item in accepted],
            "skipped": skipped,
        }
