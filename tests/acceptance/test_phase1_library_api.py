"""The reference vault over HTTP: ids only, read-only sources, honest errors.

Under test (Phase 1 M1 API, F-50, expansion sections 17-19, 25 and the inbox):

* a page region becomes a reference through ``media_id`` + page index; the
  response navigates back to the page and never names a path or the Vault;
* the Character Vault, Style Vault and project mode assignments are served;
* inbox intake takes raw bytes with metadata in the query - no filename or
  path parameter - and links are stored, never fetched;
* unknown ids are 404, stale versions 409, hostile input 422, and request
  bodies refuse fields they do not declare;
* the Vault is byte-identical afterwards.

PostgreSQL (the isolated test database). All content is invented.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from continuum_api import create_app
from continuum_config import Settings
from continuum_db.session import session_scope
from continuum_imaging import probe
from fastapi.testclient import TestClient

from tests.conftest import TEST_DATABASE_URL
from tests.phase1_world import (
    EPISODE,
    MANGA,
    MANGA_ENTRIES,
    World,
    build_world,
    clean_domain_tables,
    mp4_bytes,
    picture,
    snapshot,
)

PROJECT = "demo-project"


@pytest.fixture
def world(tmp_path: Path, db_settings: Settings) -> World:
    with session_scope(db_settings) as session:
        clean_domain_tables(session)
    return build_world(tmp_path)


@pytest.fixture
def client(world: World) -> Iterator[TestClient]:
    settings = Settings(
        _env_file=None,
        data_home=str(world.data_home),
        source_vault_root=str(world.vault),
        acquisition_data_dir=str(world.acquisition_dir),
        database_url=TEST_DATABASE_URL,
    )
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def no_paths(world: World, text: str) -> None:
    assert str(world.vault) not in text
    assert str(world.root) not in text
    assert "Demo Orbit/manga" not in text and "Demo Orbit/anime" not in text


class TestReferencesOverHttp:
    def test_page_region_to_character_vault_roundtrip(
        self, client: TestClient, world: World
    ) -> None:
        before = snapshot(world.vault)
        hero = ok(client.post("/library/characters", json={"display_name": "Aster Vale"}), 201)
        outfit = ok(
            client.post(
                f"/library/characters/{hero['id']}/outfits", json={"name": "Guild uniform"}
            ),
            201,
        )
        created = client.post(
            "/library/references/from-source",
            json={
                "media_id": world.id_of(MANGA),
                "page_index": 2,
                "spec": {
                    "reference_class": "CANON",
                    "region": {"x": 0.25, "y": 0.25, "width": 0.5, "height": 0.5},
                    "uses": ["IDENTITY"],
                    "characters": [
                        {"character_id": hero["id"], "aspect": "FACE", "preferred": True},
                        {
                            "character_id": hero["id"],
                            "aspect": "OUTFIT",
                            "outfit_id": outfit["id"],
                        },
                    ],
                    "descriptors": [{"facet": "MOOD", "value": "determined"}],
                    "standings": [{"project_key": PROJECT, "standing": "CANONICAL_FOR_PROJECT"}],
                    "panel_sources": [
                        {
                            "project_key": PROJECT,
                            "episode": "S1E1",
                            "page": 40,
                            "role": "COMPOSITION",
                        }
                    ],
                },
            },
        )
        reference = ok(created, 201)
        no_paths(world, created.text)
        assert reference["locator"].endswith(f"#entry={MANGA_ENTRIES[2]}")
        assert reference["source"] == {
            "available": True,
            "media_id": world.id_of(MANGA),
            "page_index": 2,
            "time_ms": None,
            "held_name": "demo-orbit-v01.cbz",
        }
        assert reference["descriptors"][0]["origin_label"] == "USER TAGGED"

        image = client.get(f"/library/references/{reference['id']}/image")
        assert image.status_code == 200 and image.headers["content-type"] == "image/webp"
        assert (probe(image.content).width, probe(image.content).height) == (150, 210)

        vault = ok(client.get(f"/library/characters/{hero['id']}"))
        assert vault["identity"]["FACE"][0]["reference"]["id"] == reference["id"]
        assert vault["wardrobe"]["outfits"][0]["references"][0]["aspect"] == "OUTFIT"
        assert vault["project_standing"][PROJECT]["CANONICAL_FOR_PROJECT"] == [reference["id"]]

        sources = ok(client.get(f"/projects/{PROJECT}/panel-sources", params={"page": 40}))
        assert [s["reference"]["id"] for s in sources] == [reference["id"]]

        listed = client.get("/library/references", params={"character_id": hero["id"]})
        assert [r["id"] for r in ok(listed)] == [reference["id"]]
        no_paths(world, listed.text)

        removed = client.post(
            f"/library/references/{reference['id']}/remove",
            json={"row_version": reference["row_version"]},
        )
        ok(removed)
        assert ok(client.get("/library/references")) == []
        assert ok(client.get(f"/library/references/{reference['id']}"))["removed"] is True
        assert snapshot(world.vault) == before

    def test_style_vault_and_scoped_modes(self, client: TestClient, world: World) -> None:
        mode = ok(
            client.post(
                "/library/visual-modes",
                json={"name": "Comic squash", "category": "COMEDIC_DEFORMATION"},
            ),
            201,
        )
        hero = ok(client.post("/library/characters", json={"display_name": "Aster Vale"}), 201)
        ok(
            client.post(
                "/library/references/from-source",
                json={
                    "media_id": world.id_of(MANGA),
                    "page_index": 0,
                    "spec": {
                        "reference_class": "TECHNIQUE",
                        "techniques": [{"facet": "COMEDY", "visual_mode_id": mode["id"]}],
                    },
                },
            ),
            201,
        )
        style = ok(client.get("/library/visual-modes"))
        assert len(style["modes"][0]["references"]) == 1

        assignment = ok(
            client.post(
                f"/projects/{PROJECT}/visual-modes",
                json={
                    "visual_mode_id": mode["id"],
                    "scope": "EVENT",
                    "trigger": "CHARACTER_CONTROLLED",
                    "event_label": "shrinks to hide",
                    "character_id": hero["id"],
                },
            ),
            201,
        )
        assert ok(client.get(f"/projects/{PROJECT}/visual-modes"))[0]["id"] == assignment["id"]
        missing = client.post(
            f"/projects/{PROJECT}/visual-modes",
            json={
                "visual_mode_id": mode["id"],
                "scope": "EVENT",
                "trigger": "CHARACTER_CONTROLLED",
                "event_label": "x",
            },
        )
        assert missing.status_code == 422

    def test_errors_are_honest(self, client: TestClient, world: World) -> None:
        unknown = uuid.uuid4()
        assert client.get(f"/library/characters/{unknown}").status_code == 404
        assert client.get(f"/library/references/{unknown}/image").status_code == 404
        assert client.get("/library/characters/not-a-uuid").status_code == 422

        hero = ok(client.post("/library/characters", json={"display_name": "Aster Vale"}), 201)
        ok(
            client.post(
                f"/library/characters/{hero['id']}/update",
                json={"row_version": hero["row_version"], "changes": {"summary": "one"}},
            )
        )
        stale = client.post(
            f"/library/characters/{hero['id']}/update",
            json={"row_version": hero["row_version"], "changes": {"summary": "two"}},
        )
        assert stale.status_code == 409
        assert stale.json()["detail"]["error"] == "catalog.conflict"

        for body in (
            {"media_id": "../../etc/passwd", "page_index": 0, "spec": {"reference_class": "CANON"}},
            {
                "media_id": world.id_of(MANGA),
                "page_index": 99,
                "spec": {"reference_class": "CANON"},
            },
            {
                "media_id": world.id_of(MANGA),
                "page_index": 0,
                "spec": {"reference_class": "CANON", "origin": "GENERATED"},
            },
            {
                "media_id": world.id_of(MANGA),
                "page_index": 0,
                "spec": {
                    "reference_class": "CANON",
                    "region": {"x": 0.9, "y": 0, "width": 0.5, "height": 1},
                },
            },
            {
                "media_id": world.id_of(MANGA),
                "page_index": 0,
                "path": "C:\\ContinuumVault\\x.cbz",
                "spec": {"reference_class": "CANON"},
            },
        ):
            response = client.post("/library/references/from-source", json=body)
            assert response.status_code == 422, (body, response.text)
            no_paths(world, response.text)

        assert client.get("/projects/..%2Fescape/visual-modes").status_code in (404, 422)
        assert client.get("/projects/Demo Project/panel-sources").status_code == 422


class TestInboxOverHttp:
    def test_links_files_frames_and_acceptance(self, client: TestClient, world: World) -> None:
        before = snapshot(world.vault)
        links = ok(
            client.post(
                "/library/inbox/urls",
                json={
                    "label": "paste",
                    "entries": [
                        {"url": "https://art.example.org/p/1", "creator_handle": "@inkfox"},
                        {"url": "https://art.example.org/p/1"},
                        {"url": "file:///C:/secret.png"},
                    ],
                    "defaults": {"suggested_class": "MOOD", "intended_uses": ["OUTFIT"]},
                },
            ),
            201,
        )
        assert len(links["created"]) == 1 and len(links["skipped"]) == 2
        link = links["created"][0]
        attached = ok(
            client.post(
                f"/library/inbox/candidates/{link['id']}/attach",
                params={"row_version": link["row_version"]},
                content=picture(30),
            )
        )
        assert attached["has_file"] is True

        batch = ok(
            client.post("/library/inbox/batches", params={"kind": "IMAGE", "label": "drop"}), 201
        )
        files = [
            ok(
                client.post(
                    "/library/inbox/files",
                    params={
                        "kind": "IMAGE",
                        "batch_id": batch["id"],
                        "label": f"ref-{seed}.png",
                        "creator_handle": "@quill",
                        "tags": "winter,coat",
                        "uses": "OUTFIT,STYLE",
                    },
                    content=picture(seed),
                ),
                201,
            )["candidate"]
            for seed in (31, 32)
        ]
        duplicate = client.post(
            "/library/inbox/files",
            params={"kind": "IMAGE", "label": "ref-31 (1).png"},
            content=picture(31),
        )
        assert duplicate.status_code == 200
        assert duplicate.json()["duplicate"] is True and duplicate.json()["candidate"] is None
        assert duplicate.json()["duplicate_of"]["id"] == files[0]["id"]
        assert files[0]["tags"] == ["winter", "coat"]
        content = client.get(f"/library/inbox/candidates/{files[0]['id']}/content")
        assert content.headers["content-type"] == "image/webp"

        clip = ok(
            client.post(
                "/library/inbox/files",
                params={"kind": "VIDEO", "label": "reel.mp4"},
                content=mp4_bytes(9),
            ),
            201,
        )["candidate"]
        refused = client.post(
            f"/library/inbox/candidates/{clip['id']}/accept",
            json={"row_version": clip["row_version"], "reference_class": "TECHNIQUE"},
        )
        assert refused.status_code == 422
        frame = ok(
            client.post(
                f"/library/inbox/candidates/{clip['id']}/clip-frame",
                params={"time_ms": 1500},
                content=picture(33),
            ),
            201,
        )["candidate"]
        held = ok(
            client.post(
                "/library/inbox/frames",
                params={
                    "media_id": world.id_of(EPISODE),
                    "time_ms": 2000,
                    "suggested_class": "CONTINUITY",
                },
                content=picture(34),
            ),
            201,
        )["candidate"]
        no_paths(world, str(held))

        accepted = ok(
            client.post(
                "/library/inbox/bulk-accept",
                json={
                    "ids": [link["id"], files[0]["id"], files[1]["id"], frame["id"], held["id"]],
                    "reference_class": "MOOD",
                },
            )
        )
        assert len(accepted["accepted"]) == 5 and accepted["skipped"] == []
        origins = sorted(r["origin"] for r in accepted["accepted"])
        assert origins == ["FAN_ART", "FAN_ART", "FAN_ART", "FAN_ART", "SOURCE"]

        inbox = ok(client.get("/library/inbox"))
        assert [c["id"] for c in inbox["candidates"]] == [clip["id"]]
        assert snapshot(world.vault) == before

    def test_intake_refuses_bad_bytes_and_undeclared_fields(
        self, client: TestClient, world: World
    ) -> None:
        assert (
            client.post("/library/inbox/files", params={"kind": "IMAGE"}, content=b"").status_code
            == 422
        )
        assert (
            client.post(
                "/library/inbox/files", params={"kind": "IMAGE"}, content=b"<svg/>"
            ).status_code
            == 422
        )
        assert (
            client.post(
                "/library/inbox/files", params={"kind": "VIDEO"}, content=b"not a clip"
            ).status_code
            == 422
        )
        installer = client.post(
            "/library/inbox/files",
            params={"kind": "IMAGE", "label": "Some Installer.exe"},
            content=b"MZ\x90\x00\x03" + b"\x00" * 8192,
        )
        assert installer.status_code == 422
        assert "installer" in installer.json()["detail"]["message"]
        assert ok(client.get("/library/inbox"))["candidates"] == []
        assert (
            client.post(
                "/library/inbox/files",
                params={"kind": "IMAGE", "origin": "GENERATED"},
                content=picture(35),
            ).status_code
            == 422
        )
        assert (
            client.post(
                "/library/inbox/urls",
                json={"entries": [{"url": "https://a.example/x"}], "directory": "C:\\"},
            ).status_code
            == 422
        )
        assert (
            client.post(
                "/library/inbox/frames",
                params={"media_id": world.id_of(MANGA), "time_ms": 0},
                content=picture(36),
            ).status_code
            == 422
        )
