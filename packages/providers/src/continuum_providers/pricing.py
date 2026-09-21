"""What a paid image request would cost, before it is made.

Provider pricing changes, so no price is written in code: the table is
configuration (``CONTINUUM_IMAGE_PRICE_LIST``), and this module only reads it.
Three rules make the budget enforceable rather than decorative:

* money is counted in **integer micro-dollars**. Floating point cents lose
  money in both directions, and a budget that drifts is not a budget;
* an **unpriced** request is not free, it is unknown, and an unknown cost can
  never be reserved. A provider whose price nobody configured simply cannot be
  used for paid work until somebody says what it costs;
* an estimate names exactly what it priced - provider, model, size bracket,
  batch mode - so the number in the ledger can be checked later against the
  invoice.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

__all__ = [
    "MICROS_PER_USD",
    "Estimate",
    "ImagePrice",
    "PriceList",
    "micros_to_usd",
    "usd_to_micros",
]

MICROS_PER_USD = 1_000_000


def usd_to_micros(amount: float | str) -> int:
    """Dollars to integer micro-dollars, rounded half up, never negative."""
    value = round(float(amount) * MICROS_PER_USD)
    if value < 0:
        raise ValueError("an amount of money is never negative")
    return int(value)


def micros_to_usd(micros: int) -> str:
    """A micro-dollar amount as a plain decimal string, for display and records."""
    sign = "-" if micros < 0 else ""
    whole, rest = divmod(abs(int(micros)), MICROS_PER_USD)
    return f"{sign}{whole}.{rest:06d}".rstrip("0").rstrip(".") or "0"


@dataclass(frozen=True, slots=True)
class ImagePrice:
    """What one image costs from one provider and model, in one size bracket."""

    provider_id: str
    model_ref: str
    per_image_micros: int
    #: Largest image this row prices, in pixels. 0 means any size.
    up_to_pixels: int = 0
    #: Price per image when the request is submitted in the provider's cheaper
    #: batch/asynchronous mode. ``None`` means the provider has no batch mode.
    batch_per_image_micros: int | None = None
    note: str = ""

    def covers(self, model_ref: str, pixels: int) -> bool:
        return self.model_ref == model_ref and (
            self.up_to_pixels == 0 or pixels <= self.up_to_pixels
        )


@dataclass(frozen=True, slots=True)
class Estimate:
    """What a request would cost, or why that cannot be said."""

    provider_id: str
    model_ref: str
    images: int
    pixels: int
    batch: bool
    known: bool
    micros: int = 0
    per_image_micros: int = 0
    reason: str = ""

    @property
    def usd(self) -> str:
        return micros_to_usd(self.micros)

    def as_dict(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "model_ref": self.model_ref,
            "images": self.images,
            "pixels": self.pixels,
            "batch": self.batch,
            "known": self.known,
            "micros": self.micros,
            "per_image_micros": self.per_image_micros,
            "usd": self.usd,
            "reason": self.reason,
        }


class PriceList:
    """The configured image prices. Empty by default: nothing costs money yet."""

    def __init__(self, prices: Iterable[ImagePrice] = ()) -> None:
        self._prices: tuple[ImagePrice, ...] = tuple(prices)

    def __len__(self) -> int:
        return len(self._prices)

    def rows(self) -> Sequence[ImagePrice]:
        return self._prices

    @classmethod
    def from_json(cls, text: str) -> PriceList:
        """Parse the configured table. A malformed table prices nothing, loudly."""
        if not text.strip():
            return cls()
        payload = json.loads(text)
        if not isinstance(payload, list):
            raise ValueError("the image price list must be a JSON array of price rows")
        rows = []
        for index, item in enumerate(payload):
            if not isinstance(item, dict):
                raise ValueError(f"price row {index} is not an object")
            try:
                rows.append(
                    ImagePrice(
                        provider_id=str(item["provider_id"]),
                        model_ref=str(item["model_ref"]),
                        per_image_micros=int(item["per_image_micros"]),
                        up_to_pixels=int(item.get("up_to_pixels", 0)),
                        batch_per_image_micros=(
                            int(item["batch_per_image_micros"])
                            if item.get("batch_per_image_micros") is not None
                            else None
                        ),
                        note=str(item.get("note", "")),
                    )
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(f"price row {index} is not usable: {exc}") from exc
        return cls(rows)

    def estimate(
        self,
        provider_id: str,
        model_ref: str,
        *,
        images: int,
        width: int,
        height: int,
        batch: bool = False,
    ) -> Estimate:
        """What ``images`` renders would cost, or an unknown estimate saying why."""
        pixels = max(0, int(width)) * max(0, int(height))
        count = max(0, int(images))
        candidates = sorted(
            (
                price
                for price in self._prices
                if price.provider_id == provider_id and price.covers(model_ref, pixels)
            ),
            key=lambda price: (price.up_to_pixels == 0, price.up_to_pixels),
        )
        base = Estimate(
            provider_id=provider_id,
            model_ref=model_ref,
            images=count,
            pixels=pixels,
            batch=batch,
            known=False,
        )
        if not candidates:
            return _unknown(
                base,
                f"no configured price covers {provider_id} / {model_ref} at "
                f"{width}x{height}. Add it to CONTINUUM_IMAGE_PRICE_LIST.",
            )
        price = candidates[0]
        if batch and price.batch_per_image_micros is None:
            return _unknown(base, f"{provider_id} / {model_ref} has no configured batch price")
        per_image = (
            price.batch_per_image_micros
            if batch and price.batch_per_image_micros is not None
            else price.per_image_micros
        )
        return Estimate(
            provider_id=provider_id,
            model_ref=model_ref,
            images=count,
            pixels=pixels,
            batch=batch,
            known=True,
            micros=per_image * count,
            per_image_micros=per_image,
        )


def _unknown(base: Estimate, reason: str) -> Estimate:
    return Estimate(
        provider_id=base.provider_id,
        model_ref=base.model_ref,
        images=base.images,
        pixels=base.pixels,
        batch=base.batch,
        known=False,
        reason=reason,
    )
