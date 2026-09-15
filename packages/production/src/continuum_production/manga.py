"""Page-by-page manga production (M3): runs, pages, continuity, review, invalidation.

The loop this module owns::

    materialize chapter -> start run (sample or canonical)
      -> page READY -> assemble bundle (grounded characters, continuity from
         approved pages, manga grammar, environment) -> attempt (a durable
         render job: composition master + B&W + color finishes)
      -> review -> approve -> continuity version + 1 -> next page READY

Invariants enforced here (and, where possible, by the database):

* **Page by page.** A page is WAITING until the page before it is approved.
* **Sample is never canon.** A NON_CANON_SAMPLE run's pages are sample
  artifacts; approving one (a technical pass) advances the sample only. A
  sample can PASS only when every approved page is an ARTWORK_CANDIDATE - a
  sample of diagrams proves nothing about art. A pass promotes the *profile*,
  never the images.
* **Canonical E1 starts deliberately.** Only with a PROMOTED profile and no
  creative-readiness blocker (unconfirmed insertion placements, required
  sources missing, season checklists still in review).
* **No silent substitution.** A character without grounded identity and body
  references blocks the page with MISSING_REQUIRED_REFERENCE.
* **Continuity comes only from approved pages** of the same run.
* **Selective invalidation.** Every page records what it was built from; a
  changed page body, character grounding, profile or earlier approved master
  marks exactly the dependent pages STALE, with the old and new versions.
  Approved art is never regenerated or replaced by this module.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from continuum_core import canonical_json_hash
from continuum_core.catalog import UnitKind
from continuum_core.references import (
    AssetOrigin,
    AttemptState,
    BundleRole,
    RenderOutput,
    ReviewDecision,
    RoughArtifactKind,
    RoughPurpose,
)
from continuum_db.models import (
    AttemptDerivative,
    CatalogEntry,
    CatalogUnit,
    CharacterObservation,
    CharacterProfile,
    ContinuityState,
    MaterializedChapter,
    PageDependency,
    ProductionPage,
    ProductionProfile,
    ProductionRun,
    ReferenceDescriptor,
    ReferenceItem,
    RoughArtifact,
    RoughAttempt,
)
from continuum_library import (
    CatalogConflictError,
    CatalogInputError,
    CatalogNotFoundError,
    ReferenceCatalog,
)
from continuum_library.validation import clean_text, require_project_key
from continuum_storage import ProjectLibrary, SourceChangedError, SourceUnavailableError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from continuum_production.corpus import CharacterCorpus, page_needs, setting_tags
from continuum_production.materialize import (
    MATERIALIZER_VERSION,
    MaterializationInput,
    PlacementDecision,
    SourceText,
    materialize_chapter,
)
from continuum_production.plan import page_plan, page_references
from continuum_production.service import RoughProduction

__all__ = [
    "PAGE_WORKFLOW",
    "GrammarCandidate",
    "MangaProduction",
    "catalog_grammar_candidates",
    "chapter_qa",
    "rank_grammar",
    "source_page_reader",
]

PAGE_WORKFLOW = "page.v1"
APPROVAL_FOR = {
    RoughPurpose.NON_CANON_SAMPLE: ReviewDecision.TECHNICAL_PASS,
    RoughPurpose.PRODUCTION: ReviewDecision.CREATIVE_APPROVE,
}
APPROVED_STATES = {
    RoughPurpose.NON_CANON_SAMPLE: {AttemptState.TECHNICAL_PASS},
    RoughPurpose.PRODUCTION: {AttemptState.CREATIVE_APPROVED, AttemptState.FINAL_APPROVED},
}


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Manga grammar: structural relevance from page layout
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class GrammarCandidate:
    locator: str
    series_key: str | None
    label: str
    panel_count: int
    largest_panel_share: float
    negative_space: float
    ink_density: float
    unit_key: str | None = None
    page_offset: int | None = None


def _grammar_score(intents: Sequence[str], c: GrammarCandidate) -> float:
    tags = set(intents)
    score = 0.0
    if tags & {"large_composition", "back_shot", "chapter_end"}:
        score += 2.0 * c.largest_panel_share + (1.0 if c.panel_count <= 3 else 0.0)
    if "silent" in tags:
        score += c.negative_space + (0.5 if c.panel_count <= 4 else 0.0)
    if "conversation" in tags:
        score += 1.0 if 4 <= c.panel_count <= 7 else 0.0
    if tags & {"low_dialogue", "quiet_acting", "confused_reaction"}:
        score += (1.0 if 3 <= c.panel_count <= 6 else 0.0) + 0.5 * c.negative_space
    if "close_up" in tags:
        score += 0.5 if c.panel_count >= 3 else 0.0
    if "magic_effect" in tags:
        score += c.ink_density
    return round(score, 4)


def rank_grammar(
    intents: Sequence[str], candidates: Sequence[GrammarCandidate], limit: int
) -> list[dict[str, Any]]:
    """The most structurally relevant pages, one per series first (a school, not a blend)."""
    scored = sorted(
        ((c, _grammar_score(intents, c)) for c in candidates),
        key=lambda pair: (-pair[1], pair[0].locator),
    )
    chosen: list[tuple[GrammarCandidate, float]] = []
    seen_series: set[str | None] = set()
    for pair in scored:  # first pass: diversity across series
        if pair[1] > 0 and pair[0].series_key not in seen_series and len(chosen) < limit:
            chosen.append(pair)
            seen_series.add(pair[0].series_key)
    for pair in scored:
        if pair[1] > 0 and pair not in chosen and len(chosen) < limit:
            chosen.append(pair)
    teaches = ["panel_density", "panel_geometry", "negative_space", "reading_flow"]
    return [
        {
            "locator": c.locator,
            "series_key": c.series_key,
            "label": c.label,
            "score": score,
            "teaches": teaches,
            "structure": {
                "panel_count": c.panel_count,
                "largest_panel_share": c.largest_panel_share,
                "negative_space": c.negative_space,
                "ink_density": c.ink_density,
            },
        }
        for c, score in chosen
    ]


# ---------------------------------------------------------------------------
class MangaProduction:
    """Page-by-page production inside one database session (the caller commits)."""

    def __init__(
        self,
        rough: RoughProduction,
        projects: ProjectLibrary,
        *,
        grammar_candidates: Callable[[Sequence[str], int], list[GrammarCandidate]] | None = None,
        page_reader: Callable[[CatalogUnit, CatalogEntry, int], tuple[str, bytes] | None]
        | None = None,
    ) -> None:
        self.rough = rough
        self.session: Session = rough.session
        self.catalog = rough.catalog
        self.projects = projects
        self.grammar_candidates = grammar_candidates
        self.corpus = CharacterCorpus(self.session, self.catalog, page_reader=page_reader)

    # =====================================================================
    # Materialization
    # =====================================================================
    def _source(self, project_key: str, document_id: str) -> SourceText:
        found = self.projects.document(project_key, document_id)
        if found is None:
            raise CatalogNotFoundError(f"The project document {document_id} is not available.")
        _project, document, text = found
        return SourceText(document_id, text, document.commit, document.version, _sha(text))

    def materialize(
        self,
        project_key: str,
        episode: str,
        chapter: int,
        decisions: Sequence[PlacementDecision] = (),
    ) -> MaterializedChapter:
        require_project_key(project_key)
        project = self.projects.project(project_key)
        if project is None:
            raise CatalogNotFoundError("That project is not discovered on this machine.")
        standing = next((e for e in project.episodes if e.code == episode), None)
        if standing is None:
            raise CatalogNotFoundError(f"The project has no episode {episode}.")
        by_role: dict[str, list[str]] = {}
        for role, doc_id, _required, _when in standing.sources:
            by_role.setdefault(role, []).append(doc_id)
        script_ids = by_role.get("base-panel-script") or [
            d for c, d in standing.documents if c == "panel-script"
        ]
        if not script_ids:
            raise CatalogInputError(f"{episode} has no approved panel script to materialize.")
        overlay_ids = by_role.get("production-overlay") or []
        beat_ids = [
            d.id
            for d in project.documents
            if d.category == "revision-beats" and d.lifecycle in {"APPROVED", "LOCKED"}
        ]
        context = tuple(
            (role, self._source(project_key, doc_id))
            for role, ids in sorted(by_role.items())
            if role not in {"base-panel-script", "production-overlay"}
            for doc_id in ids
        )
        names = tuple(
            sorted(
                self.session.execute(
                    select(CharacterProfile.display_name).where(
                        CharacterProfile.removed_at.is_(None)
                    )
                ).scalars()
            )
        )
        body = materialize_chapter(
            MaterializationInput(
                project_key=project_key,
                episode=episode,
                chapter=chapter,
                panel_script=self._source(project_key, script_ids[0]),
                overlay=self._source(project_key, overlay_ids[0]) if overlay_ids else None,
                beats=tuple(self._source(project_key, b) for b in sorted(beat_ids)),
                context_sources=context,
                decisions=tuple(decisions),
                character_names=names,
            )
        )
        existing = self.session.execute(
            select(MaterializedChapter).where(
                MaterializedChapter.project_key == project_key,
                MaterializedChapter.episode == episode,
                MaterializedChapter.chapter == chapter,
                MaterializedChapter.body_hash == body["hash"],
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing
        row = MaterializedChapter(
            project_key=project_key,
            episode=episode,
            chapter=chapter,
            materializer_version=MATERIALIZER_VERSION,
            body=body,
            body_hash=body["hash"],
        )
        self.session.add(row)
        self.session.flush()
        return row

    # =====================================================================
    # Profiles
    # =====================================================================
    def create_profile(
        self, project_key: str, name: str, body: dict[str, Any]
    ) -> ProductionProfile:
        require_project_key(project_key)
        version = (
            self.session.execute(
                select(func.coalesce(func.max(ProductionProfile.version), 0)).where(
                    ProductionProfile.project_key == project_key, ProductionProfile.name == name
                )
            ).scalar_one()
            + 1
        )
        row = ProductionProfile(
            project_key=project_key,
            name=clean_text(name, 120, field="Profile name"),
            version=version,
            status="DRAFT",
            body=body,
            body_hash=canonical_json_hash(body),
        )
        self.session.add(row)
        self.session.flush()
        return row

    def sample_profile(self, project_key: str, provider_id: str) -> ProductionProfile:
        """The draft profile a non-canon sample runs with, reused while unchanged.

        Grammar draws on every catalogued manga series with enough chapters;
        character rules come from what each character's notes forbid.
        """
        series = sorted(
            key
            for key, count in self.session.execute(
                select(CatalogUnit.series_key, func.count())
                .where(
                    CatalogUnit.kind == UnitKind.MANGA_CHAPTER,
                    CatalogUnit.series_key.is_not(None),
                )
                .group_by(CatalogUnit.series_key)
            ).all()
            if key and count >= 5
        )
        rules: dict[str, Any] = {}
        for character in self.session.execute(
            select(CharacterProfile).where(CharacterProfile.removed_at.is_(None))
        ).scalars():
            forbidden = self.corpus.forbidden(character)
            if forbidden:
                accessories = self.corpus.forbidden_accessories(forbidden)
                rules[character.display_name] = {
                    "forbidden": forbidden,
                    "forbidden_accessories": accessories,
                }
        body = {
            "backend": {"provider_id": provider_id, "width": 1024, "height": 1456},
            "reference_policy": {"per_character": 6, "use_candidates": True, "stylization": 1},
            "character_rules": rules,
            "grammar": {"series": series, "pool": min(40, len(series)), "limit": 6},
            "setting": {"environment_tags": []},
        }
        name = f"{project_key}-manga-sample"[:120]
        latest = self.session.execute(
            select(ProductionProfile)
            .where(ProductionProfile.project_key == project_key, ProductionProfile.name == name)
            .order_by(ProductionProfile.version.desc())
            .limit(1)
        ).scalar_one_or_none()
        if latest is not None and latest.body_hash == canonical_json_hash(body):
            return latest
        return self.create_profile(project_key, name, body)

    def start_sample(
        self,
        project_key: str,
        episode: str,
        chapter: int,
        *,
        decisions: Sequence[PlacementDecision] = (),
        provider_id: str = "fake.deterministic-page",
    ) -> ProductionRun:
        """START NON-CANON SAMPLE: one chapter, a draft profile, never canon."""
        profile = self.sample_profile(project_key, provider_id)
        return self.start_run(
            project_key,
            episode,
            purpose=RoughPurpose.NON_CANON_SAMPLE,
            profile_id=profile.id,
            chapters=[chapter],
            decisions=decisions,
        )

    # =====================================================================
    # Runs
    # =====================================================================
    def creative_readiness(
        self, project_key: str, episode: str, chapters: Sequence[MaterializedChapter]
    ) -> list[dict[str, Any]]:
        """Why canonical production of this episode may not start yet ([] = ready)."""
        reasons: list[dict[str, Any]] = []
        project = self.projects.project(project_key)
        standing = (
            next((e for e in project.episodes if e.code == episode), None) if project else None
        )
        if standing is None:
            return [{"kind": "EPISODE", "detail": f"{episode} is not on the project board"}]
        for role in standing.missing_sources:
            reasons.append(
                {"kind": "SOURCE_MISSING", "key": role, "detail": "required source missing"}
            )
        season = standing.season
        for doc in project.documents if project else ():
            if (
                doc.category == "review-checklist"
                and doc.applies_to == f"season:{season}"
                and doc.lifecycle not in {"APPROVED", "LOCKED", "SUPERSEDED", "ARCHIVED"}
            ):
                reasons.append(
                    {
                        "kind": "CREATIVE_REVIEW_PENDING",
                        "key": doc.id,
                        "detail": f"{doc.title} is {doc.lifecycle}: its additions are not final",
                    }
                )
        for chapter in chapters:
            unplaced = chapter.body["insertions"]["unplaced"]
            for item in unplaced:
                reasons.append(
                    {
                        "kind": "INSERTION_UNPLACED",
                        "key": item["item_key"],
                        "detail": f"overlay item has no placement: {item['text'][:120]}",
                    }
                )
            for placed in chapter.body["insertions"]["placed_in_chapter"]:
                if placed["status"] != "CONFIRMED":
                    reasons.append(
                        {
                            "kind": "INSERTION_UNCONFIRMED",
                            "key": placed["item_key"],
                            "detail": "placement is proposed, not confirmed by the creator",
                        }
                    )
        return reasons

    def start_run(
        self,
        project_key: str,
        episode: str,
        *,
        purpose: RoughPurpose,
        profile_id: uuid.UUID,
        chapters: Sequence[int],
        decisions: Sequence[PlacementDecision] = (),
    ) -> ProductionRun:
        if purpose not in APPROVAL_FOR and purpose is not RoughPurpose.WORKFLOW_TEST:
            raise CatalogInputError(
                "A production run is a NON_CANON_SAMPLE, PRODUCTION or chapter preview."
            )
        preview = purpose is RoughPurpose.WORKFLOW_TEST
        profile = self.session.get(ProductionProfile, profile_id)
        if profile is None or profile.project_key != project_key:
            raise CatalogNotFoundError("That production profile does not exist for the project.")
        materialized = [self.materialize(project_key, episode, c, decisions) for c in chapters]
        if purpose is RoughPurpose.PRODUCTION:
            if profile.status != "PROMOTED":
                raise CatalogConflictError(
                    "Canonical production uses a PROMOTED profile - pass a sample first."
                )
            reasons = self.creative_readiness(project_key, episode, materialized)
            if reasons:
                raise CatalogConflictError(
                    "Canonical production cannot start: "
                    + "; ".join(f"{r['kind']}: {r.get('detail', '')}" for r in reasons)
                )
        run = ProductionRun(
            project_key=project_key,
            episode=episode,
            chapter=chapters[0] if len(chapters) == 1 else None,
            purpose=purpose,
            profile_id=profile.id,
            status="OPEN",
        )
        self.session.add(run)
        self.session.flush()
        self._continuity(run, profile, reason="run started", approved=[])
        sequence = 0
        for chapter in materialized:
            for page in chapter.body["pages"]:
                sequence += 1
                artifact = RoughArtifact(
                    project_key=project_key,
                    episode=episode,
                    chapter=chapter.chapter,
                    page=sequence,
                    panel=None,
                    kind=RoughArtifactKind.PAGE,
                    purpose=purpose,
                    production_run_id=run.id,
                    title=f"{page['page_key']} (integrated p{page['integrated_page']})",
                    panel_script_document=(chapter.body["sources"]["panel_script"] or {}).get(
                        "document_id"
                    ),
                    panel_script_version=(chapter.body["sources"]["panel_script"] or {}).get(
                        "version"
                    ),
                    brief=" ".join(page["directions"])[:8000],
                )
                self.session.add(artifact)
                self.session.flush()
                row = ProductionPage(
                    run_id=run.id,
                    sequence=sequence,
                    materialized_chapter_id=chapter.id,
                    page_key=page["page_key"],
                    page_hash=page["page_hash"],
                    artifact_id=artifact.id,
                    # A chapter preview renders every page for QA; nothing waits.
                    state="READY" if sequence == 1 or preview else "WAITING",
                    reasons=[],
                )
                self.session.add(row)
                self.session.flush()
                planned = self._with_plan(row, page)
                self._record_dependencies(row, planned, profile)
                self._check_grounding(row, planned)
        self.session.flush()
        return run

    # =====================================================================
    # Pages
    # =====================================================================
    def pages(self, run_id: uuid.UUID) -> list[ProductionPage]:
        return list(
            self.session.execute(
                select(ProductionPage)
                .where(ProductionPage.run_id == run_id)
                .order_by(ProductionPage.sequence)
            ).scalars()
        )

    def page_body(self, page: ProductionPage) -> dict[str, Any]:
        chapter = self.session.get(MaterializedChapter, page.materialized_chapter_id)
        assert chapter is not None
        raw = next(p for p in chapter.body["pages"] if p["page_key"] == page.page_key)
        return self._with_plan(page, raw)

    def _known_characters(self) -> list[str]:
        return sorted(
            self.session.execute(
                select(CharacterProfile.display_name).where(CharacterProfile.removed_at.is_(None))
            ).scalars()
        )

    def _with_plan(self, page: ProductionPage, raw: dict[str, Any]) -> dict[str, Any]:
        """The page with its derived plan; the plan's cast drives everything downstream."""
        plan = page_plan(raw, self._known_characters(), page.cast_override or None)
        return {**raw, "characters": plan["characters_present"], "plan": plan}

    def set_cast_override(
        self,
        page_id: uuid.UUID,
        *,
        add: Sequence[str] = (),
        remove: Sequence[str] = (),
        primary: str | None = None,
        note: str = "",
    ) -> ProductionPage:
        """A person corrects who appears on a page. Recorded, never guessed."""
        page = self.session.get(ProductionPage, page_id)
        if page is None:
            raise CatalogNotFoundError("That production page does not exist.")
        known = set(self._known_characters())
        unknown = [n for n in [*add, *remove, *([primary] if primary else [])] if n not in known]
        if unknown:
            raise CatalogInputError(f"Unknown characters: {', '.join(unknown)}.")
        page.cast_override = (
            {"add": list(add), "remove": list(remove), "primary": primary, "note": note[:500]}
            if add or remove or primary
            else {}
        )
        body = self.page_body(page)
        self._check_grounding(page, body)
        self.session.flush()
        return page

    def current_continuity(self, run_id: uuid.UUID) -> ContinuityState:
        state = self.session.execute(
            select(ContinuityState)
            .where(ContinuityState.run_id == run_id)
            .order_by(ContinuityState.version.desc())
            .limit(1)
        ).scalar_one()
        return state

    def next_page(self, run_id: uuid.UUID) -> ProductionPage | None:
        """The first page not yet approved, in reading order."""
        return next((p for p in self.pages(run_id) if p.state != "APPROVED"), None)

    def _grounding(self, run: ProductionRun, name: str) -> dict[str, Any] | None:
        """Grounding from the character corpus: confirmed, high-authority observations."""
        character = self.corpus.by_name(name)
        if character is None:
            return None
        self.corpus.sync_curated(character.id)
        readiness = self.corpus.readiness(character.id)
        return {
            "character": {"id": str(character.id), "name": name},
            "grounded": readiness["grounded"],
            "ungrounded": readiness["ungrounded"],
            "readiness": readiness,
            **self.corpus.grounding(character.id),
        }

    def _check_grounding(self, page: ProductionPage, body: dict[str, Any]) -> None:
        run = self.session.get(ProductionRun, page.run_id)
        assert run is not None
        reasons = [r for r in page.reasons if r.get("kind") != "MISSING_REQUIRED_REFERENCE"]
        for name in body["characters"]:
            manifest = self._grounding(run, name)
            if manifest is None or not manifest["grounded"]:
                reasons.append(
                    {
                        "kind": "MISSING_REQUIRED_REFERENCE",
                        "key": name,
                        "detail": (
                            f"{name} has no character profile"
                            if manifest is None
                            else f"{name} lacks grounded {', '.join(manifest['ungrounded'])}"
                        ),
                    }
                )
        page.reasons = reasons
        blocked = any(r["kind"] == "MISSING_REQUIRED_REFERENCE" for r in reasons)
        if run.purpose is RoughPurpose.WORKFLOW_TEST:
            return  # a preview reports missing references as QA warnings instead
        if blocked and page.state in {"READY", "WAITING", "BLOCKED"}:
            page.state = "BLOCKED"
        elif not blocked and page.state == "BLOCKED":
            previous = self._previous(page)
            page.state = "READY" if previous is None or previous.state == "APPROVED" else "WAITING"

    def _previous(self, page: ProductionPage) -> ProductionPage | None:
        return self.session.execute(
            select(ProductionPage).where(
                ProductionPage.run_id == page.run_id, ProductionPage.sequence == page.sequence - 1
            )
        ).scalar_one_or_none()

    def _character_fingerprint(self, run: ProductionRun, name: str) -> str:
        character = self.corpus.by_name(name)
        if character is None:
            return _sha("missing")
        self.corpus.sync_curated(character.id)
        return canonical_json_hash({"confirmed": self.corpus.fingerprint_rows(character.id)})

    def _record_dependencies(
        self, page: ProductionPage, body: dict[str, Any], profile: ProductionProfile
    ) -> None:
        run = self.session.get(ProductionRun, page.run_id)
        assert run is not None
        wanted: dict[tuple[str, str], str] = {
            ("MATERIALIZED_PAGE", page.page_key): body["page_hash"],
            ("PROFILE", profile.name): profile.body_hash,
        }
        lineage = body["lineage"]
        docs = [lineage] if lineage.get("document_id") else []
        if lineage.get("overlay"):
            docs.append(lineage["overlay"])
        for doc in docs:
            wanted[("SOURCE_DOCUMENT", doc["document_id"])] = doc.get("content_hash") or _sha(
                str(doc.get("commit"))
            )
        for name in body["characters"]:
            wanted[("CHARACTER_REFERENCES", name)] = self._character_fingerprint(run, name)
        existing = {
            (d.kind, d.key): d
            for d in self.session.execute(
                select(PageDependency).where(PageDependency.page_id == page.id)
            ).scalars()
        }
        for (kind, key), version in wanted.items():
            row = existing.get((kind, key))
            if row is None:
                self.session.add(
                    PageDependency(page_id=page.id, kind=kind, key=key, version_hash=version)
                )
            else:
                row.version_hash = version

    def _continuity(
        self,
        run: ProductionRun,
        profile: ProductionProfile,
        *,
        reason: str,
        approved: list[dict[str, Any]],
    ) -> ContinuityState:
        version = (
            self.session.execute(
                select(func.coalesce(func.max(ContinuityState.version), 0)).where(
                    ContinuityState.run_id == run.id
                )
            ).scalar_one()
            + 1
        )
        body = {
            "run_id": str(run.id),
            "profile": {"id": str(profile.id), "name": profile.name, "version": profile.version},
            "character_rules": profile.body.get("character_rules", {}),
            "setting": profile.body.get("setting", {}),
            "approved_pages": approved,
        }
        state = ContinuityState(
            run_id=run.id,
            version=version,
            body=body,
            body_hash=canonical_json_hash(body),
            reason=reason[:300],
        )
        self.session.add(state)
        self.session.flush()
        return state

    # -- assembling and requesting an attempt -------------------------------
    def assemble(self, page: ProductionPage) -> dict[str, Any]:
        """Everything the page will be generated from, before anything is generated."""
        run = self.session.get(ProductionRun, page.run_id)
        profile = self.session.get(ProductionProfile, run.profile_id) if run else None
        assert run is not None and profile is not None
        body = self.page_body(page)
        continuity = self.current_continuity(run.id)
        characters = []
        inputs: list[dict[str, Any]] = []
        policy = profile.body.get("reference_policy") or {}
        per_character = int(policy.get("per_character", 6))
        candidates_allowed = bool(
            policy.get("use_candidates", run.purpose is RoughPurpose.NON_CANON_SAMPLE)
        )
        for name in body["characters"]:
            grounding = self._grounding(run, name)
            if grounding is None or not grounding["grounded"]:
                continue
            character_id = uuid.UUID(grounding["character"]["id"])
            need = page_needs(body, name)
            found = self.corpus.retrieve(
                character_id,
                need,
                limit=per_character,
                include_candidates=candidates_allowed,
                include_supplemental=bool(policy.get("use_supplemental", False)),
            )
            rule = (profile.body.get("character_rules") or {}).get(name, {})
            characters.append(
                {
                    "name": name,
                    "character_id": str(character_id),
                    "grounding": grounding["grounding"],
                    "stylization": grounding["stylization"],
                    "readiness": grounding["readiness"],
                    "need": need,
                    "observations": found["observations"],
                    "stylization_observations": found["stylization"],
                    "available_observations": found["available"],
                    "forbidden": self.corpus.forbidden(self.corpus.character(character_id)),
                    "rules": rule,
                }
            )
            for entry in found["observations"]:
                inputs.append(
                    {
                        "role": BundleRole.CANON,
                        "observation_id": entry["id"],
                        "reference_id": entry["reference_id"],
                        "character": name,
                        "authority": entry["authority"],
                        "status": entry["status"],
                        "facets": entry["facets"],
                        "why": entry["why"],
                    }
                )
            for entry in found["stylization"][: int(policy.get("stylization", 1))]:
                inputs.append(
                    {
                        "role": BundleRole.STYLE,
                        "observation_id": entry["id"],
                        "reference_id": entry["reference_id"],
                        "character": name,
                        "authority": entry["authority"],
                        "status": entry["status"],
                        "facets": entry["facets"],
                        "why": ["stylization - never identity"],
                    }
                )
        grammar_policy = profile.body.get("grammar") or {}
        references: dict[str, list[dict[str, Any]]] = {
            "grammar": [],
            "technique": [],
            "environment_pages": [],
        }
        if self.grammar_candidates is not None and grammar_policy.get("limit", 0) > 0:
            candidates = self.grammar_candidates(
                grammar_policy.get("series", []), int(grammar_policy.get("pool", 40))
            )
            ranked = rank_grammar(body["intents"], candidates, int(grammar_policy["limit"]))
            world = self._cast_series([c["character_id"] for c in characters])
            world_candidates = self.grammar_candidates(sorted(world), 12) if world else []
            intents = set(body["intents"])
            references = page_references(
                body["intents"],
                ranked,
                candidates,
                world_candidates,
                world_series=world,
                environment_wanted=bool(
                    body["plan"]["environment_tags"]
                    or intents & {"nature_exterior", "large_composition", "back_shot"}
                ),
            )
        grammar = references["grammar"]
        environment_tags = sorted(
            set((profile.body.get("setting") or {}).get("environment_tags", []))
            | set(setting_tags(" ".join(body["directions"]) + " " + str(body.get("scene") or "")))
        )
        environment = self._environment_references(environment_tags, limit=4)
        gaps = []
        if environment_tags and not environment:
            gaps.append(
                "no curated environment references match "
                + ", ".join(environment_tags)
                + " - the setting canon governs; add references to improve"
            )
        return {
            "schema": "continuum.page-bundle/1",
            "page": body,
            "run": {"id": str(run.id), "purpose": run.purpose.value},
            "profile": {
                "id": str(profile.id),
                "name": profile.name,
                "version": profile.version,
                "hash": profile.body_hash,
            },
            "continuity": {
                "id": str(continuity.id),
                "version": continuity.version,
                "hash": continuity.body_hash,
                "approved_pages": continuity.body["approved_pages"],
                "character_rules": continuity.body["character_rules"],
                "setting": continuity.body["setting"],
            },
            "plan": body["plan"],
            "characters": characters,
            "canon_inputs": [{**i, "role": i["role"].value} for i in inputs],
            "grammar": grammar,
            "technique": references["technique"],
            "environment": environment,
            "environment_pages": references["environment_pages"],
            "gaps": gaps,
        }

    def _cast_series(self, character_ids: Sequence[str]) -> set[str]:
        """The source series the cast's corpus comes from (their source world)."""
        if not character_ids:
            return set()
        return {
            key
            for key in self.session.execute(
                select(CharacterObservation.series_key)
                .where(
                    CharacterObservation.character_id.in_([uuid.UUID(c) for c in character_ids]),
                    CharacterObservation.series_key.is_not(None),
                )
                .distinct()
            ).scalars()
            if key
        }

    def _environment_references(self, tags: Sequence[str], limit: int) -> list[dict[str, Any]]:
        if not tags:
            return []
        rows = self.session.execute(
            select(ReferenceItem, ReferenceDescriptor.value)
            .join(ReferenceDescriptor, ReferenceDescriptor.reference_id == ReferenceItem.id)
            .where(
                ReferenceItem.removed_at.is_(None),
                func.lower(ReferenceDescriptor.value).in_([t.lower() for t in tags]),
            )
            .order_by(ReferenceItem.created_at, ReferenceItem.id)
        ).all()
        found: dict[uuid.UUID, dict[str, Any]] = {}
        for item, value in rows:
            entry = found.setdefault(
                item.id,
                {
                    "reference_id": str(item.id),
                    "locator": item.locator,
                    "label": item.label,
                    "origin": item.origin.value,
                    "matched": [],
                    "teaches": ["perspective", "spatial_composition", "atmosphere"],
                },
            )
            entry["matched"].append(value)
        return list(found.values())[:limit]

    def request_page_attempt(
        self, page_id: uuid.UUID, *, seed: int | None = None, notes: str = ""
    ) -> RoughAttempt:
        page = self.session.get(ProductionPage, page_id)
        if page is None:
            raise CatalogNotFoundError("That production page does not exist.")
        if page.state in {"WAITING", "BLOCKED"}:
            detail = "; ".join(r.get("detail", "") for r in page.reasons) or (
                "the page before it is not approved yet"
            )
            raise CatalogConflictError(f"Page {page.sequence} is {page.state}: {detail}")
        run = self.session.get(ProductionRun, page.run_id)
        profile = self.session.get(ProductionProfile, run.profile_id) if run else None
        assert run is not None and profile is not None
        if run.status != "OPEN":
            raise CatalogConflictError("That run is closed.")
        if page.state == "STALE":
            chapter, body = self._current_pages(run).get(page.page_key, (None, None))
            if body is not None:
                body = self._with_plan(page, body)
            if chapter is None or body is None:
                raise CatalogConflictError(
                    f"Page {page.sequence} no longer exists in the committed sources."
                )
            page.materialized_chapter_id = chapter.id
            page.page_hash = body["page_hash"]
            self._record_dependencies(page, body, profile)
            page.reasons = [
                r for r in page.reasons if r.get("kind") == "MISSING_REQUIRED_REFERENCE"
            ]
            self._check_grounding(page, body)
            if any(r["kind"] == "MISSING_REQUIRED_REFERENCE" for r in page.reasons):
                raise CatalogConflictError(
                    f"Page {page.sequence} is missing required references: "
                    + "; ".join(r["detail"] for r in page.reasons)
                )
        # What this attempt is built from is what the page now depends on.
        self._record_dependencies(page, self.page_body(page), profile)
        bundle = self.assemble(page)
        artifact = self.rough._lock_artifact(page.artifact_id)
        inputs: list[dict[str, Any]] = []
        character_ids = {c["name"]: uuid.UUID(c["character_id"]) for c in bundle["characters"]}
        for entry in bundle["canon_inputs"]:
            observation = self.corpus.observation(uuid.UUID(entry["observation_id"]))
            resolved = self.corpus.resolve(observation)
            if resolved is None:
                continue
            locator, reference_id = resolved
            item = self.catalog.reference(reference_id) if reference_id else None
            inputs.append(
                {
                    "position": len(inputs),
                    "role": BundleRole(entry["role"]),
                    "reference_id": reference_id,
                    "locator": locator,
                    "unit_index": item.unit_index if item else None,
                    "region": None,
                    "character_id": character_ids[entry["character"]],
                    "outfit_id": None,
                    "aspect": None,
                    "label": f"{entry['character']} - {entry['authority'].lower()}"[:300],
                    "provenance": {
                        "observation_id": entry["observation_id"],
                        "authority": entry["authority"],
                        "status": entry["status"],
                        "facets": entry["facets"],
                        "why": entry["why"],
                        **({"origin": item.origin.value} if item else {"kind": "source_page"}),
                    },
                }
            )
        for offset, grammar in enumerate(bundle["grammar"], start=len(inputs)):
            inputs.append(
                {
                    "position": offset,
                    "role": BundleRole.GRAMMAR,
                    "reference_id": None,
                    "locator": grammar["locator"],
                    "unit_index": None,
                    "region": None,
                    "character_id": None,
                    "outfit_id": None,
                    "aspect": None,
                    "label": f"grammar: {grammar['label']}"[:300],
                    "provenance": {
                        k: grammar.get(k)
                        for k in ("series_key", "score", "teaches", "structure", "why", "status")
                    }
                    | {"identity_evidence": False},
                }
            )
        for page_ref in [*bundle.get("technique", []), *bundle.get("environment_pages", [])]:
            inputs.append(
                {
                    "position": len(inputs),
                    "role": BundleRole(page_ref["role"]),
                    "reference_id": None,
                    "locator": page_ref["locator"],
                    "unit_index": None,
                    "region": None,
                    "character_id": None,
                    "outfit_id": None,
                    "aspect": None,
                    "label": f"{page_ref['role'].lower()}: {page_ref['label']}"[:300],
                    "provenance": {
                        k: page_ref.get(k)
                        for k in ("series_key", "teaches", "structure", "why", "status")
                    }
                    | {"identity_evidence": False},
                }
            )
        for offset, env in enumerate(bundle["environment"], start=len(inputs)):
            inputs.append(
                {
                    "position": offset,
                    "role": BundleRole.ENVIRONMENT,
                    "reference_id": uuid.UUID(env["reference_id"]),
                    "locator": env["locator"],
                    "unit_index": None,
                    "region": None,
                    "character_id": None,
                    "outfit_id": None,
                    "aspect": None,
                    "label": f"environment: {env['label']}"[:300],
                    "provenance": {"matched": env["matched"], "teaches": env["teaches"]},
                }
            )
        backend = profile.body.get("backend") or {}
        intent: dict[str, Any] = {
            "schema": "continuum.page-recipe/1",
            "mode": "NEW_GENERATION",
            "target": {
                "project_key": run.project_key,
                "episode": run.episode,
                "chapter": artifact.chapter,
                "page": artifact.page,
                "panel": None,
                "kind": "PAGE",
            },
            "panel_script": {
                "document": artifact.panel_script_document,
                "version": artifact.panel_script_version,
            },
            "brief": clean_text(notes or artifact.brief, 8000, field="Brief"),
            "characters": [],
            "visual_modes": [],
            "bundle": [],
            "source_plates": [],
            "plate_region": None,
            "operations": [],
            "protected_regions": [],
            "placements": [],
            "page_bundle": bundle,
        }
        previous = self.session.execute(
            select(RoughAttempt)
            .where(RoughAttempt.production_page_id == page.id)
            .order_by(RoughAttempt.attempt.desc())
            .limit(1)
        ).scalar_one_or_none()
        width, height = (int(backend.get("width", 1024)), int(backend.get("height", 1456)))
        attempt = self.rough._create_attempt(
            artifact,
            intent=intent,
            inputs=inputs,
            seed=seed,
            width=width,
            height=height,
            workflow=str(backend.get("workflow", PAGE_WORKFLOW)),
            extra_execution={
                "provider_id": (
                    "fake.deterministic-page"
                    if run.purpose is RoughPurpose.WORKFLOW_TEST
                    else backend.get("provider_id", "fake.deterministic-page")
                ),
                "backend_settings": backend.get("settings", {}),
            },
            parent=previous,
        )
        attempt.production_page_id = page.id
        attempt.continuity_state_id = uuid.UUID(bundle["continuity"]["id"])
        attempt.profile_id = profile.id
        for approved in bundle["continuity"]["approved_pages"]:
            key = f"page:{approved['sequence']}"
            existing = self.session.execute(
                select(PageDependency).where(
                    PageDependency.page_id == page.id,
                    PageDependency.kind == "CONTINUITY",
                    PageDependency.key == key,
                )
            ).scalar_one_or_none()
            if existing is None:
                self.session.add(
                    PageDependency(
                        page_id=page.id,
                        kind="CONTINUITY",
                        key=key,
                        version_hash=approved["master_sha256"],
                    )
                )
            else:
                existing.version_hash = approved["master_sha256"]
        if page.state in {"READY", "STALE"}:
            page.state = "IN_REVIEW"
        self.session.flush()
        return attempt

    # -- review ---------------------------------------------------------------
    def review_page(
        self,
        attempt_id: uuid.UUID,
        decision: ReviewDecision,
        *,
        notes: str = "",
        seed: int | None = None,
    ) -> RoughAttempt | None:
        """Record a review of a page attempt; approving advances the run."""
        attempt = self.rough.attempt(attempt_id)
        if attempt.production_page_id is None:
            raise CatalogInputError("That attempt does not belong to a production page.")
        page = self.session.get(ProductionPage, attempt.production_page_id)
        run = self.session.get(ProductionRun, page.run_id) if page else None
        assert page is not None and run is not None
        if decision is ReviewDecision.REGENERATE:
            self.rough.review(attempt_id, ReviewDecision.REJECT, notes=notes or "regenerate")
            return self.request_page_attempt(page.id, seed=seed, notes="")
        if run.purpose is RoughPurpose.WORKFLOW_TEST and decision in (
            ReviewDecision.TECHNICAL_PASS,
            ReviewDecision.CREATIVE_APPROVE,
            ReviewDecision.FINAL_APPROVE,
        ):
            raise CatalogInputError(
                "A chapter technical preview is never approved; review the sample run instead."
            )
        if decision is APPROVAL_FOR.get(run.purpose):
            self.rough.review(attempt_id, decision, notes=notes)
            master = self._derivative(attempt.id, "COMPOSITION_MASTER")
            if master is None:
                raise CatalogConflictError("That attempt has no composition master yet.")
            page.state = "APPROVED"
            page.approved_attempt_id = attempt.id
            page.approved_at = _now()
            page.reasons = [
                r for r in page.reasons if r.get("kind") == "MISSING_REQUIRED_REFERENCE"
            ]
            profile = self.session.get(ProductionProfile, run.profile_id)
            assert profile is not None
            approved = [
                entry
                for entry in self.current_continuity(run.id).body["approved_pages"]
                if entry["sequence"] != page.sequence
            ]
            approved.append(
                {
                    "sequence": page.sequence,
                    "page_key": page.page_key,
                    "attempt_id": str(attempt.id),
                    "master_sha256": master.content_hash,
                    "bw_sha256": (self._derivative(attempt.id, "BW_FINISH") or master).content_hash,
                    "color_sha256": (
                        self._derivative(attempt.id, "COLOR_FINISH") or master
                    ).content_hash,
                    "output_class": attempt.output_class.value if attempt.output_class else None,
                }
            )
            approved.sort(key=lambda e: e["sequence"])
            self._continuity(
                run, profile, reason=f"page {page.sequence} approved", approved=approved
            )
            if run.purpose is RoughPurpose.PRODUCTION:
                self._learn_from_approved(page, attempt)
            following = self.session.execute(
                select(ProductionPage).where(
                    ProductionPage.run_id == run.id, ProductionPage.sequence == page.sequence + 1
                )
            ).scalar_one_or_none()
            if following is not None and following.state == "WAITING":
                following.state = "READY"
            self.session.flush()
            return None
        if decision in (ReviewDecision.CREATIVE_APPROVE, ReviewDecision.FINAL_APPROVE):
            raise CatalogInputError(
                "A sample page is accepted with a technical pass; it is never creative approval."
            )
        self.rough.review(attempt_id, decision, notes=notes)
        self.session.flush()
        return None

    def _learn_from_approved(self, page: ProductionPage, attempt: RoughAttempt) -> None:
        """A creatively approved canonical page becomes project-created character evidence.

        Only approved production pages: a sample, a technical pass, a rejected or a
        superseded attempt never enters the reference pool.
        """
        body = self.page_body(page)
        item = self.rough.promote_to_continuity(
            attempt.id, label=f"{page.page_key} - approved page", notes="approved project page"
        )
        for name in body["characters"]:
            character = self.corpus.by_name(name)
            if character is None:
                continue
            self.corpus.record_approved_output(
                character.id,
                item.id,
                facets=page_needs(body, name)["facets"],
                evidence={
                    "attempt_id": str(attempt.id),
                    "run_id": str(page.run_id),
                    "page_key": page.page_key,
                    "label": f"{page.page_key} approved",
                },
            )

    def _derivative(self, attempt_id: uuid.UUID, kind: str) -> AttemptDerivative | None:
        return next((d for d in self.rough.derivatives(attempt_id) if d.kind.value == kind), None)

    # -- invalidation -----------------------------------------------------------
    def _current_pages(
        self, run: ProductionRun
    ) -> dict[str, tuple[MaterializedChapter, dict[str, Any]]]:
        """Each page of the run as the committed sources materialize it *now*."""
        chapters = {
            c.chapter: c
            for c in self.session.execute(
                select(MaterializedChapter).where(
                    MaterializedChapter.id.in_(
                        [p.materialized_chapter_id for p in self.pages(run.id)]
                    )
                )
            ).scalars()
        }
        keys = ("item_key", "chapter", "after_base_page", "status", "author", "note")
        current: dict[str, tuple[MaterializedChapter, dict[str, Any]]] = {}
        for number, chapter in chapters.items():
            decisions = tuple(
                PlacementDecision(**{k: d[k] for k in keys}) for d in chapter.body["decisions"]
            )
            fresh = self.materialize(run.project_key, run.episode, number, decisions)
            for body in fresh.body["pages"]:
                current[body["page_key"]] = (fresh, body)
        return current

    def _has_work(self, page: ProductionPage) -> bool:
        return (
            page.approved_attempt_id is not None
            or self.session.execute(
                select(RoughAttempt.id).where(RoughAttempt.production_page_id == page.id).limit(1)
            ).first()
            is not None
        )

    def refresh_staleness(self, run_id: uuid.UUID) -> list[dict[str, Any]]:
        """Compare what each page was built from with what is current; mark STALE.

        Only a page with work on it (an attempt, or approved art) can be stale.
        A page nothing was drawn for yet simply follows its sources: its
        dependencies are re-recorded and its grounding re-checked. A changed
        profile is reported on such a page but changes nothing - the run keeps
        the profile it started with.
        """
        run = self.session.get(ProductionRun, run_id)
        if run is None:
            raise CatalogNotFoundError("That run does not exist.")
        profile = self.session.get(ProductionProfile, run.profile_id)
        assert profile is not None
        current_pages = self._current_pages(run)
        latest_profile = self.session.execute(
            select(ProductionProfile)
            .where(
                ProductionProfile.project_key == run.project_key,
                ProductionProfile.name == profile.name,
            )
            .order_by(ProductionProfile.version.desc())
            .limit(1)
        ).scalar_one()
        approved_masters = {
            p.sequence: (self._derivative(p.approved_attempt_id, "COMPOSITION_MASTER").content_hash)  # type: ignore[union-attr]
            for p in self.pages(run_id)
            if p.approved_attempt_id is not None
        }
        changes = []
        for page in self.pages(run_id):
            chapter, body = current_pages.get(page.page_key, (None, None))
            if body is not None:
                body = self._with_plan(page, body)
            worked = self._has_work(page)
            if not worked and chapter is not None and body is not None:
                page.materialized_chapter_id = chapter.id
                page.page_hash = body["page_hash"]
                self._record_dependencies(page, body, profile)
            if body is not None and page.state != "APPROVED":
                self._check_grounding(page, body)
            stale: list[dict[str, Any]] = []
            for dep in self.session.execute(
                select(PageDependency).where(PageDependency.page_id == page.id)
            ).scalars():
                current: str | None = None
                if dep.kind == "MATERIALIZED_PAGE":
                    current = body["page_hash"] if body else "removed"
                elif dep.kind == "PROFILE":
                    current = latest_profile.body_hash
                elif dep.kind == "CHARACTER_REFERENCES":
                    current = self._character_fingerprint(run, dep.key)
                elif dep.kind == "SOURCE_DOCUMENT" and body is not None:
                    lineage = body["lineage"]
                    docs = [lineage] if lineage.get("document_id") else []
                    docs += [lineage["overlay"]] if lineage.get("overlay") else []
                    match = next((d for d in docs if d["document_id"] == dep.key), None)
                    current = (
                        match.get("content_hash") if match else "removed"
                    ) or dep.version_hash
                elif dep.kind == "CONTINUITY":
                    sequence = int(dep.key.split(":", 1)[1])
                    current = approved_masters.get(sequence, "unapproved")
                if current is not None and current != dep.version_hash:
                    stale.append(
                        {
                            "kind": dep.kind,
                            "key": dep.key,
                            "old": dep.version_hash,
                            "new": current,
                            "detail": f"{dep.kind.lower().replace('_', ' ')} {dep.key} changed",
                        }
                    )
            kept = [r for r in page.reasons if r.get("kind") == "MISSING_REQUIRED_REFERENCE"]
            page.reasons = kept + stale
            if stale and worked:
                if page.state != "WAITING":
                    page.state = "STALE"
                changes.append(
                    {"sequence": page.sequence, "page_key": page.page_key, "reasons": stale}
                )
        self.session.flush()
        return changes

    # -- chapter technical preview -----------------------------------------------------
    def start_preview(self, run_id: uuid.UUID) -> ProductionRun:
        """A CHAPTER TECHNICAL PREVIEW of a run's chapter: every page planned and test-rendered.

        Separate from the run it previews: its pages are never approved, never
        join continuity, never count, and it renders only with the test backend.
        """
        source = self.session.get(ProductionRun, run_id)
        if source is None:
            raise CatalogNotFoundError("That run does not exist.")
        pages = self.pages(run_id)
        chapters = {
            c.chapter: c
            for c in self.session.execute(
                select(MaterializedChapter).where(
                    MaterializedChapter.id.in_([p.materialized_chapter_id for p in pages])
                )
            ).scalars()
        }
        keys = ("item_key", "chapter", "after_base_page", "status", "author", "note")
        decisions = [
            PlacementDecision(**{k: d[k] for k in keys})
            for chapter in chapters.values()
            for d in chapter.body["decisions"]
        ]
        preview = self.start_run(
            source.project_key,
            source.episode,
            purpose=RoughPurpose.WORKFLOW_TEST,
            profile_id=source.profile_id,
            chapters=sorted(chapters),
            decisions=decisions,
        )
        for page in self.pages(preview.id):
            if page.state == "BLOCKED":
                page.state = "READY"
        self.session.flush()
        return preview

    def render_preview(self, run_id: uuid.UUID) -> int:
        """Queue a test render for every preview page that has none pending or drawn."""
        run = self.session.get(ProductionRun, run_id)
        if run is None or run.purpose is not RoughPurpose.WORKFLOW_TEST:
            raise CatalogConflictError("Only a chapter technical preview renders every page.")
        queued = 0
        for page in self.pages(run_id):
            attempts = self.rough.attempts(page.artifact_id)
            if attempts and attempts[0].state in (AttemptState.QUEUED, AttemptState.GENERATED):
                continue
            if page.state == "BLOCKED":
                page.state = "READY"
            self.request_page_attempt(page.id)
            queued += 1
        self.session.flush()
        return queued

    def chapter_view(self, run_id: uuid.UUID) -> dict[str, Any]:
        """Every page of a run as a sequence: plan, bundle summary, test render, QA."""
        run = self.session.get(ProductionRun, run_id)
        if run is None:
            raise CatalogNotFoundError("That run does not exist.")
        entries: list[dict[str, Any]] = []
        for page in self.pages(run_id):
            bundle = self.assemble(page)
            body, plan = bundle["page"], bundle["plan"]
            attempts = self.rough.attempts(page.artifact_id)
            latest = attempts[0] if attempts else None
            drawn = next((a for a in attempts if a.state is not AttemptState.QUEUED), None)
            job = None
            if latest is not None and latest.job_id is not None:
                from continuum_db.models import Job

                row = self.session.get(Job, latest.job_id)
                if row is not None:
                    job = {
                        "status": row.status.value,
                        "blocked_reason": row.blocked_reason.value if row.blocked_reason else None,
                        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
                        "error": (row.last_error or {}).get("user_message"),
                    }
            lineage = body.get("lineage") or {}
            entries.append(
                {
                    "id": str(page.id),
                    "sequence": page.sequence,
                    "page_key": page.page_key,
                    "integrated_page": body.get("integrated_page"),
                    "base_page": body.get("base_page"),
                    "origin": body.get("origin"),
                    "scene": body.get("scene"),
                    "state": page.state,
                    "reasons": page.reasons,
                    "lineage": {
                        "document_id": lineage.get("document_id"),
                        "version": lineage.get("version"),
                        "overlay": (lineage.get("overlay") or {}).get("document_id"),
                        "insertion": (body.get("insertion") or {}).get("item_key"),
                    },
                    "plan": plan,
                    "dialogue": body.get("dialogue") or [],
                    "directions": body.get("directions") or [],
                    "characters": [
                        {
                            "name": c["name"],
                            "character_id": c["character_id"],
                            "grounded": c["readiness"]["grounded"],
                            "need": c["need"],
                            "observations": c["observations"],
                            "stylization": c["stylization_observations"],
                            "readiness": {
                                k: v["state"] for k, v in c["readiness"]["groups"].items()
                            },
                        }
                        for c in bundle["characters"]
                    ],
                    "grammar": bundle["grammar"],
                    "technique": bundle["technique"],
                    "environment": bundle["environment"],
                    "environment_pages": bundle["environment_pages"],
                    "gaps": bundle["gaps"],
                    "continuity_pages": len(bundle["continuity"]["approved_pages"]),
                    "render": {
                        "attempt_id": str(drawn.id) if drawn else None,
                        "latest_attempt_id": str(latest.id) if latest else None,
                        "state": latest.state.value if latest else None,
                        "output_class": drawn.output_class.value
                        if drawn and drawn.output_class
                        else None,
                        "content_hash": drawn.content_hash if drawn else None,
                        "created_at": latest.created_at.isoformat() if latest else None,
                        "job": job,
                    },
                }
            )
        qa = chapter_qa(entries)
        profile = self.session.get(ProductionProfile, run.profile_id)
        return {
            "run": {
                "id": str(run.id),
                "project_key": run.project_key,
                "episode": run.episode,
                "chapter": run.chapter,
                "purpose": run.purpose.value,
                "status": run.status,
                "profile": {"name": profile.name, "version": profile.version} if profile else None,
            },
            "pages": entries,
            "qa": qa,
        }

    # -- sample decision and profile promotion -------------------------------------
    def decide_sample(
        self, run_id: uuid.UUID, *, passed: bool, notes: str = ""
    ) -> ProductionProfile | None:
        """SAMPLE PASS promotes the profile (never the images); FAIL closes the sample."""
        run = self.session.get(ProductionRun, run_id)
        if run is None:
            raise CatalogNotFoundError("That run does not exist.")
        if run.purpose is not RoughPurpose.NON_CANON_SAMPLE or run.status != "OPEN":
            raise CatalogConflictError("Only an open non-canon sample can pass or fail.")
        run.decision_notes = clean_text(notes, 8000, field="Notes")
        run.decided_at = _now()
        if not passed:
            run.status = "SAMPLE_FAILED"
            self.session.flush()
            return None
        approved = [p for p in self.pages(run_id) if p.approved_attempt_id is not None]
        if not approved:
            raise CatalogConflictError("A sample with no approved page cannot pass.")
        for page in approved:
            attempt = self.rough.attempt(page.approved_attempt_id)  # type: ignore[arg-type]
            if attempt.output_class is not RenderOutput.ARTWORK_CANDIDATE:
                raise CatalogConflictError(
                    f"Page {page.sequence} was drawn by a test renderer; a sample of test "
                    "renders cannot pass. Generate it with an artwork backend."
                )
        profile = self.session.get(ProductionProfile, run.profile_id)
        assert profile is not None
        run.status = "SAMPLE_PASSED"
        body = {
            **profile.body,
            "proven_by": {
                "run_id": str(run.id),
                "episode": run.episode,
                "chapter": run.chapter,
                "approved_pages": len(approved),
                "decided_at": run.decided_at.isoformat(),
            },
        }
        promoted = ProductionProfile(
            project_key=profile.project_key,
            name=profile.name,
            version=self.session.execute(
                select(func.max(ProductionProfile.version)).where(
                    ProductionProfile.project_key == profile.project_key,
                    ProductionProfile.name == profile.name,
                )
            ).scalar_one()
            + 1,
            status="PROMOTED",
            body=body,
            body_hash=canonical_json_hash(body),
            promoted_from_run=run.id,
            promoted_at=run.decided_at,
            notes=run.decision_notes,
        )
        self.session.add(promoted)
        self.session.flush()
        return promoted

    def canonical_start_readiness(
        self,
        project_key: str,
        episode: str,
        profile_id: uuid.UUID,
        chapters: Sequence[int],
        decisions: Sequence[PlacementDecision] = (),
    ) -> list[dict[str, Any]]:
        profile = self.session.get(ProductionProfile, profile_id)
        reasons: list[dict[str, Any]] = []
        if profile is None or profile.status != "PROMOTED":
            reasons.append({"kind": "PROFILE_NOT_PROMOTED", "detail": "pass a sample first"})
        materialized = [self.materialize(project_key, episode, c, decisions) for c in chapters]
        seen: set[tuple[str, str]] = set()
        unique = []
        for reason in reasons + self.creative_readiness(project_key, episode, materialized):
            key = (str(reason.get("kind")), str(reason.get("key", "")))
            if key not in seen:
                seen.add(key)
                unique.append(reason)
        return unique


def chapter_qa(pages: list[dict[str, Any]]) -> dict[str, Any]:
    """Lightweight checks across a chapter. They flag; they never fix or rewrite."""
    import datetime as _dt
    from collections import Counter

    def warn(entry: dict[str, Any], kind: str, detail: str, severity: str = "warn") -> None:
        entry.setdefault("warnings", []).append(
            {"kind": kind, "detail": detail, "severity": severity}
        )

    usage: Counter[str] = Counter()
    hashes: Counter[str] = Counter()
    for entry in pages:
        refs = {o["id"] for c in entry["characters"] for o in c["observations"]}
        refs |= {g["locator"] for g in entry["grammar"]}
        refs |= {t["locator"] for t in entry["technique"]}
        usage.update(refs)
        if entry["render"]["content_hash"]:
            hashes[entry["render"]["content_hash"]] += 1
    labels: dict[str, str] = {}
    for entry in pages:
        for c in entry["characters"]:
            for o in c["observations"]:
                labels[o["id"]] = f"{c['name']}: {o['source_label']}"
        for g in [*entry["grammar"], *entry["technique"]]:
            labels[g["locator"]] = f"{g['role'].lower()}: {g['label']}"
    now = _dt.datetime.now(_dt.UTC)
    previous: dict[str, Any] | None = None
    for entry in pages:
        entry["warnings"] = []
        plan = entry["plan"]
        for item in plan["uncertain"]:
            warn(entry, "CAST_UNCERTAIN", item)
        bundled = {c["name"]: c for c in entry["characters"]}
        for name in plan["characters_present"]:
            c = bundled.get(name)
            if c is None:
                warn(
                    entry,
                    "CHARACTER_NO_REFERENCES",
                    f"{name} is in the cast but has no grounded references",
                    "error",
                )
                continue
            identity = [o for o in c["observations"] if set(o["facets"]) & {"FACE", "HAIR"}]
            confirmed = [o for o in c["observations"] if o["status"] == "CONFIRMED"]
            if not confirmed:
                warn(
                    entry,
                    "IDENTITY_ONLY_CANDIDATES",
                    f"{name}: no confirmed reference - only candidates",
                    "error",
                )
            elif not identity:
                warn(
                    entry,
                    "NO_IDENTITY_REFERENCE",
                    f"{name}: no face or hair reference retrieved for this page",
                )
            candidates = [o for o in c["observations"] if o["status"] == "CANDIDATE"]
            if candidates:
                warn(
                    entry,
                    "CANDIDATES_IN_BUNDLE",
                    f"{name}: {len(candidates)} unconfirmed candidate(s) included"
                    " - never identity proof",
                    "info",
                )
            for group in ("body", "wardrobe"):
                wanted = group.upper() in set(c["need"]["facets"])
                if wanted and c["readiness"].get(group) == "MISSING":
                    warn(
                        entry,
                        f"{group.upper()}_MISSING",
                        f"{name}: the page needs {group} and none is confirmed",
                    )
            for o in c["observations"]:
                if o["authority"] in {"SUPPLEMENTAL", "UNSORTED"} and o["role"] == "GROUNDING":
                    warn(
                        entry,
                        "ROLE_MISUSE",
                        f"{name}: {o['source_label']} is supplemental but used as grounding",
                        "error",
                    )
        if not entry["grammar"]:
            warn(entry, "NO_GRAMMAR", "no grammar page retrieved")
        environment_needed = bool(plan["environment_tags"]) or bool(
            set(plan["intents"]) & {"nature_exterior", "large_composition", "back_shot"}
        )
        if environment_needed and not entry["environment"]:
            detail = "no tagged environment reference"
            detail += " - only unverified wide pages" if entry["environment_pages"] else ""
            warn(
                entry,
                "ENVIRONMENT_GAP",
                detail
                + (f" ({', '.join(plan['environment_tags'])})" if plan["environment_tags"] else ""),
            )
        if previous is not None:
            same_grammar = {g["locator"] for g in entry["grammar"]} == {
                g["locator"] for g in previous["grammar"]
            } and bool(entry["grammar"])
            if same_grammar:
                warn(
                    entry, "REPEATED_GRAMMAR", f"same grammar pages as page {previous['sequence']}"
                )
            if (
                plan["primary_intent"] == previous["plan"]["primary_intent"]
                and plan["characters_present"] == previous["plan"]["characters_present"]
                and same_grammar
            ):
                warn(
                    entry,
                    "POSSIBLE_REPEATED_COMPOSITION",
                    f"same intent, cast and grammar as page {previous['sequence']}",
                )
        render = entry["render"]
        job = render.get("job") or {}
        if render["state"] in ("FAILED",) or job.get("status") in ("FAILED", "BLOCKED"):
            warn(
                entry,
                "RENDER_FAILED",
                job.get("error") or job.get("blocked_reason") or "render failed",
                "error",
            )
        elif render["state"] == "QUEUED" and render["created_at"]:
            age = (now - _dt.datetime.fromisoformat(render["created_at"])).total_seconds()
            if age > 300:
                warn(
                    entry,
                    "RENDER_STUCK",
                    f"queued for {int(age // 60)} minutes - is the worker running?",
                    "error",
                )
        if render["content_hash"] and hashes[render["content_hash"]] > 1:
            warn(
                entry,
                "DUPLICATE_RENDER",
                "this test render is identical to another page's",
                "error",
            )
        if not render["attempt_id"] and render["state"] != "QUEUED":
            warn(entry, "NOT_RENDERED", "no test render yet", "info")
        previous = entry
    overused = []
    threshold = max(4, int(len(pages) * 0.6))
    for key, count in usage.items():
        if count >= threshold and len(pages) >= 4:
            overused.append({"reference": labels.get(key, key), "pages": count})
    counts: Counter[str] = Counter(w["kind"] for e in pages for w in e["warnings"])
    return {
        "pages": len(pages),
        "rendered": sum(1 for e in pages if e["render"]["attempt_id"]),
        "pages_with_warnings": sum(
            1 for e in pages if any(w["severity"] != "info" for w in e["warnings"])
        ),
        "pages_with_cast_warnings": sum(
            1 for e in pages if any(w["kind"] == "CAST_UNCERTAIN" for w in e["warnings"])
        ),
        "pages_with_character_warnings": sum(
            1
            for e in pages
            if any(
                w["kind"]
                in {
                    "CHARACTER_NO_REFERENCES",
                    "IDENTITY_ONLY_CANDIDATES",
                    "NO_IDENTITY_REFERENCE",
                    "BODY_MISSING",
                    "WARDROBE_MISSING",
                    "ROLE_MISUSE",
                }
                for w in e["warnings"]
            )
        ),
        "pages_with_environment_gaps": sum(
            1 for e in pages if any(w["kind"] == "ENVIRONMENT_GAP" for w in e["warnings"])
        ),
        "pages_with_grammar": sum(1 for e in pages if e["grammar"]),
        "counts": dict(counts),
        "overused_references": overused,
    }


def catalog_grammar_candidates(
    session: Session,
    read_page: Callable[[CatalogUnit, CatalogEntry, int], tuple[str, bytes] | None],
    analyze: Callable[[bytes], Any],
    cache: dict[str, GrammarCandidate] | None = None,
) -> Callable[[Sequence[str], int], list[GrammarCandidate]]:
    """Candidate manga pages from catalogued chapters of the named series.

    Deterministic: for each series, chapters are taken in reading order at an
    even stride and one interior page of each is analysed. ``read_page`` returns
    (locator, bytes) through the read-only storage layer; ``analyze`` measures
    layout. Results are cached by catalog unit and page, so a page is read once.
    """
    memo = cache if cache is not None else {}

    def candidates(series: Sequence[str], pool: int) -> list[GrammarCandidate]:
        out: list[GrammarCandidate] = []
        if not series:
            return out
        per_series = max(1, pool // len(series))
        for series_key in series:
            rows = session.execute(
                select(CatalogUnit, CatalogEntry)
                .join(CatalogEntry, CatalogEntry.id == CatalogUnit.entry_id)
                .where(
                    CatalogUnit.series_key == series_key,
                    CatalogUnit.kind == UnitKind.MANGA_CHAPTER,
                    CatalogEntry.duplicate_of_id.is_(None),
                )
                .order_by(CatalogUnit.sort_key)
            ).all()
            if not rows:
                continue
            stride = max(1, len(rows) // per_series)
            for unit, entry in rows[::stride][:per_series]:
                offset = max(1, (unit.page_count or 2) // 2)
                key = f"{unit.unit_key}:{offset}"
                if key in memo:
                    out.append(memo[key])
                    continue
                found = read_page(unit, entry, offset)
                if found is None:
                    continue
                locator, data = found
                if key not in memo:
                    layout = analyze(data)
                    memo[key] = GrammarCandidate(
                        locator=locator,
                        series_key=series_key,
                        label=f"{unit.label} p{offset + 1}",
                        panel_count=layout.panel_count,
                        largest_panel_share=round(layout.largest_panel_share, 4),
                        negative_space=layout.negative_space,
                        ink_density=layout.ink_density,
                        unit_key=unit.unit_key,
                        page_offset=offset,
                    )
                out.append(memo[key])
        return out

    return candidates


def source_page_reader(
    catalog: ReferenceCatalog,
) -> Callable[[CatalogUnit, CatalogEntry, int], tuple[str, bytes] | None]:
    """Read one page of a catalogued Source Vault chapter, read-only.

    The page is recorded as a library asset (a database row, never a file in
    the Vault) so a render job can resolve its locator later. A chapter that is
    a folder inside an archive is addressed by its first page index in the
    archive's reading order; unreadable pages return ``None``.
    """

    def read(unit: CatalogUnit, entry: CatalogEntry, offset: int) -> tuple[str, bytes] | None:
        sources = catalog.sources
        if sources is None or entry.root_key != "source_vault":
            return None
        media_id = sources.media_id_for(entry.relative_path)
        if media_id is None:
            return None
        try:
            held = sources.select(
                media_id,
                page_index=(unit.first_page_index or 0) + offset,
                known_hash=catalog.known_hash,
            )
            data = sources.read_unit(
                held.relative,
                byte_size=held.byte_size,
                mtime_ns=held.mtime_ns,
                locator=held.locator,
            ).data
        except (SourceUnavailableError, SourceChangedError):
            return None
        asset = catalog.asset(
            held.content_hash, held.medium, AssetOrigin.SOURCE_VAULT, held.byte_size
        )
        catalog.observe(asset, "source_vault", held.relative, held.byte_size, held.mtime_ns)
        return held.locator.render(), data

    return read
