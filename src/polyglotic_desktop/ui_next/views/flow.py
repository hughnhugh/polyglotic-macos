"""The one caption layout: caption models composed into lines as wide as
the window (polyglotic-hq 340, decision 0132; the user, 2026-11-15: "our
frame can handle the processed data and efficiently customise the lines to
accurately fill screen width").

Every way a window lays its captions is this one composer with different
options (`FlowOptions`), not code of its own:

- **A clause a row** (the default): `cut=CLAUSE` - each clause on a line
  pair of its own, what was said over its translation.
- **Translation below**: `cut=CAPTION` - the caption's clauses run on in
  the upper lines, their translations in the lines below.
- **Line by line**: `cut=CLAUSE, share=True, split=True` - clauses share a
  line pair as they fit, and one that doesn't fit what's left of the pair
  is cut there, on both sides, at the place the fewest word links cross
  (`_split`): none where the languages agree, the nearest thing to it
  where they order their words differently. A line pair is always filled;
  nothing falls back to another shape.
- `aligned`: each part starts at the same place in both lines of its
  pair, so a word's counterpart is under it - in every way of filling
  (polyglotic-hq 372; the user, 2026-11-15, DECISIONS #175: "the parts
  lined up feature should be an independent one click setting which
  applies to every mode"):
  - *Line by line*: as said; the parts of clauses that share a pair too.
  - *A clause a row*: a clause's parts share its pair, lined up; a part
    that doesn't fit what's left of the line starts the clause's next
    pair (a long clause is cut at its parts, not wrapped side by side).
  - *Translation below*: the caption is composed as Line by line's pairs
    (clauses share a pair, parts lined up, nothing cut inside a part),
    then its lines of what was said are gathered over its translation's
    (`_below`): the k-th line of the translation holds the counterparts
    of the k-th line above, each part at its counterpart's place.
  - What can't be lined up honestly: a part wider than a whole line (a
    long stretch of words with no place both sides can be cut) is cut as
    Line by line cuts a clause - both sides, where the fewest word links
    cross, its translation in proportion - so the pairs stay in step and
    each piece starts lined up; inside it, words are where they fall.
    Only a single unit wider than the line is wrapped on lines of its own
    (what was said, then its translation). Text still being spoken has
    no links yet, so no parts: it lines up once it is finished. A part
    much wider than its counterpart leaves a gap after the counterpart:
    that gap is the cost of lining up, and why lines fill less.
- `run_on` (with Line by line): a caption carries on in the line pair
  the one before ended in. A surface lays its captions out one by one, so
  each composition says what it left open (`Flowed.open`: where its last
  line pair's text ends) and the next is composed from there (`entry`):
  its first runs are on that pair, drawn over it. Nothing of the caption
  before is laid out again. A pair that ended with its translation's line
  alone (the translation ran on past what was said) has no line above it
  to take what the next caption said: that starts on the pair below.

- `placing` (polyglotic-hq 458, decision 0215): where a line pair's
  parts go in the room the pair has, once its lines are made - packed
  (each straight after the one before: all of the above), nearest their
  word links (`_near`), or a full pair's spread evenly (`_even`). A pass
  over a finished pair that only moves pieces sideways: every line holds
  the same characters in all three. Finished captions only - text still
  being spoken stays packed.

What it is given, and what it gives back:

- **Models, not rows** (`core.listening.caption_model`): the units a line
  is never broken inside are cut once per clause there; their widths are
  measured once per clause and text size here (`_Sides`), so a resize step
  is arithmetic over numbers already known.
- **Runs** (`Run`): each a place in the caption (`Words`) and where it is
  drawn. Marks, word links, the word under the mouse and a dragged phrase
  go by place, so they are the same in every option.
- **Text already shown never moves when more comes.** A line is filled
  first-fit, in order; a join's ellipsis is drawn in the room that is
  there and never asks for room of its own - so adding a clause or a
  caption changes no line above the one it lands on (`views.pour`
  kept room for the ellipsis only once a clause followed: a word moved
  down a line in 2-3 % of growths, measured in 340).

Plain Python, no Qt: `Fonts` hands in the measuring. Holds no caption text
beyond the models it was given.
"""

from bisect import bisect_right
from collections import OrderedDict, deque
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Protocol

from polyglotic_desktop.core.listening.caption_model import (
    ELLIPSIS,
    CaptionModel,
    ClauseModel,
    Unit,
    Words,
    wide,
)
from polyglotic_desktop.core.listening.captions import Language
from polyglotic_desktop.core.listening.display import RowKind
from polyglotic_desktop.ui_next.views.lab import Fill, Join, Placing
from polyglotic_desktop.ui_next.views.placing import evenly, nearest

SIDES_KEPT = 1200
"""Clause sides whose measured widths are kept: a caption window's 150
captions of four clauses, both sides."""
WORTH_FILLING = 0.1
"""A clause is cut to fill what's left of a line pair only when that is at
least this share of the width: less, and the pair ends there - a word or
two of a clause alone at a line's end reads worse than the room does. (A
quarter of the width, at first: a tenth fills the lines 2 to 4 points
more on recorded captions, and none at all no more than that - 340's
fill3.)"""
CLEAN_CUT = 0.6
"""A cut no word link crosses is taken over the fullest cut when it fills
at least this share of what the fullest would."""
LOOK_BACK = 8
"""How many units back from the fullest cut a clean one is looked for."""
IN_STEP = 0.1
"""How much more of a clause - as a share of its width - a line may hold of
what was said than the line under it holds of its translation."""
FIT = 0.5
"""Pixels a line may run over the width: the measuring's rounding."""


class Cut(StrEnum):
    """What a line pair holds together."""

    CAPTION = "caption"
    """The whole caption: what was said in the upper lines, its
    translation in the lines below."""
    CLAUSE = "clause"
    """A clause, over its translation."""


@dataclass(frozen=True, slots=True)
class FlowOptions:
    """How captions are laid in lines (the module's docstring)."""

    cut: Cut = Cut.CLAUSE
    share: bool = False
    split: bool = False
    aligned: bool = False
    run_on: bool = False
    join: Join = Join.ELLIPSIS
    show_original: bool = True
    placing: Placing = Placing.PACKED


def flow_options(
    fill: Fill,
    join: Join = Join.ELLIPSIS,
    show_original: bool = True,
    run_on: bool = False,
    aligned: bool = False,
    placing: Placing = Placing.PACKED,
) -> FlowOptions:
    """The Lab's choices as the composer's options. `run_on` is Line by
    line's: only there do a clause and its translation share a line pair
    with others. `aligned` lines parts up in every one (372); `placing`
    says where a line pair's parts go in the room it has (458)."""
    if fill is Fill.STACKED:
        return FlowOptions(
            Cut.CAPTION,
            aligned=aligned,
            join=join,
            show_original=show_original,
            placing=placing,
        )
    if fill is Fill.PAIRED:
        return FlowOptions(
            share=True,
            split=True,
            aligned=aligned,
            run_on=run_on,
            join=join,
            show_original=show_original,
            placing=placing,
        )
    return FlowOptions(
        aligned=aligned, join=join, show_original=show_original, placing=placing
    )


class Font(Protocol):
    """One font's measuring: how wide it draws text, its ascent, and
    what's below the baseline (the room for a word link's underline
    included)."""

    ascent: float
    below: float

    def width(self, text: str) -> float: ...


class Fonts(Protocol):
    """The measuring a composer needs: the font a side's text is drawn in
    (`text`: the clause's - a language not named is told by its script)."""

    def font(self, side: RowKind, language: Language | None, text: str) -> Font: ...


@dataclass(frozen=True, slots=True)
class Above:
    """A reading line over a side's text (polyglotic-hq 364: pinyin over
    Chinese): the room each character takes with it - `before[n]` and
    `after[n]` pixels each side of character `n`, so a reading wider than
    its characters has room and stays centred on them - and `band`, the
    height the line gets above its text."""

    before: Sequence[float]
    after: Sequence[float]
    band: float

    def room(self, start: int, end: int) -> float:
        """The room added to characters `[start, end)`."""
        return sum(self.before[start:end]) + sum(self.after[start:end])


Readable = Callable[[RowKind, Language | None, str], Above | None]
"""The reading line over a side's text in a language, as the surface
draws it; None: none."""


@dataclass(frozen=True, slots=True)
class Gaps:
    """The room between lines, in pixels: between what was said and its
    translation, and between line pairs."""

    row: float = 2.0
    pair: float = 8.0


@dataclass(frozen=True, slots=True)
class Run:
    """Words of caption `caption` (its index among those composed) drawn
    from `x`, `width` wide - the spaces after them not counted."""

    caption: int
    words: Words
    x: float
    width: float


@dataclass(frozen=True, slots=True)
class FlowLine:
    """One line of text: its runs, left to right; where its ellipses are
    drawn (`joins`: each the x it starts at); where it ends; its top
    within the composition, its ascent and height; and its line pair."""

    side: RowKind
    runs: tuple[Run, ...]
    joins: tuple[float, ...]
    end: float
    top: float
    ascent: float
    height: float
    pair: int


@dataclass(frozen=True, slots=True)
class OpenLine:
    """One line of a line pair left open: where its text ends, and what
    the next text on it needs to know of the text before - a space's and
    an ellipsis's width in its font, whether it ends in a script written
    without spaces, and the line's ascent and room below."""

    end: float
    space: float
    dots: float
    tight: bool
    ascent: float
    below: float


@dataclass(frozen=True, slots=True)
class Open:
    """The line pair a composition ended in, for the next caption to carry
    on in (`FlowOptions.run_on`): its lines (None: the pair has none on
    that side) and its height - how far above the composition's end it
    starts."""

    upper: OpenLine | None
    lower: OpenLine | None
    height: float


@dataclass(frozen=True, slots=True)
class Flowed:
    """Captions composed: their lines, top to bottom, and the height.
    `open`: the line pair it ended in, if the next caption may carry on
    there."""

    lines: tuple[FlowLine, ...]
    height: float
    width: float
    open: Open | None = None

    @property
    def breaks(self) -> tuple[float, ...]:
        """Where each line ends, from the top."""
        return tuple(line.top + line.height for line in self.lines)

    def runs_of(self, caption: int, words: Words) -> list[tuple[int, Run]]:
        """The runs holding characters of `words`: each with its line's
        index."""
        return [
            (n, run)
            for n, line in enumerate(self.lines)
            for run in line.runs
            if run.caption == caption and run.words.meets(words)
        ]


class _Side:
    """One side of a clause, measured: each unit's width without and with
    the spaces after it, and its font's line."""

    __slots__ = (
        "ascent",
        "below",
        "cum",
        "dots",
        "language",
        "space",
        "starts",
        "text",
        "units",
        "whole",
        "word",
    )

    def __init__(
        self,
        text: str,
        units: tuple[Unit, ...],
        side: RowKind,
        language: Language | None,
        fonts: Fonts,
        above: Above | None = None,
    ) -> None:
        self.text, self.units, self.language = text, units, language
        font = fonts.font(side, language, text)
        width = font.width
        self.word = [width(text[a:b]) for a, b, _ in units]
        self.whole = [
            word if after == b else width(text[a:after])
            for word, (a, b, after) in zip(self.word, units, strict=True)
        ]
        if above is not None:  # a unit is as wide as its reading needs
            self.word = [
                word + above.room(a, b)
                for word, (a, b, _) in zip(self.word, units, strict=True)
            ]
            self.whole = [
                whole + above.room(a, after)
                for whole, (a, _, after) in zip(self.whole, units, strict=True)
            ]
        self.cum = [0.0]
        for whole in self.whole:
            self.cum.append(self.cum[-1] + whole)
        self.starts = [a for a, _, _ in units]
        self.space = width(" ")
        self.dots = width(ELLIPSIS)
        self.ascent, self.below = font.ascent, font.below
        if above is not None:
            self.ascent += above.band

    def width(self, first: int, end: int) -> float:
        """Units `[first, end)` on one line, the last one's spaces left off."""
        if end <= first:
            return 0.0
        return self.cum[end - 1] - self.cum[first] + self.word[end - 1]

    def unit_at(self, char: int) -> int:
        """The unit that starts at character `char` (the count of units
        for the text's end)."""
        for n, start in enumerate(self.starts):
            if start >= char:
                return n
        return len(self.starts)

    def span(self, first: int, start: int, end: int) -> tuple[float, float]:
        """Where characters `[start, end)` are drawn, from the start of
        unit `first`: their left and right edges - a place inside a unit
        by its share of the unit's characters."""
        return self._at(first, start, start), self._at(first, max(start, end - 1), end)

    def _at(self, first: int, within: int, char: int) -> float:
        """The x of `char`, in the unit holding character `within`."""
        unit = max(first, bisect_right(self.starts, within) - 1)
        a, b, _ = self.units[unit]
        share = min(max(char - a, 0), b - a) / (b - a) if b > a else 0.0
        return self.cum[unit] - self.cum[first] + self.word[unit] * share

    def fitting(self, first: int, end: int, room: float) -> int:
        """The most units from `first` that fit in `room`: where they end."""
        fits = first
        while fits < end and self.width(first, fits + 1) <= room + FIT:
            fits += 1
        return fits


@dataclass(slots=True)
class _Piece:
    """Units `[first, end)` of one side of a clause."""

    caption: int
    clause: int
    side: RowKind
    measured: _Side
    first: int
    end: int

    @property
    def width(self) -> float:
        return self.measured.width(self.first, self.end)

    @property
    def chars(self) -> tuple[int, int]:
        """The characters of its side it holds."""
        units = self.measured.units
        return units[self.first][0], units[self.end - 1][2]


@dataclass(slots=True)
class _Item:
    """A piece on a line whose parts are placed (458): where the packed
    line has it (`least`) and where it is (`x`); its run and, if a join's
    ellipsis stands before it, that one's place in the line's joins and
    its distance from the text before (`before`); the room it keeps after
    the text before it (`lead`); its segment's number (the two pieces of
    a part share one) and its clause."""

    piece: _Piece
    least: float
    x: float
    run: int
    mark: int | None
    before: float
    lead: float
    part: int
    model: ClauseModel

    @property
    def end(self) -> float:
        return self.x + self.piece.width

    def centre(self, start: int, end: int) -> float:
        """Where characters `[start, end)` of its side have their middle."""
        left, right = self.piece.measured.span(self.piece.first, start, end)
        return self.x + (left + right) / 2.0


@dataclass(slots=True)
class _Segment:
    """What a line pair takes whole, or is cut to take: a clause's piece
    of what was said and of its translation (either may be missing).
    `ends`: its clause ends with it - a join follows."""

    top: _Piece | None
    bottom: _Piece | None
    ends: bool
    model: ClauseModel


class _Row:
    """A line being filled."""

    __slots__ = (
        "ascent",
        "below",
        "carried",
        "closing",
        "ended",
        "items",
        "joins",
        "last",
        "runs",
        "side",
        "text_end",
    )

    def __init__(
        self, side: RowKind, carried: OpenLine | None = None, placing: bool = False
    ) -> None:
        """`carried`: the line already holds the caption before's text, as
        far as `carried.end` (run-on): this one's goes after it.
        `placing`: its pieces are kept apart, to be placed (458)."""
        self.side = side
        self.items: list[_Item] | None = [] if placing else None
        self.closing: int | None = None  # its closing ellipsis, in `joins`
        self.runs: list[Run] = []
        self.joins: list[float] = []
        self.text_end = 0.0
        self.ended = False  # the last piece on it ended its clause
        self.last: _Piece | None = None
        self.ascent = self.below = 0.0
        self.carried = carried
        if carried is not None:
            self.text_end = carried.end
            self.ended = True  # a caption's end ends its clause
            self.ascent, self.below = carried.ascent, carried.below

    @property
    def empty(self) -> bool:
        return not self.runs and self.carried is None

    def _before(self) -> tuple[float, float, bool] | None:
        """Of the text before on this line: a space's width, an
        ellipsis's, and whether it ends in a script without spaces."""
        last = self.last
        if last is not None:
            measured = last.measured
            return measured.space, measured.dots, _tight(measured.text)
        carried = self.carried
        if carried is not None:
            return carried.space, carried.dots, carried.tight
        return None

    def open(self) -> OpenLine | None:
        """The line as the next caption finds it; None if it has no text."""
        before = self._before()
        if before is None:
            return None
        return OpenLine(self.text_end, *before, self.ascent, self.below)

    @property
    def end(self) -> float:
        return self.text_end

    def lead(self, piece: _Piece, join: Join) -> tuple[float, float | None]:
        """The room before `piece` here, after what's on the line - and
        where the join's ellipsis goes in it (None: none)."""
        last = self.last
        found = self._before()
        if found is None:
            return 0.0, None
        if last is not None and not self.ended:
            # the same clause runs on: its own spaces
            measured = last.measured
            return measured.whole[last.end - 1] - measured.word[last.end - 1], None
        space, dots, tight = found
        first = piece.measured.text[piece.measured.units[piece.first][0]]
        between = 0.0 if tight or wide(first) else space
        if join is Join.SPACE:
            return between, None
        before = 0.0 if tight else space * 0.5
        return before + dots + between, self.text_end + before

    def add(
        self,
        piece: _Piece,
        x: float,
        ends: bool,
        mark: float | None,
        part: tuple[int, ClauseModel, float] | None = None,
    ) -> None:
        """`part`, on a line whose pieces are placed: the piece's
        segment's number, its clause and the room it keeps before it."""
        measured = piece.measured
        if self.items is not None and part is not None:
            self.items.append(
                _Item(
                    piece,
                    x,
                    x,
                    len(self.runs),
                    len(self.joins) if mark is not None else None,
                    mark - self.text_end if mark is not None else 0.0,
                    part[2],
                    part[0],
                    part[1],
                )
            )
        if mark is not None:
            self.joins.append(mark)
        start = measured.units[piece.first][0]
        end = measured.units[piece.end - 1][2]
        width = piece.width
        words = Words(piece.side, piece.clause, start, end)
        last = self.runs[-1] if self.runs else None
        if (
            last is not None
            and self.items is None
            and mark is None
            and last.caption == piece.caption
            and last.words.clause == piece.clause
            and last.words.end == start
            and abs(self.text_end + self.lead_natural() - x) < FIT
        ):
            joined = Words(piece.side, piece.clause, last.words.start, end)
            self.runs[-1] = Run(piece.caption, joined, last.x, x + width - last.x)
        else:
            self.runs.append(Run(piece.caption, words, x, width))
        self.text_end = x + width
        self.ended = ends
        self.last = piece
        self.ascent = max(self.ascent, measured.ascent)
        self.below = max(self.below, measured.below)

    def lead_natural(self) -> float:
        last = self.last
        if last is None or self.ended:
            return 0.0
        return last.measured.whole[last.end - 1] - last.measured.word[last.end - 1]

    def put(self, shifts: Sequence[float]) -> None:
        """Its pieces each `shifts` right of where the packed line has
        them (458): their runs, the ellipses before them (each stays with
        the text it follows) and the line's end move with them."""
        items = self.items
        if not items:
            return
        was = items[-1].end
        end = self.carried.end if self.carried is not None else 0.0
        for item, shift in zip(items, shifts, strict=True):
            item.x = item.least + shift
            run = self.runs[item.run]
            self.runs[item.run] = Run(run.caption, run.words, item.x, run.width)
            if item.mark is not None:
                self.joins[item.mark] = end + item.before
            end = item.end
        moved = end - was
        if self.closing is not None:
            self.joins[self.closing] += moved
        self.text_end += moved

    def closes(self, join: Join, width: float, more: bool) -> float | None:
        """The room its closing ellipsis takes after its text (`close`);
        None: it has none."""
        found = self._before()
        if found is None or not more or join is Join.SPACE:
            return None
        if not self.ended and join is not Join.LINE_ENDS:
            return None
        space, dots, tight = found
        before = 0.0 if tight else space * 0.5
        if self.text_end + before + dots <= width + FIT:
            return before + dots
        return None

    def close(self, join: Join, width: float, more: bool) -> None:
        """The line ends here; `more`: text follows it. An ellipsis at its
        end where the join asks for one, if there is room - never room
        made for it."""
        room = self.closes(join, width, more)
        if room is None:
            return
        found = self._before()
        assert found is not None
        self.closing = len(self.joins)
        self.joins.append(self.text_end + room - found[1])
        self.text_end += room


_Starts = tuple[float, float, float | None, float | None]
"""Where a segment's pieces start on a pair - its upper line, its lower -
and where each line's join's ellipsis goes (None: none)."""


def _below(rows: list[tuple[_Row, int, bool]], first: int, pair: int) -> int:
    """A caption's rows from `first` on, composed as Line by line's pairs,
    put as Translation below has them: its lines of what was said, then
    its translation's, as one pair numbered `pair` - so the k-th line of
    the translation holds the counterparts of the k-th line of what was
    said, each part where its counterpart starts (372). The next pair's
    number."""
    mine = rows[first:]
    if not mine:
        return pair
    said = [row for row, _, _ in mine if row.side is RowKind.ORIGINAL]
    meant = [row for row, _, _ in mine if row.side is not RowKind.ORIGINAL]
    rows[first:] = [(row, pair, n == 0) for n, row in enumerate(said + meant)]
    return pair + 1


def _tight(text: str) -> bool:
    """Whether `text` ends in a script written without spaces: its
    punctuation brings its own room."""
    end = text.rstrip()
    return bool(end) and wide(end[-1])


class Flow:
    """Composes captions into lines; keeps each clause's measured widths
    while its model is the same object. One per surface and text size
    (`forget` on a change of fonts); not thread-safe."""

    def __init__(
        self,
        fonts: Fonts,
        gaps: Gaps | None = None,
        above: Readable | None = None,
    ) -> None:
        """`above`: the reading line over a side's text, if it has one
        (polyglotic-hq 364): its units are measured with the room it
        needs, and its lines are taller by its band."""
        self.fonts = fonts
        self.gaps = gaps or Gaps()
        self.above = above
        self.measured = 0  # clause sides measured since made: what tests count
        self._sides: OrderedDict[tuple[int, RowKind], tuple[ClauseModel, _Side]] = (
            OrderedDict()
        )

    def forget(self) -> None:
        """The fonts changed: everything is measured again."""
        self._sides.clear()

    def _side(
        self, clause: ClauseModel, side: RowKind, original: Language | None
    ) -> _Side:
        key = (id(clause), side)
        found = self._sides.get(key)
        if found is not None and found[0] is clause:
            self._sides.move_to_end(key)
            return found[1]
        language = original if side is RowKind.ORIGINAL else clause.language
        text = clause.text(side)
        above = self.above(side, language, text) if self.above else None
        made = _Side(text, clause.units(side), side, language, self.fonts, above)
        self._sides[key] = (clause, made)
        self.measured += 1
        if len(self._sides) > SIDES_KEPT:
            self._sides.popitem(last=False)
        return made

    # -- composing -----------------------------------------------------------------

    def compose(
        self,
        captions: Sequence[CaptionModel],
        width: float,
        options: FlowOptions,
        right: bool = False,
        top: float = 0.0,
        trail: bool = True,
        entry: Open | None = None,
    ) -> Flowed:
        """`captions` - one, or those that run together - in lines `width`
        wide, from `top` down. `right`: lined up on the right (the
        learner's own speech). `trail`: a caption still being spoken ends
        with an ellipsis. `entry`: the line pair the caption before left
        open (its `Flowed.open`): the first lines here are that pair's,
        this text after what they hold - `top` is that pair's top."""
        # Translation below, lined up (372): Line by line's pairs, each
        # caption's lines of what was said then gathered over its translation's
        lined_below = options.cut is Cut.CAPTION and options.aligned
        if lined_below:
            options = replace(
                options, cut=Cut.CLAUSE, share=True, split=False, run_on=False
            )
        if not options.share and options.cut is Cut.CLAUSE:
            options = replace(options, join=Join.SPACE)  # a clause a row: no joins
        runs_on = options.share and options.run_on and not right
        if not runs_on:
            entry = None
        rows: list[tuple[_Row, int, bool]] = []  # the row, its pair, starts a pair
        pair = 0
        # parts are placed once a caption is finished (458): text still
        # being spoken has no links yet, and must not move as more comes
        places = options.placing is not Placing.PACKED and not any(
            caption.live for caption in captions
        )
        number = 0  # the segments placed so far: a part's two pieces share one
        upper = _Row(RowKind.ORIGINAL, entry.upper if entry else None, places)
        lower = _Row(RowKind.TRANSLATION, entry.lower if entry else None, places)
        left_open: tuple[_Row, _Row] | None = None
        # The pair the caption before ended in holds its translation's last
        # line and nothing of what was said: no upper line can go over that
        # one now - text already shown never moves - so this caption's text
        # takes it only where none of what was said comes with it (366).
        barred = upper.empty and not lower.empty

        def close(more: bool, full: bool = False, last: bool = False) -> None:
            """The pair ends here. `full`: because what came next didn't
            fit it; `last`: the composition's last (run-on leaves it open
            for the caption after)."""
            nonlocal upper, lower, pair, left_open, barred
            barred = False
            left_open = None if upper.empty and lower.empty else (upper, lower)
            if places and options.placing is Placing.NEAREST:
                self._near(upper, lower, options, width, more, runs_on and last, right)
            first = True
            for row in (upper, lower):
                if row.empty:
                    continue
                row.close(options.join, width, more)
                rows.append((row, pair, first))
                first = False
            if places and full and options.placing is Placing.EVENLY:
                self._even(upper, lower, width)
            if not first:
                pair += 1
            upper = _Row(RowKind.ORIGINAL, None, places)
            lower = _Row(RowKind.TRANSLATION, None, places)

        def place(segment: _Segment, starts: _Starts) -> None:
            nonlocal number
            self._place(
                segment, starts, upper, lower, number if places else None, options.join
            )
            number += 1

        def block(segment: _Segment, more: bool) -> None:
            """A segment in lines of its own: what was said wrapped over
            the lines it needs, then its translation."""
            nonlocal pair
            first = True
            for piece in (segment.top, segment.bottom):
                if piece is None:
                    continue
                for row in self._wrapped([(piece, segment.ends)], width, options, more):
                    rows.append((row, pair, first))
                    first = False
            pair += 1

        for index, caption in enumerate(captions):
            last_caption = index == len(captions) - 1
            if options.cut is Cut.CAPTION:
                close(True)
                self._stacked(index, caption, width, options, rows, pair)
                pair += 1
                continue
            if index:
                barred = upper.empty and not lower.empty
            first_row, first_pair = len(rows), pair
            pending = deque(self._segments(index, caption, options))
            while pending:
                segment = pending.popleft()
                more = bool(pending) or not last_caption
                if barred and segment.top is not None:
                    close(True)
                    pending.appendleft(segment)
                    continue
                starts = self._starts(segment, upper, lower, options)
                if self._fits(segment, starts, width):
                    place(segment, starts)
                    # a clause a row: its parts, lined up, share its pair (372)
                    if not options.share and segment.ends:
                        close(more)
                    continue
                # lined up, a part wider than a whole line is cut as Line by
                # line cuts (372): both sides, so the pairs stay in step
                too_wide = options.aligned and upper.empty and lower.empty
                if options.split or too_wide:
                    cut = self._split(
                        segment, starts, upper.empty and lower.empty, width
                    )
                    if cut is not None:
                        first, rest = cut
                        place(first, starts)
                        close(True, full=True)
                        pending.appendleft(rest)
                        continue
                if not (upper.empty and lower.empty):
                    close(True, full=True)
                    pending.appendleft(segment)
                    continue
                block(segment, more)
            if not (options.share and options.run_on):
                close(not last_caption)
            if lined_below:
                pair = _below(rows, first_row, first_pair)
        close(False, last=True)
        live = bool(captions) and captions[-1].live
        still_open = left_open if runs_on and not live else None
        if trail and captions and captions[-1].live and rows:
            row = rows[-1][0]  # still being spoken: it trails off
            if row.last is not None:
                before = (
                    0.0 if _tight(row.last.measured.text) else row.last.measured.space
                )
                row.joins.append(row.text_end + before)
                row.text_end += before + row.last.measured.dots
        placed = self._placed(rows, width, right, options, top)
        if still_open is None:
            return placed
        said, meant = still_open[0].open(), still_open[1].open()
        tall = sum(line.ascent + line.below for line in (said, meant) if line)
        if said is not None and meant is not None:
            tall += self.gaps.row
        return replace(placed, open=Open(said, meant, tall))

    def _segments(
        self, index: int, caption: CaptionModel, options: FlowOptions
    ) -> list[_Segment]:
        found: list[_Segment] = []
        for n, clause in enumerate(caption.clauses):
            translated = bool(clause.translation)
            shows_original = options.show_original or not translated
            parts = (
                clause.parts
                if options.aligned and translated and shows_original
                else (((0, len(clause.original)), (0, len(clause.translation or ""))),)
            )
            for k, ((a, b), (c, d)) in enumerate(parts):
                top = bottom = None
                if shows_original and clause.original_units:
                    said = self._side(clause, RowKind.ORIGINAL, caption.language)
                    first, end = said.unit_at(a), said.unit_at(b)
                    if end > first:
                        top = _Piece(index, n, RowKind.ORIGINAL, said, first, end)
                if translated and clause.translation_units:
                    meant = self._side(clause, RowKind.TRANSLATION, caption.language)
                    first, end = meant.unit_at(c), meant.unit_at(d)
                    if end > first:
                        bottom = _Piece(
                            index, n, RowKind.TRANSLATION, meant, first, end
                        )
                if top is not None or bottom is not None:
                    found.append(_Segment(top, bottom, k == len(parts) - 1, clause))
        return found

    def _starts(
        self, segment: _Segment, upper: _Row, lower: _Row, options: FlowOptions
    ) -> _Starts:
        """Where `segment`'s pieces would start on the pair being filled -
        its upper line, its lower - and where each line's join's ellipsis
        would go."""
        top_at = bottom_at = 0.0
        top_mark = bottom_mark = None
        if segment.top is not None:
            lead, top_mark = upper.lead(segment.top, options.join)
            top_at = upper.text_end + lead
        if segment.bottom is not None:
            lead, bottom_mark = lower.lead(segment.bottom, options.join)
            bottom_at = lower.text_end + lead
        if options.aligned:
            top_at = bottom_at = max(top_at, bottom_at, upper.text_end, lower.text_end)
        return top_at, bottom_at, top_mark, bottom_mark

    @staticmethod
    def _fits(segment: _Segment, starts: _Starts, width: float) -> bool:
        top_at, bottom_at, _, _ = starts
        return all(
            at + piece.width <= width + FIT
            for piece, at in ((segment.top, top_at), (segment.bottom, bottom_at))
            if piece is not None
        )

    @staticmethod
    def _place(
        segment: _Segment,
        starts: _Starts,
        upper: _Row,
        lower: _Row,
        number: int | None = None,
        join: Join = Join.ELLIPSIS,
    ) -> None:
        """`number`: the segment's, where a pair's parts are placed (458)."""
        top_at, bottom_at, top_mark, bottom_mark = starts
        for piece, row, at, mark in (
            (segment.top, upper, top_at, top_mark),
            (segment.bottom, lower, bottom_at, bottom_mark),
        ):
            if piece is None:
                continue
            part = None
            if number is not None:
                part = (number, segment.model, row.lead(piece, join)[0])
            row.add(piece, at, segment.ends, mark, part)

    # -- placing a pair's parts (458) ------------------------------------------------

    def _near(
        self,
        upper: _Row,
        lower: _Row,
        options: FlowOptions,
        width: float,
        more: bool,
        stays_open: bool,
        right: bool,
    ) -> None:
        """The pair's parts moved to where their word links are shortest,
        in the room the packed pair leaves - so every part still starts on
        the line, and the pair, it does when packed.

        *Lined up*: a part's two pieces share a slot as wide as the wider
        one, and the narrower one moves inside it - over (or under) the
        words it is linked to, instead of at the slot's start. A part's
        links never leave it (`matching_cuts`), so each slot is settled by
        itself. *Not lined up*: the fuller line of the two stays as it is,
        text from the left edge, and the other line's pieces move as a
        row, in order, over (or under) it (`placing.nearest`: the least
        total there is for that line; moving the fuller one as well
        gained about 1 % at most on real captions, 458's measure, and
        left its text starting away from the edge). A pair left open for the
        caption after (`stays_open`) keeps that caption's start where it
        is, or nearly: lined up, its last piece stops short of the slot's
        end by the room a join takes; not, the line that moves ends no
        further right than the fuller one."""
        if options.aligned:
            self._near_parts(upper, lower, stays_open)
        elif not right:
            self._near_rows(upper, lower, options, width, more, stays_open)

    def _near_parts(self, upper: _Row, lower: _Row, stays_open: bool) -> None:
        over, under = upper.items or [], lower.items or []
        tops = {item.part: n for n, item in enumerate(over)}
        shifts = {id(over): [0.0] * len(over), id(under): [0.0] * len(under)}
        for m, below in enumerate(under):
            n = tops.get(below.part)
            if n is None:
                continue
            above = over[n]
            if above.piece.width <= below.piece.width:
                items, at, item, facing = over, n, above, below
            else:
                items, at, item, facing = under, m, below, above
            most = facing.end - item.end
            if at + 1 < len(items):
                after = items[at + 1]
                most = min(most, after.least - after.lead - item.end)
            elif stays_open:
                # the caption after starts past both lines' ends and the
                # room it keeps: no further right than it would be anyway
                measured = item.piece.measured
                most -= measured.space * 1.5 + measured.dots
            wants = self._wants(item, [facing])
            if most > 0.0 and wants:
                shifts[id(items)][at] = nearest([wants], most)[0]
        upper.put(shifts[id(over)])
        lower.put(shifts[id(under)])

    def _near_rows(
        self,
        upper: _Row,
        lower: _Row,
        options: FlowOptions,
        width: float,
        more: bool,
        stays_open: bool,
    ) -> None:
        if not upper.items or not lower.items:
            return
        row, fuller = sorted((upper, lower), key=lambda row: row.text_end)
        if stays_open:
            # no further right than the fuller line ends: the caption
            # after starts no later on the line that decides what fits
            most = fuller.text_end - row.text_end
        else:
            closing = row.closes(options.join, width, more) or 0.0
            most = width - closing - row.text_end
        facing = fuller.items or []
        row.put(nearest([self._wants(item, facing) for item in row.items or []], most))

    @staticmethod
    def _wants(item: _Item, facing: Sequence[_Item]) -> list[float]:
        """How far right `item` would have each of its linked words right
        over (or under) its counterpart, where that is in `facing`."""
        piece = item.piece
        start, end = piece.chars
        said = piece.side is RowKind.ORIGINAL
        wants: list[float] = []
        for pairs in item.model.pairs:
            for span in pairs.original:
                mine, theirs = (
                    (span, pairs.translation) if said else (pairs.translation, span)
                )
                if not start <= mine[0] < end:
                    continue
                for other in facing:
                    if (
                        other.model is not item.model
                        or other.piece.caption != piece.caption
                    ):
                        continue
                    low, high = other.piece.chars
                    if low <= theirs[0] < high:
                        wants.append(other.centre(*theirs) - item.centre(*mine))
                        break
        return wants

    @staticmethod
    def _even(upper: _Row, lower: _Row, width: float) -> None:
        """A full pair's pieces spread over the width, each line's by
        themselves, with the same room between every two - the links
        drawn as they fall. Lined up, the pieces are the parts and each
        line holds what it does lined up; where a part starts is no
        longer its counterpart's place."""
        for row in (upper, lower):
            items = row.items or []
            if not items:
                continue
            after = row.text_end - items[-1].end  # its closing ellipsis
            end = row.carried.end if row.carried is not None else 0.0
            natural = []  # each straight after the one before
            for item in items:
                natural.append(end + item.lead)
                end = natural[-1] + item.piece.width
            spread = evenly(len(items), width - end - after, row.carried is not None)
            row.put(
                [
                    x + more - item.least
                    for item, x, more in zip(items, natural, spread, strict=True)
                ]
            )

    def _split(
        self,
        segment: _Segment,
        starts: _Starts,
        empty: bool,
        width: float,
    ) -> tuple[_Segment, _Segment] | None:
        """`segment` cut in two so its first part fills what's left of the
        line pair: on both sides, where the fewest word links cross - a
        cut none crosses if one fills at least `CLEAN_CUT` of what the
        fullest would, else the fullest, its translation cut in
        proportion. None: not worth it (little room left, and the pair
        has text), or not even one unit fits."""
        top_at, bottom_at, _, _ = starts
        top, bottom = segment.top, segment.bottom
        if not empty and width - max(top_at, bottom_at) < WORTH_FILLING * width:
            return None
        if top is None or bottom is None:
            piece = top if top is not None else bottom
            assert piece is not None
            at = top_at if top is not None else bottom_at
            cut = piece.measured.fitting(piece.first, piece.end, width - at)
            if cut <= piece.first or cut >= piece.end:
                return None
            return self._halves(segment, cut if top else None, None if top else cut)
        said, meant = top.measured, bottom.measured
        most = said.fitting(top.first, top.end, width - top_at)
        most_meant = meant.fitting(bottom.first, bottom.end, width - bottom_at)
        if most <= top.first or most_meant <= bottom.first:
            return None
        whole_said, whole_meant = top.width, bottom.width
        # no more of what was said than of its translation: the wider
        # language fills the line, the other keeps in step with it
        share = meant.width(bottom.first, most_meant) / whole_meant
        while (
            most > top.first + 1
            and said.width(top.first, most) / whole_said > share + IN_STEP
        ):
            most -= 1
        spans = [
            (a, b, *pairs.translation)
            for pairs in segment.model.pairs
            for a, b in pairs.original
        ]
        fullest: tuple[int, int] | None = None
        for p in range(most, max(top.first, most - LOOK_BACK), -1):
            share = said.width(top.first, p) / whole_said if whole_said else 1.0
            wanted = share * whole_meant
            q = self._meant_cut(bottom, most_meant, wanted, None)
            if fullest is None:
                fullest = (p, q)
            if said.width(top.first, p) < CLEAN_CUT * said.width(top.first, most):
                break
            at = said.starts[p] if p < len(said.starts) else len(said.text)
            if any(a < at < b for a, b, _, _ in spans):
                continue  # inside a linked word
            low = max((d for _, b, _, d in spans if b <= at), default=0)
            high = min((c for a, _, c, _ in spans if a >= at), default=len(meant.text))
            if low > high:
                continue  # the links cross here
            clean = self._meant_cut(bottom, most_meant, wanted, (low, high))
            if clean is not None and (p, clean) != (top.end, bottom.end):
                return self._halves(segment, p, clean)
        if fullest is None or fullest == (top.end, bottom.end):
            return None
        return self._halves(segment, *fullest)

    @staticmethod
    def _meant_cut(
        piece: _Piece, most: int, wanted: float, within: tuple[int, int] | None
    ) -> int:
        """Where to cut a translation's piece: the unit boundary, no later
        than `most`, whose width from the piece's start is nearest
        `wanted` - among those starting in `within` (characters), if
        given; None if none does."""
        measured = piece.measured
        best: int | None = None
        nearest = 0.0
        for q in range(piece.first + 1, most + 1):
            at = measured.starts[q] if q < len(measured.starts) else len(measured.text)
            if within is not None and not within[0] <= at <= within[1]:
                continue
            off = abs(measured.width(piece.first, q) - wanted)
            if best is None or off < nearest:
                best, nearest = q, off
        if best is None and within is None:
            best = piece.first + 1
        return best  # type: ignore[return-value]

    @staticmethod
    def _halves(
        segment: _Segment, top_cut: int | None, bottom_cut: int | None
    ) -> tuple[_Segment, _Segment]:
        def cut(piece: _Piece | None, at: int | None) -> tuple[_Piece | None, ...]:
            if piece is None or at is None:
                return None, None
            first = _Piece(
                piece.caption, piece.clause, piece.side, piece.measured, piece.first, at
            )
            rest = _Piece(
                piece.caption, piece.clause, piece.side, piece.measured, at, piece.end
            )
            return (first if at > piece.first else None), (
                rest if at < piece.end else None
            )

        top_first, top_rest = cut(segment.top, top_cut)
        bottom_first, bottom_rest = cut(segment.bottom, bottom_cut)
        return (
            _Segment(top_first, bottom_first, False, segment.model),
            _Segment(top_rest, bottom_rest, segment.ends, segment.model),
        )

    def _stacked(
        self,
        index: int,
        caption: CaptionModel,
        width: float,
        options: FlowOptions,
        rows: list[tuple[_Row, int, bool]],
        pair: int,
    ) -> None:
        """The whole caption: what was said in the upper lines, its
        translation in the lines below."""
        said: list[tuple[_Piece, bool]] = []
        meant: list[tuple[_Piece, bool]] = []
        for n, clause in enumerate(caption.clauses):
            translated = bool(clause.translation) and bool(clause.translation_units)
            if (options.show_original or not translated) and clause.original_units:
                side = self._side(clause, RowKind.ORIGINAL, caption.language)
                piece = _Piece(index, n, RowKind.ORIGINAL, side, 0, len(side.units))
                said.append((piece, True))
            if translated:
                side = self._side(clause, RowKind.TRANSLATION, caption.language)
                piece = _Piece(index, n, RowKind.TRANSLATION, side, 0, len(side.units))
                meant.append((piece, True))
        first = True
        for pieces in (said, meant):
            for row in self._wrapped(pieces, width, options, False):
                rows.append((row, pair, first))
                first = False

    def _wrapped(
        self,
        pieces: Sequence[tuple[_Piece, bool]],
        width: float,
        options: FlowOptions,
        more: bool,
    ) -> list[_Row]:
        """`pieces` (each with whether its clause ends with it), one
        stream, wrapped over the lines it needs."""
        found: list[_Row] = []
        if not pieces:
            return found
        row = _Row(pieces[0][0].side)
        for piece, ends in pieces:
            measured = piece.measured
            for unit in range(piece.first, piece.end):
                one = _Piece(
                    piece.caption, piece.clause, piece.side, measured, unit, unit + 1
                )
                lead, mark = row.lead(one, options.join)
                if not row.empty and row.text_end + lead + one.width > width + FIT:
                    row.close(options.join, width, True)
                    found.append(row)
                    row = _Row(piece.side)
                    lead, mark = 0.0, None
                row.add(one, row.text_end + lead, ends and unit == piece.end - 1, mark)
        row.close(options.join, width, more)
        found.append(row)
        return found

    def _placed(
        self,
        rows: Sequence[tuple[_Row, int, bool]],
        width: float,
        right: bool,
        options: FlowOptions,
        top: float,
    ) -> Flowed:
        """The rows as lines, top to bottom: no room between the lines of
        one stream, the row gap under what was said, the pair gap between
        line pairs. `right`: each line against the right edge - a line
        pair together, when its parts are lined up."""
        lines: list[FlowLine] = []
        y = top
        ends: dict[int, float] = {}
        for row, pair, _ in rows:
            ends[pair] = max(ends.get(pair, 0.0), row.end)
        before: tuple[int, RowKind] | None = None
        for row, pair, _ in rows:
            if before is not None:
                if before[0] != pair:
                    y += self.gaps.pair
                elif before[1] is not row.side:
                    y += self.gaps.row
            shift = 0.0
            if right:
                shift = max(0.0, width - (ends[pair] if options.aligned else row.end))
            runs = row.runs
            joins = row.joins
            if shift:
                runs = [Run(r.caption, r.words, r.x + shift, r.width) for r in runs]
                joins = [x + shift for x in joins]
            height = row.ascent + row.below
            lines.append(
                FlowLine(
                    row.side,
                    tuple(runs),
                    tuple(joins),
                    row.end + shift,
                    y,
                    row.ascent,
                    height,
                    pair,
                )
            )
            y += height
            before = (pair, row.side)
        return Flowed(tuple(lines), y, width)
