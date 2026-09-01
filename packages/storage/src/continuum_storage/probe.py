"""Non-mutating environment probes (FOUNDATION_APPROVAL A-01, F-13).

**A-01 is the binding constraint here.** Continuum must never attempt a test
write, delete, rename, mkdir, temporary-file creation or cleanup write inside
the Source Vault -- not even as a diagnostic. ADR-0001's original Layer 5
proposed exactly such a probe; the approval overrode it.

The invariant is: *Continuum itself is never the process that writes to the
vault.* Where OS-level write denial cannot be proven without mutating, the
honest answer is ``NOT_VERIFIED``, not a guess and certainly not a write.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

__all__ = [
    "SYNC_PROVIDER_MARKERS",
    "ReadOnlyStatus",
    "SyncFolderWarning",
    "VaultProtectionReport",
    "detect_sync_provider",
    "probe_vault_readonly",
]


class ReadOnlyStatus(StrEnum):
    """How confident we are that the OS denies writes to the vault."""

    VERIFIED_READONLY = "verified_readonly"
    """The OS reports the path is not writable by this process."""

    NOT_HARDENED = "not_hardened"
    """The OS reports the path *is* writable. Application layers still apply."""

    NOT_VERIFIED = "not_verified"
    """Cannot be determined without mutating the vault, which is forbidden."""

    ABSENT = "absent"
    """The configured vault path does not exist (normal: OQ-3 allows an
    external or disconnected disk)."""


#: Path segments and environment variables that indicate a cloud-sync root.
SYNC_PROVIDER_MARKERS: dict[str, tuple[str, ...]] = {
    "OneDrive": ("onedrive",),
    "Dropbox": ("dropbox",),
    "Google Drive": ("google drive", "googledrive", "my drive"),
    "iCloud Drive": ("iclouddrive", "icloud drive", "com~apple~clouddocs"),
    "Box": ("box sync",),
}


@dataclass(frozen=True, slots=True)
class SyncFolderWarning:
    """A configured root that sits inside a cloud-sync folder."""

    root_key: str
    path: str
    provider: str

    @property
    def message(self) -> str:
        return (
            f"Storage root '{self.root_key}' is inside {self.provider} "
            f"({self.path}). Cloud sync can present placeholder files that "
            f"stat() as real but block or fail on read, and can create "
            f"conflict copies that a scan would treat as new assets. Move "
            f"Continuum data roots to non-synced local storage "
            f"(FOUNDATION_APPROVAL OQ-2)."
        )


@dataclass(frozen=True, slots=True)
class VaultProtectionReport:
    """Result of inspecting Source Vault protection. Purely observational."""

    status: ReadOnlyStatus
    detail: str
    path: str

    @property
    def informational_only(self) -> bool:
        """Always true. This signal never gates boot.

        Application-level structural protection (ADR-0001 Layers 1-4) is
        mandatory regardless of what the OS reports, so a NOT_HARDENED result
        is a recommendation to the user, never a startup failure.
        """
        return True


def detect_sync_provider(path: str | os.PathLike[str]) -> str | None:
    """Return the cloud-sync provider containing ``path``, or ``None``.

    Purely a string/environment inspection: reads no file and writes nothing.
    """
    text = str(path).replace("\\", "/").lower()

    for provider, markers in SYNC_PROVIDER_MARKERS.items():
        for marker in markers:
            if f"/{marker}" in text or text.startswith(marker):
                return provider

    # OneDrive on Windows also advertises itself through the environment,
    # which catches a redirected OneDrive folder that is not named "OneDrive".
    for env_var in ("OneDrive", "OneDriveConsumer", "OneDriveCommercial"):
        configured = os.environ.get(env_var)
        if not configured:
            continue
        normalised = configured.replace("\\", "/").lower().rstrip("/")
        if normalised and (text == normalised or text.startswith(normalised + "/")):
            return "OneDrive"

    return None


def probe_vault_readonly(vault_root: str | os.PathLike[str]) -> VaultProtectionReport:
    """Inspect whether the OS denies writes to the vault, without writing.

    Never creates, renames or deletes anything. The only calls made are
    ``stat``-class and ``access``-class inspections.
    """
    path = Path(vault_root)
    text = str(path)

    if not path.exists():
        return VaultProtectionReport(
            status=ReadOnlyStatus.ABSENT,
            detail=(
                "Configured Source Vault path does not exist. This is not an "
                "error: an external or disconnected vault is expected (OQ-3)."
            ),
            path=text,
        )

    if os.name == "nt":
        # os.access(W_OK) on Windows only reflects the read-only *attribute*,
        # not the ACL that actually governs writes, so it cannot prove
        # hardening. Proving it would require attempting a write, which A-01
        # forbids outright. NOT_VERIFIED is the honest answer.
        return VaultProtectionReport(
            status=ReadOnlyStatus.NOT_VERIFIED,
            detail=(
                "Windows ACL enforcement cannot be observed non-mutatively, and "
                "Continuum must never test-write into the vault "
                "(FOUNDATION_APPROVAL A-01). Application-level protection is "
                "active regardless. Run scripts/harden_vault.ps1 to apply a "
                'deny-write ACE and confirm with: icacls "<vault>"'
            ),
            path=text,
        )

    writable = os.access(path, os.W_OK)
    if not writable:
        return VaultProtectionReport(
            status=ReadOnlyStatus.VERIFIED_READONLY,
            detail="The operating system reports this path is not writable by this process.",
            path=text,
        )

    return VaultProtectionReport(
        status=ReadOnlyStatus.NOT_HARDENED,
        detail=(
            "The operating system reports this path IS writable by this process. "
            "Continuum's own layers still make vault writes unrepresentable, but "
            "OS-level hardening (read-only mount, or an unprivileged runtime user) "
            "is recommended as defence in depth."
        ),
        path=text,
    )
