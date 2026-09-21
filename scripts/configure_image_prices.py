"""Write the paid-image price list from prices the creator confirms.

Continuum refuses to spend money on a request whose cost it does not know, and
it will not invent one either: nobody but the creator can say what the vendor
charges today. This script turns two confirmed per-image prices into the exact
``CONTINUUM_IMAGE_PRICE_LIST`` line to paste into ``.env``.

    python scripts/configure_image_prices.py --high-usd 0.134 --cheap-usd 0.039

Check the numbers against the provider's own pricing page first. They are
recorded with every reservation, so a wrong price is a wrong ledger, not a
wrong bill - the bill is whatever the vendor charges regardless.

Nothing is written unless --write is given, and nothing is ever sent anywhere.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROVIDER_ID = "google.image"
#: Recorded on each row so a later reader knows where the number came from.
SOURCE_NOTE = "confirmed by the creator against the provider's pricing page"


def rows(
    *,
    high_model: str,
    cheap_model: str,
    high_usd: float,
    cheap_usd: float,
    high_batch_usd: float | None,
    cheap_batch_usd: float | None,
    confirmed_on: str,
) -> list[dict[str, object]]:
    def micros(amount: float) -> int:
        value = round(amount * 1_000_000)
        if value <= 0:
            raise SystemExit(f"a per-image price of {amount} is not a price; nothing written")
        return value

    note = f"{SOURCE_NOTE} on {confirmed_on}" if confirmed_on else SOURCE_NOTE
    out: list[dict[str, object]] = []
    for model, usd, batch in (
        (high_model, high_usd, high_batch_usd),
        (cheap_model, cheap_usd, cheap_batch_usd),
    ):
        row: dict[str, object] = {
            "provider_id": PROVIDER_ID,
            "model_ref": model,
            "per_image_micros": micros(usd),
            "note": note,
        }
        if batch is not None:
            row["batch_per_image_micros"] = micros(batch)
        out.append(row)
    return out


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--high-usd", type=float, required=True, help="USD per image, HIGH tier")
    parser.add_argument("--cheap-usd", type=float, required=True, help="USD per image, CHEAP tier")
    parser.add_argument("--high-batch-usd", type=float, default=None)
    parser.add_argument("--cheap-batch-usd", type=float, default=None)
    parser.add_argument(
        "--high-model",
        default="",
        help="Defaults to CONTINUUM_GOOGLE_IMAGE_MODEL_HIGH from the settings.",
    )
    parser.add_argument("--cheap-model", default="")
    parser.add_argument(
        "--confirmed-on", default="", help="The date you checked the pricing page, e.g. 2026-09-21."
    )
    parser.add_argument(
        "--write",
        type=Path,
        default=None,
        help="Append the line to this file (usually .env) instead of only printing it.",
    )
    args = parser.parse_args(argv)

    from continuum_config import get_settings

    settings = get_settings()
    priced = rows(
        high_model=args.high_model or settings.google_image_model_high,
        cheap_model=args.cheap_model or settings.google_image_model_cheap,
        high_usd=args.high_usd,
        cheap_usd=args.cheap_usd,
        high_batch_usd=args.high_batch_usd,
        cheap_batch_usd=args.cheap_batch_usd,
        confirmed_on=args.confirmed_on,
    )
    line = "CONTINUUM_IMAGE_PRICE_LIST=" + json.dumps(priced, separators=(",", ":"))

    from continuum_providers.pricing import PriceList, micros_to_usd

    prices = PriceList.from_json(json.dumps(priced))
    print("Prices Continuum will use:")
    for row in prices.rows():
        batch = (
            f", batch ${micros_to_usd(row.batch_per_image_micros)}"
            if row.batch_per_image_micros is not None
            else ""
        )
        print(f"  {row.model_ref}: ${micros_to_usd(row.per_image_micros)} per image{batch}")
    cap = settings.spend_cap_usd
    dearest = max(row.per_image_micros for row in prices.rows())
    print(
        f"\nAt the dearest tier the ${cap:g} cap covers about "
        f"{int(cap * 1_000_000 // dearest)} images."
    )
    print("\n" + line)
    if args.write:
        with args.write.open("a", encoding="utf-8") as handle:
            handle.write("\n" + line + "\n")
        print(f"\nAppended to {args.write}. Restart the API and the worker to pick it up.")
    else:
        print("\nNothing was written. Re-run with --write .env to add it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
