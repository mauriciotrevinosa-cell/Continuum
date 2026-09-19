"""The external-resource registry: datasets, annotations, models and tools (M3).

The committed registry document (``continuum.external-dataset-registry/0.1``)
*proposes*: what a resource is, where it is published, what its license says
and what it might be good for. A person *decides*: whether access was requested
or granted, whether its license was accepted locally, what material from it may
be used for, and which read-only intake folder holds its bytes.

Import rules, all conservative:

* an import never grants a training use; research-only and non-commercial
  resources get no training use proposed at all;
* re-importing a changed entry updates what the registry says, and can narrow
  what is allowed (the registry withdrew a use), never widen it;
* a person's decisions (access, acceptance, allowed uses, intake binding,
  notes) are never touched by an import.

Nothing here downloads anything or stores a local path.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass
from typing import Any

from continuum_core import canonical_json_hash
from continuum_core.knowledge import TRAINING_USES, AccessState, KnowledgeUse, ResourceKind
from continuum_db.models import CatalogEntry, ExternalResource, ReferenceItem
from sqlalchemy import String, cast, func, select
from sqlalchemy.orm import Session

from continuum_library.validation import (
    CatalogConflictError,
    CatalogInputError,
    CatalogNotFoundError,
    clean_text,
)

__all__ = [
    "REGISTRY_SCHEMA",
    "ExternalResources",
    "ImportSummary",
    "proposed_uses",
    "resource_kind",
    "resource_view",
]

REGISTRY_SCHEMA = "continuum.external-dataset-registry/0.1"
_KEY = re.compile(r"^[a-z0-9][a-z0-9._-]{1,79}$")
_INTAKE_KEY = re.compile(r"^intake:[a-z0-9-]{1,57}$")
_MAX_ENTRIES = 500
#: A drive-letter path (never a URL scheme: no letter before the drive), a UNC
#: share, or a POSIX home/mount directory.
_LOCAL_PATH = re.compile(r"(?<![A-Za-z])[A-Za-z]:[\\/]|\\\\|(?:^|\s)/(?:home|Users|mnt)/")
#: Registry training defaults that mean "never propose training".
_NO_TRAINING = (
    "blocked",
    "research_only",
    "not_approved",
    "not_training",
    "not_dataset",
    "synthetic_test_only",
)
#: License language that confines a resource to research.
_RESEARCH_ONLY = re.compile(
    r"research (?:purposes )?only|academic research only|non-commercial|noncommercial"
    r"|commercial use prohibited",
    re.I,
)


@dataclass(frozen=True, slots=True)
class ImportSummary:
    created: tuple[str, ...]
    updated: tuple[str, ...]
    unchanged: tuple[str, ...]
    narrowed: tuple[str, ...]

    def as_dict(self) -> dict[str, list[str]]:
        return {
            "created": list(self.created),
            "updated": list(self.updated),
            "unchanged": list(self.unchanged),
            "narrowed": list(self.narrowed),
        }


def resource_kind(raw: str) -> ResourceKind:
    """Normalize a registry ``kind`` (free text) to a resource kind."""
    kind = raw.lower()
    if "unverified" in kind:
        return ResourceKind.UNVERIFIED
    if "research" in kind:
        return ResourceKind.RESEARCH
    if "annotation" in kind:
        return ResourceKind.ANNOTATIONS
    if "dataset" in kind:
        return ResourceKind.DATASET
    if "model" in kind or "analyzer" in kind:
        return ResourceKind.MODEL
    if "tool" in kind:
        return ResourceKind.TOOL
    return ResourceKind.UNVERIFIED


def _access(raw: str) -> AccessState:
    access = raw.lower()
    if access.startswith("public"):
        return AccessState.OPEN
    if access in {"gated", "authorization_form", "registration", "research_project"}:
        return AccessState.NOT_REQUESTED
    return AccessState.UNKNOWN


def proposed_uses(entry: dict[str, Any]) -> list[str]:
    """What the registry entry proposes, never more than it says, never training-approved."""
    kind = resource_kind(str(entry.get("kind") or ""))
    if kind is ResourceKind.UNVERIFIED:
        return []
    scope = {str(s).lower() for s in entry.get("scope") or []}
    training_default = str(entry.get("training_default") or "").lower()
    status = str(entry.get("status") or "").lower()
    research_only = bool(
        _RESEARCH_ONLY.search(str(entry.get("license_summary") or ""))
        or "research_only" in training_default
        or "research_only" in status
        or status == "do_not_adopt"
    )
    uses = [KnowledgeUse.REFERENCE_ONLY]
    if not research_only:
        if "retrieval" in scope:
            uses.append(KnowledgeUse.RETRIEVAL)
        if scope & {"validator", "validators"}:
            uses.append(KnowledgeUse.VALIDATOR)
        if "training_candidate" in scope and not any(
            token in training_default for token in _NO_TRAINING
        ):
            uses.append(KnowledgeUse.TRAINING_CANDIDATE)
    return [use.value for use in uses]


def _clean_entry(entry: Any) -> dict[str, Any]:
    if not isinstance(entry, dict):
        raise CatalogInputError("Every registry entry is an object.")
    key = str(entry.get("id") or "")
    if not _KEY.match(key):
        raise CatalogInputError(f"Registry id {key[:60]!r} is not a valid key.")
    urls = entry.get("urls") or []
    if not isinstance(urls, list) or not all(
        isinstance(u, str) and re.match(r"^https?://", u) for u in urls
    ):
        raise CatalogInputError(f"{key}: urls must be a list of web addresses.")
    if any(_LOCAL_PATH.search(text) for text in _strings(entry)):
        raise CatalogInputError(f"{key}: a registry entry never holds a local path.")
    return entry


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [text for item in value.values() for text in _strings(item)]
    if isinstance(value, list):
        return [text for item in value for text in _strings(item)]
    return []


class ExternalResources:
    """Read, import and decide on external resources."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def all(self) -> list[ExternalResource]:
        return list(
            self.session.execute(select(ExternalResource).order_by(ExternalResource.key)).scalars()
        )

    def get(self, key: str) -> ExternalResource:
        found = self.session.execute(
            select(ExternalResource).where(ExternalResource.key == key)
        ).scalar_one_or_none()
        if found is None:
            raise CatalogNotFoundError(f"No external resource {key!r}.")
        return found

    def item_counts(self) -> dict[str, int]:
        """References imported from each intake root, by the catalog entry they came from."""
        rows = self.session.execute(
            select(CatalogEntry.root_key, func.count(func.distinct(ReferenceItem.id)))
            .join(
                ReferenceItem,
                ReferenceItem.provenance["catalog_entry_id"].astext
                == cast(CatalogEntry.id, String),
            )
            .where(ReferenceItem.removed_at.is_(None), CatalogEntry.root_key.like("intake:%"))
            .group_by(CatalogEntry.root_key)
        ).all()
        return {root: int(count) for root, count in rows}

    # -- import ---------------------------------------------------------------
    def import_registry(self, document: dict[str, Any]) -> ImportSummary:
        if not isinstance(document, dict) or document.get("schema") != REGISTRY_SCHEMA:
            raise CatalogInputError(f"A registry document declares schema {REGISTRY_SCHEMA}.")
        entries = document.get("entries")
        if not isinstance(entries, list) or not entries or len(entries) > _MAX_ENTRIES:
            raise CatalogInputError(f"A registry holds 1-{_MAX_ENTRIES} entries.")
        cleaned = [_clean_entry(entry) for entry in entries]
        keys = [str(entry["id"]) for entry in cleaned]
        if len(set(keys)) != len(keys):
            raise CatalogInputError("A registry id appears twice.")
        created: list[str] = []
        updated: list[str] = []
        unchanged: list[str] = []
        narrowed: list[str] = []
        for entry in cleaned:
            key = str(entry["id"])
            digest = canonical_json_hash(entry)
            proposed = proposed_uses(entry)
            row = self.session.execute(
                select(ExternalResource).where(ExternalResource.key == key)
            ).scalar_one_or_none()
            if row is None:
                self.session.add(
                    ExternalResource(
                        key=key,
                        kind=resource_kind(str(entry.get("kind") or "")).value,
                        title=clean_text(str(entry.get("title") or key), 200, field="Title"),
                        urls=list(entry.get("urls") or []),
                        license_summary=str(entry.get("license_summary") or ""),
                        access_state=_access(str(entry.get("access") or "")).value,
                        license_acceptance_note="",
                        proposed_uses=proposed,
                        # A new resource starts with nothing but looking allowed; a
                        # person widens it deliberately.
                        allowed_uses=[KnowledgeUse.REFERENCE_ONLY.value],
                        registry_entry=entry,
                        registry_hash=digest,
                        notes="",
                    )
                )
                created.append(key)
                continue
            if row.registry_hash == digest:
                unchanged.append(key)
                continue
            # Only what the registry *withdrew* is narrowed; a use a person allowed
            # beyond the old proposal stays their decision.
            withdrawn = set(row.proposed_uses) - set(proposed)
            if KnowledgeUse.TRAINING_CANDIDATE.value in withdrawn:
                withdrawn.add(KnowledgeUse.TRAINING_APPROVED.value)
            withdrawn.discard(KnowledgeUse.REFERENCE_ONLY.value)
            row.kind = resource_kind(str(entry.get("kind") or "")).value
            row.urls = list(entry.get("urls") or [])
            row.license_summary = str(entry.get("license_summary") or "")
            row.proposed_uses = proposed
            row.registry_entry = entry
            row.registry_hash = digest
            kept = [use for use in row.allowed_uses if use not in withdrawn]
            if kept != list(row.allowed_uses):
                row.allowed_uses = kept
                narrowed.append(key)
            updated.append(key)
        self.session.flush()
        return ImportSummary(tuple(created), tuple(updated), tuple(unchanged), tuple(narrowed))

    # -- decisions ------------------------------------------------------------
    def decide(
        self,
        key: str,
        row_version: int,
        *,
        access_state: AccessState | None = None,
        accept_license: bool | None = None,
        acceptance_note: str | None = None,
        allowed_uses: list[KnowledgeUse] | None = None,
        intake_root_key: str | None = None,
        clear_intake_root: bool = False,
        notes: str | None = None,
        known_intake_roots: frozenset[str] = frozenset(),
    ) -> ExternalResource:
        """Record a person's decision. Every rule the database also enforces is
        checked here first, so the refusal says why in words."""
        row = self.get(key)
        if row.row_version != row_version:
            raise CatalogConflictError(
                "This resource changed since you loaded it.",
                remediation="Reload and apply your change again.",
            )
        if access_state is not None:
            row.access_state = access_state.value
        if accept_license is True:
            note = clean_text(acceptance_note or "", 2000, field="Acceptance note")
            if not note:
                raise CatalogInputError(
                    "Say which terms were accepted (version, date, where) when accepting a license."
                )
            row.license_accepted_at = dt.datetime.now(dt.UTC)
            row.license_acceptance_note = note
        elif accept_license is False:
            row.license_accepted_at = None
            row.license_acceptance_note = ""
        if intake_root_key is not None:
            if not _INTAKE_KEY.match(intake_root_key):
                raise CatalogInputError("An intake binding is an intake root key (intake:...).")
            if intake_root_key not in known_intake_roots:
                raise CatalogInputError(
                    f"{intake_root_key} is not a configured read-only intake root.",
                    remediation="Add the folder to CONTINUUM_INTAKE_ROOTS first.",
                )
            row.intake_root_key = intake_root_key
        elif clear_intake_root:
            row.intake_root_key = None
        if notes is not None:
            row.notes = clean_text(notes, 8000, field="Notes")
        if allowed_uses is not None:
            uses = list(dict.fromkeys(allowed_uses))
            if KnowledgeUse.REFERENCE_ONLY not in uses and uses:
                uses.insert(0, KnowledgeUse.REFERENCE_ONLY)
            if KnowledgeUse.TRAINING_APPROVED in uses:
                if row.license_accepted_at is None:
                    raise CatalogInputError(
                        "Training needs the resource's license accepted and recorded first."
                    )
                if row.access_state not in (AccessState.OPEN.value, AccessState.GRANTED.value):
                    raise CatalogInputError("Training needs access granted (or an open resource).")
            if any(use in TRAINING_USES for use in uses) and row.kind in (
                ResourceKind.UNVERIFIED.value,
                ResourceKind.RESEARCH.value,
            ):
                raise CatalogInputError(
                    "An unverified or research-only resource is never training material."
                )
            row.allowed_uses = [use.value for use in uses]
        if (
            KnowledgeUse.TRAINING_APPROVED.value in row.allowed_uses
            and row.license_accepted_at is None
        ):
            # Withdrawing the acceptance withdraws the training approval with it.
            row.allowed_uses = [
                use for use in row.allowed_uses if use != KnowledgeUse.TRAINING_APPROVED.value
            ]
        self.session.flush()
        return row


def resource_view(row: ExternalResource, items: int = 0) -> dict[str, Any]:
    entry = row.registry_entry or {}
    return {
        "key": row.key,
        "kind": row.kind,
        "title": row.title,
        "urls": list(row.urls),
        "license_summary": row.license_summary,
        "access_state": row.access_state,
        "license_accepted_at": (
            row.license_accepted_at.isoformat() if row.license_accepted_at else None
        ),
        "license_acceptance_note": row.license_acceptance_note,
        "proposed_uses": list(row.proposed_uses),
        "allowed_uses": list(row.allowed_uses),
        "intake_root_key": row.intake_root_key,
        "items": items if row.intake_root_key else 0,
        "registry": {
            "kind": entry.get("kind"),
            "status": entry.get("status"),
            "priority": entry.get("priority"),
            "scope": list(entry.get("scope") or []),
            "training_default": entry.get("training_default"),
            "hash": row.registry_hash,
        },
        "notes": row.notes,
        "row_version": row.row_version,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }
