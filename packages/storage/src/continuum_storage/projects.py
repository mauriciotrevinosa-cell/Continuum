"""Projects and their documents, discovered from declared sources.

A project is a directory holding a ``continuum.project.json`` manifest. The
manifest is the registry of what the project contains and - explicitly - what
state each document is in. Nothing here infers approval on its own: a
document's lifecycle comes from its manifest entry, or from a rule the
manifest itself declares, and a Markdown file no entry or rule covers is
UNFILED, never canon.

Two kinds of source:

* a **directory** on disk (the historical form); and
* a **Git ref** (``git:<repository>@<ref>[:<directory>]``): the project is
  read from the tree at the commit the ref points to, without a checkout, and
  every document says which commit last changed it. When a branch is the
  project's source of truth, this is how Continuum shows exactly what is
  committed there.

What a manifest may declare (all optional, all project data - no project
name appears anywhere in this module):

* ``documents`` - explicit entries, as before;
* ``conventions`` - rules that register files by name: a regular expression
  whose named groups (``episode``, ``version``...) fill in the entry, so a new
  episode's panel script is indexed the moment it is committed, without a
  hand-edited registry becoming a second source of truth;
* ``status_lifecycle`` - how the author's own ``**Status:**`` line maps to a
  lifecycle for convention-registered documents, first match wins;
* ``facts`` - small values read from each document's head (page totals,
  titles);
* ``supersedes_header`` - honour a document's own ``**Supersedes:**`` line:
  the named file is shown as superseded by it;
* ``episodes`` - the readiness levels an episode can reach and which
  document categories each level requires, named page counts (a panel
  script's own total, a later overlay's table), and the ordered production
  sources a chapter package is built from; the board is computed from the
  documents, never stored.

Boundaries:

* Sources are configuration, never a request (F-50).
* Directory documents are resolved with :func:`resolve_within`; Git documents
  are looked up by name in the committed tree. Either way a manifest cannot
  reach a file outside its project.
* Reads only. The one exception is :meth:`ProjectLibrary.resync`, which asks
  Git to update a remote-tracking ref.
"""

from __future__ import annotations

import fnmatch
import json
import os
import re
import threading
import time
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path, PurePosixPath
from typing import Any, Protocol

from continuum_core import PathEscapesRootError

from continuum_storage.git_tree import (
    GitCommit,
    GitFile,
    GitSourceError,
    GitSpec,
    GitTree,
    normal_name,
)
from continuum_storage.paths import resolve_within

__all__ = [
    "AUTHORITY",
    "LIFECYCLE",
    "MANIFEST_NAME",
    "MATURITY",
    "PROJECT_ID_PATTERN",
    "EpisodeStanding",
    "Project",
    "ProjectDocument",
    "ProjectLibrary",
    "ResyncResult",
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
CONTINUITY = frozenset({"APPROVED", "LOCKED"})
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
MAX_RULES = 200
MAX_PATTERN = 400
HEAD_BYTES = 16384
DOCUMENT_SUFFIXES = frozenset({".md", ".markdown"})
CACHE_SECONDS = 5.0

_H1 = re.compile(r"^#\s+(.+?)\s*$", re.M)
_FIELD = re.compile(r"^\*\*(Status|Date|Supersedes|Scope):\*\*\s*(.+?)\s*$", re.M | re.I)
_VERSION = re.compile(r"[_-]v(\d+(?:\.\d+)*)$", re.I)
_TEMPLATE = re.compile(r"\{([a-z_][a-z0-9_]*)\}")


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
    #: to people; only a rule the manifest declares turns it into a lifecycle.
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
    #: ``explicit`` (a manifest entry), ``convention`` (a manifest rule) or
    #: ``unfiled``.
    registration: str = "explicit"
    convention: str | None = None
    #: Values read from the document's head by the manifest's ``facts``.
    facts: tuple[tuple[str, str], ...] = ()
    #: The commit that last changed the document, for Git sources.
    commit: str | None = None
    #: A work-in-progress document the episode has since moved past (for
    #: example a voice-check revision once the episode's GREEN LIGHT exists).
    resolved_by: str | None = None
    #: What a document applies to beyond one episode: ``season:<n>`` or ``project``.
    applies_to: str | None = None
    relative: str = field(default="", repr=False)

    def fact(self, name: str) -> str | None:
        return next((value for key, value in self.facts if key == name), None)


@dataclass(frozen=True, slots=True)
class EpisodeStanding:
    """Where one episode stands, computed from its committed documents."""

    code: str
    season: int | None
    number: int | None
    title: str | None
    #: The highest declared level whose required categories are all
    #: continuity, or None.
    level: str | None
    label: str
    state: str | None
    pages: int | None
    #: (category, document id), in the manifest's category order.
    documents: tuple[tuple[str, str], ...]
    #: Categories the next level up still needs.
    missing: tuple[str, ...]
    last_commit: str | None
    last_changed_ns: int
    #: Named page counts: (count id, label, pages, document id). ``pages`` above
    #: is the one the manifest declares current, when the episode has it.
    page_counts: tuple[tuple[str, str, int, str], ...] = ()
    current_count: str | None = None
    #: Ordered production sources: (role, document id, required, when).
    sources: tuple[tuple[str, str, bool, str], ...] = ()
    #: Required source roles no approved document fills.
    missing_sources: tuple[str, ...] = ()


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
    root: _Root = field(repr=False)
    #: ``{"kind": "directory"}`` or the Git ref and commit it was read at.
    source: dict[str, Any] = field(default_factory=dict)
    episodes: tuple[EpisodeStanding, ...] = ()
    #: The manifest's declared levels, highest first: id, label, requires, state.
    levels: tuple[dict[str, Any], ...] = ()
    #: One row per declared page count: id, label, pages, episodes, current.
    page_totals: tuple[dict[str, Any], ...] = ()
    #: The declared production source roles, in order.
    source_roles: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True, slots=True)
class ResyncResult:
    project_id: str
    fetched: bool
    previous_commit: str | None
    commit: str | None
    detail: str


# ---------------------------------------------------------------------------
# Where a project's files come from
# ---------------------------------------------------------------------------
class _Root(Protocol):
    def manifest(self) -> tuple[bytes, int] | None: ...

    def stat(self, relative: str) -> tuple[int, int, str | None] | None:
        """(size, modified ns, commit) or None; raises PathEscapesRootError."""
        ...

    def read(self, relative: str, limit: int) -> bytes | None: ...

    def glob(self, pattern: str) -> list[str]: ...

    def origin(self) -> dict[str, Any]: ...


class _DirectoryRoot:
    def __init__(self, path: Path) -> None:
        self.path = path

    def manifest(self) -> tuple[bytes, int] | None:
        target = self.path / MANIFEST_NAME
        try:
            info = target.stat()
            if info.st_size > MAX_MANIFEST_BYTES:
                return None
            return target.read_bytes(), info.st_mtime_ns
        except OSError:
            return None

    def stat(self, relative: str) -> tuple[int, int, str | None] | None:
        resolved = resolve_within(self.path, relative, root_key="project")
        try:
            info = resolved.path.stat()
        except OSError:
            return None
        return info.st_size, info.st_mtime_ns, None

    def read(self, relative: str, limit: int) -> bytes | None:
        try:
            resolved = resolve_within(self.path, relative, root_key="project")
            with resolved.path.open("rb") as handle:
                return handle.read(limit + 1)
        except (PathEscapesRootError, OSError):
            return None

    def glob(self, pattern: str) -> list[str]:
        return sorted(
            path.name
            for path in self.path.glob(pattern)
            if path.is_file() and path.name != MANIFEST_NAME
        )

    def origin(self) -> dict[str, Any]:
        return {"kind": "directory"}


class _GitRoot:
    """One project directory inside a committed tree, read at one commit."""

    def __init__(
        self,
        tree: GitTree,
        commit: GitCommit,
        files: dict[str, GitFile],
        base: str,
        changes: dict[str, GitCommit],
    ) -> None:
        self.tree = tree
        self.commit = commit
        self.base = base
        prefix = f"{base}/" if base else ""
        self.files = {
            name[len(prefix) :]: entry for name, entry in files.items() if name.startswith(prefix)
        }
        self.changes = {
            name[len(prefix) :]: change
            for name, change in changes.items()
            if name.startswith(prefix)
        }
        self._blobs: dict[str, bytes] = {}
        self._lock = threading.Lock()

    def preload(self) -> None:
        """Read every Markdown blob (and the manifest) in one git call."""
        wanted = [
            entry.oid
            for name, entry in self.files.items()
            if PurePosixPath(name).suffix.lower() in DOCUMENT_SUFFIXES or name == MANIFEST_NAME
        ]
        with self._lock:
            self._blobs.update(self.tree.read(wanted, limit=MAX_DOCUMENT_BYTES))

    def _bytes(self, name: str, limit: int) -> bytes | None:
        entry = self.files.get(name)
        if entry is None:
            return None
        with self._lock:
            blob = self._blobs.get(entry.oid)
        if blob is None:
            blob = self.tree.read([entry.oid], limit=MAX_DOCUMENT_BYTES).get(entry.oid)
            if blob is None:
                return None
            with self._lock:
                self._blobs[entry.oid] = blob
        return blob[: limit + 1]

    def manifest(self) -> tuple[bytes, int] | None:
        entry = self.files.get(MANIFEST_NAME)
        if entry is None or entry.size > MAX_MANIFEST_BYTES:
            return None
        data = self._bytes(MANIFEST_NAME, MAX_MANIFEST_BYTES)
        if data is None:
            return None
        change = self.changes.get(MANIFEST_NAME)
        return data, change.committed_ns if change else self.commit.committed_ns

    def stat(self, relative: str) -> tuple[int, int, str | None] | None:
        name = normal_name(relative)
        if name is None:
            raise PathEscapesRootError(
                "A manifest path must stay inside its project.",
                technical_detail=f"relative={relative!r}",
            )
        entry = self.files.get(name)
        if entry is None:
            return None
        change = self.changes.get(name)
        if change is None:
            return entry.size, self.commit.committed_ns, self.commit.short
        return entry.size, change.committed_ns, change.short

    def read(self, relative: str, limit: int) -> bytes | None:
        name = normal_name(relative)
        return None if name is None else self._bytes(name, limit)

    def glob(self, pattern: str) -> list[str]:
        return sorted(
            name
            for name in self.files
            if "/" not in name and name != MANIFEST_NAME and fnmatch.fnmatch(name, pattern)
        )

    def origin(self) -> dict[str, Any]:
        return {
            "kind": "git",
            "ref": self.tree.spec.ref,
            "directory": "/".join(p for p in (self.tree.spec.subdir, self.base) if p),
            "commit": self.commit.sha,
            "committed_ns": self.commit.committed_ns,
            "subject": self.commit.subject,
        }


class _GitSource:
    """A configured ``git:`` source, re-read only when its commit changes."""

    def __init__(self, spec: GitSpec) -> None:
        self.tree = GitTree(spec)
        self._loaded: tuple[str, list[_GitRoot]] | None = None

    def roots(self) -> tuple[list[_GitRoot], str | None]:
        """The project roots at the ref's current commit, and any error."""
        try:
            commit = self.tree.commit()
            if self._loaded is not None and self._loaded[0] == commit.sha:
                return self._loaded[1], None
            files = self.tree.files(commit.sha)
            changes = self.tree.last_changes(commit.sha)
        except GitSourceError as exc:
            cached = self._loaded[1] if self._loaded is not None else []
            return cached, str(exc)
        bases = []
        if MANIFEST_NAME in files:
            bases.append("")
        bases += sorted(
            name.rsplit("/", 1)[0]
            for name in files
            if name.count("/") == 1
            and name.endswith(f"/{MANIFEST_NAME}")
            and not name.startswith(".")
        )
        roots = [_GitRoot(self.tree, commit, files, base, changes) for base in bases]
        try:
            for root in roots:
                root.preload()
        except GitSourceError as exc:
            cached = self._loaded[1] if self._loaded is not None else []
            return cached, str(exc)
        self._loaded = (commit.sha, roots)
        return roots, None

    def commit(self) -> str | None:
        return self._loaded[0] if self._loaded is not None else None


# ---------------------------------------------------------------------------
class ProjectLibrary:
    """Discovery of projects under configured sources (directories or Git refs)."""

    def __init__(self, sources: Sequence[str]) -> None:
        self._sources = [s for s in sources if s]
        self._git: dict[str, _GitSource] = {}
        self._source_errors: list[str] = []
        for source in self._sources:
            try:
                spec = GitSpec.parse(source)
            except GitSourceError as exc:
                self._source_errors.append(str(exc))
                continue
            if spec is not None:
                self._git[source] = _GitSource(spec)
        self._cache: tuple[float, dict[str, Project]] | None = None
        self._lock = threading.RLock()

    @property
    def sources(self) -> list[str]:
        return list(self._sources)

    def projects(self) -> list[Project]:
        with self._lock:
            now = time.monotonic()
            if self._cache is not None and now - self._cache[0] < CACHE_SECONDS:
                return list(self._cache[1].values())
            found: dict[str, Project] = {}
            for root, notes in self._roots():
                project = _load(root, notes)
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
        raw = project.root.read(document.relative, MAX_DOCUMENT_BYTES)
        if raw is None or len(raw) > MAX_DOCUMENT_BYTES:
            return None
        return project, document, raw.decode("utf-8", errors="replace")

    def forget(self) -> None:
        with self._lock:
            self._cache = None

    def resync(self, project_id: str) -> ResyncResult | None:
        """Fetch a Git project's ref from its remote, then re-read the project.

        A directory project is simply re-read. Returns None for an unknown
        project. A failed fetch is reported, and the project is re-read from
        whatever the ref points to locally.
        """
        project = self.project(project_id)
        if project is None:
            return None
        previous = project.source.get("commit")
        fetched = False
        detail = "re-read from disk"
        if isinstance(project.root, _GitRoot):
            tree = project.root.tree
            try:
                fetched = tree.fetch()
                detail = (
                    f"fetched {tree.spec.ref}"
                    if fetched
                    else f"{tree.spec.ref} is a local ref; update it with git yourself"
                )
            except GitSourceError as exc:
                detail = f"could not fetch: {exc}"
        self.forget()
        current = self.project(project_id)
        return ResyncResult(
            project_id=project_id,
            fetched=fetched,
            previous_commit=previous,
            commit=current.source.get("commit") if current else None,
            detail=detail,
        )

    def _roots(self) -> list[tuple[_Root, list[str]]]:
        out: list[tuple[_Root, list[str]]] = []
        for source in self._sources:
            git = self._git.get(source)
            if git is not None:
                roots, error = git.roots()
                notes = [f"Git source {git.tree.spec.label}: {error}"] if error else []
                out.extend((root, list(notes)) for root in roots)
                continue
            if source.startswith("git:"):
                continue
            base = Path(source)
            if not base.is_dir():
                continue
            if (base / MANIFEST_NAME).is_file():
                out.append((_DirectoryRoot(base), []))
            try:
                with os.scandir(base) as entries:
                    children = sorted(e.name for e in entries if e.is_dir(follow_symlinks=False))
            except OSError:
                continue
            for name in children:
                if not name.startswith(".") and (base / name / MANIFEST_NAME).is_file():
                    out.append((_DirectoryRoot(base / name), []))
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


def _peek(root: _Root, relative: str) -> tuple[dict[str, str], str]:
    """Title and the author's header fields from the start of a document, and the head."""
    raw = root.read(relative, HEAD_BYTES)
    if raw is None:
        return {}, ""
    head = raw[:HEAD_BYTES].decode("utf-8", errors="replace")
    out: dict[str, str] = {}
    title = _H1.search(head)
    if title:
        out["title"] = title.group(1).strip().strip("`")
    for match in _FIELD.finditer(head):
        out.setdefault(match.group(1).lower(), match.group(2).strip())
    return out, head


def _compile(pattern: Any, flags: int, warnings: list[str], where: str) -> re.Pattern[str] | None:
    if not isinstance(pattern, str) or not pattern or len(pattern) > MAX_PATTERN:
        warnings.append(f"{where}: missing or overlong pattern, ignored")
        return None
    try:
        return re.compile(pattern, flags)
    except re.error as exc:
        warnings.append(f"{where}: invalid pattern ({exc}), ignored")
        return None


def _fill(template: str, groups: dict[str, str]) -> str:
    return _TEMPLATE.sub(lambda m: groups.get(m.group(1), ""), template)


@dataclass(frozen=True, slots=True)
class _Convention:
    id: str
    pattern: re.Pattern[str]
    entry: dict[str, Any]


def _conventions(data: dict[str, Any], warnings: list[str]) -> list[_Convention]:
    out: list[_Convention] = []
    for index, raw in enumerate((data.get("conventions") or [])[:MAX_RULES]):
        if not isinstance(raw, dict):
            continue
        rule_id = _text(raw.get("id"), 80) or f"convention-{index + 1}"
        pattern = _compile(raw.get("match"), 0, warnings, f"convention {rule_id}")
        if pattern is not None:
            out.append(_Convention(rule_id, pattern, raw))
    return out


def _status_rules(data: dict[str, Any], warnings: list[str]) -> list[tuple[re.Pattern[str], str]]:
    rules: list[tuple[re.Pattern[str], str]] = []
    for index, raw in enumerate((data.get("status_lifecycle") or [])[:MAX_RULES]):
        if not isinstance(raw, dict):
            continue
        lifecycle = _text(raw.get("lifecycle"), 20).upper()
        where = f"status_lifecycle rule {index + 1}"
        if lifecycle not in LIFECYCLE:
            warnings.append(f"{where}: unknown lifecycle {lifecycle!r}, ignored")
            continue
        pattern = _compile(raw.get("match"), re.I, warnings, where)
        if pattern is not None:
            rules.append((pattern, lifecycle))
    return rules


def _fact_rules(
    data: dict[str, Any], warnings: list[str]
) -> list[tuple[str, list[re.Pattern[str]]]]:
    out: list[tuple[str, list[re.Pattern[str]]]] = []
    facts = data.get("facts")
    if not isinstance(facts, dict):
        return out
    for name, patterns in list(facts.items())[:50]:
        if not re.fullmatch(r"[a-z_][a-z0-9_]{0,40}", str(name)):
            continue
        items = patterns if isinstance(patterns, list) else [patterns]
        compiled = [
            p
            for p in (_compile(item, re.M, warnings, f"fact {name}") for item in items[:10])
            if p is not None
        ]
        if compiled:
            out.append((str(name), compiled))
    return out


def _load(root: _Root, notes: list[str]) -> Project | None:
    warnings: list[str] = list(notes)
    found = root.manifest()
    if found is None:
        return None
    raw_manifest, manifest_ns = found
    try:
        data = json.loads(raw_manifest.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    project_id = _text(data.get("id"), 80)
    title = _text(data.get("title"), 200)
    if not _ID.match(project_id) or not title:
        return None

    conventions = _conventions(data, warnings)
    status_rules = _status_rules(data, warnings)
    fact_rules = _fact_rules(data, warnings)
    documents: list[ProjectDocument] = []
    seen_ids: set[str] = set()
    seen_paths: set[str] = set()
    newest = manifest_ns
    declared_supersedes: dict[str, str] = {}

    def add(entry: dict[str, Any], *, registration: str, convention: str | None = None) -> None:
        nonlocal newest
        filed = registration != "unfiled"
        relative = _text(entry.get("path"), 400)
        if not relative or PurePosixPath(relative).suffix.lower() not in DOCUMENT_SUFFIXES:
            warnings.append(f"skipped an entry without a Markdown path: {relative or '(none)'}")
            return
        try:
            info = root.stat(relative)
        except PathEscapesRootError:
            warnings.append(f"skipped {relative}: it is not inside the project")
            return
        if info is None:
            warnings.append(f"{relative} is listed but not present")
            return
        size, modified_ns, commit = info
        key = relative.replace("\\", "/").lower()
        if key in seen_paths:
            return
        document_id = _text(entry.get("id"), 80) or _slug(PurePosixPath(relative).stem)
        if not _ID.match(document_id) or document_id in seen_ids:
            warnings.append(f"skipped {relative}: missing or duplicate id")
            return
        peek, head = _peek(root, relative)
        lifecycle = UNFILED
        if registration == "explicit":
            lifecycle = _text(entry.get("lifecycle"), 20).upper()
            if lifecycle not in LIFECYCLE:
                warnings.append(f"{document_id}: unknown lifecycle {lifecycle!r}, shown as unfiled")
                lifecycle = UNFILED
        elif registration == "convention":
            status = peek.get("status") or ""
            lifecycle = (
                next(
                    (life for pattern, life in status_rules if status and pattern.search(status)),
                    "",
                )
                or _text(entry.get("lifecycle"), 20).upper()
            )
            if lifecycle not in LIFECYCLE:
                lifecycle = "REVIEW"
        section = _text(entry.get("section"), 20).lower() or ("story" if filed else "extra")
        if section not in SECTIONS:
            section = "extra"
        version = _optional(entry.get("version"), 20)
        if version is None:
            match = _VERSION.search(PurePosixPath(relative).stem)
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
        facts: list[tuple[str, str]] = []
        for name, patterns in fact_rules:
            for pattern in patterns:
                hit = pattern.search(head)
                if hit:
                    value = (hit.group(1) if hit.groups() else hit.group(0)).strip().strip('`“”"')
                    if value:
                        facts.append((name, value[:200]))
                    break
        documents.append(
            ProjectDocument(
                id=document_id,
                title=_text(entry.get("title"), 200)
                or peek.get("title")
                or PurePosixPath(relative).stem,
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
                modified_ns=modified_ns,
                size_bytes=size,
                filed=filed,
                constraints=tuple(_text(c, 300) for c in constraints if isinstance(c, str))
                if isinstance(constraints, list)
                else (),
                maturity=maturity if filed else None,
                authority=authority if filed else "CONTENT",
                overrides=tuple(overrides) if filed else (),
                registration=registration,
                convention=convention,
                facts=tuple(facts),
                commit=commit,
                applies_to=_optional(entry.get("applies_to"), 40),
                relative=relative.replace("\\", "/"),
            )
        )
        if registration == "convention" and peek.get("supersedes"):
            declared_supersedes[document_id] = peek["supersedes"]
        seen_ids.add(document_id)
        seen_paths.add(key)
        newest = max(newest, modified_ns)

    for entry in data.get("documents") or []:
        if isinstance(entry, dict):
            add(entry, registration="explicit")

    if conventions:
        for name in root.glob("*"):
            if PurePosixPath(name).suffix.lower() not in DOCUMENT_SUFFIXES:
                continue
            if name.lower() in seen_paths:
                continue
            for rule in conventions:
                hit = rule.pattern.fullmatch(name)
                if hit is None:
                    continue
                groups = {k: v for k, v in hit.groupdict().items() if v is not None}
                groups.update({f"{k}_lower": v.lower() for k, v in list(groups.items())})
                entry = {
                    key: _fill(value, groups) if isinstance(value, str) else value
                    for key, value in rule.entry.items()
                    if key not in {"id", "match"}
                }
                entry["path"] = name
                if "episode" not in entry and groups.get("episode"):
                    entry["episode"] = groups["episode"]
                if "version" not in entry and groups.get("version"):
                    entry["version"] = groups["version"]
                template = _text(rule.entry.get("document_id"), 120)
                entry["id"] = (
                    _slug(_fill(template, groups)) if template else _slug(PurePosixPath(name).stem)
                )
                add(entry, registration="convention", convention=rule.id)
                break

    for pattern in data.get("discover") or []:
        if not isinstance(pattern, str) or "/" in pattern or "\\" in pattern or ".." in pattern:
            continue
        for name in root.glob(pattern):
            add({"path": name}, registration="unfiled")

    if data.get("supersedes_header") is True and declared_supersedes:
        documents = _header_supersession(documents, declared_supersedes)

    board = data.get("episodes") if isinstance(data.get("episodes"), dict) else None
    levels = _levels(board, warnings) if board else []
    counts = _page_counts(board, warnings) if board else []
    roles = _source_roles(board, warnings) if board else []
    if board:
        documents = _resolve_iterations(documents, board)
    tables = _page_tables(root, documents, counts, warnings)
    episodes = (
        _episodes(documents, board, levels, warnings, counts=counts, tables=tables, roles=roles)
        if board
        else []
    )
    counting = {level["id"] for level in levels if level.get("count_pages")}
    page_totals = tuple(
        {
            "id": count["id"],
            "label": count["label"],
            "pages": sum(
                pages
                for e in episodes
                if e.level in counting
                for cid, _label, pages, _doc in e.page_counts
                if cid == count["id"]
            ),
            "episodes": sum(
                1
                for e in episodes
                if e.level in counting and any(cid == count["id"] for cid, *_ in e.page_counts)
            ),
            "current": bool(count.get("current")),
        }
        for count in counts
    )

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
        source=root.origin(),
        episodes=tuple(episodes),
        levels=tuple(levels),
        page_totals=page_totals,
        source_roles=tuple(roles),
    )


# ---------------------------------------------------------------------------
# The episode board
# ---------------------------------------------------------------------------
def _levels(board: dict[str, Any], warnings: list[str]) -> list[dict[str, Any]]:
    levels = []
    for raw in (board.get("levels") or [])[:20]:
        if not isinstance(raw, dict):
            continue
        level_id = _text(raw.get("id"), 20)
        requires = [_text(c, 40).lower() for c in raw.get("requires") or [] if _text(c, 40)]
        if not level_id or not requires:
            warnings.append("episodes: a level needs an id and the categories it requires")
            continue
        levels.append(
            {
                "id": level_id,
                "label": _text(raw.get("label"), 120) or level_id,
                "requires": requires,
                "state": _optional(raw.get("state"), 40),
                "count_pages": bool(raw.get("count_pages")),
            }
        )
    return levels


_FILE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*\.(?:md|markdown)", re.I)


def _header_supersession(
    documents: list[ProjectDocument], declared: dict[str, str]
) -> list[ProjectDocument]:
    """A document that says ``**Supersedes:** `OLD.md``` supersedes that file.

    Only files registered by convention change lifecycle; an explicit entry keeps
    the standing its manifest entry gives it. The newer document records which
    one it supersedes either way.
    """
    by_name = {PurePosixPath(d.relative).name.lower(): d for d in documents}
    retired: dict[str, str] = {}
    out = []
    for d in documents:
        text = declared.get(d.id)
        target = None
        if text:
            names = _FILE_NAME.findall(text)
            target = next((by_name[n.lower()] for n in names if n.lower() in by_name), None)
        if target is not None and target.id != d.id:
            if target.registration != "explicit":
                retired[target.id] = d.id
            out.append(replace(d, supersedes=d.supersedes or target.id))
        else:
            out.append(d)
    return [replace(d, lifecycle="SUPERSEDED") if d.id in retired else d for d in out]


def _page_counts(board: dict[str, Any], warnings: list[str]) -> list[dict[str, Any]]:
    """Declared page counts; a board without any keeps its single panel-script total."""
    raw_counts = board.get("page_counts")
    if not isinstance(raw_counts, list):
        return [
            {
                "id": "base",
                "label": "Pages",
                "from": "fact",
                "category": _text(board.get("pages_from"), 40).lower(),
                "fact": _text(board.get("pages_fact"), 40) or "pages",
                "current": True,
            }
        ]
    counts = []
    for raw in raw_counts[:10]:
        if not isinstance(raw, dict) or not _text(raw.get("id"), 40):
            continue
        count: dict[str, Any] = {
            "id": _text(raw.get("id"), 40),
            "label": _text(raw.get("label"), 80) or _text(raw.get("id"), 40),
            "from": _text(raw.get("from"), 10).lower() or "fact",
            "category": _text(raw.get("category"), 40).lower(),
            "fact": _text(raw.get("fact"), 40) or "pages",
            "current": bool(raw.get("current")),
        }
        if count["from"] == "table":
            count["row"] = _compile(raw.get("row"), re.M, warnings, f"page count {count['id']}")
            if count["row"] is None:
                continue
        counts.append(count)
    return counts


def _source_roles(board: dict[str, Any], warnings: list[str]) -> list[dict[str, Any]]:
    roles = []
    for raw in (board.get("production_sources") or [])[:30]:
        if not isinstance(raw, dict) or not _text(raw.get("role"), 40):
            continue
        scope = _text(raw.get("scope"), 10).lower() or "episode"
        if scope not in {"episode", "season", "project"}:
            warnings.append(f"production source {raw.get('role')}: unknown scope {scope!r}")
            continue
        roles.append(
            {
                "role": _text(raw.get("role"), 40),
                "label": _text(raw.get("label"), 80) or _text(raw.get("role"), 40),
                "categories": [
                    _text(c, 40).lower() for c in raw.get("categories") or [] if _text(c, 40)
                ],
                "scope": scope,
                "required": bool(raw.get("required")),
                "when": _text(raw.get("when"), 120),
            }
        )
    return roles


def _page_tables(
    root: _Root,
    documents: list[ProjectDocument],
    counts: list[dict[str, Any]],
    warnings: list[str],
) -> dict[str, dict[str, tuple[int, str]]]:
    """For table counts: episode code -> (pages, document id), newest approved document wins."""
    tables: dict[str, dict[str, tuple[int, str]]] = {}
    for count in counts:
        if count["from"] != "table":
            continue
        rows: dict[str, tuple[int, str]] = {}
        sources = sorted(
            (d for d in documents if d.category == count["category"] and d.lifecycle in CONTINUITY),
            key=lambda d: d.modified_ns,
        )
        for d in sources:
            raw = root.read(d.relative, MAX_DOCUMENT_BYTES)
            if raw is None:
                warnings.append(f"page count {count['id']}: {d.id} could not be read")
                continue
            text = raw[:MAX_DOCUMENT_BYTES].decode("utf-8", errors="replace")
            for hit in count["row"].finditer(text):
                groups = hit.groupdict()
                if groups.get("episode") and (groups.get("pages") or "").isdigit():
                    rows[groups["episode"]] = (int(groups["pages"]), d.id)
        tables[count["id"]] = rows
    return tables


def _episode_code(board: dict[str, Any]) -> re.Pattern[str]:
    pattern = board.get("match")
    try:
        if isinstance(pattern, str) and 0 < len(pattern) <= MAX_PATTERN:
            return re.compile(pattern)
    except re.error:
        pass
    return re.compile(r"^S(?P<season>\d+)E(?P<number>\d+)$")


def _resolve_iterations(
    documents: list[ProjectDocument], board: dict[str, Any]
) -> list[ProjectDocument]:
    """Mark work-in-progress documents an episode's approved milestone has moved past.

    Declared as ``"resolves": {"green-light": ["voice-check-iteration"]}``: once an
    episode has an approved green-light document, its voice-check iterations
    still in REVIEW are shown as resolved by it. Their lifecycle stays exactly
    what their authors recorded.
    """
    resolves = board.get("resolves")
    if not isinstance(resolves, dict):
        return documents
    milestones: dict[tuple[str, str], str] = {}
    for d in documents:
        if d.episode and d.lifecycle in CONTINUITY:
            milestones.setdefault((d.episode, d.category), d.id)
    out = []
    for d in documents:
        resolved_by = None
        if d.episode and d.lifecycle not in CONTINUITY:
            for milestone, categories in resolves.items():
                if isinstance(categories, list) and d.category in categories:
                    resolved_by = milestones.get((d.episode, str(milestone).lower()))
                    if resolved_by:
                        break
        out.append(replace(d, resolved_by=resolved_by) if resolved_by else d)
    return out


def _episodes(
    documents: list[ProjectDocument],
    board: dict[str, Any],
    levels: list[dict[str, Any]],
    warnings: list[str],
    *,
    counts: list[dict[str, Any]] | None = None,
    tables: dict[str, dict[str, tuple[int, str]]] | None = None,
    roles: list[dict[str, Any]] | None = None,
) -> list[EpisodeStanding]:
    code = _episode_code(board)
    order = [_text(c, 40).lower() for c in board.get("categories") or [] if _text(c, 40)]
    title_from = [_text(c, 40).lower() for c in board.get("title_from") or [] if _text(c, 40)]
    title_fact = _text(board.get("title_fact"), 40) or "title"
    counts = counts or []
    tables = tables or {}
    roles = roles or []
    live = [d for d in documents if d.lifecycle in CONTINUITY and d.resolved_by is None]
    by_episode: dict[str, list[ProjectDocument]] = {}
    for d in documents:
        if d.episode and code.match(d.episode) and d.lifecycle not in {"SUPERSEDED", "ARCHIVED"}:
            by_episode.setdefault(d.episode, []).append(d)

    def rank(category: str) -> int:
        return order.index(category) if category in order else len(order)

    rows = []
    for episode, docs in by_episode.items():
        match = code.match(episode)
        groups = match.groupdict() if match else {}
        approved = {d.category for d in docs if d.lifecycle in CONTINUITY}
        reached = next(
            (
                i
                for i, candidate in enumerate(levels)
                if all(c in approved for c in candidate["requires"])
            ),
            None,
        )
        level: dict[str, Any] | None = levels[reached] if reached is not None else None
        target = levels[reached - 1] if reached is not None and reached > 0 else None
        if reached is None and levels:
            target = levels[-1]
        missing = tuple(c for c in (target or {}).get("requires", []) if c not in approved)
        title = None
        for category in title_from or order:
            doc = next((d for d in docs if d.category == category and d.fact(title_fact)), None)
            if doc is not None:
                title = doc.fact(title_fact)
                break
        page_counts: list[tuple[str, str, int, str]] = []
        for count in counts:
            if count["from"] == "table":
                found = tables.get(count["id"], {}).get(episode)
                if found is not None:
                    page_counts.append((count["id"], count["label"], found[0], found[1]))
                continue
            page_doc = next(
                (
                    d
                    for d in docs
                    if (not count["category"] or d.category == count["category"])
                    and d.lifecycle in CONTINUITY
                    and d.fact(count["fact"])
                ),
                None,
            )
            if page_doc is not None:
                digits = re.sub(r"\D", "", page_doc.fact(count["fact"]) or "")
                if digits:
                    page_counts.append((count["id"], count["label"], int(digits), page_doc.id))
        current = next(
            (c for c in counts if c.get("current") and any(p[0] == c["id"] for p in page_counts)),
            None,
        )
        chosen = next(
            (p for p in page_counts if current is not None and p[0] == current["id"]),
            page_counts[0] if page_counts else None,
        )
        pages = chosen[2] if chosen else None
        season = groups.get("season")
        number = groups.get("number")
        sources: list[tuple[str, str, bool, str]] = []
        missing_sources: list[str] = []
        for role in roles:
            if role["scope"] == "episode":
                pool = [d for d in live if d.episode == episode]
            elif role["scope"] == "season":
                pool = [d for d in live if d.applies_to == f"season:{int(season or 0)}"]
            else:
                pool = [d for d in live if not d.episode and d.applies_to in (None, "project")]
            chosen_docs = sorted(
                (d for d in pool if d.category in role["categories"]),
                key=lambda d: (d.category, d.id),
            )
            for d in chosen_docs:
                sources.append((role["role"], d.id, role["required"], role["when"]))
            if role["required"] and not chosen_docs:
                missing_sources.append(role["role"])
        newest = max(docs, key=lambda d: d.modified_ns)
        rows.append(
            EpisodeStanding(
                code=episode,
                season=int(season) if season and season.isdigit() else None,
                number=int(number) if number and number.isdigit() else None,
                title=title,
                level=level["id"] if level else None,
                label=level["label"]
                if level
                else _text(board.get("unmet_label"), 120) or "No declared level reached",
                state=level["state"] if level else None,
                pages=pages,
                documents=tuple(
                    (d.category, d.id) for d in sorted(docs, key=lambda d: (rank(d.category), d.id))
                ),
                missing=missing,
                last_commit=newest.commit,
                last_changed_ns=newest.modified_ns,
                page_counts=tuple(page_counts),
                current_count=chosen[0] if chosen else None,
                sources=tuple(sources),
                missing_sources=tuple(missing_sources),
            )
        )
    rows.sort(key=lambda r: (r.season or 0, r.number or 0, r.code))
    if levels and not rows:
        warnings.append("episodes: levels are declared but no document names an episode")
    return rows
