"""Open-beta screens, using made-up accounts, prices, codes and checkout
links: sign-in, the allowance, Upgrade (with a code, a plan change's review
and Lite), and a capped plan's usage ring on the caption bar at each of its
compression steps (polyglotic-hq 660, 684)."""

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from functools import partial

from PySide6.QtCore import QUrl
from PySide6.QtWidgets import QWidget

from polyglotic_desktop.core.shared.open_beta import (
    Account,
    Allowance,
    ChangePreview,
    CodeOffer,
    Money,
    Offer,
    PriceList,
    Subscription,
    UsageMeter,
)
from polyglotic_desktop.ports.open_beta import Region
from polyglotic_desktop.ui.app import ConnectionState
from polyglotic_desktop.ui.open_beta import EmailSignIn
from polyglotic_desktop.ui_next.caption_window import CaptionWindow, StripLabels
from polyglotic_desktop.ui_next.upgrade import (
    Billing,
    UpgradePage,
    account_line,
    money,
)
from polyglotic_desktop.ui_next.views import placement
from tools.ui_lab.bar_timing import fit_labels, responsive_bar
from tools.ui_lab.first_run import _shown
from tools.ui_lab.home import hub
from tools.ui_lab.lab import Lab, State
from tools.ui_lab.pages import no_horizontal_scrollbar

ACCOUNT = Account("beta-demo", "open_beta", True, "beta_free", Allowance(10))
RENEWAL = datetime(2027, 11, 22, 13, tzinfo=UTC)
NEXT_MONTH = datetime(2026, 12, 22, 13, tzinfo=UTC)
CHECKOUT = "https://checkout.example.test/polyglotic/demo"
LAB_CODE = "LAB-DEMO-CODE"  # a made-up code: real ones live only on the server
MIDNIGHT = datetime(2026, 11, 22, 13, tzinfo=UTC)  # Melbourne's, 23 November
DECEMBER = datetime(2026, 11, 30, 13, tzinfo=UTC)  # Melbourne's 1 December


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


def passes(standard: tuple[str, ...], premium: tuple[str, ...]) -> tuple[Offer, ...]:
    return tuple(
        Offer(plan, period, cny(price))
        for plan, prices in (("standard", standard), ("premium", premium))
        for period, price in zip(("pass_3", "pass_6", "pass_12"), prices, strict=True)
    )


MAINLAND = passes(("66.66", "118.88", "198.88"), ("126.66", "228.88", "388.88"))
COMMUNITY = passes(("59.66", "106.88", "178.88"), ("113.66", "205.88", "348.88"))


def sign_in(lab: Lab, *, mainland: bool) -> QWidget:
    dialog = EmailSignIn(
        lambda: Region("CN" if mainland else "AU"),
        lambda *_: "challenge",
        lambda *_: ACCOUNT,
        lambda _: None,
    )
    dialog.adjustSize()
    return _shown(lab, dialog, "margin", "dark")


def allowance(lab: Lab, *, exhausted: bool) -> QWidget:
    built = hub(lab, {"whole_system": True})
    account = Account(
        ACCOUNT.id,
        ACCOUNT.cohort,
        True,
        ACCOUNT.plan,
        Allowance(0) if exhausted else Allowance(10),
    )
    if exhausted:
        built.desktop.set_connection(ConnectionState.ALLOWANCE_EXHAUSTED)
        built.home.state.set_plan(account_line(account))
    else:
        built.account.set_signed_in(True)
        built.account.show_beta_account(account)
        built.window.go_to("account")
    lab.pump()
    return built.window


def billing(
    code: PriceList | None = None, preview: ChangePreview | None = None
) -> Billing:
    """The server's answers, at once: a checkout link, `code`'s prices for
    any typed code, `preview` for any change."""
    return Billing(
        lambda _offer, _code, receive: receive(QUrl(CHECKOUT)),
        lambda _typed, receive: receive(code or "That code isn’t available."),
        lambda _offer, receive: receive(preview),
        lambda _preview, receive: receive(None),
    )


def _pick(page: UpgradePage, offer: Offer) -> None:
    """`offer`'s choice, found by its price: the words are the language's."""
    next(
        button
        for button in page._group.buttons()
        if button.accessibleName().endswith(money(offer.price))
    ).setChecked(True)


def _on_upgrade(lab: Lab, page: UpgradePage) -> QWidget:
    built = hub(lab, {})
    window = built.window
    window.add_page("upgrade", "", page, place=None)
    window.go_to("upgrade")
    lab.pump()
    no_horizontal_scrollbar(window)
    return window


def upgrade(lab: Lab, *, mainland: bool) -> QWidget:
    page = UpgradePage(billing())
    page.set_account(ACCOUNT)
    page.set_prices(PriceList(MAINLAND if mainland else PLUS))
    page.pay_phone.click()
    return _on_upgrade(lab, page)


def upgrade_subscription(lab: Lab, *, ending: bool) -> QWidget:
    end = RENEWAL.replace(minute=30)
    annual, monthly = Money(Decimal("179.00"), "AUD"), Money(Decimal("20.99"), "AUD")
    subscription = (
        Subscription("ending", "year", end)
        if ending
        else Subscription("active", "year", end, end, annual)
    )
    page = UpgradePage(replace(billing(), resume=lambda receive: receive(None)))
    page.set_account(
        Account(
            ACCOUNT.id,
            ACCOUNT.cohort,
            True,
            "plus",
            None,
            provider="paddle",
            subscription=subscription,
        )
    )
    page.set_prices(
        PriceList(
            (Offer("plus", "month", monthly, monthly, end, change_mode="next_period"),)
        )
    )
    return _on_upgrade(lab, page)


def upgrade_with_code(lab: Lab) -> QWidget:
    """ "Have a code?" answered: the community passes, in the buyer's currency."""
    page = UpgradePage(
        billing(PriceList(COMMUNITY, CodeOffer("community_pass_prices")))
    )
    page.set_account(ACCOUNT)
    page.set_prices(PriceList(PLUS))
    page.have_code.click()
    page.code.setText(LAB_CODE)
    page.apply_code.click()
    assert page.code_applied and page.code_offer.text()
    return _on_upgrade(lab, page)


def upgrade_first_payment_off(lab: Lab) -> QWidget:
    """A code that takes a percentage off the first payment."""
    discounted = (
        Offer("plus", "month", usd("10.49"), usd("13.99"), NEXT_MONTH),
        Offer("plus", "year", usd("74.25"), usd("119.00"), RENEWAL),
    )
    page = UpgradePage(
        billing(PriceList(discounted, CodeOffer("percent_off_first_period", 25)))
    )
    page.set_account(ACCOUNT)
    page.set_prices(PriceList(PLUS))
    page.have_code.click()
    page.code.setText(LAB_CODE)
    page.apply_code.click()
    return _on_upgrade(lab, page)


def upgrade_preview(lab: Lab, *, down: bool) -> QWidget:
    """A paying account reviews a change: up to yearly Plus at once (the
    unused month credited), or down to Lite from the next period."""
    preview = (
        ChangePreview(
            "lab-preview",
            "lite",
            "month",
            "next_period",
            usd("0.00"),
            usd("8.99"),
            NEXT_MONTH,
            NEXT_MONTH,
        )
        if down
        else ChangePreview(
            "lab-preview",
            "plus",
            "year",
            "prorated_immediately",
            usd("92.47"),
            usd("119.00"),
            RENEWAL,
            datetime(2026, 11, 22, 13, tzinfo=UTC),
        )
    )
    page = UpgradePage(billing(preview=preview))
    page.set_account(
        replace(
            ACCOUNT,
            plan="plus",
            allowance=None,
            provider="paddle",
            subscription=Subscription(
                "active", "month", NEXT_MONTH, NEXT_MONTH, PLUS[0].price
            ),
        )
    )
    page.set_prices(
        PriceList(
            (
                replace(LITE[0], change_mode="next_period"),
                replace(PLUS[1], change_mode="prorated_immediately"),
            )
        )
    )
    if down:
        _pick(page, LITE[0])
    page.review.click()
    assert page.confirm.isVisibleTo(page) and page.preview.text()
    return _on_upgrade(lab, page)


def upgrade_pass_stack(lab: Lab) -> QWidget:
    """A Standard pass holder buys a further pass: it starts when the
    current one ends, and runs until the date the server gives."""
    stacked = tuple(
        replace(offer, pass_ends_at=datetime(2027, 8, 22, 13, tzinfo=UTC))
        for offer in MAINLAND
    )
    page = UpgradePage(billing())  # no preview: the server says "not a change"
    page.set_account(
        Account("beta-demo", "open_beta", True, "standard", Allowance(64, DECEMBER))
    )
    page.set_prices(PriceList(stacked))
    _pick(page, stacked[1])
    page.review.click()
    lines = page.preview.text().splitlines()  # the price, the start, the end
    assert page.pay_here.isVisibleTo(page) and len(lines) == 3
    return _on_upgrade(lab, page)


def upgrade_lite(lab: Lab) -> QWidget:
    """The server's prices include Lite: its card beside Plus."""
    page = UpgradePage(billing())
    page.set_account(ACCOUNT)
    page.set_prices(PriceList((*LITE, *PLUS)))
    return _on_upgrade(lab, page)


def _ring(lab: Lab, meter: UsageMeter) -> CaptionWindow:
    shown = responsive_bar(lab)
    shown.set_usage(meter)
    return shown


def _assert_ring_fits(lab: Lab, shown: CaptionWindow) -> None:
    lab.pump()
    ring = shown.usage_ring
    assert ring.isVisible() and shown.band.rect().contains(ring.geometry())


def ring_full(lab: Lab) -> QWidget:
    """Every label, and the ring beside the mic: Free, 62 % left."""
    shown = _ring(lab, UsageMeter("beta_free", 62, MIDNIGHT))
    fit_labels(shown, StripLabels.FULL)
    _assert_ring_fits(lab, shown)
    return shown


def ring_short(lab: Lab) -> QWidget:
    """Short labels: Lite, 74 % of the month's hours left."""
    shown = _ring(lab, UsageMeter("lite", 74, DECEMBER))
    fit_labels(shown, StripLabels.SHORT)
    _assert_ring_fits(lab, shown)
    return shown


def ring_icons(lab: Lab) -> QWidget:
    """The icon step, at the window's minimum: the ring stays, low at 18 %."""
    shown = _ring(lab, UsageMeter("beta_free", 18, MIDNIGHT))
    shown.resize(shown._minimum().width, shown.height())
    _assert_ring_fits(lab, shown)
    assert shown.strip_labels is StripLabels.ICONS
    assert all(not chip.isHidden() for chip in shown._chips)
    return shown


def ring_overflow(lab: Lab) -> QWidget:
    """Narrower still, a chip gone into the gear's menu: the ring stays, 5 %."""
    shown = _ring(lab, UsageMeter("beta_free", 5, MIDNIGHT))
    width = (
        shown.tag.icon_width()
        + shown._strip_buttons_width()
        + shown.preset_chip.iconSize().width()
        + 2 * placement.CORNER_ZONE
    )
    shown.resize(width, shown.height())
    _assert_ring_fits(lab, shown)
    assert any(chip.isHidden() for chip in shown._chips)
    assert shown.mic_button.isVisible()
    return shown


def _state(name: str, run: Callable[[Lab], QWidget], scene: bool = False) -> State:
    return State(f"ui_next.{name}", run, gated=True, scene=scene)


STATES = [
    _state("beta_sign_in", partial(sign_in, mainland=False)),
    _state("beta_sign_in_mainland", partial(sign_in, mainland=True)),
    _state("beta_account", partial(allowance, exhausted=False)),
    _state("beta_exhausted", partial(allowance, exhausted=True)),
    _state("beta_upgrade", partial(upgrade, mainland=False)),
    _state("beta_upgrade_renewing", partial(upgrade_subscription, ending=False)),
    _state("beta_upgrade_ending", partial(upgrade_subscription, ending=True)),
    _state("beta_upgrade_mainland", partial(upgrade, mainland=True)),
    _state("beta_upgrade_code", upgrade_with_code),
    _state("beta_upgrade_code_percent", upgrade_first_payment_off),
    _state("beta_upgrade_preview", partial(upgrade_preview, down=False)),
    _state("beta_upgrade_preview_down", partial(upgrade_preview, down=True)),
    _state("beta_upgrade_lite", upgrade_lite),
    _state("beta_upgrade_pass_stack", upgrade_pass_stack),
    _state("w1_usage_ring", ring_full, scene=True),
    _state("w1_usage_ring_short", ring_short, scene=True),
    _state("w1_usage_ring_icons", ring_icons, scene=True),
    _state("w1_usage_ring_overflow", ring_overflow, scene=True),
]
