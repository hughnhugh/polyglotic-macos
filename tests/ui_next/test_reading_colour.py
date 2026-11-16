"""Pinyin's colour, and linked words in their link's colour (polyglotic-hq
395; the user's preview-1 feedback, 2026-11-16: "pinyin should have the
option of matching the word link colour (maybe it should be a word link
feature allowing all three pinyin, caption, translation to match the arrow
link colour) ... There should be option to customise pinyin colour").

Settings > Look's Pinyin group: "Pinyin colour: Same as its line / Its
word link's colour / Custom"; the Word links group: "Colour the linked
words too". Each saved; drawn in the link's colour, readable on every
preset's panel. Offscreen, made-up captions and the sample CC-CEDICT."""

from collections.abc import Iterator
from dataclasses import replace

import pytest
import shiboken6
from PySide6.QtCore import QPointF
from PySide6.QtGui import QColor, QFont, QImage, QPainter
from PySide6.QtWidgets import QApplication, QWidget
from tests.ui.fakes import chinese_tools
from tests.ui_next.test_caption_window import areas

from polyglotic_desktop.core.listening.display import ReadingColour, WordLinks
from polyglotic_desktop.core.listening.sources import SourceLabel
from polyglotic_desktop.main import caption_look, look_settings
from polyglotic_desktop.ui.recorded_captions import APP, MIC, finished
from polyglotic_desktop.ui.settings import AppSettings
from polyglotic_desktop.ui_next import reading_lines
from polyglotic_desktop.ui_next.caption_layout import (
    Ink,
    _coloured_words,
    _reading_colours,
    link_ink,
)
from polyglotic_desktop.ui_next.caption_marks import LINK_COLORS
from polyglotic_desktop.ui_next.caption_window import CaptionWindow, look_ink
from polyglotic_desktop.ui_next.panels import ReadingLinesPanel, WordLinksPanel
from polyglotic_desktop.ui_next.views.caption_window import CaptionLook, WindowChoices
from polyglotic_desktop.ui_next.views.panels import LookView
from polyglotic_desktop.ui_next.views.presets import AA_TEXT, PRESETS, _mix, contrast

MADE: list[QWidget] = []
ORANGE, VIOLET = QColor(LINK_COLORS[0]), QColor(LINK_COLORS[1])


@pytest.fixture(autouse=True)
def deleted() -> Iterator[None]:
    yield
    while MADE:
        made = MADE.pop()
        if shiboken6.isValid(made):
            made.close()
            shiboken6.delete(made)


def placed(*starts: int) -> tuple[reading_lines.Placed, ...]:
    return tuple(
        reading_lines.Placed(10.0 * n, 0.0, "yóu", start)
        for n, start in enumerate(starts)
    )


# -- the colours -----------------------------------------------------------------------


def test_pinyin_is_its_lines_colour_by_default() -> None:
    row = QColor("#ffd76e")
    links = [(0, 2, ORANGE, 0)]
    assert _reading_colours(placed(0, 1), links, Ink(), row) == []


def test_in_its_word_links_colour_where_a_link_joins_it_else_its_lines() -> None:
    """游戏 linked in orange, 的 not linked, 画面 in violet."""
    ink = Ink(reading_colour=ReadingColour.LINK)
    row = QColor("#ffd76e")
    links = [(0, 2, ORANGE, 0), (3, 5, VIOLET, 1)]
    found = _reading_colours(placed(0, 1, 2, 3, 4), links, ink, row)
    assert [c.name() if c else None for c in found] == [
        ORANGE.name(), ORANGE.name(), None, VIOLET.name(), VIOLET.name(),
    ]  # fmt: skip


def test_with_no_links_shown_its_lines_colour() -> None:
    ink = Ink(reading_colour=ReadingColour.LINK)
    assert _reading_colours(placed(0, 1), [], ink, QColor("#ffffff")) == []


def test_a_custom_colour_for_every_reading_as_faint_as_its_line() -> None:
    ink = Ink(reading_colour=ReadingColour.CUSTOM, reading=QColor("#9ad0ff"))
    row = QColor("#ffffff")
    row.setAlphaF(0.5)  # an older caption
    found = _reading_colours(placed(0, 1, 2), [(0, 1, ORANGE, 0)], ink, row)
    assert {c.name() for c in found if c} == {"#9ad0ff"}
    assert all(
        c is not None and c.alphaF() == pytest.approx(0.5, abs=0.01) for c in found
    )


def test_linked_words_take_their_links_colour() -> None:
    ink = Ink(link_words=True)
    ranges = _coloured_words(
        [(0, 2, ORANGE, 0), (3, 5, VIOLET, 1)], ink, QColor("#fff")
    )
    assert [
        (r.start, r.length, r.format.foreground().color().name()) for r in ranges
    ] == [
        (0, 2, ORANGE.name()),
        (3, 2, VIOLET.name()),
    ]


@pytest.mark.parametrize("preset", PRESETS, ids=lambda p: p.key)
@pytest.mark.parametrize("alpha", [1.0, 0.6], ids=["newest", "older"])
def test_every_link_colour_reads_on_every_presets_panel(
    preset: object, alpha: float
) -> None:
    """Readable over a game: a link's colour as a word or its pinyin is
    drawn in it - as faint as it's drawn (an older caption, a reading's
    own faintness) - reaches 4.5:1 on the panel drawn solid, on Paper's
    cream too, where the colours (picked for dark panels) are darkened.
    The lab's contrast check found 2.9:1 on Paper before (395)."""
    background = preset.background  # type: ignore[attr-defined]
    ink = Ink(panel=background)
    row = QColor("#ffffff")
    row.setAlphaF(alpha)
    for colour in LINK_COLORS:
        for faint in (1.0, reading_lines.ALPHA):
            drawn = link_ink(QColor(colour), ink, row, faint)
            seen = _mix(background, drawn.name(), drawn.alphaF() * faint)
            assert contrast(seen, background) >= AA_TEXT, (colour, background, faint)


def test_on_a_dark_panel_the_link_colours_are_as_they_are() -> None:
    ink = Ink(panel="#0a0c10")
    assert all(
        link_ink(QColor(c), ink, QColor("#ffffff")).name() == c for c in LINK_COLORS
    )


def test_readings_are_drawn_in_their_own_colours(qapp: QApplication) -> None:
    """`reading_lines.draw` with a colour per reading: the first in orange,
    the second in its row's white."""
    font = QFont()
    font.setPixelSize(20)
    readings = (
        reading_lines.Placed(4.0, 24.0, "hé", 0),
        reading_lines.Placed(60.0, 24.0, "hé", 1),
    )
    image = QImage(120, 32, QImage.Format.Format_ARGB32)
    image.fill(QColor("#000000"))
    painter = QPainter(image)
    reading_lines.draw(
        painter, readings, font, QPointF(0, 0), QColor("#ffffff"), [ORANGE, None]
    )
    painter.end()

    def hues(x0: int, x1: int) -> set[str]:
        found = set()
        for x in range(x0, x1):
            for y in range(32):
                c = image.pixelColor(x, y)
                if c.red() > 200 and c.green() > 120:
                    found.add("orange" if c.blue() < 120 else "white")
        return found

    assert hues(0, 50) == {"orange"}
    assert hues(56, 120) == {"white"}


# -- in a caption window ---------------------------------------------------------------


def test_a_caption_windows_ink_follows_the_look(qapp: QApplication) -> None:
    look = CaptionLook(
        word_links=WordLinks.COLOURS,
        reading_lines=("zh",),
        reading_colour=ReadingColour.LINK,
        link_words=True,
    )
    window = CaptionWindow(
        "Discord.exe", APP, WindowChoices(), SourceLabel("Discord", "#4dd0e1"),
        mic=MIC, areas=areas, learner=chinese_tools(),
    )  # fmt: skip
    MADE.append(window)
    window.set_look(look)
    window.view.apply(finished("a"))
    window.apply_changed(new_caption=True)
    window.show()
    qapp.processEvents()
    window.canvas.repaint()  # drawn with it, no error
    ink = window.canvas.ink
    assert ink.reading_colour is ReadingColour.LINK and ink.link_words
    assert ink.panel == look.background
    assert look_ink(Ink(), replace(look, reading_colour=ReadingColour.CUSTOM)).reading


# -- the settings ----------------------------------------------------------------------


def test_the_choices_are_saved_and_come_back() -> None:
    look = CaptionLook(
        reading_colour=ReadingColour.CUSTOM, reading_custom="#a5f28a", link_words=True
    )
    stored = AppSettings.from_stored(look_settings(look)).to_stored()
    back = caption_look(AppSettings.from_stored(stored))
    assert (back.reading_colour, back.reading_custom, back.link_words) == (
        ReadingColour.CUSTOM,
        "#a5f28a",
        True,
    )


def test_off_and_its_lines_colour_until_chosen_and_wrong_values_are_the_default() -> (
    None
):
    assert caption_look(AppSettings()).reading_colour is ReadingColour.SAME
    assert not caption_look(AppSettings()).link_words
    found = AppSettings.from_stored(
        {"reading_colour": "rainbow", "reading_custom_color": "blue"}
    )
    assert found.reading_colour == "same" and found.reading_custom_color == "#9ad0ff"


def test_the_pinyin_group_offers_the_three_and_custom_shows_its_colour(
    qapp: QApplication,
) -> None:
    view = LookView(CaptionLook(reading_lines=("zh",)))
    panel = ReadingLinesPanel(view, notes=True)
    MADE.append(panel)
    assert panel.custom_row.isHidden()
    panel.reading_colour.changed.emit(ReadingColour.LINK.value)
    assert view.value.reading_colour is ReadingColour.LINK
    assert panel.custom_row.isHidden()
    panel.reading_colour.changed.emit(ReadingColour.CUSTOM.value)
    assert not panel.custom_row.isHidden()
    panel.reading_custom.chosen.emit("#ff9ecf")  # a swatch, typed or picked
    assert view.value.reading_custom == "#ff9ecf"
    assert view.value.reading_colour is ReadingColour.CUSTOM
    view.set_reading_line("zh", False)
    assert not panel.reading_colour.isEnabled()  # pinyin off: nothing to colour


def test_the_word_links_group_colours_the_linked_words(qapp: QApplication) -> None:
    view = LookView(CaptionLook(word_links=WordLinks.COLOURS))
    panel = WordLinksPanel(view, notes=True)
    MADE.append(panel)
    assert not panel.link_words.isChecked()
    panel.link_words.click()
    assert view.value.link_words
    view.set_word_links(WordLinks.OFF)
    assert not panel.link_words.isEnabled()  # no links: nothing to colour
