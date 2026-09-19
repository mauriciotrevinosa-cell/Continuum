"""The manga page analyzer boundary (Visual Knowledge, M3).

``analyze_page(bytes) -> regions`` - panels, text, faces, bodies, characters,
balloons - each a normalized box with a confidence, plus a reading order and
the analyzer's own lineage (id, version, model hash, license, and the external
resource it comes from). Continuum's domain code depends on this contract, never
on a detector: a pretrained YOLO/RT-DETR/segmentation model or a learned panel
order estimator plugs in as another analyzer, and results are stored per
analyzer version so two analyzers never overwrite each other.

The first analyzer is local and model-free: recursive gutter cuts
(:func:`continuum_imaging.manga.analyze_layout`) for panels and the
deterministic right-to-left row order.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

__all__ = [
    "AnalyzerInfo",
    "GutterLayoutAnalyzer",
    "MangaPageAnalyzer",
    "PageAnalysis",
    "PageRegion",
    "RegionKind",
]


class RegionKind(StrEnum):
    PANEL = "PANEL"
    TEXT = "TEXT"
    BALLOON = "BALLOON"
    FACE = "FACE"
    BODY = "BODY"
    CHARACTER = "CHARACTER"


@dataclass(frozen=True, slots=True)
class AnalyzerInfo:
    id: str
    version: str
    #: The weights' sha256; None for a model-free analyzer.
    model_sha256: str | None = None
    license: str = ""
    #: The external resource (registry key) the analyzer or its weights come from.
    resource_key: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "version": self.version,
            "model_sha256": self.model_sha256,
            "license": self.license,
            "resource_key": self.resource_key,
        }


@dataclass(frozen=True, slots=True)
class PageRegion:
    kind: RegionKind
    #: Normalized box on the page: x, y, width, height in 0..1.
    box: tuple[float, float, float, float]
    confidence: float | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "box": [round(v, 5) for v in self.box],
            "confidence": self.confidence,
        }


@dataclass(frozen=True, slots=True)
class PageAnalysis:
    analyzer: AnalyzerInfo
    width: int
    height: int
    regions: tuple[PageRegion, ...]
    #: Indices into ``regions`` of the PANEL regions, in reading order.
    reading_order: tuple[int, ...] = ()
    #: Page-level measures (negative space, ink density...), analyzer-defined.
    measures: dict[str, float] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "analyzer": self.analyzer.as_dict(),
            "width": self.width,
            "height": self.height,
            "regions": [region.as_dict() for region in self.regions],
            "reading_order": list(self.reading_order),
            "measures": dict(self.measures),
        }


@runtime_checkable
class MangaPageAnalyzer(Protocol):
    info: AnalyzerInfo

    def analyze_page(self, data: bytes) -> PageAnalysis: ...


class GutterLayoutAnalyzer:
    """Panels by recursive gutter cuts; right-to-left rows. Local, model-free."""

    info = AnalyzerInfo(
        id="local.gutter-layout",
        version="1",
        model_sha256=None,
        license="Continuum code; no model weights",
    )

    def analyze_page(self, data: bytes) -> PageAnalysis:
        from continuum_imaging.manga import analyze_layout, rtl_reading_order

        layout = analyze_layout(data)
        regions = tuple(PageRegion(RegionKind.PANEL, box) for box in layout.panels)
        return PageAnalysis(
            analyzer=self.info,
            width=layout.width,
            height=layout.height,
            regions=regions,
            reading_order=rtl_reading_order(layout.panels),
            measures={
                "panel_count": float(layout.panel_count),
                "largest_panel_share": round(layout.largest_panel_share, 4),
                "negative_space": layout.negative_space,
                "ink_density": layout.ink_density,
            },
        )
