"""ComfyUI as a layered-construction stage backend, against a fake ComfyUI server.

The first stage is a bounded text-to-image panel; every later stage starts from
the frozen upstream as its initial latent at a low denoise; the contract's
forbidden content reaches the negative prompt; results carry reproducible
provenance and keep the frozen geometry; candidates never condition identity;
a remote backend withholds source excerpts per reference instead of refusing the
stage; setting and style references image-condition a stage through a scene lane
kept apart from each character's identity lane.
"""

from __future__ import annotations

import hashlib
import io
from typing import Any

import pytest
from continuum_core import ProviderUnavailableError
from continuum_core.references import RenderOutput
from continuum_providers.artwork import ArtworkBackendKind, ArtworkReference
from continuum_providers.comfy import STAGE_DENOISE, STAGE_WORKFLOW_ID
from continuum_providers.stages import PanelStageRequest, check_stage_result, stage_gaps
from PIL import Image

from tests.acceptance.test_m3_comfy_backend import FakeComfy, _provider

CONTRACT = {
    "beat": "Wide establishing view of a tiny abandoned settlement in the forest; no people.",
    "shot": "WIDE",
    "cast": [],
    "required": ["the inn is the largest surviving building"],
    "forbidden": ["people or figures of any kind", "lettering, speech balloons or any text"],
}


def _png(width: int, height: int) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), (120, 120, 120)).save(buffer, format="PNG")
    return buffer.getvalue()


def _request(stage: str, upstream: bytes | None, **extra: object) -> PanelStageRequest:
    return PanelStageRequest(
        stage=stage,
        contract={**CONTRACT, **extra.pop("contract", {})},  # type: ignore[dict-item]
        stage_contract={"stage": stage},
        width=300,
        height=420,
        seed=5,
        upstream=upstream,
        upstream_stage=None if upstream is None else "COMPOSITION",
        references=extra.pop("references", ()),  # type: ignore[arg-type]
    )


def test_first_stage_is_a_bounded_panel_and_later_stages_hold_the_upstream() -> None:
    with FakeComfy() as comfy:
        provider = _provider(comfy.url)
        caps = provider.stage_capabilities
        assert caps.available and caps.preserves_upstream
        assert caps.output is RenderOutput.ARTWORK_CANDIDATE
        assert "no control net" in caps.notes

        first = _request("COMPOSITION", None)
        assert stage_gaps(caps, first) == []
        composed = provider.render_stage(first)
        graph = comfy.prompts[-1]
        assert any(n["class_type"] == "EmptyLatentImage" for n in graph.values())
        sampler = next(n for n in graph.values() if n["class_type"] == "KSampler")
        assert sampler["inputs"]["denoise"] == 1.0
        texts = [n["inputs"]["text"] for n in graph.values() if n["class_type"] == "CLIPTextEncode"]
        assert any("no humans" in t and "wide shot" in t for t in texts)
        assert any("people or figures of any kind" in t for t in texts)
        assert check_stage_result(first, composed) == []
        assert composed.provenance["workflow"]["id"] == STAGE_WORKFLOW_ID

        line = _request("LINE", _png(300, 420))
        result = provider.render_stage(line)
        graph = comfy.prompts[-1]
        load = next(n for n in graph.values() if n["class_type"] == "LoadImage")
        assert load["inputs"]["image"] in comfy.uploads
        assert not any(n["class_type"] == "EmptyLatentImage" for n in graph.values())
        sampler = next(n for n in graph.values() if n["class_type"] == "KSampler")
        assert sampler["inputs"]["denoise"] == STAGE_DENOISE["LINE"]
        assert (result.image.width, result.image.height) == (300, 420)
        assert result.provenance["settings"]["upstream_held_by"] == "init latent"
        assert check_stage_result(line, result) == []


def test_a_vae_rounding_is_restored_but_a_moved_geometry_is_not() -> None:
    with FakeComfy() as comfy:
        provider = _provider(comfy.url)
        # The fake returns 300x420 for image-to-image; an upstream 4px wider is a
        # rounding (restored), one 60px wider is a different geometry (refused).
        rounded = _request("DRAWING", _png(304, 420))
        assert (provider.render_stage(rounded).image.width) == 304
        moved = _request("DRAWING", _png(360, 420))
        assert any(
            "changed the frozen geometry" in p
            for p in check_stage_result(moved, provider.render_stage(moved))
        )


def _ref(
    reference_id: str,
    role: str,
    *,
    shade: int,
    origin: str = "USER_CREATED",
    character: str | None = None,
    **provenance: object,
) -> ArtworkReference:
    buffer = io.BytesIO()
    Image.new("RGB", (64, 64), (shade, shade, shade)).save(buffer, format="PNG")
    return ArtworkReference(
        role=role,
        reference_id=reference_id,
        data=buffer.getvalue(),
        character=character,
        provenance={"origin": origin, **provenance},
    )


def _uploaded(comfy: FakeComfy, reference: ArtworkReference) -> bool:
    return f"continuum-{hashlib.sha256(reference.data).hexdigest()[:24]}.png" in comfy.uploads


def _adapters(graph: dict[str, Any]) -> list[dict[str, Any]]:
    return [n["inputs"] for n in graph.values() if n["class_type"] == "IPAdapterAdvanced"]


def _images_of(graph: dict[str, Any], node_ref: list[Any]) -> set[str]:
    """The uploaded file names feeding one adapter's image input (through ImageBatch)."""
    node = graph[node_ref[0]]
    if node["class_type"] == "LoadImage":
        return {node["inputs"]["image"]}
    return _images_of(graph, node["inputs"]["image1"]) | _images_of(graph, node["inputs"]["image2"])


# A CAL-01-like pack: the creator-approved inn image (project-owned) and two
# source manga pages retrieved for technique and setting.
INN = _ref(
    "inn",
    "ENVIRONMENT",
    shade=30,
    standing="PREFERRED_FOR_CURRENT_LOOK",
    matched_facets=["COMPOSITION", "ESTABLISHING_SHOT", "LINEART"],
)
SOURCE_SETTING = _ref("source-forest", "ENVIRONMENT", shade=60, origin="SOURCE")
SOURCE_TECHNIQUE = _ref(
    "source-page", "TECHNIQUE", shade=90, origin="SOURCE", matched_facets=["PAGE_COMPOSITION"]
)


def test_remote_withholds_source_excerpts_and_still_conditions_on_the_safe_reference() -> None:
    with FakeComfy() as comfy:
        remote = _provider(comfy.url, backend=ArtworkBackendKind.COMFY_REMOTE)
        assert remote.stage_capabilities.source_excerpts is False
        result = remote.render_stage(
            _request("COMPOSITION", None, references=(INN, SOURCE_SETTING, SOURCE_TECHNIQUE))
        )
        prov = result.provenance
        # Not blocked; the source pages are withheld with a reason, the inn is used.
        assert {w["reference_id"] for w in prov["references_withheld"]} == {
            "source-forest",
            "source-page",
        }
        assert all("never leaves this machine" in w["reason"] for w in prov["references_withheld"])
        assert prov["references_transmitted"] == ["inn"]
        assert prov["conditioning"]["scene"]["references"] == ["inn"]
        assert prov["conditioning"]["identity"] == {}
        # Forbidden bytes never reach the remote transport; the safe image does.
        assert _uploaded(comfy, INN)
        assert not _uploaded(comfy, SOURCE_SETTING)
        assert not _uploaded(comfy, SOURCE_TECHNIQUE)


def test_an_empty_cast_composition_is_image_conditioned_on_the_environment() -> None:
    with FakeComfy() as comfy:
        provider = _provider(comfy.url)
        result = provider.render_stage(_request("COMPOSITION", None, references=(INN,)))
        graph = comfy.prompts[-1]
        (scene,) = _adapters(graph)
        assert scene["weight_type"] == "composition" and scene["weight"] == 0.8
        assert _images_of(graph, scene["image"]) == {
            f"continuum-{hashlib.sha256(INN.data).hexdigest()[:24]}.png"
        }
        # The conditioned model is the one the sampler uses.
        sampler = next(n for n in graph.values() if n["class_type"] == "KSampler")
        assert graph[sampler["inputs"]["model"][0]]["class_type"] == "IPAdapterAdvanced"
        assert result.provenance["conditioning"]["scene"] == {
            "purpose": "COMPOSITION",
            "mechanism": "IP-Adapter weight_type='composition'",
            "weight": 0.8,
            "references": ["inn"],
        }


def test_later_stages_take_style_and_technique_never_image_conditions() -> None:
    with FakeComfy() as comfy:
        local = _provider(comfy.url)
        assert local.stage_capabilities.source_excerpts is True
        result = local.render_stage(
            _request("LINE", _png(300, 420), references=(SOURCE_TECHNIQUE, INN))
        )
        (scene,) = _adapters(comfy.prompts[-1])
        assert scene["weight_type"] == "style transfer"
        prov = result.provenance
        assert prov["conditioning"]["scene"]["references"] == ["inn"]
        assert prov["references_withheld"] == []  # local: nothing is withheld
        (skipped,) = prov["references_not_conditioned"]
        assert skipped["reference_id"] == "source-page"
        assert "teach by abstraction" in skipped["reason"]
        assert not _uploaded(comfy, SOURCE_TECHNIQUE)


def test_identity_stays_scoped_to_each_character_and_apart_from_the_scene() -> None:
    aster = _ref("aster-face", "CANON", shade=120, character="Aster Vale")
    rowan = _ref("rowan-face", "CANON", shade=150, character="Rowan")
    candidate = _ref("aster-maybe", "CANON", shade=180, character="Aster Vale", status="CANDIDATE")
    with FakeComfy() as comfy:
        provider = _provider(comfy.url)
        result = provider.render_stage(
            _request(
                "DRAWING",
                _png(300, 420),
                contract={"cast": ["Aster Vale", "Rowan"]},
                references=(aster, rowan, candidate, INN),
            )
        )
        graph = comfy.prompts[-1]
        lanes = {
            frozenset(_images_of(graph, a["image"])): a["weight_type"] for a in _adapters(graph)
        }
        name = lambda r: f"continuum-{hashlib.sha256(r.data).hexdigest()[:24]}.png"  # noqa: E731
        assert lanes == {
            frozenset({name(INN)}): "style and composition",
            frozenset({name(aster)}): "linear",
            frozenset({name(rowan)}): "linear",
        }
        conditioning = result.provenance["conditioning"]
        assert conditioning["identity"] == {"Aster Vale": ["aster-face"], "Rowan": ["rowan-face"]}
        assert conditioning["scene"]["references"] == ["inn"]
        assert result.provenance["candidates_not_used_for_identity"] == ["aster-maybe"]


def test_a_cast_member_is_never_drawn_from_setting_or_style_references() -> None:
    style = _ref("house", "STYLE", shade=200)
    request = _request(
        "COMPOSITION",
        None,
        contract={"cast": ["Aster Vale"]},
        references=(INN, style),
    )
    with FakeComfy() as comfy:
        provider = _provider(comfy.url)
        gaps = stage_gaps(provider.stage_capabilities, request)
        assert any("Aster Vale has no identity evidence" in g for g in gaps)
        with pytest.raises(ProviderUnavailableError, match="No identity evidence"):
            provider.render_stage(request)
        # A remote backend whose only identity evidence is a source excerpt stops too.
        remote = _provider(comfy.url, backend=ArtworkBackendKind.COMFY_REMOTE)
        source_face = _ref(
            "source-face", "CANON", shade=210, origin="SOURCE", character="Aster Vale"
        )
        with pytest.raises(ProviderUnavailableError, match="No identity evidence"):
            remote.render_stage(
                _request(
                    "COMPOSITION",
                    None,
                    contract={"cast": ["Aster Vale"]},
                    references=(source_face, INN),
                )
            )
        assert not _uploaded(comfy, source_face)
