"""Invariant - filesystem access stays inside continuum_storage.

ADR-0001 Layer 3. Type separation (Layer 1) only helps if nobody bypasses the
module, and this is the layer that prevents drift over years.

Two complementary checks:

* ``lint-imports`` (config in ``.importlinter``) enforces *module-level*
  bans -- nothing outside storage may import ``pathlib``, ``shutil``,
  ``tempfile``, ``zipfile`` and friends -- plus the package layering.
* The AST walk below enforces *call-level* bans that a module ban cannot
  express: ``os`` is legitimately used everywhere for ``os.environ`` and
  ``os.name``, but ``os.remove`` and bare ``open()`` are filesystem access.
"""

from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.conftest import REPO_ROOT

#: The one package allowed to touch the filesystem.
STORAGE_PACKAGE = REPO_ROOT / "packages" / "storage"

#: Product source that must NOT touch the filesystem directly.
GUARDED_SOURCE_ROOTS: tuple[Path, ...] = (
    REPO_ROOT / "packages" / "core",
    REPO_ROOT / "packages" / "config",
    REPO_ROOT / "packages" / "observability",
    REPO_ROOT / "packages" / "db",
    REPO_ROOT / "packages" / "jobs",
    REPO_ROOT / "packages" / "providers",
    REPO_ROOT / "apps" / "api",
    REPO_ROOT / "workers",
)

#: ``os`` members that perform filesystem access.
FORBIDDEN_OS_ATTRS = frozenset(
    {
        "open",
        "remove",
        "unlink",
        "rename",
        "replace",
        "mkdir",
        "makedirs",
        "rmdir",
        "removedirs",
        "walk",
        "listdir",
        "scandir",
        "chmod",
        "chown",
        "symlink",
        "link",
        "truncate",
        "fsync",
        "startfile",
        "sendfile",
    }
)

#: Callables that construct or touch filesystem paths.
FORBIDDEN_CALLS = frozenset({"open", "Path", "PosixPath", "WindowsPath"})

FORBIDDEN_MODULES = frozenset(
    {"pathlib", "shutil", "tempfile", "zipfile", "tarfile", "glob", "fileinput", "aiofiles"}
)


def _python_files(root: Path) -> list[Path]:
    return [
        p
        for p in root.rglob("*.py")
        if "__pycache__" not in p.parts and "migrations" not in p.parts
    ]


class FilesystemAccessVisitor(ast.NodeVisitor):
    """Collect filesystem access performed outside continuum_storage."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.violations: list[str] = []

    def _record(self, node: ast.AST, what: str) -> None:
        rel = self.path.relative_to(REPO_ROOT)
        self.violations.append(f"{rel}:{getattr(node, 'lineno', '?')}: {what}")

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            top = alias.name.split(".")[0]
            if top in FORBIDDEN_MODULES:
                self._record(node, f"imports {alias.name!r}")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module:
            top = node.module.split(".")[0]
            if top in FORBIDDEN_MODULES:
                self._record(node, f"imports from {node.module!r}")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        func = node.func
        if isinstance(func, ast.Name) and func.id in FORBIDDEN_CALLS:
            self._record(node, f"calls {func.id}()")
        elif isinstance(func, ast.Attribute):
            value = func.value
            if isinstance(value, ast.Name) and value.id == "os" and func.attr in FORBIDDEN_OS_ATTRS:
                self._record(node, f"calls os.{func.attr}()")
            if func.attr in {"read_text", "read_bytes", "write_text", "write_bytes"}:
                self._record(node, f"calls .{func.attr}() (path-like I/O)")
        self.generic_visit(node)


def test_no_filesystem_access_outside_storage() -> None:
    violations: list[str] = []
    checked = 0

    for root in GUARDED_SOURCE_ROOTS:
        if not root.is_dir():
            continue
        for path in _python_files(root):
            checked += 1
            source = path.read_text(encoding="utf-8")
            # An explicit, reviewed exemption. Deliberately noisy to write.
            if "continuum: allow-filesystem" in source:
                continue
            visitor = FilesystemAccessVisitor(path)
            visitor.visit(ast.parse(source, filename=str(path)))
            violations.extend(visitor.violations)

    assert checked > 0, "no product source discovered; this invariant would pass vacuously"
    assert violations == [], (
        "Only continuum_storage may perform filesystem access (ADR-0001 Layer 3):\n  "
        + "\n  ".join(violations)
        + "\n\nRoute the access through SourceVaultReader or DerivedStore."
    )


def test_storage_package_is_the_exception() -> None:
    """Confirm the guard would fire -- storage really does use these APIs.

    Without this, a bug that made the visitor detect nothing would leave the
    invariant above passing vacuously forever.
    """
    found = False
    for path in _python_files(STORAGE_PACKAGE):
        visitor = FilesystemAccessVisitor(path)
        visitor.visit(ast.parse(path.read_text(encoding="utf-8"), filename=str(path)))
        if visitor.violations:
            found = True
            break
    assert found, (
        "continuum_storage performs no detectable filesystem access, so the "
        "detector is broken and the boundary test is meaningless."
    )


def test_import_linter_contracts_hold() -> None:
    """Run the declared import-linter contracts (layering, forbidden modules)."""
    # The console script, not "python -m importlinter.cli": the module form
    # exits 0 without printing or running anything, which would make this
    # test pass vacuously while enforcing nothing.
    script = Path(sys.executable).parent / (
        "lint-imports.exe" if os.name == "nt" else "lint-imports"
    )
    if not script.is_file():
        pytest.skip(f"lint-imports console script not found at {script}")

    result = subprocess.run(
        [str(script)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        "import-linter contracts broken:\n" + result.stdout + result.stderr
    )
    assert "0 broken" in result.stdout, (
        "import-linter produced no contract summary, so it did not actually run:\n"
        + result.stdout
        + result.stderr
    )


def test_worker_does_not_import_the_api() -> None:
    """ADR-0002 topology: coordination is through PostgreSQL only."""
    for path in _python_files(REPO_ROOT / "workers"):
        source = path.read_text(encoding="utf-8")
        assert "continuum_api" not in source, (
            f"{path.relative_to(REPO_ROOT)} imports the API application. "
            "The worker coordinates only through PostgreSQL (ADR-0002 section 12)."
        )
