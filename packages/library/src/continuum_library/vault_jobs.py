"""Job types of the full-Vault catalog, and how the API asks for them.

The API only enqueues (ADR-0002): every scan, hash pass, import and member
extraction runs in the worker as a durable job. Requests deduplicate - asking
twice while a scan is still running returns the running scan's job.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from continuum_db.models import Job
from continuum_jobs import enqueue
from sqlalchemy.orm import Session

__all__ = [
    "CATALOG_HASH_JOB",
    "CATALOG_SCAN_JOB",
    "INTAKE_IMPORT_JOB",
    "MEMBER_EXTRACT_JOB",
    "RequestedJobs",
    "request_hash",
    "request_import",
    "request_member_extraction",
    "request_scan",
]

CATALOG_SCAN_JOB = "library.catalog_scan"
CATALOG_HASH_JOB = "library.catalog_hash"
INTAKE_IMPORT_JOB = "library.intake_import"
MEMBER_EXTRACT_JOB = "library.member_extract"


@dataclass(frozen=True, slots=True)
class RequestedJobs:
    root_key: str
    scan: Job
    hash: Job | None
    created: bool


def request_scan(
    session: Session, root_keys: Sequence[str], *, hash_after: bool = True
) -> list[RequestedJobs]:
    """Queue a scan of each root, and a hash pass that waits for it."""
    out: list[RequestedJobs] = []
    for root_key in root_keys:
        scan, created = enqueue(
            session,
            CATALOG_SCAN_JOB,
            payload={"root_key": root_key},
            priority=5,
            max_attempts=5,
        )
        hashed: Job | None = None
        if hash_after:
            hashed, _ = enqueue(
                session,
                CATALOG_HASH_JOB,
                payload={"root_key": root_key},
                priority=1,
                max_attempts=5,
                depends_on=[scan.id],
            )
        out.append(RequestedJobs(root_key, scan, hashed, created))
    session.flush()
    return out


def request_hash(session: Session, root_key: str) -> Job:
    job, _ = enqueue(session, CATALOG_HASH_JOB, payload={"root_key": root_key}, priority=1)
    session.flush()
    return job


def request_import(session: Session, root_key: str) -> RequestedJobs:
    """Rescan a collection, hash it, then import it - in that order."""
    requested = request_scan(session, [root_key], hash_after=True)[0]
    after = [requested.hash.id] if requested.hash is not None else [requested.scan.id]
    job, _ = enqueue(
        session,
        INTAKE_IMPORT_JOB,
        payload={"root_key": root_key},
        priority=3,
        depends_on=after,
    )
    session.flush()
    return RequestedJobs(root_key, requested.scan, job, requested.created)


def request_member_extraction(session: Session, member_id: uuid.UUID) -> Job:
    job, _ = enqueue(
        session,
        MEMBER_EXTRACT_JOB,
        payload={"member_id": str(member_id)},
        priority=8,
        max_attempts=3,
    )
    session.flush()
    return job
