"""Acceptance 110.12 - providers work with fakes; no cloud credentials.

Runs entirely offline with an empty environment. The strongest assertion
here is the negative one: under ``FREE_LOCAL`` there is no code path to a
paid or remote provider, so a fake "expensive" provider is registered and
asserted never to be selected.
"""

from __future__ import annotations

import pytest
from continuum_config import ProductionProfile
from continuum_core import ProviderUnavailableError
from continuum_db.enums import BlockedReason
from continuum_providers import (
    Capability,
    CostClass,
    DataClass,
    GenerationRequest,
    Locality,
    PrivacyClass,
    ProviderDescriptor,
    ProviderPolicy,
    ProviderRegistry,
    build_default_registry,
)


class _ExpensiveRemoteProvider:
    """A trap. Selecting this under FREE_LOCAL would be the worst possible
    bug in a product whose default operating profile is $0."""

    invoked = False

    descriptor = ProviderDescriptor(
        id="trap.expensive-remote",
        capabilities=frozenset({Capability.TEXT_GENERATE, Capability.VIDEO_GENERATE}),
        locality=Locality.REMOTE,
        cost_class=CostClass.PAID,
        privacy_class=PrivacyClass.THIRD_PARTY,
        model_ref="trap-model",
        version="1",
    )

    def generate(self, request: GenerationRequest):
        type(self).invoked = True
        raise AssertionError("a PAID/REMOTE provider was invoked under FREE_LOCAL")


@pytest.fixture(autouse=True)
def _reset_trap() -> None:
    _ExpensiveRemoteProvider.invoked = False


class TestDefaultRegistryIsLocalAndFree:
    def test_every_default_provider_is_local_and_free(self) -> None:
        for descriptor in build_default_registry().descriptors():
            assert descriptor.locality is Locality.LOCAL
            assert descriptor.cost_class is CostClass.FREE
            assert descriptor.privacy_class is PrivacyClass.ON_DEVICE

    def test_no_default_provider_declares_a_model_ref(self) -> None:
        """D-12: Phase 0 downloads no model and pins no model identity."""
        assert all(d.model_ref is None for d in build_default_registry().descriptors())

    def test_text_generation_works_offline(self) -> None:
        provider = build_default_registry().resolve(Capability.TEXT_GENERATE, DataClass.SYNTHETIC)
        result = provider.generate(  # type: ignore[attr-defined]
            GenerationRequest(data_class=DataClass.SYNTHETIC, prompt="hello")
        )
        assert result.text == "hello"
        assert result.provider_id == "fake.echo-text"

    def test_embeddings_are_deterministic(self) -> None:
        """A crash-resumed unit must reproduce identical output, or effect
        idempotency (ADR-0002 s.2) does not hold for embedding jobs."""
        registry = build_default_registry()
        provider = registry.resolve(Capability.EMBED_TEXT, DataClass.SYNTHETIC)
        request = GenerationRequest(data_class=DataClass.SYNTHETIC, prompt="stable")
        first = provider.embed(request)  # type: ignore[attr-defined]
        second = provider.embed(request)  # type: ignore[attr-defined]
        assert first.vector == second.vector
        assert first.vector is not None and len(first.vector) == 16


class TestFreeLocalNeverEscalates:
    def test_paid_remote_provider_is_never_selected(self) -> None:
        registry = build_default_registry(ProviderPolicy(ProductionProfile.FREE_LOCAL))
        registry.register(_ExpensiveRemoteProvider())

        decision = registry.evaluate(Capability.TEXT_GENERATE, DataClass.PROJECT_TEXT)
        assert decision.permitted
        assert decision.provider_id == "fake.echo-text"
        assert _ExpensiveRemoteProvider.invoked is False

    def test_capability_only_a_paid_provider_offers_blocks_for_approval(self) -> None:
        """It does not fall back, and it does not fail silently: it parks
        with AWAITING_APPROVAL so the user decides (Master Plan s.103)."""
        registry = build_default_registry(ProviderPolicy(ProductionProfile.FREE_LOCAL))
        registry.register(_ExpensiveRemoteProvider())

        decision = registry.evaluate(Capability.VIDEO_GENERATE, DataClass.PROJECT_TEXT)
        assert decision.blocked
        assert decision.blocked_reason is BlockedReason.AWAITING_APPROVAL
        assert _ExpensiveRemoteProvider.invoked is False
        assert "REMOTE/PAID" in str(decision.remediation)

    def test_hybrid_profile_may_select_it_once_explicitly_chosen(self) -> None:
        registry = build_default_registry(ProviderPolicy(ProductionProfile.HYBRID_OPTIONAL))
        registry.register(_ExpensiveRemoteProvider())
        decision = registry.evaluate(Capability.VIDEO_GENERATE, DataClass.PROJECT_TEXT)
        assert decision.permitted
        assert decision.provider_id == "trap.expensive-remote"

    def test_local_is_preferred_even_when_both_are_permitted(self) -> None:
        registry = build_default_registry(ProviderPolicy(ProductionProfile.HYBRID_OPTIONAL))
        registry.register(_ExpensiveRemoteProvider())
        decision = registry.evaluate(Capability.TEXT_GENERATE, DataClass.PROJECT_TEXT)
        assert decision.provider_id == "fake.echo-text"


class TestPrivacyBeatsEverything:
    def test_source_excerpt_never_goes_remote_even_on_a_permissive_profile(self) -> None:
        """Master Plan section 40 / section 2.8. Privacy is filtered before
        cost, so a cheaper remote option can never win."""
        registry = ProviderRegistry(ProviderPolicy(ProductionProfile.SHOWCASE_OPTIONAL))
        registry.register(_ExpensiveRemoteProvider())

        decision = registry.evaluate(Capability.TEXT_GENERATE, DataClass.SOURCE_EXCERPT)
        assert decision.blocked
        assert decision.blocked_reason is BlockedReason.MISSING_PROVIDER
        assert "never be sent to a remote provider" in str(decision.remediation)
        assert _ExpensiveRemoteProvider.invoked is False

    def test_project_text_may_go_remote_when_the_profile_permits(self) -> None:
        registry = ProviderRegistry(ProviderPolicy(ProductionProfile.HYBRID_OPTIONAL))
        registry.register(_ExpensiveRemoteProvider())
        assert registry.evaluate(Capability.TEXT_GENERATE, DataClass.PROJECT_TEXT).permitted


class TestBlockedIsActionable:
    def test_missing_capability_names_a_remediation(self) -> None:
        decision = build_default_registry().evaluate(Capability.VIDEO_GENERATE, DataClass.SYNTHETIC)
        assert decision.blocked
        assert decision.blocked_reason is BlockedReason.MISSING_PROVIDER
        remediation = decision.remediation or {}
        assert remediation.get("capability") == Capability.VIDEO_GENERATE.value
        assert remediation.get("action")

    def test_resolve_raises_with_the_reason_attached(self) -> None:
        with pytest.raises(ProviderUnavailableError) as excinfo:
            build_default_registry().resolve(Capability.VIDEO_GENERATE, DataClass.SYNTHETIC)
        assert excinfo.value.context.get("blocked_reason") == BlockedReason.MISSING_PROVIDER.value
        assert excinfo.value.remediation

    def test_selection_success_and_invocation_failure_stay_distinguishable(self) -> None:
        """The null image provider is selectable but refuses to run; the two
        failure modes need different remediation."""
        registry = build_default_registry()
        provider = registry.resolve(Capability.IMAGE_GENERATE, DataClass.SYNTHETIC)
        with pytest.raises(ProviderUnavailableError) as excinfo:
            provider.generate_image(  # type: ignore[attr-defined]
                GenerationRequest(data_class=DataClass.SYNTHETIC)
            )
        assert "Phase 10" in (excinfo.value.remediation or "")


class TestNoAiSdkIsInstalled:
    @pytest.mark.parametrize(
        "module",
        [
            "openai",
            "anthropic",
            "google.generativeai",
            "cohere",
            "mistralai",
            "torch",
            "transformers",
            "faster_whisper",
            "ctranslate2",
            "llama_cpp",
            "ollama",
        ],
    )
    def test_vendor_sdk_absent(self, module: str) -> None:
        """D-12 verified by inventory, not by auditing code paths."""
        import importlib.util

        try:
            spec = importlib.util.find_spec(module)
        except ModuleNotFoundError:
            # find_spec raises rather than returning None when a PARENT
            # package is missing (e.g. "google" for "google.generativeai").
            # That is still absence, which is what this test asserts.
            return

        assert spec is None, (
            f"{module} is installed. Phase 0 must ship no AI SDK "
            "(FOUNDATION_APPROVAL D-12); this makes 110.12 checkable from "
            "docs/DEPENDENCIES.md alone."
        )
