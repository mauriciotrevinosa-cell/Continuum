"""Secret redaction (F-53 / ADR-0004 section 9, acceptance test 110.13).

Two mechanisms, because either alone is insufficient:

* **Pattern** catches secrets whose shape is recognisable, including ones
  this process never loaded (a token pasted into an error message by a
  dependency).
* **Exact value** catches secrets that do *not* look like secrets -- a short
  shared token, a local database password like ``postgres``. Pattern
  matching cannot possibly recognise those, and they are exactly the kind
  this application actually holds.

The registry is populated when settings load, so every value the process
knows to be secret is scrubbed from every log record regardless of how it
reached the log.
"""

from __future__ import annotations

import re
import threading
from typing import Final

__all__ = ["REDACTED", "SecretRegistry", "redact", "secret_registry"]

REDACTED: Final = "[REDACTED]"

#: Shapes worth catching even when the value was never registered.
_PATTERNS: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(r"\bsk-[A-Za-z0-9_\-]{16,}"),  # OpenAI-style
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}"),  # GitHub tokens
    re.compile(r"\bxox[baprs]-[A-Za-z0-9\-]{10,}"),  # Slack
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),  # AWS access key id
    re.compile(r"\bBearer\s+[A-Za-z0-9._\-]{16,}", re.IGNORECASE),
    re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}"),  # JWT
    re.compile(r"-----BEGIN[A-Z ]*PRIVATE KEY-----.*?-----END[A-Z ]*PRIVATE KEY-----", re.DOTALL),
    # postgresql://user:password@host/db  -- redact only the password group
    re.compile(r"(?<=://)([^:/@\s]+):([^@/\s]+)(?=@)"),
    # key=value / "key": "value" for obviously sensitive key names
    re.compile(
        r"((?:password|passwd|secret|token|api[_\-]?key|authorization)\s*[=:]\s*)"
        r'("?)([^\s,;"\'}\)]{4,})(\2)',
        re.IGNORECASE,
    ),
)

#: Values shorter than this are not registered for exact-match redaction:
#: scrubbing every occurrence of a 3-character string would corrupt logs
#: without protecting anything meaningful.
_MIN_REGISTERABLE_LEN: Final = 4


class SecretRegistry:
    """Process-wide set of exact secret values to scrub from output."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._values: set[str] = set()

    def register(self, value: str | None) -> None:
        """Register a concrete secret value. Short/empty values are ignored."""
        if not value or len(value) < _MIN_REGISTERABLE_LEN:
            return
        with self._lock:
            self._values.add(value)

    def clear(self) -> None:
        with self._lock:
            self._values.clear()

    def snapshot(self) -> frozenset[str]:
        with self._lock:
            return frozenset(self._values)

    def redact(self, text: str) -> str:
        """Remove every registered value and every recognised pattern."""
        if not text:
            return text
        # Longest first, so a secret that contains another secret as a
        # substring is not partially replaced into an unrecognisable form.
        for value in sorted(self.snapshot(), key=len, reverse=True):
            if value in text:
                text = text.replace(value, REDACTED)
        for pattern in _PATTERNS:
            if pattern.groups >= 3:
                text = pattern.sub(
                    lambda m: f"{m.group(1)}{m.group(2)}{REDACTED}{m.group(4)}", text
                )
            elif pattern.groups == 2:
                text = pattern.sub(lambda m: f"{m.group(1)}:{REDACTED}", text)
            else:
                text = pattern.sub(REDACTED, text)
        return text


#: The shared registry. Settings load registers into this instance.
secret_registry = SecretRegistry()


def redact(text: str) -> str:
    """Convenience wrapper over the shared registry."""
    return secret_registry.redact(text)
