"""The catalog's Vault files, in the shape the Library viewer already reads.

:class:`CatalogRecordSupplement` lets :class:`~continuum_storage.MediaLibrary`
open files the acquisition engine has not listed yet - an archive added last
night becomes readable as soon as the catalog has observed it, without waiting
for (or depending on) another engine scan.

It never adds a way to name a file: records are keyed by the Vault-relative
paths the catalog observed, and the viewer still resolves every one through the
hardened Source Vault reader.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Any

from continuum_core.catalog import DetectedKind, EntryStatus, MemberKind, ScanStatus
from continuum_db.models import CatalogEntry, CatalogMember, CatalogScan
from continuum_storage.survey import root_fingerprint
from sqlalchemy import func, select
from sqlalchemy.orm import Session

__all__ = ["CatalogRecordSupplement", "catalog_records"]

VAULT_ROOT_KEY = "source_vault"
_KINDS = {
    DetectedKind.ARCHIVE: "archive",
    DetectedKind.VIDEO: "video",
    DetectedKind.IMAGE: "image",
    DetectedKind.DOCUMENT: "document",
    DetectedKind.SOFTWARE: "software",
}


def catalog_records(session: Session) -> dict[str, dict[str, Any]]:
    """Every present Source Vault entry as an engine-shaped record."""
    entries = session.execute(
        select(CatalogEntry).where(
            CatalogEntry.root_key == VAULT_ROOT_KEY,
            CatalogEntry.status.in_(
                [EntryStatus.CATALOGUED, EntryStatus.UNSUPPORTED, EntryStatus.FAILED]
            ),
        )
    ).scalars()
    videos: dict[Any, list[dict[str, Any]]] = {}
    for member in session.execute(
        select(CatalogMember.entry_id, CatalogMember.name, CatalogMember.byte_size)
        .join(CatalogEntry, CatalogEntry.id == CatalogMember.entry_id)
        .where(CatalogEntry.root_key == VAULT_ROOT_KEY, CatalogMember.kind == MemberKind.VIDEO)
        .order_by(CatalogMember.entry_id, CatalogMember.position)
    ).all():
        videos.setdefault(member[0], []).append({"name": member[1], "size": int(member[2])})
    out: dict[str, dict[str, Any]] = {}
    for entry in entries:
        record: dict[str, Any] = {
            "size": int(entry.byte_size),
            "mtime_ns": int(entry.mtime_ns),
            "kind": _KINDS.get(entry.detected_kind, "other"),
            "ext": entry.extension,
            "source": "catalog",
        }
        if (
            entry.content_hash
            and entry.hashed_size == entry.byte_size
            and entry.hashed_mtime_ns == entry.mtime_ns
        ):
            record["sha256"] = entry.content_hash
        if entry.detected_kind is DetectedKind.ARCHIVE:
            software = entry.material_class.value == "SOFTWARE"
            record["archive"] = {
                "entries": int(entry.member_count),
                "images": int(entry.image_count),
                "videos": int(entry.video_count),
                "video_entries": videos.get(entry.id, []),
                "executables": 1 if software else 0,
            }
        out[entry.relative_path] = record
    return out


class CatalogRecordSupplement:
    """A :class:`~continuum_storage.media.RecordSupplement` backed by the catalog.

    Rebuilt only when the catalog's Vault entries change (count or newest
    update), so a request costs one small aggregate query.
    """

    def __init__(
        self, sessions: Callable[[], AbstractContextManager[Session]], vault_root: str = ""
    ) -> None:
        self._sessions = sessions
        self._fingerprint = root_fingerprint(vault_root) if vault_root else ""
        self._lock = threading.Lock()
        self._marker: object = None
        self._records: dict[str, dict[str, Any]] = {}

    def records(self) -> tuple[object, dict[str, dict[str, Any]]]:
        with self._sessions() as session:
            if self._fingerprint:
                scanned = session.execute(
                    select(CatalogScan.survey)
                    .where(
                        CatalogScan.root_key == VAULT_ROOT_KEY,
                        CatalogScan.status == ScanStatus.COMPLETED,
                    )
                    .order_by(CatalogScan.finished_at.desc(), CatalogScan.id.desc())
                    .limit(1)
                ).scalar_one_or_none()
                if (scanned or {}).get("root_fingerprint") != self._fingerprint:
                    # The catalog describes another folder (or none yet): offer nothing.
                    return ("other-folder",), {}
            marker = tuple(
                session.execute(
                    select(func.count(), func.max(CatalogEntry.updated_at)).where(
                        CatalogEntry.root_key == VAULT_ROOT_KEY
                    )
                ).one()
            )
            with self._lock:
                if marker != self._marker:
                    self._records = catalog_records(session)
                    self._marker = marker
                return self._marker, self._records

    def forget(self) -> None:
        with self._lock:
            self._marker = None
            self._records = {}
