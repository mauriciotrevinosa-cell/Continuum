"""Regression coverage for ambiguous active character names during M3 calibration."""

from __future__ import annotations

import pytest
from continuum_library import CatalogConflictError, ReferenceCatalog
from continuum_production.corpus import CharacterCorpus
from sqlalchemy.orm import Session

from tests.acceptance import test_phase1_rough_production as rough
from tests.phase1_world import clean_domain_tables

pytestmark = pytest.mark.requires_db

session = rough.session
catalog = rough.catalog


@pytest.fixture(autouse=True)
def _clean_domain_tables(session: Session) -> None:
    clean_domain_tables(session)


def test_by_name_rejects_ambiguous_active_character_names(
    session: Session, catalog: ReferenceCatalog
) -> None:
    catalog.create_character("Mau", source_label="Invented Almanac")
    catalog.create_character("Mau", source_label="Invented Almanac")
    session.flush()

    with pytest.raises(CatalogConflictError, match="More than one active character") as exc_info:
        CharacterCorpus(session, catalog).by_name("Mau")

    assert exc_info.value.remediation == (
        "Archive or merge duplicate Character Vault entries, then retry."
    )
