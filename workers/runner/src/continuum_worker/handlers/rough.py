"""The Phase 1 rough attempt renderer, as a durable job handler.

One unit per attempt. The effect - derived bytes under ``generated/`` - is
content-addressed, and the attempt's rows are written into the job session so
they commit with the step completion under the worker's ownership lock
(ADR-0002). A missing provider or an unreachable source raises an error that
carries ``blocked_reason``; the worker parks the job BLOCKED with remediation.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any, ClassVar

from continuum_core import ContinuumError, ErrorCategory
from continuum_db.session import session_scope
from continuum_jobs import JobContext, UnitOutcome, UnitSpec
from continuum_library import ReferenceCatalog
from continuum_library.catalog_records import CatalogRecordSupplement
from continuum_production import ROUGH_JOB_TYPE, render_attempt
from continuum_storage import AcquisitionStore, MediaLibrary, SourceAccess

__all__ = ["RoughAttemptHandler"]


class RoughPayloadError(ContinuumError):
    code = "production.bad_payload"
    category = ErrorCategory.PERMANENT_INPUT


class RoughAttemptHandler:
    job_type: ClassVar[str] = ROUGH_JOB_TYPE

    def __init__(self) -> None:
        self._sources: dict[tuple[str, str], SourceAccess] = {}

    def plan(self, ctx: JobContext) -> Sequence[UnitSpec]:
        self._attempt_id(ctx)
        return [UnitSpec(unit_key="render", ordinal=0)]

    def execute_unit(self, ctx: JobContext, unit: UnitSpec) -> UnitOutcome:
        catalog = ReferenceCatalog(
            ctx.session, sources=self._source_access(ctx), derived=ctx.derived
        )
        result = render_attempt(
            ctx.session, self._attempt_id(ctx), catalog=catalog, providers=ctx.providers
        )
        return UnitOutcome(result=result)

    @staticmethod
    def _attempt_id(ctx: JobContext) -> uuid.UUID:
        try:
            return uuid.UUID(str(ctx.payload["attempt_id"]))
        except (KeyError, ValueError):
            raise RoughPayloadError(
                "This rough job does not name its attempt.",
                technical_detail=f"payload keys={sorted(ctx.payload)}",
            ) from None

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
