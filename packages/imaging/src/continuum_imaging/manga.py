"""Manga page imaging: finishes derived from one master, and page layout analysis.

* :func:`bw_finish` turns a composition master into a black-and-white manga
  finish of **exactly the same geometry**: grayscale, tone-mapped to inks,
  mid-tones as an ordered screentone. Any backend can use it, and a backend
  that draws its own finish must still match the master's size.
* :func:`tint_finish` is the test renderer's stand-in for a color finish (a
  deterministic tint of the master). Real color comes from a real backend.
* :func:`analyze_layout` measures a manga page's structure - panels by
  recursive gutter cuts, negative space, ink density - for grammar retrieval.
  It reads layout, never identity; it keeps no pixels.
"""

from __future__ import annotations

from dataclasses import dataclass

from PIL import Image, ImageOps

from continuum_imaging import EncodedImage, encode_png, open_image

__all__ = ["PageLayout", "analyze_layout", "bw_finish", "tint_finish"]

_BAYER = (
    (0, 8, 2, 10),
    (12, 4, 14, 6),
    (3, 11, 1, 9),
    (15, 7, 13, 5),
)


def bw_finish(master: bytes, *, ink: int = 70, paper: int = 200) -> EncodedImage:
    """A black-and-white manga finish with the master's exact dimensions."""
    image = ImageOps.autocontrast(open_image(master).convert("L"))
    width, height = image.size
    source = image.load()
    out = Image.new("L", (width, height), 255)
    target = out.load()
    assert source is not None and target is not None
    for y in range(height):
        row = _BAYER[y % 4]
        for x in range(width):
            value = int(source[x, y])  # type: ignore[arg-type]
            if value <= ink:
                target[x, y] = 0
            elif value >= paper:
                target[x, y] = 255
            else:
                level = (value - ink) * 16 // max(1, paper - ink)
                target[x, y] = 255 if level > row[x % 4] else 0
    return encode_png(out)


def tint_finish(master: bytes, seed: int) -> EncodedImage:
    """A deterministic color tint of the master (test renderer only)."""
    gray = open_image(master).convert("L")
    dark = ((seed * 37) % 90, (seed * 53) % 90, (seed * 71) % 90 + 40)
    light = (255, 246, 228)
    return encode_png(ImageOps.colorize(gray, black=dark, white=light))


@dataclass(frozen=True, slots=True)
class PageLayout:
    width: int
    height: int
    #: Normalized (x, y, w, h) boxes in reading-agnostic top-to-bottom order.
    panels: tuple[tuple[float, float, float, float], ...]
    negative_space: float
    ink_density: float

    @property
    def panel_count(self) -> int:
        return len(self.panels)

    @property
    def largest_panel_share(self) -> float:
        return max((w * h for _x, _y, w, h in self.panels), default=0.0)


def _is_gutter(values: list[float], threshold: float) -> list[bool]:
    return [v >= threshold for v in values]


def _runs(flags: list[bool], min_len: int) -> list[tuple[int, int]]:
    """Content runs (False stretches) separated by gutters of at least ``min_len``."""
    runs = []
    start = None
    gap = 0
    for index, gutter in enumerate([*flags, True]):
        if not gutter:
            if start is None:
                start = index
            gap = 0
        else:
            gap += 1
            if start is not None and (gap >= min_len or index == len(flags)):
                runs.append((start, index - gap + 1))
                start = None
    return [(a, b) for a, b in runs if b - a > 2]


def analyze_layout(data: bytes, *, max_side: int = 400, depth: int = 4) -> PageLayout:
    """Panels by recursive XY gutter cuts on a small grayscale copy."""
    image = open_image(data).convert("L")
    scale = max_side / max(image.size)
    small = image.resize((max(1, int(image.width * scale)), max(1, int(image.height * scale))))
    width, height = small.size
    pixels = list(small.tobytes())  # mode L: one byte per pixel
    white = [p >= 235 for p in pixels]
    ink = sum(1 for p in pixels if p < 80) / len(pixels)
    negative = sum(white) / len(white)

    def white_share(x0: int, y0: int, x1: int, y1: int, axis: int) -> list[float]:
        if axis == 0:  # rows
            return [
                sum(white[y * width + x] for x in range(x0, x1)) / max(1, x1 - x0)
                for y in range(y0, y1)
            ]
        return [
            sum(white[y * width + x] for y in range(y0, y1)) / max(1, y1 - y0)
            for x in range(x0, x1)
        ]

    boxes: list[tuple[int, int, int, int]] = []

    def cut(x0: int, y0: int, x1: int, y1: int, level: int) -> None:
        if level > depth:
            boxes.append((x0, y0, x1, y1))
            return
        for axis in (0, 1):
            shares = white_share(x0, y0, x1, y1, axis)
            runs = _runs(_is_gutter(shares, 0.985), min_len=3)
            if len(runs) > 1:
                for a, b in runs:
                    if axis == 0:
                        cut(x0, y0 + a, x1, y0 + b, level + 1)
                    else:
                        cut(x0 + a, y0, x0 + b, y1, level + 1)
                return
        boxes.append((x0, y0, x1, y1))

    cut(0, 0, width, height, 0)
    area = width * height
    panels = tuple(
        (x0 / width, y0 / height, (x1 - x0) / width, (y1 - y0) / height)
        for x0, y0, x1, y1 in boxes
        if (x1 - x0) * (y1 - y0) >= area * 0.01
    )
    return PageLayout(
        width=image.width,
        height=image.height,
        panels=panels,
        negative_space=round(negative, 4),
        ink_density=round(ink, 4),
    )
