"""Structured error taxonomy (F-70 / ADR-0002 section 6).

Free-text errors make the Production Queue a wall of stack traces and make
retry classification impossible. Handlers raise typed errors carrying their
own classification; the framework never guesses retryability from an
exception type at the call site.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

__all__ = [
    "ContinuumError",
    "ErrorCategory",
    "IllegalTransitionError",
    "PathEscapesRootError",
    "PolicyViolationError",
    "ProviderUnavailableError",
    "StructuredError",
    "VaultWriteAttemptedError",
]


class ErrorCategory(StrEnum):
    """Whether and why an error may be retried."""

    RETRYABLE_TRANSIENT = "RETRYABLE_TRANSIENT"
    RETRYABLE_RESOURCE = "RETRYABLE_RESOURCE"
    PERMANENT_INPUT = "PERMANENT_INPUT"
    PERMANENT_CONFIG = "PERMANENT_CONFIG"

    @property
    def retryable(self) -> bool:
        return self in (ErrorCategory.RETRYABLE_TRANSIENT, ErrorCategory.RETRYABLE_RESOURCE)


@dataclass(frozen=True, slots=True)
class StructuredError:
    """The serialisable form stored on ``job.last_error`` and job events."""

    code: str
    category: ErrorCategory
    user_message: str
    technical_detail: str = ""
    remediation: str | None = None
    context: dict[str, Any] = field(default_factory=dict)

    @property
    def retryable(self) -> bool:
        return self.category.retryable

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "category": self.category.value,
            "retryable": self.retryable,
            "user_message": self.user_message,
            "technical_detail": self.technical_detail,
            "remediation": self.remediation,
            "context": self.context,
        }


class ContinuumError(Exception):
    """Base for every error Continuum raises deliberately."""

    code = "continuum.error"
    category = ErrorCategory.PERMANENT_INPUT

    def __init__(
        self,
        user_message: str,
        *,
        technical_detail: str = "",
        remediation: str | None = None,
        **context: Any,
    ) -> None:
        super().__init__(user_message)
        self.user_message = user_message
        self.technical_detail = technical_detail
        self.remediation = remediation
        self.context = context

    def structured(self) -> StructuredError:
        return StructuredError(
            code=self.code,
            category=self.category,
            user_message=self.user_message,
            technical_detail=self.technical_detail or repr(self),
            remediation=self.remediation,
            context=self.context,
        )


class PathEscapesRootError(ContinuumError):
    """A candidate path resolved outside its declared root (ADR-0001)."""

    code = "storage.path_escapes_root"
    category = ErrorCategory.PERMANENT_INPUT


class VaultWriteAttemptedError(ContinuumError):
    """Something tried to obtain a writable handle on the Source Vault.

    Reaching this is a bug, not a user error: the type system is supposed to
    make it unrepresentable (ADR-0001 Layer 1). It exists as a last backstop
    for dynamic root lookups.
    """

    code = "storage.vault_write_attempted"
    category = ErrorCategory.PERMANENT_CONFIG


class ProviderUnavailableError(ContinuumError):
    """No permitted provider satisfies a requested capability (ADR-0004)."""

    code = "provider.unavailable"
    category = ErrorCategory.PERMANENT_CONFIG


class PolicyViolationError(ContinuumError):
    """A call would breach the privacy or cost policy (ADR-0004 sections 2-3)."""

    code = "provider.policy_violation"
    category = ErrorCategory.PERMANENT_CONFIG


class IllegalTransitionError(ContinuumError):
    """A job state transition not permitted by the table (ADR-0002 section 4)."""

    code = "jobs.illegal_transition"
    category = ErrorCategory.PERMANENT_CONFIG
