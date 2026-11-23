"""Open-beta controls with in-memory account, price, code and checkout
responses. The code typed here is made up: real ones live only on the server."""

from collections.abc import Callable, Iterator
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from PySide6.QtCore import QDate, QEvent, QLocale, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from tests.fake_server import wait_until

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
)
from polyglotic_desktop.ports.open_beta import AccountError, Region
from polyglotic_desktop.ui.open_beta import EmailSignIn, account_error, sign_in_region
from polyglotic_desktop.ui_next.controls import Card
from polyglotic_desktop.ui_next.upgrade import (
    Billing,
    ChangeResult,
    ChangeStatus,
    UpgradePage,
    money,
)

ACCOUNT = Account("account", "open_beta", True, "beta_free", Allowance(10))
PAYING = Account("account", "open_beta", True, "plus", None, None, "paddle")
RENEWAL = datetime(2027, 11, 22, 13, tzinfo=UTC)
NEXT_MONTH = datetime(2026, 12, 22, 13, tzinfo=UTC)
TODAY = datetime(2026, 11, 22, 13, tzinfo=UTC)
TEST_CODE = "fixture-code"


def usd(amount: str) -> Money:
    return Money(Decimal(amount), "USD")


def cny(amount: str) -> Money:
    return Money(Decimal(amount), "CNY")


PLUS = (
    Offer("plus", "month", usd("13.99"), usd("13.99"), NEXT_MONTH),
    Offer("plus", "year", usd("99.00"), usd("119.00"), RENEWAL),
)
LITE = (
    Offer("lite", "month", usd("8.99"), usd("8.99"), NEXT_MONTH),
    Offer("lite", "year", usd("79.00"), usd("79.00"), RENEWAL),
)
PASSES = tuple(
    Offer(plan, period, cny(price))
    for plan, prices in (
        ("standard", ("59.66", "106.88", "178.88")),
        ("premium", ("113.66", "205.88", "348.88")),
    )
    for period, price in zip(("pass_3", "pass_6", "pass_12"), prices, strict=True)
)


STACK_ENDS = datetime(2027, 8, 22, 13, tzinfo=UTC)
# what a subscriber is offered: each option a change, as the server marks it
CHANGES = (
    *(replace(offer, change_mode="next_period") for offer in LITE),
    *(replace(offer, change_mode="prorated_immediately") for offer in PLUS),
)


def unexpected(*_: object) -> None:
    raise AssertionError("not asked for in this test")


def billing(
    checkout: Callable[..., None] = unexpected,
    check_code: Callable[..., None] = unexpected,
    preview: Callable[..., None] = unexpected,
    change: Callable[..., None] = unexpected,
) -> Billing:
    return Billing(checkout, check_code, preview, change)


def short_date(moment: datetime) -> str:
    return QLocale().toString(
        QDate(moment.astimezone().date()), QLocale.FormatType.ShortFormat
    )


def cards(page: UpgradePage) -> list[str]:
    titles = []
    for index in range(page.choices.count()):
        item = page.choices.itemAt(index)
        card = item.widget() if item is not None else None
        assert isinstance(card, Card) and card.title is not None
        titles.append(card.title.text())
    return titles


def choose(page: UpgradePage, name: str) -> None:
    next(
        button
        for button in page._group.buttons()
        if button.accessibleName().startswith(name)
    ).setChecked(True)


@pytest.fixture(autouse=True)
def windows_deleted(qapp: QApplication) -> Iterator[None]:
    before = set(qapp.topLevelWidgets())
    yield
    for widget in qapp.topLevelWidgets():
        if widget not in before:
            widget.deleteLater()
    qapp.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def _pumping(test: bool) -> bool:
    QTest.qWait(1)
    return test


@pytest.mark.parametrize(
    ("status", "beta_confirmed", "invite_only"),
    [(404, False, True), (404, True, False), (502, False, False), (None, False, False)],
)
def test_email_sign_in_only_falls_back_for_an_unconfirmed_servers_missing_route(
    qapp: QApplication,
    caplog: pytest.LogCaptureFixture,
    status: int | None,
    beta_confirmed: bool,
    invite_only: bool,
) -> None:
    failure = AccountError("untrusted error text", status=status)

    def read() -> Region:
        raise failure

    with caplog.at_level("INFO"):
        result = sign_in_region(read, qapp, beta_confirmed=beta_confirmed)
    assert result is (None if invite_only else failure)
    assert ("using invite-code sign-in" in caplog.text) is invite_only
    assert ("keeping email sign-in" in caplog.text) is not invite_only
    assert "untrusted error text" not in caplog.text


def test_mainland_sign_in_asks_for_separate_consent_before_requesting_code(
    qapp: QApplication,
) -> None:
    started: list[tuple[bool, bool]] = []

    def start(email: str, marketing: bool, cross_border: bool, zone: str) -> str:
        assert email == "learner@example.test" and zone
        started.append((marketing, cross_border))
        return "challenge"

    def verify(challenge: str, code: str) -> Account:
        assert (challenge, code) == ("challenge", "012345")
        return ACCOUNT

    dialog = EmailSignIn(lambda: Region("CN"), start, verify, lambda _: None)
    dialog.show()
    wait_until(lambda: _pumping(dialog.consent.isVisible()))
    assert not dialog.consent.isChecked()
    assert not dialog.marketing.isVisible()
    assert dialog.invite.isVisible()
    dialog.email.setText("learner@example.test")
    assert not dialog.ok.isEnabled() and not started
    dialog.consent.setChecked(True)
    dialog.ok.click()
    wait_until(lambda: _pumping(dialog.code.isVisible()))
    assert started == [(False, True)]
    dialog.code.setText("012345")
    dialog.ok.click()
    wait_until(lambda: _pumping(dialog.account is ACCOUNT))


def test_email_sign_in_presents_invite_codes_as_the_alternative(
    qapp: QApplication,
) -> None:
    def start(_: str, _marketing: bool, _cross_border: bool, _zone: str) -> str:
        raise AssertionError("not started")

    def verify(_: str, _code: str) -> Account:
        raise AssertionError("not verified")

    dialog = EmailSignIn(lambda: Region("AU"), start, verify, lambda _: None)
    dialog.show()
    wait_until(lambda: _pumping(not dialog._work.busy))
    assert dialog.invite.text() == "Have an invite code? Sign in with it instead"


def test_desktop_and_phone_share_the_selected_checkout(
    qapp: QApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    url = "https://checkout.example.test/pay"
    requests: list[tuple[Offer, str | None]] = []
    opened: list[str] = []

    def checkout(
        offer: Offer, code: str | None, receive: Callable[[QUrl | str], None]
    ) -> None:
        requests.append((offer, code))
        receive(QUrl(url))

    def open_url(location: QUrl) -> bool:
        opened.append(location.toString())
        return True

    monkeypatch.setattr(QDesktopServices, "openUrl", open_url)
    page = UpgradePage(billing(checkout=checkout))
    page.set_account(ACCOUNT)
    page.set_prices(PriceList(PLUS))
    page.show()
    assert "US$119.00" in page.renewal.text()
    # a free account buys: nothing to review
    assert not page.review.isVisible() and not page.confirm.isVisible()
    page.pay_phone.click()
    wait_until(lambda: _pumping(page.qr.isVisible()))
    assert page.qr.pixmap() is not None and not page.qr.pixmap().isNull()
    page.pay_here.click()
    assert requests == [(PLUS[1], None)]
    assert opened == [url]
    assert "% of today" in page.current_plan.text()


def test_money_keeps_the_servers_decimals_and_an_unmistakable_sign(
    qapp: QApplication,
) -> None:
    assert money(usd("13.99")) == "US$13.99"
    assert money(usd("99.00")) == "US$99.00"
    yen = QLocale().toString(1250.0, "f", 0)
    assert money(Money(Decimal(1250), "JPY")) == f"JP¥{yen}"
    assert money(Money(Decimal("39.99"), "PLN")) == "PLN 39.99"


def test_lite_has_a_card_only_when_the_servers_prices_include_it(
    qapp: QApplication,
) -> None:
    page = UpgradePage(billing())
    page.set_account(ACCOUNT)
    page.set_prices(PriceList(PLUS))
    assert cards(page) == ["Monthly", "Yearly"]  # Lite is off: Plus alone
    page.set_prices(PriceList((*PLUS, *LITE)))
    assert cards(page) == ["Lite", "Plus"]
    assert page._choice == PLUS[1]  # yearly Plus stays the recommended one
    choose(page, "Lite Monthly")
    assert "US$8.99" in page.renewal.text()
    assert "Listening allowance" in page.benefits.text()
    assert page.auto_renewal.isVisibleTo(page)
    # a Lite price without its renewal terms can't be shown honestly
    page.set_prices(PriceList((*PLUS, Offer("lite", "month", usd("8.99")))))
    assert cards(page) == ["Monthly", "Yearly"]
    page.deleteLater()


def test_a_valid_code_shows_its_offer_and_checkout_uses_it(
    qapp: QApplication,
) -> None:
    checked: list[str] = []
    bought: list[tuple[Offer, str | None]] = []
    answers: list[PriceList | str] = [
        "That code isn’t available. Check it and try again.",
        PriceList(PASSES, CodeOffer("community_pass_prices")),
    ]

    def check_code(typed: str, receive: Callable[[PriceList | str], None]) -> None:
        checked.append(typed)
        receive(answers.pop(0))

    def checkout(
        offer: Offer, code: str | None, receive: Callable[[QUrl | str], None]
    ) -> None:
        bought.append((offer, code))
        receive("stop here")

    page = UpgradePage(billing(checkout=checkout, check_code=check_code))
    page.set_account(ACCOUNT)
    page.set_prices(PriceList(PLUS))
    page.show()
    assert page.have_code.isVisible() and not page.code.isVisible()
    assert not page.code_offer.isVisible()
    page.have_code.click()
    assert page.code.isVisible() and not page.apply_code.isEnabled()
    page.code.setText("wrong")
    page.apply_code.click()
    assert "isn’t available" in page.code_message.text()
    assert cards(page) == ["Monthly", "Yearly"] and not page.code_applied
    page.code.setText(f" {TEST_CODE} ")
    page.apply_code.click()
    assert checked == ["wrong", TEST_CODE]
    assert page.code_applied
    assert page.code_offer.isVisible()
    assert page.code_offer.text() == "Code applied: community pass prices."
    assert cards(page) == ["Standard", "Premium"]
    assert not page.code.isVisible() and page.remove_code.isVisible()
    assert page.code.text() == ""  # the code isn't left on the page
    # the account's own prices arriving again don't take the code's away
    page.set_prices(PriceList(PLUS))
    assert cards(page) == ["Standard", "Premium"]
    choose(page, "Standard 6-month pass")
    page.pay_here.click()
    assert bought == [(PASSES[1], TEST_CODE)]
    page.remove_code.click()
    assert cards(page) == ["Monthly", "Yearly"] and not page.code_applied
    assert not page.code_offer.isVisible() and page.have_code.isVisible()
    page.pay_here.click()
    assert bought[-1] == (PLUS[1], None)
    page.deleteLater()


def test_a_percent_code_and_an_offer_saved_on_the_account_are_said(
    qapp: QApplication,
) -> None:
    discounted = (
        Offer("plus", "month", usd("10.49"), usd("13.99"), NEXT_MONTH),
        Offer("plus", "year", usd("74.25"), usd("119.00"), RENEWAL),
    )
    page = UpgradePage(billing())
    page.set_account(ACCOUNT)
    # saved on the account already (Account's "Redeem a code"): no typing
    page.set_prices(PriceList(discounted, CodeOffer("percent_off_first_period", 25)))
    page.show()
    assert page.code_offer.text() == "Code applied: 25% off your first payment."
    assert not page.code_applied and not page.remove_code.isVisible()
    prices = [
        label.text()
        for label in page.findChildren(type(page.renewal))
        if "for the first" in label.text()
    ]
    assert prices == ["US$10.49 for the first month", "US$74.25 for the first year"]
    assert "US$119.00" in page.renewal.text()  # what it renews at
    page.clear()  # another account
    assert not page.code_offer.isVisible() and not page.has_prices
    page.deleteLater()


def test_a_plan_change_shows_todays_and_the_next_charge_before_confirming(
    qapp: QApplication,
) -> None:
    preview = ChangePreview(
        "preview-1",
        "plus",
        "year",
        "prorated_immediately",
        usd("92.47"),
        usd("119.00"),
        RENEWAL,
        TODAY,
    )
    asked: list[Offer] = []
    confirmed: list[ChangePreview] = []

    def preview_of(
        offer: Offer, receive: Callable[[ChangePreview | str | None], None]
    ) -> None:
        asked.append(offer)
        receive(preview)

    def change(
        reviewed: ChangePreview, receive: Callable[[QUrl | str | None], None]
    ) -> None:
        confirmed.append(reviewed)
        receive(None)

    page = UpgradePage(billing(preview=preview_of, change=change))
    page.set_account(PAYING)
    page.set_prices(PriceList(CHANGES))
    page.show()
    # nothing can be paid or confirmed before the review
    assert page.review.isVisible() and page.review.isEnabled()
    assert not page.pay_here.isVisible() and not page.pay_phone.isVisible()
    assert not page.confirm.isVisible() and not page.preview.isVisible()
    page.review.click()
    assert asked == [CHANGES[3]] and not confirmed
    assert page.preview.text().split("\n") == [
        "Today: US$92.47",
        f"Next charge: US$119.00 on {short_date(RENEWAL)}",
    ]
    assert page.confirm.isVisible() and not page.review.isVisible()
    # the review's card has the room its lines need: no empty message line
    # counted in (it squeezed the card by a line in the UI lab)
    qapp.processEvents()
    assert not page.message.isVisible()
    assert page.pay.height() >= page.pay.minimumSizeHint().height()
    # the allowance ticking over while it's read doesn't lose the review
    page.set_account(PAYING)
    assert page.confirm.isVisible()
    page.confirm.click()
    assert confirmed == [preview]
    assert page.message.text() == "Done. Your plan is updating."
    assert page.review.isVisible() and not page.confirm.isVisible()
    # choosing another offer always starts from a fresh review
    page.review.click()
    choose(page, "Lite Monthly")
    assert page.review.isVisible() and not page.preview.isVisible()
    page.deleteLater()


def test_a_confirmation_timeout_waits_for_the_account_poll(qapp: QApplication) -> None:
    preview = ChangePreview(
        "preview-1",
        "plus",
        "year",
        "prorated_immediately",
        usd("92.47"),
        usd("119.00"),
        RENEWAL,
        TODAY,
    )
    callbacks: list[Callable[[ChangeResult], None]] = []
    page = UpgradePage(
        billing(
            preview=lambda _offer, receive: receive(preview),
            change=lambda _preview, receive: callbacks.append(receive),
        )
    )
    try:
        before = replace(PAYING, renews_at=NEXT_MONTH)
        page.set_account(before)
        page.set_prices(PriceList(CHANGES))
        page.show()
        page.review.click()
        page.confirm.click()
        callbacks[0](ChangeStatus.PENDING)
        page.set_account(before)
        assert page.message.text() == "Your plan change is still being confirmed."
        assert page.paying and not page.review.isEnabled()
        page.set_account(replace(before, renews_at=RENEWAL))
        assert page.message.text() == "Done. Your plan is updating."
        assert not page.paying and page.review.isEnabled()
    finally:
        page.deleteLater()


@pytest.mark.parametrize(
    ("code", "retry_after", "expected"),
    [
        ("malformed_code", None, "That code isn't valid - check it and try again."),
        ("too_many_attempts", 79200, "Too many attempts. Try again in 22 hours."),
        (
            "too_many_attempts",
            75,
            "Too many attempts. Try again in 1 minute and 15 seconds.",
        ),
        (
            "plan_offer_not_available",
            None,
            "This plan is unavailable for your account.",
        ),
        (
            "offer_checkout_pending",
            None,
            "Finish paying in the open checkout, or try again in about 30 minutes.",
        ),
        (
            "change_pending",
            None,
            "Finish paying in the open checkout, or try again in about 30 minutes.",
        ),
    ],
)
def test_open_beta_refusals_give_the_next_step(
    qapp: QApplication, code: str, retry_after: int | None, expected: str
) -> None:
    assert expected in account_error(AccountError(code, retry_after))


def test_a_downgrade_says_from_when_and_charges_nothing_today(
    qapp: QApplication,
) -> None:
    preview = ChangePreview(
        "preview-2",
        "lite",
        "month",
        "next_period",
        usd("0.00"),
        usd("8.99"),
        NEXT_MONTH,
        NEXT_MONTH,
    )
    page = UpgradePage(
        billing(
            preview=lambda _offer, receive: receive(preview),
            change=lambda _preview, receive: receive(None),
        )
    )
    page.set_account(PAYING)
    page.set_prices(PriceList(CHANGES))
    page.show()
    choose(page, "Lite Monthly")
    page.review.click()
    date = short_date(NEXT_MONTH)
    assert page.preview.text().split("\n") == [
        "Today: US$0.00",
        f"Next charge: US$8.99 on {date}",
        f"Switches to Lite, monthly, on {date}.",
    ]
    page.confirm.click()
    assert page.message.text() == f"Done. Lite starts from {date}."
    page.deleteLater()


def test_a_pass_upgrade_is_reviewed_then_paid_and_a_further_pass_stacks(
    qapp: QApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ends = datetime(2027, 2, 22, 13, tzinfo=UTC)
    upgrade = ChangePreview(
        "preview-3", "premium", "pass_3", "pass_upgrade", cny("36.00")
    )
    answers: list[ChangePreview | str | None] = [
        upgrade,
        None,  # change_not_available: a further pass of the plan it holds
        ChangePreview(
            "preview-4",
            "premium",
            "pass_6",
            "pass_upgrade",
            cny("80.00"),
            pass_ends_at=ends,
        ),
        "The price has changed. Review the change again.",
    ]
    changed: list[ChangePreview] = []
    bought: list[tuple[Offer, str | None]] = []
    opened: list[str] = []

    def open_url(location: QUrl) -> bool:
        opened.append(location.toString())
        return True

    monkeypatch.setattr(QDesktopServices, "openUrl", open_url)

    def change(
        reviewed: ChangePreview, receive: Callable[[QUrl | str | None], None]
    ) -> None:
        changed.append(reviewed)
        receive(QUrl("https://checkout.example.test/upgrade"))

    def checkout(
        offer: Offer, code: str | None, receive: Callable[[QUrl | str], None]
    ) -> None:
        bought.append((offer, code))
        receive(QUrl("https://checkout.example.test/pass"))

    page = UpgradePage(
        billing(
            checkout=checkout,
            preview=lambda _offer, receive: receive(answers.pop(0)),
            change=change,
        )
    )
    page.set_account(Account("account", "open_beta", True, "standard", Allowance(80)))
    stack = replace(PASSES[1], pass_ends_at=STACK_ENDS)  # the server's date
    page.set_prices(PriceList((PASSES[0], stack, *PASSES[2:])))
    page.show()
    choose(page, "Premium 3-month pass")
    assert not page.pay_here.isVisible()
    page.review.click()
    assert page.preview.text().split("\n") == [
        "Today: CN¥36.00",
        "Your pass keeps its end date.",
    ]
    assert page.pay_here.isVisible() and page.pay_phone.isVisible()
    assert not page.confirm.isVisible()
    page.pay_here.click()
    assert changed == [upgrade] and not bought
    assert opened == ["https://checkout.example.test/upgrade"]
    # a further Standard pass isn't a change: it's bought, and starts later
    choose(page, "Standard 6-month pass")
    page.review.click()
    assert page.preview.text().split("\n") == [
        "Today: CN¥106.88",
        "This pass starts when your current pass ends.",
        f"Your pass then runs until {short_date(STACK_ENDS)}.",
    ]
    page.pay_here.click()
    assert bought == [(stack, None)]
    # when the server says the pass's end date, it's shown
    choose(page, "Premium 6-month pass")
    page.review.click()
    assert f"Your pass then runs until {short_date(ends)}." in page.preview.text()
    # a refusal leaves nothing to pay
    choose(page, "Premium 12-month pass")
    page.review.click()
    assert page.message.text() == "The price has changed. Review the change again."
    assert page.review.isVisible() and not page.pay_here.isVisible()
    page.deleteLater()


def test_a_change_the_server_wont_preview_is_never_confirmed(
    qapp: QApplication,
) -> None:
    page = UpgradePage(billing(preview=lambda _offer, receive: receive(None)))
    page.set_account(PAYING)
    page.set_prices(PriceList(CHANGES))
    page.show()
    page.review.click()
    assert page.message.text() == "That change isn’t available for your plan."
    assert not page.confirm.isVisible() and not page.pay_here.isVisible()
    page.deleteLater()


@pytest.mark.parametrize(
    ("status", "message"),
    [
        ("active", "Renews at A$179.00 on"),
        ("ending", "and won’t renew."),
        ("past_due", "Payment overdue."),
        ("trial", "Trial ends on"),
        ("paused", "Subscription paused."),
    ],
)
def test_current_subscription_state_and_checkout_visibility(
    qapp: QApplication, status: str, message: str
) -> None:
    total = Money(Decimal("179.00"), "AUD")
    end = RENEWAL.replace(minute=30)  # 23 November in Melbourne; 22 November UTC
    renewing = status in ("active", "trial")
    subscription = Subscription(
        status, "year", end, end if renewing else None, total if renewing else None
    )
    account = replace(PAYING, subscription=subscription)
    monthly = Offer(
        "plus",
        "month",
        Money(Decimal("20.99"), "AUD"),
        Money(Decimal("20.99"), "AUD"),
        end,
        change_mode="next_period",
    )
    resumed = []

    def resume(done: Callable[[str | None], None]) -> None:
        resumed.append(True)
        done(None)

    page = UpgradePage(replace(billing(), resume=resume))
    try:
        page.set_account(account)
        page.set_prices(PriceList((*PLUS, monthly)))
        page.show()
        assert page.current_plan.text().startswith("Plus, yearly.")
        assert message in page.current_plan.text()
        if status not in ("past_due", "paused"):
            assert short_date(end) in page.current_plan.text()
        assert page.manage.isVisible()
        assert not page.pay_here.isVisible() and not page.pay_phone.isVisible()
        assert not page.qr.isVisible()
        assert page.review.isVisible() is (status in ("active", "ending"))
        if status in ("active", "ending"):
            assert page.review.text() == "Switch to Monthly"
            assert f"A$20.99 a month from {short_date(end)}." in page.renewal.text()
        assert page.resume.isVisible() is (status == "ending")
        if status == "ending":
            assert "Renews at" not in page.current_plan.text()
            assert "also resumes auto-renew" in page.renewal.text()
            page.resume.click()
            assert resumed == [True]
    finally:
        page.deleteLater()


def test_scheduled_switch_shows_both_cadences_without_another_checkout(
    qapp: QApplication,
) -> None:
    scheduled = ScheduledSwitch("plus", "month", RENEWAL)
    subscription = Subscription(
        "active", "year", RENEWAL, RENEWAL, usd("13.99"), scheduled
    )
    page = UpgradePage(billing())
    try:
        page.set_account(replace(PAYING, subscription=subscription))
        page.set_prices(PriceList(CHANGES))
        page.show()
        assert page.current_plan.text() == (
            f"Plus, yearly. Switches to Plus, monthly, on {short_date(RENEWAL)}."
            f" Next charge: US$13.99 on {short_date(RENEWAL)}"
        )
        assert not page.pay.isVisible()
    finally:
        page.deleteLater()


def test_refresh_discards_a_checkout_answer_from_before_the_payment(
    qapp: QApplication,
) -> None:
    replies: list[Callable[[QUrl | str], None]] = []
    page = UpgradePage(
        billing(checkout=lambda _offer, _code, deliver: replies.append(deliver))
    )
    try:
        page.set_account(ACCOUNT)
        page.set_prices(PriceList(PLUS))
        page.show()
        page.pay_phone.click()
        page.refreshing_account()
        assert not page.pay_phone.isVisible()
        page.set_account(
            replace(PAYING, subscription=Subscription("ending", "year", RENEWAL))
        )
        page.set_prices(PriceList(PLUS))
        replies[0](QUrl("https://checkout.example.test/obsolete"))
        assert not page.qr.isVisible() and not page.pay_phone.isVisible()
        assert not page.pay.isVisible()
    finally:
        page.deleteLater()


def test_ending_switch_review_discloses_that_confirmation_resumes_renewal(
    qapp: QApplication,
) -> None:
    offer = replace(PLUS[0], renewal_at=RENEWAL, change_mode="next_period")
    preview = ChangePreview(
        "preview-732",
        "plus",
        "month",
        "next_period",
        usd("0.00"),
        usd("13.99"),
        RENEWAL,
        RENEWAL,
        resumes_renewal=True,
    )
    page = UpgradePage(billing(preview=lambda _offer, receive: receive(preview)))
    try:
        page.set_account(
            replace(PAYING, subscription=Subscription("ending", "year", RENEWAL))
        )
        page.set_prices(PriceList((offer,)))
        page.show()
        page.review.click()
        assert page.confirm.isVisible()
        assert "This switch also resumes auto-renew." in page.preview.text()
        assert not page.pay_here.isVisible()
    finally:
        page.deleteLater()
