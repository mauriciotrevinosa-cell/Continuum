"""Shared Phase 0 test fixtures.

Tests are allowed raw filesystem access (the import-boundary contract exempts
them): building a hostile directory tree is exactly what these tests are for.
"""

from __future__ import annotations

import os
import shutil
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from continuum_config import WRITABLE_ROOT_KEYS, Settings
from continuum_storage import DerivedStore, SourceVaultReader

REPO_ROOT = Path(__file__).resolve().parents[1]
DEMO_VAULT = REPO_ROOT / "fixtures" / "demo_vault"

#: Every Python source directory that ships in the product, excluding tests.
PRODUCT_SOURCE_DIRS: tuple[Path, ...] = (
    REPO_ROOT / "packages",
    REPO_ROOT / "apps" / "api",
    REPO_ROOT / "workers",
)

windows_only = pytest.mark.skipif(
    os.name != "nt", reason="Windows path semantics; must be run on the Windows machine (OQ-6)"
)
posix_only = pytest.mark.skipif(os.name == "nt", reason="POSIX-only filesystem semantics")


@pytest.fixture
def data_home(tmp_path: Path) -> Path:
    """An isolated data home, standing in for the eight configured roots."""
    home = tmp_path / "ContinuumData"
    home.mkdir()
    return home


@pytest.fixture
def vault_root(tmp_path: Path) -> Path:
    """A writable *copy* of the synthetic demo vault.

    A copy, because tests must be able to build hostile structures (symlinks,
    junctions) inside it. Continuum itself still never writes here -- the test
    harness does, before handing the path to a SourceVaultReader.
    """
    destination = tmp_path / "source-vault"
    shutil.copytree(DEMO_VAULT, destination)
    return destination


@pytest.fixture
def settings(data_home: Path, vault_root: Path) -> Settings:
    return Settings(
        _env_file=None,
        data_home=str(data_home),
        source_vault_root=str(vault_root),
    )


@pytest.fixture
def vault(vault_root: Path) -> SourceVaultReader:
    return SourceVaultReader(vault_root)


@pytest.fixture
def derived(settings: Settings) -> DerivedStore:
    store = DerivedStore({key: settings.root(key) for key in WRITABLE_ROOT_KEYS})
    for key in WRITABLE_ROOT_KEYS:
        store.ensure_root(key)
    return store


@pytest.fixture(scope="session")
def fuzz_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Session-scoped root for property-based tests.

    Hypothesis cannot be combined with function-scoped fixtures, because the
    fixture would not be reset between generated examples.
    """
    return tmp_path_factory.mktemp("fuzz-root")


@pytest.fixture
def outside_dir(tmp_path: Path) -> Path:
    """A directory deliberately outside every configured root."""
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("must never be reachable through a root")
    return outside


def try_symlink(link: Path, target: Path, *, directory: bool = False) -> bool:
    """Create a symlink, returning False when the OS refuses.

    Windows needs Developer Mode or elevation for symlinks. A test that
    cannot create one must report that honestly rather than passing silently.
    """
    try:
        link.symlink_to(target, target_is_directory=directory)
    except (OSError, NotImplementedError):
        return False
    return True


def try_junction(link: Path, target: Path) -> bool:
    """Create a Windows directory junction (a reparse point, not a symlink).

    Junctions need no special privilege, which makes them the realistic
    escape vector on Windows.
    """
    if os.name != "nt":
        return False
    import subprocess

    result = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), str(target)],
        capture_output=True,
        check=False,
    )
    return result.returncode == 0 and link.exists()


@pytest.fixture
def snapshot_tree() -> Iterator[object]:
    """Helper for asserting a directory tree is byte-identical afterwards."""

    def snapshot(root: Path) -> dict[str, tuple[int, bytes]]:
        out: dict[str, tuple[int, bytes]] = {}
        for path in sorted(root.rglob("*")):
            rel = str(path.relative_to(root))
            if path.is_file():
                data = path.read_bytes()
                out[rel] = (path.stat().st_mtime_ns, data)
            else:
                out[rel] = (0, b"<dir>")
        return out

    yield snapshot


def database_available() -> tuple[bool, str]:
    """Whether a live PostgreSQL is reachable for the DB-dependent suite."""
    from continuum_db.session import database_is_reachable, reset_engine

    reset_engine()
    return database_is_reachable(Settings(_env_file=None, data_home=str(REPO_ROOT)))


@pytest.fixture(scope="session")
def db_settings(tmp_path_factory: pytest.TempPathFactory) -> Settings:
    """Settings pointing at the docker-compose database.

    Skips the whole DB suite when PostgreSQL is unreachable, with a message
    that names the exact command to fix it. Skipping is honest here; what
    would NOT be honest is reporting these acceptance items as PASS.
    """
    reachable, detail = database_available()
    if not reachable:
        pytest.skip(
            f"PostgreSQL is not reachable ({detail}). "
            "Start it with: docker compose up -d db && uv run alembic upgrade head"
        )
    home = tmp_path_factory.mktemp("db-data-home")
    return Settings(
        _env_file=None,
        data_home=str(home),
        source_vault_root=str(DEMO_VAULT),
    )


@pytest.fixture
def db_session(db_settings: Settings):
    """A transactional session against the live database."""
    from continuum_db.session import session_scope

    with session_scope(db_settings) as session:
        yield session


@pytest.fixture
def clean_jobs(db_session):
    """Remove all job rows so each test starts from a known state."""
    from continuum_db.models import Job, Worker
    from sqlalchemy import delete

    db_session.execute(delete(Job))
    db_session.execute(delete(Worker))
    db_session.commit()
    return db_session


def pytest_report_header(config: pytest.Config) -> list[str]:
    return [
        f"continuum: platform={sys.platform} os.name={os.name}",
        "continuum: Windows-only path tests "
        + ("ENABLED" if os.name == "nt" else "SKIPPED (see OQ-6)"),
        "continuum: database suite "
        + ("ENABLED" if database_available()[0] else "SKIPPED (no PostgreSQL reachable)"),
    ]
