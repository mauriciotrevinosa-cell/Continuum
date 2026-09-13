"""Projects: generic, discovered, and explicit about what is approved.

* Continuum works with zero projects; a project exists because a manifest
  describes it, never because the application knows its name.
* A document's lifecycle comes from the manifest alone. Its author's prose,
  its file name and its folder decide nothing; a Markdown file the manifest
  does not register is UNFILED.
* Superseded versions stay visible as history.
* A manifest cannot reach outside its own project directory.

All content is invented (D-18 / A-05).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from continuum_api import create_app
from continuum_config import Settings
from fastapi.testclient import TestClient

from tests.conftest import try_junction, try_symlink


def _doc(path: Path, title: str, status_line: str = "", body: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    header = f"# {title}\n\n"
    if status_line:
        header += f"**Status:** {status_line}  \n**Date:** 2026-01-02\n\n"
    path.write_text(header + (body or "## Scene one\n\nSomething happens.\n"), encoding="utf-8")


def _manifest(root: Path, data: dict[str, Any]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "continuum.project.json").write_text(json.dumps(data), encoding="utf-8")


@pytest.fixture
def sources(tmp_path: Path) -> dict[str, Path]:
    source = tmp_path / "projects"
    saga = source / "demo-saga"
    _doc(saga / "EPISODE_1_v0.1.md", "Episode One", "approved story structure")
    _doc(saga / "EPISODE_1_v0.2.md", "Episode One", "approved story structure")
    _doc(saga / "EPISODE_2_v0.1.md", "Episode Two", "approved - but the manifest says draft")
    _doc(saga / "NOTES_v0.1.md", "Loose Notes", "approved, says the prose")
    _doc(saga / "IDEAS.md", "Ideas", "exploratory")
    _doc(saga / "BRAINSTORM.md", "Brainstorm", "kept, not canon")
    (tmp_path / "outside.md").write_text("# Not this project\n\nprivate", encoding="utf-8")
    link_made = try_symlink(saga / "LINKED.md", tmp_path / "outside.md") or try_junction(
        saga / "linked-dir", tmp_path
    )
    _manifest(
        saga,
        {
            "id": "demo-saga",
            "title": "Demo Saga",
            "kind": "what-if",
            "logline": "A test story.",
            "description": "Invented for tests.",
            "discover": ["*.md"],
            "documents": [
                {
                    "id": "ep1-v1",
                    "path": "EPISODE_1_v0.1.md",
                    "category": "episode",
                    "section": "story",
                    "lifecycle": "SUPERSEDED",
                    "lineage": "ep1",
                    "episode": "E1",
                },
                {
                    "id": "ep1-v2",
                    "path": "EPISODE_1_v0.2.md",
                    "category": "episode",
                    "section": "story",
                    "lifecycle": "APPROVED",
                    "lineage": "ep1",
                    "supersedes": "ep1-v1",
                    "episode": "E1",
                    "constraints": ["keep the opening scene"],
                },
                {
                    "id": "ep2",
                    "path": "EPISODE_2_v0.1.md",
                    "category": "draft",
                    "section": "story",
                    "lifecycle": "DRAFT",
                    "episode": "E2",
                    "derived_from": "ep1-v2",
                },
                {"id": "odd", "path": "IDEAS.md", "lifecycle": "CANON-ISH"},
                {
                    "id": "brainstorm",
                    "path": "BRAINSTORM.md",
                    "section": "extra",
                    "lifecycle": "IDEA",
                },
                {"id": "escape", "path": "../outside.md", "lifecycle": "APPROVED"},
                {"id": "absolute", "path": str(tmp_path / "outside.md"), "lifecycle": "APPROVED"},
                {"id": "linked", "path": "LINKED.md", "lifecycle": "APPROVED"},
                {"id": "linked-dir", "path": "linked-dir/outside.md", "lifecycle": "APPROVED"},
                {"id": "not-markdown", "path": "notes.txt", "lifecycle": "APPROVED"},
            ],
            "pipeline": [
                {"id": "draft", "title": "Draft", "track": "story"},
                {"id": "rough", "title": "Rough pages", "track": "manga"},
            ],
        },
    )
    _manifest(source / "empty-one", {"id": "empty-one", "title": "Empty One"})
    (source / "broken").mkdir()
    (source / "broken" / "continuum.project.json").write_text("{not json", encoding="utf-8")
    return {"source": source, "saga": saga, "link_made": link_made}  # type: ignore[dict-item]


def _client(data_home: Path, vault_root: Path, project_sources: str) -> TestClient:
    settings = Settings(
        _env_file=None,
        data_home=str(data_home),
        source_vault_root=str(vault_root),
        project_sources=project_sources,
    )
    return TestClient(create_app(settings))


# ---------------------------------------------------------------------------
def test_no_projects_is_a_valid_state(data_home: Path, vault_root: Path, tmp_path: Path) -> None:
    with _client(data_home, vault_root, str(tmp_path / "nothing")) as client:
        assert client.get("/projects").json() == []
        assert client.get("/projects/anything").status_code == 404


def test_projects_are_discovered_from_manifests(
    data_home: Path, vault_root: Path, sources: dict[str, Path]
) -> None:
    with _client(data_home, vault_root, str(sources["source"])) as client:
        listed = client.get("/projects").json()
    assert [p["id"] for p in listed] == ["demo-saga", "empty-one"], "broken manifests are skipped"
    saga = listed[0]
    assert saga["kind"] == "what-if"
    assert saga["approved"] == 1
    assert saga["extras"] == 2, "the brainstorm, and the discovered but unregistered notes"
    assert listed[1]["documents"] == 0
    with _client(data_home, vault_root, str(sources["source"])) as client:
        documents = client.get("/projects/demo-saga").json()["documents"]
    work = [
        d
        for d in documents
        if d["lifecycle"] in {"IDEA", "DRAFT", "REVIEW", "UNFILED"} and d["section"] != "extra"
    ]
    assert saga["in_progress"] == len(work), "extras are kept, not counted as work"
    assert "brainstorm" not in {d["id"] for d in work}


def test_lifecycle_comes_only_from_the_manifest(
    data_home: Path, vault_root: Path, sources: dict[str, Path]
) -> None:
    with _client(data_home, vault_root, str(sources["source"])) as client:
        detail = client.get("/projects/demo-saga").json()
    docs = {d["id"]: d for d in detail["documents"]}
    assert docs["ep1-v2"]["lifecycle"] == "APPROVED"
    assert docs["ep2"]["lifecycle"] == "DRAFT", "the author's prose does not approve it"
    assert docs["ep2"]["author_status"].startswith("approved"), "but it is shown verbatim"
    assert docs["odd"]["lifecycle"] == "UNFILED", "an unknown lifecycle is not guessed"
    unfiled = [d for d in detail["documents"] if not d["filed"]]
    assert {d["title"] for d in unfiled} == {"Loose Notes"}
    assert all(d["lifecycle"] == "UNFILED" for d in unfiled)
    assert detail["counts"]["APPROVED"] == 1


def test_versions_and_provenance_are_kept(
    data_home: Path, vault_root: Path, sources: dict[str, Path]
) -> None:
    with _client(data_home, vault_root, str(sources["source"])) as client:
        body = client.get("/projects/demo-saga/documents/ep1-v2").json()
        old = client.get("/projects/demo-saga/documents/ep1-v1").json()
        draft = client.get("/projects/demo-saga/documents/ep2").json()
    assert [v["id"] for v in body["versions"]] == ["ep1-v1", "ep1-v2"]
    assert body["document"]["constraints"] == ["keep the opening scene"]
    assert old["document"]["superseded_by"] == "ep1-v2", "a superseded version stays readable"
    assert draft["document"]["derived_from"] == "ep1-v2"
    assert "Something happens." in body["markdown"]


def test_a_manifest_cannot_reach_outside_its_project(
    data_home: Path, vault_root: Path, sources: dict[str, Path]
) -> None:
    with _client(data_home, vault_root, str(sources["source"])) as client:
        detail = client.get("/projects/demo-saga").json()
        ids = {d["id"] for d in detail["documents"]}
        for hostile in ("escape", "absolute", "linked", "linked-dir", "not-markdown"):
            assert hostile not in ids, hostile
            response = client.get(f"/projects/demo-saga/documents/{hostile}")
            assert response.status_code == 404
            assert "private" not in response.text
        listed = client.get("/projects").json()
    warnings = listed[0]["warnings"]
    assert any("not inside the project" in w for w in warnings)


@pytest.mark.parametrize(
    "path",
    [
        "/projects/..%2F..%2Fetc",
        "/projects/DEMO-SAGA",
        "/projects/demo-saga/documents/..%2Foutside",
        "/projects/demo-saga/documents/C:%5Cx",
        "/projects/demo-saga/documents/unknown-doc",
        "/projects/unknown-project/documents/ep1-v2",
    ],
)
def test_bad_or_unknown_ids_are_refused(
    data_home: Path, vault_root: Path, sources: dict[str, Path], path: str
) -> None:
    with _client(data_home, vault_root, str(sources["source"])) as client:
        response = client.get(path)
    assert response.status_code in (404, 422), path
    assert "private" not in response.text


def test_pipeline_is_project_data(
    data_home: Path, vault_root: Path, sources: dict[str, Path]
) -> None:
    with _client(data_home, vault_root, str(sources["source"])) as client:
        detail = client.get("/projects/demo-saga").json()
        empty = client.get("/projects/empty-one").json()
    assert [(s["id"], s["track"]) for s in detail["pipeline"]] == [
        ("draft", "story"),
        ("rough", "manga"),
    ]
    assert detail["pipeline"][0]["artifacts"] == 1, "one document of category 'draft'"
    assert empty["pipeline"] == [] and empty["documents"] == []


def test_projects_default_to_the_projects_root(data_home: Path, vault_root: Path) -> None:
    root = data_home / "projects" / "demo-root-project"
    _doc(root / "A.md", "A")
    _manifest(
        root,
        {
            "id": "demo-root-project",
            "title": "Root Project",
            "documents": [{"path": "A.md", "lifecycle": "IDEA"}],
        },
    )
    with _client(data_home, vault_root, "") as client:
        listed = client.get("/projects").json()
    assert [p["id"] for p in listed] == ["demo-root-project"]
