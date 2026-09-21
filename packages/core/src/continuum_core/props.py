"""Recurring objects and their size (M3).

A brooch that is four centimetres across in one panel and the size of a hand in
the next is not a style choice, it is a continuity failure, and no amount of
reference imagery fixes it on its own: the renderer needs the *measurement*.

A **prop** is any object a project wants to stay the same: worn, carried, or
standing in a room. It records what the object is, roughly how big it is, what
its size is relative to (a head, a hand, a doorway), which references show it,
and - only when the object earns it - what it means in the story.

Nothing here names an object, a character or a project. A prop is a row.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

__all__ = [
    "PROP_VIEWS",
    "PropStatus",
    "PropView",
    "ScaleAnchor",
    "describe_scale",
    "describe_size",
]


class PropStatus(StrEnum):
    DRAFT = "DRAFT"
    """Recorded, not yet a lock: production may see it, nothing is enforced."""
    APPROVED = "APPROVED"
    """A person accepted these measurements. Renders are held to them."""
    RETIRED = "RETIRED"
    """No longer in production. Kept for the pages that used it."""


class PropView(StrEnum):
    """What a prop reference shows."""

    FRONT = "FRONT"
    PROFILE = "PROFILE"
    DETAIL = "DETAIL"
    IN_CONTEXT = "IN_CONTEXT"
    """Worn or held, so the size reads against the person."""
    SCALE = "SCALE"
    """Beside something of known size."""


PROP_VIEWS: tuple[PropView, ...] = tuple(PropView)


class ScaleAnchor(StrEnum):
    """What a prop's size is expressed relative to.

    Absolute millimetres are the truth; an anchor is what a renderer can
    actually act on, because a drawing has no centimetres in it.
    """

    HEAD_HEIGHT = "HEAD_HEIGHT"
    HEAD_WIDTH = "HEAD_WIDTH"
    HAND_LENGTH = "HAND_LENGTH"
    FOREARM = "FOREARM"
    SHOULDER_WIDTH = "SHOULDER_WIDTH"
    BODY_HEIGHT = "BODY_HEIGHT"
    DOORWAY = "DOORWAY"
    NONE = "NONE"


@dataclass(frozen=True, slots=True)
class PropSize:
    """Roughly how big an object is, in millimetres."""

    length_mm: float | None = None
    width_mm: float | None = None
    height_mm: float | None = None
    diameter_mm: float | None = None
    approximate: bool = True

    def as_dict(self) -> dict[str, object]:
        return {
            "length_mm": self.length_mm,
            "width_mm": self.width_mm,
            "height_mm": self.height_mm,
            "diameter_mm": self.diameter_mm,
            "approximate": self.approximate,
        }

    @property
    def known(self) -> bool:
        return any(
            value is not None
            for value in (self.length_mm, self.width_mm, self.height_mm, self.diameter_mm)
        )


def _mm(value: float) -> str:
    if value >= 1000:
        return f"{value / 1000:g} m"
    if value >= 10:
        return f"{value / 10:g} cm"
    return f"{value:g} mm"


def describe_size(size: dict[str, object] | None) -> str:
    """A prop's measurements as one short phrase a renderer can be told."""
    if not size:
        return ""
    parts = [
        f"{label} {_mm(float(size[key]))}"  # type: ignore[arg-type]
        for key, label in (
            ("diameter_mm", "across"),
            ("length_mm", "long"),
            ("width_mm", "wide"),
            ("height_mm", "tall"),
        )
        if size.get(key) is not None
    ]
    if not parts:
        return ""
    about = "about " if size.get("approximate", True) else ""
    return about + ", ".join(parts)


def describe_scale(scale: dict[str, object] | None) -> str:
    """A prop's size relative to the body, as a phrase, or "" when unset."""
    if not scale:
        return ""
    anchor = str(scale.get("relative_to") or ScaleAnchor.NONE.value)
    if anchor == ScaleAnchor.NONE.value:
        return ""
    try:
        ratio = float(scale["ratio"])  # type: ignore[arg-type]
    except (KeyError, TypeError, ValueError):
        return ""
    return f"{ratio:g}x the wearer's {anchor.lower().replace('_', ' ')}"
