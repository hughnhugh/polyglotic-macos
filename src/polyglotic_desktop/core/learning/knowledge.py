"""What the learner knows in one language: one answer per word, with how
sure it is and why (polyglotic-hq 349's design, built by 373; the user,
DECISIONS #170 and #176, 2026-11-16).

Every feature asks one question, `Knowledge.of(word)`, and reads the
answer (`Knows`): the word's status (new, learning, known, ignored - the
glossary's, unchanged), a confidence, and the reason. What a feature then
does with a known word is its own business - a link hides, a mark isn't
drawn, coverage counts it - but none of them works the answer out again.

**The line is a frequency rank** (the user, #176: "we don't really need
levels for any languages, can just use word frequency ranking"): "I know
about N words" (`known_words`), one number per language, so it can follow
the learner to another PC later. A word is within it when its place
(`levels.place`) is no further than N. A line kept as a level from before
- the level picker's HSK 3, or the starting line - is read as the number
of words its level stands for (HSK 3: about 1,000); only a scheme that
says no number (HSK 3.0's 2021 standard) is still read by level.

**The evidence, strongest first.** The first kind that says anything
about the word answers:

1. **What the learner said about this word** - known, new again, in the
   deck, ignored; a graduation from the learning load is the learner's
   "I know this". Sure.
2. **What another tool said** (an import: Anki, later). Likely.
3. **What they looked up**: pinned lookups of a word only assumed known,
   two of them (`lookups.TURNS_NEW_AFTER`; one click alone isn't, nor
   any number for a word in the first half of the line, polyglotic-hq
   397), say they don't know it (kept as a status "new" whose source is
   "estimated", `Vocabulary.looked_up`). Likely.
4. **A number written as a word of numerals** (二十): known once its
   numerals are (polyglotic-hq 360). Likely.
5. **The line**: within it, known - likely if the learner set it, a guess
   while it is the app's starting line; placed past it, new.
6. **The words it is made of** (its base words, from Lexicon): a form
   nothing places is known when every word it is made of is (step 2 of
   349's migration fills this in; until then nothing is made of others).
   A guess.
7. **Nothing**: a word nothing places is new, as a guess.

"Start links at" asks the same question as if the line were elsewhere
(`of(word, as_if_knowing=N)`): evidence about the word still wins.

A language with a basic dictionary keeps no learning data yet (decision
0035), so its `Knowledge` has a line and nothing else (`by_line`) - the
same question, fewer kinds of evidence.

**Who reads it so far** (349's migration, step 1): word links, for full
and basic languages alike. Marks, the learning load, coverage and Words
still read `Vocabulary.status` - moving them is step 3, which changes what
a learner with no line set sees, and waits for the user's word (DECISIONS
#176 (a)).

Plain rules: no storage, no Qt. `Vocabulary` holds one over its own
statuses and line (`Vocabulary.knowledge`).
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import IntEnum, StrEnum

from polyglotic_desktop.core.learning.levels import (
    KnownLine,
    LevelWords,
    place,
    placed_within,
)
from polyglotic_desktop.core.learning.statuses import StatusRecord, StatusSource
from polyglotic_desktop.core.shared import EntryFacts, EntryId, WordStatus


class Confidence(IntEnum):
    """How sure an answer is. Three grades, not a number: nothing measured
    yet would tell 0.7 from 0.8 (349)."""

    GUESS = 1  # the app's own assumption
    LIKELY = 2  # follows from what the learner said in general, or did
    SURE = 3  # the learner said so about this word


class Reason(StrEnum):
    """Why a word has the answer it has - one a learner could be told."""

    SAID = "said"  # the learner set this word's status
    IMPORTED = "imported"  # another tool did
    LOOKED_UP = "looked_up"  # they looked it up, so it isn't known
    NUMBER = "number"  # a number written in numerals
    LINE = "line"  # within what they said they know
    STARTING_LINE = "starting_line"  # within the line the app assumes meanwhile
    PAST_LINE = "past_line"  # placed, past the line
    PARTS = "parts"  # by the words it is made of
    NOT_PLACED = "not_placed"  # nothing says how common it is


@dataclass(frozen=True)
class Knows:
    """The answer about one word."""

    status: WordStatus
    confidence: Confidence
    reason: Reason

    @property
    def known(self) -> bool:
        """Known, or a word the learner said to ignore: either way one
        they don't want pointed out or linked."""
        return self.status in (WordStatus.KNOWN, WordStatus.IGNORED)


BaseWords = Callable[[EntryFacts], Sequence[EntryFacts]]
"""The words a form nothing places is made of (Lexicon's, by its word
split: 中 and 的 for 中的) - empty when it isn't made of others."""


def _no_bases(_: EntryFacts) -> Sequence[EntryFacts]:
    return ()


class Knowledge:
    """What the learner knows in one language."""

    def __init__(
        self,
        own: Callable[[EntryId], StatusRecord | None],
        line: Callable[[], KnownLine | None],
        starting: KnownLine,
        level_words: LevelWords | None = None,
        bases: BaseWords | None = None,
    ) -> None:
        """`own`: the status kept for a word, if one is (the learner's, an
        import's, or what a lookup left); `line`: the learner's line, None
        until they set one - `starting` is assumed meanwhile;
        `level_words`: about how many words a level of a scheme stands
        for, to read a line kept as a level as a rank; `bases`: the words
        a form nothing places is made of."""
        self._own = own
        self._line = line
        self._starting = starting
        self._level_words = level_words
        self._bases = bases or _no_bases

    @classmethod
    def by_line(cls, starting_words: int) -> "Knowledge":
        """A language with ranks and no learning data (a basic dictionary's
        pack): nothing but a line, assumed at `starting_words` until
        `of(..., as_if_knowing=...)` says where."""
        return cls(lambda _: None, lambda: None, KnownLine.words(starting_words))

    @property
    def known_words(self) -> int | None:
        """The line as one number: "I know about N words" - the learner's,
        or the starting line's until they set one. None only for a line
        kept in a scheme that says no number of words (HSK 3.0's 2021
        standard)."""
        return (self._line() or self._starting).words_known(self._level_words)

    @property
    def line_set(self) -> bool:
        """Whether the learner set the line (else it is the starting one)."""
        return self._line() is not None

    def of(self, word: EntryFacts, as_if_knowing: int | None = None) -> Knows:
        """The one question. `as_if_knowing`: answer as if the learner had
        said they know about that many words ("Start links at")."""
        said = self._said(word)
        if said is not None:
            return said
        by_line = self._by_line(word, as_if_knowing)
        if by_line.reason is not Reason.NOT_PLACED:
            return by_line
        bases = self._bases(word)
        if not bases:
            return by_line
        answers = [self._said(b) or self._by_line(b, as_if_knowing) for b in bases]
        if all(a.known for a in answers):
            return Knows(WordStatus.KNOWN, Confidence.GUESS, Reason.PARTS)
        if any(a.reason is Reason.NOT_PLACED for a in answers):
            return by_line  # a part nothing places: still not placed
        return Knows(WordStatus.NEW, Confidence.GUESS, Reason.PARTS)

    def _said(self, word: EntryFacts) -> Knows | None:
        """The answer from evidence about this word itself, if any."""
        own = self._own(word.entry_id)
        if own is not None:
            return _from_record(own)
        if word.is_number:  # 二十, as 20 is (polyglotic-hq 360)
            return Knows(WordStatus.KNOWN, Confidence.LIKELY, Reason.NUMBER)
        return None

    def _by_line(self, word: EntryFacts, as_if_knowing: int | None) -> Knows:
        """The answer from what the learner said they know in general."""
        said = self._line()
        if as_if_knowing is not None:
            line = KnownLine.words(as_if_knowing)
        else:
            line = said or self._starting
        chosen = said is not None or as_if_knowing is not None
        sure = Confidence.LIKELY if chosen else Confidence.GUESS
        if _within(word, line, self._level_words):
            return Knows(
                WordStatus.KNOWN, sure, Reason.LINE if chosen else Reason.STARTING_LINE
            )
        if place(word) is None and not (line.by_level and word.level is not None):
            return Knows(WordStatus.NEW, Confidence.GUESS, Reason.NOT_PLACED)
        return Knows(WordStatus.NEW, sure, Reason.PAST_LINE)


def _within(word: EntryFacts, line: KnownLine, level_words: LevelWords | None) -> bool:
    """Whether the word is within the line, read as a rank: its place no
    further than the number of words the line stands for. A line kept in
    a scheme that says no number is read by level, as before 323."""
    words = line.words_known(level_words)
    if words is None:
        return line.knows(word)
    # a level line also knows its own levels' words: HSK 3's words are
    # placed within its 1,000 by their level's size, whatever their rank
    return placed_within(word, words) or line.knows(word)


def _from_record(own: StatusRecord) -> Knows:
    if own.source is StatusSource.LEARNER:
        return Knows(own.status, Confidence.SURE, Reason.SAID)
    if own.source is StatusSource.IMPORTED:
        return Knows(own.status, Confidence.LIKELY, Reason.IMPORTED)
    # estimated and kept: a pinned lookup turned an assumed-known word new
    return Knows(own.status, Confidence.LIKELY, Reason.LOOKED_UP)
