"""The full-Vault catalog as durable, resumable jobs (Phase 1.5).

* ``library.catalog_scan`` - survey one root, observe its files in batches,
  then close the scan (mark what vanished, name exact duplicates, write the
  coverage report). A crash resumes at the first unfinished batch; a batch
  re-run is a no-op because unchanged files are never reopened.
* ``library.catalog_hash`` - stream the SHA-256 of every catalogued file that
  lacks a hash valid for its current size and mtime, one file per unit, then
  re-link exact duplicates. Files hashed before, or by the acquisition engine,
  are skipped - a restart never re-hashes the Vault.

Both write catalog rows through the job session, so each unit's effect commits
together with its completion record under the worker's ownership lock
(ADR-0002). Neither can write to a catalog root: every read goes through the
read-only survey layer.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import uuid
from collections.abc import Sequence
from typing import Any, ClassVar

from continuum_core import ContinuumError, ErrorCategory
from continuum_jobs import JobContext, UnitOutcome, UnitSpec
from continuum_library import ReferenceCatalog
from continuum_library.collection_import import (
    CollectionImport,
    import_report,
    render_import_markdown,
)
from continuum_library.coverage import write_coverage_report
from continuum_library.members import extract_member
from continuum_library.vault_catalog import VaultCatalog, work_map, works_aliases
from continuum_library.vault_jobs import (
    CATALOG_HASH_JOB,
    CATALOG_SCAN_JOB,
    INTAKE_IMPORT_JOB,
    MEMBER_EXTRACT_JOB,
)
from continuum_storage import AcquisitionStore, DerivedStore, engine_index_records, write_report
from continuum_storage.member_cache import MemberCache
from continuum_storage.survey import CatalogRoot, SurveyedFile, catalog_roots, survey_root

__all__ = [
    "SCAN_BATCH_FILES",
    "CatalogHashHandler",
    "CatalogScanHandler",
    "CollectionImportHandler",
    "MemberExtractHandler",
]

#: Files observed per unit. Small enough that a resumed scan repeats little,
#: large enough that a 2,500-file Vault is about a hundred units, not thousands.
SCAN_BATCH_FILES = 25


class CatalogPayloadError(ContinuumError):
    code = "catalog.bad_payload"
    category = ErrorCategory.PERMANENT_INPUT


def _root(ctx: JobContext) -> CatalogRoot:
    settings: Any = ctx.settings
    key = str(ctx.payload.get("root_key") or "")
    if settings is None:
        raise CatalogPayloadError("The catalog job has no settings to find its folders.")
    for root in catalog_roots(settings):
        if root.key == key:
            return root
    raise CatalogPayloadError(
        "The catalog job names a folder that is not configured.",
        technical_detail=f"root_key={key!r}",
        remediation="Configure the folder (CONTINUUM_SOURCE_VAULT_ROOT or CONTINUUM_INTAKE_ROOTS).",
    )


#: One document reader per acquisition folder: it re-parses a document only when
#: the file changes, so a hundred units do not parse the engine index a hundred times.
_STORES: dict[str, AcquisitionStore] = {}


def _catalog(ctx: JobContext, root: CatalogRoot) -> VaultCatalog:
    settings: Any = ctx.settings
    engine: dict[str, Any] = {}
    aliases: dict[str, tuple[str, ...]] = {}
    works: dict[str, tuple[str, str]] = {}
    if root.is_vault:
        directory = str(settings.acquisition_dir())
        store = _STORES.setdefault(directory, AcquisitionStore(directory))
        engine = engine_index_records(store, settings.root("source_vault"))
        aliases = works_aliases(store.read("works-catalog.json"))
        works = work_map(store.read("vault-coverage.json"), store.read("vault-layout.json"))
    return VaultCatalog(ctx.session, [root], engine_records=engine, aliases=aliases, works=works)


class CatalogScanHandler:
    job_type: ClassVar[str] = CATALOG_SCAN_JOB

    def plan(self, ctx: JobContext) -> Sequence[UnitSpec]:
        root = _root(ctx)
        survey = survey_root(root)
        catalog = _catalog(ctx, root)
        scan = catalog.scan_for_job(root.key, ctx.job_id)
        catalog.record_survey(scan, survey)
        units: list[UnitSpec] = []
        for index in range(0, len(survey.files), SCAN_BATCH_FILES):
            batch = survey.files[index : index + SCAN_BATCH_FILES]
            digest = hashlib.sha256(
                "\x00".join(f"{f.relative}\x01{f.size}\x01{f.mtime_ns}" for f in batch).encode()
            ).hexdigest()[:32]
            units.append(
                UnitSpec(
                    unit_key=f"observe:{digest}",
                    ordinal=len(units),
                    payload={"files": [[f.relative, f.size, f.mtime_ns] for f in batch]},
                )
            )
        units.append(
            UnitSpec(unit_key="finish", ordinal=len(units), payload={"scan_id": str(scan.id)})
        )
        return units

    def execute_unit(self, ctx: JobContext, unit: UnitSpec) -> UnitOutcome:
        root = _root(ctx)
        catalog = _catalog(ctx, root)
        scan = catalog.scan_for_job(root.key, ctx.job_id)
        if unit.unit_key == "finish":
            counts = catalog.finish_scan(scan)
            report = write_coverage_report(
                ctx.session,
                derived=ctx.derived if isinstance(ctx.derived, DerivedStore) else None,
                settings=ctx.settings,
            )
            return UnitOutcome(result={"counts": counts, "report": report})
        states: dict[str, int] = {}
        for relative, size, mtime_ns in unit.payload.get("files", []):
            seen = SurveyedFile(str(relative), int(size), int(mtime_ns))
            outcome = catalog.observe(scan, root, seen)
            states[outcome.state] = states.get(outcome.state, 0) + 1
        return UnitOutcome(result=states)


class CatalogHashHandler:
    job_type: ClassVar[str] = CATALOG_HASH_JOB

    def plan(self, ctx: JobContext) -> Sequence[UnitSpec]:
        root = _root(ctx)
        catalog = _catalog(ctx, root)
        units = [
            UnitSpec(
                unit_key=f"hash:{entry_id}:{size}:{mtime}",
                ordinal=position,
                payload={"entry_id": str(entry_id)},
            )
            for position, (entry_id, size, mtime) in enumerate(
                catalog.entries_needing_hash(root.key)
            )
        ]
        units.append(UnitSpec(unit_key="duplicates", ordinal=len(units)))
        return units

    def execute_unit(self, ctx: JobContext, unit: UnitSpec) -> UnitOutcome:
        root = _root(ctx)
        catalog = _catalog(ctx, root)
        if unit.unit_key == "duplicates":
            return UnitOutcome(result={"relinked": catalog.mark_duplicates()})
        digest = catalog.hash_entry(uuid.UUID(str(unit.payload["entry_id"])))
        return UnitOutcome(result={"hashed": digest is not None})


#: Intake entries settled per unit: small, because each may store an image.
IMPORT_BATCH_ENTRIES = 10


def _derived(ctx: JobContext) -> DerivedStore:
    if not isinstance(ctx.derived, DerivedStore):
        raise CatalogPayloadError("This job needs writable storage, and the worker has none.")
    return ctx.derived


class CollectionImportHandler:
    job_type: ClassVar[str] = INTAKE_IMPORT_JOB

    def _importer(self, ctx: JobContext) -> CollectionImport:
        root = _root(ctx)
        return CollectionImport(
            ctx.session, ReferenceCatalog(ctx.session, derived=_derived(ctx)), root
        )

    def plan(self, ctx: JobContext) -> Sequence[UnitSpec]:
        importer = self._importer(ctx)
        batch = importer.batch(f"{importer.root.collection} collection import")
        ids = importer.entry_ids()
        units = [
            UnitSpec(
                unit_key="settle:"
                + hashlib.sha256(
                    "|".join(str(i) for i in ids[start : start + IMPORT_BATCH_ENTRIES]).encode()
                ).hexdigest()[:32],
                ordinal=start // IMPORT_BATCH_ENTRIES,
                payload={
                    "entries": [str(i) for i in ids[start : start + IMPORT_BATCH_ENTRIES]],
                    "batch_id": str(batch.id),
                },
            )
            for start in range(0, len(ids), IMPORT_BATCH_ENTRIES)
        ]
        units.append(UnitSpec(unit_key="report", ordinal=len(units)))
        return units

    def execute_unit(self, ctx: JobContext, unit: UnitSpec) -> UnitOutcome:
        importer = self._importer(ctx)
        if unit.unit_key == "report":
            report = import_report(ctx.session, importer.root)
            slug = importer.root.key.split(":", 1)[-1]
            derived = _derived(ctx)
            body = json.dumps(report, indent=2, ensure_ascii=False).encode("utf-8")
            write_report(derived, "imports", f"{slug}-latest.json", body)
            write_report(
                derived,
                "imports",
                f"{slug}-latest.md",
                render_import_markdown(report).encode("utf-8"),
            )
            stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%dt%H%M%Sz")
            write_report(derived, "imports", f"{slug}-{stamp}.json", body)
            return UnitOutcome(result={"totals": report["totals"]})
        states: dict[str, int] = {}
        batch_id = uuid.UUID(str(unit.payload["batch_id"]))
        for raw in unit.payload.get("entries", []):
            outcome = importer.settle(uuid.UUID(str(raw)), batch_id=batch_id)
            states[outcome["state"]] = states.get(outcome["state"], 0) + 1
        return UnitOutcome(result=states)


class MemberExtractHandler:
    job_type: ClassVar[str] = MEMBER_EXTRACT_JOB

    def plan(self, ctx: JobContext) -> Sequence[UnitSpec]:
        try:
            uuid.UUID(str(ctx.payload.get("member_id")))
        except ValueError:
            raise CatalogPayloadError("The extraction job does not name a member.") from None
        return [UnitSpec(unit_key="extract", ordinal=0)]

    def execute_unit(self, ctx: JobContext, unit: UnitSpec) -> UnitOutcome:
        settings: Any = ctx.settings
        if settings is None:
            raise CatalogPayloadError("The extraction job has no settings.")
        vault = next((r for r in catalog_roots(settings) if r.is_vault), None)
        if vault is None:
            raise CatalogPayloadError("The Source Vault is not configured.")
        cache = MemberCache(
            _derived(ctx),
            budget_bytes=settings.member_cache_bytes,
            max_member_bytes=settings.member_cache_max_member_bytes,
        )
        result = extract_member(
            ctx.session, uuid.UUID(str(ctx.payload["member_id"])), root=vault, cache=cache
        )
        return UnitOutcome(result=result)
