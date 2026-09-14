"""What a file probably is: series, season, episode, chapter - with evidence.

Pure functions over names. Nothing here reads a file, and nothing here knows a
title: a series is whatever folder the material sits in, a program title is
whatever the file name says, and when the two disagree - or a name says too
little - the identification is **flagged**, never silently guessed.

The layout conventions recognised (all optional, none required):

* ``<Series>/<material>/...`` where ``<material>`` is a folder such as
  ``manga``, ``manhwa`` or ``anime`` (case-insensitive);
* episode names such as ``Title - S01E02``, ``Title S2 - 08``, ``Title - OVA 01``,
  ``Title - S02SP01``, ``Title - 27`` or ``title-07``;
* chapter folders such as ``Ch0042``, ``Ch71.5``, ``Chapter 12`` or ``c012``,
  and volume folders such as ``Vol 03``.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from continuum_core.catalog import Confidence, EpisodeKind, MaterialClass

__all__ = [
    "ChapterIdentity",
    "EpisodeIdentity",
    "Placement",
    "comparable_title",
    "identify_chapter",
    "identify_episode",
    "place",
    "series_key_for",
]

MATERIAL_FOLDERS: dict[str, MaterialClass] = {
    "manga": MaterialClass.MANGA,
    "manhwa": MaterialClass.MANHWA,
    "manhua": MaterialClass.MANHUA,
    "webtoon": MaterialClass.MANHWA,
    "comic": MaterialClass.COMIC,
    "comics": MaterialClass.COMIC,
    "anime": MaterialClass.ANIME,
    "animation": MaterialClass.ANIME,
    "movies": MaterialClass.ANIME,
    "ova": MaterialClass.ANIME,
}
INTAKE_MATERIALS: dict[str, MaterialClass] = {
    "fan_art": MaterialClass.FAN_ART,
    "reference": MaterialClass.REFERENCE,
    "document": MaterialClass.DOCUMENT,
    "manga": MaterialClass.MANGA,
    "anime": MaterialClass.ANIME,
}

_TAGS = re.compile(
    r"\[[^\]]*\]|\((?:[^()]*(?:season|batch|bd|1080p|720p|x26[45]|hevc|dual)[^()]*)\)", re.I
)
_SPACES = re.compile(r"[\s_]+")


def series_key_for(title: str) -> str:
    """A stable, path-free key for a series title: lowercase ASCII words and dashes."""
    normal = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", normal.lower()).strip("-")
    return slug[:120] or "untitled"


def comparable_title(text: str) -> str:
    """A title reduced to letters and digits, for "does this name the series?"."""
    normal = unicodedata.normalize("NFKD", _TAGS.sub(" ", text)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "", normal.lower())


@dataclass(frozen=True, slots=True)
class Placement:
    """Where a file sits in its root, and what that says about it."""

    series_title: str | None
    series_key: str | None
    material: MaterialClass
    #: Folders between the material folder and the file ("Season 3", "Volume 2").
    subfolders: tuple[str, ...]
    evidence: tuple[str, ...]
    flags: tuple[str, ...]


def place(relative: str, *, is_vault: bool, intake_material: str = "") -> Placement:
    """Series and material from a file's position in its root."""
    parts = [p for p in relative.split("/") if p]
    folders = parts[:-1]
    if not is_vault:
        material = INTAKE_MATERIALS.get(intake_material, MaterialClass.REFERENCE)
        declared = (f"declared by the intake folder ({intake_material or 'reference'})",)
        return Placement(None, None, material, tuple(folders), declared, ())
    if not folders:
        return Placement(
            None,
            None,
            MaterialClass.UNKNOWN,
            (),
            (),
            ("file at the top of the Vault: no series folder",),
        )
    series_title = folders[0].strip()
    evidence = [f"series folder '{series_title}'"]
    flags: list[str] = []
    if len(folders) >= 2 and folders[1].strip().lower() in MATERIAL_FOLDERS:
        material = MATERIAL_FOLDERS[folders[1].strip().lower()]
        evidence.append(f"material folder '{folders[1]}'")
        subfolders = tuple(folders[2:])
    else:
        material = MaterialClass.UNKNOWN
        flags.append("no material folder (manga, anime...) under the series folder")
        subfolders = tuple(folders[1:])
    return Placement(
        series_title,
        series_key_for(series_title),
        material,
        subfolders,
        tuple(evidence),
        tuple(flags),
    )


# ---------------------------------------------------------------------------
# episodes
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class EpisodeIdentity:
    program_title: str | None
    season: int | None
    episode: int | None
    kind: EpisodeKind
    label: str
    confidence: Confidence
    evidence: tuple[str, ...] = ()
    flags: tuple[str, ...] = ()
    #: A program the name adds to the series title ("... Diary", "... Visions of
    #: X"): kept apart from the series' own seasons, never merged into them.
    subseries: str | None = None


_SXXEYY = re.compile(r"(?<![a-z0-9])s(\d{1,2})\s*e(\d{1,4})(?![0-9])", re.I)
_SXXSP = re.compile(r"(?<![a-z0-9])s(\d{1,2})\s*sp\s*(\d{1,3})(?![0-9])", re.I)
_S_DASH = re.compile(r"(?<![a-z0-9])s(\d{1,2})\s*-\s*(\d{1,4})(?![0-9])", re.I)
_OVA = re.compile(r"(?<![a-z0-9])(ova|oad|ona)\s*-?\s*(\d{1,3})?(?![0-9])", re.I)
_TRAILING = re.compile(r"(?:^|[\s_-])(?:ep(?:isode)?\s*)?(\d{1,4})(?:v\d)?\s*$", re.I)
_SEASON_WORD = re.compile(r"(?<![a-z0-9])season\s*(\d{1,2})(?![0-9])", re.I)
_MOVIE = re.compile(r"(?<![a-z])(movie|film)(?![a-z])", re.I)
_RECAP = re.compile(r"(?<![a-z])recap(?![a-z])", re.I)
_YEAR = re.compile(r"\((19|20)\d{2}\)")


def _stem(name: str) -> str:
    base = name.rsplit("/", 1)[-1]
    return base.rsplit(".", 1)[0] if "." in base else base


_COPY_SUFFIX = re.compile(r"\s*\((\d{1,2})\)\s*$")


def _clean_title(text: str) -> str:
    cleaned = _TAGS.sub(" ", text)
    cleaned = _COPY_SUFFIX.sub("", cleaned)
    cleaned = _SPACES.sub(" ", cleaned).strip(" -_.")
    return cleaned


def _match(program: str | None, names: list[str]) -> tuple[str, str] | None:
    """(the name matched, any words the program adds to it), or None."""
    if not program:
        return None
    wanted = comparable_title(program)
    if not wanted:
        return None
    for candidate in names:
        other = comparable_title(candidate)
        if not other:
            continue
        if wanted == other:
            return candidate, ""
        if wanted.startswith(other) and len(other) >= 4:
            extra = (
                program[len(candidate) :] if program.lower().startswith(candidate.lower()) else ""
            )
            return candidate, extra.strip(" -_:.") or program
        if other.startswith(wanted) and len(wanted) >= 4:
            return candidate, ""
    return None


def identify_episode(
    name: str,
    *,
    series_title: str | None,
    aliases: tuple[str, ...] = (),
    folders: tuple[str, ...] = (),
) -> EpisodeIdentity:
    """Season, episode and program from a video's name and the folders around it."""
    stem = _stem(name)
    evidence: list[str] = []
    flags: list[str] = []
    season: int | None = None
    episode: int | None = None
    kind = EpisodeKind.REGULAR
    title_part = stem

    match = _SXXSP.search(stem)
    if match:
        season, episode, kind = int(match.group(1)), int(match.group(2)), EpisodeKind.SPECIAL
        title_part = stem[: match.start()]
        evidence.append(f"'{match.group(0)}' in the file name")
    else:
        match = _SXXEYY.search(stem)
        if match:
            season, episode = int(match.group(1)), int(match.group(2))
            title_part = stem[: match.start()]
            evidence.append(f"'{match.group(0)}' in the file name")
        else:
            match = _S_DASH.search(stem)
            if match:
                season, episode = int(match.group(1)), int(match.group(2))
                title_part = stem[: match.start()]
                evidence.append(f"'{match.group(0)}' in the file name")
            else:
                ova = _OVA.search(stem)
                if ova:
                    kind = EpisodeKind.OVA
                    episode = int(ova.group(2)) if ova.group(2) else None
                    title_part = stem[: ova.start()]
                    evidence.append(f"'{ova.group(0).strip()}' in the file name")
                else:
                    cleaned = _TAGS.sub(" ", stem).rstrip(" -_.")
                    cleaned = _COPY_SUFFIX.sub("", cleaned).rstrip(" -_.")
                    trailing = _TRAILING.search(cleaned)
                    if trailing and not _YEAR.search(stem) and int(trailing.group(1)) > 0:
                        episode = int(trailing.group(1))
                        title_part = cleaned[: trailing.start()]
                        evidence.append(f"trailing number '{trailing.group(1)}' in the file name")
                        flags.append("episode number without a season in the name")
                    elif trailing:
                        title_part = cleaned[: trailing.start()]
                        flags.append("numbered 0: may be a film or a prologue")

    if _RECAP.search(stem):
        kind = EpisodeKind.RECAP
        evidence.append("'recap' in the file name")
    if episode is None and kind is EpisodeKind.REGULAR:
        if _MOVIE.search(stem) or _YEAR.search(stem):
            kind = EpisodeKind.MOVIE
            evidence.append("named as a film")
        else:
            kind = EpisodeKind.UNKNOWN
            flags.append("no episode number could be read from the name")

    folder_season = None
    for folder in folders:
        found = _SEASON_WORD.search(folder)
        if found:
            folder_season = int(found.group(1))
    if folder_season is not None:
        if season is None:
            season = folder_season
            evidence.append(f"season folder ({folder_season})")
            if "episode number without a season in the name" in flags:
                flags.remove("episode number without a season in the name")
        elif season != folder_season:
            flags.append(f"season {season} in the name, but the folder says season {folder_season}")

    if _COPY_SUFFIX.search(_TAGS.sub(" ", stem)):
        flags.append("the name ends in a copy number, e.g. ' (1)'")
    program = _clean_title(title_part) or None
    names = [n for n in (series_title, *aliases) if n]
    matched = _match(program, names)
    named = matched is not None
    subseries: str | None = None
    if matched is not None:
        name_matched, extra = matched
        # A film's own title is expected after the series name; it is not a program run.
        subseries = program if extra and kind is not EpisodeKind.MOVIE else None
        if name_matched == series_title:
            evidence.append("the name matches the series folder")
        else:
            evidence.append(f"the name matches a known title of the series ('{name_matched}')")
        if extra and kind is not EpisodeKind.MOVIE:
            flags.append(f"a separate program within the series? ('{extra}')")
    elif program and names:
        flags.append(f"the name '{program}' does not match the series folder or its known titles")
    elif not program:
        flags.append("the file name does not name a program")

    if episode is None and kind not in (EpisodeKind.MOVIE, EpisodeKind.OVA):
        confidence = Confidence.LOW
    elif (
        named
        and subseries is None
        and (season is not None or kind in (EpisodeKind.OVA, EpisodeKind.MOVIE))
    ):
        confidence = Confidence.HIGH
    elif named or (season is not None and program):
        confidence = Confidence.MEDIUM
    else:
        confidence = Confidence.LOW

    label = _episode_label(season, episode, kind, program)
    return EpisodeIdentity(
        program_title=program,
        season=season,
        episode=episode,
        kind=kind,
        label=label,
        confidence=confidence,
        subseries=subseries,
        evidence=tuple(evidence),
        flags=tuple(dict.fromkeys(flags)),
    )


def _episode_label(
    season: int | None, episode: int | None, kind: EpisodeKind, program: str | None
) -> str:
    if kind is EpisodeKind.MOVIE:
        return f"Film · {program}" if program else "Film"
    if kind is EpisodeKind.OVA:
        return f"OVA {episode}" if episode is not None else "OVA"
    if kind is EpisodeKind.SPECIAL:
        return f"S{season} · Special {episode}" if season is not None else f"Special {episode}"
    head = f"S{season} · E{episode}" if season is not None else f"Episode {episode}"
    if episode is None:
        return program or "Video"
    return f"{head} (recap)" if kind is EpisodeKind.RECAP else head


# ---------------------------------------------------------------------------
# chapters
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class ChapterIdentity:
    number: Decimal | None
    volume: int | None
    label: str
    confidence: Confidence
    evidence: tuple[str, ...] = ()
    flags: tuple[str, ...] = field(default_factory=tuple)


_CHAPTER = re.compile(r"^(?:ch(?:apter|ap)?|c|episode|ep)[\s_.-]*0*(\d+(?:\.\d+)?)(?:\b|$)", re.I)
_VOLUME = re.compile(r"(?:^|[\s_.-])vol(?:ume)?[\s_.-]*0*(\d{1,4})(?![0-9])", re.I)
_BARE_NUMBER = re.compile(r"^0*(\d+(?:\.\d+)?)$")


def identify_chapter(folder: str) -> ChapterIdentity:
    """A chapter number (and volume) from the folder a group of pages sits in."""
    parts = [p for p in folder.split("/") if p]
    evidence: list[str] = []
    number: Decimal | None = None
    volume: int | None = None
    for part in parts:
        found = _VOLUME.search(part)
        if found:
            volume = int(found.group(1))
            evidence.append(f"volume folder '{part}'")
    last = parts[-1] if parts else ""
    match = _CHAPTER.match(last) or _BARE_NUMBER.match(last)
    if match:
        try:
            number = Decimal(match.group(1))
        except InvalidOperation:
            number = None
    if number is not None:
        evidence.append(f"chapter folder '{last}'")
        text = format(number.normalize(), "f") if number == number.to_integral() else str(number)
        label = f"Chapter {text}"
        confidence = Confidence.HIGH if _CHAPTER.match(last) else Confidence.MEDIUM
        flags: tuple[str, ...] = (
            () if _CHAPTER.match(last) else ("a bare number taken as the chapter",)
        )
        return ChapterIdentity(number, volume, label, confidence, tuple(evidence), flags)
    if volume is not None:
        return ChapterIdentity(None, volume, f"Volume {volume}", Confidence.MEDIUM, tuple(evidence))
    return ChapterIdentity(
        None,
        None,
        last or "Pages",
        Confidence.LOW,
        tuple(evidence),
        ("the page folder does not name a chapter",),
    )
