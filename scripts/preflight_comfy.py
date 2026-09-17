"""Probe configured ComfyUI backends for real manga-production readiness.

This is stricter than the provider's generic ``ready`` flag. A server can be
healthy enough to render a generic image while still be unsuitable for
Continuum manga because character identity conditioning or reproducibility
metadata is missing.

By default this is a read-only structural probe. ``--smoke`` goes one step
further: it sends one tiny, synthetic character reference through the real
Continuum page workflow. That verifies the checkpoint, IP-Adapter/CLIP Vision
assets and both sibling finishes together before a real page is queued. The
smoke reference is generated in memory; no Source Vault material is sent.

Examples::

    uv run --no-sync python scripts/preflight_comfy.py
    uv run --no-sync python scripts/preflight_comfy.py --backend local
    uv run --no-sync python scripts/preflight_comfy.py --backend local --smoke
    uv run --no-sync python scripts/preflight_comfy.py --backend remote --json

Exit status is zero only when at least one selected Comfy backend is production
ready (and, with ``--smoke``, also completes the synthetic render). No model is
downloaded and no setting is changed.
"""

from __future__ import annotations

import argparse
import io
import json
import sys
from typing import Any

from continuum_config import get_settings
from continuum_providers import artwork_backends, build_default_registry
from continuum_providers.artwork import ArtworkReference, PageRenderRequest, check_result
from continuum_providers.comfy import ComfyPageProvider
from PIL import Image, ImageDraw


def _selected(states: list[dict[str, Any]], backend: str) -> list[dict[str, Any]]:
    wanted = {
        "local": {"COMFY_LOCAL"},
        "remote": {"COMFY_REMOTE"},
        "any": {"COMFY_LOCAL", "COMFY_REMOTE"},
    }[backend]
    return [state for state in states if state.get("kind") in wanted]


def _print_state(state: dict[str, Any]) -> None:
    kind = str(state.get("kind") or "COMFY")
    provider = str(state.get("provider_id") or "unknown")
    print(f"{kind} ({provider})")
    print(f"  configured: {'yes' if state.get('configured') else 'no'}")
    print(f"  reachable: {'yes' if state.get('reachable') else 'no'}")
    print(f"  core render ready: {'yes' if state.get('ready') else 'no'}")
    print(f"  identity conditioning: {'yes' if state.get('identity_conditioning') else 'no'}")
    print(f"  checkpoint available: {'yes' if state.get('checkpoint_available') else 'no'}")
    print(f"  manga production ready: {'YES' if state.get('production_ready') else 'NO'}")
    model = state.get("model")
    if isinstance(model, dict) and model.get("name"):
        print(f"  checkpoint: {model['name']}")
    endpoint = state.get("endpoint")
    if endpoint:
        print(f"  endpoint: {endpoint}")
    gaps = [str(gap) for gap in state.get("production_gaps") or []]
    if gaps:
        print("  blockers:")
        for gap in gaps:
            print(f"    - {gap}")
    else:
        print("  blockers: none")


def _synthetic_reference() -> bytes:
    """A tiny invented image: enough to prove the identity-conditioning path."""
    image = Image.new("RGB", (192, 256), (230, 230, 230))
    draw = ImageDraw.Draw(image)
    draw.ellipse((52, 28, 140, 116), outline=(30, 30, 30), width=5)
    draw.line((96, 116, 96, 210), fill=(30, 30, 30), width=7)
    draw.line((96, 142, 48, 184), fill=(30, 30, 30), width=6)
    draw.line((96, 142, 144, 184), fill=(30, 30, 30), width=6)
    draw.line((96, 208, 62, 246), fill=(30, 30, 30), width=6)
    draw.line((96, 208, 130, 246), fill=(30, 30, 30), width=6)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _smoke(provider: ComfyPageProvider) -> dict[str, Any]:
    reference = ArtworkReference(
        role="CANON",
        reference_id="synthetic-preflight-reference",
        data=_synthetic_reference(),
        character="Continuum Preflight Figure",
        provenance={
            "authority": "CREATOR_PRIMARY",
            "status": "CONFIRMED",
            "kind": "synthetic_preflight",
        },
    )
    request = PageRenderRequest(
        page_key="continuum-comfy-preflight",
        width=256,
        height=384,
        seed=17,
        page={
            "characters": ["Continuum Preflight Figure"],
            "directions": ["Single invented figure, centered, simple standing pose."],
        },
        plan={},
        continuity={"character_rules": {}},
        references=(reference,),
        settings={"workflow": "page.v1", "purpose": "preflight"},
    )
    result = provider.render_page(request)
    problems = check_result(result)
    if problems:
        raise RuntimeError("; ".join(problems))
    return {
        "provider_id": result.provider_id,
        "master_sha256": result.master.sha256,
        "master_size": [result.master.width, result.master.height],
        "bw_size": [result.bw.width, result.bw.height],
        "color_size": [result.color.width, result.color.height],
        "identity_references_sent": result.provenance.get("identity_references_sent", []),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--backend", choices=("local", "remote", "any"), default="any")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="Run one tiny synthetic identity-conditioned page through the selected backend(s).",
    )
    args = parser.parse_args(argv)

    settings = get_settings()
    registry = build_default_registry(settings=settings)
    selected = _selected(artwork_backends(registry, settings), args.backend)
    smoke_results: dict[str, dict[str, Any]] = {}

    if args.smoke:
        for state in selected:
            provider_id = str(state.get("provider_id") or "")
            if not state.get("production_ready"):
                smoke_results[provider_id] = {
                    "ok": False,
                    "error": (
                        "structural production preflight failed; "
                        "smoke render was not attempted"
                    ),
                }
                continue
            provider = registry.get(provider_id)
            if not isinstance(provider, ComfyPageProvider):
                smoke_results[provider_id] = {
                    "ok": False,
                    "error": "not a ComfyUI page provider",
                }
                continue
            try:
                smoke_results[provider_id] = {"ok": True, **_smoke(provider)}
            except Exception as exc:  # the CLI must turn any backend failure into a clear result
                smoke_results[provider_id] = {
                    "ok": False,
                    "error": f"{type(exc).__name__}: {exc}",
                }

    if args.json:
        payload: dict[str, Any] = {"backends": selected}
        if args.smoke:
            payload["smoke"] = smoke_results
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        for index, state in enumerate(selected):
            if index:
                print()
            _print_state(state)
            if args.smoke:
                result = smoke_results.get(str(state.get("provider_id") or ""), {})
                print(f"  smoke render: {'PASS' if result.get('ok') else 'FAIL'}")
                if result.get("ok"):
                    master_size = result.get("master_size")
                    master_sha = result.get("master_sha256")
                    print(f"    master: {master_size} · {master_sha}")
                    print(
                        "    identity refs sent: "
                        + ", ".join(
                            str(v)
                            for v in result.get("identity_references_sent") or []
                        )
                    )
                elif result.get("error"):
                    print(f"    error: {result['error']}")

    structurally_ready = [state for state in selected if bool(state.get("production_ready"))]
    if not structurally_ready:
        return 1
    if args.smoke and not any(result.get("ok") for result in smoke_results.values()):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
