"""Page analysis behind the analyzer boundary, persisted per analyzer version.

A grammar candidate is measured once: a new process (an empty in-memory cache)
reads the stored analysis instead of re-reading and re-measuring the page, and
a different analyzer version never reuses another version's result.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from continuum_config import Settings
from continuum_db.models import CatalogEntry, CatalogUnit, PageAnalysis
from continuum_db.session import session_scope
from continuum_imaging.manga import panel_boxes, rtl_reading_order
from continuum_library.analysis import PageAnalyses, unit_subject
from continuum_production.manga import catalog_grammar_candidates
from continuum_providers.analysis import (
    AnalyzerInfo,
    GutterLayoutAnalyzer,
    PageRegion,
    RegionKind,
)
from continuum_providers.analysis import (
    PageAnalysis as Analysis,
)
from PIL import Image, ImageDraw
from sqlalchemy import func, select

from tests.phase1_world import clean_domain_tables
from tests.phase15_world import Phase15World, build_phase15_world

pytestmark = pytest.mark.requires_db


def _page(boxes: list[tuple[int, int, int, int]]) -> bytes:
    import io

    image = Image.new("L", (400, 600), 255)
    draw = ImageDraw.Draw(image)
    for box in boxes:
        draw.rectangle(box, outline=0, width=4)
        draw.line((box[0], box[1], box[2], box[3]), fill=0, width=3)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


THREE_PANELS = _page([(20, 20, 380, 180), (210, 200, 380, 400), (20, 200, 190, 400)])


def test_rtl_reading_order_reads_rows_top_down_and_right_to_left() -> None:
    boxes = [(0.0, 0.0, 0.45, 0.4), (0.55, 0.0, 0.45, 0.4), (0.0, 0.5, 1.0, 0.5)]
    assert rtl_reading_order(boxes) == (1, 0, 2)
    # Continuum's own RTL templates are already in reading order.
    for count in range(1, 7):
        assert rtl_reading_order(panel_boxes(count)) == tuple(range(count))


def test_gutter_analyzer_reports_panels_order_and_lineage() -> None:
    analysis = GutterLayoutAnalyzer().analyze_page(THREE_PANELS)
    panels = [r for r in analysis.regions if r.kind is RegionKind.PANEL]
    assert len(panels) == 3
    assert analysis.measures["panel_count"] == 3.0
    # The right panel of the second row is read before the left one.
    second_row = [analysis.regions[i].box for i in analysis.reading_order[1:]]
    assert second_row[0][0] > second_row[1][0]
    body = analysis.as_dict()
    assert body["analyzer"] == {
        "id": "local.gutter-layout",
        "version": "1",
        "model_sha256": None,
        "license": "Continuum code; no model weights",
        "resource_key": None,
    }


@pytest.fixture
def world(tmp_path: Path, db_settings: Settings) -> Phase15World:
    with session_scope(db_settings) as session:
        clean_domain_tables(session)
    return build_phase15_world(tmp_path)


def _chapters(session: Any, series: str, count: int) -> list[tuple[CatalogUnit, CatalogEntry]]:
    """Synthetic catalogued chapters: rows only; bytes come from the fake reader."""
    from continuum_core.catalog import (
        Confidence,
        DetectedKind,
        EntryStatus,
        MaterialClass,
        UnitKind,
    )

    out = []
    for index in range(count):
        entry = CatalogEntry(
            root_key="source_vault",
            relative_path=f"Demo/ch{index:03d}.cbz",
            file_name=f"ch{index:03d}.cbz",
            byte_size=100,
            mtime_ns=1,
            detected_kind=DetectedKind.ARCHIVE,
            material_class=MaterialClass.MANGA,
            status=EntryStatus.CATALOGUED,
            scanner_version=1,
        )
        session.add(entry)
        session.flush()
        unit = CatalogUnit(
            entry_id=entry.id,
            unit_key=f"{index:040x}",
            kind=UnitKind.MANGA_CHAPTER,
            material_class=MaterialClass.MANGA,
            confidence=Confidence.HIGH,
            series_key=series,
            label=f"Chapter {index + 1}",
            sort_key=f"{index:05d}",
            page_count=8,
        )
        session.add(unit)
        out.append((unit, entry))
    session.flush()
    return out


def test_grammar_candidates_are_measured_once_across_processes(world: Phase15World) -> None:
    reads: list[str] = []

    def reader(unit: CatalogUnit, _entry: CatalogEntry, offset: int) -> tuple[str, bytes]:
        reads.append(f"{unit.unit_key}:{offset}")
        return f"unit:{unit.unit_key}:{offset}", THREE_PANELS

    settings = world.settings()
    with session_scope(settings) as session:
        try:
            _chapters(session, "demo-series", 3)
        except TypeError as exc:  # the catalog schema moved; the test must follow it
            pytest.fail(f"synthetic catalog rows no longer match the models: {exc}")
        first = catalog_grammar_candidates(session, reader, GutterLayoutAnalyzer())
        found = first(["demo-series"], 3)
        session.commit()
    assert len(found) == 3 and len(reads) == 3
    assert {c.panel_count for c in found} == {3}

    # A new process: empty in-memory cache, a reader that must not be called.
    def refuse(*_args: Any) -> tuple[str, bytes]:
        raise AssertionError("a stored analysis was read and measured again")

    with session_scope(settings) as session:
        again = catalog_grammar_candidates(session, refuse, GutterLayoutAnalyzer())
        assert [c.locator for c in again(["demo-series"], 3)] == [c.locator for c in found]
        stored = session.execute(select(func.count()).select_from(PageAnalysis)).scalar_one()
        assert stored == 3

    # Another analyzer version never reuses this version's result.
    class Next(GutterLayoutAnalyzer):
        info = AnalyzerInfo(id="local.gutter-layout", version="2", license="test")

    with session_scope(settings) as session:
        newer = catalog_grammar_candidates(session, reader, Next())
        newer(["demo-series"], 3)
        session.commit()
    assert len(reads) == 6


def test_the_store_is_idempotent_and_refuses_paths(world: Phase15World) -> None:
    analyzer = AnalyzerInfo(id="double.detector", version="0.1", model_sha256="a" * 64)
    result: Callable[[], dict[str, Any]] = lambda: Analysis(  # noqa: E731
        analyzer=analyzer,
        width=10,
        height=10,
        regions=(PageRegion(RegionKind.FACE, (0.1, 0.1, 0.2, 0.2), 0.9),),
    ).as_dict()
    with session_scope(world.settings()) as session:
        store = PageAnalyses(session)
        subject = unit_subject("f" * 40, 3)
        one = store.record(
            subject, locator="gen:sha256:" + "b" * 64, analyzer=analyzer, result=result()
        )
        two = store.record(
            subject, locator="gen:sha256:" + "b" * 64, analyzer=analyzer, result=result()
        )
        assert one.id == two.id
        assert one.model_sha256 == "a" * 64
        from continuum_library import CatalogInputError

        with pytest.raises(CatalogInputError):
            store.record("C:/pages/1.png", locator="x", analyzer=analyzer, result=result())
        session.rollback()


def test_the_analysis_job_resumes_without_rereading(world: Phase15World) -> None:
    from continuum_db.models import Job
    from continuum_production.analysis_jobs import request_page_analysis
    from continuum_worker import register_default_handlers
    from continuum_worker.main import Worker

    settings = world.settings()
    register_default_handlers()
    with session_scope(settings) as session:
        chapters = _chapters(session, "demo-series", 3)
        # Two pages were analysed before (an earlier job, or grammar retrieval).
        store = PageAnalyses(session)
        info = GutterLayoutAnalyzer.info
        body = GutterLayoutAnalyzer().analyze_page(THREE_PANELS).as_dict()
        for unit, _entry in chapters[:2]:
            store.record(
                unit_subject(unit.unit_key, 4),
                locator=f"unit:{unit.unit_key}:4",
                analyzer=info,
                result=body,
            )
        job, created = request_page_analysis(session, series_keys=["demo-series"], per_series=3)
        again, created_again = request_page_analysis(
            session, series_keys=["demo-series"], per_series=3
        )
        session.commit()
        job_id = job.id
    assert created and not created_again and again.id == job_id

    worker = Worker(settings)
    worker.register()
    ran = 0
    while ran < 5 and worker.run_once():
        ran += 1
    with session_scope(settings) as session:
        finished = session.get(Job, job_id)
        assert finished is not None and finished.status.value == "SUCCEEDED"
        stored = session.execute(select(func.count()).select_from(PageAnalysis)).scalar_one()
        # The third chapter has no bytes in this synthetic catalog: reported, not fatal.
        assert stored == 2
