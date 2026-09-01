"""Engine and session factory.

PostgreSQL is the sole durable job store (D-02). There is no SQLite fallback:
`FOR UPDATE SKIP LOCKED` does not exist there, so the queue would be built on
a different concurrency model than it ships with and acceptance tests
110.6-110.11 would be testing the wrong thing (FOUNDATION_APPROVAL OQ-1).
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager

from continuum_config import Settings, get_settings
from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

__all__ = [
    "build_engine",
    "database_is_reachable",
    "dispose_engine",
    "reset_engine",
    "session_factory",
    "session_scope",
]

# Engines are cached **per database URL**, not in a single process-wide slot.
#
# The earlier single-slot cache returned the first engine ever built and
# silently ignored the Settings it was handed. That is a latent correctness
# bug, not merely a testing inconvenience: any caller passing different
# settings would transparently get the wrong database, and /ready could report
# on a database the request was not asking about.
#
# Keying by URL keeps the real benefit of caching (one connection pool per
# database) while making the function honour its own argument.
_engines: dict[str, Engine] = {}
_factories: dict[str, sessionmaker[Session]] = {}
_lock = threading.Lock()


def _url_of(settings: Settings | None) -> tuple[Settings, str]:
    resolved = settings or get_settings()
    return resolved, resolved.database_url.get_secret_value()


def build_engine(settings: Settings | None = None, *, echo: bool = False) -> Engine:
    """Return the engine for these settings' database, creating it once."""
    resolved, url = _url_of(settings)

    with _lock:
        engine = _engines.get(url)
        if engine is not None:
            return engine

        engine = create_engine(
            url,
            echo=echo,
            pool_size=resolved.db_pool_size,
            pool_pre_ping=True,
            future=True,
            # A readiness probe that hangs is useless: without an explicit
            # timeout, connecting to an unreachable host blocks for the OS TCP
            # default (which on Windows can exceed 20s) and /ready never answers.
            connect_args={"connect_timeout": 3},
        )

        @event.listens_for(engine, "connect")
        def _set_session_defaults(dbapi_connection, _record):  # type: ignore[no-untyped-def]
            with dbapi_connection.cursor() as cursor:
                cursor.execute("SET TIME ZONE 'UTC'")

        _engines[url] = engine
        return engine


def session_factory(settings: Settings | None = None) -> sessionmaker[Session]:
    """Return the session factory bound to these settings' database."""
    _, url = _url_of(settings)
    with _lock:
        factory = _factories.get(url)
    if factory is not None:
        return factory

    # build_engine takes the lock itself, so it is called outside the guard.
    bound = sessionmaker(bind=build_engine(settings), expire_on_commit=False, future=True)
    with _lock:
        return _factories.setdefault(url, bound)


@contextmanager
def session_scope(settings: Settings | None = None) -> Iterator[Session]:
    """Transactional scope: commit on success, roll back on error."""
    session = session_factory(settings)()
    try:
        yield session
        session.commit()
    except BaseException:
        session.rollback()
        raise
    finally:
        session.close()


def database_is_reachable(settings: Settings | None = None) -> tuple[bool, str]:
    """Cheap liveness probe for /ready. Never raises."""
    try:
        engine = build_engine(settings)
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception as exc:
        return False, type(exc).__name__
    return True, "ok"


def dispose_engine(settings: Settings) -> None:
    """Dispose and drop the cached engine for ONE database.

    Preferred over :func:`reset_engine` inside a test suite: dropping every
    engine would also dispose the live acceptance database's pool, which other
    tests in the same run are still using.
    """
    _, url = _url_of(settings)
    with _lock:
        engine = _engines.pop(url, None)
        _factories.pop(url, None)
    if engine is not None:
        engine.dispose()


def reset_engine() -> None:
    """Dispose and drop every cached engine/factory.

    Whole-process reset. Use :func:`dispose_engine` when other databases in
    the same process must keep working.
    """
    with _lock:
        engines = list(_engines.values())
        _engines.clear()
        _factories.clear()
    for engine in engines:
        engine.dispose()
