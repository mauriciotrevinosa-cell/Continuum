# ADR-0004 — Provider abstraction, privacy, and the local-first contract

- **Status:** Proposed — awaiting human approval (handoff §2 gate)
- **Date:** 2026-08-28
- **Implements:** Master Plan §2.5, §2.6, §2.8, §37, §40, §50, §90, §101.2, §102, §103
- **Supersedes:** §2.5's provider sketch, §37's example configuration
- **Related findings:** F-06, F-07, F-11, F-34, F-37, F-38, F-50, F-53, F-54, F-55

---

## Context

§90 makes `$0 recurring cost` the default operating profile and requires the application to remain useful with no cloud account configured. §111 forbids a cloud requirement for core library use. §40 requires a per-franchise `LOCAL_ONLY` flag and explicit control over what leaves the machine.

None of that is enforceable with the provider sketch in §2.5, which has no capability metadata, no locality, no privacy class, no cost class, and no model identity — while §91.2 simultaneously requires jobs to record provider/model/recipe versions.

§37's example configuration, meanwhile, assigns cloud vendors to planning, drafting, and extraction. Read as a default rather than as an illustration, it inverts the product's stated policy.

---

## Decision

### 1. The provider contract

Defined around Continuum's needs, not around any vendor's API shape:

```
ProviderCapability = TEXT_GENERATE | TEXT_STRUCTURED | EMBED_TEXT | EMBED_IMAGE
                   | TRANSCRIBE | IMAGE_GENERATE | IMAGE_EDIT
                   | SPEECH_SYNTHESIZE | VIDEO_GENERATE

ProviderDescriptor:
    id                 stable identifier
    capabilities       set[ProviderCapability]
    locality           LOCAL | REMOTE
    cost_class         FREE | METERED | PAID
    privacy_class      what the provider may be trusted with
    license_note       code AND model-weight terms (F-55)
    model_ref          opaque; meaningful only to the adapter
    version            adapter + model version, recorded on every job
    requirements       optional VRAM/disk/runtime hints
```

A call takes a prompt package, a response schema, a budget, and a **data class** — and each adapter maps inward. An interface shaped like one vendor's `messages`/`tools` schema would make every local adapter a translation layer, which is how "model-agnostic" quietly dies.

### 2. Every provider call declares a data class (F-37, F-54)

```
DataClass = SOURCE_EXCERPT | DERIVED_METADATA | PROJECT_TEXT | USER_NOTE | SYNTHETIC
```

**The parameter is required and has no default**, so a new call site cannot forget it. Policy rules are expressed against it:

- `SOURCE_EXCERPT` may never reach a `REMOTE` provider without explicit per-operation approval.
- Content belonging to a `LOCAL_ONLY` franchise (§40) may never leave the machine in any class.
- `SYNTHETIC` (fixtures, tests) is unrestricted.

This is what makes §40's per-franchise flag actually enforceable: without a declared class at the call site, the flag is decoration.

### 3. Policy resolution cannot silently escalate to paid (F-07)

`ProviderPolicy(capability, data_class, active ProductionProfile) → permitted provider | BLOCKED(reason)`.

Profiles per §101.2: `FREE_LOCAL` (default), `BALANCED_LOCAL`, `HYBRID_OPTIONAL`, `SHOWCASE_OPTIONAL`.

**There is no code path from a `FREE_LOCAL` profile to a `PAID` or `REMOTE` provider that does not pass through explicit user approval.** When no permitted provider can satisfy a capability, the job becomes `BLOCKED(AWAITING_APPROVAL)` (ADR-0002 §3) naming the capability and the cost class — it does not fall back, and it does not fail silently.

§50's cost tiers are reinterpreted accordingly: they are **escalation options gated by the active profile**, not a default pipeline. Under `FREE_LOCAL`, work that cannot complete at Tier 0/1 blocks for approval or produces a low-confidence record queued for review.

### 4. No model identifier may appear outside the registry (F-06)

Model identifiers exist only in `packages/providers/registry/` and in `/config`. A CI check greps application code for known vendor and model naming patterns. This turns §90's "no specific AI model hardcoded as mandatory" from an aspiration into a test.

The shipped default configuration resolves every capability to a local or null provider. §37's example is relabeled as an illustration of a *user-enabled hybrid* configuration.

### 5. Schema validation lives above the provider, not inside it

A provider that advertises structured output may still return prose. Validation and repair therefore live in a shared call wrapper so **every** provider gets the same guarantee regardless of native support. Validation failures are recorded on the job as structured errors (ADR-0002 §6), with a bounded repair attempt — never an unbounded retry loop.

Prompt templates remain versioned files (§38), and the template package version is recorded on every call and every recipe (ADR-0005).

### 6. Phase 0 ships fakes only, and zero AI SDKs (F-38)

- `EchoTextProvider` — deterministic, structured-output-capable via schema echo.
- `DeterministicEmbeddingProvider` — hash-derived vectors, stable across runs.
- `NullImageProvider` — declares the capability, refuses execution with a structured error.
- `UnsatisfiableProvider` fixture — used by the `synthetic.blocked_capability` job to prove `BLOCKED(MISSING_PROVIDER)` and its remediation payload.

Shipping **no vendor SDK at all** makes §110.12 verifiable by reading `docs/DEPENDENCIES.md` rather than by auditing code paths, and keeps the first dependency inventory small and honest. Real providers arrive in the phase that first needs one — local transcription, Phase 4.

### 7. Missing models block; recipes survive (F-34)

A recipe records `required_capability`, `required_model_ref`, and version constraints. At claim time the scheduler consults the registry; if unsatisfiable, the job becomes `BLOCKED(MISSING_MODEL)` with a remediation payload naming the model and where it was expected. **Never discard the recipe, never substitute silently.** A user-approved substitution creates a new recipe revision so lineage stays honest (ADR-0005).

### 8. Network posture: loopback by default, and no path parameters (F-50)

Phase 0 has no authentication. That is acceptable for a local-first single-user tool **only** under two rules, both enforced by the config validator at boot:

1. **Default bind is `127.0.0.1`.** Binding to any other interface requires authentication to be configured. The validator enforces the pairing, so "unauthenticated on `0.0.0.0`" is unreachable rather than merely discouraged. An unauthenticated service that reads the filesystem, exposed on a café or dormitory network, is a file-disclosure service.
2. **No endpoint accepts a filesystem path as a parameter.** All file access is by asset id or artifact id. A `GET /files?path=…` endpoint is a directory-traversal machine regardless of how carefully it validates — and it *will* be proposed, because it is convenient.

CORS is restricted to the configured web origin; no wildcard.

### 9. Secrets (F-53, §110.13)

- Secrets live in the environment or an OS credential store. **Never in the database.** Never in `/config` files that are backed up (§108 excludes them explicitly).
- A `SecretStr` type whose `__repr__` and `__str__` redact.
- A logging filter that scrubs **both** by pattern **and** by exact match against the registry of loaded secret values — pattern matching alone misses secrets that do not look like secrets.
- `.env` is gitignored; `.env.example` contains no real values.
- Test: dump the full effective configuration and trigger an exception at DEBUG level; assert no sentinel secret appears in any handler's output.

### 10. Model-weight licensing is tracked separately from code licensing (F-55)

The dependency shortlist covers code licenses carefully and model-weight licenses not at all. They are independent, and the weights are what Continuum will actually download: Whisper weights, image-model checkpoints, community LoRAs, TTS voices — several carrying OpenRAIL-style, non-commercial, or likeness restrictions that bear directly on §2.8 and §111.

`docs/DEPENDENCIES.md` gains a **Model Assets** section recording, per weight file: source, license, redistribution permitted, commercial use, and any likeness or authorization constraint. Continuum never bundles weights it cannot redistribute — it points at them, the user fetches them, and the license note is carried in the `ProviderDescriptor`.

### 11. Voice and likeness (§2.8, §102)

Performance knowledge (cadence, pauses, energy, restraint) is separated from voice synthesis implementation and is a Tier B/C data concern, not a provider concern. Exact third-party performer likeness cloning is **not** a default pipeline and remains behind an authorization gate plus provider policy. Nothing in this area is built before Phase 12.

---

## Consequences

**Positive**

- §110.12 is provable from the dependency inventory, not from code inspection.
- Silent escalation to a paid provider — the most damaging possible bug in a $0-default product — is structurally impossible under `FREE_LOCAL`.
- `LOCAL_ONLY` becomes enforceable rather than decorative.
- Provider swaps do not touch story data; only the registry and config change.
- Weight licensing is tracked before any weight is downloaded, rather than after.

**Negative / accepted costs**

- The required `DataClass` parameter adds ceremony to every call. Intentional: a defaulted parameter is a forgotten parameter.
- Validation above the provider means some duplicated effort with providers that natively enforce schemas. Worth it for one uniform guarantee.
- Phase 0 cannot demonstrate real generation. Correct — §109 forbids it anyway.

---

## Alternatives considered

| Alternative | Rejected because |
|---|---|
| Adopt one vendor's API shape as the interface | Every local adapter becomes a translation layer; the abstraction leaks immediately. |
| Automatic fallback to a cloud provider when local fails | Directly violates §90 and §103; the worst possible surprise in a $0-default product. |
| Optional `DataClass` with a permissive default | The first forgotten parameter silently ships source excerpts to a remote provider. |
| Ship one real local provider in Phase 0 | Pulls a heavy ML dependency into the foundation, muddies the dependency inventory, and is forbidden by §109's scope. |
| Provider-native structured output only | Guarantees differ per provider, so the calling code must handle both cases anyway. |
| Bind to `0.0.0.0` for convenience ("it's just local") | Unauthenticated filesystem-reading service on every network the machine joins. |

---

## Verification

Acceptance tests §110.12 and §110.13; review §S and §S.1:

- Full test suite passes with **no network access** and an empty `.env`.
- Assert `FREE_LOCAL` never resolves to a `PAID` or `REMOTE` provider (fake "expensive" provider asserted never invoked).
- Assert no AI SDK appears in the lockfiles.
- `test_no_model_literals.py` — model identifiers only inside `providers/registry` and config.
- Config validator rejects non-loopback bind without configured authentication.
- Secret redaction test over a full config dump plus an exception at DEBUG.
