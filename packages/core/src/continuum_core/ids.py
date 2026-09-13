"""UUIDv7 identifiers (D-07).

UUIDv7 is time-ordered, which gives index locality, and globally unique,
which is what makes export/import and cross-machine merges safe (ADR-0003
section 1). Implemented here rather than pulled from a dependency: the
layout is fixed by RFC 9562 and is about twenty lines, so a dependency
would cost more than it saves.

Layout (RFC 9562 section 5.7)::

    0                   1                   2                   3
     0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
    +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
    |                       unix_ts_ms (48 bits)                    |
    +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
    |  ver (4)  |      rand_a (12)      | var (2) |   rand_b (62)   |
    +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
"""

from __future__ import annotations

import os
import threading
import time
from uuid import UUID

__all__ = ["uuid7", "uuid7_timestamp_ms"]

_UNIX_TS_MS_BITS = 48
_RAND_A_BITS = 12
_RAND_A_MAX = (1 << _RAND_A_BITS) - 1
_RAND_B_MASK = (1 << 62) - 1
_VERSION = 0x7
_VARIANT_RFC4122 = 0b10

# RFC 9562 section 6.2 method 1: rand_a carries a monotonic counter so that
# identifiers minted inside the same millisecond still sort in creation
# order. Without it, index locality still holds but same-millisecond
# ordering is random, which makes "time-ordered" untestable and makes
# paging by id subtly non-deterministic.
_lock = threading.Lock()
_last_ts_ms = -1
_counter = 0


def uuid7(*, _now_ms: int | None = None) -> UUID:
    """Return a new time-ordered UUIDv7.

    Strictly increasing within a process, including inside a single
    millisecond. ``_now_ms`` exists only so tests can pin the timestamp;
    production callers never pass it.
    """
    global _last_ts_ms, _counter

    ts_ms = int(time.time() * 1000) if _now_ms is None else _now_ms
    if not 0 <= ts_ms < (1 << _UNIX_TS_MS_BITS):
        raise ValueError(f"timestamp out of UUIDv7 range: {ts_ms}")

    with _lock:
        if ts_ms > _last_ts_ms:
            _last_ts_ms = ts_ms
            # Seed below the midpoint so a burst has counter headroom
            # without risking rollover into the next millisecond.
            _counter = int.from_bytes(os.urandom(2), "big") & (_RAND_A_MAX >> 1)
        else:
            # Same millisecond, or a clock that went backwards: keep
            # increasing. On counter overflow, borrow the next millisecond
            # rather than emitting a duplicate or going backwards.
            ts_ms = _last_ts_ms
            _counter += 1
            if _counter > _RAND_A_MAX:
                _last_ts_ms += 1
                ts_ms = _last_ts_ms
                _counter = 0
        rand_a = _counter

    rand_b = int.from_bytes(os.urandom(8), "big") & _RAND_B_MASK

    value = ts_ms << 80
    value |= _VERSION << 76
    value |= rand_a << 64
    value |= _VARIANT_RFC4122 << 62
    value |= rand_b
    return UUID(int=value)


def uuid7_timestamp_ms(value: UUID) -> int:
    """Recover the embedded millisecond timestamp from a UUIDv7.

    Raises ``ValueError`` for any other UUID version, so callers cannot
    silently read garbage out of a v4.
    """
    if value.version != 7:
        raise ValueError(f"not a UUIDv7: version={value.version}")
    return value.int >> 80
