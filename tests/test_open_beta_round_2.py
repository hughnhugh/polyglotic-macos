"""The open beta's round 2 (polyglotic-hq 684): the usage meter's rules, and
the prices, code, and plan-change requests against the server's contract
(683's CONTRACT-ROUND-2.md), with a fake HTTPS response. The code used here
is made up: real codes live only on the server."""

import json
import urllib.error
import urllib.request
from datetime import UTC, datetime
from decimal import Decimal
from io import BytesIO

import pytest
from tests.fakes import MemoryCredentialStore

from polyglotic_desktop.connection import open_beta, protocol, tls
from polyglotic_desktop.core.shared.open_beta import (
    Account,
    Allowance,
    ChangePreview,
    CodeOffer,
    Money,
    Offer,
    PriceList,
    ScheduledSwitch,
    Subscription,
    UsageMeter,
    UsageWarnings,
    usage_meter,
)
from polyglotic_desktop.ports.credentials import DeviceCredentials
from polyglotic_desktop.ports.open_beta import AccountError

DEVICE = DeviceCredentials("test-install", "test-device")
MIDNIGHT = datetime(2026, 11, 22, 13, tzinfo=UTC)  # Melbourne's, 23 November
NEXT_MIDNIGHT = datetime(2026, 11, 23, 13, tzinfo=UTC)
TEST_CODE = "fixture-code"


class Reply(BytesIO):
    status = 200


def account(plan: str, percent: int | None) -> Account:
    allowance = Allowance(percent, MIDNIGHT) if percent is not None else None
    return Account("account", "open_beta", True, plan, allowance)


# -- the meter ----------------------------------------------------------------------


@pytest.mark.parametrize("plan", ["plus", "premium", "alpha"])
def test_an_unlimited_plan_has_no_meter(plan: str) -> None:
    assert usage_meter(account(plan, None)) is None
    assert usage_meter(None) is None


def test_a_capped_plan_meters_what_the_server_says_is_left() -> None:
    free = usage_meter(account("beta_free", 62))
    assert free == UsageMeter("beta_free", 62, MIDNIGHT) and free.daily
    for plan in ("lite", "standard"):
        monthly = usage_meter(account(plan, 74))
        assert monthly is not None and not monthly.daily


def crossed(
    warnings: UsageWarnings, percent: int, reset: datetime = MIDNIGHT
) -> int | None:
    return warnings.crossed("account", UsageMeter("beta_free", percent, reset))


def test_each_warning_level_is_given_once_as_the_allowance_drains() -> None:
    warnings = UsageWarnings()
    seen = [crossed(warnings, percent) for percent in (62, 21, 20, 19, 12, 5, 4, 1)]
    assert seen == [None, None, 20, None, None, 5, None, None]


def test_a_drop_past_both_levels_warns_once_at_the_lower() -> None:
    warnings = UsageWarnings()
    assert crossed(warnings, 80) is None
    assert crossed(warnings, 3) == 5
    assert crossed(warnings, 2) is None


def test_running_out_while_open_is_said_once_and_not_when_first_seen_empty() -> None:
    warnings = UsageWarnings()
    assert crossed(warnings, 1) == 5
    assert crossed(warnings, 0) == 0
    assert crossed(warnings, 0) is None
    # the app opened with nothing left: Home says so; no new event
    assert crossed(UsageWarnings(), 0) is None


def test_a_refill_or_another_account_starts_the_warnings_again() -> None:
    warnings = UsageWarnings()
    assert crossed(warnings, 18) == 20
    assert crossed(warnings, 0) == 0
    assert crossed(warnings, 100, NEXT_MIDNIGHT) is None
    assert crossed(warnings, 18, NEXT_MIDNIGHT) == 20
    # the reset time unchanged (the server sends none), the allowance back
    undated = UsageWarnings()
    meter = UsageMeter("lite", 4, None)
    assert undated.crossed("account", meter) == 5
    assert undated.crossed("account", UsageMeter("lite", 100, None)) is None
    assert undated.crossed("account", meter) == 5
    assert undated.crossed("another", meter) == 5
    # an unlimited plan in between forgets them too
    assert undated.crossed("another", None) is None
    assert undated.crossed("another", meter) == 5


def test_a_longer_periods_price_is_spread_over_its_months() -> None:
    yearly = Offer("plus", "year", Money(Decimal("119.00"), "USD"))
    assert yearly.monthly == Money(Decimal("9.92"), "USD")
    pass_6 = Offer("standard", "pass_6", Money(Decimal("118.88"), "CNY"))
    assert pass_6.monthly == Money(Decimal("19.81"), "CNY")
    whole = Offer("plus", "year", Money(Decimal(15000), "JPY"))
    assert whole.monthly == Money(Decimal(1250), "JPY")
    assert Offer("plus", "month", Money(Decimal("13.99"), "USD")).monthly is None


# -- the server's contract ----------------------------------------------------------


def answering(
    monkeypatch: pytest.MonkeyPatch,
    path: str,
    reply: dict[str, object],
    sent: list[dict[str, object] | None],
    status: int = 200,
    headers: dict[str, str] | None = None,
) -> open_beta.Accounts:
    def send(request: urllib.request.Request, timeout: float, same_host: bool) -> Reply:
        assert request.full_url == "https://example.test" + path
        assert request.headers["Authorization"] == "Bearer test-device"
        assert same_host and timeout > 0
        sent.append(
            json.loads(request.data) if isinstance(request.data, bytes) else None
        )
        if status not in (200, 204):
            raise urllib.error.HTTPError(
                request.full_url,
                status,
                "refused",
                headers or {},  # type: ignore[arg-type]
                BytesIO(json.dumps(reply).encode()),
            )
        response = Reply(json.dumps(reply).encode() if status != 204 else b"")
        response.status = status
        return response

    monkeypatch.setattr(tls, "urlopen", send)
    return open_beta.Accounts("wss://example.test", MemoryCredentialStore(DEVICE))


def test_legacy_server_missing_account_endpoint_is_distinguishable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    accounts = answering(
        monkeypatch, "/v1/accounts/me", {"detail": "Not Found"}, [], status=404
    )
    with pytest.raises(AccountError) as missing:
        accounts.current(DEVICE)
    assert missing.value.status == 404


def test_the_meter_reads_percent_left_and_the_older_name_until_it_goes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    view: dict[str, object] = {
        "account_id": "beta-account",
        "cohort": "open_beta",
        "registered": True,
        "plan": "lite",
        "email": "learner@example.test",
        "percent_left": 74,
        "allowance_percent": 70,
        "resets_at": "2026-11-30T13:00:00Z",
    }
    accounts = answering(monkeypatch, "/v1/accounts/me", view, [])
    assert accounts.current(DEVICE).allowance == Allowance(
        74, datetime(2026, 11, 30, 13, tzinfo=UTC)
    )
    assert accounts.current(DEVICE).email == "learner@example.test"
    del view["percent_left"]
    assert accounts.current(DEVICE).allowance is not None
    assert accounts.current(DEVICE).allowance.percent == 70  # type: ignore[union-attr]
    view["allowance_percent"] = None  # an unlimited plan
    assert accounts.current(DEVICE).allowance is None
    update = protocol.validate(
        protocol.AllowanceUpdate,
        {"type": "allowance_update", "allowance_percent": 70, "percent_left": 74},
    )
    assert update.left == 74
    older = protocol.validate(
        protocol.AllowanceUpdate, {"type": "allowance_update", "allowance_percent": 70}
    )
    assert older.left == 70


PRICES: dict[str, object] = {
    "prices": [
        {
            "plan": "lite",
            "period": "month",
            "currency": "USD",
            "amount": "8.99",
            "renewal_amount": "8.99",
            "renewal_at": "2026-12-22T13:00:00Z",
        },
        {
            "plan": "standard",
            "period": "pass_6",
            "currency": "CNY",
            "amount": "106.88",
            "renewal_amount": None,
            "renewal_at": None,
            "pass_ends_at": "2027-08-22T13:00:00Z",
        },
        {
            "plan": "plus",
            "period": "year",
            "currency": "USD",
            "amount": "119.00",
            "renewal_amount": "119.00",
            "renewal_at": "2027-11-22T13:00:00Z",
            "mode": "prorated_immediately",
        },
    ],
    "offer": {"kind": "community_pass_prices", "percent_off": None},
}
PRICED = PriceList(
    (
        Offer(
            "lite",
            "month",
            Money(Decimal("8.99"), "USD"),
            Money(Decimal("8.99"), "USD"),
            datetime(2026, 12, 22, 13, tzinfo=UTC),
        ),
        Offer(
            "standard",
            "pass_6",
            Money(Decimal("106.88"), "CNY"),
            pass_ends_at=datetime(2027, 8, 22, 13, tzinfo=UTC),
        ),
        Offer(
            "plus",
            "year",
            Money(Decimal("119.00"), "USD"),
            Money(Decimal("119.00"), "USD"),
            datetime(2027, 11, 22, 13, tzinfo=UTC),
            change_mode="prorated_immediately",
        ),
    ),
    CodeOffer("community_pass_prices"),
)


def test_prices_are_the_servers_amounts_with_the_offer_saved_on_the_account(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: list[dict[str, object] | None] = []
    accounts = answering(monkeypatch, "/v1/checkout/prices", PRICES, sent)
    assert accounts.prices(DEVICE) == PRICED
    assert sent == [None]


def test_a_price_that_isnt_a_plain_amount_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    broken: dict[str, object] = {
        "prices": [
            {"plan": "plus", "period": "month", "currency": "USD", "amount": "$13.99"}
        ]
    }
    accounts = answering(monkeypatch, "/v1/checkout/prices", broken, [])
    with pytest.raises(AccountError, match="unavailable"):
        accounts.prices(DEVICE)


def test_a_typed_code_is_checked_by_the_server_and_claims_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: list[dict[str, object] | None] = []
    accounts = answering(monkeypatch, "/v1/codes/check", PRICES, sent)
    assert accounts.check_code(DEVICE, f"  {TEST_CODE} ") == PRICED
    assert sent == [{"code": TEST_CODE}]
    assert accounts.check_code(DEVICE, "　ｆｉｘｔｕｒｅ－ｃｏｄｅ　") == PRICED
    # malformed input never reaches the server
    for typed in ("  ", "short", "fixture code", "fixture.code", "x" * 81):
        with pytest.raises(AccountError, match="malformed_code"):
            accounts.check_code(DEVICE, typed)
    assert sent == [{"code": TEST_CODE}] * 2


@pytest.mark.parametrize("refusal", ["offer_not_available", "offer_already_redeemed"])
def test_the_servers_refusal_of_a_code_is_passed_on(
    monkeypatch: pytest.MonkeyPatch, refusal: str
) -> None:
    accounts = answering(monkeypatch, "/v1/codes/check", {"error": refusal}, [], 409)
    with pytest.raises(AccountError, match=refusal):
        accounts.check_code(DEVICE, TEST_CODE)


def test_a_code_check_without_an_offer_is_not_an_offer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plain = {"prices": PRICES["prices"], "offer": None}
    accounts = answering(monkeypatch, "/v1/codes/check", plain, [])
    with pytest.raises(AccountError, match="offer_not_available"):
        accounts.check_code(DEVICE, TEST_CODE)


def test_checkout_carries_the_code_only_when_one_was_typed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: list[dict[str, object] | None] = []
    url = "https://checkout.example.test/pay"
    accounts = answering(monkeypatch, "/v1/checkout", {"checkout_url": url}, sent)
    buyer = account("beta_free", 40)
    offer = PRICED.offers[1]
    assert (
        accounts.checkout(DEVICE, buyer, offer, "　ｆｉｘｔｕｒｅ－ｃｏｄｅ　") == url
    )
    assert accounts.checkout(DEVICE, buyer, offer) == url
    body = {"account_id": "account", "plan": "standard", "period": "pass_6"}
    assert sent == [{**body, "code": TEST_CODE}, body]


def test_offer_lookup_reads_retry_after_from_billing_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    accounts = answering(
        monkeypatch,
        "/v1/codes/check",
        {"error": "too_many_attempts"},
        [],
        429,
        {"Retry-After": "79200"},
    )
    with pytest.raises(AccountError, match="too_many_attempts") as refused:
        accounts.check_code(DEVICE, TEST_CODE)
    assert refused.value.retry_after == 79200


def test_unavailable_checkout_names_the_failed_offer_only_if_a_code_was_sent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    accounts = answering(
        monkeypatch, "/v1/checkout", {"error": "offer_not_available"}, [], 403
    )
    buyer, offer = account("beta_free", 40), PRICED.offers[1]
    with pytest.raises(AccountError, match="^plan_offer_not_available$"):
        accounts.checkout(DEVICE, buyer, offer)
    with pytest.raises(AccountError, match="^offer_not_available$"):
        accounts.checkout(DEVICE, buyer, offer, TEST_CODE)


@pytest.mark.parametrize("pending", ["offer_checkout_pending", "change_pending"])
def test_a_pending_payment_is_the_servers_to_say(
    monkeypatch: pytest.MonkeyPatch, pending: str
) -> None:
    accounts = answering(monkeypatch, "/v1/checkout", {"error": pending}, [], 409)
    with pytest.raises(AccountError, match=pending):
        accounts.checkout(DEVICE, account("beta_free", 40), PRICED.offers[1])


PREVIEW: dict[str, object] = {
    "preview_id": "preview-1",
    "plan": "plus",
    "period": "year",
    "mode": "prorated_immediately",
    "currency": "USD",
    "amount": "92.47",
    "renewal_amount": "119.00",
    "renewal_at": "2027-11-22T13:00:00Z",
    "effective_at": "2026-11-22T13:00:00Z",
}


def test_a_plan_change_is_previewed_with_todays_and_the_next_charge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: list[dict[str, object] | None] = []
    accounts = answering(monkeypatch, "/v1/checkout/change/preview", PREVIEW, sent)
    target = Offer("plus", "year", Money(Decimal("119.00"), "USD"))
    preview = accounts.preview_change(DEVICE, target)
    assert sent == [{"plan": "plus", "period": "year"}]
    assert preview == ChangePreview(
        "preview-1",
        "plus",
        "year",
        "prorated_immediately",
        Money(Decimal("92.47"), "USD"),
        Money(Decimal("119.00"), "USD"),
        datetime(2027, 11, 22, 13, tzinfo=UTC),
        datetime(2026, 11, 22, 13, tzinfo=UTC),
    )
    assert not preview.scheduled and not preview.needs_checkout


def test_confirming_sends_the_preview_and_a_pass_upgrade_is_paid_at_checkout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    subscription = open_beta._Preview.model_validate(PREVIEW).preview()
    upgrade = open_beta._Preview.model_validate(
        {
            **PREVIEW,
            "mode": "pass_upgrade",
            "plan": "premium",
            "period": "pass_12",
            "pass_ends_at": "2027-02-22T13:00:00Z",
        }
    ).preview()
    assert upgrade.needs_checkout
    assert upgrade.pass_ends_at == datetime(2027, 2, 22, 13, tzinfo=UTC)
    sent: list[dict[str, object] | None] = []
    accounts = answering(monkeypatch, "/v1/checkout/change", PREVIEW, sent)
    assert accounts.change(DEVICE, subscription) is None
    assert sent == [{"preview_id": "preview-1"}]
    # a pass upgrade without its checkout link can't be paid: refused
    with pytest.raises(AccountError, match="checkout_unavailable"):
        accounts.change(DEVICE, upgrade)
    url = "https://checkout.example.test/upgrade"
    paid = answering(
        monkeypatch, "/v1/checkout/change", {**PREVIEW, "checkout_url": url}, []
    )
    assert paid.change(DEVICE, upgrade) == url
    unsafe = answering(
        monkeypatch,
        "/v1/checkout/change",
        {**PREVIEW, "checkout_url": "http://checkout.example.test/upgrade"},
        [],
    )
    with pytest.raises(AccountError, match="checkout_unavailable"):
        unsafe.change(DEVICE, upgrade)


def test_a_stale_preview_is_the_servers_to_refuse(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    accounts = answering(
        monkeypatch,
        "/v1/checkout/change",
        {"error": "change_preview_required"},
        [],
        409,
    )
    with pytest.raises(AccountError, match="change_preview_required"):
        accounts.change(DEVICE, open_beta._Preview.model_validate(PREVIEW).preview())


@pytest.mark.parametrize("wrapped", [False, True])
def test_a_timed_out_confirm_can_still_change_the_plan(
    monkeypatch: pytest.MonkeyPatch, wrapped: bool
) -> None:
    def send(request: urllib.request.Request, timeout: float, same_host: bool) -> Reply:
        assert timeout == 35.0
        assert request.full_url.endswith("/v1/checkout/change")
        assert same_host
        if wrapped:
            raise urllib.error.URLError(TimeoutError())
        raise TimeoutError()

    monkeypatch.setattr(tls, "urlopen", send)
    accounts = open_beta.Accounts("wss://example.test", MemoryCredentialStore(DEVICE))
    with pytest.raises(AccountError, match="change_confirmation_pending"):
        accounts.change(DEVICE, open_beta._Preview.model_validate(PREVIEW).preview())


def test_a_provider_unavailable_reply_leaves_subscription_confirmation_uncertain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    accounts = answering(
        monkeypatch, "/v1/checkout/change", {"error": "checkout_unavailable"}, [], 503
    )
    subscription = open_beta._Preview.model_validate(PREVIEW).preview()
    with pytest.raises(AccountError, match="^change_confirmation_pending$"):
        accounts.change(DEVICE, subscription)


def test_account_billing_view_reads_provider_charge_and_scheduled_switch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    at = "2027-11-22T13:30:00Z"
    data = {
        "account_id": "account",
        "registered": True,
        "cohort": "open_beta",
        "plan": "plus",
        "provider": "paddle",
        "subscription": {
            "status": "active",
            "period": "year",
            "plan": "plus",
            "period_end": at,
            "renews_at": at,
            "renewal_amount": "20.99",
            "currency": "AUD",
            "scheduled": {"plan": "plus", "period": "month", "effective_at": at},
        },
    }
    calls: list[dict[str, object] | None] = []
    accounts = answering(monkeypatch, "/v1/accounts/me?billing=1", data, calls)
    current = accounts.current(DEVICE, billing=True)
    end = datetime(2027, 11, 22, 13, 30, tzinfo=UTC)
    assert current.subscribed and calls == [None]
    assert current.subscription == Subscription(
        "active",
        "year",
        end,
        end,
        Money(Decimal("20.99"), "AUD"),
        ScheduledSwitch("plus", "month", end),
        "plus",
    )


def test_switch_resume_consent_is_explicit_in_each_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object] | None] = []
    target = Offer("plus", "month", Money(Decimal("20.99"), "AUD"))
    accounts = answering(
        monkeypatch,
        "/v1/checkout/change/preview",
        {**PREVIEW, "resumes_renewal": True},
        calls,
    )
    preview = accounts.preview_change(DEVICE, target, allow_resume=True)
    assert preview.resumes_renewal
    assert calls == [{"plan": "plus", "period": "month", "allow_resume": True}]
    accounts = answering(monkeypatch, "/v1/checkout/change", PREVIEW, calls)
    assert accounts.change(DEVICE, preview) is None
    assert calls[-1] == {"preview_id": "preview-1", "resume_renewal": True}
    accounts = answering(monkeypatch, "/v1/billing/resume-renewal", {}, calls, 204)
    accounts.resume_renewal(DEVICE)
    assert calls[-1] is None
