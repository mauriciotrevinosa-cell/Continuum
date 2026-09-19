"""Layered panel construction (M3): panel contract -> frozen stages -> composed page.

Continuum owns the visual problem; a renderer solves one bounded stage of it.

* A **panel contract** is derived from the materialized page: the panel's beat,
  shot, cast (possibly nobody), the required anchors, what must never appear,
  and the construction stages it needs. It is hashed; a changed contract makes
  every stage drawn from the old one stale.
* Each **stage** of each panel is its own ``rough_artifact`` (kind PANEL, with
  ``stage`` set), so its attempts, reviews and supersession never touch
  another stage's rows.
* **Freeze = approval.** A stage builds only on the frozen output of the stage
  before it, recorded as an ``UPSTREAM_STAGE`` input plus a control input in the
  recipe. It may change only what its stage contract lists as editable.
* **Invalidation is derived, never stored:** a stage is STALE when its attempt
  was built on an upstream attempt that is no longer the frozen one, or from an
  older contract. Re-freezing COMPOSITION stales everything after it; re-freezing
  LIGHT_SHADOW stales only what follows LIGHT_SHADOW.
* The final **page** is a normal page attempt composed deterministically from
  each panel's frozen last stage (no diffusion), so page review, continuity and
  staleness work unchanged.

Retrieval gives each stage the narrowest evidence for its problem (the stage's
techniques, the panel's setting and shot), never identity from style material;
a panel with a cast additionally receives that cast's identity and wardrobe
inputs from the character corpus, exactly as whole pages do.
"""

from __future__ import annotations

import re
import uuid
from typing import TYPE_CHECKING, Any

from continuum_core import canonical_json_hash
from continuum_core.knowledge import STAGE_CONTRACTS, STAGE_FACETS, stage_plan
from continuum_core.references import (
    AttemptState,
    BundleRole,
    PanelStage,
    RenderOutput,
    ReviewDecision,
    RoughArtifactKind,
    RoughPurpose,
    TechniqueFacet,
)
from continuum_db.models import (
    AttemptInput,
    AttemptReview,
    ProductionPage,
    ProductionProfile,
    ProductionRun,
    RoughArtifact,
    RoughAttempt,
)
from continuum_imaging.manga import panel_boxes
from continuum_library import CatalogConflictError, CatalogInputError, CatalogNotFoundError
from continuum_library.knowledge import VisualKnowledge
from continuum_library.validation import clean_text
from sqlalchemy import select

from continuum_production.service import refusal
from continuum_production.views import _job

if TYPE_CHECKING:
    from continuum_production.manga import MangaProduction

__all__ = [
    "COMPOSE_SCHEMA",
    "COMPOSE_WORKFLOW",
    "CONTRACT_SCHEMA",
    "DEFAULT_STAGE_PROVIDER",
    "FROZEN_STATES",
    "STAGE_SCHEMA",
    "STAGE_WORKFLOW",
    "PanelConstruction",
    "panel_contracts",
    "stage_contract",
]

CONTRACT_SCHEMA = "continuum.panel-contract/1"
STAGE_SCHEMA = "continuum.panel-stage-recipe/1"
COMPOSE_SCHEMA = "continuum.page-composition/1"
STAGE_WORKFLOW = "continuum.panel-stage/1"
COMPOSE_WORKFLOW = "continuum.page-compose/1"
DEFAULT_STAGE_PROVIDER = "fake.deterministic-stage"
FROZEN_STATES = frozenset(
    {AttemptState.TECHNICAL_PASS, AttemptState.CREATIVE_APPROVED, AttemptState.FINAL_APPROVED}
)
#: What no panel image ever contains: Continuum letters and borders pages itself.
GLOBAL_FORBIDDEN = (
    "lettering, speech balloons, captions or any text",
    "panel borders or extra panels",
)
#: Stages that look up the project's house-style exemplars.
HOUSE_STYLE_STAGES = frozenset(
    {PanelStage.LINE, PanelStage.VALUE_MATERIAL, PanelStage.LIGHT_SHADOW, PanelStage.FINISH}
)
_ENVIRONMENT_FACETS = {TechniqueFacet.BACKGROUND_TREATMENT.value, TechniqueFacet.ARCHITECTURE.value}
_EFFECT = re.compile(
    r"\b(magic\w*|spells?|glow\w*|energy|explosions?|impact|sparks?|particles?|smoke|rain"
    r"|fire|flames?|lightning|aura)\b",
    re.I,
)
_NEGATED = re.compile(r"\b(no|not|without|never)\s+(?:\w+\s+){0,2}$", re.I)
_MAX_PANEL_EDGE = 1024


def _needs_effects(text: str) -> bool:
    """True when the panel asks for an effect (a negated mention does not count)."""
    for match in _EFFECT.finditer(text):
        if not _NEGATED.search(text[max(0, match.start() - 30) : match.start()]):
            return True
    return False


def panel_contracts(body: dict[str, Any]) -> list[dict[str, Any]]:
    """One hashed contract per render panel of a materialized page."""
    plan = body.get("plan") or {}
    panels = plan.get("render_panels") or []
    locks = [
        str(item).removeprefix("MUST SHOW:").strip().rstrip(".")
        for item in body.get("directions") or []
        if str(item).startswith("MUST SHOW:")
    ]
    page_forbidden = [
        str(item).removeprefix("DO NOT:").strip().rstrip(".")
        for item in body.get("constraints") or []
    ]
    calibration = body.get("calibration") or {}
    contracts: list[dict[str, Any]] = []
    for panel in panels:
        cast = [str(name) for name in panel.get("characters") or []]
        required = [
            lock
            for lock in locks
            if not cast or len(panels) == 1 or any(n.lower() in lock.lower() for n in cast)
        ] or locks[:2]
        forbidden = [
            *page_forbidden,
            *GLOBAL_FORBIDDEN,
            "people or figures of any kind" if not cast else "anyone outside the panel cast",
        ]
        direction = str(panel.get("direction") or "")
        stages = stage_plan(
            has_cast=bool(cast),
            needs_effects=_needs_effects(" ".join([direction, *required])),
        )
        contract: dict[str, Any] = {
            "schema": CONTRACT_SCHEMA,
            "page_key": body.get("page_key"),
            "page_hash": body.get("page_hash"),
            "panel": int(panel.get("number") or len(contracts) + 1),
            "panel_count": len(panels),
            "beat": direction,
            "shot": str(panel.get("shot") or "STANDARD"),
            "cast": cast,
            "required": required,
            "forbidden": forbidden,
            "environment_tags": list(plan.get("environment_tags") or []),
            "intents": list(body.get("intents") or []),
            "stages": [stage.value for stage in stages],
            "lineage": dict(body.get("lineage") or {}),
            "calibration": (
                {
                    key: calibration.get(key)
                    for key in ("cal_id", "source_document", "source_locator")
                }
                if calibration
                else None
            ),
        }
        contract["hash"] = canonical_json_hash(contract)
        contracts.append(contract)
    return contracts


def stage_contract(stages: list[str], stage: str) -> dict[str, Any]:
    """What this stage may change, and everything the stages before it froze."""
    index = stages.index(stage)
    frozen: list[str] = []
    for prior in stages[:index]:
        frozen.extend(STAGE_CONTRACTS[PanelStage(prior)].protects)
    return {
        **STAGE_CONTRACTS[PanelStage(stage)].as_dict(),
        "frozen_before": list(dict.fromkeys(frozen)),
        "upstream": stages[index - 1] if index else None,
        "order": index + 1,
        "of": len(stages),
    }


def _panel_size(width: int, height: int, count: int, index: int) -> tuple[int, int]:
    _x, _y, share_w, share_h = panel_boxes(count)[index]
    target_w, target_h = max(1.0, width * share_w), max(1.0, height * share_h)
    scale = min(1.0, _MAX_PANEL_EDGE / max(target_w, target_h))
    return (
        max(256, int(target_w * scale) // 8 * 8),
        max(256, int(target_h * scale) // 8 * 8),
    )


def _role(entry: dict[str, Any]) -> BundleRole:
    if entry["reference_class"] == "MOOD":
        return BundleRole.MOOD
    if set(entry["matched_facets"]) & _ENVIRONMENT_FACETS or any(
        term.startswith("location:") for term in entry["matched_descriptors"]
    ):
        return BundleRole.ENVIRONMENT
    return BundleRole.TECHNIQUE


class PanelConstruction:
    """Build a page's panels stage by stage, then compose the page."""

    def __init__(self, manga: MangaProduction) -> None:
        self.manga = manga
        self.session = manga.session
        self.rough = manga.rough
        self.knowledge = VisualKnowledge(manga.session)

    # -- lookups --------------------------------------------------------------
    def _page(self, page_id: uuid.UUID) -> ProductionPage:
        page = self.session.get(ProductionPage, page_id)
        if page is None:
            raise CatalogNotFoundError("That production page does not exist.")
        return page

    def _run(self, page: ProductionPage) -> tuple[ProductionRun, ProductionProfile]:
        run = self.session.get(ProductionRun, page.run_id)
        profile = self.session.get(ProductionProfile, run.profile_id) if run else None
        assert run is not None and profile is not None
        return run, profile

    def contracts(self, page: ProductionPage) -> list[dict[str, Any]]:
        return panel_contracts(self.manga.page_body(page))

    def _contract(self, page: ProductionPage, panel: int) -> dict[str, Any]:
        for contract in self.contracts(page):
            if contract["panel"] == panel:
                return contract
        raise CatalogNotFoundError(f"Page {page.sequence} has no panel {panel}.")

    def _artifact(
        self, page: ProductionPage, contract: dict[str, Any], stage: str, *, create: bool
    ) -> RoughArtifact | None:
        owner = self.session.get(RoughArtifact, page.artifact_id)
        assert owner is not None
        found = self.session.execute(
            select(RoughArtifact).where(
                RoughArtifact.project_key == owner.project_key,
                RoughArtifact.purpose == owner.purpose,
                RoughArtifact.production_run_id == owner.production_run_id,
                RoughArtifact.episode == owner.episode,
                RoughArtifact.page == owner.page,
                RoughArtifact.panel == contract["panel"],
                RoughArtifact.kind == RoughArtifactKind.PANEL,
                RoughArtifact.stage == PanelStage(stage),
            )
        ).scalar_one_or_none()
        if found is not None or not create:
            return found
        artifact = RoughArtifact(
            project_key=owner.project_key,
            episode=owner.episode,
            chapter=owner.chapter,
            page=owner.page,
            panel=contract["panel"],
            kind=RoughArtifactKind.PANEL,
            purpose=owner.purpose,
            title=f"{page.page_key} panel {contract['panel']} - {stage.lower()}"[:300],
            production_run_id=owner.production_run_id,
            panel_script_document=owner.panel_script_document,
            panel_script_version=owner.panel_script_version,
            brief=contract["beat"][:8000],
            stage=PanelStage(stage),
        )
        self.session.add(artifact)
        self.session.flush()
        return artifact

    def _attempts(self, artifact: RoughArtifact | None) -> list[RoughAttempt]:
        if artifact is None:
            return []
        return list(
            self.session.execute(
                select(RoughAttempt)
                .where(RoughAttempt.artifact_id == artifact.id)
                .order_by(RoughAttempt.attempt)
            ).scalars()
        )

    def _upstream(self, attempt: RoughAttempt) -> dict[str, Any] | None:
        row = self.session.execute(
            select(AttemptInput).where(
                AttemptInput.attempt_id == attempt.id,
                AttemptInput.role == BundleRole.UPSTREAM_STAGE,
            )
        ).scalar_one_or_none()
        return dict(row.provenance or {}) if row is not None else None

    # -- the stage chain ------------------------------------------------------
    def _chain(self, page: ProductionPage, contract: dict[str, Any]) -> dict[str, dict[str, Any]]:
        """Every stage of one panel, in order, with its state and why."""
        stages: list[str] = contract["stages"]
        chain: dict[str, dict[str, Any]] = {}
        for index, stage in enumerate(stages):
            artifact = self._artifact(page, contract, stage, create=False)
            attempts = self._attempts(artifact)
            previous = chain[stages[index - 1]] if index else None

            def valid(attempt: RoughAttempt, previous: dict[str, Any] | None = previous) -> str:
                """'' when the attempt was built on what is frozen now, else why not."""
                recipe = self.rough.recipe(attempt.recipe_id)
                if (recipe.intent.get("contract") or {}).get("hash") != contract["hash"]:
                    return "the panel contract changed since it was drawn"
                if previous is None:
                    return ""
                if previous["frozen"] is None:
                    return f"{previous['stage']} is no longer frozen"
                if not previous["frozen_valid"]:
                    return f"{previous['stage']} is stale ({previous['frozen_reason']})"
                source = (self._upstream(attempt) or {}).get("attempt_id")
                if source != str(previous["frozen"].id):
                    return (
                        f"{previous['stage']} was frozen again "
                        f"(attempt {previous['frozen'].attempt})"
                    )
                return ""

            frozen = next((a for a in reversed(attempts) if a.state in FROZEN_STATES), None)
            frozen_reason = valid(frozen) if frozen is not None else ""
            frozen_valid = frozen is not None and not frozen_reason
            latest = attempts[-1] if attempts else None
            newer = latest is not None and (frozen is None or latest.attempt > frozen.attempt)
            upstream_ready = previous is None or previous["frozen_valid"]
            reason = ""
            if newer and latest is not None and latest.state is AttemptState.QUEUED:
                job = _job(self.rough, latest)
                status = (job or {}).get("status")
                state = status if status in ("BLOCKED", "FAILED") else "QUEUED"
                if state != "QUEUED":
                    remediation = (job or {}).get("remediation")
                    reason = str(
                        (job or {}).get("error")
                        or (remediation.get("message") if isinstance(remediation, dict) else "")
                        or (job or {}).get("blocked_reason")
                        or "the render did not complete"
                    )
            elif newer and latest is not None and latest.state is AttemptState.GENERATED:
                reason = valid(latest)
                state = "STALE" if reason else "IN_REVIEW"
            elif frozen is not None:
                reason = frozen_reason
                state = "FROZEN" if frozen_valid else "STALE"
            elif upstream_ready:
                state = "READY"
            else:
                assert previous is not None
                state = "WAITING"
                reason = f"freeze {previous['stage']} first"
            pending = latest is not None and latest.state is AttemptState.QUEUED
            chain[stage] = {
                "stage": stage,
                "index": index,
                "artifact": artifact,
                "attempts": attempts,
                #: The frozen attempt (valid or not); later stages build on it only if valid.
                "frozen": frozen,
                "frozen_valid": frozen_valid,
                "frozen_reason": frozen_reason,
                "latest": latest,
                "state": state,
                "reason": reason,
                "can_render": not pending and upstream_ready,
                "valid": valid,
            }
        return chain

    # -- retrieval --------------------------------------------------------------
    def pack(
        self, run: ProductionRun, contract: dict[str, Any], stage: str
    ) -> list[dict[str, Any]]:
        """The stage's reference pack by role. Never identity from style material."""
        terms = [
            *contract["environment_tags"],
            contract["shot"].lower(),
            *(intent.replace("_", " ") for intent in contract["intents"]),
        ]
        stage_enum = PanelStage(stage)
        found = self.knowledge.retrieve(
            run.project_key, facets=STAGE_FACETS[stage_enum], terms=terms, limit=4
        )
        pack = [{**entry, "role": _role(entry).value} for entry in found]
        if stage_enum in HOUSE_STYLE_STAGES:
            seen = {entry["reference_id"] for entry in pack}
            for entry in self.knowledge.house_style(run.project_key, limit=2):
                if entry["reference_id"] not in seen:
                    pack.append(
                        {
                            **entry,
                            "role": BundleRole.STYLE.value,
                            "why": [*entry["why"], "house style exemplar - never identity"],
                        }
                    )
        return pack

    # -- views ----------------------------------------------------------------
    def view(self, page_id: uuid.UUID) -> dict[str, Any]:
        page = self._page(page_id)
        run, _profile = self._run(page)
        panels = []
        compose_problems = []
        for contract in self.contracts(page):
            chain = self._chain(page, contract)
            stages = []
            for stage in contract["stages"]:
                entry = chain[stage]
                stages.append(
                    {
                        "stage": stage,
                        "contract": stage_contract(contract["stages"], stage),
                        "state": entry["state"],
                        "reason": entry["reason"],
                        "can_render": entry["can_render"],
                        "frozen_attempt_id": str(entry["frozen"].id) if entry["frozen"] else None,
                        "frozen_valid": entry["frozen_valid"],
                        "attempts": [self._attempt_view(a) for a in entry["attempts"]],
                        "pack": self.pack(run, contract, stage),
                    }
                )
            final = chain[contract["stages"][-1]]
            if not final["frozen_valid"]:
                compose_problems.append(
                    f"panel {contract['panel']}: {final['stage'].lower()} is "
                    f"{final['state'].lower().replace('_', ' ')}"
                )
            panels.append({"contract": contract, "stages": stages})
        return {
            "page_id": str(page.id),
            "run": {"id": str(run.id), "purpose": run.purpose.value, "status": run.status},
            "panels": panels,
            "compose": {
                "ready": bool(panels) and not compose_problems,
                "blocked": compose_problems,
            },
        }

    def _attempt_view(self, attempt: RoughAttempt) -> dict[str, Any]:
        upstream = self._upstream(attempt)
        provenance = attempt.artwork_provenance or {}
        return {
            "id": str(attempt.id),
            "attempt": attempt.attempt,
            "state": attempt.state.value,
            "output_class": attempt.output_class.value if attempt.output_class else None,
            "content_hash": attempt.content_hash,
            "width": attempt.width,
            "height": attempt.height,
            "created_at": attempt.created_at.isoformat() if attempt.created_at else None,
            "generated_at": attempt.generated_at.isoformat() if attempt.generated_at else None,
            "image": (
                f"/production/attempts/{attempt.id}/image?kind=OUTPUT"
                if attempt.content_hash
                else None
            ),
            "upstream": upstream,
            "structure_drift": provenance.get("structure_drift"),
            "provider_id": provenance.get("provider_id"),
            # What reached the backend and how it conditioned the image; what was
            # withheld from it (never transmitted) and why.
            "conditioning": provenance.get("conditioning"),
            "transmitted": list(provenance.get("references_transmitted") or []),
            "withheld": list(provenance.get("references_withheld") or []),
            "job": _job(self.rough, attempt),
        }

    # -- rendering a stage ----------------------------------------------------
    def request_stage(
        self,
        page_id: uuid.UUID,
        panel: int,
        stage: str,
        *,
        seed: int | None = None,
        notes: str = "",
    ) -> RoughAttempt:
        page = self._page(page_id)
        if page.state in {"WAITING", "BLOCKED"}:
            raise CatalogConflictError(
                f"Page {page.sequence} is {page.state}; its panels cannot be built yet."
            )
        run, profile = self._run(page)
        if run.status != "OPEN":
            raise CatalogConflictError("That run is closed.")
        contract = self._contract(page, panel)
        stages: list[str] = contract["stages"]
        if stage not in stages:
            raise CatalogInputError(
                f"{stage} is not a stage of panel {panel} (its stages: {', '.join(stages)})."
            )
        chain = self._chain(page, contract)
        entry = chain[stage]
        if not entry["can_render"]:
            raise CatalogConflictError(
                entry["reason"]
                or f"Stage {stage} is already rendering; review it when it finishes."
            )
        index = stages.index(stage)
        this_stage = stage_contract(stages, stage)
        artifact = self._artifact(page, contract, stage, create=True)
        assert artifact is not None
        self.rough._lock_artifact(artifact.id)
        backend = profile.body.get("backend") or {}

        inputs: list[dict[str, Any]] = []
        control: list[dict[str, Any]] = []
        upstream: dict[str, Any] | None = None
        if index:
            previous = chain[stages[index - 1]]
            frozen: RoughAttempt = previous["frozen"]
            upstream = {
                "attempt_id": str(frozen.id),
                "attempt": frozen.attempt,
                "stage": previous["stage"],
                "sha256": frozen.content_hash,
                "output_class": frozen.output_class.value if frozen.output_class else None,
                "protects": this_stage["frozen_before"],
            }
            inputs.append(
                {
                    "role": BundleRole.UPSTREAM_STAGE,
                    "reference_id": None,
                    "locator": f"gen:sha256:{frozen.content_hash}",
                    "unit_index": None,
                    "region": None,
                    "character_id": None,
                    "outfit_id": None,
                    "aspect": None,
                    "label": f"frozen {previous['stage'].lower()} (attempt {frozen.attempt})",
                    "provenance": upstream,
                }
            )
            control.append(
                {
                    "kind": "upstream_stage",
                    "stage": previous["stage"],
                    "sha256": frozen.content_hash,
                    "preserve": this_stage["frozen_before"],
                }
            )
            width, height = int(frozen.width or 0), int(frozen.height or 0)
        else:
            width, height = _panel_size(
                int(backend.get("width", 1024)),
                int(backend.get("height", 1456)),
                contract["panel_count"],
                contract["panel"] - 1,
            )

        pack = self.pack(run, contract, stage)
        for ref in pack:
            item = self.manga.catalog.reference(uuid.UUID(ref["reference_id"]))
            inputs.append(
                {
                    "role": BundleRole(ref["role"]),
                    "reference_id": item.id,
                    "locator": item.locator,
                    "unit_index": item.unit_index,
                    "region": None,
                    "character_id": None,
                    "outfit_id": None,
                    "aspect": None,
                    "label": f"{ref['role'].lower()}: {ref['label'] or ref['reference_id']}"[:300],
                    "provenance": {
                        key: ref[key]
                        for key in (
                            "why",
                            "matched_facets",
                            "matched_descriptors",
                            "standing",
                            "rights_status",
                            "training_eligibility",
                            "warnings",
                            "origin",
                            "reference_class",
                        )
                    }
                    | {"identity_evidence": False},
                }
            )
        if contract["cast"]:
            bundle = self.manga.assemble(page)
            inputs.extend(self.manga.character_inputs(bundle, contract["cast"]))
        for position, row in enumerate(inputs):
            row["position"] = position

        provider_id = (
            DEFAULT_STAGE_PROVIDER
            if run.purpose is RoughPurpose.WORKFLOW_TEST
            else str(backend.get("stage_provider_id") or DEFAULT_STAGE_PROVIDER)
        )
        intent: dict[str, Any] = {
            "schema": STAGE_SCHEMA,
            "mode": "NEW_GENERATION" if index == 0 else "COMPOSITE",
            "target": {
                "project_key": run.project_key,
                "episode": run.episode,
                "chapter": artifact.chapter,
                "page": artifact.page,
                "panel": contract["panel"],
                "kind": "PANEL",
                "stage": stage,
            },
            "page_id": str(page.id),
            # A stage edits no source plate; what it keeps is the upstream (control).
            "plate_region": None,
            "operations": [],
            "contract": contract,
            "stage": this_stage,
            "upstream": upstream,
            "creator_notes": clean_text(notes, 8000, field="Notes") if notes else "",
            "pack": [
                {"role": ref["role"], "reference_id": ref["reference_id"], "why": ref["why"]}
                for ref in pack
            ],
        }
        attempts = entry["attempts"]
        attempt = self.rough._create_attempt(
            artifact,
            intent=intent,
            inputs=inputs,
            seed=seed,
            width=width,
            height=height,
            workflow=STAGE_WORKFLOW,
            extra_execution={
                "provider_id": provider_id,
                "backend_settings": backend.get("stage_settings", {}),
                "control_inputs": control,
            },
            parent=attempts[-1] if attempts else None,
        )
        self.session.flush()
        return attempt

    # -- review ---------------------------------------------------------------
    def review_stage(
        self,
        attempt_id: uuid.UUID,
        decision: str,
        *,
        notes: str = "",
        seed: int | None = None,
    ) -> tuple[RoughAttempt, RoughAttempt | None]:
        """FREEZE, REJECT or REGENERATE one stage attempt. Returns (attempt, new attempt)."""
        attempt = self.rough.attempt(attempt_id)
        artifact = self.rough._lock_artifact(attempt.artifact_id)
        if artifact.stage is None:
            raise CatalogInputError("That attempt is not a construction stage.")
        recipe = self.rough.recipe(attempt.recipe_id)
        page = self._page(uuid.UUID(recipe.intent["page_id"]))
        run, _profile = self._run(page)
        panel = int(recipe.intent["contract"]["panel"])
        stage = artifact.stage.value
        text = clean_text(notes, 4000, field="Notes")
        if decision == "REJECT":
            self.rough.review(attempt.id, ReviewDecision.REJECT, notes=text)
            return attempt, None
        if decision == "REGENERATE":
            if attempt.state is AttemptState.QUEUED:
                raise CatalogConflictError("That attempt has not been rendered yet.")
            self.session.add(
                AttemptReview(attempt_id=attempt.id, decision=ReviewDecision.REGENERATE, notes=text)
            )
            if attempt.state is AttemptState.GENERATED:
                attempt.state = AttemptState.REJECTED
            self.session.flush()
            return attempt, self.request_stage(page.id, panel, stage, seed=seed, notes=notes)
        if decision != "FREEZE":
            raise CatalogInputError("A stage is frozen, rejected or regenerated.")
        if attempt.state is AttemptState.QUEUED:
            raise CatalogConflictError("That attempt has not been rendered yet.")
        if attempt.state in FROZEN_STATES:
            raise CatalogConflictError("That attempt is already frozen.")
        if attempt.state is not AttemptState.GENERATED:
            raise CatalogInputError(
                f"Attempt {attempt.attempt} is {attempt.state.value.lower()}; "
                "render the stage again to freeze a new one."
            )
        contract = self._contract(page, panel)
        chain = self._chain(page, contract)
        stale = chain[stage]["valid"](attempt)
        if stale:
            raise CatalogConflictError(
                f"Attempt {attempt.attempt} cannot be frozen: {stale}. Render the stage again."
            )
        verdict = (
            ReviewDecision.TECHNICAL_PASS
            if attempt.output_class is not RenderOutput.ARTWORK_CANDIDATE
            or run.purpose in (RoughPurpose.WORKFLOW_TEST, RoughPurpose.NON_CANON_SAMPLE)
            else ReviewDecision.CREATIVE_APPROVE
        )
        refused = refusal(artifact, attempt, verdict)
        if refused is not None:
            raise CatalogInputError(refused)
        for other in chain[stage]["attempts"]:
            if other.id != attempt.id and other.state in FROZEN_STATES:
                other.state = AttemptState.SUPERSEDED
        attempt.state = (
            AttemptState.TECHNICAL_PASS
            if verdict is ReviewDecision.TECHNICAL_PASS
            else AttemptState.CREATIVE_APPROVED
        )
        self.session.add(AttemptReview(attempt_id=attempt.id, decision=verdict, notes=text))
        self.session.flush()
        return attempt, None

    # -- the page -------------------------------------------------------------
    def compose(self, page_id: uuid.UUID, *, notes: str = "") -> RoughAttempt:
        """A page attempt composed deterministically from every panel's frozen last stage."""
        page = self._page(page_id)
        if page.state in {"WAITING", "BLOCKED"}:
            raise CatalogConflictError(f"Page {page.sequence} is {page.state}.")
        run, profile = self._run(page)
        if run.status != "OPEN":
            raise CatalogConflictError("That run is closed.")
        contracts = self.contracts(page)
        if not contracts:
            raise CatalogInputError("This page has no panels to compose.")
        panels: list[dict[str, Any]] = []
        problems = []
        for contract in contracts:
            final = self._chain(page, contract)[contract["stages"][-1]]
            if not final["frozen_valid"]:
                problems.append(
                    f"panel {contract['panel']}: {final['stage'].lower()} is "
                    f"{final['state'].lower()}"
                )
                continue
            frozen: RoughAttempt = final["frozen"]
            panels.append(
                {
                    "panel": contract["panel"],
                    "stage": final["stage"],
                    "attempt_id": str(frozen.id),
                    "attempt": frozen.attempt,
                    "sha256": frozen.content_hash,
                    "output_class": frozen.output_class.value if frozen.output_class else None,
                    "contract_hash": contract["hash"],
                }
            )
        if problems:
            raise CatalogConflictError("The page cannot be composed yet: " + "; ".join(problems))
        owner = self.rough._lock_artifact(page.artifact_id)
        inputs = [
            {
                "position": position,
                "role": BundleRole.UPSTREAM_STAGE,
                "reference_id": None,
                "locator": f"gen:sha256:{entry['sha256']}",
                "unit_index": None,
                "region": None,
                "character_id": None,
                "outfit_id": None,
                "aspect": None,
                "label": f"panel {entry['panel']} - frozen {entry['stage'].lower()}",
                "provenance": entry,
            }
            for position, entry in enumerate(panels)
        ]
        backend = profile.body.get("backend") or {}
        intent: dict[str, Any] = {
            "schema": COMPOSE_SCHEMA,
            "mode": "COMPOSITE",
            "target": {
                "project_key": run.project_key,
                "episode": run.episode,
                "chapter": owner.chapter,
                "page": owner.page,
                "panel": None,
                "kind": "PAGE",
            },
            "page_id": str(page.id),
            "plate_region": None,
            "operations": [],
            "panels": panels,
            "reading_order": "RTL",
            "brief": clean_text(notes or owner.brief, 8000, field="Brief"),
            "creator_notes": clean_text(notes, 8000, field="Creator notes") if notes else "",
        }
        previous = self.session.execute(
            select(RoughAttempt)
            .where(RoughAttempt.production_page_id == page.id)
            .order_by(RoughAttempt.attempt.desc())
            .limit(1)
        ).scalar_one_or_none()
        self.manga._record_dependencies(page, self.manga.page_body(page), profile)
        attempt = self.rough._create_attempt(
            owner,
            intent=intent,
            inputs=inputs,
            seed=None,
            width=int(backend.get("width", 1024)),
            height=int(backend.get("height", 1456)),
            workflow=COMPOSE_WORKFLOW,
            extra_execution={"provider_id": "continuum.compose"},
            parent=previous,
        )
        attempt.production_page_id = page.id
        attempt.continuity_state_id = self.manga.current_continuity(run.id).id
        attempt.profile_id = profile.id
        if page.state in {"READY", "STALE"}:
            page.state = "IN_REVIEW"
        self.session.flush()
        return attempt
