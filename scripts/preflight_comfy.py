"""Probe configured ComfyUI backends for real manga-production readiness.

This is stricter than the provider's generic ``ready`` flag. A server can be
healthy enough to render a generic image while still being unsuitable for
Continuum manga because character identity conditioning or reproducibility
metadata is missing.

Examples::

    uv run --no-sync python scripts/preflight_comfy.py
    uv run --no-sync python scripts/preflight_comfy.py --backend local
    uv run --no-sync python scripts/preflight_comfy.py --backend remote --json

Exit status is zero only when at least one selected Comfy backend is production
ready. No model is downloaded and no setting is changed.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from continuum_config import get_settings
from continuum_providers import artwork_backends, build_default_registry


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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--backend", choices=("local", "remote", "any"), default="any")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args(argv)

    settings = get_settings()
    registry = build_default_registry(settings=settings)
    selected = _selected(artwork_backends(registry, settings), args.backend)

    if args.json:
        print(json.dumps({"backends": selected}, indent=2, sort_keys=True))
    else:
        for index, state in enumerate(selected):
            if index:
                print()
            _print_state(state)

    return 0 if any(bool(state.get("production_ready")) for state in selected) else 1


if __name__ == "__main__":
    sys.exit(main())
