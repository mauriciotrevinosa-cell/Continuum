"""Read models for rough production: artifact history, attempts, provenance.

The provenance view reconstructs the whole chain for one attempt, from the
recorded rows alone:

    original source (locator + page) -> region -> bundle role -> recipe
    (intent + execution hashes) -> job -> derivatives (crop, mask, output)
    -> reviews -> parent attempt

Displayed state folds in the render job: a QUEUED attempt whose job is
BLOCKED shows as BLOCKED with the job's reason and remediation; a failed job
shows FAILED. The stored attempt state never pretends otherwise.

Every view says what an attempt can mean: the artifact's purpose (production,
workflow test, non-canon sample), whether its image is artwork or a test
render, and which review decisions are possible. Only production artifacts
count toward completion, and only through creative or final approval.
"""

from __future__ import annotations

from typing import Any

from continuum_core.references import (
    CREATIVE_STATES,
    AttemptState,
    BundleRole,
    RenderOutput,
    RoughPurpose,
)
from continuum_db.models import Job, RoughArtifact, RoughAttempt
from continuum_library import CatalogNotFoundError, region_of

from continuum_production.service import RoughProduction, allowed_decisions

__all__ = ["artifact_view", "attempt_view", "completion_view", "provenance_view"]


def _iso(value: Any) -> str | None:
    return value.isoformat() if value is not None else None


def _job(production: RoughProduction, attempt: RoughAttempt) -> dict[str, Any] | None:
    if attempt.job_id is None:
        return None
    job = production.session.get(Job, attempt.job_id)
    if job is None:
        return None
    last_error = job.last_error or {}
    return {
        "id": str(job.id),
        "status": job.status.value,
        "blocked_reason": job.blocked_reason.value if job.blocked_reason else None,
        "remediation": job.remediation,
        "error": last_error.get("user_message"),
        "error_remediation": last_error.get("remediation"),
        "attempts": job.attempt,
    }


def display_state(attempt: RoughAttempt, job: dict[str, Any] | None) -> str:
    if attempt.state is not AttemptState.QUEUED or job is None:
        return attempt.state.value
    if job["status"] in ("BLOCKED", "FAILED", "CANCELLED", "PAUSED"):
        return str(job["status"])
    if job["status"] == "RUNNING":
        return "RENDERING"
    return "QUEUED"


def attempt_summary(
    production: RoughProduction, attempt: RoughAttempt, artifact: RoughArtifact | None = None
) -> dict[str, Any]:
    recipe = production.recipe(attempt.recipe_id)
    job = _job(production, attempt)
    artifact = artifact or production.artifact(attempt.artifact_id)
    return {
        "id": str(attempt.id),
        "artifact_id": str(attempt.artifact_id),
        "attempt": attempt.attempt,
        "state": attempt.state.value,
        "display_state": display_state(attempt, job),
        "output_class": attempt.output_class.value if attempt.output_class else None,
        #: Never manga, whatever its review says: a test render, or a test/sample artifact.
        "test_only": attempt.output_class is RenderOutput.TEST_RENDER
        or artifact.purpose is not RoughPurpose.PRODUCTION,
        "allowed_decisions": [d.value for d in allowed_decisions(artifact, attempt)],
        "mode": recipe.mode.value,
        "seed": recipe.execution.get("seed"),
        "content_hash": attempt.content_hash,
        "width": attempt.width,
        "height": attempt.height,
        "parent_attempt_id": str(attempt.parent_attempt_id) if attempt.parent_attempt_id else None,
        "created_at": _iso(attempt.created_at),
        "generated_at": _iso(attempt.generated_at),
        "job": job,
    }


def artifact_view(production: RoughProduction, artifact: RoughArtifact) -> dict[str, Any]:
    attempts = production.attempts(artifact.id)
    creative = next((a for a in attempts if a.state in CREATIVE_STATES), None)
    final = next((a for a in attempts if a.state is AttemptState.FINAL_APPROVED), None)
    passed = next((a for a in attempts if a.state is AttemptState.TECHNICAL_PASS), None)
    production_work = artifact.purpose is RoughPurpose.PRODUCTION
    return {
        "id": str(artifact.id),
        "project_key": artifact.project_key,
        "episode": artifact.episode,
        "chapter": artifact.chapter,
        "page": artifact.page,
        "panel": artifact.panel,
        "kind": artifact.kind.value,
        "purpose": artifact.purpose.value,
        "test_only": not production_work,
        "title": artifact.title,
        "brief": artifact.brief,
        "panel_script": {
            "document": artifact.panel_script_document,
            "version": artifact.panel_script_version,
        },
        "created_at": _iso(artifact.created_at),
        "creative_approved_attempt_id": str(creative.id) if creative else None,
        "final_approved_attempt_id": str(final.id) if final else None,
        "technical_pass_attempt_id": str(passed.id) if passed else None,
        #: Whether this artifact counts toward rough/final manga completion now.
        "counts_toward_completion": production_work and creative is not None,
        "attempts": [attempt_summary(production, a, artifact) for a in attempts],
    }


def completion_view(production: RoughProduction, project_key: str) -> dict[str, Any]:
    """How much rough manga exists, counting production work only.

    Workflow tests and non-canon samples are reported beside it, never inside it.
    """
    out: dict[str, Any] = {
        "production": {"artifacts": 0, "creative_approved": 0, "final_approved": 0},
        "workflow_tests": {"artifacts": 0, "technical_pass": 0},
        "non_canon_samples": {"artifacts": 0, "technical_pass": 0},
    }
    keys = {
        RoughPurpose.PRODUCTION: "production",
        RoughPurpose.WORKFLOW_TEST: "workflow_tests",
        RoughPurpose.NON_CANON_SAMPLE: "non_canon_samples",
    }
    for artifact in production.artifacts(project_key):
        bucket = out[keys[artifact.purpose]]
        bucket["artifacts"] += 1
        states = {a.state for a in production.attempts(artifact.id)}
        if artifact.purpose is RoughPurpose.PRODUCTION:
            if states & CREATIVE_STATES:
                bucket["creative_approved"] += 1
            if AttemptState.FINAL_APPROVED in states:
                bucket["final_approved"] += 1
        elif AttemptState.TECHNICAL_PASS in states:
            bucket["technical_pass"] += 1
    return out


def attempt_view(production: RoughProduction, attempt: RoughAttempt) -> dict[str, Any]:
    recipe = production.recipe(attempt.recipe_id)
    catalog = production.catalog
    bundle: dict[str, list[dict[str, Any]]] = {role.value: [] for role in BundleRole}
    for row in production.inputs(attempt.id):
        region = region_of(row)
        entry: dict[str, Any] = {
            "position": row.position,
            "role": row.role.value,
            "reference_id": str(row.reference_id) if row.reference_id else None,
            "locator": row.locator,
            "unit_index": row.unit_index,
            "region": region.as_dict() if region else None,
            "character_id": str(row.character_id) if row.character_id else None,
            "outfit_id": str(row.outfit_id) if row.outfit_id else None,
            "aspect": row.aspect.value if row.aspect else None,
            "label": row.label,
            "provenance": row.provenance,
            "reference_available": False,
            "source": {"available": False},
        }
        if row.reference_id is not None:
            try:
                item = catalog.reference(row.reference_id, include_removed=True)
            except CatalogNotFoundError:
                item = None
            if item is not None:
                entry["reference_available"] = item.removed_at is None
                entry["reference_origin"] = item.origin.value
                entry["source"] = catalog.source_position(item)
        bundle[row.role.value].append(entry)
    return {
        **attempt_summary(production, attempt),
        "purpose": production.artifact(attempt.artifact_id).purpose.value,
        "recipe": {
            "id": str(recipe.id),
            "mode": recipe.mode.value,
            "schema": recipe.recipe_schema_version,
            "template_package_version": recipe.template_package_version,
            "intent_hash": recipe.intent_hash,
            "execution_hash": recipe.execution_hash,
            "intent": recipe.intent,
            "execution": recipe.execution,
        },
        "bundle": bundle,
        "derivatives": [
            {
                "kind": d.kind.value,
                "content_hash": d.content_hash,
                "mime": d.mime,
                "width": d.width,
                "height": d.height,
                "detail": d.detail,
            }
            for d in production.derivatives(attempt.id)
        ],
        "reviews": [
            {
                "decision": r.decision.value,
                "notes": r.notes,
                "decided_at": _iso(r.decided_at),
                "reclassified_from": r.reclassified_from,
            }
            for r in production.reviews(attempt.id)
        ],
    }


def provenance_view(production: RoughProduction, attempt: RoughAttempt) -> dict[str, Any]:
    """The chain from original source to this attempt's bytes, and its ancestry."""
    artifact = production.artifact(attempt.artifact_id)
    view = attempt_view(production, attempt)
    lineage: list[dict[str, Any]] = []
    parent_id = attempt.parent_attempt_id
    while parent_id is not None and len(lineage) < 100:
        parent = production.attempt(parent_id)
        lineage.append({"attempt_id": str(parent.id), "attempt": parent.attempt})
        parent_id = parent.parent_attempt_id
    output = next((d for d in view["derivatives"] if d["kind"] == "OUTPUT"), None)
    return {
        "artifact": {
            "id": str(artifact.id),
            "project_key": artifact.project_key,
            "episode": artifact.episode,
            "chapter": artifact.chapter,
            "page": artifact.page,
            "panel": artifact.panel,
            "purpose": artifact.purpose.value,
            "panel_script": view["recipe"]["intent"].get("panel_script"),
        },
        "sources": [
            {
                "role": entry["role"],
                "locator": entry["locator"],
                "region": entry["region"],
                "reference_id": entry["reference_id"],
                "source": entry["source"],
                "provenance": entry["provenance"],
            }
            for entries in view["bundle"].values()
            for entry in entries
        ],
        "recipe": {
            "mode": view["recipe"]["mode"],
            "intent_hash": view["recipe"]["intent_hash"],
            "execution_hash": view["recipe"]["execution_hash"],
            "operations": view["recipe"]["intent"].get("operations"),
            "seed": view["recipe"]["execution"].get("seed"),
            "workflow": view["recipe"]["execution"].get("workflow"),
        },
        "job": view["job"],
        "derivatives": view["derivatives"],
        "rendered_with": (output or {}).get("detail", {}).get("rendered_with"),
        "output_hash": attempt.content_hash,
        "output_class": view["output_class"],
        "reviews": view["reviews"],
        "lineage": lineage,
    }
