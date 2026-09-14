"""Content-derived source locators and normalized regions (ADR-0005 section 1).

A locator names *bytes*, never a path and never a database row::

    <medium>:sha256:<asset_content_hash>[#<unit-address>]

    zip:sha256:ab12...#entry=Vol%2001/Ch0003/012.webp
    image:sha256:cd34...
    pdf:sha256:ef56...#page=88
    video:sha256:0a1b...#t=00:12:03.400
    gen:sha256:9c8d...

Re-scanning, restoring or moving the library never repoints a locator,
because nothing in it depends on where the file lives. Archive units are
addressed by **entry path**, not by page index: the index is a display order
that can change with sorting rules, while the entry name belongs to the bytes.

A crop is not a new locator. It is a :class:`NormalizedRegion` carried beside
the locator of the page it was cut from, so the reference can always be
followed back to the original page.

Pure functions only: this module performs no I/O.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from enum import StrEnum
from urllib.parse import quote, unquote

from continuum_core.errors import ContinuumError, ErrorCategory
from continuum_core.hashing import is_sha256_hex

__all__ = [
    "InvalidLocatorError",
    "LocatorMedium",
    "NormalizedRegion",
    "SourceLocator",
    "parse_locator",
]

#: Characters left unescaped in an archive entry. Everything else - including
#: ``#``, ``&``, ``%``, spaces and non-ASCII - is percent-encoded, so a
#: locator is unambiguous and survives being passed through a URL.
_ENTRY_SAFE = "/-._~!$'()*+,;=:@"
_MAX_ENTRY = 1024
_TIME = re.compile(r"^(\d{2,}):([0-5]\d):([0-5]\d)\.(\d{3})$")
#: Smallest crop edge, as a fraction of the page. Smaller selections are
#: almost always accidental clicks, and cannot serve as a visual reference.
MIN_REGION_EDGE = 0.01


class InvalidLocatorError(ContinuumError):
    """A locator or region is malformed or names something unsafe."""

    code = "locator.invalid"
    category = ErrorCategory.PERMANENT_INPUT


class LocatorMedium(StrEnum):
    """The unit grammar a locator uses."""

    IMAGE = "image"
    """A standalone image; addresses the whole file."""
    ZIP = "zip"
    """An image archive (ZIP/CBZ); addresses one entry."""
    PDF = "pdf"
    """A PDF; addresses one page (1-based)."""
    VIDEO = "video"
    """A video; addresses one instant."""
    GEN = "gen"
    """Bytes Continuum generated, stored content-addressed."""


def _invalid(message: str, detail: str) -> InvalidLocatorError:
    return InvalidLocatorError(message, technical_detail=detail)


def _check_entry(entry: str) -> str:
    if not entry or len(entry) > _MAX_ENTRY:
        raise _invalid("An archive entry name is empty or too long.", f"length={len(entry)}")
    if any(ord(c) < 32 or ord(c) == 127 for c in entry):
        raise _invalid("An archive entry name contains control characters.", repr(entry))
    if "\\" in entry or entry.startswith("/") or re.match(r"^[A-Za-z]:", entry):
        raise _invalid("An archive entry must be a relative, forward-slash name.", repr(entry))
    if any(part in ("", ".", "..") for part in entry.split("/")):
        raise _invalid("An archive entry name contains an empty, '.' or '..' segment.", repr(entry))
    return entry


@dataclass(frozen=True, slots=True)
class SourceLocator:
    """A parsed locator. Construct through :meth:`asset` or :func:`parse_locator`."""

    medium: LocatorMedium
    sha256: str
    entry: str | None = None
    page: int | None = None
    time_ms: int | None = None

    def __post_init__(self) -> None:
        if not is_sha256_hex(self.sha256):
            raise _invalid("A locator needs a lowercase SHA-256 content hash.", self.sha256)
        unit = {
            LocatorMedium.ZIP: ("entry", self.entry),
            LocatorMedium.PDF: ("page", self.page),
            LocatorMedium.VIDEO: ("t", self.time_ms),
        }
        expected = unit.get(self.medium)
        given = [
            name
            for name, value in (("entry", self.entry), ("page", self.page), ("t", self.time_ms))
            if value is not None
        ]
        if expected is None and given:
            raise _invalid(f"A {self.medium} locator addresses the whole file.", str(given))
        if expected is not None and given != [expected[0]]:
            raise _invalid(
                f"A {self.medium} locator needs exactly one '{expected[0]}' unit.", str(given)
            )
        if self.entry is not None:
            _check_entry(self.entry)
        if self.page is not None and self.page < 1:
            raise _invalid("PDF pages are numbered from 1.", str(self.page))
        if self.time_ms is not None and self.time_ms < 0:
            raise _invalid("A video instant cannot be negative.", str(self.time_ms))

    # -- construction ---------------------------------------------------------
    @classmethod
    def asset(cls, medium: LocatorMedium, sha256: str) -> SourceLocator:
        """The whole-file locator for media with no unit (image, gen)."""
        return cls(medium=medium, sha256=sha256)

    @classmethod
    def archive_entry(cls, sha256: str, entry: str) -> SourceLocator:
        return cls(medium=LocatorMedium.ZIP, sha256=sha256, entry=entry)

    @classmethod
    def pdf_page(cls, sha256: str, page: int) -> SourceLocator:
        return cls(medium=LocatorMedium.PDF, sha256=sha256, page=page)

    # -- rendering ------------------------------------------------------------
    def render(self) -> str:
        head = f"{self.medium.value}:sha256:{self.sha256}"
        if self.entry is not None:
            return f"{head}#entry={quote(self.entry, safe=_ENTRY_SAFE)}"
        if self.page is not None:
            return f"{head}#page={self.page}"
        if self.time_ms is not None:
            total_seconds, millis = divmod(self.time_ms, 1000)
            minutes, seconds = divmod(total_seconds, 60)
            hours, minutes = divmod(minutes, 60)
            return f"{head}#t={hours:02d}:{minutes:02d}:{seconds:02d}.{millis:03d}"
        return head

    def __str__(self) -> str:
        return self.render()


def parse_locator(text: str) -> SourceLocator:
    """Parse and validate a rendered locator. ``parse_locator(x.render()) == x``."""
    if not isinstance(text, str) or len(text) > 2048:
        raise _invalid("A locator must be a string of reasonable length.", type(text).__name__)
    head, _, fragment = text.partition("#")
    parts = head.split(":")
    if len(parts) != 3 or parts[1] != "sha256":
        raise _invalid("A locator looks like '<medium>:sha256:<hash>[#unit]'.", text)
    try:
        medium = LocatorMedium(parts[0])
    except ValueError:
        raise _invalid("Unknown locator medium.", parts[0]) from None
    sha256 = parts[2]
    if "#" in text and not fragment:
        raise _invalid("A locator has an empty unit address.", text)
    if not fragment:
        return SourceLocator(medium=medium, sha256=sha256)
    key, sep, value = fragment.partition("=")
    if not sep or not value:
        raise _invalid("A locator unit looks like 'key=value'.", fragment)
    if key == "entry":
        if "%" in value:
            # Only well-formed escapes; a raw '%' would decode ambiguously.
            if re.search(r"%(?![0-9A-Fa-f]{2})", value):
                raise _invalid("An archive entry has a malformed escape.", value)
        entry = unquote(value, errors="strict")
        if quote(entry, safe=_ENTRY_SAFE) != value:
            raise _invalid("An archive entry is not in canonical form.", value)
        return SourceLocator(medium=medium, sha256=sha256, entry=entry)
    if key == "page":
        if not value.isdigit() or value.startswith("0"):
            raise _invalid("A PDF page is a positive integer.", value)
        return SourceLocator(medium=medium, sha256=sha256, page=int(value))
    if key == "t":
        match = _TIME.match(value)
        if not match:
            raise _invalid("A video instant looks like 'hh:mm:ss.mmm'.", value)
        hours, minutes, seconds, millis = (int(g) for g in match.groups())
        return SourceLocator(
            medium=medium,
            sha256=sha256,
            time_ms=((hours * 60 + minutes) * 60 + seconds) * 1000 + millis,
        )
    raise _invalid("Unknown locator unit.", key)


@dataclass(frozen=True, slots=True)
class NormalizedRegion:
    """A rectangle as fractions of the unit it was selected on (0..1).

    Resolution-independent, so the same region is valid for a thumbnail, the
    full page, or a re-encoded copy of identical content.
    """

    x: float
    y: float
    width: float
    height: float

    def __post_init__(self) -> None:
        values = (self.x, self.y, self.width, self.height)
        if not all(isinstance(v, int | float) and math.isfinite(v) for v in values):
            raise _invalid("A region needs four finite numbers.", repr(values))
        if self.x < 0 or self.y < 0:
            raise _invalid("A region cannot start outside the page.", repr(values))
        if self.width < MIN_REGION_EDGE or self.height < MIN_REGION_EDGE:
            raise _invalid("A region is too small to be a reference.", repr(values))
        # A tiny tolerance absorbs floating-point rounding from a browser.
        if self.x + self.width > 1.000001 or self.y + self.height > 1.000001:
            raise _invalid("A region cannot extend past the page.", repr(values))

    def to_pixels(self, width: int, height: int) -> tuple[int, int, int, int]:
        """``(left, top, right, bottom)`` in pixels, clamped to the image."""
        left = max(0, min(width - 1, round(self.x * width)))
        top = max(0, min(height - 1, round(self.y * height)))
        right = max(left + 1, min(width, round((self.x + self.width) * width)))
        bottom = max(top + 1, min(height, round((self.y + self.height) * height)))
        return left, top, right, bottom

    def as_dict(self) -> dict[str, float]:
        return {"x": self.x, "y": self.y, "width": self.width, "height": self.height}
