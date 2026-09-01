# Claude Credit / Session Handoff Protocol

**Applies to:** Claude Code while implementing Continuum Phase 0
**Purpose:** preserve work cleanly if Claude is approaching its usage/credit/session limit.

## Rule

Claude must not silently run until the session/credit limit cuts it off in the middle of work.

If Claude can detect or reasonably infer that remaining usage is becoming low, it must stop starting new large tasks and create a clean handoff **before** the limit is reached.

## Required actions before stopping

1. Finish the smallest safe unit currently in progress when practical. Do not rush a risky partial change merely to finish it.
2. Run the narrowest relevant tests for the work just completed.
3. Commit completed, coherent work. Avoid leaving important finished work only in the working tree.
4. If unfinished edits must remain, list every modified/untracked file and explain whether each is safe to keep, revert, or continue.
5. Create or update `docs/CLAUDE_SESSION_HANDOFF.md` with:
   - current branch and HEAD commit SHA;
   - Phase 0 subsection/task being worked on;
   - what is fully complete;
   - what is partially complete;
   - exact next implementation step;
   - tests already run and their results;
   - tests still required;
   - known failures/blockers and whether they are code defects or environment prerequisites;
   - exact commands the next agent should run first;
   - files/directories most relevant to the unfinished task;
   - any design question that genuinely needs human/ChatGPT review;
   - explicit confirmation that no Phase 1 work was started.
6. In the final Claude message, clearly say that usage/credits are low and point the user to `docs/CLAUDE_SESSION_HANDOFF.md`.

## Handoff quality standard

The handoff must be good enough that another capable coding agent can continue without reconstructing Claude's private reasoning or repeating broad exploration.

Prefer concrete state over narrative. Example:

```text
Current task: worker lease expiry / reaper
HEAD: <sha>
Complete: job claim, heartbeat, lease columns, unit tests
Incomplete: expired RUNNING -> QUEUED transition integration test
Next command: uv run pytest tests/acceptance/test_110_11_failure_state.py -q
Known issue: test fixture database clock is mocked incorrectly; production code not yet implicated
Relevant files: packages/jobs/lease.py, packages/jobs/queue.py, tests/acceptance/test_110_11_failure_state.py
```

## Do not do these things when credits are low

- Do not begin a new large subsystem.
- Do not make broad refactors just to "clean up" before stopping.
- Do not weaken or delete failing tests.
- Do not start Phase 1.
- Do not create the `continuum-phase-0` tag.
- Do not claim Phase 0 is complete if required tests/reporting are unfinished.

## Continuation

After a credit-limit handoff, the user/ChatGPT may choose either:

- resume Claude later from `docs/CLAUDE_SESSION_HANDOFF.md`; or
- authorize Codex to continue the unfinished **Phase 0 implementation** before performing its independent audit.

Codex must not assume the implementation is audit-ready merely because Claude stopped; `docs/PHASE_0_REPORT.md` and the Phase 0 candidate gate still control when the independent audit begins.
