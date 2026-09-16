"""Ensure a project calibration roster has one usable Character Vault profile per name.

This is intentionally conservative: it creates missing profile shells but does
not auto-approve images, candidates, outfits or Production Models. The user's
Source Vault is local and is not stored in Git, so visual grounding still has
to come from the local catalog and creator review.

Examples:

    uv run --no-sync python scripts/bootstrap_calibration_cast.py
    uv run --no-sync python scripts/bootstrap_calibration_cast.py --apply
    uv run --no-sync python scripts/bootstrap_calibration_cast.py --group core9 --apply
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path
from typing import Any

from continuum_config import get_settings
from continuum_core.references import CharacterOrigin
from continuum_db.models import CatalogUnit, CharacterProfile
from continuum_db.session import session_scope
from continuum_library import ReferenceCatalog
from sqlalchemy import func, select

REPO = Path(__file__).resolve().parents[1]
DEFAULT_ROSTER = REPO / "docs" / "creative" / "THE_ARRIVALS_CALIBRATION_CAST_v0.1.json"


def _characters(roster: dict[str, Any], group: str) -> list[dict[str, Any]]:
    groups = roster.get("groups") or {}
    if group == "all":
        out: list[dict[str, Any]] = []
        for name in ("core9", "g3", "antagonists"):
            out.extend(groups.get(name) or [])
        return out
    return list(groups.get(group) or [])


def _held_counts(session: Any) -> dict[str, int]:
    rows = session.execute(
        select(CatalogUnit.series_title, func.count(CatalogUnit.id))
        .where(CatalogUnit.series_title.is_not(None))
        .group_by(CatalogUnit.series_title)
    ).all()
    return {str(title).casefold(): int(count) for title, count in rows if title}


def _held_for(spec: dict[str, Any], held: dict[str, int]) -> int:
    labels = [spec.get("source_label", ""), *(spec.get("aliases") or [])]
    return max((held.get(str(label).casefold(), 0) for label in labels if label), default=0)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--roster", type=Path, default=DEFAULT_ROSTER)
    parser.add_argument("--group", choices=("all", "core9", "g3", "antagonists"), default="all")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)

    roster = json.loads(args.roster.read_text(encoding="utf-8"))
    wanted = _characters(roster, args.group)
    if not wanted:
        raise SystemExit(f"No characters found for group {args.group!r}")

    settings = get_settings()
    created = conflicts = 0
    with session_scope(settings) as session:
        catalog = ReferenceCatalog(session)
        held = _held_counts(session)

        for spec in wanted:
            name = str(spec["name"]).strip()
            source_label = str(spec.get("source_label") or "").strip()
            expected_id = spec.get("existing_profile_id")
            profile: CharacterProfile | None = None

            if expected_id:
                try:
                    candidate = session.get(CharacterProfile, uuid.UUID(str(expected_id)))
                except ValueError:
                    candidate = None
                if candidate is not None and candidate.removed_at is None:
                    profile = candidate

            matches = list(
                session.execute(
                    select(CharacterProfile).where(
                        CharacterProfile.removed_at.is_(None),
                        func.lower(CharacterProfile.display_name) == name.casefold(),
                        func.lower(CharacterProfile.source_label) == source_label.casefold(),
                    )
                ).scalars()
            )
            if profile is None:
                if len(matches) == 1:
                    profile = matches[0]
                elif len(matches) > 1:
                    conflicts += 1
                    ids = ", ".join(str(row.id) for row in matches)
                    print(f"AMBIGUOUS {name}: {len(matches)} exact active profiles ({ids})")
                    continue

            held_units = _held_for(spec, held)
            if profile is not None:
                print(
                    f"OK        {name:12} {profile.id}  source={profile.source_label!r}  "
                    f"held_units={held_units}"
                )
                continue

            print(
                f"MISSING   {name:12} source={source_label!r}  held_units={held_units}"
                + ("  -> create" if args.apply else "")
            )
            if not args.apply:
                continue

            origin = CharacterOrigin(str(spec.get("origin") or "SOURCE_WORK"))
            profile = catalog.create_character(
                name,
                origin=origin,
                source_label=source_label,
                project_key=spec.get("project_key"),
                design_documents=spec.get("design_documents") or [],
                summary="Calibration roster profile; visual grounding still requires reviewed Vault evidence.",
                notes=str(spec.get("notes") or ""),
            )
            created += 1
            print(f"CREATED   {name:12} {profile.id}")

        session.flush()

    print(
        f"\nRoster {args.group}: {len(wanted)} target(s), {created} created, "
        f"{conflicts} unresolved ambiguity group(s)."
    )
    if not args.apply:
        print("Dry run only; pass --apply to create missing profile shells.")
    print("No visual reference was auto-approved by this command.")
    return 1 if conflicts else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
