"""Soft-retire known M3 acceptance-test character pollution without moving child data.

This cleanup exists for one historical failure mode: acceptance fixtures were
written into the application database before database isolation was hardened.
The fingerprints below come directly from those invented fixtures. Dry-run is
the default. Linked observations, references, outfits and production models are
preserved on the retired profile for provenance; nothing is merged into a real
character and no source/reference bytes are deleted.

Examples:

    uv run --no-sync python scripts/retire_m3_test_character_pollution.py
    uv run --no-sync python scripts/retire_m3_test_character_pollution.py --apply
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from dataclasses import dataclass

from continuum_config import get_settings
from continuum_db.models import CharacterOutfit, CharacterProfile
from continuum_db.session import session_scope
from continuum_library import ReferenceCatalog
from sqlalchemy import select
from sqlalchemy.orm import Session

from scripts.audit_character_duplicates import _dependency_counts

_INVENTED_SOURCE_NAMES = frozenset({"frieren", "juniper quill", "kestrel moss"})
_DEMO_PROJECT_NAMES = frozenset({"mau", "rowan"})
_MAU_TEST_OUTFITS = frozenset({"M-H1 McLaren hoodie", "M-A2 McLaren cap"})


@dataclass(frozen=True, slots=True)
class Candidate:
    profile: CharacterProfile
    reason: str


def _has_mau_test_outfit(session: Session, character_id: object) -> bool:
    return (
        session.execute(
            select(CharacterOutfit.id)
            .where(
                CharacterOutfit.character_id == character_id,
                CharacterOutfit.removed_at.is_(None),
                CharacterOutfit.name.in_(_MAU_TEST_OUTFITS),
            )
            .limit(1)
        ).scalar_one_or_none()
        is not None
    )


def _fixture_reason(session: Session, row: CharacterProfile) -> str | None:
    """Return the exact acceptance-fixture fingerprint matched by an active profile."""
    name = row.display_name.casefold()
    origin = row.origin.value

    if row.source_label == "Invented Almanac" and name in _INVENTED_SOURCE_NAMES:
        return "acceptance source label 'Invented Almanac'"

    if (
        name in _DEMO_PROJECT_NAMES
        and row.project_key == "demo-project"
        and origin == "PROJECT_ORIGINAL"
    ):
        return "acceptance project 'demo-project'"

    if (
        name == "aster vale"
        and row.source_label == ""
        and row.project_key is None
        and origin == "SOURCE_WORK"
    ):
        return "rough-production fixture 'Aster Vale'"

    if (
        name == "mau"
        and row.source_label == ""
        and row.project_key == "the-arrivals"
        and origin == "PROJECT_ORIGINAL"
        and _has_mau_test_outfit(session, row.id)
    ):
        return "M3 wardrobe fixture outfit"

    return None


def _duplicate_groups(session: Session) -> list[list[CharacterProfile]]:
    rows = list(
        session.execute(
            select(CharacterProfile)
            .where(CharacterProfile.removed_at.is_(None))
            .order_by(
                CharacterProfile.display_name,
                CharacterProfile.created_at,
                CharacterProfile.id,
            )
        ).scalars()
    )
    grouped: dict[str, list[CharacterProfile]] = defaultdict(list)
    for row in rows:
        grouped[row.display_name.casefold()].append(row)
    return [group for group in grouped.values() if len(group) > 1]


def _pollution_plan(
    session: Session,
) -> tuple[list[Candidate], dict[str, list[CharacterProfile]]]:
    """Plan known fixture retirements and flag groups still ambiguous afterwards."""
    candidates: list[Candidate] = []
    unresolved: dict[str, list[CharacterProfile]] = {}

    for group in _duplicate_groups(session):
        matched: list[Candidate] = []
        survivors: list[CharacterProfile] = []
        for row in group:
            reason = _fixture_reason(session, row)
            if reason is None:
                survivors.append(row)
            else:
                matched.append(Candidate(row, reason))

        candidates.extend(matched)
        if len(survivors) > 1:
            unresolved[group[0].display_name] = survivors

    return candidates, unresolved


def _apply_retirement(session: Session, candidates: list[Candidate]) -> None:
    """Soft-retire profiles only; linked rows deliberately remain attached to them."""
    catalog = ReferenceCatalog(session)
    for candidate in candidates:
        row = candidate.profile
        catalog.remove_character(row.id, row.row_version)
    session.flush()


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)

    settings = get_settings()
    with session_scope(settings) as session:
        candidates, unresolved = _pollution_plan(session)

        if not candidates:
            print("No known M3 character fixture pollution found in duplicate groups.")
            if unresolved:
                print("Unresolved duplicate groups still require manual review.")
                return 1
            return 0

        print(f"Known fixture pollution: {len(candidates)} profile(s)")
        for candidate in candidates:
            row = candidate.profile
            links = _dependency_counts(session, row.id)
            summary = ", ".join(f"{key}={value}" for key, value in sorted(links.items()))
            print(
                f"  ARCHIVE {row.display_name}: {row.id}  reason={candidate.reason}; "
                f"links={summary or 'none'}"
            )

        if unresolved:
            print("\nBLOCK: cleanup would leave these duplicate groups ambiguous:")
            for name, rows in sorted(unresolved.items()):
                ids = ", ".join(str(row.id) for row in rows)
                print(f"  {name}: {ids}")
            print("No rows changed.")
            return 1

        print(
            "\nChild rows stay attached to the archived fixture profiles; "
            "nothing is merged or deleted."
        )
        if not args.apply:
            print("Dry run only; pass --apply to soft-retire exactly the ARCHIVE rows above.")
            return 2

        _apply_retirement(session, candidates)
        print(f"Soft-retired {len(candidates)} known fixture profile(s).")
        print("Run scripts/audit_character_duplicates.py again to verify active names.")
        return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
