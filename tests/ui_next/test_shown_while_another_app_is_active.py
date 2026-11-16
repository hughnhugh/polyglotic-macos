"""On a Mac a Qt tool window hides while its app isn't active, and
Polyglotic is never the active app while the learner is in a game or a
video: GitHub's Mac showed the dictation sign never appearing over TextEdit
(polyglotic-hq 429's run 3). Each of the app's tool windows asks to be
shown anyway (`WA_MacAlwaysShowToolWindow`; nothing changes on Windows)."""

from collections.abc import Iterator

import pytest
import shiboken6
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QWidget
from tests.ui_next.test_lookup_view import learner

from polyglotic_desktop.core.listening.sources import SourceId, SourceLabel
from polyglotic_desktop.ui_next.caption_window import CaptionWindow
from polyglotic_desktop.ui_next.dictation_sign import DictationSign
from polyglotic_desktop.ui_next.joined_window import JoinedWindow
from polyglotic_desktop.ui_next.lookup_card import LookupCard
from polyglotic_desktop.ui_next.settings_popover import SettingsPopover
from polyglotic_desktop.ui_next.views.caption_window import JoinedChoices, WindowChoices
from polyglotic_desktop.ui_next.views.placement import Rect

AREA = [Rect(0, 0, 1920, 1040)]


@pytest.fixture
def window(qapp: QApplication) -> Iterator[CaptionWindow]:
    made = CaptionWindow(
        "shown",
        SourceId("app"),
        WindowChoices(),
        SourceLabel("App", "#4dd0e1"),
        areas=lambda: AREA,
    )
    yield made
    shiboken6.delete(made)


def shows_anyway(widget: QWidget) -> bool:
    return widget.testAttribute(Qt.WidgetAttribute.WA_MacAlwaysShowToolWindow)


def test_the_caption_window_and_its_popover_show_while_another_app_is_active(
    window: CaptionWindow,
) -> None:
    assert shows_anyway(window)
    popover = SettingsPopover(window)
    assert shows_anyway(popover)


def test_the_joined_window_the_card_and_the_sign_too(qapp: QApplication) -> None:
    made: list[QWidget] = [
        JoinedWindow(JoinedChoices(), areas=lambda: AREA),
        LookupCard(learner()),
        DictationSign(),
    ]
    try:
        assert all(shows_anyway(widget) for widget in made)
    finally:
        for widget in made:
            shiboken6.delete(widget)
