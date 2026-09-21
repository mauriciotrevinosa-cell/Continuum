"""Running one calibration specification against several providers (M3).

The question a benchmark answers is "which backend draws *this* better?", and
it is only answerable if everything except the backend is identical: the same
panel contract, the same routed reference packet, the same seed, the same
stage. So a comparison is several attempts on the same stage of the same
panel, each naming its provider, kept side by side.

Two things it deliberately does not do:

* it never reviews. Every attempt arrives as a candidate and a person decides.
  An approved environment master is replaced by an approval, never by a run;
* it never overwrites. Attempts are append-only, so a comparison adds evidence
  to a panel's history rather than replacing what is there.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from continuum_db.models import GenerationRecipe, RoughAttempt
from continuum_library.validation import CatalogInputError
from sqlalchemy import select

if TYPE_CHECKING:
    from continuum_production.layered import PanelConstruction

__all__ = ["CalibrationBenchmark"]


class CalibrationBenchmark:
    """The same stage, drawn by several backends, compared on equal terms."""

    def __init__(self, construction: PanelConstruction) -> None:
        self.construction = construction
        self.session = construction.session

    def compare(
        self,
        page_id: uuid.UUID,
        panel: int,
        stage: str,
        provider_ids: Sequence[str],
        *,
        seed: int | None = None,
        notes: str = "",
    ) -> list[dict[str, Any]]:
        """Request this stage once per provider, with everything else held equal."""
        wanted = [p for p in dict.fromkeys(provider_ids) if p]
        if len(wanted) < 2:
            raise CatalogInputError("A comparison needs at least two providers.")
        shared_seed = seed if seed is not None else _seed(page_id, panel, stage)
        out = []
        for provider_id in wanted:
            attempt = self.construction.request_stage(
                page_id,
                panel,
                stage,
                seed=shared_seed,
                notes=notes,
                provider_id=provider_id,
                allow_parallel=True,
            )
            out.append(
                {
                    "provider_id": provider_id,
                    "attempt_id": str(attempt.id),
                    "attempt": attempt.attempt,
                    "seed": shared_seed,
                }
            )
        return out

    def results(self, page_id: uuid.UUID, panel: int, stage: str) -> dict[str, Any]:
        """Every attempt at this stage, by provider, with what it was made from."""
        contract = self.construction._contract(self.construction._page(page_id), panel)
        artifact = self.construction._artifact(
            self.construction._page(page_id), contract, stage, create=False
        )
        if artifact is None:
            return {"stage": stage, "panel": panel, "attempts": []}
        attempts = list(
            self.session.execute(
                select(RoughAttempt)
                .where(RoughAttempt.artifact_id == artifact.id)
                .order_by(RoughAttempt.attempt)
            ).scalars()
        )
        rows = []
        for attempt in attempts:
            recipe = self.session.get(GenerationRecipe, attempt.recipe_id)
            provenance = attempt.artwork_provenance or {}
            execution = (recipe.execution if recipe else {}) or {}
            rows.append(
                {
                    "attempt_id": str(attempt.id),
                    "attempt": attempt.attempt,
                    "provider_id": execution.get("provider_id"),
                    "state": attempt.state.value,
                    "output_class": attempt.output_class.value if attempt.output_class else None,
                    "seed": execution.get("seed"),
                    "model": provenance.get("model"),
                    "workflow": provenance.get("workflow"),
                    "settings": provenance.get("settings"),
                    "conditioning": provenance.get("conditioning"),
                    "references_transmitted": provenance.get("references_transmitted") or [],
                    "structure_drift": provenance.get("structure_drift"),
                    "image": (
                        f"/production/attempts/{attempt.id}/image?kind=OUTPUT"
                        if attempt.content_hash
                        else None
                    ),
                }
            )
        comparable = {
            "same_contract_hash": contract["hash"],
            "same_seed": len({row["seed"] for row in rows}) <= 1,
            "providers": sorted({str(row["provider_id"]) for row in rows if row["provider_id"]}),
        }
        return {"stage": stage, "panel": panel, "comparison": comparable, "attempts": rows}


def _seed(page_id: uuid.UUID, panel: int, stage: str) -> int:
    """A stable seed for one panel's stage, so reruns compare with earlier runs."""
    return int.from_bytes(f"{page_id}:{panel}:{stage}".encode()[:4], "big") % 2_147_483_647
