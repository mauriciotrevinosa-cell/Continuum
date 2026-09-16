"""Safety coverage for the M3 duplicate-character retirement tool."""

from __future__ import annotations

import pytest
from continuum_library import ReferenceCatalog
from sqlalchemy.orm import Session

from scripts.audit_character_duplicates import _retirement_plan
from tests.phase1_world import clean_domain_tables

pytestmark = pytest.mark.requires_db


@pytest.fixture
def session(db_session: Session) -> Session:
    """Use only the isolated ``*_test`` database for destructive fixture cleanup."""
    clean_domain_tables(db_session)
    return db_session


@pytest.fixture
def catalog(session: Session) -> ReferenceCatalog:
    return ReferenceCatalog(session)


def test_retirement_plan_skips_polluted_profile_with_linked_data(
    session: Session, catalog: ReferenceCatalog
) -> None:
    keeper = catalog.create_character("Mau", source_label="Primary Source")
    linked_pollution = catalog.create_character("Mau", source_label="Invented Almanac")
    unlinked_pollution = catalog.create_character("Mau", source_label="Invented Almanac")
    catalog.create_outfit(linked_pollution.id, "Test Outfit")
    session.flush()

    planned, blocked = _retirement_plan(
        [[keeper, linked_pollution, unlinked_pollution]], "Invented Almanac", session
    )

    assert [row.id for row in planned] == [unlinked_pollution.id]
    assert linked_pollution.id in blocked
    assert blocked[linked_pollution.id]["character_outfit.character_id"] == 1
