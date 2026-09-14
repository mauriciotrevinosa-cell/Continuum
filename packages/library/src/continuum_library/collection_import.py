"""Importing a whole intake collection (for example collected fan art) as references.

Every file the catalog observed in an intake folder is settled exactly once:

* **images** become references - reference class ``UNSORTED`` (no person has
  decided what they are for), origin ``FAN_ART`` for a fan-art collection, the
  collection name, creator handle and posting date read from the download-style
  file name when it follows that convention, ``rights_status = UNKNOWN`` and
  ``training_eligibility = MANUAL_REVIEW``;
* **video clips** become Inbox candidates with the same metadata, so frames
  can be captured from them;
* **exact duplicates** (same bytes) are linked to the first copy - within the
  collection or already in the library - and create nothing;
* **visually similar but different files are separate** - nothing perceptual
  is decided on anyone's behalf;
* **unsupported files** (installers, documents) are rejected with the reason
  the catalog recorded; files that cannot be read are reported as failed.

Originals are preserved byte for byte under the library root (HEIC/HEIF keep
their original beside a deterministic PNG rendition). The intake folder is only
read: nothing there is moved, renamed or deleted. The original file name and
its path inside the collection are kept as provenance.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from continuum_core import content_hash_bytes
from continuum_core.catalog import (
    DetectedKind,
    EntryStatus,
    MaterialClass,
    RightsStatus,
    TrainingEligibility,
)
from continuum_core.references import (
    AssetMedium,
    AssetOrigin,
    CandidateStatus,
    IntakeKind,
    ReferenceClass,
    ReferenceOrigin,
)
from continuum_db.models import CatalogEntry, IntakeBatch, ReferenceCandidate, ReferenceItem
from continuum_imaging import UnsupportedImageError, sniff
from continuum_storage import MediaUnavailableError, SourceChangedError
from continuum_storage.survey import (
    CatalogRoot,
    FileChangedError,
    SurveyReadError,
    read_catalog_file,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from continuum_library.catalog import (
    LIBRARY_ROOT,
    MAX_UPLOAD_IMAGE_BYTES,
    ReferenceCatalog,
    ReferenceSpec,
)
from continuum_library.inbox import MAX_UPLOAD_VIDEO_BYTES, ReferenceInbox
from continuum_library.validation import CatalogInputError, clean_handle

__all__ = [
    "IMPORT_SCHEMA",
    "CollectionImport",
    "import_report",
    "render_import_markdown",
]

IMPORT_SCHEMA = "continuum.collection-import/1"
_IMPORTED = ("imported", "linked_duplicate", "linked_existing")


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


class CollectionImport:
    """Settle the entries of one intake root. The caller commits."""

    def __init__(self, session: Session, catalog: ReferenceCatalog, root: CatalogRoot) -> None:
        if root.is_vault:
            raise CatalogInputError(
                "Collections are imported from intake folders, not the Source Vault."
            )
        self.session = session
        self.catalog = catalog
        self.inbox = ReferenceInbox(catalog)
        self.root = root

    @property
    def origin(self) -> ReferenceOrigin:
        return (
            ReferenceOrigin.FAN_ART
            if self.root.material == "fan_art"
            else ReferenceOrigin.USER_CREATED
        )

    def entry_ids(self) -> list[uuid.UUID]:
        return list(
            self.session.execute(
                select(CatalogEntry.id)
                .where(CatalogEntry.root_key == self.root.key)
                # First copies before their exact duplicates, so "file (1).jpg" links
                # to "file.jpg" and not the other way round.
                .order_by(CatalogEntry.duplicate_of_id.is_not(None), CatalogEntry.relative_path)
            ).scalars()
        )

    def batch(self, label: str) -> IntakeBatch:
        existing = self.session.execute(
            select(IntakeBatch)
            .where(IntakeBatch.label == label)
            .order_by(IntakeBatch.created_at.desc(), IntakeBatch.id.desc())
            .limit(1)
        ).scalar_one_or_none()
        if existing is not None:
            return existing
        created = IntakeBatch(
            kind=IntakeKind.VIDEO,
            label=label[:200],
            notes="Video clips from a collection import. Images became references directly.",
        )
        self.session.add(created)
        self.session.flush()
        return created

    # -- one entry ------------------------------------------------------------
    def settle(self, entry_id: uuid.UUID, *, batch_id: uuid.UUID) -> dict[str, Any]:
        entry = self.session.get(CatalogEntry, entry_id)
        if entry is None or entry.root_key != self.root.key:
            return {"state": "unknown"}
        previous = (entry.facts or {}).get("import") or {}
        if previous.get("state") in _IMPORTED and self._target_exists(previous):
            return self._record(entry, {**previous, "state": previous["state"]}, keep_time=True)
        if entry.status is EntryStatus.UNSUPPORTED:
            return self._record(entry, {"state": "rejected", "reason": entry.status_reason})
        if entry.status is EntryStatus.MISSING:
            return self._record(
                entry, {"state": "missing", "reason": "The file is no longer in the folder."}
            )
        if entry.status is EntryStatus.FAILED:
            return self._record(
                entry, {"state": "failed", "reason": entry.status_reason or "Unreadable."}
            )
        if entry.detected_kind not in (DetectedKind.IMAGE, DetectedKind.VIDEO):
            return self._record(
                entry, {"state": "rejected", "reason": "Only images and video clips are imported."}
            )
        limit = (
            MAX_UPLOAD_IMAGE_BYTES
            if entry.detected_kind is DetectedKind.IMAGE
            else MAX_UPLOAD_VIDEO_BYTES
        )
        if entry.byte_size > limit:
            return self._record(
                entry,
                {
                    "state": "rejected",
                    "reason": f"Larger than {limit // (1024 * 1024)} MB; not imported.",
                },
            )
        try:
            data = self._read(entry)
        except (OSError, ValueError, SourceChangedError, MediaUnavailableError) as exc:
            return self._record(entry, {"state": "failed", "reason": str(exc)[:500]})
        digest = content_hash_bytes(data)

        first = self._first_copy(entry, digest)
        if first is not None:
            first_import = (first.facts or {}).get("import") or {}
            return self._record(
                entry,
                {
                    "state": "linked_duplicate",
                    "duplicate_of_entry": str(first.id),
                    "duplicate_of_file": first.file_name,
                    "reference_id": first_import.get("reference_id"),
                    "candidate_id": first_import.get("candidate_id"),
                    "sha256": digest,
                },
            )
        existing = self.inbox._duplicate(digest)
        if existing.duplicate_of is not None or existing.duplicate_reference_id is not None:
            return self._record(
                entry,
                {
                    "state": "linked_existing",
                    "reference_id": str(existing.duplicate_reference_id)
                    if existing.duplicate_reference_id
                    else None,
                    "candidate_id": str(existing.duplicate_of.id)
                    if existing.duplicate_of
                    else None,
                    "sha256": digest,
                },
            )

        facts = entry.facts or {}
        handle = clean_handle(facts.get("creator_handle")) if facts.get("creator_handle") else None
        posted = _parse_time(facts.get("posted_at"))
        provenance: dict[str, Any] = {
            "kind": "collection_import",
            "source": "local_intake",
            "collection": self.root.collection,
            "original_file_name": entry.file_name,
            "original_relative_path": entry.relative_path,
            "original_sha256": digest,
            "original_bytes": len(data),
            "detected_format": entry.detected_format,
            "catalog_entry_id": str(entry.id),
            "imported_at": _now().isoformat(timespec="seconds"),
        }
        if handle:
            provenance["creator_handle_source"] = "filename"
        for key in ("posted_at", "source_post_id", "extension_mismatch"):
            if facts.get(key):
                provenance[key] = facts[key]

        sniffed = sniff(data[:512])
        if entry.detected_kind is DetectedKind.IMAGE and sniffed.kind == "image":
            try:
                stored = self.catalog._store_image(data)
            except (UnsupportedImageError, CatalogInputError) as exc:
                reason = getattr(exc, "user_message", str(exc))
                return self._record(entry, {"state": "rejected", "reason": str(reason)[:500]})
            if stored.conversion:
                provenance["conversion"] = stored.conversion
            item = self.catalog._create_reference(
                stored.asset,
                self.catalog._image_locator(stored.asset),
                None,
                ReferenceSpec(
                    reference_class=ReferenceClass.UNSORTED,
                    origin=self.origin,
                    label=entry.file_name.rsplit(".", 1)[0][:300],
                    creator_handle=handle,
                ),
                provenance,
            )
            item.collection = self.root.collection
            item.source_posted_at = posted
            item.rights_status = RightsStatus.UNKNOWN
            item.training_eligibility = TrainingEligibility.MANUAL_REVIEW
            self.session.flush()
            return self._record(
                entry, {"state": "imported", "reference_id": str(item.id), "sha256": digest}
            )

        if entry.detected_kind is DetectedKind.VIDEO and sniffed.kind == "video":
            asset = self.catalog.store_bytes(
                data, root_key=LIBRARY_ROOT, medium=AssetMedium.VIDEO, origin=AssetOrigin.USER_ADDED
            )
            candidate = ReferenceCandidate(
                batch_id=batch_id,
                intake_kind=IntakeKind.VIDEO,
                status=CandidateStatus.INBOX,
                creator_handle=handle,
                display_name=entry.file_name[:300],
                asset_id=asset.id,
                origin=self.origin,
                suggested_class=ReferenceClass.UNSORTED,
                intended_uses=[],
                tags=[f"collection:{self.root.collection.lower()}"[:60], "source:local_intake"],
                notes="",
                capture={k: v for k, v in provenance.items() if isinstance(v, (str, int))},
                collection=self.root.collection,
                source_posted_at=posted,
                rights_status=RightsStatus.UNKNOWN,
                training_eligibility=TrainingEligibility.MANUAL_REVIEW,
            )
            self.session.add(candidate)
            self.session.flush()
            return self._record(
                entry, {"state": "imported", "candidate_id": str(candidate.id), "sha256": digest}
            )
        return self._record(
            entry,
            {
                "state": "rejected",
                "reason": f"The bytes are {sniffed.description}, not what was catalogued.",
            },
        )

    # -- helpers --------------------------------------------------------------
    def _read(self, entry: CatalogEntry) -> bytes:
        try:
            return read_catalog_file(
                self.root,
                entry.relative_path,
                expected_size=entry.byte_size,
                expected_mtime_ns=entry.mtime_ns,
            )
        except FileChangedError as exc:
            raise SourceChangedError(exc.user_message) from None
        except SurveyReadError as exc:
            raise OSError(exc.user_message) from None

    def _first_copy(self, entry: CatalogEntry, digest: str) -> CatalogEntry | None:
        rows = self.session.execute(
            select(CatalogEntry).where(
                CatalogEntry.root_key == self.root.key,
                CatalogEntry.id != entry.id,
                CatalogEntry.facts["import"]["sha256"].astext == digest,
                CatalogEntry.facts["import"]["state"].astext == "imported",
            )
        ).scalars()
        return next(iter(rows), None)

    def _target_exists(self, record: dict[str, Any]) -> bool:
        if record.get("reference_id"):
            found = self.session.get(ReferenceItem, uuid.UUID(str(record["reference_id"])))
            return found is not None and found.removed_at is None
        if record.get("candidate_id"):
            return (
                self.session.get(ReferenceCandidate, uuid.UUID(str(record["candidate_id"])))
                is not None
            )
        return record.get("state") == "linked_duplicate"

    def _record(
        self, entry: CatalogEntry, outcome: dict[str, Any], *, keep_time: bool = False
    ) -> dict[str, Any]:
        facts = dict(entry.facts or {})
        stamped = dict(outcome)
        if not keep_time or "at" not in stamped:
            stamped["at"] = _now().isoformat(timespec="seconds")
        facts["import"] = stamped
        entry.facts = facts
        self.session.flush()
        return stamped


def _parse_time(value: Any) -> dt.datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.UTC)


# ---------------------------------------------------------------------------
def import_report(session: Session, root: CatalogRoot) -> dict[str, Any]:
    """What the import of one collection did, entry by entry, from the catalog."""
    entries = list(
        session.execute(
            select(CatalogEntry)
            .where(CatalogEntry.root_key == root.key)
            .order_by(CatalogEntry.relative_path)
        ).scalars()
    )
    by_state: dict[str, list[CatalogEntry]] = {}
    formats: dict[str, int] = {}
    for entry in entries:
        state = ((entry.facts or {}).get("import") or {}).get("state", "not_imported")
        by_state.setdefault(state, []).append(entry)
        formats[entry.detected_format or "?"] = formats.get(entry.detected_format or "?", 0) + 1
    importable = [e for e in entries if e.status is EntryStatus.CATALOGUED]
    imported = by_state.get("imported", [])

    def rows(state: str) -> list[dict[str, Any]]:
        return [
            {
                "file": e.file_name,
                "reason": ((e.facts or {}).get("import") or {}).get("reason"),
                "duplicate_of": ((e.facts or {}).get("import") or {}).get("duplicate_of_file"),
            }
            for e in by_state.get(state, [])
        ]

    return {
        "schema": IMPORT_SCHEMA,
        "root_key": root.key,
        "collection": root.collection,
        "material": root.material or MaterialClass.REFERENCE.value.lower(),
        "generated_at": _now().isoformat(timespec="seconds"),
        "defaults": {
            "class": root.material or "reference",
            "source": "local_intake",
            "collection": root.collection,
            "reference_class": ReferenceClass.UNSORTED.value,
            "rights_status": RightsStatus.UNKNOWN.value,
            "training_eligibility": TrainingEligibility.MANUAL_REVIEW.value,
        },
        "totals": {
            "discovered": len(entries),
            "importable_media": len(importable),
            "imported": len(imported),
            "imported_images_as_references": sum(
                1 for e in imported if e.detected_kind is DetectedKind.IMAGE
            ),
            "imported_clips_as_inbox_candidates": sum(
                1 for e in imported if e.detected_kind is DetectedKind.VIDEO
            ),
            "exact_duplicates_linked": len(by_state.get("linked_duplicate", [])),
            "already_in_library_linked": len(by_state.get("linked_existing", [])),
            "rejected": len(by_state.get("rejected", [])),
            "failed": len(by_state.get("failed", [])),
            "missing": len(by_state.get("missing", [])),
            "not_imported_yet": len(by_state.get("not_imported", [])),
        },
        "formats": formats,
        "rejected": rows("rejected"),
        "failed": rows("failed"),
        "duplicates": rows("linked_duplicate"),
        "unknown_creator": [
            e.file_name for e in importable if not (e.facts or {}).get("creator_handle")
        ],
        "unknown_date": [e.file_name for e in importable if not (e.facts or {}).get("posted_at")],
        "extension_mismatches": [
            {"file": e.file_name, "detail": (e.facts or {}).get("extension_mismatch")}
            for e in entries
            if (e.facts or {}).get("extension_mismatch")
        ],
    }


def render_import_markdown(report: dict[str, Any]) -> str:
    totals = report["totals"]
    lines = [
        f"# Collection import - {report['collection']}",
        "",
        f"Generated {report['generated_at']}. Local report; never committed.",
        "",
        "Defaults applied: "
        + ", ".join(f"{k} = {v}" for k, v in report["defaults"].items())
        + ". Nothing is approved for model training.",
        "",
        "| | |",
        "|---|---:|",
        *[f"| {k.replace('_', ' ')} | {v} |" for k, v in totals.items()],
        "",
        "## Formats (by content)",
        "",
        *[f"- {k}: {v}" for k, v in sorted(report["formats"].items())],
    ]
    for title, key in (("Rejected", "rejected"), ("Failed", "failed")):
        if report[key]:
            lines += ["", f"## {title}", ""]
            lines += [f"- `{r['file']}` - {r['reason']}" for r in report[key]]
    if report["duplicates"]:
        lines += ["", "## Exact duplicates (linked, not stored twice)", ""]
        lines += [f"- `{r['file']}` = `{r['duplicate_of']}`" for r in report["duplicates"]]
    for title, key in (("Unknown creator", "unknown_creator"), ("Unknown date", "unknown_date")):
        lines += ["", f"## {title} ({len(report[key])})", ""]
        lines += [f"- `{name}`" for name in report[key]] or ["- none"]
    if report["extension_mismatches"]:
        lines += ["", "## Named as another format", ""]
        lines += [f"- `{r['file']}` - {r['detail']}" for r in report["extension_mismatches"]]
    return "\n".join(lines) + "\n"
