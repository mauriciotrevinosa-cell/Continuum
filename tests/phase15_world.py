"""A synthetic whole-Vault world for Phase 1.5 tests.

Builds, under a temporary directory, a Source Vault shaped like a real one -
series folders, material folders, manga archives with chapter folders, video
archives split into parts, standalone episodes with good and poor names, a
mixed archive, software, junk and a damaged archive - plus an intake folder of
collected artwork with download-style names, a disguised JPEG, an installer and
exact duplicates. The acquisition engine's index lists only *some* of the Vault
(with hashes for some), as a real, slightly stale engine scan does.

All content is invented (D-18 / A-05): generated pictures, made-up titles and
handles. Nothing here resembles a real work.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from continuum_config import Settings

from tests.conftest import TEST_DATABASE_URL
from tests.phase1_world import mp4_bytes, picture

SERIES = "Demo Orbit"
ALIAS = "Kido Orbit Monogatari"

VOLUME = f"{SERIES}/manga/demo-orbit-part-01.cbz"
VOLUME_COPY = f"{SERIES}/manga/copies/demo-orbit-part-01 (1).cbz"
VOLUME_PAGES = {
    "Ch0001/001.png": 1,
    "Ch0001/002.png": 2,
    "Ch0001/ComicInfo.xml": None,
    "Ch1.5/001.png": 3,
    "Ch0002/001.png": 4,
    "Ch0002/002.png": 5,
    "Ch0002/003.png": 6,
}
SEASON_PART_1 = f"{SERIES}/anime/Season 2-20260101T000000Z-1-001.zip"
SEASON_PART_2 = f"{SERIES}/anime/Season 2-20260101T000000Z-1-002.zip"
SEASON_MEMBERS = {
    SEASON_PART_1: (
        f"Season 2/[Group] {ALIAS} - S02E02.mkv",
        f"Season 2/[Group] {ALIAS} - S02E01.mkv",
    ),
    SEASON_PART_2: (f"Season 2/[Group] {ALIAS} - S02E03 Recap.mkv",),
}
EPISODE_GOOD = f"{SERIES}/anime/{SERIES} - S01E01.mp4"
EPISODE_POOR = f"{SERIES}/anime/dmorbt-07.mp4"
MOVIE = f"{SERIES}/anime/{SERIES} The Movie (2031) [BD].mkv"
MIXED = f"{SERIES}/extras/bonus-disc.zip"
SOFTWARE = f"{SERIES}/tools/reader-setup.zip"
NOTES = f"{SERIES}/notes.txt"
DAMAGED = f"{SERIES}/manga/damaged-part.cbz"
RAR = f"{SERIES}/manga/old-scan.rar"
EMPTY = f"{SERIES}/manga/empty.cbz"
LOOSE = "loose-page.png"

INTAKE_IMAGES = {
    "orbit.sketches_1700000000_3100000000000000001_4200.jpg": ("JPEG", 11),
    "orbit.sketches_1700000300_3100000000000000002_4200 (1).jpg": ("JPEG", 11),  # same bytes
    "moon_painter_1700500000_3100000000000000003_7700.heic": ("JPEG", 12),  # JPEG named .heic
    "moon_painter_1700600000_3100000000000000004_7700.webp": ("WEBP", 13),
    "untitled-scan.png": ("PNG", 14),
}
INTAKE_CLIP = "orbit.sketches_1700700000_3100000000000000005_4200.mp4"
INTAKE_INSTALLER = "Some Installer.exe"
INTAKE_DUPLICATE_CLIP = "orbit.sketches_1700700000_3100000000000000005_4200 (1).mp4"


@dataclass
class Phase15World:
    root: Path
    vault: Path
    intake: Path
    data_home: Path
    acquisition: Path
    bytes_of: dict[str, bytes] = field(default_factory=dict)

    def settings(self, **overrides: object) -> Settings:
        values: dict[str, object] = {
            "_env_file": None,
            "data_home": str(self.data_home),
            "source_vault_root": str(self.vault),
            "acquisition_data_dir": str(self.acquisition),
            "intake_roots": f"Sketchbook:fan_art={self.intake}",
            "database_url": TEST_DATABASE_URL,
            "project_sources": str(self.root / "projects"),
        }
        values.update(overrides)
        return Settings(**values)  # type: ignore[arg-type]

    def sha256(self, relative: str, *, intake: bool = False) -> str:
        base = self.intake if intake else self.vault
        return hashlib.sha256((base / relative).read_bytes()).hexdigest()


def _zip(path: Path, members: dict[str, bytes], *, compression: int = zipfile.ZIP_DEFLATED) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", compression=compression) as archive:
        for name, data in members.items():
            archive.writestr(name, data)


def mkv_bytes(seed: int, length: int = 6000) -> bytes:
    """Bytes with a Matroska signature (never decoded)."""
    return b"\x1a\x45\xdf\xa3" + bytes((seed * 7 + i) % 251 for i in range(length))


def build_phase15_world(tmp: Path) -> Phase15World:
    vault = tmp / "vault"
    intake = tmp / "intake" / "Sketchbook"
    data_home = tmp / "ContinuumData"
    acquisition = tmp / "acquisition"
    for directory in (vault, intake, data_home, acquisition, tmp / "projects"):
        directory.mkdir(parents=True, exist_ok=True)
    world = Phase15World(tmp, vault, intake, data_home, acquisition)

    pages = {
        name: (picture(seed, (200, 280)) if seed is not None else b"<ComicInfo/>")
        for name, seed in VOLUME_PAGES.items()
    }
    _zip(vault / VOLUME, dict(reversed(list(pages.items()))))
    (vault / VOLUME_COPY).parent.mkdir(parents=True, exist_ok=True)
    (vault / VOLUME_COPY).write_bytes((vault / VOLUME).read_bytes())
    for part, names in SEASON_MEMBERS.items():
        _zip(vault / part, {name: mkv_bytes(i + 1) for i, name in enumerate(names)})
    for relative, data in (
        (EPISODE_GOOD, mp4_bytes(1)),
        (EPISODE_POOR, mp4_bytes(2)),
        (MOVIE, mkv_bytes(9)),
        (LOOSE, picture(30)),
        (NOTES, b"remember to rescan"),
        (DAMAGED, b"PK\x03\x04 this is not really an archive"),
        (RAR, b"Rar!\x1a\x07\x00 invented"),
        (EMPTY, b""),
    ):
        (vault / relative).parent.mkdir(parents=True, exist_ok=True)
        (vault / relative).write_bytes(data)
    _zip(
        vault / MIXED,
        {
            "Booklet/01.png": picture(40),
            "Booklet/02.png": picture(41),
            "Video/making-of.mp4": mp4_bytes(5),
        },
    )
    _zip(vault / SOFTWARE, {"app/setup.exe": b"MZ\x90\x00", "app/icon.png": picture(42)})
    (vault / "Thumbs.db").write_bytes(b"system")

    for name, (fmt, seed) in INTAKE_IMAGES.items():
        data = picture(seed, fmt=fmt)
        world.bytes_of[name] = data
        (intake / name).write_bytes(data)
    world.bytes_of[INTAKE_CLIP] = mp4_bytes(21)
    (intake / INTAKE_CLIP).write_bytes(world.bytes_of[INTAKE_CLIP])
    (intake / INTAKE_DUPLICATE_CLIP).write_bytes(world.bytes_of[INTAKE_CLIP])
    (intake / INTAKE_INSTALLER).write_bytes(b"MZ\x90\x00 invented installer")

    # The engine scanned before the season parts, the movie and the extras arrived,
    # and hashed only the volume.
    def record(
        relative: str, kind: str, *, hashed: bool = False, **archive: object
    ) -> dict[str, object]:
        info = (vault / relative).stat()
        out: dict[str, object] = {
            "size": info.st_size,
            "mtime_ns": info.st_mtime_ns,
            "kind": kind,
            "ext": os.path.splitext(relative)[1],
            "archive": archive or None,
        }
        if hashed:
            out["sha256"] = hashlib.sha256((vault / relative).read_bytes()).hexdigest()
        return out

    files = {
        VOLUME: record(
            VOLUME, "archive", hashed=True, images=6, videos=0, series=f"{SERIES} (ComicInfo)"
        ),
        EPISODE_GOOD: record(EPISODE_GOOD, "video"),
        EPISODE_POOR: record(EPISODE_POOR, "video"),
        LOOSE: record(LOOSE, "image"),
    }
    now = dt.datetime.now(tz=dt.UTC).isoformat(timespec="seconds")
    (acquisition / "vault-index.json").write_text(
        json.dumps({"vault_root": str(vault), "generated_at": now, "files": files}),
        encoding="utf-8",
    )
    (acquisition / "works-catalog.json").write_text(
        json.dumps(
            {
                "families": [
                    {
                        "family": SERIES,
                        "vault_family_folder": SERIES,
                        "works": [{"work": SERIES, "titles": {"romaji": ALIAS}, "aliases": []}],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return world
