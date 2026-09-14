"""What bytes are, from their signature alone - before any decoder sees them.

File names and client-declared MIME types are hints at best: the real fan-art
intake holds JPEG bytes named ``.heic``, and ISO-BMFF ``ftyp`` boxes open both
MP4 video and HEIC stills. Every intake decision (image, video clip, or
refuse) is taken from content, here, and never from an extension.

Only the first few hundred bytes are inspected; nothing is decoded.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

__all__ = ["HEIF_BRANDS", "Sniffed", "sniff"]

#: ISO-BMFF brands of HEVC-coded HEIF stills and sequences (HEIC files).
HEIF_BRANDS: Final = frozenset(
    {b"heic", b"heix", b"heim", b"heis", b"hevc", b"hevx", b"hevm", b"hevs"}
)
#: Generic HEIF brands; the coded format is decided by the decoder.
_GENERIC_HEIF: Final = frozenset({b"mif1", b"msf1", b"miaf"})
_AVIF_BRANDS: Final = frozenset({b"avif", b"avis"})
_MAX_FTYP: Final = 512
_RAR4: Final = bytes.fromhex("526172211a0700")
_RAR5: Final = bytes.fromhex("526172211a070100")
_SEVEN_ZIP: Final = bytes.fromhex("377abcaf271c")
_TS_PACKET: Final = 188
_TS_SYNC: Final = 0x47


@dataclass(frozen=True, slots=True)
class Sniffed:
    kind: Literal["image", "video", "other"]
    #: JPEG, PNG, WEBP, GIF, BMP, HEIF, AVIF, TIFF, MP4, QUICKTIME, MATROSKA,
    #: AVI, MPEG_TS, EXECUTABLE, OLE, ZIP, RAR, SEVEN_ZIP, PDF, EMPTY or UNKNOWN.
    format: str
    #: What a person would call it, for refusal messages.
    description: str


def _ftyp_brands(data: bytes) -> list[bytes]:
    """Major brand followed by compatible brands of a leading ``ftyp`` box."""
    if len(data) < 16 or data[4:8] != b"ftyp":
        return []
    size = int.from_bytes(data[0:4], "big")
    end = min(size if 16 <= size <= _MAX_FTYP else 16, len(data))
    brands = [data[8:12]]
    brands.extend(data[offset : offset + 4] for offset in range(16, end - 3, 4))
    return brands


def sniff(data: bytes) -> Sniffed:
    """Classify bytes by signature. Never raises."""
    head = data[:64]
    if not head:
        return Sniffed("other", "EMPTY", "an empty file")
    if head[:3] == b"\xff\xd8\xff":
        return Sniffed("image", "JPEG", "a JPEG image")
    if head[:8] == b"\x89PNG\r\n\x1a\n":
        return Sniffed("image", "PNG", "a PNG image")
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return Sniffed("image", "WEBP", "a WebP image")
    if head[:4] == b"RIFF" and head[8:12] == b"AVI ":
        return Sniffed("video", "AVI", "an AVI video")
    if head[:6] in (b"GIF87a", b"GIF89a"):
        return Sniffed("image", "GIF", "a GIF image")
    if head[:2] == b"BM":
        return Sniffed("image", "BMP", "a BMP image")
    if head[:4] in (b"II*\x00", b"MM\x00*"):
        return Sniffed("image", "TIFF", "a TIFF image")
    brands = _ftyp_brands(data)
    if brands:
        if any(b in _AVIF_BRANDS for b in brands) and not any(b in HEIF_BRANDS for b in brands):
            return Sniffed("image", "AVIF", "an AVIF image")
        if any(b in HEIF_BRANDS for b in brands) or brands[0] in _GENERIC_HEIF:
            return Sniffed("image", "HEIF", "a HEIC/HEIF image")
        if brands[0] == b"qt  ":
            return Sniffed("video", "QUICKTIME", "a QuickTime video")
        return Sniffed("video", "MP4", "an MP4 video")
    if head[:4] == b"\x1a\x45\xdf\xa3":
        return Sniffed("video", "MATROSKA", "a Matroska/WebM video")
    if head[:2] == b"MZ":
        return Sniffed("other", "EXECUTABLE", "a Windows program or installer")
    if head[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
        return Sniffed("other", "OLE", "an installer package or Office document")
    if head[:4] in (b"PK\x03\x04", b"PK\x05\x06"):
        return Sniffed("other", "ZIP", "a ZIP archive")
    if head[:5] == b"%PDF-":
        return Sniffed("other", "PDF", "a PDF document")
    if head.startswith((_RAR4, _RAR5)):
        return Sniffed("other", "RAR", "a RAR archive")
    if head.startswith(_SEVEN_ZIP):
        return Sniffed("other", "SEVEN_ZIP", "a 7-Zip archive")
    if len(data) > 2 * _TS_PACKET and all(data[i * _TS_PACKET] == _TS_SYNC for i in range(3)):
        return Sniffed("video", "MPEG_TS", "an MPEG transport stream")
    return Sniffed("other", "UNKNOWN", "a file that is not an image or a video clip")
