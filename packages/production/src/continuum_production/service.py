"""Rough production: artifacts, append-only attempts, review, continuity.

Rules enforced here, below every surface:

* **Attempts are append-only.** Requesting or regenerating creates the next
  numbered attempt with its own recipe; nothing is overwritten. Review only
  moves an attempt between its review states, and every decision is appended
  to the review history.
* **A technical pass is not a creative approval.** ``TECHNICAL_PASS`` says the
  workflow did its job. ``CREATIVE_APPROVE`` is a person accepting an image as
  the project's rough manga, and is only possible for a PRODUCTION artifact
  whose attempt a real model drew (an ARTWORK_CANDIDATE); ``FINAL_APPROVE``
  follows creative approval. A workflow test, a non-canon sample and a test
  render can pass technically and can never be approved as art.
* **One creative approval per artifact.** Approving an attempt supersedes the
  previous approval; its bytes stay.
* **The bundle is snapshotted.** Locator, region, role, character, outfit and
  aspect are copied into ``attempt_input``, so a removed catalog record never
  breaks the chain back to the source page - and regeneration still works.
* **The API only enqueues.** Rendering runs in the worker as a durable
  ``visual.rough_attempt`` job (see :mod:`continuum_production.render`).
"""

from __future__ import annotations

import uuid
from typing import Any

from continuum_core import NormalizedRegion, content_hash_bytes
from continuum_core.references import (
    CREATIVE_STATES,
    AttemptState,
    BundleRole,
    DerivativeKind,
    ProjectStanding,
    ReferenceClass,
    ReferenceOrigin,
    ReferenceUse,
    RenderOutput,
    ReviewDecision,
    RoughArtifactKind,
    RoughPurpose,
)
from continuum_db.models import (
    AttemptDerivative,
    AttemptInput,
    AttemptReview,
    GenerationRecipe,
    LibraryAsset,
    RoughArtifact,
    RoughAttempt,
)
from continuum_jobs import enqueue
from continuum_library import (
    CatalogConflictError,
    CatalogInputError,
    CatalogNotFoundError,
    CharacterLink,
    ReferenceCatalog,
    ReferenceSpec,
    StandingSpec,
    region_of,
)
from continuum_library.validation import clean_text, require_episode, require_project_key
from continuum_providers import Capability, DataClass, ProviderRegistry
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from continuum_production.recipe import (
    CHANGING,
    RECIPE_SCHEMA_VERSION,
    TEMPLATE_PACKAGE_VERSION,
    RoughIntentSpec,
    default_size,
    execution_document,
    recipe_hashes,
)

__all__ = [
    "DEFAULT_WORKFLOW",
    "ROUGH_JOB_TYPE",
    "RoughProduction",
    "allowed_decisions",
    "reference_provenance",
    "refusal",
]

ROUGH_JOB_TYPE = "visual.rough_attempt"
DEFAULT_WORKFLOW = "sketch.v1"
GENERATED_ROOT = "generated"


def _derived_seed(intent_hash: str, attempt_number: int) -> int:
    return int(content_hash_bytes(f"{intent_hash}:{attempt_number}".encode())[:8], 16) & 0x7FFFFFFF


def refusal(artifact: RoughArtifact, attempt: RoughAttempt, decision: ReviewDecision) -> str | None:
    """Why ``decision`` cannot be recorded for this attempt, or None if it can."""
    if attempt.state is AttemptState.QUEUED:
        return "That attempt has not been rendered yet."
    if decision in (ReviewDecision.CREATIVE_APPROVE, ReviewDecision.FINAL_APPROVE):
        if artifact.purpose is RoughPurpose.WORKFLOW_TEST:
            return (
                "This artifact is a workflow test: non-canon, never manga. Record a technical pass "
                "if the workflow did its job."
            )
        if artifact.purpose is RoughPurpose.NON_CANON_SAMPLE:
            return (
                "This artifact is a non-canon sample: it is judged for quality, never approved as "
                "project artwork. Record a technical pass or reject it."
            )
        if attempt.output_class is not RenderOutput.ARTWORK_CANDIDATE:
            return (
                f"Attempt {attempt.attempt} was drawn by a test renderer - a labelled diagram of "
                "its recipe, not artwork. Record a technical pass; creative approval needs an "
                "image from a real generation model."
            )
    if decision is ReviewDecision.TECHNICAL_PASS and attempt.state in (
        AttemptState.TECHNICAL_PASS,
        *CREATIVE_STATES,
    ):
        return "That attempt already passed technically."
    if decision is ReviewDecision.CREATIVE_APPROVE and attempt.state in CREATIVE_STATES:
        return "That attempt is already creatively approved."
    if decision is ReviewDecision.FINAL_APPROVE:
        if attempt.state is AttemptState.FINAL_APPROVED:
            return "That attempt is already final."
        if attempt.state is not AttemptState.CREATIVE_APPROVED:
            return "Only a creatively approved attempt can be approved as final."
    if decision is ReviewDecision.REJECT and attempt.state is AttemptState.REJECTED:
        return "That attempt is already rejected."
    return None


def allowed_decisions(artifact: RoughArtifact, attempt: RoughAttempt) -> list[ReviewDecision]:
    """The decisions a reviewer may record for this attempt now, in display order."""
    return [d for d in ReviewDecision if refusal(artifact, attempt, d) is None]


def reference_provenance(item: Any, asset: Any = None) -> dict[str, Any]:
    """A reference's provenance as it stood when it was chosen, for the bundle snapshot."""
    provenance = dict(item.provenance or {})
    return {
        "reference_id": str(item.id),
        "origin": item.origin.value,
        "reference_class": item.reference_class.value,
        "collection": item.collection,
        "creator_handle": item.creator_handle,
        "source_url": item.source_url,
        "rights_status": item.rights_status.value,
        "training_eligibility": item.training_eligibility.value,
        "asset_content_hash": getattr(asset, "content_hash", None),
        "locator": item.locator,
        "catalog": provenance,
    }


def _region_dict(item: Any) -> dict[str, float] | None:
    region = region_of(item)
    return region.as_dict() if region else None


class RoughProduction:
    """Production operations inside one database session (the caller commits)."""

    def __init__(
        self,
        session: Session,
        catalog: ReferenceCatalog,
        *,
        providers: ProviderRegistry | None = None,
    ) -> None:
        self.session = session
        self.catalog = catalog
        self.providers = providers

    # =====================================================================
    # Artifacts
    # =====================================================================
    def create_artifact(
        self,
        project_key: str,
        episode: str,
        page: int,
        *,
        panel: int | None = None,
        chapter: int | None = None,
        title: str = "",
        panel_script_document: str | None = None,
        panel_script_version: str | None = None,
        brief: str = "",
        purpose: RoughPurpose = RoughPurpose.PRODUCTION,
    ) -> RoughArtifact:
        """The artifact for a page or panel - created once per purpose, then found again."""
        require_project_key(project_key)
        require_episode(episode)
        if page < 1 or (panel is not None and panel < 1) or (chapter is not None and chapter < 1):
            raise CatalogInputError("Chapters, pages and panels are numbered from 1.")
        kind = RoughArtifactKind.PANEL if panel is not None else RoughArtifactKind.PAGE
        existing = self._find_artifact(project_key, episode, page, panel, kind, purpose)
        if existing is not None:
            return existing
        artifact = RoughArtifact(
            project_key=project_key,
            episode=episode,
            chapter=chapter,
            page=page,
            panel=panel,
            kind=kind,
            purpose=purpose,
            title=clean_text(title, 300, field="Title"),
            panel_script_document=panel_script_document,
            panel_script_version=panel_script_version,
            brief=clean_text(brief, 8000, field="Brief"),
        )
        try:
            with self.session.begin_nested():
                self.session.add(artifact)
                self.session.flush()
        except IntegrityError:
            found = self._find_artifact(project_key, episode, page, panel, kind, purpose)
            assert found is not None
            return found
        return artifact

    def _find_artifact(
        self,
        project_key: str,
        episode: str,
        page: int,
        panel: int | None,
        kind: RoughArtifactKind,
        purpose: RoughPurpose,
    ) -> RoughArtifact | None:
        return self.session.execute(
            select(RoughArtifact).where(
                RoughArtifact.project_key == project_key,
                RoughArtifact.purpose == purpose,
                RoughArtifact.episode == episode,
                RoughArtifact.page == page,
                RoughArtifact.panel.is_(None) if panel is None else RoughArtifact.panel == panel,
                RoughArtifact.kind == kind,
            )
        ).scalar_one_or_none()

    def artifact(self, artifact_id: uuid.UUID) -> RoughArtifact:
        found = self.session.get(RoughArtifact, artifact_id)
        if found is None:
            raise CatalogNotFoundError("That rough artifact does not exist.")
        return found

    def artifacts(
        self,
        project_key: str,
        *,
        episode: str | None = None,
        purpose: RoughPurpose | None = None,
        include_stages: bool = False,
    ) -> list[RoughArtifact]:
        """A project's rough pages and panels.

        Construction stages of a panel (layered construction) are parts of one
        panel, not panels of their own: they are left out unless asked for.
        """
        require_project_key(project_key)
        query = select(RoughArtifact).where(RoughArtifact.project_key == project_key)
        if not include_stages:
            query = query.where(RoughArtifact.stage.is_(None))
        if episode is not None:
            query = query.where(RoughArtifact.episode == episode)
        if purpose is not None:
            query = query.where(RoughArtifact.purpose == purpose)
        return list(
            self.session.execute(
                query.order_by(
                    RoughArtifact.purpose,
                    RoughArtifact.episode,
                    RoughArtifact.page,
                    RoughArtifact.panel.nulls_first(),
                )
            ).scalars()
        )

    # =====================================================================
    # Attempts
    # =====================================================================
    def request_attempt(
        self,
        artifact_id: uuid.UUID,
        spec: RoughIntentSpec,
        *,
        workflow: str = DEFAULT_WORKFLOW,
    ) -> RoughAttempt:
        """Record the recipe and bundle, create the next attempt, enqueue its render."""
        artifact = self._lock_artifact(artifact_id)
        spec.validate()
        inputs = self._snapshot_bundle(spec)
        intent = self._intent(artifact, spec, inputs)
        width, height = default_size(artifact.kind)
        return self._create_attempt(
            artifact,
            intent=intent,
            inputs=inputs,
            seed=spec.seed,
            width=spec.width or width,
            height=spec.height or height,
            workflow=workflow,
            extra_execution=spec.extra_execution,
            parent=None,
        )

    def regenerate(
        self, attempt_id: uuid.UUID, *, seed: int | None = None, notes: str = ""
    ) -> RoughAttempt:
        """The same intent and bundle again, with a new seed, as a new attempt."""
        previous = self.attempt(attempt_id)
        if previous.state is AttemptState.QUEUED:
            raise CatalogConflictError("That attempt has not been rendered yet.")
        if seed is not None and not 0 <= seed < 2**31:
            raise CatalogInputError("A seed is a non-negative 31-bit integer.")
        artifact = self._lock_artifact(previous.artifact_id)
        recipe = self.recipe(previous.recipe_id)
        self.session.add(
            AttemptReview(
                attempt_id=previous.id,
                decision=ReviewDecision.REGENERATE,
                notes=clean_text(notes, 4000, field="Notes"),
            )
        )
        if previous.state is AttemptState.GENERATED:
            previous.state = AttemptState.REJECTED
        inputs = [
            {
                "position": row.position,
                "role": row.role,
                "reference_id": row.reference_id,
                "locator": row.locator,
                "unit_index": row.unit_index,
                "region": _region_dict(row),
                "character_id": row.character_id,
                "outfit_id": row.outfit_id,
                "aspect": row.aspect,
                "label": row.label,
                "provenance": row.provenance,
            }
            for row in self.inputs(previous.id)
        ]
        execution = recipe.execution
        return self._create_attempt(
            artifact,
            intent=recipe.intent,
            inputs=inputs,
            seed=seed,
            width=int(execution["width"]),
            height=int(execution["height"]),
            workflow=str(execution["workflow"]),
            extra_execution={
                key: execution[key]
                for key in (
                    "strength",
                    "inpaint",
                    "control_inputs",
                    "compositing",
                    "post_processing",
                )
                if execution.get(key) not in (None, {}, [])
            },
            parent=previous,
        )

    def review(
        self,
        attempt_id: uuid.UUID,
        decision: ReviewDecision,
        *,
        notes: str = "",
        seed: int | None = None,
    ) -> tuple[AttemptReview | None, RoughAttempt | None]:
        """Record a review decision. Returns (review, new attempt if regenerated)."""
        if decision is ReviewDecision.REGENERATE:
            return None, self.regenerate(attempt_id, seed=seed, notes=notes)
        attempt = self.attempt(attempt_id)
        artifact = self._lock_artifact(attempt.artifact_id)
        reason = refusal(artifact, attempt, decision)
        if reason is not None:
            if attempt.state is AttemptState.QUEUED or "already" in reason:
                raise CatalogConflictError(reason)
            raise CatalogInputError(reason)
        if decision in (ReviewDecision.CREATIVE_APPROVE, ReviewDecision.FINAL_APPROVE):
            replaced = (
                CREATIVE_STATES
                if decision is ReviewDecision.CREATIVE_APPROVE
                else frozenset({AttemptState.FINAL_APPROVED})
            )
            for other in self.session.execute(
                select(RoughAttempt).where(
                    RoughAttempt.artifact_id == attempt.artifact_id,
                    RoughAttempt.state.in_(replaced),
                    RoughAttempt.id != attempt.id,
                )
            ).scalars():
                other.state = AttemptState.SUPERSEDED
            attempt.state = (
                AttemptState.CREATIVE_APPROVED
                if decision is ReviewDecision.CREATIVE_APPROVE
                else AttemptState.FINAL_APPROVED
            )
        elif decision is ReviewDecision.TECHNICAL_PASS:
            attempt.state = AttemptState.TECHNICAL_PASS
        else:  # REJECT
            attempt.state = AttemptState.REJECTED
        review = AttemptReview(
            attempt_id=attempt.id, decision=decision, notes=clean_text(notes, 4000, field="Notes")
        )
        self.session.add(review)
        self.session.flush()
        return review, None

    def attempt(self, attempt_id: uuid.UUID) -> RoughAttempt:
        found = self.session.get(RoughAttempt, attempt_id)
        if found is None:
            raise CatalogNotFoundError("That attempt does not exist.")
        return found

    def attempts(self, artifact_id: uuid.UUID) -> list[RoughAttempt]:
        return list(
            self.session.execute(
                select(RoughAttempt)
                .where(RoughAttempt.artifact_id == artifact_id)
                .order_by(RoughAttempt.attempt.desc())
            ).scalars()
        )

    def recipe(self, recipe_id: uuid.UUID) -> GenerationRecipe:
        found = self.session.get(GenerationRecipe, recipe_id)
        if found is None:  # pragma: no cover - FK guarantees it
            raise CatalogNotFoundError("That recipe does not exist.")
        return found

    def inputs(self, attempt_id: uuid.UUID) -> list[AttemptInput]:
        return list(
            self.session.execute(
                select(AttemptInput)
                .where(AttemptInput.attempt_id == attempt_id)
                .order_by(AttemptInput.position)
            ).scalars()
        )

    def derivatives(self, attempt_id: uuid.UUID) -> list[AttemptDerivative]:
        return list(
            self.session.execute(
                select(AttemptDerivative)
                .where(AttemptDerivative.attempt_id == attempt_id)
                .order_by(AttemptDerivative.kind)
            ).scalars()
        )

    def reviews(self, attempt_id: uuid.UUID) -> list[AttemptReview]:
        return list(
            self.session.execute(
                select(AttemptReview)
                .where(AttemptReview.attempt_id == attempt_id)
                .order_by(AttemptReview.decided_at, AttemptReview.id)
            ).scalars()
        )

    def derivative_bytes(self, attempt_id: uuid.UUID, kind: DerivativeKind) -> tuple[bytes, str]:
        self.attempt(attempt_id)
        row = next((d for d in self.derivatives(attempt_id) if d.kind is kind), None)
        if row is None:
            raise CatalogNotFoundError(f"This attempt has no {kind.value.lower()} image.")
        derived = self.catalog.derived
        if derived is None or not derived.has(GENERATED_ROOT, row.content_hash):
            raise CatalogNotFoundError("The attempt's image is not reachable.")
        return derived.get_bytes(GENERATED_ROOT, row.content_hash), row.mime

    # =====================================================================
    # Continuity
    # =====================================================================
    def promote_to_continuity(
        self,
        attempt_id: uuid.UUID,
        *,
        label: str = "",
        characters: tuple[CharacterLink, ...] = (),
        notes: str = "",
    ) -> Any:
        """An approved attempt becomes a CONTINUITY reference for later attempts."""
        attempt = self.attempt(attempt_id)
        artifact = self.artifact(attempt.artifact_id)
        if (
            attempt.state not in CREATIVE_STATES
            or attempt.content_hash is None
            or artifact.purpose is not RoughPurpose.PRODUCTION
        ):
            raise CatalogInputError(
                "Only a creatively approved production attempt becomes a continuity reference; "
                "a technical pass or a test render never does."
            )
        recipe = self.recipe(attempt.recipe_id)
        where = f"{artifact.episode} p{artifact.page}" + (
            f" panel {artifact.panel}" if artifact.panel else ""
        )
        return self.catalog.add_generated(
            attempt.content_hash,
            ReferenceSpec(
                reference_class=ReferenceClass.CONTINUITY,
                origin=ReferenceOrigin.PROJECT_APPROVED,
                label=label or f"{where} - attempt {attempt.attempt}",
                notes=notes,
                uses=(ReferenceUse.CONTINUITY,),
                characters=characters,
                standings=(StandingSpec(artifact.project_key, ProjectStanding.USEFUL),),
            ),
            {
                "kind": "rough_attempt",
                "attempt_id": str(attempt.id),
                "artifact_id": str(artifact.id),
                "attempt": attempt.attempt,
                "intent_hash": recipe.intent_hash,
                "execution_hash": recipe.execution_hash,
            },
        )

    # =====================================================================
    # Internals
    # =====================================================================
    def _lock_artifact(self, artifact_id: uuid.UUID) -> RoughArtifact:
        found = self.session.execute(
            select(RoughArtifact).where(RoughArtifact.id == artifact_id).with_for_update()
        ).scalar_one_or_none()
        if found is None:
            raise CatalogNotFoundError("That rough artifact does not exist.")
        return found

    def _snapshot_bundle(self, spec: RoughIntentSpec) -> list[dict[str, Any]]:
        catalog = self.catalog
        rows: list[dict[str, Any]] = []
        for position, entry in enumerate(spec.bundle):
            item = catalog.reference(entry.reference_id)
            if item.locator.startswith("pdf:"):
                raise CatalogInputError("PDF pages cannot be used in a rough attempt yet.")
            if entry.character_id is not None:
                catalog.character(entry.character_id)
            if entry.outfit_id is not None:
                outfit = catalog.outfit(entry.outfit_id)
                if outfit.character_id != entry.character_id:
                    raise CatalogInputError("That outfit belongs to a different character.")
            region = entry.region.as_dict() if entry.region else _region_dict(item)
            asset = self.session.get(LibraryAsset, item.asset_id)
            rows.append(
                {
                    "position": position,
                    "role": entry.role,
                    "reference_id": item.id,
                    "locator": item.locator,
                    "unit_index": item.unit_index,
                    "region": region,
                    "character_id": entry.character_id,
                    "outfit_id": entry.outfit_id,
                    "aspect": entry.aspect,
                    "label": clean_text(entry.label or item.label, 300, field="Label"),
                    "provenance": reference_provenance(item, asset),
                }
            )
        return rows

    def _intent(
        self, artifact: RoughArtifact, spec: RoughIntentSpec, inputs: list[dict[str, Any]]
    ) -> dict[str, Any]:
        catalog = self.catalog
        characters = []
        for direction in spec.characters:
            character = catalog.character(direction.character_id)
            outfit = catalog.outfit(direction.outfit_id) if direction.outfit_id else None
            if outfit is not None and outfit.character_id != character.id:
                raise CatalogInputError("That outfit belongs to a different character.")
            mode = (
                catalog.visual_mode(direction.visual_mode_id) if direction.visual_mode_id else None
            )
            characters.append(
                {
                    "character_id": str(character.id),
                    "name": character.display_name,
                    "outfit_id": str(outfit.id) if outfit else None,
                    "outfit_name": outfit.name if outfit else None,
                    "acting_direction": clean_text(
                        direction.acting_direction, 2000, field="Acting direction"
                    ),
                    "visual_mode_id": str(mode.id) if mode else None,
                    "visual_mode_name": mode.name if mode else None,
                }
            )
        modes: list[dict[str, Any]] = []
        for mode_id in spec.visual_mode_ids:
            mode = catalog.visual_mode(mode_id)
            modes.append(
                {
                    "visual_mode_id": str(mode.id),
                    "name": mode.name,
                    "category": mode.category.value,
                    "source": "chosen",
                }
            )
        for assignment in catalog.modes_in_effect(
            artifact.project_key, artifact.episode, artifact.page, artifact.panel
        ):
            mode = catalog.visual_mode(assignment.visual_mode_id)
            modes.append(
                {
                    "visual_mode_id": str(mode.id),
                    "name": mode.name,
                    "category": mode.category.value,
                    "source": "project_assignment",
                    "assignment_id": str(assignment.id),
                    "scope": assignment.scope.value,
                    "trigger": assignment.trigger.value,
                    "character_id": str(assignment.character_id)
                    if assignment.character_id
                    else None,
                }
            )
        operations = []
        for op in spec.operations:
            if op.character_id is not None:
                catalog.character(op.character_id)
            if (
                op.outfit_id is not None
                and catalog.outfit(op.outfit_id).character_id != op.character_id
            ):
                raise CatalogInputError("That outfit belongs to a different character.")
            operations.append(
                {
                    "kind": op.kind.value,
                    "region": op.region.as_dict(),
                    "label": clean_text(op.label, 200, field="Operation label"),
                    "character_id": str(op.character_id) if op.character_id else None,
                    "outfit_id": str(op.outfit_id) if op.outfit_id else None,
                    "reference_position": op.reference_position,
                    "text": clean_text(op.text, 1000, field="Text"),
                    "notes": clean_text(op.notes, 2000, field="Notes"),
                }
            )
        placements = []
        for placement in spec.placements:
            if placement.character_id is not None:
                catalog.character(placement.character_id)
            placements.append(
                {
                    "region": placement.region.as_dict(),
                    "label": clean_text(placement.label, 200, field="Placement label"),
                    "character_id": str(placement.character_id) if placement.character_id else None,
                }
            )
        plates = [row["position"] for row in inputs if row["role"] is BundleRole.SOURCE_PLATE]
        return {
            "schema": RECIPE_SCHEMA_VERSION,
            "mode": spec.mode.value,
            "target": {
                "project_key": artifact.project_key,
                "episode": artifact.episode,
                "chapter": artifact.chapter,
                "page": artifact.page,
                "panel": artifact.panel,
                "kind": artifact.kind.value,
            },
            "panel_script": {
                "document": artifact.panel_script_document,
                "version": artifact.panel_script_version,
            },
            "brief": clean_text(spec.brief or artifact.brief, 8000, field="Brief"),
            "characters": characters,
            "visual_modes": modes,
            "bundle": [
                {
                    "position": row["position"],
                    "role": row["role"].value,
                    "reference_id": str(row["reference_id"]),
                    "locator": row["locator"],
                    "region": row["region"],
                    "character_id": str(row["character_id"]) if row["character_id"] else None,
                    "outfit_id": str(row["outfit_id"]) if row["outfit_id"] else None,
                    "aspect": row["aspect"].value if row["aspect"] else None,
                    "label": row["label"],
                }
                for row in inputs
            ],
            "source_plates": plates,
            "plate_region": spec.plate_region.as_dict() if spec.plate_region else None,
            "operations": operations,
            "protected_regions": [op["region"] for op in operations if op["kind"] == "PRESERVE"],
            "placements": placements,
        }

    def _create_attempt(
        self,
        artifact: RoughArtifact,
        *,
        intent: dict[str, Any],
        inputs: list[dict[str, Any]],
        seed: int | None,
        width: int,
        height: int,
        workflow: str,
        extra_execution: dict[str, Any],
        parent: RoughAttempt | None,
    ) -> RoughAttempt:
        number = (
            int(
                self.session.execute(
                    select(func.coalesce(func.max(RoughAttempt.attempt), 0)).where(
                        RoughAttempt.artifact_id == artifact.id
                    )
                ).scalar_one()
            )
            + 1
        )
        intent_hash, _ = recipe_hashes(intent, {})
        chosen_seed = seed if seed is not None else _derived_seed(intent_hash, number)
        data_class = DataClass.SOURCE_EXCERPT if inputs else DataClass.PROJECT_TEXT
        requested = None
        if self.providers is not None:
            decision = self.providers.evaluate(Capability.ROUGH_RENDER, data_class)
            requested = decision.provider_id if decision.permitted else None
        plate_region = intent.get("plate_region")
        has_mask = any(op["kind"] in {k.value for k in CHANGING} for op in intent["operations"])
        execution = execution_document(
            workflow=workflow,
            requested_provider=requested,
            seed=chosen_seed,
            width=width,
            height=height,
            plate_region=NormalizedRegion(**plate_region) if plate_region else None,
            has_mask=has_mask,
            extra=extra_execution,
        )
        intent_hash, execution_hash = recipe_hashes(intent, execution)
        recipe = (
            self.session.execute(
                select(GenerationRecipe).where(
                    GenerationRecipe.intent_hash == intent_hash,
                    GenerationRecipe.execution_hash == execution_hash,
                )
            )
            .scalars()
            .first()
        )
        if recipe is None:
            recipe = GenerationRecipe(
                mode=intent["mode"],
                recipe_schema_version=RECIPE_SCHEMA_VERSION,
                template_package_version=TEMPLATE_PACKAGE_VERSION,
                intent=intent,
                execution=execution,
                intent_hash=intent_hash,
                execution_hash=execution_hash,
            )
            self.session.add(recipe)
            self.session.flush()
        attempt = RoughAttempt(
            artifact_id=artifact.id,
            attempt=number,
            recipe_id=recipe.id,
            parent_attempt_id=parent.id if parent else None,
            state=AttemptState.QUEUED,
        )
        self.session.add(attempt)
        self.session.flush()
        for row in inputs:
            region = row["region"] or {}
            self.session.add(
                AttemptInput(
                    attempt_id=attempt.id,
                    position=row["position"],
                    role=row["role"],
                    reference_id=row["reference_id"],
                    locator=row["locator"],
                    unit_index=row["unit_index"],
                    region_x=region.get("x"),
                    region_y=region.get("y"),
                    region_width=region.get("width"),
                    region_height=region.get("height"),
                    character_id=row["character_id"],
                    outfit_id=row["outfit_id"],
                    aspect=row["aspect"],
                    label=row["label"],
                    provenance=row.get("provenance") or {},
                )
            )
        job, _created = enqueue(
            self.session,
            ROUGH_JOB_TYPE,
            payload={"attempt_id": str(attempt.id)},
            resource_class="cpu",
            max_attempts=3,
            recipe_version=TEMPLATE_PACKAGE_VERSION,
        )
        attempt.job_id = job.id
        self.session.flush()
        return attempt
