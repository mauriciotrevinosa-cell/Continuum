"""Provider selection policy (ADR-0004 section 3).

**The single most damaging possible bug in a $0-default product would be
silently escalating to a paid provider.** There is deliberately no code path
from a free profile to a ``PAID`` provider. When no permitted provider can
satisfy a capability, resolution returns a blocked decision naming the reason
-- it never falls back, never retries elsewhere and never fails silently.

Selection turns on two **independent** axes, because conflating them is how a
$0 product accidentally spends money:

* **locality** - may the work leave this machine? A GPU session the creator
  opened in a notebook is remote and costs nothing;
* **spend** - may the work cost money? A cheap API is nobody's local machine
  and bills on every call.

A production profile is just a named pair of the two. Either may be set on its
own, so "use the free remote GPU, never pay for anything" is expressible, and
allowing one never widens the other.

Master Plan section 50's cost tiers are escalation options *gated by these
policies*, not a default pipeline.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from continuum_config import (
    PROFILE_POLICIES,
    LocalityPolicy,
    ProductionProfile,
    Settings,
    SpendPolicy,
    policies,
)
from continuum_core import BlockedReason

from continuum_providers.contracts import (
    Capability,
    CostClass,
    DataClass,
    Locality,
    ProviderDescriptor,
)

__all__ = [
    "PolicyDecision",
    "ProviderPolicy",
    "policy_allows",
    "profile_allows",
    "reference_data_class",
    "transmission_refusal",
]


#: Where each locality policy lets work run. LOCAL_ONLY is the shipped default
#: (Master Plan section 90).
_LOCALITIES: dict[LocalityPolicy, frozenset[Locality]] = {
    LocalityPolicy.LOCAL_ONLY: frozenset({Locality.LOCAL}),
    LocalityPolicy.REMOTE_ALLOWED: frozenset({Locality.LOCAL, Locality.REMOTE}),
}
#: What each spend policy lets work cost. Remote compute the creator opened is
#: FREE, so REMOTE_ALLOWED + FREE_ONLY is a real, useful combination: a free GPU
#: session may be used while nothing can bill a card.
_COSTS: dict[SpendPolicy, frozenset[CostClass]] = {
    SpendPolicy.FREE_ONLY: frozenset({CostClass.FREE}),
    SpendPolicy.METERED_ALLOWED: frozenset({CostClass.FREE, CostClass.METERED}),
    SpendPolicy.PAID_ALLOWED_WITH_CAP: frozenset(
        {CostClass.FREE, CostClass.METERED, CostClass.PAID}
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


def policy_allows(
    locality: LocalityPolicy, spend: SpendPolicy, descriptor: ProviderDescriptor
) -> bool:
    """Whether the two policies together permit this provider at all."""
    return descriptor.locality in _LOCALITIES[locality] and descriptor.cost_class in _COSTS[spend]


def profile_allows(profile: ProductionProfile, descriptor: ProviderDescriptor) -> bool:
    """Whether a profile's default pair of policies permits this provider."""
    locality, spend = PROFILE_POLICIES[profile]
    return policy_allows(locality, spend, descriptor)


class ProviderPolicy:
    """Resolves (capability, data class, policies) to a permitted provider.

    Locality and spend are separate axes. A profile names a pair of them; either
    can be overridden on its own, and nothing in resolution can widen them.
    """

    def __init__(
        self,
        profile: ProductionProfile = ProductionProfile.FREE_LOCAL,
        *,
        locality: LocalityPolicy | None = None,
        spend: SpendPolicy | None = None,
    ) -> None:
        self.profile = profile
        default_locality, default_spend = PROFILE_POLICIES[profile]
        self.locality = locality or default_locality
        self.spend = spend or default_spend

    @classmethod
    def from_settings(cls, settings: Settings) -> ProviderPolicy:
        locality, spend = policies(settings)
        return cls(settings.production_profile, locality=locality, spend=spend)

    def allows(self, descriptor: ProviderDescriptor) -> bool:
        return policy_allows(self.locality, self.spend, descriptor)

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

        permitted = [d for d in capable if self.allows(d)]
        if not permitted:
            offered = sorted({f"{d.locality.value}/{d.cost_class.value}" for d in capable})
            return PolicyDecision(
                provider_id=None,
                permitted=False,
                # Approval, not a missing provider: something CAN do this, but
                # the active policies forbid it. The user decides, explicitly.
                blocked_reason=BlockedReason.AWAITING_APPROVAL,
                remediation={
                    "message": (
                        f"No provider offering {capability.value} is permitted by the current "
                        f"{self.locality.value} / {self.spend.value} policies."
                    ),
                    "capability": capability.value,
                    "available_but_not_permitted": offered,
                    "locality_policy": self.locality.value,
                    "spend_policy": self.spend.value,
                    "blocked_by": _blocking_axes(self.locality, self.spend, capable),
                    "action": (
                        "Change the policy that blocks this explicitly - allowing remote "
                        "compute and allowing money to be spent are separate decisions. "
                        "Continuum never widens either on its own "
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


#: Reference origins whose images are someone else's published work.
_THIRD_PARTY_ORIGINS = frozenset({"SOURCE", "OFFICIAL_ART", "FAN_ART"})
#: Corpus authorities that mean "the source work or its official art".
_THIRD_PARTY_AUTHORITIES = frozenset({"PRIMARY_SOURCE", "OFFICIAL"})
#: Origins the user or the project produced.
_PROJECT_ORIGINS = frozenset({"USER_CREATED", "GENERATED", "PROJECT_APPROVED"})


def reference_data_class(provenance: Mapping[str, Any]) -> DataClass:
    """What a reference image is, judged from the provenance snapshotted with it.

    Fails closed: an image whose provenance does not say it is the project's own
    is treated as a verbatim source excerpt.
    """
    origin = str(provenance.get("origin") or "")
    authority = str(provenance.get("authority") or "")
    if (
        origin in _THIRD_PARTY_ORIGINS
        or authority in _THIRD_PARTY_AUTHORITIES
        or provenance.get("kind") == "source_page"
    ):
        return DataClass.SOURCE_EXCERPT
    if origin in _PROJECT_ORIGINS or authority in {"PROJECT_CREATED", "CREATOR_PRIMARY"}:
        return DataClass.PROJECT_MEDIA
    if provenance.get("attempt_id") and provenance.get("sha256"):
        # A Continuum stage or page output (an upstream stage, a frozen finish).
        return DataClass.PROJECT_MEDIA
    return DataClass.SOURCE_EXCERPT


def transmission_refusal(
    provenance: Mapping[str, Any],
    locality: Locality,
    *,
    source_excerpts_allowed: bool = False,
) -> str | None:
    """Why one reference may not be sent to a provider at this locality, or None.

    The per-reference form of the rule that ``SOURCE_EXCERPT`` never leaves the
    machine: a remote request keeps every reference it may receive, and each one
    it may not is withheld (and recorded) instead of blocking the whole request.
    """
    if locality is Locality.LOCAL:
        return None
    data_class = reference_data_class(provenance)
    if data_class in _NEVER_REMOTE and not source_excerpts_allowed:
        if not provenance.get("origin") and not provenance.get("authority"):
            return (
                "its provenance does not show it is the project's own; treated as a source excerpt"
            )
        return "a source excerpt (third-party published work) never leaves this machine"
    return None


def _blocking_axes(
    locality: LocalityPolicy, spend: SpendPolicy, capable: list[ProviderDescriptor]
) -> list[str]:
    """Which axis is actually in the way, so the message names the real gate."""
    axes = []
    if any(policy_allows(LocalityPolicy.REMOTE_ALLOWED, spend, d) for d in capable):
        axes.append("locality")
    if any(policy_allows(locality, SpendPolicy.PAID_ALLOWED_WITH_CAP, d) for d in capable):
        axes.append("spend")
    return axes
