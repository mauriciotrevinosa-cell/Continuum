"""Import a character reference pack (a ZIP of images plus a pack spec) into the Reference Vault.

    uv run python scripts/import_character_pack.py \
        --pack path/to/pack.zip --spec spec.json [--apply]

Dry-run by default: prints what would be imported. ``--apply`` writes.

The spec is local data, never committed. It names the character and says what
each folder (or file) of the pack grounds. Rules may override class, origin and
uses so a small pack can mix authoritative grounding with supplemental fanart
without fanart silently becoming identity canon::

    {
      "character": {"display_name": "...", "origin": "SOURCE_WORK",
                    "source_label": "...", "subject_kind": "CHARACTER"},
      "reference_class": "CANON",
      "reference_origin": "SOURCE",
      "rights_status": "OWNED",
      "folders": {
        "lite_grounding/": {
          "aspects": ["FACE", "HAIR", "FULL_BODY"],
          "uses": ["IDENTITY"],
          "preferred": true,
          "notes": "One of the small authoritative grounding set."
        },
        "fanart_variants/": {
          "aspects": ["FULL_BODY", "POSE"],
          "reference_class": "MOOD",
          "reference_origin": "FAN_ART",
          "uses": ["STYLE"],
          "training_eligibility": "EXCLUDED",
          "notes": "Supplemental angle/look inspiration only; never identity grounding."
        }
      },
      "files": {
        "lite_grounding/a.jpeg": {"aspects": ["FACE", "HAIR", "FULL_BODY"]}
      }
    }

Re-running is safe: an image already linked to the character (same bytes) is skipped.
Every reference records the pack's SHA-256 and the member path it came from.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from pathlib import Path
from typing import Any

from continuum_config import get_settings
from continuum_core.catalog import RightsStatus, TrainingEligibility
from continuum_core.references import (
    CharacterAspect,
    CharacterOrigin,
    ProjectStanding,
    ReferenceClass,
    ReferenceOrigin,
    ReferenceUse,
    SubjectKind,
)
from continuum_db.models import CharacterProfile, LibraryAsset, ReferenceCharacter, ReferenceItem
from continuum_db.session import session_scope
from continuum_library import CharacterLink, ReferenceCatalog, ReferenceSpec, StandingSpec
from continuum_storage import build_storage
from sqlalchemy import select

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}


def _rule(spec: dict[str, Any], member: str) -> dict[str, Any] | None:
    rule: dict[str, Any] | None = None
    for folder, folder_rule in (spec.get("folders") or {}).items():
        if member.startswith(folder) or f"/{folder}" in f"/{member}":
            rule = dict(folder_rule)
    for name, file_rule in (spec.get("files") or {}).items():
        if member.endswith(name):
            rule = {**(rule or {}), **file_rule}
    return rule


def _setting(rule: dict[str, Any], spec: dict[str, Any], key: str, default: Any) -> Any:
    """A per-file/folder choice overrides the pack-level default."""
    return rule[key] if key in rule else spec.get(key, default)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--pack", required=True)
    parser.add_argument("--spec", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)

    pack = Path(args.pack)
    spec = json.loads(Path(args.spec).read_text(encoding="utf-8"))
    pack_sha = hashlib.sha256(pack.read_bytes()).hexdigest()
    with zipfile.ZipFile(pack) as archive:
        members = [
            info
            for info in archive.infolist()
            if not info.is_dir() and Path(info.filename).suffix.lower() in IMAGE_SUFFIXES
        ]
        plan = [(info, _rule(spec, info.filename)) for info in members]
        for info, rule in plan:
            if not rule:
                summary = "SKIP (no rule)"
            else:
                aspects = ",".join(rule.get("aspects") or []) or "no aspects"
                origin = _setting(rule, spec, "reference_origin", "USER_CREATED")
                reference_class = _setting(rule, spec, "reference_class", "CANON")
                uses = ",".join(_setting(rule, spec, "uses", [])) or "no uses"
                summary = f"{reference_class}/{origin} {aspects} [{uses}]"
            print(f"{summary:64} {info.filename}")
        if not args.apply:
            print(f"\n{len(plan)} image(s); dry run - pass --apply to import.")
            return 0

        settings = get_settings()
        storage = build_storage(settings)
        with session_scope(settings) as session:
            catalog = ReferenceCatalog(session, sources=None, derived=storage.derived)
            wanted = spec["character"]
            character = session.execute(
                select(CharacterProfile).where(
                    CharacterProfile.display_name == wanted["display_name"],
                    CharacterProfile.removed_at.is_(None),
                )
            ).scalar_one_or_none()
            if character is None:
                character = catalog.create_character(
                    wanted["display_name"],
                    subject_kind=SubjectKind(wanted.get("subject_kind", "CHARACTER")),
                    origin=CharacterOrigin(wanted.get("origin", "SOURCE_WORK")),
                    source_label=wanted.get("source_label", ""),
                    project_key=wanted.get("project_key"),
                    design_documents=wanted.get("design_documents", []),
                    summary=wanted.get("summary", ""),
                    notes=wanted.get("notes", ""),
                )
                print(f"created character {character.display_name} ({character.id})")
            imported = skipped = 0
            for info, rule in plan:
                if not rule:
                    continue
                data = archive.read(info)
                digest = hashlib.sha256(data).hexdigest()
                existing = session.execute(
                    select(ReferenceItem.id)
                    .join(LibraryAsset, LibraryAsset.id == ReferenceItem.asset_id)
                    .join(ReferenceCharacter, ReferenceCharacter.reference_id == ReferenceItem.id)
                    .where(
                        ReferenceCharacter.character_id == character.id,
                        ReferenceItem.removed_at.is_(None),
                        ReferenceItem.provenance["member_sha256"].astext == digest,
                    )
                ).first()
                if existing is not None:
                    skipped += 1
                    continue
                standing = rule.get("standing")
                origin = ReferenceOrigin(
                    _setting(rule, spec, "reference_origin", "USER_CREATED")
                )
                reference_class = ReferenceClass(
                    _setting(rule, spec, "reference_class", "CANON")
                )
                uses = tuple(
                    ReferenceUse(use) for use in _setting(rule, spec, "uses", [])
                )
                item = catalog.add_upload(
                    data,
                    ReferenceSpec(
                        reference_class=reference_class,
                        origin=origin,
                        label=rule.get("label")
                        or f"{wanted['display_name']} - {Path(info.filename).name}",
                        notes=rule.get("notes", ""),
                        favorite=bool(_setting(rule, spec, "favorite", False)),
                        uses=uses,
                        characters=tuple(
                            CharacterLink(
                                character.id,
                                CharacterAspect(aspect),
                                preferred=bool(rule.get("preferred")) and index == 0,
                                notes=rule.get("notes", ""),
                            )
                            for index, aspect in enumerate(rule.get("aspects") or [])
                        ),
                        standings=(
                            (StandingSpec(wanted["project_key"], ProjectStanding(standing)),)
                            if standing and wanted.get("project_key")
                            else ()
                        ),
                        extra_provenance={
                            "pack": pack.name,
                            "pack_sha256": pack_sha,
                            "member": info.filename,
                            "member_sha256": digest,
                        },
                    ),
                )
                item.rights_status = RightsStatus(
                    rule.get("rights_status", spec.get("rights_status", "UNKNOWN"))
                )
                item.training_eligibility = TrainingEligibility(
                    rule.get(
                        "training_eligibility", spec.get("training_eligibility", "MANUAL_REVIEW")
                    )
                )
                imported += 1
            session.flush()
            print(f"imported {imported}, already present {skipped}; character {character.id}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
