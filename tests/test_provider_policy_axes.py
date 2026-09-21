"""Where work runs and what it costs are different questions.

The failure this prevents is the expensive one: turning on a free GPU session
somewhere else and thereby also turning on a provider that bills a card. Every
case here is about keeping those two decisions apart, and about never letting a
refusal turn into a quiet escalation.
"""

from __future__ import annotations

import pytest
from continuum_config import LocalityPolicy, ProductionProfile, Settings, SpendPolicy
from continuum_core import BlockedReason, ProviderUnavailableError
from continuum_providers.contracts import (
    Capability,
    CostClass,
    DataClass,
    Locality,
    PrivacyClass,
    ProviderDescriptor,
)
from continuum_providers.policy import ProviderPolicy
from continuum_providers.registry import ProviderRegistry

CAP = Capability.IMAGE_GENERATE


def _d(
    provider_id: str,
    locality: Locality,
    cost: CostClass,
    capability: Capability = CAP,
) -> ProviderDescriptor:
    return ProviderDescriptor(
        id=provider_id,
        capabilities=frozenset({capability}),
        locality=locality,
        cost_class=cost,
        privacy_class=(
            PrivacyClass.ON_DEVICE if locality is Locality.LOCAL else PrivacyClass.THIRD_PARTY
        ),
    )


LOCAL_FREE = _d("local.free", Locality.LOCAL, CostClass.FREE)
REMOTE_FREE = _d("remote.free", Locality.REMOTE, CostClass.FREE)
REMOTE_PAID = _d("remote.paid", Locality.REMOTE, CostClass.PAID)
REMOTE_PAID_DEAR = _d("remote.paid-premium", Locality.REMOTE, CostClass.PAID)


def test_free_remote_compute_is_allowed_without_allowing_anything_paid() -> None:
    """A GPU someone opened in a notebook is remote and costs nothing."""
    policy = ProviderPolicy(locality=LocalityPolicy.REMOTE_ALLOWED, spend=SpendPolicy.FREE_ONLY)
    decision = policy.evaluate(CAP, DataClass.PROJECT_MEDIA, [REMOTE_FREE, REMOTE_PAID])
    assert decision.permitted and decision.provider_id == "remote.free"


def test_free_only_can_never_select_a_paid_provider() -> None:
    policy = ProviderPolicy(locality=LocalityPolicy.REMOTE_ALLOWED, spend=SpendPolicy.FREE_ONLY)
    decision = policy.evaluate(CAP, DataClass.PROJECT_MEDIA, [REMOTE_PAID])
    assert decision.blocked
    assert decision.blocked_reason is BlockedReason.AWAITING_APPROVAL
    assert decision.remediation is not None
    assert decision.remediation["blocked_by"] == ["spend"]


def test_paid_allowed_without_remote_still_refuses_a_remote_provider() -> None:
    policy = ProviderPolicy(
        locality=LocalityPolicy.LOCAL_ONLY, spend=SpendPolicy.PAID_ALLOWED_WITH_CAP
    )
    decision = policy.evaluate(CAP, DataClass.PROJECT_MEDIA, [REMOTE_PAID])
    assert decision.blocked
    assert decision.remediation is not None
    assert decision.remediation["blocked_by"] == ["locality"]


def test_a_paid_provider_failing_does_not_hand_the_work_to_a_dearer_one() -> None:
    """Resolution picks one provider. There is no fallback ladder to climb."""
    registry = ProviderRegistry(
        ProviderPolicy(
            locality=LocalityPolicy.REMOTE_ALLOWED, spend=SpendPolicy.PAID_ALLOWED_WITH_CAP
        )
    )

    class Stub:
        def __init__(self, descriptor: ProviderDescriptor) -> None:
            self.descriptor = descriptor
            self.calls = 0

        def generate_image(self, request: object) -> None:
            self.calls += 1
            raise RuntimeError("the paid provider failed")

    cheap, dear = Stub(REMOTE_PAID), Stub(REMOTE_PAID_DEAR)
    registry.register(cheap)
    registry.register(dear)
    chosen = registry.resolve(CAP, DataClass.PROJECT_MEDIA)
    assert chosen is cheap
    with pytest.raises(RuntimeError):
        chosen.generate_image(object())  # type: ignore[attr-defined]
    # Nothing re-resolved; the dearer provider was never touched.
    assert dear.calls == 0


def test_selection_is_deterministic_and_prefers_local_then_free() -> None:
    policy = ProviderPolicy(
        locality=LocalityPolicy.REMOTE_ALLOWED, spend=SpendPolicy.PAID_ALLOWED_WITH_CAP
    )
    pool = [REMOTE_PAID, REMOTE_FREE, LOCAL_FREE]
    first = policy.evaluate(CAP, DataClass.PROJECT_MEDIA, pool)
    second = policy.evaluate(CAP, DataClass.PROJECT_MEDIA, list(reversed(pool)))
    assert first.provider_id == second.provider_id == "local.free"


def test_a_source_excerpt_stays_local_whatever_the_policies_say() -> None:
    policy = ProviderPolicy(
        locality=LocalityPolicy.REMOTE_ALLOWED, spend=SpendPolicy.PAID_ALLOWED_WITH_CAP
    )
    decision = policy.evaluate(CAP, DataClass.SOURCE_EXCERPT, [REMOTE_FREE, REMOTE_PAID])
    assert decision.blocked
    assert decision.remediation is not None
    assert "never be sent to a remote provider" in str(decision.remediation["message"])


@pytest.mark.parametrize(
    ("profile", "expected"),
    [
        (ProductionProfile.FREE_LOCAL, (LocalityPolicy.LOCAL_ONLY, SpendPolicy.FREE_ONLY)),
        (
            ProductionProfile.BALANCED_LOCAL,
            (LocalityPolicy.LOCAL_ONLY, SpendPolicy.METERED_ALLOWED),
        ),
        (
            ProductionProfile.HYBRID_OPTIONAL,
            (LocalityPolicy.REMOTE_ALLOWED, SpendPolicy.PAID_ALLOWED_WITH_CAP),
        ),
    ],
)
def test_a_profile_is_just_a_named_pair_of_policies(
    profile: ProductionProfile, expected: tuple[LocalityPolicy, SpendPolicy]
) -> None:
    policy = ProviderPolicy(profile)
    assert (policy.locality, policy.spend) == expected


def test_settings_may_override_one_axis_without_touching_the_other() -> None:
    settings = Settings(
        _env_file=None,
        data_home="/tmp/continuum-test",
        production_profile=ProductionProfile.FREE_LOCAL,
        locality_policy=LocalityPolicy.REMOTE_ALLOWED,
    )
    policy = ProviderPolicy.from_settings(settings)
    assert policy.locality is LocalityPolicy.REMOTE_ALLOWED
    assert policy.spend is SpendPolicy.FREE_ONLY
    assert policy.allows(REMOTE_FREE) and not policy.allows(REMOTE_PAID)


def test_an_unregistered_capability_is_a_missing_provider_not_an_approval() -> None:
    registry = ProviderRegistry(ProviderPolicy())
    with pytest.raises(ProviderUnavailableError) as raised:
        registry.resolve(Capability.VIDEO_GENERATE, DataClass.PROJECT_MEDIA)
    assert raised.value.context["blocked_reason"] == BlockedReason.MISSING_PROVIDER.value
