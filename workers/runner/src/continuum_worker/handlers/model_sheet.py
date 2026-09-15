"""Durable W4 character model-sheet renderer."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any, ClassVar

from continuum_core import ContinuumError, ErrorCategory
from continuum_db.session import session_scope
from continuum_jobs import JobContext, UnitOutcome, UnitSpec
from continuum_library import ReferenceCatalog
from continuum_library.catalog_records import CatalogRecordSupplement
from continuum_production.corpus import CharacterCorpus
from continuum_production.manga import source_page_reader
from continuum_production.model_builder import MODEL_SHEET_JOB_TYPE, render_model_sheet
from continuum_storage import AcquisitionStore, MediaLibrary, SourceAccess


class ModelSheetPayloadError(ContinuumError):
    code = "production.bad_model_sheet_payload"
    category = ErrorCategory.PERMANENT_INPUT


class CharacterModelSheetHandler:
    job_type: ClassVar[str] = MODEL_SHEET_JOB_TYPE

    def __init__(self) -> None:
        self._sources: dict[tuple[str, str], SourceAccess] = {}

    def plan(self, ctx: JobContext) -> Sequence[UnitSpec]:
        self._attempt_id(ctx)
        return [UnitSpec(unit_key="render", ordinal=0)]

    def execute_unit(self, ctx: JobContext, unit: UnitSpec) -> UnitOutcome:
        catalog = ReferenceCatalog(
            ctx.session, sources=self._source_access(ctx), derived=ctx.derived
        )
        corpus = CharacterCorpus(ctx.session, catalog, page_reader=source_page_reader(catalog))
        return UnitOutcome(
            result=render_model_sheet(
                ctx.session,
                self._attempt_id(ctx),
                catalog=catalog,
                providers=ctx.providers,
                corpus=corpus,
            )
        )

    @staticmethod
    def _attempt_id(ctx: JobContext) -> uuid.UUID:
        try:
            return uuid.UUID(str(ctx.payload["attempt_id"]))
        except (KeyError, ValueError):
            raise ModelSheetPayloadError(
                "This model-sheet job does not name its attempt."
            ) from None

    def _source_access(self, ctx: JobContext) -> SourceAccess | None:
        settings: Any = ctx.settings
        if settings is None:
            return None
        vault, documents = settings.root("source_vault"), settings.acquisition_dir()
        key = (str(vault), str(documents))
        if key not in self._sources:
            media = MediaLibrary(
                AcquisitionStore(documents),
                vault,
                supplement=CatalogRecordSupplement(lambda: session_scope(settings), vault),
            )
            self._sources[key] = SourceAccess(media, vault)
        return self._sources[key]
