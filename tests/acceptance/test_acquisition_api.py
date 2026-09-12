"""Library acquisition API: read real documents, never write to the Vault.

The acquisition engine is a separate local tool. These tests stand in for it
with synthetic documents and a fake CLI, so they assert the *contract*:

* an unconfigured or empty library answers 200 with empty collections;
* documents are projected into the published schema;
* actions run only allowlisted CLI verbs, and ``--apply`` can never be one;
* a missing CLI is reported to the user, not raised as a 500.

All fixture content is invented (D-18 / A-05): no real title appears here.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from continuum_api import create_app
from continuum_config import Settings
from continuum_storage import AcquisitionCliError, AcquisitionStore
from fastapi.testclient import TestClient

FAMILY_ID = "demo-alpha"

LAYOUT = {
    "schema": "continuum.personal.vault-layout/1",
    "generated_at": "2026-09-12T00:00:00-04:00",
    "vault_root": "C:/DemoVault",
    "summary": {
        "files": 12,
        "bytes": 1024,
        "missing_folder": 1,
        "legacy_paths_mapped": 1,
        "possible_duplicate_groups": 1,
    },
    "families": [
        {
            "family_id": FAMILY_ID,
            "family_title": "Demo Alpha",
            "category": "FAVORITE",
            "primary_medium": "manga",
            "family_path": "C:/DemoVault/Demo Alpha",
            "folder_exists": True,
            "files": 12,
            "bytes": 1024,
            "family_aliases": ["Demo A"],
            "works": [
                {
                    "work_id": "demo-alpha/main",
                    "work": "Demo Alpha",
                    "family_id": FAMILY_ID,
                    "family_title": "Demo Alpha",
                    "relationship_type": "MAIN_WORK",
                    "material_class": "manga",
                    "medium": "manga",
                    "official_status": True,
                    "coverage_status": "PARTIAL",
                    "layout_status": "LEGACY_MAPPING",
                    "legacy_mapping": True,
                    "legacy_kind": "class-root",
                    "local_path": "C:/DemoVault/Demo Alpha/manga",
                    "expected_path": "C:/DemoVault/Demo Alpha/manga/Alpha",
                    "folder_exists": True,
                    "local_files": 12,
                },
                {
                    "work_id": "demo-alpha/guide",
                    "work": "Demo Alpha Guide",
                    "family_id": FAMILY_ID,
                    "family_title": "Demo Alpha",
                    "relationship_type": "GUIDEBOOK",
                    "material_class": "guidebook",
                    "official_status": True,
                    "coverage_status": "MISSING",
                    "layout_status": "MISSING_FOLDER",
                    "expected_path": "C:/DemoVault/Demo Alpha/guidebook/Guide",
                    "local_path": "C:/DemoVault/Demo Alpha/guidebook/Guide",
                    "confidence": "high",
                },
            ],
            "findings": [
                {"type": "POSSIBLE_DUPLICATE", "path": "manga/a.zip",
                 "detail": "two identical files"}
            ],
        }
    ],
    "global_findings": [],
    "proposed_moves": [],
}

COVERAGE = {
    "works": {
        "demo-alpha/main": {
            "status": "PARTIAL",
            "reason": "chapter gaps 4",
            "local_chapters": 11,
            "chapter_min": 1,
            "chapter_max": 12,
            "gaps_text": "4",
            "missing_chapters_text": "13-14",
            "remote_latest_chapter": 14,
        }
    }
}

QUEUE = {
    "generated_at": "2026-09-12T00:00:00-04:00",
    "works": [
        {
            "family": "Demo Alpha",
            "work": "Demo Alpha Guide",
            "work_id": "demo-alpha/guide",
            "relation": "GUIDEBOOK",
            "material_class": "guidebook",
            "official": True,
            "coverage_status": "MISSING",
            "coverage_reason": "no local media",
            "best_source": "Demo Store",
            "availability": "AVAILABLE_MANUAL",
            "manual_action_required": True,
            "automatic_download_allowed": False,
            "search_title": "Demo Alpha Guide",
            "priority": 4,
            "url": "https://store.invalid/search?q=demo",
            "requires_purchase": "yes",
            "source_hits": [{"source": "demo-store", "title": "Demo Alpha Guide", "score": 0.9}],
        },
        {
            "family": "Demo Alpha",
            "work": "Demo Alpha",
            "work_id": "demo-alpha/main",
            "relation": "MAIN_WORK",
            "official": True,
            "coverage_status": "COMPLETE",
        },
    ],
}

REGISTRY = {
    "schema": "continuum.personal.sources/2",
    "sources": {
        "demo-store": {
            "id": "demo-store",
            "name": "Demo Store",
            "url": "https://store.invalid",
            "adapter": "web",
            "enabled": True,
            "capabilities": ["DISCOVERY_ONLY", "MANUAL_ACQUISITION"],
            "access": ["DRM_EBOOK"],
            "roles": ["store-search-en"],
            "download_permitted": False,
            "last_test": {"at": "2026-09-12T00:00:00-04:00", "ok": True, "checks": [],
                          "operations": ["search"]},
        },
        "demo-off": {
            "id": "demo-off",
            "name": "Disabled Source",
            "url": "https://off.invalid",
            "adapter": "web",
            "enabled": False,
            "capabilities": ["DISCOVERY_ONLY"],
        },
    },
    "unofficial_hosts": ["bad.invalid"],
}

WATCH = {
    "generated_at": "2026-09-12T00:00:00-04:00",
    "last_check": "2026-09-12T00:10:00-04:00",
    "works": [
        {
            "family": "Demo Alpha",
            "work": "Demo Alpha",
            "work_id": "demo-alpha/main",
            "latest_local": 12,
            "latest_remote": 14,
            "update_available": True,
            "status": "PARTIAL",
        }
    ],
    "alerts": [
        {"at": "2026-09-12T00:10:00-04:00", "kind": "NEW_CHAPTERS", "family": "Demo Alpha",
         "work": "Demo Alpha", "detail": "latest chapter 12 -> 14"}
    ],
    "sources": {"demo-store": {"fingerprint": "abc", "last_checked": "2026-09-12T00:10:00-04:00"}},
}

REVIEW = {"items": [{"kind": "WORK_REVIEW", "family": "Demo Alpha", "item": "Demo Alpha Extra",
                     "detail": "needs confirmation", "action": "confirm or correct"}]}

INGEST = {
    "mode": "DRY RUN",
    "intake_dirs": ["C:/DemoIntake/Manual"],
    "counts": {"imported (dry-run)": 2, "left-in-intake: unclassified": 1},
    "units": [
        {"source": "Manual", "unit": "Demo Alpha v03",
         "path": "C:/DemoIntake/Manual/Demo Alpha v03",
         "files": 1, "classified_by": "alias", "series": {"Demo Alpha": 1}, "languages": {"en": 1},
         "unofficial_provenance": [], "colored": False, "action": "imported (dry-run)"},
        {"source": "Manual", "unit": "Mystery Folder",
         "path": "C:/DemoIntake/Manual/Mystery Folder",
         "files": 1, "classified_by": "unclassified", "series": {}, "languages": {},
         "unofficial_provenance": ["bad.invalid"], "colored": False,
         "action": "left-in-intake: unclassified"},
    ],
}

DOCUMENTS = {
    "vault-layout.json": LAYOUT,
    "vault-coverage.json": COVERAGE,
    "acquisition-queue.json": QUEUE,
    "sources.json": REGISTRY,
    "update-watch.json": WATCH,
    "REVIEW_REQUIRED.json": REVIEW,
    "ingest-last.json": INGEST,
}

FAKE_CLI = """import sys
print("fake acquisition cli:", " ".join(sys.argv[1:]))
sys.exit(0)
"""


@pytest.fixture
def acquisition_dir(tmp_path: Path) -> Path:
    directory = tmp_path / "acquisition"
    directory.mkdir()
    for name, document in DOCUMENTS.items():
        (directory / name).write_text(json.dumps(document), encoding="utf-8")
    return directory


@pytest.fixture
def fake_cli(tmp_path: Path) -> Path:
    script = tmp_path / "fake_cli.py"
    script.write_text(FAKE_CLI, encoding="utf-8")
    return script


def _settings(data_home: Path, vault_root: Path, **extra: str) -> Settings:
    return Settings(
        _env_file=None,
        data_home=str(data_home),
        source_vault_root=str(vault_root),
        **extra,
    )


@pytest.fixture
def client(data_home: Path, vault_root: Path, acquisition_dir: Path) -> TestClient:
    settings = _settings(data_home, vault_root, acquisition_data_dir=str(acquisition_dir))
    with TestClient(create_app(settings)) as test_client:
        yield test_client


@pytest.fixture
def empty_client(data_home: Path, vault_root: Path, tmp_path: Path) -> TestClient:
    """A user who has never run acquisition: the directory does not exist."""
    settings = _settings(data_home, vault_root, acquisition_data_dir=str(tmp_path / "nothing-here"))
    with TestClient(create_app(settings)) as test_client:
        yield test_client


# ---------------------------------------------------------------------------
def test_empty_library_is_a_valid_state(empty_client: TestClient) -> None:
    response = empty_client.get("/library/acquisition")
    assert response.status_code == 200
    body = response.json()
    assert body["status"]["available"] is False
    assert body["families"] == []
    assert body["totals"]["works"] == 0
    assert body["sources_total"] == 0
    for path in ("/library/acquisition/families", "/library/acquisition/queue"):
        assert empty_client.get(path).json() == []
    assert empty_client.get("/library/acquisition/sources").json()["sources"] == []
    assert empty_client.get("/library/acquisition/updates").json()["items"] == []


def test_overview_projects_the_documents(client: TestClient) -> None:
    body = client.get("/library/acquisition").json()
    assert body["status"]["available"] is True
    assert body["status"]["vault_root"] == "C:/DemoVault"
    assert body["totals"] == {
        "families": 1, "works": 2, "official_works": 2, "complete": 0, "partial": 1, "missing": 1,
        "unknown": 0, "files": 12, "bytes": 1024, "missing_folders": 1, "legacy_paths": 1,
        "duplicate_groups": 1,
    }
    assert body["relations"] == {"MAIN_WORK": 1, "GUIDEBOOK": 1}
    assert body["families"][0]["title"] == "Demo Alpha"
    assert body["families"][0]["missing_folders"] == 1
    assert [q["work"] for q in body["queue_preview"]] == ["Demo Alpha Guide"]
    assert body["alerts"][0]["kind"] == "NEW_CHAPTERS"
    assert body["review_count"] == 1
    assert body["intake_pending"] == 1
    assert body["sources_enabled"] == 1
    assert body["sources_total"] == 2


def test_family_detail_merges_coverage(client: TestClient) -> None:
    body = client.get(f"/library/acquisition/families/{FAMILY_ID}").json()
    works = {w["title"]: w for w in body["works"]}
    main = works["Demo Alpha"]
    assert main["relation"] == "MAIN_WORK"
    assert main["chapter_max"] == 12
    assert main["gaps"] == "4"
    assert main["missing_chapters"] == "13-14"
    assert main["legacy_mapping"] is True
    assert works["Demo Alpha Guide"]["material_class"] == "guidebook"
    assert body["findings"][0]["type"] == "POSSIBLE_DUPLICATE"


def test_unknown_family_is_404(client: TestClient) -> None:
    assert client.get("/library/acquisition/families/nope").status_code == 404


def test_queue_filters_and_keeps_source_hits(client: TestClient) -> None:
    items = client.get("/library/acquisition/queue").json()
    assert [i["work"] for i in items] == ["Demo Alpha Guide"]
    assert items[0]["source_hits"][0]["source"] == "demo-store"
    assert items[0]["requires_user_action"] is True
    assert client.get("/library/acquisition/queue?status=PARTIAL").json() == []


def test_sources_view_lists_capabilities_and_unofficial_hosts(client: TestClient) -> None:
    body = client.get("/library/acquisition/sources").json()
    assert [s["id"] for s in body["sources"]] == ["demo-store", "demo-off"]
    assert body["sources"][0]["capabilities"] == ["DISCOVERY_ONLY", "MANUAL_ACQUISITION"]
    assert body["sources"][0]["test_ok"] is True
    assert body["sources"][1]["enabled"] is False
    assert body["unofficial_hosts"] == ["bad.invalid"]
    assert "AUTOMATIC_ACQUISITION" in body["capabilities"]


def test_intake_and_updates_views(client: TestClient) -> None:
    intake = client.get("/library/acquisition/intake").json()
    assert intake["counts"]["imported (dry-run)"] == 2
    assert len(intake["units"]) == 2
    assert intake["units"][1]["unofficial_provenance"] == ["bad.invalid"]
    assert intake["duplicates"][0]["type"] == "POSSIBLE_DUPLICATE"
    assert intake["review"][0]["kind"] == "WORK_REVIEW"

    updates = client.get("/library/acquisition/updates").json()
    assert updates["items"][0]["update_available"] is True
    assert updates["alerts"][0]["detail"].endswith("12 -> 14")
    assert "demo-store" in updates["sources"]


def test_scaffold_plan_lists_missing_folders_without_creating_them(client: TestClient) -> None:
    body = client.get("/library/acquisition/scaffold").json()
    assert [c["work"] for c in body["create"]] == ["Demo Alpha Guide"]
    assert body["counts"]["MISSING_FOLDER"] == 1
    assert body["ran"] is False


def test_actions_without_a_cli_explain_themselves(client: TestClient) -> None:
    """No CLI configured is a message to the user, never a 500."""
    response = client.post("/library/acquisition/sources", json={"url": "https://example.invalid"})
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert "not configured" in body["message"]
    assert body["exit_code"] == 126


def test_actions_run_the_allowlisted_cli(
    data_home: Path, vault_root: Path, acquisition_dir: Path, fake_cli: Path
) -> None:
    settings = _settings(
        data_home, vault_root,
        acquisition_data_dir=str(acquisition_dir),
        acquisition_cli=str(fake_cli),
    )
    with TestClient(create_app(settings)) as client:
        body = client.post(
            "/library/acquisition/sources",
            json={"url": "https://example.invalid", "source_id": "example", "test": False},
        ).json()
        assert body["ok"] is True, body
        assert "sources add https://example.invalid --id example --no-test" in body["command"]
        assert str(acquisition_dir) in body["command"]

        for action in ("test", "enable", "disable", "remove"):
            result = client.post(f"/library/acquisition/sources/example/{action}").json()
            assert result["ok"] is True
            assert f"sources {action} example" in result["command"]

        plan = client.post("/library/acquisition/scaffold/plan").json()
        assert plan["ran"] is True
        assert plan["command"].endswith("scaffold --apply"), "the UI shows it; it never runs it"


def test_add_source_rejects_a_malformed_id(client: TestClient) -> None:
    response = client.post(
        "/library/acquisition/sources",
        json={"url": "https://example.invalid", "source_id": "../escape"},
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
class TestStoreGuards:
    """The store itself refuses what the router must never be able to ask."""

    def test_only_known_documents_can_be_read(self, acquisition_dir: Path) -> None:
        store = AcquisitionStore(str(acquisition_dir))
        assert store.read("vault-layout.json") is not None
        with pytest.raises(KeyError):
            store.read("../../.env")

    def test_apply_is_not_reachable(self, acquisition_dir: Path, fake_cli: Path) -> None:
        store = AcquisitionStore(str(acquisition_dir), cli_path=str(fake_cli))
        with pytest.raises(AcquisitionCliError):
            store.build_command("scaffold", "--apply")
        with pytest.raises(AcquisitionCliError):
            store.build_command("ingest", "--apply")
        with pytest.raises(AcquisitionCliError):
            store.build_command("discover")  # not on the allowlist at all
        with pytest.raises(AcquisitionCliError):
            store.build_command("sources", "nonsense")

    def test_unreadable_document_does_not_raise(self, acquisition_dir: Path) -> None:
        (acquisition_dir / "sources.json").write_text("{not json", encoding="utf-8")
        store = AcquisitionStore(str(acquisition_dir))
        assert store.read("sources.json") is None
        broken = next(d for d in store.documents() if d.name == "sources.json")
        assert broken.present is True
        assert broken.error is not None
