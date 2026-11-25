"""Reading lines (polyglotic-hq 364, 369; decision 0155): room for pinyin
above Chinese in today's clause rows and in the one layout. The text is
the same text - every character in a line, found and looked up by its row
and character as before - taller by a band, with the room a wider reading
needs; a reading reaches over a narrower neighbour's room; with the line
off, nothing changes. Offscreen, made-up captions and readings."""

from collections.abc import Sequence

import pytest
from PySide6.QtCore import QPointF
from PySide6.QtGui import QFont, QFontMetricsF
from PySide6.QtWidgets import QApplication
from tests.ui_next.made_up import EN
from tests.ui_next.test_flow import PAIRED, ROWS, Pitch, one

from polyglotic_desktop.core.lexicon.chinese import is_han
from polyglotic_desktop.core.lexicon.readings import Reading
from polyglotic_desktop.core.listening.captions import Language
from polyglotic_desktop.core.listening.display import RowKind
from polyglotic_desktop.ui.recorded_captions import APP, CONTROLS, GAME, finished
from polyglotic_desktop.ui_next import reading_lines
from polyglotic_desktop.ui_next.caption_layout import (
    CaptionLayout,
    CaptionStyle,
    LaidLine,
    char_under,
    cursor_x,
)
from polyglotic_desktop.ui_next.views.captions import CaptionLines, Line
from polyglotic_desktop.ui_next.views.flow import Above, Flow, FlowOptions

ZH = frozenset({"zh"})
SYLLABLES = ("zhuāng", "yī", "shuǎng", "de", "nǚ")


def made_up(text: str, language: str | None) -> Sequence[Reading]:
    """A syllable over each Chinese character, long and short by turns,
    every third the last of its word."""
    return [
        Reading(n, n + 1, SYLLABLES[n % 5], n % 3 == 2)
        for n, char in enumerate(text)
        if is_han(char)
    ]


def lines_of(*updates: object) -> CaptionLines:
    view = CaptionLines((APP,), EN, keep=20)
    view.set_models(True)
    for update in updates:
        view.apply(update)  # type: ignore[arg-type]
    return view


def laid_both(
    flow: FlowOptions | None, width: int = 420
) -> tuple[Line, LaidLine, LaidLine]:
    (line,) = lines_of(finished("a", GAME, CONTROLS)).lines
    plain = CaptionLayout(CaptionStyle(flow=flow), readings=made_up).laid(
        line, width, 1.0
    )
    read = CaptionLayout(
        CaptionStyle(flow=flow, reading_lines=ZH), readings=made_up
    ).laid(line, width, 1.0)
    return line, plain, read


# -- the composer ----------------------------------------------------------------------


def test_the_composer_gives_a_unit_the_room_its_reading_needs() -> None:
    """A side with a reading line is measured wider and its lines taller;
    the side without one is as it was."""
    captions = one(GAME)

    def above(side: RowKind, language: Language | None, text: str) -> Above | None:
        if side is not RowKind.ORIGINAL:
            return None
        return Above([3.0] * len(text), [3.0] * len(text), 12.0)

    plain = Flow(Pitch()).compose(captions, 900, ROWS)
    read = Flow(Pitch(), above=above).compose(captions, 900, ROWS)
    characters = len(captions[0].clauses[0].original)
    assert read.lines[0].end == pytest.approx(plain.lines[0].end + 6.0 * characters)
    assert read.lines[0].ascent == plain.lines[0].ascent + 12.0
    assert read.lines[1].end == plain.lines[1].end  # the translation: untouched
    assert read.height == plain.height + 12.0


def test_a_line_with_readings_holds_fewer_characters_and_none_twice() -> None:
    captions = one(GAME, CONTROLS)

    def above(side: RowKind, language: Language | None, text: str) -> Above | None:
        if side is not RowKind.ORIGINAL:
            return None
        return Above([5.0] * len(text), [5.0] * len(text), 12.0)

    flowed = Flow(Pitch(), above=above).compose(captions, 300, PAIRED)
    seen: set[tuple[int, int]] = set()
    for line in flowed.lines:
        assert line.end <= 300.5
        for run in line.runs:
            if run.words.side is RowKind.ORIGINAL:
                for char in range(run.words.start, run.words.end):
                    assert (run.words.clause, char) not in seen
                    seen.add((run.words.clause, char))
    assert len(seen) == sum(len(c.original) for c in captions[0].clauses)


# -- the room --------------------------------------------------------------------------


def font(px: int = 28) -> QFont:
    found = QFont()
    found.setFamilies(["Microsoft YaHei", "Noto Sans CJK SC", "Sans Serif"])
    found.setPixelSize(px)
    return found


def test_a_wide_reading_takes_room_on_both_sides_and_a_line_start_is_safe(
    qapp: QApplication,
) -> None:
    """张 alone, read zhuāng: room each side of it, enough that a line
    starting at it is drawn its reading's overhang in."""
    big = font()
    measured = reading_lines.ruby("张", [Reading(0, 1, "zhuāng")], big)
    wide = QFontMetricsF(measured.font).horizontalAdvance("zhuāng")
    under = QFontMetricsF(big).horizontalAdvance("张")
    assert wide > under  # the case under test
    assert measured.before[0] == pytest.approx((wide - under) / 2)
    assert measured.after[0] == pytest.approx((wide - under) / 2)
    assert measured.band > 0


def test_a_reading_reaches_over_a_narrower_neighbours_room(qapp: QApplication) -> None:
    """张的 read zhuāng de, one word: de is narrower than 的, so zhuāng
    reaches over the room it leaves - less room between the two than if
    each reading kept to its own half (364's pictures: "什么 都")."""
    big = font()
    two = reading_lines.ruby(
        "张的", [Reading(0, 1, "zhuāng", False), Reading(1, 2, "de")], big
    )
    metrics, base = QFontMetricsF(two.font), QFontMetricsF(big)
    wide = (metrics.horizontalAdvance("zhuāng") - base.horizontalAdvance("张")) / 2
    narrow = (metrics.horizontalAdvance("de") - base.horizontalAdvance("的")) / 2
    assert narrow < 0 < wide
    pad = reading_lines.PAD * two.font.pixelSize()
    between = two.after[0] + two.before[1]
    assert between == pytest.approx(max(0.0, wide + pad + narrow))
    assert between < wide + pad  # 364 gave it its whole overhang and pad
    # the readings still don't touch: centred, with the pad between them
    assert (
        base.horizontalAdvance("张") / 2 + between + base.horizontalAdvance("的") / 2
        >= (metrics.horizontalAdvance("zhuāng") + metrics.horizontalAdvance("de")) / 2
    )


def test_a_words_last_reading_leaves_a_little_more_room(qapp: QApplication) -> None:
    big = font()
    readings = [Reading(0, 1, "yī", False), Reading(1, 2, "yī")]
    joined = reading_lines.ruby("一一", readings, big)
    apart = reading_lines.ruby("一一", [Reading(0, 1, "yī"), readings[1]], big)
    px = joined.font.pixelSize()
    assert apart.after[0] + apart.before[1] == pytest.approx(
        joined.after[0] + joined.before[1] + reading_lines.WORD_GAP * px, abs=0.6
    )


# -- the engine ------------------------------------------------------------------------


@pytest.mark.parametrize("flow", [None, ROWS, PAIRED], ids=["today", "rows", "paired"])
def test_the_text_is_the_same_text_with_its_reading_line(
    qapp: QApplication, flow: FlowOptions | None
) -> None:
    """Every character still in a line, in order, inside the width; taller
    by the readings' band; and the word under the mouse is found by its
    row and character as before."""
    width = 420
    line, plain, read = laid_both(flow, width)
    assert read.height > plain.height
    for laid in (plain, read):
        for index, source in enumerate(line.rows):
            # Reading guides can change a break. Every fragment must still
            # start at the next source character and together cover the row.
            cursor = 0
            for fragment in (row for row in laid.rows if row.index == index):
                assert fragment.start == cursor
                cursor += len(fragment.row.text)
                assert fragment.row.text == source.text[fragment.start : cursor]
            assert cursor == len(source.text)
    for row in read.rows:
        covered = 0
        for n in range(row.layout.lineCount()):
            text_line = row.layout.lineAt(n)
            assert text_line.textStart() == covered
            covered += text_line.textLength()
            box = text_line.naturalTextRect()
            assert box.right() <= width + 1.0
        display = row.row.text.rstrip() + "..." if row.continues else row.row.text
        assert row.layout.text() == display
        assert covered == len(display)
    said = next(row for row in read.rows if row.row.kind is RowKind.ORIGINAL)
    text_line = said.layout.lineAt(0)
    for index in (0, 3, 5):
        middle = (cursor_x(text_line, index) + cursor_x(text_line, index + 1)) / 2
        at = QPointF(10 + middle - 2, 10 + said.top + text_line.y() + 6)
        found = char_under([(said, QPointF(10, 10))], at)
        assert found is not None and found[2] == index


@pytest.mark.parametrize("flow", [None, ROWS, PAIRED], ids=["today", "rows", "paired"])
def test_nothing_changes_with_the_line_off_or_no_readings_given(
    qapp: QApplication, flow: FlowOptions | None
) -> None:
    (line,) = lines_of(finished("a", GAME)).lines
    off = CaptionLayout(CaptionStyle(flow=flow), readings=made_up).laid(line, 600, 1.0)
    other = CaptionLayout(
        CaptionStyle(flow=flow, reading_lines=frozenset({"ja"})), readings=made_up
    ).laid(line, 600, 1.0)
    none = CaptionLayout(CaptionStyle(flow=flow, reading_lines=ZH)).laid(line, 600, 1.0)
    for laid in (other, none):
        assert laid.height == off.height
        assert [r.layout.lineAt(0).naturalTextWidth() for r in laid.rows] == [
            r.layout.lineAt(0).naturalTextWidth() for r in off.rows
        ]


def test_readings_not_ready_yet_are_asked_for_again(qapp: QApplication) -> None:
    """While the dictionary is still being read the source says None: the
    row is laid without a reading line, and nothing is kept against it."""
    (line,) = lines_of(finished("a", GAME)).lines
    ready = False
    engine = CaptionLayout(
        CaptionStyle(reading_lines=ZH),
        readings=lambda text, language: made_up(text, language) if ready else None,
    )
    plain = engine.laid(line, 600, 1.0).height
    ready = True
    assert engine.laid(line, 601, 1.0).height > plain


@pytest.mark.parametrize("flow", [None, ROWS, PAIRED], ids=["today", "rows", "paired"])
def test_a_line_keeps_its_readings_band_when_none_of_its_words_has_one(
    qapp: QApplication, flow: FlowOptions | None
) -> None:
    """A live caption's text would move down when its first reading came."""
    (line,) = lines_of(finished("a", GAME)).lines
    every = CaptionLayout(
        CaptionStyle(flow=flow, reading_lines=ZH), readings=made_up
    ).laid(line, 600, 1.0)
    none = CaptionLayout(
        CaptionStyle(flow=flow, reading_lines=ZH), readings=lambda text, lang: ()
    ).laid(line, 600, 1.0)
    off = CaptionLayout(CaptionStyle(flow=flow)).laid(line, 600, 1.0)
    assert none.height == pytest.approx(every.height)
    assert none.height > off.height
