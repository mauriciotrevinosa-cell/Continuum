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

from continuum_core import ProviderUnavailableError
from continuum_db.enums import BlockedReason

from continuum_providers.contracts import Capability, DataClass, Provider, ProviderDescriptor
from continuum_providers.policy import PolicyDecision, ProviderPolicy

__all__ = ["ProviderRegistry", "build_default_registry"]


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


def build_default_registry(policy: ProviderPolicy | None = None) -> ProviderRegistry:
    """The Phase 0 registry: deterministic fakes, nothing else."""
    from continuum_providers.fakes import (
        DeterministicEmbeddingProvider,
        EchoTextProvider,
        NullImageProvider,
    )

    registry = ProviderRegistry(policy)
    registry.register(EchoTextProvider())
    registry.register(DeterministicEmbeddingProvider())
    registry.register(NullImageProvider())
    return registry
