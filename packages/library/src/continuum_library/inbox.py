"""The Reference Inbox: large-scale intake without organizing every item by hand.

Candidates arrive in batches - a paste of links, a folder of images, a set of
clips, screenshots - carry whatever the user knows (source link, creator
handle, tags, intended uses, suggested class), and are triaged later:
accepted into real references (singly or in bulk), or dismissed.

Boundaries:

* **A link is only a link.** URL candidates are stored and shown; nothing is
  fetched, scraped or downloaded. A link becomes acceptable when the user
  attaches an image or screenshot to it.
* **Bytes are the user's own intake.** Uploaded images, clips and screenshots
  land content-addressed under the writable library root - never in the
  Source Vault.
* **Video is kept, not decoded.** A clip cannot become a reference directly;
  the viewer captures a frame, and the frame keeps the clip's locator and
  instant as provenance.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from typing import Any

from continuum_core.references import (
    AssetMedium,
    AssetOrigin,
    CandidateStatus,
    DescriptorFacet,
    IntakeKind,
    ReferenceClass,
    ReferenceOrigin,
    ReferenceUse,
)
from continuum_db.models import IntakeBatch, LibraryAsset, ReferenceCandidate, ReferenceItem
from continuum_imaging import probe
from continuum_storage import SourceUnavailableError
from sqlalchemy import func, select

from continuum_library.catalog import (
    LIBRARY_ROOT,
    USER_DECLARED_ORIGINS,
    DescriptorSpec,
    ReferenceCatalog,
    ReferenceSpec,
)
from continuum_library.validation import (
    CatalogConflictError,
    CatalogInputError,
    CatalogNotFoundError,
    clean_display_name,
    clean_handle,
    clean_tags,
    clean_text,
    clean_url,
)

__all__ = [
    "MAX_UPLOAD_VIDEO_BYTES",
    "AcceptSpec",
    "CandidateDefaults",
    "IntakeResult",
    "ReferenceInbox",
    "UrlEntry",
]

MAX_UPLOAD_VIDEO_BYTES = 256 * 1024 * 1024
MAX_URLS_PER_BATCH = 500


@dataclass(frozen=True, slots=True)
class UrlEntry:
    url: str
    creator_handle: str | None = None
    notes: str = ""
    tags: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CandidateDefaults:
    """What a whole batch shares, applied to every candidate in it."""

    origin: ReferenceOrigin = ReferenceOrigin.FAN_ART
    suggested_class: ReferenceClass | None = None
    intended_uses: tuple[ReferenceUse, ...] = ()
    tags: tuple[str, ...] = ()
    notes: str = ""


@dataclass(frozen=True, slots=True)
class AcceptSpec:
    """Decisions made when accepting; unspecified fields come from the candidate.

    ``base`` carries links (characters, techniques, standings, scene sources)
    and its class. Origin is the candidate's declared origin unless ``origin``
    overrides it explicitly - a base spec never silently relabels fan art.
    """

    reference_class: ReferenceClass | None = None
    origin: ReferenceOrigin | None = None
    uses: tuple[ReferenceUse, ...] | None = None
    label: str | None = None
    notes: str | None = None
    base: ReferenceSpec | None = None


@dataclass
class IntakeResult:
    batch: IntakeBatch
    created: list[ReferenceCandidate] = field(default_factory=list)
    skipped: list[dict[str, str]] = field(default_factory=list)


def _video_signature_ok(data: bytes) -> bool:
    """MP4/MOV/M4V ('ftyp' box) or Matroska/WebM (EBML header)."""
    return data[4:8] == b"ftyp" or data[:4] == b"\x1a\x45\xdf\xa3"


class ReferenceInbox:
    def __init__(self, catalog: ReferenceCatalog) -> None:
        self.catalog = catalog
        self.session = catalog.session

    # -- batches ------------------------------------------------------------
    def create_batch(self, kind: IntakeKind, *, label: str = "", notes: str = "") -> IntakeBatch:
        batch = IntakeBatch(
            kind=kind,
            label=clean_text(label, 200, field="Batch label"),
            notes=clean_text(notes, 4000, field="Batch notes"),
        )
        self.session.add(batch)
        self.session.flush()
        return batch

    def batch(self, batch_id: uuid.UUID) -> IntakeBatch:
        found = self.session.get(IntakeBatch, batch_id)
        if found is None:
            raise CatalogNotFoundError("That intake batch does not exist.")
        return found

    def batches(self) -> list[tuple[IntakeBatch, dict[str, int]]]:
        rows = self.session.execute(
            select(IntakeBatch).order_by(IntakeBatch.created_at.desc(), IntakeBatch.id.desc())
        ).scalars()
        counts: dict[uuid.UUID, dict[str, int]] = {}
        for batch_id, status, count in self.session.execute(
            select(ReferenceCandidate.batch_id, ReferenceCandidate.status, func.count()).group_by(
                ReferenceCandidate.batch_id, ReferenceCandidate.status
            )
        ):
            if batch_id is not None:
                counts.setdefault(batch_id, {})[status.value] = int(count)
        return [(batch, counts.get(batch.id, {})) for batch in rows]

    # -- intake -------------------------------------------------------------
    def add_urls(
        self,
        entries: Sequence[UrlEntry],
        *,
        label: str = "",
        defaults: CandidateDefaults | None = None,
    ) -> IntakeResult:
        """Store links as candidates. Nothing is fetched."""
        defaults = self._check_defaults(defaults or CandidateDefaults())
        if len(entries) > MAX_URLS_PER_BATCH:
            raise CatalogInputError(f"At most {MAX_URLS_PER_BATCH} links per batch.")
        result = IntakeResult(batch=self.create_batch(IntakeKind.URL, label=label))
        seen: set[str] = set()
        for entry in entries:
            try:
                url = clean_url(entry.url)
            except CatalogInputError as exc:
                result.skipped.append({"input": entry.url[:200], "reason": exc.user_message})
                continue
            if url is None:
                continue
            if url in seen or self._url_known(url):
                result.skipped.append({"input": url, "reason": "already in the inbox or library"})
                continue
            seen.add(url)
            candidate = ReferenceCandidate(
                batch_id=result.batch.id,
                intake_kind=IntakeKind.URL,
                status=CandidateStatus.INBOX,
                source_url=url,
                creator_handle=clean_handle(entry.creator_handle),
                display_name="",
                origin=defaults.origin,
                suggested_class=defaults.suggested_class,
                intended_uses=[u.value for u in defaults.intended_uses],
                tags=clean_tags([*defaults.tags, *entry.tags]),
                notes=clean_text(entry.notes or defaults.notes, 4000, field="Notes"),
                capture={},
            )
            self.session.add(candidate)
            result.created.append(candidate)
        self.session.flush()
        return result

    def add_file(
        self,
        data: bytes,
        kind: IntakeKind,
        *,
        batch_id: uuid.UUID | None = None,
        display_name: str = "",
        source_url: str | None = None,
        creator_handle: str | None = None,
        capture: dict[str, Any] | None = None,
        defaults: CandidateDefaults | None = None,
    ) -> ReferenceCandidate:
        """One uploaded image, clip or screenshot, kept under the library root."""
        defaults = self._check_defaults(defaults or CandidateDefaults())
        if kind is IntakeKind.URL:
            raise CatalogInputError("Links are added with add_urls.")
        if batch_id is not None:
            self.batch(batch_id)
        asset = self._store(data, kind)
        candidate = ReferenceCandidate(
            batch_id=batch_id,
            intake_kind=kind,
            status=CandidateStatus.INBOX,
            source_url=clean_url(source_url),
            creator_handle=clean_handle(creator_handle),
            display_name=clean_display_name(display_name),
            asset_id=asset.id,
            origin=defaults.origin,
            suggested_class=defaults.suggested_class,
            intended_uses=[u.value for u in defaults.intended_uses],
            tags=clean_tags(defaults.tags),
            notes=clean_text(defaults.notes, 4000, field="Notes"),
            capture=_clean_capture(capture or {}),
        )
        self.session.add(candidate)
        self.session.flush()
        return candidate

    def add_held_frame(
        self,
        media_id: str,
        time_ms: int,
        image: bytes,
        *,
        batch_id: uuid.UUID | None = None,
        defaults: CandidateDefaults | None = None,
    ) -> ReferenceCandidate:
        """A frame captured in the viewer from held video (anime and other clips)."""
        sources = self.catalog.sources
        if sources is None:
            raise CatalogInputError("The Source Vault is not configured.")
        try:
            instant = sources.video_instant(media_id, time_ms, known_hash=self.catalog.known_hash)
        except SourceUnavailableError as exc:
            raise CatalogInputError(exc.user_message) from None
        video = self.catalog.asset(
            instant.content_hash, AssetMedium.VIDEO, AssetOrigin.SOURCE_VAULT, instant.byte_size
        )
        self.catalog.observe(
            video, "source_vault", instant.relative, instant.byte_size, instant.mtime_ns
        )
        return self.add_file(
            image,
            IntakeKind.SCREENSHOT,
            batch_id=batch_id,
            display_name=f"{instant.name} @ {instant.locator.render().rsplit('#t=', 1)[-1]}",
            capture={
                "kind": "held_video_frame",
                "video_locator": instant.locator.render(),
                "held_name": instant.name,
            },
            defaults=replace(
                defaults or CandidateDefaults(), origin=(defaults or CandidateDefaults()).origin
            ),
        )

    def add_clip_frame(
        self, candidate_id: uuid.UUID, time_ms: int, image: bytes
    ) -> ReferenceCandidate:
        """A frame captured from an uploaded clip in the inbox."""
        clip = self.candidate(candidate_id)
        if clip.intake_kind is not IntakeKind.VIDEO or clip.asset_id is None:
            raise CatalogInputError("Frames are captured from a video candidate.")
        video = self.session.get(LibraryAsset, clip.asset_id)
        assert video is not None
        return self.add_file(
            image,
            IntakeKind.SCREENSHOT,
            batch_id=clip.batch_id,
            display_name=f"{clip.display_name or 'clip'} @ {time_ms} ms",
            source_url=clip.source_url,
            creator_handle=clip.creator_handle,
            capture={
                "kind": "clip_frame",
                "video_locator": f"video:sha256:{video.content_hash}#t={_clock(time_ms)}",
                "from_candidate": str(clip.id),
            },
            defaults=CandidateDefaults(
                origin=clip.origin,
                suggested_class=clip.suggested_class,
                intended_uses=tuple(ReferenceUse(u) for u in clip.intended_uses),
                tags=tuple(clip.tags),
                notes=clip.notes,
            ),
        )

    def attach_image(
        self, candidate_id: uuid.UUID, row_version: int, image: bytes
    ) -> ReferenceCandidate:
        """Give a link candidate the bytes the user saved from it."""
        candidate = self._editable(candidate_id, row_version)
        if candidate.intake_kind is not IntakeKind.URL:
            raise CatalogInputError("Only a link candidate takes an attached image.")
        asset = self._store(image, IntakeKind.IMAGE)
        candidate.asset_id = asset.id
        self.catalog._flush()
        return candidate

    # -- triage -------------------------------------------------------------
    def candidate(self, candidate_id: uuid.UUID) -> ReferenceCandidate:
        found = self.session.get(ReferenceCandidate, candidate_id)
        if found is None:
            raise CatalogNotFoundError("That candidate does not exist.")
        return found

    def candidates(
        self,
        *,
        status: CandidateStatus | None = CandidateStatus.INBOX,
        batch_id: uuid.UUID | None = None,
        kind: IntakeKind | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[ReferenceCandidate]:
        query = select(ReferenceCandidate)
        if status is not None:
            query = query.where(ReferenceCandidate.status == status)
        if batch_id is not None:
            query = query.where(ReferenceCandidate.batch_id == batch_id)
        if kind is not None:
            query = query.where(ReferenceCandidate.intake_kind == kind)
        return list(
            self.session.execute(
                query.order_by(ReferenceCandidate.created_at.desc(), ReferenceCandidate.id.desc())
                .limit(max(1, min(limit, 500)))
                .offset(max(0, offset))
            ).scalars()
        )

    def update(
        self, candidate_id: uuid.UUID, row_version: int, **changes: Any
    ) -> ReferenceCandidate:
        candidate = self._editable(candidate_id, row_version)
        self._apply(candidate, changes)
        self.catalog._flush()
        return candidate

    def bulk_update(self, candidate_ids: Sequence[uuid.UUID], **changes: Any) -> int:
        """Apply the same triage decision to many inbox candidates."""
        updated = 0
        for candidate_id in dict.fromkeys(candidate_ids):
            candidate = self.candidate(candidate_id)
            if candidate.status is not CandidateStatus.INBOX:
                continue
            self._apply(candidate, changes)
            updated += 1
        self.catalog._flush()
        return updated

    def dismiss(self, candidate_id: uuid.UUID, row_version: int) -> ReferenceCandidate:
        candidate = self._editable(candidate_id, row_version)
        candidate.status = CandidateStatus.DISMISSED
        self.catalog._flush()
        return candidate

    def restore(self, candidate_id: uuid.UUID, row_version: int) -> ReferenceCandidate:
        candidate = self.candidate(candidate_id)
        self.catalog._check_version(candidate.row_version, row_version)
        if candidate.status is not CandidateStatus.DISMISSED:
            raise CatalogInputError("Only a dismissed candidate can be restored.")
        candidate.status = CandidateStatus.INBOX
        self.catalog._flush()
        return candidate

    def accept(
        self, candidate_id: uuid.UUID, row_version: int, spec: AcceptSpec | None = None
    ) -> ReferenceItem:
        """Turn a candidate with image bytes into a catalogued reference."""
        candidate = self._editable(candidate_id, row_version)
        return self._accept(candidate, spec or AcceptSpec())

    def bulk_accept(
        self, candidate_ids: Sequence[uuid.UUID], spec: AcceptSpec | None = None
    ) -> tuple[list[ReferenceItem], list[dict[str, str]]]:
        accepted: list[ReferenceItem] = []
        skipped: list[dict[str, str]] = []
        for candidate_id in dict.fromkeys(candidate_ids):
            candidate = self.candidate(candidate_id)
            if candidate.status is not CandidateStatus.INBOX:
                skipped.append({"id": str(candidate_id), "reason": "not in the inbox"})
                continue
            try:
                with self.session.begin_nested():
                    accepted.append(self._accept(candidate, spec or AcceptSpec()))
            except CatalogInputError as exc:
                skipped.append({"id": str(candidate_id), "reason": exc.user_message})
        return accepted, skipped

    def candidate_bytes(self, candidate: ReferenceCandidate) -> tuple[bytes, AssetMedium]:
        if candidate.asset_id is None:
            raise CatalogNotFoundError("This candidate has no attached file.")
        asset = self.session.get(LibraryAsset, candidate.asset_id)
        assert asset is not None
        if self.catalog.derived is None or not self.catalog.derived.has(
            LIBRARY_ROOT, asset.content_hash
        ):
            raise CatalogNotFoundError("The candidate's file is not reachable.")
        return self.catalog.derived.get_bytes(LIBRARY_ROOT, asset.content_hash), asset.medium

    # -- internals ----------------------------------------------------------
    def _accept(self, candidate: ReferenceCandidate, spec: AcceptSpec) -> ReferenceItem:
        if candidate.asset_id is None:
            raise CatalogInputError(
                "Attach an image or screenshot first; a link is not fetched.",
            )
        asset = self.session.get(LibraryAsset, candidate.asset_id)
        assert asset is not None
        if asset.medium is AssetMedium.VIDEO:
            raise CatalogInputError("Capture a frame from the clip; a clip is not a reference.")
        reference_class = (
            spec.reference_class
            or (spec.base.reference_class if spec.base is not None else None)
            or candidate.suggested_class
        )
        if reference_class is None:
            raise CatalogInputError(
                "Choose what the reference is: canon, technique, mood or continuity."
            )
        base = spec.base or ReferenceSpec(reference_class=reference_class, origin=candidate.origin)
        uses = (
            spec.uses
            if spec.uses is not None
            else tuple(ReferenceUse(u) for u in candidate.intended_uses)
        )
        tags = tuple(DescriptorSpec(DescriptorFacet.TAG, tag) for tag in candidate.tags)
        provenance: dict[str, Any] = {
            "kind": "inbox",
            "candidate_id": str(candidate.id),
            "intake_kind": candidate.intake_kind.value,
            "batch_id": str(candidate.batch_id) if candidate.batch_id else None,
        }
        if candidate.capture:
            provenance["capture"] = candidate.capture
            if candidate.capture.get("kind") == "held_video_frame":
                provenance = {
                    **provenance,
                    "kind": "source_frame",
                    "video_locator": candidate.capture.get("video_locator"),
                    "held_name": candidate.capture.get("held_name"),
                }
        final = replace(
            base,
            reference_class=reference_class,
            origin=spec.origin or candidate.origin,
            label=spec.label if spec.label is not None else (base.label or candidate.display_name),
            notes=spec.notes if spec.notes is not None else (base.notes or candidate.notes),
            source_url=base.source_url or candidate.source_url,
            creator_handle=base.creator_handle or candidate.creator_handle,
            uses=tuple(dict.fromkeys((*base.uses, *uses))),
            descriptors=(*base.descriptors, *tags),
        )
        item = self.catalog.add_existing_image(asset, final, provenance)
        candidate.status = CandidateStatus.ACCEPTED
        candidate.reference_id = item.id
        self.catalog._flush()
        return item

    def _editable(self, candidate_id: uuid.UUID, row_version: int) -> ReferenceCandidate:
        candidate = self.candidate(candidate_id)
        self.catalog._check_version(candidate.row_version, row_version)
        if candidate.status is not CandidateStatus.INBOX:
            raise CatalogConflictError("That candidate was already triaged.")
        return candidate

    def _apply(self, candidate: ReferenceCandidate, changes: dict[str, Any]) -> None:
        for key, value in changes.items():
            if key == "notes":
                candidate.notes = clean_text(value, 4000, field="Notes")
            elif key == "tags":
                candidate.tags = clean_tags(value)
            elif key == "add_tags":
                candidate.tags = clean_tags([*candidate.tags, *value])
            elif key == "intended_uses":
                candidate.intended_uses = list(dict.fromkeys(ReferenceUse(u).value for u in value))
            elif key == "suggested_class":
                candidate.suggested_class = ReferenceClass(value) if value else None
            elif key == "origin":
                origin = ReferenceOrigin(value)
                if origin not in USER_DECLARED_ORIGINS:
                    raise CatalogInputError("That origin is created by production, not intake.")
                candidate.origin = origin
            elif key == "creator_handle":
                candidate.creator_handle = clean_handle(value)
            elif key == "source_url":
                url = clean_url(value)
                if candidate.intake_kind is IntakeKind.URL and url is None:
                    raise CatalogInputError("A link candidate keeps its link.")
                candidate.source_url = url
            else:
                raise CatalogInputError(f"'{key}' cannot be changed on a candidate.")

    def _check_defaults(self, defaults: CandidateDefaults) -> CandidateDefaults:
        if defaults.origin not in USER_DECLARED_ORIGINS:
            raise CatalogInputError("That origin is created by production, not intake.")
        clean_tags(defaults.tags)
        return defaults

    def _store(self, data: bytes, kind: IntakeKind) -> LibraryAsset:
        if kind is IntakeKind.VIDEO:
            if len(data) > MAX_UPLOAD_VIDEO_BYTES:
                raise CatalogInputError("That clip is too large (256 MB at most).")
            if not _video_signature_ok(data):
                raise CatalogInputError("That file is not an MP4, MOV, WebM or MKV clip.")
            return self.catalog.store_bytes(
                data, root_key=LIBRARY_ROOT, medium=AssetMedium.VIDEO, origin=AssetOrigin.USER_ADDED
            )
        probe(data)
        return self.catalog._store_image(data)

    def _url_known(self, url: str) -> bool:
        in_inbox = self.session.execute(
            select(ReferenceCandidate.id)
            .where(
                ReferenceCandidate.source_url == url,
                ReferenceCandidate.status != CandidateStatus.DISMISSED,
            )
            .limit(1)
        ).scalar_one_or_none()
        if in_inbox is not None:
            return True
        in_library = self.session.execute(
            select(ReferenceItem.id)
            .where(ReferenceItem.source_url == url, ReferenceItem.removed_at.is_(None))
            .limit(1)
        ).scalar_one_or_none()
        return in_library is not None


def _clock(time_ms: int) -> str:
    seconds, millis = divmod(max(0, int(time_ms)), 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{millis:03d}"


def _clean_capture(capture: dict[str, Any]) -> dict[str, Any]:
    """Keep only simple, bounded capture facts; never a path."""
    allowed = {"kind", "video_locator", "held_name", "from_candidate", "note", "captured_at"}
    cleaned: dict[str, Any] = {}
    for key, value in capture.items():
        if key in allowed and isinstance(value, str | int | float) and len(str(value)) <= 500:
            cleaned[key] = value
    return cleaned
