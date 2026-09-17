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
        character["character_id"]: character["name"]
        for character in intent.get("characters") or []
    }
    if op.get("character_id") in names:
        parts.append(names[op["character_id"]])
    if op.get("text"):
        parts.append(f'"{op["text"]}"')
    return " ".join(part for part in parts if part).strip()


def _placement_label(placement: dict[str, Any], intent: dict[str, Any]) -> str:
    names = {
        character["character_id"]: character["name"]
        for character in intent.get("characters") or []
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
        character["character_id"]: character["name"]
        for character in bundle.get("characters") or []
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
