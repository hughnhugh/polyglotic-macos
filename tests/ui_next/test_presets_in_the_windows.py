"""Presets in the caption windows (polyglotic-hq 556, decision 0264): the
bar's preset chip, its dropdown and the Word links button (731); Video's
subtitles along the bottom of the screen, sized from the screen, and back
where the learner put it; the original only in every window, each
window's language kept and given back."""

from collections.abc import Iterator
from dataclasses import replace

import pytest
from PySide6.QtWidgets import QApplication, QLabel, QPushButton

from polyglotic_desktop.core.listening.timing import CaptionMode
from polyglotic_desktop.ui.recorded_captions import APP, MIC
from polyglotic_desktop.ui_next import preset_popover, style
from polyglotic_desktop.ui_next.caption_window import CaptionWindow
from polyglotic_desktop.ui_next.caption_windows import (
    CaptionWindows,
    subtitle_text_size,
)
from polyglotic_desktop.ui_next.views.caption_window import (
    ORIGINAL_ONLY,
    STORED_KEY,
    WindowChoices,
)
from polyglotic_desktop.ui_next.views.placement import Rect, subtitle_slot
from polyglotic_desktop.ui_next.views.preset_menu import PresetItem, PresetMenu, Show

FULL_HD = Rect(0, 0, 1920, 1040)
QHD = Rect(0, 0, 2560, 1400)
MENU = PresetMenu(
    (
        PresetItem("everyday", "Everyday"),
        PresetItem("conversation", "Conversation"),
        PresetItem("video", "Video, film & TV"),
        PresetItem("learning", "Learning"),
    ),
    "video",
    Show.BOTH,
    links=False,
    quiet=False,
    readings=False,
)


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
    return Store({"targets": ["en"]})


@pytest.fixture
def windows(qapp: QApplication, store: Store) -> Iterator[CaptionWindows]:
    found = CaptionWindows(store, MIC, lambda: [FULL_HD])
    yield found
    found.close()


def opened(windows: CaptionWindows, qapp: QApplication) -> CaptionWindow:
    windows.set_captioned([("Video Player.exe", APP)])
    window = windows.windows["Video Player.exe"]
    window.show()
    qapp.processEvents()
    return window


def test_the_bar_has_the_preset_chip_and_word_links_button(
    windows: CaptionWindows, qapp: QApplication
) -> None:
    window = opened(windows, qapp)
    windows.set_presets(MENU)
    window._show_band(True)
    assert window.buttons["links"].isVisible()
    for gone in ("quiet", "fill", "aligned"):
        assert gone not in window.buttons
    assert window.preset_chip.text() == "Video, film && TV ▾"
    assert window.preset_chip.accessibleName() == "Preset: Video, film & TV"  # 593


def test_the_dropdown_picks_shows_adds_and_customises(
    windows: CaptionWindows, qapp: QApplication
) -> None:
    window = opened(windows, qapp)
    windows.set_presets(MENU)
    asked: list[object] = []
    windows.preset_wanted.connect(asked.append)
    windows.lines_wanted.connect(asked.append)
    windows.customise_wanted.connect(lambda: asked.append("customise"))
    window.toggle_presets()
    dropdown = window.presets
    assert dropdown is not None and dropdown.isVisible()
    assert window.preset_chip.text().endswith("▴")

    def button(name: str) -> QPushButton:
        found = dropdown.findChild(QPushButton, name)
        assert found is not None, name
        return found

    assert button("presets.preset.video").isChecked()
    for extra in ("links", "quiet", "readings"):
        assert not button(f"presets.add.{extra}").isChecked()
    button("presets.show.original").click()
    assert dropdown.findChild(QPushButton, "presets.add.my_speech") is None
    button("presets.add.quiet").click()
    assert dropdown.isVisible()  # an option keeps it open
    button("presets.preset.conversation").click()
    assert not dropdown.isVisible()  # a preset picked closes it
    window.toggle_presets()
    button("presets.customise").click()
    assert asked == ["original", "conversation", "customise"]


def test_word_links_cant_be_added_with_the_translation_only(
    windows: CaptionWindows, qapp: QApplication
) -> None:
    window = opened(windows, qapp)
    windows.set_presets(PresetMenu(MENU.items, "video", Show.TRANSLATION))
    window.toggle_presets()
    assert window.presets is not None
    links = window.presets.findChild(QPushButton, "presets.add.links")
    assert links is not None and not links.isEnabled()


@pytest.mark.parametrize("timing", [CaptionMode.INSTANT, CaptionMode.SCROLLING])
def test_video_line_count_in_the_menu_and_the_minimum_height(
    windows: CaptionWindows, qapp: QApplication, timing: CaptionMode
) -> None:
    window = opened(windows, qapp)
    windows.set_presets(MENU)
    windows.set_timing(timing)
    window.toggle_presets()
    assert window.presets is not None
    dropdown = window.presets
    assert dropdown.findChild(QPushButton, "presets.video_lines.2") is None
    windows.set_subtitles((0.02, 0.3))
    heights = []
    windows.video_lines_wanted.connect(
        lambda count: windows.set_presets(replace(MENU, video_lines_shown=count))
    )
    for count in (1, 2, 3):
        button = dropdown.findChild(QPushButton, f"presets.video_lines.{count}")
        assert button is not None
        button.click()
        assert window.preset_menu.video_lines_shown == count
        minimum = window._minimum().height
        assert window.height() == minimum
        heights.append(minimum)
    assert heights[0] < heights[1] < heights[2]


@pytest.mark.parametrize("area", [FULL_HD, QHD])
def test_video_puts_every_window_along_the_bottom_sized_from_the_screen(
    qapp: QApplication, store: Store, area: Rect
) -> None:
    windows = CaptionWindows(store, MIC, lambda: [area])
    try:
        window = opened(windows, qapp)
        own = window.geometry()
        windows.set_subtitles((0.045, 0.8))
        qapp.processEvents()
        size = window.view.text_size
        # 4.5 % of the screen's height: about 47 px at 1080p, 63 at 1440p
        assert (
            abs(window.text_px() * size - 0.045 * area.height) < 0.6 * window.text_px()
        )
        place = window.geometry()
        expected = subtitle_slot(area, 0.8, window.subtitle_height(size))
        assert (place.x(), place.y(), place.width()) == (
            expected.x,
            expected.y,
            expected.width,
        )
        assert place.width() == min(1600, round(area.width * 0.8))
        assert place.bottom() < area.bottom  # over a player's controls
        windows.set_subtitles(None)  # another preset: back where it was
        qapp.processEvents()
        assert window.geometry() == own
        assert window.view.text_size == WindowChoices().text_size
    finally:
        windows.close()


def test_the_learners_own_place_is_kept_while_its_a_subtitle(
    windows: CaptionWindows, qapp: QApplication, store: Store
) -> None:
    window = opened(windows, qapp)
    window.take_place(window.choices.preset, Rect(100, 100, 700, 300), 1.2)
    windows._changed(window)  # moved and sized by the learner
    windows.set_subtitles((0.045, 0.8))
    changed: list[tuple[float, float]] = []
    windows.subtitles_changed.connect(lambda s, w: changed.append((s, w)))
    window.step_text(1)  # A+ while it's a subtitle: Video's size, not its own
    windows.save_now()
    saved = store.values[STORED_KEY]
    assert isinstance(saved, dict)
    own = saved["windows"]["Video Player.exe"]
    assert own["geometry"] == [100, 100, 700, 300] and own["text_size"] == 1.2
    (share, width) = changed[-1]
    assert share > 0.045 and width == 0.8


def test_subtitle_text_stays_within_a_windows_sizes() -> None:
    assert subtitle_text_size(0.5, FULL_HD, 21.0) == 4.0
    assert subtitle_text_size(0.001, FULL_HD, 21.0) == 0.6


def test_original_only_keeps_each_windows_language_and_gives_it_back(
    windows: CaptionWindows, qapp: QApplication, store: Store
) -> None:
    window = opened(windows, qapp)
    window.set_language("ja")
    windows.set_original_only(True)
    assert window.choices.translate_into == ORIGINAL_ONLY
    assert windows.targets()[APP] == ()  # the server isn't asked to translate
    windows.save_now()
    saved = store.values[STORED_KEY]
    assert isinstance(saved, dict) and saved["kept_languages"] == {
        "Video Player.exe": "ja"
    }
    windows.set_original_only(False)
    assert window.choices.translate_into == "ja"


def test_a_window_original_only_by_its_own_choice_stays_so(
    windows: CaptionWindows, qapp: QApplication
) -> None:
    window = opened(windows, qapp)
    window.set_language(ORIGINAL_ONLY)  # the learner's own, before the preset
    windows.set_original_only(True)
    windows.set_original_only(False)
    assert window.choices.translate_into == ORIGINAL_ONLY


def test_a_language_picked_while_the_original_only_shows_asks_for_translations(
    windows: CaptionWindows, qapp: QApplication
) -> None:
    window = opened(windows, qapp)
    windows.set_original_only(True)
    asked: list[bool] = []
    windows.translations_wanted.connect(lambda: asked.append(True))
    window.set_language("fr")
    assert asked == [True]


def test_a_long_line_under_a_preset_wraps_whole(
    windows: CaptionWindows, qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A long language's line under a preset runs to a second row, never
    past the dropdown's edge (polyglotic-hq 572: Everyday's was cut by
    17 px in French and Russian)."""
    long = "Toutes les aides activées : la configuration propre à l'application"
    monkeypatch.setattr(preset_popover, "preset_note", lambda key: long)
    window = opened(windows, qapp)
    windows.set_presets(MENU)
    window.toggle_presets()
    dropdown = window.presets
    assert dropdown is not None
    qapp.processEvents()
    row = dropdown.findChild(QPushButton, "presets.preset.everyday")
    assert row is not None
    (note,) = [line for line in row.findChildren(QLabel) if line.text() == long]
    assert note.wordWrap()
    assert note.height() >= note.heightForWidth(note.width())  # every row of it
    assert note.geometry().right() <= row.width()
    assert dropdown.width() == style.px(preset_popover.WIDTH)  # not widened for it


def test_video_selects_its_own_renderer(
    windows: CaptionWindows, qapp: QApplication
) -> None:
    window = opened(windows, qapp)
    assert not window.video_enabled
    windows.set_subtitles((0.045, 0.8))
    assert window.video_enabled
    assert window.deck is None
    windows.set_subtitles(None)
    assert not window.video_enabled
