"""The level as a known line with its learning window, and statuses
estimated from it (polyglotic-hq 323; before it, project 019's curve)."""

import math

import pytest
from tests.learning.fakes import facts

from polyglotic_desktop.core.learning.levels import (
    DEFAULT_WINDOW,
    MAX_WINDOW,
    MIN_WINDOW,
    UNLIMITED,
    WINDOW_SIZES,
    WORDS,
    KnownLine,
    LanguageChoices,
    place,
    window_size,
)
from polyglotic_desktop.core.learning.statuses import (
    StatusRecord,
    StatusSource,
    estimated_status,
    status_of,
)
from polyglotic_desktop.core.shared import Level, WordStatus


def test_a_picked_level_counts_words_at_or_below_it_as_known() -> None:
    line = KnownLine.picked(Level("hsk-2025", 4))
    assert line == KnownLine("hsk-2025", 4) and line.by_level
    assert [line.knows(facts("w", level=level)) for level in range(1, 8)] == [
        True, True, True, True, False, False, False,
    ]  # fmt: skip
    assert not line.knows(facts("w", level=None))  # not on the HSK lists


def test_just_starting_knows_nothing_yet() -> None:
    line = KnownLine.picked(Level("hsk-2025", 0))
    assert line.known == 0
    assert not line.knows(facts("w", level=1))
    assert not KnownLine.words(0).knows(facts("w", level=None, rank=1))


def test_a_levels_window_is_the_next_level_whatever_its_size() -> None:
    line = KnownLine.picked(Level("hsk-2025", 2))
    for size in (None, 100, 2000):
        window = line.window(size)
        assert [
            window.reaches(facts("w", level=level)) for level in (1, 2, 3, 4, None)
        ] == [True, True, True, False, False]
        assert [
            window.holds(facts("w", level=level)) for level in (1, 2, 3, 4, None)
        ] == [False, False, True, False, False]


def _as_the_curve_did(midpoint: float, level: int | None) -> tuple[bool, bool]:
    """Known and within reach as the level curve gave them before 323
    (slope 2, known from a chance of 0.6, reach one level past the
    midpoint) - written out here, the curve being gone."""
    if level is None:
        return False, False
    chance = 1.0 / (1.0 + math.exp(2.0 * (level - midpoint)))
    return chance >= 0.6, level <= midpoint + 1.0


@pytest.mark.parametrize("scheme", ["hsk-2025", "hsk-2021", "en-frequency"])
@pytest.mark.parametrize("picked", range(8))
def test_a_level_kept_before_323_reads_as_it_always_did(
    scheme: str, picked: int
) -> None:
    """Every level a learner has stored - a scheme and the midpoint half a
    level above the level picked - gives each word what the curve gave
    it: nothing they see changes until they change their level."""
    stored = picked + 0.5
    line = KnownLine.stored(scheme, stored)
    assert line == KnownLine.picked(Level(scheme, picked))
    assert line.midpoint == stored  # and is kept as it was
    for level in [*range(1, 9), None]:
        word = facts("w", level=level, rank=5, level_words=1)  # by level alone
        known, within_reach = _as_the_curve_did(stored, level)
        assert line.knows(word) is known
        assert line.window().reaches(word) is within_reach


def test_a_line_in_words_knows_the_most_common_words() -> None:
    line = KnownLine.words(3000)
    assert line == KnownLine(WORDS, 3000) and not line.by_level
    assert line.knows(facts("w", level=None, rank=3000))
    assert not line.knows(facts("w", level=None, rank=3001))
    assert not line.knows(facts("w", level=None, rank=None))
    window = line.window()
    assert window.size == DEFAULT_WINDOW in WINDOW_SIZES and window.last == 4000
    assert window.holds(facts("w", level=None, rank=3001))
    assert window.holds(facts("w", level=None, rank=4000))
    assert not window.holds(facts("w", level=None, rank=4001))  # rarer
    assert not window.holds(facts("w", level=None, rank=3000))  # known
    assert window.reaches(facts("w", level=None, rank=10))
    assert line.window(500).last == 3500
    # kept as the store's two values, and read back
    assert (line.scale, line.midpoint) == ("words", 3000.0)
    assert KnownLine.stored("words", 3000.0) == line


def test_an_unlimited_window_holds_every_word_past_the_line() -> None:
    """Decision 0144: no end - the rarest ranked word, and a word with no
    place at all, are in it; a known one still isn't."""
    line = KnownLine.words(3000)
    window = line.window(UNLIMITED)
    assert window.size is UNLIMITED and window.last is None
    for rank in (3001, 4001, 50_000, 87_125, None):
        assert window.reaches(facts("w", level=None, rank=rank))
        assert window.holds(facts("w", level=None, rank=rank))
    assert window.reaches(facts("w", level=None, rank=3000))
    assert not window.holds(facts("w", level=None, rank=3000))  # known


def test_a_window_of_the_learners_own_size_ends_where_they_said() -> None:
    line = KnownLine.words(3000)
    window = line.window(3000)
    assert window.last == 6000
    assert window.holds(facts("w", level=None, rank=6000))
    assert not window.holds(facts("w", level=None, rank=6001))  # rarer


def test_past_a_level_unlimited_is_every_level_above_and_a_number_the_next() -> None:
    """A line kept as a level (HSK): any number - one of the sizes or the
    learner's own - is the next level, as before; unlimited is every level
    above it, and words the scheme leaves out."""
    line = KnownLine.picked(Level("hsk-2025", 2))
    custom = line.window(3000)
    assert [custom.holds(facts("w", level=lv)) for lv in (2, 3, 4, None)] == [
        False,
        True,
        False,
        False,
    ]
    unlimited = line.window(UNLIMITED)
    assert [unlimited.holds(facts("w", level=lv)) for lv in (2, 3, 4, 7, None)] == [
        False,
        True,
        True,
        True,
        True,
    ]


def test_a_number_of_the_learners_own_is_kept_within_its_bounds() -> None:
    assert window_size(3000) == 3000
    assert window_size(MIN_WINDOW - 1) == MIN_WINDOW
    assert window_size(MAX_WINDOW + 1) == MAX_WINDOW
    assert (MIN_WINDOW, MAX_WINDOW) == (10, 100_000)


def test_unlimited_and_custom_are_stored_so_an_older_app_reads_its_default() -> None:
    unlimited = LanguageChoices(window_size=UNLIMITED)
    assert unlimited.to_stored() == {"window": "unlimited"}
    assert LanguageChoices.from_stored(unlimited.to_stored()) == unlimited
    custom = LanguageChoices(window_size=3000)
    assert LanguageChoices.from_stored(custom.to_stored()) == custom
    # out of bounds (a hand-edited file): kept within them
    assert LanguageChoices.from_stored({"window": 1}).window_size == MIN_WINDOW
    assert LanguageChoices.from_stored({"window": 10**9}).window_size == MAX_WINDOW
    # what a version before 0144 does with "unlimited": its reading of a
    # window was a whole number of words or nothing chosen - so its default
    assert _as_before_0144({"window": "unlimited"}) is None
    assert _as_before_0144({"window": 3000}) == 3000


def _as_before_0144(stored: dict[str, object]) -> int | None:
    """The window as `LanguageChoices.from_stored` read it before 0144
    (`_count`), written out here: an int of 0 or more, else None."""
    value = stored.get("window")
    valid = isinstance(value, int) and not isinstance(value, bool) and value >= 0
    return value if valid and isinstance(value, int) else None


def test_a_words_place_is_the_better_of_its_rank_and_its_levels_vocabulary() -> None:
    assert place(facts("w", level=None, rank=250)) == 250
    assert place(facts("w", level=1, rank=6361, level_words=300)) == 300
    assert place(facts("w", level=4, rank=40, level_words=2000)) == 40
    assert place(facts("w", level=7, rank=None, level_words=11000)) == 11000
    assert place(facts("w", level=None, rank=None)) is None


def test_default_statuses_are_computed_from_the_line() -> None:
    line = KnownLine.picked(Level("hsk-2025", 3))
    assert estimated_status(facts("easy", level=2), line) is WordStatus.KNOWN
    assert estimated_status(facts("hard", level=5), line) is WordStatus.NEW
    assert estimated_status(facts("off-list", level=None), line) is WordStatus.NEW
    assert estimated_status(facts("Beijing", is_name=True), line) is WordStatus.IGNORED
    # with no line, everything is new
    assert estimated_status(facts("easy", level=1), None) is WordStatus.NEW
    words = KnownLine.words(1000)
    assert estimated_status(facts("a", level=None, rank=900), words) is WordStatus.KNOWN
    assert estimated_status(facts("b", level=None, rank=1100), words) is WordStatus.NEW


def test_an_explicit_status_wins_over_the_estimate() -> None:
    line = KnownLine.picked(Level("hsk-2025", 6))
    easy = facts("easy", level=1)
    explicit = StatusRecord(WordStatus.LEARNING, StatusSource.LEARNER)
    assert status_of(easy, explicit, line) is explicit
    estimated = status_of(easy, None, line)
    assert estimated == StatusRecord(WordStatus.KNOWN, StatusSource.ESTIMATED)
    assert not estimated.is_learners_own and explicit.is_learners_own
    # the same on a line in words: a common word the learner put in the deck
    assert status_of(facts("a", rank=5), explicit, KnownLine.words(3000)) is explicit
