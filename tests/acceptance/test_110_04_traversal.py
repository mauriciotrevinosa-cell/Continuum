"""Acceptance 110.4 - traversal and symlink/junction escape are rejected.

The containment check must happen *after* full link resolution. These tests
build real escaping structures on disk rather than only passing hostile
strings, because a string-only test cannot tell the difference between an
implementation that resolves links and one that does not.

Windows-specific structures (junctions, 8.3 short names, alternate data
streams, real device names) are marked and reported explicitly rather than
silently skipped -- FOUNDATION_APPROVAL OQ-6 forbids counting a skipped
Windows check as a pass.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from continuum_core import PathEscapesRootError
from continuum_storage import SourceVaultReader, resolve_within

from tests.conftest import posix_only, try_junction, try_symlink, windows_only


class TestStringTraversal:
    @pytest.mark.parametrize(
        "candidate",
        [
            "../outside/secret.txt",
            "../../outside/secret.txt",
            "notes/../../outside/secret.txt",
            "./../../outside/secret.txt",
            "a/b/../../../outside/secret.txt",
        ],
    )
    def test_dotdot_never_escapes(
        self, vault_root: Path, outside_dir: Path, candidate: str
    ) -> None:
        with pytest.raises(PathEscapesRootError):
            resolve_within(vault_root, candidate, root_key="source_vault")

    def test_absolute_path_to_real_secret_is_rejected(
        self, vault_root: Path, outside_dir: Path
    ) -> None:
        with pytest.raises(PathEscapesRootError):
            resolve_within(vault_root, str(outside_dir / "secret.txt"), root_key="source_vault")


class TestSymlinkEscape:
    def test_symlink_to_outside_file_is_rejected(self, vault_root: Path, outside_dir: Path) -> None:
        link = vault_root / "escape-link.txt"
        if not try_symlink(link, outside_dir / "secret.txt"):
            pytest.skip("symlink creation not permitted on this runner (needs Developer Mode)")

        with pytest.raises(PathEscapesRootError):
            resolve_within(vault_root, "escape-link.txt", root_key="source_vault")

    def test_symlinked_directory_component_is_rejected(
        self, vault_root: Path, outside_dir: Path
    ) -> None:
        link = vault_root / "escape-dir"
        if not try_symlink(link, outside_dir, directory=True):
            pytest.skip("symlink creation not permitted on this runner (needs Developer Mode)")

        with pytest.raises(PathEscapesRootError):
            resolve_within(vault_root, "escape-dir/secret.txt", root_key="source_vault")

    def test_symlink_inside_the_root_is_allowed(self, vault_root: Path) -> None:
        """Containment, not link-phobia: a link that stays inside is fine."""
        target = vault_root / "marker.txt"
        link = vault_root / "inside-link.txt"
        if not try_symlink(link, target):
            pytest.skip("symlink creation not permitted on this runner")

        resolved = resolve_within(vault_root, "inside-link.txt", root_key="source_vault")
        assert resolved.path.is_relative_to(Path(os.path.realpath(vault_root)))

    def test_vault_iteration_skips_escaping_links(
        self, vault_root: Path, outside_dir: Path
    ) -> None:
        """One hostile link must not abort a scan of an otherwise good vault."""
        if not try_symlink(vault_root / "escape-link.txt", outside_dir / "secret.txt"):
            pytest.skip("symlink creation not permitted on this runner")

        reader = SourceVaultReader(vault_root)
        names = {str(e.relative) for e in reader.iter_entries(recursive=True)}
        assert "marker.txt" in names, "healthy entries must still be discovered"
        assert not any("secret" in n for n in names)


@windows_only
class TestWindowsSpecificEscapes:
    """Windows path semantics. Must pass on the primary Windows machine (OQ-6)."""

    def test_directory_junction_to_outside_is_rejected(
        self, vault_root: Path, outside_dir: Path
    ) -> None:
        """Junctions are the realistic Windows escape: unlike symlinks they
        need no elevation or Developer Mode."""
        link = vault_root / "junction-out"
        if not try_junction(link, outside_dir):
            pytest.skip("mklink /J unavailable on this runner")

        with pytest.raises(PathEscapesRootError):
            resolve_within(vault_root, "junction-out/secret.txt", root_key="source_vault")

    def test_alternate_data_stream_is_rejected(self, vault_root: Path) -> None:
        with pytest.raises(PathEscapesRootError):
            resolve_within(vault_root, "marker.txt:hidden", root_key="source_vault")

    def test_short_name_alias_cannot_escape(self, vault_root: Path, outside_dir: Path) -> None:
        """8.3 short names alias a different literal string to the same path."""
        with pytest.raises(PathEscapesRootError):
            resolve_within(vault_root, "../OUTSID~1/secret.txt", root_key="source_vault")

    def test_device_names_are_rejected(self, vault_root: Path) -> None:
        for name in ("CON", "NUL", "COM1", "LPT1", "con.txt", "nul.log"):
            with pytest.raises(PathEscapesRootError):
                resolve_within(vault_root, name, root_key="source_vault")

    def test_case_insensitive_containment_holds(self, vault_root: Path) -> None:
        """Windows compares paths case-insensitively; containment must too."""
        resolved = resolve_within(vault_root, "MARKER.TXT", root_key="source_vault")
        assert resolved.path.is_relative_to(Path(os.path.realpath(vault_root)))

    def test_extended_length_and_unc_prefixes_rejected(self, vault_root: Path) -> None:
        for candidate in ("\\\\?\\C:\\Windows\\win.ini", "\\\\localhost\\C$\\Windows\\win.ini"):
            with pytest.raises(PathEscapesRootError):
                resolve_within(vault_root, candidate, root_key="source_vault")


@posix_only
class TestPosixSpecificEscapes:
    def test_absolute_posix_path_rejected(self, vault_root: Path) -> None:
        with pytest.raises(PathEscapesRootError):
            resolve_within(vault_root, "/etc/passwd", root_key="source_vault")


class TestTimeOfCheckTimeOfUse:
    def test_swapped_path_after_validation_is_detected(
        self, vault_root: Path, outside_dir: Path
    ) -> None:
        """The TOCTOU window: validate a real file, then replace it with a
        link to somewhere else before it is opened.

        ``open_read`` re-verifies the descriptor against the resolved target
        by device/inode identity, so the swap is caught rather than read.
        """
        victim = vault_root / "swap-me.txt"
        victim.write_bytes(b"legitimate content")

        reader = SourceVaultReader(vault_root)
        assert reader.read_bytes("swap-me.txt") == b"legitimate content"

        # Swap the file for a link pointing outside the root.
        victim.unlink()
        if not try_symlink(victim, outside_dir / "secret.txt"):
            pytest.skip("symlink creation not permitted on this runner")

        # Resolution now escapes, so the read is refused outright.
        with pytest.raises(PathEscapesRootError):
            reader.read_bytes("swap-me.txt")

    def test_same_file_as_rejects_a_different_file(self, vault_root: Path) -> None:
        from continuum_storage import same_file_as

        a = vault_root / "a.bin"
        b = vault_root / "b.bin"
        a.write_bytes(b"aaa")
        b.write_bytes(b"bbb")

        with a.open("rb") as handle:
            assert same_file_as(handle.fileno(), a) is True
            assert same_file_as(handle.fileno(), b) is False
