"""The four time axes (F-68 / ADR-0003 section 5).

The Master Plan conflates several notions of time across sections 11, 69 and
97. Separating them costs nothing now and is a full-schema migration later,
so the distinction is encoded in the type system from the first commit.

    source_time      in-universe time within source canon
    project_time     in-universe time within a project branch
    narrative_order  position in the telling (chapter/episode/scene sequence)
    record_time      real-world time the system learned or recorded something

Phase 0 only ever uses ``record_time`` -- jobs, leases, audit events. The
other three axes have no consumers until Phase 3+. They are defined here
anyway so that the first temporal domain column added in a later phase has
to name its axis explicitly rather than defaulting to an untyped timestamp.

In-universe time must also tolerate imprecision: "some weeks later" and
"before the war" are normal source statements, and a bare timestamp forces
implementers to invent fake precision. ``FuzzyInstant`` is the shape that
avoids that. Nothing in Phase 0 constructs one.
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass
from enum import StrEnum

__all__ = [
    "FuzzyInstant",
    "TimeAxis",
    "TimePrecision",
    "utc_now",
]


class TimeAxis(StrEnum):
    """Which clock a temporal value is measured against.

    Every temporal domain field must declare exactly one. Two axes must
    never share a column.
    """

    SOURCE_TIME = "source_time"
    PROJECT_TIME = "project_time"
    NARRATIVE_ORDER = "narrative_order"
    RECORD_TIME = "record_time"


class TimePrecision(StrEnum):
    """How precisely an in-universe instant is known."""

    EXACT = "exact"
    DAY = "day"
    WEEK = "week"
    MONTH = "month"
    YEAR = "year"
    ERA = "era"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class FuzzyInstant:
    """An in-universe instant that may be imprecise.

    ``label`` preserves the source's own wording ("some weeks after the
    festival") so the uncertainty stays inspectable instead of being
    flattened into an invented date.
    """

    axis: TimeAxis
    earliest: int | None
    latest: int | None
    precision: TimePrecision
    label: str | None = None

    def __post_init__(self) -> None:
        if self.axis is TimeAxis.RECORD_TIME:
            raise ValueError("record_time is a real clock; use utc_now() instead")
        if self.earliest is not None and self.latest is not None and self.earliest > self.latest:
            raise ValueError(f"earliest {self.earliest} is after latest {self.latest}")


def utc_now() -> _dt.datetime:
    """Timezone-aware UTC now, for ``record_time`` only.

    Lease expiry and job scheduling deliberately do *not* use this: they
    use the database clock (D-09, ADR-0002 section 5) so that clock skew
    between machines cannot expire a live lease.
    """
    return _dt.datetime.now(_dt.UTC)
