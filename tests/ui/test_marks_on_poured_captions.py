"""Learning load's colours and the marks under words sit on the right
words when captions fill the width (polyglotic-hq 309 with 324 and 323,
then 489's colours): a poured row keeps its own text and layout, so a
mark - by row and character - is drawn where the pour put those
characters, on whichever line. Offscreen, a made-up line, painted into
an image and read back."""

from collections import Counter

import pytest
from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QTextCharFormat, QTextLayout
from PySide6.QtWidgets import QApplication
from tests.ui.test_learning_load_view import SPANS, entry, learner, on, shown

from polyglotic_desktop.core.learning.highlights import WordIntroductions
from polyglotic_desktop.core.listening.display import WordLinks
from polyglotic_desktop.core.shared import WordStatus
from polyglotic_desktop.ui.learning import LearningTools
from polyglotic_desktop.ui_next.caption_layout import (
    CaptionLayout,
    CaptionStyle,
    Ink,
    LaidLine,
    drawn_whole,
    span_rects,
)
from polyglotic_desktop.ui_next.caption_marks import CaptionMarks
from polyglotic_desktop.ui_next.views.known_colours import known_colour
from polyglotic_desktop.ui_next.views.lab import Fill

AT = QPointF(10.0, 10.0)
SHARE = 0.6
"""The window's width as a share of the line's, as its own font draws it:
its words go over two poured lines whatever the font (Linux's draws it
narrower than a fixed width that wrapped it on Windows)."""


def told_apart(tools: LearningTools) -> dict[str, QColor]:
    """Three words set apart - said new, just past the line, said known -
    each in its colour on Classic's panel; the two commonest are as known."""
    tools.vocabulary.set_status(entry(tools, "研究"), WordStatus.NEW)
    tools.vocabulary.set_status(entry(tools, "电脑"), WordStatus.KNOWN)
    panel = on()
    found = {}
    for word in ("研究", "游戏", "电脑"):
        chance = tools.vocabulary.chances.of(tools.words_in(word)[0].entry)
        assert chance is not None
        found[word] = QColor(
            known_colour(chance.chance, panel.palette, panel.background)
        )
    return found


def narrow(engine: CaptionLayout) -> int:
    row = engine.laid(shown(), 4000, 1.0).rows[0]
    return max(40, int(row.layout.lineAt(0).naturalTextWidth() * SHARE))


def near(pixel: QColor, colour: QColor) -> bool:
    return (
        abs(pixel.red() - colour.red())
        + abs(pixel.green() - colour.green())
        + abs(pixel.blue() - colour.blue())
    ) < 60


def painted(engine: CaptionLayout, marks: CaptionMarks) -> tuple[QImage, LaidLine]:
    line = shown()
    width = narrow(engine)
    laid = engine.laid(line, width, 1.0)
    image = QImage(width + 20, int(laid.height) + 20, QImage.Format.Format_ARGB32)
    image.fill(QColor("#101014"))
    painter = QPainter(image)
    ink = Ink(QColor("#ffffff"), QColor("#ffffff"))
    engine.paint(painter, line, laid, AT, ink, marks)
    painter.end()
    return image, laid


def count(image: QImage, rects: list[QRectF], top: float, colour: QColor) -> int:
    found = 0
    for rect in rects:
        # in from its sides: a neighbour's glyph may reach a pixel over
        box = (
            rect.adjusted(2, 0, -2, 0).translated(AT.x(), AT.y() + top).toAlignedRect()
        )
        for y in range(box.top(), box.bottom() + 1):
            for x in range(box.left(), box.right() + 1):
                if image.rect().contains(x, y) and near(image.pixelColor(x, y), colour):
                    found += 1
    return found


def seen(image: QImage, rects: list[QRectF], top: float) -> str:
    """The commonest colours in `rects` but the background's, for a failure
    to say what was drawn instead (polyglotic-hq 420: on GitHub's Mac a
    word had none of its stage's colour)."""
    found: Counter[str] = Counter()
    for rect in rects:
        box = rect.translated(AT.x(), AT.y() + top).toAlignedRect()
        for y in range(box.top(), box.bottom() + 1):
            for x in range(box.left(), box.right() + 1):
                if image.rect().contains(x, y):
                    found[image.pixelColor(x, y).name()] += 1
    found.pop("#101014", None)
    return ", ".join(f"{name} x{n}" for name, n in found.most_common(4)) or "none"


@pytest.mark.parametrize("fill", [Fill.STACKED, Fill.PAIRED])
def test_a_words_colour_is_on_it_wherever_the_pour_put_it(
    qapp: QApplication, fill: Fill
) -> None:
    tools = learner()
    wanted = told_apart(tools)
    marks = CaptionMarks(tools)
    marks.set_look(WordLinks.OFF, WordIntroductions.A_FEW, on())
    image, laid = painted(CaptionLayout(CaptionStyle(fill=fill)), marks)
    assert laid.poured
    row = next(row for row in laid.rows if row.index == 0)
    assert row.layout.lineCount() > 1  # the row is over more than one poured line
    tops: set[int] = set()
    for word, colour in wanted.items():
        rects = span_rects(row.layout, *SPANS[word])
        tops.update(round(rect.top()) for rect in rects)
        assert count(image, rects, row.top, colour) > 8, (  # in its colour
            word,
            colour.name(),
            rects,
            seen(image, rects, row.top),
            [(start, end) for start, end, _ in marks(shown(), 0)],
        )
        for other_word, other in wanted.items():
            if other_word != word:  # and no other word's colour on it
                assert count(image, rects, row.top, other) == 0, (word, other_word)
    assert len(tops) > 1  # the coloured words aren't all on one line
    for word in ("这个", "人"):  # as known as 电脑: in its colour, on any line
        rects = span_rects(row.layout, *SPANS[word])
        assert count(image, rects, row.top, wanted["电脑"]) > 5
        assert not count(image, rects, row.top, wanted["研究"])


def test_the_marks_are_the_same_poured_or_in_rows(qapp: QApplication) -> None:
    """By row and character, whatever the fill: what 323's and 324's marks
    say doesn't change - only where the characters are."""
    tools = learner()
    marks = CaptionMarks(tools)
    marks.set_look(WordLinks.OFF, WordIntroductions.EVERY, on())
    line = shown()
    said = [(s, e) for s, e, _ in marks(line, 0)]
    for fill in Fill:
        engine = CaptionLayout(CaptionStyle(fill=fill))
        width = narrow(engine)
        laid = engine.laid(line, width, 1.0)
        row = next(row for row in laid.rows if row.index == 0)
        for start, end in said:  # each marked word has somewhere it's drawn
            rects = span_rects(row.layout, start, end)
            assert rects and all(
                r.width() > 4 and r.right() <= width + 1.5 for r in rects
            )


def test_the_word_after_one_split_over_two_lines_keeps_its_colour(
    qapp: QApplication,
) -> None:
    """Polyglotic-hq 420: Qt drew a coloured range over a line break with a
    region that reached the next word, and skipped that word's colour as
    already drawn: 游戏 after 电脑 split over two lines was drawn plain, on
    Windows at some widths and on GitHub's Mac (电脑 itself there). Every
    width that splits 电脑 with 游戏 whole on the next line is tried."""
    tools = learner()
    yellow = told_apart(tools)["游戏"]
    marks = CaptionMarks(tools)
    marks.set_look(WordLinks.OFF, WordIntroductions.A_FEW, on())
    engine = CaptionLayout(CaptionStyle(fill=Fill.STACKED))
    widest = int(
        engine.laid(shown(), 4000, 1.0).rows[0].layout.lineAt(0).naturalTextWidth()
    )
    tried = 0
    for width in range(40, widest, 2):
        laid = engine.laid(shown(), width, 1.0)
        row = next(row for row in laid.rows if row.index == 0)
        split = len(span_rects(row.layout, *SPANS["电脑"])) == 2
        game = span_rects(row.layout, *SPANS["游戏"])
        if not split or len(game) != 1:
            continue
        tried += 1
        image = QImage(width + 20, int(laid.height) + 20, QImage.Format.Format_ARGB32)
        image.fill(QColor("#101014"))
        painter = QPainter(image)
        ink = Ink(QColor("#ffffff"), QColor("#ffffff"))
        engine.paint(painter, shown(), laid, AT, ink, marks)
        painter.end()
        assert count(image, game, row.top, yellow) > 8, (
            width,
            seen(image, game, row.top),
        )
    assert tried


@pytest.mark.parametrize("spacing", [0.0, 0.3, 0.421875])
def test_coloured_words_side_by_side_are_each_drawn_in_their_colour(
    qapp: QApplication, spacing: float
) -> None:
    """Polyglotic-hq 420: Qt skipped a coloured range whose region, rounded
    out to whole pixels, overlapped the one before it - so with fractional
    advances (a Mac's font; here letter spacing makes them) the middle of
    three coloured words was drawn plain."""
    font = QFont()
    font.setPixelSize(22)
    font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, spacing)
    layout = QTextLayout("AAAABBBBCCCC", font)
    layout.beginLayout()
    line = layout.createLine()
    line.setLineWidth(1000)
    layout.endLayout()
    colours = [QColor("#ff6b5e"), QColor("#ffa033"), QColor("#f5e050")]
    selections = []
    for n, colour in enumerate(colours):
        format_ = QTextCharFormat()
        format_.setForeground(colour)
        selection = QTextLayout.FormatRange()
        selection.start, selection.length, selection.format = 4 * n, 4, format_
        selections.append(selection)
    drawn_whole(selections)
    image = QImage(400, 40, QImage.Format.Format_ARGB32)
    image.fill(QColor("#101014"))
    painter = QPainter(image)
    painter.setPen(QColor("#ffffff"))
    layout.draw(painter, AT, selections)
    painter.end()
    for n, colour in enumerate(colours):
        word = span_rects(layout, 4 * n, 4 * n + 4)
        assert count(image, word, 0.0, colour) > 8, (spacing, n)
