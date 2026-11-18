"""Each caption window's spoken language and its "Lines already in ..."
row (polyglotic-hq project 263; 248's IA.md 1.9 and Q6 A, the user,
2026-11-09): the popover's rows, what the windows tell the server, the
honest fallback for a server that takes one spoken language for every
window, and the choice kept between launches."""

from collections.abc import Iterator

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel, QListWidget, QListWidgetItem
from tests.ui_next.made_up import EN, ZH

from polyglotic_desktop.core.listening.captions import Language
from polyglotic_desktop.core.listening.sources import SourceId, SourceLabel
from polyglotic_desktop.ui.recorded_captions import APP, MIC
from polyglotic_desktop.ui_next.caption_window import CaptionWindow
from polyglotic_desktop.ui_next.caption_windows import CaptionWindows
from polyglotic_desktop.ui_next.settings_popover import SettingsPopover
from polyglotic_desktop.ui_next.views.caption_window import (
    STORED_KEY,
    StoredWindows,
    WindowChoices,
)
from polyglotic_desktop.ui_next.views.migration import stored_windows
from polyglotic_desktop.ui_next.views.placement import Rect

SECOND_APP = SourceId("app-2")
YUE = Language("yue")


def areas() -> list[Rect]:
    return [Rect(0, 0, 1920, 1040)]


class Store:
    def __init__(self, values: dict[str, object]) -> None:
        self.values = values

    def load(self) -> dict[str, object]:
        return dict(self.values)

    def save(self, values: object) -> None:
        assert isinstance(values, dict)
        self.values = dict(values)


@pytest.fixture
def window(qapp: QApplication) -> Iterator[CaptionWindow]:
    shown = CaptionWindow(
        "Discord.exe", APP, WindowChoices(), SourceLabel("Discord", "#4dd0e1"),
        mic=MIC, areas=areas,
    )  # fmt: skip
    shown.resize(960, 300)
    shown.show()
    yield shown
    shown.close()


@pytest.fixture
def windows(qapp: QApplication) -> Iterator[CaptionWindows]:
    found = CaptionWindows(Store({"targets": ["en"]}), MIC, areas)
    yield found
    found.close()


def opened(window: CaptionWindow) -> SettingsPopover:
    window.hovered = True
    window._show_band(True)
    window.toggle_settings()
    popover = window.popover
    assert popover is not None and popover.isVisible()
    return popover


def item(choices: QListWidget, code: str) -> QListWidgetItem:
    for index in range(choices.count()):
        found = choices.item(index)
        if found.data(Qt.ItemDataRole.UserRole) == code:
            return found
    raise AssertionError(f"no {code!r} in the list")


# -- the popover ------------------------------------------------------------------------


def test_spoken_language_is_chosen_in_the_window_and_says_detect_first(
    window: CaptionWindow,
) -> None:
    changed: list[bool] = []
    window.language_changed.connect(lambda: changed.append(True))
    popover = opened(window)
    assert popover.spoken.text().startswith("Detect · 30 languages")
    popover.spoken.click()  # the choices open inside it
    assert popover.spoken_choices.isVisible()
    shown = [
        label.text() for label in popover.findChildren(QLabel) if label.isVisible()
    ]
    assert not [
        text for text in shown if "less accurate" in text
    ]  # the user, 2026-11-13
    codes = popover.spoken_choices.codes_shown()
    assert codes[0] == "" and len(codes) == 31  # Detect, then all 30 (317)
    assert {"en", "zh", "yue", "ru", "ja", "sv"} <= set(codes)
    items = popover.spoken_choices.items
    assert items is not None
    popover.spoken_choices.chosen.emit("zh")
    assert window.choices.spoken == ZH and changed == [True]
    assert not popover.spoken_choices.isVisible()
    assert popover.spoken.text().startswith("Always Mandarin")
    popover.spoken_choices.chosen.emit(None)
    assert window.choices.spoken is None  # Detect


def test_lines_already_in_the_windows_language_only_where_they_can_be(
    window: CaptionWindow,
) -> None:
    """Shown while a line can already be in the window's language: its app
    detected, or speaking that language (IA.md 1.9)."""
    popover = opened(window)
    second = popover.rows["second"]
    assert second.isVisible()  # Detect, into English
    # named by the window's language (465)
    assert popover.second_title.text() == "When they already speak English"
    assert popover.second.text().startswith("Leave as they are")
    window.set_spoken_language("zh")  # Mandarin into English: never already in it
    assert not second.isVisible()
    window.set_spoken_language("en")
    assert second.isVisible()
    window.set_language("")  # Original only: nothing is translated
    assert not second.isVisible()


def test_a_second_language_is_asked_for_by_language_and_shown_once_set(
    window: CaptionWindow,
) -> None:
    asked: list[tuple[str, str]] = []
    window.second_wanted.connect(lambda target, second: asked.append((target, second)))
    popover = opened(window)
    popover.second.click()
    choices = popover.second_choices
    assert choices.isVisible()
    assert choices.item(0).text() == "Leave as they are"
    shown = [
        choices.item(i).data(Qt.ItemDataRole.UserRole) for i in range(choices.count())
    ]
    assert "en" not in shown  # not the window's own
    popover._second_chosen(item(choices, "zh"))
    assert asked == [("en", "zh")]
    window.set_second_languages({EN: ZH})  # the app kept it: every window follows
    # the picker names the language, whatever its script (polyglotic-hq 433)
    assert popover.second.text().startswith("Also translate into Chinese")
    assert "Simplified" not in popover.second.text()
    window.set_second("zh")  # already so: not asked again
    window.set_second("")
    assert asked == [("en", "zh"), ("en", "")]


def test_the_choices_shut_at_each_open(window: CaptionWindow) -> None:
    popover = opened(window)
    popover.spoken.click()
    popover.second.click()
    window.toggle_settings()  # closed
    window.toggle_settings()  # and open again
    assert not popover.spoken_choices.isVisible()
    assert not popover.second_choices.isVisible()


# -- the windows: what the server is told, and the honest fallback -----------------------


def test_each_sources_spoken_language_and_the_mics_from_the_windows_showing_it(
    windows: CaptionWindows,
) -> None:
    sent: list[bool] = []
    windows.languages_changed.connect(lambda: sent.append(True))
    windows.set_captioned([("a", APP), ("b", SECOND_APP)])
    assert windows.spoken_languages() == {APP: None, SECOND_APP: None}
    windows.windows["a"].set_spoken_language("zh")
    assert sent[-1] and windows.spoken_languages()[APP] == ZH
    windows.windows["a"].set_show_mic(True)
    assert windows.spoken_languages()[MIC] == ZH  # my speech goes with the call
    windows.windows["b"].set_show_mic(True)  # and with a window detecting
    assert windows.spoken_languages()[MIC] is None
    windows.set_show_mic_everywhere(False)
    assert MIC not in windows.spoken_languages()


def test_an_older_server_hears_every_window_as_detect_and_a_window_says_so(
    windows: CaptionWindows,
) -> None:
    windows.set_captioned([("a", APP), ("b", SECOND_APP)])
    a, b = windows.windows["a"], windows.windows["b"]
    a.set_spoken_language("zh")
    assert not a.spoken_fallback  # not known yet: nothing said
    windows.set_spoken_per_source(False)  # a server from before 2026-11-09
    assert a.spoken_fallback and not b.spoken_fallback  # b is Detect anyway
    popover = opened(a)
    assert popover.spoken_fallback.isVisible()
    assert popover.spoken.text().startswith("Always Mandarin")  # the choice is kept
    b.set_spoken_language("zh")  # they agree: Mandarin for both
    assert not a.spoken_fallback and not popover.spoken_fallback.isVisible()
    b.set_spoken_language("en")
    assert a.spoken_fallback and b.spoken_fallback
    windows.set_spoken_per_source(True)  # a server that takes one per window
    assert not a.spoken_fallback and not b.spoken_fallback


def test_a_window_opened_later_is_told_too(windows: CaptionWindows) -> None:
    windows.set_captioned([("a", APP)])
    windows.windows["a"].set_spoken_language("yue")
    windows.set_spoken_per_source(False)
    windows.set_captioned([("a", APP), ("b", SECOND_APP)])
    windows.windows["b"].set_spoken_language("en")
    assert windows.windows["a"].spoken_fallback
    windows.set_captioned([("a", APP)])  # b closed: a alone names Cantonese
    assert not windows.windows["a"].spoken_fallback


def test_homes_spoken_language_sets_every_windows(windows: CaptionWindows) -> None:
    windows.set_captioned([("a", APP), ("b", SECOND_APP)])
    windows.windows["a"].set_spoken_language("en")
    windows.set_spoken_everywhere("yue")
    assert set(windows.spoken_languages().values()) == {YUE}


# -- kept between launches ---------------------------------------------------------------


def test_a_windows_spoken_language_is_saved_and_read_back(
    windows: CaptionWindows, qapp: QApplication
) -> None:
    windows.set_captioned([("a", APP), ("b", SECOND_APP)])
    windows.windows["a"].set_spoken_language("zh")
    windows.save_now()
    store = windows._store
    assert isinstance(store, Store)
    saved = store.values[STORED_KEY]
    assert isinstance(saved, dict)
    assert saved["windows"]["a"]["spoken_language"] == "zh"
    assert saved["windows"]["b"]["spoken_language"] == "detect"
    again = CaptionWindows(store, MIC, areas)
    again.set_captioned([("a", APP), ("b", SECOND_APP)])
    assert again.spoken_languages() == {APP: ZH, SECOND_APP: None}
    again.close()


def test_a_new_window_starts_at_detect_whatever_the_last_one_named() -> None:
    """A new app may speak anything; its translation language is copied."""
    stored = StoredWindows(last=WindowChoices("ja", spoken_language="zh"))
    new = stored.for_new(1)
    assert new.translate_into == "ja" and new.spoken is None


@pytest.mark.parametrize(
    ("stored", "read"),
    [
        ({"spoken_language": "yue"}, YUE),
        ({"spoken_language": "ru"}, Language("ru")),  # any the model hears (317)
        ({"spoken_language": "detect"}, None),
        ({"spoken_language": "uk"}, ZH),  # a caption language it can't be told
        ({"spoken_language": "Klingon"}, ZH),  # not offered: the base's
        ({"spoken_language": None}, ZH),
        ({}, ZH),  # stored before windows had their own: the base's
    ],
)
def test_a_stored_spoken_language_is_one_offered_or_the_bases(
    stored: dict[str, object], read: Language | None
) -> None:
    base = WindowChoices(spoken_language="zh")
    assert WindowChoices.from_stored(stored, base).spoken == read


def test_todays_one_spoken_language_moves_to_every_window() -> None:
    """Home's Spoken language was for every window: each window starts
    with it - and a window saved before windows had their own takes it
    too."""
    today = {"apps": ["Discord", "VLC"], "spoken_language": "zh"}
    moved = stored_windows(today)
    assert {c.spoken for c in moved.by_key.values()} == {ZH}
    saved = {**today, STORED_KEY: {"windows": {"Discord": {"translate_into": "en"}}}}
    assert stored_windows(saved).by_key["Discord"].spoken == ZH
    assert stored_windows({"apps": ["Discord"]}).by_key["Discord"].spoken is None
