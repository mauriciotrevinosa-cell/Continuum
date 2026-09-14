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

import hashlib
import uuid
from collections.abc import Sequence
from typing import Any, ClassVar

from continuum_core import ContinuumError, ErrorCategory
from continuum_jobs import JobContext, UnitOutcome, UnitSpec
from continuum_library.coverage import write_coverage_report
from continuum_library.vault_catalog import VaultCatalog, works_aliases
from continuum_library.vault_jobs import CATALOG_HASH_JOB, CATALOG_SCAN_JOB
from continuum_storage import AcquisitionStore, DerivedStore, engine_index_records
from continuum_storage.survey import CatalogRoot, SurveyedFile, catalog_roots, survey_root

__all__ = ["SCAN_BATCH_FILES", "CatalogHashHandler", "CatalogScanHandler"]

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
    if root.is_vault:
        directory = str(settings.acquisition_dir())
        store = _STORES.setdefault(directory, AcquisitionStore(directory))
        engine = engine_index_records(store, settings.root("source_vault"))
        aliases = works_aliases(store.read("works-catalog.json"))
    return VaultCatalog(ctx.session, [root], engine_records=engine, aliases=aliases)


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
