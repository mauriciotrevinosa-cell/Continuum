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

import math
from collections.abc import Sequence
from dataclasses import dataclass

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageOps

from continuum_imaging import EncodedImage, encode_png, open_image

__all__ = [
    "PageLayout",
    "analyze_layout",
    "bw_finish",
    "compose_manga_page",
    "panel_boxes",
    "tint_finish",
]


def bw_finish(master: bytes) -> EncodedImage:
    """Preserve drawing structure as clean monochrome without global dot dithering.

    A production manga finish may later add authored screentones selectively.
    This derivative deliberately keeps grayscale values, sharpened contours and
    clean highlights so faces and environments are not destroyed by a page-wide
    Bayer pattern.
    """
    gray = ImageOps.autocontrast(open_image(master).convert("L"), cutoff=1)
    gray = gray.filter(ImageFilter.UnsharpMask(radius=1.0, percent=150, threshold=3))
    gray = ImageEnhance.Contrast(gray).enhance(1.18)
    return encode_png(gray)


def tint_finish(master: bytes, seed: int) -> EncodedImage:
    """A deterministic color tint of the master (test renderer only)."""
    gray = open_image(master).convert("L")
    dark = ((seed * 37) % 90, (seed * 53) % 90, (seed * 71) % 90 + 40)
    light = (255, 246, 228)
    return encode_png(ImageOps.colorize(gray, black=dark, white=light))


def panel_boxes(count: int) -> tuple[tuple[float, float, float, float], ...]:
    """Deterministic manga-like panel geometry in reading order.

    Geometry belongs to Continuum, not to the diffusion model. Rows read right-to-left.
    Templates keep
    gutters and hierarchy stable; a five-panel page deliberately reserves a
    large lower panel for climax/reaction beats such as CAL-17/CAL-18.
    """
    if count <= 0:
        return ()
    templates: dict[int, tuple[tuple[float, float, float, float], ...]] = {
        1: ((0.0, 0.0, 1.0, 1.0),),
        2: ((0.0, 0.0, 1.0, 0.47), (0.0, 0.53, 1.0, 0.47)),
        3: (
            (0.0, 0.0, 1.0, 0.42),
            (0.52, 0.48, 0.48, 0.52),
            (0.0, 0.48, 0.48, 0.52),
        ),
        4: (
            (0.0, 0.0, 1.0, 0.25),
            (0.52, 0.31, 0.48, 0.34),
            (0.0, 0.31, 0.48, 0.34),
            (0.0, 0.71, 1.0, 0.29),
        ),
        5: (
            (0.0, 0.0, 1.0, 0.16),
            (0.52, 0.22, 0.48, 0.20),
            (0.0, 0.22, 0.48, 0.20),
            (0.0, 0.48, 1.0, 0.16),
            (0.0, 0.70, 1.0, 0.30),
        ),
        6: (
            (0.52, 0.0, 0.48, 0.27),
            (0.0, 0.0, 0.48, 0.27),
            (0.0, 0.33, 1.0, 0.24),
            (0.52, 0.63, 0.48, 0.17),
            (0.0, 0.63, 0.48, 0.17),
            (0.0, 0.86, 1.0, 0.14),
        ),
    }
    if count in templates:
        return templates[count]

    columns = 2 if count <= 8 else 3
    rows = math.ceil(count / columns)
    gap = 0.04
    cell_w = (1.0 - gap * (columns - 1)) / columns
    cell_h = (1.0 - gap * (rows - 1)) / rows
    boxes = []
    for index in range(count):
        row, logical_column = divmod(index, columns)
        column = columns - 1 - logical_column
        boxes.append(
            (
                column * (cell_w + gap),
                row * (cell_h + gap),
                cell_w,
                cell_h,
            )
        )
    return tuple(boxes)


def compose_manga_page(
    panels: Sequence[bytes],
    width: int,
    height: int,
    *,
    margin: int = 28,
    gutter: int = 12,
    border: int = 3,
) -> EncodedImage:
    """Assemble already-rendered panels on deterministic white manga paper."""
    if not panels:
        raise ValueError("at least one panel is required")
    canvas = Image.new("RGB", (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(canvas)
    inner_w = max(1, width - 2 * margin)
    inner_h = max(1, height - 2 * margin)
    boxes = panel_boxes(len(panels))

    for data, (nx, ny, nw, nh) in zip(panels, boxes, strict=True):
        x0 = margin + round(nx * inner_w)
        y0 = margin + round(ny * inner_h)
        x1 = margin + round((nx + nw) * inner_w)
        y1 = margin + round((ny + nh) * inner_h)
        # Pull the image inward slightly so neighbouring borders never touch.
        x0 += gutter // 2
        y0 += gutter // 2
        x1 -= gutter // 2
        y1 -= gutter // 2
        panel = open_image(data)
        panel = ImageOps.fit(
            panel,
            (max(1, x1 - x0), max(1, y1 - y0)),
            method=Image.Resampling.LANCZOS,
            centering=(0.5, 0.5),
        )
        canvas.paste(panel, (x0, y0))
        draw.rectangle((x0, y0, x1 - 1, y1 - 1), outline=0, width=border)
    return encode_png(canvas)


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
