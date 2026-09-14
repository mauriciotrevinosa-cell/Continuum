"""Chapter packages: one chapter's production plan, as a versioned, validated document.

A generic schema - nothing in it knows any project, season or story. A package
names the project and the chapter it belongs to, the characters present, its
scenes, pages and panels (with scene description, dialogue, required source
references and optional visual references), generation notes, the outputs
generated for it, provenance back to the project documents it was derived
from, and an approval state.

Packages are written by people (or by an assistant a person has green-lit);
Continuum validates structure and cross-references, stores each save as a new
version with a content hash, and never fills a package with story content of
its own. The JSON Schema in ``docs/schemas`` is generated from these models and
checked for drift by the test suite.
"""

from __future__ import annotations

import datetime as dt
import re
import uuid
from typing import Any, Literal

from continuum_core import canonical_json_hash
from continuum_core.catalog import ApprovalState
from continuum_db.models import ChapterPackage, MusicReference
from continuum_library import CatalogConflictError, CatalogInputError, CatalogNotFoundError
from continuum_library.validation import clean_text, clean_url, require_project_key
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

__all__ = [
    "PACKAGE_SCHEMA",
    "ChapterPackageBody",
    "ChapterPackages",
    "MusicReferences",
    "music_view",
    "package_json_schema",
    "package_view",
]

PACKAGE_SCHEMA = "continuum.chapter-package/1"
_PACKAGE_KEY = re.compile(r"^[a-z0-9][a-z0-9-]{0,119}$")
_ID = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$"


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class SourceRef(_Model):
    """A reference a panel needs, named by catalog ids or a content locator."""

    reference_id: uuid.UUID | None = None
    unit_id: uuid.UUID | None = None
    #: 1-based page within the unit, for a chapter.
    page: int | None = Field(default=None, ge=1)
    #: Milliseconds into the unit, for an episode.
    time_ms: int | None = Field(default=None, ge=0)
    locator: str | None = Field(default=None, max_length=2048)
    note: str = Field(default="", max_length=1000)

    @model_validator(mode="after")
    def _names_something(self) -> SourceRef:
        if not (self.reference_id or self.unit_id or self.locator):
            raise ValueError("a reference names a reference_id, a unit_id or a locator")
        if (self.page is not None or self.time_ms is not None) and self.unit_id is None:
            raise ValueError("page and time_ms belong to a unit_id")
        return self


class DialogueLine(_Model):
    speaker: str = Field(default="", max_length=120)
    kind: Literal["speech", "thought", "caption", "narration", "sfx"] = "speech"
    text: str = Field(max_length=2000)


class GeneratedOutput(_Model):
    artifact_id: uuid.UUID | None = None
    attempt_id: uuid.UUID | None = None
    content_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    note: str = Field(default="", max_length=1000)


class Panel(_Model):
    panel_id: str = Field(pattern=_ID)
    description: str = Field(default="", max_length=8000)
    characters_present: list[str] = Field(default_factory=list, max_length=40)
    dialogue: list[DialogueLine] = Field(default_factory=list, max_length=60)
    required_source_references: list[SourceRef] = Field(default_factory=list, max_length=40)
    optional_visual_references: list[SourceRef] = Field(default_factory=list, max_length=40)
    generation_notes: str = Field(default="", max_length=8000)
    generated_outputs: list[GeneratedOutput] = Field(default_factory=list, max_length=40)
    approval_state: ApprovalState = ApprovalState.DRAFT


class Page(_Model):
    page_id: str = Field(pattern=_ID)
    scene_id: str | None = Field(default=None, pattern=_ID)
    panels: list[Panel] = Field(default_factory=list, max_length=40)
    notes: str = Field(default="", max_length=4000)


class Scene(_Model):
    scene_id: str = Field(pattern=_ID)
    description: str = Field(default="", max_length=8000)
    characters_present: list[str] = Field(default_factory=list, max_length=40)


class CharacterEntry(_Model):
    #: How the package refers to the character (panels list these names).
    name: str = Field(min_length=1, max_length=120)
    character_id: uuid.UUID | None = None
    notes: str = Field(default="", max_length=2000)


class SourceDocument(_Model):
    document_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,79}$")
    version: str | None = Field(default=None, max_length=20)
    sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


class Provenance(_Model):
    source_documents: list[SourceDocument] = Field(default_factory=list, max_length=40)
    prepared_by: str = Field(default="", max_length=200)
    notes: str = Field(default="", max_length=4000)


class ChapterPackageBody(_Model):
    schema_: Literal["continuum.chapter-package/1"] = Field(
        default="continuum.chapter-package/1", alias="schema"
    )
    project: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,79}$")
    season: str | None = Field(default=None, max_length=40)
    episode: str | None = Field(default=None, max_length=40)
    chapter: str = Field(min_length=1, max_length=40)
    title: str = Field(default="", max_length=300)
    characters: list[CharacterEntry] = Field(default_factory=list, max_length=200)
    scenes: list[Scene] = Field(default_factory=list, max_length=200)
    pages: list[Page] = Field(default_factory=list, max_length=400)
    provenance: Provenance = Field(default_factory=Provenance)
    approval_state: ApprovalState = ApprovalState.DRAFT

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, populate_by_name=True)

    @model_validator(mode="after")
    def _cross_references(self) -> ChapterPackageBody:
        problems: list[str] = []
        names = [c.name for c in self.characters]
        if len(set(names)) != len(names):
            problems.append("character names repeat")
        known = set(names)
        scene_ids = [s.scene_id for s in self.scenes]
        if len(set(scene_ids)) != len(scene_ids):
            problems.append("scene ids repeat")
        page_ids = [p.page_id for p in self.pages]
        if len(set(page_ids)) != len(page_ids):
            problems.append("page ids repeat")
        for scene in self.scenes:
            for name in scene.characters_present:
                if name not in known:
                    problems.append(f"scene {scene.scene_id}: '{name}' is not in characters")
        for page in self.pages:
            if page.scene_id is not None and page.scene_id not in scene_ids:
                problems.append(f"page {page.page_id}: scene '{page.scene_id}' does not exist")
            panel_ids = [p.panel_id for p in page.panels]
            if len(set(panel_ids)) != len(panel_ids):
                problems.append(f"page {page.page_id}: panel ids repeat")
            for panel in page.panels:
                for name in panel.characters_present:
                    if name not in known:
                        problems.append(
                            f"panel {page.page_id}/{panel.panel_id}: '{name}' is not in characters"
                        )
                for line in panel.dialogue:
                    if (
                        line.kind in ("speech", "thought")
                        and line.speaker
                        and line.speaker not in known
                    ):
                        problems.append(
                            f"panel {page.page_id}/{panel.panel_id}: "
                            f"speaker '{line.speaker}' is not in characters"
                        )
        if problems:
            raise ValueError("; ".join(problems[:50]))
        return self


def package_json_schema() -> dict[str, Any]:
    """The JSON Schema of a chapter package, as published in ``docs/schemas``."""
    schema = ChapterPackageBody.model_json_schema(by_alias=True)
    schema["$id"] = "https://continuum.local/schemas/chapter-package.v1.schema.json"
    schema["title"] = "Continuum chapter package v1"
    return schema


def _problems(exc: ValidationError) -> list[dict[str, Any]]:
    return [
        {"where": "/".join(str(p) for p in error.get("loc", ())), "message": str(error.get("msg"))}
        for error in exc.errors()[:100]
    ]


def package_view(row: ChapterPackage, *, full: bool = True) -> dict[str, Any]:
    view: dict[str, Any] = {
        "id": str(row.id),
        "project_key": row.project_key,
        "package_key": row.package_key,
        "version": row.version,
        "schema_version": row.schema_version,
        "approval_state": row.approval_state.value,
        "body_hash": row.body_hash,
        "notes": row.notes,
        "row_version": row.row_version,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        "chapter": (row.body or {}).get("chapter"),
        "title": (row.body or {}).get("title"),
        "pages": len((row.body or {}).get("pages") or []),
    }
    if full:
        view["body"] = row.body
    return view


class ChapterPackages:
    def __init__(self, session: Session) -> None:
        self.session = session

    @staticmethod
    def validate(
        project_key: str, body: dict[str, Any]
    ) -> tuple[ChapterPackageBody | None, list[dict[str, Any]]]:
        require_project_key(project_key)
        try:
            parsed = ChapterPackageBody.model_validate(body)
        except ValidationError as exc:
            return None, _problems(exc)
        if parsed.project != project_key:
            return None, [{"where": "project", "message": "the package names another project"}]
        return parsed, []

    def save(
        self, project_key: str, package_key: str, body: dict[str, Any], *, notes: str = ""
    ) -> ChapterPackage:
        """Store a new version. Identical content returns the latest version unchanged."""
        if not _PACKAGE_KEY.match(package_key):
            raise CatalogInputError("A package key is lowercase letters, digits and dashes.")
        parsed, problems = self.validate(project_key, body)
        if parsed is None:
            raise CatalogInputError(
                "The chapter package is not valid: "
                + "; ".join(f"{p['where']}: {p['message']}" for p in problems[:5])
            )
        canonical = parsed.model_dump(mode="json", by_alias=True)
        digest = canonical_json_hash(canonical)
        latest = self.latest(project_key, package_key)
        if latest is not None and latest.body_hash == digest:
            return latest
        version = (latest.version + 1) if latest is not None else 1
        row = ChapterPackage(
            project_key=project_key,
            package_key=package_key,
            version=version,
            schema_version=PACKAGE_SCHEMA,
            approval_state=parsed.approval_state,
            body=canonical,
            body_hash=digest,
            notes=clean_text(notes, 4000, field="Notes"),
        )
        self.session.add(row)
        self.session.flush()
        return row

    def latest(self, project_key: str, package_key: str) -> ChapterPackage | None:
        return self.session.execute(
            select(ChapterPackage)
            .where(
                ChapterPackage.project_key == project_key, ChapterPackage.package_key == package_key
            )
            .order_by(ChapterPackage.version.desc())
            .limit(1)
        ).scalar_one_or_none()

    def versions(self, project_key: str, package_key: str) -> list[ChapterPackage]:
        rows = list(
            self.session.execute(
                select(ChapterPackage)
                .where(
                    ChapterPackage.project_key == project_key,
                    ChapterPackage.package_key == package_key,
                )
                .order_by(ChapterPackage.version.desc())
            ).scalars()
        )
        if not rows:
            raise CatalogNotFoundError("That chapter package does not exist.")
        return rows

    def for_project(self, project_key: str) -> list[ChapterPackage]:
        require_project_key(project_key)
        newest = (
            select(ChapterPackage.package_key, func.max(ChapterPackage.version).label("version"))
            .where(ChapterPackage.project_key == project_key)
            .group_by(ChapterPackage.package_key)
            .subquery()
        )
        return list(
            self.session.execute(
                select(ChapterPackage)
                .join(
                    newest,
                    (ChapterPackage.package_key == newest.c.package_key)
                    & (ChapterPackage.version == newest.c.version),
                )
                .where(ChapterPackage.project_key == project_key)
                .order_by(ChapterPackage.package_key)
            ).scalars()
        )

    def set_approval(
        self,
        project_key: str,
        package_key: str,
        version: int,
        state: ApprovalState,
        row_version: int,
    ) -> ChapterPackage:
        row = self.session.execute(
            select(ChapterPackage).where(
                ChapterPackage.project_key == project_key,
                ChapterPackage.package_key == package_key,
                ChapterPackage.version == version,
            )
        ).scalar_one_or_none()
        if row is None:
            raise CatalogNotFoundError("That chapter package version does not exist.")
        if row.row_version != row_version:
            raise CatalogConflictError("Someone changed this package; reload it.")
        row.approval_state = state
        try:
            self.session.flush()
        except StaleDataError:
            raise CatalogConflictError("Someone changed this package; reload it.") from None
        return row


class MusicReferences:
    """Playlist and music notes for a project: metadata only, never fetched or played."""

    FIELDS = {
        "track": 300,
        "artist": 300,
        "reference": 2000,
        "episode": 40,
        "scene": 200,
        "mood": 200,
        "intended_use": 200,
        "notes": 8000,
    }

    def __init__(self, session: Session) -> None:
        self.session = session

    def _clean(self, values: dict[str, Any]) -> dict[str, str]:
        out: dict[str, str] = {}
        for key, value in values.items():
            if key not in self.FIELDS:
                raise CatalogInputError(f"'{key}' is not a music reference field.")
            out[key] = clean_text(value, self.FIELDS[key], field=key)
        reference = out.get("reference", "")
        if reference.startswith(("http://", "https://")):
            out["reference"] = clean_url(reference) or ""
        return out

    def add(self, project_key: str, **values: Any) -> MusicReference:
        require_project_key(project_key)
        cleaned = self._clean(values)
        if not cleaned.get("track"):
            raise CatalogInputError("A music reference needs a track.")
        row = MusicReference(project_key=project_key, **cleaned)
        self.session.add(row)
        self.session.flush()
        return row

    def get(self, project_key: str, music_id: uuid.UUID) -> MusicReference:
        row = self.session.get(MusicReference, music_id)
        if row is None or row.project_key != project_key or row.removed_at is not None:
            raise CatalogNotFoundError("That music reference does not exist.")
        return row

    def list(self, project_key: str, *, episode: str | None = None) -> list[MusicReference]:
        require_project_key(project_key)
        query = select(MusicReference).where(
            MusicReference.project_key == project_key, MusicReference.removed_at.is_(None)
        )
        if episode:
            query = query.where(MusicReference.episode == episode)
        return list(
            self.session.execute(
                query.order_by(MusicReference.episode, MusicReference.track)
            ).scalars()
        )

    def update(
        self, project_key: str, music_id: uuid.UUID, row_version: int, **values: Any
    ) -> MusicReference:
        row = self.get(project_key, music_id)
        if row.row_version != row_version:
            raise CatalogConflictError("Someone changed this music reference; reload it.")
        for key, value in self._clean(values).items():
            setattr(row, key, value)
        if not row.track:
            raise CatalogInputError("A music reference needs a track.")
        try:
            self.session.flush()
        except StaleDataError:
            raise CatalogConflictError("Someone changed this music reference; reload it.") from None
        return row

    def remove(self, project_key: str, music_id: uuid.UUID, row_version: int) -> None:
        row = self.get(project_key, music_id)
        if row.row_version != row_version:
            raise CatalogConflictError("Someone changed this music reference; reload it.")
        row.removed_at = dt.datetime.now(dt.UTC)
        self.session.flush()


def music_view(row: MusicReference) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "project_key": row.project_key,
        "track": row.track,
        "artist": row.artist,
        "reference": row.reference,
        "episode": row.episode,
        "scene": row.scene,
        "mood": row.mood,
        "intended_use": row.intended_use,
        "notes": row.notes,
        "row_version": row.row_version,
    }
