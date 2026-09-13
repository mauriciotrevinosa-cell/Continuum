"""Invariant - the schema keeps canon, catalog, project state and generated work apart.

ADR-0003 section 2: foreign keys point only downward, D (generated) -> C
(project) -> B (interpretation/catalog) -> A (observed). A higher-tier table
may reference a lower one; never the reverse. Operational tables (jobs,
workers) may be referenced by domain tables but reference none of them.

Also asserts the Phase 1 separations as structure, not convention:

* character identity, outfits and visual modes are distinct tables;
* nothing links a character to a visual mode ("character X implies style Y"
  is not representable);
* an outfit cannot exist without its character.

No database is needed; the ORM metadata is the schema definition.
"""

from __future__ import annotations

from continuum_db.models import Base
from continuum_db.tiers import TABLE_REGISTRY, Tier


def _foreign_keys() -> list[tuple[str, str, str]]:
    edges = []
    for table in Base.metadata.tables.values():
        for fk in table.foreign_keys:
            edges.append((table.name, fk.parent.name, fk.column.table.name))
    return edges


def test_every_table_is_declared_with_a_tier() -> None:
    assert set(Base.metadata.tables) == set(TABLE_REGISTRY)


def test_foreign_keys_point_only_downward() -> None:
    violations = []
    for source, column, target in _foreign_keys():
        source_tier = TABLE_REGISTRY[source][1]
        target_tier = TABLE_REGISTRY[target][1]
        if source_tier is Tier.OPERATIONAL and target_tier is not Tier.OPERATIONAL:
            violations.append(f"{source}.{column} -> {target} (operational -> domain)")
        elif target_tier > source_tier:
            violations.append(
                f"{source}.{column} -> {target} ({source_tier.name} -> {target_tier.name})"
            )
    assert violations == [], violations


def test_character_identity_outfit_and_visual_mode_are_separate() -> None:
    tables = Base.metadata.tables
    for name in ("character_profile", "character_outfit", "visual_mode"):
        assert name in tables
    character_columns = set(tables["character_profile"].columns.keys())
    assert not {"outfit", "outfit_id", "visual_mode_id", "style"} & character_columns

    outfit_character = tables["character_outfit"].columns["character_id"]
    assert not outfit_character.nullable, "an outfit belongs to a character"
    assert {fk.column.table.name for fk in outfit_character.foreign_keys} == {"character_profile"}


def test_nothing_links_a_character_to_a_visual_mode() -> None:
    for table in Base.metadata.tables.values():
        targets = {fk.column.table.name for fk in table.foreign_keys}
        assert not {"character_profile", "visual_mode"} <= targets, (
            f"{table.name} links characters to visual modes; style is contextual, "
            "never implied by who is in the frame"
        )
    technique = Base.metadata.tables["reference_technique"]
    assert "character_id" not in technique.columns


def test_source_vault_paths_are_observations_not_identity() -> None:
    """No table keys anything on a path; only the location table holds one."""
    for table in Base.metadata.tables.values():
        path_columns = [c for c in table.columns if "path" in c.name]
        if table.name == "library_asset_location":
            assert [c.name for c in path_columns] == ["relative_path"]
            continue
        assert path_columns == [], f"{table.name} stores a path: {path_columns}"
    unique = [
        set(constraint.columns.keys())
        for constraint in Base.metadata.tables["library_asset"].constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    ] + [
        {c.name}
        for c in Base.metadata.tables["library_asset"].columns
        if c.unique and c.name != "id"
    ]
    assert {"content_hash"} in unique, "an asset is identified by its content hash"
