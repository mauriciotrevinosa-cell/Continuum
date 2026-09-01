# Claude — Next Session Continuation Note

**Status:** additive coordination note. This does not supersede `docs/FOUNDATION_APPROVAL.md`, the Phase 0 runbooks, or `docs/CLAUDE_SESSION_HANDOFF.md`.

## Resume order

When Claude usage is available again:

1. Check out `phase-0/claude-implementation`.
2. Read `docs/CLAUDE_SESSION_HANDOFF.md` first.
3. Confirm the working tree and current HEAD before changing anything.
4. Finish the four missing Phase 0 documents identified in the handoff:
   - `README.md`
   - `AGENTS.md`
   - `docs/DEPENDENCIES.md`
   - `docs/PHASE_0_REPORT.md`
5. Resolve or clearly report local environment prerequisites needed for the remaining acceptance tests. Do not fake PASS results for tests that were not executed.
6. Run the required acceptance/invariant gates.
7. Produce the exact Phase 0 candidate SHA and STOP for Codex audit.
8. Do not create `continuum-phase-0` before Codex + final human/ChatGPT review.

## New creative/product context added while Claude was paused

Read:

`docs/creative/THE_ARRIVALS_CREATIVE_DIRECTION_v0.1.md`

It records new/clarified ideas including:

- **Continuum** as the app/project name and **The Arrivals** as the working title for the primary series.
- The Opening Cohort has **no fixed size**. “10 characters + Avatar” was only an example.
- Franchise cast closure should eventually be visual and source-grounded, with `UNREVIEWED_RESERVE` for identifiable characters that were missed rather than silently treating them as excluded.
- The Avatar may have emergent romantic comedy / an accidental “harem gag,” but major relationships never auto-canon.
- Characters without supernatural powers can still progress enormously through multidimensional mastery: art, music, medicine, science, leadership, craft, logistics, culture, etc.
- Not every normal character needs to become overpowered or learn magic.
- A normal character may learn a supernatural system later only if that system's rules, compatibility, training, costs and story support it.
- The desired visual direction is **multistyle**: characters may retain meaningful parts of their source visual grammar while shared lighting, perspective, environment and physical interaction unify the scene.

## Scope lock

These creative notes are **future requirements/context only** while Phase 0 is open.

Do **not** implement Character Vault, Source Intelligence, story generation, relationship logic, powers, image generation, animation, cast review, or any Phase 1+ feature as part of the Phase 0 continuation.

Finish the current phase cleanly first. Future implementation must follow the approved phase order.
