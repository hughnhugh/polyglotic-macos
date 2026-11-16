"""What the learner knows, as one answer per word (polyglotic-hq 349's
design, built by 373): each kind of evidence, which one wins, how sure the
answer is, the line read as a rank - and that word links answer exactly as
they did before it (no change a learner sees, DECISIONS #176 (a)).
Made-up words."""

import itertools
from datetime import UTC, datetime

import pytest
from tests.learning.fakes import facts

from polyglotic_desktop.core.learning.knowledge import (
    Confidence,
    Knowledge,
    Knows,
    Reason,
)
from polyglotic_desktop.core.learning.levels import KnownLine, placed_within
from polyglotic_desktop.core.learning.statuses import StatusRecord, StatusSource
from polyglotic_desktop.core.shared import EntryFacts, EntryId, Level, WordStatus

AT = datetime(2026, 11, 16, tzinfo=UTC)
COMMON = facts("的", level=1, rank=1, level_words=300)
MIDDLE = facts("旅游", level=2, rank=468, level_words=500)
RARE = facts("榴莲", level=None, rank=30000)
OUT_OF_SYLLABUS = facts("与", level=4, rank=27, level_words=2000)
UNPLACED = facts("中的", level=None, rank=None)
PART = facts("中", level=1, rank=14, level_words=300)
NAME = facts("张伟", level=None, rank=None, is_name=True)
TWENTY = EntryFacts(EntryId("test:二十"), None, None, False, None, is_number=True)


def hsk_words(scheme: str, level: int) -> int | None:
    if scheme != "hsk-2025":
        return None  # as HSK 3.0's 2021 standard: no number of words
    return (0, 300, 500, 1000, 2000, 3600, 5400, 11000)[level]


class Learner:
    """A `Knowledge` over statuses and a line a test sets."""

    def __init__(self) -> None:
        self.own: dict[EntryId, StatusRecord] = {}
        self.line: KnownLine | None = None
        self.bases: dict[EntryId, list[EntryFacts]] = {}
        self.knowledge = Knowledge(
            self.own.get,
            lambda: self.line,
            KnownLine.starting("hsk-2025"),
            hsk_words,
            lambda word: self.bases.get(word.entry_id, ()),
        )

    def says(
        self,
        word: EntryFacts,
        status: WordStatus,
        source: StatusSource = StatusSource.LEARNER,
    ) -> None:
        self.own[word.entry_id] = StatusRecord(status, source, AT)

    def of(self, word: EntryFacts, as_if_knowing: int | None = None) -> Knows:
        return self.knowledge.of(word, as_if_knowing)


def test_until_the_learner_says_anything_every_answer_is_a_guess() -> None:
    """The starting line (HSK 3, about 1,000 words) is the app's own
    assumption, and the answer says so."""
    learner = Learner()
    assert learner.of(COMMON) == Knows(
        WordStatus.KNOWN, Confidence.GUESS, Reason.STARTING_LINE
    )
    assert learner.of(RARE) == Knows(WordStatus.NEW, Confidence.GUESS, Reason.PAST_LINE)
    assert learner.of(NAME) == Knows(
        WordStatus.NEW, Confidence.GUESS, Reason.NOT_PLACED
    )


def test_the_line_is_one_number_of_words() -> None:
    """No levels (the user, DECISIONS #176 (b)): the line is "I know about
    N words", and a level kept from before reads as its number."""
    learner = Learner()
    assert learner.knowledge.known_words == 1000  # HSK 3, the starting line
    assert not learner.knowledge.line_set
    learner.line = KnownLine.words(2500)
    assert learner.knowledge.known_words == 2500
    assert learner.knowledge.line_set
    learner.line = KnownLine.picked(Level("hsk-2025", 5))
    assert learner.knowledge.known_words == 3600
    learner.line = KnownLine.picked(Level("hsk-2021", 5))
    assert learner.knowledge.known_words is None  # the scheme says no number


def test_the_line_the_learner_set_answers_as_likely() -> None:
    learner = Learner()
    learner.line = KnownLine.words(1000)
    assert learner.of(MIDDLE) == Knows(WordStatus.KNOWN, Confidence.LIKELY, Reason.LINE)
    assert learner.of(RARE) == Knows(
        WordStatus.NEW, Confidence.LIKELY, Reason.PAST_LINE
    )
    learner.line = KnownLine.words(300)
    assert not learner.of(MIDDLE).known


def test_a_level_kept_from_before_is_read_as_its_number_of_words() -> None:
    """与 is HSK 4 and the 27th commonest word: a learner of HSK 3 (about
    1,000 words) knows it by its rank; 旅游 by its level."""
    learner = Learner()
    learner.line = KnownLine.picked(Level("hsk-2025", 3))
    assert learner.of(OUT_OF_SYLLABUS).known
    assert learner.of(MIDDLE).known
    assert not learner.of(RARE).known


def test_a_level_in_a_scheme_that_says_no_number_is_read_by_level() -> None:
    learner = Learner()
    learner.line = KnownLine.picked(Level("hsk-2021", 3))
    assert learner.of(MIDDLE).known  # level 2
    assert not learner.of(OUT_OF_SYLLABUS).known  # level 4, as before 323


def test_what_the_learner_said_about_a_word_wins_and_is_sure() -> None:
    learner = Learner()
    learner.line = KnownLine.words(1000)
    learner.says(MIDDLE, WordStatus.NEW)  # "new again"
    learner.says(RARE, WordStatus.KNOWN)
    learner.says(NAME, WordStatus.IGNORED)
    assert learner.of(MIDDLE) == Knows(WordStatus.NEW, Confidence.SURE, Reason.SAID)
    assert learner.of(RARE) == Knows(WordStatus.KNOWN, Confidence.SURE, Reason.SAID)
    assert learner.of(NAME).known  # ignored: not pointed out either
    # wherever the line is asked to be ("Start links at")
    assert not learner.of(MIDDLE, 5000).known and learner.of(RARE, 500).known


def test_an_import_is_likely_and_a_lookup_says_not_known() -> None:
    learner = Learner()
    learner.line = KnownLine.words(1000)
    learner.says(RARE, WordStatus.KNOWN, StatusSource.IMPORTED)
    assert learner.of(RARE) == Knows(
        WordStatus.KNOWN, Confidence.LIKELY, Reason.IMPORTED
    )
    # a pinned lookup of a word only assumed known (`Vocabulary.looked_up`)
    learner.says(MIDDLE, WordStatus.NEW, StatusSource.ESTIMATED)
    assert learner.of(MIDDLE) == Knows(
        WordStatus.NEW, Confidence.LIKELY, Reason.LOOKED_UP
    )


def test_a_number_in_numerals_is_known_unless_the_learner_said_otherwise() -> None:
    learner = Learner()
    assert learner.of(TWENTY) == Knows(
        WordStatus.KNOWN, Confidence.LIKELY, Reason.NUMBER
    )
    learner.says(TWENTY, WordStatus.NEW)
    assert not learner.of(TWENTY).known


def test_start_links_at_asks_as_if_the_line_were_elsewhere() -> None:
    learner = Learner()
    learner.line = KnownLine.words(3000)
    assert learner.of(MIDDLE).known and not learner.of(MIDDLE, 300).known
    assert learner.of(RARE, 50000) == Knows(
        WordStatus.KNOWN, Confidence.LIKELY, Reason.LINE
    )


def test_a_form_nothing_places_is_judged_by_the_words_it_is_made_of() -> None:
    """中的 is in the dictionary only as "to hit the target", unranked; in a
    caption it is 中 and 的, and was linked at every line (346's runs)."""
    learner = Learner()
    learner.line = KnownLine.words(1000)
    assert not learner.of(UNPLACED).known  # nothing says what it is made of
    learner.bases[UNPLACED.entry_id] = [PART, COMMON]
    assert learner.of(UNPLACED) == Knows(
        WordStatus.KNOWN, Confidence.GUESS, Reason.PARTS
    )
    learner.line = KnownLine.words(10)  # 中 is the 14th
    assert learner.of(UNPLACED) == Knows(WordStatus.NEW, Confidence.GUESS, Reason.PARTS)
    learner.says(PART, WordStatus.KNOWN)  # the learner's own word for a part
    assert learner.of(UNPLACED).known
    learner.says(UNPLACED, WordStatus.NEW)  # and for the form itself: it wins
    assert learner.of(UNPLACED) == Knows(WordStatus.NEW, Confidence.SURE, Reason.SAID)
    # a part nothing places leaves the form unplaced
    learner.bases[NAME.entry_id] = [COMMON, facts("伟", level=None, rank=None)]
    assert learner.of(NAME).reason is Reason.NOT_PLACED


def test_a_language_with_ranks_alone_answers_by_a_line() -> None:
    """A basic dictionary's language keeps no learning data (decision
    0035): the same question, with a line and nothing else."""
    russian = Knowledge.by_line(1000)
    common, rarer = facts("и", None, 1), facts("природа", None, 1800)
    assert russian.of(common) == Knows(
        WordStatus.KNOWN, Confidence.GUESS, Reason.STARTING_LINE
    )
    assert not russian.of(rarer).known
    assert russian.of(rarer, 2000) == Knows(
        WordStatus.KNOWN, Confidence.LIKELY, Reason.LINE
    )
    assert russian.known_words == 1000


# -- word links answer as they did before (no change a learner sees) ----------


def links_before(
    word: EntryFacts,
    own: StatusRecord | None,
    line: KnownLine,
    links_from: int | None,
) -> bool:
    """`Vocabulary.needs_no_link` as it was on main at ce9a8fb3 (2026-11-16),
    before it asked `Knowledge`."""
    if own is not None:
        return own.status in (WordStatus.KNOWN, WordStatus.IGNORED)
    if word.is_number:
        return True
    if links_from is None:
        if line.knows(word):
            return True
        links_from = line.words_known(hsk_words)
        if links_from is None:
            return False
    return placed_within(word, links_from)


WORDS = [
    facts(f"w{n}", level=level, rank=rank, is_name=name, level_words=size)
    for n, (level, rank, name, size) in enumerate(
        itertools.product(
            (None, 1, 3, 4, 7),
            (None, 1, 27, 999, 1000, 1001, 3000, 30000),
            (False, True),
            (None, 300, 1000, 2000),
        )
    )
] + [TWENTY]
LINES = [
    None,
    KnownLine.words(0),
    KnownLine.words(1000),
    KnownLine.words(5000),
    KnownLine.picked(Level("hsk-2025", 0)),
    KnownLine.picked(Level("hsk-2025", 3)),
    KnownLine.picked(Level("hsk-2025", 7)),
    KnownLine.picked(Level("hsk-2021", 3)),
]
OWN = [
    None,
    StatusRecord(WordStatus.KNOWN, StatusSource.LEARNER, AT),
    StatusRecord(WordStatus.NEW, StatusSource.ESTIMATED, AT),
    StatusRecord(WordStatus.LEARNING, StatusSource.LEARNER, AT),
    StatusRecord(WordStatus.IGNORED, StatusSource.LEARNER, AT),
]


@pytest.mark.parametrize("line", LINES, ids=str)
def test_links_answer_as_before_for_every_kind_of_word_and_line(
    line: KnownLine | None,
) -> None:
    learner = Learner()
    learner.line = line
    estimating = line or KnownLine.starting("hsk-2025")
    differ = []
    for word, own, links_from in itertools.product(WORDS, OWN, (None, 500, 1000, 8000)):
        learner.own.clear()
        if own is not None:
            learner.own[word.entry_id] = own
        before = links_before(word, own, estimating, links_from)
        if learner.of(word, links_from).known != before:
            differ.append((word, own, links_from))
    assert differ == []
