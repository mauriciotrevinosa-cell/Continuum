"""Audit active duplicate character profiles and optionally soft-retire known test pollution.

Nothing is deleted from the Source Vault or reference storage. By default this
only prints duplicate groups. Applying a source-label cleanup soft-retires only
profiles with that exact source label, and only inside a duplicate-name group.

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
from collections import defaultdict

from continuum_config import get_settings
from continuum_db.models import CharacterProfile
from continuum_db.session import session_scope
from continuum_library import ReferenceCatalog
from sqlalchemy import select


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
                .order_by(CharacterProfile.display_name, CharacterProfile.created_at, CharacterProfile.id)
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
                print(
                    "  "
                    f"{row.id}  source={row.source_label!r}  origin={row.origin.value}  "
                    f"project={row.project_key!r}  created={row.created_at.isoformat()}"
                )

        label = args.retire_source_label.strip()
        if not label:
            print("\nDry audit only; no rows changed.")
            return 1

        planned: list[CharacterProfile] = []
        for group in duplicates:
            matching = [row for row in group if row.source_label == label]
            if not matching:
                continue
            nonmatching = [row for row in group if row.source_label != label]
            if nonmatching:
                planned.extend(matching)
            elif len(matching) > 1:
                # If every duplicate has the polluted label, preserve the oldest
                # record and retire only the redundant copies. This keeps the
                # operation conservative and reversible.
                planned.extend(matching[1:])

        print(f"\nExact source-label cleanup: {label!r}")
        if not planned:
            print("Nothing qualifies for safe retirement.")
            return 1
        for row in planned:
            print(f"  RETIRE {row.display_name}: {row.id} ({row.source_label})")

        if not args.apply:
            print("\nDry run; pass --apply to soft-retire exactly these rows.")
            return 2

        catalog = ReferenceCatalog(session)
        for row in planned:
            catalog.remove_character(row.id, row.row_version)
        session.flush()
        print(f"\nSoft-retired {len(planned)} profile(s). Reference/source bytes were not deleted.")
        print("Run this script again with no arguments to see any remaining ambiguity.")
        return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
