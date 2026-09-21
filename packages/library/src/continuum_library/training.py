"""Curated training manifests (M3).

Training is where "it was in the library" must never be enough. A dataset here
is an exact, hashed list: every item names where it came from, the rights it
was admitted under, how it was preprocessed, its caption and its split. A
dataset is **locked** before anything may be trained on it, and a locked
dataset never changes - a second version is a second row.

Three rules do the real work:

* an item is admitted only if a person already approved that material for
  training. Nothing an import decided is enough;
* **style and structure never share a dataset.** A pose or lineart annotation
  set teaches a control model, not a look; blending them is how a style
  adapter quietly becomes a pose model. The kind is part of the dataset's
  identity and items carry the purpose tags they were admitted for;
* the split is derived from a seed, so the same manifest always splits the
  same way, and the manifest hash covers everything a training run depends on.

Nothing is trained here. This makes a training run reproducible, inspectable
and refusable; running it is a separate, deliberate act.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import re
import uuid
from collections.abc import Sequence
from typing import Any

from continuum_core import canonical_json_hash
from continuum_core.catalog import TrainingEligibility
from continuum_db.models import (
    ExternalResource,
    ReferenceItem,
    TrainingDataset,
    TrainingDatasetItem,
    TrainingRun,
)
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from continuum_library.validation import (
    CatalogConflictError,
    CatalogInputError,
    CatalogNotFoundError,
    clean_text,
    require_project_key,
)

__all__ = [
    "DATASET_SCHEMA",
    "TrainingDatasets",
    "TrainingRuns",
    "dataset_view",
]

DATASET_SCHEMA = "continuum.training-dataset/1"
#: What each kind of dataset is allowed to teach. A tag outside its kind's set
#: is refused at admission, with the tag named.
KIND_TAGS: dict[str, frozenset[str]] = {
    "STYLE": frozenset(
        {
            "LINE_LANGUAGE",
            "SPOT_BLACKS",
            "SCREENTONE",
            "ENVIRONMENT_DETAIL",
            "ATMOSPHERE",
            "ACTION_ENERGY",
            "PANEL_HIERARCHY",
            "COMPOSITION",
        }
    ),
    "STRUCTURE": frozenset({"POSE", "LINEART", "SCRIBBLE", "SEGMENTATION", "DEPTH", "EDGES"}),
    "SUBJECT": frozenset({"IDENTITY", "BODY", "WARDROBE", "EXPRESSION"}),
}
_DEFAULT_RECIPE = {
    "crop": "panel",
    "target_edge": 1024,
    "caption": "tag-list",
    "dedup": "sha256",
}


def _reference_hash(item: ReferenceItem) -> str | None:
    """The bytes this reference points at, when the locator carries a digest."""
    match = re.search(r"sha256:([0-9a-f]{64})", item.locator or "")
    return match.group(1) if match else None


def dataset_view(
    dataset: TrainingDataset, items: Sequence[TrainingDatasetItem] = ()
) -> dict[str, Any]:
    return {
        "id": str(dataset.id),
        "project_key": dataset.project_key,
        "dataset_key": dataset.dataset_key,
        "version": dataset.version,
        "kind": dataset.kind,
        "name": dataset.name,
        "summary": dataset.summary,
        "state": dataset.state,
        "recipe": dict(dataset.recipe or {}),
        "split": dict(dataset.split or {}),
        "purpose_tags": list(dataset.purpose_tags or []),
        "counts": dict(dataset.counts or {}),
        "manifest_hash": dataset.manifest_hash,
        "locked_by": dataset.locked_by,
        "locked_at": dataset.locked_at.isoformat() if dataset.locked_at else None,
        "items": [
            {
                "id": str(item.id),
                "source_kind": item.source_kind,
                "reference_id": str(item.reference_id) if item.reference_id else None,
                "locator": item.locator,
                "caption": item.caption,
                "purpose_tags": list(item.purpose_tags or []),
                "split": item.split,
                "rights_status": item.rights_status,
                "training_eligibility": item.training_eligibility,
                "content_hash": item.content_hash,
            }
            for item in items
        ],
    }


class TrainingDatasets:
    """Build, inspect and lock a training manifest."""

    def __init__(self, session: Session) -> None:
        self.session = session

    # -- reading --------------------------------------------------------------
    def get(self, dataset_id: uuid.UUID) -> TrainingDataset:
        dataset = self.session.get(TrainingDataset, dataset_id)
        if dataset is None:
            raise CatalogNotFoundError("That training dataset does not exist.")
        return dataset

    def items(self, dataset_id: uuid.UUID) -> list[TrainingDatasetItem]:
        return list(
            self.session.execute(
                select(TrainingDatasetItem)
                .where(TrainingDatasetItem.dataset_id == dataset_id)
                .order_by(TrainingDatasetItem.position, TrainingDatasetItem.id)
            ).scalars()
        )

    def view(self, dataset_id: uuid.UUID) -> dict[str, Any]:
        dataset = self.get(dataset_id)
        return dataset_view(dataset, self.items(dataset.id))

    def all(self, project_key: str) -> list[dict[str, Any]]:
        rows = self.session.execute(
            select(TrainingDataset)
            .where(TrainingDataset.project_key == require_project_key(project_key))
            .order_by(TrainingDataset.dataset_key, TrainingDataset.version)
        ).scalars()
        return [dataset_view(row) for row in rows]

    # -- building -------------------------------------------------------------
    def create(
        self,
        project_key: str,
        dataset_key: str,
        kind: str,
        name: str,
        *,
        summary: str = "",
        purpose_tags: Sequence[str] = (),
        recipe: dict[str, Any] | None = None,
        validation: float = 0.1,
        seed: int = 1,
    ) -> TrainingDataset:
        if kind not in KIND_TAGS:
            raise CatalogInputError(
                "A dataset teaches one of: " + ", ".join(sorted(KIND_TAGS)) + "."
            )
        tags = self._check_tags(kind, purpose_tags)
        if not 0.0 <= validation < 1.0:
            raise CatalogInputError("The validation share is between 0 and 1.")
        version = (
            self.session.execute(
                select(func.max(TrainingDataset.version)).where(
                    TrainingDataset.project_key == require_project_key(project_key),
                    TrainingDataset.dataset_key == dataset_key,
                )
            ).scalar_one()
            or 0
        ) + 1
        dataset = TrainingDataset(
            project_key=project_key,
            dataset_key=dataset_key,
            version=version,
            kind=kind,
            name=clean_text(name, 200, field="Name"),
            summary=clean_text(summary, 4000, field="Summary") if summary else "",
            state="DRAFT",
            recipe={**_DEFAULT_RECIPE, **(recipe or {})},
            split={"validation": validation, "seed": seed},
            purpose_tags=sorted(tags),
        )
        self.session.add(dataset)
        self.session.flush()
        return dataset

    def add_reference(
        self,
        dataset_id: uuid.UUID,
        reference_id: uuid.UUID,
        *,
        caption: str = "",
        purpose_tags: Sequence[str] = (),
        crop: dict[str, Any] | None = None,
    ) -> TrainingDatasetItem:
        """Admit one catalogued reference, or say exactly why it may not be."""
        dataset = self._draft(dataset_id)
        item = self.session.get(ReferenceItem, reference_id)
        if item is None or item.removed_at is not None:
            raise CatalogNotFoundError("That reference does not exist.")
        if item.training_eligibility is not TrainingEligibility.APPROVED:
            raise CatalogInputError(
                "This reference is not approved for training "
                f"({item.training_eligibility.value.lower().replace('_', ' ')}). "
                "Approving material for training is a separate, deliberate decision."
            )
        tags = self._check_tags(dataset.kind, purpose_tags or dataset.purpose_tags)
        key = hashlib.sha256(
            canonical_json_hash({"locator": item.locator, "crop": crop or {}}).encode()
        ).hexdigest()
        if self.session.execute(
            select(TrainingDatasetItem).where(
                TrainingDatasetItem.dataset_id == dataset.id,
                TrainingDatasetItem.item_key == key,
            )
        ).scalar_one_or_none():
            raise CatalogConflictError("That exact crop of that image is already in the dataset.")
        row = TrainingDatasetItem(
            dataset_id=dataset.id,
            source_kind="REFERENCE",
            reference_id=item.id,
            locator=item.locator,
            crop=crop,
            item_key=key,
            content_hash=_reference_hash(item),
            caption=clean_text(caption, 2000, field="Caption") if caption else "",
            purpose_tags=sorted(tags),
            split="TRAIN",
            rights_status=item.rights_status.value,
            training_eligibility=item.training_eligibility.value,
            position=len(self.items(dataset.id)),
        )
        self.session.add(row)
        self.session.flush()
        return row

    def add_resource(
        self,
        dataset_id: uuid.UUID,
        resource_id: uuid.UUID,
        locator: str,
        *,
        caption: str = "",
        purpose_tags: Sequence[str] = (),
    ) -> TrainingDatasetItem:
        """Admit material from a registered external resource."""
        dataset = self._draft(dataset_id)
        resource = self.session.get(ExternalResource, resource_id)
        if resource is None:
            raise CatalogNotFoundError("That external resource is not registered.")
        if "TRAINING_APPROVED" not in (resource.allowed_uses or []):
            raise CatalogInputError(
                f"{resource.title or resource.key} is not approved for training. The registry "
                "refuses to "
                "widen an allowed use; record the licence decision first."
            )
        tags = self._check_tags(dataset.kind, purpose_tags or dataset.purpose_tags)
        key = hashlib.sha256(
            canonical_json_hash({"locator": locator, "resource": str(resource_id)}).encode()
        ).hexdigest()
        row = TrainingDatasetItem(
            dataset_id=dataset.id,
            source_kind="EXTERNAL_RESOURCE",
            external_resource_id=resource.id,
            locator=locator[:500],
            item_key=key,
            caption=clean_text(caption, 2000, field="Caption") if caption else "",
            purpose_tags=sorted(tags),
            split="TRAIN",
            rights_status="LICENSED" if resource.license_accepted_at else "UNKNOWN",
            training_eligibility="APPROVED",
            position=len(self.items(dataset.id)),
        )
        self.session.add(row)
        self.session.flush()
        return row

    # -- locking --------------------------------------------------------------
    def manifest(self, dataset_id: uuid.UUID) -> dict[str, Any]:
        """The canonical manifest: what a training run is actually built from."""
        dataset = self.get(dataset_id)
        items = self.items(dataset.id)
        return {
            "schema": DATASET_SCHEMA,
            "project_key": dataset.project_key,
            "dataset_key": dataset.dataset_key,
            "version": dataset.version,
            "kind": dataset.kind,
            "purpose_tags": list(dataset.purpose_tags or []),
            "recipe": dict(dataset.recipe or {}),
            "split": dict(dataset.split or {}),
            "items": [
                {
                    "item_key": item.item_key,
                    "source_kind": item.source_kind,
                    "locator": item.locator,
                    "crop": item.crop,
                    "content_hash": item.content_hash,
                    "caption": item.caption,
                    "purpose_tags": list(item.purpose_tags or []),
                    "split": item.split,
                    "rights_status": item.rights_status,
                    "training_eligibility": item.training_eligibility,
                }
                for item in sorted(items, key=lambda row: row.item_key)
            ],
        }

    def lock(self, dataset_id: uuid.UUID, reviewer: str) -> TrainingDataset:
        """Fix the split and hash the manifest. After this, nothing may change."""
        dataset = self._draft(dataset_id)
        who = reviewer.strip()
        if not who:
            raise CatalogInputError("A human reviewer is required.")
        items = self.items(dataset.id)
        if not items:
            raise CatalogInputError("An empty dataset cannot be locked.")
        self._assign_splits(dataset, items)
        self.session.flush()
        manifest = self.manifest(dataset.id)
        counts = {
            "items": len(items),
            "train": sum(1 for item in items if item.split == "TRAIN"),
            "validation": sum(1 for item in items if item.split == "VALIDATION"),
        }
        dataset.counts = counts
        dataset.manifest_hash = canonical_json_hash(manifest)
        dataset.state = "LOCKED"
        dataset.locked_by, dataset.locked_at = who[:200], dt.datetime.now(dt.UTC)
        self.session.flush()
        return dataset

    def _assign_splits(
        self, dataset: TrainingDataset, items: Sequence[TrainingDatasetItem]
    ) -> None:
        """Deterministic from the seed: the same manifest always splits the same."""
        share = float((dataset.split or {}).get("validation", 0.0))
        seed = int((dataset.split or {}).get("seed", 1))
        ranked = sorted(
            items,
            key=lambda item: hashlib.sha256(f"{seed}:{item.item_key}".encode()).hexdigest(),
        )
        holdout = int(len(ranked) * share)
        for index, item in enumerate(ranked):
            item.split = "VALIDATION" if index < holdout else "TRAIN"

    def _draft(self, dataset_id: uuid.UUID) -> TrainingDataset:
        dataset = self.get(dataset_id)
        if dataset.state != "DRAFT":
            raise CatalogConflictError(
                f"That dataset is {dataset.state.lower()}. A locked manifest never changes; "
                "make a new version instead."
            )
        return dataset

    def _check_tags(self, kind: str, tags: Sequence[str]) -> set[str]:
        allowed = KIND_TAGS[kind]
        wanted = {str(tag).strip().upper() for tag in tags if str(tag).strip()}
        stray = sorted(wanted - allowed)
        if stray:
            raise CatalogInputError(
                f"A {kind} dataset does not teach {', '.join(t.lower() for t in stray)}. "
                "Structural conditioning and visual style belong to different datasets."
            )
        return wanted


class TrainingRuns:
    """Reproducible training configurations over locked datasets."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def plan(
        self,
        dataset_id: uuid.UUID,
        base_model_ref: str,
        config: dict[str, Any],
        *,
        label: str = "",
        adapter_kind: str = "LORA",
    ) -> TrainingRun:
        dataset = TrainingDatasets(self.session).get(dataset_id)
        if dataset.state != "LOCKED":
            raise CatalogConflictError(
                "Training runs on a locked manifest only: lock the dataset first."
            )
        if not base_model_ref.strip():
            raise CatalogInputError("A training run names the base model it adapts.")
        body = {
            "dataset_hash": dataset.manifest_hash,
            "base_model_ref": base_model_ref,
            "adapter_kind": adapter_kind,
            "config": config,
        }
        run = TrainingRun(
            dataset_id=dataset.id,
            project_key=dataset.project_key,
            label=clean_text(label, 200, field="Label") if label else "",
            base_model_ref=base_model_ref[:200],
            adapter_kind=adapter_kind[:20],
            config=config,
            config_hash=canonical_json_hash(body),
            state="PLANNED",
        )
        self.session.add(run)
        self.session.flush()
        return run

    def record_output(
        self, run_id: uuid.UUID, output: dict[str, Any], *, state: str = "SUCCEEDED"
    ) -> TrainingRun:
        """What a run produced: file name, hash, licence, where it ran."""
        run = self.session.get(TrainingRun, run_id)
        if run is None:
            raise CatalogNotFoundError("That training run does not exist.")
        missing = [
            key for key in ("name", "sha256", "license", "trained_on") if not output.get(key)
        ]
        if state == "SUCCEEDED" and missing:
            raise CatalogInputError(
                "A trained adapter is not reproducible without " + ", ".join(missing) + "."
            )
        run.output, run.state = output, state
        run.finished_at = dt.datetime.now(dt.UTC)
        self.session.flush()
        return run
