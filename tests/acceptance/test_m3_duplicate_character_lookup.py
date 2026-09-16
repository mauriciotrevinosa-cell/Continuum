"""Regression coverage for ambiguous active character names during M3 calibration."""

from __future__ import annotations

import pytest
from continuum_library import CatalogConflictError, ReferenceCatalog
from continuum_production.corpus import CharacterCorpus
from sqlalchemy.orm import Session

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


def test_by_name_rejects_ambiguous_active_character_names(
    session: Session, catalog: ReferenceCatalog
) -> None:
    catalog.create_character("Mau", source_label="Invented Almanac")
    catalog.create_character("Mau", source_label="Invented Almanac")
    session.flush()

    with pytest.raises(
        CatalogConflictError, match="More than one active character"
    ) as exc_info:
        CharacterCorpus(session, catalog).by_name("Mau")

    assert exc_info.value.remediation == (
        "Archive or merge duplicate Character Vault entries, then retry."
    )
