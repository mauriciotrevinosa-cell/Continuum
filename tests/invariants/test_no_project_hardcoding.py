"""Invariant - no creative project is hardcoded into generic infrastructure.

Continuum works with zero projects; a project exists because a manifest
describes it. The Phase 1 kickoff adds the explicit rule: the first project
used to prove the rough-manga slice must not leak into packages, the API, the
web app or the worker. The project ids and titles are read from the committed
manifests at test time, so this file names none of them.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

import pytest

from tests.conftest import REPO_ROOT

MANIFEST_ROOT = REPO_ROOT / "docs" / "creative"
GUARDED_ROOTS: tuple[Path, ...] = (
    REPO_ROOT / "packages",
    REPO_ROOT / "apps",
    REPO_ROOT / "workers",
)
SUFFIXES = frozenset({".py", ".ts", ".tsx", ".js", ".json", ".toml", ".sql", ".css"})
SKIP_DIRS = frozenset({"node_modules", "__pycache__", "generated"})


def _normal(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _terms() -> list[str]:
    manifests = list(MANIFEST_ROOT.rglob("continuum.project.json"))
    if not manifests:  # pragma: no cover - the creative docs are committed
        pytest.skip("no project manifests to derive terms from")
    terms: set[str] = set()
    for manifest in manifests:
        data = json.loads(manifest.read_text(encoding="utf-8"))
        for value in (data.get("id"), data.get("title")):
            if isinstance(value, str) and len(_normal(value)) >= 6:
                terms.add(_normal(value))
    return sorted(terms)


def test_no_project_id_or_title_in_product_source() -> None:
    terms = _terms()
    assert terms, "no project terms derived; the invariant would pass vacuously"
    offenders: list[str] = []
    for root in GUARDED_ROOTS:
        for base, dirs, files in os.walk(root):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
            for name in files:
                path = Path(base) / name
                if path.suffix not in SUFFIXES:
                    continue
                text = _normal(path.read_text(encoding="utf-8", errors="ignore"))
                offenders.extend(f"{path.relative_to(REPO_ROOT)}: {t}" for t in terms if t in text)
    assert offenders == [], f"project names hardcoded in product source: {offenders}"
