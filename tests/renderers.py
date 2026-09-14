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
from continuum_providers.fakes import (
    DeterministicEmbeddingProvider,
    DeterministicSketchProvider,
    EchoTextProvider,
    NullImageProvider,
)

__all__ = ["ArtworkCandidateDouble", "artwork_registry"]


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
