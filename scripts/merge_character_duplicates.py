"""Merge duplicate character profiles by moving every FK to one canonical profile.

Dry-run is the default. The planner is schema-driven: every current or future
foreign key to ``character_profile.id`` is included automatically. Before any
apply, the exact updates are executed inside a nested transaction and rolled
back, so PostgreSQL itself validates unique/check/FK constraints.

Examples::

    uv run --no-sync python scripts/merge_character_duplicates.py \
        --target <canonical-uuid> --source <duplicate-uuid>

    uv run --no-sync python scripts/merge_character_duplicates.py \
        --target <canonical-uuid> --source <duplicate-uuid> --apply
"""

from __future__ import annotations

import argparse
import sys
import uuid
from dataclasses import dataclass
from typing import Any

from continuum_config import get_settings
from continuum_db.models import CharacterProfile
from continuum_db.session import session_scope
from continuum_library import CatalogInputError, CatalogNotFoundError, ReferenceCatalog
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session


@dataclass(frozen=True, slots=True)
class Move:
    table: Any
    column: Any
    source_id: uuid.UUID
    count: int

    @property
    def key(self) -> str:
        return f"{self.table.name}.{self.column.name}"


def _character_fk_columns() -> list[tuple[Any, Any]]:
    """Every schema column that references ``character_profile.id``."""
    found: list[tuple[Any, Any]] = []
    for table in CharacterProfile.metadata.tables.values():
        if table is CharacterProfile.__table__:
            continue
        for column in table.c:
            if any(fk.target_fullname == "character_profile.id" for fk in column.foreign_keys):
                found.append((table, column))
    return sorted(found, key=lambda pair: (pair[0].name, pair[1].name))


def _validate_profiles(
    session: Session, target_id: uuid.UUID, source_ids: list[uuid.UUID]
) -> tuple[CharacterProfile, list[CharacterProfile]]:
    if not source_ids:
        raise CatalogInputError("At least one --source profile is required.")
    if target_id in source_ids:
        raise CatalogInputError("The target profile cannot also be a source profile.")
    if len(set(source_ids)) != len(source_ids):
        raise CatalogInputError("A source profile was supplied more than once.")

    target = session.get(CharacterProfile, target_id)
    if target is None or target.removed_at is not None:
        raise CatalogNotFoundError("The target character profile is not active.")

    sources: list[CharacterProfile] = []
    for source_id in source_ids:
        source = session.get(CharacterProfile, source_id)
        if source is None or source.removed_at is not None:
            raise CatalogNotFoundError(f"Source character profile {source_id} is not active.")
        if source.display_name.casefold() != target.display_name.casefold():
            raise CatalogInputError(
                f"Refusing to merge {source.display_name!r} into {target.display_name!r}: "
                "display names differ."
            )
        sources.append(source)
    return target, sources


def _merge_plan(session: Session, target_id: uuid.UUID, source_ids: list[uuid.UUID]) -> list[Move]:
    """Count every FK row that would move from each source to the target."""
    moves: list[Move] = []
    for table, column in _character_fk_columns():
        for source_id in source_ids:
            count = session.execute(
                select(func.count()).select_from(table).where(column == source_id)
            ).scalar_one()
            if count:
                moves.append(Move(table, column, source_id, int(count)))
    return moves


def _move_links(session: Session, target_id: uuid.UUID, moves: list[Move]) -> None:
    for move in moves:
        session.execute(
            update(move.table)
            .where(move.column == move.source_id)
            .values({move.column.name: target_id})
        )


def _constraint_probe(
    session: Session, target_id: uuid.UUID, moves: list[Move]
) -> dict[str, str] | None:
    """Ask PostgreSQL whether the complete merge satisfies every constraint.

    The updates run inside a savepoint and are always rolled back. This catches
    ordinary UNIQUE constraints as well as partial unique indexes and future
    schema rules without trying to reimplement PostgreSQL constraint semantics.
    """
    nested = session.begin_nested()
    try:
        _move_links(session, target_id, moves)
        session.flush()
    except IntegrityError as exc:
        nested.rollback()
        session.expire_all()
        orig = exc.orig
        diag = getattr(orig, "diag", None)
        return {
            "table": str(getattr(diag, "table_name", "") or "unknown"),
            "constraint": str(getattr(diag, "constraint_name", "") or "unknown"),
            "detail": str(orig).splitlines()[0][:500],
        }
    else:
        nested.rollback()
        session.expire_all()
        return None


def _apply_merge(
    session: Session,
    target_id: uuid.UUID,
    sources: list[CharacterProfile],
    moves: list[Move],
) -> None:
    """Move links, verify the sources are unreferenced, then soft-retire them."""
    _move_links(session, target_id, moves)
    session.flush()

    remaining: dict[uuid.UUID, list[str]] = {}
    for source in sources:
        links: list[str] = []
        for table, column in _character_fk_columns():
            count = session.execute(
                select(func.count()).select_from(table).where(column == source.id)
            ).scalar_one()
            if count:
                links.append(f"{table.name}.{column.name}={count}")
        if links:
            remaining[source.id] = links
    if remaining:
        detail = "; ".join(
            f"{source_id}: {', '.join(links)}" for source_id, links in remaining.items()
        )
        raise RuntimeError(f"Merge left linked source profiles: {detail}")

    catalog = ReferenceCatalog(session)
    for source in sources:
        catalog.remove_character(source.id, source.row_version)
    session.flush()


def _uuid(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"not a UUID: {value}") from exc


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--target", required=True, type=_uuid)
    parser.add_argument("--source", action="append", required=True, type=_uuid)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)

    settings = get_settings()
    with session_scope(settings) as session:
        try:
            target, sources = _validate_profiles(session, args.target, args.source)
        except (CatalogInputError, CatalogNotFoundError) as exc:
            print(f"ERROR: {exc}")
            return 1

        print(
            f"TARGET {target.display_name}: {target.id} "
            f"source={target.source_label!r} project={target.project_key!r}"
        )
        for source in sources:
            print(
                f"SOURCE {source.display_name}: {source.id} "
                f"source={source.source_label!r} project={source.project_key!r}"
            )

        moves = _merge_plan(session, target.id, [source.id for source in sources])
        if moves:
            print("\nPlanned FK moves:")
            for move in moves:
                print(f"  MOVE {move.count:>4}  {move.key}  from {move.source_id}")
        else:
            print("\nNo linked rows; only the source profile(s) would be soft-retired.")

        conflict = _constraint_probe(session, target.id, moves)
        if conflict is not None:
            print(
                "\nBLOCK: PostgreSQL rejected the simulated merge: "
                f"table={conflict['table']} constraint={conflict['constraint']}"
            )
            print(f"  {conflict['detail']}")
            print("No rows changed.")
            return 1

        print("\nConstraint probe: PASS (simulation rolled back; no rows changed).")
        if not args.apply:
            print("Dry run only; pass --apply to perform exactly this merge.")
            return 2

        _apply_merge(session, target.id, sources, moves)
        print(f"Applied merge into {target.id}; soft-retired {len(sources)} source profile(s).")
        return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
