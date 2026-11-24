"""Word links on the caption window's hover strip, where A- / A+ were; the
text size in its settings popover (the user's rehearsal feedback F9,
polyglotic-hq 249, 2026-11-08: "I want the word links toggle to be on the
main caption window instead of font change")."""

from dataclasses import replace

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QIcon
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel, QPushButton
from tests.ui_next.test_caption_window import MIC, Store, areas, window_of
from tests.ui_next.test_joined_window import THREE

from polyglotic_desktop.core.listening.captions import WordClass
from polyglotic_desktop.core.listening.display import WordLinks
from polyglotic_desktop.core.listening.sources import SourceLabel
from polyglotic_desktop.ui_next.caption_window import STRIP, CaptionWindow
from polyglotic_desktop.ui_next.caption_windows import CaptionWindows
from polyglotic_desktop.ui_next.glyphs import Glyph
from polyglotic_desktop.ui_next.panels import WordLinksPanel
from polyglotic_desktop.ui_next.settings_popover import COLUMN_ROWS, ROWS
from polyglotic_desktop.ui_next.views.caption_window import CaptionLook
from polyglotic_desktop.ui_next.views.panels import LookView
from polyglotic_desktop.ui_next.views.presets import BY_KEY, contrast
from polyglotic_desktop.ui_next.word_classes import (
    CLASS_ALTERNATES,
    CLASS_COLOURS,
    CLASS_CONTRAST,
    WordClassLegend,
    class_colour,
)


def test_word_links_is_the_first_icon_in_the_strip() -> None:
    assert STRIP == ("links", "lock", "report", "settings", "stop")


def test_the_button_shows_and_asks_for_word_links(qapp: QApplication) -> None:
    window = window_of(qapp)
    try:
        button = window.controls["links"]
        assert window.buttons["links"].defaultAction() is button
        assert window.glyphs["links"] is Glyph.LINKS
        assert not button.icon().isNull()
        assert button.text() == "Word links"
        assert button.toolTip()  # what they are, in plain words
        assert not button.isChecked()  # off by default
        asked: list[bool] = []
        window.links_wanted.connect(lambda on, _: asked.append(on))
        button.trigger()
        assert asked == [True]
        window.set_look(replace(window.look, word_links=WordLinks.HOVER))
        assert button.isChecked()
        button.trigger()
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
        button = window.controls["links"]
        on = button.toolTip()
        asked: list[bool] = []
        window.links_wanted.connect(lambda on, _: asked.append(on))
        window.set_look(replace(window.look, show_original=False))
        assert not button.isEnabled()
        assert button.toolTip() == (
            "Word links need what was said: turn on “Show the original above the "
            "translation” in Settings"
        )
        button.trigger()
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
        button.trigger()
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
    first.controls["links"].trigger()
    assert look.value.word_links is WordLinks.ARROWS
    assert first.controls["links"].isChecked() and second.controls["links"].isChecked()
    second.controls["links"].trigger()
    assert look.value.word_links is WordLinks.OFF
    assert not first.controls["links"].isChecked()
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
    assert ROWS.index("translation_size") == ROWS.index("text_size") + 1  # 655
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
        assert smaller.accessibleName() == "Smaller caption size"
        assert bigger.accessibleName() == "Bigger caption size"
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


def test_word_class_legend_opens_on_hover_and_from_keyboard(qapp: QApplication) -> None:
    window = window_of(qapp)
    try:
        window.show()
        window.open_bar_controls()
        qapp.processEvents()
        chooser = window.bar_controls
        assert chooser is not None
        legend = chooser.rows["bar_word_classes"]
        assert isinstance(legend, WordClassLegend)
        assert not legend.toggle.isChecked()
        assert not legend.button.isVisible()
        wanted: list[bool] = []
        window.class_colours_wanted.connect(wanted.append)
        legend.toggle.click()
        assert wanted == [True]
        window.set_look(replace(window.look, colour_links_by_word_class=True))
        chooser.refresh()
        for _ in range(len(chooser.rows)):
            focused = qapp.focusWidget()
            assert focused is not None
            if focused is legend.button:
                break
            QTest.keyClick(focused, Qt.Key.Key_Tab)
        assert qapp.focusWidget() is legend.button
        QTest.keyClick(legend.button, Qt.Key.Key_Space)
        assert legend.labels.isVisible()
        assert "Adjective" in legend.labels.text()
        adverb = CLASS_COLOURS[WordClass.ADVERB]
        alternate = CLASS_ALTERNATES[WordClass.ADVERB][0]
        assert f"color:{adverb}" not in legend.labels.text()
        assert f"color:{alternate}" in legend.labels.text()
        window.close_settings()

        button = window.buttons["links"]
        qapp.sendEvent(button, QEvent(QEvent.Type.Enter))
        window.tips._show()
        assert "Noun" in window.tips.label.text()
        assert "Class unavailable" in window.tips.label.text()
        assert window.tips.label.isVisible()
        assert f"color:{adverb}" not in window.tips.label.text()
        assert f"color:{alternate}" in window.tips.label.text()

        paper = BY_KEY["paper"]
        window.set_look(
            replace(
                window.look,
                original=paper.original,
                translation=paper.translation,
                background=paper.background,
                opacity=paper.opacity,
            )
        )
        window.tips._show()
        assert (
            f"color:{CLASS_ALTERNATES[WordClass.ADVERB][2]}" in window.tips.label.text()
        )
        assert f"color:{adverb}" not in window.tips.label.text()
    finally:
        window.close()


def test_class_marks_keep_the_palette_over_white_at_default_panel_opacity() -> None:
    for pos, swatch in CLASS_COLOURS.items():
        assert class_colour(pos, "#0a0c10", 0.72, "#ffffff") == swatch
        assert contrast(swatch, "#4f5053") >= CLASS_CONTRAST


def test_settings_word_links_has_the_same_legend(qapp: QApplication) -> None:
    panel = WordLinksPanel(
        LookView(CaptionLook(colour_links_by_word_class=True)), learning=True
    )
    try:
        panel.show()
        legend = panel.findChild(WordClassLegend)
        assert legend is not None
        assert legend.button.focusPolicy() != Qt.FocusPolicy.NoFocus
        QTest.keyClick(legend.button, Qt.Key.Key_Space)
        assert legend.labels.isVisible()
        assert "Particle, connector or interjection" in legend.labels.text()
    finally:
        panel.close()
