"""Phase 1 reference vault: catalog, inbox, Character Vault and Style Vault.

Everything here reads source media through ``continuum_storage`` (read-only)
and writes only catalog rows and user-added bytes under writable roots.
"""

from continuum_library.catalog import (
    MAX_UPLOAD_IMAGE_BYTES,
    CharacterLink,
    DescriptorSpec,
    PanelSourceSpec,
    ReferenceCatalog,
    ReferenceSpec,
    StandingSpec,
    StoredImage,
    TechniqueLink,
    region_of,
)
from continuum_library.inbox import (
    MAX_UPLOAD_VIDEO_BYTES,
    AcceptSpec,
    CandidateDefaults,
    FileIntake,
    IntakeResult,
    ReferenceInbox,
    UrlEntry,
    download_name_facts,
)
from continuum_library.validation import (
    CatalogConflictError,
    CatalogInputError,
    CatalogNotFoundError,
)
from continuum_library.views import (
    candidate_view,
    character_summary,
    character_vault,
    reference_view,
    style_vault,
    visual_mode_view,
)

__all__ = [
    "MAX_UPLOAD_IMAGE_BYTES",
    "MAX_UPLOAD_VIDEO_BYTES",
    "AcceptSpec",
    "CandidateDefaults",
    "CatalogConflictError",
    "CatalogInputError",
    "CatalogNotFoundError",
    "CharacterLink",
    "DescriptorSpec",
    "FileIntake",
    "IntakeResult",
    "PanelSourceSpec",
    "ReferenceCatalog",
    "ReferenceInbox",
    "ReferenceSpec",
    "StandingSpec",
    "StoredImage",
    "TechniqueLink",
    "UrlEntry",
    "candidate_view",
    "character_summary",
    "character_vault",
    "download_name_facts",
    "reference_view",
    "region_of",
    "style_vault",
    "visual_mode_view",
]
