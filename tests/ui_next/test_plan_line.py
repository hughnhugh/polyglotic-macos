"""The plan line (polyglotic-hq 185, from 191's P3): each state of the plan
record as the server states it - its own examples - in one line, with
"Get Plus" only where Plus ends with nothing after it."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from PySide6.QtCore import QLocale
from PySide6.QtGui import QAction, QDesktopServices
from PySide6.QtWidgets import QApplication, QPushButton
from tests.ui.fakes import FakeAppList, MemorySettingsStore

from polyglotic_desktop.connection.protocol import Plan, PlanState, parse_at
from polyglotic_desktop.connection.reconnect import StopReason
from polyglotic_desktop.connection.session import SessionState, Status
from polyglotic_desktop.core.shared.papers import PLUS
from polyglotic_desktop.main import QtListener, plan_shown
from polyglotic_desktop.ui.app import DesktopApp
from polyglotic_desktop.ui_next.account_page import AccountPage
from polyglotic_desktop.ui_next.caption_window import notice_text
from polyglotic_desktop.ui_next.home import StateCard
from polyglotic_desktop.ui_next.plan import plan_text
from polyglotic_desktop.ui_next.views.caption_window import Notice
from polyglotic_desktop.ui_next.views.home import (
    Action,
    HomeState,
    ListeningState,
    Title,
    state_line,
)
from polyglotic_desktop.ui_next.views.plan import (
    PlanLine,
    PlanShown,
    PlanWords,
    plan_line,
    plus_page,
)

EXAMPLES = Path(__file__).resolve().parents[1] / "protocol_examples" / "v1"


def example(name: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((EXAMPLES / f"{name}.json").read_text("utf-8"))
    return data


def line_of(name: str) -> PlanLine:
    data = example(name)
    state = PlanState.model_validate(data.get("plan", data))
    return plan_line(plan_shown(state))


def at(text: str) -> datetime:
    return parse_at(text)


def test_each_state_of_the_servers_examples_in_one_line() -> None:
    assert line_of("welcome.plan") == PlanLine(PlanWords.TESTING)  # the alpha
    assert line_of("plan.plus") == PlanLine(
        PlanWords.RENEWS, at("2027-01-03T13:00:00.000Z")
    )
    assert line_of("plan.ending") == PlanLine(
        PlanWords.UNTIL, at("2027-12-03T13:00:00.000Z")
    )
    assert line_of("plan.grace") == PlanLine(
        PlanWords.PAYMENT_RETRYING, at("2027-01-02T13:00:00.000Z")
    )
    assert line_of("plan.free") == PlanLine(
        PlanWords.ENDED_PAYMENT, get_plus=True, has_plus=False
    )
    assert line_of("plan.pass") == PlanLine(
        PlanWords.UNTIL, at("2026-12-15T09:00:00.000Z")
    )


def test_a_cohort_says_its_end_and_offers_plus() -> None:
    until = datetime(2026, 12, 3, 13, tzinfo=UTC)
    cohort = PlanShown("plus", "cohort", "active", until)
    assert plan_line(cohort) == PlanLine(PlanWords.TESTING_UNTIL, until, get_plus=True)


def test_a_cohorts_line_fits_any_cohort(qapp: QApplication) -> None:
    """polyglotic-hq 228 (224's finding 2; DECISIONS.md #93): a cohort with
    an end date read "Plus for the beta, until ..." - the alpha's testers
    too. The line fits the alpha, the beta's cohorts and any later one,
    with no date, a date, and once Plus has ended."""
    before = QLocale()
    QLocale.setDefault(QLocale(QLocale.Language.English, QLocale.Country.Australia))
    try:
        until = datetime(2026, 12, 3, 13, tzinfo=UTC)
        dated = plan_text(plan_line(PlanShown("plus", "cohort", "active", until)))
    finally:
        QLocale.setDefault(before)
    assert dated.startswith("Plus, free while you test, until ") and "2026" in dated
    open_ended = plan_text(plan_line(PlanShown("plus", "cohort", "active")))
    assert open_ended == "Plus, free while you test Polyglotic"
    ended = plan_text(plan_line(PlanShown("free", "cohort", "ended")))
    assert ended == "Plus has ended"
    for text in (dated, open_ended, ended):
        assert "beta" not in text and "alpha" not in text


def test_ended_and_no_plus_offer_plus_and_say_why_when_told() -> None:
    assert plan_line(PlanShown("free", "cohort", "ended")) == PlanLine(
        PlanWords.ENDED, get_plus=True, has_plus=False
    )
    refunded = PlanShown("free", "subscription", "ended", message="plus_ended_refund")
    assert plan_line(refunded).words is PlanWords.ENDED_REFUND
    assert plan_line(PlanShown("free", "none", "ended")).words is PlanWords.NO_PLUS
    paused = PlanShown("plus", "subscription", "paused")
    assert plan_line(paused) == PlanLine(PlanWords.PAUSED, has_plus=False)


def test_a_refunds_line_never_says_the_money_is_back() -> None:
    """polyglotic-hq 237 (223's QA, medium 2): "Plus has ended with a
    refund" after the payment provider refused the refund - the buyer had
    neither Plus nor the money. The server ends Plus as the refund is asked
    for (`plus_ended_refund`), so the line says that, in every language."""
    from tools.i18n import __main__ as i18n
    from tools.i18n import ts

    refunded = PlanShown("free", "subscription", "ended", message="plus_ended_refund")
    text = plan_text(plan_line(refunded))
    assert text == "Plus has ended: you asked for a refund"
    source = "Plus has ended: you asked for a refund"
    for language, refunded_words in (("zh_CN", "已退还"), ("zh_TW", "已退還")):
        file = ts.read(i18n.ts_path(language))
        said = {s: t.forms for (_c, s, _d), t in file.translations.items()}
        assert said[source][0].startswith("Plus ")
        assert refunded_words not in said[source][0] and "退款" in said[source][0]


def test_a_date_that_cant_be_read_is_left_out_not_guessed() -> None:
    state = PlanState.model_validate(example("plan.plus") | {"until": "soon"})
    assert plan_line(plan_shown(state)) == PlanLine(PlanWords.PLUS)


def test_get_plus_carries_the_installs_link_tag() -> None:
    assert plus_page(PLUS) == PLUS
    assert plus_page(PLUS, "discord") == PLUS + "?ref=discord"
    assert plus_page(PLUS, "a b&c") == PLUS + "?ref=a+b%26c"


def test_the_words_with_the_date_in_the_learners_format(qapp: QApplication) -> None:
    before = QLocale()
    QLocale.setDefault(QLocale(QLocale.Language.English, QLocale.Country.Australia))
    try:
        until = datetime(2027, 1, 3, 13, tzinfo=UTC)
        text = plan_text(PlanLine(PlanWords.RENEWS, until))
    finally:
        QLocale.setDefault(before)
    assert text.startswith("Plus, renews ") and "2027" in text
    assert plan_text(PlanLine(PlanWords.UNTIL)) == "Plus"  # no date: none made up
    assert plan_text(PlanLine(PlanWords.ENDED, get_plus=True)) == "Plus has ended"


def test_account_shows_the_line_and_get_plus_opens_the_plus_page(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    opened: list[str] = []
    monkeypatch.setattr(
        QDesktopServices, "openUrl", lambda url: opened.append(url.toString())
    )
    page = AccountPage(plus_page(PLUS, "discord"))
    assert page.plan_card.isHidden()  # no plan heard yet
    page.show_plan(PlanLine(PlanWords.ENDED, get_plus=True))
    assert not page.plan_card.isHidden() and page.plan.text() == "Plus has ended"
    button = page.findChild(QPushButton, "account.get_plus")
    assert button is not None and button.text() == "Get Plus"
    assert not button.isHidden()
    button.click()
    assert opened == [PLUS + "?ref=discord"]
    page.show_plan(PlanLine(PlanWords.RENEWS, datetime(2027, 1, 3, tzinfo=UTC)))
    assert button.isHidden()  # a renewing subscription isn't offered Plus
    page.set_signed_in(False)
    assert page.plan_card.isHidden()


def test_home_says_the_line_under_the_state(qapp: QApplication) -> None:
    card = StateCard(QAction("Pause"))
    assert card.plan.isHidden()
    card.set_plan("Plus, free while you test, until 3 December 2026")
    assert not card.plan.isHidden()
    assert card.plan.text() == "Plus, free while you test, until 3 December 2026"
    card.set_plan(None)
    assert card.plan.isHidden()


def test_plus_ended_says_what_ended_what_stays_and_what_to_do(
    qapp: QApplication,
) -> None:
    """polyglotic-hq 185 (191's P3): the 4009 close is "Plus has ended",
    with what the learner keeps and "Get Plus" in the place of Pause -
    never a generic "Stopped"."""
    line = state_line(HomeState(ListeningState.PLUS_ENDED, chosen=True))
    assert (line.title, line.action) == (Title.PLUS_ENDED, Action.GET_PLUS)
    card = StateCard(QAction("Pause"))
    card.show_state(HomeState(ListeningState.PLUS_ENDED, chosen=True))
    assert card.title_label.text() == "Plus has ended"
    assert "Your words and lookups stay" in card.detail.text()
    assert "get Plus to listen again" in card.detail.text()
    assert not card.get_plus.isHidden() and card.pause.isHidden()
    assert card.get_plus.text() == "Get Plus"
    card.set_plan("Plus has ended")  # the title says it already: not twice
    assert card.plan.isHidden()
    window_words = notice_text(Notice.PLUS_ENDED, None)
    assert window_words == "Plus has ended - captions stopped; see Home"
    card.set_plan("Plus, free while you test, until 3 December 2026")
    card.show_state(HomeState(ListeningState.LISTENING, chosen=True))
    assert card.get_plus.isHidden() and not card.pause.isHidden()
    assert not card.plan.isHidden()


def test_plus_ended_says_what_really_stays(qapp: QApplication) -> None:
    """polyglotic-hq 235 (228's note): "Your words, transcripts and lookups
    stay" read as if transcripts are stored, but a transcript lasts only
    the session unless it's saved (#346). Home's line and Help's check
    both say what stays, and that a transcript is gone when you quit - in
    the transcript's own words."""
    from polyglotic_desktop.core.listening.check import Problem
    from polyglotic_desktop.ui_next.help_page import problem

    card = StateCard(QAction("Pause"))
    card.show_state(HomeState(ListeningState.PLUS_ENDED, chosen=True))
    _, help_fix = problem(Problem.PLUS_ENDED, "")
    for said in (card.detail.text(), help_fix):
        assert "Your words and lookups stay" in said
        assert "transcripts" not in said
        assert "a transcript is gone when you quit, unless you save it" in said


def test_a_plan_with_plus_again_is_plus_and_an_ended_one_isnt() -> None:
    assert line_of("plan.plus").has_plus and line_of("welcome.plan").has_plus
    assert not line_of("plan.free").has_plus


def test_no_plus_while_a_session_holding_plus_is_open_ends_with_it() -> None:
    """polyglotic-hq 237 (223's QA, medium 1): a cancel mid-session said
    "Plus has ended" over captions that carried on - by the protocol's
    design the session keeps its tier until it ends."""
    cancelled = PlanShown("free", "subscription", "ended")
    ends = PlanLine(PlanWords.ENDS_WITH_SESSION, get_plus=True, has_plus=False)
    assert plan_line(cancelled, held="plus") == ends
    for message in ("plus_ended_payment", "plus_ended_refund"):
        ended = PlanShown("free", "subscription", "ended", message=message)
        assert plan_line(ended, held="plus") == ends
    paused = PlanShown("plus", "subscription", "paused")
    assert plan_line(paused, held="plus") == ends
    # with no session open, or one that holds no Plus, the plan's own line
    assert plan_line(cancelled).words is PlanWords.ENDED
    assert plan_line(cancelled, held="free").words is PlanWords.ENDED
    # a change up, or one that keeps Plus, is said as it is
    assert line_of("plan.ending") == plan_line(
        plan_shown(PlanState.model_validate(example("plan.ending"))), held="plus"
    )


def test_the_line_says_plus_ends_with_the_session_then_that_it_has_ended(
    qapp: QApplication,
) -> None:
    """The app's listener: a `plan` without Plus mid-session says Plus ends
    when you stop listening; once the session ends, the plan's own line.
    `limit_reached`'s plan (the session ending now) and a sign-out's end
    say nothing of the kind."""
    desktop = DesktopApp(MemorySettingsStore(), None, FakeAppList())
    listener = QtListener(desktop, None)
    lines: list[PlanLine] = []
    listener.plan_shown.connect(lines.append)
    welcome = PlanState.model_validate(example("plan.plus"))
    cancelled = Plan.model_validate(
        example("plan.plus") | {"tier": "free", "status": "ended", "until": None}
    )
    listener.status_changed(Status(SessionState.LISTENING, tier="plus"))
    listener.plan_changed(welcome)
    listener.plan_changed(cancelled)
    QApplication.processEvents()
    assert [line.words for line in lines] == [
        PlanWords.RENEWS,
        PlanWords.ENDS_WITH_SESSION,
    ]
    assert plan_text(lines[-1]) == "Plus ends when you stop listening"
    listener.status_changed(Status(SessionState.STOPPED, stopped=StopReason.CLOSED))
    QApplication.processEvents()
    assert lines[-1] == PlanLine(PlanWords.ENDED, get_plus=True, has_plus=False)

    lines.clear()  # Plus's date passes mid-session: limit_reached, then 4009
    listener.status_changed(Status(SessionState.LISTENING, tier="plus"))
    listener.plan_changed(PlanState.model_validate(example("limit_reached")["plan"]))
    QApplication.processEvents()
    assert [line.words for line in lines] == [PlanWords.ENDED]

    lines.clear()  # signing out mid-session: the account's plan isn't shown again
    listener.status_changed(Status(SessionState.LISTENING, tier="plus"))
    listener.plan_changed(cancelled)
    listener.status_changed(
        Status(SessionState.STOPPED, stopped=StopReason.SIGN_IN_NEEDED)
    )
    QApplication.processEvents()
    assert [line.words for line in lines] == [PlanWords.ENDS_WITH_SESSION]
    desktop.close()
