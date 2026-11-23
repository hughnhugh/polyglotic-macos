"""Steady's two zones (polyglotic-hq 526, decision 0251; the user's words
on DECISIONS #230: the live reading lines below and the settled transcript
above).

A caption window in a paced mode shows its captions in two places:

- **the live zone** at the bottom: the captions still being read, run on
  as one paragraph (line by line, each line's translation under it), the
  last few lines of it - `LIVE_LINES_MONOLOGUE` while one speaker talks,
  `LIVE_LINES_CONVERSATION` when two have within `CONVERSATION_WITHIN_SEC`;
- **the settled transcript** above it: each caption set again, whole, once
  it has left the live zone.

**The handoff is by line** (526's DESIGN.md 8.1): a caption settles when
its last line has rolled out of the live zone - never while part of it is
still there, so no word leaves the middle of a line being read - or when
nothing new has come for `PAUSE_SEC`: then the zone empties and the next
caption starts a line of its own.

`Zones` keeps which captions have settled, where a new paragraph starts
and who spoke lately. Plain Python, no Qt, no caption text: line keys,
sources and times only.
"""

from collections.abc import Collection, Hashable, Iterable, Sequence

LIVE_LINES_MONOLOGUE = 3
LIVE_LINES_CONVERSATION = 2
CONVERSATION_WITHIN_SEC = 60.0
"""Two speakers within this long are a conversation: the live zone is a
line shorter, and each turn reaches the transcript sooner."""
PAUSE_SEC = 5.0
"""Nothing new for this long: what is in the live zone settles."""


def handed_off(
    captions: Sequence[tuple[int, int, bool]], lines: int, live_lines: int
) -> list[int]:
    """The handoff by line, as a rule (docs/rule-cases/playout.json): of
    the live paragraph's `captions` - each its key, the paragraph line its
    last word is on (from 0) and whether it is still being spoken - those
    that have left a zone of `live_lines` lines when the paragraph is
    `lines` long: every line of theirs is above the zone's top, and they
    are finished. The caption window's `ZoneCanvas.rolled_out` is this in
    pixels."""
    top = lines - live_lines
    return [key for key, last, live in captions if last < top and not live]


class Zones:
    """Which of a window's captions have settled (`settled`, by line key),
    the captions a new paragraph starts after (`ended`), and each
    speaker's last time (`spoke`)."""

    def __init__(self) -> None:
        self.settled: set[int] = set()
        self.ended: set[int] = set()
        self.spoke: dict[Hashable, float] = {}

    def heard(self, speaker: Hashable, at: float) -> None:
        """`speaker` (a source, and whether it is the user) had new text
        at `at`."""
        self.spoke[speaker] = at

    def live_lines(self, now: float) -> int:
        """How many lines the live zone shows at `now`."""
        lately = sum(
            1 for at in self.spoke.values() if now - at <= CONVERSATION_WITHIN_SEC
        )
        return LIVE_LINES_CONVERSATION if lately > 1 else LIVE_LINES_MONOLOGUE

    def settle(self, keys: Iterable[int]) -> bool:
        """The captions `keys` have left the live zone. True if any is new."""
        before = len(self.settled)
        self.settled.update(keys)
        return len(self.settled) != before

    def pause(self, keys: Collection[int]) -> bool:
        """Nothing new for `PAUSE_SEC`: the captions `keys` - all the
        window has - settle, and the next starts a paragraph. True if
        anything changed."""
        changed = self.settle(keys)
        if keys:
            last = max(keys)
            changed = changed or last not in self.ended
            self.ended.add(last)
        return changed

    def keep(self, keys: Collection[int]) -> None:
        """Only `keys` are still in the window: the rest are forgotten."""
        self.settled &= set(keys)
        self.ended &= set(keys)

    def clear(self) -> None:
        self.settled.clear()
        self.ended.clear()
        self.spoke.clear()
