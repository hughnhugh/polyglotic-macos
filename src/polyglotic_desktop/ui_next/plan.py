"""The plan line's words (`views.plan`), in the interface's language, with
its date in the learner's own format - for Home and Account
(polyglotic-hq 185)."""

from collections.abc import Callable
from datetime import datetime

from PySide6.QtCore import QDate, QLocale
from PySide6.QtWidgets import QApplication

from polyglotic_desktop.ui_next.views.plan import PlanLine, PlanWords


def _tr(text: str) -> str:
    return QApplication.translate("Plan", text)


def day(moment: datetime) -> str:
    """`moment`'s date on this PC, as its regional format writes it."""
    local = moment.astimezone()
    return QLocale().toString(
        QDate(local.year, local.month, local.day), QLocale.FormatType.LongFormat
    )


_WORDS: dict[PlanWords, Callable[[], str]] = {
    # any testers' cohort - the alpha, the beta's, a later one (228)
    PlanWords.TESTING_UNTIL: lambda: _tr("Plus, free while you test, until {date}"),
    PlanWords.TESTING: lambda: _tr("Plus, free while you test Polyglotic"),
    PlanWords.RENEWS: lambda: _tr("Plus, renews {date}"),
    PlanWords.UNTIL: lambda: _tr("Plus until {date}"),
    PlanWords.PLUS: lambda: _tr("Plus"),
    PlanWords.PAYMENT_RETRYING: lambda: _tr(
        "Plus - your payment didn't go through; we'll try again until {date}"
    ),
    PlanWords.PAUSED: lambda: _tr("Plus is paused: your payment didn't go through"),
    PlanWords.ENDED: lambda: _tr("Plus has ended"),
    PlanWords.ENDED_PAYMENT: lambda: _tr(
        "Plus has ended: your payment didn't go through"
    ),
    # the server ends Plus as the refund is asked for, before the payment
    # provider approves it - and it may refuse it - so the line never says
    # the money is back (polyglotic-hq 237, from 223's QA)
    PlanWords.ENDED_REFUND: lambda: _tr("Plus has ended: you asked for a refund"),
    PlanWords.NO_PLUS: lambda: _tr("No Plus on this account"),
    # captions carry on to the session's end (protocol.md, `plan`; 237)
    PlanWords.ENDS_WITH_SESSION: lambda: _tr("Plus ends when you stop listening"),
}


def plan_text(line: PlanLine) -> str:
    """The line in words. A line about a date the server didn't send says
    so plainly rather than inventing one."""
    words = _WORDS[line.words]()
    if "{date}" not in words:
        return words
    if line.date is None:
        return _tr("Plus")
    return words.format(date=day(line.date))


def get_plus_text() -> str:
    """The button beside a line whose Plus ends with nothing after it."""
    return _tr("Get Plus")
