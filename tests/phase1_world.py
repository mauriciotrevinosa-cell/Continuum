"""A synthetic held-media world for Phase 1 tests.

Builds, under a temporary directory:

* a Source Vault holding an invented manga archive, a standalone image, a PDF
  and a video;
* the acquisition engine's ``vault-index.json`` describing them (with the
  engine's recorded SHA-256 for some files, as a real scan writes);
* writable ContinuumData roots.

All content is invented (D-18 / A-05): generated pictures, made-up titles.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import io
import json
import os
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from continuum_config import WRITABLE_ROOT_KEYS, Settings
from continuum_storage import (
    AcquisitionStore,
    DerivedStore,
    MediaLibrary,
    SourceAccess,
    media_id_for,
)
from PIL import Image, ImageDraw

MANGA = "Demo Orbit/manga/demo-orbit-v01.cbz"
MANGA_ENTRIES = ("Ch0001/001.png", "Ch0001/002.png", "Ch0002/003.png")
ART = "Demo Orbit/art/key-visual.png"
GUIDE = "Demo Orbit/books/guide.pdf"
EPISODE = "Demo Orbit/anime/Demo Orbit - S01E01.mp4"
#: An archive whose entry name is hostile; it must not be addressable.
HOSTILE = "Demo Orbit/manga/hostile.cbz"


def clean_domain_tables(session: object) -> None:
    """Empty every Phase 1 domain table in the *test* database."""
    from continuum_db.tiers import TABLE_REGISTRY, Tier
    from sqlalchemy import text
    from sqlalchemy.orm import Session

    assert isinstance(session, Session)
    database = session.get_bind().url.database or ""
    assert database.endswith("_test"), f"refusing to empty {database!r}"
    tables = [name for name, (_phase, tier) in TABLE_REGISTRY.items() if tier > Tier.OPERATIONAL]
    session.execute(text(f"TRUNCATE {', '.join(tables)} CASCADE"))
    session.commit()


def picture(seed: int, size: tuple[int, int] = (240, 320), *, fmt: str = "PNG") -> bytes:
    """A small, distinct, decodable image."""
    image = Image.new("RGB", size, ((seed * 53) % 256, (seed * 97) % 256, (seed * 29) % 256))
    draw = ImageDraw.Draw(image)
    draw.rectangle((10 + seed % 40, 20, 120, 200), outline=(255, 255, 255), width=3)
    draw.ellipse((60, 60 + seed % 50, 200, 220), outline=(0, 0, 0), width=4)
    buffer = io.BytesIO()
    image.save(buffer, format=fmt)
    return buffer.getvalue()


def mp4_bytes(seed: int = 0, length: int = 4096) -> bytes:
    """Bytes with an MP4 'ftyp' signature (not decodable video; never decoded)."""
    body = bytes((seed + i) % 256 for i in range(length))
    return b"\x00\x00\x00\x18ftypisom" + body


def snapshot(root: Path) -> dict[str, tuple[int, int, str]]:
    """(size, mtime_ns, sha256) of every file under a root."""
    out: dict[str, tuple[int, int, str]] = {}
    for base, _dirs, files in os.walk(root):
        for name in files:
            full = Path(base) / name
            info = full.stat()
            digest = hashlib.sha256(full.read_bytes()).hexdigest()
            out[str(full.relative_to(root))] = (info.st_size, info.st_mtime_ns, digest)
    return out


@dataclass
class World:
    root: Path
    vault: Path
    data_home: Path
    acquisition_dir: Path
    page_bytes: dict[str, bytes] = field(default_factory=dict)
    art_bytes: bytes = b""

    @property
    def settings(self) -> Settings:
        return Settings(
            _env_file=None,
            data_home=str(self.data_home),
            source_vault_root=str(self.vault),
        )

    def derived(self) -> DerivedStore:
        settings = self.settings
        store = DerivedStore({key: settings.root(key) for key in WRITABLE_ROOT_KEYS})
        for key in WRITABLE_ROOT_KEYS:
            store.ensure_root(key)
        return store

    def media(self) -> MediaLibrary:
        return MediaLibrary(AcquisitionStore(str(self.acquisition_dir)), str(self.vault))

    def sources(self) -> SourceAccess:
        return SourceAccess(self.media(), str(self.vault))

    @staticmethod
    def id_of(relative: str) -> str:
        return media_id_for(relative)

    def sha256_of(self, relative: str) -> str:
        return hashlib.sha256((self.vault / relative).read_bytes()).hexdigest()


def build_world(tmp: Path, *, record_engine_hash: bool = True) -> World:
    vault = tmp / "vault"
    data_home = tmp / "ContinuumData"
    acquisition = tmp / "acquisition"
    for directory in (vault, data_home, acquisition):
        directory.mkdir(parents=True, exist_ok=True)
    world = World(root=tmp, vault=vault, data_home=data_home, acquisition_dir=acquisition)

    (vault / MANGA).parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(vault / MANGA, "w") as archive:
        # Written out of reading order: the reader sorts by folder and number.
        for position, entry in reversed(list(enumerate(MANGA_ENTRIES))):
            data = picture(position + 1, (300, 420))
            world.page_bytes[entry] = data
            archive.writestr(entry, data)
        archive.writestr("ComicInfo.xml", b"<ComicInfo/>")

    with zipfile.ZipFile(vault / HOSTILE, "w") as archive:
        archive.writestr("../escape/001.png", picture(40))

    (vault / ART).parent.mkdir(parents=True, exist_ok=True)
    world.art_bytes = picture(9, (400, 300))
    (vault / ART).write_bytes(world.art_bytes)

    (vault / GUIDE).parent.mkdir(parents=True, exist_ok=True)
    (vault / GUIDE).write_bytes(b"%PDF-1.4\n% invented guide\n%%EOF\n")

    (vault / EPISODE).parent.mkdir(parents=True, exist_ok=True)
    (vault / EPISODE).write_bytes(mp4_bytes(3))

    def record(rel: str, kind: str, **archive: object) -> dict[str, object]:
        info = (vault / rel).stat()
        entry: dict[str, object] = {
            "size": info.st_size,
            "mtime_ns": info.st_mtime_ns,
            "kind": kind,
            "ext": os.path.splitext(rel)[1],
            "archive": archive or None,
        }
        if record_engine_hash:
            entry["sha256"] = hashlib.sha256((vault / rel).read_bytes()).hexdigest()
        return entry

    now = dt.datetime.now(tz=dt.UTC).isoformat(timespec="seconds")
    files = {
        MANGA: record(MANGA, "archive", images=3, videos=0, chapters=["1", "2"]),
        HOSTILE: record(HOSTILE, "archive", images=1, videos=0),
        ART: record(ART, "image"),
        GUIDE: record(GUIDE, "document"),
        EPISODE: record(EPISODE, "video"),
    }
    (acquisition / "vault-index.json").write_text(
        json.dumps({"vault_root": str(vault), "generated_at": now, "files": files}),
        encoding="utf-8",
    )
    return world
