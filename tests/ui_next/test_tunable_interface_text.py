"""Changing a value changes the text that describes it."""

from datetime import timedelta

import pytest
from PySide6.QtWidgets import QApplication

from polyglotic_desktop.core.learning.coverage import Coverage
from polyglotic_desktop.core.learning.known_chance import Chance, Moved, Start
from polyglotic_desktop.core.learning.known_map import Tally
from polyglotic_desktop.core.listening.check import Link, Problem, Status, Step
from polyglotic_desktop.ui_next import (
    heard_card,
    help_page,
    known_map_card,
    os_words,
)


@pytest.mark.parametrize("is_mac", [False, True])
def test_help_shows_the_live_limits(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch, is_mac: bool
) -> None:
    monkeypatch.setattr(os_words, "on_a_mac", lambda: is_mac)
    monkeypatch.setattr(help_page, "SOUND_WINDOW", 1)
    monkeypatch.setattr(help_page, "LIMIT", 8)
    monkeypatch.setattr(help_page, "HOLD_MINUTES", 1)
    monkeypatch.setattr(help_page, "MAX_WAIT_FOR_TEXT_SEC", 5)
    assert help_page.words(Link(Step.SOUND, Status.OK, source="Film"), False)[0] == (
        "Sound from Film in the last 1 second"
    )
    assert help_page.words(Link(Step.SOUND, Status.WAITING), False)[0] == (
        "Sound from it in the last 1 second"
    )
    for reason in (Problem.APP_QUIET, Problem.SYSTEM_QUIET, Problem.MIC_QUIET):
        title, _ = help_page.problem(reason, "Film")
        assert title.endswith("1 second")
    assert "up to 8" in help_page.problem(Problem.NOTHING_TICKED, "")[1]
    assert "add up to 8 apps" in help_page.set_up()[0][1]
    questions = dict(help_page.questions())
    assert "last 1 minute" in questions["What we keep"]
    assert "5 seconds by default" in questions["When do captions appear?"]
    monkeypatch.setattr(help_page, "MAX_WAIT_FOR_TEXT_SEC", 2.5)
    assert "2.5 s by default" in dict(help_page.questions())["When do captions appear?"]


def test_words_shows_each_feature_window(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(heard_card, "RECENT_DAYS", 1)
    monkeypatch.setattr(known_map_card, "WEEK", timedelta(days=4))
    monkeypatch.setattr(known_map_card, "FRESH", timedelta(days=2))
    assert "words in 1 day," in heard_card.coverage_lines(Coverage())[2]
    assert heard_card.listening_lines(0, 0)[1] == "0 min in the last 1 day"
    assert heard_card.met_lines(5, 2)[1] == "+2 new in the last 1 day"
    card = heard_card.HeardCard()
    try:
        assert card.coverage.title.text() == "COVERAGE, LAST 1 DAY"
    finally:
        card.deleteLater()
    assert known_map_card.week_text(Tally(), Tally()) == "No change in the last 4 days."
    assert "In the last 4 days:" in known_map_card.week_text(Tally(mastered=1), Tally())
    chance = Chance(0.4, Start.NOT_PLACED, ((Moved.FRESH_LOOKUP, -1.5),))
    assert "Looked up in the last 2 days." in known_map_card.why(chance, None, False)
