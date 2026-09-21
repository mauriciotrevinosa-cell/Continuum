"""The paid-generation cap is a wall, not a warning.

A budget that is only shown in the interface is decoration. These checks are
about the ledger that actually stops a request: the estimate must be known,
reservations hold money before the provider is called, two requests racing for
the last dollar cannot both win, and a failed request gives its money back.
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pytest
from continuum_config import Settings
from continuum_db.models import SpendBudget, SpendEntry
from continuum_db.session import session_scope
from continuum_production.budget import (
    BudgetExceededError,
    SpendLedger,
    budget_view,
    paid_call,
)
from continuum_providers.contracts import (
    Capability,
    CostClass,
    Locality,
    PrivacyClass,
    ProviderDescriptor,
)
from continuum_providers.pricing import PriceList, micros_to_usd, usd_to_micros
from sqlalchemy import delete
from sqlalchemy.orm import Session

pytestmark = pytest.mark.requires_db

#: A synthetic price table: one dollar an image, forty cents in batch mode.
PRICES = json.dumps(
    [
        {
            "provider_id": "test.paid",
            "model_ref": "test-model",
            "per_image_micros": 1_000_000,
            "batch_per_image_micros": 400_000,
        },
        {
            "provider_id": "test.paid",
            "model_ref": "test-model-large",
            "per_image_micros": 2_000_000,
            "up_to_pixels": 1024 * 1024,
        },
    ]
)


@pytest.fixture
def session(db_settings: Settings):
    with session_scope(db_settings) as handle:
        handle.execute(delete(SpendEntry))
        handle.execute(delete(SpendBudget))
        handle.commit()
        yield handle
        handle.execute(delete(SpendEntry))
        handle.execute(delete(SpendBudget))
        handle.commit()


def _ledger(session: Session, cap: float = 10.0) -> SpendLedger:
    return SpendLedger(
        session, prices=PriceList.from_json(PRICES), cap_usd=cap, scope="test-budget"
    )


def _reserve(ledger: SpendLedger, images: int = 1, **kwargs: Any) -> SpendEntry:
    return ledger.reserve(
        "test.paid",
        "test-model",
        purpose="CHARACTER_SHEET",
        images=images,
        width=1024,
        height=1024,
        **kwargs,
    )


def test_the_cap_is_enforced_and_there_is_no_overdraft(session: Session) -> None:
    ledger = _ledger(session)
    _reserve(ledger, images=9)
    assert ledger.state()["remaining_micros"] == usd_to_micros(1)
    with pytest.raises(BudgetExceededError) as refused:
        _reserve(ledger, images=2)
    assert "only $1" in refused.value.user_message
    assert ledger.state()["remaining_micros"] == usd_to_micros(1)
    # Exactly the remaining dollar still fits.
    _reserve(ledger, images=1)
    assert ledger.state()["remaining_micros"] == 0


def test_an_unpriced_request_is_unknown_not_free(session: Session) -> None:
    ledger = _ledger(session)
    with pytest.raises(BudgetExceededError) as refused:
        ledger.reserve("test.paid", "a-model-nobody-priced", purpose="CAL", width=512, height=512)
    assert "does not know" in refused.value.user_message
    assert "CONTINUUM_IMAGE_PRICE_LIST" in str(refused.value.remediation)
    assert ledger.state()["reserved_micros"] == 0


def test_concurrent_reservations_cannot_both_take_the_last_dollar(
    db_settings: Settings, session: Session
) -> None:
    """Two workers, one dollar left. The budget row is locked, so one loses."""
    _reserve(_ledger(session), images=9)
    session.commit()

    def attempt() -> str:
        with session_scope(db_settings) as own:
            try:
                _reserve(_ledger(own), images=1)
                own.commit()
                return "reserved"
            except BudgetExceededError:
                return "refused"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = sorted(pool.map(lambda _: attempt(), range(2)))
    assert outcomes == ["refused", "reserved"]
    session.expire_all()
    state = _ledger(session).state()
    assert state["reserved_micros"] == usd_to_micros(10)
    assert state["remaining_micros"] == 0
    assert state["over_committed"] is False


def test_a_released_reservation_gives_the_money_back(session: Session) -> None:
    ledger = _ledger(session)
    entry = _reserve(ledger, images=10)
    assert ledger.state()["remaining_micros"] == 0
    ledger.release(entry.id, "the render failed")
    assert ledger.state()["remaining_micros"] == usd_to_micros(10)
    # Released money can be spent again.
    _reserve(ledger, images=3)
    assert ledger.state()["remaining_micros"] == usd_to_micros(7)


def test_settling_records_what_it_really_cost(session: Session) -> None:
    ledger = _ledger(session)
    entry = _reserve(ledger, images=4)
    ledger.settle(entry.id, actual_micros=usd_to_micros(5.5))
    state = ledger.state()
    assert state["settled_micros"] == usd_to_micros(5.5)
    assert state["reserved_micros"] == 0
    assert state["remaining_micros"] == usd_to_micros(4.5)
    assert budget_view(state)["remaining_usd"] == "4.5"
    with pytest.raises(BudgetExceededError, match="already happened"):
        ledger.release(entry.id)


def test_the_ledger_records_provider_model_and_what_it_was_for(session: Session) -> None:
    ledger = _ledger(session)
    entry = _reserve(ledger, images=2, subject="cal-01/panel-1", batch=False)
    (row,) = ledger.entries()
    assert row["provider_id"] == "test.paid"
    assert row["model_ref"] == "test-model"
    assert row["purpose"] == "CHARACTER_SHEET"
    assert row["images"] == 2
    assert row["subject"] == "cal-01/panel-1"
    assert row["estimated_usd"] == "2"
    assert entry.detail["estimate"]["per_image_micros"] == 1_000_000


def test_batch_pricing_is_a_different_price_not_a_discount_guess(session: Session) -> None:
    ledger = _ledger(session)
    _reserve(ledger, images=5, batch=True)
    assert ledger.state()["reserved_micros"] == usd_to_micros(2)


def test_lowering_the_configured_cap_applies_immediately(session: Session) -> None:
    _reserve(_ledger(session, cap=10.0), images=3)
    tightened = _ledger(session, cap=4.0)
    assert tightened.state()["limit_micros"] == usd_to_micros(4)
    assert tightened.state()["remaining_micros"] == usd_to_micros(1)
    with pytest.raises(BudgetExceededError):
        _reserve(tightened, images=2)


def test_money_is_counted_in_whole_micro_dollars() -> None:
    assert usd_to_micros(10) == 10_000_000
    assert usd_to_micros(0.03) == 30_000
    assert micros_to_usd(30_000) == "0.03"
    assert micros_to_usd(10_000_000) == "10"


# -- the gate that sits around the call that spends the money ---------------
PAID_DESCRIPTOR = ProviderDescriptor(
    id="test.paid",
    capabilities=frozenset({Capability.IMAGE_GENERATE}),
    locality=Locality.REMOTE,
    cost_class=CostClass.PAID,
    privacy_class=PrivacyClass.THIRD_PARTY,
    model_ref="test-model",
)


def test_a_paid_call_holds_the_money_around_it_and_settles_on_success(
    session: Session,
) -> None:
    ledger = _ledger(session)
    with paid_call(ledger, PAID_DESCRIPTOR, purpose="SMOKE_TEST", width=1024, height=1024) as entry:
        assert entry is not None
        # Inside the call the money is already held, so a second request
        # racing alongside it sees a smaller budget.
        assert ledger.state()["reserved_micros"] == usd_to_micros(1)
    state = ledger.state()
    assert state["settled_micros"] == usd_to_micros(1)
    assert state["reserved_micros"] == 0
    assert state["remaining_micros"] == usd_to_micros(9)


def test_a_failed_paid_call_keeps_none_of_the_budget(session: Session) -> None:
    ledger = _ledger(session)
    with pytest.raises(RuntimeError, match="the endpoint refused"):
        with paid_call(ledger, PAID_DESCRIPTOR, purpose="SMOKE_TEST", width=1024, height=1024):
            raise RuntimeError("the endpoint refused")
    state = ledger.state()
    assert state["reserved_micros"] == 0 and state["settled_micros"] == 0
    assert state["remaining_micros"] == usd_to_micros(10)
    (released,) = ledger.entries()
    assert released["state"] == "RELEASED"


def test_a_paid_call_that_would_not_fit_never_reaches_the_provider(
    session: Session,
) -> None:
    ledger = _ledger(session, cap=0.5)
    reached = False
    with pytest.raises(BudgetExceededError, match=r"only \$0.5"):
        with paid_call(ledger, PAID_DESCRIPTOR, purpose="SMOKE_TEST", width=1024, height=1024):
            reached = True
    assert reached is False
    assert ledger.state()["reserved_micros"] == 0
