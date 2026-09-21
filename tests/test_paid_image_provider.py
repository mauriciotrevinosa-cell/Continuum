"""The paid image provider: configured, gated, and never called by accident.

No network is touched here. A fake transport records exactly what would have
been sent, which is the only way to check the things that matter before the
first real request: that the key travels in a header and nowhere else, that
the URL is built from configuration, that a source excerpt is refused before
transmission, and that money is held around the call rather than after it.
"""

from __future__ import annotations

import base64
import io
import json
from typing import Any

import pytest
from continuum_config import LocalityPolicy, Settings, SpendPolicy
from continuum_core import ContinuumError
from continuum_production.budget import BudgetExceededError, paid_call
from continuum_providers import build_default_registry
from continuum_providers.artwork import ArtworkReference
from continuum_providers.contracts import (
    Capability,
    CostClass,
    DataClass,
    GenerationRequest,
    Locality,
    PrivacyClass,
    ProviderDescriptor,
)
from continuum_providers.google_images import (
    GOOGLE_PROVIDER_ID,
    GoogleImageProvider,
    configured_google_provider,
    google_image_config,
)
from continuum_providers.policy import ProviderPolicy
from continuum_providers.pricing import PriceList
from PIL import Image

KEY = "not-a-real-key"


def _png(shade: int = 128) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (8, 8), (shade, shade, shade)).save(buffer, format="PNG")
    return buffer.getvalue()


class Recorder:
    """A transport that answers with one image and remembers the request."""

    def __init__(self, status: int = 200) -> None:
        self.calls: list[dict[str, Any]] = []
        self.status = status

    def __call__(
        self, method: str, url: str, body: bytes | None, headers: dict[str, str]
    ) -> tuple[int, bytes]:
        self.calls.append(
            {
                "method": method,
                "url": url,
                "headers": headers,
                "body": json.loads(body) if body else None,
            }
        )
        if self.status >= 400:
            return self.status, b'{"error": "refused"}'
        reply = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "inlineData": {
                                    "mimeType": "image/png",
                                    "data": base64.b64encode(_png()).decode(),
                                }
                            }
                        ]
                    }
                }
            ]
        }
        return 200, json.dumps(reply).encode()


def _settings(**extra: Any) -> Settings:
    return Settings(_env_file=None, data_home="/tmp/continuum-paid-test", **extra)


def _provider(transport: Recorder, **extra: Any) -> GoogleImageProvider:
    return GoogleImageProvider(
        google_image_config(_settings(google_api_key=KEY, **extra)), transport=transport
    )


# -- configuration -----------------------------------------------------------
def test_the_api_key_is_the_only_thing_the_creator_has_to_supply() -> None:
    plain = google_image_config(_settings())
    assert plain.missing() == ["CONTINUUM_GOOGLE_API_KEY"]
    assert plain.endpoint.startswith("https://") and plain.action
    assert plain.model_for("HIGH") and plain.model_for("CHEAP")
    assert plain.model_for("HIGH") != plain.model_for("CHEAP")
    with_key = google_image_config(_settings(google_api_key=KEY))
    assert with_key.missing() == [] and with_key.configured


def test_a_key_registers_the_provider_and_an_explicit_false_never_does() -> None:
    assert configured_google_provider(_settings()) is None
    assert configured_google_provider(_settings(google_api_key=KEY)) is not None
    off = _settings(google_api_key=KEY, google_images_enabled=False)
    assert configured_google_provider(off) is None


def test_the_registry_picks_it_up_from_settings_alone() -> None:
    registry = build_default_registry(settings=_settings(google_api_key=KEY))
    ids = {d.id for d in registry.descriptors()}
    assert GOOGLE_PROVIDER_ID in ids
    (paid,) = [d for d in registry.descriptors() if d.id == GOOGLE_PROVIDER_ID]
    assert paid.cost_class is CostClass.PAID
    assert paid.locality is Locality.REMOTE
    assert paid.privacy_class is PrivacyClass.THIRD_PARTY


def test_the_authority_tier_is_the_one_a_sheet_asks_for_by_default() -> None:
    """A production sheet is an anchor; it does not go to the exploration tier."""
    recorder = Recorder()
    provider = _provider(recorder)
    from continuum_providers.artwork import CharacterSheetRequest

    provider.render_character_sheet(
        CharacterSheetRequest(
            sheet_kind="HEAD",
            views=("FRONT",),
            width=1024,
            height=1024,
            seed=7,
            references=(),
            identity_rules=(),
            restrictions=(),
            outfit_id=None,
            settings={},
        )
    )
    settings = _settings()
    assert settings.google_image_model_high in recorder.calls[-1]["url"]
    assert settings.google_image_model_cheap not in recorder.calls[-1]["url"]


# -- the request on the wire -------------------------------------------------
def test_the_url_comes_from_configuration_and_the_key_from_a_header() -> None:
    recorder = Recorder()
    provider = _provider(recorder)
    provider.generate_image(
        GenerationRequest(data_class=DataClass.PROJECT_TEXT, prompt="a quiet room", seed=11)
    )
    (call,) = recorder.calls
    settings = _settings()
    expected = (
        f"{settings.google_image_endpoint}/{settings.google_image_model_cheap}"
        f":{settings.google_image_action}"
    )
    assert call["url"] == expected
    assert call["headers"]["x-goog-api-key"] == KEY
    # The secret never travels in the URL or the body.
    assert KEY not in call["url"]
    assert KEY not in json.dumps(call["body"])


def test_the_body_asks_for_an_image_and_carries_the_seed() -> None:
    recorder = Recorder()
    _provider(recorder).generate_image(
        GenerationRequest(data_class=DataClass.PROJECT_TEXT, prompt="a quiet room", seed=42)
    )
    body = recorder.calls[-1]["body"]
    assert body["contents"][0]["parts"][0]["text"] == "a quiet room"
    assert body["generationConfig"]["responseModalities"] == ["IMAGE"]
    assert body["generationConfig"]["seed"] == 42


def test_the_creator_can_override_the_generation_config_without_a_release() -> None:
    recorder = Recorder()
    provider = _provider(
        recorder,
        google_image_generation_config=json.dumps({"responseModalities": ["IMAGE"], "topK": 3}),
    )
    provider.generate_image(
        GenerationRequest(data_class=DataClass.PROJECT_TEXT, prompt="x", seed=1)
    )
    assert recorder.calls[-1]["body"]["generationConfig"]["topK"] == 3


def test_a_refusal_from_the_endpoint_is_reported_not_swallowed() -> None:
    provider = _provider(Recorder(status=429))
    with pytest.raises(ContinuumError, match="refused the request"):
        provider.generate_image(
            GenerationRequest(data_class=DataClass.PROJECT_TEXT, prompt="x", seed=1)
        )


def test_a_source_excerpt_never_reaches_the_paid_endpoint() -> None:
    recorder = Recorder()
    provider = _provider(recorder)
    from continuum_providers.artwork import CharacterSheetRequest

    excerpt = ArtworkReference(
        role="CANON",
        reference_id="a-source-page",
        data=_png(60),
        provenance={"origin": "SOURCE"},
    )
    with pytest.raises(ContinuumError, match="source excerpt"):
        provider.render_character_sheet(
            CharacterSheetRequest(
                sheet_kind="HEAD",
                views=("FRONT",),
                width=512,
                height=512,
                seed=1,
                references=(excerpt,),
                identity_rules=(),
                restrictions=(),
                outfit_id=None,
                settings={},
            )
        )
    assert recorder.calls == []


# -- the policy gate ---------------------------------------------------------
def _named(policy: ProviderPolicy) -> Any:
    registry = build_default_registry(policy, settings=_settings(google_api_key=KEY))
    return registry.resolve_named(
        GOOGLE_PROVIDER_ID, Capability.IMAGE_GENERATE, DataClass.PROJECT_TEXT
    )


def test_naming_the_paid_provider_still_goes_through_the_policy() -> None:
    with pytest.raises(ContinuumError) as refused:
        _named(ProviderPolicy())  # the shipped default: local only, free only
    assert "LOCAL_ONLY / FREE_ONLY" in refused.value.user_message
    allowed = _named(
        ProviderPolicy(
            locality=LocalityPolicy.REMOTE_ALLOWED, spend=SpendPolicy.PAID_ALLOWED_WITH_CAP
        )
    )
    assert allowed.descriptor.id == GOOGLE_PROVIDER_ID


def test_automatic_resolution_still_prefers_the_free_local_provider() -> None:
    """Naming it is a deliberate act; nothing drifts onto the paid path."""
    registry = build_default_registry(
        ProviderPolicy(
            locality=LocalityPolicy.REMOTE_ALLOWED, spend=SpendPolicy.PAID_ALLOWED_WITH_CAP
        ),
        settings=_settings(google_api_key=KEY),
    )
    chosen = registry.resolve(Capability.IMAGE_GENERATE, DataClass.PROJECT_TEXT)
    assert chosen.descriptor.cost_class is CostClass.FREE


def test_a_named_provider_is_still_refused_for_a_capability_it_lacks() -> None:
    registry = build_default_registry(settings=_settings(google_api_key=KEY))
    with pytest.raises(ContinuumError, match="does not offer"):
        registry.resolve_named(GOOGLE_PROVIDER_ID, Capability.TRANSCRIBE, DataClass.PROJECT_TEXT)


# -- the cost gate -----------------------------------------------------------
PAID = ProviderDescriptor(
    id="test.paid",
    capabilities=frozenset({Capability.IMAGE_GENERATE}),
    locality=Locality.REMOTE,
    cost_class=CostClass.PAID,
    privacy_class=PrivacyClass.THIRD_PARTY,
    model_ref="a-model",
)
FREE = ProviderDescriptor(
    id="test.free",
    capabilities=frozenset({Capability.IMAGE_GENERATE}),
    locality=Locality.LOCAL,
    cost_class=CostClass.FREE,
    privacy_class=PrivacyClass.ON_DEVICE,
)


def test_a_paid_call_without_a_budget_is_refused_not_billed() -> None:
    with pytest.raises(BudgetExceededError, match="without a budget"):
        with paid_call(None, PAID, purpose="SMOKE_TEST"):
            raise AssertionError("the provider must never be reached")


def test_a_free_call_needs_no_budget_at_all() -> None:
    with paid_call(None, FREE, purpose="ANYTHING") as entry:
        assert entry is None


def test_prices_are_configuration_and_a_free_paid_row_is_refused() -> None:
    with pytest.raises(ValueError, match="costs"):
        PriceList.from_json(
            json.dumps([{"provider_id": "google.image", "model_ref": "m", "per_image_micros": 0}])
        )
    priced = PriceList.from_json(
        json.dumps(
            [
                {
                    "provider_id": "google.image",
                    "model_ref": "m",
                    "per_image_micros": 134_000,
                    "note": "confirmed on the pricing page",
                }
            ]
        )
    )
    estimate = priced.estimate("google.image", "m", images=1, width=1024, height=1024)
    assert estimate.known and estimate.usd == "0.134"
    unknown = priced.estimate("google.image", "other", images=1, width=1024, height=1024)
    assert not unknown.known and "no configured price" in unknown.reason
