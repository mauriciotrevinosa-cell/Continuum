"""A deterministic rough sketch, standing in for a real model.

This is not art. It makes an attempt's *intent* visible so the rough-manga
pipeline can be exercised end to end with no model installed:

* the source plate, cropped to its region and letterboxed;
* every edit operation drawn at its region - removals hatched, replacements
  and insertions boxed and labelled with who goes there, preserved areas
  outlined;
* placeholder figures for new characters, or boxes for a layout-only page;
* a strip of reference thumbnails labelled by bundle role;
* a caption with the mode, the target and the seed.

Same inputs give the same pixels. A different seed visibly changes the
output, so "regenerate" produces a genuinely new attempt.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from continuum_core import NormalizedRegion
from PIL import Image, ImageDraw, ImageFont, ImageOps

from continuum_imaging import EncodedImage, encode_png, open_image

__all__ = [
    "SketchOperation",
    "SketchPlacement",
    "SketchReference",
    "SketchRequest",
    "render_sketch",
]

_STRIP = 96
_CAPTION = 64
_MARGIN = 12
_HATCHED = {"REMOVE", "REMOVE_TEXT"}
_FILLED = {"REPLACE", "INSERT", "CHANGE_EXPRESSION", "CHANGE_OUTFIT", "REPLACE_TEXT"}


@dataclass(frozen=True, slots=True)
class SketchOperation:
    kind: str
    region: NormalizedRegion
    label: str = ""


@dataclass(frozen=True, slots=True)
class SketchPlacement:
    region: NormalizedRegion
    label: str = ""


@dataclass(frozen=True, slots=True)
class SketchReference:
    role: str
    label: str
    data: bytes
    region: NormalizedRegion | None = None


@dataclass(frozen=True, slots=True)
class SketchRequest:
    width: int
    height: int
    mode: str
    seed: int
    title: str
    lines: tuple[str, ...] = ()
    plate: bytes | None = None
    plate_region: NormalizedRegion | None = None
    operations: tuple[SketchOperation, ...] = ()
    placements: tuple[SketchPlacement, ...] = ()
    references: tuple[SketchReference, ...] = field(default_factory=tuple)


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    return ImageFont.load_default(size=size)


def _box(region: NormalizedRegion, area: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    left, top, right, bottom = area
    x0, y0, x1, y1 = region.to_pixels(right - left, bottom - top)
    return left + x0, top + y0, left + x1 - 1, top + y1 - 1


def _hatch(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], offset: int) -> None:
    x0, y0, x1, y1 = box
    draw.rectangle(box, fill=255)
    step = 10
    for start in range(x0 - (y1 - y0) + offset % step, x1, step):
        draw.line((start, y1, start + (y1 - y0), y0), fill=150, width=1)
    draw.rectangle(box, outline=60, width=2)


def _dashed(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], dash: int = 8) -> None:
    x0, y0, x1, y1 = box
    for x in range(x0, x1, dash * 2):
        draw.line((x, y0, min(x + dash, x1), y0), fill=40, width=2)
        draw.line((x, y1, min(x + dash, x1), y1), fill=40, width=2)
    for y in range(y0, y1, dash * 2):
        draw.line((x0, y, x0, min(y + dash, y1)), fill=40, width=2)
        draw.line((x1, y, x1, min(y + dash, y1)), fill=40, width=2)


def _figure(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int]) -> None:
    x0, y0, x1, y1 = box
    width, height = x1 - x0, y1 - y0
    head = max(6, min(width, height) // 5)
    cx = x0 + width // 2
    draw.ellipse((cx - head, y0 + 4, cx + head, y0 + 4 + head * 2), outline=20, width=3)
    draw.line((cx, y0 + 4 + head * 2, cx, y1 - height // 4), fill=20, width=3)
    draw.line((cx, y0 + head * 3, x0 + width // 6, y0 + height // 2), fill=20, width=3)
    draw.line((cx, y0 + head * 3, x1 - width // 6, y0 + height // 2), fill=20, width=3)
    draw.line((cx, y1 - height // 4, x0 + width // 4, y1 - 4), fill=20, width=3)
    draw.line((cx, y1 - height // 4, x1 - width // 4, y1 - 4), fill=20, width=3)


def _label(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, size: int = 14) -> None:
    if not text:
        return
    font = _font(size)
    left, top, right, bottom = draw.textbbox(xy, text, font=font)
    draw.rectangle((left - 3, top - 2, right + 3, bottom + 2), fill=255, outline=0)
    draw.text(xy, text, fill=0, font=font)


def render_sketch(request: SketchRequest) -> EncodedImage:
    """Render the request deterministically as a grayscale PNG."""
    canvas = Image.new("L", (request.width, request.height), 255)
    draw = ImageDraw.Draw(canvas)
    rng = random.Random(request.seed)  # noqa: S311 - a repeatable texture, not cryptography

    top = _STRIP if request.references else _MARGIN
    area = (_MARGIN, top, request.width - _MARGIN, request.height - _CAPTION)

    # The seed's fingerprint: a sparse, repeatable texture in the margins.
    for _ in range(40):
        x = rng.randrange(0, request.width)
        y = rng.randrange(request.height - _CAPTION, request.height)
        draw.point((x, y), fill=rng.randrange(120, 200))

    # Reference strip, by role.
    x = _MARGIN
    for reference in request.references[:8]:
        try:
            thumb = open_image(reference.data)
        except Exception:  # an unreadable reference is shown as missing, not fatal
            thumb = Image.new("RGB", (64, 64), (230, 230, 230))
        if reference.region is not None:
            thumb = thumb.crop(reference.region.to_pixels(thumb.width, thumb.height))
        thumb = ImageOps.grayscale(thumb)
        thumb.thumbnail((_STRIP - 34, _STRIP - 34))
        canvas.paste(thumb, (x, 8))
        _label(draw, (x, _STRIP - 24), f"{reference.role}:{reference.label}"[:28], size=11)
        x += max(thumb.width, 90) + 10
        if x > request.width - 100:
            break

    # Base: the source plate, or a blank frame.
    draw.rectangle(area, outline=0, width=3)
    area_w, area_h = area[2] - area[0], area[3] - area[1]
    if request.plate is not None:
        plate = open_image(request.plate)
        if request.plate_region is not None:
            plate = plate.crop(request.plate_region.to_pixels(plate.width, plate.height))
        plate = ImageOps.grayscale(plate)
        plate = ImageOps.contain(plate, (area_w, area_h), Image.Resampling.LANCZOS)
        offset = (area[0] + (area_w - plate.width) // 2, area[1] + (area_h - plate.height) // 2)
        canvas.paste(plate, offset)
        area = (offset[0], offset[1], offset[0] + plate.width, offset[1] + plate.height)

    for placement in request.placements:
        box = _box(placement.region, area)
        if request.mode == "LAYOUT_ONLY":
            draw.rectangle(box, outline=0, width=3)
        else:
            _figure(draw, box)
        _label(draw, (box[0] + 4, box[1] + 4), placement.label)

    for index, operation in enumerate(request.operations):
        box = _box(operation.region, area)
        if operation.kind in _HATCHED:
            _hatch(draw, box, offset=request.seed + index)
        elif operation.kind in _FILLED:
            draw.rectangle(box, fill=225, outline=0, width=3)
            _figure(draw, box)
        elif operation.kind == "PRESERVE":
            draw.rectangle(box, outline=90, width=1)
        else:
            _dashed(draw, box)
        _label(draw, (box[0] + 4, box[1] + 4), f"{operation.kind} {operation.label}".strip())

    caption_top = request.height - _CAPTION + 8
    draw.text((_MARGIN, caption_top), request.title[:90], fill=0, font=_font(15))
    detail = "  ·  ".join([request.mode, f"seed {request.seed}", *request.lines])[:120]
    draw.text((_MARGIN, caption_top + 22), detail, fill=60, font=_font(12))
    return encode_png(canvas)
