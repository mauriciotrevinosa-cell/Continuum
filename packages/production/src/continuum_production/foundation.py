"""The foundation batch: the reusable anchors everything else is built on.

The first paid run should not be a handful of final manga pages. It should be
the artifacts every later page depends on - the cast's production sheets, the
outfits they actually wear, the objects that must not change size, and a small
number of calibration reruns that prove the look. Those are reusable; a page
is not.

A batch is a **manifest**, so it is editable, reviewable and reproducible. This
module reads one, prices it against the configured price list, checks it
against what is left of the budget and reports exactly what would happen. It
never starts anything: reserving money is a separate call, and the creator
makes it.

Nothing here knows a character, a project or a count. The manifest carries all
of that; the engine carries none of it.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from continuum_core import canonical_json_hash
from continuum_library.validation import CatalogInputError, require_project_key
from continuum_providers.pricing import micros_to_usd
from sqlalchemy.orm import Session

from continuum_production.budget import SpendLedger

__all__ = ["BATCH_SCHEMA", "ITEM_KINDS", "FoundationBatch", "parse_manifest"]

BATCH_SCHEMA = "continuum.foundation-batch/1"
#: What a batch item asks for. Every kind is a reusable anchor, not a page.
ITEM_KINDS = (
    "CHARACTER_SHEET",
    "OUTFIT_SHEET",
    "PROP_SCALE_SHEET",
    "CALIBRATION_RERUN",
    "INTERACTION",
    "ENSEMBLE",
    "LANGUAGE_STRESS_TEST",
)


def parse_manifest(text: str | dict[str, Any]) -> dict[str, Any]:
    """Read a batch manifest, refusing anything Continuum could not act on."""
    payload = json.loads(text) if isinstance(text, str) else dict(text)
    if payload.get("schema") != BATCH_SCHEMA:
        raise CatalogInputError(f"A foundation batch manifest declares {BATCH_SCHEMA!r}.")
    require_project_key(str(payload.get("project_key") or ""))
    items = payload.get("items")
    if not isinstance(items, list) or not items:
        raise CatalogInputError("A foundation batch has at least one item.")
    seen: set[str] = set()
    cleaned = []
    for index, raw in enumerate(items):
        if not isinstance(raw, dict):
            raise CatalogInputError(f"Batch item {index} is not an object.")
        item_id = str(raw.get("id") or "").strip()
        kind = str(raw.get("kind") or "").strip().upper()
        if not item_id:
            raise CatalogInputError(f"Batch item {index} needs an id.")
        if item_id in seen:
            raise CatalogInputError(f"Batch item id {item_id!r} appears twice.")
        if kind not in ITEM_KINDS:
            raise CatalogInputError(
                f"Batch item {item_id!r} asks for {kind!r}; a batch builds "
                + ", ".join(k.lower().replace("_", " ") for k in ITEM_KINDS)
                + "."
            )
        count = int(raw.get("count", 1))
        if not 1 <= count <= 100:
            raise CatalogInputError(f"Batch item {item_id!r} asks for {count} images.")
        seen.add(item_id)
        cleaned.append({**raw, "id": item_id, "kind": kind, "count": count})
    defaults = dict(payload.get("defaults") or {})
    return {
        "schema": BATCH_SCHEMA,
        "project_key": payload["project_key"],
        "label": str(payload.get("label") or ""),
        "defaults": defaults,
        "items": cleaned,
    }


class FoundationBatch:
    """Price a batch, check it against the budget, and - only when asked - hold it."""

    def __init__(self, session: Session, ledger: SpendLedger) -> None:
        self.session = session
        self.ledger = ledger

    def plan(self, manifest: str | dict[str, Any]) -> dict[str, Any]:
        """What this batch would cost and whether it fits. Spends nothing."""
        batch = parse_manifest(manifest)
        defaults = batch["defaults"]
        state = self.ledger.state()
        items: list[dict[str, Any]] = []
        total = 0
        blockers: list[str] = []
        for raw in batch["items"]:
            provider_id = str(raw.get("provider_id") or defaults.get("provider_id") or "")
            model_ref = str(raw.get("model_ref") or defaults.get("model_ref") or "")
            width = int(raw.get("width") or defaults.get("width") or 0)
            height = int(raw.get("height") or defaults.get("height") or 0)
            batch_mode = bool(raw.get("batch", defaults.get("batch", False)))
            if not provider_id or not model_ref:
                blockers.append(f"{raw['id']}: no provider or model named, here or in defaults")
                items.append({**_summary(raw), "known": False, "usd": None})
                continue
            estimate = self.ledger.estimate(
                provider_id,
                model_ref,
                images=raw["count"],
                width=width,
                height=height,
                batch=batch_mode,
            )
            if not estimate.known:
                blockers.append(f"{raw['id']}: {estimate.reason}")
            total += estimate.micros
            items.append(
                {
                    **_summary(raw),
                    "provider_id": provider_id,
                    "model_ref": model_ref,
                    "known": estimate.known,
                    "micros": estimate.micros,
                    "usd": estimate.usd if estimate.known else None,
                }
            )
        fits = total <= state["remaining_micros"] and not blockers
        if total > state["remaining_micros"]:
            blockers.append(
                f"the batch costs ${micros_to_usd(total)} and "
                f"${micros_to_usd(state['remaining_micros'])} is left"
            )
        return {
            "schema": BATCH_SCHEMA,
            "project_key": batch["project_key"],
            "label": batch["label"],
            "manifest_hash": canonical_json_hash(batch),
            "items": items,
            "images": sum(int(item["count"]) for item in batch["items"]),
            "total_micros": total,
            "total_usd": micros_to_usd(total),
            "budget": self.ledger.state(),
            "fits": fits,
            "blockers": blockers,
        }

    def reserve(self, manifest: str | dict[str, Any], *, approved_by: str) -> dict[str, Any]:
        """Hold the money for a planned batch. Explicit: nobody calls this for you.

        Either every item is held or none is - a half-reserved batch is a batch
        that stops in the middle with money already spent.
        """
        if not approved_by.strip():
            raise CatalogInputError("A paid batch is started by a person. Name who approved it.")
        plan = self.plan(manifest)
        if not plan["fits"]:
            raise CatalogInputError(
                "This batch does not fit the budget: " + "; ".join(plan["blockers"])
            )
        batch = parse_manifest(manifest)
        held: list[uuid.UUID] = []
        for raw, priced in zip(batch["items"], plan["items"], strict=True):
            entry = self.ledger.reserve(
                str(priced["provider_id"]),
                str(priced["model_ref"]),
                purpose=str(raw["kind"])[:40],
                images=int(raw["count"]),
                width=int(raw.get("width") or batch["defaults"].get("width") or 0),
                height=int(raw.get("height") or batch["defaults"].get("height") or 0),
                batch=bool(raw.get("batch", batch["defaults"].get("batch", False))),
                subject=f"{plan['manifest_hash'][:12]}/{raw['id']}",
                detail={
                    "batch_label": plan["label"],
                    "item": raw["id"],
                    "approved_by": approved_by,
                },
            )
            held.append(entry.id)
        return {
            "manifest_hash": plan["manifest_hash"],
            "reserved": [str(entry_id) for entry_id in held],
            "total_usd": plan["total_usd"],
            "budget": self.ledger.state(),
            "approved_by": approved_by,
        }


def _summary(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": raw["id"],
        "kind": raw["kind"],
        "count": raw["count"],
        "subject": raw.get("subject") or raw.get("character") or raw.get("cal_id") or "",
        "note": str(raw.get("note") or ""),
    }
