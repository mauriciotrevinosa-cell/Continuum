"""Opening held media: opaque ids only, read-only, never outside the Vault.

The viewer contract under test:

* a client addresses media by opaque id; no route accepts a path (F-50);
* an id resolves only to a file the scan listed, inside the configured Vault;
* a poisoned index - a traversal entry, a link pointing outside - still
  cannot make the API read outside the Vault;
* archives are containers: pages are served by position, bundled videos are
  listed and never passed off as streamable episodes;
* video streams honour byte ranges;
* nothing in the Vault changes.

All content is invented (D-18 / A-05).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import zipfile
from pathlib import Path
from typing import Any

import pytest
from continuum_api import create_app
from continuum_config import Settings
from continuum_storage import media_id_for
from fastapi.testclient import TestClient

from tests.conftest import try_junction, try_symlink

FAMILY = "demo-orbit"
PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00"
    b"\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)
VIDEO = bytes(range(256)) * 40  # 10,240 bytes standing in for an episode


def _zip(path: Path, entries: dict[str, bytes]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in entries.items():
            archive.writestr(name, data)


def _snapshot(root: Path) -> dict[str, str]:
    out = {}
    for base, _dirs, files in os.walk(root):
        for name in files:
            full = Path(base) / name
            out[str(full.relative_to(root))] = hashlib.sha256(full.read_bytes()).hexdigest()
    return out


@pytest.fixture
def world(tmp_path: Path) -> dict[str, Any]:
    vault = tmp_path / "vault"
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("not yours", encoding="utf-8")

    manga = "Demo Orbit/manga/demo-orbit-part-01.zip"
    _zip(vault / manga, {"Ch0002/002.png": PNG, "Ch0001/001.png": PNG, "Ch0001/010.png": PNG})
    episode = "Demo Orbit/anime/Demo Orbit - S01E02.mp4"
    (vault / episode).parent.mkdir(parents=True, exist_ok=True)
    (vault / episode).write_bytes(VIDEO)
    bundle = "Demo Orbit/anime/season-2-bundle.zip"
    _zip(
        vault / bundle,
        {"Season 2/Demo Orbit S2 - 01.mkv": b"x", "Season 2/Demo Orbit S2 - 02.mkv": b"y"},
    )
    notes = "Demo Orbit/extras/notes.txt"
    (vault / notes).parent.mkdir(parents=True, exist_ok=True)
    (vault / notes).write_text("hello", encoding="utf-8")
    unmatched = "Demo Orbit/manga/stray-part-09.zip"
    _zip(vault / unmatched, {"001.png": PNG})

    def record(rel: str, kind: str, **archive: Any) -> dict[str, Any]:
        full = vault / rel
        return {
            "size": full.stat().st_size if full.exists() else 1,
            "mtime_ns": full.stat().st_mtime_ns if full.exists() else 1,
            "kind": kind,
            "ext": os.path.splitext(rel)[1],
            "archive": archive or None,
        }

    files: dict[str, Any] = {
        manga: record(manga, "archive", images=3, videos=0, chapters=["1", "2"]),
        episode: record(episode, "video"),
        bundle: record(
            bundle,
            "archive",
            images=0,
            videos=2,
            video_entries=[
                {"name": "Season 2/Demo Orbit S2 - 01.mkv", "size": 1},
                {"name": "Season 2/Demo Orbit S2 - 02.mkv", "size": 1},
            ],
        ),
        notes: record(notes, "other"),
        unmatched: record(unmatched, "archive", images=1, videos=0),
        # A poisoned index: entries no honest scan would produce.
        "../outside/secret.txt": {"size": 9, "kind": "document", "ext": ".pdf"},
        "Demo Orbit/../../outside/secret.pdf": {"size": 9, "kind": "document", "ext": ".pdf"},
    }
    link_rel = "Demo Orbit/extras/escape.pdf"
    link_dir = vault / "Demo Orbit" / "linked"
    linked = try_symlink(vault / link_rel, outside / "secret.txt") or try_junction(
        link_dir, outside
    )
    if (vault / link_rel).is_symlink():
        files[link_rel] = {"size": 9, "kind": "document", "ext": ".pdf"}
    if link_dir.exists():
        files["Demo Orbit/linked/secret.pdf"] = {"size": 9, "kind": "document", "ext": ".pdf"}

    data = tmp_path / "acquisition"
    data.mkdir()
    now = dt.datetime.now(tz=dt.UTC).isoformat(timespec="seconds")
    documents = {
        "vault-index.json": {"vault_root": str(vault), "generated_at": now, "files": files},
        "vault-layout.json": {
            "generated_at": now,
            "vault_root": str(vault),
            "families": [
                {
                    "family_id": FAMILY,
                    "family_title": "Demo Orbit",
                    "family_path": str(vault / "Demo Orbit"),
                    "classes": {"manga": {"unattributed_rels": [unmatched]}},
                    "works": [
                        {
                            "work_id": "o/main",
                            "work": "Demo Orbit",
                            "material_class": "manga",
                            "relationship_type": "MAIN_WORK",
                            "coverage_status": "COMPLETE",
                        },
                        {
                            "work_id": "o/tv",
                            "work": "Demo Orbit TV",
                            "material_class": "anime",
                            "relationship_type": "PARALLEL_ADAPTATION",
                            "coverage_status": "UNKNOWN",
                        },
                    ],
                }
            ],
        },
        "vault-coverage.json": {
            "generated_at": now,
            "works": {
                "o/main": {
                    "status": "COMPLETE",
                    "media": "pages",
                    "media_files": [manga],
                    "units": [
                        {
                            "file": manga,
                            "kind": "archive",
                            "chapters": 2,
                            "chapter_text": "1-2",
                            "volumes": [],
                            "pages": 3,
                        }
                    ],
                },
                "o/tv": {
                    "status": "UNKNOWN",
                    "media": "video",
                    "media_files": [bundle, episode],
                    "units": [
                        {"file": episode, "kind": "video", "season": 1, "episode": 2},
                        {
                            "file": bundle,
                            "kind": "archive",
                            "contained_videos": 2,
                            "contained_episodes": [
                                {"season": 2, "episode": 1},
                                {"season": 2, "episode": 2},
                            ],
                        },
                    ],
                },
            },
        },
    }
    for name, document in documents.items():
        (data / name).write_text(json.dumps(document), encoding="utf-8")

    return {
        "vault": vault,
        "data": data,
        "manga": manga,
        "episode": episode,
        "bundle": bundle,
        "notes": notes,
        "unmatched": unmatched,
        "linked": linked,
        "files": files,
    }


def _client(data_home: Path, world: dict[str, Any], vault: Path | None = None) -> TestClient:
    settings = Settings(
        _env_file=None,
        data_home=str(data_home),
        source_vault_root=str(vault or world["vault"]),
        acquisition_data_dir=str(world["data"]),
    )
    return TestClient(create_app(settings))


# ---------------------------------------------------------------------------
def test_a_work_lists_openable_units_without_paths(data_home: Path, world: dict[str, Any]) -> None:
    with _client(data_home, world) as client:
        response = client.get("/library/media", params={"work": "o/tv"})
    assert response.status_code == 200
    body = response.json()
    assert body["available"] is True
    units = {u["label"]: u for u in body["units"]}
    assert set(units) == {"S1 · E2", "season-2-bundle"}
    assert units["S1 · E2"]["view"] == "video"
    assert units["S1 · E2"]["plays_in_browser"] == "yes"
    bundle = units["season-2-bundle"]
    assert bundle["view"] == "bundle", "an archive of videos is not a video"
    assert bundle["contained_videos"] == 2
    assert [(c["season"], c["episode"]) for c in bundle["contained"]] == [(2, 1), (2, 2)]
    assert all(u["id"].startswith("m1_") for u in body["units"])
    text = response.text
    assert str(world["vault"]) not in text and "Demo Orbit/anime" not in text, "no path leaks"


def test_image_archive_pages_are_served_by_position(data_home: Path, world: dict[str, Any]) -> None:
    media = media_id_for(world["manga"])
    with _client(data_home, world) as client:
        listing = client.get(f"/library/media/{media}/pages").json()
        page = client.get(f"/library/media/{media}/pages/0")
        beyond = client.get(f"/library/media/{media}/pages/3")
    assert [p["label"] for p in listing["pages"]] == ["001.png", "010.png", "002.png"]
    assert [(c["label"], c["first"], c["count"]) for c in listing["chapters"]] == [
        ("Ch0001", 0, 2),
        ("Ch0002", 2, 1),
    ]
    assert page.status_code == 200
    assert page.headers["content-type"] == "image/png"
    assert page.content == PNG
    assert beyond.status_code == 404


def test_video_streams_with_byte_ranges(data_home: Path, world: dict[str, Any]) -> None:
    media = media_id_for(world["episode"])
    with _client(data_home, world) as client:
        whole = client.get(f"/library/media/{media}/content")
        part = client.get(f"/library/media/{media}/content", headers={"Range": "bytes=100-199"})
        tail = client.get(f"/library/media/{media}/content", headers={"Range": "bytes=-16"})
        bad = client.get(f"/library/media/{media}/content", headers={"Range": "bytes=99999-"})
        junk = client.get(f"/library/media/{media}/content", headers={"Range": "lines=1-2"})
    assert whole.status_code == 200
    assert whole.content == VIDEO
    assert whole.headers["accept-ranges"] == "bytes"
    assert part.status_code == 206
    assert part.content == VIDEO[100:200]
    assert part.headers["content-range"] == f"bytes 100-199/{len(VIDEO)}"
    assert tail.status_code == 206 and tail.content == VIDEO[-16:]
    assert bad.status_code == 416
    assert junk.status_code == 416


def test_bundled_videos_are_listed_not_streamed(data_home: Path, world: dict[str, Any]) -> None:
    media = media_id_for(world["bundle"])
    with _client(data_home, world) as client:
        listing = client.get(f"/library/media/{media}/pages").json()
        stream = client.get(f"/library/media/{media}/content")
    assert [v["name"] for v in listing["videos"]] == [
        "Demo Orbit S2 - 01.mkv",
        "Demo Orbit S2 - 02.mkv",
    ]
    assert listing["pages"] == []
    assert stream.status_code == 404


def test_unsupported_files_are_described_honestly(data_home: Path, world: dict[str, Any]) -> None:
    media = media_id_for(world["notes"])
    with _client(data_home, world) as client:
        detail = client.get(f"/library/media/{media}").json()
        stream = client.get(f"/library/media/{media}/content")
        pages = client.get(f"/library/media/{media}/pages")
    assert detail["unit"]["view"] == "none"
    assert stream.status_code == 404
    assert pages.status_code == 404


def test_detail_gives_position_within_the_work(data_home: Path, world: dict[str, Any]) -> None:
    media = media_id_for(world["episode"])
    with _client(data_home, world) as client:
        detail = client.get(f"/library/media/{media}").json()
    assert detail["work_id"] == "o/tv"
    assert detail["family_id"] == FAMILY
    assert detail["position"] == 0 and detail["total"] == 2
    assert detail["next_id"] == media_id_for(world["bundle"])


@pytest.mark.parametrize(
    "bad",
    [
        "m1_" + "0" * 32,  # well formed, unknown
        "m1_" + "g" * 32,
        "m1_" + "a" * 31,
        "..%2F..%2Foutside%2Fsecret.txt",
        "%2E%2E%5Coutside%5Csecret.txt",
        "C:%5CWindows%5Cwin.ini",
        "%5C%5Cserver%5Cshare%5Cfile",
        "file:%2F%2F%2Fetc%2Fpasswd",
    ],
)
def test_bad_ids_are_refused(data_home: Path, world: dict[str, Any], bad: str) -> None:
    with _client(data_home, world) as client:
        for suffix in ("", "/content", "/pages", "/pages/0"):
            response = client.get(f"/library/media/{bad}{suffix}")
            assert response.status_code in (404, 422), (bad, suffix, response.status_code)
            assert "not yours" not in response.text


def test_a_poisoned_index_cannot_reach_outside_the_vault(
    data_home: Path, world: dict[str, Any]
) -> None:
    """Even entries written into the scan document are resolved inside the Vault or refused."""
    hostile = [rel for rel in world["files"] if ".." in rel or "escape" in rel or "linked" in rel]
    assert len(hostile) >= 2
    with _client(data_home, world) as client:
        for rel in hostile:
            media = media_id_for(rel)
            for suffix in ("", "/content"):
                response = client.get(f"/library/media/{media}{suffix}")
                assert response.status_code == 404, (rel, suffix, response.status_code)
                assert "not yours" not in response.text


def test_no_media_route_takes_a_path(data_home: Path, world: dict[str, Any]) -> None:
    with _client(data_home, world) as client:
        spec = client.get("/openapi.json").json()
        ignored = client.get(
            "/library/media", params={"path": str(world["vault"] / world["notes"])}
        )
    for route, operations in spec["paths"].items():
        if not route.startswith("/library/media"):
            continue
        for operation in operations.values():
            names = {p["name"] for p in operation.get("parameters", [])}
            assert not names & {"path", "file", "filepath", "filename", "dir", "directory"}, route
    assert ignored.status_code == 422, "a path is not a way to ask for media"


def test_viewing_is_unavailable_when_the_vault_does_not_match_the_scan(
    data_home: Path, world: dict[str, Any], tmp_path: Path
) -> None:
    other = tmp_path / "another-vault"
    other.mkdir()
    media = media_id_for(world["episode"])
    with _client(data_home, world, vault=other) as client:
        status = client.get("/library/media/status").json()
        response = client.get(f"/library/media/{media}/content")
    assert status["available"] is False
    assert "different folder" in status["reason"]
    assert response.status_code == 404


def test_unmatched_material_can_be_opened_too(data_home: Path, world: dict[str, Any]) -> None:
    with _client(data_home, world) as client:
        body = client.get("/library/media", params={"family": FAMILY, "material": "manga"}).json()
    assert body["unmapped"] is True
    assert body["state"] == "NEEDS_MAPPING"
    assert [u["id"] for u in body["units"]] == [media_id_for(world["unmatched"])]


def test_viewing_never_changes_the_vault(data_home: Path, world: dict[str, Any]) -> None:
    before = _snapshot(world["vault"])
    with _client(data_home, world) as client:
        for rel in (world["manga"], world["episode"], world["bundle"], world["notes"]):
            media = media_id_for(rel)
            client.get(f"/library/media/{media}")
            client.get(f"/library/media/{media}/pages")
            client.get(f"/library/media/{media}/pages/0")
            client.get(f"/library/media/{media}/content", headers={"Range": "bytes=0-9"})
    assert _snapshot(world["vault"]) == before
