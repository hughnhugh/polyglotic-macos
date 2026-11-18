"""Dictionary entries, and the level schemes a learner picks from.

A dictionary entry is one headword with its reading and meanings,
identified by an entry ID (glossary). For known words (polyglotic-hq
MVP.md) each entry also has a frequency rank and levels, so that at first
run "words at or below my level" can count as known, and a name flag, so
names aren't shown as unfamiliar.
"""

import bisect
import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass, replace

from polyglotic_desktop.core.shared import EntryFacts, EntryId, Level
from polyglotic_desktop.ports.dictionary import MeaningsFile

_VARIANT = re.compile(r"^(old |archaic |unofficial |Japanese |erroneous )?variant of ")


@dataclass(frozen=True)
class LevelScheme:
    """A scale a learner's level is measured on, as offered by the level
    picker. `levels` are the labels, lowest first; a Level's value is a
    position in it, from 1. A scheme with `cutoffs` is frequency bands:
    level n is the `cutoffs[n - 1]` most common words."""

    id: str
    name: str
    levels: tuple[str, ...]
    cutoffs: tuple[int, ...] = ()
    sizes: tuple[int, ...] = ()
    """About how many words a learner at each level knows, counting the
    levels below - for the level picker; () if not known."""

    def words_at(self, value: int) -> int | None:
        """About how many words a learner at level `value` knows (0 for
        "just starting"), or None if the scheme doesn't say."""
        sizes = self.sizes or self.cutoffs
        if value == 0:
            return 0
        return sizes[value - 1] if 0 < value <= len(sizes) else None


HSK_2025 = LevelScheme(
    "hsk-2025",
    "HSK 3.0 (2025 exam syllabus)",
    ("1", "2", "3", "4", "5", "6", "7-9"),
    # cumulative, from the syllabus via the hsk30 package (project 019, 2026-11-04)
    sizes=(300, 500, 1000, 2000, 3600, 5400, 11000),
)
"""HSK 3.0's exam syllabus, published 2025-11 and in force from 2026-07 -
what learners are tested on: about 300 words at level 1, 11,000 by 7-9.
The level picker's default for Chinese learners (the user, 2026-11-04)."""

HSK_2021 = LevelScheme(
    "hsk-2021",
    "HSK 3.0 (2021 standard)",
    ("1", "2", "3", "4", "5", "6", "7-9"),
)
"""HSK 3.0's national standard GF0025-2021: about 500 words at level 1. The
same name as the 2025 syllabus, but 41.5% of their shared words are at
different levels - never mix the two."""

ENGLISH_FREQUENCY = LevelScheme(
    "en-frequency",
    "The most common English words",
    ("1,000", "2,000", "3,000", "5,000", "8,000", "12,000", "20,000"),
    cutoffs=(1000, 2000, 3000, 5000, 8000, 12000, 20000),
)
"""English frequency bands by headword (not word family), proposed by
project 018 on 2026-11-04 - project 019 may refine them."""

SCHEMES = {scheme.id: scheme for scheme in (HSK_2025, HSK_2021, ENGLISH_FREQUENCY)}

DEFAULT_CHINESE_SCHEME = HSK_2025
"""The scheme the level picker starts on for Chinese learners: the 2025
exam syllabus, chosen by the user on 2026-11-04. English learners have one
scheme, `ENGLISH_FREQUENCY`."""


@dataclass(frozen=True)
class DictionaryEntry:
    """One headword with its reading and meanings.

    Chinese: `headword` is the simplified form, `traditional` the
    traditional one, `reading` pinyin with tone marks ("diàn nǎo").
    English: `headword` is the word, `traditional` is "", `reading` IPA.
    `frequency_rank` is 1 for the most common word in the dictionary.
    """

    entry_id: EntryId
    headword: str
    traditional: str
    reading: str
    meanings: tuple[str, ...]
    frequency_rank: int | None = None
    levels: tuple[tuple[str, int], ...] = ()
    is_name: bool = False
    spoken_rank: int | None = None
    """Its rank in speech, where the pack ranks it rarer (`spoken`)."""
    is_filler: bool = False
    """A hesitation sound or interjection (`spoken`)."""
    spells_a_number: bool = False
    """A number spelled out in letters (`spoken`)."""
    names_capitalised: bool = False
    """Its language capitalises a word inside a sentence only for a name."""

    @property
    def idiom(self) -> bool:
        return any("(idiom)" in m for m in self.meanings)

    @property
    def variant_only(self) -> bool:
        """Just "variant of X" - a form you'd look up under X."""
        return bool(self.meanings) and all(_VARIANT.match(m) for m in self.meanings)

    def level_in(self, scheme: LevelScheme) -> int | None:
        """This entry's level in `scheme` (1 = the lowest), or None if the
        scheme doesn't include it."""
        return level_in(scheme, self.frequency_rank, self.levels)

    def is_at_or_below(self, level: Level) -> bool:
        """Whether a learner at `level` counts this entry as known at first
        run. False for a scheme this entry isn't in, or one we don't know."""
        scheme = SCHEMES.get(level.scheme)
        own = self.level_in(scheme) if scheme else None
        return own is not None and own <= level.value

    @property
    def is_number(self) -> bool:
        return is_number_word(self.headword, self.levels)

    def facts(self, scheme_id: str) -> EntryFacts:
        """What Learning needs to know about this entry, for a learner whose
        level is in the scheme `scheme_id`: its level there (None if the
        scheme doesn't include it, or is unknown), rank, and whether it's a
        name or a number; how common it is in speech."""
        return entry_facts(
            self.entry_id,
            self.frequency_rank,
            self.levels,
            self.is_name,
            scheme_id,
            self.is_number,
            self.spoken_rank,
            self.is_filler,
            self.spells_a_number,
            self.names_capitalised,
        )


def level_in(
    scheme: LevelScheme,
    frequency_rank: int | None,
    levels: Sequence[tuple[str, int]],
) -> int | None:
    """The level in `scheme` (1 = the lowest) of an entry with this rank
    and these levels, or None if the scheme doesn't include it."""
    if scheme.cutoffs:
        if frequency_rank is None:
            return None
        return next(
            (n for n, cut in enumerate(scheme.cutoffs, 1) if frequency_rank <= cut),
            None,
        )
    return dict(levels).get(scheme.id)


_NUMERALS = frozenset("两")
"""Numerals Unicode gives no number: 两 (its traditional 兩 has 2)."""


def is_number_word(headword: str, levels: Sequence[tuple[str, int]]) -> bool:
    """Whether a headword is a number written in numerals - 二十, 十五,
    百万, "20" - that no syllabus teaches as a word of its own. The
    frequency list ranks them as rare written forms (二十 5,165th, 十五
    3,172nd: numbers are mostly written in digits), so a learner who
    chose a big window saw them pointed out as new (polyglotic-hq 351).
    One numeral alone (二, 万) is a word, placed as any word is; so is a
    compound a syllabus teaches (千万 "by all means", 万一 "just in case")."""
    if levels or not headword:
        return False
    if len(headword) < 2 and not headword.isdecimal():
        return False
    return all(
        c in _NUMERALS or unicodedata.numeric(c, None) is not None for c in headword
    )


def entry_facts(
    entry_id: EntryId,
    frequency_rank: int | None,
    levels: Sequence[tuple[str, int]],
    is_name: bool,
    scheme_id: str,
    is_number: bool = False,
    spoken_rank: int | None = None,
    is_filler: bool = False,
    spells_a_number: bool = False,
    names_capitalised: bool = False,
) -> EntryFacts:
    """`DictionaryEntry.facts` from the parts it needs - for a dictionary
    that reads them without making the whole entry (its reading marked):
    Words asks for every word met (polyglotic-hq project 212)."""
    scheme = SCHEMES.get(scheme_id)
    level = level_in(scheme, frequency_rank, levels) if scheme else None
    return EntryFacts(
        entry_id=entry_id,
        level=level,
        frequency_rank=frequency_rank,
        is_name=is_name,
        is_number=is_number,
        spoken_rank=spoken_rank,
        is_filler=is_filler,
        spells_a_number=spells_a_number,
        names_capitalised=names_capitalised,
        # a syllabus's levels only: a frequency band's words are its rank's
        level_words=scheme.sizes[level - 1]
        if scheme and level and len(scheme.sizes) >= level
        else None,
    )


def words_in_runs(ranks: Sequence[int], runs: Sequence[tuple[int, int]]) -> list[int]:
    """How many of `ranks` (sorted, each once - a dictionary's
    `words_ranked`) fall in each run of ranks (first, last)."""
    return [
        bisect.bisect_right(ranks, last) - bisect.bisect_left(ranks, first)
        for first, last in runs
    ]


def explained(entry: DictionaryEntry, meanings: MeaningsFile | None) -> DictionaryEntry:
    """`entry` with its meanings in the learner's language where `meanings`
    (the dictionary's meanings file in it, decision 0234) has them; else as
    the dictionary has it. Only what's shown changes: its ID, rank, levels
    and whether it's a name stay the dictionary's own."""
    found = meanings.meanings(entry.entry_id) if meanings is not None else None
    return replace(entry, meanings=found) if found else entry
