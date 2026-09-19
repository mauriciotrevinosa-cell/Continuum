"""Shared Phase 0 test fixtures.

Tests are allowed raw filesystem access (the import-boundary contract exempts
them): building a hostile directory tree is exactly what these tests are for.
"""

from __future__ import annotations

import functools
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
    # The database is always the isolated test database. A Settings built
    # without one falls back to the application's default URL - the user's real
    # catalog - and any DB test resolving this fixture would write into it.
    return Settings(
        _env_file=None,
        data_home=str(data_home),
        source_vault_root=str(vault_root),
        database_url=TEST_DATABASE_URL,
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


#: The database the suite runs against. **Never the application's database**:
#: from Phase 1 on PostgreSQL holds the user's curated reference catalog, and
#: the suite deletes job rows and drops every table in the migration round
#: trip. The name must end in ``_test`` or the suite refuses to use it.
TEST_DATABASE_URL = os.environ.get(
    "CONTINUUM_TEST_DATABASE_URL",
    "postgresql+psycopg://continuum:continuum_local_dev@127.0.0.1:5433/continuum_test",
)


def _application_databases() -> set[tuple[str | None, int | None, str | None]]:
    """(host, port, database) of every application database this checkout knows:
    the built-in default and whatever the local ``.env`` configures."""
    from sqlalchemy.engine import make_url

    urls = [Settings(_env_file=None).database_url.get_secret_value()]
    env_file = REPO_ROOT / ".env"
    if env_file.is_file():
        for line in env_file.read_text(encoding="utf-8", errors="replace").splitlines():
            key, sep, value = line.partition("=")
            if sep and key.strip() == "CONTINUUM_DATABASE_URL" and value.strip():
                urls.append(value.strip().strip('"').strip("'"))
    targets = set()
    for raw in urls:
        url = make_url(raw)
        targets.add((url.host, url.port, url.database))
    return targets


def _refuse_application_databases() -> None:
    """No test may ever open a connection to the application's database.

    It holds the user's real catalog and production history. A fixture that
    forgets the test URL must fail loudly here instead of writing test rows into
    it (which is exactly what happened before this guard existed).
    """
    from continuum_db import session as db_session
    from sqlalchemy.engine import make_url

    protected = _application_databases()
    original = db_session.create_engine

    def guarded(url: object, *args: object, **kwargs: object) -> object:
        target = make_url(str(url) if not hasattr(url, "database") else url)  # type: ignore[arg-type]
        if (target.host, target.port, target.database) in protected:
            raise RuntimeError(
                f"a test tried to open the application database {target.database!r}; "
                "tests use TEST_DATABASE_URL only"
            )
        return original(url, *args, **kwargs)  # type: ignore[arg-type]

    db_session.create_engine = guarded  # type: ignore[assignment]


_refuse_application_databases()


@functools.lru_cache(maxsize=1)
def database_available() -> tuple[bool, str]:
    """Whether the isolated test database is reachable, created and migrated."""
    import subprocess

    from continuum_db.session import reset_engine
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import make_url

    reset_engine()
    url = make_url(TEST_DATABASE_URL)
    name = url.database or ""
    if not name.endswith("_test") or not name.replace("_", "").isalnum():
        return False, f"refusing to run the suite against database {name!r} (must end in _test)"
    try:
        admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
        with admin.connect() as connection:
            exists = connection.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": name}
            ).scalar()
            if not exists:
                connection.execute(text(f'CREATE DATABASE "{name}"'))
        admin.dispose()
    except Exception as exc:
        return False, type(exc).__name__
    migrated = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=REPO_ROOT,
        env={**os.environ, "CONTINUUM_DATABASE_URL": TEST_DATABASE_URL},
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
    )
    if migrated.returncode != 0:
        return False, f"migrating the test database failed: {migrated.stderr[-400:]}"
    return True, "ok"


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
        database_url=TEST_DATABASE_URL,
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
