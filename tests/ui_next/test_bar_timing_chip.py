"""A caption window's bar: the timing chip after the preset chip, offering
only the timings the preset's use allows; the gear menu with per-window opacity;
and the microphone status light (polyglotic-hq 593; 585's sections 3 and
6; the user, 2026-11-21: "So language detection, preset, timing")."""

import sys
from collections.abc import Iterator

import pytest
from PySide6.QtCore import QRect, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QWidget
from tests.ui_next.test_caption_window import window_of

from polyglotic_desktop.core.listening.playout import ReadingPath
from polyglotic_desktop.core.listening.sources import SourceLabel
from polyglotic_desktop.core.listening.timing import CaptionMode
from polyglotic_desktop.ui.recorded_captions import MIC
from polyglotic_desktop.ui_next import style
from polyglotic_desktop.ui_next.caption_window import CaptionWindow, StripLabels
from polyglotic_desktop.ui_next.settings_popover import (
    BAR_ROWS,
    COLUMN_ROWS,
    KEYBOARD_BAR_ROWS,
    ROWS,
)
from polyglotic_desktop.ui_next.views.preset_menu import PresetItem, PresetMenu, Show

ITEMS = (
    PresetItem("everyday", "Everyday"),
    PresetItem("conversation", "Conversation"),
    PresetItem("video", "Video, film & TV"),
    PresetItem("learning", "Learning"),
)


@pytest.fixture
def window(qapp: QApplication) -> Iterator[CaptionWindow]:
    style.use_app_text_size("normal")
    shown = window_of(qapp, captions=0)
    shown.resize(1000, 300)
    shown.hovered = True
    shown._show_band(True)
    qapp.processEvents()
    yield shown
    shown.close()
    shown.deleteLater()


def offered_rows(window: CaptionWindow) -> list[str]:
    timings = window.timings
    assert timings is not None and timings.isVisible()
    return [
        row.objectName().split(".", 1)[1]
        for row in timings.body.findChildren(QPushButton)
        if row.objectName().startswith("timings.")
    ]


def on_window(window: CaptionWindow, widget: QWidget) -> QRect:
    return QRect(widget.mapTo(window, widget.rect().topLeft()), widget.size())


# -- the timing chip --------------------------------------------------------------------


def test_icon_chips_stay_together_at_intermediate_icon_width(
    window: CaptionWindow,
) -> None:
    window.set_presets(PresetMenu(ITEMS, "video"))
    for width in range(window.strip_least(), window.width()):
        window.resize(width, window.height())
        if window.strip_labels is not StripLabels.ICONS:
            break
        language, preset, timing = window._chips
        assert (
            preset.x() - language.geometry().right()
            == timing.x() - preset.geometry().right()
        )


def test_window_and_preset_controls_show_literal_ampersands(
    window: CaptionWindow,
) -> None:
    window.set_labels({window.source: SourceLabel("Arts & News", "#4dd0e1")}, "You")
    window.set_presets(PresetMenu(ITEMS, "video", restorable=True))
    assert window.controls["stop"].text() == "Stop captioning Arts && News"
    assert window.controls["stop"].toolTip() == "Stop captioning Arts & News"
    window.toggle_presets()
    assert window.presets is not None
    restore = window.presets.findChild(QPushButton, "presets.step.restore")
    assert restore is not None and "film && TV" in restore.text()
    window.toggle_presets()
    window.toggle_settings()
    assert window.popover is not None
    assert "Arts && News" in window.popover.app.text()


def test_the_timing_chip_sits_after_the_preset_chip(window: CaptionWindow) -> None:
    window.set_presets(PresetMenu(ITEMS, "everyday"))
    window.set_timing(CaptionMode.STEADY)
    chip = window.timing_chip
    assert chip.isVisible() and chip.text() == "Steady ▾"
    assert (
        on_window(window, chip).left() > on_window(window, window.preset_chip).right()
    )
    assert (
        on_window(window, chip).right()
        < on_window(window, window.buttons["lock"]).left()
    )
    assert chip.toolTip() == "Timing: Steady"


@pytest.mark.parametrize(
    ("preset", "timing", "rows"),
    [
        ("everyday", CaptionMode.STEADY, ["timing.live", "timing.steady", "timing.words", "timing.calm"]),
        ("conversation", CaptionMode.STEADY, ["timing.live", "timing.words"]),
        ("video", CaptionMode.INSTANT, ["timing.live", "timing.scrolling", "show.original", "show.translation"]),
        ("learning", CaptionMode.STEADY, ["timing.live", "timing.words", "timing.calm", "path.acquisition", "path.both"]),
        ("learning", CaptionMode.INSTANT, ["timing.live", "timing.words", "timing.calm"]),
    ],
)  # fmt: skip
def test_the_chip_offers_only_the_presets_timings(
    qapp: QApplication,
    window: CaptionWindow,
    preset: str,
    timing: CaptionMode,
    rows: list[str],
) -> None:
    window.set_presets(PresetMenu(ITEMS, preset))
    window.set_timing(timing)
    window.timing_chip.click()
    qapp.processEvents()
    assert offered_rows(window) == rows
    assert window.timing_chip.text().endswith("▴")  # its arrow turned while open
    timings = window.timings
    assert timings is not None
    for name in rows:  # each with its line of what it does
        row = timings.body.findChild(QPushButton, f"timings.{name}")
        assert row is not None
        if name.startswith("show."):
            assert row.isChecked() and row.text()
            continue
        lines = [
            label.text()
            for label in row.findChildren(QLabel)
            if not label.property("recommended")
        ]
        assert len(lines) == 2 and all(lines), name
        assert "experimental" not in lines[0].casefold(), name
    assert timings.findChild(QLabel, "timings.not_offered") is None
    timings.close()


def test_video_names_scrolling_and_everyday_names_whole_captions(
    qapp: QApplication, window: CaptionWindow
) -> None:
    window.set_presets(PresetMenu(ITEMS, "video"))
    window.set_timing(CaptionMode.SCROLLING)
    assert window.timing_chip.text() == "Scrolling ▾"
    window.set_presets(PresetMenu(ITEMS, "everyday"))
    window.set_timing(CaptionMode.WHOLE)
    assert window.timing_chip.text() == "Whole captions ▾"


def test_a_pick_asks_for_the_timing_and_closes(
    qapp: QApplication, window: CaptionWindow
) -> None:
    window.set_presets(PresetMenu(ITEMS, "conversation"))
    window.set_timing(CaptionMode.STEADY)
    asked: list[str] = []
    window.timing_wanted.connect(asked.append)
    window.timing_chip.click()
    qapp.processEvents()
    timings = window.timings
    assert timings is not None
    instant = timings.body.findChild(QPushButton, "timings.timing.live")
    assert instant is not None
    instant.click()
    assert asked == ["live"] and not timings.isVisible()
    window.set_timing(CaptionMode.INSTANT)  # as main answers
    assert window.timing_chip.text() == "Instant ▾"


def test_explicitly_choosing_the_effective_video_timing_saves_it(
    qapp: QApplication, window: CaptionWindow
) -> None:
    window.set_presets(PresetMenu(ITEMS, "video"))
    window.set_timing(CaptionMode.INSTANT)  # can be the fallback for a saved preference
    asked: list[str] = []
    window.timing_wanted.connect(asked.append)
    window.timing_chip.click()
    qapp.processEvents()
    assert window.timings is not None
    row = window.timings.body.findChild(QPushButton, "timings.timing.live")
    assert row is not None and row.isChecked()
    row.click()
    assert asked == ["live"]


@pytest.mark.parametrize("mode", [CaptionMode.INSTANT, CaptionMode.SCROLLING])
def test_video_timing_menu_keeps_one_track_visible(
    window: CaptionWindow, mode: CaptionMode
) -> None:
    window.set_presets(PresetMenu(ITEMS, "video"))
    window.set_timing(mode)
    asked: list[str] = []

    def select(value: str) -> None:
        asked.append(value)
        window.set_presets(PresetMenu(ITEMS, "video", show=Show(value)))

    def side(name: str) -> QPushButton:
        assert window.timings is not None
        row = window.timings.body.findChild(QPushButton, f"timings.show.{name}")
        assert row is not None
        return row

    window.lines_wanted.connect(select)
    window.timing_chip.click()
    side("original").click()
    assert asked == ["translation"]
    assert side("translation").isChecked() and not side("translation").isEnabled()
    assert not side("original").isChecked() and side("original").isEnabled()
    side("translation").click()
    side("original").click()
    side("translation").click()
    assert asked == ["translation", "both", "original"]
    assert side("original").isChecked() and not side("original").isEnabled()


def test_learnings_translation_after_or_with(
    qapp: QApplication, window: CaptionWindow
) -> None:
    window.set_presets(PresetMenu(ITEMS, "learning"))
    window.set_timing(CaptionMode.STEADY)
    window.set_path(ReadingPath.ACQUISITION)
    asked: list[str] = []
    window.path_wanted.connect(asked.append)
    window.timing_chip.click()
    qapp.processEvents()
    timings = window.timings
    assert timings is not None
    after = timings.body.findChild(QPushButton, "timings.path.acquisition")
    with_it = timings.body.findChild(QPushButton, "timings.path.both")
    assert after is not None and with_it is not None
    assert after.isChecked() and not with_it.isChecked()
    assert "a moment later" in after.accessibleName()
    with_it.click()
    assert asked == ["both"]


def test_a_timing_the_preset_doesnt_offer_is_said_and_kept(
    qapp: QApplication, window: CaptionWindow
) -> None:
    """Outside Video the chip keeps the requested timing and offers
    the timings that suit this preset."""
    window.set_presets(PresetMenu(ITEMS, "conversation"))
    window.set_timing(CaptionMode.CALM)
    assert window.timing_chip.text() == "Calm ▾"
    window.timing_chip.click()
    qapp.processEvents()
    timings = window.timings
    assert timings is not None
    note = timings.findChild(QLabel, "timings.not_offered")
    assert note is not None and note.isVisible()
    assert "Calm" in note.text() and "Conversation" in note.text()
    assert offered_rows(window) == ["timing.live", "timing.words"]
    assert not any(b.isChecked() for b in timings.body.findChildren(QPushButton))


def test_the_chip_follows_main_while_its_dropdown_is_open(
    qapp: QApplication, window: CaptionWindow
) -> None:
    window.set_presets(PresetMenu(ITEMS, "everyday"))
    window.set_timing(CaptionMode.STEADY)
    window.timing_chip.click()
    qapp.processEvents()
    window.set_timing(CaptionMode.CALM)  # Settings > Timing, meanwhile
    timings = window.timings
    assert timings is not None
    calm = timings.body.findChild(QPushButton, "timings.timing.calm")
    assert calm is not None and calm.isChecked()


# -- a narrow bar ------------------------------------------------------------------------


def test_labels_shorten_at_measured_widths_and_keep_all_icons_at_the_minimum(
    qapp: QApplication, window: CaptionWindow
) -> None:
    window.set_labels(
        {window.source: SourceLabel("Polyglotic Test Player", "#4dd0e1")}, "You"
    )
    window.set_presets(PresetMenu(ITEMS, "video"))
    window.set_timing(CaptionMode.SCROLLING)
    window.set_respeaking(True, "f8", hold_only=True)
    assert window.strip_labels is StripLabels.FULL
    assert window.tag.width() == window.tag.sizeHint().width()
    least = window._minimum().width
    states: dict[StripLabels, int] = {}
    for width in range(least, window.width() + 1):
        window.resize(width, 300)
        assert all(
            chip.isVisible()
            for chip in (window.chip, window.preset_chip, window.timing_chip)
        )
        states.setdefault(window.strip_labels, width)
    assert list(states) == [StripLabels.ICONS, StripLabels.SHORT, StripLabels.FULL]
    assert states[StripLabels.ICONS] == least
    window.resize(states[StripLabels.FULL], 300)
    assert window.tag.width() < window.tag.sizeHint().width()
    assert window.chip.text() == "Detect → English  ▾"
    assert window.preset_chip.text() == "Video, film && TV ▾"
    window.resize(states[StripLabels.SHORT], 300)
    assert window.chip.text() == "→ EN  ▾"
    assert window.preset_chip.text().endswith("… ▾")
    assert window.timing_chip.text() == "Scrolling ▾"
    window.resize(least, 300)
    assert window.mic_button.isVisible()
    assert window.tag.dot_only
    assert window.strip_labels is StripLabels.ICONS
    assert window._minimum().width == least
    qapp.processEvents()


def test_below_icon_minimum_the_gear_opens_each_overflowed_dropdown(
    qapp: QApplication, window: CaptionWindow
) -> None:
    window.set_presets(PresetMenu(ITEMS, "learning"))
    window.set_timing(CaptionMode.STEADY)
    least = window.strip_least()
    chips = (window.timing_chip, window.chip, window.preset_chip)
    for i, (name, chip, dropdown) in enumerate(
        zip(BAR_ROWS, chips, ("timings", "languages", "presets"), strict=True)
    ):
        window.resize(least, 300)
        assert chip.isVisible()
        window.resize(least - 1, 300)
        assert [c.isHidden() for c in chips] == [j <= i for j in range(len(chips))]
        window.buttons["settings"].click()
        qapp.processEvents()
        gear = window.popover
        assert gear is not None
        assert [n for n in BAR_ROWS if gear.rows[n].isVisible()] == list(
            BAR_ROWS[: i + 1]
        )
        row = gear.rows[name]
        assert isinstance(row, QPushButton)
        assert row.text() == chip.accessibleName()
        row.click()
        opened = getattr(window, dropdown)
        assert opened.isVisible() and not gear.isVisible()
        assert opened._anchor == on_window(
            window, window.buttons["settings"]
        ).translated(window.pos())
        window.close_settings()
        layout = window.band.layout()
        assert layout is not None
        least -= chip.width() + layout.spacing()


def focus(qapp: QApplication) -> QWidget:
    qapp.processEvents()
    focused = qapp.focusWidget()
    assert focused is not None
    return focused


@pytest.mark.parametrize("tier", ["full", "short", "icons", "overflow"])
def test_keyboard_reaches_and_changes_every_chip(
    qapp: QApplication, window: CaptionWindow, tier: str
) -> None:
    window.set_presets(PresetMenu(ITEMS, "everyday"))
    window.set_timing(CaptionMode.INSTANT)
    if tier == "overflow":
        window.resize(window.strip_least(), 300)
        layout = window.band.layout()
        assert layout is not None
        chips = (window.chip, window.preset_chip, window.timing_chip)
        room = sum(chip.width() + layout.spacing() for chip in chips)
        window.resize(window.width() - room, 300)
        assert all(chip.isHidden() for chip in chips)
    else:
        for width in range(window.width(), window._minimum().width - 1, -1):
            window.resize(width, 300)
            if window.strip_labels == tier:
                break
        assert window.strip_labels == tier
    names = ("Timing: Instant", "Languages: Detect → English", "Preset: Everyday")
    for chip, name in zip(
        (window.timing_chip, window.chip, window.preset_chip), names, strict=True
    ):
        assert chip.toolTip() == name
        assert chip.accessibleName() == name

    timings: list[str] = []
    presets: list[str] = []
    window.timing_wanted.connect(timings.append)
    window.preset_wanted.connect(presets.append)
    for index in range(len(BAR_ROWS)):
        window.open_bar_controls()
        chooser = window.bar_controls
        assert chooser is not None
        assert focus(qapp) is chooser.rows[BAR_ROWS[0]]
        for _ in range(index):
            QTest.keyClick(focus(qapp), Qt.Key.Key_Tab)
        assert focus(qapp) is chooser.rows[BAR_ROWS[index]]
        QTest.keyClick(focus(qapp), Qt.Key.Key_Return)
        qapp.processEvents()
        if index == 0:
            timings_menu = window.timings
            assert timings_menu is not None and timings_menu.isActiveWindow()
            QTest.keyClick(focus(qapp), Qt.Key.Key_Tab)
            QTest.keyClick(focus(qapp), Qt.Key.Key_Return)
            assert timings == ["steady"]
        elif index == 1:
            language_menu = window.languages
            assert language_menu is not None and language_menu.isActiveWindow()
            QTest.keyClick(focus(qapp), Qt.Key.Key_Tab)
            assert focus(qapp) is language_menu.language
            QTest.keyClick(focus(qapp), Qt.Key.Key_Return)
            QTest.keyClick(focus(qapp), Qt.Key.Key_Tab)
            assert focus(qapp) is language_menu.languages
            QTest.keyClick(focus(qapp), Qt.Key.Key_Home)
            QTest.keyClick(focus(qapp), Qt.Key.Key_Return)
            assert window.choices.target is None
            QTest.keyClick(focus(qapp), Qt.Key.Key_Escape)
            window.set_language("en")
        else:
            presets_menu = window.presets
            assert presets_menu is not None and presets_menu.isActiveWindow()
            QTest.keyClick(focus(qapp), Qt.Key.Key_Tab)
            QTest.keyClick(focus(qapp), Qt.Key.Key_Return)
            assert presets == ["conversation"]
        assert not window.keyboard_bar_open

    # On Linux the mouse-opened popup still needs focus to catch Escape and
    # clicks outside the popup, including over a Wayland app.
    window.toggle_timings()
    assert window.timings is not None and not window.timings.keyboard
    assert bool(
        window.timings.windowFlags() & Qt.WindowType.WindowDoesNotAcceptFocus
    ) == (not sys.platform.startswith("linux"))


# -- the gear menu -----------------------------------------------------------------------


def test_the_gear_menu_rows(qapp: QApplication, window: CaptionWindow) -> None:
    assert (
        "app",
        *BAR_ROWS,
        "text_size",
        "translation_size",
        "long_lines",
        "opacity",
        "show_pace",
        "show_caption_info",
        "transcript",
        "join",
        "stop",
        "all_settings",
    ) == ROWS
    assert (
        "app",
        *BAR_ROWS,
        "text_size",
        "translation_size",
        "long_lines",
        "opacity",
        "show_pace",
        "show_caption_info",
        "transcript",
        "stop",
    ) == COLUMN_ROWS
    window.windows = 2  # Join windows shows with two or more
    window.buttons["settings"].click()
    qapp.processEvents()
    popover = window.popover
    assert popover is not None
    shown = [name for name in ROWS if popover.rows[name].isVisible()]
    # Captioning shows only for a window with apps to pick from; bar chips
    # (including bar_languages) show only when folded away at narrow widths.
    assert shown == [
        name for name in ROWS if name not in {"app", *BAR_ROWS}
    ] or shown == [name for name in ROWS if name not in {*BAR_ROWS}]
    assert "respeak" not in popover.rows
    assert "languages" not in popover.rows
    assert not popover.rows["bar_languages"].isVisible()
    for gone in (
        "show_mic",
        "timing",
        "said_colours",
        "translation_colours",
        "quiet_words",
        "copy_all",
    ):
        assert gone not in popover.rows
    popover.close()


def test_the_menus_languages_row_shows_only_when_bar_chip_is_folded(
    qapp: QApplication, window: CaptionWindow
) -> None:
    """655: the gear menu's language row shows only when the bar has folded
    the language chip away (635's narrow steps); otherwise the bar's chip is
    the one place."""
    assert window.chip.isVisible()
    window.buttons["settings"].click()
    qapp.processEvents()
    popover = window.popover
    assert popover is not None
    assert "languages" not in popover.rows
    assert not popover.rows["bar_languages"].isVisible()
    popover.close()

    # Narrow until the language chip folds away
    least = window.strip_least()
    layout = window.band.layout()
    assert layout is not None
    narrow = least - window.timing_chip.width() - layout.spacing() - 1
    window.resize(narrow, 300)
    qapp.processEvents()
    assert window.chip.isHidden()
    window.buttons["settings"].click()
    qapp.processEvents()
    popover = window.popover
    assert popover is not None
    assert popover.rows["bar_languages"].isVisible()
    bar_languages = popover.rows["bar_languages"]
    assert isinstance(bar_languages, QPushButton)
    bar_languages.click()
    qapp.processEvents()
    assert window.languages is not None and window.languages.isVisible()
    assert window.languages.rows["spoken"].isVisible()
    assert window.languages.rows["language"].isVisible()
    window.close_settings()


# -- bar own-speech switch ---------------------------------------------------------------


def test_bar_mic_toggles_own_speech_without_taking_focus(
    qapp: QApplication, window: CaptionWindow
) -> None:
    from PySide6.QtGui import QAccessible

    mic = window.mic_button
    assert mic.isVisible() and mic.isCheckable() and not mic.isChecked()
    assert mic.focusPolicy() == Qt.FocusPolicy.NoFocus
    assert window.testAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
    assert mic.toolTip() == "Show my speech here: off"
    assert mic.accessibleName() == "Show my speech here"
    iface = QAccessible.queryAccessibleInterface(mic)
    assert iface.text(QAccessible.Text.Name) == "Show my speech here"
    assert iface.state().checkable and not iface.state().checked

    changed: list[bool] = []
    window.mic_changed.connect(lambda: changed.append(window.choices.show_mic))

    # Clicking turns own speech on and accepts live mic levels
    mic.click()
    assert window.choices.show_mic and mic.isChecked()
    assert changed == [True]
    assert mic.toolTip() == "Show my speech here: on"
    assert iface.state().checked
    window.set_mic_level(0.6)
    assert mic.level == 0.6
    mic.repaint()

    # Clicking again turns it off and clears the meter
    mic.click()
    assert not window.choices.show_mic and not mic.isChecked()
    assert changed == [True, False]
    assert mic.level is None
    assert mic.toolTip() == "Show my speech here: off"
    assert not iface.state().checked


def test_bar_mic_is_keyboard_accessible_through_bar_controls(
    qapp: QApplication, window: CaptionWindow
) -> None:
    window.open_bar_controls()
    chooser = window.bar_controls
    assert chooser is not None and "bar_mic" in chooser.rows
    for _ in range(KEYBOARD_BAR_ROWS.index("bar_mic")):
        QTest.keyClick(focus(qapp), Qt.Key.Key_Tab)
    row = chooser.rows["bar_mic"]
    assert focus(qapp) is row
    assert row.accessibleName() == "Show my speech here"
    QTest.keyClick(focus(qapp), Qt.Key.Key_Space)
    qapp.processEvents()
    assert window.choices.show_mic and window.mic_button.isChecked()
    QTest.keyClick(focus(qapp), Qt.Key.Key_Space)
    qapp.processEvents()
    assert not window.choices.show_mic and not window.mic_button.isChecked()
    window.close_settings()


def test_a_window_of_the_mic_has_no_bar_mic_switch(qapp: QApplication) -> None:
    mine = window_of(qapp)
    try:
        mine.source = MIC  # it captions the mic itself: own-speech switch hidden
        mine._fit_band()
        qapp.processEvents()
        assert not mine.mic_offered() and mine.mic_button.isHidden()
        assert not mine.respeak_offered()
    finally:
        mine.close()


# -- the chips in words -------------------------------------------------------------------


def test_a_screen_reader_says_the_chips_in_words(
    qapp: QApplication, window: CaptionWindow
) -> None:
    """Read the preset and timing without the dropdown arrows."""
    from dataclasses import replace

    from PySide6.QtGui import QAccessible

    window.set_presets(PresetMenu(ITEMS, "learning"))
    window.set_timing(CaptionMode.STEADY)
    preset = QAccessible.queryAccessibleInterface(window.preset_chip)
    timing = QAccessible.queryAccessibleInterface(window.timing_chip)
    assert preset.text(QAccessible.Text.Name) == "Preset: Learning"
    assert timing.text(QAccessible.Text.Name) == "Timing: Steady"
    window.set_presets(replace(PresetMenu(ITEMS, "learning"), edited=3))
    assert window.preset_chip.text() == "Learning ▾"
    assert preset.text(QAccessible.Text.Name) == "Preset: Learning"
    window.set_presets(PresetMenu(ITEMS, "video"))
    window.set_timing(CaptionMode.SCROLLING)
    assert timing.text(QAccessible.Text.Name) == "Timing: Scrolling"
    window.timing_chip.click()  # open: the arrow turns, the name doesn't
    qapp.processEvents()
    assert timing.text(QAccessible.Text.Name) == "Timing: Scrolling"
    assert window.timings is not None
    window.timings.close()


# -- timing recommendations per preset (638) ---------------------------------------------


def _recommended_badges(widget: QWidget) -> list[str]:
    return [
        label.objectName()
        for label in widget.findChildren(QLabel)
        if label.property("recommended")
    ]


def test_timing_menu_marks_the_presets_recommendation_and_moves_with_preset(
    qapp: QApplication, window: CaptionWindow
) -> None:
    window.set_presets(PresetMenu(ITEMS, "everyday"))
    window.set_timing(CaptionMode.INSTANT)
    window.timing_chip.click()
    qapp.processEvents()
    timings = window.timings
    assert timings is not None
    assert _recommended_badges(timings.body) == ["timings.recommended.live"]
    instant = timings.body.findChild(QPushButton, "timings.timing.live")
    assert instant is not None
    assert instant.toolTip().startswith("Recommended for Everyday: ")
    assert "Recommended for Everyday: " in instant.accessibleName()
    assert instant.accessibleDescription().startswith("Recommended for Everyday: ")

    # Switching preset while the menu is open moves the mark at once
    window.set_presets(PresetMenu(ITEMS, "video"))
    qapp.processEvents()
    assert _recommended_badges(timings.body) == ["timings.recommended.live"]
    instant = timings.body.findChild(QPushButton, "timings.timing.live")
    assert instant is not None
    assert instant.toolTip().startswith("Recommended for Video, film & TV: ")
    assert "Recommended for Video, film & TV: " in instant.accessibleName()
    # Choosing Scrolling is allowed and never nagged
    asked: list[str] = []
    window.timing_wanted.connect(asked.append)
    delayed = timings.body.findChild(QPushButton, "timings.timing.scrolling")
    assert delayed is not None
    assert "Recommended for" not in delayed.toolTip()
    delayed.click()
    assert asked == ["scrolling"]
    assert window.notices.showing(0.0)[1] is None


def test_timing_menu_inherits_saved_preset_parent_and_shows_none_without_parent(
    qapp: QApplication, window: CaptionWindow
) -> None:
    with_saved = (
        *ITEMS,
        PresetItem("own1", "Anime", own=True, parent="video"),
        PresetItem("own2", "Freeform", own=True, parent=None),
        PresetItem("custom", "Custom", own=True, parent=None),
    )
    window.set_presets(PresetMenu(with_saved, "own1"))
    window.set_timing(CaptionMode.WHOLE)
    window.timing_chip.click()
    qapp.processEvents()
    timings = window.timings
    assert timings is not None
    assert _recommended_badges(timings.body) == ["timings.recommended.live"]
    instant = timings.body.findChild(QPushButton, "timings.timing.live")
    assert instant is not None
    assert instant.toolTip().startswith("Recommended for Anime: ")
    assert "Recommended for Anime: " in instant.accessibleName()

    window.set_presets(PresetMenu(with_saved, "own2"))
    qapp.processEvents()
    assert _recommended_badges(timings.body) == []

    window.set_presets(PresetMenu(with_saved, "custom"))
    qapp.processEvents()
    assert _recommended_badges(timings.body) == []
    timings.close()


def test_folded_timing_menu_shows_the_recommended_tag(
    qapp: QApplication, window: CaptionWindow
) -> None:
    window.set_presets(PresetMenu(ITEMS, "video"))
    window.set_timing(CaptionMode.WHOLE)
    window.resize(window.strip_least() - 1, 300)
    qapp.processEvents()
    assert window.timing_chip.isHidden()
    window.toggle_settings()
    assert window.popover is not None
    row = window.popover.rows["bar_timing"]
    assert isinstance(row, QPushButton)
    row.click()
    timings = window.timings
    assert timings is not None
    assert _recommended_badges(timings.body) == ["timings.recommended.live"]
    instant = timings.body.findChild(QPushButton, "timings.timing.live")
    assert instant is not None
    assert instant.toolTip().startswith("Recommended for Video, film & TV: ")
    assert "Recommended for Video, film & TV: " in instant.accessibleName()
    timings.close()
