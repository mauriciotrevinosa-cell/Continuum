"""Deterministic fake providers (D-12, ADR-0004 section 6).

Phase 0 ships **no real AI SDK and downloads no model**. These fakes prove
the contract, the policy engine and the blocked/remediation path without any
network access or credential, which is exactly what acceptance test 110.12
requires.

Every fake is deterministic: identical input produces identical output, so a
job re-running a unit after a crash still satisfies the effect-idempotency
invariant of ADR-0002 section 2.
"""

from __future__ import annotations

import hashlib
from typing import Any

from continuum_core import ProviderUnavailableError

from continuum_providers.contracts import (
    Capability,
    CostClass,
    GenerationRequest,
    GenerationResult,
    Locality,
    PrivacyClass,
    ProviderDescriptor,
    RoughRenderRequest,
    RoughRenderResult,
)

__all__ = [
    "UNSATISFIABLE_CAPABILITY",
    "DeterministicEmbeddingProvider",
    "DeterministicPageProvider",
    "DeterministicSketchProvider",
    "EchoTextProvider",
    "NullImageProvider",
]

#: A capability nothing in Phase 0 provides, used by the
#: synthetic.blocked_capability job to prove the BLOCKED path.
UNSATISFIABLE_CAPABILITY = Capability.VIDEO_GENERATE


class EchoTextProvider:
    """Returns its prompt back, plus a schema-shaped stub when asked."""

    descriptor = ProviderDescriptor(
        id="fake.echo-text",
        capabilities=frozenset({Capability.TEXT_GENERATE, Capability.TEXT_STRUCTURED}),
        locality=Locality.LOCAL,
        cost_class=CostClass.FREE,
        privacy_class=PrivacyClass.ON_DEVICE,
        model_ref=None,
        version="1",
        license_note="Fake provider. No model weights, no third-party code.",
    )

    def generate(self, request: GenerationRequest) -> GenerationResult:
        structured = None
        if request.schema is not None:
            structured = {key: f"echo:{key}" for key in request.schema.get("properties", {})}
        return GenerationResult(
            provider_id=self.descriptor.id,
            model_ref=self.descriptor.model_ref,
            version=self.descriptor.version,
            text=request.prompt,
            structured=structured,
            usage={"data_class": request.data_class.value},
        )


class DeterministicEmbeddingProvider:
    """Hash-derived vectors: stable across runs, processes and machines."""

    DIMENSIONS = 16

    descriptor = ProviderDescriptor(
        id="fake.deterministic-embedding",
        capabilities=frozenset({Capability.EMBED_TEXT}),
        locality=Locality.LOCAL,
        cost_class=CostClass.FREE,
        privacy_class=PrivacyClass.ON_DEVICE,
        model_ref=None,
        version="1",
        license_note="Fake provider. No model weights.",
    )

    def embed(self, request: GenerationRequest) -> GenerationResult:
        digest = hashlib.sha256(request.prompt.encode()).digest()
        vector = tuple(
            (digest[i % len(digest)] / 255.0) * 2.0 - 1.0 for i in range(self.DIMENSIONS)
        )
        return GenerationResult(
            provider_id=self.descriptor.id,
            model_ref=self.descriptor.model_ref,
            version=self.descriptor.version,
            vector=vector,
            usage={"dimensions": self.DIMENSIONS, "data_class": request.data_class.value},
        )


class NullImageProvider:
    """Declares the capability and refuses to execute.

    Exists so the registry has a provider whose *selection* succeeds while
    its *invocation* fails -- the two failure modes must stay
    distinguishable, because they need different remediation.
    """

    descriptor = ProviderDescriptor(
        id="fake.null-image",
        capabilities=frozenset({Capability.IMAGE_GENERATE}),
        locality=Locality.LOCAL,
        cost_class=CostClass.FREE,
        privacy_class=PrivacyClass.ON_DEVICE,
        model_ref=None,
        version="1",
        license_note="Fake provider. Generates nothing.",
    )

    def generate_image(self, request: GenerationRequest) -> GenerationResult:
        raise ProviderUnavailableError(
            "Image generation is not implemented in Phase 0.",
            technical_detail=f"data_class={request.data_class.value}",
            remediation=(
                "Visual Lab and image generation arrive in Phase 10 "
                "(Master Plan section 109). Phase 0 ships contracts only."
            ),
        )


class DeterministicSketchProvider:
    """Renders a rough as a labelled grayscale sketch of its recipe.

    No model, no network, no randomness beyond the recorded seed: the same
    request yields the same pixels, and a different seed yields a visibly
    different attempt. It exists so the rough-manga pipeline (bundle, source
    plate, edit intent, attempts, review) runs end to end before any real
    image model is installed - and it says so in every image it draws.
    """

    WORKFLOW = "sketch.v1"

    descriptor = ProviderDescriptor(
        id="fake.deterministic-sketch",
        capabilities=frozenset({Capability.ROUGH_RENDER}),
        locality=Locality.LOCAL,
        cost_class=CostClass.FREE,
        privacy_class=PrivacyClass.ON_DEVICE,
        model_ref=None,
        version="1",
        license_note="Fake provider. Draws recipe diagrams with Pillow; no model weights.",
    )

    def render_rough(self, request: RoughRenderRequest) -> RoughRenderResult:
        from continuum_imaging.sketch import (
            SketchOperation,
            SketchPlacement,
            SketchReference,
            SketchRequest,
            render_sketch,
        )

        rendered = render_sketch(
            SketchRequest(
                width=request.width,
                height=request.height,
                mode=request.mode,
                seed=request.seed,
                title=request.title,
                lines=(*request.lines, "deterministic sketch - no model"),
                plate=request.plate,
                plate_region=request.plate_region,
                operations=tuple(
                    SketchOperation(op.kind, op.region, op.label) for op in request.operations
                ),
                placements=tuple(SketchPlacement(p.region, p.label) for p in request.placements),
                references=tuple(
                    SketchReference(r.role, r.label, r.data, r.region) for r in request.references
                ),
            )
        )
        return RoughRenderResult(
            provider_id=self.descriptor.id,
            model_ref=self.descriptor.model_ref,
            version=self.descriptor.version,
            workflow=self.WORKFLOW,
            image=rendered.data,
            mime=rendered.mime,
            width=rendered.width,
            height=rendered.height,
            usage={"data_class": request.data_class.value},
        )


class DeterministicPageProvider:
    """The test backend for page production: a labelled diagram, never artwork.

    It draws a composition master (the page's key, characters, dialogue and
    directions as a sketch), then derives both finishes from that master - a
    black-and-white screentone finish and a tinted "color" finish - so the
    sibling-derivative invariant is exercised without a model.
    """

    WORKFLOW = "test.page-sketch.v1"

    def __init__(self) -> None:
        from continuum_core.references import RenderOutput

        from continuum_providers.artwork import ArtworkBackendKind, ArtworkCapabilities

        self.backend = ArtworkBackendKind.TEST
        self.capabilities = ArtworkCapabilities(
            output=RenderOutput.TEST_RENDER,
            max_reference_images=64,
            sibling_finishes=True,
            layout_conditioning=True,
            seeded=True,
            notes="Deterministic diagrams for workflow tests. Never artwork.",
        )

    descriptor = ProviderDescriptor(
        id="fake.deterministic-page",
        capabilities=frozenset({Capability.PAGE_RENDER}),
        locality=Locality.LOCAL,
        cost_class=CostClass.FREE,
        privacy_class=PrivacyClass.ON_DEVICE,
        model_ref=None,
        version="1",
        license_note="Fake provider. Draws page diagrams with Pillow; no model weights.",
    )

    def render_page(self, request):  # type: ignore[no-untyped-def]
        from continuum_core.references import RenderOutput
        from continuum_imaging.manga import bw_finish, tint_finish
        from continuum_imaging.sketch import SketchReference, SketchRequest, render_sketch

        from continuum_providers.artwork import PageRenderResult, RenderedImage

        page = request.page
        plan = page.get("plan") or {}
        lines = [
            "WORKFLOW TEST - NOT ARTWORK",
            f"{page.get('page_key', request.page_key)} - p.{page.get('integrated_page', '?')}"
            f" - {page.get('origin', '')} - {page.get('scene') or ''}",
            f"cast: {plan.get('primary_character') or '-'}"
            f" + {', '.join(plan.get('supporting_characters') or []) or '-'}"
            f" | intent: {plan.get('primary_intent') or '-'}"
            " | "
            + ("silent" if plan.get("silent") else f"{plan.get('dialogue_lines', 0)} line(s)"),
            *[
                f"{d.get('speaker') or d.get('kind')}: {d.get('text')}"
                for d in page.get("dialogue") or []
            ],
            *list(page.get("directions") or [])[:6],
            "deterministic page sketch - no model",
        ]
        master = render_sketch(
            SketchRequest(
                width=request.width,
                height=request.height,
                mode="NEW_GENERATION",
                seed=request.seed,
                title=request.page_key,
                lines=tuple(lines),
                references=tuple(
                    SketchReference(r.role, r.character or r.role.lower(), r.data, None)
                    for r in request.references[:8]
                ),
            )
        )
        bw = bw_finish(master.data)
        color = tint_finish(master.data, request.seed)

        def image(encoded: Any) -> RenderedImage:
            return RenderedImage(encoded.data, encoded.mime, encoded.width, encoded.height)

        rendered = image(master)
        return PageRenderResult(
            backend=self.backend,
            provider_id=self.descriptor.id,
            output=RenderOutput.TEST_RENDER,
            master=rendered,
            bw=image(bw),
            color=image(color),
            provenance={
                "backend": self.backend.value,
                "workflow": {"id": self.WORKFLOW, "version": "1"},
                "settings": {"width": request.width, "height": request.height},
                "seed": request.seed,
                "master_sha256": rendered.sha256,
            },
        )


class DeterministicStageProvider:
    """The test backend for layered construction: stage diagrams, never artwork.

    The first stage draws a blocking diagram of the panel contract; every later
    stage is a geometry-preserving transform of the frozen upstream it was given,
    so freezing, building on and invalidating stages is exercised without a model.
    """

    WORKFLOW = "test.panel-stage.v1"

    def __init__(self) -> None:
        from continuum_core.knowledge import STAGE_ORDER
        from continuum_core.references import RenderOutput

        from continuum_providers.artwork import ArtworkBackendKind
        from continuum_providers.stages import StageCapabilities

        self.backend = ArtworkBackendKind.TEST
        self.stage_capabilities = StageCapabilities(
            output=RenderOutput.TEST_RENDER,
            stages=frozenset(stage.value for stage in STAGE_ORDER),
            preserves_upstream=True,
            seeded=True,
            max_edge=2400,
            notes="Deterministic stage diagrams for workflow tests. Never artwork.",
        )

    descriptor = ProviderDescriptor(
        id="fake.deterministic-stage",
        capabilities=frozenset({Capability.PANEL_STAGE_RENDER}),
        locality=Locality.LOCAL,
        cost_class=CostClass.FREE,
        privacy_class=PrivacyClass.ON_DEVICE,
        model_ref=None,
        version="1",
        license_note="Fake provider. Draws stage diagrams with Pillow; no model weights.",
    )

    def render_stage(self, request):  # type: ignore[no-untyped-def]
        from continuum_core.references import RenderOutput
        from continuum_imaging.stages import stage_diagram

        from continuum_providers.artwork import RenderedImage
        from continuum_providers.stages import PanelStageResult

        contract = request.contract
        lines = [
            *[str(item) for item in contract.get("required") or []],
            str(contract.get("beat") or ""),
        ]
        image = stage_diagram(
            request.stage,
            width=request.width,
            height=request.height,
            seed=request.seed,
            upstream=request.upstream,
            lines=[line[:40] for line in lines if line],
        )
        return PanelStageResult(
            backend=self.backend,
            provider_id=self.descriptor.id,
            output=RenderOutput.TEST_RENDER,
            image=RenderedImage(image.data, image.mime, image.width, image.height),
            provenance={
                "backend": self.backend.value,
                "workflow": {"id": self.WORKFLOW, "version": "1"},
                "settings": {"stage": request.stage, "seed": request.seed},
                "seed": request.seed,
                "references_seen": [r.reference_id for r in request.references],
            },
        )
