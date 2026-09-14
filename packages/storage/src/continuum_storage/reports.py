"""Named reports under the generated root: coverage audits, import reports.

Content-addressed storage is right for artifacts; a report is different - a
person wants ``catalog/coverage-latest.md`` to be where they left it. Report
names come from code, never from a request, and are checked against a strict
pattern before they reach the filesystem. Writes land temp -> fsync -> atomic
rename in the report folder, so a reader never sees half a report.

Reports go to the writable ``generated`` root only: never the Source Vault,
never an intake folder, never the repository (ADR-0001).
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from continuum_core import uuid7

from continuum_storage.derived import DerivedStore
from continuum_storage.paths import resolve_within

__all__ = ["REPORT_ROOT", "StoredReport", "read_report", "write_report"]

REPORT_ROOT = "generated"
_CATEGORY = re.compile(r"^[a-z][a-z0-9-]{0,39}$")
_NAME = re.compile(r"^[a-z0-9][a-z0-9._-]{0,120}\.(json|md)$")


@dataclass(frozen=True, slots=True)
class StoredReport:
    category: str
    name: str
    size_bytes: int
    #: Root-relative, for display in a report index; never accepted back as input.
    relative: str


def _check(category: str, name: str) -> None:
    if not _CATEGORY.match(category) or not _NAME.match(name) or ".." in name:
        raise ValueError(f"not a valid report name: {category!r}/{name!r}")


def write_report(derived: DerivedStore, category: str, name: str, data: bytes) -> StoredReport:
    """Write (or replace) one named report atomically."""
    _check(category, name)
    root = derived.ensure_root(REPORT_ROOT)
    destination = resolve_within(root, f"reports/{category}/{name}", root_key=REPORT_ROOT)
    destination.path.parent.mkdir(parents=True, exist_ok=True)
    temp = destination.path.parent / f".tmp-{uuid7().hex}"
    try:
        with temp.open("wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, destination.path)
    except BaseException:
        temp.unlink(missing_ok=True)
        raise
    return StoredReport(category, name, len(data), f"reports/{category}/{name}")


def read_report(derived: DerivedStore, category: str, name: str) -> bytes | None:
    """A named report's bytes, or None when it was never written."""
    _check(category, name)
    root: Path = derived.root(REPORT_ROOT)
    target = resolve_within(root, f"reports/{category}/{name}", root_key=REPORT_ROOT)
    try:
        return target.path.read_bytes()
    except OSError:
        return None
