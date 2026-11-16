"""Reading lines over caption text: pinyin above Chinese (polyglotic-hq
364 and 369, decision 0155).

A reading (`core.lexicon.readings.Reading`) is drawn small above the
characters it reads, centred on them. Where it is wider than they are,
they get the room: the layout is told how much each character takes
(`Ruby.before`, `.after`; the one layout measures its units with it,
`views.flow.Above`), and Qt spaces the characters by the same amounts
(`spaced`), so a word is still found, marked, selected and looked up by
its row and character - a reading line changes where text is, never what
it is. A reading may reach over its neighbour's character where that
one's reading is narrower than it, so characters keep their own spacing
where they can (369). A word's last reading is followed by a little more
room (`WORD_GAP`), so the words show in a script written without spaces.

Which languages have their line on is the caption style's
(`CaptionStyle.reading_lines`); where readings come from is the caption
layout's `readings` - the Chinese dictionary's word split and everyday
readings, on this PC: nothing is sent anywhere for it.

Holds caption text's sound in what it lays out: never log it.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from PySide6.QtCore import QPointF
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetricsF,
    QPainter,
    QTextCharFormat,
    QTextLayout,
)

from polyglotic_desktop.core.lexicon.chinese import ChineseDictionary
from polyglotic_desktop.core.lexicon.readings import Reading, Readings
from polyglotic_desktop.core.listening.display import READING_LANGUAGES, ReadingSize
from polyglotic_desktop.core.shared import EntryFacts
from polyglotic_desktop.ui_next.views.lookup import Learner

SHARE = 0.5
"""A reading's text size, as a share of the text it is over (Small)."""
SHARES = {ReadingSize.SMALL: SHARE, ReadingSize.MEDIUM: 0.62}
"""Each size a learner can choose, as that share: Medium for a small
window or a small text size, where Small's tone marks are hard to tell
apart (both never under `SMALLEST_PX`)."""
SMALLEST_PX = 10
"""Never smaller than this: tone marks stop being told apart."""
PAD = 0.3
"""The least room between two readings, as a share of their text size."""
WORD_GAP = 0.45
"""More room after a word's last reading, the same way."""
LIFT = 0.05
"""How far a reading sits above its text's line box, as a share of its
text size: a CJK font's own room above its glyphs is nearly enough."""
ALPHA = 0.92
"""A reading is drawn this much fainter than its text: the text leads."""


def language_of(language: str | None) -> str | None:
    """The reading line a row in `language` can have - its language's
    first part ("zh-hant": "zh") - None if none."""
    if language is None:
        return None
    first = language.split("-")[0]
    return first if first in READING_LANGUAGES else None


def source_of(learner: Learner, past: bool = False) -> Readings:
    """Where a caption window's readings come from: pinyin from the
    Chinese dictionary on this PC (a learner's, `Learner.of`), once its
    word split's data is read - never read here, on the interface's
    thread (None: ask again when `dictionary_ready`). Nothing for a
    language without a reading line; None, too, without a Chinese
    dictionary open (Chinese not learned): ask again.
    `past`: only over the words past what the learner knows - the words
    word links "past what I know" link (decision 0130; `past_only`)."""

    def read(text: str, language: str | None) -> Sequence[Reading] | None:
        if language_of(language) is None:
            return ()
        dictionary = reader(learner, language)
        if dictionary is None:
            # Chinese not learned, so no Chinese dictionary open: no reading
            # line, and no room kept for one (395: an empty band over a
            # translation into Chinese) - asked again on the next layout
            return None
        if not dictionary.ready:
            return None
        found = dictionary.readings(text)
        return past_only(learner, text, language, found) if past and found else found

    return read


def past_only(
    learner: Learner, text: str, language: str | None, readings: Sequence[Reading]
) -> list[Reading]:
    """`readings` without those over a word the learner knows (`knows`)."""
    known = knows(learner, language)
    if known is None:
        return list(readings)
    spans = [
        (word.start, word.end)
        for word in learner.words_in(text, language)
        if known(word.entry)
    ]
    return [
        reading
        for reading in readings
        if not any(start <= reading.start < end for start, end in spans)
    ]


def knows(
    learner: Learner, language: str | None
) -> Callable[[EntryFacts], bool] | None:
    """Whether the learner knows a word of `language`: one they set known
    or ignored, or one up to their known line (where links start, if they
    moved it) - as word links judge it (`Vocabulary.needs_no_link`). None
    where no dictionary on this PC knows the language's words.

    Stands in for polyglotic-hq 373's one known-words model: once
    `Learner.knowledge_of(language)` is on main, this is
    `knowledge.of(facts).known` (DECISIONS #177's train; the orchestrator,
    2026-11-16)."""
    ours = learner.of(language)  # its own language's tools, as links (306)
    if not ours.learns(language):
        return None
    choices = learner.choices_of(language)
    links_from = choices.links_from if choices is not None else None
    return lambda facts: ours.vocabulary.needs_no_link(facts, links_from)


def reader(learner: Learner, language: str | None) -> ChineseDictionary | None:
    """The dictionary that reads a row in `language` on this PC, if one
    does: the learner's Chinese dictionary, for Chinese."""
    if language_of(language) != "zh":
        return None
    dictionary = learner.of(language).dictionary
    return dictionary if isinstance(dictionary, ChineseDictionary) else None


@dataclass(frozen=True, slots=True)
class Ruby:
    """A text's readings, measured for one font: the room each character
    takes with them (`before`, `after`: pixels each side of it - `before`
    is all a line starting at it needs, so a reading is never cut at the
    window's edge), the height they need above a line (`band`), their
    font, and each reading's own width and its characters'."""

    readings: tuple[Reading, ...]
    before: tuple[float, ...]
    after: tuple[float, ...]
    band: float
    font: QFont
    widths: tuple[float, ...]
    base: tuple[float, ...]
    drop: float
    """How far above a line's top a reading's baseline is."""
    spacing: tuple[tuple[int, int, float], ...]
    """The room as Qt is given it (`spaced`): Qt's index of a character,
    its length there, and the room after it."""

    def room(self, start: int, end: int) -> float:
        return sum(self.before[start:end]) + sum(self.after[start:end])


_WIDTHS: dict[str, dict[str, float]] = {}
"""By font: the widths measured in it - a caption's syllables and
characters come again and again."""
WIDTHS_KEPT = 6000


def _measure(font: QFont) -> tuple[dict[str, float], QFontMetricsF]:
    key = font.key()
    kept = _WIDTHS.get(key)
    if kept is None:
        if len(_WIDTHS) > 24:
            _WIDTHS.clear()
        kept = _WIDTHS[key] = {}
    elif len(kept) > WIDTHS_KEPT:
        kept.clear()
    return kept, QFontMetricsF(font)


def reading_font(font: QFont, share: float = SHARE) -> QFont:
    """The font a reading over text in `font` is drawn in: `share` of its
    size, upright, a little bold."""
    small = QFont(font)
    small.setItalic(False)
    small.setPixelSize(max(SMALLEST_PX, round(font.pixelSize() * share)))
    small.setWeight(QFont.Weight.DemiBold)
    return small


def ruby(
    text: str, readings: Sequence[Reading], font: QFont, share: float = SHARE
) -> Ruby:
    """`readings` over `text` drawn in `font`, at `share` of its size.
    With none, the band alone: a language's lines are one height whether
    a line has a reading or not, so a live caption's text never moves
    down when its first one comes.

    Two readings side by side need the room their overhangs and `PAD`
    take together, less what one's narrower reading leaves free over its
    character (zhāng over 张 reaches over 的's room, de being narrower
    than 的): `after` a character is that room, less the next one's own
    `before` - which a line starting at it needs whole."""
    small = reading_font(font, share)
    px = small.pixelSize()
    (kept, metrics), (base_kept, base_metrics) = _measure(small), _measure(font)
    count = len(text)
    before, after = [0.0] * count, [0.0] * count
    widths, base = [], []
    over: dict[int, tuple[float, Reading]] = {}
    """By a reading's first character: half of how much wider than its
    characters it is (less than 0: narrower), and the reading."""
    for reading in readings:
        wide = kept.get(reading.text)
        if wide is None:
            wide = kept[reading.text] = metrics.horizontalAdvance(reading.text)
        read = text[reading.start : reading.end]
        under = base_kept.get(read)
        if under is None:
            under = base_kept[read] = base_metrics.horizontalAdvance(read)
        widths.append(wide)
        base.append(under)
        over[reading.start] = ((wide - under) / 2, reading)
        before[reading.start] = max(0.0, (wide - under) / 2)
    for half, reading in over.values():
        last = reading.end - 1
        then = over.get(reading.end)
        if then is None:  # no reading next: room for its own reach alone
            after[last] = max(0.0, half)
            continue
        room = max(0.0, half + PAD * px + then[0])
        if reading.ends_word:
            room += WORD_GAP * px
        after[last] = max(0.0, room - before[reading.end])
    drop = metrics.descent() * 0.6 + LIFT * px
    spacing = []
    plain = text.isascii() or all(ord(char) <= 0xFFFF for char in text)
    for n in range(count):
        room = after[n] + (before[n + 1] if n + 1 < count else 0.0)
        if room > 0.0:
            spacing.append(
                (
                    n if plain else _unit(text, n),
                    2 if ord(text[n]) > 0xFFFF else 1,
                    room,
                )
            )
    return Ruby(
        tuple(readings),
        tuple(before),
        tuple(after),
        metrics.ascent() + drop,
        small,
        tuple(widths),
        tuple(base),
        drop,
        tuple(spacing),
    )


def _unit(text: str, index: int) -> int:
    """Qt's index (UTF-16 units) of `text`'s character `index`."""
    piece = text[:index]
    if piece.isascii():
        return index
    return index + sum(1 for char in piece if ord(char) > 0xFFFF)


_ROOMS: dict[int, QTextCharFormat] = {}
"""The format that gives a character its room, by the room in hundredths
of a pixel: the same few rooms come again and again."""
ROOMS_KEPT = 4000


def _room(room: float) -> QTextCharFormat:
    key = round(room * 100)
    found = _ROOMS.get(key)
    if found is None:
        if len(_ROOMS) > ROOMS_KEPT:
            _ROOMS.clear()
        found = _ROOMS[key] = QTextCharFormat()
        found.setFontLetterSpacingType(QFont.SpacingType.AbsoluteSpacing)
        found.setFontLetterSpacing(key / 100)
    return found


def spaced(layout: QTextLayout, readings: Ruby) -> None:
    """Gives `layout` (not yet begun) the room `readings` need: each
    character followed by its own room after and the next one's before."""
    ranges = []
    for start, length, room in readings.spacing:
        found = QTextLayout.FormatRange()
        found.start = start
        found.length = length
        found.format = _room(room)
        ranges.append(found)
    if ranges:
        layout.setFormats(ranges)


def lead(text: str, readings: Ruby, unit: int) -> float:
    """The room before the character at Qt's index `unit`: a line that
    starts with it is drawn that much further in."""
    if text.isascii() or all(ord(char) <= 0xFFFF for char in text):
        index = unit
    else:
        index = next((n for n in range(len(text)) if _unit(text, n) >= unit), 0)
    return readings.before[index] if 0 <= index < len(readings.before) else 0.0


@dataclass(frozen=True, slots=True)
class Placed:
    """A reading where it is drawn: its left and its baseline, from its
    row's top left."""

    x: float
    y: float
    text: str
    start: int = -1
    """The first character it reads, in its row's text."""


def placed(layout: QTextLayout, text: str, readings: Ruby) -> tuple[Placed, ...]:
    """Where each reading is drawn over `layout` (laid out): centred on
    its characters, above their line."""
    found = []
    plain = text.isascii() or all(ord(char) <= 0xFFFF for char in text)
    line = None
    last = -1  # the line in hand holds Qt's indexes below this
    y = 0.0
    for reading, wide, under in zip(
        readings.readings, readings.widths, readings.base, strict=True
    ):
        unit = reading.start if plain else _unit(text, reading.start)
        if line is None or unit >= last or unit < line.textStart():
            line = layout.lineForTextPosition(unit)
            if not line.isValid():
                line = None
                continue
            last = line.textStart() + line.textLength()
            y = line.y() - readings.drop
        at: object = line.cursorToX(unit)  # (x, index) in PySide6
        x = at[0] if isinstance(at, tuple) else at
        found.append(Placed(x + (under - wide) / 2, y, reading.text, reading.start))  # type: ignore[operator]
    return tuple(found)


_DRAWN: dict[int, tuple[Sequence[Placed], str, QTextLayout]] = {}
"""A row's readings as one laid-out text, by the row's own tuple of them
(its identity; kept with it, so it is the same one while the row is):
drawn in one call, and shaped once, not once a paint."""
DRAWN_KEPT = 400
_BREAK = " "
"""Between two readings in the one laid-out text: a line of its own each."""


def _drawn(readings: Sequence[Placed], font: QFont) -> QTextLayout:
    key = font.key()
    kept = _DRAWN.get(id(readings))
    if kept is not None and kept[0] is readings and kept[1] == key:
        return kept[2]
    if len(_DRAWN) > DRAWN_KEPT:
        _DRAWN.clear()
    layout = QTextLayout(_BREAK.join(reading.text for reading in readings), font)
    layout.setCacheEnabled(True)
    layout.beginLayout()
    for reading in readings:
        line = layout.createLine()
        if not line.isValid():
            break
        line.setLineWidth(1_000_000)
        line.setPosition(QPointF(reading.x, reading.y - line.ascent()))
    layout.endLayout()
    _DRAWN[id(readings)] = (readings, key, layout)
    return layout


def draw(
    painter: QPainter,
    readings: Sequence[Placed],
    font: QFont,
    at: QPointF,
    colour: QColor,
    colours: Sequence[QColor | None] = (),
) -> None:
    """Draws `readings` over a row drawn at `at`, in `colour` a little
    fainter - or each in its own of `colours` (one per reading; None: in
    `colour`), as fainter (395: pinyin in its word link's colour)."""
    painter.save()
    painter.setPen(_faint(colour))
    ranges = []
    at_char = 0
    for reading, own in zip(readings, colours, strict=False):
        if own is not None:
            part = QTextLayout.FormatRange()
            part.start, part.length = at_char, len(reading.text)
            part.format = QTextCharFormat()
            part.format.setForeground(_faint(own))
            ranges.append(part)
        at_char += len(reading.text) + len(_BREAK)
    _drawn(readings, font).draw(painter, at, ranges)
    painter.restore()


def _faint(colour: QColor) -> QColor:
    """`colour` as a reading is drawn: a little fainter than its text."""
    faint = QColor(colour)
    faint.setAlphaF(colour.alphaF() * ALPHA)
    return faint
