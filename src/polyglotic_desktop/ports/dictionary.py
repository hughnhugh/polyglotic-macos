"""DictionaryFile: one dictionary's entries, as stored on the PC.

The app ships one file per dictionary (CC-CEDICT for Chinese learners,
ECDICT for English learners), built by `tools/dictionaries`. Core's Lexicon
reads entries through this port and gives them their meaning: pinyin tone
marks, names, levels.

`MeaningsFile`: one dictionary's meanings in the learner's language, beside
it (decision 0234): where it has an entry, the card shows those instead.

A file that can't be read never stops the app (polyglotic-hq 199): the
learner's dictionary is then *out* - every query answers nothing, so
captions run without word marks or counting, and lookups say why
(`DictionaryProblem`).
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from polyglotic_desktop.ports.word_classes import SenseClasses


class DictionaryProblem(StrEnum):
    """Why the learner's dictionary is out. Content-free: the log and
    `--check-install`'s report carry it as it is."""

    MISSING = "missing"
    """No file where the app keeps it."""
    DAMAGED = "damaged"
    """Not readable as a dictionary file: cut off, overwritten, or not a
    dictionary file at all."""
    WRONG_FORMAT = "wrong_format"
    """A dictionary file of a format this version doesn't read."""
    UNREADABLE = "unreadable"
    """The PC wouldn't open it: no permission, a disk error."""


@dataclass(frozen=True)
class EntryRecord:
    """One dictionary entry as stored.

    `reading` is as the source gives it: numbered pinyin ("dian4 nao3") for
    Chinese, IPA for English. `levels` are (scheme, level) pairs such as
    ("hsk-2025", 1). `frequency_rank` is 1 for the most common word in the
    dictionary, None if the frequency source doesn't have it.
    """

    entry_id: str
    headword: str  # simplified Chinese, or the English word
    traditional: str  # traditional Chinese ("" for English)
    reading: str
    meanings: tuple[str, ...]
    frequency_rank: int | None = None
    levels: tuple[tuple[str, int], ...] = ()
    sense_classes: tuple[SenseClasses, ...] = ()
    """One value per meaning, or empty for a pack without class evidence."""
    sense_prefixes: tuple[int, ...] = ()
    """Lengths of legacy class labels identified by the builder, by ordinal."""


class DictionaryFile(Protocol):
    """One dictionary's entries, found by the words that name them."""

    def headwords(self) -> Iterable[str]:
        """Every written form with an entry - both scripts for Chinese."""
        ...

    def frequency_ranks(self) -> Mapping[str, int]:
        """Written form -> the best (lowest) frequency rank among its
        entries, for the forms that have one. The word split breaks ties
        with it. Empty for a dictionary without frequencies."""
        ...

    def records(self, word: str) -> Sequence[EntryRecord]:
        """The entries for `word` exactly as written, in the file's order:
        everyday reading first."""
        ...

    def records_by_meaning(
        self, english_word: str, limit: int
    ) -> Sequence[EntryRecord]:
        """Entries whose meanings use `english_word` (lower case), commonest
        first, at most `limit` - for reverse lookup. Empty for a dictionary
        without that index."""
        ...

    def lemma(self, word: str) -> str | None:
        """The headword `word` is an inflected form of ("running" -> "run"),
        or None. Always None for a dictionary without inflections."""
        ...

    def form_reading(self, word: str) -> str:
        """How `word` itself is said, where the dictionary marks it apart
        from its entries' headwords - Russian's stress on an inflected form
        ("руку" is "ру́ку"; "руки" is "ру́ки, руки́", two forms written
        alike) - or "". Always "" for a dictionary without form readings."""
        ...

    def record(self, entry_id: str) -> EntryRecord | None:
        """The entry with this ID - or, if it was merged into another, that
        one. None if it was removed."""
        ...

    def merged_ids(self) -> Sequence[str]:
        """Every entry ID that was merged into another entry (`record`
        finds the one it became) - few: 8 between two CC-CEDICT releases
        (decision 0007); none in a dictionary as first built."""
        ...

    def words_ranked(self, last: int) -> Sequence[int]:
        """The frequency ranks from 1 to `last` that entries have, each once,
        in order - one per written form (Words' bands count the words in a
        run of ranks with them)."""
        ...

    def headwords_ranked(self, after: int, limit: int) -> Sequence[tuple[str, int]]:
        """The headwords whose own first entry (`records(headword)[0]`: the
        one a caption counts the word for) has a frequency rank past
        `after`: each with that rank, commonest first, at most `limit` -
        the words a learning load takes in, in order (polyglotic-hq 324).
        Empty for a dictionary without frequencies."""
        ...

    def headwords_at_levels(self, scheme: str) -> Sequence[tuple[str, int, int | None]]:
        """The headwords whose own first entry the level scheme `scheme`
        gives a level: each with that level and the entry's frequency rank
        (None: it has none) - a syllabus's words, which a learning load
        places by their level where that is earlier than their rank. None
        for a scheme of frequency cut-offs."""
        ...

    def words_at_levels(self, scheme: str) -> Mapping[int, int]:
        """How many headwords the level scheme `scheme` puts at each level,
        by the entries' own levels - none for a scheme of frequency
        cut-offs, which entries don't carry."""
        ...


class MeaningsFile(Protocol):
    """One dictionary's meanings in one more language, by entry ID: a small
    file beside the dictionary (a rider, decision 0133), so a dictionary is
    built once and explained in each learner's language (decision 0234)."""

    def meanings(self, entry_id: str) -> tuple[str, ...] | None:
        """The entry's meanings in this file's language, one per line of the
        card, as people wrote them; None: it has none for the entry (the
        dictionary's own are shown)."""
        ...
