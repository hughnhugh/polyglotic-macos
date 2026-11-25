"""The settings inventory follows the audit and covers the live controls."""

from collections.abc import Iterator
from dataclasses import fields
from fnmatch import fnmatchcase
from pathlib import Path

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractButton,
    QAbstractSlider,
    QApplication,
    QComboBox,
    QLineEdit,
    QListWidget,
    QPlainTextEdit,
    QScrollBar,
    QWidget,
)
from tools.ui_lab.home import hub
from tools.ui_lab.lab import Lab

from polyglotic_desktop.ui.settings import AppSettings
from polyglotic_desktop.ui_next import style
from polyglotic_desktop.ui_next.controls import Card, Segmented
from polyglotic_desktop.ui_next.home import HomePage
from polyglotic_desktop.ui_next.preset_popover import PresetPopover
from polyglotic_desktop.ui_next.presets_card import PresetLine
from polyglotic_desktop.ui_next.settings_marks import GlyphTile, PinnedCard
from polyglotic_desktop.ui_next.settings_page import SECTIONS, SettingsPage
from polyglotic_desktop.ui_next.settings_popover import LANGUAGE_ROWS, SettingsPopover
from polyglotic_desktop.ui_next.timing_popover import TimingPopover
from polyglotic_desktop.ui_next.views.caption_window import StoredWindows, WindowChoices
from polyglotic_desktop.ui_next.views.settings_map import (
    KNOWN_DUPLICATES,
    SETTINGS_MAP,
    SettingEntry,
    duplicates,
    expected_duplicates,
    summary,
)


def test_settings_audit(capsys: pytest.CaptureFixture[str]) -> None:
    ids = [entry.id for entry in SETTINGS_MAP]
    assert len(set(ids)) == len(ids)
    assert [
        entry.id for entry in SETTINGS_MAP if entry.place_today.startswith("settings:")
    ] == [
        f"{prefix}{number}"
        for prefix, first, count in (
            ("P", 1, 6),
            ("L", 1, 14),
            ("W", 1, 12),
            ("R", 1, 13),
            ("T", 1, 10),
            ("B", 1, 4),
            ("S", 1, 8),
            ("D", 1, 9),
            ("H", 1, 13),
            ("A", 0, 9),
            ("X", 1, 24),
        )
        for number in range(first, first + count)
    ]
    assert set(KNOWN_DUPLICATES) == set(range(1, 12))
    assert all(set(item.rows) <= set(ids) for item in KNOWN_DUPLICATES.values())
    app_keys = {field.name for field in fields(AppSettings)} | {"start_at_sign_in"}
    window_keys = {
        field.name for kind in (WindowChoices, StoredWindows) for field in fields(kind)
    }
    for entry in SETTINGS_MAP:
        for key in entry.setting_keys:
            base, _, child = key.partition(".")
            if base == "window":
                assert child in window_keys, (entry.id, key)
            else:
                assert base in app_keys, (entry.id, key)
    with capsys.disabled():
        print(summary())
    assert summary().splitlines()[0] == (
        "122 Settings rows today; 9 Everyday choices, 76 More, 28 Lab, 8 leaving."
    )


def assert_duplicates(entries: tuple[SettingEntry, ...]) -> None:
    assert duplicates(entries) == expected_duplicates()


def test_duplicate_ratchet() -> None:
    assert_duplicates(SETTINGS_MAP)


def test_duplicate_ratchet_rejects_new_duplicate() -> None:
    extra = SettingEntry("planted", ("theme",), ("planted",), "home", "home")
    with pytest.raises(AssertionError, match="theme"):
        assert_duplicates((*SETTINGS_MAP, extra))


def test_duplicate_ratchet_rejects_a_new_place_for_a_known_duplicate() -> None:
    extra = SettingEntry("planted", ("opacity",), ("planted",), "home", "home")
    with pytest.raises(AssertionError, match="opacity"):
        assert_duplicates((*SETTINGS_MAP, extra))


def test_duplicate_ratchet_notices_a_removed_duplicate() -> None:
    without_cog_size = tuple(entry for entry in SETTINGS_MAP if entry.id != "G1")
    with pytest.raises(AssertionError, match="window.text_size"):
        assert_duplicates(without_cog_size)


@pytest.fixture
def audit_ui(qapp: QApplication, tmp_path: Path) -> Iterator[dict[str, QWidget]]:
    lab = Lab(qapp, tmp_path)
    built = hub(lab, {"apps": ("discord.exe",), "whole_system": False})
    window = next(iter(built.windows.windows.values()))
    cog = SettingsPopover(window)
    language = SettingsPopover(window, rows=LANGUAGE_ROWS)
    presets = PresetPopover(window)
    timing = TimingPopover(window)
    try:
        presets.refresh()
        timing.refresh()
        for section in SECTIONS:
            built.settings.show_section(section)
            lab.pump()
        sound = built.home.sound
        assert sound is not None
        yield {
            "settings": built.settings,
            "home/captions": built.home.picker_card,
            "home/sound": sound,
            "home/windows": built.home,
            "cog": cog,
            "bar:language": language,
            "bar:preset": presets,
            "bar:timing": timing,
            "bar:mic": window,
        }
    finally:
        cog.close()
        language.close()
        presets.close()
        timing.close()
        for close in reversed(lab.closing):
            close()


def test_cards_keep_their_spacing_and_home_row_buttons_are_ghosts(
    audit_ui: dict[str, QWidget],
) -> None:
    settings = audit_ui["settings"]
    home = audit_ui["home/windows"]
    assert isinstance(settings, SettingsPage)
    assert isinstance(home, HomePage)
    assert home.content.spacing() == style.px(32)
    for section in settings.section.values():
        layout = section.layout()
        assert layout is not None
        assert layout.spacing() == style.px(32)
    for action in ("captions", "transcript", "stop"):
        buttons = [
            button
            for button in home.picker_card.findChildren(QAbstractButton)
            if fnmatchcase(button.objectName(), f"picker.{action}.[0-9]*")
        ]
        assert buttons and all(button.property("kind") == "ghost" for button in buttons)


def test_cards_and_marks_are_flat_and_inputs_keep_their_border(
    audit_ui: dict[str, QWidget],
) -> None:
    settings = audit_ui["settings"]
    assert isinstance(settings, SettingsPage)
    theme = style.current()
    page = QWidget()
    page.setObjectName("Content")
    page.setStyleSheet(style.stylesheet(theme))
    page.resize(600, 280)
    try:
        card = Card("Card", parent=page)
        # A pinned heading is visually flat, but it must still occlude the
        # card words scrolling underneath it. A transparent pinned heading
        # made Appearance overlap its first setting in the scrolled App state.
        behind_pinned = QWidget(page)
        behind_pinned.setStyleSheet("background: #ff0000")
        behind_pinned.setGeometry(10, 50, 300, 50)
        pinned = PinnedCard(page)
        preset = PresetLine(settings.preset_line.view, page)
        field = QLineEdit(page)
        mark = settings.findChild(GlyphTile, "CardMark")
        assert mark is not None
        glyph = GlyphTile(mark.glyph, parent=page)
        for y, control in enumerate((card, pinned, preset, field, glyph)):
            control.move(10, 50 * y)
            control.adjustSize()
        page.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        page.show()
        page.setFocus()
        QApplication.processEvents()
        background = QColor(theme["BG"] if theme.dark else theme["SURFACE"])
        image = page.grab().toImage()
        scale = image.devicePixelRatio()
        for control in (card, pinned, preset, glyph):
            middle = round((control.x() + control.width() // 2) * scale)
            top = round(control.y() * scale)
            assert image.pixelColor(middle, top) == background, control.objectName()
            assert image.pixelColor(middle, top + 1) == background, control.objectName()
        pinned_corner = pinned.mapTo(page, QPoint(2, 2))
        assert (
            image.pixelColor(
                round(pinned_corner.x() * scale), round(pinned_corner.y() * scale)
            )
            == background
        )
        glyph_image = glyph.grab().toImage()
        assert any(
            glyph_image.pixelColor(x, y).alpha() != 0
            for y in range(glyph_image.height())
            for x in range(glyph_image.width())
        )
        image = field.grab().toImage()
        assert image.pixelColor(image.width() // 2, 0) == QColor(theme["BORDER"])
        assert image.pixelColor(image.width() // 2, image.height() // 2) == QColor(
            theme["SURFACE_2"]
        )
    finally:
        page.close()


def test_card_stylesheet_has_no_border() -> None:
    card = style.stylesheet(style.current()).split("#Card {", 1)[1].split("}", 1)[0]
    assert "border: none" in card


def test_checked_segment_keeps_the_same_text_weight(qapp: QApplication) -> None:
    """Selecting a flat segment must not make its label outgrow its choice."""
    choices = Segmented((("short", "Short"), ("long", "A few per caption")), "long")
    choices.setStyleSheet(style.stylesheet(style.current()))
    choices.show()
    qapp.processEvents()
    try:
        assert choices.buttons[1].isChecked()
        assert choices.buttons[1].font().weight() == choices.buttons[0].font().weight()
    finally:
        choices.close()


PREFIXES = (
    "settings.",
    "caption_window.",
    "look.",
    "hotkeys.",
    "home.",
    "settings_popover.",
    "picker.",
    "presets.",
    "sound.",
    "languages.",
    "timing.",
    "lab.",
)
CONTROLS = (
    QAbstractButton,
    QAbstractSlider,
    QComboBox,
    QLineEdit,
    QListWidget,
    QPlainTextEdit,
)


# Navigation and session actions do not write a setting. The per-source
# actions are constructed on You as well, where they are always hidden.
NON_SETTINGS_CONTROLS = {
    "settings.section_picker",
    "picker.captions.you",
    "picker.language.you",
    "picker.mic.you",
    "picker.stop.you",
    "picker.transcript.you",
    "home.get_plus",
    "home.level.set",
    "home.listen_here",
    "home.sign_in",
    "home.status_page",
    "home.system_audio_settings",
    "home.update.download_anyway",
    "home.update.later",
    "home.update.open_folder",
    "home.update.restart",
    "home.upgrade",
    "home.whats_new.all",
    "home.whats_new.close",
}


def scope(place: str) -> str:
    return "settings" if place.startswith("settings:") else place


def test_settings_map_walks_the_live_controls(audit_ui: dict[str, QWidget]) -> None:
    names = {
        place: {child.objectName() for child in root.findChildren(QWidget)}
        for place, root in audit_ui.items()
    }
    missing = [
        (row.id, pattern)
        for row in SETTINGS_MAP
        for pattern in row.object_names
        if not any(fnmatchcase(name, pattern) for name in names[scope(row.place_today)])
    ]
    unmapped = set()
    for place, root in audit_ui.items():
        if place in {"bar:preset", "bar:timing", "bar:mic"}:
            continue  # supplemental bar rows are checked for existence above
        patterns = [
            pattern
            for entry in SETTINGS_MAP
            if scope(entry.place_today) == place
            for pattern in entry.object_names
        ]
        for child in root.findChildren(QWidget):
            if place == "home/windows" and any(
                audit_ui[card].isAncestorOf(child)
                for card in ("home/captions", "home/sound")
            ):
                continue
            name = child.objectName()
            if (
                isinstance(child, CONTROLS)
                and not isinstance(child, QScrollBar)
                and name.startswith(PREFIXES)
                and name not in NON_SETTINGS_CONTROLS
                and not any(fnmatchcase(name, pattern) for pattern in patterns)
            ):
                unmapped.add((place, name))
    assert not missing, missing
    assert not unmapped, "\n".join(
        f"{place}: {name}" for place, name in sorted(unmapped)
    )
