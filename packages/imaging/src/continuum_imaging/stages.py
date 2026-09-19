"""Layered-construction imaging: the test renderer's stages and a structure-drift measure.

* :func:`stage_diagram` is what the deterministic test backend draws for one
  construction stage. The first stage is a blocking diagram of the panel
  contract; every later stage is a **geometry-preserving transform of the frozen
  upstream image** (sharpen, line extraction, value banding, a light gradient,
  effect marks, a vignette, the ink finish). It proves the stage workflow -
  freeze, build on, invalidate - without a model, and is never artwork.
* :func:`structure_drift` measures how much a stage changed the structure it was
  given: the share of the upstream's edges that no longer have an edge nearby.
  0 means the drawing was kept; values near 1 mean it was redrawn. It is
  advisory evidence for review, never a verdict.
"""

from __future__ import annotations

import random
from collections.abc import Sequence

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

from continuum_imaging import EncodedImage, encode_png, open_image
from continuum_imaging.manga import bw_finish

__all__ = ["resize_exact", "stage_diagram", "structure_drift"]

_DRIFT_EDGE = 96


def _tag(image: Image.Image, text: str) -> Image.Image:
    """A small corner label: the only pixels a test stage adds outside its transform."""
    out = image.convert("RGB")
    draw = ImageDraw.Draw(out)
    font = ImageFont.load_default(size=max(10, out.width // 60))
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
    width, height = right - left, bottom - top
    x0 = out.width - width - 12
    y0 = out.height - height - 12
    draw.rectangle((x0 - 4, y0 - 3, x0 + width + 4, y0 + height + 4), fill=(255, 255, 255))
    draw.text((x0, y0 - top), text, fill=(0, 0, 0), font=font)
    return out


def _blocking(width: int, height: int, seed: int, lines: Sequence[str]) -> Image.Image:
    """COMPOSITION: horizon, depth bands and one labelled block per required anchor."""
    rng = random.Random(seed)  # noqa: S311 - a repeatable layout, not cryptography
    canvas = Image.new("RGB", (width, height), (246, 244, 238))
    draw = ImageDraw.Draw(canvas)
    horizon = int(height * (0.34 + rng.random() * 0.12))
    draw.rectangle((0, 0, width, horizon), fill=(226, 230, 234))
    for band in range(3):
        y = horizon + int((height - horizon) * (band + 1) / 4)
        draw.line((0, y, width, y), fill=(170, 170, 160), width=2)
    draw.line((0, horizon, width, horizon), fill=(90, 90, 90), width=3)
    # A vanishing point and two converging guides give the stage a camera.
    vx = int(width * (0.3 + rng.random() * 0.4))
    for edge in (0, width):
        draw.line((edge, height, vx, horizon), fill=(140, 140, 140), width=2)
    font = ImageFont.load_default(size=max(11, width // 70))
    anchors = [line for line in lines if line][:8]
    for index, text in enumerate(anchors):
        bw = int(width * (0.12 + rng.random() * 0.14))
        bh = int(height * (0.08 + rng.random() * 0.1))
        x0 = int((width - bw) * (index + 0.5) / max(1, len(anchors)))
        y0 = horizon - bh // 2 + int((height - horizon) * rng.random() * 0.5)
        draw.rectangle((x0, y0, x0 + bw, y0 + bh), outline=(20, 20, 20), width=3)
        draw.text((x0 + 4, y0 + 4), text[:28], fill=(20, 20, 20), font=font)
    return canvas


def _light(image: Image.Image, seed: int) -> Image.Image:
    """LIGHT_SHADOW: a seeded directional light multiplied over the upstream."""
    gradient = Image.linear_gradient("L").resize(image.size)
    if seed % 2:
        gradient = ImageOps.mirror(gradient.rotate(90, expand=False))
    gradient = ImageOps.autocontrast(gradient).point(lambda v: 150 + v * 105 // 255)
    return ImageChops.multiply(image.convert("RGB"), Image.merge("RGB", (gradient,) * 3))


def _effects(image: Image.Image, seed: int) -> Image.Image:
    """FX: seeded marks added on top; the upstream underneath is untouched."""
    rng = random.Random(seed)  # noqa: S311 - repeatable marks, not cryptography
    out = image.convert("RGB")
    draw = ImageDraw.Draw(out)
    for _ in range(60):
        x, y = rng.randrange(out.width), rng.randrange(out.height)
        r = rng.randrange(2, 6)
        draw.ellipse((x - r, y - r, x + r, y + r), outline=(255, 255, 255), width=1)
    return out


def stage_diagram(
    stage: str,
    *,
    width: int,
    height: int,
    seed: int,
    upstream: bytes | None,
    lines: Sequence[str] = (),
) -> EncodedImage:
    """The test backend's image for one stage. Later stages keep the upstream geometry."""
    if upstream is None:
        image = _blocking(width, height, seed, lines)
    else:
        base = open_image(upstream).convert("RGB")
        if stage == "DRAWING":
            image = base.filter(ImageFilter.UnsharpMask(radius=2, percent=160, threshold=2))
        elif stage == "LINE":
            gray = ImageOps.grayscale(base).filter(ImageFilter.FIND_EDGES)
            lines_only = ImageOps.invert(ImageOps.autocontrast(gray))
            image = Image.blend(Image.merge("RGB", (lines_only,) * 3), base, 0.25)
        elif stage == "VALUE_MATERIAL":
            image = ImageOps.posterize(base, 3)
        elif stage == "LIGHT_SHADOW":
            image = _light(base, seed)
        elif stage == "FX":
            image = _effects(base, seed)
        elif stage == "ENVIRONMENT_INTEGRATION":
            image = ImageEnhance.Contrast(base).enhance(0.92)
        elif stage == "FINISH":
            image = open_image(bw_finish(upstream).data)
        else:
            image = base
    return encode_png(_tag(image, f"WORKFLOW TEST - NOT ARTWORK - {stage}"))


def _edges(data: bytes) -> Image.Image:
    gray = ImageOps.grayscale(open_image(data)).resize(
        (_DRIFT_EDGE, _DRIFT_EDGE), Image.Resampling.LANCZOS
    )
    edges = gray.filter(ImageFilter.GaussianBlur(1)).filter(ImageFilter.FIND_EDGES)
    histogram = edges.histogram()
    count = sum(histogram)
    mean = sum(value * n for value, n in enumerate(histogram)) / count
    spread = (sum(n * (value - mean) ** 2 for value, n in enumerate(histogram)) / count) ** 0.5
    threshold = mean + spread
    return edges.point(lambda v: 255 if v > threshold else 0)


def structure_drift(upstream: bytes, output: bytes) -> float:
    """Share of the upstream's edges with no output edge within one cell (0..1)."""
    before = _edges(upstream)
    after = _edges(output).filter(ImageFilter.MaxFilter(3))
    kept = ImageChops.multiply(before, after)
    # Edge maps are strictly 0 or 255, so the histogram's last bin counts edges.
    total = before.histogram()[255]
    if not total:
        return 0.0
    return round(1.0 - kept.histogram()[255] / total, 4)


def resize_exact(data: bytes, width: int, height: int) -> EncodedImage:
    """The image at exactly ``width`` x ``height`` (a backend's /8 rounding undone)."""
    image = open_image(data).convert("RGB")
    if image.size != (width, height):
        image = image.resize((width, height), Image.Resampling.LANCZOS)
    return encode_png(image)
