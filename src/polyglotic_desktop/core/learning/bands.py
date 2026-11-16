"""Bands: the words the learner has met, by how common they are or by
level, and where they stand in each (glossary: band; polyglotic-hq
project 155, section 5.2, mock 2).

A band is a run of frequency ranks (the top 1,000, 1,001-2,000, 2,001-
5,000, 5,001-10,000) or one level of the learner's level scheme (HSK 1
to 7-9). Each counts its words met - heard in at least one finished
caption from what the PC played, names left out - as known (or ignored),
in the deck, or new, by their status now; the rest of the band's words
are not heard yet. A word met but ranked past the last band, or with no
rank, is "rarer".

Frequency bands count written forms: entries that share a written form
share its rank (还 hái and huán), so a rank is one word, with the best
status among its met entries. Level bands count entries. Each band's
size is the dictionary's (Lexicon's), handed in.
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from polyglotic_desktop.core.shared import EntryFacts, WordStatus

FREQUENCY_BANDS: tuple[tuple[int, int], ...] = (
    (1, 1000),
    (1001, 2000),
    (2001, 5000),
    (5001, 10000),
)
"""The runs of frequency ranks Words shows (155's mock 2), commonest first."""

MetWord = tuple[EntryFacts, WordStatus]
"""A word the learner has met, and its status now."""

_BEST = {
    WordStatus.KNOWN: 3,
    WordStatus.IGNORED: 3,
    WordStatus.LEARNING: 2,
    WordStatus.NEW: 1,
}


@dataclass(frozen=True)
class Band:
    """A band's words met, by status, and its size (None: no size - the
    rarer words)."""

    known: int = 0
    deck: int = 0
    new: int = 0
    size: int | None = None

    @property
    def met(self) -> int:
        return self.known + self.deck + self.new

    @property
    def not_heard(self) -> int:
        """The band's words not heard yet (0 for one without a size)."""
        return max(0, (self.size or 0) - self.met)


def _band(statuses: Iterable[WordStatus], size: int | None) -> Band:
    known = deck = new = 0
    for status in statuses:
        if status is WordStatus.LEARNING:
            deck += 1
        elif status is WordStatus.NEW:
            new += 1
        else:
            known += 1
    return Band(known, deck, new, size)


def by_frequency(
    met: Iterable[MetWord], sizes: Sequence[int]
) -> tuple[list[Band], Band]:
    """The `FREQUENCY_BANDS`, each with its size from `sizes` (in the same
    order), and the rarer words met."""
    best: dict[int, WordStatus] = {}
    rarer: list[WordStatus] = []
    last = FREQUENCY_BANDS[-1][1]
    for facts, status in met:
        rank = facts.frequency_rank
        if rank is None or rank > last:
            rarer.append(status)
        elif rank not in best or _BEST[status] > _BEST[best[rank]]:
            best[rank] = status
    bands = [
        _band((s for r, s in best.items() if first <= r <= end), size)
        for (first, end), size in zip(FREQUENCY_BANDS, sizes, strict=True)
    ]
    return bands, _band(rarer, None)


def by_level(met: Iterable[MetWord], sizes: Mapping[int, int]) -> dict[int, Band]:
    """Each level of `sizes` (level -> its words), lowest first, with the
    words met at it."""
    statuses: dict[int, list[WordStatus]] = {level: [] for level in sizes}
    for facts, status in met:
        if facts.level in statuses:
            statuses[facts.level].append(status)
    return {level: _band(statuses[level], sizes[level]) for level in sorted(statuses)}
