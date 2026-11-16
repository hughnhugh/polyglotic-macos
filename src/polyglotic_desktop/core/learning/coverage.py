"""Coverage: how much of what the learner heard they knew.

Coverage is the share of a period's tokens - each dictionary word in a
finished caption, every time it comes up - whose entry the learner knew
when the caption finished (glossary: coverage). Names count as known, as
the research counts proper nouns (Webb and Rodgers 2009), and so do words
the learner said to ignore. Captions from the user's own mic don't count:
coverage is about what they heard. Words the dictionary hasn't got
(Latin letters in a Chinese line, digits) aren't tokens.

What it means, and what not (polyglotic-hq project 155, section 3.3):
95 % is where research on listening puts "can follow, with effort" (van
Zeeland and Schmitt 2013) and 98 % "comfortable, guess the rest" (Hu and
Nation 2000). Those are reference lines, not a measure of understanding:
the app never calls coverage comprehension. Under `MIN_TOKENS` a period
has no coverage - one short session would swing it.

Counted per UTC day, like exposures, once per caption: a join finishing
a caption again replaces what it counted, and a withdrawn caption takes
it back (`CoverageCounter`, as `exposures.ExposureCounter` does). The
daily counts stay on this PC; they're never sent (the server has its own
minutes, and coverage is the learner's).
"""

from collections import OrderedDict
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date

from polyglotic_desktop.core.learning.exposures import RECENT_CAPTIONS
from polyglotic_desktop.core.shared import EntryFacts, WordInLine, WordStatus

MIN_TOKENS = 200
"""A period with fewer tokens has no coverage (155: one short session
swings it)."""

RECENT_DAYS = 7
"""Words shows the coverage of the last this many days, today included."""

CAN_FOLLOW = 0.95
"""The reference line "can follow, with effort" (van Zeeland and Schmitt
2013, listening)."""

COMFORTABLE = 0.98
"""The reference line "comfortable, guess the rest" (Hu and Nation 2000)."""


@dataclass(frozen=True)
class Coverage:
    """A period's tokens, and how many were known, in the deck and new as
    their captions finished. `tokens` is their sum (`known + deck + new`)."""

    known: int = 0
    deck: int = 0
    new: int = 0

    @property
    def tokens(self) -> int:
        return self.known + self.deck + self.new

    def __add__(self, other: "Coverage") -> "Coverage":
        return Coverage(
            self.known + other.known, self.deck + other.deck, self.new + other.new
        )

    def __neg__(self) -> "Coverage":
        return Coverage(-self.known, -self.deck, -self.new)

    @property
    def share(self) -> float | None:
        """Known tokens over all tokens - None under `MIN_TOKENS`."""
        if self.tokens < MIN_TOKENS:
            return None
        return self.known / self.tokens

    @property
    def one_new_in(self) -> int | None:
        """N in "1 word in N was new" - the tokens not known (new or in the
        deck), as one in so many; None under `MIN_TOKENS` or when every
        token was known."""
        unknown = self.deck + self.new
        if self.tokens < MIN_TOKENS or unknown <= 0:
            return None
        return round(self.tokens / unknown)


def coverage_of(
    words: Iterable[WordInLine], status: Callable[[EntryFacts], WordStatus]
) -> Coverage:
    """The tokens of a finished caption's words, by their `status` now -
    names known whatever their status."""
    known = deck = new = 0
    for word in words:
        state = WordStatus.KNOWN if word.entry.is_name else status(word.entry)
        if state is WordStatus.LEARNING:
            deck += 1
        elif state is WordStatus.NEW:
            new += 1
        else:  # known, or ignored
            known += 1
    return Coverage(known, deck, new)


@dataclass(frozen=True)
class _Counted:
    coverage: Coverage
    day: date


class CoverageCounter:
    """Turns finished and withdrawn captions into changes in the days'
    coverage, once per caption."""

    def __init__(self) -> None:
        self._recent: OrderedDict[str, _Counted] = OrderedDict()

    def finished(
        self, caption_id: str, coverage: Coverage, day: date
    ) -> dict[date, Coverage]:
        """A finished caption (or one finished again by a join), counted on
        `day`: the change to each day - what it counted before taken back,
        what it counts now added."""
        before = self._recent.pop(caption_id, None)
        self._recent[caption_id] = _Counted(coverage, day)
        while len(self._recent) > RECENT_CAPTIONS:
            self._recent.popitem(last=False)
        return _changes(before, _Counted(coverage, day))

    def withdrawn(self, caption_id: str) -> dict[date, Coverage]:
        """A caption taken back: whatever it counted is taken back too."""
        return _changes(self._recent.pop(caption_id, None), None)


def _changes(before: _Counted | None, after: _Counted | None) -> dict[date, Coverage]:
    changes: dict[date, Coverage] = {}
    if before is not None:
        changes[before.day] = -before.coverage
    if after is not None:
        changes[after.day] = changes.get(after.day, Coverage()) + after.coverage
    return {day: c for day, c in changes.items() if c != Coverage()}
