"""The plan line: the account's plan as the server states it, in one line for
Home and Account (polyglotic-hq 185, from 191's P3; plain Python, no Qt).

The app never decides a plan (protocol.md, `plan`; server decision 0039):
it reads the plan record's state and says it plainly, with the date it's
about. Plus is a monthly or yearly subscription (the user, 2026-11-08); the
alpha and beta have Plus by their cohort. A cohort's line fits any cohort -
the alpha, the beta's, a later one - with or without an end date
(polyglotic-hq 228; DECISIONS.md #93 leaves the alpha's open).

| The plan | The line |
|---|---|
| a cohort (testers) with an end date | Plus, free while you test, until {date} |
| a cohort with none | Plus, free while you test Polyglotic |
| a subscription, renewing | Plus, renews {date} |
| a subscription, cancelled | Plus until {date} |
| a payment being tried again (grace) | Plus - your payment didn't go through; we'll try again until {date} |
| paused | Plus is paused: your payment didn't go through |
| ended, or no Plus | Plus has ended (with why, when the server says) / No Plus on this account |

`plus_ended_refund` means Plus ended for a refund or a withdrawal: the
server ends it when the refund is asked for, before the payment provider
approves it, and the provider may refuse it (server `refund_refused`). So
its line says the refund was asked for, never that the money is back.
| given by us, a gift | Plus until {date}, or Plus |
| no Plus, while a listening session that holds Plus is open | Plus ends when you stop listening |

A change down never interrupts a listening session (protocol.md, `plan`):
the session keeps the tier it had until it ends, and the next `hello` gets
the new one. So while a session holding Plus is open, a plan without Plus
- a cancel, a refund or a failed payment mid-session - says Plus ends when
the session does, not that it has ended over captions that carry on
(polyglotic-hq 237, from 223's QA); the plan's own line follows once the
session ends.

"Get Plus" (it opens the site's Plus page in the browser) goes with a line
whose Plus ends with nothing after it - a cohort's with an end date, or none
at all - never with a subscription that renews or is being paid.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from urllib.parse import urlencode


@dataclass(frozen=True)
class PlanShown:
    """What the line reads from the server's plan: `tier` (free, plus,
    premium), `source` (cohort, subscription, pass, gift, complimentary,
    none), `status` (active, grace, ending, paused, ended), `until` (when the
    tier stops; None when open-ended) and the server's message code."""

    tier: str
    source: str
    status: str
    until: datetime | None = None
    message: str | None = None


class PlanWords(StrEnum):
    TESTING_UNTIL = "testing_until"
    TESTING = "testing"
    RENEWS = "renews"
    UNTIL = "until"
    PLUS = "plus"
    PAYMENT_RETRYING = "payment_retrying"
    PAUSED = "paused"
    ENDED = "ended"
    ENDED_PAYMENT = "ended_payment"
    ENDED_REFUND = "ended_refund"
    NO_PLUS = "no_plus"
    ENDS_WITH_SESSION = "ends_with_session"


@dataclass(frozen=True)
class PlanLine:
    words: PlanWords
    date: datetime | None = None
    get_plus: bool = False
    """Offer "Get Plus" beside it."""
    has_plus: bool = True
    """Plus now: a listening session stopped for its end may start again."""


_PAID = ("plus", "premium")


def plan_line(plan: PlanShown, held: str | None = None) -> PlanLine:
    """The line for `plan` (the table above). `held`: the tier the open
    listening session holds until it ends (its `welcome`'s), None when no
    listening session is open."""
    line = _line(plan)
    if held in _PAID and not line.has_plus:
        return PlanLine(PlanWords.ENDS_WITH_SESSION, get_plus=True, has_plus=False)
    return line


def _line(plan: PlanShown) -> PlanLine:
    until = plan.until
    if plan.tier in _PAID and plan.status != "ended":
        if plan.source == "cohort":
            if until is None:
                return PlanLine(PlanWords.TESTING)
            return PlanLine(PlanWords.TESTING_UNTIL, until, get_plus=True)
        if plan.status == "grace":
            return PlanLine(PlanWords.PAYMENT_RETRYING, until)
        if plan.status == "paused":  # Free from the next session (DOMAIN.md)
            return PlanLine(PlanWords.PAUSED, has_plus=False)
        if until is None:
            return PlanLine(PlanWords.PLUS)
        if plan.source == "subscription" and plan.status == "active":
            return PlanLine(PlanWords.RENEWS, until)
        return PlanLine(PlanWords.UNTIL, until)  # cancelled, a gift, ours
    if plan.message == "plus_ended_payment":
        return PlanLine(PlanWords.ENDED_PAYMENT, get_plus=True, has_plus=False)
    if plan.message == "plus_ended_refund":
        return PlanLine(PlanWords.ENDED_REFUND, get_plus=True, has_plus=False)
    if plan.source == "none":
        return PlanLine(PlanWords.NO_PLUS, get_plus=True, has_plus=False)
    return PlanLine(PlanWords.ENDED, get_plus=True, has_plus=False)


def plus_page(page: str, ref: str | None = None) -> str:
    """The site's Plus page, with the install's link tag (`?ref=`) when it
    has one, so a purchase is counted to the channel the learner came from
    (polyglotic-hq 191's P5)."""
    return f"{page}?{urlencode({'ref': ref})}" if ref else page
