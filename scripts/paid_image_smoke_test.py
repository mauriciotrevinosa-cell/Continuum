"""One paid image, on purpose, with the money held first.

This is the first request that can cost real money, so it is deliberately the
smallest one Continuum can make: one image, the authority tier, no references,
nothing approved at the end. It exists to prove the whole chain works before a
foundation batch depends on it.

What it does, in order:

1. resolves the provider **through the policy**, so a spend policy that does
   not admit paid work stops here with the axis that blocked it;
2. estimates the cost from the configured price list. An unpriced model stops
   here: an unknown cost is never zero;
3. reserves that estimate against the hard cap, inside a locked budget row;
4. makes exactly one request;
5. stores the bytes content-addressed, records a reference with the full
   lineage (provider, model, tier, workflow, settings, seed, prompt, the
   reservation it was paid from) and settles the reservation;
6. stops. The image is a candidate. Nothing approves it.

It is a **dry run by default**: it does everything up to the request, prints
what would be sent and what it would cost, and reserves nothing.

    uv run python scripts/paid_image_smoke_test.py
    uv run python scripts/paid_image_smoke_test.py --execute --approved-by "<your name>"

If the request fails the reservation is released, so a failed call keeps none
of the budget.
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
from typing import Any

#: Deliberately plain and project-neutral: this checks plumbing, not art.
DEFAULT_PROMPT = (
    "A black-and-white manga panel of an empty wooden interior: a table, a window, "
    "morning light. No people, no text, no panel borders."
)


def _print_config(config: Any, settings: Any) -> None:
    print("provider:      google.image (REMOTE, PAID)")
    print(f"endpoint:      {config.endpoint}")
    print(f"HIGH tier:     {config.model_for('HIGH')}")
    print(f"CHEAP tier:    {config.model_for('CHEAP')}")
    print(f"method:        {config.action}")
    print(f"api key:       {'set' if config.api_key else 'MISSING'}")
    print(f"spend policy:  {settings.spend_policy or '(from the production profile)'}")
    print(f"cap:           ${settings.spend_cap_usd:g} on scope {settings.spend_scope!r}")


def _dry_run(config: Any, model: str) -> None:
    """Say exactly what a real run would send, without sending any of it."""
    endpoint = config.endpoint.rstrip("/")
    lines = [
        "",
        "DRY RUN. Nothing was reserved and no request was made.",
        f"Would POST {endpoint}/{model}:{config.action}",
        "  headers: Content-Type, x-goog-api-key (the key is never printed)",
        "  body:    one text part, generationConfig responseModalities=[IMAGE]",
        "",
        "Run it for real with:",
        '  uv run python scripts/paid_image_smoke_test.py --execute --approved-by "<your name>"',
    ]
    print("\n".join(lines))


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--prompt", default=DEFAULT_PROMPT)
    parser.add_argument("--tier", default="HIGH", choices=("HIGH", "CHEAP"))
    parser.add_argument("--width", type=int, default=1024)
    parser.add_argument("--height", type=int, default=1024)
    parser.add_argument("--seed", type=int, default=17012026)
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually reserve the money and make the one request.",
    )
    parser.add_argument("--approved-by", default="", help="Required with --execute.")
    args = parser.parse_args(argv)

    from continuum_config import WRITABLE_ROOT_KEYS, get_settings
    from continuum_core import ContinuumError
    from continuum_db.session import session_scope
    from continuum_library import ReferenceCatalog
    from continuum_production.budget import SpendLedger, paid_call
    from continuum_providers import build_default_registry
    from continuum_providers.contracts import Capability, DataClass, GenerationRequest
    from continuum_providers.google_images import GOOGLE_PROVIDER_ID, google_image_config
    from continuum_providers.pricing import PriceList, micros_to_usd
    from continuum_storage import DerivedStore

    settings = get_settings()
    config = google_image_config(settings)
    _print_config(config, settings)
    missing = config.missing()
    if missing:
        print("\nNot configured yet. Set: " + ", ".join(missing))
        return 1

    registry = build_default_registry(settings=settings)
    # Named, not auto-resolved: automatic resolution prefers local and free,
    # which is right everywhere else and wrong here, where the point is this
    # one paid backend. Naming it skips the preference, never the policy.
    try:
        provider = registry.resolve_named(
            GOOGLE_PROVIDER_ID, Capability.IMAGE_GENERATE, DataClass.PROJECT_TEXT
        )
    except ContinuumError as refusal:
        print("\nThe policy refused the paid provider:\n  " + refusal.user_message)
        if refusal.remediation:
            print("  " + refusal.remediation)
        print("\n  Nothing was reserved and no request was made.")
        return 1

    # Pricing needs no database, so a dry run still works while the database is
    # down - which is exactly when somebody is setting this up for the first time.
    prices = PriceList.from_json(settings.image_price_list)
    model = config.model_for(args.tier)
    estimate = prices.estimate(
        "google.image", model, images=1, width=args.width, height=args.height
    )
    print(f"\nmodel:         {model} ({args.tier} tier)")
    print(f"size:          {args.width}x{args.height}, seed {args.seed}")
    if not estimate.known:
        print("\nNo price is configured for this model, so nothing can be reserved:")
        print("  " + estimate.reason)
        print("  Fix it with scripts/configure_image_prices.py, then try again.")
        return 1
    print(f"estimate:      ${estimate.usd} for 1 image")
    for row in prices.rows():
        if row.model_ref == model and row.note:
            print(f"price note:    {row.note}")

    try:
        with session_scope(settings) as probe:
            state = SpendLedger.from_settings(probe, settings).state()
        print(
            f"budget:        ${micros_to_usd(state['remaining_micros'])} left "
            f"of ${micros_to_usd(state['limit_micros'])}"
        )
    except Exception as exc:  # the database is the next thing to fix, so say so
        print(f"budget:        unreadable - the database is not reachable ({type(exc).__name__})")
        if args.execute:
            print("  Start it with: docker compose up -d db")
            return 1

    if not args.execute:
        _dry_run(config, model)
        return 0
    if not args.approved_by.strip():
        print("\n--execute spends real money. Say who approved it with --approved-by.")
        return 1

    with session_scope(settings) as session:
        ledger = SpendLedger.from_settings(session, settings)
        derived = DerivedStore({key: settings.root(key) for key in WRITABLE_ROOT_KEYS})
        catalog = ReferenceCatalog(session, derived=derived)
        request = GenerationRequest(
            data_class=DataClass.PROJECT_TEXT,
            prompt=args.prompt,
            seed=args.seed,
            options={"tier": args.tier, "width": args.width, "height": args.height},
        )
        # Reserve, call once, settle. A failure releases the hold.
        with paid_call(
            ledger,
            provider.descriptor,
            purpose="SMOKE_TEST",
            images=1,
            width=args.width,
            height=args.height,
            subject="paid-image-smoke-test",
            detail={"tier": args.tier, "approved_by": args.approved_by.strip()},
        ) as entry:
            result = provider.generate_image(request)  # type: ignore[attr-defined]
        payload = result.structured or {}
        data = base64.b64decode(str(payload.get("image_base64") or ""))
        if not data:
            print("The provider returned no image. The reservation was settled; check the ledger.")
            return 1

        from continuum_core.references import (
            AssetMedium,
            AssetOrigin,
            ReferenceClass,
            ReferenceOrigin,
            ReferenceUse,
        )
        from continuum_library import ReferenceSpec

        stored = catalog.store_bytes(
            data, root_key="generated", medium=AssetMedium.IMAGE, origin=AssetOrigin.GENERATED
        )
        reference = catalog.add_generated(
            stored.content_hash,
            ReferenceSpec(
                reference_class=ReferenceClass.UNSORTED,
                origin=ReferenceOrigin.GENERATED,
                label="paid image smoke test",
                uses=(ReferenceUse.TECHNIQUE,),
            ),
            {
                "kind": "paid_image_smoke_test",
                "provider_id": result.provider_id,
                "model_ref": result.model_ref,
                "tier": args.tier,
                "version": result.version,
                "prompt": args.prompt,
                "seed": args.seed,
                "size": [args.width, args.height],
                "endpoint": config.endpoint,
                "action": config.action,
                "license": config.license_note,
                "source": config.model_source,
                "spend_entry_id": str(entry.id) if entry else None,
                "estimated_usd": estimate.usd,
                "approved_by": args.approved_by.strip(),
                "review_state": "CANDIDATE - nothing here is approved",
            },
        )
        session.commit()
        after = ledger.state()
        print(f"\nimage stored:  sha256:{stored.content_hash}")
        print(f"reference:     {reference.id} (UNSORTED candidate - not approved)")
        print(f"spend entry:   {entry.id if entry else '-'} (settled)")
        print(
            f"budget:        ${micros_to_usd(after['remaining_micros'])} left "
            f"of ${micros_to_usd(after['limit_micros'])}"
        )
        print(
            "\nNothing was approved. Look at the image, and only then decide whether to "
            "run the foundation batch."
        )
        print(json.dumps({"reference_id": str(reference.id)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
