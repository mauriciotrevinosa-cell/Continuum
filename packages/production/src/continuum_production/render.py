"""Rendering one rough attempt - the worker side of the pipeline.

Called by the ``visual.rough_attempt`` job handler inside the job's session.
Every effect - derived bytes under ``generated/`` - is content-addressed and
attempt state is committed with the durable job step. Production pages use the
PAGE_RENDER boundary while legacy rough attempts continue through ROUGH_RENDER.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from continuum_core import (
    BlockedReason,
    ContinuumError,
    ErrorCategory,
    NormalizedRegion,
    ProviderUnavailableError,
    parse_locator,
)
from continuum_core.references import (
    AssetMedium,
    AssetOrigin,
    AttemptState,
    BundleRole,
    DerivativeKind,
    RenderOutput,
)
from continuum_db.models import (
    AttemptDerivative,
    AttemptInput,
    CharacterProfile,
    GenerationRecipe,
    LibraryAsset,
    RoughArtifact,
    RoughAttempt,
)
from continuum_imaging import crop_region, mask_from_regions, probe
from continuum_library import CatalogNotFoundError, ReferenceCatalog, region_of
from continuum_providers import (
    Capability,
    DataClass,
    ProviderRegistry,
    RoughEditOperation,
    RoughPlacement,
    RoughReference,
    RoughRenderRequest,
)
from continuum_storage import SourceChangedError, SourceUnavailableError
from sqlalchemy import select
from sqlalchemy.orm import Session

from continuum_production.layered import COMPOSE_SCHEMA, STAGE_SCHEMA
from continuum_production.recipe import CHANGING

__all__ = ["SourceAssetMissingError", "render_attempt"]

GENERATED_ROOT = "generated"


class SourceAssetMissingError(ContinuumError):
    """A bundle member's bytes cannot be read; the attempt waits, it does not fail."""

    code = "production.source_missing"
    category = ErrorCategory.PERMANENT_CONFIG


def render_attempt(
    session: Session,
    attempt_id: uuid.UUID,
    *,
    catalog: ReferenceCatalog,
    providers: ProviderRegistry,
) -> dict[str, Any]:
    attempt = session.execute(
        select(RoughAttempt).where(RoughAttempt.id == attempt_id)
    ).scalar_one_or_none()
    if attempt is None:
        raise CatalogNotFoundError("That attempt does not exist.")
    if attempt.state is not AttemptState.QUEUED:
        return {"attempt_id": str(attempt.id), "content_hash": attempt.content_hash, "rerun": True}
    if catalog.derived is None:
        raise SourceAssetMissingError("Writable storage is not configured for rendering.")

    recipe = session.get(GenerationRecipe, attempt.recipe_id)
    artifact = session.get(RoughArtifact, attempt.artifact_id)
    assert recipe is not None and artifact is not None
    schema = (recipe.intent or {}).get("schema")
    if schema == STAGE_SCHEMA:
        return _render_stage(session, attempt, recipe, catalog=catalog, providers=providers)
    if schema == COMPOSE_SCHEMA:
        return _compose_page(session, attempt, recipe, catalog=catalog)
    if attempt.production_page_id is not None:
        return _render_page(session, attempt, recipe, catalog=catalog, providers=providers)
    intent, execution = recipe.intent, recipe.execution
    inputs = list(
        session.execute(
            select(AttemptInput)
            .where(AttemptInput.attempt_id == attempt.id)
            .order_by(AttemptInput.position)
        ).scalars()
    )

    data_class = DataClass.SOURCE_EXCERPT if inputs else DataClass.PROJECT_TEXT
    provider = providers.resolve(Capability.ROUGH_RENDER, data_class)

    loaded = {row.position: _input_bytes(session, catalog, row) for row in inputs}
    plate_row = next((row for row in inputs if row.role is BundleRole.SOURCE_PLATE), None)
    raw_crop = intent.get("plate_region")
    plate_region = NormalizedRegion(**raw_crop) if raw_crop else None
    if plate_row is not None and plate_region is None:
        plate_region = region_of(plate_row)

    operations = tuple(
        RoughEditOperation(
            kind=op["kind"],
            region=NormalizedRegion(**op["region"]),
            label=_operation_label(op, intent),
        )
        for op in intent.get("operations") or []
    )
    placements = tuple(
        RoughPlacement(
            region=NormalizedRegion(**placement["region"]),
            label=_placement_label(placement, intent),
        )
        for placement in intent.get("placements") or []
    )

    derivatives: list[tuple[DerivativeKind, bytes, dict[str, Any]]] = []
    plate_bytes: bytes | None = None
    mask_bytes: bytes | None = None
    if plate_row is not None:
        plate_bytes = loaded[plate_row.position]
        crop = crop_region(plate_bytes, plate_region)
        derivatives.append(
            (
                DerivativeKind.SOURCE_CROP,
                crop.data,
                {"input_position": plate_row.position, "locator": plate_row.locator},
            )
        )
        changing = [op.region for op in operations if op.kind in {kind.value for kind in CHANGING}]
        if changing:
            mask = mask_from_regions(crop.width, crop.height, changing)
            mask_bytes = mask.data
            derivatives.append(
                (
                    DerivativeKind.MASK,
                    mask.data,
                    {"operations": [op.kind for op in operations], "coordinates": "plate_crop"},
                )
            )

    target = intent["target"]
    where = f"{target['episode']} p{target['page']}" + (
        f" panel {target['panel']}" if target.get("panel") else ""
    )
    result = provider.render_rough(  # type: ignore[attr-defined]
        RoughRenderRequest(
            data_class=data_class,
            mode=intent["mode"],
            width=int(execution["width"]),
            height=int(execution["height"]),
            seed=int(execution["seed"]),
            title=f"{target['project_key']} {where}",
            workflow=str(execution["workflow"]),
            lines=tuple(_lines(intent)),
            plate=plate_bytes,
            plate_region=plate_region,
            mask=mask_bytes,
            operations=operations,
            placements=placements,
            references=tuple(
                RoughReference(
                    role=row.role.value,
                    label=row.label or row.role.value.lower(),
                    data=loaded[row.position],
                    region=region_of(row),
                )
                for row in inputs
                if row.role is not BundleRole.SOURCE_PLATE
            ),
            options={
                key: execution.get(key)
                for key in ("strength", "inpaint", "control_inputs", "compositing")
            },
        )
    )
    info = probe(result.image)
    derivatives.append(
        (
            DerivativeKind.OUTPUT,
            result.image,
            {
                "rendered_with": {
                    "provider_id": result.provider_id,
                    "model_ref": result.model_ref,
                    "version": result.version,
                    "workflow": result.workflow,
                },
                "requested_provider": execution.get("requested_provider"),
            },
        )
    )

    output_hash = ""
    for kind, data, detail in derivatives:
        image = probe(data)
        stored = catalog.store_bytes(
            data, root_key=GENERATED_ROOT, medium=AssetMedium.IMAGE, origin=AssetOrigin.GENERATED
        )
        exists = session.execute(
            select(AttemptDerivative.id).where(
                AttemptDerivative.attempt_id == attempt.id,
                AttemptDerivative.kind == kind,
                AttemptDerivative.content_hash == stored.content_hash,
            )
        ).scalar_one_or_none()
        if exists is None:
            session.add(
                AttemptDerivative(
                    attempt_id=attempt.id,
                    kind=kind,
                    content_hash=stored.content_hash,
                    mime=image.mime,
                    width=image.width,
                    height=image.height,
                    detail=detail,
                )
            )
        if kind is DerivativeKind.OUTPUT:
            output_hash = stored.content_hash

    attempt.state = AttemptState.GENERATED
    descriptor = getattr(provider, "descriptor", None)
    attempt.output_class = RenderOutput(
        getattr(descriptor, "rough_output", RenderOutput.TEST_RENDER)
    )
    attempt.artwork_provenance = {
        "backend": result.provider_id,
        "model": {
            "name": result.model_ref,
            "version": result.version,
            "license": getattr(descriptor, "license_note", ""),
        },
        "workflow": {"id": result.workflow},
        "settings": {
            key: execution.get(key)
            for key in ("seed", "width", "height", "strength", "inpaint", "control_inputs")
        },
    }
    attempt.content_hash = output_hash
    attempt.mime = info.mime
    attempt.width = info.width
    attempt.height = info.height
    attempt.generated_at = dt.datetime.now(dt.UTC)
    session.flush()
    return {
        "attempt_id": str(attempt.id),
        "content_hash": output_hash,
        "provider_id": result.provider_id,
        "rerun": False,
    }


def _input_bytes(session: Session, catalog: ReferenceCatalog, row: AttemptInput) -> bytes:
    """A bundle member's unit bytes, from its snapshotted locator."""
    locator = row.locator
    digest = locator.split(":sha256:", 1)[1][:64] if ":sha256:" in locator else ""
    if not locator.startswith("gen:"):
        parse_locator(locator)
    asset = session.execute(
        select(LibraryAsset).where(LibraryAsset.content_hash == digest)
    ).scalar_one_or_none()
    try:
        if asset is None:
            raise CatalogNotFoundError("The reference's bytes are not recorded.")
        return catalog.asset_bytes(asset, locator)
    except (CatalogNotFoundError, SourceChangedError, SourceUnavailableError) as exc:
        raise SourceAssetMissingError(
            f"A {row.role.value.lower().replace('_', ' ')} reference is not reachable.",
            technical_detail=f"position={row.position} locator={locator} ({exc.code})",
            remediation=(
                "Connect the Source Vault and rescan the Library, or replace the reference "
                "and regenerate. The attempt keeps waiting; nothing was lost."
            ),
            blocked_reason=BlockedReason.MISSING_SOURCE_ASSET.value,
            input_position=row.position,
        ) from None


def _operation_label(op: dict[str, Any], intent: dict[str, Any]) -> str:
    parts = [op.get("label") or ""]
    names = {
        character["character_id"]: character["name"] for character in intent.get("characters") or []
    }
    if op.get("character_id") in names:
        parts.append(names[op["character_id"]])
    if op.get("text"):
        parts.append(f'"{op["text"]}"')
    return " ".join(part for part in parts if part).strip()


def _placement_label(placement: dict[str, Any], intent: dict[str, Any]) -> str:
    names = {
        character["character_id"]: character["name"] for character in intent.get("characters") or []
    }
    name = names.get(placement.get("character_id") or "", "")
    return " ".join(part for part in (placement.get("label") or "", name) if part).strip()


def _lines(intent: dict[str, Any]) -> list[str]:
    lines = []
    for character in intent.get("characters") or []:
        text = character["name"]
        if character.get("outfit_name"):
            text += f" in {character['outfit_name']}"
        if character.get("visual_mode_name"):
            text += f" [{character['visual_mode_name']}]"
        lines.append(text)
    modes = sorted({mode["name"] for mode in intent.get("visual_modes") or []})
    if modes:
        lines.append("modes: " + ", ".join(modes))
    return lines[:4]


def _store_derivative(
    session: Session,
    catalog: ReferenceCatalog,
    attempt: RoughAttempt,
    kind: DerivativeKind,
    data: bytes,
    detail: dict[str, Any],
) -> str:
    image = probe(data)
    stored = catalog.store_bytes(
        data, root_key=GENERATED_ROOT, medium=AssetMedium.IMAGE, origin=AssetOrigin.GENERATED
    )
    exists = session.execute(
        select(AttemptDerivative.id).where(
            AttemptDerivative.attempt_id == attempt.id,
            AttemptDerivative.kind == kind,
            AttemptDerivative.content_hash == stored.content_hash,
        )
    ).scalar_one_or_none()
    if exists is None:
        session.add(
            AttemptDerivative(
                attempt_id=attempt.id,
                kind=kind,
                content_hash=stored.content_hash,
                mime=image.mime,
                width=image.width,
                height=image.height,
                detail=detail,
            )
        )
    return stored.content_hash


def _render_page(
    session: Session,
    attempt: RoughAttempt,
    recipe: GenerationRecipe,
    *,
    catalog: ReferenceCatalog,
    providers: ProviderRegistry,
) -> dict[str, Any]:
    """A production page: one composition master and its two sibling finishes."""
    from continuum_providers.artwork import (
        ArtworkReference,
        PageRenderProvider,
        PageRenderRequest,
        capability_gaps,
        check_result,
    )

    execution = recipe.execution
    bundle = recipe.intent["page_bundle"]
    provider_id = str(execution.get("provider_id") or "fake.deterministic-page")
    provider = providers.get(provider_id)
    if not isinstance(provider, PageRenderProvider):
        raise ProviderUnavailableError(
            f"{provider_id} cannot render manga pages.",
            remediation="Choose a PAGE_RENDER backend in the production profile.",
            blocked_reason=BlockedReason.MISSING_PROVIDER.value,
        )
    names = {
        character["character_id"]: character["name"] for character in bundle.get("characters") or []
    }
    inputs = list(
        session.execute(
            select(AttemptInput)
            .where(AttemptInput.attempt_id == attempt.id)
            .order_by(AttemptInput.position)
        ).scalars()
    )
    references = [
        ArtworkReference(
            role=row.role.value,
            reference_id=str(row.reference_id) if row.reference_id else row.locator,
            data=_input_bytes(session, catalog, row),
            character=names.get(str(row.character_id)) if row.character_id else None,
            provenance=dict(row.provenance or {}),
        )
        for row in inputs
    ]
    derived = catalog.derived
    assert derived is not None
    for approved in (bundle.get("continuity") or {}).get("approved_pages") or []:
        digest = approved["master_sha256"]
        if derived.has(GENERATED_ROOT, digest):
            references.append(
                ArtworkReference(
                    role="CONTINUITY",
                    reference_id=f"page:{approved['sequence']}:{digest}",
                    data=derived.get_bytes(GENERATED_ROOT, digest),
                    teaches=("identity", "wardrobe", "setting", "lighting"),
                    provenance={"attempt_id": approved["attempt_id"]},
                )
            )
    request = PageRenderRequest(
        page_key=bundle["page"]["page_key"],
        width=int(execution["width"]),
        height=int(execution["height"]),
        seed=int(execution["seed"]),
        page=bundle["page"],
        plan=bundle.get("plan") or {},
        continuity=bundle.get("continuity") or {},
        references=tuple(references),
        settings={
            **(execution.get("backend_settings") or {}),
            "workflow": execution["workflow"],
            "brief": str(recipe.intent.get("brief") or ""),
            "creator_notes": str(recipe.intent.get("creator_notes") or ""),
            "character_context": {
                character["name"]: {
                    "source_label": str(character.get("source_label") or ""),
                    "origin": str(character.get("origin") or ""),
                }
                for character in bundle.get("characters") or []
            },
        },
    )
    gaps = capability_gaps(provider.capabilities, request)
    if gaps:
        raise ProviderUnavailableError(
            f"{provider_id} cannot render this page: " + "; ".join(gaps),
            remediation="Use a backend whose capabilities cover the page, or change the profile.",
            blocked_reason=BlockedReason.MISSING_PROVIDER.value,
        )
    result = provider.render_page(request)
    problems = check_result(result)
    if problems:
        raise ProviderUnavailableError(
            "The backend's result was refused: " + "; ".join(problems),
            remediation="Fix the backend or its workflow so results are reproducible siblings.",
            blocked_reason=BlockedReason.MISSING_MODEL.value,
        )
    master = _store_derivative(
        session, catalog, attempt, DerivativeKind.COMPOSITION_MASTER, result.master.data, {}
    )
    detail = {"master_sha256": master, "provider_id": result.provider_id}
    _store_derivative(session, catalog, attempt, DerivativeKind.OUTPUT, result.master.data, detail)
    _store_derivative(session, catalog, attempt, DerivativeKind.BW_FINISH, result.bw.data, detail)
    _store_derivative(
        session, catalog, attempt, DerivativeKind.COLOR_FINISH, result.color.data, detail
    )
    attempt.artwork_provenance = {
        **result.provenance,
        "backend": result.backend.value,
        "provider_id": result.provider_id,
        "master_sha256": master,
        "references": [
            {
                "role": reference.role,
                "reference_id": reference.reference_id,
                "character": reference.character,
            }
            for reference in references
        ],
    }
    attempt.output_class = RenderOutput(result.output)
    attempt.state = AttemptState.GENERATED
    attempt.content_hash = master
    attempt.mime = result.master.mime
    attempt.width = result.master.width
    attempt.height = result.master.height
    attempt.generated_at = dt.datetime.now(dt.UTC)
    session.flush()
    return {"attempt_id": str(attempt.id), "content_hash": master, "provider_id": provider_id}


def _render_stage(
    session: Session,
    attempt: RoughAttempt,
    recipe: GenerationRecipe,
    *,
    catalog: ReferenceCatalog,
    providers: ProviderRegistry,
) -> dict[str, Any]:
    """One construction stage of one panel, built on the frozen upstream it names."""
    from continuum_imaging.stages import structure_drift
    from continuum_providers.artwork import ArtworkReference
    from continuum_providers.contracts import Locality
    from continuum_providers.policy import transmission_refusal
    from continuum_providers.stages import (
        PanelStageProvider,
        PanelStageRequest,
        check_stage_result,
        stage_gaps,
    )

    intent, execution = recipe.intent, recipe.execution
    provider_id = str(execution.get("provider_id") or "fake.deterministic-stage")
    provider = providers.get(provider_id)
    if not isinstance(provider, PanelStageProvider):
        raise ProviderUnavailableError(
            f"{provider_id} cannot draw construction stages.",
            remediation="Name a stage backend (backend.stage_provider_id) in the profile.",
            blocked_reason=BlockedReason.MISSING_PROVIDER.value,
        )
    inputs = list(
        session.execute(
            select(AttemptInput)
            .where(AttemptInput.attempt_id == attempt.id)
            .order_by(AttemptInput.position)
        ).scalars()
    )
    upstream_row = next((r for r in inputs if r.role is BundleRole.UPSTREAM_STAGE), None)
    upstream = _input_bytes(session, catalog, upstream_row) if upstream_row else None
    upstream_prov = dict(upstream_row.provenance or {}) if upstream_row else {}
    # A cast member's identity inputs name their character, so a backend conditions
    # each character on its own evidence (never one blended batch).
    names: dict[uuid.UUID, str] = {}
    for row in inputs:
        if row.character_id is not None and row.character_id not in names:
            profile = session.get(CharacterProfile, row.character_id)
            if profile is not None:
                names[row.character_id] = profile.display_name
    # What retrieval selected stays in the lineage whatever happens next. What this
    # backend may not receive (a source excerpt on a remote GPU) is withheld per
    # reference - its bytes are never even read - instead of blocking the stage.
    caps = provider.stage_capabilities
    locality = getattr(getattr(provider, "descriptor", None), "locality", Locality.LOCAL)
    selected: list[dict[str, Any]] = []
    withheld: list[dict[str, Any]] = []
    given: list[AttemptInput] = []
    for row in inputs:
        if row.role is BundleRole.UPSTREAM_STAGE:
            continue
        entry = {
            "reference_id": str(row.reference_id) if row.reference_id else row.locator,
            "role": row.role.value,
            "character": names.get(row.character_id) if row.character_id else None,
        }
        selected.append(entry)
        reason = transmission_refusal(
            row.provenance or {}, locality, source_excerpts_allowed=caps.source_excerpts
        )
        if reason is None:
            given.append(row)
        else:
            withheld.append({**entry, "reason": reason})
    references = tuple(
        ArtworkReference(
            role=row.role.value,
            reference_id=str(row.reference_id) if row.reference_id else row.locator,
            data=_input_bytes(session, catalog, row),
            character=names.get(row.character_id) if row.character_id else None,
            teaches=tuple((row.provenance or {}).get("matched_facets") or ()),
            provenance=dict(row.provenance or {}),
        )
        for row in given
    )
    stage = str(intent["stage"]["stage"])
    request = PanelStageRequest(
        stage=stage,
        contract=intent["contract"],
        stage_contract=intent["stage"],
        width=int(execution["width"]),
        height=int(execution["height"]),
        seed=int(execution["seed"]),
        upstream=upstream,
        upstream_stage=(intent.get("upstream") or {}).get("stage"),
        references=references,
        settings={
            **(execution.get("backend_settings") or {}),
            "control_inputs": execution.get("control_inputs") or [],
            "creator_notes": str(intent.get("creator_notes") or ""),
        },
    )
    gaps = stage_gaps(caps, request)
    lost_identity = sorted(
        {str(w["character"]) for w in withheld if w["role"] == "CANON" and w["character"]}
        - {r.character for r in references if r.role == "CANON" and r.character}
    )
    if lost_identity:
        # Identity never silently degrades: a cast member whose only evidence is
        # remote-forbidden is a stop with a way out, not a generic character.
        raise ProviderUnavailableError(
            f"{provider_id} may not receive the identity evidence of "
            f"{', '.join(lost_identity)}: every identity reference is a source excerpt.",
            remediation=(
                "Confirm project-created references for the character (creator photos, approved "
                "project art), or render this stage on a local backend. Source excerpts are "
                "never sent to a remote GPU."
            ),
            blocked_reason=BlockedReason.MISSING_SOURCE_ASSET.value,
            missing_safe_identity=lost_identity,
        )
    if (
        upstream_prov.get("output_class") == RenderOutput.TEST_RENDER.value
        and provider.stage_capabilities.output is RenderOutput.ARTWORK_CANDIDATE
    ):
        gaps.append("an artwork stage cannot build on a test diagram; freeze an artwork upstream")
    if gaps:
        raise ProviderUnavailableError(
            f"{provider_id} cannot draw {stage}: " + "; ".join(gaps),
            remediation="Use a stage backend that covers this stage, or change the profile.",
            blocked_reason=BlockedReason.MISSING_PROVIDER.value,
        )
    result = provider.render_stage(request)
    problems = check_stage_result(request, result)
    if problems:
        raise ProviderUnavailableError(
            "The stage result was refused: " + "; ".join(problems),
            remediation="Fix the backend so a stage keeps the frozen geometry it was given.",
            blocked_reason=BlockedReason.MISSING_MODEL.value,
        )
    drift = structure_drift(upstream, result.image.data) if upstream is not None else None
    upstream_sha = upstream_prov.get("sha256")
    output = _store_derivative(
        session,
        catalog,
        attempt,
        DerivativeKind.OUTPUT,
        result.image.data,
        {"stage": stage, "upstream_sha256": upstream_sha, "structure_drift": drift},
    )
    attempt.artwork_provenance = {
        **result.provenance,
        "references_selected": selected,
        "references_given": [
            str(row.reference_id) if row.reference_id else row.locator for row in given
        ],
        "references_withheld": [
            *withheld,
            *[
                w
                for w in result.provenance.get("references_withheld") or []
                if w.get("reference_id") not in {x["reference_id"] for x in withheld}
            ],
        ],
        "backend": result.backend.value,
        "provider_id": result.provider_id,
        "stage": stage,
        "upstream_sha256": upstream_sha,
        "structure_drift": drift,
        "references": [{"role": r.role, "reference_id": r.reference_id} for r in references],
    }
    attempt.output_class = RenderOutput(result.output)
    attempt.state = AttemptState.GENERATED
    attempt.content_hash = output
    attempt.mime = result.image.mime
    attempt.width = result.image.width
    attempt.height = result.image.height
    attempt.generated_at = dt.datetime.now(dt.UTC)
    session.flush()
    return {"attempt_id": str(attempt.id), "content_hash": output, "stage": stage}


def _compose_page(
    session: Session,
    attempt: RoughAttempt,
    recipe: GenerationRecipe,
    *,
    catalog: ReferenceCatalog,
) -> dict[str, Any]:
    """A page composed from frozen panel finishes: deterministic, no diffusion."""
    from continuum_imaging.manga import bw_finish, compose_manga_page

    intent, execution = recipe.intent, recipe.execution
    rows = list(
        session.execute(
            select(AttemptInput)
            .where(
                AttemptInput.attempt_id == attempt.id,
                AttemptInput.role == BundleRole.UPSTREAM_STAGE,
            )
            .order_by(AttemptInput.position)
        ).scalars()
    )
    panels = [_input_bytes(session, catalog, row) for row in rows]
    width, height = int(execution["width"]), int(execution["height"])
    master = compose_manga_page(panels, width, height)
    bw = bw_finish(master.data)
    detail: dict[str, Any] = {
        "panels": [p["attempt_id"] for p in intent["panels"]],
        "reading_order": "RTL",
    }
    master_hash = _store_derivative(
        session, catalog, attempt, DerivativeKind.COMPOSITION_MASTER, master.data, detail
    )
    detail = {**detail, "master_sha256": master_hash}
    _store_derivative(session, catalog, attempt, DerivativeKind.OUTPUT, master.data, detail)
    _store_derivative(session, catalog, attempt, DerivativeKind.BW_FINISH, bw.data, detail)
    # Color is the panel composite itself: no whole-page re-diffusion.
    _store_derivative(session, catalog, attempt, DerivativeKind.COLOR_FINISH, master.data, detail)
    artwork = all(
        p.get("output_class") == RenderOutput.ARTWORK_CANDIDATE.value for p in intent["panels"]
    )
    panel_provenance = {}
    for p in intent["panels"]:
        source = session.get(RoughAttempt, uuid.UUID(p["attempt_id"]))
        prov = (source.artwork_provenance or {}) if source is not None else {}
        panel_provenance[str(p["panel"])] = {
            key: prov.get(key) for key in ("backend", "provider_id", "model", "workflow", "seed")
        }
    attempt.artwork_provenance = {
        "backend": "CONTINUUM_COMPOSE",
        "provider_id": "continuum.compose",
        "model": {"name": "deterministic page composition", "panels": panel_provenance},
        "workflow": {"id": "continuum.page-compose", "version": "1"},
        "settings": {"width": width, "height": height, "reading_order": "RTL"},
        "master_sha256": master_hash,
        "panels": intent["panels"],
        "bw_finish": "line-preserving continuum_imaging.manga.bw_finish",
        "color_finish": "deterministic panel composite; no whole-page re-diffusion",
    }
    attempt.output_class = RenderOutput.ARTWORK_CANDIDATE if artwork else RenderOutput.TEST_RENDER
    attempt.state = AttemptState.GENERATED
    attempt.content_hash = master_hash
    attempt.mime = master.mime
    attempt.width = master.width
    attempt.height = master.height
    attempt.generated_at = dt.datetime.now(dt.UTC)
    session.flush()
    return {"attempt_id": str(attempt.id), "content_hash": master_hash, "composed": True}
