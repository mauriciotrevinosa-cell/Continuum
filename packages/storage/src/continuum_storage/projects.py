"""Projects and their documents, discovered from declared sources.

A project is a directory holding a ``continuum.project.json`` manifest. The
manifest is the registry of what the project contains and - explicitly - what
state each document is in. Nothing here infers approval: a document is
APPROVED only because its manifest entry says so, and a Markdown file the
manifest does not list is UNFILED, never canon.

The product model this serves (``CONTINUUM_PRODUCT_PROJECT_MODEL_v0.2``):
Continuum is the studio, a project is data inside it. There is no project
name anywhere in this module, and an installation with no sources has no
projects - a valid, empty state.

Boundaries:

* Sources are directories from configuration, never from a request (F-50).
* Every document path in a manifest is resolved with :func:`resolve_within`
  against the project's own directory, so a manifest cannot reach a file
  outside its project - no traversal, no absolute path, no link escape.
* Reads only. Project artifacts will need writes later; those belong to the
  writable projects root, and never to the Source Vault (ADR-0001).
"""

from __future__ import annotations

import json
import os
import re
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path, PurePath
from typing import Any

from continuum_core import PathEscapesRootError

from continuum_storage.paths import resolve_within

__all__ = [
    "AUTHORITY",
    "LIFECYCLE",
    "MANIFEST_NAME",
    "MATURITY",
    "PROJECT_ID_PATTERN",
    "Project",
    "ProjectDocument",
    "ProjectLibrary",
]

MANIFEST_NAME = "continuum.project.json"
PROJECT_ID_PATTERN = r"^[a-z0-9][a-z0-9-]{0,79}$"
_ID = re.compile(PROJECT_ID_PATTERN)

#: Where a document stands. APPROVED and LOCKED are continuity; everything
#: before them is work in progress; SUPERSEDED and ARCHIVED are history.
LIFECYCLE: tuple[str, ...] = (
    "IDEA",
    "DRAFT",
    "REVIEW",
    "APPROVED",
    "LOCKED",
    "SUPERSEDED",
    "ARCHIVED",
)
#: A Markdown file matched by a manifest's ``discover`` patterns but not
#: registered: visible, never treated as decided.
UNFILED = "UNFILED"
#: How developed a document is, independent of whether it is approved: an
#: approved rough roadmap is not a production-ready panel script.
MATURITY: tuple[str, ...] = ("ROUGH", "DETAILED", "PRODUCTION_READY")
#: What kind of standing a document claims over others. ``RULE`` governs how
#: the project works, ``CORRECTION`` overrides named parts of other documents,
#: ``INDEX`` is the author's source-of-truth overview, ``CONTENT`` is the rest.
AUTHORITY: tuple[str, ...] = ("CONTENT", "RULE", "CORRECTION", "INDEX")
SECTIONS: tuple[str, ...] = ("story", "production", "reference", "extra")

MAX_DOCUMENT_BYTES = 4 * 1024 * 1024
MAX_MANIFEST_BYTES = 1024 * 1024
DOCUMENT_SUFFIXES = frozenset({".md", ".markdown"})
CACHE_SECONDS = 5.0

_H1 = re.compile(r"^#\s+(.+?)\s*$", re.M)
_FIELD = re.compile(r"^\*\*(Status|Date|Supersedes|Scope):\*\*\s*(.+?)\s*$", re.M | re.I)
_VERSION = re.compile(r"[_-]v(\d+(?:\.\d+)*)$", re.I)


@dataclass(frozen=True, slots=True)
class ProjectDocument:
    """One document of a project, described from its manifest entry."""

    id: str
    title: str
    category: str
    section: str
    lifecycle: str
    version: str | None
    lineage: str | None
    supersedes: str | None
    derived_from: str | None
    episode: str | None
    summary: str
    #: What the author wrote about the document's standing, verbatim. Shown
    #: to people; never used to decide ``lifecycle``.
    author_status: str | None
    dated: str | None
    modified_ns: int
    size_bytes: int
    filed: bool
    constraints: tuple[str, ...] = ()
    #: ROUGH, DETAILED or PRODUCTION_READY, when the manifest records it.
    maturity: str | None = None
    authority: str = "CONTENT"
    #: Partial precedence the documents state themselves: (document id, scope).
    #: Whole-document replacement stays ``supersedes``.
    overrides: tuple[tuple[str, str], ...] = ()
    relative: str = field(default="", repr=False)


@dataclass(frozen=True, slots=True)
class Project:
    id: str
    title: str
    kind: str
    logline: str
    description: str
    status: str
    documents: tuple[ProjectDocument, ...]
    pipeline: tuple[dict[str, Any], ...]
    warnings: tuple[str, ...]
    modified_ns: int
    root: Path = field(repr=False)


class ProjectLibrary:
    """Read-only discovery of projects under configured source directories."""

    def __init__(self, sources: Sequence[str]) -> None:
        self._sources = [s for s in sources if s]
        self._cache: tuple[float, dict[str, Project]] | None = None

    @property
    def sources(self) -> list[str]:
        return list(self._sources)

    def projects(self) -> list[Project]:
        now = time.monotonic()
        if self._cache is not None and now - self._cache[0] < CACHE_SECONDS:
            return list(self._cache[1].values())
        found: dict[str, Project] = {}
        for manifest in self._manifests():
            project = _load(manifest)
            if project is not None and project.id not in found:
                found[project.id] = project
        self._cache = (now, found)
        return list(found.values())

    def project(self, project_id: str) -> Project | None:
        if not _ID.match(project_id or ""):
            return None
        return next((p for p in self.projects() if p.id == project_id), None)

    def document(
        self, project_id: str, document_id: str
    ) -> tuple[Project, ProjectDocument, str] | None:
        project = self.project(project_id)
        if project is None or not _ID.match(document_id or ""):
            return None
        document = next((d for d in project.documents if d.id == document_id), None)
        if document is None:
            return None
        try:
            resolved = resolve_within(project.root, document.relative, root_key="project")
            with resolved.path.open("rb") as handle:
                raw = handle.read(MAX_DOCUMENT_BYTES + 1)
        except (PathEscapesRootError, OSError):
            return None
        if len(raw) > MAX_DOCUMENT_BYTES:
            return None
        return project, document, raw.decode("utf-8", errors="replace")

    def forget(self) -> None:
        self._cache = None

    def _manifests(self) -> list[Path]:
        out: list[Path] = []
        for source in self._sources:
            base = Path(source)
            if not base.is_dir():
                continue
            direct = base / MANIFEST_NAME
            if direct.is_file():
                out.append(direct)
            try:
                with os.scandir(base) as entries:
                    children = sorted(e.name for e in entries if e.is_dir(follow_symlinks=False))
            except OSError:
                continue
            for name in children:
                if name.startswith("."):
                    continue
                candidate = base / name / MANIFEST_NAME
                if candidate.is_file():
                    out.append(candidate)
        return out


# ---------------------------------------------------------------------------
def _text(value: Any, limit: int = 2000) -> str:
    return str(value).strip()[:limit] if isinstance(value, str) else ""


def _optional(value: Any, limit: int = 200) -> str | None:
    text = _text(value, limit)
    return text or None


def _slug(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug[:80] or "document"


def _peek(path: Path) -> dict[str, str]:
    """Title and the author's header fields from the start of a document."""
    try:
        with path.open("rb") as handle:
            head = handle.read(8192).decode("utf-8", errors="replace")
    except OSError:
        return {}
    out: dict[str, str] = {}
    title = _H1.search(head)
    if title:
        out["title"] = title.group(1).strip().strip("`")
    for match in _FIELD.finditer(head):
        out.setdefault(match.group(1).lower(), match.group(2).strip())
    return out


def _load(manifest: Path) -> Project | None:
    root = manifest.parent
    warnings: list[str] = []
    try:
        if manifest.stat().st_size > MAX_MANIFEST_BYTES:
            return None
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    project_id = _text(data.get("id"), 80)
    title = _text(data.get("title"), 200)
    if not _ID.match(project_id) or not title:
        return None

    documents: list[ProjectDocument] = []
    seen_ids: set[str] = set()
    seen_paths: set[str] = set()
    newest = manifest.stat().st_mtime_ns

    def add(entry: dict[str, Any], *, filed: bool) -> None:
        nonlocal newest
        relative = _text(entry.get("path"), 400)
        if not relative or PurePath(relative).suffix.lower() not in DOCUMENT_SUFFIXES:
            warnings.append(f"skipped an entry without a Markdown path: {relative or '(none)'}")
            return
        try:
            resolved = resolve_within(root, relative, root_key="project")
            info = resolved.path.stat()
        except PathEscapesRootError:
            warnings.append(f"skipped {relative}: it is not inside the project")
            return
        except OSError:
            warnings.append(f"{relative} is listed but not present")
            return
        key = str(resolved.relative).lower()
        if key in seen_paths:
            return
        document_id = _text(entry.get("id"), 80) or _slug(PurePath(relative).stem)
        if not _ID.match(document_id) or document_id in seen_ids:
            warnings.append(f"skipped {relative}: missing or duplicate id")
            return
        lifecycle = _text(entry.get("lifecycle"), 20).upper() if filed else UNFILED
        if filed and lifecycle not in LIFECYCLE:
            warnings.append(f"{document_id}: unknown lifecycle {lifecycle!r}, shown as unfiled")
            lifecycle = UNFILED
        section = _text(entry.get("section"), 20).lower() or ("story" if filed else "extra")
        if section not in SECTIONS:
            section = "extra"
        peek = _peek(resolved.path)
        version = _optional(entry.get("version"), 20)
        if version is None:
            match = _VERSION.search(PurePath(relative).stem)
            version = match.group(1) if match else None
        constraints = entry.get("constraints")
        maturity = _text(entry.get("maturity"), 20).upper() or None
        if maturity is not None and maturity not in MATURITY:
            warnings.append(f"{document_id}: unknown maturity {maturity!r}, ignored")
            maturity = None
        authority = _text(entry.get("authority"), 20).upper() or "CONTENT"
        if authority not in AUTHORITY:
            warnings.append(f"{document_id}: unknown authority {authority!r}, shown as content")
            authority = "CONTENT"
        overrides: list[tuple[str, str]] = []
        for item in entry.get("overrides") or []:
            if isinstance(item, dict) and _ID.match(_text(item.get("document"), 80)):
                overrides.append((_text(item.get("document"), 80), _text(item.get("scope"), 400)))
        documents.append(
            ProjectDocument(
                id=document_id,
                title=_text(entry.get("title"), 200)
                or peek.get("title")
                or PurePath(relative).stem,
                category=_text(entry.get("category"), 40).lower() or "document",
                section=section,
                lifecycle=lifecycle,
                version=version,
                lineage=_optional(entry.get("lineage"), 80),
                supersedes=_optional(entry.get("supersedes"), 80),
                derived_from=_optional(entry.get("derived_from"), 80),
                episode=_optional(entry.get("episode"), 40),
                summary=_text(entry.get("summary"), 600),
                author_status=peek.get("status"),
                dated=peek.get("date"),
                modified_ns=info.st_mtime_ns,
                size_bytes=info.st_size,
                filed=filed,
                constraints=tuple(_text(c, 300) for c in constraints if isinstance(c, str))
                if isinstance(constraints, list)
                else (),
                maturity=maturity if filed else None,
                authority=authority if filed else "CONTENT",
                overrides=tuple(overrides) if filed else (),
                relative=str(resolved.relative),
            )
        )
        seen_ids.add(document_id)
        seen_paths.add(key)
        newest = max(newest, info.st_mtime_ns)

    for entry in data.get("documents") or []:
        if isinstance(entry, dict):
            add(entry, filed=True)

    for pattern in data.get("discover") or []:
        if not isinstance(pattern, str) or "/" in pattern or "\\" in pattern or ".." in pattern:
            continue
        for path in sorted(root.glob(pattern)):
            if path.is_file() and path.name != MANIFEST_NAME:
                add({"path": path.name}, filed=False)

    pipeline = tuple(
        {
            "id": _text(stage.get("id"), 40),
            "title": _text(stage.get("title"), 80),
            "track": _text(stage.get("track"), 20).lower() or "story",
            "description": _text(stage.get("description"), 400),
        }
        for stage in (data.get("pipeline") or [])
        if isinstance(stage, dict) and _text(stage.get("id"), 40) and _text(stage.get("title"), 80)
    )
    return Project(
        id=project_id,
        title=title,
        kind=_text(data.get("kind"), 40).lower() or "original",
        logline=_text(data.get("logline"), 400),
        description=_text(data.get("description"), 4000),
        status=_text(data.get("status"), 40).lower() or "active",
        documents=tuple(documents),
        pipeline=pipeline,
        warnings=tuple(warnings),
        modified_ns=newest,
        root=root,
    )
