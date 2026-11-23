"""The first caption window sets itself up, and a language chip on every
window's bar (polyglotic-hq 465; 449's design 3A, DECISIONS.md #195 item
5). The user, 2026-11-17: "make detect, translation selection and
secondary language selection more noticeable / easier to reach. Maybe
introduce a set up screen on first caption window opening which sets it as
a default, existing behaviour remains where last behaviour remains as
default on open."
"""

from collections.abc import Iterator
from dataclasses import replace

import pytest
from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QAbstractButton, QApplication
from tests.ui_next.made_up import SEPARATE, finished_updates

from polyglotic_desktop.core.listening.sources import SourceId, SourceLabel
from polyglotic_desktop.ui.recorded_captions import APP, MIC
from polyglotic_desktop.ui_next.caption_set_up import MARGIN, beside_if_short, placed_in
from polyglotic_desktop.ui_next.caption_window import CaptionWindow, chip_text
from polyglotic_desktop.ui_next.caption_windows import CaptionWindows
from polyglotic_desktop.ui_next.settings_popover import LANGUAGE_ROWS
from polyglotic_desktop.ui_next.views.caption_window import (
    STORED_KEY,
    StoredWindows,
    WindowChoices,
)
from polyglotic_desktop.ui_next.views.migration import stored_windows
from polyglotic_desktop.ui_next.views.placement import CORNER_ZONE, Rect

SECOND_APP = SourceId("app-2")
THIRD_APP = SourceId("app-3")


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
def store() -> Store:
    return Store({"targets": ["en"]})  # a new PC: no windows yet


@pytest.fixture
def windows(qapp: QApplication, store: Store) -> Iterator[CaptionWindows]:
    found = CaptionWindows(store, MIC, areas, offer_set_up=True)
    found.stored.joined = SEPARATE  # on their own: windows start joined (554)
    yield found
    found.close()


def first(windows: CaptionWindows, qapp: QApplication) -> CaptionWindow:
    windows.set_captioned([("Discord.exe", APP)])
    window = windows.windows["Discord.exe"]
    window.show()
    qapp.processEvents()  # the set-up goes over it once it's shown
    return window


# -- what new windows start with (plain Python) -------------------------------------


def test_a_new_window_hears_detect_unless_new_windows_start_like_the_last() -> None:
    stored = StoredWindows(last=WindowChoices("ja", 1.2, spoken_language="zh"))
    assert stored.for_new(1).spoken_language is None  # as before: Detect
    assert stored.for_new(1).translate_into == "ja"  # the last one's language
    stored.start_like_this = True
    new = stored.for_new(1)
    assert (new.spoken_language, new.translate_into, new.text_size) == ("zh", "ja", 1.2)


def test_set_up_and_start_like_this_are_kept() -> None:
    stored = StoredWindows(set_up=True, start_like_this=True)
    again = StoredWindows.from_stored(stored.to_stored(), WindowChoices())
    assert again.set_up and again.start_like_this
    assert not StoredWindows.from_stored({}, WindowChoices()).start_like_this


def test_a_learner_with_windows_from_before_is_never_asked() -> None:
    """0.1.7's windows have no "set_up": they're set up already. Since,
    windows kept without Use as my default still ask (478)."""
    before = {"windows": {"Discord.exe": WindowChoices().to_stored()}}
    assert StoredWindows.from_stored(before, WindowChoices()).set_up
    since = {**before, "set_up": False}
    assert not StoredWindows.from_stored(since, WindowChoices()).set_up
    assert not StoredWindows.from_stored({}, WindowChoices()).set_up
    # and today's settings moved over, with apps picked: set up too
    assert stored_windows({"apps": ["Discord.exe"]}).set_up
    assert not stored_windows({"targets": ["en"]}).set_up


# -- the set-up --------------------------------------------------------------------


def test_the_first_window_asks_its_languages_and_only_it(
    windows: CaptionWindows, qapp: QApplication
) -> None:
    window = first(windows, qapp)
    set_up = window.set_up
    assert set_up is not None and set_up.isVisible()
    assert set_up.spoken.text().startswith("Detect · 30 languages")  # filled in
    assert set_up.language.text().startswith("English")
    assert set_up.second_title.text() == "When they already speak English"
    assert set_up.second.text().startswith("Leave as they are")
    windows.set_captioned([("Discord.exe", APP), ("Video", SECOND_APP)])
    assert windows.windows["Video"].set_up is None  # one window asks


def test_used_as_my_default_its_answers_are_how_new_windows_start(
    windows: CaptionWindows, store: Store, qapp: QApplication
) -> None:
    window = first(windows, qapp)
    set_up = window.set_up
    assert set_up is not None
    assert not set_up.as_default.isChecked()  # the learner's to choose (478)
    set_up._spoken_chosen("zh")  # They speak: Mandarin
    assert window.choices.spoken_language == "zh"  # at once, as in the popover
    set_up.as_default.trigger()  # Use as my default (478)
    set_up.start.click()  # Start captions
    assert window.set_up is None and not set_up.isVisible()
    assert windows.stored.set_up and windows.stored.start_like_this
    windows.set_captioned([("Discord.exe", APP), ("Video", SECOND_APP)])
    assert windows.windows["Video"].choices.spoken_language == "zh"
    windows.save_now()
    own = store.values[STORED_KEY]
    assert isinstance(own, dict) and own["set_up"] is True
    again = CaptionWindows(store, MIC, areas, offer_set_up=True)
    again.set_captioned([("Game", THIRD_APP)])
    assert again.windows["Game"].set_up is None  # never asked again
    again.close()


def test_without_use_as_my_default_every_window_that_opens_asks_again(
    windows: CaptionWindows, store: Store, qapp: QApplication
) -> None:
    """The user, 2026-11-18: "need a caption open quick configuration
    screen ... (selecting as default on start up gets rid of the screen for
    future opens)" (478)."""
    window = first(windows, qapp)
    set_up = window.set_up
    assert set_up is not None
    set_up._spoken_chosen("zh")
    set_up.start.click()  # Start captions, not as my default
    assert window.set_up is None and not windows.stored.set_up
    assert not windows.stored.start_like_this  # the answers were this window's
    windows.set_captioned([("Discord.exe", APP), ("Video", SECOND_APP)])
    video = windows.windows["Video"]
    assert video.set_up is not None  # the next window that opens asks
    assert video.choices.spoken_language is None  # They speak: Detect
    windows.save_now()
    own = store.values[STORED_KEY]
    assert isinstance(own, dict) and own["set_up"] is False
    again = CaptionWindows(store, MIC, areas, offer_set_up=True)
    again.set_captioned([("Discord.exe", APP)])  # the app started again
    assert again.windows["Discord.exe"].set_up is not None  # asked again
    again.close()


def test_a_windows_chip_brings_it_back(
    windows: CaptionWindows, qapp: QApplication
) -> None:
    window = first(windows, qapp)
    assert window.controls["ask_set_up"].isChecked()  # asking: on
    set_up = window.set_up
    assert set_up is not None
    set_up.as_default.trigger()
    window.finish_set_up()
    assert windows.stored.set_up
    assert not window.controls["ask_set_up"].isChecked()
    window.controls["ask_set_up"].trigger()  # the chip's "Ask when a window opens"
    assert not windows.stored.set_up
    windows.set_captioned([("Discord.exe", APP), ("Video", SECOND_APP)])
    assert windows.windows["Video"].set_up is not None


def test_a_caption_starts_the_captions_it_never_blocks(
    windows: CaptionWindows, qapp: QApplication
) -> None:
    window = first(windows, qapp)
    set_up = window.set_up
    assert set_up is not None
    set_up.language.click()  # the learner is at it: a list open
    updates = finished_updates(2, APP)
    windows.apply(updates[0])
    assert window.view.lines  # the caption is there, under it
    assert window.set_up is set_up  # not taken from under the learner
    set_up.language.click()  # the list shut
    window.pointer = lambda: QPoint(-100, -100)  # the mouse off it
    windows.apply(updates[1])
    assert window.set_up is None and not set_up.isVisible()
    assert not windows.stored.set_up  # not my default: the next window asks (478)


def test_it_waits_while_locked_or_hidden_and_follows_the_window(
    windows: CaptionWindows, qapp: QApplication
) -> None:
    window = first(windows, qapp)
    set_up = window.set_up
    assert set_up is not None
    window.set_locked(True)  # clicks pass through a locked window
    assert not set_up.isVisible() and window.set_up is set_up
    window.set_locked(False)
    assert set_up.isVisible()
    inside = window.frameGeometry()
    assert inside.left() <= set_up.x() and set_up.geometry().right() <= inside.right()
    window.move(window.x() - 200, window.y() - 300)
    qapp.processEvents()
    assert inside.left() - 200 <= set_up.x() <= window.frameGeometry().right()
    top = window.mapToGlobal(QPoint(0, 0)).y()
    area = areas()[0]
    expected = beside_if_short(
        top, window.height(), window.band_bottom(), set_up.height(), area
    )
    assert set_up.y() == placed_in(Rect(0, expected, 1, set_up.height()), area)[1]
    window.hide()
    assert not set_up.isVisible() and window.set_up is set_up  # asked when shown


def test_the_set_up_stays_on_the_work_area() -> None:
    area = Rect(0, 0, 1920, 1040)
    assert placed_in(Rect(100, 900, 400, 300), area) == (100, 740)
    assert placed_in(Rect(1700, 10, 400, 300), area) == (1520, 10)


def test_not_offered_no_set_up(qapp: QApplication) -> None:
    """The UI lab's and the tests' windows: only `main` offers it."""
    found = CaptionWindows(Store({}), MIC, areas)
    found.set_captioned([("Discord.exe", APP)])
    assert found.windows["Discord.exe"].set_up is None
    found.close()


# -- in a joined window (polyglotic-hq 554) ------------------------------------------


def test_a_set_up_too_tall_for_its_window_goes_beside_it() -> None:
    """Under the band while it fits clear of the window's foot and corners;
    else above the window, else below it - never over its resize edges
    (polyglotic-hq 586: a 372 px set-up hung past a 300 px window's foot)."""
    area = Rect(0, 0, 2560, 1392)
    assert beside_if_short(700, 600, 28, 372, area) == 728  # fits: under the band
    tall = 600 - 28 - CORNER_ZONE  # the most that fits
    assert beside_if_short(700, 600, 28, tall, area) == 728
    assert beside_if_short(700, 600, 28, tall + 1, area) == 700 - MARGIN - tall - 1
    assert beside_if_short(1002, 300, 28, 372, area) == 1002 - MARGIN - 372  # above
    assert beside_if_short(20, 300, 28, 372, area) == 20 + 300 + MARGIN  # below
    assert beside_if_short(20, 300, 28, 1300, area) == 48  # room nowhere: as before


def test_the_set_up_never_covers_a_short_windows_edges(
    windows: CaptionWindows, qapp: QApplication
) -> None:
    """The first window at its usual size, at the screen's foot: its set-up
    is above it, clear of the window, so every edge still resizes."""
    window = first(windows, qapp)
    window.resize(window.width(), 300)
    window.move(window.x(), areas()[0].bottom - 300)
    qapp.processEvents()
    set_up = window.set_up
    assert set_up is not None and set_up.isVisible()
    assert set_up.height() > 300 - window.band_bottom() - CORNER_ZONE  # too tall
    assert not set_up.geometry().intersects(window.geometry())
    assert set_up.geometry().bottom() < window.y()
    window.move(window.x(), 100)
    window.resize(window.width(), set_up.height() + 200)  # room for it: inside
    qapp.processEvents()
    assert set_up.y() == window.y() + window.band_bottom()
    foot = window.y() + window.height() - CORNER_ZONE
    assert set_up.y() + set_up.height() <= foot


@pytest.fixture
def joining(qapp: QApplication, store: Store) -> Iterator[CaptionWindows]:
    """A new PC's windows as they start: joined once there are two (554)."""
    found = CaptionWindows(store, MIC, areas, offer_set_up=True)
    yield found
    found.close()


def inside(column: CaptionWindow, qapp: QApplication) -> bool:
    """Whether its set-up shows with it: across it, under its strip - or,
    the window too short for it, just above or below it (586) - moved as
    far as keeps it on the work area (`placed_in`)."""
    qapp.processEvents()
    set_up = column.set_up
    assert set_up is not None
    corner = column.mapToGlobal(QPoint(0, 0))
    area = areas()[0]
    y = beside_if_short(
        corner.y(), column.height(), column.band_bottom(), set_up.height(), area
    )
    return (
        set_up.isVisible()
        and corner.x() <= set_up.x()
        and set_up.x() + set_up.width() <= corner.x() + column.width()
        and set_up.y() == placed_in(Rect(0, y, 1, set_up.height()), area)[1]
    )


def test_a_second_app_joining_doesnt_take_the_first_windows_question_away(
    joining: CaptionWindows, qapp: QApplication
) -> None:
    """Bug (polyglotic-hq 554): joining ended a window's set-up - "the
    learner is past it" - and windows start joined now, so a second app's
    window opening while the first asked took its question away for good.
    It stays, inside the first window's column, and still answers."""
    window = first(joining, qapp)
    set_up = window.set_up
    assert set_up is not None and set_up.isVisible()
    joining.set_captioned([("Discord.exe", APP), ("Video", SECOND_APP)])
    joined = joining.joined_window
    assert joined is not None and window.host is joined  # joined
    assert window.set_up is set_up and inside(window, qapp)
    assert joining.windows["Video"].set_up is None  # one window asks at a time
    joined.move(joined.x() - 120, joined.y() - 200)  # it goes with the window
    assert inside(window, qapp)
    set_up._spoken_chosen("zh")
    assert window.choices.spoken_language == "zh"  # answered in its column
    set_up.start.click()
    assert window.set_up is None and not set_up.isVisible()


def test_windows_joining_stay_where_the_first_window_was(
    joining: CaptionWindows, qapp: QApplication
) -> None:
    """polyglotic-hq 572 (preview 2): with presets (desktop #976) a second
    app's window joining placed the joined window again from the first
    window's geometry - by then its place inside the joined window, (0, 0) -
    so the joined window went to the screen's top left."""
    window = first(joining, qapp)
    at = window.geometry()
    joining.set_captioned([("Discord.exe", APP), ("Video", SECOND_APP)])
    joined = joining.joined_window
    assert joined is not None and window.host is joined
    qapp.processEvents()
    assert joined.y() == at.y() and joined.height() == at.height()


def test_a_window_that_opens_as_a_column_asks_its_question(
    joining: CaptionWindows, qapp: QApplication
) -> None:
    """Without Use as my default every window that opens asks (478) - a
    joined window's new column too, where it never showed (554)."""
    window = first(joining, qapp)
    assert window.set_up is not None
    window.set_up.start.click()  # Start captions, not as my default
    joining.set_captioned([("Discord.exe", APP), ("Video", SECOND_APP)])
    video = joining.windows["Video"]
    assert video.host is joining.joined_window  # a column
    assert video.set_up is not None and inside(video, qapp)
    joining.separate()  # on its own again: still asked, at its own place
    qapp.processEvents()
    assert video.set_up is not None and inside(video, qapp)


# -- the language chip --------------------------------------------------------------


def test_the_chip_says_what_they_speak_and_what_its_translated_into(
    windows: CaptionWindows, qapp: QApplication
) -> None:
    assert chip_text(None, None) == "Detect → Original only  ▾"
    window = first(windows, qapp)
    window.finish_set_up()
    window.resize(960, 300)
    assert window.chip.text() == "Detect → English  ▾"
    window.set_spoken_language("zh")
    assert window.chip.text() == "Mandarin → English  ▾"
    window.set_language("ja")
    assert window.chip.text() == "Mandarin → Japanese  ▾"


def test_the_chip_opens_the_three_rows_and_start_like_this(
    windows: CaptionWindows, qapp: QApplication
) -> None:
    window = first(windows, qapp)
    assert window.set_up is not None
    window.set_up.as_default.trigger()  # Use as my default (478)
    window.finish_set_up()  # Start new windows like this: on
    window.resize(960, 300)
    window.hovered = True
    window._show_band(True)
    window.chip.click()
    languages = window.languages
    assert languages is not None and languages.isVisible()
    assert tuple(languages.rows) == LANGUAGE_ROWS
    assert window.chip.text().endswith("▴")
    switch = languages.rows["start_like_this"]
    assert isinstance(switch, QAbstractButton)
    assert window.controls["start_like_this"].isChecked()
    switch.click()  # off: a new window hears Detect again
    assert not windows.stored.start_like_this
    languages._spoken_chosen("ko")
    windows.set_captioned([("Discord.exe", APP), ("Video", SECOND_APP)])
    assert windows.windows["Video"].choices.spoken_language is None
    assert not windows.windows["Video"].controls["start_like_this"].isChecked()
    window.chip.click()  # closed again
    assert not languages.isVisible()
    window.toggle_settings()  # the settings popover closes the chip's
    window.chip.click()
    assert window.popover is not None and not window.popover.isVisible()


def test_the_set_up_and_the_chip_are_no_part_of_a_window_of_before(
    qapp: QApplication,
) -> None:
    """A window made outside the windows (the lab): no set-up, a chip."""
    window = CaptionWindow(
        "lab", APP, replace(WindowChoices(), translate_into="fr"),
        SourceLabel("Discord", "#4dd0e1"), mic=MIC, areas=areas,
    )  # fmt: skip
    assert window.set_up is None
    assert window.chip.text() == "Detect → French  ▾"
    window.close()
