"""The full-Vault catalog vocabulary (Phase 1.5).

Pure enumerations shared by the database, the services and the API. Two
separations are expressed as types rather than conventions:

* **Observation is not interpretation.** What a file *is* (its bytes, its
  archive members) is recorded apart from what Continuum *thinks* it is (a
  chapter of a series, an episode of a season). An interpretation carries a
  :class:`Confidence` and the evidence it was drawn from, so an uncertain
  identification is flagged instead of silently presented as fact.
* **Rights and training are never assumed.** Imported material starts with
  :attr:`RightsStatus.UNKNOWN` and :attr:`TrainingEligibility.MANUAL_REVIEW`;
  only a person can change either.
"""

from __future__ import annotations

from enum import StrEnum

__all__ = [
    "SCANNER_VERSION",
    "ApprovalState",
    "Confidence",
    "DetectedKind",
    "EntryStatus",
    "EpisodeKind",
    "HashSource",
    "MaterialClass",
    "MemberKind",
    "ProgressMedium",
    "RightsStatus",
    "ScanStatus",
    "TrainingEligibility",
    "UnitKind",
]

#: Bumped whenever observation or identification rules change, so an
#: unchanged file observed by older rules is re-examined once - and only once.
SCANNER_VERSION = 3


class EntryStatus(StrEnum):
    """Where one file stands in the catalog."""

    CATALOGUED = "CATALOGUED"
    """Recognised media, recorded with its members and units."""
    UNSUPPORTED = "UNSUPPORTED"
    """Seen and explained, but not media Continuum can use (with a reason)."""
    FAILED = "FAILED"
    """Could not be read or inspected; retried by the next scan."""
    MISSING = "MISSING"
    """Catalogued before, not found by the latest completed scan of its root."""


class DetectedKind(StrEnum):
    """What the bytes are, decided from content, never from the extension alone."""

    ARCHIVE = "ARCHIVE"
    VIDEO = "VIDEO"
    IMAGE = "IMAGE"
    DOCUMENT = "DOCUMENT"
    SOFTWARE = "SOFTWARE"
    EMPTY = "EMPTY"
    OTHER = "OTHER"


class MaterialClass(StrEnum):
    """What the material is for a person: manga, anime, fan art..."""

    MANGA = "MANGA"
    MANHWA = "MANHWA"
    MANHUA = "MANHUA"
    COMIC = "COMIC"
    ANIME = "ANIME"
    FAN_ART = "FAN_ART"
    REFERENCE = "REFERENCE"
    DOCUMENT = "DOCUMENT"
    SOFTWARE = "SOFTWARE"
    UNKNOWN = "UNKNOWN"


class HashSource(StrEnum):
    """Where a recorded SHA-256 came from."""

    ENGINE_INDEX = "ENGINE_INDEX"
    """Reused from the acquisition engine's index for the same size and mtime."""
    COMPUTED = "COMPUTED"
    """Streamed by Continuum's own hash pass."""


class ScanStatus(StrEnum):
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"


class MemberKind(StrEnum):
    """Archive members worth recording individually."""

    VIDEO = "VIDEO"
    """One video file inside an archive."""
    PAGE_GROUP = "PAGE_GROUP"
    """One folder of images inside an archive, in reading order."""


class UnitKind(StrEnum):
    """Addressable units of material, as Continuum understands them."""

    MANGA_CHAPTER = "MANGA_CHAPTER"
    ARCHIVE_PAGES = "ARCHIVE_PAGES"
    """A group of pages that does not name a chapter."""
    EPISODE = "EPISODE"
    VIDEO = "VIDEO"
    """A video that is not part of a series' episodes (a clip, an extra)."""
    IMAGE = "IMAGE"
    DOCUMENT = "DOCUMENT"


class EpisodeKind(StrEnum):
    REGULAR = "REGULAR"
    SPECIAL = "SPECIAL"
    OVA = "OVA"
    MOVIE = "MOVIE"
    RECAP = "RECAP"
    UNKNOWN = "UNKNOWN"


class Confidence(StrEnum):
    """How sure an identification is. LOW is always shown as uncertain."""

    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class RightsStatus(StrEnum):
    """What is known about the right to use a piece of material."""

    UNKNOWN = "UNKNOWN"
    OWNED = "OWNED"
    LICENSED = "LICENSED"
    PERMITTED = "PERMITTED"
    RESTRICTED = "RESTRICTED"


class TrainingEligibility(StrEnum):
    """Whether material may be used to train a model. Never approved by default."""

    MANUAL_REVIEW = "MANUAL_REVIEW"
    APPROVED = "APPROVED"
    EXCLUDED = "EXCLUDED"


class ProgressMedium(StrEnum):
    READING = "READING"
    WATCHING = "WATCHING"


class ApprovalState(StrEnum):
    """Where a production package stands."""

    DRAFT = "DRAFT"
    IN_REVIEW = "IN_REVIEW"
    APPROVED = "APPROVED"
    SUPERSEDED = "SUPERSEDED"
