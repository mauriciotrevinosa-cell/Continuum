"""Acceptance 110.5 - Continuum cannot write, delete or rename in the vault.

Four independent layers are asserted here, because any one of them alone
could be bypassed:

1. **Type level** - ``SourceVaultReader`` has no mutating member at all.
2. **Root table** - ``DerivedStore`` cannot even be constructed over the vault.
3. **Behaviour** - running the health/probe path leaves the vault byte-identical.
4. **No escape hatch** - no force flag, admin mode or override exists (D-13/OQ-5).

Layer 5 (the import boundary) lives in tests/invariants/test_import_boundaries.py.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest
from continuum_config import ROOT_KEYS, Settings
from continuum_core import VaultWriteAttemptedError
from continuum_storage import (
    DerivedStore,
    ReadOnlyStatus,
    SourceVaultReader,
    build_storage,
    probe_vault_readonly,
)

#: Any member name that would imply mutation. Asserting on names rather than
#: on behaviour is deliberate: a method that exists and raises is still a
#: method someone can be tempted to "fix".
MUTATING_NAMES = frozenset(
    {
        "write",
        "write_bytes",
        "write_text",
        "open_write",
        "create",
        "touch",
        "delete",
        "remove",
        "unlink",
        "rmdir",
        "rmtree",
        "rename",
        "replace",
        "move",
        "copy_into",
        "mkdir",
        "makedirs",
        "chmod",
        "truncate",
        "save",
        "put",
        "put_bytes",
        "store",
        "append",
        "update",
        "set",
        "sync",
    }
)


class TestTypeLevelImmutability:
    def test_reader_exposes_no_mutating_member(self) -> None:
        members = {name for name, _ in inspect.getmembers(SourceVaultReader)}
        offenders = sorted(members & MUTATING_NAMES)
        assert offenders == [], (
            f"SourceVaultReader gained mutating member(s) {offenders}. "
            "A vault write must remain unrepresentable, not merely disabled "
            "(ADR-0001 Layer 1)."
        )

    def test_reader_public_api_is_read_only(self) -> None:
        public = {
            name
            for name, value in inspect.getmembers(SourceVaultReader)
            if not name.startswith("_")
            and (inspect.isfunction(value) or isinstance(value, property))
        }
        expected = {
            "content_hash",
            "entry",
            "exists",
            "iter_entries",
            "open_read",
            "read_bytes",
            "resolve",
            "root",
            "root_key",
            "stat",
        }
        assert public == expected, (
            f"SourceVaultReader public surface changed: {sorted(public ^ expected)}. "
            "Every method must be a read."
        )

    def test_open_read_returns_a_read_only_handle(self, vault: SourceVaultReader) -> None:
        with vault.open_read("marker.txt") as handle:
            assert handle.readable() is True
            assert handle.writable() is False


class TestWritableStoreCannotTargetTheVault:
    def test_derived_store_rejects_the_vault_root_key(self, settings: Settings) -> None:
        with pytest.raises(VaultWriteAttemptedError):
            DerivedStore({"source_vault": settings.root("source_vault")})

    def test_derived_store_rejects_vault_mixed_with_valid_roots(self, settings: Settings) -> None:
        with pytest.raises(VaultWriteAttemptedError):
            DerivedStore(
                {
                    "cache": settings.root("cache"),
                    "source_vault": settings.root("source_vault"),
                }
            )

    def test_built_store_has_no_vault_root(self, settings: Settings) -> None:
        env = build_storage(settings)
        assert "source_vault" not in env.derived.root_keys
        assert len(env.derived.root_keys) == 7

    def test_asking_a_built_store_for_the_vault_raises(self, derived: DerivedStore) -> None:
        with pytest.raises(VaultWriteAttemptedError):
            derived.root("source_vault")

    def test_writes_land_only_in_writable_roots(
        self, derived: DerivedStore, vault_root: Path, snapshot_tree
    ) -> None:
        before = snapshot_tree(vault_root)
        stored = derived.put_bytes("cache", b"derived artifact")
        assert stored.path.is_relative_to(derived.root("cache"))
        assert not stored.path.is_relative_to(vault_root)
        assert snapshot_tree(vault_root) == before


class TestVaultIsUntouchedByOperation:
    def test_probe_does_not_write_to_the_vault(self, vault_root: Path, snapshot_tree) -> None:
        """FOUNDATION_APPROVAL A-01: not even a diagnostic write is allowed.

        ADR-0001's original Layer 5 proposed probing read-only status by
        creating a file in the vault. The approval overrode that. This test
        is what keeps the override honest.
        """
        before = snapshot_tree(vault_root)
        for _ in range(3):
            probe_vault_readonly(vault_root)
        assert snapshot_tree(vault_root) == before

    def test_full_boot_does_not_write_to_the_vault(
        self, settings: Settings, vault_root: Path, snapshot_tree
    ) -> None:
        before = snapshot_tree(vault_root)
        env = build_storage(settings, create=True)
        env.summary()
        assert snapshot_tree(vault_root) == before

    def test_reading_does_not_change_content(
        self, vault: SourceVaultReader, vault_root: Path, snapshot_tree
    ) -> None:
        before = snapshot_tree(vault_root)
        vault.read_bytes("marker.txt")
        vault.content_hash("marker.txt")
        list(vault.iter_entries(recursive=True))
        vault.entry("marker.txt")
        after = snapshot_tree(vault_root)
        assert {k: v[1] for k, v in after.items()} == {k: v[1] for k, v in before.items()}

    def test_probe_never_reports_a_guess(self, vault_root: Path) -> None:
        """Where OS hardening cannot be proven without writing, the honest
        answer is NOT_VERIFIED (A-01)."""
        report = probe_vault_readonly(vault_root)
        assert report.status in set(ReadOnlyStatus)
        assert report.informational_only is True
        assert report.detail


class TestNoEscapeHatch:
    """D-13 / OQ-5: no force flag, admin mode or override may exist."""

    def test_reader_constructor_takes_no_write_option(self) -> None:
        params = set(inspect.signature(SourceVaultReader.__init__).parameters)
        forbidden = {"writable", "allow_write", "force", "readonly", "admin", "unsafe"}
        assert params & forbidden == set()

    def test_settings_expose_no_vault_write_toggle(self) -> None:
        names = set(Settings.model_fields)
        suspicious = {
            n
            for n in names
            if any(t in n for t in ("allow_write", "force", "unsafe", "admin", "override"))
        }
        assert suspicious == set(), f"possible vault escape hatch in settings: {suspicious}"

    def test_source_vault_is_the_only_read_only_root(self) -> None:
        from continuum_config import WRITABLE_ROOT_KEYS

        assert set(ROOT_KEYS) - set(WRITABLE_ROOT_KEYS) == {"source_vault"}
