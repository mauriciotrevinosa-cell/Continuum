"""Correlation ids (F-71 / ADR-0006 section 1).

A correlation id is propagated request -> job -> step -> provider call.
Without one, debugging a failed six-hour job that spans three processes is
archaeology: the API log, the worker log and the job audit trail have no
shared key.

The id is carried in a ``ContextVar`` so it survives across await points
without being threaded through every function signature, and is copied onto
the durable ``job`` row at enqueue time so it survives process boundaries --
which a ContextVar alone cannot do.
"""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from contextvars import ContextVar, Token

from continuum_core import uuid7

__all__ = [
    "correlation_scope",
    "current_correlation_id",
    "new_correlation_id",
    "set_correlation_id",
]

_correlation_id: ContextVar[str | None] = ContextVar("continuum_correlation_id", default=None)


def new_correlation_id() -> str:
    """Mint a fresh correlation id."""
    return str(uuid7())


def current_correlation_id() -> str | None:
    """The correlation id in scope, or ``None`` outside any scope."""
    return _correlation_id.get()


def set_correlation_id(value: str | None) -> Token[str | None]:
    """Set the id directly. Prefer ``correlation_scope`` where possible."""
    return _correlation_id.set(value)


@contextlib.contextmanager
def correlation_scope(value: str | None = None) -> Iterator[str]:
    """Run a block under a correlation id, restoring the previous one after.

    Passing an existing id continues an inbound trace (an HTTP header, or
    the id stored on a job row); passing ``None`` starts a new one.
    """
    resolved = value or new_correlation_id()
    token = _correlation_id.set(resolved)
    try:
        yield resolved
    finally:
        _correlation_id.reset(token)
