"""Every table's phase and ADR-0003 tier, declared in one place.

Two invariants are checked against this registry (``tests/invariants``):

* the ORM metadata contains **exactly** the declared tables - a new table is a
  deliberate, reviewed act, not a side effect;
* foreign keys point only **downward**: D (generated) -> C (project) ->
  B (interpretation / catalog) -> A (observed). Operational tables (jobs,
  workers) sit outside the domain tiers; domain tables may reference them,
  never the reverse.
"""

from __future__ import annotations

from enum import IntEnum

__all__ = ["TABLE_REGISTRY", "Tier"]


class Tier(IntEnum):
    """Ordered so that a valid foreign key never points to a higher tier."""

    OPERATIONAL = 0
    A_OBSERVED = 1
    B_INTERPRETATION = 2
    C_PROJECT = 3
    D_GENERATED = 4


#: table name -> (phase introduced, tier)
TABLE_REGISTRY: dict[str, tuple[int, Tier]] = {
    # Phase 0 - durable jobs (ADR-0002, ADR-0006)
    "job": (0, Tier.OPERATIONAL),
    "job_step": (0, Tier.OPERATIONAL),
    "job_checkpoint": (0, Tier.OPERATIONAL),
    "job_dependency": (0, Tier.OPERATIONAL),
    "job_event": (0, Tier.OPERATIONAL),
    "worker": (0, Tier.OPERATIONAL),
    # Phase 1 - reference vault
    "library_asset": (1, Tier.A_OBSERVED),
    "library_asset_location": (1, Tier.A_OBSERVED),
    "character_profile": (1, Tier.B_INTERPRETATION),
    "character_outfit": (1, Tier.B_INTERPRETATION),
    "visual_mode": (1, Tier.B_INTERPRETATION),
    "reference_item": (1, Tier.B_INTERPRETATION),
    "reference_character": (1, Tier.B_INTERPRETATION),
    "reference_technique": (1, Tier.B_INTERPRETATION),
    "reference_descriptor": (1, Tier.B_INTERPRETATION),
    "reference_use": (1, Tier.B_INTERPRETATION),
    "intake_batch": (1, Tier.B_INTERPRETATION),
    "reference_candidate": (1, Tier.B_INTERPRETATION),
    "project_reference_standing": (1, Tier.C_PROJECT),
    "project_panel_source": (1, Tier.C_PROJECT),
    "project_visual_mode_assignment": (1, Tier.C_PROJECT),
    # Phase 1 - rough manga production (pull-forward slice, generated tier)
    "rough_artifact": (1, Tier.D_GENERATED),
    "generation_recipe": (1, Tier.D_GENERATED),
    "rough_attempt": (1, Tier.D_GENERATED),
    "attempt_input": (1, Tier.D_GENERATED),
    "attempt_derivative": (1, Tier.D_GENERATED),
    "attempt_review": (1, Tier.D_GENERATED),
}
