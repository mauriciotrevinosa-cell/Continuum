"""The only module in Continuum permitted filesystem access (ADR-0001 Layer 3).

Enforced by the import-linter contract in ``.importlinter``: no other package
may import ``os``, ``pathlib``, ``shutil``, ``tempfile``, ``zipfile`` or call
bare ``open()`` for filesystem work.
"""

from continuum_storage.derived import DerivedStore, StoredArtifact
from continuum_storage.paths import (
    RESERVED_DEVICE_NAMES,
    ResolvedPath,
    resolve_within,
    same_file_as,
    validate_relative_candidate,
)
from continuum_storage.probe import (
    ReadOnlyStatus,
    SyncFolderWarning,
    VaultProtectionReport,
    detect_sync_provider,
    probe_vault_readonly,
)
from continuum_storage.roots import (
    RootStatus,
    StorageEnvironment,
    build_storage,
    validate_roots,
)
from continuum_storage.vault import SourceVaultReader, VaultEntry

__all__ = [
    "RESERVED_DEVICE_NAMES",
    "DerivedStore",
    "ReadOnlyStatus",
    "ResolvedPath",
    "RootStatus",
    "SourceVaultReader",
    "StorageEnvironment",
    "StoredArtifact",
    "SyncFolderWarning",
    "VaultEntry",
    "VaultProtectionReport",
    "build_storage",
    "detect_sync_provider",
    "probe_vault_readonly",
    "resolve_within",
    "same_file_as",
    "validate_relative_candidate",
    "validate_roots",
]
