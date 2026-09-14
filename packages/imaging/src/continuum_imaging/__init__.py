"""Image operations on bytes: decode, crop, preview, mask, digest.

**Bytes in, bytes out.** Nothing here opens a file, so nothing here can touch
the Source Vault: callers read source bytes through the storage layer and
hand them in, and derived bytes go back out to be stored content-addressed
under a writable root. A crop, a mask or a preview is always a *new* artifact;
the original bytes are never modified.

Every decode goes through :func:`open_image`, which accepts only an allowlist
of formats and refuses images whose declared size exceeds a pixel budget
before any pixel data is decoded (decompression bombs, F-51).

**HEIC / HEIF** is decoded by ``pi-heif`` (decode-only libheif + libde265; see
``docs/DEPENDENCIES.md``) with thumbnails, depth and auxiliary images disabled
and libheif's security limits left on. A HEIF original is never the working
image: :func:`working_rendition` turns it into a deterministic PNG, and callers
keep the original bytes and their hash beside it as provenance. Without the
decoder, HEIF is recognised by signature and refused with a remediation - it is
never mistaken for video or silently dropped.
"""

from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass
from typing import Final

from continuum_core import ContinuumError, ErrorCategory, NormalizedRegion
from PIL import Image, ImageOps, UnidentifiedImageError

from continuum_imaging.formats import HEIF_BRANDS, Sniffed, sniff

try:  # pragma: no cover - exercised by both branches in tests via monkeypatch
    import pi_heif as _pi_heif
except ImportError:  # pragma: no cover
    _pi_heif = None

__all__ = [
    "ALLOWED_FORMATS",
    "CONVERTED_FORMATS",
    "HEIF_BRANDS",
    "HEIF_DECODER",
    "MAX_PIXELS",
    "EncodedImage",
    "HeifDecoderUnavailableError",
    "ImageInfo",
    "Rendition",
    "Sniffed",
    "UnsupportedImageError",
    "crop_region",
    "encode_png",
    "mask_from_regions",
    "open_image",
    "pixel_digest",
    "preview",
    "probe",
    "sniff",
    "working_rendition",
]

#: Decoded formats and the content type served for each.
ALLOWED_FORMATS: Final[dict[str, str]] = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
    "GIF": "image/gif",
    "BMP": "image/bmp",
    "HEIF": "image/heif",
}
#: Formats kept only as immutable originals; work happens on a PNG rendition.
CONVERTED_FORMATS: Final = frozenset({"HEIF"})
#: 120 megapixels: far above any manga page or illustration, far below a bomb.
MAX_PIXELS: Final = 120_000_000
#: Longest edge for previews served to the browser.
PREVIEW_EDGE: Final = 1600

# Pillow's own guard, as a backstop to the explicit check in open_image().
Image.MAX_IMAGE_PIXELS = MAX_PIXELS


def _register_heif() -> str | None:
    if _pi_heif is None:
        return None
    # Only the primary image is ever decoded: no thumbnails, depth maps or
    # auxiliary images (less attack surface, deterministic output).
    _pi_heif.register_heif_opener(
        thumbnails=False, depth_images=False, aux_images=False, decode_threads=1
    )
    return f"pi-heif {_pi_heif.__version__} / libheif {_pi_heif.libheif_version()}"


#: The HEIF decoder in use, recorded as provenance on every conversion; None
#: when it is not installed.
HEIF_DECODER: str | None = _register_heif()


class UnsupportedImageError(ContinuumError):
    """Bytes that are not an allowed, decodable image within the pixel budget."""

    code = "imaging.unsupported"
    category = ErrorCategory.PERMANENT_INPUT


class HeifDecoderUnavailableError(UnsupportedImageError):
    """A real HEIC/HEIF image, but no HEIF decoder is installed."""

    code = "imaging.heif_decoder_missing"
    category = ErrorCategory.PERMANENT_CONFIG


@dataclass(frozen=True, slots=True)
class ImageInfo:
    format: str
    mime: str
    width: int
    height: int


@dataclass(frozen=True, slots=True)
class EncodedImage:
    data: bytes
    mime: str
    width: int
    height: int


@dataclass(frozen=True, slots=True)
class Rendition:
    """A deterministic working copy of an image kept only as an original."""

    image: EncodedImage
    original_format: str
    converter: str


def probe(data: bytes) -> ImageInfo:
    """Format and dimensions from the header, without decoding pixels."""
    sniffed = sniff(data)
    if sniffed.format == "HEIF" and HEIF_DECODER is None:
        raise HeifDecoderUnavailableError(
            "This is a HEIC/HEIF image, and the HEIF decoder is not installed.",
            technical_detail="pi_heif is not importable",
            remediation="Install the project dependencies (uv sync) to add the pi-heif decoder.",
        )
    if sniffed.kind != "image":
        raise UnsupportedImageError(
            f"These bytes are {sniffed.description}, not an image.",
            technical_detail=f"sniffed={sniffed.format}",
        )
    try:
        with Image.open(io.BytesIO(data)) as image:
            fmt = image.format or ""
            width, height = image.size
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
        raise UnsupportedImageError(
            "These bytes are not an image Continuum can read.",
            technical_detail=f"{type(exc).__name__}: {exc}",
        ) from None
    if fmt not in ALLOWED_FORMATS:
        raise UnsupportedImageError(
            "This image format is not supported.",
            technical_detail=f"format={fmt!r}",
            remediation=f"Supported formats: {', '.join(sorted(ALLOWED_FORMATS))}.",
        )
    if width <= 0 or height <= 0 or width * height > MAX_PIXELS:
        raise UnsupportedImageError(
            "This image is too large to process safely.",
            technical_detail=f"{width}x{height} exceeds {MAX_PIXELS} pixels",
        )
    return ImageInfo(format=fmt, mime=ALLOWED_FORMATS[fmt], width=width, height=height)


def open_image(data: bytes) -> Image.Image:
    """Decode an allowed image into RGB, applying EXIF orientation."""
    probe(data)
    try:
        with Image.open(io.BytesIO(data)) as image:
            image.seek(0)
            oriented = ImageOps.exif_transpose(image)
            return oriented.convert("RGB")
    except (OSError, ValueError, Image.DecompressionBombError) as exc:
        raise UnsupportedImageError(
            "This image could not be decoded.",
            technical_detail=f"{type(exc).__name__}: {exc}",
        ) from None


def working_rendition(data: bytes) -> Rendition | None:
    """A deterministic PNG to work with, for formats kept only as originals.

    Returns None for formats Continuum works with directly. The same bytes and
    decoder always give the same PNG bytes; the decoder's identity is returned
    so callers record it with the original's hash.
    """
    info = probe(data)
    if info.format not in CONVERTED_FORMATS:
        return None
    image = open_image(data)
    return Rendition(encode_png(image), info.format, HEIF_DECODER or "")


def encode_png(image: Image.Image) -> EncodedImage:
    """Lossless, deterministic encoding for derived artifacts (crops, masks, renders)."""
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=False, compress_level=6)
    return EncodedImage(buffer.getvalue(), "image/png", image.width, image.height)


def crop_region(data: bytes, region: NormalizedRegion | None) -> EncodedImage:
    """The selected region of an image as PNG; the whole image when no region."""
    image = open_image(data)
    if region is not None:
        image = image.crop(region.to_pixels(image.width, image.height))
    return encode_png(image)


def preview(data: bytes, region: NormalizedRegion | None = None) -> EncodedImage:
    """A browser preview (WebP) of an image or a region of it, bounded in size."""
    image = open_image(data)
    if region is not None:
        image = image.crop(region.to_pixels(image.width, image.height))
    image.thumbnail((PREVIEW_EDGE, PREVIEW_EDGE), Image.Resampling.LANCZOS)
    buffer = io.BytesIO()
    image.save(buffer, format="WEBP", quality=85, method=4)
    return EncodedImage(buffer.getvalue(), "image/webp", image.width, image.height)


def mask_from_regions(width: int, height: int, regions: list[NormalizedRegion]) -> EncodedImage:
    """A single-channel mask: white inside the regions, black elsewhere."""
    from PIL import ImageDraw

    mask = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(mask)
    for region in regions:
        left, top, right, bottom = region.to_pixels(width, height)
        draw.rectangle((left, top, right - 1, bottom - 1), fill=255)
    return encode_png(mask)


def pixel_digest(data: bytes) -> str:
    """SHA-256 over decoded pixels and size: equal images, regardless of encoder bytes."""
    image = open_image(data)
    digest = hashlib.sha256(f"{image.width}x{image.height}:".encode())
    digest.update(image.tobytes())
    return digest.hexdigest()
