"""The desktop upgrade page. Prices, code offers, plan-change previews and
checkout links all come from the server (polyglotic-hq 660, 684;
PLAN-OPEN-BETA v11, v16, v18): the page shows them and never works a price,
a discount or an end date out itself.

- **The cards:** what this account may buy, in its own currency. Lite has a
  card only when the server's prices include it.
- **"Have a code?"** (v16): a typed code is checked by the server; a valid
  one shows its offer (a first-payment discount, or the community passes)
  and the prices under it, and checkout carries the code. No code is ever
  written in the app.
- **A plan change** (v18): where the server's price says an option changes
  the account's subscription, or the account holds a pass and picks another,
  "Review change" asks the server what it costs - today's charge, the next
  charge and its date, "from {date}" for a change that waits for the next
  period - before "Confirm change" or the payment buttons do anything. A
  pass the server won't upgrade to is a further pass: bought, starting when
  the current one ends, with the end date the server gives.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from io import BytesIO

from PySide6.QtCore import QDate, QLocale, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QGridLayout,
    QLineEdit,
    QPushButton,
    QRadioButton,
)

from polyglotic_desktop.core.shared.open_beta import (
    CHANGE_CONFIRMATION_HOLD,
    Account,
    ChangePreview,
    CodeOffer,
    Money,
    Offer,
    PriceList,
)
from polyglotic_desktop.core.shared.papers import AUTO_RENEWAL_TERMS, TERMS
from polyglotic_desktop.core.shared.tunables import tunable
from polyglotic_desktop.ui_next.controls import Card, label, page_button, right_row
from polyglotic_desktop.ui_next.home import Page
from polyglotic_desktop.ui_next.os_words import pc_or_mac

QR_MODULE_SCALE = 4  # px per module; keeps the raster sharp when scanned
QR_WIDTH_PX = 320  # maximum raster width within the checkout card
OFFER_GAP = 10  # logical px between plan cards
OFFER_COLUMNS = tunable(
    "upgrade.offer_columns",
    3,
    "cards in a row",
    (1, 4),
    source="684: plan cards beside each other before they wrap; three read"
    " at the main window's least width",
)


SUBSCRIPTIONS = ("lite", "plus")
"""Plans that renew (month, year), in the order their cards show."""
PASSES = ("standard", "premium")
"""Plans bought as passes that end by themselves."""
_PERIODS = {
    "month": 0,
    "year": 1,
    "pass_1": 2,
    "pass_3": 3,
    "pass_6": 4,
    "pass_12": 5,
}
CURRENCY_SIGNS = {
    "AUD": "A$",
    "BRL": "R$",
    "CAD": "CA$",
    "CNY": "CN¥",
    "EUR": "€",
    "GBP": "£",
    "HKD": "HK$",
    "INR": "₹",
    "JPY": "JP¥",
    "KRW": "₩",
    "MXN": "MX$",
    "NZD": "NZ$",
    "SGD": "S$",
    "TWD": "NT$",
    "USD": "US$",
}
"""Signs that can't be read as another currency's (CLDR's English ones); a
currency not here is written with its code, "PLN 39.99"."""


def _tr(text: str) -> str:
    return QApplication.translate("Upgrade", text)


def money(value: Money) -> str:
    """An amount as this PC's region writes numbers, with the decimals the
    server sent and a sign no other currency shares."""
    exponent = value.amount.as_tuple().exponent
    places = -exponent if isinstance(exponent, int) and exponent < 0 else 0
    number = QLocale().toString(float(value.amount), "f", places)
    sign = CURRENCY_SIGNS.get(value.currency)
    return f"{sign}{number}" if sign else f"{value.currency} {number}"


def plan_name(plan: str) -> str:
    return {
        "alpha": lambda: _tr("Alpha"),
        "beta_free": lambda: _tr("Free beta"),
        "lite": lambda: _tr("Lite"),
        "plus": lambda: _tr("Plus"),
        "standard": lambda: _tr("Standard"),
        "premium": lambda: _tr("Premium"),
    }.get(plan, lambda: _tr("Plan unavailable"))()


def account_line(account: Account) -> str:
    name = plan_name(account.plan)
    if account.allowance is None:
        return name
    if account.plan == "beta_free":
        return _tr("{plan} · {percent}% of today’s allowance left").format(
            plan=name,
            percent=account.allowance.percent,
        )
    return _tr("{plan} · {percent}% of allowance left").format(
        plan=name,
        percent=account.allowance.percent,
    )


def _date(moment: datetime) -> str:
    local = moment.astimezone().date()
    return QLocale().toString(QDate(local), QLocale.FormatType.ShortFormat)


def _period(period: str) -> str:
    return {
        "month": lambda: _tr("Monthly"),
        "year": lambda: _tr("Yearly"),
        "pass_1": lambda: _tr("1-month pass"),
        "pass_3": lambda: _tr("3-month pass"),
        "pass_6": lambda: _tr("6-month pass"),
        "pass_12": lambda: _tr("12-month pass"),
    }[period]()


def billing_line(account: Account) -> str:
    """The account's current cadence and next event, separate from offers."""
    subscription = account.subscription
    if subscription is None:
        return account_line(account)
    cadence = _cadence(subscription.period)
    name = plan_name(account.billing_plan)
    title = (
        _tr("{plan}, {cadence}.").format(plan=name, cadence=cadence)
        if cadence
        else name
    )
    status = subscription.status
    end = subscription.period_end
    price, at = subscription.next_price, subscription.renews_at
    scheduled = subscription.scheduled
    if status == "ending":
        event = (
            _tr("Ends on {date} and won’t renew.").format(date=_date(end))
            if end
            else _tr("Auto-renew is off.")
        )
    elif status == "past_due":
        event = _tr("Payment overdue. Update your payment details.")
    elif status == "pausing":
        event = _tr("Auto-renew is off.")
    elif status == "paused":
        event = _tr("Subscription paused.")
    elif status == "ended":
        return account_line(account)
    elif status == "trial":
        event = (
            _tr("Trial ends on {date}.").format(date=_date(end))
            if end
            else _tr("Trial")
        )
        if price and at:
            event += " " + _next_charge(price, at)
    elif scheduled is not None and scheduled.period in ("month", "year"):
        event = _scheduled_switch_line(
            scheduled.plan, scheduled.period, scheduled.effective_at
        )
        if price and at:
            event += " " + _next_charge(price, at)
    elif status == "active" and at:
        event = (
            _tr("Renews at {price} on {date}.").format(
                price=money(price), date=_date(at)
            )
            if price
            else _tr("Renews on {date}.").format(date=_date(at))
        )
    else:
        return title
    return f"{title} {event}"


def _cadence(period: str | None) -> str:
    return {"month": _tr("monthly"), "year": _tr("yearly")}.get(period or "", "")


def _scheduled_switch_line(plan: str, period: str, at: datetime) -> str:
    return _tr("Switches to {plan}, {cadence}, on {date}.").format(
        plan=plan_name(plan), cadence=_cadence(period), date=_date(at)
    )


def _next_charge(price: Money, at: datetime) -> str:
    return _tr("Next charge: {amount} on {date}").format(
        amount=money(price), date=_date(at)
    )


def _switch_disclosure(offer: Offer, ending: bool) -> str:
    if offer.change_mode == "next_period" and offer.renewal_at is not None:
        cadence = (
            _tr("{price} a month") if offer.period == "month" else _tr("{price} a year")
        )
        text = _tr("{rate} from {date}.").format(
            rate=cadence.format(price=money(offer.price)), date=_date(offer.renewal_at)
        )
    else:
        text = _tr("Review the price and start date.")
    if ending:
        text += " " + _tr("This switch also resumes auto-renew.")
    return text


def _disclosure(offer: Offer) -> str:
    if offer.plan in PASSES:
        return _tr("One payment. The pass ends automatically.")
    if offer.renewal_price and offer.renewal_at:
        return _tr("Renews at {price} on {date}. Cancel any time.").format(
            price=money(offer.renewal_price),
            date=_date(offer.renewal_at),
        )
    return ""


def _sellable(offer: Offer) -> bool:
    """An option the page can show honestly: a subscription only with its
    renewal terms, a pass only for a period it can name."""
    if offer.plan in SUBSCRIPTIONS:
        return offer.period in ("month", "year") and bool(_disclosure(offer))
    return (
        offer.plan in PASSES
        and offer.period.startswith("pass_")
        and offer.period in _PERIODS
    )


def _price_line(offer: Offer) -> str:
    price = money(offer.price)
    if offer.plan in SUBSCRIPTIONS and offer.first_period_differs:
        if offer.period == "year":
            return _tr("{price} for the first year").format(price=price)
        return _tr("{price} for the first month").format(price=price)
    return price


def code_offer_line(offer: CodeOffer) -> str:
    """What a code gives, as the server states it."""
    if offer.kind == "percent_off_first_period" and offer.percent_off:
        return _tr("Code applied: {percent}% off your first payment.").format(
            percent=offer.percent_off
        )
    if offer.kind == "community_pass_prices":
        return _tr("Code applied: community pass prices.")
    return _tr("Code applied.")


def preview_lines(preview: ChangePreview) -> str:
    """A plan change before it's confirmed: today's charge, the next charge
    and its date, and when it starts or ends (v18)."""
    lines = [_tr("Today: {amount}").format(amount=money(preview.due_now))]
    if preview.renewal_price is not None and preview.renewal_at is not None:
        lines.append(_next_charge(preview.renewal_price, preview.renewal_at))
    if preview.scheduled and preview.effective_at is not None:
        lines.append(
            _scheduled_switch_line(preview.plan, preview.period, preview.effective_at)
        )
    if preview.resumes_renewal:
        lines.append(_tr("This switch also resumes auto-renew."))
    if preview.pass_ends_at is not None:
        lines.append(_runs_until(preview.pass_ends_at))
    elif preview.needs_checkout:
        lines.append(_tr("Your pass keeps its end date."))
    return "\n".join(lines)


def _runs_until(end: datetime) -> str:
    return _tr("Your pass then runs until {date}.").format(date=_date(end))


def further_pass_lines(offer: Offer) -> str:
    """A pass bought while another runs: it starts when that one ends, and
    runs until the date the server gives (v18: passes stack)."""
    lines = [
        _tr("Today: {amount}").format(amount=money(offer.price)),
        _tr("This pass starts when your current pass ends."),
    ]
    if offer.pass_ends_at is not None:
        lines.append(_runs_until(offer.pass_ends_at))
    return "\n".join(lines)


def _qr(url: str) -> QPixmap:
    import segno

    output = BytesIO()
    code = segno.make(url, micro=False)
    width, _ = code.symbol_size()
    scale = max(1, min(QR_MODULE_SCALE, QR_WIDTH_PX // width))
    code.save(output, kind="png", scale=scale)
    pixmap = QPixmap()
    pixmap.loadFromData(output.getvalue())
    return pixmap


class ChangeStatus(Enum):
    PENDING = "pending"


type ChangeResult = QUrl | str | ChangeStatus | None


@dataclass(frozen=True, slots=True)
class Billing:
    """What the page asks `main` for. Each answers later, on the Qt thread,
    with its result - or with words to show when it couldn't."""

    checkout: Callable[[Offer, str | None, Callable[[QUrl | str], None]], None]
    """A checkout link for an offer, with the typed code it's bought under."""
    check_code: Callable[[str, Callable[[PriceList | str], None]], None]
    """A typed code's offer and the prices under it."""
    preview: Callable[[Offer, Callable[[ChangePreview | str | None], None]], None]
    """What changing to an offer costs; None when the server doesn't treat
    it as a change (a further pass: it's bought, and starts after this one)."""
    change: Callable[[ChangePreview, Callable[[ChangeResult], None]], None]
    """Confirm a previewed change: a checkout link to pay a pass upgrade
    on, pending when confirmation is uncertain, or None on subscription success."""
    resume: Callable[[Callable[[str | None], None]], None] | None = None


class UpgradePage(Page):
    """Select a server-priced offer and use its checkout on a PC or phone."""

    back_wanted = Signal()
    restore_wanted = Signal()
    manage_wanted = Signal()

    def __init__(self, billing: Billing) -> None:
        super().__init__(_tr("Upgrade"))
        self._billing = billing
        self._paying = False
        self._account: Account | None = None
        self._account_ready = False
        self._account_revision = 0
        self._choice: Offer | None = None
        self._url: QUrl | None = None
        self._offers: tuple[Offer, ...] = ()
        self._prices = PriceList(())
        """The account's own prices (and the offer saved on it), kept
        under a typed code's."""
        self._code: str | None = None
        """A typed code the server accepted: sent with checkout, never kept."""
        self._code_offer: CodeOffer | None = None
        self._asking_code = False
        self._preview: ChangePreview | None = None
        self._pending_change: tuple[ChangePreview, Account | None] | None = None
        self._change_hold = QTimer(self)
        self._change_hold.setSingleShot(True)
        self._change_hold.timeout.connect(self._buttons)
        self._further_pass = False
        """The chosen pass is a further one: bought, not a change."""
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)

        current = Card(_tr("Your plan"))
        self.current_plan = label("", wrap=True)
        current.add(self.current_plan)
        self.manage = QPushButton(_tr("Manage subscription"))
        self.manage.clicked.connect(self.manage_wanted)
        self.resume = QPushButton(_tr("Resume auto-renew"))
        self.resume.setProperty("kind", "primary")
        self.resume.clicked.connect(self._resume)
        current.add(right_row(self.manage, self.resume))
        self.content.addWidget(current)

        self.code_offer = label("", wrap=True)
        self.code_offer.setTextFormat(Qt.TextFormat.PlainText)
        self.code_offer.hide()
        self.content.addWidget(self.code_offer)
        self.choices = QGridLayout()
        self.choices.setSpacing(OFFER_GAP)
        self.content.addLayout(self.choices)
        self.renewal = label("", "Dim", wrap=True)
        self.content.addWidget(self.renewal)
        self.benefits = label("", wrap=True)
        self.content.addWidget(self.benefits)
        self.terms = page_button(_tr("Terms"), TERMS, "upgrade.terms")
        self.auto_renewal = page_button(
            _tr("Auto-renewal terms"), AUTO_RENEWAL_TERMS, "upgrade.auto_renewal"
        )
        self.content.addLayout(right_row(self.terms, self.auto_renewal))

        self.have_code = QPushButton(_tr("Have a code?"))
        self.have_code.setObjectName("upgrade.have_code")
        self.have_code.setProperty("kind", "ghost")
        self.have_code.clicked.connect(self._ask_code)
        self.code = QLineEdit()
        self.code.setObjectName("upgrade.code")
        self.code.setPlaceholderText(_tr("Code"))
        self.code.setAccessibleName(_tr("Code"))
        self.code.returnPressed.connect(self._check_code)
        self.code.textChanged.connect(lambda _: self._buttons())
        self.code.hide()
        self.apply_code = QPushButton(_tr("Apply"))
        self.apply_code.clicked.connect(self._check_code)
        self.apply_code.hide()
        self.remove_code = QPushButton(_tr("Remove code"))
        self.remove_code.setProperty("kind", "ghost")
        self.remove_code.clicked.connect(self._remove_code)
        self.remove_code.hide()
        self.content.addLayout(
            right_row(self.have_code, self.code, self.apply_code, self.remove_code)
        )
        self.code_message = label("", "Dim", wrap=True)
        self.code_message.hide()
        self.content.addWidget(self.code_message)

        pay = self.pay = Card(_tr("Checkout"))
        self.preview = label("", wrap=True)
        self.preview.setObjectName("upgrade.preview")
        self.preview.setTextFormat(Qt.TextFormat.PlainText)
        self.preview.hide()
        pay.add(self.preview)
        self.review = QPushButton(_tr("Review change"))
        self.review.setProperty("kind", "primary")
        self.review.clicked.connect(self._review)
        self.confirm = QPushButton(_tr("Confirm change"))
        self.confirm.setProperty("kind", "primary")
        self.confirm.clicked.connect(self._confirm)
        self.pay_here = QPushButton(
            pc_or_mac(_tr("Pay on this PC"), _tr("Pay on this Mac"))
        )
        self.pay_here.setProperty("kind", "primary")
        self.pay_here.clicked.connect(lambda: self._pay(on_pc=True))
        self.pay_phone = QPushButton(_tr("Show payment QR code"))
        self.pay_phone.clicked.connect(lambda: self._pay(on_pc=False))
        pay.add(right_row(self.pay_phone, self.pay_here, self.review, self.confirm))
        self.qr = label("")
        self.qr.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.qr.setAccessibleName(_tr("Checkout QR code"))
        self.qr.hide()
        pay.add(self.qr)
        self.message = label("", wrap=True)
        self.message.hide()  # shown with words only: empty, it'd keep a line
        pay.add(self.message)
        self.content.addWidget(pay)

        back = QPushButton(_tr("Back to Account"))
        back.clicked.connect(self.back_wanted)
        restore = QPushButton(_tr("Restore purchase"))
        restore.clicked.connect(self.restore_wanted)
        self.content.addLayout(right_row(back, restore))
        self.content.addStretch(1)
        self.set_account(None)
        self._choose(None)

    @property
    def paying(self) -> bool:
        return self._paying or self._change_hold.isActive()

    @property
    def confirming_change(self) -> bool:
        return self._pending_change is not None

    @property
    def has_prices(self) -> bool:
        return bool(self._offers)

    @property
    def code_applied(self) -> bool:
        """A typed code is in use: `main` keeps its prices over a reload."""
        return self._code is not None

    def show_status(self, text: str) -> None:
        self._say(text)

    def refreshing_account(self) -> None:
        self._account_ready = False
        self._account_revision += 1
        self._url = None
        self.qr.clear()
        self.qr.hide()
        self._forget_review()
        self.current_plan.setText(_tr("Checking your plan…"))
        if self._code is None:
            self.set_prices(PriceList(()))
        self._say("")
        self._show_code_offer()

    def account_unavailable(self, reason: str) -> None:
        self.refreshing_account()
        self.current_plan.setText(_tr("Plan unavailable"))
        self._say(reason)

    def set_account(self, account: Account | None) -> None:
        was = self._account
        self._account = account
        self._account_ready = account is not None
        self.current_plan.setText(
            billing_line(account) if account else _tr("Sign in to see your plan.")
        )
        if self._pending_change is not None:
            preview, before = self._pending_change
            if self._change_seen(preview, before):
                self._finish_pending_change()
                self._say(_tr("Done. Your plan is updating."))
            elif account is None or (
                before is not None
                and (account.id != before.id or account.plan != before.plan)
            ):
                self._finish_pending_change()
                self._say("")
        previous_billing = was.billing_state if was else None
        current_billing = account.billing_state if account else None
        if previous_billing != current_billing:
            self._account_revision += 1
            self._url = None
            self.qr.clear()
            self.qr.hide()
            self._forget_review()
            if was and (
                account is None
                or (was.id, was.plan, was.provider)
                != (account.id, account.plan, account.provider)
            ):
                self.clear()
            elif self._code is None:
                self._show(self._prices.offers)
            self._offer_description()
        self._show_code_offer()

    def clear(self) -> None:
        """Another account or plan: no prices, no code, nothing reviewed."""
        self._code = self._code_offer = None
        self._asking_code = False
        self._prices = PriceList(())
        self.code.clear()
        self.code_message.hide()
        self._show(())
        self._show_code_offer()

    def set_prices(self, prices: PriceList) -> None:
        """The account's own prices, with the code offer saved on it (if
        any). A typed code's prices stay up until it's removed."""
        self._prices = prices
        if self._code is None:
            self._show(prices.offers)
            self._show_code_offer()

    def _show(self, offers: tuple[Offer, ...]) -> None:
        valid = tuple(
            sorted(
                (
                    offer
                    for offer in offers
                    if _sellable(offer) and self._can_offer(offer)
                ),
                key=lambda offer: _PERIODS[offer.period],
            )
        )
        if self._offers == valid:
            return
        selected = self._choice
        self._offers = valid
        self._choose(None)
        while item := self.choices.takeAt(0):
            if card := item.widget():
                card.hide()
                card.deleteLater()
        for button in self._group.buttons():
            self._group.removeButton(button)
        plans = [
            plan
            for plan in (*SUBSCRIPTIONS, *PASSES)
            if any(offer.plan == plan for offer in valid)
        ]
        buttons: dict[Offer, QRadioButton] = {}
        cards: list[Card] = []
        if plans == ["plus"]:  # one plan: a card for each way to pay for it
            for offer in valid:
                card = Card(_period(offer.period))
                buttons[offer] = self._add_offer(card, offer, _tr("Select plan"))
                cards.append(card)
        else:
            for plan in plans:
                card = Card(plan_name(plan))
                for offer in valid:
                    if offer.plan == plan:
                        buttons[offer] = self._add_offer(
                            card, offer, _period(offer.period)
                        )
                cards.append(card)
        columns = OFFER_COLUMNS.value
        for index, card in enumerate(cards):
            card.column.addStretch(1)
            self.choices.addWidget(card, index // columns, index % columns)
        for column in range(min(len(cards), columns)):
            self.choices.setColumnStretch(column, 1)
        if buttons:
            recommended = next(
                (offer for offer in buttons if self._recommended(offer)),
                next(iter(buttons)),
            )
            buttons[selected if selected in buttons else recommended].setChecked(True)

    def _add_offer(self, card: Card, offer: Offer, title: str) -> QRadioButton:
        button = QRadioButton(title)
        button.setAccessibleName(
            f"{plan_name(offer.plan)} {title} {money(offer.price)}"
        )
        self._group.addButton(button)
        button.toggled.connect(lambda checked: self._choose(offer) if checked else None)
        if self._recommended(offer):
            card.setProperty("recommendedOffer", True)
            card.add(label(_tr("Recommended"), wrap=True))
        card.add(button)
        price_label = label(_price_line(offer), "StateTitle", wrap=True)
        price_label.setTextFormat(Qt.TextFormat.PlainText)
        card.add(price_label)
        if (monthly := offer.monthly) is not None:
            text = _tr("= {price} a month").format(price=money(monthly))
            monthly_label = label(text, "Dim", wrap=True)
            monthly_label.setTextFormat(Qt.TextFormat.PlainText)
            card.add(monthly_label)
        return button

    @staticmethod
    def _recommended(offer: Offer) -> bool:
        return (offer.plan, offer.period) in (("plus", "year"), ("premium", "pass_12"))

    def _choose(self, offer: Offer | None) -> None:
        self._choice = offer
        self._url = None
        self.qr.clear()
        self.qr.hide()
        if self._pending_change is None:
            self._say("")
        self._forget_review()
        self._offer_description()
        self.benefits.setText(
            _tr("◷ Listening allowance    ◈ Learning tools")
            if offer and offer.plan in ("standard", "lite")
            else _tr("∞ Unlimited listening    ◈ Learning tools    ⚡ Priority")
            if offer
            else ""
        )
        self._buttons()

    @property
    def _subscribed(self) -> bool:
        return self._account is not None and self._account.subscribed

    @property
    def _ending(self) -> bool:
        account = self._account
        return (
            account is not None
            and account.subscription is not None
            and account.subscription.status == "ending"
        )

    def _can_offer(self, offer: Offer) -> bool:
        if not self._subscribed:
            return offer.change_mode is None
        account = self._account
        assert account is not None
        subscription = account.subscription
        return (
            offer.change_mode is not None
            and offer.plan in SUBSCRIPTIONS
            and (
                subscription is None
                or (
                    subscription.status in ("active", "ending")
                    and subscription.scheduled is None
                    and (offer.plan, offer.period)
                    != (account.billing_plan, subscription.period)
                )
            )
        )

    def _offer_description(self) -> None:
        offer = self._choice
        words = ""
        if offer is not None:
            words = (
                _switch_disclosure(offer, self._ending)
                if self._subscribed
                else _disclosure(offer)
            )
        self.renewal.setText(words)
        self.renewal.setTextFormat(Qt.TextFormat.PlainText)

    # -- "Have a code?" ---------------------------------------------------------------

    def _show_code_offer(self) -> None:
        offer = None if self._code is None else self._code_offer
        if offer is None:
            offer = self._prices.code_offer
        self.code_offer.setText(code_offer_line(offer) if offer else "")
        show_codes = self._account_ready and not self._subscribed
        self.code_offer.setVisible(show_codes and offer is not None)
        typed = self._code is not None
        asking = self._asking_code and not typed
        self.have_code.setVisible(show_codes and not typed and not asking)
        self.code.setVisible(show_codes and asking)
        self.apply_code.setVisible(show_codes and asking)
        self.remove_code.setVisible(show_codes and typed)
        if not show_codes:
            self.code_message.hide()
        self._buttons()

    def _ask_code(self) -> None:
        self._asking_code = True
        self._show_code_offer()
        self.code.setFocus()

    def _check_code(self) -> None:
        typed = self.code.text().strip()
        if self.paying or not self._account_ready or self._subscribed or not typed:
            return
        revision = self._account_revision

        def received(result: PriceList | str) -> None:
            self._paying = False
            if self._account_revision != revision:
                self._buttons()
                return
            if isinstance(result, str):
                self.code_message.setText(result)
                self.code_message.show()
            else:
                self._code, self._code_offer = typed, result.code_offer
                self._asking_code = False
                self.code.clear()
                self.code_message.hide()
                self._show(result.offers)
            self._show_code_offer()

        self._paying = True
        self.code_message.setText(_tr("Checking the code…"))
        self.code_message.show()
        self._buttons()
        self._billing.check_code(typed, received)

    def _remove_code(self) -> None:
        if self.paying:
            return
        self._code = None
        self._show(self._prices.offers)
        self._show_code_offer()

    # -- paying, and a plan change's review --------------------------------------------

    @property
    def _changing(self) -> bool:
        """The chosen offer is a change, reviewed first: the server's price
        says so (a subscription's), or the account holds a pass and picks
        another - unless the server then said it's a further pass, simply
        bought."""
        choice, account = self._choice, self._account
        if choice is None or self._further_pass:
            return False
        return choice.change_mode is not None or (
            account is not None and account.plan in PASSES and choice.plan in PASSES
        )

    def _say(self, words: str) -> None:
        self.message.setText(words)
        self.message.setVisible(bool(words))
        self._buttons()

    def _forget_review(self) -> None:
        self._preview = None
        self._further_pass = False
        self.preview.clear()
        self.preview.hide()

    @property
    def _can_pay(self) -> bool:
        return (
            self._account_ready
            and not self._subscribed
            and self._choice is not None
            and (
                not self._changing
                or (self._preview is not None and self._preview.needs_checkout)
            )
        )

    def _buttons(self) -> None:
        free = self._account_ready and not self.paying
        choice = self._choice if self._account_ready else None
        available = choice is not None and free
        changing = choice is not None and self._changing
        reviewed = self._preview is not None
        pays = self._can_pay
        assert self.pay.title is not None
        self.pay.title.setText(_tr("Checkout") if pays else _tr("Review change"))
        self.pay.title.setVisible(pays or changing)
        self.pay.setVisible(pays or changing or not self.message.isHidden())
        self.pay_here.setVisible(pays)
        self.pay_phone.setVisible(pays)
        self.review.setVisible(changing and not reviewed)
        self.confirm.setVisible(changing and reviewed and not pays)
        self.review.setText(
            _tr("Switch to {period}").format(period=_period(choice.period))
            if self._subscribed
            and choice is not None
            and self._account is not None
            and choice.plan == self._account.billing_plan
            else _tr("Review change")
        )
        for button in (self.pay_here, self.pay_phone, self.review, self.confirm):
            button.setEnabled(available)
        account = self._account
        self.manage.setVisible(
            self._account_ready and account is not None and account.provider is not None
        )
        self.resume.setVisible(
            self._account_ready and self._ending and self._billing.resume is not None
        )
        self.manage.setEnabled(free)
        self.resume.setEnabled(free)
        self.renewal.setVisible(choice is not None and bool(self.renewal.text()))
        self.benefits.setVisible(choice is not None)
        self.auto_renewal.setVisible(
            choice is not None and not self._subscribed and choice.plan in SUBSCRIPTIONS
        )
        for index in range(self.choices.count()):
            item = self.choices.itemAt(index)
            if item is not None and (card := item.widget()) is not None:
                card.setVisible(self._account_ready)
        for radio in self._group.buttons():
            radio.setEnabled(free)
        self.apply_code.setEnabled(free and bool(self.code.text().strip()))
        self.code.setEnabled(free)
        self.remove_code.setEnabled(free)

    def _resume(self) -> None:
        resume = self._billing.resume
        if resume is None or self.paying or not self._account_ready or not self._ending:
            return
        revision = self._account_revision

        def received(reason: str | None) -> None:
            self._paying = False
            if revision == self._account_revision:
                self._say(reason or "")
            self._buttons()

        self._paying = True
        self._say(_tr("Changing your plan…"))
        resume(received)

    def _review(self) -> None:
        choice = self._choice
        if (
            self.paying
            or not self._account_ready
            or choice is None
            or not self._changing
        ):
            return
        revision = self._account_revision
        self._finish_pending_change()

        def received(result: ChangePreview | str | None) -> None:
            self._paying = False
            if choice is self._choice and revision == self._account_revision:
                if isinstance(result, str):
                    self._say(result)
                elif result is None and choice.plan in PASSES:
                    self._further_pass = True
                    self.preview.setText(further_pass_lines(choice))
                    self.preview.show()
                    self._say("")
                elif (
                    result is None
                    or self._subscribed
                    and (
                        result.needs_checkout
                        or (self._ending and not result.resumes_renewal)
                    )
                ):
                    self._say(_tr("That change isn’t available for your plan."))
                else:
                    self._preview = result
                    self.preview.setText(preview_lines(result))
                    self.preview.show()
                    self._say("")
            self._buttons()

        self._paying = True
        self._say(_tr("Working out the change…"))
        self._buttons()
        self._billing.preview(choice, received)

    def _change_seen(self, preview: ChangePreview, before: Account | None) -> bool:
        account = self._account
        if account is None or before is None or account.id != before.id:
            return False
        subscription = account.subscription
        previous = before.subscription
        if subscription is not None:
            scheduled = subscription.scheduled
            if scheduled is not None and (
                scheduled.plan,
                scheduled.period,
                scheduled.effective_at,
            ) == (preview.plan, preview.period, preview.effective_at):
                return True
            if (
                account.billing_plan == preview.plan
                and subscription.period == preview.period
            ):
                return account.billing_plan != before.billing_plan or (
                    previous is not None and previous.period != subscription.period
                )
        return account.plan == preview.plan and (
            account.plan != before.plan
            or (
                account.renews_at != before.renews_at
                and account.renews_at == preview.renewal_at
            )
        )

    def _finish_pending_change(self) -> None:
        self._pending_change = None
        self._change_hold.stop()
        self._buttons()

    def _confirm(self) -> None:
        preview = self._preview
        if self.paying or not self._account_ready or preview is None:
            return
        before = self._account

        def received(result: ChangeResult) -> None:
            self._paying = False
            if preview is self._preview:
                self._forget_review()
                if result is ChangeStatus.PENDING and not self._change_seen(
                    preview, before
                ):
                    self._pending_change = (preview, before)
                    # A scheduled change may only show in the account once it takes effect.
                    # Keep watching the account after the hold allows another review.
                    self._change_hold.start(CHANGE_CONFIRMATION_HOLD.value * 60 * 1000)
                    self._say(_tr("Your plan change is still being confirmed."))
                elif isinstance(result, str):
                    self._say(result)
                elif (
                    result is None
                    and preview.scheduled
                    and preview.effective_at is not None
                ):
                    self._say(
                        _tr("Done. {plan} starts from {date}.").format(
                            plan=plan_name(preview.plan),
                            date=_date(preview.effective_at),
                        )
                    )
                else:
                    self._say(_tr("Done. Your plan is updating."))
            self._buttons()

        self._paying = True
        self._say(_tr("Changing your plan…"))
        self._buttons()
        self._billing.change(preview, received)

    def _pay(self, *, on_pc: bool) -> None:
        choice, preview = self._choice, self._preview
        if self.paying or choice is None or not self._can_pay:
            return
        revision = self._account_revision
        if self._url is not None:
            self._display_checkout(self._url, on_pc)
            return
        self._finish_pending_change()

        def received(result: ChangeResult) -> None:
            self._paying = False
            self._buttons()
            if (
                choice is self._choice
                and revision == self._account_revision
                and self._can_pay
            ):
                if result is ChangeStatus.PENDING:
                    # Retry the same preview ID to recover the pass checkout link.
                    self._say(_tr("Your plan change is still being confirmed."))
                elif isinstance(result, (QUrl, str)):
                    self._display_checkout(result, on_pc)

        self._paying = True
        self._say(_tr("Preparing checkout…"))
        self._buttons()
        if preview is not None:
            self._billing.change(preview, received)
        else:
            self._billing.checkout(choice, self._code, received)

    def _display_checkout(self, result: QUrl | str, on_pc: bool) -> None:
        if isinstance(result, str):
            self._say(result)
            if self._preview is not None:  # its price may have gone stale
                self._forget_review()
                self._buttons()
            return
        self._url = result
        if on_pc:
            if QDesktopServices.openUrl(result):
                self._say(_tr("Your plan updates when payment is confirmed."))
            else:
                self._say(_tr("Use the QR code to open checkout."))
        else:
            self.qr.setPixmap(
                _qr(result.toString(QUrl.ComponentFormattingOption.FullyEncoded))
            )
            self.qr.show()
            self._say(_tr("Scan with your phone to open checkout."))
