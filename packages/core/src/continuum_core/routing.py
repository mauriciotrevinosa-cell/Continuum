"""Purpose-aware reference routing: what a reference is asked to teach.

Retrieval used to answer "which references are about this panel?". That is the
wrong question, and it is why a render can receive a page of someone eating
while it is trying to draw someone casting a spell. The right question is
**what does the renderer need this reference to teach?** - and the answer must
travel with the reference, into the render packet and into lineage.

So every reference enters a packet with a :class:`ReferencePurpose`, and a
purpose carries a rule:

* what it may **influence** - identity, wardrobe, layout, treatment or the
  construction of one object. A style reference may shape treatment and
  nothing else; no purpose may silently redefine who a character is;
* whether it is **character scoped** (it belongs to one named cast member) and
  whether it is **identity bearing** (it may define who that person is). Only
  two purposes are identity bearing, and both require a named character;
* whether it may **image-condition** the render at all. Scale locks and colour
  notes are facts about the packet, not pictures to copy.

The module is pure data and pure ranking: no I/O, no database, no franchise,
character or project literal. Which references exist is the catalog's problem;
which of them serve *this* panel is this module's.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum

from continuum_core.references import BundleRole, PanelStage, TechniqueFacet

__all__ = [
    "AUTHORITY_ORDER",
    "PURPOSE_RULES",
    "STAGE_NEEDS",
    "STANDING_ORDER",
    "Candidate",
    "ConditioningPurpose",
    "Influence",
    "PurposeNeed",
    "PurposeRule",
    "ReferencePurpose",
    "RejectedReference",
    "RoutedPacket",
    "RoutedReference",
    "purposes_for_stage",
    "record",
    "route",
]


class Influence(StrEnum):
    """What a reference is allowed to change about the image."""

    IDENTITY = "IDENTITY"
    """Who a named character is: face, hair, head shape, distinguishing marks."""
    WARDROBE = "WARDROBE"
    """What a character wears. Never who they are."""
    LAYOUT = "LAYOUT"
    """Camera, placement, massing, perspective, depth."""
    TREATMENT = "TREATMENT"
    """Line, value, tone, light, colour - how the image is drawn, never what."""
    DETAIL = "DETAIL"
    """The construction or size of one named object."""


class ConditioningPurpose(StrEnum):
    """What an image-conditioned reference is allowed to shape.

    The lane an image actually enters at render time. Identity is per character
    and never blended; every other lane is the scene lane of its stage.
    """

    IDENTITY = "IDENTITY"
    COMPOSITION = "COMPOSITION"
    STYLE_AND_COMPOSITION = "STYLE_AND_COMPOSITION"
    STYLE = "STYLE"


class ReferencePurpose(StrEnum):
    """What a reference was selected to teach."""

    IDENTITY = "IDENTITY"
    BODY = "BODY"
    WARDROBE = "WARDROBE"
    ACCESSORY = "ACCESSORY"
    ACCESSORY_SCALE = "ACCESSORY_SCALE"
    EXPRESSION = "EXPRESSION"
    QUIET_ACTING = "QUIET_ACTING"
    ACTION_POSE = "ACTION_POSE"
    FIGURE_CONSTRUCTION = "FIGURE_CONSTRUCTION"
    """How bodies, hands, faces and garments are *drawn* - craft, never identity."""
    COMPOSITION = "COMPOSITION"
    ENVIRONMENT = "ENVIRONMENT"
    ARCHITECTURE = "ARCHITECTURE"
    MATERIAL_DETAIL = "MATERIAL_DETAIL"
    MANGA_LINE_LANGUAGE = "MANGA_LINE_LANGUAGE"
    SCREENTONE_LANGUAGE = "SCREENTONE_LANGUAGE"
    MAGIC_EFFECT = "MAGIC_EFFECT"
    LIGHTING = "LIGHTING"
    ATMOSPHERE = "ATMOSPHERE"
    DEPTH = "DEPTH"
    COLOR_REFERENCE = "COLOR_REFERENCE"


@dataclass(frozen=True, slots=True)
class PurposeRule:
    """What one purpose means, and what it is permitted to do."""

    purpose: ReferencePurpose
    influences: frozenset[Influence]
    #: Belongs to one named cast member; never routed without one.
    character_scoped: bool
    #: May define who that character is. Implies ``character_scoped``.
    identity_bearing: bool
    #: May be handed to the renderer as an image. False means the packet
    #: carries it as a recorded fact (a measurement, a palette note).
    image_conditioned: bool
    #: Reference roles that can carry this purpose.
    roles: frozenset[str]
    #: Technique facets that count as teaching it.
    facets: frozenset[str]
    summary: str


def _rule(
    purpose: ReferencePurpose,
    influences: Iterable[Influence],
    roles: Iterable[BundleRole],
    facets: Iterable[TechniqueFacet],
    summary: str,
    *,
    character_scoped: bool = False,
    identity_bearing: bool = False,
    image_conditioned: bool = True,
) -> PurposeRule:
    return PurposeRule(
        purpose=purpose,
        influences=frozenset(influences),
        character_scoped=character_scoped or identity_bearing,
        identity_bearing=identity_bearing,
        image_conditioned=image_conditioned,
        roles=frozenset(role.value for role in roles),
        facets=frozenset(facet.value for facet in facets),
        summary=summary,
    )


PURPOSE_RULES: dict[ReferencePurpose, PurposeRule] = {
    rule.purpose: rule
    for rule in (
        _rule(
            ReferencePurpose.IDENTITY,
            (Influence.IDENTITY,),
            (BundleRole.CANON,),
            (),
            "who this character is: face, hair, head shape, marks",
            identity_bearing=True,
        ),
        _rule(
            ReferencePurpose.BODY,
            (Influence.IDENTITY,),
            (BundleRole.CANON,),
            (),
            "their proportions, scale, posture and silhouette",
            identity_bearing=True,
        ),
        _rule(
            ReferencePurpose.WARDROBE,
            (Influence.WARDROBE,),
            (BundleRole.WARDROBE,),
            (),
            "the garment they wear at this story stage",
            character_scoped=True,
        ),
        _rule(
            ReferencePurpose.ACCESSORY,
            (Influence.WARDROBE, Influence.DETAIL),
            (BundleRole.WARDROBE, BundleRole.CONTINUITY),
            (),
            "a recurring worn or carried object",
            character_scoped=True,
        ),
        _rule(
            ReferencePurpose.ACCESSORY_SCALE,
            (Influence.DETAIL,),
            (BundleRole.WARDROBE, BundleRole.CONTINUITY, BundleRole.CANON),
            (),
            "how big that object is, and relative to what",
            character_scoped=True,
            image_conditioned=False,
        ),
        _rule(
            ReferencePurpose.EXPRESSION,
            (Influence.DETAIL,),
            (BundleRole.CONTINUITY, BundleRole.CANON),
            (TechniqueFacet.FACIAL_ACTING,),
            "the facial acting this beat needs",
            character_scoped=True,
        ),
        _rule(
            ReferencePurpose.QUIET_ACTING,
            (Influence.DETAIL,),
            (BundleRole.TECHNIQUE, BundleRole.CONTINUITY),
            (TechniqueFacet.QUIET_ACTING, TechniqueFacet.FACIAL_ACTING),
            "how stillness carries a beat",
        ),
        _rule(
            ReferencePurpose.ACTION_POSE,
            (Influence.LAYOUT, Influence.DETAIL),
            (BundleRole.CONTINUITY, BundleRole.TECHNIQUE),
            (TechniqueFacet.POSE, TechniqueFacet.ACTION_READABILITY),
            "the action this beat needs, read at a glance",
        ),
        _rule(
            ReferencePurpose.FIGURE_CONSTRUCTION,
            (Influence.DETAIL,),
            (BundleRole.TECHNIQUE, BundleRole.STYLE),
            (
                TechniqueFacet.ANATOMY,
                TechniqueFacet.HANDS,
                TechniqueFacet.CLOTHING,
                TechniqueFacet.POSE,
            ),
            "how a figure is constructed - craft, never a character's identity",
        ),
        _rule(
            ReferencePurpose.COMPOSITION,
            (Influence.LAYOUT,),
            (BundleRole.TECHNIQUE, BundleRole.ENVIRONMENT, BundleRole.CANON),
            (
                TechniqueFacet.COMPOSITION,
                TechniqueFacet.CINEMATOGRAPHY,
                TechniqueFacet.NEGATIVE_SPACE,
                TechniqueFacet.ESTABLISHING_SHOT,
            ),
            "how this shot is composed",
        ),
        _rule(
            ReferencePurpose.ENVIRONMENT,
            (Influence.LAYOUT, Influence.TREATMENT),
            (BundleRole.ENVIRONMENT, BundleRole.CANON),
            (TechniqueFacet.BACKGROUND_TREATMENT, TechniqueFacet.ESTABLISHING_SHOT),
            "what this place looks like",
        ),
        _rule(
            ReferencePurpose.ARCHITECTURE,
            (Influence.LAYOUT,),
            (BundleRole.ENVIRONMENT, BundleRole.TECHNIQUE, BundleRole.CANON),
            (TechniqueFacet.ARCHITECTURE, TechniqueFacet.PERSPECTIVE),
            "how the built space is drawn and measured",
        ),
        _rule(
            ReferencePurpose.MATERIAL_DETAIL,
            (Influence.TREATMENT,),
            (BundleRole.TECHNIQUE, BundleRole.STYLE),
            (TechniqueFacet.MATERIALS,),
            "how surfaces and materials read",
        ),
        _rule(
            ReferencePurpose.MANGA_LINE_LANGUAGE,
            (Influence.TREATMENT,),
            (BundleRole.STYLE, BundleRole.TECHNIQUE),
            (TechniqueFacet.LINEART,),
            "the project's line language",
        ),
        _rule(
            ReferencePurpose.SCREENTONE_LANGUAGE,
            (Influence.TREATMENT,),
            (BundleRole.STYLE, BundleRole.TECHNIQUE),
            (TechniqueFacet.SCREENTONE,),
            "how tone and black are used",
        ),
        _rule(
            ReferencePurpose.MAGIC_EFFECT,
            (Influence.TREATMENT, Influence.DETAIL),
            (BundleRole.TECHNIQUE, BundleRole.STYLE),
            (TechniqueFacet.MAGIC, TechniqueFacet.FX, TechniqueFacet.IMPACT_LANGUAGE),
            "how this effect is drawn",
        ),
        _rule(
            ReferencePurpose.LIGHTING,
            (Influence.TREATMENT,),
            (BundleRole.TECHNIQUE, BundleRole.STYLE, BundleRole.MOOD),
            (TechniqueFacet.LIGHTING, TechniqueFacet.NIGHT_RENDERING),
            "how this light is built",
        ),
        _rule(
            ReferencePurpose.ATMOSPHERE,
            (Influence.TREATMENT,),
            (BundleRole.MOOD, BundleRole.TECHNIQUE, BundleRole.STYLE),
            (TechniqueFacet.ATMOSPHERE,),
            "the air and density of the moment",
        ),
        _rule(
            ReferencePurpose.DEPTH,
            (Influence.LAYOUT,),
            (BundleRole.TECHNIQUE, BundleRole.ENVIRONMENT),
            (TechniqueFacet.PERSPECTIVE,),
            "how depth is staged",
        ),
        _rule(
            ReferencePurpose.COLOR_REFERENCE,
            (Influence.TREATMENT,),
            (BundleRole.STYLE, BundleRole.CANON),
            (TechniqueFacet.COLOR,),
            "the approved palette; recorded, never conditioned in a mono pass",
            image_conditioned=False,
        ),
    )
}


@dataclass(frozen=True, slots=True)
class PurposeNeed:
    """One purpose a stage wants, how many of it, and whether it is mandatory."""

    purpose: ReferencePurpose
    budget: int = 1
    #: For a character-scoped purpose, ``budget`` is per cast member.
    required_for_cast: bool = False


def _needs(*pairs: tuple[ReferencePurpose, int]) -> tuple[PurposeNeed, ...]:
    return tuple(
        PurposeNeed(
            purpose,
            budget,
            required_for_cast=PURPOSE_RULES[purpose].identity_bearing,
        )
        for purpose, budget in pairs
    )


#: What each construction stage asks for, in priority order. A stage takes the
#: narrowest evidence for *its* problem: the line stage never asks for a
#: composition, and the composition stage never asks for screentone.
STAGE_NEEDS: dict[PanelStage, tuple[PurposeNeed, ...]] = {
    PanelStage.COMPOSITION: _needs(
        (ReferencePurpose.IDENTITY, 1),
        (ReferencePurpose.ENVIRONMENT, 1),
        (ReferencePurpose.ARCHITECTURE, 1),
        (ReferencePurpose.COMPOSITION, 1),
        (ReferencePurpose.DEPTH, 1),
        (ReferencePurpose.ACTION_POSE, 1),
    ),
    PanelStage.DRAWING: _needs(
        (ReferencePurpose.IDENTITY, 2),
        (ReferencePurpose.BODY, 1),
        (ReferencePurpose.WARDROBE, 1),
        (ReferencePurpose.ACCESSORY, 1),
        (ReferencePurpose.ACCESSORY_SCALE, 1),
        (ReferencePurpose.EXPRESSION, 1),
        (ReferencePurpose.FIGURE_CONSTRUCTION, 1),
        (ReferencePurpose.QUIET_ACTING, 1),
        (ReferencePurpose.ARCHITECTURE, 1),
    ),
    PanelStage.LINE: _needs(
        (ReferencePurpose.MANGA_LINE_LANGUAGE, 2),
        (ReferencePurpose.FIGURE_CONSTRUCTION, 1),
    ),
    PanelStage.VALUE_MATERIAL: _needs(
        (ReferencePurpose.SCREENTONE_LANGUAGE, 2),
        (ReferencePurpose.MATERIAL_DETAIL, 1),
    ),
    PanelStage.LIGHT_SHADOW: _needs(
        (ReferencePurpose.LIGHTING, 2),
        (ReferencePurpose.ATMOSPHERE, 1),
    ),
    PanelStage.FX: _needs(
        (ReferencePurpose.MAGIC_EFFECT, 2),
        (ReferencePurpose.ATMOSPHERE, 1),
    ),
    PanelStage.ENVIRONMENT_INTEGRATION: _needs(
        (ReferencePurpose.ENVIRONMENT, 1),
        (ReferencePurpose.ARCHITECTURE, 1),
        (ReferencePurpose.ATMOSPHERE, 1),
        (ReferencePurpose.DEPTH, 1),
    ),
    PanelStage.FINISH: _needs(
        (ReferencePurpose.MANGA_LINE_LANGUAGE, 1),
        (ReferencePurpose.SCREENTONE_LANGUAGE, 1),
        (ReferencePurpose.COLOR_REFERENCE, 1),
    ),
}

#: The scene-lane conditioning of each stage: what a non-identity image may
#: shape there. Composition takes layout; everything after it takes treatment.
STAGE_SCENE_LANE: dict[PanelStage, ConditioningPurpose] = {
    PanelStage.COMPOSITION: ConditioningPurpose.COMPOSITION,
    PanelStage.DRAWING: ConditioningPurpose.STYLE_AND_COMPOSITION,
    PanelStage.ENVIRONMENT_INTEGRATION: ConditioningPurpose.STYLE_AND_COMPOSITION,
    PanelStage.LINE: ConditioningPurpose.STYLE,
    PanelStage.VALUE_MATERIAL: ConditioningPurpose.STYLE,
    PanelStage.LIGHT_SHADOW: ConditioningPurpose.STYLE,
    PanelStage.FX: ConditioningPurpose.STYLE,
    PanelStage.FINISH: ConditioningPurpose.STYLE,
}

#: Lower is stronger. Mirrors the corpus authority ranking without importing it,
#: and tolerates an unknown value rather than failing the whole routing pass.
AUTHORITY_ORDER: dict[str, int] = {
    "PRIMARY_SOURCE": 0,
    "CREATOR_PRIMARY": 0,
    "OFFICIAL": 1,
    "PROJECT_CREATED": 2,
    "SUPPLEMENTAL": 3,
    "UNSORTED": 9,
}
#: Lower is stronger.
STANDING_ORDER: dict[str, int] = {
    "PREFERRED_FOR_CURRENT_LOOK": 0,
    "CANONICAL_FOR_PROJECT": 1,
    "USEFUL": 2,
}


def purposes_for_stage(stage: PanelStage) -> tuple[ReferencePurpose, ...]:
    return tuple(need.purpose for need in STAGE_NEEDS.get(stage, ()))


@dataclass(frozen=True, slots=True)
class Candidate:
    """One reference retrieval offered, described by what is recorded about it."""

    reference_id: str
    role: str
    #: Technique facets recorded on the reference.
    facets: frozenset[str] = frozenset()
    #: Human-readable descriptor matches ("location: forest").
    descriptors: tuple[str, ...] = ()
    #: The cast member it is evidence of, when it is character evidence.
    character: str | None = None
    outfit_id: str | None = None
    prop_id: str | None = None
    standing: str | None = None
    authority: str | None = None
    status: str | None = None
    origin: str | None = None
    #: The source world it comes from, when it comes from one.
    series: str | None = None
    #: 0.0-1.0; retrieval's own confidence that it is worth using.
    quality: float = 0.0
    #: Retrieval order, the final tie-break: routing is deterministic.
    order: int = 0
    #: Purposes retrieval already committed this reference to (a wardrobe row
    #: resolved for a story stage, a prop's own scale plate). Empty means the
    #: router decides from role and facets.
    declared: frozenset[str] = frozenset()
    why: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RoutedReference:
    reference_id: str
    purpose: ReferencePurpose
    role: str
    character: str | None
    influences: tuple[str, ...]
    image_conditioned: bool
    why: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RejectedReference:
    reference_id: str
    role: str
    reason: str


@dataclass(frozen=True, slots=True)
class RoutedPacket:
    selected: tuple[RoutedReference, ...] = ()
    rejected: tuple[RejectedReference, ...] = ()
    #: Purposes the stage needed for a cast member and did not get.
    unmet: tuple[str, ...] = ()

    @property
    def identity(self) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {}
        for entry in self.selected:
            if PURPOSE_RULES[entry.purpose].identity_bearing and entry.character:
                out.setdefault(entry.character, []).append(entry.reference_id)
        return out


def _eligible(candidate: Candidate, rule: PurposeRule, cast: Sequence[str]) -> str | None:
    """Why this candidate may not serve this purpose, or None.

    A candidate retrieval already committed to a purpose (``declared``) serves
    that purpose and no other: the commitment replaces the role and facet
    guesses, never the identity rules, which always apply.
    """
    declared = rule.purpose.value in candidate.declared
    if candidate.declared and not declared:
        return "retrieved to teach " + ", ".join(sorted(candidate.declared)).lower()
    if rule.character_scoped:
        if not candidate.character:
            return f"{rule.purpose.value.lower()} must belong to a named character"
        if candidate.character not in cast:
            return f"{candidate.character} is not in this panel"
    elif candidate.character:
        # A character's evidence is theirs. It never becomes style or setting.
        return "character evidence is never routed to a non-character purpose"
    if rule.identity_bearing and candidate.status == "CANDIDATE":
        return "an unconfirmed candidate never grounds identity"
    if declared:
        return None
    if candidate.role not in rule.roles:
        return f"a {candidate.role.lower()} reference does not teach {rule.purpose.value.lower()}"
    if _house_style(candidate, rule):
        # The project said this is the look. That is the treatment authority,
        # whether or not anybody also tagged it with a technique facet.
        return None
    if rule.facets and not (candidate.facets & rule.facets) and not candidate.descriptors:
        return (
            "nothing recorded about it teaches "
            f"{rule.purpose.value.lower().replace('_', ' ')} for this panel"
        )
    return None


def _house_style(candidate: Candidate, rule: PurposeRule) -> bool:
    return (
        candidate.standing == "PREFERRED_FOR_CURRENT_LOOK"
        and Influence.TREATMENT in rule.influences
    )


def _rank(
    candidate: Candidate, rule: PurposeRule, current_outfits: Mapping[str, str]
) -> tuple[int | str, ...]:
    """Ordering inside one purpose. Lower is better; fully deterministic."""
    facet_hit = 0 if candidate.facets & rule.facets or _house_style(candidate, rule) else 1
    outfit_hit = (
        0
        if candidate.character
        and candidate.outfit_id
        and current_outfits.get(candidate.character) == candidate.outfit_id
        else 1
    )
    return (
        facet_hit,
        outfit_hit,
        STANDING_ORDER.get(candidate.standing or "", 3),
        AUTHORITY_ORDER.get(candidate.authority or "", 4),
        0 if candidate.status == "CONFIRMED" else 1,
        -round(candidate.quality * 1000),
        candidate.order,
        candidate.reference_id,
    )


def route(
    needs: Sequence[PurposeNeed],
    candidates: Sequence[Candidate],
    *,
    cast: Sequence[str] = (),
    current_outfits: Mapping[str, str] | None = None,
    relevant_series: Sequence[str] = (),
) -> RoutedPacket:
    """Route each candidate to the purpose it best serves, inside the stage's budgets.

    Needs are honoured in order, so the stage's own priority decides who gets a
    scarce reference. A reference is used once: the first purpose that takes it
    owns it, and later purposes see it as already spent rather than duplicating
    it. Material from an unrelated source world is refused unless something
    recorded about it actually matches this panel - availability is not a
    reason to send a reference.
    """
    outfits = dict(current_outfits or {})
    wanted_series = {s for s in relevant_series if s}
    selected: list[RoutedReference] = []
    rejected: dict[str, RejectedReference] = {}
    unmet: list[str] = []
    spent: set[str] = set()
    reasons: dict[str, list[str]] = {}

    def refuse(candidate: Candidate, reason: str) -> None:
        reasons.setdefault(candidate.reference_id, []).append(reason)

    relevant: list[Candidate] = []
    for candidate in candidates:
        if (
            candidate.series
            and wanted_series
            and candidate.series not in wanted_series
            and not candidate.facets
            and not candidate.descriptors
        ):
            refuse(
                candidate,
                f"unrelated source material ({candidate.series}): nothing recorded "
                "about it matches this panel",
            )
            rejected.setdefault(
                candidate.reference_id,
                RejectedReference(
                    candidate.reference_id, candidate.role, reasons[candidate.reference_id][-1]
                ),
            )
            continue
        relevant.append(candidate)

    for need in needs:
        rule = PURPOSE_RULES[need.purpose]
        pool: list[tuple[tuple[int | str, ...], Candidate]] = []
        for candidate in relevant:
            if candidate.reference_id in spent:
                continue
            reason = _eligible(candidate, rule, cast)
            if reason is not None:
                refuse(candidate, reason)
                continue
            pool.append((_rank(candidate, rule, outfits), candidate))
        pool.sort(key=lambda pair: pair[0])
        if rule.character_scoped and cast:
            taken = _per_character(pool, need.budget, cast)
        else:
            taken = [candidate for _rank_key, candidate in pool[: need.budget]]
            for _rank_key, candidate in pool[need.budget :]:
                refuse(candidate, f"over the {need.purpose.value.lower()} budget ({need.budget})")
        for candidate in taken:
            spent.add(candidate.reference_id)
            selected.append(
                RoutedReference(
                    reference_id=candidate.reference_id,
                    purpose=need.purpose,
                    role=candidate.role,
                    character=candidate.character,
                    influences=tuple(sorted(i.value for i in rule.influences)),
                    image_conditioned=rule.image_conditioned,
                    why=(*candidate.why, f"selected to teach {rule.summary}"),
                )
            )
        if need.required_for_cast and cast:
            covered = {c.character for c in taken}
            unmet.extend(
                f"{name}: no {need.purpose.value.lower()} evidence"
                for name in cast
                if name not in covered
            )

    for reference_id, why in reasons.items():
        if reference_id in spent or reference_id in rejected:
            continue
        candidate = next(c for c in candidates if c.reference_id == reference_id)
        rejected[reference_id] = RejectedReference(reference_id, candidate.role, why[0])
    return RoutedPacket(
        selected=tuple(selected),
        rejected=tuple(rejected[key] for key in sorted(rejected)),
        unmet=tuple(unmet),
    )


def _per_character(
    pool: Sequence[tuple[tuple[int | str, ...], Candidate]], budget: int, cast: Sequence[str]
) -> list[Candidate]:
    """A character-scoped budget is per cast member, so nobody is crowded out."""
    per: dict[str, list[Candidate]] = {name: [] for name in cast}
    for _rank_key, candidate in pool:
        bucket = per.get(str(candidate.character))
        if bucket is not None and len(bucket) < budget:
            bucket.append(candidate)
    return [candidate for name in cast for candidate in per[name]]


def record(stage: str, packet: RoutedPacket) -> dict[str, object]:
    """The packet as JSON for ``artwork_provenance`` and the construction screen."""
    return {
        "stage": stage,
        "selected": [
            {
                "reference_id": entry.reference_id,
                "purpose": entry.purpose.value,
                "role": entry.role,
                "character": entry.character,
                "influences": list(entry.influences),
                "image_conditioned": entry.image_conditioned,
                "why": list(entry.why),
            }
            for entry in packet.selected
        ],
        "rejected": [
            {"reference_id": e.reference_id, "role": e.role, "reason": e.reason}
            for e in packet.rejected
        ],
        "unmet": list(packet.unmet),
    }
