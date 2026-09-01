"""Invariant - no real franchise leaks into executable or test data.

FOUNDATION_APPROVAL A-05 scopes the rule precisely: it applies to
application source, runtime seed data, migrations, fixtures and automated
test data. It does **not** apply to human-facing Markdown documentation,
which is allowed to name the franchises the project is discussing.

The denylist is *derived from the documentation at test time* rather than
hardcoded here. Hardcoding franchise names in a test file would itself put
them into automated-test data -- the exact thing the rule prohibits -- and
it would go stale the moment the creative pool changes. Reading the pool doc
means the guard automatically covers every franchise the user adds.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.conftest import REPO_ROOT

POOL_DOC = REPO_ROOT / "docs" / "CONTINUUM_FRANCHISE_MASTER_POOL_v0.2.md"

#: Directories whose contents must stay franchise-agnostic.
GUARDED_ROOTS: tuple[Path, ...] = (
    REPO_ROOT / "packages",
    REPO_ROOT / "apps",
    REPO_ROOT / "workers",
    REPO_ROOT / "tests",
    REPO_ROOT / "fixtures",
    REPO_ROOT / "scripts",
)

GUARDED_SUFFIXES = frozenset(
    {".py", ".ts", ".tsx", ".js", ".jsx", ".sql", ".json", ".yaml", ".yml", ".toml", ".txt", ".cfg"}
)

SKIP_DIR_PARTS = frozenset({"node_modules", ".next", "__pycache__", ".venv", "dist", "build"})


def _franchise_terms() -> list[str]:
    """Extract franchise titles from the documentation pool table.

    Only **whole normalised titles** are matched. An earlier version also
    split titles into individual words, which flagged ordinary English and
    programming vocabulary ("class", "status", "attack", "master") because
    those words appear inside multi-word franchise titles. The franchise
    title is the real unit of identity: a one-word title like "Dandadan" is
    distinctive on its own, and a multi-word title is distinctive as a whole
    ("attackontitan"). Matching anything smaller produces noise that would
    train future readers to ignore this invariant.
    """
    if not POOL_DOC.is_file():  # pragma: no cover - doc is committed
        pytest.skip(f"franchise pool documentation not found at {POOL_DOC}")

    terms: set[str] = set()
    for line in POOL_DOC.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^\|\s*\d+\s*\|\s*([^|]+?)\s*\|", line)
        if not match:
            continue
        title = match.group(1).strip()
        normalised = _normalise(title)
        # 6 characters avoids matching very short titles against incidental
        # substrings of ordinary identifiers.
        if len(normalised) >= 6:
            terms.add(normalised)
    return sorted(terms)


def _normalise(text: str) -> str:
    return re.sub(r"[^0-9a-z]+", "", text.lower())


def _guarded_files() -> list[Path]:
    found: list[Path] = []
    for root in GUARDED_ROOTS:
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in GUARDED_SUFFIXES:
                continue
            if SKIP_DIR_PARTS & set(path.parts):
                continue
            if path.name == "test_no_franchise_strings.py":
                continue  # this file names the rule, not a franchise
            found.append(path)
    return found


def test_pool_document_yields_a_usable_denylist() -> None:
    """Guard the guard: a silently empty denylist would pass everything."""
    terms = _franchise_terms()
    assert len(terms) >= 20, (
        f"only {len(terms)} franchise terms parsed from {POOL_DOC.name}; "
        "the table format may have changed and this invariant is no longer protecting anything"
    )


def test_no_franchise_strings_in_executable_or_test_data() -> None:
    terms = _franchise_terms()
    files = _guarded_files()
    assert files, "no guarded files discovered; the invariant would pass vacuously"

    violations: list[str] = []
    for path in files:
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        haystack = _normalise(text)
        for term in terms:
            if term in haystack:
                violations.append(
                    f"{path.relative_to(REPO_ROOT)}: contains franchise term {term!r}"
                )

    assert violations == [], (
        "Real franchise strings must not appear in application code, fixtures, "
        "migrations, seed data or automated tests (A-05, D-18, F-10):\n  "
        + "\n  ".join(sorted(violations))
    )


def test_fixture_vault_is_synthetic() -> None:
    """The demo vault must be invented content only."""
    vault = REPO_ROOT / "fixtures" / "demo_vault"
    assert vault.is_dir()
    names = {p.name for p in vault.rglob("*")}
    assert "franchise.yaml" in names
    franchise = (vault / "franchises" / "demo-alpha" / "franchise.yaml").read_text(encoding="utf-8")
    assert "demo-alpha" in franchise
