"""Price a foundation batch, and - only when a person says so - hold the money.

The batch is a manifest you edit, not a number in the code. This prices every
item against the configured price list, checks the total against what is left
of the hard cap, and prints exactly what would happen.

    uv run python scripts/foundation_batch.py --manifest <path>          # plan only
    uv run python scripts/foundation_batch.py --manifest <path> \\
        --reserve --approved-by "<your name>"                            # hold the money

Reserving holds every item or none. It does **not** render anything: each
artifact is then produced through its own ordinary flow (a character sheet
request, a calibration stage), and each one settles its own reservation when
it runs. Nothing here approves any output.

Keep your real manifest outside the repository - it names your cast.
``docs/foundation-batch.example.json`` is the shape to copy.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument(
        "--reserve", action="store_true", help="Hold the estimated cost for every item."
    )
    parser.add_argument("--approved-by", default="", help="Required with --reserve.")
    args = parser.parse_args(argv)

    from continuum_config import get_settings
    from continuum_core import ContinuumError
    from continuum_db.session import session_scope
    from continuum_production.budget import SpendLedger
    from continuum_production.foundation import FoundationBatch
    from continuum_providers.pricing import micros_to_usd

    settings = get_settings()
    text = args.manifest.read_text(encoding="utf-8")

    with session_scope(settings) as session:
        ledger = SpendLedger.from_settings(session, settings)
        batch = FoundationBatch(session, ledger)
        try:
            plan = batch.plan(text)
        except ContinuumError as refusal:
            print("The manifest was refused:\n  " + refusal.user_message)
            return 1

        print(f"batch:    {plan['label'] or '(unnamed)'}  [{plan['manifest_hash'][:12]}]")
        print(f"project:  {plan['project_key']}")
        for item in plan["items"]:
            cost = f"${item['usd']}" if item.get("usd") else "unpriced"
            subject = f" {item['subject']}" if item.get("subject") else ""
            print(f"  {item['id']:<20} {item['kind']:<20} x{item['count']:<3} {cost}{subject}")
        budget = plan["budget"]
        print(f"\nimages:   {plan['images']}")
        print(f"total:    ${plan['total_usd']}")
        print(
            f"budget:   ${micros_to_usd(budget['remaining_micros'])} left "
            f"of ${micros_to_usd(budget['limit_micros'])}"
        )
        if plan["blockers"]:
            print("\nblocked:")
            for blocker in plan["blockers"]:
                print("  - " + blocker)
        if not plan["fits"]:
            print("\nNothing was reserved.")
            return 1
        if not args.reserve:
            print(
                "\nPLAN ONLY. Nothing was reserved.\n"
                "When you are ready, and after the paid smoke test has produced an image "
                "you are happy with:\n"
                f"  uv run python scripts/foundation_batch.py --manifest {args.manifest} "
                f'--reserve --approved-by "<your name>"'
            )
            return 0

        try:
            held = batch.reserve(text, approved_by=args.approved_by)
        except ContinuumError as refusal:
            print("\nRefused:\n  " + refusal.user_message)
            return 1
        session.commit()
        print(f"\nreserved: {len(held['reserved'])} items, ${held['total_usd']} held")
        print(f"approved by: {held['approved_by']}")
        print(
            "\nThe money is held; nothing has been rendered. Produce each artifact "
            "through its own flow and review every candidate yourself."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
