"""ORM models.

Phase 0: the six durable job tables (ADR-0006 section 3). Phase 1: the
reference vault and rough-manga production tables. Phase 1.5: the full-Vault
catalog, reading progress and project production inputs. ``continuum_db.tiers``
declares every table's phase and tier.
"""

from continuum_db.models.base import Base
from continuum_db.models.catalog import (
    CatalogEntry,
    CatalogMember,
    CatalogScan,
    CatalogUnit,
    ChapterPackage,
    MediaProgress,
    MusicReference,
    ReferenceManifest,
)
from continuum_db.models.character_models import (
    CharacterProductionEvidence,
    CharacterProductionModel,
)
from continuum_db.models.corpus import CharacterObservation
from continuum_db.models.jobs import (
    Job,
    JobCheckpoint,
    JobDependency,
    JobEvent,
    JobStep,
    Worker,
)
from continuum_db.models.library import (
    CharacterOutfit,
    CharacterProfile,
    IntakeBatch,
    LibraryAsset,
    LibraryAssetLocation,
    ProjectPanelSource,
    ProjectReferenceStanding,
    ProjectVisualModeAssignment,
    ReferenceCandidate,
    ReferenceCharacter,
    ReferenceDescriptor,
    ReferenceItem,
    ReferenceTechnique,
    ReferenceUseLink,
    VisualMode,
)
from continuum_db.models.manga import (
    ContinuityState,
    MaterializedChapter,
    PageDependency,
    ProductionPage,
    ProductionProfile,
    ProductionRun,
)
from continuum_db.models.production import (
    AttemptDerivative,
    AttemptInput,
    AttemptReview,
    GenerationRecipe,
    RoughArtifact,
    RoughAttempt,
)

__all__ = [
    "AttemptDerivative",
    "AttemptInput",
    "AttemptReview",
    "Base",
    "CatalogEntry",
    "CatalogMember",
    "CatalogScan",
    "CatalogUnit",
    "ChapterPackage",
    "CharacterObservation",
    "CharacterOutfit",
    "CharacterProductionEvidence",
    "CharacterProductionModel",
    "CharacterProfile",
    "ContinuityState",
    "GenerationRecipe",
    "IntakeBatch",
    "Job",
    "JobCheckpoint",
    "JobDependency",
    "JobEvent",
    "JobStep",
    "LibraryAsset",
    "LibraryAssetLocation",
    "MaterializedChapter",
    "MediaProgress",
    "MusicReference",
    "PageDependency",
    "ProductionPage",
    "ProductionProfile",
    "ProductionRun",
    "ProjectPanelSource",
    "ProjectReferenceStanding",
    "ProjectVisualModeAssignment",
    "ReferenceCandidate",
    "ReferenceCharacter",
    "ReferenceDescriptor",
    "ReferenceItem",
    "ReferenceManifest",
    "ReferenceTechnique",
    "ReferenceUseLink",
    "RoughArtifact",
    "RoughAttempt",
    "VisualMode",
    "Worker",
]
