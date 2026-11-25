"""Reading lines over caption text: pinyin above Chinese (polyglotic-hq
364 and 369, decision 0155), Jyutping above Cantonese (polyglotic-hq
450, decision 0160), furigana above Japanese, a respelling above
English (KAY-oss: polyglotic-hq 511, DECISIONS #200), stress marks
over Russian (молоко́), Korean in Revised Romanization and Hindi in Latin
letters (511).

A reading (`core.lexicon.readings.Reading`) is drawn small above the
characters it reads, centred on them. Where it is wider than they are,
they get the room: the layout is told how much each character takes
(`Ruby.before`, `.after`; the one layout measures its units with it,
`views.flow.Above`), and Qt spaces the characters by the same amounts
(`rooms`), so a word is still found, marked, selected and looked up by
its row and character - a reading line changes where text is, never what
it is. A reading may reach over its neighbour's character where that
one's reading is narrower than it, so characters keep their own spacing
where they can (369). A word's last reading is followed by a little more
room (`WORD_GAP`), so the words show in a script written without spaces.

Which languages have their line on is the caption style's
(`CaptionStyle.reading_lines`); where readings come from is the caption
layout's `readings` - the Chinese dictionary's word split and everyday
readings, the Cantonese pack's (`core.lexicon.jyutping`), the Japanese
pack's word split (`core.lexicon.furigana`), the English dictionary's
respellings (`EnglishDictionary.readings`), or the Russian pack's
stressed forms (`core.lexicon.stress`) - or, for Korean and Hindi, rules
with no dictionary (`core.lexicon.korean`, `.hindi`) - on this PC:
nothing is sent anywhere for it.

Holds caption text's sound in what it lays out: never log it.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from typing import Protocol, cast

from PySide6.QtCore import QPointF
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetricsF,
    QGlyphRun,
    QPainter,
    QTextCharFormat,
    QTextLayout,
)

from polyglotic_desktop.core.lexicon.basic import BasicDictionary
from polyglotic_desktop.core.lexicon.chinese import ChineseDictionary
from polyglotic_desktop.core.lexicon.english import EnglishDictionary
from polyglotic_desktop.core.lexicon.furigana import FuriganaReader
from polyglotic_desktop.core.lexicon.hindi import HindiReader
from polyglotic_desktop.core.lexicon.jyutping import JyutpingReader
from polyglotic_desktop.core.lexicon.korean import KoreanReader
from polyglotic_desktop.core.lexicon.readings import Reading, Readings
from polyglotic_desktop.core.lexicon.stress import StressReader
from polyglotic_desktop.core.listening.display import (
    READING_LANGUAGES,
    JapaneseReading,
    ReadingSize,
)
from polyglotic_desktop.core.shared import EntryFacts
from polyglotic_desktop.ui_next import caption_faces, fonts
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
"""Gap from the text line box, as a share of the reading's pixel size."""
BELOW_SCALE = 0.9
"""The secondary reading's size relative to the primary reading (0 to 1)."""
ALPHA = 0.92
"""A reading is drawn this much fainter than its text: the text leads."""
KANA_REACH = 0.5
"""How far a reading may reach over the kana written after its kanji, as
a share of that kana's width - as Japanese typesetting lets furigana
overhang (必ずしも, not 必 ずしも; polyglotic-hq 511)."""


ONE_CLICK = ("zh", "yue")
"""The reading lines word links' one click turns on with the links, for a
window in their language (446): pinyin and Jyutping. The others come on
only by their own switch in Settings > Readings (polyglotic-hq 511)."""


MARKED = ("ru",)
"""The languages whose reading line is marks on their letters (Russian's
stress: `Reading.mark`): their rows keep no band above them."""


def marked(language: str | None) -> bool:
    """Whether `language`'s readings are marks on its letters (`MARKED`)."""
    return language is not None and language.split("-")[0] in MARKED


def language_of(language: str | None) -> str | None:
    """The reading line a row in `language` can have - its language's
    first part ("zh-hant": "zh") - None if none."""
    if language is None:
        return None
    first = language.split("-")[0]
    return first if first in READING_LANGUAGES else None


def source_of(
    learner: Learner,
    past: bool = False,
    respelling_past: bool = True,
    japanese: JapaneseReading = JapaneseReading.KANA,
) -> Readings:
    """Where a caption window's readings come from: pinyin from the
    Chinese dictionary on this PC (a learner's, `Learner.of`), Jyutping
    from the Cantonese pack (`reader`), once its word split's data is
    read - never read here, on the interface's thread (None: ask again
    when `dictionary_ready`). Nothing for a language without a reading
    line; None, too, without its dictionary open (Chinese or Cantonese not
    learned): ask again.
    `past`: only over the words past what the learner knows - the words
    word links "past what I know" link (decision 0130; `past_only`);
    `respelling_past`: the same, for English's respelling, which has its
    own choice (polyglotic-hq 511: past what you know at first)."""

    def read(text: str, language: str | None) -> Sequence[Reading] | None:
        if language_of(language) is None:
            return ()
        dictionary = reader(learner, language)
        if dictionary is None:
            # its language not learned, so no dictionary of it open: no
            # reading line, and no room kept for one (395: an empty band over
            # a translation into Chinese) - asked again on the next layout
            return None
        if not dictionary.ready:
            return None
        found: Sequence[Reading]
        if isinstance(dictionary, FuriganaReader) and japanese is JapaneseReading.BOTH:
            found = [
                *dictionary.readings(text),
                *(
                    replace(reading, below=True)
                    for reading in dictionary.romaji_readings(text)
                ),
            ]
        elif (
            isinstance(dictionary, FuriganaReader)
            and japanese is JapaneseReading.ROMAJI
        ):
            found = dictionary.romaji_readings(text)
        else:
            found = dictionary.readings(text)
        only = respelling_past if language_of(language) == "en" else past
        return past_only(learner, text, language, found) if only and found else found

    return read


def sources(learner: Learner) -> Callable[[bool, bool, JapaneseReading], Readings]:
    """A window's sources of readings by how their words are chosen - the
    scripts' readings past what the learner knows or over every word, and
    English's respelling the same way (`source_of`) - each made once."""
    made: dict[tuple[bool, bool, JapaneseReading], Readings] = {}

    def of(past: bool, respelling_past: bool, japanese: JapaneseReading) -> Readings:
        key = (past, respelling_past, japanese)
        if key not in made:
            made[key] = source_of(learner, past, respelling_past, japanese)
        return made[key]

    return of


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


class Reader(Protocol):
    """What reads one language's text for its reading line."""

    @property
    def ready(self) -> bool:
        """Whether it can answer now: its data read."""
        ...

    def readings(self, text: str) -> Sequence[Reading]:
        """The readings of `text`."""
        ...


KOREAN = KoreanReader()
HINDI = HindiReader()
"""Korean's and Hindi's readers: rules alone, the same for every learner."""


def reader(learner: Learner, language: str | None) -> Reader | None:
    """What reads a row in `language` on this PC, if anything does: the
    learner's Chinese dictionary, for Chinese; for Cantonese, the Cantonese
    pack once Cantonese is learned and its pack here (its own tools,
    `Learner.of`; decision 0175) - as pinyin needs Chinese learned; for
    Japanese, the Japanese pack's word split, the same way, and for
    Russian its pack's stressed forms; for English, the English dictionary
    once English is learned. Korean's and Hindi's need no dictionary: their
    rules, for anyone who turns them on."""
    code = language_of(language)
    if code == "zh":
        dictionary = learner.of(language).dictionary
        return dictionary if isinstance(dictionary, ChineseDictionary) else None
    if code == "yue":
        pack = learner.of(language).dictionary
        if isinstance(pack, BasicDictionary) and pack.language == "yue":
            return _jyutping(pack)
    if code == "ja":
        pack = learner.of(language).dictionary
        if isinstance(pack, BasicDictionary) and pack.language == "ja":
            return FuriganaReader(pack)  # keeps nothing: rubies are kept
    if code == "ru":
        pack = learner.of(language).dictionary
        if isinstance(pack, BasicDictionary) and pack.language == "ru":
            return _stress(pack)
    if code == "ko":
        return KOREAN
    if code == "hi":
        return HINDI
    if code == "en":
        english = learner.of(language).dictionary
        return english if isinstance(english, EnglishDictionary) else None
    return None


_READERS: list[JyutpingReader] = []
"""The Cantonese pack's reader, kept while the pack is the same: it keeps
the words it has read."""


def _jyutping(pack: BasicDictionary) -> JyutpingReader:
    if not _READERS or _READERS[0].dictionary is not pack:
        _READERS[:] = [JyutpingReader(pack)]
    return _READERS[0]


_STRESSES: list[StressReader] = []
"""The Russian pack's reader, kept while the pack is the same: it keeps
the words it has read."""


def _stress(pack: BasicDictionary) -> StressReader:
    if not _STRESSES or _STRESSES[0].dictionary is not pack:
        _STRESSES[:] = [StressReader(pack)]
    return _STRESSES[0]


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
    """Baseline distance from the line's top (above) or bottom (below)."""
    spacing: tuple[tuple[int, int, float], ...]
    """The room as Qt is given it (`rooms`): Qt's index of a character,
    its length there, and the room after it."""
    text_font: QFont
    """The text's own font: a mark (`Reading.mark`) is drawn in it."""
    below: "Ruby | None" = None
    """A secondary reading measured for the same text, drawn underneath."""

    @property
    def below_band(self) -> float:
        return self.below.band if self.below is not None else 0.0

    def room(self, start: int, end: int) -> float:
        return sum(self.before[start:end]) + sum(self.after[start:end])


_WIDTHS: dict[str, dict[str, float]] = {}
"""By font: the widths measured in it - a caption's syllables and
characters come again and again."""
WIDTHS_KEPT = 6000


_measured_in = [caption_faces.generation]
"""The faces' generation `_WIDTHS` was measured in: a face added since
measures them again."""


def _measure(font: QFont) -> tuple[dict[str, float], QFontMetricsF]:
    if _measured_in[0] != caption_faces.generation:
        _measured_in[0] = caption_faces.generation
        _WIDTHS.clear()
    key = font.key()
    kept = _WIDTHS.get(key)
    if kept is None:
        if len(_WIDTHS) > 24:
            _WIDTHS.clear()
        kept = _WIDTHS[key] = {}
    elif len(kept) > WIDTHS_KEPT:
        kept.clear()
    return kept, QFontMetricsF(font)


def reading_font(
    font: QFont, share: float = SHARE, weight: QFont.Weight = QFont.Weight.DemiBold
) -> QFont:
    """The font a reading over text in `font` is drawn in: `share` of its
    size, upright, a little bold - `weight`, a step above the text's
    (polyglotic-hq 481) - in its face's own weight or heavier, never one Qt
    makes up (479: a made-up bold drew some letters of the same pinyin
    lighter than others); in the text's weight if the face has none; and
    not in a face holding the text's weight alone (`fonts.WEIGHT_FACES`):
    asked for another, it would be made up - nor in one that doesn't draw
    readings (`fonts.reading_families`: Ma Shan Zheng has no tone marks)."""
    small = QFont(font)
    small.setFamilies(fonts.reading_families(small.families()))
    small.setStyleName("")  # by weight: the text's style may be Medium (532)
    small.setItalic(False)
    small.setPixelSize(max(SMALLEST_PX, round(font.pixelSize() * share)))
    single = {face for faces in fonts.WEIGHT_FACES.values() for face in faces}
    if single.intersection(small.families()):
        small.setFamilies([f for f in small.families() if f not in single])
    families = small.families()
    first = next(
        (family for family in families if caption_faces.has_family(family)),
        families[0] if families else "",
    )
    if not first or caption_faces.has_weight(first, int(weight.value)):
        small.setWeight(weight)
    return small


def below_font(font: QFont, share: float) -> QFont:
    return reading_font(font, share * BELOW_SCALE, QFont.Weight.Normal)


def band_height(font: QFont, *, below: bool = False) -> float:
    """Height reserved for a reading font, including its gap from the text."""
    return _band(font, QFontMetricsF(font), below)[0]


def _band(font: QFont, metrics: QFontMetricsF, below: bool) -> tuple[float, float]:
    """Reserved height and distance from the base text to the reading baseline."""
    gap = LIFT * font.pixelSize()
    if below:
        return metrics.height() + gap, metrics.ascent() + gap
    drop = metrics.descent() * 0.6 + gap
    return metrics.ascent() + drop, drop


def ruby(
    text: str,
    readings: Sequence[Reading],
    font: QFont,
    share: float = SHARE,
    weight: QFont.Weight = QFont.Weight.DemiBold,
    band: bool = True,
) -> Ruby:
    """`readings` over `text` drawn in `font`, at `share` of its size.
    With none, the band alone: a language's lines are one height whether
    a line has a reading or not, so a live caption's text never moves
    down when its first one comes.

    Two readings side by side need the room their overhangs and `PAD`
    take together, less what one's narrower reading leaves free over its
    character (zhāng over 张 reaches over 的's room, de being narrower
    than 的): `after` a character is that room, less the next one's own
    `before` - which a line starting at it needs whole.

    A mark (`Reading.mark`) takes no room and is measured in `font`;
    `band` False: no band - a language whose readings are all marks."""
    below = [r for r in readings if r.below]
    above = [r for r in readings if not r.below] if below else readings
    primary = _measure_ruby(text, above, font, reading_font(font, share, weight), band)
    if not below:
        return primary
    secondary = _measure_ruby(
        text, below, font, below_font(font, share), True, below=True
    )
    before = tuple(map(max, primary.before, secondary.before))
    after = tuple(map(max, primary.after, secondary.after))
    return replace(
        primary,
        before=before,
        after=after,
        spacing=_spacing(text, before, after),
        below=secondary,
    )


def _measure_ruby(
    text: str,
    readings: Sequence[Reading],
    font: QFont,
    small: QFont,
    band: bool,
    *,
    below: bool = False,
) -> Ruby:
    px = small.pixelSize()
    (kept, metrics), (base_kept, base_metrics) = _measure(small), _measure(font)
    count = len(text)
    before, after = [0.0] * count, [0.0] * count
    widths, base = [], []
    over: dict[int, tuple[float, Reading]] = {}
    """By a reading's first character: half of how much wider than its
    characters it is (less than 0: narrower), and the reading."""
    for reading in readings:
        read = text[reading.start : reading.end]
        under = base_kept.get(read)
        if under is None:
            under = base_kept[read] = base_metrics.horizontalAdvance(read)
        if reading.mark:  # on its letter, in the text's size: no room
            widths.append(base_metrics.horizontalAdvance(reading.text))
            base.append(under)
            continue
        wide = kept.get(reading.text)
        if wide is None:
            wide = kept[reading.text] = metrics.horizontalAdvance(reading.text)
        widths.append(wide)
        base.append(under)
        over[reading.start] = ((wide - under) / 2, reading)
        before[reading.start] = max(0.0, (wide - under) / 2)
    for half, reading in over.values():
        last = reading.end - 1
        then = over.get(reading.end)
        if then is None:  # no reading next: room for its own reach alone,
            # less what it may reach over kana written after it (`KANA_REACH`)
            reach = 0.0
            if reading.end < count and _is_kana(text[reading.end]):
                reach = KANA_REACH * base_metrics.horizontalAdvance(text[reading.end])
            after[last] = max(0.0, half - reach)
            continue
        room = max(0.0, half + PAD * px + then[0])
        if reading.ends_word:
            room += WORD_GAP * px
        after[last] = max(0.0, room - before[reading.end])
    height, drop = _band(small, metrics, below)
    return Ruby(
        tuple(readings),
        tuple(before),
        tuple(after),
        height if band else 0.0,
        small,
        tuple(widths),
        tuple(base),
        drop,
        _spacing(text, before, after),
        QFont(font),
    )


def _spacing(
    text: str, before: Sequence[float], after: Sequence[float]
) -> tuple[tuple[int, int, float], ...]:
    count = len(text)
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
    return tuple(spacing)


def _is_kana(char: str) -> bool:
    """Hiragana or katakana: what furigana may reach over."""
    return "\u3041" <= char <= "\u30ff"


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


def rooms(readings: Ruby) -> list[QTextLayout.FormatRange]:
    """The formats that give a layout (not yet begun) the room `readings`
    need: each character followed by its own room after and the next
    one's before."""
    ranges = []
    for start, length, room in readings.spacing:
        found = QTextLayout.FormatRange()
        found.start = start
        found.length = length
        found.format = _room(room)
        ranges.append(found)
    return ranges


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
    font: QFont | None = None
    """A mark's font, the text's own (`Reading.mark`); None: a reading's,
    the line's (`Ruby.font`)."""
    end: int = -1
    """End of the text span this reading belongs to."""


def placed(layout: QTextLayout, text: str, readings: Ruby) -> tuple[Placed, ...]:
    """Centre each reading on its characters on the measured side of the line."""
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
            y = (
                line.y() + line.height() + readings.drop
                if reading.below
                else line.y() - readings.drop
            )
        at: object = line.cursorToX(unit)  # (x, index) in PySide6
        x = at[0] if isinstance(at, tuple) else cast(float, at)
        if reading.mark:  # at the text's baseline, as an accent on the letter
            base_y = line.y() + line.ascent()
            if text[reading.start].isupper():  # over a capital: its height
                metrics = QFontMetricsF(readings.text_font)
                base_y -= metrics.capHeight() - metrics.xHeight()
            left = x + (under - wide) / 2
            found.append(
                Placed(
                    left,
                    base_y,
                    reading.text,
                    reading.start,
                    readings.text_font,
                    reading.end,
                )
            )
            continue
        found.append(
            Placed(
                x + (under - wide) / 2, y, reading.text, reading.start, end=reading.end
            )
        )
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
    faint = _faint(colour)
    if any(reading.font is not None for reading in readings):
        _marks(painter, readings, at, faint, colours)
        painter.restore()
        return
    painter.setPen(faint)
    layout = _drawn(readings, font)
    if not any(own is not None for own in colours):
        layout.draw(painter, at)
    else:  # a line a reading, each drawn once in its own colour (437): not
        # Qt's format range a reading, which draws each one's line again
        for i in range(layout.lineCount()):
            own = colours[i] if i < len(colours) else None
            painter.setPen(faint if own is None else _faint(own))
            layout.lineAt(i).draw(painter, at)
    painter.restore()


def _marks(
    painter: QPainter,
    readings: Sequence[Placed],
    at: QPointF,
    faint: QColor,
    colours: Sequence[QColor | None],
) -> None:
    """Marks on their letters (`Placed.font`), each in its colour - a
    language's readings are all marks or none (`MARKED`)."""
    for i, reading in enumerate(readings):
        own = colours[i] if i < len(colours) else None
        painter.setPen(faint if own is None else _faint(own))
        if reading.font is not None:
            painter.setFont(reading.font)
        painter.drawText(QPointF(at.x() + reading.x, at.y() + reading.y), reading.text)


def glyphs(readings: Sequence[Placed], font: QFont) -> list[QGlyphRun]:
    """`readings`' glyphs as `draw` places them: a caption's edge drawn
    under them (Visibility; polyglotic-hq 481) - none for marks on their
    letters (`MARKED`), drawn in the text's own font."""
    if any(reading.font is not None for reading in readings):
        return []
    return _drawn(readings, font).glyphRuns()


def faint(colour: QColor) -> QColor:
    """`colour` as a reading is drawn: a little fainter than its text."""
    return _faint(colour)


def _faint(colour: QColor) -> QColor:
    """`colour` as a reading is drawn: a little fainter than its text."""
    faint = QColor(colour)
    faint.setAlphaF(colour.alphaF() * ALPHA)
    return faint
