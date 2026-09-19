"""Safety coverage for retiring historical M3 fixture pollution."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from continuum_core.references import CharacterOrigin, OutfitKind
from continuum_db.models import CharacterOutfit
from continuum_library import ReferenceCatalog
from sqlalchemy.orm import Session

from scripts.retire_m3_test_character_pollution import (
    _apply_retirement,
    _pollution_plan,
)
from tests.phase1_world import clean_domain_tables

pytestmark = pytest.mark.requires_db


@pytest.fixture(autouse=True)
def _clean_domain_tables(db_session: Session) -> None:
    clean_domain_tables(db_session)


def test_direct_script_entrypoint_imports_successfully() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [sys.executable, "scripts/retire_m3_test_character_pollution.py", "--help"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "Soft-retire known M3 acceptance-test character pollution" in result.stdout


def test_fixture_pollution_retires_without_moving_linked_rows(db_session: Session) -> None:
    catalog = ReferenceCatalog(db_session)
    canonical_frieren = catalog.create_character(
        "Frieren", source_label="Canonical Source Work"
    )
    polluted_frieren = catalog.create_character("Frieren", source_label="Invented Almanac")
    polluted_robe = catalog.create_outfit(
        polluted_frieren.id, "Travelling robes", kind=OutfitKind.SOURCE_DEFAULT
    )

    canonical_mau = catalog.create_character(
        "Mau",
        source_label="The Arrivals / creator-photo grounding",
        origin=CharacterOrigin.PROJECT_ORIGINAL,
        project_key="the-arrivals",
    )
    polluted_mau = catalog.create_character(
        "Mau",
        origin=CharacterOrigin.PROJECT_ORIGINAL,
        project_key="the-arrivals",
    )
    polluted_hoodie = catalog.create_outfit(
        polluted_mau.id,
        "M-H1 McLaren hoodie",
        kind=OutfitKind.PROJECT,
        project_key="the-arrivals",
    )
    db_session.flush()

    candidates, unresolved = _pollution_plan(db_session)

    assert unresolved == {}
    assert {candidate.profile.id for candidate in candidates} == {
        polluted_frieren.id,
        polluted_mau.id,
    }

    _apply_retirement(db_session, candidates)
    db_session.flush()

    assert canonical_frieren.removed_at is None
    assert canonical_mau.removed_at is None
    assert polluted_frieren.removed_at is not None
    assert polluted_mau.removed_at is not None

    robe = db_session.get(CharacterOutfit, polluted_robe.id)
    hoodie = db_session.get(CharacterOutfit, polluted_hoodie.id)
    assert robe is not None and robe.character_id == polluted_frieren.id
    assert hoodie is not None and hoodie.character_id == polluted_mau.id

    active_by_name = {row.display_name: row for row in catalog.list_characters()}
    assert active_by_name["Frieren"].id == canonical_frieren.id
    assert active_by_name["Mau"].id == canonical_mau.id


def test_unknown_duplicate_group_blocks_cleanup(db_session: Session) -> None:
    catalog = ReferenceCatalog(db_session)
    catalog.create_character("Unknown Duplicate", source_label="User Source A")
    catalog.create_character("Unknown Duplicate", source_label="User Source B")
    db_session.flush()

    candidates, unresolved = _pollution_plan(db_session)

    assert candidates == []
    assert list(unresolved) == ["Unknown Duplicate"]
