"""A word link's underline is drawn below the descenders, never through
them, and its thickness and gap are the learner's (the user's rehearsal
feedback F14, polyglotic-hq 249, 2026-11-08: "word link underline gets
covered partly by characters, users should be able to customise the
thickness of this"). Painted offscreen, in English and Chinese, at 100 %
and 200 % text. (Here beside test_caption_marks: the made-up captions are
`ui.recorded_captions`'.)"""

from dataclasses import replace

import pytest
from PySide6.QtCore import QPointF
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QApplication

from polyglotic_desktop.core.learning.highlights import WordIntroductions
from polyglotic_desktop.core.listening.captions import Language
from polyglotic_desktop.core.listening.display import (
    DisplayOptions,
    LinkGap,
    LinkLine,
    WordLinks,
)
from polyglotic_desktop.main import caption_look, look_settings
from polyglotic_desktop.ui.recorded_captions import APP, clause, finished
from polyglotic_desktop.ui.settings import AppSettings
from polyglotic_desktop.ui_next.caption_layout import (
    LINK_GAP_PX,
    LINK_PX,
    CaptionLayout,
    CaptionStyle,
    Ink,
    Mark,
)
from polyglotic_desktop.ui_next.caption_marks import CaptionMarks
from polyglotic_desktop.ui_next.caption_window import caption_style
from polyglotic_desktop.ui_next.panels import WordLinksPanel
from polyglotic_desktop.ui_next.views.caption_window import CaptionLook
from polyglotic_desktop.ui_next.views.captions import CaptionLines, Line

EN = Language("en")
RED = QColor("#ff0000")
TEXT = (
    # descenders under every linked word: g, y, p and 的's, 你's peers
    ("一个游戏", "a playing game", (("游戏", "playing game"),)),
    ("我的电脑", "My gypsy pug", (("电脑", "gypsy pug"),)),
)


def _line(chinese: str, english: str, pairs: tuple[tuple[str, str], ...]) -> Line:
    view = CaptionLines(
        (APP,), EN, keep=10, options=DisplayOptions(word_links=WordLinks.COLOURS)
    )
    view.apply(finished("a", clause(chinese, english, pairs)))
    return view.lines[0]


def _red_marks(line: Line, row: int) -> list[Mark]:
    marks = CaptionMarks(None)
    marks.set_look(WordLinks.COLOURS, WordIntroductions.A_FEW)
    found = []
    for start, end, format_ in marks(line, row):
        format_ = type(format_)(format_)
        format_.setUnderlineColor(RED)
        found.append((start, end, format_))
    return found


def _painted(line: Line, style: CaptionStyle, text_size: float) -> QImage:
    engine = CaptionLayout(style)
    laid = engine.laid(line, 900, text_size)
    image = QImage(920, int(laid.height) + 40, QImage.Format.Format_ARGB32)
    image.fill(QColor("#000000"))
    painter = QPainter(image)
    engine.paint(
        painter,
        line,
        laid,
        QPointF(10, 10),
        Ink(QColor("#ffffff"), QColor("#ffffff")),
        _red_marks,
    )
    painter.end()
    return image


def _rows_with(image: QImage, wanted: str) -> list[int]:
    """The pixel rows with red (an underline) or white (a glyph) in them."""
    found = []
    for y in range(image.height()):
        for x in range(0, image.width(), 1):
            c = image.pixelColor(x, y)
            red = c.red() > 200 and c.green() < 60 and c.blue() < 60
            white = c.red() > 120 and c.green() > 120 and c.blue() > 120
            if (wanted == "red" and red) or (wanted == "white" and white):
                found.append(y)
                break
    return found


def _bands(rows: list[int]) -> list[tuple[int, int]]:
    """Runs of consecutive pixel rows: (first, last)."""
    bands: list[tuple[int, int]] = []
    for y in rows:
        if bands and y == bands[-1][1] + 1:
            bands[-1] = (bands[-1][0], y)
        else:
            bands.append((y, y))
    return bands


@pytest.mark.parametrize("translation_size", [1.0, 0.5, 2.0])
@pytest.mark.parametrize("text_size", [1.0, 2.0])
@pytest.mark.parametrize("words", TEXT)
def test_the_underline_is_below_the_descenders_never_through_them(
    qapp: QApplication,
    text_size: float,
    words: tuple[str, str, tuple[tuple[str, str], ...]],
    translation_size: float,
) -> None:
    """At every text size, and with the translation at half and twice what
    was said (polyglotic-hq 305)."""
    line = _line(*words)
    image = _painted(
        line,
        caption_style(
            replace(CaptionLook(), word_links=WordLinks.COLOURS), translation_size
        ),
        text_size,
    )
    red = _bands(_rows_with(image, "red"))
    white = _bands(_rows_with(image, "white"))
    # both rows' glyphs drawn: fonts with Chinese (tests/conftest.py, 258)
    assert len(white) == 2, white
    assert len(red) == 2  # the Chinese row's link, and the English row's
    for top, _ in red:
        # the glyphs just above it end before it starts: a gap, no overlap
        above = [band for band in white if band[0] < top]
        assert above and above[-1][1] < top - 0, (red, white)


def test_thickness_and_gap_are_the_learner_s(qapp: QApplication) -> None:
    line = _line(*TEXT[0])
    looks = [
        replace(CaptionLook(), word_links=WordLinks.COLOURS, link_line=w, link_gap=g)
        for w, g in (
            (LinkLine.THIN, LinkGap.CLOSE),
            (LinkLine.MEDIUM, LinkGap.MEDIUM),
            (LinkLine.THICK, LinkGap.FAR),
        )
    ]
    thick = []
    for look in looks:
        style = caption_style(look)
        assert (style.link_px, style.link_gap) == (
            LINK_PX[look.link_line],
            LINK_GAP_PX[look.link_gap],
        )
        red = _bands(_rows_with(_painted(line, style, 2.0), "red"))
        thick.append(red[-1][1] - red[-1][0])
    assert thick[0] < thick[1] < thick[2]
    gaps = [LINK_GAP_PX[g] for g in LinkGap]
    assert gaps == sorted(gaps)


def test_rows_make_room_for_it_only_while_links_are_underlined() -> None:
    plain = caption_style(CaptionLook())
    assert not plain.link_room
    for links in (WordLinks.COLOURS, WordLinks.ARROWS):
        assert caption_style(replace(CaptionLook(), word_links=links)).link_room
    assert not caption_style(
        replace(CaptionLook(), word_links=WordLinks.HOVER)
    ).link_room


def test_the_choices_are_kept_with_the_settings() -> None:
    assert (AppSettings().link_line, AppSettings().link_gap) == ("medium", "medium")
    stored = AppSettings(link_line="thick", link_gap="far").to_stored()
    back = AppSettings.from_stored(stored)
    look = caption_look(back)
    assert (look.link_line, look.link_gap) == (LinkLine.THICK, LinkGap.FAR)
    assert look_settings(look)["link_line"] == "thick"
    assert AppSettings.from_stored({"link_line": "huge"}).link_line == "medium"


def test_the_word_links_panel_offers_them_with_underlined_links(
    qapp: QApplication,
) -> None:
    from polyglotic_desktop.ui_next.views.panels import LookView

    view = LookView(CaptionLook())
    panel = WordLinksPanel(view)
    assert not panel.link_line.isEnabled() and not panel.link_gap.isEnabled()
    view.set_word_links(WordLinks.COLOURS)
    assert panel.link_line.isEnabled() and panel.link_gap.isEnabled()
    panel.link_line.buttons[2].click()
    panel.link_gap.buttons[0].click()
    assert (view.value.link_line, view.value.link_gap) == (
        LinkLine.THICK,
        LinkGap.CLOSE,
    )
