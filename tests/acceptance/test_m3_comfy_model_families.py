"""A second model family through the same backend, and adapters on top of it.

Two things matter here and nothing else: a different family gets the graph it
actually needs rather than a renamed copy of the first one, and every adapter
that touched an image is recorded with it. A backend that cannot condition on
references in a given family says so instead of claiming it did.
"""

from __future__ import annotations

from typing import Any

import pytest
from continuum_core import ProviderUnavailableError
from continuum_providers.artwork import ArtworkBackendKind
from continuum_providers.comfy import (
    ComfyConfig,
    ComfyLora,
    ComfyModel,
    ComfyModelFamily,
    ComfyPageProvider,
    configured_loras,
)
from continuum_providers.stages import stage_gaps

from tests.acceptance.test_m3_comfy_backend import CHECKPOINT, FakeComfy
from tests.acceptance.test_m3_comfy_stages import INN, _png, _request

MODEL = ComfyModel(
    name=CHECKPOINT,
    version="1.0",
    sha256="c" * 64,
    license="a permissive licence",
    source="https://example.invalid/model",
)
ADAPTER = ComfyLora(
    name="house-style.safetensors",
    strength_model=0.7,
    strength_clip=0.6,
    version="1",
    sha256="d" * 64,
    license="a permissive licence",
    source="https://example.invalid/lora",
)


def _flux(url: str, loras: tuple[ComfyLora, ...] = ()) -> ComfyPageProvider:
    return ComfyPageProvider(
        ComfyConfig(
            backend=ArtworkBackendKind.COMFY_LOCAL,
            base_url=url,
            model=MODEL,
            family=ComfyModelFamily.FLUX,
            clip_names=("clip-a.safetensors", "clip-b.safetensors"),
            vae_name="vae.safetensors",
            loras=loras,
        )
    )


def _sdxl(url: str, loras: tuple[ComfyLora, ...] = ()) -> ComfyPageProvider:
    return ComfyPageProvider(
        ComfyConfig(backend=ArtworkBackendKind.COMFY_LOCAL, base_url=url, model=MODEL, loras=loras)
    )


def _nodes(graph: dict[str, Any]) -> set[str]:
    return {node["class_type"] for node in graph.values()}


def test_a_flux_checkpoint_gets_its_own_graph_not_a_renamed_one() -> None:
    with FakeComfy(family=ComfyModelFamily.FLUX) as comfy:
        provider = _flux(comfy.url)
        assert provider.status(refresh=True).ready
        provider.render_stage(_request("COMPOSITION", None))
        graph = comfy.prompts[-1]
        assert {"UNETLoader", "DualCLIPLoader", "VAELoader", "FluxGuidance"} <= _nodes(graph)
        assert "CheckpointLoaderSimple" not in _nodes(graph)
        loader = next(n for n in graph.values() if n["class_type"] == "DualCLIPLoader")
        assert loader["inputs"]["clip_name1"] == "clip-a.safetensors"
        assert (
            next(n for n in graph.values() if n["class_type"] == "VAELoader")["inputs"]["vae_name"]
            == "vae.safetensors"
        )


def test_the_other_family_keeps_working_exactly_as_before() -> None:
    with FakeComfy() as comfy:
        _sdxl(comfy.url).render_stage(_request("COMPOSITION", None))
        assert "CheckpointLoaderSimple" in _nodes(comfy.prompts[-1])
        assert "UNETLoader" not in _nodes(comfy.prompts[-1])


def test_a_flux_stage_continues_from_the_frozen_upstream() -> None:
    with FakeComfy(family=ComfyModelFamily.FLUX) as comfy:
        _flux(comfy.url).render_stage(_request("LINE", _png(300, 420)))
        graph = comfy.prompts[-1]
        assert "VAEEncode" in _nodes(graph)
        sampler = next(n for n in graph.values() if n["class_type"] == "KSampler")
        assert graph[sampler["inputs"]["latent_image"][0]]["class_type"] == "VAEEncode"


def test_flux_does_not_claim_reference_conditioning_it_does_not_have() -> None:
    """Honesty, not capability: the IP-Adapter lanes are an SDXL-family path."""
    with FakeComfy(family=ComfyModelFamily.FLUX) as comfy:
        provider = _flux(comfy.url)
        caps = provider.stage_capabilities
        assert caps.identity_conditioning is False
        assert caps.reference_conditioning is False
        request = _request("COMPOSITION", None, contract={"cast": ["Aster Vale"]})
        assert any("identity" in gap for gap in stage_gaps(caps, request))
        with pytest.raises(ProviderUnavailableError, match="No identity evidence"):
            provider.render_stage(request)


def test_an_adapter_is_applied_once_and_recorded_with_the_image() -> None:
    with FakeComfy() as comfy:
        result = _sdxl(comfy.url, (ADAPTER,)).render_stage(_request("COMPOSITION", None))
        graph = comfy.prompts[-1]
        loaders = [n for n in graph.values() if n["class_type"] == "LoraLoader"]
        assert len(loaders) == 1
        assert loaders[0]["inputs"]["lora_name"] == "house-style.safetensors"
        assert loaders[0]["inputs"]["strength_model"] == 0.7
        # The sampler reads the adapted model, so nothing bypasses the adapter.
        sampler = next(n for n in graph.values() if n["class_type"] == "KSampler")
        assert graph[sampler["inputs"]["model"][0]]["class_type"] == "LoraLoader"
        recorded = result.provenance["model"]
        assert recorded["family"] == "SDXL"
        assert recorded["loras"][0]["sha256"] == "d" * 64
        assert recorded["loras"][0]["license"] == "a permissive licence"


def test_the_adapter_is_part_of_the_workflow_identity() -> None:
    """A render with an adapter is not the same workflow as one without it."""
    with FakeComfy() as comfy:
        plain = _sdxl(comfy.url).render_stage(_request("COMPOSITION", None))
        adapted = _sdxl(comfy.url, (ADAPTER,)).render_stage(_request("COMPOSITION", None))
    assert plain.provenance["workflow"]["sha256"] != adapted.provenance["workflow"]["sha256"]


def test_an_adapter_keeps_the_scene_lane_in_front_of_the_sampler() -> None:
    with FakeComfy() as comfy:
        _sdxl(comfy.url, (ADAPTER,)).render_stage(_request("COMPOSITION", None, references=(INN,)))
        graph = comfy.prompts[-1]
        adapter = next(n for n in graph.values() if n["class_type"] == "IPAdapterAdvanced")
        loader = next(n for n in graph.values() if n["class_type"] == "IPAdapterUnifiedLoader")
        assert graph[loader["inputs"]["model"][0]]["class_type"] == "LoraLoader"
        sampler = next(n for n in graph.values() if n["class_type"] == "KSampler")
        assert graph[sampler["inputs"]["model"][0]]["class_type"] == "IPAdapterAdvanced"
        assert adapter["inputs"]["weight_type"] == "composition"


def test_adapters_are_configuration_and_a_broken_row_is_refused() -> None:
    assert configured_loras("") == ()
    (one,) = configured_loras('[{"name": "a.safetensors", "strength_model": 0.5}]')
    assert (one.name, one.strength_model, one.strength_clip) == ("a.safetensors", 0.5, 1.0)
    with pytest.raises(ValueError, match="needs at least a name"):
        configured_loras('[{"strength_model": 0.5}]')
