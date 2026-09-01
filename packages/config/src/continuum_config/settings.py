"""Typed settings and boot validation (ADR-0004, ADR-0006).

Lives in its own package rather than in ``apps/api`` (where architecture
review section Q sketched it) because the worker needs the same settings and
must not import from the API application -- that would couple the two
processes the topology deliberately separates (ADR-0002 section 12).

Root paths are typed ``str`` here, not ``Path``. ``continuum_storage`` is the
only module permitted to construct filesystem objects (ADR-0001 Layer 3), so
config carries the configured strings and storage resolves them.
"""

from __future__ import annotations

import os
from enum import StrEnum
from functools import lru_cache
from typing import Any, Literal

from continuum_observability import secret_registry
from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

__all__ = ["ROOT_KEYS", "WRITABLE_ROOT_KEYS", "ProductionProfile", "Settings", "get_settings"]

#: The eight roots of ADR-0001 / Master Plan section 108.
ROOT_KEYS: tuple[str, ...] = (
    "source_vault",
    "library",
    "projects",
    "generated",
    "jobs",
    "models",
    "cache",
    "config",
)

#: Everything except the Source Vault. The vault is absent from this tuple by
#: construction, which is what makes a writable-root lookup unable to return
#: it (ADR-0001 Layer 1).
WRITABLE_ROOT_KEYS: tuple[str, ...] = tuple(k for k in ROOT_KEYS if k != "source_vault")

_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})


class ProductionProfile(StrEnum):
    """Provider selection policy (Master Plan section 101.2)."""

    FREE_LOCAL = "FREE_LOCAL"
    BALANCED_LOCAL = "BALANCED_LOCAL"
    HYBRID_OPTIONAL = "HYBRID_OPTIONAL"
    SHOWCASE_OPTIONAL = "SHOWCASE_OPTIONAL"


class Settings(BaseSettings):
    """Continuum runtime configuration.

    Every field is read from the environment or ``.env`` with the
    ``CONTINUUM_`` prefix, e.g. ``CONTINUUM_API_HOST``.
    """

    model_config = SettingsConfigDict(
        env_prefix="CONTINUUM_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    # -- data roots (D-01: outside the repository) --------------------------
    data_home: str = Field(
        default="",
        description="Base directory for roots that are not individually configured.",
    )
    source_vault_root: str = ""
    library_root: str = ""
    projects_root: str = ""
    generated_root: str = ""
    jobs_root: str = ""
    models_root: str = ""
    cache_root: str = ""
    config_root: str = ""

    # -- database ----------------------------------------------------------
    database_url: SecretStr = Field(
        default=SecretStr(
            "postgresql+psycopg://continuum:continuum_local_dev@127.0.0.1:5433/continuum"
        ),
        description="SQLAlchemy URL for the sole durable job store (D-02).",
    )
    db_pool_size: int = Field(default=5, ge=1, le=50)

    # -- API (A-03: loopback only in Phase 0) ------------------------------
    api_host: str = "127.0.0.1"
    api_port: int = Field(default=8000, ge=1, le=65535)
    web_origin: str = "http://127.0.0.1:3000"

    # -- worker ------------------------------------------------------------
    worker_resource_classes: str = "cpu"
    worker_poll_seconds: float = Field(default=0.5, gt=0, le=60)
    worker_lease_seconds: int = Field(default=30, ge=5, le=3600)
    worker_heartbeat_seconds: float = Field(default=5.0, gt=0, le=600)
    max_concurrency_cpu: int = Field(default=4, ge=1, le=64)
    max_concurrency_gpu: int = Field(default=1, ge=1, le=8)

    # -- providers ---------------------------------------------------------
    production_profile: ProductionProfile = ProductionProfile.FREE_LOCAL

    # -- observability -----------------------------------------------------
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    @field_validator("api_host")
    @classmethod
    def _must_be_loopback(cls, value: str) -> str:
        """Reject any non-loopback bind (A-03, F-50, acceptance checklist).

        Phase 0 has no authentication. There is deliberately no "bind to LAN
        if auth is configured" escape route, because auth does not exist yet
        and a dormant path would be the thing someone enables later without
        the security decision that should accompany it.
        """
        if value not in _LOOPBACK_HOSTS:
            raise ValueError(
                f"CONTINUUM_API_HOST must be loopback in Phase 0, got {value!r}. "
                "Phase 0 has no authentication; non-loopback binding requires a "
                "future security ADR and an authentication implementation first "
                "(FOUNDATION_APPROVAL A-03)."
            )
        return value

    @model_validator(mode="after")
    def _register_secrets(self) -> Settings:
        """Feed concrete secret values to the redaction registry (F-53)."""
        secret_registry.register(self.database_url.get_secret_value())
        try:
            from urllib.parse import urlsplit

            password = urlsplit(self.database_url.get_secret_value()).password
        except ValueError:  # pragma: no cover - malformed URL still redacts whole value
            password = None
        secret_registry.register(password)
        return self

    def root(self, key: str) -> str:
        """Return the configured path string for a root key.

        Falls back to ``<data_home>/<key>`` when the root was not configured
        individually. Raises for an unknown key so a typo cannot silently
        produce a new root.
        """
        if key not in ROOT_KEYS:
            raise KeyError(f"unknown storage root {key!r}; known roots: {', '.join(ROOT_KEYS)}")
        configured = getattr(self, f"{key}_root", "")
        if configured:
            return str(configured)
        if not self.data_home:
            raise ValueError(
                f"storage root {key!r} is not configured and CONTINUUM_DATA_HOME is unset. "
                f"Set CONTINUUM_{key.upper()}_ROOT or CONTINUUM_DATA_HOME (see .env.example)."
            )
        # On-disk directory names follow Master Plan section 108 (hyphenated),
        # while the key stays a valid Python identifier.
        return os.path.join(self.data_home, key.replace("_", "-"))  # noqa: PTH118 - str join only

    def all_roots(self) -> dict[str, str]:
        """Every root key mapped to its configured path string."""
        return {key: self.root(key) for key in ROOT_KEYS}

    def safe_dump(self) -> dict[str, Any]:
        """Configuration for /health and logs, with secrets already masked."""
        data = self.model_dump(mode="json")
        data["database_url"] = "**********"
        return data


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Process-wide settings singleton."""
    return Settings()
