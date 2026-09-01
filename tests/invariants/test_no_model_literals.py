"""Invariant - model identifiers live only in the registry and config.

ADR-0004 section 4. This is how "model-agnostic" stops being an aspiration:
if an application module may not name a model, it cannot quietly become
dependent on one.
"""

from __future__ import annotations

import re
from pathlib import Path

from tests.conftest import REPO_ROOT

#: Where a model identifier is legitimately allowed to appear.
ALLOWED = (
    REPO_ROOT / "packages" / "providers" / "src" / "continuum_providers" / "registry.py",
    REPO_ROOT / "packages" / "providers" / "src" / "continuum_providers" / "fakes",
    REPO_ROOT / "packages" / "config",
)

GUARDED_ROOTS = (
    REPO_ROOT / "packages",
    REPO_ROOT / "apps" / "api",
    REPO_ROOT / "workers",
)

#: Naming shapes used by real model identifiers. Deliberately shape-based
#: rather than a vendor denylist: a denylist goes stale the moment a new
#: vendor appears, while these shapes are how model ids are actually written.
PATTERNS = (
    re.compile(r"\bgpt-[0-9]", re.IGNORECASE),
    re.compile(r"\bclaude-[a-z0-9]", re.IGNORECASE),
    re.compile(r"\bgemini-[0-9]", re.IGNORECASE),
    re.compile(r"\bllama-?[0-9]", re.IGNORECASE),
    re.compile(r"\bmistral-[a-z0-9]", re.IGNORECASE),
    re.compile(r"\bstable-diffusion", re.IGNORECASE),
    re.compile(r"\bwhisper-(tiny|base|small|medium|large)", re.IGNORECASE),
    re.compile(r"\btext-embedding-", re.IGNORECASE),
    re.compile(r"\bsd(xl|-turbo)\b", re.IGNORECASE),
)


def _is_allowed(path: Path) -> bool:
    return any(path == a or a in path.parents for a in ALLOWED)


def test_no_model_identifiers_in_application_logic() -> None:
    violations: list[str] = []
    checked = 0

    for root in GUARDED_ROOTS:
        if not root.is_dir():
            continue
        for path in root.rglob("*.py"):
            if "__pycache__" in path.parts or _is_allowed(path):
                continue
            checked += 1
            text = path.read_text(encoding="utf-8")
            for pattern in PATTERNS:
                for match in pattern.finditer(text):
                    line = text[: match.start()].count("\n") + 1
                    violations.append(
                        f"{path.relative_to(REPO_ROOT)}:{line}: model identifier {match.group(0)!r}"
                    )

    assert checked > 0, "no source scanned; this invariant would pass vacuously"
    assert violations == [], (
        "Model identifiers belong only in the provider registry and config "
        "(ADR-0004 section 4, Master Plan section 90):\n  " + "\n  ".join(violations)
    )


def test_the_pattern_set_actually_matches_model_identifiers() -> None:
    """Guard the guard: a broken regex set would pass everything."""
    samples = ["gpt-4o", "claude-opus-5", "gemini-2.0", "llama-3", "stable-diffusion-xl"]
    for sample in samples:
        assert any(p.search(sample) for p in PATTERNS), f"no pattern matches {sample!r}"
