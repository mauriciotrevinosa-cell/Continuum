"""job_type -> handler registry (ADR-0002 section 14).

One worker process with pluggable handlers, not five worker services. The
five directories in Master Plan section 3 describe modules; five deployables
would be the microservice architecture section 111 forbids. Future horizontal
scaling differs by ``resource_class``, not by module.
"""

from __future__ import annotations

from continuum_core import ContinuumError, ErrorCategory

from continuum_jobs.execution import JobHandler

__all__ = ["HandlerRegistry", "UnknownJobTypeError", "registry"]


class UnknownJobTypeError(ContinuumError):
    """No handler is registered for a job type."""

    code = "jobs.unknown_job_type"
    category = ErrorCategory.PERMANENT_CONFIG


class HandlerRegistry:
    """Maps a job type string to the handler that executes it."""

    def __init__(self) -> None:
        self._handlers: dict[str, JobHandler] = {}

    def register(self, handler: JobHandler) -> JobHandler:
        job_type = handler.job_type
        if job_type in self._handlers:
            raise ValueError(f"duplicate handler registration for {job_type!r}")
        self._handlers[job_type] = handler
        return handler

    def get(self, job_type: str) -> JobHandler:
        try:
            return self._handlers[job_type]
        except KeyError:
            raise UnknownJobTypeError(
                f"No handler is registered for job type {job_type!r}.",
                technical_detail=f"registered: {sorted(self._handlers)}",
                remediation="Register the handler in the worker before starting it.",
            ) from None

    def known_types(self) -> list[str]:
        return sorted(self._handlers)

    def clear(self) -> None:
        self._handlers.clear()


registry = HandlerRegistry()
