"""Phase 1 - content-derived locators and normalized regions (ADR-0005 section 1).

Pure tests, no database: parse(render(x)) == x for every medium, canonical
form is enforced, and nothing path-like or ambiguous survives parsing.
"""

from __future__ import annotations

import pytest
from continuum_core import (
    InvalidLocatorError,
    LocatorMedium,
    NormalizedRegion,
    SourceLocator,
    parse_locator,
)
from hypothesis import given
from hypothesis import strategies as st

H = "ab" * 32


@pytest.mark.parametrize(
    "locator",
    [
        SourceLocator.asset(LocatorMedium.IMAGE, H),
        SourceLocator.asset(LocatorMedium.GEN, H),
        SourceLocator.archive_entry(H, "Vol 01/Ch0003/012.webp"),
        SourceLocator.archive_entry(H, "page#1&x=%20.png"),
        SourceLocator.archive_entry(H, "章/ページ 01.jpg"),
        SourceLocator.pdf_page(H, 88),
        SourceLocator(medium=LocatorMedium.VIDEO, sha256=H, time_ms=43_383_400),
    ],
)
def test_round_trip(locator: SourceLocator) -> None:
    text = locator.render()
    assert parse_locator(text) == locator
    assert parse_locator(text).render() == text


def test_rendered_forms_are_stable() -> None:
    assert SourceLocator.archive_entry(H, "Vol 01/012.webp").render() == (
        f"zip:sha256:{H}#entry=Vol%2001/012.webp"
    )
    assert SourceLocator.pdf_page(H, 3).render() == f"pdf:sha256:{H}#page=3"
    assert (
        SourceLocator(medium=LocatorMedium.VIDEO, sha256=H, time_ms=3_723_004).render()
        == f"video:sha256:{H}#t=01:02:03.004"
    )


@given(
    st.text(
        alphabet=st.characters(blacklist_categories=("Cs", "Cc"), blacklist_characters="\\"),
        min_size=1,
        max_size=40,
    )
)
def test_any_safe_entry_round_trips(name: str) -> None:
    segments = [s for s in name.split("/") if s not in ("", ".", "..")]
    if not segments:
        return
    entry = "/".join(segments)
    locator = SourceLocator.archive_entry(H, entry)
    assert parse_locator(locator.render()) == locator


@pytest.mark.parametrize(
    "text",
    [
        "",
        "zip:sha256:" + H,  # an archive locator needs its entry
        "image:sha256:" + H + "#entry=a.png",  # whole-file media take no unit
        "zip:md5:" + H + "#entry=a.png",
        "zip:sha256:" + H.upper() + "#entry=a.png",
        "zip:sha256:abc#entry=a.png",
        "tar:sha256:" + H + "#entry=a.png",
        "zip:sha256:" + H + "#entry=../../etc/passwd",
        "zip:sha256:" + H + "#entry=%2E%2E/secret",
        "zip:sha256:" + H + "#entry=/absolute.png",
        "zip:sha256:" + H + "#entry=C:%5Cvault%5Cx.png",
        "zip:sha256:" + H + "#entry=a%5Cb.png",
        "zip:sha256:" + H + "#entry=a//b.png",
        "zip:sha256:" + H + "#entry=a%00.png",
        "zip:sha256:" + H + "#entry=a%zz.png",
        "zip:sha256:" + H + "#entry=a b.png",  # not canonical: space must be escaped
        "zip:sha256:" + H + "#",
        "pdf:sha256:" + H + "#page=0",
        "pdf:sha256:" + H + "#page=01",
        "pdf:sha256:" + H + "#page=-1",
        "video:sha256:" + H + "#t=1:2:3",
        "zip:sha256:" + H + "#path=a.png",
        "file:///C:/ContinuumVault/x.cbz",
        r"C:\ContinuumVault\x.cbz",
    ],
)
def test_unsafe_or_malformed_locators_are_refused(text: str) -> None:
    with pytest.raises(InvalidLocatorError):
        parse_locator(text)


def test_region_bounds() -> None:
    region = NormalizedRegion(0.25, 0.5, 0.5, 0.25)
    assert region.to_pixels(1000, 2000) == (250, 1000, 750, 1500)
    NormalizedRegion(0, 0, 1, 1)
    for bad in [
        (-0.1, 0, 0.5, 0.5),
        (0, 0, 0, 0.5),
        (0.6, 0, 0.5, 0.5),
        (0, 0.9, 0.5, 0.2),
        (0, 0, 0.005, 0.5),
        (float("nan"), 0, 0.5, 0.5),
        (0, 0, float("inf"), 0.5),
    ]:
        with pytest.raises(InvalidLocatorError):
            NormalizedRegion(*bad)


def test_tiny_selection_still_maps_to_at_least_one_pixel() -> None:
    left, top, right, bottom = NormalizedRegion(0.99, 0.99, 0.01, 0.01).to_pixels(10, 10)
    assert right > left and bottom > top
