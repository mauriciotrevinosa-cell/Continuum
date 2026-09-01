"""Engine and session factory.

PostgreSQL is the sole durable job store (D-02). There is no SQLite fallback:
`FOR UPDATE SKIP LOCKED` does not exist there, so the queue would be built on
a different concurrency model than it ships with and acceptance tests
110.6-110.11 would be testing the wrong thing (FOUNDATION_APPROVAL OQ-1).
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from continuum_config import Settings, get_settings
from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

__all__ = ["build_engine", "database_is_reachable", "session_factory", "session_scope"]

_engine: Engine | None = None
_factory: sessionmaker[Session] | None = None


def build_engine(settings: Settings | None = None, *, echo: bool = False) -> Engine:
    """Create (once) the process-wide engine."""
    global _engine
    if _engine is not None:
        return _engine
    resolved = settings or get_settings()
    _engine = create_engine(
        resolved.database_url.get_secret_value(),
        echo=echo,
        pool_size=resolved.db_pool_size,
        pool_pre_ping=True,
        future=True,
        # A readiness probe that hangs is useless: without an explicit
        # timeout, connecting to an unreachable host blocks for the OS TCP
        # default (which on Windows can exceed 20s) and /ready never answers.
        connect_args={"connect_timeout": 3},
    )

    @event.listens_for(_engine, "connect")
    def _set_session_defaults(dbapi_connection, _record):  # type: ignore[no-untyped-def]
        with dbapi_connection.cursor() as cursor:
            cursor.execute("SET TIME ZONE 'UTC'")

    return _engine


def session_factory(settings: Settings | None = None) -> sessionmaker[Session]:
    global _factory
    if _factory is None:
        _factory = sessionmaker(bind=build_engine(settings), expire_on_commit=False, future=True)
    return _factory


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


def reset_engine() -> None:
    """Drop cached engine/factory. Tests only."""
    global _engine, _factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _factory = None
