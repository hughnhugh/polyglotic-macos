"""Poured captions: a caption's text as a running stream, in lines as wide
as the window (the Lab's "Captions fill the width", polyglotic-hq 309; the
user, 2026-11-14: "often clauses will only be a few words and rarely make
it to the complete width of the window ... text will fill the complete
caption window line by line seperating by ellipsis ... it should know
which size the caption window is and assign the correct number of words
per line").

Today a clause takes a row of its own, its translation under it. Poured,
a caption's clauses run on: a line ends where the next word wouldn't fit,
not where a clause ends, and an ellipsis marks the join (`Join`).

- **What fits is measured** (`Measure`: the caption layout's fonts): words
  in a spaced language - never split across lines, unless one is wider
  than the whole line - and characters in Chinese, Japanese and Thai, with
  closing punctuation kept on its character's line (`tokens`).
- **Each row keeps its own text**: a line is made of `Piece`s - characters
  `[start, end)` of one of the caption's rows, drawn from `x` - so the
  word under the mouse, a lookup, a dragged phrase and the marks still go
  by row and character, as in clause rows.
- **Stacked** (`pour_stacked`): what was said poured into the upper lines,
  its translation into the lines below, each on its own.
- **Line by line** (`pour_paired`): a line of what was said, the line of
  its translation under it, both cut at matching places - a clause's end,
  or inside a clause where its word links say each part of one says what
  the same part of the other does (`matching_cuts`). A part too wide for a
  line with no such place inside it wraps as a clause row does.

Plain Python, no Qt: the layout engine hands in the measuring and draws
what comes back (`caption_layout`). Holds no caption text beyond the call.
"""

import itertools
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from enum import StrEnum

from polyglotic_desktop.core.listening.caption_model import (
    ELLIPSIS,
    matching_cuts,
    units,
    wide,
)
from polyglotic_desktop.ui_next.views.lab import Join

__all__ = ["ELLIPSIS", "matching_cuts", "tokens", "wide"]

Measure = Callable[[int, str], float]
"""How wide a row's text is drawn, in pixels: the row's index, the text."""

Row = tuple[int, str]
"""A row of the caption to pour: its index in the line's rows, its text."""


class Gap(StrEnum):
    """The room above a poured line."""

    NONE = "none"
    """The next line of the same stream: the font's own line spacing."""
    ROW = "row"
    """As between a clause and its translation."""
    CLAUSE = "clause"
    """As between clauses."""


@dataclass(frozen=True, slots=True)
class Piece:
    """Characters `[start, end)` of row `row`, drawn from `x` on a line."""

    row: int
    start: int
    end: int
    x: float


@dataclass(frozen=True, slots=True)
class Poured:
    """One line of poured text: its pieces, left to right; the ellipses
    drawn on it (`marks`: after which row's text - in its font and colour -
    and where); where it ends; and the room above it."""

    pieces: tuple[Piece, ...]
    marks: tuple[tuple[int, float], ...]
    end: float
    gap: Gap = Gap.NONE
    fallback: bool = False
    """Paired: a part too wide for a line with no matching place to cut
    it at, wrapped as a clause row is."""


def tokens(text: str) -> list[tuple[int, int, int]]:
    """`text` as the pieces a line is never broken inside (the caption
    model's `units`, polyglotic-hq 340)."""
    return list(units(text))


class _Line:
    """A poured line being filled."""

    def __init__(self) -> None:
        self.pieces: list[Piece] = []
        self.marks: list[tuple[int, float]] = []
        self.x = 0.0  # where the next word goes
        self.end = 0.0  # where what's on it ends
        self.text_end = 0.0  # where its last word ends (before spaces)
        self.marked = False  # an ellipsis is the last thing on it

    @property
    def empty(self) -> bool:
        return not self.pieces and not self.marks

    def add(self, row: int, start: int, end: int, word: float, whole: float) -> None:
        """Characters `[start, end)` of `row` - `word` px wide without the
        spaces after, `whole` with them - at the line's end."""
        last = self.pieces[-1] if self.pieces else None
        if last is not None and last.row == row and last.end == start:
            self.pieces[-1] = Piece(row, last.start, end, last.x)
        else:
            self.pieces.append(Piece(row, start, end, self.x))
        self.text_end = self.end = self.x + word
        self.x += whole
        self.marked = False

    def mark(self, row: int, before: float, width: float, after: float) -> None:
        """An ellipsis after the last word, in `row`'s font: `before` px
        from it, `width` wide, the next word `after` px on."""
        at = self.text_end + before
        self.marks.append((row, at))
        self.end = self.text_end = at + width
        self.x = self.end + after
        self.marked = True

    def done(self, gap: Gap) -> Poured:
        return Poured(tuple(self.pieces), tuple(self.marks), self.end, gap)


def pour(
    rows: Sequence[Row],
    width: float,
    measure: Measure,
    join: Join,
    first: Gap = Gap.NONE,
) -> list[Poured]:
    """`rows`, one stream, poured into lines `width` px wide: each row
    runs on from the one before, with `join` between them. `first`: the
    room above the first line."""
    parts = [(row, text, 0, len(text)) for row, text in rows]
    return _flow(parts, width, measure, join, first)


Part = tuple[int, str, int, int]
"""Characters `[start, end)` of a row's text to pour: the row's index, its
whole text, start, end - both where a word starts (`tokens`)."""


def _flow(
    parts: Sequence[Part],
    width: float,
    measure: Measure,
    join: Join,
    first: Gap = Gap.NONE,
    goes_on: bool = False,
    fallback: bool = False,
) -> list[Poured]:
    """`parts`, one stream, poured (`pour`). `goes_on`: another clause
    follows the last part - it ends with the join's ellipsis."""
    lines: list[Poured] = []
    line = _Line()
    texts = {row: text for row, text, _, _ in parts}
    rows = [(row, text) for row, text, _, _ in parts]

    def new_line(row: int) -> None:
        nonlocal line
        if join is Join.LINE_ENDS and not line.marked and not line.empty:
            last = _last_row(line, row)
            space, dots = _ellipsis(last, texts[last], measure)
            line.mark(last, space, dots, 0.0)
        lines.append(line.done(Gap.NONE if lines else first))
        line = _Line()

    for n, (row, text, first_char, last_char) in enumerate(parts):
        space, dots = _ellipsis(row, text, measure)
        reserve = space + dots if join is Join.LINE_ENDS else 0.0
        pieces = [t for t in tokens(text) if first_char <= t[0] < last_char]
        follows = n + 1 < len(parts) or goes_on
        for i, (start, end, after) in enumerate(pieces):
            word = measure(row, text[start:end])
            tail = 0.0  # the join's ellipsis stays on its clause's last line
            if follows and i == len(pieces) - 1 and join is not Join.SPACE:
                tail = space + dots
            room = width - reserve
            while word > room and end - start > 1:  # wider than a whole line
                if not line.empty:
                    new_line(row)
                cut = _fitting(row, text, start, end, room, measure)
                part = measure(row, text[start:cut])
                line.add(row, start, cut, part, part)
                start, word = cut, measure(row, text[cut:end])
            if not line.empty and line.x + word + tail > room + 0.5:
                new_line(row)
            whole = word if after == end else measure(row, text[start:after])
            line.add(row, start, after, word, whole)
        if not follows:
            break
        after_it = rows[n + 1][1] if n + 1 < len(rows) else ""
        between = _between(text, after_it, row, measure)
        if join is Join.SPACE:
            line.x = line.text_end + between
        else:
            line.mark(row, space, dots, between)
    if not line.empty:
        lines.append(line.done(Gap.NONE if lines else first))
    if fallback:
        lines = [replace(found, fallback=True) for found in lines]
    return lines


def pour_stacked(
    originals: Sequence[Row],
    translations: Sequence[Row],
    width: float,
    measure: Measure,
    join: Join,
) -> list[Poured]:
    """What was said poured into the upper lines and its translation into
    the lines below, each on its own (either may be empty: captions only,
    originals hidden, a translation still on its way)."""
    lines = pour(originals, width, measure, join) if originals else []
    if translations:
        gap = Gap.ROW if lines else Gap.NONE
        lines += pour(translations, width, measure, join, gap)
    return lines


def _fitting(
    row: int, text: str, start: int, end: int, room: float, measure: Measure
) -> int:
    """Where to cut a word wider than a whole line: after as many of its
    characters as fit in `room` px (one at least)."""
    cut = start + 1
    while cut + 1 < end and measure(row, text[start : cut + 1]) <= room:
        cut += 1
    return cut


def _last_row(line: _Line, otherwise: int) -> int:
    return line.pieces[-1].row if line.pieces else otherwise


def _ellipsis(row: int, text: str, measure: Measure) -> tuple[float, float]:
    """The room before an ellipsis after `row`'s `text`, in its font - half
    a space; none in a script written without them, whose punctuation
    brings its own - and the ellipsis's width."""
    end = text.rstrip()
    tight = bool(end) and wide(end[-1])
    return (0.0 if tight else measure(row, " ") * 0.5), measure(row, ELLIPSIS)


def _between(before: str, after: str, row: int, measure: Measure) -> float:
    """The room between two rows' text run together: a space, or none next
    to a character of a script written without them."""
    a, b = before.rstrip(), after.lstrip()
    if not a or not b or wide(a[-1]) or wide(b[0]):
        return 0.0
    return measure(row, " ")


@dataclass(frozen=True, slots=True)
class Pair:
    """A clause to pour in step with its translation: its original's row,
    its translation's (None: not translated, or not yet), and the places
    both can be cut at - (characters into the original, into the
    translation), in order (`matching_cuts`)."""

    original: Row
    translation: Row | None = None
    cuts: tuple[tuple[int, int], ...] = ()


def pour_paired(
    pairs: Sequence[Pair], width: float, measure: Measure, join: Join
) -> list[Poured]:
    """Lines that alternate: a line of what was said, the line of its
    translation under it, cut at matching places - a clause's end, or
    inside a clause where its word links say both can be cut
    (`Pair.cuts`). A pair of lines takes as many such parts as fit both.
    A part too wide for a line on either side, with no matching place
    inside it, falls back to today's shape: its original wrapped over
    the lines it needs, then its translation (`Poured.fallback`)."""
    lines: list[Poured] = []
    top, bottom = _Line(), _Line()

    def close() -> None:
        nonlocal top, bottom
        if top.empty and bottom.empty:
            return
        for line, gap in ((top, Gap.CLAUSE), (bottom, Gap.ROW)):
            if line.empty:
                continue
            if join is Join.LINE_ENDS and not line.marked and more:
                row = line.pieces[-1].row
                space, dots = _ellipsis(row, texts[row], measure)
                line.mark(row, space, dots, 0.0)
            lines.append(line.done(gap if lines else Gap.NONE))
        top, bottom = _Line(), _Line()

    texts: dict[int, str] = {}
    for pair in pairs:
        texts[pair.original[0]] = pair.original[1]
        if pair.translation is not None:
            texts[pair.translation[0]] = pair.translation[1]
    more = True  # text follows what's on the lines being closed
    for n, pair in enumerate(pairs):
        follows = n + 1 < len(pairs)
        o_row, o_text = pair.original
        t_row, t_text = pair.translation or (-1, "")
        bounds = [(0, 0), *pair.cuts, (len(o_text), len(t_text))]
        if pair.translation is None:
            bounds = [(0, 0), (len(o_text), 0)]
        for (o_a, t_a), (o_b, t_b) in itertools.pairwise(bounds):
            ends = (o_b, t_b) == bounds[-1] and follows  # a join comes after
            sides = [_Side(top, o_row, o_text, o_a, o_b, measure, join, ends)]
            if pair.translation is not None:
                sides.append(
                    _Side(bottom, t_row, t_text, t_a, t_b, measure, join, ends)
                )
            if not all(side.fits(width) for side in sides):
                close()
                sides[0].line = top
                if len(sides) > 1:
                    sides[1].line = bottom
            if all(side.fits(width) for side in sides):
                after = pairs[n + 1] if follows else None
                for at, side in enumerate(sides):
                    side.add(_next_text(after, at))
                continue
            # too wide for a line, and nowhere to cut both: wrapped
            for at, side in enumerate(sides):
                gap = (Gap.ROW if at else Gap.CLAUSE) if lines else Gap.NONE
                part = [(side.row, side.text, side.start, side.end)]
                lines += _flow(part, width, measure, join, gap, ends, fallback=True)
    more = False
    close()
    return lines


def _next_text(pair: Pair | None, side: int) -> str | None:
    """What follows on a side (0: what was said, 1: its translation) when
    `pair` comes next: its text there - the translation's own language
    decides the room before it."""
    if pair is None:
        return None
    if side and pair.translation is not None:
        return pair.translation[1]
    return pair.original[1]


class _Side:
    """One side - what was said, or its translation - of a part being
    added to a pair of lines: characters `[start, end)` of `row`."""

    def __init__(
        self,
        line: _Line,
        row: int,
        text: str,
        start: int,
        end: int,
        measure: Measure,
        join: Join,
        ends: bool,
    ) -> None:
        self.line, self.row, self.text = line, row, text
        self.start, self.end = start, end
        self.measure, self.join, self.ends = measure, join, ends
        piece = text[start:end]
        self.word = measure(row, piece.rstrip())
        self.whole = measure(row, piece) if piece else 0.0
        self.space, self.dots = _ellipsis(row, text, measure)

    def fits(self, width: float) -> bool:
        """Whether the part, and the ellipsis after it if a clause ends
        with it, fits at the end of its line."""
        tail = (
            self.space + self.dots if self.ends and self.join is not Join.SPACE else 0.0
        )
        reserve = self.space + self.dots if self.join is Join.LINE_ENDS else 0.0
        return self.line.x + self.word + tail <= width - reserve + 0.5

    def add(self, after: str | None) -> None:
        """The part onto its line. `after`: the text of the clause that
        follows on this side, if this part ends its clause."""
        if self.end > self.start:
            self.line.add(self.row, self.start, self.end, self.word, self.whole)
        if not self.ends or after is None:
            return
        between = _between(self.text, after, self.row, self.measure)
        if self.join is Join.SPACE:
            self.line.x = self.line.text_end + between
        else:
            self.line.mark(self.row, self.space, self.dots, between)
