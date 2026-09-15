"""The character reference corpus: evidence for a character, retrieved per page.

A character is not one picture. This module keeps, per character, every
observation Continuum can use - and says for each one what it teaches and how
much it may define the character:

* **curated** references a person linked to the character are confirmed
  observations; their authority follows their origin (the source manga is
  primary for a franchise character, the creator's photos for an original one;
  a reference marked STYLE is stylization, never identity);
* **source pages**: the catalogued chapters of the character's source manga are
  swept for pages where the character very likely appears (from the chapter of
  their first curated appearance onward). They are CANDIDATES - found, not
  confirmed - and never ground production or count toward readiness until a
  person confirms them and says what they show;
* **fan art** whose own labels name the character is a supplemental candidate:
  angles and ideas, never identity;
* **approved project pages** become project-created observations.

Retrieval builds a request from what a page needs (framing, angle, expression,
pose, who else is present) and returns a small, diverse, authority-ranked
subset. Readiness and invariants count only confirmed, high-authority,
non-atypical observations: consensus by independent support, not by one image.

Nothing here reads pixels to recognise a character; automatic layout hints are
labelled as hints. Reading only; the Vault is never written.
"""

from __future__ import annotations

import datetime as dt
import re
import uuid
from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from typing import Any

from continuum_core.catalog import UnitKind
from continuum_core.corpus import (
    AUTHORITY_RANK,
    HIGH_AUTHORITY,
    Framing,
    ObservationAuthority,
    ObservationFacet,
    ObservationRole,
    ObservationSource,
    ObservationStatus,
    ViewAngle,
)
from continuum_core.references import (
    CharacterAspect,
    CharacterOrigin,
    DescriptorFacet,
    ReferenceClass,
    ReferenceOrigin,
    ReferenceUse,
)
from continuum_db.models import (
    CatalogEntry,
    CatalogUnit,
    CharacterObservation,
    CharacterProfile,
    LibraryAssetLocation,
    ReferenceCharacter,
    ReferenceDescriptor,
    ReferenceItem,
    ReferenceUseLink,
)
from continuum_imaging import EncodedImage, preview
from continuum_library import (
    CatalogInputError,
    CatalogNotFoundError,
    DescriptorSpec,
    ReferenceCatalog,
    ReferenceSpec,
)
from sqlalchemy import func, select
from sqlalchemy.orm import Session

__all__ = [
    "ASPECT_FACETS",
    "READINESS_GROUPS",
    "SETTING_TAGS",
    "CharacterCorpus",
    "PageReader",
    "observation_view",
    "page_needs",
    "setting_tags",
]

PageReader = Callable[[CatalogUnit, CatalogEntry, int], tuple[str, bytes] | None]

F = ObservationFacet
ASPECT_FACETS: dict[CharacterAspect, tuple[ObservationFacet, ...]] = {
    CharacterAspect.FACE: (F.FACE,),
    CharacterAspect.HAIR: (F.HAIR,),
    CharacterAspect.DISTINGUISHING_MARK: (F.FACE,),
    CharacterAspect.FULL_BODY: (F.BODY,),
    CharacterAspect.PROPORTIONS: (F.BODY,),
    CharacterAspect.SCALE: (F.SCALE, F.BODY),
    CharacterAspect.POSTURE: (F.POSE, F.BODY),
    CharacterAspect.OUTFIT: (F.WARDROBE,),
    CharacterAspect.ACCESSORY: (F.ACCESSORY,),
    CharacterAspect.EXPRESSION: (F.EXPRESSION,),
    CharacterAspect.QUIET_ACTING: (F.EXPRESSION, F.POSE),
    CharacterAspect.COMEDIC_EXPRESSION: (F.EXPRESSION,),
    CharacterAspect.GESTURE: (F.POSE,),
    CharacterAspect.POSE: (F.POSE,),
    CharacterAspect.ACTION_POSE: (F.POSE,),
}
#: What the overview reports readiness for, and the facets that count.
READINESS_GROUPS: dict[str, frozenset[ObservationFacet]] = {
    "identity": frozenset({F.FACE, F.HAIR}),
    "face": frozenset({F.FACE}),
    "body": frozenset({F.BODY, F.SCALE}),
    "wardrobe": frozenset({F.WARDROBE}),
    "expression": frozenset({F.EXPRESSION}),
    "pose": frozenset({F.POSE}),
    "accessory": frozenset({F.ACCESSORY}),
}
#: Angles a recurring character's face and body should eventually be seen from.
WANTED_ANGLES = (
    ViewAngle.FRONT,
    ViewAngle.THREE_QUARTER_LEFT,
    ViewAngle.THREE_QUARTER_RIGHT,
    ViewAngle.PROFILE,
    ViewAngle.BACK,
)
READY_MIN_OBSERVATIONS = 3
READY_MIN_SOURCES = 2

_ANGLE_WORDS: tuple[tuple[str, ViewAngle], ...] = (
    (r"\bprofile\b|\bside view\b|\bin profile\b", ViewAngle.PROFILE),
    (r"\b3/4\b|three[- ]quarter", ViewAngle.THREE_QUARTER_LEFT),
    (r"from behind|back shot|back view|\bback of\b|seen from the back", ViewAngle.BACK),
    (r"looking up|looks up|gazes up", ViewAngle.LOOKING_UP),
    (r"looking down|looks down|gazes down", ViewAngle.LOOKING_DOWN),
    (r"\bfront view\b|\bfacing (?:us|the reader|camera)\b|\bfrontal\b", ViewAngle.FRONT),
)
_EXPRESSION_WORDS: tuple[tuple[str, str], ...] = (
    (r"\bsmil", "smile"),
    (r"\bsad|\btear|\bgrief|\bmelanchol", "sad"),
    (r"\bangr|\bannoy|\birritat", "annoyed"),
    (r"\bsurpris|\bshock|\bstartl", "surprise"),
    (r"\bconfus|\bdisorient|\bpuzzl|\bbewilder", "confused"),
    (r"\btired|\bsleep|\bexhaust|\bdrows", "tired"),
    (r"\bneutral|\bblank|\bdeadpan|\bcalm|\bexpressionless", "neutral"),
    (r"\bwarm|\bgentle|\bsoft", "warm"),
    (r"\bconcentrat|\bfocus", "concentration"),
    (r"\bembarrass|\bblush", "embarrassed"),
    (r"\balarm|\bfear|\bafraid|\bpanic", "alarm"),
)
_POSE_WORDS: tuple[tuple[str, str], ...] = (
    (r"\bsit|\bseated", "sitting"),
    (r"\bstand", "standing"),
    (r"\bwalk", "walking"),
    (r"\brun", "running"),
    (r"\bkneel", "kneeling"),
    (r"\blying\b|\blies\b|\bunconscious|\basleep", "lying"),
    (r"\beat", "eating"),
    (r"\bcombat|\bfight|\bstance|\bcast", "action"),
)


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def _tokens(text: str) -> list[str]:
    return [t for t in re.split(r"[^a-z0-9]+", text.lower()) if t]


def _first(patterns: Iterable[tuple[str, Any]], text: str) -> list[Any]:
    return [value for pattern, value in patterns if re.search(pattern, text, re.I)]


def page_needs(page: dict[str, Any], name: str) -> dict[str, Any]:
    """What a page needs to see of one character, read from its script."""
    intents = set(page.get("intents") or [])
    first = name.split()[0].lower()
    lines = [str(line) for line in page.get("directions") or []]
    own = [line for line in lines if first in line.lower()] or lines
    text = " ".join(own)
    facets: list[ObservationFacet] = []
    framing: Framing | None = None
    if intents & {"close_up", "quiet_acting", "confused_reaction", "awakening"}:
        facets += [F.FACE, F.EXPRESSION]
        framing = Framing.CLOSE_UP if "close_up" in intents else None
    if intents & {"large_composition", "back_shot", "chapter_end"}:
        facets += [F.BODY, F.WARDROBE]
        framing = framing or Framing.FULL_BODY
    if intents & {"conversation", "two_character"}:
        facets += [F.FACE, F.BODY]
        framing = framing or Framing.UPPER_BODY
    if "two_character" in intents:
        facets.append(F.SCALE)
    if not facets:
        facets = [F.FACE, F.BODY]
    angles = _first(_ANGLE_WORDS, text)
    if "back_shot" in intents and ViewAngle.BACK not in angles:
        angles.append(ViewAngle.BACK)
    expressions = _first(_EXPRESSION_WORDS, text)
    if "confused_reaction" in intents and "confused" not in expressions:
        expressions.append("confused")
    return {
        "facets": [f.value for f in dict.fromkeys(facets)],
        "framing": framing.value if framing else None,
        "angles": [a.value for a in dict.fromkeys(angles)],
        "expressions": list(dict.fromkeys(expressions)),
        "poses": list(dict.fromkeys(_first(_POSE_WORDS, text))),
        "with": [c for c in page.get("characters") or [] if c != name],
    }


#: Setting tags an environment reference can carry, and the words that call for them.
SETTING_TAGS: dict[str, str] = {
    "forest": r"\bforest|\bwoods?\b|\btrees\b",
    "flower field": r"\bflower|\bmeadow|\bblossom|\bpetal",
    "abandoned village": r"abandoned village|\bruined village|\bdeserted village",
    "village": r"\bvillage|\bhamlet|\btown\b",
    "inn": r"\binn\b|\btavern",
    "lake": r"\blake\b|\bpond\b|\briver",
    "trail": r"\btrail|\bpath\b|\broad\b",
    "ruined house": r"\bruin",
    "warm interior": r"\binterior|\bindoors|\bhearth|\bfireplace",
    "night": r"\bnight|\bmoon|\bstars\b|\bdark\b",
    "sunset": r"\bsunset|\bdusk|\bevening",
    "camp": r"\bcamp|\bcampfire|\bbonfire",
}


def setting_tags(text: str) -> list[str]:
    """The setting tags a page's own script calls for."""
    return [tag for tag, pattern in SETTING_TAGS.items() if re.search(pattern, text, re.I)]


def observation_view(row: CharacterObservation, **extra: Any) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "character_id": str(row.character_id),
        "locator": row.locator,
        "source_kind": row.source_kind,
        "reference_id": str(row.reference_id) if row.reference_id else None,
        "unit_key": row.unit_key,
        "page_offset": row.page_offset,
        "series_key": row.series_key,
        "source_label": row.source_label,
        "authority": row.authority,
        "status": row.status,
        "role": row.role,
        "anchor": row.anchor,
        "atypical": row.atypical,
        "facets": list(row.facets or []),
        "angle": row.angle,
        "framing": row.framing,
        "expression": row.expression,
        "pose": row.pose,
        "evidence": row.evidence or {},
        "notes": row.notes,
        "reviewed": row.reviewed_at is not None,
        "image": f"/library/character-observations/{row.id}/image",
        **extra,
    }


class CharacterCorpus:
    """Observations of characters: sync, mine, retrieve, review, report."""

    def __init__(
        self,
        session: Session,
        catalog: ReferenceCatalog,
        *,
        page_reader: PageReader | None = None,
        analyze: Callable[[bytes], Any] | None = None,
    ) -> None:
        self.session = session
        self.catalog = catalog
        self.page_reader = page_reader
        self.analyze = analyze

    # -- basics ---------------------------------------------------------------
    def character(self, character_id: uuid.UUID) -> CharacterProfile:
        character = self.session.get(CharacterProfile, character_id)
        if character is None or character.removed_at is not None:
            raise CatalogNotFoundError("That character does not exist.")
        return character

    def by_name(self, name: str) -> CharacterProfile | None:
        return self.session.execute(
            select(CharacterProfile).where(
                CharacterProfile.display_name == name, CharacterProfile.removed_at.is_(None)
            )
        ).scalar_one_or_none()

    def observation(self, observation_id: uuid.UUID) -> CharacterObservation:
        row = self.session.get(CharacterObservation, observation_id)
        if row is None:
            raise CatalogNotFoundError("That observation does not exist.")
        return row

    def observations(
        self, character_id: uuid.UUID, *, include_rejected: bool = True
    ) -> list[CharacterObservation]:
        query = select(CharacterObservation).where(
            CharacterObservation.character_id == character_id
        )
        if not include_rejected:
            query = query.where(CharacterObservation.status != ObservationStatus.REJECTED.value)
        return list(self.session.execute(query.order_by(CharacterObservation.created_at)).scalars())

    def _existing(self, character_id: uuid.UUID) -> dict[str, CharacterObservation]:
        return {row.locator: row for row in self.observations(character_id)}

    # -- curated references -----------------------------------------------------
    def sync_curated(self, character_id: uuid.UUID) -> int:
        """Mirror the references linked to the character. Cheap; idempotent."""
        character = self.character(character_id)
        original = character.origin is CharacterOrigin.PROJECT_ORIGINAL
        rows = self.session.execute(
            select(ReferenceCharacter, ReferenceItem)
            .join(ReferenceItem, ReferenceItem.id == ReferenceCharacter.reference_id)
            .where(ReferenceCharacter.character_id == character_id)
        ).all()
        grouped: dict[uuid.UUID, tuple[ReferenceItem, list[ReferenceCharacter]]] = {}
        for link, item in rows:
            grouped.setdefault(item.id, (item, []))[1].append(link)
        ids = list(grouped) or [uuid.uuid4()]
        styled = set(
            self.session.execute(
                select(ReferenceUseLink.reference_id).where(
                    ReferenceUseLink.reference_id.in_(ids),
                    ReferenceUseLink.use == ReferenceUse.STYLE,
                )
            ).scalars()
        )
        descriptors: dict[uuid.UUID, list[ReferenceDescriptor]] = {}
        for descriptor in self.session.execute(
            select(ReferenceDescriptor).where(ReferenceDescriptor.reference_id.in_(ids))
        ).scalars():
            descriptors.setdefault(descriptor.reference_id, []).append(descriptor)
        existing = self._existing(character_id)
        changed = 0
        for reference_id, (item, links) in grouped.items():
            if item.removed_at is not None and f"ref:{reference_id}" not in existing:
                continue  # a reference removed before it was ever observed adds nothing
            authority, role = self._authority_of(item, original, reference_id in styled)
            facets = sorted({f.value for link in links for f in ASPECT_FACETS[link.aspect]})
            framing = expression = None
            for descriptor in descriptors.get(reference_id, []):
                value = descriptor.value.lower()
                if descriptor.facet in (DescriptorFacet.SHOT_TYPE,) or "close" in value:
                    framing = Framing.CLOSE_UP.value if "close" in value else framing
                if descriptor.facet in (DescriptorFacet.EXPRESSION, DescriptorFacet.MOOD):
                    expression = value[:80]
            status = (
                ObservationStatus.REJECTED.value
                if item.removed_at is not None
                else ObservationStatus.CONFIRMED.value
            )
            anchor = (
                status == ObservationStatus.CONFIRMED.value
                and role == ObservationRole.GROUNDING.value
                and any(link.preferred for link in links)
            )
            locator = f"ref:{reference_id}"
            row = existing.get(locator)
            fields: dict[str, Any] = {
                "source_kind": (
                    ObservationSource.FAN_ART.value
                    if item.origin is ReferenceOrigin.FAN_ART
                    else ObservationSource.CURATED.value
                ),
                "reference_id": reference_id,
                "source_label": item.label[:300],
                "evidence": {
                    "discovered_by": "curated link",
                    "aspects": sorted({link.aspect.value for link in links}),
                    "origin": item.origin.value,
                    "reference_class": item.reference_class.value,
                },
            }
            automatic = {
                "authority": authority,
                "role": role,
                "status": status,
                "facets": facets,
                "anchor": anchor,
                "framing": framing,
                "expression": expression or "",
            }
            if row is None:
                self.session.add(
                    CharacterObservation(
                        character_id=character_id, locator=locator, **fields, **automatic
                    )
                )
                changed += 1
                continue
            updates = {**fields, **(automatic if row.reviewed_at is None else {})}
            if item.removed_at is not None:
                updates["status"] = ObservationStatus.REJECTED.value
                updates["anchor"] = False
            for key, value in updates.items():
                if getattr(row, key) != value:
                    setattr(row, key, value)
                    changed += 1
            if changed:
                row.updated_at = _now()
        self.session.flush()
        return changed

    @staticmethod
    def _authority_of(item: ReferenceItem, original: bool, styled: bool) -> tuple[str, str]:
        authority, role = ObservationAuthority, ObservationRole
        if styled:
            return authority.PROJECT_CREATED.value, role.STYLIZATION.value
        # Who made the image (judged by a person) outranks where it was acquired.
        visual = item.visual_origin
        if visual and not original:
            if visual == "PRIMARY_MANGA":
                return authority.PRIMARY_SOURCE.value, role.GROUNDING.value
            if visual in ("OFFICIAL_ANIME", "OFFICIAL_ART"):
                return authority.OFFICIAL.value, role.GROUNDING.value
            if visual == "PROJECT_CREATED":
                return authority.PROJECT_CREATED.value, role.EVIDENCE.value
            return authority.SUPPLEMENTAL.value, role.EVIDENCE.value
        if item.reference_class is ReferenceClass.UNSORTED:
            return authority.UNSORTED.value, role.EVIDENCE.value
        origin = item.origin
        project_made = origin in (ReferenceOrigin.GENERATED, ReferenceOrigin.PROJECT_APPROVED)
        if origin is ReferenceOrigin.FAN_ART:
            return authority.SUPPLEMENTAL.value, role.EVIDENCE.value
        if original:
            if origin is ReferenceOrigin.USER_CREATED:
                return authority.CREATOR_PRIMARY.value, role.GROUNDING.value
            if project_made:
                return authority.PROJECT_CREATED.value, role.EVIDENCE.value
            # Franchise material never defines an original character.
            return authority.SUPPLEMENTAL.value, role.EVIDENCE.value
        if origin is ReferenceOrigin.SOURCE:
            return authority.PRIMARY_SOURCE.value, role.GROUNDING.value
        if origin is ReferenceOrigin.OFFICIAL_ART:
            return authority.OFFICIAL.value, role.GROUNDING.value
        if project_made:
            return authority.PROJECT_CREATED.value, role.EVIDENCE.value
        return authority.SUPPLEMENTAL.value, role.EVIDENCE.value

    # -- mining -----------------------------------------------------------------
    def refresh(
        self,
        character_id: uuid.UUID,
        *,
        per_chapter: int = 2,
        max_source_pages: int = 600,
        analyze_limit: int = 0,
    ) -> dict[str, Any]:
        """Sync curated references and sweep the catalog for candidate observations."""
        character = self.character(character_id)
        summary: dict[str, Any] = {"curated_changes": self.sync_curated(character_id)}
        if character.origin is CharacterOrigin.PROJECT_ORIGINAL:
            summary.update(source_pages_added=0, fan_art_added=0, series=[])
            summary["note"] = (
                "an original character is grounded by the creator, not by franchise material"
            )
            self.session.flush()
            return summary
        existing = self._existing(character_id)
        series, first = self._source_series(character)
        added = 0
        for series_key in series:
            query = (
                select(CatalogUnit, CatalogEntry)
                .join(CatalogEntry, CatalogEntry.id == CatalogUnit.entry_id)
                .where(
                    CatalogUnit.series_key == series_key,
                    CatalogUnit.kind == UnitKind.MANGA_CHAPTER,
                    CatalogEntry.duplicate_of_id.is_(None),
                )
                .order_by(CatalogUnit.sort_key)
            )
            for unit, _entry in self.session.execute(query).all():
                if first.get(series_key) and unit.sort_key < first[series_key]:
                    continue
                count = unit.page_count or 0
                if count < 3:
                    continue
                offsets = sorted(
                    {
                        min(count - 1, max(1, round(count * k / (per_chapter + 1))))
                        for k in range(1, per_chapter + 1)
                    }
                )
                for offset in offsets:
                    if added >= max_source_pages:
                        break
                    locator = f"unit:{unit.unit_key}:{offset}"
                    if locator in existing:
                        continue
                    row = CharacterObservation(
                        character_id=character_id,
                        locator=locator,
                        source_kind=ObservationSource.SOURCE_PAGE.value,
                        unit_key=unit.unit_key,
                        page_offset=offset,
                        series_key=series_key,
                        source_label=f"{unit.label} p{offset + 1}"[:300],
                        authority=ObservationAuthority.PRIMARY_SOURCE.value,
                        status=ObservationStatus.CANDIDATE.value,
                        role=ObservationRole.GROUNDING.value,
                        anchor=False,
                        facets=[],
                        evidence={
                            "discovered_by": "source series sweep",
                            "appearance": (
                                "from the chapter of the first curated appearance onward"
                                if first.get(series_key)
                                else "the source series named by the character profile"
                            ),
                            "verified": False,
                        },
                    )
                    self.session.add(row)
                    existing[locator] = row
                    added += 1
        summary["series"] = series
        summary["source_pages_added"] = added
        summary["fan_art_added"] = self._fan_art(character, existing)
        self.session.flush()
        summary["layout_hints"] = self._hints(character_id, analyze_limit) if analyze_limit else 0
        summary["totals"] = self.counts(character_id)
        return summary

    def _source_series(self, character: CharacterProfile) -> tuple[list[str], dict[str, str]]:
        """The character's source series and the sort key of their first curated appearance."""
        first: dict[str, str] = {}
        items = self.session.execute(
            select(ReferenceItem)
            .join(ReferenceCharacter, ReferenceCharacter.reference_id == ReferenceItem.id)
            .where(
                ReferenceCharacter.character_id == character.id,
                ReferenceItem.origin == ReferenceOrigin.SOURCE,
                ReferenceItem.removed_at.is_(None),
            )
        ).scalars()
        for item in items:
            for location in self.session.execute(
                select(LibraryAssetLocation).where(
                    LibraryAssetLocation.asset_id == item.asset_id,
                    LibraryAssetLocation.root_key == "source_vault",
                )
            ).scalars():
                for unit in self.session.execute(
                    select(CatalogUnit)
                    .join(CatalogEntry, CatalogEntry.id == CatalogUnit.entry_id)
                    .where(
                        CatalogEntry.root_key == "source_vault",
                        CatalogEntry.relative_path == location.relative_path,
                        CatalogUnit.kind == UnitKind.MANGA_CHAPTER,
                    )
                ).scalars():
                    start = unit.first_page_index or 0
                    inside = item.unit_index is None or (
                        start <= item.unit_index < start + (unit.page_count or 0)
                    )
                    if inside and unit.series_key:
                        current = first.get(unit.series_key)
                        if current is None or unit.sort_key < current:
                            first[unit.series_key] = unit.sort_key
        series = sorted(first)
        if not series and character.source_label.strip():
            series = sorted(
                {
                    key
                    for key in self.session.execute(
                        select(CatalogUnit.series_key).where(
                            func.lower(CatalogUnit.series_title)
                            == character.source_label.strip().lower(),
                            CatalogUnit.kind == UnitKind.MANGA_CHAPTER,
                        )
                    ).scalars()
                    if key
                }
            )
        return series, first

    def _fan_art(
        self, character: CharacterProfile, existing: dict[str, CharacterObservation]
    ) -> int:
        wanted = _tokens(character.display_name)
        if not wanted:
            return 0
        added = 0
        candidates = self.session.execute(
            select(ReferenceItem).where(
                ReferenceItem.origin == ReferenceOrigin.FAN_ART,
                ReferenceItem.removed_at.is_(None),
                func.lower(ReferenceItem.label + " " + ReferenceItem.notes).contains(wanted[0]),
            )
        ).scalars()
        for item in candidates:
            words = set(_tokens(f"{item.label} {item.notes}"))
            if not all(token in words for token in wanted):
                continue
            locator = f"ref:{item.id}"
            if locator in existing:
                continue
            row = CharacterObservation(
                character_id=character.id,
                locator=locator,
                source_kind=ObservationSource.FAN_ART.value,
                reference_id=item.id,
                source_label=item.label[:300],
                authority=ObservationAuthority.SUPPLEMENTAL.value,
                status=ObservationStatus.CANDIDATE.value,
                role=ObservationRole.EVIDENCE.value,
                anchor=False,
                facets=[],
                evidence={"discovered_by": "fan art label names the character", "verified": False},
            )
            self.session.add(row)
            existing[locator] = row
            added += 1
        return added

    def _hints(self, character_id: uuid.UUID, limit: int) -> int:
        """Automatic framing hints from page layout. Hints, never facts."""
        if self.page_reader is None or self.analyze is None:
            return 0
        done = 0
        for row in self.observations(character_id, include_rejected=False):
            if done >= limit:
                break
            if row.source_kind != ObservationSource.SOURCE_PAGE.value or "layout" in (
                row.evidence or {}
            ):
                continue
            found = self._unit(row)
            if found is None:
                continue
            read = self.page_reader(found[0], found[1], int(row.page_offset or 0))
            if read is None:
                continue
            layout = self.analyze(read[1])
            share = round(float(layout.largest_panel_share), 4)
            hint = "WIDE" if share >= 0.55 else ("CLOSE_UP" if layout.panel_count >= 5 else None)
            row.evidence = {
                **(row.evidence or {}),
                "layout": {"panel_count": int(layout.panel_count), "largest_panel_share": share},
                "framing_hint": hint,
            }
            done += 1
        self.session.flush()
        return done

    def _unit(self, row: CharacterObservation) -> tuple[CatalogUnit, CatalogEntry] | None:
        if row.unit_key is None:
            return None
        found = self.session.execute(
            select(CatalogUnit, CatalogEntry)
            .join(CatalogEntry, CatalogEntry.id == CatalogUnit.entry_id)
            .where(CatalogUnit.unit_key == row.unit_key)
        ).first()
        return (found[0], found[1]) if found else None

    def record_approved_output(
        self,
        character_id: uuid.UUID,
        reference_id: uuid.UUID,
        *,
        facets: Sequence[str],
        evidence: dict[str, Any],
    ) -> CharacterObservation:
        """A creatively approved project page becomes project-created evidence."""
        locator = f"ref:{reference_id}"
        row = self._existing(character_id).get(locator)
        if row is None:
            row = CharacterObservation(
                character_id=character_id,
                locator=locator,
                source_kind=ObservationSource.APPROVED_OUTPUT.value,
                reference_id=reference_id,
                source_label=str(evidence.get("label", ""))[:300],
                authority=ObservationAuthority.PROJECT_CREATED.value,
                status=ObservationStatus.CONFIRMED.value,
                role=ObservationRole.EVIDENCE.value,
                anchor=False,
                facets=sorted(set(facets)),
                evidence={"discovered_by": "approved project page", **evidence},
            )
            self.session.add(row)
            self.session.flush()
        return row

    # -- review -----------------------------------------------------------------
    def review(self, observation_id: uuid.UUID, changes: dict[str, Any]) -> CharacterObservation:
        """A person says what an observation shows. Reviews survive every refresh."""
        row = self.observation(observation_id)
        allowed = {
            "status": ObservationStatus,
            "role": ObservationRole,
            "authority": ObservationAuthority,
            "angle": ViewAngle,
            "framing": Framing,
        }
        for key, value in changes.items():
            if key in allowed:
                if value is None and key in {"angle", "framing"}:
                    setattr(row, key, None)
                    continue
                try:
                    setattr(row, key, allowed[key](value).value)
                except ValueError:
                    raise CatalogInputError(f"{value!r} is not a valid {key}.") from None
            elif key == "facets":
                try:
                    row.facets = sorted({ObservationFacet(f).value for f in value})
                except ValueError:
                    raise CatalogInputError("Unknown facet.") from None
            elif key in {"expression", "pose"}:
                setattr(row, key, str(value).strip().lower()[:80])
            elif key == "notes":
                row.notes = str(value)[:4000]
            elif key in {"atypical", "anchor"}:
                setattr(row, key, bool(value))
            else:
                raise CatalogInputError(f"{key} cannot be reviewed.")
        if row.anchor and row.status != ObservationStatus.CONFIRMED.value:
            raise CatalogInputError("Only a confirmed observation can be a production anchor.")
        if row.anchor and row.role == ObservationRole.STYLIZATION.value:
            raise CatalogInputError("A stylization reference is never an identity anchor.")
        visual = (
            self.catalog.reference(row.reference_id, include_removed=True).visual_origin
            if row.reference_id
            else None
        )
        if (
            row.source_kind == ObservationSource.FAN_ART.value
            and row.authority in {a.value for a in HIGH_AUTHORITY}
            and visual not in ("PRIMARY_MANGA", "OFFICIAL_ANIME", "OFFICIAL_ART")
        ):
            raise CatalogInputError(
                "Fan art is supplemental; record its visual origin first if it is really "
                "official anime or art."
            )
        character = self.character(row.character_id)
        if character.origin is CharacterOrigin.PROJECT_ORIGINAL and row.authority in {
            ObservationAuthority.PRIMARY_SOURCE.value,
            ObservationAuthority.OFFICIAL.value,
        }:
            raise CatalogInputError("An original character has no franchise source authority.")
        row.reviewed_at = _now()
        row.updated_at = row.reviewed_at
        self.session.flush()
        return row

    # -- retrieval --------------------------------------------------------------
    def retrieve(
        self,
        character_id: uuid.UUID,
        need: dict[str, Any],
        *,
        limit: int = 6,
        include_candidates: bool = True,
        include_supplemental: bool = False,
    ) -> dict[str, Any]:
        """A small, diverse, authority-ranked subset for one need."""
        character = self.character(character_id)
        original = character.origin is CharacterOrigin.PROJECT_ORIGINAL
        wanted_facets = set(need.get("facets") or [])
        angles = set(need.get("angles") or [])
        expressions = set(need.get("expressions") or [])
        poses = set(need.get("poses") or [])
        framing = need.get("framing")
        with_locators = self._shared_locators(character_id, need.get("with") or [])
        rows = self.observations(character_id, include_rejected=False)
        scored: list[tuple[float, CharacterObservation, list[str]]] = []
        stylization: list[CharacterObservation] = []
        for row in rows:
            if row.role == ObservationRole.STYLIZATION.value:
                if row.status == ObservationStatus.CONFIRMED.value:
                    stylization.append(row)
                continue
            if row.authority == ObservationAuthority.UNSORTED.value:
                continue
            if row.status == ObservationStatus.CANDIDATE.value and not include_candidates:
                continue
            if row.authority == ObservationAuthority.SUPPLEMENTAL.value and not (
                include_supplemental and row.status == ObservationStatus.CONFIRMED.value
            ):
                continue
            if original and row.authority not in {
                ObservationAuthority.CREATOR_PRIMARY.value,
                ObservationAuthority.PROJECT_CREATED.value,
            }:
                continue
            why: list[str] = []
            score = 5.0 - AUTHORITY_RANK[ObservationAuthority(row.authority)]
            if row.status == ObservationStatus.CONFIRMED.value:
                score += 3
            else:
                why.append("candidate - not confirmed to show the character")
            if row.anchor:
                score += 2
                why.append("production anchor")
            if row.atypical:
                score -= 4
                why.append("atypical - evidence only")
            matched = wanted_facets & set(row.facets or [])
            if matched:
                score += 2 * len(matched)
                why.append("teaches " + ", ".join(sorted(m.lower() for m in matched)))
            if row.angle and row.angle in angles:
                score += 2
                why.append(f"angle {row.angle.lower()}")
            if row.expression and row.expression in expressions:
                score += 1.5
                why.append(f"expression {row.expression}")
            if row.pose and row.pose in poses:
                score += 1
                why.append(f"pose {row.pose}")
            if framing and (
                row.framing == framing or (row.evidence or {}).get("framing_hint") == framing
            ):
                score += 0.5 if row.framing != framing else 1
                why.append(f"framing {framing.lower()}")
            if row.locator in with_locators:
                score += 2
                why.append("shows the other characters on this page too")
            scored.append((score, row, why))
        scored.sort(key=lambda s: (-s[0], s[1].locator))
        chosen: list[tuple[float, CharacterObservation, list[str]]] = []
        seen_sources: set[str] = set()
        for pass_ in (0, 1):
            for item in scored:
                if len(chosen) >= limit:
                    break
                if item in chosen:
                    continue
                source = (
                    item[1].source_label.split(" p", 1)[0] if item[1].unit_key else item[1].locator
                )
                if pass_ == 0 and source in seen_sources:
                    continue
                seen_sources.add(source)
                chosen.append(item)
        chosen.sort(key=lambda s: (-s[0], s[1].locator))
        return {
            "character": {"id": str(character.id), "name": character.display_name},
            "need": need,
            "observations": [
                observation_view(row, score=round(score, 2), why=why) for score, row, why in chosen
            ],
            "stylization": [observation_view(row) for row in stylization[:2]],
            "available": len(scored),
        }

    def _shared_locators(self, character_id: uuid.UUID, names: Sequence[str]) -> set[str]:
        others = [c.id for name in names if (c := self.by_name(name)) is not None]
        if not others:
            return set()
        mine = select(CharacterObservation.locator).where(
            CharacterObservation.character_id == character_id
        )
        return set(
            self.session.execute(
                select(CharacterObservation.locator).where(
                    CharacterObservation.character_id.in_(others),
                    CharacterObservation.status != ObservationStatus.REJECTED.value,
                    CharacterObservation.locator.in_(mine),
                )
            ).scalars()
        )

    # -- readiness and invariants ---------------------------------------------------
    def counts(self, character_id: uuid.UUID) -> dict[str, Any]:
        rows = self.observations(character_id)
        return {
            "total": len(rows),
            "by_status": dict(Counter(r.status for r in rows)),
            "by_authority": dict(Counter(r.authority for r in rows)),
            "by_source": dict(Counter(r.source_kind for r in rows)),
            "high_authority_confirmed": sum(
                1
                for r in rows
                if r.status == ObservationStatus.CONFIRMED.value
                and r.authority in {a.value for a in HIGH_AUTHORITY}
            ),
        }

    def readiness(self, character_id: uuid.UUID) -> dict[str, Any]:
        rows = [
            r
            for r in self.observations(character_id, include_rejected=False)
            if r.status == ObservationStatus.CONFIRMED.value
            and r.role != ObservationRole.STYLIZATION.value
            and not r.atypical
        ]
        high = [r for r in rows if r.authority in {a.value for a in HIGH_AUTHORITY}]
        groups: dict[str, Any] = {}
        for name, facets in READINESS_GROUPS.items():
            matching = [r for r in high if facets & {ObservationFacet(f) for f in r.facets or []}]
            sources = {r.unit_key or r.locator for r in matching}
            angles = sorted({r.angle for r in matching if r.angle})
            state = (
                "READY"
                if len(matching) >= READY_MIN_OBSERVATIONS and len(sources) >= READY_MIN_SOURCES
                else ("PARTIAL" if matching else "MISSING")
            )
            groups[name] = {
                "state": state,
                "confirmed_high_authority": len(matching),
                "distinct_sources": len(sources),
                "angles": angles,
                "project_created": sum(
                    1
                    for r in rows
                    if r.authority == ObservationAuthority.PROJECT_CREATED.value
                    and facets & {ObservationFacet(f) for f in r.facets or []}
                ),
            }
        for name in ("face", "body"):
            groups[name]["missing_angles"] = [
                a.value for a in WANTED_ANGLES if a.value not in groups[name]["angles"]
            ]
        grounded = groups["identity"]["confirmed_high_authority"] > 0 and (
            groups["body"]["confirmed_high_authority"] > 0
        )
        return {
            "grounded": grounded,
            "ungrounded": [
                name
                for name in ("identity", "body")
                if not groups[name]["confirmed_high_authority"]
            ],
            "groups": groups,
        }

    def grounding(self, character_id: uuid.UUID) -> dict[str, Any]:
        """Confirmed high-authority grounding and confirmed stylization, by reference or locator."""
        rows = self.observations(character_id, include_rejected=False)
        confirmed = [r for r in rows if r.status == ObservationStatus.CONFIRMED.value]

        def key(row: CharacterObservation) -> str:
            return str(row.reference_id) if row.reference_id else row.locator

        out: dict[str, list[str]] = {}
        for name in ("identity", "body"):
            facets = READINESS_GROUPS[name]
            out[name] = [
                key(r)
                for r in sorted(confirmed, key=lambda r: (not r.anchor, r.locator))
                if r.role == ObservationRole.GROUNDING.value
                and r.authority in {a.value for a in HIGH_AUTHORITY}
                and not r.atypical
                and facets & {ObservationFacet(f) for f in r.facets or []}
            ]
        return {
            "grounding": out,
            "stylization": [
                key(r) for r in confirmed if r.role == ObservationRole.STYLIZATION.value
            ],
        }

    def fingerprint_rows(self, character_id: uuid.UUID) -> list[tuple[Any, ...]]:
        """What production depends on: confirmed observations and how they are judged."""
        return sorted(
            (
                r.locator,
                r.authority,
                r.role,
                r.anchor,
                r.atypical,
                tuple(r.facets or []),
                r.angle or "",
                r.expression,
            )
            for r in self.observations(character_id)
            if r.status == ObservationStatus.CONFIRMED.value
        )

    def invariants(self, character: CharacterProfile) -> list[dict[str, Any]]:
        """Declared production invariants, each with its independent support."""
        rows = [
            r
            for r in self.observations(character.id, include_rejected=False)
            if r.status == ObservationStatus.CONFIRMED.value
            and r.authority in {a.value for a in HIGH_AUTHORITY}
            and r.role == ObservationRole.GROUNDING.value
            and not r.atypical
        ]
        declared: list[tuple[str, str]] = []
        for field, facet in (
            ("distinguishing_marks", F.FACE),
            ("scale_notes", F.SCALE),
            ("posture_notes", F.POSE),
        ):
            text = str(getattr(character, field) or "").strip()
            if text:
                declared.append((facet.value, text))
        out = []
        for name, statement in declared:
            support = [
                r
                for r in rows
                if name in (r.facets or []) or (name == "SCALE" and "BODY" in (r.facets or []))
            ]
            sources = {r.unit_key or r.locator for r in support}
            out.append(
                {
                    "facet": name,
                    "statement": statement,
                    "supported_by": len(support),
                    "distinct_sources": len(sources),
                    "state": "SUPPORTED"
                    if len(sources) >= READY_MIN_SOURCES
                    else ("THIN" if support else "DECLARED ONLY"),
                }
            )
        return out

    @staticmethod
    def forbidden(character: CharacterProfile) -> list[str]:
        """Rules like 'NO GLASSES' written in the character's notes."""
        text = f"{character.notes}\n{character.summary}"
        sentences = [
            part.strip(" -*\t")
            for line in re.split(r"[\n;]+", text)
            for part in re.split(r"(?<=[.!?])\s+", line)
        ]
        return list(
            dict.fromkeys(
                sentence
                for sentence in sentences
                if re.search(r"\bNO [A-Z]{3,}|\bSIN [A-Z]{3,}", sentence)
                or re.search(r"\bnever\b|\bnunca\b|\bsin lentes\b|\bno glasses\b", sentence, re.I)
            )
        )

    @staticmethod
    def forbidden_accessories(lines: Sequence[str]) -> list[str]:
        """Accessories the forbidden rules name, for negative prompts."""
        found: set[str] = set()
        for line in lines:
            found.update(w.lower() for w in re.findall(r"\bNO ([A-Z]{3,})", line))
            if re.search(r"\blentes\b|\bgafas\b|\bglasses\b|\bspectacles\b", line, re.I):
                found.add("glasses")
        return sorted(found)

    def overview(self, character_id: uuid.UUID) -> dict[str, Any]:
        character = self.character(character_id)
        rows = self.observations(character_id)
        anchors = [r for r in rows if r.anchor and r.status == ObservationStatus.CONFIRMED.value]
        anchors.sort(key=lambda r: (AUTHORITY_RANK[ObservationAuthority(r.authority)], r.locator))
        stylization = [
            r
            for r in rows
            if r.role == ObservationRole.STYLIZATION.value
            and r.status != ObservationStatus.REJECTED.value
        ]
        primary = anchors[0] if anchors else None
        return {
            "character": {
                "id": str(character.id),
                "display_name": character.display_name,
                "origin": character.origin.value,
                "project_key": character.project_key,
                "source_label": character.source_label,
                "summary": character.summary,
                "design_documents": list(character.design_documents or []),
            },
            "primary_visual": observation_view(primary) if primary else None,
            "readiness": self.readiness(character_id),
            "counts": self.counts(character_id),
            "anchors": [observation_view(r) for r in anchors],
            "stylization": [observation_view(r) for r in stylization],
            "invariants": self.invariants(character),
            "forbidden": self.forbidden(character),
            "grounding_rule": (
                "creator photos ground identity and body; project concepts guide stylization only"
                if character.origin is CharacterOrigin.PROJECT_ORIGINAL
                else "the source manga grounds identity and body; official art next; "
                "project pages and supplemental material add evidence only"
            ),
        }

    # -- environment ------------------------------------------------------------
    def set_visual_origin(
        self, observation_id: uuid.UUID, visual_origin: str | None
    ) -> CharacterObservation:
        """Record who made an observed image, keeping where it was acquired.

        An official anime frame reposted by a fan account keeps its acquisition
        provenance and becomes OFFICIAL evidence - still a candidate until a person
        confirms it shows the character.
        """
        row = self.observation(observation_id)
        if row.reference_id is None:
            raise CatalogInputError("A source page's origin is the source manga itself.")
        item = self.catalog.reference(row.reference_id)
        self.catalog.update_reference(item.id, item.row_version, visual_origin=visual_origin)
        character = self.character(row.character_id)
        authority, role = self._authority_of(
            item, character.origin is CharacterOrigin.PROJECT_ORIGINAL, False
        )
        if row.role != ObservationRole.STYLIZATION.value:
            row.authority, row.role = authority, role
        row.evidence = {
            **(row.evidence or {}),
            "acquired_from": {
                "origin": item.origin.value,
                "collection": item.collection,
                "creator_handle_recorded": bool(item.creator_handle),
            },
            "visual_origin": item.visual_origin,
        }
        row.reviewed_at = _now()
        self.session.flush()
        return row

    def tag_environment(self, observation_id: uuid.UUID, tags: Sequence[str]) -> ReferenceItem:
        """Use an observed page as an environment reference, with setting tags.

        The page becomes (or already is) a reference carrying LOCATION tags.
        Environment references teach composition, architecture, perspective,
        material, lighting and atmosphere; they never define a character and
        never override the project's own setting canon.
        """
        clean = list(
            dict.fromkeys(
                re.sub(r"\s+", " ", str(tag)).strip().lower()[:60]
                for tag in tags
                if str(tag).strip()
            )
        )[:8]
        if not clean:
            raise CatalogInputError("Give at least one setting tag, such as forest or inn.")
        row = self.observation(observation_id)
        if row.reference_id is not None:
            item = self.catalog.reference(row.reference_id)
        else:
            found = self._unit(row)
            sources = self.catalog.sources
            if found is None or sources is None or self.page_reader is None:
                raise CatalogNotFoundError("That source page is no longer catalogued.")
            unit, entry = found
            read = self.page_reader(unit, entry, int(row.page_offset or 0))
            media_id = sources.media_id_for(entry.relative_path)
            if read is None or media_id is None:
                raise CatalogNotFoundError("That source page cannot be read right now.")
            existing = (
                self.session.execute(
                    select(ReferenceItem).where(
                        ReferenceItem.locator == read[0],
                        ReferenceItem.region_x.is_(None),
                        ReferenceItem.removed_at.is_(None),
                    )
                )
                .scalars()
                .first()
            )
            item = existing or self.catalog.add_from_source(
                media_id,
                ReferenceSpec(
                    reference_class=ReferenceClass.TECHNIQUE,
                    origin=ReferenceOrigin.SOURCE,
                    label=f"Environment - {row.source_label}"[:300],
                    uses=(ReferenceUse.SCENE_SOURCE,),
                ),
                page_index=(unit.first_page_index or 0) + int(row.page_offset or 0),
            )
        have = {
            d.value.lower()
            for d in self.session.execute(
                select(ReferenceDescriptor).where(ReferenceDescriptor.reference_id == item.id)
            ).scalars()
        }
        for tag in clean:
            if tag not in have:
                self.catalog.add_descriptor(item.id, DescriptorSpec(DescriptorFacet.LOCATION, tag))
        self.session.flush()
        return item

    # -- images and bundle inputs ------------------------------------------------------
    def image(self, observation_id: uuid.UUID) -> EncodedImage:
        row = self.observation(observation_id)
        if row.reference_id is not None:
            return self.catalog.reference_image(row.reference_id)
        found = self._unit(row)
        if found is None or self.page_reader is None:
            raise CatalogNotFoundError("That source page is no longer catalogued.")
        read = self.page_reader(found[0], found[1], int(row.page_offset or 0))
        if read is None:
            raise CatalogNotFoundError("That source page cannot be read right now.")
        return preview(read[1], None)

    def resolve(self, row: CharacterObservation) -> tuple[str, uuid.UUID | None] | None:
        """The locator (and reference) a render job reads this observation from."""
        if row.reference_id is not None:
            item = self.catalog.reference(row.reference_id)
            return item.locator, item.id
        found = self._unit(row)
        if found is None or self.page_reader is None:
            return None
        read = self.page_reader(found[0], found[1], int(row.page_offset or 0))
        return (read[0], None) if read else None
