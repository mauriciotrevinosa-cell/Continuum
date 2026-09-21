"""Provider registry - THE ONLY place a model identifier may appear.

ADR-0004 section 4: no model identifier literal exists outside this package
and ``/config``. ``tests/invariants/test_no_model_literals.py`` enforces it,
which turns Master Plan section 90's "no specific AI model hardcoded as
mandatory" from an aspiration into a test.

Phase 0 registers deterministic fakes only. No vendor SDK is installed at
all (D-12), which makes acceptance test 110.12 verifiable by reading
docs/DEPENDENCIES.md rather than by auditing code paths.
"""

from __future__ import annotations

from typing import Any

from continuum_core import BlockedReason, ProviderUnavailableError

from continuum_providers.contracts import Capability, DataClass, Provider, ProviderDescriptor
from continuum_providers.policy import PolicyDecision, ProviderPolicy

__all__ = [
    "ProviderRegistry",
    "artwork_backends",
    "artwork_production_gaps",
    "build_default_registry",
]


class ProviderRegistry:
    """Holds registered providers and resolves capabilities through policy."""

    def __init__(self, policy: ProviderPolicy | None = None) -> None:
        self._providers: dict[str, Provider] = {}
        self.policy = policy or ProviderPolicy()

    def register(self, provider: Provider) -> Provider:
        descriptor = provider.descriptor
        if descriptor.id in self._providers:
            raise ValueError(f"duplicate provider id {descriptor.id!r}")
        self._providers[descriptor.id] = provider
        return provider

    def descriptors(self) -> list[ProviderDescriptor]:
        return [p.descriptor for p in self._providers.values()]

    def get(self, provider_id: str) -> Provider:
        try:
            return self._providers[provider_id]
        except KeyError:
            raise ProviderUnavailableError(
                f"No provider registered with id {provider_id!r}.",
                technical_detail=f"registered: {sorted(self._providers)}",
            ) from None

    def evaluate(self, capability: Capability, data_class: DataClass) -> PolicyDecision:
        """Decide which provider may serve this call, without invoking it."""
        return self.policy.evaluate(capability, data_class, self.descriptors())

    def resolve(self, capability: Capability, data_class: DataClass) -> Provider:
        """Return the permitted provider, or raise with an actionable reason."""
        decision = self.evaluate(capability, data_class)
        if not decision.permitted or decision.provider_id is None:
            reason = decision.blocked_reason or BlockedReason.MISSING_PROVIDER
            remediation = dict(decision.remediation or {})
            message = str(remediation.pop("message", "No permitted provider."))
            action = str(remediation.pop("action", ""))
            raise ProviderUnavailableError(
                message,
                technical_detail=f"capability={capability.value} data_class={data_class.value}",
                remediation=action,
                blocked_reason=reason.value,
                **remediation,
            )
        return self.get(decision.provider_id)

    def resolve_named(
        self, provider_id: str, capability: Capability, data_class: DataClass
    ) -> Provider:
        """A provider the caller chose by name, still checked against the policy.

        Automatic resolution prefers local and free, which is right for
        ordinary work and wrong when a person has deliberately chosen a
        specific backend - a paid tier for one authority render, a particular
        GPU for a comparison. Naming it skips the *preference*, never the
        rules: an unregistered id, a capability it does not offer, a data
        class it may not receive or a policy that forbids it all refuse here
        exactly as they would in :meth:`resolve`.
        """
        provider = self.get(provider_id)
        descriptor = provider.descriptor
        if not descriptor.supports(capability):
            raise ProviderUnavailableError(
                f"{provider_id} does not offer {capability.value}.",
                technical_detail=f"offers: {sorted(c.value for c in descriptor.capabilities)}",
                remediation="Name a provider that does, or use automatic resolution.",
                blocked_reason=BlockedReason.MISSING_PROVIDER.value,
            )
        decision = self.policy.evaluate(capability, data_class, [descriptor])
        if not decision.permitted:
            remediation = dict(decision.remediation or {})
            message = str(remediation.pop("message", f"{provider_id} is not permitted."))
            action = str(remediation.pop("action", ""))
            raise ProviderUnavailableError(
                message,
                technical_detail=f"provider={provider_id} data_class={data_class.value}",
                remediation=action,
                blocked_reason=(decision.blocked_reason or BlockedReason.MISSING_PROVIDER).value,
                **remediation,
            )
        return provider

    def summary(self) -> list[dict[str, object]]:
        """Non-secret provider inventory for /health."""
        return [
            {
                "id": d.id,
                "capabilities": sorted(c.value for c in d.capabilities),
                "locality": d.locality.value,
                "cost_class": d.cost_class.value,
                "privacy_class": d.privacy_class.value,
                "model_ref": d.model_ref,
                "version": d.version,
            }
            for d in sorted(self.descriptors(), key=lambda d: d.id)
        ]


def build_default_registry(
    policy: ProviderPolicy | None = None, settings: Any | None = None
) -> ProviderRegistry:
    """The default registry: deterministic fakes, plus configured ComfyUI backends.

    Phase 1 adds the deterministic sketch renderer for rough attempts. M3 adds
    ComfyUI page backends, registered only when their URL is configured, and a
    paid image provider registered only when the creator has configured both a
    key and a model. Registering a paid provider does not permit it: the spend
    policy decides that, separately from where work may run.
    """
    from continuum_providers.fakes import (
        DeterministicEmbeddingProvider,
        DeterministicPageProvider,
        DeterministicSketchProvider,
        DeterministicStageProvider,
        EchoTextProvider,
        NullImageProvider,
    )

    if policy is None and settings is not None:
        # Locality and spend come from the settings, so a free remote GPU can be
        # allowed without also allowing a paid API (and the reverse).
        policy = ProviderPolicy.from_settings(settings)
    registry = ProviderRegistry(policy)
    registry.register(EchoTextProvider())
    registry.register(DeterministicEmbeddingProvider())
    registry.register(NullImageProvider())
    registry.register(DeterministicSketchProvider())
    registry.register(DeterministicPageProvider())
    registry.register(DeterministicStageProvider())
    if settings is not None:
        from continuum_providers.comfy import configured_providers

        for provider in configured_providers(settings):
            registry.register(provider)

        from continuum_providers.google_images import configured_google_provider

        paid = configured_google_provider(settings)
        if paid is not None:
            registry.register(paid)
    return registry


def artwork_production_gaps(state: dict[str, Any]) -> list[str]:
    """What still prevents a real, identity-grounded manga render.

    ``ready`` intentionally remains the provider-level health check: Comfy can
    render a generic image when the core nodes and checkpoint are present.
    Manga production is stricter. It must also be able to condition character
    identity and record enough checkpoint/workflow metadata to reproduce the
    result later.
    """
    gaps: list[str] = []
    if not state.get("ready"):
        gaps.append(str(state.get("reason") or "backend is not ready"))
        return gaps
    if not state.get("identity_conditioning"):
        gaps.append("IP-Adapter identity conditioning nodes are not available")
    missing = [str(value) for value in state.get("model_metadata_missing") or []]
    if missing:
        gaps.append(f"checkpoint metadata is incomplete: {', '.join(missing)}")
    workflow = state.get("workflow")
    if not isinstance(workflow, dict) or not all(
        isinstance(workflow.get(key), str) and workflow.get(key)
        for key in ("id", "version", "sha256")
    ):
        gaps.append("workflow provenance metadata is incomplete")
    return gaps


def artwork_backends(
    registry: ProviderRegistry, settings: Any | None = None
) -> list[dict[str, Any]]:
    """Every artwork backend kind and its truthful state, configured or not."""
    from continuum_providers.artwork import ArtworkBackendKind
    from continuum_providers.comfy import ComfyPageProvider

    out: list[dict[str, Any]] = [
        {
            "kind": ArtworkBackendKind.TEST.value,
            "provider_id": "fake.deterministic-page",
            "configured": True,
            "reachable": True,
            "ready": True,
            "production_ready": False,
            "production_gaps": ["TEST renders are workflow diagrams, never manga artwork"],
            "output": "TEST_RENDER",
            "reason": "deterministic diagrams for workflow tests - never artwork",
        }
    ]
    registered = {
        d.id: registry.get(d.id) for d in registry.descriptors() if d.id.startswith("comfy.")
    }
    for kind, provider_id, url_field in (
        (ArtworkBackendKind.COMFY_LOCAL, "comfy.local", "comfy_local_url"),
        (ArtworkBackendKind.COMFY_REMOTE, "comfy.remote", "comfy_remote_url"),
    ):
        provider = registered.get(provider_id)
        if isinstance(provider, ComfyPageProvider):
            state = {**provider.status(refresh=True).as_dict(), "output": "ARTWORK_CANDIDATE"}
            gaps = artwork_production_gaps(state)
            state["production_ready"] = not gaps
            state["production_gaps"] = gaps
            out.append(state)
        else:
            reason = f"{kind.value} is not configured (set CONTINUUM_{url_field.upper()})"
            out.append(
                {
                    "kind": kind.value,
                    "provider_id": provider_id,
                    "configured": False,
                    "reachable": False,
                    "ready": False,
                    "production_ready": False,
                    "production_gaps": [reason],
                    "output": "ARTWORK_CANDIDATE",
                    "reason": reason,
                }
            )
    return out
