"""Word links' Arrows is back: a curve from each linked word of what was
said down to its counterpart in the translation, in the link's colour (the
user's rehearsal feedback F7, polyglotic-hq 249, 2026-11-08: "The word
links doesn't have arrow settings anymore (I like this option)"). 151 had
retired it while a window underlined Arrows as Colours."""

from dataclasses import replace

import pytest
from PySide6.QtWidgets import QApplication
from tests.ui.test_link_underline import TEXT, _bands, _line, _painted, _rows_with

from polyglotic_desktop.core.listening.display import WordLinks
from polyglotic_desktop.ui_next.caption_layout import CaptionLayout
from polyglotic_desktop.ui_next.caption_window import caption_style
from polyglotic_desktop.ui_next.views.caption_window import CaptionLook

COLOURS = replace(CaptionLook(), word_links=WordLinks.COLOURS)
ARROWS = replace(CaptionLook(), word_links=WordLinks.ARROWS)


def test_arrows_make_room_and_colours_don_t(qapp: QApplication) -> None:
    assert caption_style(ARROWS).arrows and not caption_style(COLOURS).arrows
    hidden = replace(ARROWS, show_original=False)
    assert not caption_style(hidden).arrows  # needs what was said shown
    line = _line(*TEXT[0])
    plain = CaptionLayout(caption_style(COLOURS)).laid(line, 900, 1.0)
    roomy = CaptionLayout(caption_style(ARROWS)).laid(line, 900, 1.0)
    assert roomy.height > plain.height
    gap = roomy.rows[1].top - plain.rows[1].top
    assert gap > 10  # room for the curve to cross


@pytest.mark.parametrize("translation_size", [1.0, 0.5, 2.0])
def test_a_curve_crosses_from_each_word_to_its_counterpart(
    qapp: QApplication, translation_size: float
) -> None:
    """With the translation at half and twice what was said too
    (polyglotic-hq 305)."""
    for words in TEXT:
        line = _line(*words)
        for text_size in (1.0, 2.0):
            colours = _painted(
                line, caption_style(COLOURS, translation_size), text_size
            )
            arrows = _painted(line, caption_style(ARROWS, translation_size), text_size)
            # Colours: two underlines, each a bar's height of red rows
            plain = _bands(_rows_with(colours, "red"))
            assert len(plain) == 2
            assert all(last - first <= 5 * text_size for first, last in plain)
            # Arrows: the upper word's underline runs on down, a curve, to the
            # lower row - red all the way across the gap between the rows
            white = _bands(_rows_with(arrows, "white"))
            red = _bands(_rows_with(arrows, "red"))
            top = red[0][0]
            assert top > white[0][1]  # the underline, below the upper row
            reach = max(b[1] for b in red if b[0] <= red[0][1] + 4 * text_size)
            assert reach - top > 10 * text_size, (words[1], text_size, red)
            # to the lower row's top - its line's top, above its glyphs by
            # its font's own leading: twice as far for a translation twice
            # the size (305)
            lower = text_size * max(1.0, translation_size)
            assert reach >= white[1][0] - 8 * lower
