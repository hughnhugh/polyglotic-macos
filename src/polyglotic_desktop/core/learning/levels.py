"""The learner's level as a known line, and the learning window past it.

Three kinds of word (polyglotic-hq 323, the user, 2026-11-14; decision
0114), each estimated from how common a word is, never stored, so moving
the line moves every estimate at once:

- **known**: the words up to the known line - "I know about the 3,000
  most common words";
- **learning**: the learning window - the next words past the line (the
  next 1,000, or the size the learner chose - a number, or unlimited:
  every word past the line, decision 0144): the ones a caption points
  out;
- **rarer**: everything past the window - never pointed out, still looked
  up on hover or a click.

A word's status set by hand (known, in the deck, ignored, new again)
always wins over the estimate (`statuses`).

**A word's place** on the scale is about how many words a learner knows
before it: its frequency rank, or the size of the vocabulary of its level
in the language's syllabus (HSK 3's 1,000 words) when that is smaller. The
frequency list for Chinese is counted from written text, where 谢谢 is the
6,361st word and 你好 the 8,621st: a learner of 1,000 words knows both,
and the syllabus says so. A word with neither is past every line: rarer.

**A line kept as a level** (`KnownLine.by_level`) is how every level was
kept before 323 - an HSK level or an English frequency band, as the level
picker set it. It reads as it always did: words at or below the level are
known, the level above is the learning window, and words the scheme leaves
out are rarer. Nothing a learner sees changes until they say how many
words they know.

Before 323 the level was a curve (a midpoint, a slope, and the chance from
which a word counted as known). With whole levels the curve only ever cut
at the level picked, so it is a line now; what was stored (a scheme and a
midpoint half a level above the level picked) reads as the same line.
"""

import math
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum, StrEnum
from typing import Literal

from polyglotic_desktop.core.shared import EntryFacts, Level

WORDS = "words"
"""The scale of a line said as a number of words. Any other scale is a
level scheme's ID: a line kept as a level."""

STARTING_LEVEL = 3
"""The level words are estimated at until the learner sets theirs - the
first run doesn't ask (polyglotic-hq 293): the middle of the level
picker's eight choices, HSK 3 (about 1,000 words on the 2025 syllabus) or
the 3,000 most common English words."""


class Unlimited(Enum):
    """A learning window with no end (the user, 2026-11-15: "a learning
    window for unlimited and custom amount"; decision 0144)."""

    UNLIMITED = "unlimited"


UNLIMITED = Unlimited.UNLIMITED
"""Every word past the known line is in the window."""

WindowSize = int | Literal[Unlimited.UNLIMITED]
"""A learning window's size: a number of words, or `UNLIMITED`."""

WINDOW_SIZES = (100, 500, 1000, 2000)
"""The learning window's sizes a learner chooses from (the user,
2026-11-14: "could be 100, 500, 1k, 2k"), beside `UNLIMITED` and a number
of their own between `MIN_WINDOW` and `MAX_WINDOW`."""

MIN_WINDOW, MAX_WINDOW = 10, 100_000
"""The bounds of a number of the learner's own (decision 0144): under 10
words past the line a caption would almost never meet one; 100,000 is past
the end of every ranked list a pack has (Chinese's longest, 87,125 ranks,
2026-11-15), so a bigger number would point out nothing more."""

DEFAULT_WINDOW = 1000
"""The learning window's size until the learner chooses one."""


def window_size(size: int) -> int:
    """A number of the learner's own, kept within `MIN_WINDOW` and
    `MAX_WINDOW`."""
    return min(MAX_WINDOW, max(MIN_WINDOW, size))


LevelWords = Callable[[str, int], int | None]
"""About how many words a learner at a level of a scheme knows (the
scheme's ID, the level; 0 for "just starting"), None where the scheme
doesn't say: Lexicon's `LevelScheme.words_at`, handed in by `main` -
contexts don't import each other."""


def place(facts: EntryFacts) -> int | None:
    """A word's place on the words scale: about how many words a learner
    knows before it - the smaller of its frequency rank and the size of
    its level's vocabulary. None: neither is known - rarer than any line."""
    rank, level_words = facts.frequency_rank, facts.level_words
    if rank is None:
        return level_words
    return rank if level_words is None else min(rank, level_words)


@dataclass(frozen=True)
class KnownLine:
    """The learner's level: on the `WORDS` scale, they know about the
    `known` most common words; on a level scheme's (a line kept as a
    level), the words at or below level `known`."""

    scale: str
    known: int

    @classmethod
    def words(cls, known: int) -> "KnownLine":
        """ "I know about the `known` most common words." """
        return cls(WORDS, max(0, known))

    @classmethod
    def picked(cls, level: Level) -> "KnownLine":
        """The line for a level chosen in the level picker: words at or
        below `level.value` known. Level 0 is "just starting"."""
        return cls(level.scheme, max(0, level.value))

    @classmethod
    def starting(cls, scheme: str) -> "KnownLine":
        """The line words are estimated on in `scheme` until the learner
        sets theirs: `STARTING_LEVEL`, as if picked."""
        return cls.picked(Level(scheme, STARTING_LEVEL))

    @classmethod
    def stored(cls, scheme: str, midpoint: float) -> "KnownLine":
        """The line kept as `scheme` and `midpoint` (the store's two
        values, from when the level was a curve): the number of words on
        the `WORDS` scale; for a level scheme the midpoint half a level
        above the level picked."""
        if scheme == WORDS:
            return cls.words(int(midpoint))
        return cls(scheme, max(0, math.floor(midpoint)))

    @property
    def midpoint(self) -> float:
        """What the store keeps beside the scale (`stored`)."""
        return float(self.known) if self.scale == WORDS else self.known + 0.5

    @property
    def by_level(self) -> bool:
        """A line kept as a level of a scheme, not as a number of words."""
        return self.scale != WORDS

    def knows(self, facts: EntryFacts) -> bool:
        """Whether the line estimates the word known."""
        at = facts.level if self.by_level else place(facts)
        return at is not None and at <= self.known

    def words_known(self, level_words: LevelWords | None = None) -> int | None:
        """About how many words the line stands for: on the words scale,
        its own; kept as a level, that level's in its scheme
        (`level_words`: HSK 3 is about 1,000 words) - None where that isn't
        known."""
        if not self.by_level:
            return self.known
        return level_words(self.scale, self.known) if level_words else None

    def window(self, size: WindowSize | None = None) -> "LearningWindow":
        """The learning window past this line: its next `size` words
        (None: `DEFAULT_WINDOW`), or every word past it (`UNLIMITED`). A
        line kept as a level has the level above it, whatever number
        `size` is; unlimited, every level above it."""
        if size is None:
            return LearningWindow(self, DEFAULT_WINDOW)
        return LearningWindow(self, size if size is UNLIMITED else max(0, size))


@dataclass(frozen=True)
class LearningWindow:
    """The words being learned: the `size` places past the known `line` -
    or, past a line kept as a level, the next level. A set of places with
    a size, so a fixed load whose words graduate (polyglotic-hq 324) can
    be the same set, refilled.

    An unlimited window (`UNLIMITED`, decision 0144) has no end: every
    word past the line is in it, on either scale - words with no place
    (no rank, no level) too, so nothing new is rarer."""

    line: KnownLine
    size: WindowSize = DEFAULT_WINDOW

    @property
    def last(self) -> int | None:
        """The last place (or level) in the window; None: it has no end."""
        if self.size is UNLIMITED:
            return None
        return self.line.known + (1 if self.line.by_level else self.size)

    def reaches(self, facts: EntryFacts) -> bool:
        """Whether the word is no rarer than the window's end: a new word
        that is, is one to point out - a word past it is rarer. (A word
        before the line is new only if the learner said so.) A window
        with no end reaches every word."""
        last = self.last
        if last is None:
            return True
        at = facts.level if self.line.by_level else place(facts)
        return at is not None and at <= last

    def holds(self, facts: EntryFacts) -> bool:
        """Whether the word is in the window: past the line, and reached."""
        return self.reaches(facts) and not self.line.knows(facts)


class LinkChoice(StrEnum):
    """Which of a language's words are linked to their translation (the
    user, 2026-11-14: "didn't want basic words to be linked ... probably
    make it configurable")."""

    EVERY = "every"  # as before 323
    PAST_KNOWN = "past_known"  # only words past what the learner knows
    OFF = "off"


LINKS_FROM = (500, 1000, 2000, 3000, 5000, 8000)
"""The places a learner can start links from instead of their line."""

UNKNOWN_LEVEL_LINKS_FROM = 1000
"""Where "past what you know" starts in a language whose words are ranked
but whose level isn't kept - one with a basic dictionary, which keeps no
learning data (decision 0035; its pack's frequency ranks, decision 0120)
- until the learner chooses: about the words a learner is estimated to
know until they set a level (HSK 3, `STARTING_LEVEL`). Before 338 only
key links showed there, and the server marks every Russian or Spanish
word key: every word was linked."""


def placed_within(facts: EntryFacts, words: int) -> bool:
    """Whether the word is placed (`place`) within the `words` most common:
    one a learner who knows them knows."""
    at = place(facts)
    return at is not None and at <= words


@dataclass(frozen=True)
class LanguageChoices:
    """What the learner chose for one language they learn, beside their
    line: the learning window's size (None: `DEFAULT_WINDOW`; a number,
    or `UNLIMITED`); which of its words are linked (`links`), and with
    "past what I know", from which place (`links_from`; None: the known
    line itself). Settings, kept per language; the line itself is
    learning data.

    Unlimited is kept as the word "unlimited", which a version before
    0144 reads as nothing chosen: the default window, not an error."""

    window_size: WindowSize | None = None
    links: LinkChoice = LinkChoice.EVERY
    links_from: int | None = None

    @classmethod
    def from_stored(cls, stored: object) -> "LanguageChoices":
        """From what the settings keep for a language; anything missing or
        not valid takes its default (a newer version's values too)."""
        if not isinstance(stored, dict):
            return cls()
        links = stored.get("links")
        return cls(
            window_size=_window(stored.get("window")),
            links=LinkChoice(links)
            if isinstance(links, str) and links in set(LinkChoice)
            else LinkChoice.EVERY,
            links_from=_count(stored.get("links_from")),
        )

    def to_stored(self) -> dict[str, object]:
        """Only what was chosen: {} when nothing was."""
        stored: dict[str, object] = {}
        if self.window_size is UNLIMITED:
            stored["window"] = UNLIMITED.value
        elif self.window_size is not None:
            stored["window"] = self.window_size
        if self.links is not LinkChoice.EVERY:
            stored["links"] = self.links.value
        if self.links_from is not None:
            stored["links_from"] = self.links_from
        return stored


def _window(value: object) -> WindowSize | None:
    """A learning window's size as stored: "unlimited", or a number kept
    within the bounds; None for anything else."""
    if value == UNLIMITED.value:
        return UNLIMITED
    count = _count(value)
    return None if count is None else window_size(count)


def _count(value: object) -> int | None:
    """A number of words as stored, or None for anything else."""
    valid = isinstance(value, int) and not isinstance(value, bool) and value >= 0
    return value if valid and isinstance(value, int) else None
