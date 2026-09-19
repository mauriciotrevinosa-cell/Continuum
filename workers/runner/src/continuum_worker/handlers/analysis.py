"""Page analysis as a durable, resumable job (Visual Knowledge, M3).

One unit per page of the deterministic grammar sample. A unit re-run after a
crash finds the stored analysis and does nothing; a page that cannot be read
(the Vault is not connected) is reported, not fatal. Pages are read only
through the read-only storage layer; results are rows without pixels.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, ClassVar

from continuum_core import ContinuumError, ErrorCategory
from continuum_db.session import session_scope
from continuum_jobs import JobContext, UnitOutcome, UnitSpec
from continuum_library import ReferenceCatalog
from continuum_library.catalog_records import CatalogRecordSupplement
from continuum_production.analysis_jobs import (
    ANALYZE_PAGES_JOB,
    analyzer_for,
    grammar_sample,
    measure_page,
    unit_of,
    unit_payload,
)
from continuum_production.manga import source_page_reader
from continuum_storage import AcquisitionStore, MediaLibrary, SourceAccess

__all__ = ["PageAnalysisHandler"]


class AnalysisPayloadError(ContinuumError):
    code = "analysis.bad_payload"
    category = ErrorCategory.PERMANENT_INPUT


class PageAnalysisHandler:
    job_type: ClassVar[str] = ANALYZE_PAGES_JOB

    def __init__(self) -> None:
        self._sources: dict[tuple[str, str], SourceAccess] = {}

    def plan(self, ctx: JobContext) -> Sequence[UnitSpec]:
        series = [str(s) for s in ctx.payload.get("series_keys") or []]
        per_series = int(ctx.payload.get("per_series") or 12)
        if not series:
            raise AnalysisPayloadError("This analysis job names no series.")
        analyzer = analyzer_for(str(ctx.payload.get("analyzer_id") or ""))
        return [
            UnitSpec(
                unit_key=f"{analyzer.info.id}@{analyzer.info.version}:{unit.unit_key}:{offset}",
                ordinal=position,
                payload=unit_payload(series_key, unit, offset),
            )
            for position, (series_key, unit, _entry, offset) in enumerate(
                grammar_sample(ctx.session, series, per_series * len(series))
            )
        ]

    def execute_unit(self, ctx: JobContext, unit: UnitSpec) -> UnitOutcome:
        analyzer = analyzer_for(str(ctx.payload.get("analyzer_id") or ""))
        found = unit_of(ctx.session, dict(unit.payload or {}))
        if found is None:
            return UnitOutcome(result={"analysed": False, "reason": "the chapter left the catalog"})
        chapter, entry = found
        catalog = ReferenceCatalog(
            ctx.session, sources=self._source_access(ctx), derived=ctx.derived
        )
        measured = measure_page(
            ctx.session,
            source_page_reader(catalog),
            analyzer,
            chapter,
            entry,
            int((unit.payload or {})["offset"]),
        )
        if measured is None:
            return UnitOutcome(result={"analysed": False, "reason": "the page could not be read"})
        _locator, result, fresh = measured
        return UnitOutcome(
            result={
                "analysed": fresh,
                "panels": int((result.get("measures") or {}).get("panel_count", 0)),
            }
        )

    def _source_access(self, ctx: JobContext) -> SourceAccess | None:
        settings: Any = ctx.settings
        if settings is None:
            return None
        vault = settings.root("source_vault")
        documents = settings.acquisition_dir()
        key = (str(vault), str(documents))
        if key not in self._sources:
            media = MediaLibrary(
                AcquisitionStore(documents),
                vault,
                supplement=CatalogRecordSupplement(lambda: session_scope(settings), vault),
            )
            self._sources[key] = SourceAccess(media, vault)
        return self._sources[key]
