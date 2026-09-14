"""Errors and input rules shared by the catalog, the inbox and uploads."""

from __future__ import annotations

import re
import unicodedata
from urllib.parse import urlsplit

from continuum_core import ContinuumError, ErrorCategory

__all__ = [
    "CatalogConflictError",
    "CatalogInputError",
    "CatalogNotFoundError",
    "clean_display_name",
    "clean_handle",
    "clean_tags",
    "clean_text",
    "clean_url",
    "require_episode",
    "require_project_key",
]

_PROJECT_KEY = re.compile(r"^[a-z0-9][a-z0-9-]{0,79}$")
_EPISODE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,39}$")
MAX_TAGS = 30
MAX_TAG = 60


class CatalogInputError(ContinuumError):
    code = "catalog.invalid"
    category = ErrorCategory.PERMANENT_INPUT


class CatalogNotFoundError(ContinuumError):
    code = "catalog.not_found"
    category = ErrorCategory.PERMANENT_INPUT


class CatalogConflictError(ContinuumError):
    """Someone changed the record since it was loaded (optimistic concurrency)."""

    code = "catalog.conflict"
    category = ErrorCategory.RETRYABLE_TRANSIENT


def clean_text(value: str | None, limit: int, *, field: str) -> str:
    text = (value or "").strip()
    if any(unicodedata.category(c) == "Cc" and c not in "\n\t" for c in text):
        raise CatalogInputError(f"{field} contains control characters.")
    if len(text) > limit:
        raise CatalogInputError(f"{field} is longer than {limit} characters.")
    return text


def clean_url(value: str | None) -> str | None:
    """An http(s) URL to remember. It is stored, shown and never fetched."""
    if value is None or not value.strip():
        return None
    url = value.strip()
    if len(url) > 2048 or any(c.isspace() for c in url):
        raise CatalogInputError("A link must be a single URL without spaces.")
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise CatalogInputError("Only http and https links can be stored.", technical_detail=url)
    if parts.username or parts.password:
        raise CatalogInputError("Links with embedded credentials are not stored.")
    return url


def clean_handle(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    return clean_text(value, 200, field="Creator handle")


def clean_tags(values: list[str] | tuple[str, ...] | None) -> list[str]:
    tags: list[str] = []
    for raw in values or ():
        tag = clean_text(raw, MAX_TAG, field="Tag")
        if tag and tag.lower() not in {t.lower() for t in tags}:
            tags.append(tag)
    if len(tags) > MAX_TAGS:
        raise CatalogInputError(f"At most {MAX_TAGS} tags.")
    return tags


def clean_display_name(value: str | None) -> str:
    """A name to show, reduced to its last segment; never used to find bytes."""
    name = (value or "").replace("\\", "/").rsplit("/", 1)[-1]
    name = "".join(c for c in name if unicodedata.category(c) != "Cc").strip()
    return name[:300]


def require_project_key(value: str) -> str:
    if not isinstance(value, str) or not _PROJECT_KEY.match(value):
        raise CatalogInputError("A project is named by its manifest id.", technical_detail=value)
    return value


def require_episode(value: str) -> str:
    if not isinstance(value, str) or not _EPISODE.match(value):
        raise CatalogInputError(
            "An episode is a short code such as 'S1E1'.", technical_detail=value
        )
    return value
