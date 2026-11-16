"""The caption layout engine: caption lines laid out for a width and text
size, and painted - shared by the caption windows and the transcripts
(decision 0031).

What keeps it fast (polyglotic-hq project 108's audit of today's overlay):
- **Only what shows:** a surface asks for the lines it draws, as
  `views.scroll` walks them; nothing is laid out ahead.
- **Cached per caption x width x text size:** a line's layout is kept while
  its rows stay the same, for its last few widths and text sizes - so a
  resize lays out the lines in view once per width, and a new caption
  lays out only itself - for as many lines as the surface can show again
  (`lines_kept`), never every line it ever showed.
- **Painted directly:** each row's `QTextLayout` is drawn by the painter,
  never turned into painter paths (`strokePath` was 75-85 % of today's
  slow actions).
- **Marks at paint time:** highlights and word links are format ranges
  drawn over a layout (`paint`'s `marks`), so a Learning change repaints
  and lays nothing out.

Sizes and fonts come from `CaptionStyle`; colours from `Ink`, at paint
time. Holds caption text in its layouts: never log them.
"""

from collections import OrderedDict
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field, replace
from functools import lru_cache

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontMetricsF,
    QGlyphRun,
    QPainter,
    QPainterPath,
    QPen,
    QTextCharFormat,
    QTextFormat,
    QTextLayout,
    QTextLine,
    QTextOption,
)

from polyglotic_desktop.core.lexicon.readings import Readings
from polyglotic_desktop.core.lexicon.zhuyin import zhuyin
from polyglotic_desktop.core.listening.captions import Language
from polyglotic_desktop.core.listening.display import (
    CaptionRow,
    LinkGap,
    LinkLine,
    ReadingColour,
    ReadingSystem,
    RowKind,
)
from polyglotic_desktop.ui_next import fonts, reading_lines, style
from polyglotic_desktop.ui_next.reading_lines import SHARE as READING_SHARE
from polyglotic_desktop.ui_next.reading_lines import Placed, Ruby
from polyglotic_desktop.ui_next.views.captions import (
    CAPTION_TEXT_SIZES,
    CAPTION_WINDOW_LINES,
    Line,
)
from polyglotic_desktop.ui_next.views.flow import (
    Above,
    Flow,
    Flowed,
    FlowOptions,
    Gaps,
    Open,
)
from polyglotic_desktop.ui_next.views.lab import Fill, Join, OwnLabel
from polyglotic_desktop.ui_next.views.pour import (
    ELLIPSIS,
    Gap,
    Measure,
    Pair,
    Poured,
    pour_paired,
    pour_stacked,
)
from polyglotic_desktop.ui_next.views.presets import readable_through

LATIN_FAMILIES = ("Segoe UI Variable Display", "Segoe UI", *fonts.also("latin"))
CJK_FAMILIES = {  # Windows' first; then another OS's own (`fonts`)
    "zh": ("Microsoft YaHei UI", "Microsoft YaHei", *fonts.also("zh")),
    "zh-hant": ("Microsoft JhengHei UI", "Microsoft JhengHei", *fonts.also("zh-hant")),
    "yue": ("Microsoft JhengHei UI", "Microsoft JhengHei", *fonts.also("yue")),
    "ja": ("Yu Gothic UI", "Meiryo UI", *fonts.also("ja")),
}
CJK_SCALE = 1.05
"""Chinese and Japanese a touch larger than Latin text at the same pixel
size: their denser strokes read as easily (today's overlay's)."""


RUBIES_KEPT = 600
"""Rows whose reading lines are kept measured, per engine."""
LINK_PX = {LinkLine.THIN: 1.4, LinkLine.MEDIUM: 2.2, LinkLine.THICK: 3.4}
LINK_GAP_PX = {LinkGap.CLOSE: 0.5, LinkGap.MEDIUM: 2.0, LinkGap.FAR: 4.0}
"""A word link's underline at 21 px text: its thickness, and its gap below
the font's descent - below the descenders of g, y and 的's peers, never
through them (the user's rehearsal feedback F14, 249)."""
LINK_MARK = QTextFormat.Property.UserProperty + 1
"""A format range that is a word link: the property is its link's number
in the clause, its colour the format's underline colour; the layout draws
its underline (`_underlines`) and, with Arrows, its curve (`_arrows`)."""
ARROW_ROW_GAP, ARROW_CLAUSE_GAP = 14.0, 8.0
"""With Arrows, more room - pixels at text size 1.0 - between a clause and
its translation, for the curves to cross, and between clauses (today's
overlay had 18 and 28 in all, before 151 retired Arrows; polyglotic-hq
249 brought them back, F7)."""
ARROW_PX = 1.7
"""A curve's width at 21 px text."""


@dataclass(frozen=True, slots=True)
class CaptionStyle:
    """Sizes, in pixels at text size 1.0: the text, the gap between a
    clause's original and its translation, and between clauses."""

    text_px: float = 21.0
    row_gap: float = 2.0
    clause_gap: float = 8.0
    weight: QFont.Weight = QFont.Weight.Medium
    label_px: float = 13.0
    label_gap: float = 3.0
    family: str | None = None
    """The learner's font for the captions (the Look panel's); None: the
    app's own. Qt falls back from it per character."""
    link_px: float = LINK_PX[LinkLine.MEDIUM]
    link_gap: float = LINK_GAP_PX[LinkGap.MEDIUM]
    """A word link's underline: how thick, and how far below the font's
    descent (F14) - pixels at 21 px text, scaled with it."""
    link_room: bool = False
    """Room under every row for a word link's underline (word links shown
    underlined): the underline is below the descenders, so without it the
    next row's tops would touch it."""
    arrows: bool = False
    """Word links joined by curves too (Arrows, F7): room between a clause
    and its translation for them to cross, and between clauses."""
    caption_gap: float = 10.0
    """Between one caption and the next (the surface's; the Lab's, 284)."""
    italic_provisional: bool = True
    italic_live: bool = False
    """Text still being spoken in italic: a provisional line (today's), a
    live caption (the Lab's Text still being spoken, 284)."""
    translation_size: float = 1.0
    """A translation row's text, as a share of what was said's (a caption
    window's own Translation size, polyglotic-hq 305): 1.0, the same. Kept
    within CAPTION_TEXT_SIZES of the base size: 50 % of 60 % is drawn at
    60 %, never under the app's 12 px; 200 % of 400 % at 400 %."""
    own_right: bool = False
    own_tint: bool = False
    own_bar: bool = False
    own_label: OwnLabel = OwnLabel.AS_NOW
    """The user's own speech (a line `by_you`), as the Lab has it (305): on
    the right, a tint of its label's colour behind it, a bar of it at its
    side, its "You" label as now, in a badge or not shown."""
    fill: Fill = Fill.CLAUSES
    join: Join = Join.ELLIPSIS
    """A clause a row (today's), or the caption poured into lines as wide
    as the surface, and what stands between its clauses then (the Lab's
    Captions fill the width, polyglotic-hq 309; `views.pour`)."""
    flow: FlowOptions | None = None
    """The one layout (polyglotic-hq 340, decision 0132; the Lab's "New
    layout"): a line that carries its caption's model is composed by
    `views.flow` with these options - every way of filling the window the
    same code - in place of the clause rows and the pour above. None: as
    before."""
    reading_lines: frozenset[str] = frozenset()
    """The languages whose rows carry their reading line (polyglotic-hq
    364, 369, decision 0155: "zh", pinyin above Chinese) - what was said
    and translations alike; a language's variants go by its first part
    ("zh-hant"). Needs the layout's `readings`."""
    reading_share: float = READING_SHARE
    reading_system: ReadingSystem = ReadingSystem.PINYIN
    """Chinese's readings in pinyin or zhuyin (395): converted as they're
    read, so a change lays the rows out again."""
    reading_past: bool = False
    """Readings only over the words past what the learner knows: the
    source's to say which (`reading_lines.source_of`); here, so a change
    lays the rows out again."""
    """A reading's text size as a share of its row's (the size chosen,
    `reading_lines.SHARES`)."""


@dataclass(frozen=True)
class Ink:
    """Colours, applied at paint time: white is what was said, yellow is
    always a translation (as today's overlay); a live line, and Quick
    preview's provisional one, drawn fainter."""

    original: QColor = field(default_factory=lambda: QColor("#ffffff"))
    translation: QColor = field(default_factory=lambda: QColor("#ffd76e"))
    label: QColor = field(default_factory=lambda: QColor("#aab2c0"))
    """A label without a colour of its own (the language spoken alone)."""
    live_alpha: float = 0.85
    provisional_alpha: float = 0.6
    unfinished: QColor | None = None
    """Text still being spoken - a live or provisional line, both rows - in
    this colour instead (the Lab's, 284); None: the rows' own."""
    alpha: float = 1.0
    """Everything drawn this much fainter (Strip's previous caption)."""
    translation_alpha: float = 1.0
    """The translation rows, and the label, this much fainter again than
    `alpha` - or less faint, above 1: an older caption's yellow steps back
    less than what was said (`views.arrivals`, F21)."""
    reading_colour: ReadingColour = ReadingColour.SAME
    """What colour a reading line is drawn in (395): its row's, its word
    link's, or `reading`."""
    reading: QColor | None = None
    """The colour picked for readings (`ReadingColour.CUSTOM`)."""
    said_in_link_colours: bool = False
    """Linked words in what was said drawn in their link's colour (395;
    on its own since 431)."""
    translation_in_link_colours: bool = False
    """Linked words in the translation drawn in their link's colour (395;
    on its own since 431: the user, 2026-11-17, "toggleable
    separately")."""
    panel: str | None = None
    """The panel's colour ("#rrggbb"): a link's colour as a word or a
    reading is drawn in it is made readable on it (`readable_on`) - they're
    picked for dark panels. None: as they are."""
    panel_opacity: float = 1.0
    """How solid the panel is: below 1, a link's colour is made readable
    on it seen over a light or a black video too (431)."""


@dataclass(frozen=True, slots=True)
class LaidRow:
    """A row laid out: its layout, its top within the line, and its index
    in the line's rows (what its marks are asked for by - a Strip shows
    some of a line's rows, not from the first)."""

    row: CaptionRow
    layout: QTextLayout
    top: float
    index: int
    full_px: int = 0
    """Its text's pixel size at the translation's full size - its own for
    what was said: Arrows' curves are drawn as thick as that (305)."""
    trails: tuple[QPointF, ...] = ()
    """Poured (309): where an ellipsis is drawn after its text - a join
    with the next clause, a line that runs on - each the start of its
    baseline, from the row's top left. In the row's font and colour."""
    above: tuple[Placed, ...] = ()
    """Its reading line (369, decision 0155): each reading where it is
    drawn, from the row's top left, in `above_font`."""
    above_font: QFont | None = None
    band: float = 0.0
    """The height of its reading line's band above each of its lines: a
    point over a reading is over its characters (`char_under`), a hovered
    word's highlight and an arrow's tip reach over it (369)."""


@dataclass(frozen=True, slots=True)
class LaidLine:
    """A line laid out: its rows, its height, and the label above them
    (`label`, None for none; the rows' tops already leave room for it)."""

    rows: tuple[LaidRow, ...]
    height: float
    label: QTextLayout | None = None
    width: float = 0.0
    """The width it was laid out at: a tint behind it spans it."""
    poured: bool = False
    """Its rows run on in lines as wide as the surface (the Lab's Captions
    fill the width, 309): `rows` are in the order they start down the
    caption, and a row can begin part way along a line."""
    breaks: tuple[float, ...] = ()
    """Where each line of text across the caption ends, from its top: the
    caption shown as far as `breaks[n - 1]` shows its first `n` lines (a
    new caption's lines arrive one at a time, `views.reveal`). The last is
    `height`."""
    lead: float = 0.0
    """Run-on (the one layout, 340): how much of its top lies over the end
    of the caption before - the line pair that one left open, which this
    one's first text is on. A surface draws it that much higher: its top
    is that pair's top. 0: it starts below the caption before."""
    open: Open | None = None
    """The line pair it ends in, if the next caption may carry on there."""


Mark = tuple[int, int, QTextCharFormat]
"""Characters `[start, end)` of a row, drawn with a format (a highlight,
a word link) - at paint time, over the layout. A dotted or dashed underline
is drawn as dots or dashes below where an underline goes, so a word both
linked and in the deck shows both."""

Marks = Callable[[Line, int], Sequence[Mark]]
"""The marks for a line's row, by the row's index."""


class _Kept:
    """A line's layouts while its rows stay the same, by (width, text size)."""

    __slots__ = (
        "composed",
        "cuts",
        "label",
        "live",
        "provisional",
        "rows",
        "sized",
    )

    def __init__(self, line: Line) -> None:
        self.rows = line.rows
        self.cuts = line.cuts
        self.provisional = line.provisional
        self.live = line.live
        self.label = line.label
        self.sized: OrderedDict[tuple[int, float, Open | None], LaidLine] = (
            OrderedDict()
        )
        self.composed: OrderedDict[tuple[int, float, Open | None], Flowed] = (
            OrderedDict()
        )

    def holds(self, line: Line) -> bool:
        return (
            (self.rows is line.rows or self.rows == line.rows)
            and self.provisional == line.provisional
            and self.live == line.live
            and self.label == line.label
            and self.cuts == line.cuts
        )


class CaptionLayout:
    """Lines laid out and painted. One per surface; not thread-safe."""

    SIZES_KEPT = 4
    """Widths x text sizes kept per line: a resize step, and the ones it may
    go back to."""

    def __init__(
        self,
        style: CaptionStyle | None = None,
        *,
        lines_kept: int = CAPTION_WINDOW_LINES,
        readings: Readings | None = None,
    ) -> None:
        """`lines_kept`: lines whose layouts are kept, least recently used
        dropped first - no more than the surface can show again: a caption
        window's lines, a few screens of a transcript (polyglotic-hq 239:
        each kept line holds its rows' `QTextLayout`s, about 15 KB of Qt's
        memory, and 2,500 kept per surface grew the app 0.5 MB a minute
        over an evening)."""
        self.style = style or CaptionStyle()
        self.lines_kept = lines_kept
        self.laid_out = 0  # rows laid out since made: what tests count
        self._kept: OrderedDict[int, _Kept] = OrderedDict()
        self._fonts: dict[tuple[tuple[str, ...], int, bool], QFont] = {}
        self._flows: OrderedDict[tuple[float, bool], Flow] = OrderedDict()
        self.readings = readings
        """Where a row's readings come from (369): what `style.reading_lines`
        needs; None: no reading lines."""
        self._rubies: OrderedDict[tuple[str, str | None, int], Ruby | None] = (
            OrderedDict()
        )

    def _ruby(self, row: CaptionRow, font: QFont) -> Ruby | None:
        """`row`'s reading line in `font`, if its language's is on: kept
        by text, a caption's rows are laid out again and again."""
        wanted = self.style.reading_lines
        if not wanted:
            return None
        language = row.language if row.language is not None else _script(row.text)
        if language is None or language.split("-")[0] not in wanted:
            return None
        key = (row.text, language, font.pixelSize())
        if key in self._rubies:
            self._rubies.move_to_end(key)
            return self._rubies[key]
        source = self.readings
        read = source(row.text, language) if source is not None else None
        if read is None:
            return None  # not yet: the dictionary is still being read
        if self.style.reading_system is ReadingSystem.ZHUYIN:
            read = [replace(r, text=zhuyin(r.text)) for r in read]
        found = reading_lines.ruby(row.text, read, font, self.style.reading_share)
        self._rubies[key] = found
        if len(self._rubies) > RUBIES_KEPT:
            self._rubies.popitem(last=False)
        return found

    def _above(
        self,
        side: RowKind,
        language: Language | None,
        text: str,
        text_size: float,
        italic: bool,
    ) -> Above | None:
        """The room a side's reading line needs, for the one layout."""
        row = CaptionRow(text, side, language, 0, True)
        found = self._ruby(row, self._font(row, text_size, italic))
        return Above(found.before, found.after, found.band) if found else None

    @property
    def held(self) -> int:
        """Lines whose layouts are kept now (at most `lines_kept`)."""
        return len(self._kept)

    def laid(
        self, line: Line, width: int, text_size: float, entry: Open | None = None
    ) -> LaidLine:
        """`line` laid out `width` pixels wide at `text_size`: from the
        cache unless its rows changed or it wasn't laid out so before.
        `entry`: the line pair the caption before left open (`left_open`),
        for this one to carry on in (the one layout's run-on)."""
        kept = self._keeping(line)
        size = (width, text_size, entry)
        found = kept.sized.get(size)
        if found is not None:
            kept.sized.move_to_end(size)
            return found
        found = kept.sized[size] = self._lay_out(line, width, text_size, entry)
        if len(kept.sized) > self.SIZES_KEPT:
            kept.sized.popitem(last=False)
        return found

    def left_open(
        self, line: Line, width: int, text_size: float, entry: Open | None = None
    ) -> Open | None:
        """The line pair `line` ends in at this width, for the next caption
        to carry on in - None unless the one layout runs captions on
        (`FlowOptions.run_on`), and for a caption still being spoken or on
        the right. Composed, not laid out: arithmetic over widths measured
        once, so a surface can follow a run of captions back from the ones
        in view without laying the others out."""
        if self.style.flow is None or line.model is None:
            return None
        return self._composed(self._keeping(line), line, width, text_size, entry).open

    def _keeping(self, line: Line) -> _Kept:
        kept = self._kept.get(line.key)
        if kept is None or not kept.holds(line):
            kept = self._kept[line.key] = _Kept(line)
            if len(self._kept) > self.lines_kept:
                self._kept.popitem(last=False)
        self._kept.move_to_end(line.key)
        return kept

    def _composed(
        self,
        kept: _Kept,
        line: Line,
        width: int,
        text_size: float,
        entry: Open | None,
    ) -> Flowed:
        """`line`'s caption composed by the one layout, from its own top."""
        size = (width, text_size, entry)
        found = kept.composed.get(size)
        if found is not None:
            kept.composed.move_to_end(size)
            return found
        style = self.style
        model, options = line.model, style.flow
        assert model is not None and options is not None
        right = line.by_you and style.own_right
        found = kept.composed[size] = self._flow(
            text_size, _italic(line, style)
        ).compose(
            [model], float(max(10, width)), options, right, trail=False, entry=entry
        )
        if len(kept.composed) > self.SIZES_KEPT:
            kept.composed.popitem(last=False)
        return found

    def paint(
        self,
        painter: QPainter,
        line: Line,
        laid: LaidLine,
        at: QPointF,
        ink: Ink,
        marks: Marks | None = None,
    ) -> None:
        """Draws `laid` (the layout of `line`) with its top left at `at`."""
        alpha = ink.alpha * (
            ink.provisional_alpha
            if line.provisional
            else ink.live_alpha
            if line.live
            else 1.0
        )
        own = self.style if line.by_you else None
        if own is not None and (own.own_tint or own.own_bar):
            _own_marks(painter, line, laid, at, ink, own)
        if laid.label is not None:
            label = QColor(line.label_color) if line.label_color else QColor(ink.label)
            label.setAlphaF(
                min(1.0, label.alphaF() * ink.alpha * ink.translation_alpha * 0.9)
            )
            where = at
            if own is not None and own.own_label is OwnLabel.BADGE:
                # in from the edge by its room, so the badge lines up with the text
                inward = -BADGE_PAD[0] if own.own_right else BADGE_PAD[0]
                where = QPointF(at.x() + inward, at.y())
                label = _badge(painter, laid.label, where, label)
            painter.setPen(label)
            laid.label.draw(painter, where)
        clip = painter.clipBoundingRect() if painter.hasClipping() else None
        above: dict[int, list[QPointF]] = {}  # Arrows: the clause's upper row's ends
        flowed: list[tuple[LaidRow, QPointF, list[Linked]]] = []
        for row in laid.rows:
            top_left = QPointF(at.x(), at.y() + row.top)
            if clip is not None and (
                top_left.y() + row.layout.boundingRect().height() <= clip.top()
                or top_left.y() >= clip.bottom()
            ):
                continue  # out of view, marks included: dots sit below a row's
                # box, and a row under the hover band leaked them into the gap
            original = row.row.kind is RowKind.ORIGINAL
            color = QColor(ink.original if original else ink.translation)
            if ink.unfinished is not None and (line.live or line.provisional):
                color = QColor(ink.unfinished)
            row_alpha = alpha if original else min(1.0, alpha * ink.translation_alpha)
            if row_alpha < 1.0:
                color.setAlphaF(color.alphaF() * row_alpha)
            painter.setPen(color)
            selections, dotted, links = split_marks(
                marks(line, row.index) if marks else ()
            )
            coloured = (
                ink.said_in_link_colours
                if original
                else ink.translation_in_link_colours
            )
            words = _coloured_words(links, ink, color) if coloured and links else []
            if words and not selections:
                in_colours(painter, row.layout, top_left, color, words)
                painter.setPen(color)
            else:  # beside other marks (the load, saved words): Qt's ranges
                selections += [_format_range(word) for word in words]
                drawn_whole(selections)
                row.layout.draw(painter, top_left, selections)
            if row.above and row.above_font is not None:
                reading_lines.draw(
                    painter,
                    row.above,
                    row.above_font,
                    top_left,
                    color,
                    _reading_colours(row.above, links, ink, color),
                )
            if row.trails:
                _trails(painter, row, top_left, color)
            if dotted:
                _dots(painter, row.layout, top_left, dotted, alpha)
            if links:
                _underlines(painter, row.layout, top_left, links, alpha, self.style)
            if self.style.arrows and laid.poured:
                flowed.append((row, top_left, links))
            elif self.style.arrows:
                if row.row.starts_clause:
                    above = _ends(row.layout, top_left, links, self.style, upper=True)
                elif links and above:
                    _arrows(painter, row, top_left, links, above, alpha, self.style)

        if flowed:
            _flow_arrows(painter, flowed, alpha, self.style)

    def _lay_out(
        self, line: Line, width: int, text_size: float, entry: Open | None = None
    ) -> LaidLine:
        style = self.style
        rows = []
        ends: list[float] = []
        y = 0.0
        label = None
        right = line.by_you and style.own_right
        flows = style.flow is not None and line.model is not None
        if flows and entry is not None:
            # it carries on in the caption before's line pair: that one's
            # label says whose both are
            composed = self._composed(
                self._keeping(line), line, width, text_size, entry
            )
            poured, y, breaks = self._flowed(line, composed, width, text_size, 0.0)
            return LaidLine(
                poured, y, None, float(width), True, breaks, entry.height, composed.open
            )
        if line.label and not (line.by_you and style.own_label is OwnLabel.NONE):
            font = self._label_font(text_size)
            label, height = _laid_text(line.label, font, width, right)
            y = height + style.label_gap * text_size
            if line.by_you and style.own_label is OwnLabel.BADGE:
                y += BADGE_PAD[1] * 2  # the badge's room, above and below
        if flows:
            composed = self._composed(self._keeping(line), line, width, text_size, None)
            poured, y, breaks = self._flowed(line, composed, width, text_size, y)
            return LaidLine(
                poured, y, label, float(width), True, breaks, open=composed.open
            )
        if style.fill is not Fill.CLAUSES:
            poured, y, breaks = self._poured(line, width, text_size, y)
            return LaidLine(poured, y, label, float(width), True, breaks)
        for index, row in enumerate(line.rows):
            if index:
                gap = style.clause_gap if row.starts_clause else style.row_gap
                if style.arrows:  # every pair: a row doesn't jump as links come
                    gap += ARROW_CLAUSE_GAP if row.starts_clause else ARROW_ROW_GAP
                y += gap * text_size
            italic = (
                style.italic_provisional if line.provisional else style.italic_live
            ) and (line.provisional or line.live)
            font = self._font(row, text_size, italic)
            ruby = self._ruby(row, font)
            layout, height = _laid_text(row.text, font, width, right, ruby)
            full = font
            if row.kind is RowKind.TRANSLATION and style.translation_size != 1.0:
                full = self._font(row, text_size, italic, own_size=False)
            rows.append(
                LaidRow(
                    row,
                    layout,
                    y,
                    index,
                    full.pixelSize(),
                    (),
                    *_above(layout, row, ruby),
                )
            )
            count = layout.lineCount()
            ends.extend(
                y + layout.lineAt(n).y() + layout.lineAt(n).height()
                for n in range(count - 1)
            )
            y += height + (self._link_room(font) if style.link_room else 0.0)
            ends.append(y)
            self.laid_out += 1
        return LaidLine(tuple(rows), y, label, float(width), breaks=tuple(ends))

    def _flow(self, text_size: float, italic: bool) -> Flow:
        """The composer for a text size: it keeps each clause's measured
        widths, so a resize step measures nothing."""
        key = (text_size, italic)
        found = self._flows.get(key)
        if found is None:
            style = self.style
            row_gap = style.row_gap + (ARROW_ROW_GAP if style.arrows else 0.0)
            pair_gap = style.clause_gap + (ARROW_CLAUSE_GAP if style.arrows else 0.0)
            found = self._flows[key] = Flow(
                _FlowFonts(self, text_size, italic),
                Gaps(row_gap * text_size, pair_gap * text_size),
                lambda side, language, text: self._above(
                    side, language, text, text_size, italic
                ),
            )
            if len(self._flows) > self.SIZES_KEPT:
                self._flows.popitem(last=False)
        self._flows.move_to_end(key)
        return found

    def _flowed(
        self, line: Line, flowed: Flowed, width: int, text_size: float, top: float
    ) -> tuple[tuple[LaidRow, ...], float, tuple[float, ...]]:
        """`line`'s caption as the one layout composed it (`flowed`,
        `views.flow`), from `top` down. As a poured caption, each row - a
        clause's text on one side - keeps a layout of its own, its lines
        placed where the composer put its runs: a word is found, marked
        and looked up by its row and character whatever the options."""
        style = self.style
        model = line.model
        assert model is not None
        italic = _italic(line, style)
        right = line.by_you and style.own_right
        index = {(row.clause, row.kind): n for n, row in enumerate(line.rows)}
        fonts_ = [self._font(row, text_size, italic) for row in line.rows]
        rubies = [
            self._ruby(row, font) for row, font in zip(line.rows, fonts_, strict=True)
        ]
        layouts: dict[int, QTextLayout] = {}
        tops: dict[int, float] = {}
        trails: dict[int, list[QPointF]] = {}
        alone: list[tuple[RowKind, float, float]] = []
        for placed_line in flowed.lines:
            flow_line = replace(placed_line, top=placed_line.top + top)
            on_line = None
            for run in flow_line.runs:
                n = index.get((run.words.clause, run.words.side))
                if n is None:
                    continue
                on_line = n
                row = line.rows[n]
                layout = layouts.get(n)
                if layout is None:
                    layout = layouts[n] = _begun(row.text, fonts_[n], rubies[n])
                text_line = layout.createLine()
                if not text_line.isValid():
                    continue
                ruby = rubies[n]
                # a reading wider than the run's first character: its room
                lead = ruby.before[run.words.start] if ruby is not None else 0.0
                clause = model.clauses[run.words.clause]
                end = run.words.end
                if end >= len(clause.text(run.words.side)):
                    end = len(row.text)  # with a live caption's trail
                columns = _units(row.text, run.words.start, end)
                if columns > 0:
                    text_line.setNumColumns(columns)
                else:
                    text_line.setLineWidth(1)
                row_top = tops.setdefault(n, flow_line.top)
                text_line.setPosition(
                    QPointF(
                        run.x + lead,
                        flow_line.top - row_top + flow_line.ascent - text_line.ascent(),
                    )
                )
            if on_line is not None:
                row_top = tops[on_line]
                trails.setdefault(on_line, []).extend(
                    QPointF(x, flow_line.top - row_top + flow_line.ascent)
                    for x in flow_line.joins
                )
            else:
                # a line of the caption before's (run-on) that none of this
                # one's text fitted on: its closing ellipsis is drawn here
                alone.extend(
                    (flow_line.side, x, flow_line.top + flow_line.ascent)
                    for x in flow_line.joins
                )
        for side, x, baseline in alone:
            n = next((n for n in sorted(tops) if line.rows[n].kind is side), None)
            if n is not None:  # in that side's font and colour
                trails.setdefault(n, []).append(QPointF(x, baseline - tops[n]))
        y = placed = top + flowed.height
        rows = []
        for n, row in enumerate(line.rows):
            layout = layouts.get(n)
            ruby = rubies[n]
            if layout is None:
                layout = _begun(row.text, fonts_[n], ruby)
            y = _rest(layout, y, tops.setdefault(n, y), width, right)
            layout.endLayout()
            full = fonts_[n]
            if row.kind is RowKind.TRANSLATION and style.translation_size != 1.0:
                full = self._font(row, text_size, italic, own_size=False)
            marks = tuple(trails.get(n, ()))
            rows.append(
                LaidRow(
                    row,
                    layout,
                    tops[n],
                    n,
                    full.pixelSize(),
                    marks,
                    *_above(layout, row, ruby),
                )
            )
            self.laid_out += 1
        rows.sort(key=lambda laid: (laid.top, laid.index))
        ends = [top + end for end in flowed.breaks]
        if y > placed or not ends:
            ends.append(y)
        return tuple(rows), y, tuple(ends)

    def _poured(
        self, line: Line, width: int, text_size: float, top: float
    ) -> tuple[tuple[LaidRow, ...], float, tuple[float, ...]]:
        """`line`'s rows poured into lines `width` wide from `top` down
        (`views.pour`), and where they end. Each row keeps a layout of its
        own text, its lines placed where the pour put them - so a word is
        still found, marked and looked up by its row and character. A row
        with a reading line (369) is measured with its readings' room, and
        each line it's on has their band above it (polyglotic-hq 395:
        pinyin over a translation into Chinese, Translation below or Line
        by line without the New layout, had none)."""
        style = self.style
        italic = (
            style.italic_provisional if line.provisional else style.italic_live
        ) and (line.provisional or line.live)
        fonts_ = [self._font(row, text_size, italic) for row in line.rows]
        rubies = [
            self._ruby(row, font) for row, font in zip(line.rows, fonts_, strict=True)
        ]
        metrics = [QFontMetricsF(font) for font in fonts_]
        measured: dict[tuple[int, str], float] = {}

        def measure(row: int, text: str) -> float:
            found = measured.get((row, text))
            if found is None:
                found = metrics[row].horizontalAdvance(text)
                ruby = rubies[row]
                at = line.rows[row].text.find(text) if ruby is not None else -1
                if ruby is not None and text and at >= 0:
                    # the pour measures the row's own text: its readings'
                    # room too (the same characters read the same way
                    # wherever they are in a row, but for a rare polyphone)
                    found += ruby.room(at, at + len(text))
                measured[row, text] = found
            return found

        lines = self._pour(line, float(max(10, width)), measure)
        layouts = [
            _begun(row.text, font, ruby)
            for row, font, ruby in zip(line.rows, fonts_, rubies, strict=True)
        ]
        tops: dict[int, float] = {}
        trails: dict[int, list[QPointF]] = {}
        gaps = {Gap.NONE: 0.0, Gap.ROW: style.row_gap, Gap.CLAUSE: style.clause_gap}
        right = line.by_you and style.own_right
        y = top
        ends: list[float] = []
        for n, poured in enumerate(lines):
            if n:
                y += gaps[poured.gap] * text_size
            y = self._place(
                poured, line, layouts, fonts_, rubies, y, tops, trails, width, right
            )
            ends.append(y)
        placed = y
        rows = []
        for index, row in enumerate(line.rows):
            layout = layouts[index]
            y = _rest(layout, y, tops.setdefault(index, y), width, right)
            layout.endLayout()
            full = fonts_[index]
            if row.kind is RowKind.TRANSLATION and style.translation_size != 1.0:
                full = self._font(row, text_size, italic, own_size=False)
            marks = tuple(trails.get(index, ()))
            rows.append(
                LaidRow(
                    row,
                    layout,
                    tops[index],
                    index,
                    full.pixelSize(),
                    marks,
                    *_above(layout, row, rubies[index]),
                )
            )
            self.laid_out += 1
        rows.sort(key=lambda laid: (laid.top, laid.index))
        if y > placed or not ends:  # text Qt laid in lines of its own (`_rest`)
            ends.append(y)
        return tuple(rows), y, tuple(ends)

    def _pour(self, line: Line, width: float, measure: Measure) -> list[Poured]:
        """`line`'s rows as poured lines, the way the style fills them."""
        originals = [
            (i, r.text) for i, r in enumerate(line.rows) if r.kind is RowKind.ORIGINAL
        ]
        translations = [
            (i, r.text)
            for i, r in enumerate(line.rows)
            if r.kind is RowKind.TRANSLATION
        ]
        join = self.style.join
        if self.style.fill is Fill.PAIRED and originals and translations:
            return pour_paired(_pairs(line), width, measure, join)
        return pour_stacked(originals, translations, width, measure, join)

    def _place(
        self,
        poured: Poured,
        line: Line,
        layouts: list[QTextLayout],
        fonts_: list[QFont],
        rubies: list[Ruby | None],
        y: float,
        tops: dict[int, float],
        trails: dict[int, list[QPointF]],
        width: int,
        right: bool,
    ) -> float:
        """One poured line's pieces placed at `y`, on one baseline; where
        the next line starts. A row's top is its first piece's line's. A
        line with a reading line's row on it has its band above it, and a
        piece starts after its first character's reading's room (369)."""
        bands = [
            ruby.band
            for piece in poured.pieces
            if (ruby := rubies[piece.row]) is not None
        ]
        y += max(bands, default=0.0)
        made = []
        for piece in poured.pieces:
            text_line = layouts[piece.row].createLine()
            if not text_line.isValid():
                continue
            columns = _units(line.rows[piece.row].text, piece.start, piece.end)
            if columns > 0:
                text_line.setNumColumns(columns)
            else:
                text_line.setLineWidth(1)
            made.append((piece, text_line))
        ascent = max((t.ascent() for _, t in made), default=0.0)
        below = max((t.height() - t.ascent() for _, t in made), default=0.0)
        shift = 0.0
        if right:  # against the edge by what Qt laid, not by what was measured:
            # the two differ a little by font (a fallback font's glyphs)
            end = max((p.x + t.naturalTextWidth() for p, t in made), default=0.0)
            if poured.marks:
                end = max(end, poured.end)
            shift = max(0.0, width - end)
        room = 0.0
        for piece, text_line in made:
            row_top = tops.setdefault(piece.row, y)
            ruby = rubies[piece.row]
            lead = ruby.before[piece.start] if ruby is not None else 0.0
            text_line.setPosition(
                QPointF(
                    piece.x + lead + shift, y - row_top + ascent - text_line.ascent()
                )
            )
            if self.style.link_room:
                room = max(room, self._link_room(fonts_[piece.row]))
        for row, x in poured.marks:
            row_top = tops.setdefault(row, y)
            trails.setdefault(row, []).append(QPointF(x + shift, y - row_top + ascent))
        return y + ascent + below + room

    def _link_room(self, font: QFont) -> float:
        """How far a word link's underline reaches below a row's descent."""
        scale = max(0.5, font.pixelSize() / 21.0)
        return (self.style.link_gap + self.style.link_px) * scale

    def _label_font(self, text_size: float) -> QFont:
        px = max(8, round(self.style.label_px * min(text_size, 1.6)))
        families = tuple(style.UI_FAMILIES)  # the interface's words: an app, a language
        key = (families, -px, False)
        font = self._fonts.get(key)
        if font is None:
            font = self._fonts[key] = QFont()
            font.setFamilies(list(families))
            font.setPixelSize(px)
            font.setWeight(QFont.Weight.DemiBold)
        return font

    def _font(
        self, row: CaptionRow, text_size: float, italic: bool, own_size: bool = True
    ) -> QFont:
        """`row`'s font at `text_size` - a translation's at its share of it
        (`own_size`), kept within CAPTION_TEXT_SIZES."""
        script = row.language if row.language is not None else _script(row.text)
        cjk = script in CJK_FAMILIES
        share = self.style.translation_size
        if own_size and row.kind is RowKind.TRANSLATION and share != 1.0:
            low, high = CAPTION_TEXT_SIZES
            text_size = min(high, max(low, text_size * share))
        families = LATIN_FAMILIES
        if script is not None and cjk:
            families = (*CJK_FAMILIES[script], *LATIN_FAMILIES)
        if self.style.family:
            families = (self.style.family, *families)
        px = max(8, round(self.style.text_px * text_size * (CJK_SCALE if cjk else 1.0)))
        key = (families, px, italic)
        font = self._fonts.get(key)
        if font is None:
            font = self._fonts[key] = QFont()
            font.setFamilies(list(families))
            font.setPixelSize(px)
            font.setWeight(self.style.weight)
            font.setItalic(italic)
        return font


_DOTTED = QTextCharFormat.UnderlineStyle.DotLine
_DASHED = QTextCharFormat.UnderlineStyle.DashUnderline
DOT_PX, DOT_STEP_PX, DOT_DROP_PX = 1.7, 4.5, 2.0
"""A dotted mark's dots, at text size 1.0 (21 px): their size, spacing, and
how far below the underline's place they sit."""
DASH_PX, DASH_STEP_PX = 5.0, 7.5
"""A dashed mark's dashes (a word in the deck): their length and spacing,
as high as a dot; a different shape from the dots, not only a different
colour."""

Linked = tuple[int, int, QColor, int]
"""Characters `[start, end)` of a row a word link underlines, in its
colour, and the link's number in the clause."""

Dotted = tuple[int, int, QColor, bool]
"""Characters `[start, end)` marked below the underline's place, in a
colour; dashes rather than dots if the last is True."""


def split_marks(
    marks: Sequence[Mark],
) -> tuple[list[QTextLayout.FormatRange], list[Dotted], list[Linked]]:
    """A row's marks as the format ranges Qt draws with its text, and apart:
    the dotted and dashed ones - drawn as dots or dashes below where an
    underline goes, so an underline on the same word doesn't replace them -
    and the word links, underlined below the descenders (`_underlines`)."""
    selections = []
    dotted = []
    links = []
    for start, end, format_ in marks:
        if format_.hasProperty(LINK_MARK):
            link = int(format_.property(LINK_MARK))
            links.append((start, end, format_.underlineColor(), link))
            continue
        style = format_.underlineStyle()
        if style is _DOTTED or style is _DASHED:
            dotted.append((start, end, format_.underlineColor(), style is _DASHED))
            continue
        selection = QTextLayout.FormatRange()
        selection.start, selection.length = start, end - start
        selection.format = format_
        selections.append(selection)
    return selections, dotted, links


_SEEN_THROUGH = QBrush(Qt.GlobalColor.transparent)
_FOREGROUND = QTextFormat.Property.ForegroundBrush
_BACKGROUND = QTextFormat.Property.BackgroundBrush


def drawn_whole(selections: list[QTextLayout.FormatRange]) -> None:
    """Each range that colours its text given a background - transparent,
    where it has none - so Qt draws it whatever its neighbour.

    Qt's `QTextLayout.draw` skips a text-colouring range with no background
    whose region overlaps one drawn already. It rounds each region out to
    whole pixels, and a word split over two poured lines (309) has a region
    reaching the next word. So a coloured word right after another was
    drawn plain: on Windows after a split word, at some widths; on GitHub's
    Mac, whose font has fractional advances (22.42 px a character), after
    any coloured word (polyglotic-hq 420)."""
    for selection in selections:
        format_ = selection.format
        if format_.hasProperty(_FOREGROUND) and not format_.hasProperty(_BACKGROUND):
            seen_through = QTextCharFormat(format_)
            seen_through.setBackground(_SEEN_THROUGH)
            selection.format = seen_through


LINK_CONTRAST = 5.0
"""A word or a reading drawn in its link's colour reaches this against the
panel drawn solid, as faint as it's drawn: 4.5:1 (`AA_TEXT`) with room to
spare - and, seen through a panel that isn't solid, large text's 3:1 over
a light or a black video (`readable_through`, 431)."""


def link_ink(colour: QColor, ink: Ink, row: QColor, faint: float = 1.0) -> QColor:
    """A link's `colour` as a word or a reading is drawn in it: as faint as
    its `row`'s text (and `faint` again: a reading's), and readable so on
    the panel (`Ink.panel`), solid and seen through at its opacity
    (`Ink.panel_opacity`) - moved towards white on a dark panel, black on
    a light one, only as far as it needs (395, 431)."""
    alpha = row.alphaF()
    found = QColor(colour)
    if ink.panel is not None:
        found = QColor(
            _link_shade(
                colour.name(),
                ink.panel,
                ink.panel_opacity,
                alpha * faint,
            )
        )
    found.setAlphaF(alpha)
    return found


@lru_cache(maxsize=4096)
def _link_shade(colour: str, panel: str, opacity: float, alpha: float) -> str:
    """`readable_through`, kept: each linked word of each row is drawn in
    one at every paint, and a link colour's shade is the same each time."""
    return readable_through(colour, panel, opacity, alpha, LINK_CONTRAST)


Coloured = tuple[int, int, QColor]
"""Characters `[start, end)` of a row drawn in a colour of their own."""


def _coloured_words(links: Sequence[Linked], ink: Ink, row: QColor) -> list[Coloured]:
    """A row's linked words in their links' colours
    (`Ink.said_in_link_colours`, `Ink.translation_in_link_colours`), in
    the row's order."""
    found = [
        (start, end, link_ink(colour, ink, row)) for start, end, colour, _ in links
    ]
    return sorted(found, key=lambda word: word[:2])


def _format_range(word: Coloured) -> QTextLayout.FormatRange:
    """`word` as the format range `QTextLayout.draw` colours it with, beside
    other marks' ranges."""
    start, end, colour = word
    part = QTextLayout.FormatRange()
    part.start, part.length = start, end - start
    part.format = QTextCharFormat()
    part.format.setForeground(colour)
    return part


def in_colours(
    painter: QPainter,
    layout: QTextLayout,
    at: QPointF,
    colour: QColor,
    words: Sequence[Coloured],
) -> None:
    """`layout` drawn with its top left at `at`, in `colour`, and `words`
    (in order, apart) each in its own: every glyph drawn once, in one
    colour (437). `QTextLayout.draw` with a format range a word draws
    each word's line again under a clip of its own, and unites the
    clips: with both sides' linked words coloured, a run-on live update
    went over a new caption's budget on CI (Windows, 2026-11-17)."""
    for which, runs in _runs(layout, tuple((start, end) for start, end, _ in words)):
        painter.setPen(colour if which < 0 else words[which][2])
        for run in runs:
            painter.drawGlyphRun(at, run)


Runs = list[tuple[int, list[QGlyphRun]]]
"""A layout's glyphs in the order drawn, in parts: each part's word (its
index among the coloured words; -1 for none, the row's colour) and its
glyph runs."""

_RUNS: dict[int, tuple[QTextLayout, tuple[tuple[int, int], ...], Runs]] = {}
"""Each laid-out row's `Runs`, by the layout's identity, while its words
are the same: a row is drawn at every paint, and laid out once."""
RUNS_KEPT = 600


def _runs(layout: QTextLayout, spans: tuple[tuple[int, int], ...]) -> Runs:
    kept = _RUNS.get(id(layout))
    if kept is not None and kept[0] is layout and kept[1] == spans:
        return kept[2]
    if len(_RUNS) >= RUNS_KEPT:
        _RUNS.clear()
    found: Runs = []
    for i in range(layout.lineCount()):
        line = layout.lineAt(i)
        first = line.textStart()
        last = first + line.textLength()
        done = first
        for which, (start, end) in enumerate(spans):
            start, end = max(start, done), min(end, last)
            if start >= end:
                continue
            if start > done:
                found.append((-1, line.glyphRuns(done, start - done)))
            found.append((which, line.glyphRuns(start, end - start)))
            done = end
        if done < last:
            found.append((-1, line.glyphRuns(done, last - done)))
    _RUNS[id(layout)] = (layout, spans, found)
    return found


def _reading_colours(
    readings: Sequence[reading_lines.Placed],
    links: Sequence[Linked],
    ink: Ink,
    row: QColor,
) -> list[QColor | None]:
    """Each reading's own colour, as `Ink.reading_colour` says - None for
    its row's: its word link's where a link joins its character, or the
    colour picked (395) - whether or not the words are (431: the user,
    2026-11-17, "toggleable separately")."""
    if ink.reading_colour is ReadingColour.CUSTOM and ink.reading is not None:
        picked = QColor(ink.reading)
        picked.setAlphaF(row.alphaF() * picked.alphaF())
        return [picked] * len(readings)
    if ink.reading_colour is not ReadingColour.LINK or not links:
        return []
    found: list[QColor | None] = []
    for reading in readings:
        colour = next(
            (c for start, end, c, _ in links if start <= reading.start < end), None
        )
        found.append(
            None if colour is None else link_ink(colour, ink, row, reading_lines.ALPHA)
        )
    return found


def cursor_x(line: QTextLine, index: int) -> float:
    """Where character `index` starts on a laid-out line."""
    found: object = line.cursorToX(index)  # (x, index) in PySide6
    return float(found[0] if isinstance(found, tuple) else found)  # type: ignore[arg-type]


def char_under(
    rows: Iterable[tuple[LaidRow, QPointF]], pos: QPointF
) -> tuple[LaidRow, QPointF, int] | None:
    """The character under `pos` among `rows` - each a laid-out row and its
    top left, where it's drawn: that row, its top left and the character's
    index in its text; None if `pos` is on no text. Caption windows and
    transcripts find the word under the mouse with it."""
    for row, origin in rows:
        layout = row.layout
        for i in range(layout.lineCount()):
            text_line = layout.lineAt(i)
            box = text_line.naturalTextRect()
            if row.band:  # a reading over a character is over the character
                box.setTop(box.top() - row.band)
            if box.translated(origin).contains(pos):
                index = text_line.xToCursor(
                    pos.x() - origin.x(), QTextLine.CursorPosition.CursorOnCharacter
                )
                return row, origin, index
    return None


def span_rects(layout: QTextLayout, start: int, end: int) -> list[QRectF]:
    """Where characters `[start, end)` of `layout` are, one rectangle per
    line they're on - from the layout's own top left."""
    rects = []
    for i in range(layout.lineCount()):
        text_line = layout.lineAt(i)
        a = max(start, text_line.textStart())
        b = min(end, text_line.textStart() + text_line.textLength())
        if a < b:
            x1, x2 = cursor_x(text_line, a), cursor_x(text_line, b)
            rects.append(QRectF(x1, text_line.y(), x2 - x1, text_line.height()))
    return rects


def dot_place(font: QFont) -> tuple[float, float]:
    """Where a dotted mark's dots go in `font`: how far below a line's
    baseline they start, and their size (`_dots`)."""
    scale = max(0.5, font.pixelSize() / 21.0)
    metrics = QFontMetricsF(font)
    drop = metrics.underlinePos() + metrics.lineWidth() + DOT_DROP_PX * scale
    return drop, DOT_PX * scale


def dots_below(layout: QTextLayout) -> float:
    """How far the dots under a line of `layout` reach below the line's own
    box - a new word's dots hang under its descenders (polyglotic-hq 402)."""
    if layout.lineCount() == 0:
        return 0.0
    drop, size = dot_place(layout.font())
    return max(
        0.0,
        max(
            line.ascent() + drop + size - line.height()
            for line in (layout.lineAt(n) for n in range(layout.lineCount()))
        ),
    )


def _dots(
    painter: QPainter,
    layout: QTextLayout,
    at: QPointF,
    spans: list[Dotted],
    alpha: float,
) -> None:
    """Dots - or dashes - under characters `[start, end)` of `layout`
    (drawn at `at`), below where an underline goes."""
    font = layout.font()
    scale = max(0.5, font.pixelSize() / 21.0)
    drop, size = dot_place(font)
    painter.save()
    painter.setPen(Qt.PenStyle.NoPen)
    for start, end, color, dashed in spans:
        length = DASH_PX * scale if dashed else size
        step = (DASH_STEP_PX if dashed else DOT_STEP_PX) * scale
        dot = QColor(color)
        dot.setAlphaF(dot.alphaF() * alpha)
        painter.setBrush(dot)
        for i in range(layout.lineCount()):
            text_line = layout.lineAt(i)
            a = max(start, text_line.textStart())
            b = min(end, text_line.textStart() + text_line.textLength())
            if a >= b:
                continue
            x = at.x() + cursor_x(text_line, a) + 1
            right = at.x() + cursor_x(text_line, b)
            y = at.y() + text_line.y() + text_line.ascent() + drop
            while x + length <= right:
                if dashed:
                    painter.drawRoundedRect(
                        QRectF(x, y, length, size), size / 2, size / 2
                    )
                else:
                    painter.drawEllipse(QRectF(x, y, size, size))
                x += step
    painter.restore()


def _underlines(
    painter: QPainter,
    layout: QTextLayout,
    at: QPointF,
    links: list[Linked],
    alpha: float,
    style: CaptionStyle,
) -> None:
    """Word links' underlines under characters `[start, end)` of `layout`
    (drawn at `at`): below the font's descent - under the descenders, never
    through them - `style.link_gap` further, `style.link_px` thick, both
    scaled with the text (F14)."""
    scale = max(0.5, layout.font().pixelSize() / 21.0)
    thick = style.link_px * scale
    painter.save()
    painter.setPen(Qt.PenStyle.NoPen)
    for start, end, color, _ in links:
        bar = QColor(color)
        bar.setAlphaF(bar.alphaF() * alpha)
        painter.setBrush(bar)
        for i in range(layout.lineCount()):
            text_line = layout.lineAt(i)
            a = max(start, text_line.textStart())
            b = min(end, text_line.textStart() + text_line.textLength())
            if a >= b:
                continue
            x1 = at.x() + cursor_x(text_line, a)
            x2 = at.x() + cursor_x(text_line, b)
            bottom = text_line.y() + text_line.ascent() + text_line.descent()
            y = at.y() + bottom + style.link_gap * scale
            painter.drawRoundedRect(QRectF(x1, y, x2 - x1, thick), thick / 2, thick / 2)
    painter.restore()


def _ends(
    layout: QTextLayout,
    at: QPointF,
    links: list[Linked],
    style: CaptionStyle,
    upper: bool,
    band: float = 0.0,
) -> dict[int, list[QPointF]]:
    """Where Arrows' curves end on a row (drawn at `at`), by link: under the
    middle of each linked word on its last line (`upper`, just below its
    underline) - or over it on its first line. Only the lines facing each
    other: a curve from an upper line would cut through the text."""
    found: dict[int, list[QPointF]] = {}
    if not layout.lineCount():
        return found
    scale = max(0.5, layout.font().pixelSize() / 21.0)
    text_line = layout.lineAt(layout.lineCount() - 1 if upper else 0)
    for start, end, _, link in links:
        a = max(start, text_line.textStart())
        b = min(end, text_line.textStart() + text_line.textLength())
        if a >= b:
            continue
        middle = at.x() + (cursor_x(text_line, a) + cursor_x(text_line, b)) / 2
        if upper:
            bottom = text_line.y() + text_line.ascent() + text_line.descent()
            y = bottom + (style.link_gap + style.link_px) * scale  # from the bar
        else:  # over its reading line, if it has one (`band`, 369)
            y = text_line.y() - band + 1.0 * scale
        found.setdefault(link, []).append(QPointF(middle, at.y() + y))
    return found


def _arrows(
    painter: QPainter,
    row: LaidRow,
    at: QPointF,
    links: list[Linked],
    above: dict[int, list[QPointF]],
    alpha: float,
    style: CaptionStyle,
) -> None:
    """Arrows (F7): from each linked word of a clause's upper row (`above`)
    a curve down to its counterpart on `row`, its translation row, in the
    link's colour (today's overlay's, before 151) - as thick as at the
    translation's full size (`full_px`): a smaller translation (305) left it
    a hairline beside the underline it runs on from, a larger one heavy."""
    layout = row.layout
    scale = max(0.5, (row.full_px or layout.font().pixelSize()) / 21.0)
    colors = {link: color for _, _, color, link in links}
    pen = QPen()
    pen.setWidthF(ARROW_PX * scale)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    for link, ends in _ends(layout, at, links, style, False, row.band).items():
        color = QColor(colors[link])
        color.setAlphaF(color.alphaF() * 0.9 * alpha)
        pen.setColor(color)
        painter.setPen(pen)
        for end in ends:
            for start in above.get(link, ()):
                bend = (end.y() - start.y()) * 0.6
                curve = QPainterPath(start)
                curve.cubicTo(
                    QPointF(start.x(), start.y() + bend),
                    QPointF(end.x(), end.y() - bend),
                    end,
                )
                painter.drawPath(curve)
    painter.restore()


def _flow_arrows(
    painter: QPainter,
    rows: list[tuple[LaidRow, QPointF, list[Linked]]],
    alpha: float,
    style: CaptionStyle,
) -> None:
    """Arrows in the one layout (340): a curve from each linked word of
    what was said down to its counterpart, wherever both are - drawn when
    the counterpart's line is the next one under the word's (the two
    lines of a line pair), in any way of filling the window. A link whose
    ends are further apart keeps its colour alone: a curve across other
    lines would cut through their text."""
    said: dict[tuple[int, int], list[tuple[QRectF, QColor, float]]] = {}
    for row, at, links in rows:
        if row.row.kind is not RowKind.ORIGINAL:
            continue
        scale = max(0.5, row.layout.font().pixelSize() / 21.0)
        drop = (style.link_gap + style.link_px) * scale
        for start, end, color, link in links:
            for rect in span_rects(row.layout, start, end):
                said.setdefault((row.row.clause, link), []).append(
                    (rect.translated(at), color, drop)
                )
    pen = QPen()
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    for row, at, links in rows:
        if row.row.kind is not RowKind.TRANSLATION:
            continue
        scale = max(0.5, (row.full_px or row.layout.font().pixelSize()) / 21.0)
        pen.setWidthF(ARROW_PX * scale)
        for start, end, _, link in links:
            for rect in span_rects(row.layout, start, end):
                under = rect.translated(at)
                under.setTop(under.top() - row.band)  # above its reading line
                for over, color, drop in said.get((row.row.clause, link), ()):
                    gap = under.top() - over.bottom()
                    if not -1.0 <= gap < over.height():
                        continue  # not the line just above
                    tint = QColor(color)
                    tint.setAlphaF(tint.alphaF() * 0.9 * alpha)
                    pen.setColor(tint)
                    painter.setPen(pen)
                    a = QPointF(over.center().x(), over.bottom() + drop)
                    b = QPointF(under.center().x(), under.top() + 1.0 * scale)
                    bend = (b.y() - a.y()) * 0.6
                    curve = QPainterPath(a)
                    curve.cubicTo(
                        QPointF(a.x(), a.y() + bend), QPointF(b.x(), b.y() - bend), b
                    )
                    painter.drawPath(curve)
    painter.restore()


class _FlowFont:
    """One font's measuring for the composer (`views.flow.Font`); it keeps
    the widths it measured - a caption's words come again and again."""

    def __init__(self, font: QFont, link_room: float) -> None:
        metrics = QFontMetricsF(font)
        self._advance = metrics.horizontalAdvance
        self._widths: dict[str, float] = {}
        self.ascent = metrics.ascent()
        self.below = metrics.height() - metrics.ascent() + link_room

    def width(self, text: str) -> float:
        found = self._widths.get(text)
        if found is None:
            if len(self._widths) > 4000:
                self._widths.clear()
            found = self._widths[text] = self._advance(text)
        return found


class _FlowFonts:
    """The composer's measuring (`views.flow.Fonts`), in the layout's
    fonts at one text size."""

    def __init__(self, engine: CaptionLayout, text_size: float, italic: bool) -> None:
        self._engine, self._text_size, self._italic = engine, text_size, italic
        self._fonts: dict[int, _FlowFont] = {}

    def font(self, side: RowKind, language: Language | None, text: str) -> _FlowFont:
        engine = self._engine
        row = CaptionRow(text, side, language, 0, True)
        font = engine._font(row, self._text_size, self._italic)
        found = self._fonts.get(id(font))
        if found is None:
            room = engine._link_room(font) if engine.style.link_room else 0.0
            found = self._fonts[id(font)] = _FlowFont(font, room)
        return found


OWN_TINT_ALPHA = 0.14
"""The tint behind the user's own speech: its label's colour, this strong."""
OWN_BAR_PX, OWN_BAR_GAP_PX = 3.0, 8.0
"""The bar at its side: how wide, and how far from the text (in the
window's padding, so nothing is laid out again)."""
BADGE_PAD = (5.0, 1.5)
"""The "You" badge's room around its words: across, and above and below."""


def _own_marks(
    painter: QPainter,
    line: Line,
    laid: LaidLine,
    at: QPointF,
    ink: Ink,
    style: CaptionStyle,
) -> None:
    """The user's own speech's tint and bar (the Lab's, 305), in its
    label's colour: the tint behind the whole line, the bar at the side
    its text lines up on."""
    colour = QColor(line.label_color) if line.label_color else QColor(ink.label)
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    if style.own_tint:
        tint = QColor(colour)
        tint.setAlphaF(OWN_TINT_ALPHA * ink.alpha)
        painter.setBrush(tint)
        painter.drawRoundedRect(
            QRectF(at.x() - 6, at.y() - 3, laid.width + 12, laid.height + 6), 6, 6
        )
    if style.own_bar:
        bar = QColor(colour)
        bar.setAlphaF(0.9 * ink.alpha)
        painter.setBrush(bar)
        x = (
            at.x() + laid.width + OWN_BAR_GAP_PX - OWN_BAR_PX
            if style.own_right
            else at.x() - OWN_BAR_GAP_PX
        )
        painter.drawRoundedRect(
            QRectF(x, at.y(), OWN_BAR_PX, laid.height), OWN_BAR_PX / 2, OWN_BAR_PX / 2
        )
    painter.restore()


def _badge(
    painter: QPainter, label: QTextLayout, at: QPointF, colour: QColor
) -> QColor:
    """A filled badge of `colour` behind the label (the Lab's "You" as a
    badge, 305); the colour its words are drawn in on it."""
    if not label.lineCount():
        return colour
    box = label.lineAt(0).naturalTextRect().translated(at)
    across, down = BADGE_PAD
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(colour)
    painter.drawRoundedRect(
        box.adjusted(-across, -down, across, down), box.height() / 2, box.height() / 2
    )
    painter.restore()
    words = QColor("#0a0c10" if colour.lightnessF() > 0.5 else "#ffffff")
    words.setAlphaF(colour.alphaF())
    return words


def _above(
    layout: QTextLayout, row: CaptionRow, ruby: Ruby | None
) -> tuple[tuple[Placed, ...], QFont | None, float]:
    """A laid-out row's reading line where it is drawn, its font, and its
    band's height (kept where the line has no reading: no jump)."""
    if ruby is None:
        return (), None, 0.0
    if not ruby.readings:
        return (), None, ruby.band
    return reading_lines.placed(layout, row.text, ruby), ruby.font, ruby.band


def _laid_text(
    text: str, font: QFont, width: int, right: bool = False, ruby: Ruby | None = None
) -> tuple[QTextLayout, float]:
    """`text` laid out in `font`, wrapped at `width` - lined up on the
    right, with `right`; and its height. `ruby`: its reading line (364) -
    its characters take the room their readings need, and each line has
    the readings' band above it."""
    layout = QTextLayout(text, font)
    if ruby is not None:
        reading_lines.spaced(layout, ruby)
    option = QTextOption()
    option.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
    if right:
        option.setAlignment(Qt.AlignmentFlag.AlignRight)
    layout.setTextOption(option)
    layout.setCacheEnabled(True)
    layout.beginLayout()
    height = 0.0
    while True:
        text_line = layout.createLine()
        if not text_line.isValid():
            break
        if ruby is None:
            text_line.setLineWidth(max(10, width))
            text_line.setPosition(QPointF(0, height))
        else:
            # a line starts its first reading's room in: no reading is cut
            text_line.setLineWidth(max(10, width - max(ruby.before, default=0.0)))
            lead = reading_lines.lead(text, ruby, text_line.textStart())
            height += ruby.band
            text_line.setPosition(QPointF(0.0 if right else lead, height))
        height += text_line.height()
    layout.endLayout()
    return layout, height


def _cjk_share(text: str) -> float:
    """How much of `text` is Chinese or Japanese characters."""
    if not text:
        return 0.0
    cjk = sum(1 for c in text if "⺀" <= c <= "鿿" or "豈" <= c <= "﫿")
    return cjk / len(text)


def _script(text: str) -> str | None:
    """The fonts for text in a language not known, by its script: "ja" with
    kana, "zh" for other Chinese characters, None for neither. Han
    characters are one script in Chinese and Japanese; only the kana say
    it's Japanese (polyglotic-hq 215: such a line was in YaHei, a Chinese
    face, with China's glyph shapes)."""
    if _cjk_share(text) <= 0.3:
        return None
    return "ja" if any(_is_kana(c) for c in text) else "zh"


def _is_kana(c: str) -> bool:
    """Hiragana, katakana (and its extensions), half-width katakana."""
    return "぀" <= c <= "ヿ" or "ㇰ" <= c <= "ㇿ" or "ｦ" <= c <= "ﾟ"


def _italic(line: Line, style: CaptionStyle) -> bool:
    """Whether `line`'s text is drawn italic: still being spoken, and the
    style says so for it."""
    return (style.italic_provisional if line.provisional else style.italic_live) and (
        line.provisional or line.live
    )


def _pairs(line: Line) -> list[Pair]:
    """`line`'s clauses to pour line by line: each one's first row, the
    row under it if it has one, and where both can be cut (`Line.cuts`)."""
    pairs: list[Pair] = []
    for index, row in enumerate(line.rows):
        if row.starts_clause or not pairs:
            pairs.append(Pair((index, row.text)))
            continue
        cuts = line.cuts[row.clause] if row.clause < len(line.cuts) else ()
        pairs[-1] = Pair(pairs[-1].original, (index, row.text), cuts)
    return pairs


def _begun(text: str, font: QFont, ruby: Ruby | None = None) -> QTextLayout:
    """A layout of `text` in `font`, begun: its lines are made and placed
    one by one (a poured row's, `CaptionLayout._poured`). `ruby`: its
    characters take the room their readings need (364)."""
    layout = QTextLayout(text, font)
    if ruby is not None:
        reading_lines.spaced(layout, ruby)
    option = QTextOption()
    option.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
    layout.setTextOption(option)
    layout.setCacheEnabled(True)
    layout.beginLayout()
    return layout


def _rest(
    layout: QTextLayout, y: float, top: float, width: int, right: bool = False
) -> float:
    """Any text of a begun `layout` not yet in a line (none, unless the
    pour and Qt counted its characters differently) in lines of its own
    from `y` down, so nothing said is ever left out; where they end."""
    while True:
        text_line = layout.createLine()
        if not text_line.isValid():
            return y
        text_line.setLineWidth(max(10, width))
        x = max(0.0, width - text_line.naturalTextWidth()) if right else 0.0
        text_line.setPosition(QPointF(x, y - top))
        y += text_line.height()


def _units(text: str, start: int, end: int) -> int:
    """How many of Qt's characters (UTF-16 units) `text[start:end]` is: a
    character outside the basic plane - an emoji, a rare Han character -
    is two."""
    piece = text[start:end]
    if piece.isascii():
        return len(piece)
    return len(piece) + sum(1 for char in piece if ord(char) > 0xFFFF)


TRAIL_ALPHA = 0.6
"""A poured caption's ellipses, this much fainter than the text they join:
they part the clauses, they aren't words."""


def _trails(painter: QPainter, row: LaidRow, at: QPointF, color: QColor) -> None:
    """The ellipses after `row`'s text (drawn at `at`): its joins with the
    next clause, and the ends of lines that run on (the Lab's, 309)."""
    faint = QColor(color)
    faint.setAlphaF(color.alphaF() * TRAIL_ALPHA)
    painter.save()
    painter.setPen(faint)
    painter.setFont(row.layout.font())
    for point in row.trails:
        painter.drawText(QPointF(at.x() + point.x(), at.y() + point.y()), ELLIPSIS)
    painter.restore()
