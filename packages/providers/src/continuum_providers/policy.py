"""Provider selection policy (ADR-0004 section 3).

**The single most damaging possible bug in a $0-default product would be
silently escalating to a paid provider.** There is deliberately no code path
from a ``FREE_LOCAL`` profile to a ``PAID`` or ``REMOTE`` provider. When no
permitted provider can satisfy a capability, resolution returns a blocked
decision naming the reason -- it never falls back and never fails silently.

Master Plan section 50's cost tiers are reinterpreted accordingly: they are
escalation options *gated by the active profile*, not a default pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass

from continuum_config import ProductionProfile
from continuum_core import BlockedReason

from continuum_providers.contracts import (
    Capability,
    CostClass,
    DataClass,
    Locality,
    ProviderDescriptor,
)

__all__ = ["PolicyDecision", "ProviderPolicy", "profile_allows"]


#: What each production profile permits. FREE_LOCAL is the shipped default
#: (Master Plan section 90) and admits nothing remote and nothing paid.
_PROFILE_RULES: dict[ProductionProfile, tuple[frozenset[Locality], frozenset[CostClass]]] = {
    ProductionProfile.FREE_LOCAL: (
        frozenset({Locality.LOCAL}),
        frozenset({CostClass.FREE}),
    ),
    ProductionProfile.BALANCED_LOCAL: (
        frozenset({Locality.LOCAL}),
        frozenset({CostClass.FREE, CostClass.METERED}),
    ),
    ProductionProfile.HYBRID_OPTIONAL: (
        frozenset({Locality.LOCAL, Locality.REMOTE}),
        frozenset({CostClass.FREE, CostClass.METERED, CostClass.PAID}),
    ),
    ProductionProfile.SHOWCASE_OPTIONAL: (
        frozenset({Locality.LOCAL, Locality.REMOTE}),
        frozenset({CostClass.FREE, CostClass.METERED, CostClass.PAID}),
    ),
}

#: Data classes that must never leave the machine, regardless of profile.
#: Verbatim third-party source material is the one Continuum is most
#: obliged to protect (Master Plan section 40, section 2.8).
_NEVER_REMOTE: frozenset[DataClass] = frozenset({DataClass.SOURCE_EXCERPT})


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    """The outcome of resolving a capability to a provider."""

    provider_id: str | None
    permitted: bool
    blocked_reason: BlockedReason | None = None
    remediation: dict[str, object] | None = None

    @property
    def blocked(self) -> bool:
        return not self.permitted


def profile_allows(profile: ProductionProfile, descriptor: ProviderDescriptor) -> bool:
    """Whether a profile permits this provider at all."""
    localities, costs = _PROFILE_RULES[profile]
    return descriptor.locality in localities and descriptor.cost_class in costs


class ProviderPolicy:
    """Resolves (capability, data class, profile) to a permitted provider."""

    def __init__(self, profile: ProductionProfile = ProductionProfile.FREE_LOCAL) -> None:
        self.profile = profile

    def evaluate(
        self,
        capability: Capability,
        data_class: DataClass,
        candidates: list[ProviderDescriptor],
    ) -> PolicyDecision:
        capable = [d for d in candidates if d.supports(capability)]
        if not capable:
            return PolicyDecision(
                provider_id=None,
                permitted=False,
                blocked_reason=BlockedReason.MISSING_PROVIDER,
                remediation={
                    "message": f"No provider offers the {capability.value} capability.",
                    "capability": capability.value,
                    "action": (
                        "Register a provider for this capability in the provider registry, "
                        "or install the local model it requires."
                    ),
                },
            )

        # Privacy first: a class that must stay on-device is filtered before
        # cost is even considered, so a cheaper remote option can never win.
        if data_class in _NEVER_REMOTE:
            capable = [d for d in capable if d.locality is Locality.LOCAL]
            if not capable:
                return PolicyDecision(
                    provider_id=None,
                    permitted=False,
                    blocked_reason=BlockedReason.MISSING_PROVIDER,
                    remediation={
                        "message": (
                            f"{data_class.value} may never be sent to a remote provider, "
                            f"and no local provider offers {capability.value}."
                        ),
                        "capability": capability.value,
                        "data_class": data_class.value,
                        "action": "Install a local provider for this capability.",
                    },
                )

        permitted = [d for d in capable if profile_allows(self.profile, d)]
        if not permitted:
            offered = sorted({f"{d.locality.value}/{d.cost_class.value}" for d in capable})
            return PolicyDecision(
                provider_id=None,
                permitted=False,
                # Approval, not a missing provider: something CAN do this, but
                # the active profile forbids it. The user decides, explicitly.
                blocked_reason=BlockedReason.AWAITING_APPROVAL,
                remediation={
                    "message": (
                        f"The {self.profile.value} profile does not permit any provider that "
                        f"offers {capability.value}."
                    ),
                    "capability": capability.value,
                    "available_but_not_permitted": offered,
                    "action": (
                        "Approve a different production profile explicitly. Continuum will "
                        "not switch to a paid or remote provider on its own "
                        "(Master Plan section 103)."
                    ),
                },
            )

        # Prefer local, then free, then a stable id order so selection is
        # deterministic and reproducible across runs.
        permitted.sort(
            key=lambda d: (
                d.locality is not Locality.LOCAL,
                d.cost_class is not CostClass.FREE,
                d.id,
            )
        )
        return PolicyDecision(provider_id=permitted[0].id, permitted=True)
