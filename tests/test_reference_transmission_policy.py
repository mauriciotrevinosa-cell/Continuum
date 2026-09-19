"""Per-reference transmission policy: what a remote provider may receive.

The rule is the existing one - a verbatim source excerpt never leaves the
machine - applied to each reference instead of to a whole request, and failing
closed when provenance does not show that an image is the project's own.
"""

from __future__ import annotations

import pytest
from continuum_providers.contracts import DataClass, Locality
from continuum_providers.policy import reference_data_class, transmission_refusal


@pytest.mark.parametrize(
    "provenance",
    [
        {"origin": "SOURCE"},
        {"origin": "OFFICIAL_ART"},
        {"origin": "FAN_ART"},
        {"authority": "PRIMARY_SOURCE", "origin": "USER_CREATED"},
        {"authority": "OFFICIAL"},
        {"kind": "source_page"},
        {},  # unknown: fails closed
        {"why": ["described as location: forest"]},
    ],
)
def test_third_party_or_unknown_images_are_source_excerpts(provenance: dict[str, str]) -> None:
    assert reference_data_class(provenance) is DataClass.SOURCE_EXCERPT
    assert transmission_refusal(provenance, Locality.REMOTE) is not None
    # Local providers may use them; an explicit user allowance may send them.
    assert transmission_refusal(provenance, Locality.LOCAL) is None
    assert transmission_refusal(provenance, Locality.REMOTE, source_excerpts_allowed=True) is None


@pytest.mark.parametrize(
    "provenance",
    [
        {"origin": "USER_CREATED"},
        {"origin": "GENERATED"},
        {"origin": "PROJECT_APPROVED"},
        {"authority": "CREATOR_PRIMARY", "origin": "USER_CREATED"},
        {"authority": "PROJECT_CREATED"},
        # A Continuum stage output used as the next stage's base.
        {"attempt_id": "01a0", "stage": "COMPOSITION", "sha256": "a" * 64},
    ],
)
def test_the_projects_own_images_may_travel(provenance: dict[str, str]) -> None:
    assert reference_data_class(provenance) is DataClass.PROJECT_MEDIA
    assert transmission_refusal(provenance, Locality.REMOTE) is None


def test_refusals_say_why() -> None:
    assert "never leaves this machine" in str(
        transmission_refusal({"origin": "SOURCE"}, Locality.REMOTE)
    )
    assert "does not show it is the project's own" in str(transmission_refusal({}, Locality.REMOTE))
