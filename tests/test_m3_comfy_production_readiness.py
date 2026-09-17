from continuum_providers.registry import artwork_production_gaps


def _healthy_state() -> dict[str, object]:
    return {
        "ready": True,
        "reason": "ready",
        "identity_conditioning": True,
        "model_metadata_missing": [],
        "workflow": {"id": "continuum.comfy.page", "version": "1", "sha256": "a" * 64},
    }


def test_manga_preflight_accepts_reproducible_identity_backend() -> None:
    assert artwork_production_gaps(_healthy_state()) == []


def test_manga_preflight_requires_identity_conditioning() -> None:
    state = _healthy_state()
    state["identity_conditioning"] = False
    assert artwork_production_gaps(state) == [
        "IP-Adapter identity conditioning nodes are not available"
    ]


def test_manga_preflight_requires_checkpoint_metadata() -> None:
    state = _healthy_state()
    state["model_metadata_missing"] = ["sha256", "license"]
    assert artwork_production_gaps(state) == [
        "checkpoint metadata is incomplete: sha256, license"
    ]


def test_manga_preflight_reports_core_backend_failure_first() -> None:
    state = _healthy_state()
    state.update(
        ready=False,
        reason="COMFY_LOCAL does not list the configured checkpoint 'missing.safetensors'",
        identity_conditioning=False,
        model_metadata_missing=["sha256"],
    )
    assert artwork_production_gaps(state) == [
        "COMFY_LOCAL does not list the configured checkpoint 'missing.safetensors'"
    ]
