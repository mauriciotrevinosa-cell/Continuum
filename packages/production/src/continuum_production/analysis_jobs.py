"""Durable page-analysis jobs (Visual Knowledge, M3).

``visual.analyze_pages`` analyses a deterministic sample of catalogued manga
pages - the same pages grammar retrieval uses - with a named analyzer, one page
per job unit. A unit whose page already has an analysis from that analyzer
version is a no-op, so a crashed or repeated job resumes without re-reading
anything; pages are read only through the read-only storage layer and results
hold no pixels.
"""

from __future__ import annotations

import hashlib
import re
import uuid
from collections.abc import Callable, Iterator, Sequence
from typing import Any

from continuum_core.catalog import UnitKind
from continuum_db.models import CatalogEntry, CatalogUnit, Job
from continuum_jobs import enqueue
from continuum_library import CatalogInputError
from continuum_library.analysis import PageAnalyses, unit_subject
from continuum_providers.analysis import GutterLayoutAnalyzer, MangaPageAnalyzer
from sqlalchemy import func, select
from sqlalchemy.orm import Session

__all__ = [
    "ANALYZERS",
    "ANALYZE_PAGES_JOB",
    "analyzer_for",
    "grammar_sample",
    "grammar_series",
    "measure_page",
    "request_page_analysis",
    "unit_of",
    "unit_payload",
]

ANALYZE_PAGES_JOB = "visual.analyze_pages"
#: Analyzers a job may name. A pretrained detector is added here once its
#: weights, license and registry resource are recorded.
ANALYZERS: dict[str, Callable[[], MangaPageAnalyzer]] = {
    GutterLayoutAnalyzer.info.id: GutterLayoutAnalyzer,
}
MAX_SERIES = 200
MAX_PER_SERIES = 200
#: Unit keys the analysis store can key on (content-derived hex digests).
_PERSISTABLE_UNIT = re.compile(r"^[0-9a-f]{16,64}$")

PageReader = Callable[[CatalogUnit, CatalogEntry, int], tuple[str, bytes] | None]


def measure_page(
    session: Session,
    read_page: PageReader,
    analyzer: MangaPageAnalyzer,
    unit: CatalogUnit,
    entry: CatalogEntry,
    offset: int,
) -> tuple[str, dict[str, Any], bool] | None:
    """(locator, analysis, freshly measured) for one catalogued page.

    A stored analysis from the same analyzer version is returned without reading
    the page; otherwise the page is read (read-only), analysed and stored once.
    None when the page cannot be read.
    """
    analyses = PageAnalyses(session)
    subject = unit_subject(unit.unit_key, offset)
    persist = _PERSISTABLE_UNIT.match(unit.unit_key) is not None
    if persist:
        stored = analyses.get(subject, analyzer.info)
        if stored is not None:
            return stored.locator, stored.result, False
    found = read_page(unit, entry, offset)
    if found is None:
        return None
    locator, data = found
    result = analyzer.analyze_page(data).as_dict()
    if persist:
        analyses.record(
            subject,
            locator=locator,
            analyzer=analyzer.info,
            result=result,
            content_sha256=hashlib.sha256(data).hexdigest(),
        )
    return locator, result, True


def analyzer_for(analyzer_id: str) -> MangaPageAnalyzer:
    factory = ANALYZERS.get(analyzer_id)
    if factory is None:
        raise CatalogInputError(
            f"No page analyzer {analyzer_id!r}.", remediation=f"Known: {', '.join(ANALYZERS)}."
        )
    return factory()


def grammar_series(session: Session, *, min_chapters: int = 5) -> list[str]:
    """Catalogued manga series with enough chapters to sample page craft from."""
    keys = session.execute(
        select(CatalogUnit.series_key)
        .where(
            CatalogUnit.kind == UnitKind.MANGA_CHAPTER,
            CatalogUnit.series_key.is_not(None),
        )
        .group_by(CatalogUnit.series_key)
        .having(func.count() >= min_chapters)
        .order_by(CatalogUnit.series_key)
    ).scalars()
    return [key for key in keys if key]


def grammar_sample(
    session: Session, series: Sequence[str], pool: int
) -> Iterator[tuple[str, CatalogUnit, CatalogEntry, int]]:
    """The deterministic page sample: per series, chapters in reading order at an even
    stride, one interior page each. Shared by grammar retrieval and analysis jobs."""
    if not series:
        return
    per_series = max(1, pool // len(series))
    for series_key in series:
        rows = session.execute(
            select(CatalogUnit, CatalogEntry)
            .join(CatalogEntry, CatalogEntry.id == CatalogUnit.entry_id)
            .where(
                CatalogUnit.series_key == series_key,
                CatalogUnit.kind == UnitKind.MANGA_CHAPTER,
                CatalogEntry.duplicate_of_id.is_(None),
            )
            .order_by(CatalogUnit.sort_key)
        ).all()
        if not rows:
            continue
        stride = max(1, len(rows) // per_series)
        for unit, entry in rows[::stride][:per_series]:
            yield series_key, unit, entry, max(1, (unit.page_count or 2) // 2)


def request_page_analysis(
    session: Session,
    *,
    series_keys: Sequence[str] = (),
    per_series: int = 12,
    analyzer_id: str = GutterLayoutAnalyzer.info.id,
) -> tuple[Job, bool]:
    """Queue the analysis of the grammar sample of these series (all eligible when empty)."""
    analyzer_for(analyzer_id)
    if not 1 <= per_series <= MAX_PER_SERIES:
        raise CatalogInputError(f"Analyse 1-{MAX_PER_SERIES} pages per series.")
    series = sorted(set(series_keys)) or grammar_series(session)
    if not series:
        raise CatalogInputError("No catalogued manga series to analyse yet.")
    if len(series) > MAX_SERIES:
        raise CatalogInputError(f"Analyse at most {MAX_SERIES} series per job.")
    payload: dict[str, Any] = {
        "series_keys": series,
        "per_series": per_series,
        "analyzer_id": analyzer_id,
    }
    return enqueue(session, ANALYZE_PAGES_JOB, payload=payload, resource_class="cpu")


def unit_payload(series_key: str, unit: CatalogUnit, offset: int) -> dict[str, Any]:
    return {"series_key": series_key, "unit_id": str(unit.id), "offset": offset}


def unit_of(session: Session, payload: dict[str, Any]) -> tuple[CatalogUnit, CatalogEntry] | None:
    unit = session.get(CatalogUnit, uuid.UUID(str(payload["unit_id"])))
    if unit is None:
        return None
    entry = session.get(CatalogEntry, unit.entry_id)
    return (unit, entry) if entry is not None else None
