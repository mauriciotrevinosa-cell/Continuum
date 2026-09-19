"""Safety coverage for the schema-driven M3 character merge tool."""

from __future__ import annotations

import pytest
from continuum_db.models import CharacterOutfit, CharacterProductionModel
from continuum_library import ReferenceCatalog
from sqlalchemy.orm import Session

from scripts.merge_character_duplicates import (
    _apply_merge,
    _constraint_probe,
    _merge_plan,
    _validate_profiles,
)
from tests.phase1_world import clean_domain_tables

pytestmark = pytest.mark.requires_db


@pytest.fixture(autouse=True)
def _clean_domain_tables(db_session: Session) -> None:
    clean_domain_tables(db_session)


def test_merge_moves_links_then_soft_retires_source(db_session: Session) -> None:
    catalog = ReferenceCatalog(db_session)
    target = catalog.create_character("Frieren", source_label="Primary Source")
    source = catalog.create_character("Frieren", source_label="Invented Almanac")
    outfit = catalog.create_outfit(source.id, "Polluted Outfit")
    db_session.flush()

    checked_target, sources = _validate_profiles(db_session, target.id, [source.id])
    moves = _merge_plan(db_session, checked_target.id, [source.id])

    assert [(move.key, move.count) for move in moves] == [("character_outfit.character_id", 1)]
    assert _constraint_probe(db_session, target.id, moves) is None

    _apply_merge(db_session, target.id, sources, moves)
    db_session.flush()

    moved = db_session.get(CharacterOutfit, outfit.id)
    assert moved is not None and moved.character_id == target.id
    assert catalog.character(source.id, include_removed=True).removed_at is not None


def test_constraint_probe_blocks_unique_collision(db_session: Session) -> None:
    catalog = ReferenceCatalog(db_session)
    target = catalog.create_character("Juniper Quill", source_label="Invented Almanac")
    source = catalog.create_character("Juniper Quill", source_label="Invented Almanac")
    db_session.add_all(
        [
            CharacterProductionModel(
                project_key="demo-project",
                character_id=target.id,
                version=1,
                status="DRAFT",
                name="Target model",
                summary="",
                identity_rules=[],
                restrictions=[],
                created_from={},
            ),
            CharacterProductionModel(
                project_key="demo-project",
                character_id=source.id,
                version=1,
                status="DRAFT",
                name="Source model",
                summary="",
                identity_rules=[],
                restrictions=[],
                created_from={},
            ),
        ]
    )
    db_session.flush()

    moves = _merge_plan(db_session, target.id, [source.id])
    conflict = _constraint_probe(db_session, target.id, moves)

    assert conflict is not None
    assert conflict["table"] == "character_production_model"
    assert conflict["constraint"] != "unknown"
