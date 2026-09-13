"""How the Library's documents are presented: states, roll-ups, next steps.

The acquisition engine decides what is complete, partial, missing or
unmapped. This module decides nothing of the kind. It translates the engine's
verdicts into the states the screens speak, rolls them up per kind of
material and per family, and applies exactly one rule of its own:

    A MISSING verdict is not repeated about a family whose folder changed
    after the scan that produced it. It becomes STALE ("needs rescan").

That rule is about the age of a report, not about acquisition, which is why
it lives here and not in the engine: only the reader of a document knows how
old it is by the time it is read.

Everything here is a pure function of documents already in memory. No
filesystem access (ADR-0001), no franchise knowledge (A-05).
"""

from __future__ import annotations

import datetime as dt
from collections import Counter, defaultdict
from collections.abc import Iterable
from typing import Any, Literal

from continuum_api.schemas import (
    EpisodeRun,
    Freshness,
    LibraryHero,
    MaterialSummary,
    NextStep,
    QueueGroup,
    RecentAddition,
    TimelineEvent,
)

__all__ = [
    "RECENT_DAYS",
    "family_roll_up",
    "folder_name",
    "freshness",
    "hero",
    "intake_section",
    "iso_ns",
    "next_steps",
    "queue_group",
    "queue_groups",
    "recently_added",
    "timeline",
    "work_episodes",
    "work_state",
]

#: How far back "recently added" looks.
RECENT_DAYS = 30

#: Relations that ARE the story rather than something about it.
_STORY_RELATIONS = frozenset({"MAIN_WORK", "SEQUEL", "PREQUEL"})
_HELD = ("COMPLETE", "PARTIAL", "PRESENT")
#: Display order of the story vocabulary (the engine's classes, not a ranking).
_CLASS_ORDER = ("manga", "manhwa", "manhua", "anime", "light-novel", "web-novel")


def plural(count: int, noun: str) -> str:
    return f"{count} {noun}{'' if count == 1 else 's'}"


def iso_ns(value: Any) -> str | None:
    """A nanosecond epoch as UTC ISO-8601, or None."""
    if not isinstance(value, int | float) or value <= 0:
        return None
    moment = dt.datetime.fromtimestamp(value / 1e9, tz=dt.UTC)
    return moment.isoformat(timespec="seconds")


def folder_name(path: str) -> str:
    """The last segment of a family path, whichever separator it uses."""
    return path.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]


# -- freshness ---------------------------------------------------------------
def freshness(
    coverage: dict[str, Any],
    layout: dict[str, Any],
    *,
    checked: bool,
    changed: bool,
    folders: Iterable[str],
    detail: str = "",
) -> Freshness:
    """The documents' three clocks, and whether the Vault moved since."""
    header = coverage.get("freshness") or layout.get("freshness") or {}
    scanned = header.get("library_scanned_at") or layout.get("generated_at")
    if not scanned:
        return Freshness(state="empty", detail="no library scan has been recorded yet")
    by_folder = {
        folder_name(str(f.get("family_path") or "")).lower(): str(f.get("family_id") or "")
        for f in layout.get("families") or []
        if isinstance(f, dict)
    }
    changed_families: list[str] = []
    changed_folders: list[str] = []
    for name in folders:
        family_id = by_folder.get(name.lower())
        (changed_families if family_id else changed_folders).append(family_id or name)
    state: Literal["fresh", "stale", "unknown"] = (
        "unknown" if not checked else ("stale" if changed else "fresh")
    )
    return Freshness(
        state=state,
        library_scanned_at=scanned,
        catalogue_refreshed_at=header.get("catalogue_refreshed_at"),
        documents_generated_at=coverage.get("generated_at") or layout.get("generated_at"),
        vault_changed=changed if checked else None,
        changed_families=sorted(changed_families),
        changed_folders=sorted(changed_folders),
        unhashed_files=header.get("unhashed_files"),
        detail=detail,
    )


# -- works -------------------------------------------------------------------
def work_state(coverage_status: str | None, *, stale_family: bool) -> str:
    """The engine's coverage verdict in the Library's vocabulary."""
    if coverage_status == "COMPLETE":
        return "COMPLETE"
    if coverage_status == "PARTIAL":
        return "PARTIAL"
    if coverage_status == "UNKNOWN":
        return "PRESENT"
    if coverage_status == "NEEDS_MAPPING":
        return "NEEDS_MAPPING"
    if coverage_status == "MISSING":
        return "STALE" if stale_family else "MISSING"
    return "UNVERIFIED"


def work_episodes(cov: dict[str, Any]) -> tuple[list[EpisodeRun], int]:
    episodes = cov.get("episodes") or {}
    runs = [
        EpisodeRun(
            season=s.get("season"),
            episodes=int(s.get("episodes") or 0),
            episodes_text=str(s.get("episodes_text") or ""),
            gaps_text=str(s.get("gaps_text") or ""),
        )
        for s in episodes.get("seasons") or []
        if isinstance(s, dict)
    ]
    return runs, int(episodes.get("other_videos") or 0)


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _story_classes(classes: dict[str, Any]) -> set[str]:
    return {str(k).lower() for k, v in classes.items() if isinstance(v, dict) and v.get("story")}


def _is_story_row(row: dict[str, Any], story_classes: set[str]) -> bool:
    if "story_material" in row:
        return bool(row.get("story_material"))
    return str(row.get("material_class") or "").lower() in story_classes


# -- families ----------------------------------------------------------------
def _roll_up(counts: Counter[str], *, works: int, unmapped: int, files: int) -> str:
    """One state for a set of works of the same kind, never optimistic."""
    held = sum(counts[s] for s in _HELD)
    if works == 0:
        return "UNCATALOGUED" if unmapped or files else "EMPTY"
    if held == 0:
        for state in ("NEEDS_MAPPING", "STALE", "MISSING", "UNVERIFIED"):
            if counts[state]:
                return state
        return "UNVERIFIED"
    if counts["PARTIAL"] or counts["MISSING"] or counts["NEEDS_MAPPING"] or counts["STALE"]:
        return "PARTIAL"
    if counts["PRESENT"] or counts["UNVERIFIED"]:
        return "PRESENT"
    return "COMPLETE"


def family_roll_up(family: dict[str, Any], states: dict[str, str]) -> dict[str, Any]:
    """Per-material summaries and the family's own state.

    ``states`` maps work id to the already-projected state, so staleness has
    been applied once, before anything is counted.
    """
    works = [w for w in family.get("works") or [] if isinstance(w, dict)]
    official = [w for w in works if w.get("official_status") is not False]
    classes = _mapping(family.get("classes"))
    story_classes = _story_classes(classes)

    by_class: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for w in official:
        by_class[str(w.get("material_class") or "other").lower()].append(w)
    names = set(by_class)
    for key, info in classes.items():
        if isinstance(info, dict) and (info.get("media_files") or 0) > 0:
            names.add(str(key).lower())

    materials: list[MaterialSummary] = []
    for name in names:
        rows = by_class.get(name, [])
        info = _mapping(classes.get(name))
        counts = Counter(states.get(str(w.get("work_id")), "UNVERIFIED") for w in rows)
        unmapped = int(info.get("unattributed_files") or 0)
        media_files = int(info.get("media_files") or 0)
        story = (
            bool(info.get("story")) if info else any(_is_story_row(w, story_classes) for w in rows)
        )
        materials.append(
            MaterialSummary(
                material_class=name,
                state=_roll_up(  # type: ignore[arg-type]
                    counts, works=len(rows), unmapped=unmapped, files=media_files
                ),
                story=story,
                works=len(rows),
                complete=counts["COMPLETE"],
                partial=counts["PARTIAL"],
                present=counts["PRESENT"],
                missing=counts["MISSING"],
                needs_mapping=counts["NEEDS_MAPPING"],
                unverified=counts["UNVERIFIED"],
                stale=counts["STALE"],
                files=media_files,
                bytes=int(info.get("bytes") or 0),
                video_files=int(info.get("video_files") or 0),
                unmapped_files=unmapped,
                last_added_at=iso_ns(info.get("last_added_ns")),
            )
        )
    # Story material first, in the order people think of a family in; then
    # supplements, the ones with something on disk before the ones without.
    materials.sort(
        key=lambda m: (
            not m.story,
            _CLASS_ORDER.index(m.material_class) if m.material_class in _CLASS_ORDER else 99,
            not m.files,
            -m.works,
            m.material_class,
        )
    )

    all_counts = Counter(states.get(str(w.get("work_id")), "UNVERIFIED") for w in official)
    story_rows = [w for w in official if _is_story_row(w, story_classes)]
    story_counts = Counter(states.get(str(w.get("work_id")), "UNVERIFIED") for w in story_rows)
    supplement_rows = [w for w in official if not _is_story_row(w, story_classes)]
    supplement_held = sum(1 for w in supplement_rows if states.get(str(w.get("work_id"))) in _HELD)
    story_missing_core = sum(
        1
        for w in story_rows
        if states.get(str(w.get("work_id"))) in ("MISSING", "STALE")
        and w.get("relationship_type") in _STORY_RELATIONS
    )
    unmapped_total = sum(m.unmapped_files for m in materials)
    # Things to act on: finish, map, or get the story itself. Catalogue
    # suggestions awaiting review are counted separately ("review"), because
    # a family with twenty unconfirmed guidebooks does not need attention.
    attention = (
        all_counts["PARTIAL"]
        + all_counts["NEEDS_MAPPING"]
        + all_counts["STALE"]
        + story_missing_core
        + (1 if unmapped_total and not all_counts["NEEDS_MAPPING"] else 0)
    )
    state = _roll_up(
        story_counts if story_rows else all_counts,
        works=len(story_rows) or len(official),
        unmapped=unmapped_total,
        files=int(family.get("files") or 0),
    )
    return {
        "materials": materials,
        "state": state,
        "counts": all_counts,
        "story_works": len(story_rows),
        "story_held": sum(1 for w in story_rows if states.get(str(w.get("work_id"))) in _HELD),
        "supplements": len(supplement_rows),
        "supplements_held": supplement_held,
        "attention": attention,
        "last_added_at": iso_ns(family.get("last_added_ns")),
    }


# -- overview ----------------------------------------------------------------
def hero(
    families: list[dict[str, Any]],
    rollups: dict[str, dict[str, Any]],
    states: dict[str, str],
    layout: dict[str, Any],
) -> LibraryHero:
    story_states: Counter[str] = Counter()
    for family in families:
        story_classes = _story_classes(_mapping(family.get("classes")))
        for w in family.get("works") or []:
            if w.get("official_status") is False or not _is_story_row(w, story_classes):
                continue
            story_states[states.get(str(w.get("work_id")), "UNVERIFIED")] += 1
    summary = layout.get("summary") or {}
    fam_states = Counter(r["state"] for r in rollups.values())
    return LibraryHero(
        families=len(families),
        bytes=int(summary.get("bytes") or 0),
        files=int(summary.get("files") or 0),
        story_works=sum(story_states.values()),
        complete=story_states["COMPLETE"],
        partial=story_states["PARTIAL"],
        present=story_states["PRESENT"],
        missing=story_states["MISSING"],
        needs_mapping=story_states["NEEDS_MAPPING"],
        unverified=story_states["UNVERIFIED"],
        stale=story_states["STALE"],
        complete_families=fam_states["COMPLETE"],
        attention_families=sum(1 for r in rollups.values() if r["attention"]),
    )


def recently_added(
    families: list[dict[str, Any]],
    rollups: dict[str, dict[str, Any]],
    *,
    now: dt.datetime | None = None,
    limit: int = 8,
) -> list[RecentAddition]:
    """Material that arrived on disk in the last RECENT_DAYS days, newest first.

    Arrival is the file's creation time on the Vault's disk, recorded by the
    engine's scan - a fact about the file, not a guess about the download.
    """
    now = now or dt.datetime.now(tz=dt.UTC)
    cutoff = now - dt.timedelta(days=RECENT_DAYS)
    out: list[RecentAddition] = []
    for family in families:
        family_id = str(family.get("family_id") or "")
        for material in rollups.get(family_id, {}).get("materials", []):
            if not material.last_added_at or not material.files:
                continue
            if dt.datetime.fromisoformat(material.last_added_at) < cutoff:
                continue
            out.append(
                RecentAddition(
                    family_id=family_id,
                    family=str(family.get("family_title") or ""),
                    material_class=material.material_class,
                    files=material.files,
                    bytes=material.bytes,
                    video_files=material.video_files,
                    last_added_at=material.last_added_at,
                    state=material.state,
                )
            )
    out.sort(key=lambda r: r.last_added_at, reverse=True)
    return out[:limit]


def next_steps(
    *,
    fresh: Freshness,
    families: list[dict[str, Any]],
    rollups: dict[str, dict[str, Any]],
    states: dict[str, str],
    updates_available: list[dict[str, Any]],
    intake_pending: int,
    review_count: int,
    limit: int = 6,
) -> list[NextStep]:
    """At most a handful of useful things to do, most useful first."""
    steps: list[NextStep] = []
    if fresh.state == "stale":
        count = len(fresh.changed_families) + len(fresh.changed_folders)
        steps.append(
            NextStep(
                kind="refresh",
                tone="info",
                title="Refresh your Library",
                detail=f"{count} folder{'s' if count != 1 else ''} changed since the last scan.",
            )
        )

    for family in families:
        family_id = str(family.get("family_id") or "")
        roll = rollups.get(family_id) or {}
        unmapped = sum(m.unmapped_files for m in roll.get("materials", []))
        if unmapped:
            kinds = ", ".join(m.material_class for m in roll["materials"] if m.unmapped_files)
            steps.append(
                NextStep(
                    kind="map",
                    tone="info",
                    family_id=family_id,
                    title=f"Identify local files in {family.get('family_title')}",
                    detail=f"{unmapped} file{'s' if unmapped != 1 else ''} in {kinds} "
                    "not matched to a work yet.",
                )
            )

    for item in updates_available[:3]:
        steps.append(
            NextStep(
                kind="update",
                tone="accent",
                family_id=str(item.get("family_id") or ""),
                work_id=str(item.get("work_id") or ""),
                title=f"New {item.get('unit') or 'chapters'} for {item.get('work')}",
                detail=(
                    f"You have {item.get('latest_local')}; {item.get('latest_remote')} is known."
                ),
            )
        )

    updating = {str(item.get("work_id") or "") for item in updates_available[:3]}
    partial: list[NextStep] = []
    missing_core: list[NextStep] = []
    for family in families:
        for w in family.get("works") or []:
            wid = str(w.get("work_id") or "")
            state = states.get(wid)
            if w.get("official_status") is False:
                continue
            if state == "PARTIAL" and w.get("story_material", True) and wid not in updating:
                partial.append(
                    NextStep(
                        kind="finish",
                        tone="warn",
                        family_id=str(family.get("family_id") or ""),
                        work_id=wid,
                        title=f"Finish {w.get('work')}",
                        detail=str(w.get("coverage_reason") or ""),
                    )
                )
            elif (
                state == "MISSING"
                and w.get("story_material")
                and w.get("relationship_type") in _STORY_RELATIONS
            ):
                missing_core.append(
                    NextStep(
                        kind="acquire",
                        tone="err",
                        family_id=str(family.get("family_id") or ""),
                        work_id=wid,
                        title=f"Get {w.get('work')}",
                        detail=f"{str(w.get('relationship_type')).replace('_', ' ').lower()} of "
                        f"{family.get('family_title')}, not in your Library.",
                    )
                )
    steps += partial[:2]
    if intake_pending:
        steps.append(
            NextStep(
                kind="intake",
                tone="info",
                title="Identify what arrived in Intake",
                detail=f"{intake_pending} item{'s' if intake_pending != 1 else ''} waiting.",
            )
        )
    steps += missing_core[:2]
    if review_count and len(steps) < limit:
        steps.append(
            NextStep(
                kind="review",
                tone="muted",
                title="Review catalogue suggestions",
                detail=f"{plural(review_count, 'item')} wait for a decision.",
            )
        )
    return steps[:limit]


# -- queue -------------------------------------------------------------------
_GROUPS: tuple[tuple[str, str, str, str], ...] = (
    ("rescan", "Needs a rescan", "Their family folders changed after the last scan.", "info"),
    ("updates", "Known updates", "Works you hold that have more out.", "accent"),
    ("finish", "Finish partial works", "You hold part of these.", "warn"),
    ("main", "Missing main works", "The story itself: main series, sequels and prequels.", "err"),
    ("side", "Spin-offs and adaptations", "Official story material beyond the main line.", "muted"),
    (
        "supplements",
        "Optional supplements",
        "Guidebooks, fanbooks, art books, anthologies and editions. Official is not main canon.",
        "muted",
    ),
    ("unconfirmed", "Unconfirmed", "Existence or availability is not established.", "muted"),
)


def queue_group(state: str, *, story: bool, relation: str | None, update: bool) -> str:
    if state == "STALE":
        return "rescan"
    if update:
        return "updates"
    if state == "PARTIAL":
        return "finish"
    if state == "UNVERIFIED":
        return "unconfirmed"
    if story and relation in _STORY_RELATIONS:
        return "main"
    if story:
        return "side"
    return "supplements"


def queue_groups(counts: Counter[str]) -> list[QueueGroup]:
    return [
        QueueGroup(key=key, title=title, description=description, count=counts[key], tone=tone)  # type: ignore[arg-type]
        for key, title, description, tone in _GROUPS
        if counts[key]
    ]


# -- intake ------------------------------------------------------------------
def intake_section(action: str) -> str:
    """Which part of Intake a unit belongs to, from the importer's decision."""
    lowered = action.lower()
    if lowered.startswith("imported") or lowered.startswith("created"):
        return "ready"
    if "identical" in lowered or "already" in lowered:
        return "known"
    if "incomplete" in lowered:
        return "incomplete"
    if "cannot create" in lowered or "unsafe" in lowered or "conflict" in lowered:
        return "conflict"
    return "identify"


# -- updates -----------------------------------------------------------------
_ALERT_KINDS = {
    "NEW_CHAPTERS": "new_chapters",
    "NEW_VOLUMES": "new_volumes",
    "NEW_RELEASE": "new_release",
    "NEW_WORK": "new_release",
    "SOURCE_CHANGED": "source_changed",
}


def timeline(
    alerts: list[dict[str, Any]],
    additions: list[RecentAddition],
    family_ids: dict[str, str],
    limit: int = 120,
) -> list[TimelineEvent]:
    events: list[TimelineEvent] = []
    for alert in alerts:
        kind = _ALERT_KINDS.get(str(alert.get("kind") or "").upper(), "other")
        family = str(alert.get("family") or "")
        events.append(
            TimelineEvent(
                at=alert.get("at"),
                kind=kind,  # type: ignore[arg-type]
                title=str(alert.get("kind") or "").replace("_", " ").capitalize(),
                detail=str(alert.get("detail") or ""),
                family=family,
                family_id=family_ids.get(family, ""),
                work=alert.get("work") or alert.get("source"),
            )
        )
    for addition in additions:
        what = "episode files" if addition.video_files else "files"
        events.append(
            TimelineEvent(
                at=addition.last_added_at,
                kind="local_files",
                title="New local files",
                detail=f"{addition.files} {what} in {addition.material_class}",
                family=addition.family,
                family_id=addition.family_id,
                material_class=addition.material_class,
            )
        )
    events.sort(key=lambda e: e.at or "", reverse=True)
    return events[:limit]
