"""Phase 1 - image operations on bytes (continuum_imaging).

Synthetic images only. Proves crops and previews produce new bytes from a
region, masks mark exactly their regions, the format allowlist and the pixel
budget hold, and the sketch renderer is deterministic per seed.
"""

from __future__ import annotations

import io

import pytest
from continuum_core import NormalizedRegion
from continuum_imaging import (
    UnsupportedImageError,
    crop_region,
    mask_from_regions,
    open_image,
    pixel_digest,
    preview,
    probe,
)
from continuum_imaging.sketch import (
    SketchOperation,
    SketchPlacement,
    SketchReference,
    SketchRequest,
    render_sketch,
)
from PIL import Image


def _png(width: int = 200, height: int = 300, color: tuple[int, int, int] = (10, 200, 30)) -> bytes:
    image = Image.new("RGB", (width, height), (255, 255, 255))
    image.paste(color, (50, 75, 150, 225))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def test_probe_and_crop_a_region_without_touching_the_input() -> None:
    data = _png()
    before = bytes(data)
    info = probe(data)
    assert (info.format, info.width, info.height) == ("PNG", 200, 300)
    crop = crop_region(data, NormalizedRegion(0.25, 0.25, 0.5, 0.5))
    assert (crop.width, crop.height, crop.mime) == (100, 150, "image/png")
    assert open_image(crop.data).getpixel((50, 75)) == (10, 200, 30)
    assert data == before


def test_preview_is_bounded_webp() -> None:
    big = _png(4000, 3000)
    result = preview(big, NormalizedRegion(0, 0, 1, 1))
    assert result.mime == "image/webp"
    assert max(result.width, result.height) <= 1600


def test_mask_marks_exactly_the_regions() -> None:
    mask = mask_from_regions(100, 100, [NormalizedRegion(0.1, 0.1, 0.2, 0.3)])
    image = Image.open(io.BytesIO(mask.data))
    assert image.mode == "L"
    assert image.getpixel((15, 15)) == 255
    assert image.getpixel((50, 50)) == 0


def test_unsupported_and_oversized_images_are_refused() -> None:
    with pytest.raises(UnsupportedImageError):
        probe(b"not an image at all")
    tiff = io.BytesIO()
    Image.new("RGB", (4, 4)).save(tiff, format="TIFF")
    with pytest.raises(UnsupportedImageError):
        probe(tiff.getvalue())
    # A PNG header declaring 20000 x 20000 is refused before pixels are decoded.
    header = io.BytesIO()
    Image.new("1", (20000, 20000)).save(header, format="PNG")
    with pytest.raises(UnsupportedImageError):
        open_image(header.getvalue())


def _sketch(seed: int) -> SketchRequest:
    return SketchRequest(
        width=600,
        height=800,
        mode="SOURCE_DERIVED_EDIT",
        seed=seed,
        title="Demo project · E1 · page 3 panel 2",
        lines=("brief: a quiet meeting",),
        plate=_png(),
        plate_region=NormalizedRegion(0, 0, 1, 1),
        operations=(
            SketchOperation("REMOVE", NormalizedRegion(0.5, 0.2, 0.3, 0.5), "figure B"),
            SketchOperation("INSERT", NormalizedRegion(0.1, 0.2, 0.3, 0.5), "Demo Hero"),
            SketchOperation("PRESERVE", NormalizedRegion(0, 0.7, 1, 0.3)),
        ),
        placements=(SketchPlacement(NormalizedRegion(0.6, 0.6, 0.2, 0.3), "Demo Mage"),),
        references=(
            SketchReference("CANON", "face", _png(), NormalizedRegion(0.2, 0.2, 0.6, 0.6)),
        ),
    )


def test_sketch_is_deterministic_and_seed_sensitive() -> None:
    first = render_sketch(_sketch(7))
    again = render_sketch(_sketch(7))
    other = render_sketch(_sketch(8))
    assert pixel_digest(first.data) == pixel_digest(again.data)
    assert pixel_digest(first.data) != pixel_digest(other.data)
    assert (first.width, first.height) == (600, 800)
