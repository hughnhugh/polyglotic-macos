"""Where a surface's lines are scrolled to, measuring only what shows.

A caption window or a transcript follows the newest line - drawn at the
bottom, older ones above it - until the learner scrolls back. Then it
holds the line at its top where it is, as new lines arrive, the window is
resized or the text size changes, until they scroll down to the newest
again and it follows once more.

Lines are measured only as they're walked over: `height` is asked for the
lines that show and the few a scroll steps across, never the whole list
(project 108: a list view re-measuring 1,000 rows on a width change took
26-41 ms). Heights are in pixels, from the widget that lays the lines
out; nothing here knows Qt.
"""

from bisect import bisect_left
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Protocol


class Keyed(Protocol):
    """A line with a key that grows with each new line (the caption
    history's: oldest first, in key order)."""

    @property
    def key(self) -> int: ...


@dataclass(frozen=True, slots=True)
class Anchor:
    """The line held at the top of the view while scrolled back, and where
    its top is: 0, or above the view (negative) when partly scrolled past."""

    key: int
    offset: float


@dataclass(frozen=True, slots=True)
class Placed[L: Keyed]:
    """A line that shows, and where its top is from the top of the view."""

    line: L
    top: float


class Scroll:
    """Following the newest line (`anchor` None), or held at a line."""

    def __init__(self) -> None:
        self.anchor: Anchor | None = None
        self.sticky = False
        """Held until `follow` is asked for: text that shrinks below the
        held line (a caption withdrawn or set again) never lets go of it
        (Steady's cards: a window scrolled back went live by itself)."""

    @property
    def following(self) -> bool:
        return self.anchor is None

    def follow(self) -> None:
        """Back to the newest line, and following it."""
        self.anchor = None

    def placed[L: Keyed](
        self,
        lines: Sequence[L],
        height: Callable[[L], float],
        view_height: float,
        gap: float,
    ) -> list[Placed[L]]:
        """The lines that show in a view `view_height` tall, top to bottom,
        `gap` apart. Held at a line whose newer lines no longer reach the
        bottom of the view (scrolled down to the newest, or the text
        shrank): following again."""
        if not lines:
            return []
        if self.anchor is not None:
            start = _index(lines, self.anchor.key)
            held = _down(
                lines, start, self.anchor.offset, height, view_height, gap, self.sticky
            )
            if held is not None:
                return held
            if not self.sticky:
                self.anchor = None
        return _up(lines, height, view_height, gap)

    def scroll_by[L: Keyed](
        self,
        dy: float,
        lines: Sequence[L],
        height: Callable[[L], float],
        view_height: float,
        gap: float,
    ) -> None:
        """Scrolls `dy` pixels: back to older lines if positive, towards the
        newest if negative. Stops at the oldest line's top; reaching the
        newest line's bottom follows again."""
        shown = self.placed(lines, height, view_height, gap)
        if not shown:
            return
        index = _index(lines, shown[0].line.key)
        offset = shown[0].top + dy
        while offset > 0 and index > 0:  # room above: the line before shows
            index -= 1
            offset -= height(lines[index]) + gap
        offset = min(offset, 0.0)  # the oldest line's top stays at the top
        while index < len(lines) - 1:  # the top line scrolled past: the next
            below = offset + height(lines[index]) + gap
            if below > 0:
                break
            offset, index = below, index + 1
        # Scrolling towards the newest can end a sticky hold. A reflow
        # alone can't put the reader back at live.
        sticky = dy > 0 and self.sticky and not self.following
        self.anchor = Anchor(lines[index].key, offset)
        if _down(lines, index, offset, height, view_height, gap, sticky) is None:
            self.follow()


def _index(lines: Sequence[Keyed], key: int) -> int:
    """The line with `key` - or, if it went (withdrawn, or dropped from the
    front), the next one still kept."""
    return min(bisect_left(lines, key, key=lambda line: line.key), len(lines) - 1)


def _up[L: Keyed](
    lines: Sequence[L], height: Callable[[L], float], view_height: float, gap: float
) -> list[Placed[L]]:
    """Following: the newest line at the bottom, older ones up to the top."""
    shown: list[Placed[L]] = []
    y = view_height
    for line in reversed(lines):
        y -= height(line)
        shown.append(Placed(line, y))
        if y <= 0:
            break
        y -= gap
    shown.reverse()
    return shown


def _down[L: Keyed](
    lines: Sequence[L],
    start: int,
    offset: float,
    height: Callable[[L], float],
    view_height: float,
    gap: float,
    sticky: bool,
) -> list[Placed[L]] | None:
    """Held: the line at `start` with its top at `offset`, newer ones below
    it to the bottom of the view. When the end fits, retain a sticky reading
    position while it still shows text. Otherwise follow the end."""
    shown: list[Placed[L]] = []
    y = offset
    index = start
    while index < len(lines) and y < view_height:
        line = lines[index]
        h = height(line)
        if y + h > 0:  # a line now wholly above the view (it shrank) is skipped
            shown.append(Placed(line, y))
        y += h + gap
        index += 1
    if index == len(lines) and y - gap <= view_height and not (sticky and shown):
        return None
    return shown
