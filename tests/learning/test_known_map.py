"""The whole language at a glance (polyglotic-hq 489): the tally of red,
between and green words and the share of what's heard that's green, and
the same a week ago rebuilt from the learning file's histories. Made-up
words; the days are the learner's own (UTC here)."""

from datetime import UTC, date, datetime, timedelta

import pytest
from tests.learning.fakes import Clock, MemoryLearningStore, facts, words_of

from polyglotic_desktop.core.learning.known_chance import (
    NO_EVIDENCE,
    Band,
    Chance,
    Evidence,
    Start,
)
from polyglotic_desktop.core.learning.known_map import (
    MAP_WORDS,
    Tally,
    evidence_then,
    line_then,
    statuses_then,
    tally,
)
from polyglotic_desktop.core.learning.levels import KnownLine
from polyglotic_desktop.core.learning.lookups import LookupCount
from polyglotic_desktop.core.learning.statuses import StatusRecord, StatusSource
from polyglotic_desktop.core.learning.vocabulary import Vocabulary
from polyglotic_desktop.core.shared import EntryFacts, EntryId, WordStatus
from polyglotic_desktop.ports.learning import StoredLineChange, StoredStatusChange

T0 = datetime(2026, 11, 1, 9, 0, tzinfo=UTC)
WEEK = timedelta(days=7)


def chance(p: float) -> Chance:
    return Chance(p, Start.LINE)


def test_the_tally_counts_the_bands_and_weights_what_is_heard() -> None:
    found = tally([(1, chance(0.95)), (2, chance(0.5)), (10, chance(0.05)), (5, None)])
    assert (found.unknown, found.partial, found.mastered) == (1, 1, 1)
    assert found.words == 3  # a name or an ignored word: left out
    # by 1 / place: the 1st word is said ten times as often as the 10th
    total = 1 + 1 / 2 + 1 / 10
    assert found.heard_mastered == pytest.approx(1 / total)
    assert found.heard_unknown == pytest.approx((1 / 10) / total)
    assert tally([]) == Tally()


def test_the_map_is_the_20000_most_common_words() -> None:
    assert MAP_WORDS == 20_000


def test_a_status_then_is_its_last_change_up_to_then() -> None:
    a, b, c = EntryId("a"), EntryId("b"), EntryId("c")
    now = {
        a: StatusRecord(WordStatus.KNOWN, StatusSource.LEARNER, T0 + 3 * WEEK),
        b: StatusRecord(WordStatus.LEARNING, StatusSource.LEARNER, T0),
        c: StatusRecord(WordStatus.NEW, StatusSource.LEARNER, T0),
    }
    changes = [
        StoredStatusChange("a", "known", "new", "learner", T0),
        StoredStatusChange("a", "new", "known", "learner", T0 + 3 * WEEK),
        StoredStatusChange("b", "new", "learning", "server", T0 + 3 * WEEK),
    ]
    own = statuses_then(now, changes, T0 + WEEK)
    found_a = own(a)
    assert found_a is not None and found_a.status is WordStatus.NEW
    assert own(b) is None  # set only since: none of its own then
    assert own(c) == now[c]  # no history: as now
    from_server = statuses_then(now, changes, T0 + 4 * WEEK)(b)
    assert from_server is not None
    assert from_server.source is StatusSource.LEARNER  # set on another PC


def test_the_line_then_is_its_last_move_up_to_then() -> None:
    now = KnownLine.words(3000)
    moves = [
        StoredLineChange("words", 1000.0, "words", T0),
        StoredLineChange("words", 3000.0, "words", T0 + 2 * WEEK),
    ]
    assert line_then(now, moves, T0 + WEEK) == KnownLine.words(1000)
    assert line_then(now, moves, T0 - WEEK) is None  # moved only since
    assert line_then(now, [], T0) == now
    cleared = [*moves, StoredLineChange(None, None, "restored", T0 + 3 * WEEK)]
    assert line_then(None, cleared, T0 + 4 * WEEK) is None


def test_evidence_then_takes_back_what_came_since() -> None:
    word = EntryId("w")
    at = T0 + WEEK
    now = Evidence(
        days_heard=5,
        last_heard=(at + timedelta(days=3)).date(),
        lookups=LookupCount(pinned=1, last=at + timedelta(days=1)),
        saved=True,
        saved_at=at + timedelta(days=2),
    )
    then = evidence_then(lambda _: now, {word: 2}, at, at.date())(word)
    assert then == Evidence(3, at.date(), None, False, None)
    old = Evidence(2, date(2026, 10, 1), LookupCount(1, 0, T0), True, T0)
    assert evidence_then(lambda _: old, {}, at, at.date())(word) == old
    assert evidence_then(lambda _: NO_EVIDENCE, {}, at, at.date())(word) is NO_EVIDENCE
    heard_only_since = Evidence(1, (at + timedelta(days=1)).date())
    assert evidence_then(lambda _: heard_only_since, {word: 1}, at, at.date())(
        word
    ) == Evidence(0, None)


ENTRIES = {
    "common": facts("common", level=None, rank=50),
    "middle": facts("middle", level=None, rank=1500),
    "rare": facts("rare", level=None, rank=30000),
}
BY_ID = {f.entry_id: f for f in ENTRIES.values()}


def lookup(entry_id: EntryId, scheme: str) -> EntryFacts | None:
    return BY_ID.get(entry_id)


def test_a_week_ago_is_rebuilt_from_the_learning_file() -> None:
    """A learner who set 1,000 words a fortnight ago, then this week said
    they know "rare", heard "middle" on three days and raised the line to
    2,000: a week ago "rare" was red and "middle" just past the line; now
    both have moved - and the map's week-ago tally says where from."""
    clock = Clock(T0)
    store = MemoryLearningStore()
    vocab = Vocabulary(store, lookup, "hsk-2025", clock, day_of=lambda at: at.date())
    vocab.set_known_words(1000)
    clock.advance(days=8)
    week_ago = clock.now - timedelta(hours=1)
    vocab.set_status(ENTRIES["rare"].entry_id, WordStatus.KNOWN)
    for n in range(3):
        vocab.caption_finished(f"c{n}", words_of("middle", ENTRIES), by_you=False)
        clock.advance(days=1)
    vocab.set_known_words(2000)

    then = vocab.chances_as_of(week_ago)
    now = vocab.chances
    rare_then, rare_now = then.of(ENTRIES["rare"]), now.of(ENTRIES["rare"])
    assert rare_then is not None and rare_now is not None
    assert (rare_then.band, rare_now.band) == (Band.UNKNOWN, Band.MASTERED)
    middle_then, middle_now = then.of(ENTRIES["middle"]), now.of(ENTRIES["middle"])
    assert middle_then is not None and middle_now is not None
    assert middle_then.days_heard == 0 and middle_now.days_heard == 3
    assert middle_then.chance < 0.5 < middle_now.chance
    assert then.knowledge.known_words == 1000
    words = list(ENTRIES.values())
    tally_then = tally(zip([50, 1500, 30000], then.each(words), strict=True))
    tally_now = tally(zip([50, 1500, 30000], now.each(words), strict=True))
    assert tally_then.mastered < tally_now.mastered
    assert tally_then.unknown > tally_now.unknown
