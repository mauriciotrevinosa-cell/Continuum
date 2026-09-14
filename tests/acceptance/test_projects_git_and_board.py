"""Projects read from Git, registered by convention, with a computed episode board.

The M2 closeout found the studio showing a project as it was weeks ago: its
documents were read from whatever working tree happened to be checked out,
and every new episode document needed a hand-edited registry entry before the
studio would treat it as anything but unfiled. These tests pin the fix:

* a ``git:`` source is read at the commit its ref points to - committed
  state only, reported with the commit - and a resync fetches a
  remote-tracking ref and nothing else;
* a manifest's conventions register files by name, and its declared
  ``status_lifecycle`` rules - never code - turn the author's Status line
  into a lifecycle; without a declared rule the author's prose still decides
  nothing;
* the episode board (levels, pages, what is missing) is computed from the
  documents on every read.

All content is invented (D-18 / A-05).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
from continuum_api import create_app
from continuum_config import Settings
from continuum_storage import GitSourceError, GitSpec, ProjectLibrary
from fastapi.testclient import TestClient

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")

MANIFEST: dict[str, Any] = {
    "id": "moon-harbor",
    "title": "Moon Harbor",
    "discover": ["*.md"],
    "documents": [
        {
            "id": "series-rules",
            "path": "HARBOR_RULES_v0.1.md",
            "category": "workflow",
            "section": "production",
            "lifecycle": "APPROVED",
        }
    ],
    "conventions": [
        {
            "id": "panel-script",
            "match": (
                r"^HARBOR_(?P<episode>S\d+E\d+)_(?:[A-Z0-9_]+_)?"
                r"PANEL_SCRIPT_v(?P<version>[\d.]+)\.md$"
            ),
            "document_id": "{episode_lower}-panel-script",
            "category": "panel-script",
            "section": "production",
            "maturity": "PRODUCTION_READY",
        },
        {
            "id": "draft",
            "match": (
                r"^HARBOR_(?P<episode>S\d+E\d+)_(?:[A-Z0-9_]+_)?"
                r"DRAFT_(?P<draft>\d+)_v(?P<version>[\d.]+)\.md$"
            ),
            "document_id": "{episode_lower}-draft-{draft}",
            "category": "draft",
            "section": "story",
        },
        {
            "id": "green-light",
            "match": r"^HARBOR_(?P<episode>S\d+E\d+)_GREEN_LIGHT_v(?P<version>[\d.]+)\.md$",
            "document_id": "{episode_lower}-green-light",
            "category": "green-light",
            "section": "story",
        },
        {
            "id": "iteration",
            "match": r"^HARBOR_(?P<episode>S\d+E\d+)_[A-Z0-9_]+_v(?P<version>[\d.]+)\.md$",
            "category": "voice-iteration",
            "section": "story",
        },
    ],
    "status_lifecycle": [
        {"match": r"NOT YET GREEN", "lifecycle": "REVIEW"},
        {"match": r"GREEN LIGHT|READY|COMPLETE|APPROVED", "lifecycle": "APPROVED"},
    ],
    "facts": {
        "pages": [r"^\*\*Provisional total:\*\*\s*(\d+)"],
        "title": [r"^#\s.*?S\d+E\d+\s*`([^`]+)`"],
    },
    "episodes": {
        "match": r"^S(?P<season>\d+)E(?P<number>\d+)$",
        "categories": ["green-light", "voice-iteration", "draft", "panel-script"],
        "title_from": ["panel-script", "draft", "green-light"],
        "pages_from": "panel-script",
        "levels": [
            {
                "id": "4",
                "label": "Ready for pages",
                "requires": ["draft", "panel-script"],
                "count_pages": True,
            },
            {"id": "3+", "label": "Draft done", "requires": ["draft"]},
            {"id": "3", "label": "Green-lit", "requires": ["green-light"]},
        ],
        "resolves": {"green-light": ["voice-iteration"]},
    },
}


def _doc(title: str, status: str, extra: str = "") -> str:
    return f"# {title}\n\n**Status:** {status}\n{extra}\n## Beat\n\nSomething quiet happens.\n"


FILES: dict[str, str] = {
    "HARBOR_RULES_v0.1.md": _doc("Harbor rules", "whatever the prose says"),
    "HARBOR_S1E1_DRAFT_1_v0.1.md": _doc("Harbor S1E1 `Low Tide` Draft 1", "STAGE 3 COMPLETE"),
    "HARBOR_S1E1_LOW_TIDE_PANEL_SCRIPT_v0.1.md": _doc(
        "Harbor S1E1 `Low Tide` Panel Script", "PANEL SCRIPT READY", "**Provisional total:** 41\n"
    ),
    "HARBOR_S1E2_GREEN_LIGHT_v0.1.md": _doc("Harbor S1E2 `Fog Bell` green light", "GREEN LIGHT"),
    "HARBOR_S1E2_VOICE_REVISION_v0.1.md": _doc("Harbor S1E2 revision", "NOT YET GREEN-LIT"),
    "HARBOR_S1E2_FOG_BELL_DRAFT_1_v0.1.md": _doc("Harbor S1E2 `Fog Bell` Draft 1", "COMPLETE"),
    "HARBOR_S1E3_GREEN_LIGHT_v0.1.md": _doc("Harbor S1E3 green light", "GREEN LIGHT"),
    "LOOSE_NOTES.md": _doc("Loose notes", "APPROVED says the prose"),
}


def _git(repo: Path, *args: str) -> str:
    env = dict(os.environ)
    env.update(
        GIT_AUTHOR_NAME="Test",
        GIT_AUTHOR_EMAIL="test@example.invalid",
        GIT_COMMITTER_NAME="Test",
        GIT_COMMITTER_EMAIL="test@example.invalid",
        GIT_CONFIG_NOSYSTEM="1",
    )
    done = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, env=env, check=True
    )
    return done.stdout.strip()


def _commit_project(repo: Path, files: dict[str, str], message: str) -> str:
    folder = repo / "stories" / "harbor"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "continuum.project.json").write_text(json.dumps(MANIFEST), encoding="utf-8")
    for name, text in files.items():
        (folder / name).write_text(text, encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "creative-repo"
    root.mkdir()
    _git(root, "init", "-q", "-b", "board")
    _commit_project(root, FILES, "first board")
    return root


def _client(data_home: Path, vault_root: Path, sources: str) -> TestClient:
    settings = Settings(
        _env_file=None,
        data_home=str(data_home),
        source_vault_root=str(vault_root),
        project_sources=sources,
    )
    return TestClient(create_app(settings))


# ---------------------------------------------------------------------------
def test_conventions_register_documents_and_the_board_is_computed(
    data_home: Path, vault_root: Path, repo: Path
) -> None:
    source = f"git:{repo}@board:stories/harbor"
    with _client(data_home, vault_root, source) as client:
        detail = client.get("/projects/moon-harbor").json()

    assert detail["project"]["warnings"] == []
    head = _git(repo, "rev-parse", "HEAD")
    assert detail["project"]["source"]["kind"] == "git"
    assert detail["project"]["source"]["commit"] == head
    assert detail["project"]["source"]["ref"] == "board"
    assert str(repo) not in json.dumps(detail), "a Git source never reveals a path"

    docs = {d["id"]: d for d in detail["documents"]}
    script = docs["s1e1-panel-script"]
    assert script["registration"] == "convention" and script["convention"] == "panel-script"
    assert script["lifecycle"] == "APPROVED" and script["maturity"] == "PRODUCTION_READY"
    assert script["facts"] == {"pages": "41", "title": "Low Tide"}
    assert script["commit"] == head[:7]
    assert docs["series-rules"]["registration"] == "explicit"
    assert docs["series-rules"]["lifecycle"] == "APPROVED"
    revision = docs["harbor-s1e2-voice-revision-v0-1"]
    assert revision["lifecycle"] == "REVIEW", "the author's own status, transcribed"
    assert revision["resolved_by"] == "s1e2-green-light"
    assert docs["loose-notes"]["lifecycle"] == "UNFILED", "no rule covers it; prose decides nothing"

    board = {e["code"]: e for e in detail["episodes"]}
    assert list(board) == ["S1E1", "S1E2", "S1E3"]
    assert board["S1E1"]["level"] == "4" and board["S1E1"]["pages"] == 41
    assert board["S1E1"]["title"] == "Low Tide" and board["S1E1"]["missing"] == []
    assert board["S1E2"]["level"] == "3+" and board["S1E2"]["missing"] == ["panel-script"]
    assert board["S1E3"]["level"] == "3" and board["S1E3"]["missing"] == ["draft"]
    assert [d["category"] for d in board["S1E2"]["documents"]] == [
        "green-light",
        "voice-iteration",
        "draft",
    ]
    assert detail["episode_summary"] == {
        "episodes": 3,
        "by_level": {"4": 1, "3+": 1, "3": 1},
        "pages": 41,
        "unmet": 0,
        "page_totals": [
            {"id": "base", "label": "Pages", "pages": 41, "episodes": 1, "current": True}
        ],
    }
    assert detail["project"]["in_progress"] == 0, "a resolved iteration is not open work"


def test_only_committed_state_is_shown_and_a_new_commit_appears(
    data_home: Path, vault_root: Path, repo: Path
) -> None:
    folder = repo / "stories" / "harbor"
    # Uncommitted work in the checkout is not what the branch says.
    (folder / "HARBOR_S1E3_DRAFT_1_v0.1.md").write_text(
        _doc("Harbor S1E3 `Night Ferry` Draft 1", "COMPLETE"), encoding="utf-8"
    )
    library = ProjectLibrary([f"git:{repo}@board:stories/harbor"])
    project = library.project("moon-harbor")
    assert project is not None
    assert "s1e3-draft-1" not in {d.id for d in project.documents}

    new_head = _commit_project(repo, {}, "draft three")
    library.forget()
    project = library.project("moon-harbor")
    assert project is not None and project.source["commit"] == new_head
    board = {e.code: e for e in project.episodes}
    assert board["S1E3"].level == "3+" and board["S1E3"].title == "Night Ferry"
    found = library.document("moon-harbor", "s1e3-draft-1")
    assert found is not None and "Night Ferry" in found[2]


def test_resync_fetches_a_remote_tracking_ref_and_nothing_else(
    data_home: Path, vault_root: Path, repo: Path, tmp_path: Path
) -> None:
    studio = tmp_path / "studio-clone"
    _git(tmp_path, "clone", "-q", str(repo), str(studio))
    local_branches = _git(studio, "branch", "--list")
    source = f"git:{studio}@origin/board:stories/harbor"
    with _client(data_home, vault_root, source) as client:
        before = client.get("/projects/moon-harbor").json()
        first = before["project"]["source"]["commit"]

        # The author commits on the remote; the studio has not fetched yet.
        (repo / "stories" / "harbor" / "HARBOR_S1E3_DRAFT_1_v0.1.md").write_text(
            _doc("Harbor S1E3 `Night Ferry` Draft 1", "COMPLETE"), encoding="utf-8"
        )
        pushed = _commit_project(repo, {}, "draft three upstream")
        stale = client.get("/projects/moon-harbor").json()
        assert stale["project"]["source"]["commit"] == first

        result = client.post("/projects/moon-harbor/resync").json()
        assert result["fetched"] is True and result["changed"] is True
        assert result["previous_commit"] == first and result["commit"] == pushed
        after = client.get("/projects/moon-harbor").json()
        assert {e["code"]: e["level"] for e in after["episodes"]}["S1E3"] == "3+"

        assert client.post("/projects/nobody/resync").status_code == 404
    assert _git(studio, "branch", "--list") == local_branches, "no local branch was moved"
    assert _git(studio, "status", "--porcelain") == "", "the working tree was not touched"


def test_git_sources_are_validated_and_contained(tmp_path: Path, repo: Path) -> None:
    for bad in (
        "git:C:/repo",  # no ref
        f"git:{repo}@--upload-pack=evil:stories",
        f"git:{repo}@board:../outside",
        f"git:{repo}@a..b:stories",
    ):
        with pytest.raises(GitSourceError):
            GitSpec.parse(bad)
    assert GitSpec.parse(str(tmp_path)) is None, "a plain directory is not a Git source"

    hostile = dict(MANIFEST)
    hostile["documents"] = [
        {"id": "escape", "path": "../../outside.md", "lifecycle": "APPROVED"},
        {"id": "drive", "path": "C:/Windows/win.ini", "lifecycle": "APPROVED"},
    ]
    folder = repo / "stories" / "harbor"
    (folder / "continuum.project.json").write_text(json.dumps(hostile), encoding="utf-8")
    (repo / "outside.md").write_text("# outside\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "hostile")
    library = ProjectLibrary([f"git:{repo}@board:stories/harbor"])
    project = library.project("moon-harbor")
    assert project is not None
    ids = {d.id for d in project.documents}
    assert "escape" not in ids and "drive" not in ids
    assert any("not inside the project" in w for w in project.warnings)

    missing_ref = ProjectLibrary([f"git:{repo}@no-such-branch:stories/harbor"])
    assert missing_ref.projects() == []


# ---------------------------------------------------------------------------
LAYERED: dict[str, Any] = json.loads(json.dumps(MANIFEST))
LAYERED["supersedes_header"] = True
LAYERED["conventions"][:0] = [
    {
        "id": "overlay",
        "match": r"^HARBOR_S(?P<season>\d+)_[A-Z0-9_]+_OVERLAY_v(?P<version>[\d.]+)\.md$",
        "category": "production-overlay",
        "section": "production",
        "applies_to": "season:{season}",
    },
    {
        "id": "bible",
        "match": r"^HARBOR_(?P<setting>[A-Z0-9_]+)_BIBLE_v(?P<version>[\d.]+)\.md$",
        "category": "setting-bible",
        "section": "production",
        "applies_to": "project",
    },
    {
        "id": "episode-addendum",
        "match": r"^HARBOR_(?P<episode>S\d+E\d+)_[A-Z0-9_]+_ADDENDUM_v(?P<version>[\d.]+)\.md$",
        "category": "episode-addendum",
        "section": "production",
    },
]
LAYERED["episodes"]["page_counts"] = [
    {"id": "base", "label": "Base panelization", "from": "fact", "category": "panel-script"},
    {
        "id": "integrated",
        "label": "Integrated provisional",
        "from": "table",
        "category": "production-overlay",
        "row": r"^\|\s*(?P<episode>S\d+E\d+)\s*\|\s*\d+\s*\|\s*\**(?P<pages>\d+)\**\s*\|",
        "current": True,
    },
]
LAYERED["episodes"]["production_sources"] = [
    {"role": "base", "categories": ["panel-script"], "scope": "episode", "required": True},
    {"role": "draft", "categories": ["draft"], "scope": "episode", "required": True},
    {"role": "overlay", "categories": ["production-overlay"], "scope": "season"},
    {"role": "addendum", "categories": ["episode-addendum"], "scope": "episode"},
    {
        "role": "setting",
        "categories": ["setting-bible"],
        "scope": "project",
        "when": "when the harbor appears",
    },
]


def test_later_overlays_bibles_and_addenda_need_no_registration(
    data_home: Path, vault_root: Path, repo: Path
) -> None:
    """Revisions committed after the rules are declared are indexed, counted and sourced."""
    folder = repo / "stories" / "harbor"
    (folder / "continuum.project.json").write_text(json.dumps(LAYERED), encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "declare layers once")
    library = ProjectLibrary([f"git:{repo}@board:stories/harbor"])
    project = library.project("moon-harbor")
    assert project is not None
    first = {e.code: e for e in project.episodes}["S1E1"]
    assert first.pages == 41 and first.current_count == "base", "no overlay yet: base is current"

    # The author commits an overlay, a bible and its replacement, and an addendum.
    # The manifest is not touched.
    files = {
        "HARBOR_S1_TIDE_REVISION_OVERLAY_v0.2.md": _doc(
            "Harbor Season 1 overlay",
            "APPROVED / AUTHORITATIVE PRODUCTION OVERLAY",
            "\n| Episode | Base pages | Integrated | Delta |\n|---|---:|---:|---:|\n"
            "| S1E1 | 41 | **44** | +3 |\n| S1E2 | 30 | **33** | +3 |\n",
        ),
        "HARBOR_PIER_BIBLE_v0.1.md": _doc("Pier bible v0.1", "APPROVED SPATIAL BASE"),
        "HARBOR_PIER_BIBLE_v0.2.md": _doc(
            "Pier bible v0.2",
            "APPROVED SPATIAL BASE",
            "**Supersedes:** `HARBOR_PIER_BIBLE_v0.1.md`\n",
        ),
        "HARBOR_S1E1_LANTERN_ADDENDUM_v0.1.md": _doc(
            "Lantern addendum", "APPROVED VISUAL ADDENDUM"
        ),
    }
    manifest_before = (folder / "continuum.project.json").read_bytes()
    for name, text in files.items():
        (folder / name).write_text(text, encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "revisions land")
    head = _git(repo, "rev-parse", "HEAD")
    assert (folder / "continuum.project.json").read_bytes() == manifest_before
    assert _git(repo, "show", "--name-only", "--format=", "HEAD").count("continuum.project") == 0
    library.forget()
    project = library.project("moon-harbor")
    assert project is not None and project.source["commit"] == head
    assert [d.relative for d in project.documents if d.registration == "unfiled"] == [
        "LOOSE_NOTES.md"
    ]
    docs = {d.id: d for d in project.documents}
    assert docs["harbor-pier-bible-v0-1"].lifecycle == "SUPERSEDED", "its successor says so"
    assert docs["harbor-pier-bible-v0-2"].supersedes == "harbor-pier-bible-v0-1"
    assert docs["harbor-s1-tide-revision-overlay-v0-2"].applies_to == "season:1"

    board = {e.code: e for e in project.episodes}
    one = board["S1E1"]
    assert one.pages == 44 and one.current_count == "integrated"
    assert {(c[0], c[2]) for c in one.page_counts} == {("base", 41), ("integrated", 44)}
    assert [(role, doc) for role, doc, _required, _when in one.sources] == [
        ("base", "s1e1-panel-script"),
        ("draft", "s1e1-draft-1"),
        ("overlay", "harbor-s1-tide-revision-overlay-v0-2"),
        ("addendum", "harbor-s1e1-lantern-addendum-v0-1"),
        ("setting", "harbor-pier-bible-v0-2"),
    ], "the superseded bible is not a source"
    assert one.missing_sources == ()
    assert board["S1E2"].missing_sources == ("base",), "a required source is reported missing"
    totals = {t["id"]: t for t in project.page_totals}
    assert totals["base"]["pages"] == 41 and totals["integrated"]["pages"] == 44
    assert totals["integrated"]["current"] is True and totals["base"]["current"] is False

    with _client(data_home, vault_root, f"git:{repo}@board:stories/harbor") as client:
        detail = client.get("/projects/moon-harbor").json()
        assert detail["episode_summary"]["pages"] == 44
        sources = client.get("/projects/moon-harbor/episodes/S1E1/production-sources").json()
        assert [s["role"] for s in sources] == ["base", "draft", "overlay", "addendum", "setting"]
        assert sources[-1]["when"] == "when the harbor appears"
        assert all(s["commit"] == head[:7] for s in sources[2:])
        missing = client.get("/projects/moon-harbor/episodes/S9E9/production-sources")
        assert missing.status_code == 404
