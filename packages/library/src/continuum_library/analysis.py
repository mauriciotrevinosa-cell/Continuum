"""Persisted manga page analysis (Visual Knowledge, M3).

An analysis is computed once per page and analyzer version, then read from the
database: restarting the API never re-reads and re-measures pages it already
analysed. Rows hold regions and measures, never pixels, and are rebuildable.
"""

from __future__ import annotations

import re
from typing import Any

from continuum_db.models import PageAnalysis
from continuum_providers.analysis import AnalyzerInfo
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from continuum_library.validation import CatalogInputError

__all__ = ["PageAnalyses", "unit_subject"]

_SUBJECT = re.compile(r"^(unit:[0-9a-f]{16,64}:[0-9]{1,6}|sha256:[0-9a-f]{64})$")


def unit_subject(unit_key: str, offset: int) -> str:
    """The analysis subject for one page of a catalogued chapter."""
    return f"unit:{unit_key}:{offset}"


class PageAnalyses:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, subject: str, analyzer: AnalyzerInfo) -> PageAnalysis | None:
        return self.session.execute(
            select(PageAnalysis).where(
                PageAnalysis.subject == subject,
                PageAnalysis.analyzer_id == analyzer.id,
                PageAnalysis.analyzer_version == analyzer.version,
            )
        ).scalar_one_or_none()

    def record(
        self,
        subject: str,
        *,
        locator: str,
        analyzer: AnalyzerInfo,
        result: dict[str, Any],
        content_sha256: str | None = None,
    ) -> PageAnalysis:
        """Store an analysis once; a repeat (another process, a retried job) is a no-op."""
        if not _SUBJECT.match(subject):
            raise CatalogInputError(f"{subject[:60]!r} is not a page analysis subject.")
        self.session.execute(
            insert(PageAnalysis)
            .values(
                subject=subject,
                locator=locator,
                content_sha256=content_sha256,
                analyzer_id=analyzer.id,
                analyzer_version=analyzer.version,
                model_sha256=analyzer.model_sha256,
                result=result,
            )
            .on_conflict_do_nothing(index_elements=["subject", "analyzer_id", "analyzer_version"])
        )
        found = self.get(subject, analyzer)
        assert found is not None
        return found
