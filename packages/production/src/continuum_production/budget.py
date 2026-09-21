"""The hard cap on paid generation, enforced by reservations.

The rule is one sentence: **if the estimate does not fit under what is left,
the request does not happen.** Not a warning, not a log line, not a retry with
a cheaper provider chosen on Continuum's own initiative.

How it is actually enforced:

* the budget row is locked (``SELECT ... FOR UPDATE``) before anything is
  counted, so two requests racing for the last dollar cannot both win;
* outstanding money is *reservations plus settled costs*. Money that is
  promised is spent until the request finishes or is released;
* an **unpriced** request cannot be reserved. An unknown cost is not zero.

Settling with the real cost is what keeps the ledger honest: the estimate is
released and the actual amount takes its place, so a provider that charged
more than expected is visible instead of silently over-drawing later.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from continuum_core import PolicyViolationError
from continuum_db.models import SpendBudget, SpendEntry
from continuum_providers.contracts import CostClass
from continuum_providers.pricing import Estimate, PriceList, micros_to_usd, usd_to_micros
from sqlalchemy import func, select
from sqlalchemy.orm import Session

__all__ = ["BudgetExceededError", "SpendLedger", "budget_view", "paid_call"]


class BudgetExceededError(PolicyViolationError):
    """The request would spend past the cap, or its cost is unknown."""

    code = "budget.exceeded"


def budget_view(state: dict[str, Any]) -> dict[str, Any]:
    """The ledger state as the UI and the API show it."""
    return {
        **state,
        "limit_usd": micros_to_usd(state["limit_micros"]),
        "reserved_usd": micros_to_usd(state["reserved_micros"]),
        "settled_usd": micros_to_usd(state["settled_micros"]),
        "remaining_usd": micros_to_usd(state["remaining_micros"]),
    }


class SpendLedger:
    """Reservations against one scope's cap."""

    def __init__(
        self,
        session: Session,
        *,
        prices: PriceList | None = None,
        cap_usd: float = 0.0,
        scope: str = "default",
        currency: str = "USD",
    ) -> None:
        self.session = session
        self.prices = prices or PriceList()
        self.cap_micros = usd_to_micros(cap_usd)
        self.scope = scope
        self.currency = currency

    @classmethod
    def from_settings(cls, session: Session, settings: Any) -> SpendLedger:
        return cls(
            session,
            prices=PriceList.from_json(str(getattr(settings, "image_price_list", "") or "")),
            cap_usd=float(getattr(settings, "spend_cap_usd", 0.0)),
            scope=str(getattr(settings, "spend_scope", "default") or "default"),
        )

    # -- the budget row -------------------------------------------------------
    def budget(self, *, lock: bool = False) -> SpendBudget:
        """The scope's budget, created on first use and kept at the configured cap."""
        statement = select(SpendBudget).where(SpendBudget.scope_key == self.scope)
        if lock:
            statement = statement.with_for_update()
        row = self.session.execute(statement).scalar_one_or_none()
        if row is None:
            row = SpendBudget(
                scope_key=self.scope,
                currency=self.currency,
                limit_micros=self.cap_micros,
                note="created from the configured cap",
            )
            self.session.add(row)
            self.session.flush()
            if lock:
                row = self.session.execute(statement).scalar_one()
        elif row.limit_micros != self.cap_micros:
            # The creator's configured cap is authoritative, up or down.
            row.limit_micros = self.cap_micros
            self.session.flush()
        return row

    def _outstanding(self, budget_id: uuid.UUID) -> tuple[int, int]:
        """(reserved, settled) micro-dollars against this budget."""
        rows = self.session.execute(
            select(
                SpendEntry.state,
                func.coalesce(
                    func.sum(func.coalesce(SpendEntry.actual_micros, SpendEntry.estimated_micros)),
                    0,
                ),
            )
            .where(SpendEntry.budget_id == budget_id, SpendEntry.state != "RELEASED")
            .group_by(SpendEntry.state)
        ).all()
        totals = {str(state): int(amount) for state, amount in rows}
        return totals.get("RESERVED", 0), totals.get("SETTLED", 0)

    def state(self) -> dict[str, Any]:
        budget = self.budget()
        reserved, settled = self._outstanding(budget.id)
        return {
            "scope": budget.scope_key,
            "currency": budget.currency,
            "limit_micros": budget.limit_micros,
            "reserved_micros": reserved,
            "settled_micros": settled,
            "remaining_micros": max(0, budget.limit_micros - reserved - settled),
            "over_committed": reserved + settled > budget.limit_micros,
        }

    # -- reserving ------------------------------------------------------------
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
        return self.prices.estimate(
            provider_id, model_ref, images=images, width=width, height=height, batch=batch
        )

    def reserve(
        self,
        provider_id: str,
        model_ref: str,
        *,
        purpose: str,
        images: int = 1,
        width: int = 0,
        height: int = 0,
        batch: bool = False,
        subject: str = "",
        job_id: uuid.UUID | None = None,
        detail: dict[str, Any] | None = None,
    ) -> SpendEntry:
        """Hold the estimated cost, or refuse. Never returns a partial hold."""
        estimate = self.estimate(
            provider_id, model_ref, images=images, width=width, height=height, batch=batch
        )
        if not estimate.known:
            raise BudgetExceededError(
                "Continuum cannot spend money on a request whose cost it does not know.",
                technical_detail=estimate.reason,
                remediation=(
                    "Add this provider and model to CONTINUUM_IMAGE_PRICE_LIST, then try again."
                ),
                provider_id=provider_id,
                model_ref=model_ref,
            )
        budget = self.budget(lock=True)
        reserved, settled = self._outstanding(budget.id)
        remaining = budget.limit_micros - reserved - settled
        if estimate.micros > remaining:
            raise BudgetExceededError(
                f"This request would cost ${estimate.usd} and only "
                f"${micros_to_usd(max(0, remaining))} of the "
                f"${micros_to_usd(budget.limit_micros)} budget is left.",
                technical_detail=(
                    f"reserved={reserved} settled={settled} limit={budget.limit_micros} "
                    f"estimate={estimate.micros} (micro-{budget.currency})"
                ),
                remediation=(
                    "Raise CONTINUUM_SPEND_CAP_USD deliberately, settle or release older "
                    "reservations, or run this on a free provider."
                ),
                provider_id=provider_id,
                model_ref=model_ref,
                estimate_micros=estimate.micros,
                remaining_micros=max(0, remaining),
            )
        entry = SpendEntry(
            budget_id=budget.id,
            state="RESERVED",
            provider_id=provider_id,
            model_ref=model_ref,
            purpose=purpose[:40],
            images=max(1, images),
            width=width,
            height=height,
            batch=batch,
            estimated_micros=estimate.micros,
            job_id=job_id,
            subject=subject[:160],
            detail={"estimate": estimate.as_dict(), **(detail or {})},
        )
        self.session.add(entry)
        self.session.flush()
        return entry

    # -- closing a reservation ------------------------------------------------
    def settle(self, entry_id: uuid.UUID, actual_micros: int | None = None) -> SpendEntry:
        """Record what the request really cost. Defaults to the estimate."""
        entry = self._entry(entry_id)
        if entry.state != "RESERVED":
            raise BudgetExceededError(
                f"That reservation is already {entry.state.lower()}.",
                remediation="Reserve again for a new request.",
            )
        entry.actual_micros = (
            entry.estimated_micros if actual_micros is None else max(0, int(actual_micros))
        )
        entry.state = "SETTLED"
        entry.settled_at = dt.datetime.now(dt.UTC)
        self.session.flush()
        return entry

    def release(self, entry_id: uuid.UUID, reason: str = "") -> SpendEntry:
        """Give the money back: the request failed, or never ran."""
        entry = self._entry(entry_id)
        if entry.state == "SETTLED":
            raise BudgetExceededError(
                "A settled charge cannot be released; it already happened.",
                remediation="Record a correction instead.",
            )
        entry.state = "RELEASED"
        entry.detail = {**(entry.detail or {}), "released_because": reason[:300]}
        self.session.flush()
        return entry

    def _entry(self, entry_id: uuid.UUID) -> SpendEntry:
        entry = self.session.get(SpendEntry, entry_id, with_for_update=True)
        if entry is None:
            raise BudgetExceededError("That spend reservation does not exist.")
        return entry

    def entries(self, *, limit: int = 100) -> list[dict[str, Any]]:
        budget = self.budget()
        rows = self.session.execute(
            select(SpendEntry)
            .where(SpendEntry.budget_id == budget.id)
            .order_by(SpendEntry.created_at.desc())
            .limit(limit)
        ).scalars()
        return [
            {
                "id": str(row.id),
                "state": row.state,
                "provider_id": row.provider_id,
                "model_ref": row.model_ref,
                "purpose": row.purpose,
                "images": row.images,
                "subject": row.subject,
                "estimated_usd": micros_to_usd(row.estimated_micros),
                "actual_usd": (
                    micros_to_usd(row.actual_micros) if row.actual_micros is not None else None
                ),
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "settled_at": row.settled_at.isoformat() if row.settled_at else None,
            }
            for row in rows
        ]


@contextmanager
def paid_call(
    ledger: SpendLedger | None,
    descriptor: Any,
    *,
    purpose: str,
    images: int = 1,
    width: int = 0,
    height: int = 0,
    subject: str = "",
    job_id: uuid.UUID | None = None,
    detail: dict[str, Any] | None = None,
) -> Iterator[SpendEntry | None]:
    """Hold the cost around a provider call, or do nothing when it is free.

    Every path that can reach a paid provider goes through here, so the cap is
    enforced where the money is actually spent rather than only where somebody
    remembered to check. Three behaviours, in order:

    * a provider that does not cost money is called with nothing held;
    * a paid provider with **no ledger** is refused. Failing closed is the
      point: a caller that forgot the budget must not be the caller that
      discovers the budget did not apply;
    * otherwise the estimate is reserved first, settled when the call returns,
      and released when it raises. A request that never produced an image
      never keeps its money.
    """
    if getattr(descriptor, "cost_class", None) is not CostClass.PAID:
        yield None
        return
    if ledger is None:
        raise BudgetExceededError(
            f"{getattr(descriptor, 'id', 'this provider')} costs money and this request "
            "was assembled without a budget.",
            remediation=(
                "Run it through a path that holds the spend (the paid smoke test, or a "
                "foundation batch), or use a free provider."
            ),
        )
    entry = ledger.reserve(
        str(descriptor.id),
        str(getattr(descriptor, "model_ref", "") or ""),
        purpose=purpose,
        images=images,
        width=width,
        height=height,
        subject=subject,
        job_id=job_id,
        detail=detail,
    )
    try:
        yield entry
    except Exception:
        ledger.release(entry.id, "the paid request did not produce an image")
        raise
    ledger.settle(entry.id)
