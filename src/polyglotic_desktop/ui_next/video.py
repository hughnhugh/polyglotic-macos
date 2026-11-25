"""Live Video subtitles and their Qt painting, with one layout for each row."""

from __future__ import annotations

import math
import re
from bisect import bisect_right
from collections import OrderedDict
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass, field, replace
from functools import lru_cache
from itertools import groupby, pairwise

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QFontMetricsF,
    QImage,
    QLinearGradient,
    QPainter,
    QRawFont,
)

from polyglotic_desktop.core.listening.captions import Language
from polyglotic_desktop.core.listening.display import RowKind
from polyglotic_desktop.core.listening.playout import Split, word_beats
from polyglotic_desktop.core.listening.sources import SourceId
from polyglotic_desktop.core.listening.timing import CaptionId
from polyglotic_desktop.core.shared.tunables import tunable
from polyglotic_desktop.ui_next.caption_layout import (
    ARROW_ROW_GAP,
    CaptionLayout,
    Ink,
    LaidLine,
    LaidRow,
    Marks,
    caption_language,
    graphemes,
    panned_row,
    visible_row,
)
from polyglotic_desktop.ui_next.views import card_window_defaults as timing
from polyglotic_desktop.ui_next.views import dwell
from polyglotic_desktop.ui_next.views.arrivals import ENTRY_GAP_PX
from polyglotic_desktop.ui_next.views.captions import Line
from polyglotic_desktop.ui_next.views.cards import Glide
from polyglotic_desktop.ui_next.views.flow import CONTINUATION

INSTANT_WORD_INTERVAL = tunable(
    "video_motion.instant_word_interval",
    0.016,
    "seconds",
    (0.016, 0.05),
    source="743 Video word-by-word arrival and 200 ms word deadline",
)
"""The cadence for words arriving in small updates."""

VIDEO_MARGIN = 10
ORIGINAL_LINE_EM = 1.3
TRANSLATION_LINE_EM = 1.35
TRANSLATION_GAP = 2
PlacedSubtitle = tuple[Line, LaidLine, QRectF]
RowRoom = tuple[float, float, float]

FRAME = 1 / 60  # seconds per paint in the reference replay
BLOCK_GAP_EM = 0.35
TAIL_EM = 0.8
EPS = 1e-8
NO_LINE_START = "，。！？、；：）」』”"
# Spaced words stay whole in either role. Han, kana and Hangul can break
# between characters. A closing mark belongs to the preceding word.
CJK = "\u2e80-\u9fff\uac00-\ud7af\uf900-\ufaff"
WRAP_UNIT = re.compile(
    rf"\s+|(?:[{CJK}]|[^\s{CJK}{NO_LINE_START}]+|[{NO_LINE_START}])[{NO_LINE_START}]*"
)


def _wrap_units(text: str, joined: set[int] | None) -> Iterator[tuple[int, int]]:
    first = 0
    for match in WRAP_UNIT.finditer(text):
        end = match.end()
        if joined is None or end not in joined:
            yield first, end
            first = end
    if first < len(text):
        yield first, len(text)


def ease(progress: float) -> float:
    return 1 - (1 - min(1.0, max(0.0, progress))) ** 3


@dataclass
class Tween:
    start: float
    end: float
    at: float
    duration: float

    def value(self, now: float) -> float:
        if self.duration == 0:
            return self.end
        return self.start + (self.end - self.start) * ease(
            (now - self.at) / self.duration
        )


@dataclass
class Pan:
    x: float = 0.0
    target: float = 0.0
    burst: Tween | None = None

    def follow(self, target: float, now: float, dt: float) -> None:
        if target != self.target:
            self.target = target
            self.burst = (
                Tween(self.x, target, now, timing.CATCHUP.value - FRAME)
                if abs(target - self.x) > timing.GLIDE.value * timing.CATCHUP.value
                else None
            )
        wanted = self.burst.value(now) if self.burst else target
        limit = (
            timing.MAX_STEP.value
            if self.burst
            else min(timing.MAX_STEP.value, timing.GLIDE.value * dt)
        )
        self.x += max(-limit, min(limit, wanted - self.x))


@dataclass(frozen=True)
class Copy:
    line: Line
    original: str
    translation: str
    final_translation: bool
    writing: bool = False
    original_writing: bool = False
    translation_writing: bool = False


@dataclass
class WordTrack:
    text: str = ""
    words: tuple[str, ...] = ()
    ends: tuple[int, ...] = ()
    shown: int = 0
    next_at: float = -math.inf

    def reveal(self, text: str, now: float, split: Split) -> None:
        if text != self.text:
            ends, _ = word_beats(text, split)
            words = tuple(text[a:b] for a, b in pairwise((0, *ends)))
            still_shown = 0
            for old, new in zip(self.words[: self.shown], words, strict=False):
                if old.strip() != new.strip():
                    break
                still_shown += 1
            self.text, self.words, self.shown = text, words, still_shown
            self.ends = ends
        if self.shown < len(self.words) and now + EPS >= self.next_at:
            # A buffered packet can contain a sentence. Reveal the burst
            # together when its normal cadence would spend the motion budget.
            remaining = len(self.words) - self.shown
            cadence = max(FRAME, INSTANT_WORD_INTERVAL.value)
            budget = timing.CATCHUP.value / 2
            self.shown += remaining if remaining * cadence > budget else 1
            self.next_at = now + INSTANT_WORD_INTERVAL.value

    def limit(self, end: int) -> bool:
        """Leave the rest of the packet for the next visible row."""
        count = bisect_right(self.ends, end, hi=self.shown)
        if 0 < count < self.shown:
            self.shown = count
            return True
        return False

    @property
    def visible(self) -> str:
        return self.text[: self.ends[self.shown - 1]].rstrip() if self.shown else ""

    @property
    def pending(self) -> bool:
        return self.shown < len(self.words)


@dataclass
class WordArrival:
    original: WordTrack = field(default_factory=WordTrack)
    translation: WordTrack = field(default_factory=WordTrack)

    def reveal(
        self, copy: Copy, now: float, split: Split, *, defer_translation: bool = False
    ) -> Copy:
        self.original.reveal(copy.original, now, split)
        if not defer_translation:
            self.translation.reveal(copy.translation, now, split)
        return self.copy(copy, defer_translation=defer_translation)

    def copy(self, copy: Copy, *, defer_translation: bool = False) -> Copy:
        return replace(
            copy,
            original=self.original.visible,
            translation="" if defer_translation else self.translation.visible,
            final_translation=copy.final_translation and not self.translation.pending,
            writing=self.original.pending or self.translation.pending,
            original_writing=self.original.pending,
            translation_writing=self.translation.pending,
        )


@dataclass(frozen=True)
class PaintRow:
    copy: Copy
    translation: bool
    text: str
    start: int
    x: float
    y: float
    height: float
    alpha: float
    phase: str
    continues: bool = False
    entry_offset: float = 0.0

    @property
    def key(self) -> tuple[int, bool, int]:
        return self.copy.line.key, self.translation, self.start


@dataclass
class Track:
    scrolling: bool
    pending: bool = False
    words: WordArrival = field(default_factory=WordArrival)
    pans: tuple[Pan, Pan] = field(default_factory=lambda: (Pan(), Pan()))
    first: list[int] = field(default_factory=lambda: [0, 0])
    starts: tuple[int, int] = (0, 0)

    def revise(self, copy: Copy) -> None:
        """A rewrite before a discarded wrap makes its old offsets stale."""
        starts = list(self.starts)
        for side, (before, text) in enumerate(
            (
                (self.words.original.text, copy.original),
                (self.words.translation.text, copy.translation),
            )
        ):
            if (
                self.first[side]
                and before
                and not text.startswith(before[: self.first[side]])
            ):
                self.first[side] = starts[side] = 0
        self.starts = starts[0], starts[1]


@dataclass
class Slot:
    row: PaintRow
    since: float
    ready: float | None = None
    lift: Tween | None = None
    incoming: bool = False
    settled_at: float | None = None
    entry: Glide | None = None

    def position(self, now: float) -> float:
        y = self.lift.value(now) if self.lift else self.row.y
        return y + (self.entry.to(now) if self.entry else 0.0)


class VideoFlow:
    """Keep each painted row's identity through wrapping, settling and lifting."""

    def __init__(
        self,
        measure: Callable[[str, bool], float],
        width: float,
        top: float,
        foot: float,
        original_px: int,
        translation_px: int,
        label_height: float = 0.0,
        row_heights: tuple[float, float] | None = None,
        one_row: bool = False,
        animate: bool = True,
        span_width: Callable[[Copy, bool, int, int], float] | None = None,
        translation_gap: float = TRANSLATION_GAP,
        reading_breaks: Callable[[Copy, bool], set[int]] | None = None,
        lines_shown: int | None = None,
        pan_width: Callable[[Copy, bool, int, int], float] | None = None,
        paired_ranges: Callable[[Line], list[tuple[bool, int, int]]] | None = None,
    ) -> None:
        self.measure = measure
        self.span_width = span_width
        self.pan_width = pan_width
        self.paired_ranges = paired_ranges
        self.reading_breaks = reading_breaks
        self.width, self.top, self.foot = width, top, foot
        self.oh, self.th = row_heights or (
            original_px * ORIGINAL_LINE_EM,
            translation_px * TRANSLATION_LINE_EM,
        )
        self.label_height = label_height
        self.translation_gap = translation_gap
        self.gap = original_px * BLOCK_GAP_EM
        self.tails = original_px * TAIL_EM, translation_px * TAIL_EM
        self.one_row, self.animate = one_row, animate
        self.lines_shown = lines_shown
        self.scrolling = False
        self.now = -math.inf
        self.tracks: dict[int, Track] = {}
        self.last_key = -1
        self.slots: dict[tuple[int, bool, int], Slot] = {}
        self.waiting = False
        self.single_cell_wait = False
        self.queued = False
        self.lift_ends = -math.inf
        self.events: list[str] = []

    def wrap(
        self,
        text: str,
        translation: bool,
        span_width: Callable[[int, int], float] | None = None,
        joined: set[int] | None = None,
        *,
        growing: bool = False,
    ) -> list[str]:
        lines: list[str] = []
        current = spaces = ""
        room = self.width - self.measure(CONTINUATION, translation)
        final_width = room if growing else self.width
        start = 0
        for first, end in _wrap_units(text, joined):
            token = text[first:end]
            if token.isspace():
                spaces += token
                continue
            candidate = current + spaces + token
            candidate_width = (
                span_width(start, end)
                if span_width
                else self.measure(candidate, translation)
            )
            limit = final_width if end == len(text) else room
            if current and candidate_width > limit:
                # Retain every source offset, including separators at breaks.
                lines.append(current + spaces)
                start = first
                current, spaces = "", ""
            token_width = (
                span_width(first, end)
                if span_width
                else self.measure(token, translation)
            )
            if token_width > limit:
                # An unbroken URL or word may be wider than the window.
                # Break it at grapheme boundaries, including surrogate pairs.
                current += spaces
                stop = first
                for glyph in graphemes(token):
                    stop += len(glyph)
                    width = (
                        span_width(start, stop)
                        if span_width
                        else self.measure(current + glyph, translation)
                    )
                    if current and width > (final_width if stop == len(text) else room):
                        lines.append(current)
                        start = stop - len(glyph)
                        current = ""
                    current += glyph
            else:
                current += spaces + token
            spaces = ""
        if current or spaces:
            lines.append(current + spaces)
        return lines

    def advance_width(self, copy: Copy, tr: bool, start: int, end: int) -> float:
        if self.span_width is not None:
            return self.span_width(copy, tr, start, end)
        text = copy.translation if tr else copy.original
        return self.measure(text[start:end], tr)

    @staticmethod
    def reading_need(text: str, translation: bool) -> float:
        pace = timing.READ_CPS.value * (
            timing.TRANSLATION_RATIO.value if translation else 1
        )
        wide, spaced = (
            (dwell.MEANT_PACE, dwell.MEANT_PACE_SPACED)
            if translation
            else (dwell.SAID_PACE, dwell.SAID_PACE_SPACED)
        )
        return max(len(text) / pace, dwell.need(text, wide.value, spaced.value))

    def shape(
        self,
        copy: Copy,
        scrolling: bool,
        sides: tuple[bool, bool],
        starts: tuple[int, int] = (0, 0),
        *,
        revisable: bool = False,
    ) -> list[PaintRow]:
        texts = (copy.original, copy.translation)
        heights = (self.oh, self.th)
        if (
            self.paired_ranges is not None
            and copy.line.model is not None
            and not scrolling
        ):
            spans = self.paired_ranges(copy.line)
        else:
            spans = self._wrap_ranges(copy, scrolling, sides, starts)
        rows = []
        for tr, first, end in spans:
            text = texts[tr]
            first = max(first, starts[tr])
            if not sides[tr] or not heights[tr] or first >= min(end, len(text)):
                continue
            continues = end < len(text)
            finished = (continues and not revisable) or (
                copy.final_translation
                if tr
                else not (
                    copy.line.live or copy.line.provisional or copy.original_writing
                )
            )
            rows.append(
                PaintRow(
                    copy,
                    tr,
                    text[first:end],
                    first,
                    0,
                    0,
                    heights[tr],
                    1,
                    "settled" if finished else "live",
                    continues=continues,
                )
            )
        return rows

    def _wrap_ranges(
        self,
        copy: Copy,
        scrolling: bool,
        sides: tuple[bool, bool],
        starts: tuple[int, int],
    ) -> list[tuple[bool, int, int]]:
        ranges = []
        for tr, text, height in (
            (False, copy.original, self.oh),
            (True, copy.translation, self.th),
        ):
            start = starts[int(tr)]
            text = text[start:]
            if not (sides[int(tr)] and text and height):
                continue
            growing = copy.translation_writing if tr else copy.original_writing
            if scrolling:
                pieces = [text]
            elif self.span_width is None:
                pieces = self.wrap(text, tr, growing=growing)
            else:

                def span_width(
                    first: int, end: int, translation: bool = tr, offset: int = start
                ) -> float:
                    return self.advance_width(
                        copy, translation, offset + first, offset + end
                    )

                pieces = self.wrap(
                    text,
                    tr,
                    span_width,
                    {i - start for i in self.reading_breaks(copy, tr)}
                    if self.reading_breaks
                    else None,
                    growing=growing,
                )
            for piece in pieces:
                ranges.append((tr, start, start + len(piece)))
                start += len(piece)
        return ranges

    def spacing(self, upper: PaintRow, lower: PaintRow) -> float:
        if upper.copy.line.key != lower.copy.line.key:
            return self.gap + self.label_height
        return self.translation_gap if upper.translation != lower.translation else 0.0

    def _fit_caption(self, rows: list[PaintRow]) -> list[PaintRow]:
        """For a caption taller than the window, retain the tail of each side."""
        if self.paired_ranges is not None and not self.one_row:
            room = self.foot - self.top - self.label_height
            counts = [0, 0]
            kept: list[PaintRow] = []
            for row in reversed(rows):
                cost = row.height + (self.spacing(row, kept[-1]) if kept else 0.0)
                if cost > room + EPS or counts[row.translation] == self.lines_shown:
                    # Leave a partial oldest pair together on the preceding page.
                    if kept and kept[-1].translation and not row.translation:
                        kept.pop()
                    break
                kept.append(row)
                counts[row.translation] += 1
                room -= cost
            return kept[::-1]
        original = [row for row in rows if not row.translation]
        translation = [row for row in rows if row.translation]
        if self.lines_shown is not None:
            original = original[-self.lines_shown :]
            translation = translation[-self.lines_shown :]
            rows = original + translation
        room = self.foot - self.top - self.label_height
        while rows:
            height = sum(row.height for row in rows) + (
                self.translation_gap if original and translation else 0
            )
            if height <= room + EPS:
                break
            if self.one_row and original and translation:
                key = original[0].copy.line.key
                drawn = next(
                    (s for s in self.slots.values() if s.row.copy.line.key == key), None
                )
                # A single cell gives the original its reading turn first.
                if drawn is not None and (
                    drawn.row.translation
                    or (drawn.ready is not None and self.now + EPS >= drawn.ready)
                ):
                    original.clear()
                else:
                    self.single_cell_wait = True
                    translation.clear()
            else:
                side = original if len(original) >= len(translation) else translation
                side.pop(0)
            rows = original + translation
        return rows

    def _limit_wrap(self, rows: list[PaintRow], words: WordArrival) -> bool:
        """Reveal an overfull packet in order, including its first visible rows."""
        fitted = self._fit_caption(rows)
        if len(fitted) == len(rows):
            return False
        kept = {row.key for row in fitted}
        limited = False
        for translation, track in ((False, words.original), (True, words.translation)):
            side = [row for row in rows if row.translation == translation]
            capacity = sum(row.key in kept for row in side)
            for index, row in enumerate(side):
                if row.key in kept:
                    break
                old = self.slots.get(row.key)
                if (
                    old is not None
                    and not old.incoming
                    and old.row.text.rstrip() == row.text.rstrip()
                ):
                    continue
                if capacity:
                    last = side[index + capacity - 1]
                    limited |= track.limit(last.start + len(last.text))
                break
        return limited

    def _shape_track(
        self, copy: Copy, track: Track, sides: tuple[bool, bool], revisable: bool
    ) -> list[PaintRow]:
        return [
            row
            for row in self.shape(
                copy, track.scrolling, sides, track.starts, revisable=revisable
            )
            if row.start >= track.first[int(row.translation)]
        ]

    def _layout(self, rows: list[PaintRow], *, resized: bool = False) -> list[PaintRow]:
        placed: list[PaintRow] = []
        bottom = self.foot
        remaining = [self.lines_shown, self.lines_shown]
        for _, caption in groupby(reversed(rows), lambda row: row.copy.line.key):
            chunk = list(caption)
            group: list[PaintRow] = []
            for row in chunk:
                side = int(row.translation)
                count = remaining[side]
                if count == 0:
                    break
                if lower := (group or placed):
                    bottom -= self.spacing(row, lower[-1])
                y = bottom - row.height
                old = self.slots.get(row.key)
                if old is not None and not resized:
                    y = min(y, old.row.y)
                if y < self.top + self.label_height - EPS:
                    break
                group.append(replace(row, y=y))
                bottom = y
                if count is not None:
                    remaining[side] = count - 1
            if len(group) < len(chunk):
                # A finished caption that fits by itself leaves as a unit.
                if not placed:
                    placed.extend(group)
                break
            placed.extend(group)
        return placed[::-1]

    def _settle(self, slot: Slot) -> None:
        if slot.ready is None:
            row = slot.row
            left = (
                slot.since
                + self.reading_need(row.text.rstrip(), row.translation)
                - self.now
            )
            slot.ready = (
                self.now
                + timing.SETTLE.value
                + min(timing.WAIT_CAP.value, max(0, left))
            )
            slot.settled_at = self.now
            self.events.append(
                f"settle {row.copy.line.key} {int(row.translation)} {row.start}"
            )

    def _pan_target(self, row: PaintRow) -> float:
        span = row.copy, row.translation, row.start, row.start + len(row.text.rstrip())
        width = self.advance_width(*span)
        if width <= self.width:
            return 0.0
        # Use the painted advance for the tail. Keep the design advance for
        # a line whose painted width rounds across the viewport edge.
        if self.pan_width is not None:
            painted = self.pan_width(*span)
            if painted > self.width:
                width = painted
        return width - self.width + self.tails[int(row.translation)]

    def _pan_rows(
        self, dt: float, moving: set[tuple[int, bool, int]] | None = None
    ) -> None:
        for slot in self.slots.values():
            row = slot.row
            if slot.incoming:
                if self.now + EPS < self.lift_ends:
                    continue
                slot.incoming = False
                slot.since = self.now
                if slot.entry is not None:
                    slot.entry.push(self.now, min(ENTRY_GAP_PX.value, row.height))
            track = self.tracks[row.copy.line.key]
            if self.scrolling and track.scrolling:
                pan = track.pans[int(row.translation)]
                target = self._pan_target(row)
                if self.animate:
                    pan.follow(target, self.now, dt)
                else:
                    pan.x = pan.target = target
                slot.row = replace(row, x=pan.x)
                if abs(pan.x - target) > EPS:
                    continue
            if (
                row.phase == "settled"
                and (self.one_row or not row.copy.writing)
                and self.now + EPS >= self.lift_ends
                and (moving is None or row.key not in moving)
            ):
                self._settle(slot)

    def advance(
        self,
        copies: Sequence[Copy],
        now: float,
        split: Split | None = None,
        *,
        scrolling: bool = False,
        sides: tuple[bool, bool] = (True, True),
        repack: bool = False,
        resized: bool = False,
    ) -> None:
        dt = max(0.0, now - self.now) if math.isfinite(self.now) else FRAME
        self.now = now
        self.scrolling = scrolling
        self.events.clear()
        known = {c.line.key for c in copies}
        self.tracks = {k: t for k, t in self.tracks.items() if k in known}
        self.slots = {
            k: slot
            for k, slot in self.slots.items()
            if k[0] in known and sides[int(k[1])]
        }
        if repack:
            for slot in self.slots.values():
                slot.row = replace(
                    slot.row, y=min(slot.position(now), self.foot - slot.row.height)
                )
                slot.lift = None
                slot.entry = None
            self.lift_ends = now
            for track in self.tracks.values():
                track.pending = False
            latest = next(
                (c for c in reversed(copies) if c.line.key == self.last_key), None
            )
            if latest is not None and (latest.line.live or latest.line.provisional):
                latest_track = self.tracks.get(self.last_key)
                if latest_track is not None and latest_track.scrolling != scrolling:
                    starts = latest_track.first.copy()
                    for slot in self.slots.values():
                        row = slot.row
                        if row.copy.line.key != self.last_key:
                            continue
                        side = int(row.translation)
                        start = row.start
                        if not scrolling and row.x > 0:
                            for unit in WRAP_UNIT.finditer(row.text):
                                if (
                                    self.advance_width(
                                        row.copy,
                                        row.translation,
                                        row.start,
                                        row.start + unit.end(),
                                    )
                                    > row.x
                                ):
                                    break
                                start = row.start + unit.end()
                        starts[side] = max(starts[side], start)
                    latest_track.scrolling = scrolling
                    latest_track.pans = Pan(), Pan()
                    latest_track.starts = starts[0], starts[1]
        elif now + EPS < self.lift_ends:
            self._pan_rows(dt)
            return

        rows: list[PaintRow] = []
        desired: dict[tuple[int, bool, int], PaintRow] = {}
        updates: dict[int, WordArrival] = {}
        seen: dict[int, list[PaintRow]] = {}
        self.single_cell_wait = False
        self.queued = False
        can_open = not (
            any(track.pending for track in self.tracks.values())
            or (
                split is not None and any(slot.incoming for slot in self.slots.values())
            )
        )
        for copy in copies:
            received = copy
            caption_key = copy.line.key
            caption_track = self.tracks.get(caption_key)
            if caption_track is None:
                if caption_key <= self.last_key:
                    continue
                if not can_open:
                    self.queued = True
                    continue
                caption_track = self.tracks[caption_key] = Track(scrolling)
                self.last_key = caption_key
                can_open = False
            defer = (
                self.one_row
                and all(sides)
                and self.oh > 0
                and bool(
                    copy.original and copy.translation and not caption_track.first[0]
                )
                and not any(
                    slot.row.copy.line.key == caption_key
                    and (
                        slot.row.translation
                        or (slot.ready is not None and now + EPS >= slot.ready)
                    )
                    for slot in self.slots.values()
                )
            )
            self.single_cell_wait |= defer
            if split is not None:
                if caption_key == self.last_key:
                    caption_track.revise(copy)
                words = updates[caption_key] = WordArrival(
                    replace(caption_track.words.original),
                    replace(caption_track.words.translation),
                )
                copy = words.reveal(copy, now, split, defer_translation=defer)
                if caption_key == self.last_key and (
                    defer
                    or any(
                        enabled and (after.pending or after.next_at != before.next_at)
                        for enabled, before, after in (
                            (sides[0], caption_track.words.original, words.original),
                            (
                                sides[1],
                                caption_track.words.translation,
                                words.translation,
                            ),
                        )
                    )
                ):
                    # Finish revealing words already received before admitting
                    # a later caption that could displace their rows.
                    can_open = False
            elif defer:
                copy = replace(copy, translation="")
            shaped = self._shape_track(copy, caption_track, sides, split is not None)
            if (
                split is not None
                and not caption_track.scrolling
                and self._limit_wrap(shaped, updates[caption_key])
            ):
                # Keep the breaks of the received packet when only its first
                # rows have earned a cell. Its last visible row still carries on.
                copy = updates[caption_key].copy(received, defer_translation=defer)
                limited = []
                for row in shaped:
                    end = len(copy.translation if row.translation else copy.original)
                    if row.start < end:
                        limited.append(
                            replace(row, copy=copy, text=row.text[: end - row.start])
                        )
                shaped = limited
            if (
                self.th > 0
                and not self.one_row
                and caption_key == self.last_key
                and all(sides)
                and caption_track.first[1] == 0
                and shaped
                and not any(row.translation for row in shaped)
            ):
                # Reserve the next translation's cell while its packet is in flight.
                shaped.append(PaintRow(copy, True, "", 0, 0, 0, self.th, 1, "live"))
            desired.update((row.key, row) for row in shaped)
            seen[caption_key] = self._fit_caption(shaped)
            rows.extend(seen[caption_key])

        placed = self._layout(rows, resized=resized)
        if resized:
            visible_keys = {row.copy.line.key for row in placed if row.text}
            held = [
                key[0]
                for key, slot in self.slots.items()
                if slot.ready is not None
                and now + EPS < slot.ready
                and key[0] not in visible_keys
            ]
            if held:
                prefix = [row for row in rows if row.copy.line.key <= max(held)]
                placed = self._layout(prefix, resized=True) or placed
        next_rows = {row.key: row for row in placed}
        extending = {
            row.copy.line.key
            for key, row in next_rows.items()
            if split is not None and key not in self.slots and row.text
        }
        last_start = {
            (row.copy.line.key, row.translation): row.start for row in desired.values()
        }
        blocked = False
        moving = set()
        for key, slot in self.slots.items():
            planned = desired.get(key)
            track = self.tracks[key[0]]
            pan = track.pans[int(key[1])]
            target = (
                self._pan_target(planned)
                if planned is not None and scrolling and track.scrolling
                else pan.x
            )
            next_row = next_rows.get(key)
            changes = next_row is None or (
                next_row.y < slot.row.y - EPS
                or next_row.text.rstrip() != slot.row.text.rstrip()
            )
            extending_caption = changes and key[0] in extending
            if extending_caption:
                moving.add(key)
            if (
                changes
                and extending
                and slot.ready is not None
                and slot.settled_at is not None
            ):
                # When new ink needs the space, retain the minimum hold.
                # The additional reading time is for a gap in the arrivals.
                slot.ready = min(slot.ready, slot.settled_at + timing.SETTLE.value)
            if (
                planned is not None
                and planned.phase == "settled"
                and (self.one_row or not planned.copy.writing)
                and not slot.incoming
                and planned.text.rstrip() == slot.row.text.rstrip()
                and abs(pan.x - target) <= EPS
                # A word closing a wrap starts a lift. Start the reading
                # hold once the closed row reaches its resting position.
                and (split is None or last_start[key[:2]] == key[2])
                and not extending_caption
            ):
                self._settle(slot)
            if changes and slot.ready is not None and now + EPS < slot.ready:
                blocked = True
        if blocked and not repack:
            if not self.waiting:
                self.events.append("wait starts")
            self.waiting = True
            # The next row can wait for space without freezing a live row
            # that already has its own cell.
            for key, slot in self.slots.items():
                planned = desired.get(key)
                if planned is None or (
                    slot.ready is not None and now + EPS < slot.ready
                ):
                    continue
                if slot.row.text.rstrip() != planned.text.rstrip():
                    slot.ready = None
                    slot.settled_at = None
                if not slot.row.text and planned.text:
                    slot.since = now
                slot.row = replace(planned, x=slot.row.x, y=slot.row.y)
            for caption_key, shaped in seen.items():
                track = self.tracks[caption_key]
                track.pending = False
                for side, role in ((False, "original"), (True, "translation")):
                    accepted = all(
                        (visible_slot := self.slots.get(row.key)) is not None
                        and visible_slot.row.text == row.text
                        for row in shaped
                        if row.translation == side and row.text
                    )
                    if accepted and caption_key in updates:
                        setattr(track.words, role, getattr(updates[caption_key], role))
                    track.pending |= not accepted
            self._pan_rows(dt, moving)
            return
        if self.waiting:
            self.events.append("wait ends")
        self.waiting = False
        for key, slot in self.slots.items():
            if (
                not repack
                and key not in next_rows
                and (key in desired or key[0] < self.last_key)
            ):
                first = self.tracks[key[0]].first
                first[int(key[1])] = max(
                    first[int(key[1])], key[2] + len(slot.row.text.rstrip())
                )
        # Rows that have already left never reappear when a late translation arrives.
        first_key = placed[0].copy.line.key if placed else self.last_key
        for caption_key in list(self.tracks):
            if caption_key < first_key:
                del self.tracks[caption_key]
        slots = {}
        handover = timing.HANDOVER.value
        if moving:
            # Original and translation can wrap on successive paints.
            handover = min(handover, timing.CATCHUP.value / 3)
        for row in placed:
            old = self.slots.get(row.key)
            changed = old is None or row.text.rstrip() != old.row.text.rstrip()
            if (
                old is not None
                and not scrolling
                and self.tracks[row.copy.line.key].scrolling
            ):
                row = replace(row, x=old.row.x)
            slot = Slot(
                row,
                now if old is None or not old.row.text else old.since,
                None if changed or old is None else old.ready,
                settled_at=None if changed or old is None else old.settled_at,
                entry=old.entry if old is not None else None,
            )
            if (
                old is None
                and row.start
                and self.animate
                and not repack
                and not self.tracks[row.copy.line.key].scrolling
            ):
                slot.entry = Glide()
            if (
                old is not None
                and self.animate
                and not repack
                and row.y < old.row.y - EPS
            ):
                slot.lift = Tween(old.row.y, row.y, now, handover)
                self.lift_ends = max(self.lift_ends, now + handover)
            slot.incoming = old is None or old.incoming
            slots[row.key] = slot
        self.slots = slots
        for caption_key, track in self.tracks.items():
            track.pending = False
            if caption_key in updates:
                track.words = updates[caption_key]
        self._pan_rows(dt)

    @property
    def read_until(self) -> float | None:
        return max(
            (s.ready for s in self.slots.values() if s.ready is not None), default=None
        )

    @property
    def animating(self) -> bool:
        return (
            self.waiting
            or self.queued
            or self.single_cell_wait
            or self.now + EPS < self.lift_ends
            or any(
                s.row.copy.writing
                or (s.entry is not None and s.entry.moving(self.now))
                or (s.row.phase == "settled" and s.ready is None)
                or any(
                    abs(pan.x - pan.target) > EPS
                    for pan in self.tracks[s.row.copy.line.key].pans
                )
                for s in self.slots.values()
            )
        )

    def rows(self) -> list[PaintRow]:
        rows = []
        # Surviving rows share the same lift curve. Incoming rows wait until
        # the lift clears their cells.
        for slot in self.slots.values():
            if not slot.row.text or (slot.incoming and self.now + EPS < self.lift_ends):
                continue
            phase = "settled" if slot.ready is not None else "live"
            rows.append(
                replace(
                    slot.row,
                    y=slot.position(self.now),
                    phase=phase,
                    entry_offset=slot.entry.px if slot.entry else 0.0,
                )
            )
        return rows


EDGE_FADE_EM = 1.4  # positive em spanning the fade beyond the window margin


def subtitle_rooms(
    engine: CaptionLayout,
    size: float,
    languages: tuple[Language | None, Language | None],
) -> tuple[RowRoom, RowRoom]:
    return (
        engine.subtitle_room(RowKind.ORIGINAL, size, languages[0]),
        engine.subtitle_room(RowKind.TRANSLATION, size, languages[1]),
    )


def subtitle_cell(room: RowRoom, nominal: float) -> float:
    text, above, below = room
    return max(nominal, text + 2.0) + above + below


def subtitle_gap(engine: CaptionLayout, size: float) -> float:
    return TRANSLATION_GAP + (ARROW_ROW_GAP * size if engine.style.arrows else 0)


def subtitle_pixels(
    engine: CaptionLayout,
    size: float,
    languages: tuple[Language | None, Language | None],
) -> tuple[int, int]:
    style = engine.style
    if style.language_sizes is not None:
        sizes = dict(style.language_sizes)
        spoken, target = languages
        original = sizes.get(spoken, 1.0) if spoken is not None else 1.0
        translated = sizes.get(target, 1.0) if target is not None else 1.0
        return round(style.text_px * size * original), round(
            style.text_px * size * translated
        )
    return round(style.text_px * size), round(
        style.text_px * (style.translation_size or size) * style.translation_factor
    )


def subtitle_height(
    engine: CaptionLayout,
    size: float,
    languages: tuple[Language | None, Language | None],
    sides: tuple[bool, bool],
    lines: int,
    labelled: bool,
) -> float:
    p = engine.style
    orig, tr = subtitle_pixels(engine, size, languages)
    nominal = orig * ORIGINAL_LINE_EM, tr * TRANSLATION_LINE_EM
    rooms = subtitle_rooms(engine, size, languages)
    original = subtitle_cell(rooms[0], nominal[0])
    if sides[0] and languages[0] is None and p.reading_lines:
        # Detect can choose a script with a reading band on its first update.
        for language in p.reading_lines:
            room = engine.subtitle_room(RowKind.ORIGINAL, size, Language(language))
            original = max(original, subtitle_cell(room, nominal[0]))
    cells = (original if sides[0] else 0) + (
        subtitle_cell(rooms[1], nominal[1]) if sides[1] else 0
    )
    pair = subtitle_gap(engine, size) if all(sides) else 0
    label = engine.subtitle_label_height(size) if labelled else 0
    return lines * (cells + pair + label) + (lines - 1) * orig * BLOCK_GAP_EM


class Video:
    def __init__(self) -> None:
        self.flow: VideoFlow | None = None
        self._sides = (True, True)
        self._scrolling = False
        self.history_through: int | None = None
        self._entered_after = -1
        self._prior_captions: set[tuple[SourceId, CaptionId]] = set()
        self.live_start = -1
        self.viewport: tuple = ()
        self.final: set[tuple[SourceId, CaptionId]] = set()
        self.phase = ""
        self.row_start = 0
        self.fade_width = 0.0
        self.right_fade_width = 0.0
        self.event: Callable[[str], None] | None = None
        self._fonts: dict[bool, QFont] = {}
        self._design: dict[bool, tuple[QFontMetricsF, float]] = {}
        self.measure = lru_cache(maxsize=2048)(self._measure)
        self.painted_width = lru_cache(maxsize=256)(self._painted_width)
        self._copies: dict[int, Copy] = {}
        self._painted: dict[int, Copy] = {}
        self._own_words = WordArrival()
        self._own_key: int | None = None
        self._parts: OrderedDict[tuple, LaidRow] = OrderedDict()

    def _reading_part(
        self, engine: CaptionLayout, source: LaidRow, first: int, end: int
    ) -> LaidRow:
        key = source.layout, first, end
        part = self._parts.get(key)
        if part is None:
            part = self._parts[key] = engine.subtitle_part(source, first, end)
            if len(self._parts) > 1024:
                self._parts.popitem(last=False)
        else:
            self._parts.move_to_end(key)
        return part

    @staticmethod
    def _runs(laid: LaidLine, translation: bool, first: int, end: int):
        offset = 0
        for source in laid.rows:
            if (source.row.kind is RowKind.TRANSLATION) != translation:
                continue
            stop = offset + len(source.row.text)
            start, last = max(offset, first), min(stop, end)
            if start < last:
                yield source, offset, start, last
            offset = stop + 1  # separator between clauses

    def _span_width(
        self,
        engine: CaptionLayout,
        room: int,
        size: float,
        copy: Copy,
        tr: bool,
        start: int,
        end: int,
        *,
        painted: bool = False,
    ) -> float:
        text = copy.translation if tr else copy.original
        measure = self.painted_width if painted else self.measure
        if not engine.style.reading_lines:
            return measure(text[start:end], tr)
        runs = list(
            self._runs(
                engine.laid(copy.line, room, size, single_rows=True), tr, start, end
            )
        )
        if not any(source.above or source.below for source, *_ in runs):
            return measure(text[start:end], tr)
        width = 0.0
        for source, offset, first, last in runs:
            width += measure(text[start:first], tr)
            part = self._reading_part(engine, source, first - offset, last - offset)
            line = part.layout.lineAt(0)
            width += line.horizontalAdvance() + line.x()
            start = last
        return width + measure(text[start:end], tr)

    def _reading_breaks(
        self, engine: CaptionLayout, room: int, size: float, copy: Copy, tr: bool
    ) -> set[int]:
        text = copy.translation if tr else copy.original
        laid = engine.laid(copy.line, room, size, single_rows=True)
        return {
            offset + i
            for source, offset, *_ in self._runs(laid, tr, 0, len(text))
            for marks in (source.above, source.below)
            for mark in marks
            for i in range(mark.start + 1, mark.end)
        }

    def enter(self, lines: Sequence[Line]) -> None:
        """Start the live queue beyond the transcript already in the window."""
        self._entered_after = lines[-1].key if lines else -1

    def retain_in_history(self, source: SourceId, caption: CaptionId) -> None:
        """A late update to a caption already rendered by the previous preset."""
        self._prior_captions.add((source, caption))

    def is_current(self, line: Line) -> bool:
        return (
            line.key > self._entered_after
            and (line.source, line.caption_id) not in self._prior_captions
        )

    def _measure(self, text: str, tr: bool) -> float:
        if tr not in self._design:
            font = QFont(self._fonts[tr])
            units = max(1, round(QRawFont.fromFont(font).unitsPerEm()))
            scale = font.pixelSize() / units
            font.setPixelSize(units)
            self._design[tr] = QFontMetricsF(font), scale
        metrics, scale = self._design[tr]
        return metrics.horizontalAdvance(text) * scale

    def _painted_width(self, text: str, tr: bool) -> float:
        return QFontMetricsF(self._fonts[tr]).horizontalAdvance(text)

    def _copy(self, line: Line) -> Copy:
        final = (line.source, line.caption_id) in self.final
        original = " ".join(r.text for r in line.rows if r.kind is RowKind.ORIGINAL)
        translation = " ".join(
            r.text for r in line.rows if r.kind is RowKind.TRANSLATION
        )
        return Copy(line, original, translation, final)

    def copies(self, lines: Sequence[Line]) -> list[Copy]:
        current = {}
        for line in lines:
            final = (line.source, line.caption_id) in self.final
            copy = self._copies.get(line.key)
            if copy is None or copy.line is not line or copy.final_translation != final:
                copy = self._copy(line)
            current[line.key] = copy
        self._copies = current
        return list(current.values())

    def own_words(self, line: Line, now: float, split: Split | None) -> Copy:
        copy = self._copy(line)
        if split is None:
            return copy
        if self._own_key != line.key:
            self._own_key = line.key
            self._own_words = WordArrival()
        return self._own_words.reveal(copy, now, split)

    def paint(
        self,
        painter: QPainter,
        engine: CaptionLayout,
        ink: Ink,
        marks: Marks | None,
        highlight: Callable,
        lines: Sequence[Line],
        size: float,
        width: int,
        height: int,
        now: float,
        top: float = VIDEO_MARGIN,
        bottom: float = VIDEO_MARGIN,
        *,
        anchor: int | None = None,
        frozen: bool = False,
        split: Split | None = None,
        scrolling: bool = False,
        sides: tuple[bool, bool] = (True, True),
        animate: bool = True,
        languages: tuple[Language | None, Language | None] = (None, None),
        lines_shown: int | None = None,
    ) -> list[PlacedSubtitle]:
        p = engine.style
        room = width - 2 * VIDEO_MARGIN
        if room <= 0:
            return []
        lines = [line for line in lines if line.rows]
        if anchor is None:
            self.history_through = None
            lines = [line for line in lines if self.is_current(line)]
            if not lines:
                self.flow = None
                self.live_start = -1
                self._painted.clear()
                return []
        elif lines:
            if self.history_through is None:
                self.history_through = lines[-1].key
            lines = [line for line in lines if line.key <= self.history_through]
        if not lines:
            return []
        laid = engine.laid(lines[-1], room, size, single_rows=True)
        label_height = (
            laid.label.boundingRect().height() + p.label_gap * size
            if laid.label
            else 0.0
        )
        foot = height - bottom
        available = foot - top
        actual = {
            r.row.kind: Language(language)
            for r in laid.rows
            if (language := r.row.language or caption_language(r.row)) is not None
        }
        languages = (
            actual.get(RowKind.ORIGINAL, languages[0]),
            actual.get(RowKind.TRANSLATION, languages[1]),
        )
        orig, tr = subtitle_pixels(engine, size, languages)
        rooms = subtitle_rooms(engine, size, languages)
        annotated = bool(p.reading_lines or p.link_room)
        row_heights = orig * ORIGINAL_LINE_EM, tr * TRANSLATION_LINE_EM
        if annotated:
            row_heights = (
                subtitle_cell(rooms[0], row_heights[0]),
                subtitle_cell(rooms[1], row_heights[1]),
            )
        gap = subtitle_gap(engine, size)
        one_row = False
        pair_gap = gap if all(sides) else 0
        if (
            label_height
            + sum(h for h, shown in zip(row_heights, sides, strict=True) if shown)
            + pair_gap
            > available
        ):
            # Tight windows use the fonts' natural line boxes, with room
            # for the descender. A source label can yield its own space.
            label_height = 0.0
            faces_by_row = {r.row.kind: r.layout.font() for r in laid.rows}
            measured = []
            for i, (side, px) in enumerate(
                ((RowKind.ORIGINAL, orig), (RowKind.TRANSLATION, tr))
            ):
                font = faces_by_row.get(side)
                if font is None:
                    font = QFont()
                    font.setPixelSize(px)
                height_needed = QFontMetrics(font).height() + 2.0
                measured.append(
                    subtitle_cell(rooms[i], height_needed)
                    if annotated
                    else height_needed
                )
            row_heights = measured[0], measured[1]
            if (
                sum(h for h, shown in zip(row_heights, sides, strict=True) if shown)
                + pair_gap
                > available
            ):
                one_row = True
                oh, th = row_heights
                row_heights = (
                    oh if oh <= available else 0.0,
                    th if th <= available else 0.0,
                )
                if not any(row_heights):
                    return []
        view = (
            engine,
            room,
            top,
            foot,
            size,
            label_height,
            row_heights,
            one_row,
            animate,
            rooms if annotated else (),
            lines_shown,
        )
        previous = self.flow
        # A mic strip appearing above subtitles already clear of it does
        # not restart the reading hold or change their layout.
        if (
            previous is not None
            and anchor is None
            and view[:2] == self.viewport[:2]
            and view[3:] == self.viewport[3:]
            and all(
                slot.row.y >= top + label_height - EPS
                for slot in previous.slots.values()
            )
        ):
            previous.top = top
            self.viewport = view
        layout_changed = view != self.viewport
        if previous is None or layout_changed or anchor is not None:
            self._design.clear()
            self._fonts.clear()
            self._parts.clear()
            self.measure.cache_clear()
            self.painted_width.cache_clear()
            flow = VideoFlow(
                self.measure,
                room,
                top,
                foot,
                orig,
                tr,
                label_height,
                row_heights,
                one_row,
                animate,
                span_width=(
                    lambda copy, tr, a, b: self._span_width(
                        engine, room, size, copy, tr, a, b
                    )
                )
                if p.reading_lines
                else None,
                translation_gap=gap,
                reading_breaks=(
                    lambda copy, tr: self._reading_breaks(engine, room, size, copy, tr)
                )
                if p.reading_lines
                else None,
                lines_shown=lines_shown,
                paired_ranges=(lambda line: engine.paired_ranges(line, room, size))
                if p.paired_lines
                else None,
                pan_width=lambda copy, tr, a, b: self._span_width(
                    engine, room, size, copy, tr, a, b, painted=True
                ),
            )
            if anchor is None:
                if previous is not None:
                    flow.last_key = previous.last_key
                    flow.tracks = previous.tracks
                    flow.slots = previous.slots
                    flow.now = previous.now
                    if (previous.paired_ranges is None) != (flow.paired_ranges is None):
                        # Reflow even a finished caption when its row order changes.
                        # Keep the spoken words and the first still-visible offsets.
                        flow.slots = {}
                        for caption_track in flow.tracks.values():
                            caption_track.scrolling = scrolling
                            caption_track.pans = Pan(), Pan()
                            caption_track.starts = (
                                caption_track.first[0],
                                caption_track.first[1],
                            )
                self.flow = flow
                self.viewport = view
        else:
            flow = previous
        copies = self.copies(lines)
        fonts = {r.row.kind is RowKind.TRANSLATION: r.layout.font() for r in laid.rows}
        # A translation can arrive while the newest caption has only an
        # original. A cached substitute face must give way to the real face
        # before any of that translation is measured or wrapped.
        for kind in (False, True):
            if kind not in fonts:
                older = next(
                    (
                        c.line
                        for c in reversed(copies)
                        if (c.translation if kind else c.original)
                    ),
                    None,
                )
                if older is not None:
                    track = engine.laid(older, room, size, single_rows=True)
                    fonts[kind] = next(
                        r.layout.font()
                        for r in track.rows
                        if (r.row.kind is RowKind.TRANSLATION) == kind
                    )
        font_changed = False
        for kind, font in fonts.items():
            if self._fonts.get(kind) != font:
                font_changed |= any(
                    slot.row.translation == kind and bool(slot.row.text)
                    for slot in flow.slots.values()
                )
                self._fonts[kind] = font
                self._design.pop(kind, None)
                self.measure.cache_clear()
                self.painted_width.cache_clear()
        if False not in self._fonts:
            font = QFont(self._fonts[True])
            font.setPixelSize(orig)
            self._fonts[False] = font
        if True not in self._fonts:
            font = QFont(self._fonts[False])
            font.setPixelSize(tr)
            self._fonts[True] = font
        if anchor is not None:
            rows = self._history_rows(flow, copies, anchor, sides)
        else:
            shrunk = previous is not None and (
                room < previous.width or available < previous.foot - previous.top
            )
            rows = self._live_rows(
                flow,
                copies,
                layout_changed or font_changed,
                shrunk,
                now,
                frozen,
                split,
                scrolling,
                sides,
            )
            if rows and not frozen:
                self.live_start = min(row.copy.line.key for row in rows)
        return self._paint_rows(
            painter,
            engine,
            ink,
            marks,
            highlight,
            rows,
            flow,
            size,
            width,
            height,
            orig,
            rooms if annotated else None,
        )

    def _live_rows(
        self,
        flow: VideoFlow,
        copies: list[Copy],
        repack: bool,
        shrunk: bool,
        now: float,
        frozen: bool,
        split: Split | None,
        scrolling: bool,
        sides: tuple[bool, bool],
    ) -> list[PaintRow]:
        repack |= sides != self._sides or scrolling != self._scrolling
        if frozen and not repack:
            return flow.rows()
        # Repainting a dirty region twice at one instant must not reveal more words.
        current = {c.line.key: c for c in copies}
        if repack or now != flow.now or self._painted != current:
            flow.advance(
                copies,
                now,
                split,
                scrolling=scrolling,
                sides=sides,
                repack=repack,
                resized=shrunk,
            )
            if self.event:
                for event in flow.events:
                    self.event(event)
            self._painted = current
            self._sides = sides
            self._scrolling = scrolling
        return flow.rows()

    @staticmethod
    def _history_rows(
        flow: VideoFlow,
        copies: Sequence[Copy],
        anchor: int,
        sides: tuple[bool, bool],
    ) -> list[PaintRow]:
        """Fill a stationary history page with complete, wrapped rows."""
        start = next(
            (i for i, c in enumerate(copies) if c.line.key >= anchor), len(copies) - 1
        )
        bottom = flow.top + flow.label_height
        rows: list[PaintRow] = []
        for copy in copies[start:]:
            for row in flow.shape(copy, False, sides):
                y = bottom + (flow.spacing(rows[-1], row) if rows else 0.0)
                if y + row.height > flow.foot:
                    return rows
                rows.append(replace(row, y=y, phase="history"))
                bottom = y + row.height
        return rows

    def _paint_rows(
        self,
        painter: QPainter,
        engine: CaptionLayout,
        ink: Ink,
        marks: Marks | None,
        highlight: Callable,
        rows: Sequence[PaintRow],
        flow: VideoFlow,
        size: float,
        width: int,
        height: int,
        orig: int,
        rooms: tuple[RowRoom, RowRoom] | None,
    ) -> list[PlacedSubtitle]:
        room = width - 2 * VIDEO_MARGIN
        groups = groupby(rows, lambda r: r.copy.line.key)
        placed = []
        for _, group in groups:
            rows = list(group)
            line = rows[-1].copy.line
            original = engine.laid(line, room, size, single_rows=True)
            y = rows[0].y - flow.label_height
            if original.label and flow.label_height:
                header = LaidLine(
                    (), flow.label_height, label=original.label, width=room
                )
                engine.paint(
                    painter,
                    line,
                    header,
                    QPointF(VIDEO_MARGIN, y),
                    replace(ink, alpha=ink.alpha * rows[0].alpha),
                    marks,
                )
            parts = []
            for r in rows:
                row_line = r.copy.line
                shaped = engine.laid(row_line, room, size, single_rows=True)
                self.phase = r.phase
                edge = VIDEO_MARGIN + EDGE_FADE_EM * orig
                self.fade_width = edge if r.x > 0.5 else 0.0
                stop = r.start + len(r.text.rstrip())
                extent = flow.advance_width(r.copy, r.translation, r.start, stop) - r.x
                self.right_fade_width = edge if extent > room + EPS else 0.0
                for source, offset, first, last in self._runs(
                    shaped, r.translation, r.start, r.start + len(r.text)
                ):
                    lead = flow.advance_width(r.copy, r.translation, r.start, first)
                    x = lead - r.x
                    continues = engine.style.paired_lines and (
                        (r.continues and first < stop <= last)
                        or (
                            source.row.continues
                            and last - offset == len(source.row.text)
                        )
                    )
                    if source.above or source.below:
                        fragment = self._reading_part(
                            engine, source, first - offset, last - offset
                        )
                        x += fragment.layout.lineAt(0).x()
                        part = visible_row(
                            fragment,
                            0,
                            len(fragment.row.text),
                            QPointF(lead - r.x, 0),
                            continues=continues,
                            later_readings=(
                                source.row.continues
                                or any(m.start >= last - offset for m in source.above),
                                source.row.continues
                                or any(m.start >= last - offset for m in source.below),
                            ),
                        )
                    else:
                        at = QPointF(x - source.layout.lineAt(0).x(), 0)
                        part = visible_row(
                            source,
                            first - offset,
                            last - offset,
                            at,
                            continues=continues,
                        )
                    natural = (
                        part.layout.lineAt(0)
                        .naturalTextRect()
                        .translated(part.layout.position())
                    )
                    # Leave one physical pixel below the baseline for the
                    # rasterised descender beyond its design extent.
                    _, above, below = (
                        rooms[int(r.translation)] if rooms else (0.0, 0.0, 0.0)
                    )
                    dy = (
                        (r.height - natural.height() + above - below) / 2
                        - natural.top()
                        - 1 / painter.device().devicePixelRatioF()
                    )
                    part = replace(part, top=r.y - y + dy)
                    # Only complete visible graphemes are selectable. Paint
                    # the original shaped run so its trailing pixels can fade.
                    hit_part = panned_row(part, 0, width, left_edge=-VIDEO_MARGIN)
                    if hit_part is not None:
                        parts.append((row_line, hit_part))
                    self.row_start = first
                    self._paint_row(
                        painter,
                        engine,
                        row_line,
                        part,
                        r,
                        ink,
                        marks,
                        highlight,
                        width,
                        height,
                        y,
                        x,
                    )
            if parts:
                h = max(r.y + r.height for r in rows) - y
                if engine.style.arrows and marks:
                    painter.save()
                    painter.setClipRect(
                        QRectF(0, max(flow.top, y), width, h),
                        Qt.ClipOperation.IntersectClip,
                    )
                    engine.subtitle_arrows(
                        painter, line, parts, QPointF(VIDEO_MARGIN, y), ink, marks
                    )
                    painter.restore()
                # A held wrap can still show the earlier wording of a clause.
                # Hit testing and lookup use the same snapshot as its paint.
                hit_rows = tuple(
                    part if snapshot is line else replace(part, painted_from=snapshot)
                    for snapshot, part in parts
                )
                placed.append(
                    (
                        line,
                        LaidLine(hit_rows, h, label=original.label, width=room),
                        QRectF(VIDEO_MARGIN, y, room, h),
                    )
                )
        self.phase = ""
        self.row_start = 0
        self.fade_width = 0.0
        self.right_fade_width = 0.0
        return placed

    def _paint_row(
        self,
        painter: QPainter,
        engine: CaptionLayout,
        line: Line,
        part: LaidRow,
        row: PaintRow,
        ink: Ink,
        marks: Marks | None,
        highlight: Callable,
        width: int,
        height: int,
        y: float,
        x: float,
    ) -> None:
        laid = LaidLine((part,), row.height, width=width)
        # QTextLine stores offsets in 1/64 px. Retain the subpixel remainder
        # in the painter origin so the slow end of the ease stays continuous.
        remainder = x - part.layout.lineAt(0).x()
        origin = QPointF(VIDEO_MARGIN + remainder, y)
        opacity = replace(ink, alpha=ink.alpha * row.alpha)
        cell = QRectF(0, row.y - row.entry_offset, width, row.height)
        if not (self.fade_width or self.right_fade_width):
            painter.save()
            try:
                painter.setClipRect(cell, Qt.ClipOperation.IntersectClip)
                highlight(painter, line, laid, origin)
                engine.paint(painter, line, laid, origin, opacity, marks)
            finally:
                painter.restore()
            return
        # Isolate this row so the gradient fades glyphs, decorations and
        # highlights together without erasing the panel or a neighbouring row.
        dpr = painter.device().devicePixelRatioF()
        layer = QImage(
            round(width * dpr),
            round(height * dpr),
            QImage.Format.Format_ARGB32_Premultiplied,
        )
        layer.setDevicePixelRatio(dpr)
        layer.fill(Qt.GlobalColor.transparent)
        layer_painter = QPainter(layer)
        try:
            layer_painter.setClipRect(cell)
            layer_painter.setRenderHints(painter.renderHints())
            highlight(layer_painter, line, laid, origin)
            engine.paint(layer_painter, line, laid, origin, opacity, marks)
            layer_painter.setCompositionMode(
                QPainter.CompositionMode.CompositionMode_DestinationOut
            )
            for edge, inside in (
                (0, self.fade_width),
                (width, width - self.right_fade_width),
            ):
                if edge == inside:
                    continue
                mask = QLinearGradient(edge, 0, inside, 0)
                mask.setColorAt(0, QColor(0, 0, 0, 255))
                mask.setColorAt(1, QColor(0, 0, 0, 0))
                layer_painter.fillRect(
                    QRectF(min(edge, inside), row.y, abs(edge - inside), row.height),
                    mask,
                )
        finally:
            layer_painter.end()
        painter.drawImage(QPointF(), layer)
