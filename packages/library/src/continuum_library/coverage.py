"""The coverage audit: can we account for the whole Vault, and explain every exclusion?

:func:`build_coverage` answers from the catalog itself - no walk, no reads - so
it is cheap and always consistent with what search and retrieval can see. For
every configured root it reports what the last scan discovered and skipped,
where every file ended up (catalogued, unsupported, failed, missing), what the
archives hold, which units were identified and how confidently, which exact
duplicates exist, and - for everything that cannot be searched - why.

:func:`write_coverage_report` stores it as JSON (for machines) and Markdown
(for people) under ``generated/reports/catalog/``. Reports contain personal
titles and paths: they stay on this machine and are never committed.
"""

from __future__ import annotations

import datetime as dt
import json
from collections.abc import Sequence
from typing import Any

from continuum_core.catalog import Confidence, EntryStatus, ScanStatus, UnitKind
from continuum_db.models import (
    CatalogEntry,
    CatalogMember,
    CatalogScan,
    CatalogUnit,
    ReferenceCandidate,
    ReferenceItem,
)
from continuum_storage import DerivedStore, ProjectLibrary
from continuum_storage.reports import write_report
from continuum_storage.survey import CatalogRoot, catalog_roots
from sqlalchemy import func, select
from sqlalchemy.orm import Session

__all__ = [
    "COVERAGE_SCHEMA",
    "build_coverage",
    "render_coverage_markdown",
    "write_coverage_report",
]

COVERAGE_SCHEMA = "continuum.catalog-coverage/1"
#: Individually listed problem entries per root and section; the rest are counted.
MAX_LISTED = 500


def _value(item: Any) -> str:
    return str(item.value if hasattr(item, "value") else item)


def _grouped(session: Session, column: Any, *where: Any) -> dict[str, int]:
    rows = session.execute(select(column, func.count()).where(*where).group_by(column)).all()
    return {(_value(key) if key is not None else "none"): int(count) for key, count in rows}


def _root_section(session: Session, root: CatalogRoot) -> dict[str, Any]:
    in_root = CatalogEntry.root_key == root.key
    scan = session.execute(
        select(CatalogScan)
        .where(CatalogScan.root_key == root.key)
        .order_by(CatalogScan.started_at.desc(), CatalogScan.id.desc())
        .limit(1)
    ).scalar_one_or_none()
    completed = session.execute(
        select(CatalogScan)
        .where(CatalogScan.root_key == root.key, CatalogScan.status == ScanStatus.COMPLETED)
        .order_by(CatalogScan.finished_at.desc(), CatalogScan.id.desc())
        .limit(1)
    ).scalar_one_or_none()
    shown = completed or scan
    survey: dict[str, Any] = dict(shown.survey) if shown is not None else {}
    skipped_entries = survey.pop("skipped_entries", [])

    total, total_bytes = session.execute(
        select(func.count(), func.coalesce(func.sum(CatalogEntry.byte_size), 0)).where(in_root)
    ).one()
    present = CatalogEntry.status != EntryStatus.MISSING
    hashed = session.execute(
        select(CatalogEntry.hash_source, func.count())
        .where(in_root, present, CatalogEntry.status == EntryStatus.CATALOGUED)
        .group_by(CatalogEntry.hash_source)
    ).all()
    hash_counts = {(_value(k) if k is not None else "pending"): int(v) for k, v in hashed}

    archive_rows = session.execute(
        select(
            CatalogEntry.archive_view,
            func.count(),
            func.coalesce(func.sum(CatalogEntry.member_count), 0),
            func.coalesce(func.sum(CatalogEntry.image_count), 0),
            func.coalesce(func.sum(CatalogEntry.video_count), 0),
        )
        .where(in_root, present, CatalogEntry.archive_view.is_not(None))
        .group_by(CatalogEntry.archive_view)
    ).all()
    archives = {
        "total": sum(int(r[1]) for r in archive_rows),
        "by_view": {str(r[0]): int(r[1]) for r in archive_rows},
        "members_indexed": sum(int(r[2]) for r in archive_rows),
        "image_members": sum(int(r[3]) for r in archive_rows),
        "video_members": sum(int(r[4]) for r in archive_rows),
    }
    archives["recorded_members"] = _grouped(
        session,
        CatalogMember.kind,
        CatalogMember.entry_id.in_(select(CatalogEntry.id).where(in_root, present)),
    )

    unit_where = CatalogUnit.entry_id.in_(select(CatalogEntry.id).where(in_root, present))
    units = _grouped(session, CatalogUnit.kind, unit_where)
    confidence = _grouped(session, CatalogUnit.confidence, unit_where)
    flagged = session.execute(
        select(func.count()).where(unit_where, func.jsonb_array_length(CatalogUnit.flags) > 0)
    ).scalar_one()
    low = session.execute(
        select(CatalogUnit.label, CatalogUnit.flags, CatalogEntry.relative_path)
        .join(CatalogEntry, CatalogEntry.id == CatalogUnit.entry_id)
        .where(unit_where, CatalogUnit.confidence == Confidence.LOW)
        .order_by(CatalogEntry.relative_path, CatalogUnit.sort_key)
        .limit(MAX_LISTED)
    ).all()
    series = session.execute(
        select(func.count(func.distinct(CatalogEntry.series_key))).where(
            in_root, present, CatalogEntry.series_key.is_not(None)
        )
    ).scalar_one()
    episodes_by_series = session.execute(
        select(CatalogUnit.series_title, func.count())
        .where(unit_where, CatalogUnit.kind == UnitKind.EPISODE)
        .group_by(CatalogUnit.series_title)
        .order_by(CatalogUnit.series_title)
    ).all()
    chapters_by_series = session.execute(
        select(CatalogUnit.series_title, func.count())
        .where(unit_where, CatalogUnit.kind == UnitKind.MANGA_CHAPTER)
        .group_by(CatalogUnit.series_title)
        .order_by(CatalogUnit.series_title)
    ).all()

    duplicates = session.execute(
        select(func.count()).where(in_root, CatalogEntry.duplicate_of_id.is_not(None))
    ).scalar_one()
    duplicate_groups = session.execute(
        select(func.count(func.distinct(CatalogEntry.duplicate_of_id))).where(
            in_root, CatalogEntry.duplicate_of_id.is_not(None)
        )
    ).scalar_one()

    def listed(status: EntryStatus) -> list[dict[str, Any]]:
        rows = session.execute(
            select(
                CatalogEntry.relative_path,
                CatalogEntry.status_reason,
                CatalogEntry.last_error,
                CatalogEntry.attempts,
                CatalogEntry.detected_format,
                CatalogEntry.byte_size,
            )
            .where(in_root, CatalogEntry.status == status)
            .order_by(CatalogEntry.relative_path)
            .limit(MAX_LISTED)
        ).all()
        return [
            {
                "relative": r[0],
                "reason": r[1],
                "error": r[2],
                "attempts": int(r[3] or 0),
                "format": r[4],
                "bytes": int(r[5]),
            }
            for r in rows
        ]

    catalogued_without_units = session.execute(
        select(CatalogEntry.relative_path, CatalogEntry.archive_view)
        .where(
            in_root,
            CatalogEntry.status == EntryStatus.CATALOGUED,
            ~CatalogEntry.id.in_(select(CatalogUnit.entry_id)),
        )
        .order_by(CatalogEntry.relative_path)
        .limit(MAX_LISTED)
    ).all()
    by_status = _grouped(session, CatalogEntry.status, in_root)
    not_searchable = {
        "unsupported": by_status.get("UNSUPPORTED", 0),
        "failed": by_status.get("FAILED", 0),
        "missing": by_status.get("MISSING", 0),
        "catalogued_without_units": len(catalogued_without_units),
        "skipped_by_scan": int(survey.get("skipped") or 0),
    }
    return {
        "root_key": root.key,
        "collection": root.collection,
        "available": root.available(),
        "last_scan": _scan_view(scan),
        "last_completed_scan": _scan_view(completed),
        "discovered": {
            "files": int(survey.get("files") or 0),
            "bytes": int(survey.get("bytes") or 0),
            "directories": int(survey.get("directories") or 0),
            "skipped": int(survey.get("skipped") or 0),
            "skipped_by_reason": survey.get("skipped_by_reason") or {},
            "skipped_entries": skipped_entries[:MAX_LISTED],
        },
        "entries": {
            "total": int(total),
            "bytes": int(total_bytes),
            "by_status": by_status,
            "by_kind": _grouped(session, CatalogEntry.detected_kind, in_root, present),
            "by_material": _grouped(session, CatalogEntry.material_class, in_root, present),
            "series": int(series),
        },
        "hashes": hash_counts,
        "archives": archives,
        "units": {
            "by_kind": units,
            "by_confidence": confidence,
            "flagged": int(flagged),
            "episodes_by_series": {str(k or "(no series)"): int(v) for k, v in episodes_by_series},
            "chapters_by_series": {str(k or "(no series)"): int(v) for k, v in chapters_by_series},
            "low_confidence": [{"label": r[0], "flags": r[1], "relative": r[2]} for r in low],
        },
        "duplicates": {"extra_copies": int(duplicates), "groups": int(duplicate_groups)},
        "not_searchable": not_searchable,
        "unsupported": listed(EntryStatus.UNSUPPORTED),
        "failed": listed(EntryStatus.FAILED),
        "missing": listed(EntryStatus.MISSING),
        "catalogued_without_units": [
            {"relative": r[0], "archive_view": r[1]} for r in catalogued_without_units
        ],
    }


def _scan_view(scan: CatalogScan | None) -> dict[str, Any] | None:
    if scan is None:
        return None
    return {
        "id": str(scan.id),
        "status": _value(scan.status),
        "started_at": scan.started_at.isoformat() if scan.started_at else None,
        "finished_at": scan.finished_at.isoformat() if scan.finished_at else None,
        "counts": scan.counts,
    }


def _references(session: Session) -> dict[str, Any]:
    live = ReferenceItem.removed_at.is_(None)
    return {
        "total": int(session.execute(select(func.count()).where(live)).scalar_one()),
        "by_origin": _grouped(session, ReferenceItem.origin, live),
        "by_class": _grouped(session, ReferenceItem.reference_class, live),
        "by_collection": _grouped(session, ReferenceItem.collection, live),
        "rights_status": _grouped(session, ReferenceItem.rights_status, live),
        "training_eligibility": _grouped(session, ReferenceItem.training_eligibility, live),
        "candidates_by_status": _grouped(session, ReferenceCandidate.status),
        "candidates_by_collection": _grouped(session, ReferenceCandidate.collection),
    }


def _projects(projects: ProjectLibrary | None) -> dict[str, Any]:
    if projects is None:
        return {"projects": 0}
    out: list[dict[str, Any]] = []
    for project in projects.projects():
        by_lifecycle: dict[str, int] = {}
        for document in project.documents:
            by_lifecycle[document.lifecycle] = by_lifecycle.get(document.lifecycle, 0) + 1
        out.append(
            {
                "id": project.id,
                "documents": len(project.documents),
                "by_lifecycle": by_lifecycle,
                "unfiled": sum(1 for d in project.documents if not d.filed),
                "warnings": list(project.warnings),
            }
        )
    return {"projects": len(out), "detail": out}


def build_coverage(
    session: Session,
    roots: Sequence[CatalogRoot],
    *,
    projects: ProjectLibrary | None = None,
    imports: dict[str, Any] | None = None,
) -> dict[str, Any]:
    sections = [_root_section(session, root) for root in roots]
    totals = {
        "roots": len(sections),
        "files_discovered": sum(s["discovered"]["files"] for s in sections),
        "entries": sum(s["entries"]["total"] for s in sections),
        "catalogued": sum(s["entries"]["by_status"].get("CATALOGUED", 0) for s in sections),
        "unsupported": sum(s["entries"]["by_status"].get("UNSUPPORTED", 0) for s in sections),
        "failed": sum(s["entries"]["by_status"].get("FAILED", 0) for s in sections),
        "missing": sum(s["entries"]["by_status"].get("MISSING", 0) for s in sections),
        "skipped_by_scan": sum(s["discovered"]["skipped"] for s in sections),
        "archives": sum(s["archives"]["total"] for s in sections),
        "archive_members_indexed": sum(s["archives"]["members_indexed"] for s in sections),
        "units": sum(sum(s["units"]["by_kind"].values()) for s in sections),
        "duplicates": sum(s["duplicates"]["extra_copies"] for s in sections),
    }
    # Files the scan found but the catalog has no entry for (a scan still running).
    totals["unaccounted"] = max(
        totals["files_discovered"]
        - sum(
            s["entries"]["total"] - s["entries"]["by_status"].get("MISSING", 0) for s in sections
        ),
        0,
    )
    return {
        "schema": COVERAGE_SCHEMA,
        "generated_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "totals": totals,
        "roots": sections,
        "references": _references(session),
        "imports": imports or {},
        "projects": _projects(projects),
    }


# ---------------------------------------------------------------------------
def _table(rows: list[tuple[str, Any]]) -> list[str]:
    lines = ["| | |", "|---|---:|"]
    lines.extend(f"| {k} | {v} |" for k, v in rows)
    return lines


def render_coverage_markdown(report: dict[str, Any]) -> str:
    t = report["totals"]
    out = [
        "# Catalog coverage",
        "",
        f"Generated {report['generated_at']}. "
        "Local report: it names personal files and is never committed.",
        "",
        "## Totals",
        "",
        *_table(
            [
                ("Roots", t["roots"]),
                ("Files discovered by the last scans", t["files_discovered"]),
                ("Catalog entries", t["entries"]),
                ("Catalogued", t["catalogued"]),
                ("Unsupported (with reasons)", t["unsupported"]),
                ("Failed (retried next scan)", t["failed"]),
                ("Missing since an earlier scan", t["missing"]),
                ("Skipped by the scan (with reasons)", t["skipped_by_scan"]),
                ("Not yet accounted for", t["unaccounted"]),
                ("Archives", t["archives"]),
                ("Archive members indexed", t["archive_members_indexed"]),
                ("Searchable units", t["units"]),
                ("Exact duplicate copies", t["duplicates"]),
            ]
        ),
    ]
    for section in report["roots"]:
        name = section["collection"] or "Source Vault"
        finished = (section["last_completed_scan"] or {}).get("finished_at")
        entries = section["entries"]
        out += [
            "",
            f"## {name} (`{section['root_key']}`)",
            "",
            f"Available: {'yes' if section['available'] else 'no'}. "
            f"Last completed scan: {finished or 'never'}.",
            "",
            *_table(
                [
                    ("Files discovered", section["discovered"]["files"]),
                    ("Folders walked", section["discovered"]["directories"]),
                    ("Entries", entries["total"]),
                    *[(f"Status {k}", v) for k, v in sorted(entries["by_status"].items())],
                    *[(f"Kind {k}", v) for k, v in sorted(entries["by_kind"].items())],
                    *[(f"Material {k}", v) for k, v in sorted(entries["by_material"].items())],
                    ("Series folders", entries["series"]),
                    *[(f"Hash {k}", v) for k, v in sorted(section["hashes"].items())],
                    ("Archives", section["archives"]["total"]),
                    *[
                        (f"Archive view {k}", v)
                        for k, v in sorted(section["archives"]["by_view"].items())
                    ],
                    ("Archive members indexed", section["archives"]["members_indexed"]),
                    ("Image members", section["archives"]["image_members"]),
                    ("Video members", section["archives"]["video_members"]),
                    *[(f"Units {k}", v) for k, v in sorted(section["units"]["by_kind"].items())],
                    *[
                        (f"Confidence {k}", v)
                        for k, v in sorted(section["units"]["by_confidence"].items())
                    ],
                    ("Units with flags", section["units"]["flagged"]),
                    ("Exact duplicate copies", section["duplicates"]["extra_copies"]),
                ]
            ),
        ]
        if section["units"]["episodes_by_series"]:
            out += ["", "### Episodes by series", ""]
            out += [f"- {k}: {v}" for k, v in section["units"]["episodes_by_series"].items()]
        if section["units"]["chapters_by_series"]:
            out += ["", "### Manga chapters by series", ""]
            out += [f"- {k}: {v}" for k, v in section["units"]["chapters_by_series"].items()]
        out += ["", "### Not searchable, and why", ""]
        ns = section["not_searchable"]
        out += [
            f"- Unsupported: {ns['unsupported']} (not media Continuum can use; reasons below)",
            f"- Failed: {ns['failed']} (could not be read; retried by the next scan)",
            f"- Missing: {ns['missing']} "
            "(gone since an earlier scan; progress and references are kept)",
            f"- Catalogued without units: {ns['catalogued_without_units']}",
            f"- Skipped by the scan: {ns['skipped_by_scan']}",
        ]
        for title, rows, key in (
            ("Unsupported", section["unsupported"], "reason"),
            ("Failed", section["failed"], "error"),
            ("Missing", section["missing"], "reason"),
        ):
            if rows:
                out += ["", f"#### {title}", ""]
                out += [f"- `{r['relative']}` - {r[key] or r['reason'] or ''}" for r in rows]
        skipped = section["discovered"]["skipped_by_reason"]
        if skipped:
            out += ["", "#### Skipped by the scan", ""]
            out += [f"- {reason}: {count}" for reason, count in sorted(skipped.items())]
        low = section["units"]["low_confidence"]
        if low:
            out += ["", "### Uncertain identifications (LOW confidence)", ""]
            out += [
                f"- `{r['relative']}` - {r['label']}: {'; '.join(r['flags']) or 'no evidence'}"
                for r in low
            ]
    refs = report["references"]
    out += [
        "",
        "## References",
        "",
        *_table(
            [
                ("References", refs["total"]),
                *[(f"Origin {k}", v) for k, v in sorted(refs["by_origin"].items())],
                *[(f"Class {k}", v) for k, v in sorted(refs["by_class"].items())],
                *[(f"Collection '{k}'", v) for k, v in sorted(refs["by_collection"].items())],
                *[(f"Rights {k}", v) for k, v in sorted(refs["rights_status"].items())],
                *[(f"Training {k}", v) for k, v in sorted(refs["training_eligibility"].items())],
                *[(f"Inbox {k}", v) for k, v in sorted(refs["candidates_by_status"].items())],
            ]
        ),
    ]
    for root_key, summary in sorted((report.get("imports") or {}).items()):
        out += [
            "",
            f"## Import `{root_key}`",
            "",
            "```json",
            json.dumps(summary, indent=2)[:6000],
            "```",
        ]
    projects = report["projects"]
    out += ["", "## Projects", "", f"Projects discovered: {projects['projects']}"]
    for project in projects.get("detail", []):
        out.append(
            f"- `{project['id']}`: {project['documents']} documents "
            f"({project['unfiled']} unfiled) - {project['by_lifecycle']}"
        )
    return "\n".join(out) + "\n"


def write_coverage_report(
    session: Session,
    *,
    derived: DerivedStore | None,
    settings: Any,
    imports: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the coverage report and store it as JSON and Markdown. Returns a summary."""
    if settings is None:
        return {"written": False, "reason": "no settings"}
    projects = ProjectLibrary(settings.project_source_dirs())
    report = build_coverage(session, catalog_roots(settings), projects=projects, imports=imports)
    if derived is None:
        return {"written": False, "totals": report["totals"]}
    stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%dt%H%M%Sz")
    body = json.dumps(report, indent=2, ensure_ascii=False, default=str).encode("utf-8")
    markdown = render_coverage_markdown(report).encode("utf-8")
    written = [
        write_report(derived, "catalog", "coverage-latest.json", body),
        write_report(derived, "catalog", "coverage-latest.md", markdown),
        write_report(derived, "catalog", f"coverage-{stamp}.json", body),
    ]
    return {
        "written": True,
        "files": [w.relative for w in written],
        "totals": report["totals"],
    }
