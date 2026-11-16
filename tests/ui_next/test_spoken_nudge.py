"""Naming the language is the path the app suggests (polyglotic-hq 317):
once Detect has heard a window's app speak one language steadily, the
window asks "This sounds like Russian. Always hear it as Russian?" - Yes
names it, Not now leaves Detect and never asks about that language again
for that window. Detect keeps working either way."""

from collections.abc import Iterator
from dataclasses import replace

import pytest
from PySide6.QtCore import QEvent, QObject
from PySide6.QtWidgets import QApplication
from tests.ui_next.made_up import finished_updates

from polyglotic_desktop.core.listening.captions import CaptionUpdate, Language
from polyglotic_desktop.core.listening.sources import SourceId
from polyglotic_desktop.core.listening.spoken import STEADY_CAPTIONS, SteadyLanguage
from polyglotic_desktop.ui.recorded_captions import APP, MIC
from polyglotic_desktop.ui_next.caption_window import CaptionWindow
from polyglotic_desktop.ui_next.caption_windows import CaptionWindows
from polyglotic_desktop.ui_next.spoken_nudge import SHOWN_MS
from polyglotic_desktop.ui_next.views.caption_window import (
    StoredWindows,
    WindowChoices,
)
from polyglotic_desktop.ui_next.views.placement import Rect

RU = Language("ru")
JA = Language("ja")
EN = Language("en")


class Store:
    def __init__(self, values: dict[str, object]) -> None:
        self.values = values

    def load(self) -> dict[str, object]:
        return dict(self.values)

    def save(self, values: object) -> None:
        assert isinstance(values, dict)
        self.values = dict(values)


def areas() -> list[Rect]:
    return [Rect(0, 0, 1920, 1040)]


def heard_in(
    language: Language, count: int, source: SourceId = APP, start: int = 0
) -> list[CaptionUpdate]:
    """`count` finished captions from `source`, each heard in `language`
    alone (the text is the recorded conversation's: only the label counts)."""
    return [
        replace(update, language=language, languages_heard=(language,))
        for update in finished_updates(count, source, start)
    ]


@pytest.fixture
def store() -> Store:
    return Store({"targets": ["en"]})


@pytest.fixture
def windows(qapp: QApplication, store: Store) -> Iterator[CaptionWindows]:
    found = CaptionWindows(store, MIC, areas)
    found.set_captioned([("Discord.exe", APP)])
    yield found
    found.close()


# -- the rule -----------------------------------------------------------------------------


def test_one_language_steadily_is_suggested_once_a_run() -> None:
    steady = SteadyLanguage()
    said = [steady.heard("ru", ("ru",)) for _ in range(STEADY_CAPTIONS + 3)]
    assert said == [None] * (STEADY_CAPTIONS - 1) + ["ru", None, None, None]


@pytest.mark.parametrize(
    ("between", "why"),
    [
        (("ja", ("ja",)), "another language"),
        (("ru", ("ru", "en")), "a mixed line"),
        ((None, ()), "no language known"),
        (("xx", ("xx",)), "a language it can't be told"),
    ],
)
def test_a_run_starts_again_after(
    between: tuple[str | None, tuple[str, ...]], why: str
) -> None:
    steady = SteadyLanguage()
    for _ in range(STEADY_CAPTIONS - 1):
        assert steady.heard("ru", ("ru",)) is None
    assert steady.heard(*between) is None, why
    said = [steady.heard("ru", ("ru",)) for _ in range(STEADY_CAPTIONS)]
    assert said[-1] == "ru" and said[:-1] == [None] * (STEADY_CAPTIONS - 1)


def test_a_declined_language_is_never_suggested() -> None:
    steady = SteadyLanguage()
    steady.declined.add("ru")
    assert not any(steady.heard("ru", ("ru",)) for _ in range(STEADY_CAPTIONS * 3))


# -- the window ---------------------------------------------------------------------------


def test_the_window_asks_and_yes_names_the_language(windows: CaptionWindows) -> None:
    window = windows.windows["Discord.exe"]
    window.show()
    for update in heard_in(RU, STEADY_CAPTIONS - 1):
        windows.apply(update)
    assert window.asking_spoken is None  # not steady yet
    windows.apply(heard_in(RU, 1, start=STEADY_CAPTIONS)[0])
    assert window.asking_spoken == "ru"
    nudge = window.nudge
    assert nudge is not None and nudge.isVisible()
    assert nudge.question.text() == (
        "This sounds like Russian. Always hear it as Russian?"
    )
    nudge.yes.click()
    assert window.choices.spoken == RU and window.asking_spoken is None
    assert not nudge.isVisible()
    assert windows.recent_spoken()[0] == "ru"  # first in every list now
    for update in heard_in(RU, STEADY_CAPTIONS * 2, start=10):
        windows.apply(update)
    assert window.asking_spoken is None  # named: never asked


def test_not_now_keeps_detect_and_is_never_asked_again_for_that_language(
    windows: CaptionWindows, store: Store
) -> None:
    window = windows.windows["Discord.exe"]
    window.show()
    for update in heard_in(RU, STEADY_CAPTIONS):
        windows.apply(update)
    assert window.nudge is not None
    window.nudge.no.click()
    assert window.choices.spoken is None and not window.nudge.isVisible()
    for update in heard_in(JA, 1, start=20) + heard_in(RU, 10, start=30):
        windows.apply(update)
    assert window.asking_spoken is None  # Russian: not again
    for update in heard_in(JA, STEADY_CAPTIONS, start=50):
        windows.apply(update)
    assert window.asking_spoken == "ja"  # another language may be
    windows.save_now()
    again = CaptionWindows(store, MIC, areas)
    assert again.stored.declined_spoken == {"Discord.exe": ("ru",)}
    again.close()


def test_my_speech_never_makes_the_window_ask(windows: CaptionWindows) -> None:
    window = windows.windows["Discord.exe"]
    windows.set_show_mic_everywhere(True)
    for update in heard_in(EN, STEADY_CAPTIONS * 2, source=MIC):
        windows.apply(update)
    assert window.asking_spoken is None


def test_a_window_naming_a_language_is_never_asked(windows: CaptionWindows) -> None:
    window = windows.windows["Discord.exe"]
    window.set_spoken_language("ja")
    for update in heard_in(RU, STEADY_CAPTIONS * 2):
        windows.apply(update)
    assert window.asking_spoken is None


def test_choosing_in_settings_while_asked_takes_the_question_away(
    windows: CaptionWindows,
) -> None:
    window = windows.windows["Discord.exe"]
    window.show()
    for update in heard_in(RU, STEADY_CAPTIONS):
        windows.apply(update)
    window.set_spoken_language("ja")  # the popover's list, Settings
    assert window.asking_spoken is None
    assert window.nudge is not None and not window.nudge.isVisible()


def test_the_question_hides_while_locked_and_comes_back(
    windows: CaptionWindows,
) -> None:
    window = windows.windows["Discord.exe"]
    window.show()
    for update in heard_in(RU, STEADY_CAPTIONS):
        windows.apply(update)
    nudge = window.nudge
    assert nudge is not None
    window.set_locked(True)  # clicks pass through: it couldn't be answered
    assert nudge.isHidden() and window.asking_spoken == "ru"
    window.set_locked(False)
    assert not nudge.isHidden()


def test_stored_declined_languages_read_back_and_odd_ones_left_out() -> None:
    stored = StoredWindows(declined_spoken={"Discord.exe": ("ru",)})
    read = StoredWindows.from_stored(stored.to_stored(), WindowChoices())
    assert read.declined_spoken == {"Discord.exe": ("ru",)}
    odd = {"declined_spoken": {"a": ["ru", "xx", 3], "b": "ru"}}
    assert StoredWindows.from_stored(odd, WindowChoices()).declined_spoken == {
        "a": ("ru",)
    }


def test_the_ui_lab_leaves_the_question_to_the_app_outside_its_runs() -> None:
    """The lab's windows don't ask while it runs; importing the lab (as
    tests do) must not keep the app's windows from asking - CI failed
    four tests above when it did."""
    from tools.ui_lab import lab

    from polyglotic_desktop.ui_next import caption_windows

    assert caption_windows.SteadyLanguage is SteadyLanguage
    with lab._windows_never_ask():
        assert caption_windows.SteadyLanguage is not SteadyLanguage
    assert caption_windows.SteadyLanguage is SteadyLanguage


def test_placing_the_question_never_restacks_the_window(
    windows: CaptionWindows,
) -> None:
    """With "Click any word" on the notice line and the question asked, the
    overlays placed again restack nothing: raising the question after the
    notice's raise swapped the two at every call, and each swap repainted
    the captions under both - on Linux a hovered word's repaint grew to the
    whole window (#574's CI)."""
    window = windows.windows["Discord.exe"]
    window.show()
    window.set_hint("Click any word")
    for update in heard_in(RU, STEADY_CAPTIONS):
        windows.apply(update)
    assert window.asking_spoken == "ru" and window.notice.isVisible()
    window._place_overlays()
    restacked: list[QObject] = []

    class Watch(QObject):
        def eventFilter(self, watched: QObject, event: QEvent) -> bool:
            if event.type() == QEvent.Type.ZOrderChange:
                restacked.append(watched)
            return False

    watch = Watch()
    assert window.nudge is not None
    for child in (window.nudge, window.notice):
        child.installEventFilter(watch)
    window._place_overlays()
    window._place_overlays()
    assert restacked == []


# -- it never covers the captions, and goes by itself (polyglotic-hq 350) -----------------


def test_an_unanswered_language_is_not_suggested_while_the_app_runs() -> None:
    steady = SteadyLanguage()
    steady.unanswered.add("ru")
    assert not any(steady.heard("ru", ("ru",)) for _ in range(STEADY_CAPTIONS * 3))
    said = [steady.heard("ja", ("ja",)) for _ in range(STEADY_CAPTIONS)]
    assert said[-1] == "ja"  # another language still is


def asked_in(windows: CaptionWindows) -> CaptionWindow:
    """The app's window, shown and full of captions, asking about Russian."""
    window = windows.windows["Discord.exe"]
    window.resize(560, 300)
    window.show()
    for update in heard_in(RU, STEADY_CAPTIONS + 10):
        windows.apply(update)
    assert window.asking_spoken == "ru"
    return window


def test_the_question_never_covers_a_caption(windows: CaptionWindows) -> None:
    """346's validation loop: the question sat over the top caption in
    every window picture, still there 30 minutes into a lecture. Now the
    captions start below it: no row drawn reaches up under it."""
    window = asked_in(windows)
    nudge = window.nudge
    assert nudge is not None and nudge.isVisible()
    window.canvas.grab()
    foot = nudge.geometry().bottom()
    assert window.canvas.placed, "nothing drawn"
    drawn_rows = 0
    for _, laid, rect in window.canvas.placed:
        for row in laid.rows:
            row_top = rect.top() + row.top
            row_foot = row_top + row.layout.boundingRect().height()
            if row_foot > window.canvas.clear_top:  # drawn
                drawn_rows += 1
                assert row_top > foot, (row_top, foot)
    assert drawn_rows, "every row hidden"
    nudge.no.click()  # answered: the rows come back up
    window.canvas.grab()
    assert window.canvas.clear_top < foot


def test_unanswered_it_goes_by_itself_and_is_not_asked_again_this_run(
    windows: CaptionWindows, store: Store
) -> None:
    window = asked_in(windows)
    nudge = window.nudge
    assert nudge is not None
    assert nudge._while.isActive() and nudge._while.interval() == SHOWN_MS
    nudge._while.timeout.emit()  # its minute is up
    assert window.asking_spoken is None and not nudge.isVisible()
    assert window.choices.spoken is None  # still Detect
    for update in heard_in(JA, 1, start=40) + heard_in(RU, 10, start=50):
        windows.apply(update)  # a new run of Russian
    assert window.asking_spoken is None  # not again while the app runs
    windows.save_now()
    assert (
        "declined_spoken" not in store.values or not store.values["declined_spoken"]
    )  # not a Not now: never stored
    again = CaptionWindows(store, MIC, areas)  # the app started again
    try:
        again.set_captioned([("Discord.exe", APP)])
        asked = again.windows["Discord.exe"]
        asked.show()
        for update in heard_in(RU, STEADY_CAPTIONS):
            again.apply(update)
        assert asked.asking_spoken == "ru"
    finally:
        again.close()


def test_its_while_counts_only_while_it_shows(windows: CaptionWindows) -> None:
    window = asked_in(windows)
    nudge = window.nudge
    assert nudge is not None
    window.set_locked(True)
    assert not nudge._while.isActive()  # hidden: never goes unseen
    window.set_locked(False)
    assert nudge._while.isActive() and window.asking_spoken == "ru"
