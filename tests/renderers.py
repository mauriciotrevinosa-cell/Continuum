"""Test doubles for rough renderers.

The deterministic sketch provider is a *test renderer*: its images are
diagrams of a recipe and can never be approved as art. Tests that exercise
creative approval, supersession or continuity need attempts a real model
would have drawn; this double draws the same deterministic pixels but
declares them artwork candidates, the way a real generation provider will.
"""

from __future__ import annotations

from dataclasses import replace

from continuum_core.references import RenderOutput
from continuum_providers import ProviderRegistry
from continuum_providers.artwork import ArtworkCapabilities, PageRenderRequest, PageRenderResult
from continuum_providers.fakes import (
    DeterministicEmbeddingProvider,
    DeterministicPageProvider,
    DeterministicSketchProvider,
    EchoTextProvider,
    NullImageProvider,
)

__all__ = [
    "ArtworkCandidateDouble",
    "ArtworkPageDouble",
    "artwork_page_registry",
    "artwork_registry",
]


class ArtworkCandidateDouble(DeterministicSketchProvider):
    descriptor = replace(
        DeterministicSketchProvider.descriptor,
        id="fake.artwork-candidate-double",
        rough_output=RenderOutput.ARTWORK_CANDIDATE,
        license_note="Test double: deterministic pixels declared as an artwork candidate.",
    )


def artwork_registry() -> ProviderRegistry:
    """The default fakes, with the sketch renderer replaced by the artwork double."""
    registry = ProviderRegistry()
    registry.register(EchoTextProvider())
    registry.register(DeterministicEmbeddingProvider())
    registry.register(NullImageProvider())
    registry.register(ArtworkCandidateDouble())
    return registry


class ArtworkPageDouble(DeterministicPageProvider):
    """Deterministic page pixels declared as artwork, with complete reproducibility records."""

    descriptor = replace(
        DeterministicPageProvider.descriptor,
        id="fake.artwork-page-double",
        license_note="Test double: deterministic page pixels declared as an artwork candidate.",
    )

    def __init__(self) -> None:
        super().__init__()
        self.capabilities = ArtworkCapabilities(
            output=RenderOutput.ARTWORK_CANDIDATE,
            max_reference_images=64,
            identity_conditioning=True,
            layout_conditioning=True,
            sibling_finishes=True,
            seeded=True,
        )

    def render_page(self, request: PageRenderRequest) -> PageRenderResult:
        result = super().render_page(request)
        return replace(
            result,
            provider_id=self.descriptor.id,
            output=RenderOutput.ARTWORK_CANDIDATE,
            provenance={
                **result.provenance,
                "model": {
                    "name": "double-model",
                    "version": "1.0",
                    "sha256": "0" * 64,
                    "license": "test-only",
                    "source": "tests/renderers.py",
                },
                "workflow": {"id": "double-page", "version": "1", "sha256": "1" * 64},
                "settings": {"steps": 1, "width": request.width, "height": request.height},
            },
        )


def artwork_page_registry() -> ProviderRegistry:
    """The default fakes plus the artwork page double."""
    registry = artwork_registry()
    registry.register(DeterministicPageProvider())
    registry.register(ArtworkPageDouble())
    return registry
