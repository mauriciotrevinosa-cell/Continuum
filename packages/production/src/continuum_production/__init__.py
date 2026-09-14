"""Phase 1 rough manga production over the reference vault.

Recipes (intent + execution, hashed separately), reference bundles by role,
append-only attempts rendered by a durable worker job, review, and approved
attempts promoted to continuity references. Source media is only ever read.
"""

from continuum_production.recipe import (
    RECIPE_SCHEMA_VERSION,
    TEMPLATE_PACKAGE_VERSION,
    BundleEntry,
    CharacterDirection,
    EditOperation,
    Placement,
    RoughIntentSpec,
    regions_overlap,
)
from continuum_production.render import SourceAssetMissingError, render_attempt
from continuum_production.service import DEFAULT_WORKFLOW, ROUGH_JOB_TYPE, RoughProduction
from continuum_production.views import artifact_view, attempt_view, provenance_view

__all__ = [
    "DEFAULT_WORKFLOW",
    "RECIPE_SCHEMA_VERSION",
    "ROUGH_JOB_TYPE",
    "TEMPLATE_PACKAGE_VERSION",
    "BundleEntry",
    "CharacterDirection",
    "EditOperation",
    "Placement",
    "RoughIntentSpec",
    "RoughProduction",
    "SourceAssetMissingError",
    "artifact_view",
    "attempt_view",
    "provenance_view",
    "regions_overlap",
    "render_attempt",
]
