"""Library truth: what the API says about material must match the documents.

The acquisition engine decides coverage. These tests pin down the API's side
of the contract:

* nothing the engine found locally is ever presented as MISSING;
* a MISSING verdict about a family whose folder changed after the scan is
  presented as STALE, not repeated;
* manga and anime in one family are peers, each with its own state;
* partial or absent documents degrade to honest empty states, never errors.

All content is invented (D-18 / A-05).
"""

from __future__ import annotations

import datetime as dt
import json
import os
import time
from pathlib import Path
from typing import Any

import pytest
from continuum_api import create_app
from continuum_config import Settings
from fastapi.testclient import TestClient

ORBIT = "demo-orbit"
HARBOR = "demo-harbor"


def _row(work_id: str, title: str, cls: str, relation: str, coverage: str, *,
         story: bool, files: int = 0, family: str = ORBIT) -> dict[str, Any]:
    return {
        "work_id": work_id, "work": title, "family_id": family, "family_title": family,
        "relationship_type": relation, "material_class": cls, "story_material": story,
        "official_status": True, "coverage_status": coverage, "layout_status": "FOUND",
        "local_files": files, "local_bytes": files * 1000,
    }


def _documents(vault: Path, scanned_at: str) -> dict[str, dict[str, Any]]:
    orbit_classes = {
        "manga": {"exists": True, "story": True, "media_files": 20, "video_files": 0,
                  "bytes": 20_000, "attributed_files": 20, "unattributed_files": 0,
                  "last_added_ns": time.time_ns()},
        "anime": {"exists": True, "story": True, "media_files": 13, "video_files": 13,
                  "bytes": 13_000_000, "attributed_files": 13, "unattributed_files": 0,
                  "last_added_ns": time.time_ns()},
        "light-novel": {"exists": False, "story": True, "media_files": 0},
        "guidebook": {"exists": False, "story": False, "media_files": 0},
    }
    harbor_classes = {
        "manga": {"exists": True, "story": True, "media_files": 9, "video_files": 0, "bytes": 9000,
                  "attributed_files": 0, "unattributed_files": 9, "last_added_ns": 1},
    }
    layout = {
        "generated_at": scanned_at,
        "vault_root": str(vault),
        "summary": {"files": 42, "bytes": 13_029_000},
        "families": [
            {
                "family_id": ORBIT, "family_title": "Demo Orbit",
                "family_path": str(vault / "Demo Orbit"), "folder_exists": True,
                "files": 33, "bytes": 13_020_000, "classes": orbit_classes,
                "last_added_ns": time.time_ns(),
                "works": [
                    _row("o/main", "Demo Orbit", "manga", "MAIN_WORK", "COMPLETE",
                         story=True, files=20),
                    _row("o/tv", "Demo Orbit TV", "anime", "PARALLEL_ADAPTATION", "UNKNOWN",
                         story=True, files=13),
                    _row("o/novel", "Demo Orbit Novel", "light-novel", "OFFICIAL_SPINOFF",
                         "MISSING", story=True),
                    _row("o/guide", "Demo Orbit Guide", "guidebook", "GUIDEBOOK", "MISSING",
                         story=False),
                ],
                "findings": [],
            },
            {
                "family_id": HARBOR, "family_title": "Demo Harbor",
                "family_path": str(vault / "Demo Harbor"), "folder_exists": True,
                "files": 9, "bytes": 9000, "classes": harbor_classes,
                "works": [
                    _row("h/main", "Demo Harbor", "manga", "MAIN_WORK", "NEEDS_MAPPING",
                         story=True, family=HARBOR),
                    _row("h/side", "Demo Harbor Side", "manga", "OFFICIAL_SPINOFF",
                         "NEEDS_MAPPING", story=True, family=HARBOR),
                ],
                "findings": [],
            },
        ],
        "global_findings": [],
        "proposed_moves": [],
    }
    fresh = {
        "library_scanned_at": scanned_at,
        "catalogue_refreshed_at": "2026-01-01T00:00:00+00:00",
        "unhashed_files": 13,
        "vault_root": str(vault),
        "library_files": 42,
        "library_bytes": 13_029_000,
    }
    coverage = {
        "generated_at": scanned_at,
        "freshness": fresh,
        "works": {
            "o/main": {"status": "COMPLETE", "reason": "local reaches chapter 20",
                       "local_files": 20, "media": "pages"},
            "o/tv": {"status": "UNKNOWN", "reason": "13 episode file(s) present", "local_files": 13,
                     "media": "video",
                     "episodes": {"videos": 13, "other_videos": 1, "seasons": [
                         {"season": 1, "episodes": 12, "episodes_text": "1-12", "gaps_text": ""},
                     ]}},
            "o/novel": {"status": "MISSING", "reason": "no local media"},
            "o/guide": {"status": "MISSING", "reason": "no local media"},
            "h/main": {"status": "NEEDS_MAPPING", "unmapped_local_files": 9,
                       "reason": "9 local file(s) of this kind are not mapped"},
            "h/side": {"status": "NEEDS_MAPPING", "unmapped_local_files": 9,
                       "reason": "9 local file(s) of this kind are not mapped"},
        },
    }
    queue = {
        "works": [
            {"family": "Demo Orbit", "work": "Demo Orbit Novel", "work_id": "o/novel",
             "relation": "OFFICIAL_SPINOFF", "material_class": "light-novel", "official": True,
             "coverage_status": "MISSING", "priority": 3},
            {"family": "Demo Orbit", "work": "Demo Orbit Guide", "work_id": "o/guide",
             "relation": "GUIDEBOOK", "material_class": "guidebook", "official": True,
             "coverage_status": "MISSING", "priority": 6},
        ]
    }
    ingest = {
        "mode": "DRY RUN",
        "units": [
            {"source": "Manual", "unit": "Demo Orbit v02", "path": "x", "files": 1,
             "action": "imported (dry-run)", "family": "Demo Orbit"},
            {"source": "Manual", "unit": "Unknown bundle", "path": "y", "files": 3,
             "action": "left-in-intake: unclassified"},
            {"source": "Manual", "unit": "Copy of v01", "path": "z", "files": 1,
             "action": "identical-already-in-vault"},
            {"source": "Manual", "unit": "half", "path": "w", "files": 1,
             "action": "left-in-intake: incomplete download"},
        ],
    }
    return {
        "vault-layout.json": layout,
        "vault-coverage.json": coverage,
        "acquisition-queue.json": queue,
        "ingest-last.json": ingest,
        "sources.json": {"sources": {
            "demo-shop": {"id": "demo-shop", "name": "Demo Shop", "url": "https://shop.invalid",
                          "enabled": False, "capabilities": ["DISCOVERY_ONLY"]},
        }},
    }


def _write(directory: Path, documents: dict[str, dict[str, Any]]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for name, document in documents.items():
        (directory / name).write_text(json.dumps(document), encoding="utf-8")


def _age(path: Path, seconds: float) -> None:
    """Make a directory look older than it is (its mtime), for the freshness check."""
    past = time.time() - seconds
    os.utime(path, (past, past))


@pytest.fixture
def library(tmp_path: Path) -> tuple[Path, Path]:
    vault = tmp_path / "vault"
    for folder in ("Demo Orbit/manga", "Demo Orbit/anime", "Demo Harbor/manga"):
        (vault / folder).mkdir(parents=True)
    for folder in ("Demo Orbit/manga", "Demo Orbit/anime", "Demo Harbor/manga",
                   "Demo Orbit", "Demo Harbor", ""):
        _age(vault / folder, 3600)
    scanned = dt.datetime.now(tz=dt.UTC).isoformat(timespec="seconds")
    data = tmp_path / "acquisition"
    _write(data, _documents(vault, scanned))
    return vault, data


def _client(data_home: Path, vault_root: Path, data: Path) -> TestClient:
    settings = Settings(_env_file=None, data_home=str(data_home),
                        source_vault_root=str(vault_root), acquisition_data_dir=str(data))
    return TestClient(create_app(settings))


# ---------------------------------------------------------------------------
def test_local_material_is_never_presented_as_missing(
    data_home: Path, vault_root: Path, library: tuple[Path, Path]
) -> None:
    _vault, data = library
    with _client(data_home, vault_root, data) as client:
        detail = client.get(f"/library/acquisition/families/{ORBIT}").json()
        harbor = client.get(f"/library/acquisition/families/{HARBOR}").json()
    states = {w["id"]: w["state"] for w in detail["works"]}
    assert states["o/main"] == "COMPLETE"
    assert states["o/tv"] == "PRESENT", "held with nothing to compare against is 'in library'"
    assert states["o/novel"] == "MISSING"
    assert {w["state"] for w in harbor["works"]} == {"NEEDS_MAPPING"}
    assert harbor["family"]["state"] == "NEEDS_MAPPING"
    assert harbor["family"]["missing"] == 0


def test_manga_and_anime_are_peers_in_one_family(
    data_home: Path, vault_root: Path, library: tuple[Path, Path]
) -> None:
    _vault, data = library
    with _client(data_home, vault_root, data) as client:
        family = client.get(f"/library/acquisition/families/{ORBIT}").json()
    materials = {m["material_class"]: m for m in family["family"]["materials"]}
    assert materials["manga"]["state"] == "COMPLETE"
    assert materials["anime"]["state"] == "PRESENT"
    assert materials["anime"]["video_files"] == 13
    assert materials["light-novel"]["state"] == "MISSING"
    assert materials["guidebook"]["story"] is False
    # story material leads, supplements follow
    assert [m["story"] for m in family["family"]["materials"]] == sorted(
        (m["story"] for m in family["family"]["materials"]), reverse=True
    )
    tv = next(w for w in family["works"] if w["id"] == "o/tv")
    assert tv["media"] == "video"
    assert tv["episodes"] == [
        {"season": 1, "episodes": 12, "episodes_text": "1-12", "gaps_text": ""}
    ]
    assert tv["other_videos"] == 1


def test_a_fresh_scan_is_reported_fresh(
    data_home: Path, vault_root: Path, library: tuple[Path, Path]
) -> None:
    _vault, data = library
    with _client(data_home, vault_root, data) as client:
        fresh = client.get("/library/acquisition/status").json()["freshness"]
    assert fresh["state"] == "fresh"
    assert fresh["vault_changed"] is False
    assert fresh["catalogue_refreshed_at"] == "2026-01-01T00:00:00+00:00"
    assert fresh["unhashed_files"] == 13


def test_missing_is_not_repeated_about_a_folder_that_changed_since_the_scan(
    data_home: Path, vault_root: Path, library: tuple[Path, Path]
) -> None:
    """New files arrived after the scan: its MISSING verdicts may no longer be true."""
    vault, data = library
    (vault / "Demo Orbit" / "light-novel").mkdir()  # updates the family folder's mtime
    with _client(data_home, vault_root, data) as client:
        status = client.get("/library/acquisition/status").json()
        family = client.get(f"/library/acquisition/families/{ORBIT}").json()
        other = client.get(f"/library/acquisition/families/{HARBOR}").json()
        queue = client.get("/library/acquisition/queue").json()
    assert status["freshness"]["state"] == "stale"
    assert status["freshness"]["changed_families"] == [ORBIT]
    novel = next(w for w in family["works"] if w["id"] == "o/novel")
    assert novel["state"] == "STALE"
    assert family["family"]["stale"] is True
    assert family["family"]["missing"] == 0
    assert other["family"]["stale"] is False, "only the folder that changed is in doubt"
    assert {g["key"] for g in queue["groups"]} == {"rescan"}


def test_a_new_top_level_folder_marks_the_library_stale(
    data_home: Path, vault_root: Path, library: tuple[Path, Path]
) -> None:
    vault, data = library
    (vault / "Demo Newcomer").mkdir()
    with _client(data_home, vault_root, data) as client:
        fresh = client.get("/library/acquisition/status").json()["freshness"]
    assert fresh["state"] == "stale"
    assert fresh["changed_folders"] == ["Demo Newcomer"]


def test_an_unreachable_vault_is_unknown_not_fresh(
    data_home: Path, vault_root: Path, tmp_path: Path
) -> None:
    data = tmp_path / "acquisition"
    _write(data, _documents(tmp_path / "gone", dt.datetime.now(tz=dt.UTC).isoformat()))
    with _client(data_home, vault_root, data) as client:
        body = client.get(f"/library/acquisition/families/{ORBIT}").json()
        fresh = client.get("/library/acquisition/status").json()["freshness"]
    assert fresh["state"] == "unknown"
    assert fresh["vault_changed"] is None
    assert next(w for w in body["works"] if w["id"] == "o/novel")["state"] == "MISSING"


def test_overview_leads_with_the_library_not_with_metrics(
    data_home: Path, vault_root: Path, library: tuple[Path, Path]
) -> None:
    _vault, data = library
    with _client(data_home, vault_root, data) as client:
        body = client.get("/library/acquisition").json()
    hero = body["hero"]
    assert hero["families"] == 2
    assert hero["story_works"] == 5
    assert hero["complete"] == 1
    assert hero["present"] == 1
    assert hero["needs_mapping"] == 2
    recent = {(r["family_id"], r["material_class"]) for r in body["recently_added"]}
    assert (ORBIT, "anime") in recent
    assert (HARBOR, "manga") not in recent, "a file created in 1970 is not recent"
    kinds = [s["kind"] for s in body["next_steps"]]
    assert "map" in kinds
    assert len(body["next_steps"]) <= 6


def test_the_queue_is_grouped_by_reason(
    data_home: Path, vault_root: Path, library: tuple[Path, Path]
) -> None:
    _vault, data = library
    with _client(data_home, vault_root, data) as client:
        body = client.get("/library/acquisition/queue").json()
        supplements = client.get("/library/acquisition/queue?group=supplements").json()
    groups = {g["key"]: g["count"] for g in body["groups"]}
    assert groups == {"side": 1, "supplements": 1}
    assert [i["work"] for i in supplements["items"]] == ["Demo Orbit Guide"]
    assert body["needs_mapping"] == 2, "present-but-unmapped work is never queued for purchase"


def test_intake_sorts_units_into_human_sections(
    data_home: Path, vault_root: Path, library: tuple[Path, Path]
) -> None:
    _vault, data = library
    with _client(data_home, vault_root, data) as client:
        units = client.get("/library/acquisition/intake").json()["units"]
    assert {u["unit"]: u["section"] for u in units} == {
        "Demo Orbit v02": "ready",
        "Unknown bundle": "identify",
        "Copy of v01": "known",
        "half": "incomplete",
    }


def test_updates_timeline_includes_new_local_files(
    data_home: Path, vault_root: Path, library: tuple[Path, Path]
) -> None:
    _vault, data = library
    with _client(data_home, vault_root, data) as client:
        timeline = client.get("/library/acquisition/updates").json()["timeline"]
    assert any(e["kind"] == "local_files" and e["family_id"] == ORBIT for e in timeline)


def test_partial_documents_degrade_to_honest_states(
    data_home: Path, vault_root: Path, tmp_path: Path
) -> None:
    """Only the layout exists: nothing crashes, and nothing is called missing without a verdict."""
    data = tmp_path / "acquisition"
    documents = _documents(tmp_path / "vault", dt.datetime.now(tz=dt.UTC).isoformat())
    layout = documents["vault-layout.json"]
    for family in layout["families"]:
        for work in family["works"]:
            work.pop("coverage_status")
    _write(data, {"vault-layout.json": layout})
    with _client(data_home, vault_root, data) as client:
        for path in ("", "/status", "/families", f"/families/{ORBIT}", "/queue", "/intake",
                     "/updates", "/calendar", "/sources"):
            assert client.get(f"/library/acquisition{path}").status_code == 200, path
        body = client.get(f"/library/acquisition/families/{ORBIT}").json()
    assert {w["state"] for w in body["works"]} == {"UNVERIFIED"}


def test_a_large_library_stays_quick(
    data_home: Path, vault_root: Path, tmp_path: Path
) -> None:
    """Hundreds of families: the list answers well within an interactive budget."""
    vault = tmp_path / "vault"
    vault.mkdir()
    base = _documents(vault, dt.datetime.now(tz=dt.UTC).isoformat())
    template = base["vault-layout.json"]["families"][0]
    families = []
    coverage = {}
    for n in range(600):
        family = json.loads(json.dumps(template))
        family["family_id"] = f"demo-{n:03d}"
        family["family_title"] = f"Demo {n:03d}"
        family["family_path"] = str(vault / f"Demo {n:03d}")
        for work in family["works"]:
            work["work_id"] = f"{family['family_id']}/{work['work_id']}"
            coverage[work["work_id"]] = {"status": work["coverage_status"]}
        families.append(family)
    base["vault-layout.json"]["families"] = families
    base["vault-coverage.json"]["works"] = coverage
    data = tmp_path / "acquisition"
    _write(data, base)
    with _client(data_home, vault_root, data) as client:
        client.get("/library/acquisition/families")  # parse and cache the documents
        started = time.perf_counter()
        body = client.get("/library/acquisition/families").json()
        elapsed = time.perf_counter() - started
    assert len(body) == 600
    assert elapsed < 3.0, f"families list took {elapsed:.2f}s for 600 families"


def test_a_disabled_source_is_listed_as_disabled(
    data_home: Path, vault_root: Path, library: tuple[Path, Path]
) -> None:
    _vault, data = library
    with _client(data_home, vault_root, data) as client:
        sources = client.get("/library/acquisition/sources").json()["sources"]
    assert [s["id"] for s in sources] == ["demo-shop"]
    assert sources[0]["enabled"] is False


def test_refresh_rescans_without_hashing(
    data_home: Path, vault_root: Path, library: tuple[Path, Path], tmp_path: Path
) -> None:
    """Coverage needs where files are, not their hashes; hashing can take many minutes."""
    _vault, data = library
    cli = tmp_path / "fake_cli.py"
    cli.write_text('import sys\nprint(" ".join(sys.argv[1:]))\n', encoding="utf-8")
    settings = Settings(_env_file=None, data_home=str(data_home), source_vault_root=str(vault_root),
                        acquisition_data_dir=str(data), acquisition_cli=str(cli))
    with TestClient(create_app(settings)) as client:
        body = client.post("/library/acquisition/refresh").json()
    assert body["ok"] is True
    assert body["command"].endswith("coverage --no-hash")
