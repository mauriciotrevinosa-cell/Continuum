"""Storage root registry and boot validation (ADR-0001 sections 1 and 5).

The eight roots of Master Plan section 108 are configured absolute paths
**outside the repository** (D-01). This module resolves them, creates the
writable ones, and reports on the vault -- without ever writing to the vault.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from continuum_config import ROOT_KEYS, WRITABLE_ROOT_KEYS, Settings

from continuum_storage.derived import DerivedStore
from continuum_storage.probe import (
    ReadOnlyStatus,
    SyncFolderWarning,
    VaultProtectionReport,
    detect_sync_provider,
    probe_vault_readonly,
)
from continuum_storage.vault import SourceVaultReader

__all__ = [
    "RootStatus",
    "StorageEnvironment",
    "build_storage",
    "validate_roots",
]

#: Roots created on demand rather than at boot: they only matter once real
#: media jobs and model assets exist (Phase 1+).
_LAZY_ROOTS = frozenset({"jobs", "models"})


@dataclass(frozen=True, slots=True)
class RootStatus:
    """Boot-time observation about one configured root."""

    key: str
    path: str
    writable: bool
    exists: bool
    created: bool
    sync_provider: str | None


@dataclass(frozen=True, slots=True)
class StorageEnvironment:
    """Everything the rest of the application needs from storage."""

    vault: SourceVaultReader
    derived: DerivedStore
    roots: tuple[RootStatus, ...]
    vault_protection: VaultProtectionReport
    sync_warnings: tuple[SyncFolderWarning, ...]

    @property
    def healthy(self) -> bool:
        """True when every eagerly-required writable root is usable.

        Deliberately does **not** consider the vault: a missing or
        unhardened vault is a normal operating condition (OQ-3, A-01), not a
        failure to boot.
        """
        return all(r.exists for r in self.roots if r.writable and r.key not in _LAZY_ROOTS)

    def summary(self) -> dict[str, object]:
        """Non-secret status for /health and /ready."""
        return {
            "healthy": self.healthy,
            "roots": [
                {
                    "key": r.key,
                    "writable": r.writable,
                    "exists": r.exists,
                    "created": r.created,
                    "sync_provider": r.sync_provider,
                }
                for r in self.roots
            ],
            "vault_protection": {
                "status": self.vault_protection.status.value,
                "detail": self.vault_protection.detail,
                "informational_only": self.vault_protection.informational_only,
            },
            "sync_warnings": [w.message for w in self.sync_warnings],
        }


def validate_roots(settings: Settings, *, create: bool = True) -> tuple[RootStatus, ...]:
    """Resolve every configured root, creating writable ones when asked.

    The Source Vault is never created: Continuum does not author the user's
    media directory, and creating it would be a vault write (A-01).
    """
    statuses: list[RootStatus] = []
    for key in ROOT_KEYS:
        raw = settings.root(key)
        path = Path(raw)
        writable = key in WRITABLE_ROOT_KEYS
        created = False
        if create and writable and key not in _LAZY_ROOTS and not path.exists():
            path.mkdir(parents=True, exist_ok=True)
            created = True
        statuses.append(
            RootStatus(
                key=key,
                path=str(path),
                writable=writable,
                exists=path.exists(),
                created=created,
                sync_provider=detect_sync_provider(path),
            )
        )
    return tuple(statuses)


def build_storage(settings: Settings, *, create: bool = True) -> StorageEnvironment:
    """Construct the storage environment for a process at startup."""
    statuses = validate_roots(settings, create=create)

    vault = SourceVaultReader(settings.root("source_vault"))
    derived = DerivedStore({key: settings.root(key) for key in WRITABLE_ROOT_KEYS})

    warnings = tuple(
        SyncFolderWarning(root_key=s.key, path=s.path, provider=s.sync_provider)
        for s in statuses
        if s.sync_provider is not None
    )

    return StorageEnvironment(
        vault=vault,
        derived=derived,
        roots=statuses,
        vault_protection=probe_vault_readonly(settings.root("source_vault")),
        sync_warnings=warnings,
    )


def vault_is_absent(env: StorageEnvironment) -> bool:
    """Convenience predicate: the vault disk is not currently attached."""
    return env.vault_protection.status is ReadOnlyStatus.ABSENT
