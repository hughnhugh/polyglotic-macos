"""What Learning's map shows (polyglotic-hq 489; `core.learning.known_map`):
the language's most common words in order, each one square in the colour
of how well the learner knows it, with the counts of red, between and
green, the share of what's heard that's green, and how both moved in the
last week. Plain Python, no Qt: `known_map_card` draws it.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from polyglotic_desktop.core.learning.known_chance import Chance, KnownChances
from polyglotic_desktop.core.learning.known_map import Tally, tally
from polyglotic_desktop.core.shared import EntryFacts, EntryId
from polyglotic_desktop.ui_next.views.lab import Palette

ROW = 200
"""Squares in a row of the map: 20,000 words make 100 rows."""

WEEK = timedelta(days=7)


@dataclass(frozen=True)
class KnownMapView:
    """The map as it is now: each word's place, entry and how well it is
    known (None: a name or an ignored word, drawn neutral), the tallies
    now and a week ago, the learner's line (None: assumed, not set), and
    the palette Learning load's colours use."""

    language: str
    places: Sequence[int]
    entries: Sequence[EntryId]
    chances: Sequence[Chance | None]
    now: Tally
    week_ago: Tally
    line: int | None
    line_set: bool
    palette: Palette = Palette.RED_GREEN

    @property
    def rows(self) -> int:
        return -(-len(self.places) // ROW)

    def at(self, index: int) -> tuple[int, EntryId, Chance | None] | None:
        """The word of square `index` (its place, entry and chance)."""
        if 0 <= index < len(self.places):
            return self.places[index], self.entries[index], self.chances[index]
        return None


def known_map_view(
    language: str,
    words: Sequence[tuple[int, EntryFacts]],
    chances: KnownChances,
    week_ago: Callable[[datetime], KnownChances],
    now: datetime,
    palette: Palette = Palette.RED_GREEN,
) -> KnownMapView:
    """The map of `words` (place and facts, in order) for a learner whose
    chances are `chances` now and `week_ago(at)` a week before `now`."""
    places = [at for at, _ in words]
    facts = [f for _, f in words]
    found = chances.each(facts)
    then = week_ago(now - WEEK).each(facts)
    return KnownMapView(
        language,
        places,
        [f.entry_id for f in facts],
        found,
        tally(zip(places, found, strict=True)),
        tally(zip(places, then, strict=True)),
        chances.knowledge.known_words,
        chances.knowledge.line_set,
        palette,
    )
