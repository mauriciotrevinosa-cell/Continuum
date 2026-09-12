"""Library acquisition routes (Library, not Project).

What the user owns, what is missing, where it may legally come from. The
acquisition engine owns those rules and publishes JSON documents; this
router reads them and exposes a stable projection for the UI.

Two boundaries hold here as everywhere else:

* **No filesystem path ever arrives from a client** (F-50). The data
  directory comes from configuration; document names are a fixed tuple;
  family and source ids only index dictionaries already in memory.
* **Nothing reachable from a browser writes into the Source Vault.** The
  actions below run an allowlisted CLI verb, and ``--apply`` is not in that
  allowlist: applying a scaffold or an import stays a deliberate act at a
  terminal. Every action answers with the exact command, so the user can run
  the write half themselves.

An unconfigured or empty library is a normal state, not an error: every
route answers with empty collections so the UI can render its empty state.
"""

from __future__ import annotations

import datetime as dt
import re
from collections import Counter
from typing import Annotated, Any, Literal

from continuum_observability import get_logger
from continuum_storage import AcquisitionCliError, AcquisitionStore

# `Path` is imported under another name on purpose: in an API module the bare
# name reads as a filesystem path, and the architecture invariant that keeps
# filesystem access inside continuum_storage flags every call to Path().
from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi import Path as PathParam

from continuum_api.schemas import (
    AcquisitionActionResult,
    AcquisitionOverview,
    AcquisitionStatus,
    AddSourceRequest,
    DocumentStatus,
    FamilyDetail,
    FamilyProgress,
    IntakeUnit,
    IntakeView,
    QueueItem,
    ReleaseEvent,
    ReviewItem,
    ScaffoldPlan,
    SourceOut,
    SourcesView,
    UpdateAlert,
    UpdatesView,
    UpdateWatchItem,
    WorkRow,
)

router = APIRouter(prefix="/library/acquisition", tags=["acquisition"])
log = get_logger("continuum.api.acquisition")

#: Path-parameter shapes. Both only ever index an in-memory mapping.
FamilyId = Annotated[str, PathParam(min_length=1, max_length=160, pattern=r"^[^/\\]+$")]
SourceId = Annotated[
    str, PathParam(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
]

CAPABILITIES = ("DISCOVERY_ONLY", "METADATA", "UPDATE_TRACKING", "MANUAL_ACQUISITION",
                "AUTOMATIC_ACQUISITION")
ADAPTERS = ("web", "local-folder", "bibliographic")


def _store(request: Request) -> AcquisitionStore:
    store: AcquisitionStore = request.app.state.acquisition
    return store


def _doc(request: Request, name: str) -> dict[str, Any]:
    return _store(request).read(name) or {}


def _status(store: AcquisitionStore, layout: dict[str, Any]) -> AcquisitionStatus:
    summary = store.summary()
    return AcquisitionStatus(
        configured=bool(summary["configured"]),
        available=bool(summary["available"]),
        data_dir=str(summary["data_dir"]),
        cli_available=bool(summary["cli_available"]),
        cli_path=str(summary["cli_path"]),
        vault_root=str(layout.get("vault_root") or ""),
        generated_at=layout.get("generated_at"),
        documents=[DocumentStatus(**d) for d in summary["documents"]],
    )


def _search_titles(catalog: dict[str, Any]) -> dict[str, list[str]]:
    """Exact titles to search a store with, per work: English first, then the
    Japanese one. A store that sells the Japanese edition is searched in
    Japanese; searching it in English finds nothing."""
    out: dict[str, list[str]] = {}
    for family in catalog.get("families") or []:
        for work in family.get("works") or []:
            titles = work.get("titles") or {}
            values: list[str] = []
            for candidate in (titles.get("en"), work.get("work"), titles.get("ja")):
                if isinstance(candidate, str) and candidate.strip() and candidate not in values:
                    values.append(candidate.strip())
            out[str(work.get("id"))] = values[:3]
    return out


def _families(layout: dict[str, Any]) -> list[dict[str, Any]]:
    families = layout.get("families")
    return families if isinstance(families, list) else []


def _family_progress(family: dict[str, Any]) -> FamilyProgress:
    works = family.get("works") or []
    official = [w for w in works if w.get("official_status") is not False]
    coverage = Counter((w.get("coverage_status") or "UNKNOWN") for w in official)
    relations = Counter((w.get("relationship_type") or "UNKNOWN") for w in works)
    return FamilyProgress(
        id=str(family.get("family_id") or ""),
        title=str(family.get("family_title") or ""),
        category=family.get("category"),
        medium=family.get("primary_medium"),
        path=str(family.get("family_path") or ""),
        folder_exists=bool(family.get("folder_exists")),
        works_total=len(works),
        complete=coverage.get("COMPLETE", 0),
        partial=coverage.get("PARTIAL", 0),
        missing=coverage.get("MISSING", 0),
        unknown=coverage.get("UNKNOWN", 0) + coverage.get("BLOCKED", 0),
        review=sum(1 for w in works if w.get("review_required")),
        files=int(family.get("files") or 0),
        bytes=int(family.get("bytes") or 0),
        classes=sorted({str(w.get("material_class")) for w in works if w.get("material_class")}),
        relations=dict(relations),
        missing_folders=sum(1 for w in works if w.get("layout_status") == "MISSING_FOLDER"),
        aliases=[str(a) for a in (family.get("family_aliases") or [])][:8],
    )


def _work_row(row: dict[str, Any], coverage: dict[str, Any],
              titles: dict[str, list[str]] | None = None) -> WorkRow:
    cov = (coverage.get("works") or {}).get(str(row.get("work_id"))) or {}
    return WorkRow(
        id=str(row.get("work_id") or ""),
        title=str(row.get("work") or ""),
        canonical_title=row.get("canonical_title"),
        family_id=str(row.get("family_id") or ""),
        family_title=str(row.get("family_title") or ""),
        relation=row.get("relationship_type"),
        material_class=row.get("material_class"),
        medium=row.get("medium"),
        edition=row.get("edition"),
        official=row.get("official_status"),
        authority=row.get("authority_status"),
        origin=row.get("origin"),
        confidence=row.get("confidence"),
        coverage_status=row.get("coverage_status"),
        coverage_reason=row.get("coverage_reason") or cov.get("reason"),
        layout_status=row.get("layout_status"),
        local_path=row.get("local_path"),
        expected_path=row.get("expected_path"),
        legacy_mapping=bool(row.get("legacy_mapping")),
        legacy_kind=row.get("legacy_kind"),
        folder_exists=bool(row.get("folder_exists")),
        local_files=int(row.get("local_files") or 0),
        local_bytes=int(row.get("local_bytes") or 0),
        chapter_min=cov.get("chapter_min"),
        chapter_max=cov.get("chapter_max"),
        chapters=int(cov.get("local_chapters") or 0),
        gaps=str(cov.get("gaps_text") or ""),
        missing_chapters=str(cov.get("missing_chapters_text") or ""),
        remote_latest_chapter=cov.get("remote_latest_chapter"),
        remote_volumes=cov.get("remote_volumes"),
        source_chapter_count=cov.get("source_chapter_count"),
        languages=[str(x) for x in (row.get("languages") or [])],
        unofficial_provenance=[str(x) for x in (row.get("unofficial_provenance") or [])],
        review_required=bool(row.get("review_required")),
        contained_in=row.get("contained_in"),
        aliases=[str(a) for a in (row.get("aliases") or [])][:12],
        search_titles=(titles or {}).get(str(row.get("work_id")), []),
    )


def _queue_items(queue: dict[str, Any], families: list[dict[str, Any]],
                 coverage: dict[str, Any] | None = None,
                 titles: dict[str, list[str]] | None = None) -> list[QueueItem]:
    ids = {str(f.get("family_title")): str(f.get("family_id") or "") for f in families}
    per_work = (coverage or {}).get("works") or {}
    out: list[QueueItem] = []
    for row in queue.get("works") or []:
        if row.get("coverage_status") not in ("MISSING", "PARTIAL", "BLOCKED"):
            continue
        if row.get("official") is False:
            continue
        out.append(
            QueueItem(
                family=str(row.get("family") or ""),
                family_id=ids.get(str(row.get("family") or ""), ""),
                work=str(row.get("work") or ""),
                work_id=str(row.get("work_id") or ""),
                relation=row.get("relation"),
                material_class=row.get("material_class"),
                coverage_status=row.get("coverage_status"),
                reason=row.get("coverage_reason"),
                best_source=row.get("best_source"),
                availability=row.get("availability"),
                requires_purchase=row.get("requires_purchase"),
                requires_user_action=bool(row.get("manual_action_required")),
                downloadable=bool(row.get("automatic_download_allowed")),
                search_title=row.get("search_title"),
                url=row.get("url"),
                notes=row.get("notes"),
                priority=int(row.get("priority") or 8),
                source_hits=[h for h in (row.get("source_hits") or []) if isinstance(h, dict)],
                search_titles=(titles or {}).get(str(row.get("work_id")), []),
                missing_chapters=str(
                    (per_work.get(str(row.get("work_id"))) or {}).get("missing_chapters_text") or ""
                ),
                chapters_held=int(
                    (per_work.get(str(row.get("work_id"))) or {}).get("local_chapters") or 0
                ),
                chapters_total=(per_work.get(str(row.get("work_id"))) or {}).get(
                    "source_chapter_count"
                ),
            )
        )
    out.sort(key=lambda i: (i.priority, i.family, i.work))
    return out


def _source_out(entry: dict[str, Any]) -> SourceOut:
    test = entry.get("last_test") or {}
    return SourceOut(
        id=str(entry.get("id") or ""),
        name=str(entry.get("name") or entry.get("id") or ""),
        url=str(entry.get("url") or ""),
        adapter=str(entry.get("adapter") or "web"),
        enabled=bool(entry.get("enabled", True)),
        capabilities=[str(c) for c in (entry.get("capabilities") or [])],
        operations=[str(o) for o in (test.get("operations") or [])],
        access=[str(a) for a in (entry.get("access") or [])],
        roles=[str(r) for r in (entry.get("roles") or [])],
        languages=[str(x) for x in (entry.get("languages") or [])],
        download_permitted=bool(entry.get("download_permitted")),
        origin=entry.get("origin"),
        notes=str(entry.get("notes") or ""),
        search=entry.get("search"),
        added_at=entry.get("added_at"),
        tested_at=test.get("at"),
        test_ok=test.get("ok") if test else None,
        test_error=test.get("error"),
        test_checks=[c for c in (test.get("checks") or []) if isinstance(c, dict)],
    )


def _run(store: AcquisitionStore, verb: str, *args: str, success: str) -> AcquisitionActionResult:
    """Run an allowlisted action, or explain how to run it by hand."""
    try:
        result = store.run(verb, *args)
    except AcquisitionCliError as exc:
        try:
            command = store.display(store.build_command(verb, *args))
        except AcquisitionCliError:
            command = ""
        return AcquisitionActionResult(ok=False, message=str(exc), command=command, exit_code=126)
    output = (result.stdout + ("\n" + result.stderr if result.stderr else "")).strip()
    return AcquisitionActionResult(
        ok=result.ok,
        message=success if result.ok else (result.stderr.strip() or "the command failed"),
        command=result.display_command,
        output=output[-4000:],
        exit_code=result.exit_code,
    )


# ---------------------------------------------------------------------------
@router.get("", response_model=AcquisitionOverview)
def overview(request: Request) -> AcquisitionOverview:
    """Everything the Library Acquisition landing screen needs in one call."""
    store = _store(request)
    layout = _doc(request, "vault-layout.json")
    queue = _doc(request, "acquisition-queue.json")
    registry = _doc(request, "sources.json")
    review = _doc(request, "REVIEW_REQUIRED.json")
    watch = _doc(request, "update-watch.json")
    ingest = _doc(request, "ingest-last.json")
    coverage = _doc(request, "vault-coverage.json")
    catalog = _doc(request, "works-catalog.json")

    families = _families(layout)
    progress = [_family_progress(f) for f in families]
    works = [w for f in families for w in (f.get("works") or [])]
    official = [w for w in works if w.get("official_status") is not False]
    coverage_counts = Counter((w.get("coverage_status") or "UNKNOWN") for w in official)
    relations = Counter((w.get("relationship_type") or "UNKNOWN") for w in works)
    sources = list((registry.get("sources") or {}).values())
    units = [u for u in (ingest.get("units") or []) if isinstance(u, dict)]

    totals = {
        "families": len(families),
        "works": len(works),
        "official_works": len(official),
        "complete": coverage_counts.get("COMPLETE", 0),
        "partial": coverage_counts.get("PARTIAL", 0),
        "missing": coverage_counts.get("MISSING", 0),
        "unknown": coverage_counts.get("UNKNOWN", 0) + coverage_counts.get("BLOCKED", 0),
        "files": int((layout.get("summary") or {}).get("files") or 0),
        "bytes": int((layout.get("summary") or {}).get("bytes") or 0),
        "missing_folders": int((layout.get("summary") or {}).get("missing_folder") or 0),
        "legacy_paths": int((layout.get("summary") or {}).get("legacy_paths_mapped") or 0),
        "duplicate_groups": int(
            (layout.get("summary") or {}).get("possible_duplicate_groups") or 0
        ),
    }
    alerts = [
        UpdateAlert(
            at=a.get("at"),
            kind=str(a.get("kind") or ""),
            family=str(a.get("family") or ""),
            work=a.get("work"),
            source=a.get("source"),
            detail=str(a.get("detail") or ""),
        )
        for a in (watch.get("alerts") or [])[-12:][::-1]
        if isinstance(a, dict)
    ]
    return AcquisitionOverview(
        status=_status(store, layout),
        totals=totals,
        relations=dict(relations),
        families=progress,
        queue_preview=_queue_items(queue, families, coverage, _search_titles(catalog))[:12],
        alerts=alerts,
        review_count=len(review.get("items") or []),
        intake_pending=sum(
            1 for u in units if str(u.get("action", "")).startswith("left-in-intake")
        ),
        sources_enabled=sum(1 for s in sources if s.get("enabled", True)),
        sources_total=len(sources),
    )


@router.get("/status", response_model=AcquisitionStatus)
def status_only(request: Request) -> AcquisitionStatus:
    """Just how things stand and how old the data is.

    Every screen shows this, so it must not pay for the whole overview.
    """
    return _status(_store(request), _doc(request, "vault-layout.json"))


@router.post("/refresh", response_model=AcquisitionActionResult)
def refresh(request: Request) -> AcquisitionActionResult:
    """Re-read the Vault and rebuild every document.

    Read-only over the library: it hashes what changed, recomputes coverage
    and rewrites the reports. Nothing in the Vault is modified.
    """
    return _run(_store(request), "coverage",
                success="re-read the Vault and rebuilt the reports")


@router.get("/families", response_model=list[FamilyProgress])
def list_families(request: Request) -> list[FamilyProgress]:
    return [_family_progress(f) for f in _families(_doc(request, "vault-layout.json"))]


@router.get("/families/{family_id}", response_model=FamilyDetail)
def family_detail(request: Request, family_id: FamilyId) -> FamilyDetail:
    layout = _doc(request, "vault-layout.json")
    coverage = _doc(request, "vault-coverage.json")
    for family in _families(layout):
        if str(family.get("family_id")) == family_id:
            titles = _search_titles(_doc(request, "works-catalog.json"))
            works = [_work_row(w, coverage, titles) for w in (family.get("works") or [])]
            works.sort(key=lambda w: (w.material_class or "", w.title.lower()))
            findings = [f for f in (family.get("findings") or []) if isinstance(f, dict)]
            return FamilyDetail(family=_family_progress(family), works=works, findings=findings)
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="family not found")


@router.get("/queue", response_model=list[QueueItem])
def queue(
    request: Request,
    coverage_status: Annotated[str | None, Query(alias="status", max_length=32)] = None,
    limit: Annotated[int, Query(ge=1, le=2000)] = 500,
) -> list[QueueItem]:
    layout = _doc(request, "vault-layout.json")
    items = _queue_items(
        _doc(request, "acquisition-queue.json"),
        _families(layout),
        _doc(request, "vault-coverage.json"),
        _search_titles(_doc(request, "works-catalog.json")),
    )
    if coverage_status:
        wanted = coverage_status.upper()
        items = [i for i in items if (i.coverage_status or "") == wanted]
    return items[:limit]


@router.get("/sources", response_model=SourcesView)
def list_sources(request: Request) -> SourcesView:
    registry = _doc(request, "sources.json")
    entries = list((registry.get("sources") or {}).values())
    entries.sort(key=lambda e: (not e.get("enabled", True), str(e.get("id") or "")))
    return SourcesView(
        sources=[_source_out(e) for e in entries],
        unofficial_hosts=[str(h) for h in (registry.get("unofficial_hosts") or [])],
        cli_available=_store(request).cli_available,
        capabilities=list(CAPABILITIES),
        adapters=list(ADAPTERS),
    )


@router.post("/sources", response_model=AcquisitionActionResult)
def add_source(request: Request, body: AddSourceRequest) -> AcquisitionActionResult:
    """Register a source. The engine decides whether it is acceptable."""
    args: list[str] = ["add", body.url]
    if body.source_id:
        args += ["--id", body.source_id]
    if body.name:
        args += ["--name", body.name]
    if body.adapter:
        args += ["--adapter", body.adapter]
    if body.search:
        args += ["--search", body.search]
    if body.note:
        args += ["--note", body.note]
    if body.access:
        args += ["--access", body.access]
    for role in body.roles:
        args += ["--role", role]
    if body.download_permitted:
        args.append("--download-permitted")
    if not body.test:
        args.append("--no-test")
    return _run(_store(request), "sources", *args, success=f"registered {body.url}")


@router.post("/sources/{source_id}/test", response_model=AcquisitionActionResult)
def test_source(request: Request, source_id: SourceId) -> AcquisitionActionResult:
    return _run(_store(request), "sources", "test", source_id, success=f"tested {source_id}")


@router.post("/sources/{source_id}/enable", response_model=AcquisitionActionResult)
def enable_source(request: Request, source_id: SourceId) -> AcquisitionActionResult:
    return _run(_store(request), "sources", "enable", source_id, success=f"enabled {source_id}")


@router.post("/sources/{source_id}/disable", response_model=AcquisitionActionResult)
def disable_source(request: Request, source_id: SourceId) -> AcquisitionActionResult:
    return _run(_store(request), "sources", "disable", source_id, success=f"disabled {source_id}")


@router.post("/sources/{source_id}/remove", response_model=AcquisitionActionResult)
def remove_source(request: Request, source_id: SourceId) -> AcquisitionActionResult:
    """POST rather than DELETE: the API allows only GET and POST (CORS, A-03)."""
    return _run(_store(request), "sources", "remove", source_id, success=f"removed {source_id}")


@router.get("/intake", response_model=IntakeView)
def intake(request: Request) -> IntakeView:
    ingest = _doc(request, "ingest-last.json")
    layout = _doc(request, "vault-layout.json")
    review = _doc(request, "REVIEW_REQUIRED.json")
    units = [
        IntakeUnit(
            source=str(u.get("source") or ""),
            unit=str(u.get("unit") or ""),
            path=str(u.get("path") or ""),
            files=int(u.get("files") or 0),
            classified_by=u.get("classified_by"),
            series=[str(s) for s in (u.get("series") or {})],
            languages=[str(x) for x in (u.get("languages") or {})],
            unofficial_provenance=[str(x) for x in (u.get("unofficial_provenance") or [])],
            colored=bool(u.get("colored")),
        )
        for u in (ingest.get("units") or [])
        if isinstance(u, dict)
    ]
    duplicates: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    for family in _families(layout):
        for finding in family.get("findings") or []:
            if not isinstance(finding, dict):
                continue
            entry = dict(finding, family=family.get("family_title"))
            if finding.get("type") == "POSSIBLE_DUPLICATE":
                duplicates.append(entry)
            elif finding.get("type") in ("CONFLICT", "AMBIGUOUS"):
                conflicts.append(entry)
    for finding in layout.get("global_findings") or []:
        if isinstance(finding, dict) and finding.get("type") == "POSSIBLE_DUPLICATE":
            duplicates.append(dict(finding, family=""))
    return IntakeView(
        mode=ingest.get("mode"),
        intake_dirs=[str(d) for d in (ingest.get("intake_dirs") or [])],
        counts={str(k): int(v) for k, v in (ingest.get("counts") or {}).items()},
        units=units,
        review=[
            ReviewItem(
                kind=str(i.get("kind") or ""),
                family=str(i.get("family") or ""),
                item=str(i.get("item") or ""),
                detail=str(i.get("detail") or ""),
                action=str(i.get("action") or ""),
            )
            for i in (review.get("items") or [])
            if isinstance(i, dict)
        ],
        duplicates=duplicates[:200],
        conflicts=conflicts[:200],
        proposed_moves=[
            m for m in (layout.get("proposed_moves") or []) if isinstance(m, dict)
        ][:200],
    )


@router.post("/intake/refresh", response_model=AcquisitionActionResult)
def refresh_intake(request: Request) -> AcquisitionActionResult:
    """Re-read the intake. A dry run: it can only report, never import."""
    return _run(_store(request), "ingest", success="intake re-read (dry run: nothing was imported)")


@router.get("/updates", response_model=UpdatesView)
def updates(request: Request) -> UpdatesView:
    watch = _doc(request, "update-watch.json")
    items = [
        UpdateWatchItem(
            family=str(w.get("family") or ""),
            work=str(w.get("work") or ""),
            work_id=str(w.get("work_id") or ""),
            relation=w.get("relation"),
            latest_local=w.get("latest_local"),
            latest_remote=w.get("latest_remote"),
            remote_volumes=w.get("remote_volumes"),
            update_available=w.get("update_available"),
            status=w.get("status"),
            last_checked=w.get("last_checked"),
            source=w.get("source"),
        )
        for w in (watch.get("works") or [])
        if isinstance(w, dict)
    ]
    items.sort(key=lambda i: (not bool(i.update_available), i.family, i.work))
    return UpdatesView(
        generated_at=watch.get("generated_at"),
        last_check=watch.get("last_check"),
        alerts=[
            UpdateAlert(
                at=a.get("at"),
                kind=str(a.get("kind") or ""),
                family=str(a.get("family") or ""),
                work=a.get("work"),
                source=a.get("source"),
                detail=str(a.get("detail") or ""),
            )
            for a in (watch.get("alerts") or [])[::-1]
            if isinstance(a, dict)
        ][:200],
        items=items,
        sources={str(k): v for k, v in (watch.get("sources") or {}).items() if isinstance(v, dict)},
    )


def _scaffold_plan(store: AcquisitionStore, layout: dict[str, Any], *, ran: bool = False,
                   output: str = "") -> ScaffoldPlan:
    create: list[dict[str, Any]] = []
    review: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    for family in _families(layout):
        for row in family.get("works") or []:
            state = str(row.get("layout_status") or "")
            counts[state] += 1
            entry = {
                "family": family.get("family_title"),
                "family_id": family.get("family_id"),
                "work": row.get("work"),
                "relation": row.get("relationship_type"),
                "material_class": row.get("material_class"),
                "path": row.get("local_path") or row.get("expected_path"),
                "confidence": row.get("confidence"),
                "origin": row.get("origin"),
            }
            if state == "MISSING_FOLDER" and row.get("official_status") is True:
                create.append(entry)
            elif state in ("REVIEW_REQUIRED", "AMBIGUOUS", "CONFLICT"):
                review.append(entry)
    try:
        command = store.display(store.build_command("scaffold", "--no-rescan"))
    except AcquisitionCliError:
        command = ""
    return ScaffoldPlan(
        counts=dict(counts),
        create=create[:500],
        review=review[:500],
        command=command.replace(" scaffold --no-rescan", " scaffold --apply"),
        ran=ran,
        output=output[-4000:],
    )


_DATE = re.compile(r"^(\d{4})(?:[-/.](\d{1,2}))?(?:[-/.](\d{1,2}))?")


def _parse_date(raw: Any) -> tuple[str, Literal["day", "month", "year"]] | None:
    """A bibliographic date, with the precision it was actually given.

    Legal-deposit records often carry only a year or a year and month. The
    calendar places those on the first of the period and SAYS so, rather than
    inventing a day that looks like fact.
    """
    if not isinstance(raw, str):
        return None
    match = _DATE.match(raw.strip())
    if not match:
        return None
    year = int(match.group(1))
    if not 1900 <= year <= 2100:
        return None
    precision: Literal["day", "month", "year"] = (
        "day" if match.group(3) else "month" if match.group(2) else "year"
    )
    month = min(max(int(match.group(2) or 1), 1), 12)
    day = min(max(int(match.group(3) or 1), 1), 31)
    while day > 1:
        try:
            dt.date(year, month, day)
            break
        except ValueError:
            day -= 1
    return f"{year:04d}-{month:02d}-{day:02d}", precision


@router.get("/calendar", response_model=list[ReleaseEvent])
def calendar(
    request: Request,
    limit: Annotated[int, Query(ge=1, le=5000)] = 2000,
) -> list[ReleaseEvent]:
    """Dated events for the library: what was published, and what was seen.

    Upcoming dates are absent on purpose: no registered source publishes a
    release schedule yet, and an empty future is honest where a guessed one
    would not be.
    """
    catalog = _doc(request, "works-catalog.json")
    watch = _doc(request, "update-watch.json")
    events: list[ReleaseEvent] = []

    for family in catalog.get("families") or []:
        family_id = str(family.get("id") or "")
        family_title = str(family.get("family") or "")
        for work in family.get("works") or []:
            ndl = (work.get("remote") or {}).get("ndl") or {}
            volumes = ndl.get("volumes")
            seen: set[str] = set()
            for key, label in (
                ("first_issued", "first volume published"),
                ("last_issued", "latest volume published"),
            ):
                parsed = _parse_date(ndl.get(key))
                if parsed is None or parsed[0] in seen:
                    continue
                seen.add(parsed[0])
                detail = label
                if isinstance(volumes, int) and volumes:
                    detail += f" · {volumes} volume(s) on record"
                events.append(
                    ReleaseEvent(
                        date=parsed[0],
                        precision=parsed[1],
                        kind="published",
                        family=family_title,
                        family_id=family_id,
                        work=str(work.get("work") or ""),
                        work_id=str(work.get("id") or ""),
                        relation=work.get("relation"),
                        material_class=work.get("material_class"),
                        detail=detail,
                    )
                )

    families_by_title = {
        str(f.get("family") or ""): str(f.get("id") or "") for f in (catalog.get("families") or [])
    }
    for alert in watch.get("alerts") or []:
        if not isinstance(alert, dict):
            continue
        parsed = _parse_date(alert.get("at"))
        if parsed is None:
            continue
        family_title = str(alert.get("family") or "")
        kind_label = str(alert.get("kind") or "").replace("_", " ").lower()
        events.append(
            ReleaseEvent(
                date=parsed[0],
                precision="day",
                kind="detected",
                family=family_title,
                family_id=families_by_title.get(family_title, ""),
                work=str(alert.get("work") or alert.get("source") or ""),
                work_id="",
                detail=f"{kind_label}: {alert.get('detail') or ''}",
            )
        )

    events.sort(key=lambda e: (e.date, e.family, e.work))
    return events[-limit:]


@router.get("/scaffold", response_model=ScaffoldPlan)
def scaffold_plan(request: Request) -> ScaffoldPlan:
    """Folders the library is missing, from the last recorded layout."""
    return _scaffold_plan(_store(request), _doc(request, "vault-layout.json"))


@router.post("/scaffold/plan", response_model=ScaffoldPlan)
def refresh_scaffold_plan(request: Request) -> ScaffoldPlan:
    """Recompute the plan. A dry run: creating folders stays a CLI action,
    because the Source Vault is read-only to Continuum (ADR-0001)."""
    store = _store(request)
    result = _run(store, "scaffold", "--no-rescan", success="scaffold plan refreshed (dry run)")
    layout = store.read("vault-layout.json") or {}
    return _scaffold_plan(store, layout, ran=result.ok, output=result.output or result.message)
