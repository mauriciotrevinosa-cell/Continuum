"""Structured JSON logging with mandatory redaction.

Redaction happens in the *formatter*, not in a filter, and is applied to the
fully rendered record including the exception traceback. A filter that only
inspects ``record.msg`` misses secrets that arrive via ``args``, via
``exc_info``, or via a dependency's own log records -- and those are the
paths that actually leak.
"""

from __future__ import annotations

import datetime as _dt
import json
import logging
import sys
from typing import Any

from continuum_observability.correlation import current_correlation_id
from continuum_observability.redaction import redact

__all__ = ["JsonFormatter", "configure_logging", "get_logger"]

# Attributes LogRecord always carries; anything else was added by the caller
# via `extra=` and should be emitted as structured context.
_STANDARD_ATTRS = frozenset(
    {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "module",
        "msecs",
        "message",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "taskName",
        "thread",
        "threadName",
    }
)


class JsonFormatter(logging.Formatter):
    """One JSON object per line, with every field redacted."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            # Built from record.created rather than logging.Formatter.formatTime:
            # strftime has no millisecond directive, and %f/%03d raise
            # "Invalid format string" on Windows.
            "ts": _dt.datetime.fromtimestamp(record.created, _dt.UTC).isoformat(
                timespec="milliseconds"
            ),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        correlation_id = getattr(record, "correlation_id", None) or current_correlation_id()
        if correlation_id:
            payload["correlation_id"] = correlation_id

        for key, value in record.__dict__.items():
            if key not in _STANDARD_ATTRS and key != "correlation_id":
                payload[key] = value

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack"] = self.formatStack(record.stack_info)

        try:
            rendered = json.dumps(payload, default=str, ensure_ascii=False)
        except (TypeError, ValueError):  # pragma: no cover - defensive
            rendered = json.dumps(
                {"level": record.levelname, "logger": record.name, "message": str(record.msg)}
            )

        # Redact the whole rendered line: message, structured context and
        # traceback all pass through here exactly once.
        return redact(rendered)


def configure_logging(level: str = "INFO", *, stream: Any | None = None) -> None:
    """Install the JSON formatter on the root logger.

    Idempotent: replaces existing Continuum handlers rather than stacking
    duplicates when called twice (uvicorn reload, test fixtures).
    """
    root = logging.getLogger()
    for handler in list(root.handlers):
        if getattr(handler, "_continuum", False):
            root.removeHandler(handler)

    handler = logging.StreamHandler(stream if stream is not None else sys.stderr)
    handler.setFormatter(JsonFormatter())
    handler._continuum = True  # type: ignore[attr-defined]
    root.addHandler(handler)
    root.setLevel(level.upper())


def get_logger(name: str) -> logging.Logger:
    """Return a namespaced logger."""
    return logging.getLogger(name)
