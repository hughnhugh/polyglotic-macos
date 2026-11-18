"""Word links on the caption window's hover strip, where A- / A+ were; the
text size in its settings popover (the user's rehearsal feedback F9,
polyglotic-hq 249, 2026-11-08: "I want the word links toggle to be on the
main caption window instead of font change")."""

from dataclasses import replace

from PySide6.QtGui import QAccessible, QIcon
from PySide6.QtWidgets import QApplication, QLabel, QPushButton
from tests.ui_next.test_caption_window import MIC, Store, areas, window_of
from tests.ui_next.test_joined_window import THREE

from polyglotic_desktop.core.listening.display import WordLinks
from polyglotic_desktop.core.listening.sources import SourceLabel
from polyglotic_desktop.ui_next.caption_window import STRIP, CaptionWindow
from polyglotic_desktop.ui_next.caption_windows import CaptionWindows
from polyglotic_desktop.ui_next.glyphs import Glyph
from polyglotic_desktop.ui_next.settings_popover import COLUMN_ROWS, ROWS
from polyglotic_desktop.ui_next.views.caption_window import CaptionLook
from polyglotic_desktop.ui_next.views.panels import LookView


def test_the_strip_has_word_links_and_no_text_size() -> None:
    # "report" only shows for an alpha tester (polyglotic-hq 275)
    # filled lines and parts lined up beside word links (polyglotic-hq 372)
    # and the quiet view beside them (polyglotic-hq 477)
    assert STRIP == (
        "links", "quiet", "fill", "aligned", "lock", "report", "settings", "stop",
    )  # fmt: skip


def test_the_button_shows_and_asks_for_word_links(qapp: QApplication) -> None:
    window = window_of(qapp)
    try:
        button = window.buttons["links"]
        assert window.glyphs["links"] is Glyph.LINKS
        assert not window.controls["links"].icon().isNull()
        said = QAccessible.queryAccessibleInterface(button)
        assert said.text(QAccessible.Text.Name) == "Word links"
        assert button.toolTip()  # what they are, in plain words
        assert not button.isChecked()  # off by default
        asked: list[bool] = []
        window.links_wanted.connect(lambda on, _: asked.append(on))
        button.click()
        assert asked == [True]
        window.set_look(replace(window.look, word_links=WordLinks.HOVER))
        assert button.isChecked()
        button.click()
        assert asked == [True, False]
    finally:
        window.close()


def _brightest(drawn: QIcon, mode: QIcon.Mode) -> int:
    """The lightest opaque pixel of the icon in `mode`, 0-255."""
    image = drawn.pixmap(16, mode).toImage()
    return max(
        (
            image.pixelColor(x, y).lightness()
            for x in range(image.width())
            for y in range(image.height())
            if image.pixelColor(x, y).alpha() > 200
        ),
        default=0,
    )


def test_with_what_was_said_hidden_the_button_says_why_it_does_nothing(
    qapp: QApplication,
) -> None:
    """A link joins a word of what was said to its translation: with the
    original hidden, the button changed nothing you could see (249's F9;
    polyglotic-hq 258). It's off to clicks then, and says why in Look's
    words; shown again, it works as before."""
    window = window_of(qapp)
    try:
        button = window.buttons["links"]
        on = button.toolTip()
        asked: list[bool] = []
        window.links_wanted.connect(lambda on, _: asked.append(on))
        window.set_look(replace(window.look, show_original=False))
        assert not button.isEnabled()
        assert button.toolTip() == (
            "Word links need what was said: turn on “Show the original above the "
            "translation” in Settings"
        )
        button.click()
        assert asked == []
        # dimmed: Qt's own grey of a near-white glyph stayed near white
        drawn = window.controls["links"].icon()
        assert _brightest(drawn, QIcon.Mode.Normal) > 220
        assert _brightest(drawn, QIcon.Mode.Disabled) < 180
        window.set_look(
            replace(window.look, show_original=False, word_links=WordLinks.COLOURS)
        )
        assert button.isChecked() and not button.isEnabled()  # still says it's on
        window.set_look(replace(window.look, show_original=True))
        assert button.isEnabled() and button.toolTip() == on
        button.click()
        assert asked == [False]
    finally:
        window.close()


def test_every_window_s_button_reaches_the_look(qapp: QApplication) -> None:
    windows = CaptionWindows(Store({"targets": ["en"]}), MIC, areas)
    windows.set_labels(
        {source: SourceLabel(name, "#4dd0e1") for name, source in THREE}, "You"
    )
    look = LookView(CaptionLook(), on_change=windows.set_look)
    windows.links_wanted.connect(look.set_links_shown)
    windows.set_captioned(THREE[:2])
    first, second = windows.windows.values()
    first.buttons["links"].click()
    assert look.value.word_links is WordLinks.ARROWS
    assert first.buttons["links"].isChecked() and second.buttons["links"].isChecked()
    second.buttons["links"].click()
    assert look.value.word_links is WordLinks.OFF
    assert not first.buttons["links"].isChecked()
    windows.close()


def test_on_again_is_the_way_last_chosen_in_look() -> None:
    view = LookView(CaptionLook())
    view.set_links_shown(True)
    assert view.value.word_links is WordLinks.ARROWS  # never chosen: with lines
    view.set_word_links(WordLinks.HOVER)  # chosen in Look
    view.set_links_shown(False)
    assert view.value.word_links is WordLinks.OFF
    view.set_links_shown(True)
    assert view.value.word_links is WordLinks.HOVER
    saved = LookView(CaptionLook(word_links=WordLinks.HOVER))
    saved.set_links_shown(False)
    saved.set_links_shown(True)
    assert saved.value.word_links is WordLinks.HOVER  # a saved choice too


def _popover(window: CaptionWindow, qapp: QApplication) -> None:
    window.hovered = True
    window._show_band(True)
    window.toggle_settings()
    qapp.processEvents()


def test_the_text_size_is_in_the_settings_popover(qapp: QApplication) -> None:
    assert ROWS.index("text_size") == ROWS.index("timing") + 1
    assert "text_size" in COLUMN_ROWS  # a joined window's column has its own
    window = window_of(qapp)
    try:
        _popover(window, qapp)
        popover = window.popover
        assert popover is not None
        row = popover.rows["text_size"]
        smaller, bigger = (
            row.findChild(QPushButton, f"settings_popover.caption_window.{name}")
            for name in ("smaller", "bigger")
        )
        assert smaller is not None and bigger is not None
        assert (smaller.text(), bigger.text()) == ("A-", "A+")
        assert smaller.accessibleName() == "Smaller text"
        assert bigger.accessibleName() == "Bigger text"
        heading = row.findChild(QLabel)
        assert heading is not None and "100%" in heading.text()
        bigger.click()
        assert window.choices.text_size == 1.1
        assert "110%" in heading.text()
        smaller.click()
        smaller.click()
        assert window.choices.text_size == 0.9
        assert "90%" in heading.text()
    finally:
        window.close()
