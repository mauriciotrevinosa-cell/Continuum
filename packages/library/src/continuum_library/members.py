"""Watching a video that lives inside a compressed archive.

The catalog knows each archived video member from the archive's central
directory. Asking to watch one queues a durable extraction job; the worker
copies that single member, verified, into the bounded member cache; the player
then streams the cached copy with byte ranges. The archive is only ever read.

State shown to people is honest: *not prepared*, *preparing* (with the job),
*ready*, or *unavailable* with the reason.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from continuum_core.catalog import EntryStatus, MemberKind
from continuum_db.models import CatalogEntry, CatalogMember, CatalogUnit, Job
from continuum_jobs import is_terminal
from continuum_storage.member_cache import MemberCache
from continuum_storage.survey import CatalogRoot
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from continuum_library.validation import CatalogNotFoundError
from continuum_library.vault_jobs import MEMBER_EXTRACT_JOB, request_member_extraction

__all__ = ["MEMBER_TYPES", "extract_member", "member_record", "member_state", "prepare_member"]

MEMBER_TYPES: dict[str, str] = {
    ".mp4": "video/mp4",
    ".m4v": "video/mp4",
    ".webm": "video/webm",
    ".mkv": "video/x-matroska",
    ".mov": "video/quicktime",
    ".avi": "video/x-msvideo",
    ".ts": "video/mp2t",
}


def member_record(session: Session, member_id: uuid.UUID) -> tuple[CatalogMember, CatalogEntry]:
    found = session.execute(
        select(CatalogMember, CatalogEntry)
        .join(CatalogEntry, CatalogEntry.id == CatalogMember.entry_id)
        .where(CatalogMember.id == member_id, CatalogMember.kind == MemberKind.VIDEO)
    ).first()
    if found is None:
        raise CatalogNotFoundError("That video is not in the catalog.")
    return found[0], found[1]


def _latest_job(session: Session, member_id: uuid.UUID) -> Job | None:
    return session.execute(
        select(Job)
        .where(
            Job.job_type == MEMBER_EXTRACT_JOB, Job.payload["member_id"].astext == str(member_id)
        )
        .order_by(Job.created_at.desc(), Job.id.desc())
        .limit(1)
    ).scalar_one_or_none()


def member_state(
    session: Session, member_id: uuid.UUID, cache: MemberCache | None
) -> dict[str, Any]:
    member, entry = member_record(session, member_id)
    extension = "." + member.name.rsplit(".", 1)[-1].lower() if "." in member.name else ""
    ready = bool(member.cached_sha256 and cache is not None and cache.has(member.cached_sha256))
    job = _latest_job(session, member_id)
    state = "ready" if ready else "not_prepared"
    detail = ""
    if not ready and job is not None and not is_terminal(job.status):
        state = "preparing"
    elif not ready and job is not None and job.status.value in ("FAILED_FINAL", "BLOCKED"):
        state = "unavailable"
        error = job.last_error or job.remediation or {}
        detail = str(error.get("user_message") or error.get("message") or "")
    if entry.status is not EntryStatus.CATALOGUED:
        state, detail = "unavailable", "The archive is not in the Vault as catalogued."
    unit = session.execute(
        select(CatalogUnit).where(CatalogUnit.member_id == member.id).limit(1)
    ).scalar_one_or_none()
    return {
        "unit": {
            "id": str(unit.id),
            "label": unit.label,
            "series_key": unit.series_key,
            "series_title": unit.series_title,
            "season": unit.season,
            "episode": unit.episode,
            "confidence": unit.confidence.value,
            "flags": list(unit.flags or []),
        }
        if unit is not None
        else None,
        "member_id": str(member.id),
        "name": member.name.rsplit("/", 1)[-1],
        "archive": entry.file_name,
        "byte_size": int(member.byte_size),
        "compressed_size": int(member.compressed_size),
        "content_type": MEMBER_TYPES.get(extension, "application/octet-stream"),
        "plays_in_browser": "yes" if extension in (".mp4", ".m4v", ".webm") else "maybe",
        "state": state,
        "detail": detail,
        "job_id": str(job.id) if job is not None else None,
        "job_status": job.status.value if job is not None else None,
        "cached_sha256": member.cached_sha256 if ready else None,
    }


def prepare_member(
    session: Session, member_id: uuid.UUID, cache: MemberCache | None
) -> dict[str, Any]:
    """Queue the extraction unless the member is already cached."""
    state = member_state(session, member_id, cache)
    if state["state"] in ("ready", "preparing"):
        return state
    request_member_extraction(session, member_id)
    return member_state(session, member_id, cache)


def extract_member(
    session: Session,
    member_id: uuid.UUID,
    *,
    root: CatalogRoot,
    cache: MemberCache,
) -> dict[str, Any]:
    """Extract one member into the cache and record it. Repeat-safe."""
    member, entry = member_record(session, member_id)
    if entry.root_key != root.key or entry.status is not EntryStatus.CATALOGUED:
        raise CatalogNotFoundError("That archive is not in the Vault as catalogued.")
    # Least recently used goes first: every byte-range read refreshes a member's
    # use time, so the video someone is watching is the last one evicted.
    cached = cache.extract(
        root,
        entry.relative_path,
        member.name,
        expected_size=int(member.byte_size),
        expected_crc=member.crc32,
        known_sha256=member.cached_sha256,
    )
    now = dt.datetime.now(dt.UTC)
    if cached.evicted:
        session.execute(
            update(CatalogMember)
            .where(CatalogMember.cached_sha256.in_(list(cached.evicted)))
            .values(cached_sha256=None, cached_at=None)
            .execution_options(synchronize_session=False)
        )
    # The same bytes may sit in several archives (a re-download): all share the copy.
    session.execute(
        update(CatalogMember)
        .where(
            CatalogMember.kind == MemberKind.VIDEO,
            CatalogMember.byte_size == member.byte_size,
            CatalogMember.crc32 == member.crc32,
            CatalogMember.name == member.name,
        )
        .values(cached_sha256=cached.sha256, cached_at=now, last_used_at=now)
        .execution_options(synchronize_session=False)
    )
    session.flush()
    return {
        "member_id": str(member_id),
        "sha256": cached.sha256,
        "bytes": cached.size_bytes,
        "already_present": cached.already_present,
        "evicted": len(cached.evicted),
    }
