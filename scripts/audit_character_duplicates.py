"""Audit active duplicate character profiles and optionally soft-retire known test pollution.

Nothing is deleted from the Source Vault or reference storage. By default this
only prints duplicate groups. Applying a source-label cleanup soft-retires only
profiles with that exact source label, only inside a duplicate-name group, and
only when the candidate has no database rows linked to its character identity.

Examples:

    uv run --no-sync python scripts/audit_character_duplicates.py
    uv run --no-sync python scripts/audit_character_duplicates.py \
        --retire-source-label "Invented Almanac"
    uv run --no-sync python scripts/audit_character_duplicates.py \
        --retire-source-label "Invented Almanac" --apply
"""

from __future__ import annotations

import argparse
import sys
import uuid
from collections import defaultdict

from continuum_config import get_settings
from continuum_db.models import CharacterProfile
from continuum_db.session import session_scope
from continuum_library import ReferenceCatalog
from sqlalchemy import func, select
from sqlalchemy.orm import Session


def _dependency_counts(session: Session, character_id: uuid.UUID) -> dict[str, int]:
    """Count every live DB link to a character identity, including future tables.

    The cleanup is deliberately schema-driven instead of maintaining a hand-written
    list of references. Any foreign key that points at ``character_profile.id``
    protects that profile from automatic retirement.
    """
    counts: dict[str, int] = {}
    for table in CharacterProfile.metadata.sorted_tables:
        if table is CharacterProfile.__table__:
            continue
        for column in table.c:
            if not any(fk.target_fullname == "character_profile.id" for fk in column.foreign_keys):
                continue
            count = session.execute(
                select(func.count()).select_from(table).where(column == character_id)
            ).scalar_one()
            if count:
                counts[f"{table.name}.{column.name}"] = int(count)
    return counts


def _retirement_plan(
    duplicates: list[list[CharacterProfile]], label: str, session: Session
) -> tuple[list[CharacterProfile], dict[uuid.UUID, dict[str, int]]]:
    """Return safe retirements and linked candidates that require manual merge/review."""
    candidates: list[CharacterProfile] = []
    for group in duplicates:
        matching = [row for row in group if row.source_label == label]
        if not matching:
            continue
        nonmatching = [row for row in group if row.source_label != label]
        if nonmatching:
            candidates.extend(matching)
        elif len(matching) > 1:
            # If every duplicate has the polluted label, preserve the oldest
            # record and consider only redundant copies for retirement.
            candidates.extend(matching[1:])

    planned: list[CharacterProfile] = []
    blocked: dict[uuid.UUID, dict[str, int]] = {}
    for row in candidates:
        dependencies = _dependency_counts(session, row.id)
        if dependencies:
            blocked[row.id] = dependencies
        else:
            planned.append(row)
    return planned, blocked


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--retire-source-label", default="")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)

    if args.apply and not args.retire_source_label:
        parser.error("--apply requires --retire-source-label")

    settings = get_settings()
    with session_scope(settings) as session:
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
        groups: dict[str, list[CharacterProfile]] = defaultdict(list)
        for row in rows:
            groups[row.display_name.casefold()].append(row)

        duplicates = [group for group in groups.values() if len(group) > 1]
        if not duplicates:
            print("No active duplicate display names found.")
            return 0

        print(f"Found {len(duplicates)} duplicate-name group(s):")
        for group in duplicates:
            print(f"\n{group[0].display_name} ({len(group)} active profiles)")
            for row in group:
                links = _dependency_counts(session, row.id)
                link_summary = ", ".join(f"{key}={value}" for key, value in sorted(links.items()))
                print(
                    "  "
                    f"{row.id}  source={row.source_label!r}  origin={row.origin.value}  "
                    f"project={row.project_key!r}  created={row.created_at.isoformat()}  "
                    f"links={link_summary or 'none'}"
                )

        label = args.retire_source_label.strip()
        if not label:
            print("\nDry audit only; no rows changed.")
            return 1

        planned, blocked = _retirement_plan(duplicates, label, session)

        print(f"\nExact source-label cleanup: {label!r}")
        for row in planned:
            print(f"  RETIRE {row.display_name}: {row.id} ({row.source_label})")
        for group in duplicates:
            for row in group:
                links = blocked.get(row.id)
                if links:
                    summary = ", ".join(
                        f"{key}={value}" for key, value in sorted(links.items())
                    )
                    print(
                        f"  BLOCK  {row.display_name}: {row.id} ({row.source_label}) "
                        f"has linked data: {summary}"
                    )

        if not planned:
            if blocked:
                print(
                    "No linked profile is safe to retire automatically; "
                    "merge/review it manually."
                )
            else:
                print("Nothing qualifies for safe retirement.")
            return 1

        if not args.apply:
            print("\nDry run; pass --apply to soft-retire exactly the RETIRE rows above.")
            if blocked:
                print("BLOCK rows will remain active even with --apply.")
            return 2

        catalog = ReferenceCatalog(session)
        for row in planned:
            catalog.remove_character(row.id, row.row_version)
        session.flush()
        print(
            f"\nSoft-retired {len(planned)} unlinked profile(s). "
            "Reference/source bytes were not deleted."
        )
        if blocked:
            print(f"Left {len(blocked)} linked duplicate(s) active for manual merge/review.")
        print("Run this script again with no arguments to see any remaining ambiguity.")
        return 1 if blocked else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
