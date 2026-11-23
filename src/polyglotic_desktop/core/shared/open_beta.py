"""Open-beta account, allowance, prices and plan-change values shared by the
desktop's adapters (polyglotic-hq 660, 684; PLAN-OPEN-BETA v16-v18).

The server decides everything here: the plan, the percentage left, the
prices, what a code grants and what a plan change costs. The app only shows
it - a percentage, never a caption or hour count.
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

from polyglotic_desktop.core.shared.tunables import tunable

PLAN_CHANGE_TIMEOUT = tunable(
    "billing.plan_change_timeout",
    35.0,
    "seconds",
    (15.0, 120.0),
    source="693: a plan change can make three 10-second provider calls",
)

CHANGE_CONFIRMATION_HOLD = tunable(
    "billing.change_confirmation_hold",
    30,
    "minutes",
    (5, 1440),
    source="Server #371: default hold for a plan change with no provider answer",
)

USAGE_WARNING_PERCENTS = tunable(
    "open_beta.usage_warning_percents",
    (20.0, 5.0),
    "percent of the allowance left",
    (1, 99),
    source="PLAN-OPEN-BETA v17: warn once each at 20 % and 5 % of a capped"
    " plan's allowance left; each level once per refill",
)

DAILY_PLANS = frozenset({"beta_free"})
"""Plans whose allowance refills each day (the server's plan keys; a true
constant: the server's contract names them). Every other capped plan (Lite,
a Standard pass) refills each billing month."""

PERIOD_MONTHS = {
    "month": 1,
    "year": 12,
    "pass_1": 1,
    "pass_3": 3,
    "pass_6": 6,
    "pass_12": 12,
}
"""How many months each period key of the server's price list covers."""


@dataclass(frozen=True, slots=True)
class Allowance:
    """The server's displayed percentage and when it next refills."""

    percent: int
    resets_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class Money:
    """An amount in major currency units, as the server priced it."""

    amount: Decimal
    currency: str


@dataclass(frozen=True, slots=True)
class ScheduledSwitch:
    plan: str
    period: str
    effective_at: datetime


@dataclass(frozen=True, slots=True)
class Subscription:
    status: str
    period: str | None = None
    period_end: datetime | None = None
    renews_at: datetime | None = None
    next_price: Money | None = None
    scheduled: ScheduledSwitch | None = None
    plan: str | None = None


@dataclass(frozen=True, slots=True)
class Account:
    """The server's current view of a signed-in account."""

    id: str
    cohort: str
    registered: bool
    plan: str
    allowance: Allowance | None
    renews_at: datetime | None = None
    provider: str | None = None
    subscription: Subscription | None = None
    email: str | None = None

    @property
    def subscribed(self) -> bool:
        if self.subscription is not None:
            return self.subscription.status != "ended"
        # Earlier servers sent only a provider. Keep checkout hidden there.
        return self.provider is not None

    @property
    def billing_plan(self) -> str:
        return (self.subscription.plan if self.subscription else None) or self.plan

    @property
    def billing_state(self) -> tuple[str, str, str | None, Subscription | None]:
        return self.id, self.plan, self.provider, self.subscription


@dataclass(frozen=True, slots=True)
class UsageMeter:
    """What a capped plan's meter shows: the percentage left and its refill.
    Unlimited plans have none."""

    plan: str
    percent: int
    resets_at: datetime | None = None

    @property
    def daily(self) -> bool:
        return self.plan in DAILY_PLANS


def usage_meter(account: Account | None) -> UsageMeter | None:
    """The meter for `account`: only where the server states a percentage
    (it sends none for an unlimited plan)."""
    if account is None or account.allowance is None:
        return None
    return UsageMeter(
        account.plan, account.allowance.percent, account.allowance.resets_at
    )


@dataclass(slots=True)
class UsageWarnings:
    """Which usage level a capped plan has newly reached, each once per
    refill: a warning percentage as the allowance drains, and 0 when it runs
    out while the app is open (an allowance already at 0 when first seen is
    Home's to say, not a new event)."""

    _refill: tuple[str, datetime | None] | None = None
    _warned: float | None = None
    _seen_left: bool = False
    _ran_out: bool = False

    def crossed(self, account_id: str, meter: UsageMeter | None) -> int | None:
        if meter is None:
            self._refill = None
            return None
        levels = USAGE_WARNING_PERCENTS.value
        refill = (account_id, meter.resets_at)
        if refill != self._refill or meter.percent > max(levels):
            self._refill = refill
            self._warned = None
            self._seen_left = False
            self._ran_out = False
        if meter.percent <= 0:
            newly = self._seen_left and not self._ran_out
            self._ran_out = True
            return 0 if newly else None
        self._seen_left = True
        reached = [level for level in levels if meter.percent <= level]
        if not reached:
            return None
        level = min(reached)
        if self._warned is not None and level >= self._warned:
            return None
        self._warned = level
        return round(level)


@dataclass(frozen=True, slots=True)
class Offer:
    """A server-priced purchase option: a plan for a period."""

    plan: str
    period: str
    price: Money
    renewal_price: Money | None = None
    renewal_at: datetime | None = None
    pass_ends_at: datetime | None = None
    """When a pass bought now would end: after the pass the account holds,
    when it has one (the server's date; an estimate for a first pass)."""
    change_mode: str | None = None
    """Set where buying this is a change to the account's subscription
    (`prorated_immediately`, `next_period`): reviewed before it's confirmed."""

    @property
    def monthly(self) -> Money | None:
        """The price spread over a longer period's months, None for one month."""
        months = PERIOD_MONTHS.get(self.period, 1)
        if months <= 1:
            return None
        exponent = self.price.amount.as_tuple().exponent
        smallest = Decimal(1).scaleb(
            min(exponent, 0) if isinstance(exponent, int) else 0
        )
        return Money(
            (self.price.amount / months).quantize(smallest, ROUND_HALF_UP),
            self.price.currency,
        )

    @property
    def first_period_differs(self) -> bool:
        """The first payment isn't the renewal's (a founding or code discount)."""
        return self.renewal_price is not None and self.renewal_price != self.price


@dataclass(frozen=True, slots=True)
class CodeOffer:
    """What a code grants: `percent_off_first_period` with its percentage,
    or `community_pass_prices` (the community passes, in any country)."""

    kind: str
    percent_off: int | None = None


@dataclass(frozen=True, slots=True)
class PriceList:
    """The options this account may buy, and the code offer they are under."""

    offers: tuple[Offer, ...]
    code_offer: CodeOffer | None = None


@dataclass(frozen=True, slots=True)
class ChangePreview:
    """What a plan change costs, from the server, shown before confirming:
    the charge now, the next charge and its date, and when it takes effect."""

    id: str
    plan: str
    period: str
    mode: str
    """`prorated_immediately`, `next_period` or `pass_upgrade`."""
    due_now: Money
    renewal_price: Money | None = None
    renewal_at: datetime | None = None
    effective_at: datetime | None = None
    pass_ends_at: datetime | None = None
    """A pass's end after an upgrade: the end it already had."""
    resumes_renewal: bool = False

    @property
    def scheduled(self) -> bool:
        return self.mode == "next_period"

    @property
    def needs_checkout(self) -> bool:
        """A pass upgrade is paid on a checkout page; a subscription change
        is charged to the payment method the provider holds."""
        return self.mode == "pass_upgrade"
