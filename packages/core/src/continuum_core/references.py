"""The reference-vault and rough-manga vocabulary (Phase 1).

Pure enumerations shared by the database, the services and the API. The
separations the product depends on are expressed here as *types*:

* a character **aspect** (identity, wardrobe, acting) is not a **technique
  facet** (composition, screentone, page turn...), and nothing maps one to
  the other - "character X implies style Y" is not representable;
* an **outfit** belongs to a character but is never the character's identity;
* a **descriptor** records who asserted it (``USER`` or ``ANALYSIS``), so
  hand-tagging and later automated enrichment never masquerade as each other.
"""

from __future__ import annotations

from enum import StrEnum

__all__ = [
    "ASPECT_GROUPS",
    "AspectGroup",
    "AssetMedium",
    "AssetOrigin",
    "AttemptState",
    "BundleRole",
    "CandidateStatus",
    "CharacterAspect",
    "DerivativeKind",
    "DescriptorFacet",
    "DescriptorOrigin",
    "EditOperationKind",
    "IntakeKind",
    "ModeScope",
    "ModeTrigger",
    "OutfitKind",
    "PanelSourceRole",
    "ProjectStanding",
    "ReferenceClass",
    "ReferenceOrigin",
    "ReferenceUse",
    "ReviewDecision",
    "RoughArtifactKind",
    "RoughMode",
    "SubjectKind",
    "TechniqueFacet",
    "VisualModeCategory",
]


class AssetMedium(StrEnum):
    """What kind of bytes a library asset is."""

    ARCHIVE = "ARCHIVE"
    IMAGE = "IMAGE"
    PDF = "PDF"
    VIDEO = "VIDEO"


class AssetOrigin(StrEnum):
    """Where the bytes live. Source Vault bytes are never copied."""

    SOURCE_VAULT = "SOURCE_VAULT"
    USER_ADDED = "USER_ADDED"
    GENERATED = "GENERATED"


class ReferenceClass(StrEnum):
    """What a reference is *for* in a bundle (Reference Vault direction section 3)."""

    CANON = "CANON"
    """What a person, object or place must look like."""
    TECHNIQUE = "TECHNIQUE"
    """How a visual problem may be solved."""
    CONTINUITY = "CONTINUITY"
    """How this project depicted the subject before."""
    MOOD = "MOOD"
    """Lighting, atmosphere, emotional texture, density."""
    UNSORTED = "UNSORTED"
    """Not sorted yet: imported material whose purpose no person has decided.

    Never treated as canon; a bundle only uses it once someone sorts it."""


class ReferenceOrigin(StrEnum):
    """Where a reference came from. Fan art never silently becomes canon."""

    SOURCE = "SOURCE"
    """Held source material: manga pages, anime frames."""
    OFFICIAL_ART = "OFFICIAL_ART"
    FAN_ART = "FAN_ART"
    USER_CREATED = "USER_CREATED"
    GENERATED = "GENERATED"
    PROJECT_APPROVED = "PROJECT_APPROVED"


class AspectGroup(StrEnum):
    IDENTITY = "IDENTITY"
    WARDROBE = "WARDROBE"
    ACTING = "ACTING"


class CharacterAspect(StrEnum):
    """What part of a character a reference shows."""

    FACE = "FACE"
    HAIR = "HAIR"
    FULL_BODY = "FULL_BODY"
    PROPORTIONS = "PROPORTIONS"
    SCALE = "SCALE"
    DISTINGUISHING_MARK = "DISTINGUISHING_MARK"
    POSTURE = "POSTURE"
    OUTFIT = "OUTFIT"
    ACCESSORY = "ACCESSORY"
    EXPRESSION = "EXPRESSION"
    POSE = "POSE"
    GESTURE = "GESTURE"
    ACTION_POSE = "ACTION_POSE"
    QUIET_ACTING = "QUIET_ACTING"
    COMEDIC_EXPRESSION = "COMEDIC_EXPRESSION"

    @property
    def group(self) -> AspectGroup:
        return ASPECT_GROUPS[self]


ASPECT_GROUPS: dict[CharacterAspect, AspectGroup] = {
    CharacterAspect.FACE: AspectGroup.IDENTITY,
    CharacterAspect.HAIR: AspectGroup.IDENTITY,
    CharacterAspect.FULL_BODY: AspectGroup.IDENTITY,
    CharacterAspect.PROPORTIONS: AspectGroup.IDENTITY,
    CharacterAspect.SCALE: AspectGroup.IDENTITY,
    CharacterAspect.DISTINGUISHING_MARK: AspectGroup.IDENTITY,
    CharacterAspect.POSTURE: AspectGroup.IDENTITY,
    CharacterAspect.OUTFIT: AspectGroup.WARDROBE,
    CharacterAspect.ACCESSORY: AspectGroup.WARDROBE,
    CharacterAspect.EXPRESSION: AspectGroup.ACTING,
    CharacterAspect.POSE: AspectGroup.ACTING,
    CharacterAspect.GESTURE: AspectGroup.ACTING,
    CharacterAspect.ACTION_POSE: AspectGroup.ACTING,
    CharacterAspect.QUIET_ACTING: AspectGroup.ACTING,
    CharacterAspect.COMEDIC_EXPRESSION: AspectGroup.ACTING,
}


class OutfitKind(StrEnum):
    SOURCE_DEFAULT = "SOURCE_DEFAULT"
    SOURCE_ALTERNATE = "SOURCE_ALTERNATE"
    PROJECT = "PROJECT"
    OTHER = "OTHER"


class TechniqueFacet(StrEnum):
    """A visual-language problem a style/technique reference helps solve."""

    PAGE_COMPOSITION = "PAGE_COMPOSITION"
    PANEL_DENSITY = "PANEL_DENSITY"
    PAGE_TURN = "PAGE_TURN"
    ACTION_READABILITY = "ACTION_READABILITY"
    FACIAL_ACTING = "FACIAL_ACTING"
    DIALOGUE_FRAMING = "DIALOGUE_FRAMING"
    NEGATIVE_SPACE = "NEGATIVE_SPACE"
    IMPACT_LANGUAGE = "IMPACT_LANGUAGE"
    SCREENTONE = "SCREENTONE"
    BACKGROUND_TREATMENT = "BACKGROUND_TREATMENT"
    COMEDY = "COMEDY"
    HORROR = "HORROR"
    ROMANCE = "ROMANCE"
    ATMOSPHERE = "ATMOSPHERE"
    ESTABLISHING_SHOT = "ESTABLISHING_SHOT"
    EXPERIMENTAL_LAYOUT = "EXPERIMENTAL_LAYOUT"
    LIGHTING = "LIGHTING"
    NIGHT_RENDERING = "NIGHT_RENDERING"
    CINEMATOGRAPHY = "CINEMATOGRAPHY"
    MOTION_LANGUAGE = "MOTION_LANGUAGE"


class DescriptorFacet(StrEnum):
    """Searchable descriptions of a reference, manual now, enrichable later."""

    ERA = "ERA"
    SEASON_WEATHER = "SEASON_WEATHER"
    CONDITION = "CONDITION"
    EXPRESSION = "EXPRESSION"
    POSE = "POSE"
    SHOT_TYPE = "SHOT_TYPE"
    CAMERA_ANGLE = "CAMERA_ANGLE"
    SCENE_TYPE = "SCENE_TYPE"
    ACTION_INTENSITY = "ACTION_INTENSITY"
    DIALOGUE_DENSITY = "DIALOGUE_DENSITY"
    BACKGROUND_COMPLEXITY = "BACKGROUND_COMPLEXITY"
    COMPOSITION = "COMPOSITION"
    PAGE_TURN_FUNCTION = "PAGE_TURN_FUNCTION"
    MOOD = "MOOD"
    PANEL_GEOMETRY = "PANEL_GEOMETRY"
    CHARACTER_COUNT = "CHARACTER_COUNT"
    LOCATION = "LOCATION"
    TAG = "TAG"
    """A free user tag."""


class DescriptorOrigin(StrEnum):
    USER = "USER"
    """Tagged by a person. Shown as USER TAGGED."""
    ANALYSIS = "ANALYSIS"
    """Derived by an analyzer (Source Intelligence, later). Shown as ANALYSIS DERIVED."""


class ProjectStanding(StrEnum):
    USEFUL = "USEFUL"
    CANONICAL_FOR_PROJECT = "CANONICAL_FOR_PROJECT"
    PREFERRED_FOR_CURRENT_LOOK = "PREFERRED_FOR_CURRENT_LOOK"


class PanelSourceRole(StrEnum):
    """How a source selection serves a specific project page/panel."""

    SOURCE_PLATE = "SOURCE_PLATE"
    COMPOSITION = "COMPOSITION"
    ENVIRONMENT = "ENVIRONMENT"
    CONTINUITY = "CONTINUITY"
    COMPARISON = "COMPARISON"
    MOOD = "MOOD"


class BundleRole(StrEnum):
    """A reference's role in a rough attempt's bundle (never an undifferentiated pile)."""

    CANON = "CANON"
    STYLE = "STYLE"
    TECHNIQUE = "TECHNIQUE"
    MOOD = "MOOD"
    SOURCE_PLATE = "SOURCE_PLATE"
    CONTINUITY = "CONTINUITY"


class RoughMode(StrEnum):
    NEW_GENERATION = "NEW_GENERATION"
    """Created primarily from references and the recipe."""
    SOURCE_DERIVED_EDIT = "SOURCE_DERIVED_EDIT"
    """Starts from exactly one source plate and modifies it."""
    COMPOSITE = "COMPOSITE"
    """Combines several source or derived elements and references."""
    LAYOUT_ONLY = "LAYOUT_ONLY"
    """Panel layout with placeholders, before any expensive rendering."""


class EditOperationKind(StrEnum):
    """What a source-derived edit intends to do to a region of the plate."""

    PRESERVE = "PRESERVE"
    REMOVE = "REMOVE"
    REPLACE = "REPLACE"
    INSERT = "INSERT"
    CHANGE_EXPRESSION = "CHANGE_EXPRESSION"
    CHANGE_OUTFIT = "CHANGE_OUTFIT"
    REMOVE_TEXT = "REMOVE_TEXT"
    REPLACE_TEXT = "REPLACE_TEXT"
    EXTEND_BACKGROUND = "EXTEND_BACKGROUND"
    REDRAW = "REDRAW"
    RESTYLE_LINES = "RESTYLE_LINES"
    REFRAME = "REFRAME"
    ADAPT_PROPORTIONS = "ADAPT_PROPORTIONS"


class RoughArtifactKind(StrEnum):
    PANEL = "PANEL"
    PAGE = "PAGE"


class AttemptState(StrEnum):
    """Stored attempt state. FAILED/BLOCKED are read from the attempt's job."""

    QUEUED = "QUEUED"
    GENERATED = "GENERATED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    SUPERSEDED = "SUPERSEDED"
    """A previously approved attempt replaced by a newer approval. Bytes kept."""


class ReviewDecision(StrEnum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    REGENERATE = "REGENERATE"


class DerivativeKind(StrEnum):
    """Bytes an attempt produced, all content-addressed under generated/."""

    OUTPUT = "OUTPUT"
    MASK = "MASK"
    SOURCE_CROP = "SOURCE_CROP"


class SubjectKind(StrEnum):
    """What a character profile describes. Monsters and creatures are subjects too."""

    CHARACTER = "CHARACTER"
    MONSTER = "MONSTER"
    CREATURE = "CREATURE"


class ReferenceUse(StrEnum):
    """What a reference is intended to be used for. One reference may serve several."""

    IDENTITY = "IDENTITY"
    OUTFIT = "OUTFIT"
    EXPRESSION = "EXPRESSION"
    POSE = "POSE"
    ACCESSORY = "ACCESSORY"
    STYLE = "STYLE"
    TECHNIQUE = "TECHNIQUE"
    MOOD = "MOOD"
    MONSTER_DESIGN = "MONSTER_DESIGN"
    SCENE_SOURCE = "SCENE_SOURCE"
    SOURCE_PLATE = "SOURCE_PLATE"
    CONTINUITY = "CONTINUITY"


class IntakeKind(StrEnum):
    """How a reference candidate arrived in the inbox."""

    URL = "URL"
    """A link only. Nothing is fetched; bytes are attached by the user."""
    IMAGE = "IMAGE"
    VIDEO = "VIDEO"
    SCREENSHOT = "SCREENSHOT"
    """A captured frame or screen, with where it was captured from."""


class CandidateStatus(StrEnum):
    INBOX = "INBOX"
    ACCEPTED = "ACCEPTED"
    DISMISSED = "DISMISSED"


class VisualModeCategory(StrEnum):
    """The family a visual mode belongs to. None of them is a character."""

    BASE = "BASE"
    INTIMATE = "INTIMATE"
    EXPRESSIVE_COMEDY = "EXPRESSIVE_COMEDY"
    COMEDIC_DEFORMATION = "COMEDIC_DEFORMATION"
    """Chibi / super-deformed: a rendering decision, never an identity rewrite."""
    HORROR_THREAT = "HORROR_THREAT"
    MEMORY_DREAM = "MEMORY_DREAM"
    HEIGHTENED_PERCEPTION = "HEIGHTENED_PERCEPTION"
    ACTION = "ACTION"
    ATMOSPHERE = "ATMOSPHERE"
    MONSTER = "MONSTER"
    EXPERIMENTAL = "EXPERIMENTAL"


class ModeScope(StrEnum):
    """Where a project applies a visual mode."""

    PANEL = "PANEL"
    SCENE = "SCENE"
    SEQUENCE = "SEQUENCE"
    EPISODE = "EPISODE"
    EVENT = "EVENT"
    """A special event, emotional state or monster moment, named by the project."""


class ModeTrigger(StrEnum):
    """Why a visual mode is in effect for its scope."""

    DIRECTORIAL = "DIRECTORIAL"
    """Chosen for the panel/scene/episode by the story."""
    SCENE_TONE = "SCENE_TONE"
    """Involuntary: the tone of the moment compresses or shifts the rendering."""
    CHARACTER_CONTROLLED = "CHARACTER_CONTROLLED"
    """A form a specific character can take at will, within this scope."""
