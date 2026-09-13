"""Continuum domain primitives.

This package is the bottom of the dependency graph: it performs no I/O, opens
no files, touches no database, and imports no framework. Everything above it
may depend on it; it depends on nothing internal.
"""

from continuum_core.errors import (
    ContinuumError,
    ErrorCategory,
    IllegalTransitionError,
    PathEscapesRootError,
    PolicyViolationError,
    ProviderUnavailableError,
    StructuredError,
    VaultWriteAttemptedError,
)
from continuum_core.hashing import (
    CHUNK_BYTES,
    canonical_json,
    canonical_json_hash,
    content_hash_bytes,
    content_hash_stream,
    fanout_segments,
    is_sha256_hex,
)
from continuum_core.ids import uuid7, uuid7_timestamp_ms
from continuum_core.jobstates import (
    TERMINAL_STATUSES,
    BlockedReason,
    JobEventType,
    JobStatus,
    StepStatus,
)
from continuum_core.locators import (
    InvalidLocatorError,
    LocatorMedium,
    NormalizedRegion,
    SourceLocator,
    parse_locator,
)
from continuum_core.timeaxes import FuzzyInstant, TimeAxis, TimePrecision, utc_now

__all__ = [
    "CHUNK_BYTES",
    "TERMINAL_STATUSES",
    "BlockedReason",
    "ContinuumError",
    "ErrorCategory",
    "FuzzyInstant",
    "IllegalTransitionError",
    "InvalidLocatorError",
    "JobEventType",
    "JobStatus",
    "LocatorMedium",
    "NormalizedRegion",
    "PathEscapesRootError",
    "PolicyViolationError",
    "ProviderUnavailableError",
    "SourceLocator",
    "StepStatus",
    "StructuredError",
    "TimeAxis",
    "TimePrecision",
    "VaultWriteAttemptedError",
    "canonical_json",
    "canonical_json_hash",
    "content_hash_bytes",
    "content_hash_stream",
    "fanout_segments",
    "is_sha256_hex",
    "parse_locator",
    "utc_now",
    "uuid7",
    "uuid7_timestamp_ms",
]
