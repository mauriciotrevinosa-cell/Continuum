"""The character reference corpus vocabulary (M3).

A character profile says what a character should look like in production. The
**corpus** is the evidence behind it: every observation of the character
Continuum can find or has been given - curated references, pages of the source
manga, fan art, approved project pages - each with *what it teaches* and *how
authoritative it is*. Production retrieves a small, relevant subset per page;
the corpus itself may hold hundreds of observations.

Kept apart on purpose:

* **authority** (how much an observation may define the character) is not
  **status** (whether a person has confirmed it shows the character at all);
* **role** separates identity grounding from stylization and plain evidence,
  so a stylized concept never becomes the character's identity;
* a **candidate** never grounds production and never counts toward readiness.
"""

from __future__ import annotations

from enum import StrEnum

__all__ = [
    "AUTHORITY_RANK",
    "HIGH_AUTHORITY",
    "Framing",
    "ObservationAuthority",
    "ObservationFacet",
    "ObservationRole",
    "ObservationSource",
    "ObservationStatus",
    "ProductionEvidenceRole",
    "ProductionModelStatus",
    "ViewAngle",
    "VisualOrigin",
]


class ProductionModelStatus(StrEnum):
    DRAFT = "DRAFT"
    REVIEW = "REVIEW"
    APPROVED = "APPROVED"
    SUPERSEDED = "SUPERSEDED"


class ProductionEvidenceRole(StrEnum):
    IDENTITY = "IDENTITY"
    BODY = "BODY"
    WARDROBE = "WARDROBE"
    EXPRESSION = "EXPRESSION"
    POSE = "POSE"
    ACCESSORY = "ACCESSORY"
    SCALE = "SCALE"


class VisualOrigin(StrEnum):
    """Who made the image, as a person judged it - independent of where it was acquired.

    A frame of the official anime reposted by a fan account was *acquired* as
    fan art but its *visual origin* is the official anime.
    """

    PRIMARY_MANGA = "PRIMARY_MANGA"
    OFFICIAL_ANIME = "OFFICIAL_ANIME"
    OFFICIAL_ART = "OFFICIAL_ART"
    PROJECT_CREATED = "PROJECT_CREATED"
    FAN_ART = "FAN_ART"
    UNKNOWN = "UNKNOWN"


class ObservationSource(StrEnum):
    CURATED = "CURATED"
    """A reference a person linked to the character in the Reference Vault."""
    SOURCE_PAGE = "SOURCE_PAGE"
    """A page of the catalogued source manga where the character likely appears."""
    FAN_ART = "FAN_ART"
    """Fan art whose own labels name the character."""
    APPROVED_OUTPUT = "APPROVED_OUTPUT"
    """A creatively approved production page of the project."""


class ObservationAuthority(StrEnum):
    PRIMARY_SOURCE = "PRIMARY_SOURCE"
    """The original manga or source material of a franchise character."""
    CREATOR_PRIMARY = "CREATOR_PRIMARY"
    """The creator's own grounding (photos) for an original project character."""
    OFFICIAL = "OFFICIAL"
    """Anime, official character sheets, official promotional art."""
    PROJECT_CREATED = "PROJECT_CREATED"
    """Approved project work: reference sheets, approved pages, directional concepts."""
    SUPPLEMENTAL = "SUPPLEMENTAL"
    """Selected derivative art, fan art, exploratory material: angles and ideas only."""
    UNSORTED = "UNSORTED"
    """Not sorted yet. Never grounds production."""


class ObservationStatus(StrEnum):
    CANDIDATE = "CANDIDATE"
    """Found automatically; nobody has confirmed it shows the character."""
    CONFIRMED = "CONFIRMED"
    REJECTED = "REJECTED"


class ObservationRole(StrEnum):
    GROUNDING = "GROUNDING"
    """May define identity, body and wardrobe."""
    STYLIZATION = "STYLIZATION"
    """Guides how the character is rendered; never their identity."""
    EVIDENCE = "EVIDENCE"
    """Useful angles, poses, lighting or ideas; defines nothing on its own."""


class ObservationFacet(StrEnum):
    FACE = "FACE"
    HAIR = "HAIR"
    BODY = "BODY"
    WARDROBE = "WARDROBE"
    EXPRESSION = "EXPRESSION"
    POSE = "POSE"
    ACCESSORY = "ACCESSORY"
    SCALE = "SCALE"
    """Relative height and build beside other characters."""


class ViewAngle(StrEnum):
    FRONT = "FRONT"
    THREE_QUARTER_LEFT = "THREE_QUARTER_LEFT"
    THREE_QUARTER_RIGHT = "THREE_QUARTER_RIGHT"
    PROFILE = "PROFILE"
    BACK = "BACK"
    LOOKING_UP = "LOOKING_UP"
    LOOKING_DOWN = "LOOKING_DOWN"


class Framing(StrEnum):
    CLOSE_UP = "CLOSE_UP"
    UPPER_BODY = "UPPER_BODY"
    FULL_BODY = "FULL_BODY"
    WIDE = "WIDE"


#: Lower is stronger. Creator grounding and the source manga rank equally: each
#: is the primary truth for its kind of character.
AUTHORITY_RANK: dict[ObservationAuthority, int] = {
    ObservationAuthority.PRIMARY_SOURCE: 0,
    ObservationAuthority.CREATOR_PRIMARY: 0,
    ObservationAuthority.OFFICIAL: 1,
    ObservationAuthority.PROJECT_CREATED: 2,
    ObservationAuthority.SUPPLEMENTAL: 3,
    ObservationAuthority.UNSORTED: 9,
}
#: Authorities whose confirmed observations count toward readiness.
HIGH_AUTHORITY: frozenset[ObservationAuthority] = frozenset(
    {
        ObservationAuthority.PRIMARY_SOURCE,
        ObservationAuthority.CREATOR_PRIMARY,
        ObservationAuthority.OFFICIAL,
    }
)
