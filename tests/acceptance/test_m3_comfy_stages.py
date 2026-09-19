"""ComfyUI as a layered-construction stage backend, against a fake ComfyUI server.

The first stage is a bounded text-to-image panel; every later stage starts from
the frozen upstream as its initial latent at a low denoise; the contract's
forbidden content reaches the negative prompt; results carry reproducible
provenance and keep the frozen geometry; candidates never condition identity;
a remote backend refuses source excerpts.
"""

from __future__ import annotations

import io

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


def test_candidates_never_condition_identity_and_remote_refuses_excerpts() -> None:
    confirmed = ArtworkReference(
        role="CANON", reference_id="confirmed", data=_png(64, 64), character="Aster Vale"
    )
    candidate = ArtworkReference(
        role="CANON",
        reference_id="candidate",
        data=_png(64, 64),
        character="Aster Vale",
        provenance={"status": "CANDIDATE"},
    )
    with FakeComfy() as comfy:
        provider = _provider(comfy.url)
        request = _request(
            "DRAWING",
            _png(300, 420),
            contract={"cast": ["Aster Vale"]},
            references=(confirmed, candidate),
        )
        result = provider.render_stage(request)
        assert result.provenance["identity_references_sent"] == ["confirmed"]
        assert result.provenance["candidates_not_used_for_identity"] == ["candidate"]

        remote = _provider(comfy.url, backend=ArtworkBackendKind.COMFY_REMOTE)
        excerpt = ArtworkReference(
            role="TECHNIQUE",
            reference_id="page",
            data=_png(64, 64),
            provenance={"origin": "SOURCE"},
        )
        with pytest.raises(ProviderUnavailableError, match="source excerpt"):
            remote.render_stage(_request("LINE", _png(300, 420), references=(excerpt,)))
