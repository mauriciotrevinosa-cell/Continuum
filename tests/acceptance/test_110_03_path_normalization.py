"""Acceptance 110.3 - configured roots resolve and normalise safely.

Also covers the structural validation rules of ADR-0001 Layer 2 that apply
identically on every platform.
"""

from __future__ import annotations

import os
from pathlib import Path, PurePath

import pytest
from continuum_config import ROOT_KEYS, WRITABLE_ROOT_KEYS, Settings
from continuum_core import PathEscapesRootError
from continuum_storage import (
    RESERVED_DEVICE_NAMES,
    resolve_within,
    validate_relative_candidate,
    validate_roots,
)
from hypothesis import given
from hypothesis import settings as hyp_settings
from hypothesis import strategies as st


class TestRootConfiguration:
    def test_all_eight_roots_resolve(self, settings: Settings) -> None:
        roots = settings.all_roots()
        assert set(roots) == set(ROOT_KEYS)
        assert len(ROOT_KEYS) == 8

    def test_source_vault_is_not_writable(self) -> None:
        assert "source_vault" not in WRITABLE_ROOT_KEYS
        assert len(WRITABLE_ROOT_KEYS) == 7

    def test_boot_creates_writable_roots_but_never_the_vault(
        self, settings: Settings, vault_root: Path
    ) -> None:
        statuses = validate_roots(settings, create=True)
        by_key = {s.key: s for s in statuses}

        for key in ("library", "projects", "generated", "cache", "config"):
            assert by_key[key].exists, f"{key} should have been created at boot"

        # The vault is never created by Continuum: authoring the user's media
        # directory would itself be a vault write (A-01).
        assert by_key["source_vault"].created is False

    def test_absent_vault_is_not_an_error(self, data_home: Path, tmp_path: Path) -> None:
        """OQ-3: an external or disconnected vault is a normal condition."""
        settings = Settings(
            _env_file=None,
            data_home=str(data_home),
            source_vault_root=str(tmp_path / "not-attached"),
        )
        statuses = validate_roots(settings, create=True)
        vault = next(s for s in statuses if s.key == "source_vault")
        assert vault.exists is False
        assert vault.created is False


class TestCandidateValidation:
    fuzz_root: Path

    @pytest.fixture(autouse=True)
    def _bind_fuzz_root(self, fuzz_root: Path) -> None:
        type(self).fuzz_root = fuzz_root

    @pytest.mark.parametrize(
        "candidate",
        [
            "notes/chapter-note-001.txt",
            "marker.txt",
            "franchises/demo-alpha/franchise.yaml",
            "a/b/c/d.txt",
            "file.with.many.dots.txt",
            "unicode-\u65e5\u672c\u8a9e.txt",
        ],
    )
    def test_accepts_ordinary_relative_paths(self, candidate: str) -> None:
        assert isinstance(validate_relative_candidate(candidate), PurePath)

    @pytest.mark.parametrize(
        ("candidate", "reason"),
        [
            ("", "empty"),
            ("a\x00b", "NUL byte"),
            ("a\x01b", "control character"),
            ("../escape.txt", "traversal"),
            ("a/../../escape.txt", "traversal"),
            ("..", "traversal"),
            ("/etc/passwd", "root-relative"),
            ("\\windows\\system32", "root-relative"),
            ("C:/Windows/System32", "absolute with drive"),
            ("C:relative", "drive-relative"),
            ("//server/share/file", "UNC"),
            ("\\\\server\\share\\file", "UNC"),
            ("\\\\?\\C:\\file", "extended-length prefix"),
            ("notes.txt:hidden", "alternate data stream"),
            ("trailing.", "trailing dot"),
            ("trailing ", "trailing space"),
            ("dir./file.txt", "trailing dot on a component"),
            ("CON", "reserved device name"),
            ("nul.txt", "reserved device name"),
            ("COM1", "reserved device name"),
            ("a/LPT9/b", "reserved device name"),
        ],
    )
    def test_rejects_dangerous_candidates(self, candidate: str, reason: str) -> None:
        with pytest.raises(PathEscapesRootError):
            validate_relative_candidate(candidate)

    def test_every_reserved_device_name_is_rejected(self) -> None:
        for name in RESERVED_DEVICE_NAMES:
            with pytest.raises(PathEscapesRootError):
                validate_relative_candidate(name)
            with pytest.raises(PathEscapesRootError):
                validate_relative_candidate(f"{name.lower()}.txt")

    @given(
        st.text(
            alphabet=st.characters(blacklist_categories=("Cs",)),
            min_size=1,
            max_size=60,
        )
    )
    @hyp_settings(max_examples=400, deadline=None)
    def test_fuzz_never_escapes_and_never_crashes(self, candidate: str) -> None:
        """Any string either resolves inside the root or raises. Never both,
        never anything else."""
        root = self.fuzz_root
        try:
            resolved = resolve_within(root, candidate, root_key="fuzz")
        except PathEscapesRootError:
            return
        except (ValueError, OSError):
            # A path the OS itself rejects as malformed is an acceptable
            # outcome; what matters is that it did not resolve outside.
            return
        real_root = Path(os.path.realpath(root))
        assert resolved.path == real_root or resolved.path.is_relative_to(real_root)
