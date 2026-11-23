"""A transcript's own state, as plain Python - no Qt (polyglotic-hq project
109's structure, section 3: W2).

One transcript per app captioned (the user, 2026-11-06: "a different
transcript per app"): that app's finished captions this session - and the
user's own ("You") while its caption window shows my speech - in its
caption window's language (or Original only: no translation lines), up
to `TRANSCRIPT_LINES` listed - or as far back as the learner chooses
(`TranscriptLength`: three hours, the whole session; polyglotic-hq 334) -
and the whole session (`SESSION_LINES`) kept for Copy all and Save, the
list's foot saying so once they differ (polyglotic-hq 137). It collects from the moment the app is captioned,
whether its window is open or not, so closing the window loses nothing.

- **Search** filters the lines to those that match (in any row, any case)
  and counts them; the matches are highlighted where they show
  (`match_spans`). A new search shows the newest match.
- **Following or scrolled back**, as a caption window: `new_since_scroll`
  counts the lines that arrived since the learner scrolled back ("Back to
  live · N new").
- **What it remembers, per app** (`TranscriptChoices`): its own text size
  (A- / A+; 100 % at first) and whether its settings rail is open - one
  setting, `transcripts`, beside today's.
- **Saved or not** (`needs_saving`): more than `ASK_FROM_LINES` lines
  kept and some arrived since the learner last saved the whole session -
  what Quit asks about (polyglotic-hq 334).
- **Where it opens** (`beside`): beside its caption window - right, left,
  above or below - if there's room on that screen, else centred on it;
  720 x 520 at first, 520 x 320 at least. Never exactly over another open
  transcript (`clear_of`). Below 700 px wide the rail is a popover instead (`rail_inline`).

The caption layout engine lays out the lines a transcript shows - each
transcript with a layout cache of its own, never shared with its caption
window: the two never lay a line out at the same width, text size and
style (decided in project 116; see `ui_next.transcript_window`).

Holds caption text: never log it. Not thread-safe - the interface thread.
"""

import bisect
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import StrEnum

from polyglotic_desktop.core.listening.captions import CaptionUpdate, Clause, Language
from polyglotic_desktop.core.listening.delays import CaptionDelay
from polyglotic_desktop.core.listening.history import Caption
from polyglotic_desktop.core.listening.sources import SourceId
from polyglotic_desktop.core.listening.timing import CaptionId
from polyglotic_desktop.ui_next.views.captions import (
    SESSION_LINES,
    TEXT_SIZES,
    TRANSCRIPT_LINES,
    TRANSCRIPT_MOST_LINES,
    CaptionLines,
    Labels,
    Line,
)
from polyglotic_desktop.ui_next.views.placement import Rect, Size
from polyglotic_desktop.ui_next.views.scroll import Scroll
from polyglotic_desktop.ui_next.views.sentences import Piece

STORED_KEY = "transcripts"
"""The setting the transcripts' own choices are stored under, by app."""

MIN_SIZE = Size(520, 320)
DEFAULT_SIZE = Size(720, 520)
MOST_OF_AREA = 0.75
"""A transcript's minimum is never more than this share of its work area,
each way: at Windows' 150 % and the app's Larger or Largest, MIN_SIZE times
the text size (1131 x 696, 1170 x 720) was taller than a 1080p laptop's
672 px at 150 % (polyglotic-hq 586)."""
RAIL_WIDTH = 356
"""The settings rail, beside the list: the session's panels are 320 px wide
(project 115), with the rail's margins and scroll bar around them (109
said 300)."""
RAIL_INLINE_FROM = 700
"""At least this wide, the rail slides in beside the list; narrower, it
opens as a popover."""
GAP = 12
"""Pixels between a caption window and its transcript beside it."""
CASCADE = 32
"""How far down and right a transcript opens from another one already at
its place (`clear_of`)."""


TRANSCRIPT_HOURS: int = 3
ASK_FROM_LINES = 300
"""A transcript with more lines than this - the 300 captions the app's
history kept before transcripts kept more (polyglotic-hq 334's brief) -
is asked about at Quit while it isn't saved."""


class TranscriptLength(StrEnum):
    """How far back every transcript's list goes - what its window scrolls
    through and searches: the learner's choice in Settings > App
    (polyglotic-hq 334; the user's feedback 16, 2026-11-13: "a 3-hour
    lecture"). Copy all and Save have the whole session whichever it is
    (`SESSION_LINES`), as before. The caption windows keep their own
    150 lines: none of this reaches them."""

    NEWEST = "newest"
    """The newest 1,000 lines (`TRANSCRIPT_LINES`): as before 334, the default."""
    THREE_HOURS = "three_hours"
    """The lines of the last three hours, up to `TRANSCRIPT_MOST_LINES`."""
    SESSION = "session"
    """Every line this session, up to `TRANSCRIPT_MOST_LINES`."""

    @property
    def limits(self) -> tuple[int, float | None]:
        """At most how many lines it lists, and from how many seconds back
        (None: however long ago)."""
        if self is TranscriptLength.THREE_HOURS:
            return TRANSCRIPT_MOST_LINES, TRANSCRIPT_HOURS * 3600.0
        if self is TranscriptLength.SESSION:
            return TRANSCRIPT_MOST_LINES, None
        return TRANSCRIPT_LINES, None

    @classmethod
    def from_stored(cls, stored: object) -> "TranscriptLength":
        """The stored choice; anything else is the default."""
        try:
            return cls(str(stored))
        except ValueError:
            return cls.NEWEST


@dataclass(frozen=True)
class _Unlabelled(Labels):
    """No label line above a transcript's lines: the transcript draws its
    own heading (time, "You", the language spoken, checked)."""

    def of(
        self,
        caption: Caption,
        took: CaptionDelay | None = None,
        before: Caption | None = None,
    ) -> tuple[str, str]:
        return "", ""


@dataclass(frozen=True, slots=True)
class TranscriptChoices:
    """What a transcript remembers for its app: its text size, whether its
    settings rail is open, and its window's size as the learner left it
    (None: the usual first size; polyglotic-hq 586)."""

    text_size: float = 1.0
    rail_open: bool = False
    size: tuple[int, int] | None = None

    def to_stored(self) -> dict[str, object]:
        stored: dict[str, object] = {
            "text_size": self.text_size,
            "rail_open": self.rail_open,
        }
        if self.size is not None:
            stored["size"] = list(self.size)
        return stored

    @classmethod
    def from_stored(cls, stored: object) -> "TranscriptChoices":
        """Stored choices; anything missing or not valid is the default."""
        found = cls()
        if not isinstance(stored, Mapping):
            return found
        size = stored.get("text_size")
        if (
            isinstance(size, int | float)
            and not isinstance(size, bool)
            and TEXT_SIZES[0] <= size <= TEXT_SIZES[1]
        ):
            found = replace(found, text_size=round(float(size), 2))
        if isinstance(stored.get("rail_open"), bool):
            found = replace(found, rail_open=bool(stored["rail_open"]))
        size = stored.get("size")
        if (
            isinstance(size, list | tuple)
            and len(size) == 2
            and all(isinstance(n, int) and not isinstance(n, bool) for n in size)
            and all(0 < n <= 16384 for n in size)
        ):
            found = replace(found, size=(int(size[0]), int(size[1])))
        return found


@dataclass
class StoredTranscripts:
    """Every transcript's choices, by its app's key (as its caption
    window's)."""

    by_key: dict[str, TranscriptChoices] = field(default_factory=dict)

    def to_stored(self) -> dict[str, object]:
        return {key: c.to_stored() for key, c in self.by_key.items()}

    @classmethod
    def from_stored(cls, stored: Mapping[str, object]) -> "StoredTranscripts":
        """From the whole stored settings."""
        own = stored.get(STORED_KEY)
        if not isinstance(own, Mapping):
            return cls()
        return cls({str(k): TranscriptChoices.from_stored(v) for k, v in own.items()})


def beside(window: Rect | None, size: Size, area: Rect) -> Rect:
    """Where a transcript `size` big opens: beside its caption window
    (`window`) on the work area `area` - to its right, else its left
    (level with its top), else above it, else below it (centred on it) -
    wherever it fits first; else centred on `area`. Never bigger than the
    area."""
    width, height = min(size.width, area.width), min(size.height, area.height)
    if window is not None:
        top = min(max(window.y, area.y), area.bottom - height)
        right = window.right + GAP
        if right + width <= area.right:
            return Rect(right, top, width, height)
        left = window.x - GAP - width
        if left >= area.x:
            return Rect(left, top, width, height)
        x = window.x + (window.width - width) // 2
        x = min(max(x, area.x), area.right - width)
        above = window.y - GAP - height
        if above >= area.y:
            return Rect(x, above, width, height)
        below = window.bottom + GAP
        if below + height <= area.bottom:
            return Rect(x, below, width, height)
    return Rect(
        area.x + (area.width - width) // 2,
        area.y + (area.height - height) // 2,
        width,
        height,
    )


def clear_of(
    place: Rect, taken: Sequence[Rect], area: Rect, step: int = CASCADE
) -> Rect:
    """`place`, moved down and right `step` at a time while another open
    transcript (`taken`) has its top left corner there, kept within `area`;
    `place` itself if there's no room to move. On a screen too small for a
    transcript beside its caption window - 1280 x 720 at 150 %, 1366 x 768 -
    each opened centred, exactly over the one before, so a second transcript
    looked like the first one replaced (polyglotic-hq 184)."""
    corners = {(r.x, r.y) for r in taken}
    moved = place
    while (moved.x, moved.y) in corners:
        moved = Rect(moved.x + step, moved.y + step, moved.width, moved.height)
        if moved.right > area.right or moved.bottom > area.bottom:
            return place
    return moved


def rail_inline(width: int, text_scale: float = 1.0) -> bool:
    """Whether the settings rail shows beside the list at `width` (else as
    a popover) - at a larger text size the rail is wider, and so is the
    window it fits beside."""
    return width >= RAIL_INLINE_FROM * text_scale


def pattern(query: str) -> re.Pattern[str] | None:
    """The search for `query`, any case, its characters taken literally;
    None for no search."""
    query = query.strip()
    return re.compile(re.escape(query), re.IGNORECASE) if query else None


def match_spans(text: str, search: re.Pattern[str] | None) -> list[tuple[int, int]]:
    """Where `search` matches in `text`: characters `[start, end)` each."""
    if search is None:
        return []
    return [m.span() for m in search.finditer(text)]


def _matches(line: Line, search: re.Pattern[str]) -> bool:
    return any(search.search(row.text) for row in line.rows)


Spot = tuple[int, int, int]
"""A place in a transcript's text: a line's key, a row of it (what was
said, its translation), and a place in that row's text - in reading order
as tuples are ordered (polyglotic-hq 343)."""


def selected_spans(line: Line, one: Spot, other: Spot) -> list[tuple[int, int, int]]:
    """What of `line` is selected between `one` and `other`: (row, from,
    to) for each row with something selected."""
    start, end = sorted((one, other))
    found = []
    for index, row in enumerate(line.rows):
        here = (line.key, index)
        if here < start[:2] or here > end[:2]:
            continue
        begin = start[2] if here == start[:2] else 0
        stop = end[2] if here == end[:2] else len(row.text)
        if begin < stop:
            found.append((index, begin, stop))
    return found


def selected_text(lines: Sequence[Line], one: Spot, other: Spot) -> str:
    """What's selected between `one` and `other` among `lines` (those
    listed: a search's matches while searching), as they show: what was
    said and its translation, each row on a line of its own, in order.
    Lines scrolled out of view count too."""
    start, end = sorted((one, other))
    said = []
    first = bisect.bisect_left(lines, start[0], key=lambda ln: ln.key)
    for line in lines[first:]:
        if line.key > end[0]:
            break
        said += [line.rows[i].text[a:b] for i, a, b in selected_spans(line, one, other)]
    return "\n".join(said)


def selected_pieces(lines: Sequence[Line], one: Spot, other: Spot) -> list[Piece]:
    """What's selected between `one` and `other`, as rows with their
    selected characters, in reading order: what `views.sentences` saves
    (polyglotic-hq 459)."""
    start, end = sorted((one, other))
    found: list[Piece] = []
    first = bisect.bisect_left(lines, start[0], key=lambda ln: ln.key)
    for line in lines[first:]:
        if line.key > end[0]:
            break
        found += [
            (line, line.rows[i], a, b) for i, a, b in selected_spans(line, one, other)
        ]
    return found


@dataclass(frozen=True, slots=True)
class Foot:
    """What the line under the list says: `count` lines (or matches while
    searching), and whether it's following. `earlier`: lines kept from
    before the list's - in Copy all and Save, not listed or searched;
    `listed`: the lines the list holds."""

    count: int
    searching: bool
    following: bool
    new: int
    earlier: int = 0
    listed: int = 0


class Transcript:
    """One app's transcript: its finished captions, searched or not."""

    def __init__(
        self,
        source: SourceId,
        target: Language | None,
        *,
        second: Language | None = None,
        mic: SourceId | None = None,
        show_mic: bool = False,
        text_size: float = 1.0,
        clock: Callable[[], datetime] | None = None,
        length: TranscriptLength = TranscriptLength.NEWEST,
    ) -> None:
        """`source`: the app; `mic`: the user's own mic, shown with
        `show_mic`. `target`: its caption window's language (None:
        Original only); `second`: the language shown for a clause already
        in `target`. `clock`: when captions arrive (default: now).
        `length`: how far back its list goes."""
        self.source = source
        self.mic = mic
        self.show_mic = show_mic
        self.second = second
        self.length = length
        self.captions = CaptionLines(
            self._sources(),
            target,
            keep=length.limits[0],
            keep_earlier=SESSION_LINES,
            second=second,
            yours=(mic,) if mic else (),
            text_size=text_size,
            labels=_Unlabelled(),
            finished_only=True,
            clock=clock,
        )
        if length.limits[1] is not None:
            self.captions.set_limits(*length.limits)
        self.query = ""
        self.search_pattern: re.Pattern[str] | None = None
        self._searches = 0  # searches made: what shows changed
        self._changes = 0  # lines added or changed: what a save must catch up on
        self._saved_at: int | None = None  # `_changes` at the last whole save
        self._matching: tuple[int, tuple[Line, ...]] | None = None
        self._seen = -1  # the newest line's key when last following

    # -- what shows -----------------------------------------------------------------

    @property
    def scroll(self) -> Scroll:
        return self.captions.scroll

    @property
    def revision(self) -> int:
        """Goes up on anything that changes what shows."""
        return self.captions.revision + self._searches

    @property
    def text_size(self) -> float:
        return self.captions.text_size

    @property
    def target(self) -> Language | None:
        return self.captions.target

    @property
    def started_at(self) -> datetime:
        return self.captions.started_at

    @property
    def all_lines(self) -> tuple[Line, ...]:
        """Every line kept, searched or not."""
        return self.captions.lines

    @property
    def lines(self) -> tuple[Line, ...]:
        """The lines that show: every line, or while searching the ones that
        match - oldest first."""
        search = self.search_pattern
        if search is None:
            return self.captions.lines
        revision = self.captions.revision
        if self._matching is None or self._matching[0] != revision:
            found = tuple(ln for ln in self.captions.lines if _matches(ln, search))
            self._matching = (revision, found)
        return self._matching[1]

    def captions_kept(self) -> list[Caption]:
        """What Copy all and Save write out: the whole session - the lines
        kept from before the list's, then the list's - or, while
        searching, the matches shown."""
        shown = self.captions.captions_of(self.lines)
        if self.search_pattern is not None:
            return shown
        return [*self.captions.earlier, *shown]

    @property
    def kept(self) -> int:
        """How many lines Copy all and Save have: the whole session's."""
        return len(self.captions.earlier) + len(self.captions.lines)

    def mark_saved(self) -> None:
        """The whole session was just written to a file the learner chose -
        not while searching: that writes only the matches."""
        if self.search_pattern is None:
            self._saved_at = self._changes

    def needs_saving(self) -> bool:
        """More than `ASK_FROM_LINES` lines kept, and a line added or
        changed since the learner last saved the whole session: what Quit
        asks about (polyglotic-hq 334)."""
        return self.kept > ASK_FROM_LINES and self._changes != self._saved_at

    def languages(self) -> list[Language]:
        """The translations copied and saved: the window's language, and the
        second language for lines already in it; none for Original only."""
        target, second = self.target, self.second
        if target is None:
            return []
        return [target] if second is None or second == target else [target, second]

    def seconds(self) -> dict[Language, Language]:
        """The second language of the window's language, as `transcript`'s
        exports read it: a line already in the window's language is
        translated into the second, kept under the window's language
        (polyglotic-hq 432)."""
        target, second = self.target, self.second
        return {} if target is None or second is None else {target: second}

    def foot(self) -> Foot:
        """What the line under the list says now (and, while following, the
        newest line seen - for "N new" once scrolled back)."""
        lines = self.lines
        following = self.scroll.following or not lines
        if following:
            self._seen = lines[-1].key if lines else self._seen
        new = 0 if following else sum(1 for ln in lines if ln.key > self._seen)
        return Foot(
            len(lines),
            self.search_pattern is not None,
            following,
            new,
            earlier=len(self.captions.earlier),
            listed=len(self.captions.lines),
        )

    # -- from the session ----------------------------------------------------------

    def apply(self, update: CaptionUpdate) -> bool:
        """A caption update; True if a line that shows changed."""
        changed = self.captions.apply(update)
        self._changes += changed
        return changed

    def use_checked(
        self,
        caption_id: CaptionId,
        clauses: tuple[Clause, ...],
        language: Language | None,
        languages_heard: tuple[Language, ...],
    ) -> bool:
        changed = self.captions.use_checked(
            caption_id, clauses, language, languages_heard
        )
        self._changes += changed
        return changed

    # -- what its caption window chose -------------------------------------------------

    def set_language(self, target: Language | None, second: Language | None) -> None:
        self.second = second
        self.captions.set_language(target, second)

    def set_show_mic(self, on: bool) -> None:
        """My speech shown here from now on, or not (lines kept stay)."""
        if on != self.show_mic:
            self.show_mic = on
            self.captions.show_sources(self._sources())

    def _sources(self) -> tuple[SourceId, ...]:
        if self.show_mic and self.mic is not None:
            return (self.source, self.mic)
        return (self.source,)

    # -- the learner's -----------------------------------------------------------------

    def search(self, query: str) -> None:
        """Only the lines matching `query` (none: every line), the newest
        match showing."""
        if query == self.query:
            return
        self.query = query
        self.search_pattern = pattern(query)
        self._matching = None
        self._searches += 1
        self.scroll.follow()

    def set_text_size(self, size: float) -> None:
        self.captions.set_text_size(size)

    @property
    def settle_after(self) -> float:
        return self.captions.settle_after

    def set_settle_after(self, seconds: float) -> None:
        """How long listed text may still change (polyglotic-hq 309)."""
        self.captions.set_settle_after(seconds)

    def set_length(self, length: TranscriptLength) -> None:
        """How far back the list goes, from now: shorter, its oldest lines
        go into Copy all and Save only; longer, the lines kept there come
        back to it (as text: no word links)."""
        if length is self.length:
            return
        self.length = length
        self.captions.set_limits(*length.limits)
        self._matching = None

    def go_live(self) -> None:
        self.scroll.follow()
