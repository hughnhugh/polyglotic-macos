"""The whole language at a glance (polyglotic-hq 489, after 474's map; the
user, 2026-11-18: "the display should show your relative knowledge of
the language in relation to the entire language"; decision 0226).

- **The map:** the language's `MAP_WORDS` most common words (the words
  scale's order, `levels.place`), one square each, each coloured by how
  well the learner knows it (`known_chance`). A native speaker's is all
  green.
- **Progress, as the user defined it** ("least amount of words that are
  red ... most words green"): the count of red, between and green words
  (`Tally`), and the share of what's heard that is green - each word
  weighted by how often it is said, which falls as 1 / its place (Zipf's
  law: the 10th word is said about ten times as often as the 100th). The
  share is of the map's words, which carry nearly all of everyday speech.
- **This week** (`then`): the same counts a week ago, rebuilt from what
  the learning file keeps - the histories of statuses and of the known
  line (polyglotic-hq 477), the daily counts of the last 8 weeks and when
  each lookup and save was made:
  - a word's status then is its last change up to then; a word changed
    only since had none of its own (only the line's);
  - the line then is its last move up to then; none if it has only moved
    since (the starting line);
  - the days it was heard on then are today's less the days since then
    that have a daily count, `at`'s own day included (UTC days, and the
    whole of `at`'s: near enough);
  - a lookup or a save made since didn't happen yet; one made before is
    taken as it is now.

Plain rules, no storage: `Vocabulary.chances_as_of` gathers what they
need.
"""

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime

from polyglotic_desktop.core.learning.known_chance import (
    NO_EVIDENCE,
    Band,
    Chance,
    Evidence,
)
from polyglotic_desktop.core.learning.levels import KnownLine
from polyglotic_desktop.core.learning.statuses import StatusRecord, StatusSource
from polyglotic_desktop.core.shared import EntryId, WordStatus
from polyglotic_desktop.ports.learning import StoredLineChange, StoredStatusChange

MAP_WORDS = 20_000
"""The map's words: the 20,000 most common. About the vocabulary of an
educated native speaker, and nearly all of everyday speech (by Zipf's law
the 20,000th word is said about 20,000 times less often than the
first)."""


@dataclass(frozen=True, slots=True)
class Tally:
    """How much of the language is red, between and green: words, and the
    share of what's heard (weighted by 1 / place)."""

    unknown: int = 0
    partial: int = 0
    mastered: int = 0
    heard_unknown: float = 0.0
    heard_mastered: float = 0.0

    @property
    def words(self) -> int:
        return self.unknown + self.partial + self.mastered


def tally(chances: Iterable[tuple[int, Chance | None]]) -> Tally:
    """The tally of words, each with its place and how well it's known
    (None: a name or an ignored word, left out)."""
    counts = [0, 0, 0]
    weights = [0.0, 0.0, 0.0]
    for at, chance in chances:
        if chance is None:
            continue
        band = chance.band
        counts[band] += 1
        weights[band] += 1.0 / max(at, 1)
    total = sum(weights) or 1.0
    return Tally(
        counts[Band.UNKNOWN],
        counts[Band.PARTIAL],
        counts[Band.MASTERED],
        weights[Band.UNKNOWN] / total,
        weights[Band.MASTERED] / total,
    )


_SOURCES = {
    "learner": StatusSource.LEARNER,
    "server": StatusSource.LEARNER,  # the learner's, set on another PC
    "imported": StatusSource.IMPORTED,
    "estimated": StatusSource.ESTIMATED,
}


def statuses_then(
    now: Mapping[EntryId, StatusRecord],
    changes: Sequence[StoredStatusChange],
    at: datetime,
) -> Callable[[EntryId], StatusRecord | None]:
    """Each word's own status at `at`, from its status now and the history
    of changes (in order)."""
    then: dict[EntryId, StatusRecord | None] = {}
    for change in changes:
        entry_id = EntryId(change.entry_id)
        if change.at <= at:
            try:
                status = WordStatus(change.after)
            except ValueError:
                continue
            source = _SOURCES.get(change.source, StatusSource.LEARNER)
            then[entry_id] = StatusRecord(status, source, change.at)
        else:
            then.setdefault(entry_id, None)  # changed only since: none then

    def own(entry_id: EntryId) -> StatusRecord | None:
        if entry_id in then:
            return then[entry_id]
        return now.get(entry_id)

    return own


def line_then(
    now: KnownLine | None, changes: Sequence[StoredLineChange], at: datetime
) -> KnownLine | None:
    """The learner's line at `at`, from the line now and its moves."""
    before = [c for c in changes if c.at <= at]
    if before:
        last = before[-1]
        if last.scheme is None or last.midpoint is None:
            return None
        return KnownLine.stored(last.scheme, last.midpoint)
    return None if changes else now


def evidence_then(
    now: Callable[[EntryId], Evidence],
    heard_since: Mapping[EntryId, int],
    at: datetime,
    day: date,
) -> Callable[[EntryId], Evidence]:
    """What the learner had done with each word by `at` (the learner's
    `day`): `heard_since` is the days each was heard on since."""

    def then(entry_id: EntryId) -> Evidence:
        found = now(entry_id)
        if found is NO_EVIDENCE:
            return found
        days = max(0, found.days_heard - heard_since.get(entry_id, 0))
        last = found.last_heard
        if days == 0:
            last = None
        elif last is not None and last > day:
            last = day  # heard since too: on that day or before
        lookups = found.lookups
        if lookups is not None and (lookups.last is None or lookups.last > at):
            lookups = None
        saved = found.saved and (found.saved_at is None or found.saved_at <= at)
        return Evidence(days, last, lookups, saved, found.saved_at if saved else None)

    return then
