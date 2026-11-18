"""Where contexts meet: the events they publish and the IDs they share.

DOMAIN.md: "No shared objects ... events where they can." A context
announces what happened ("caption finished", "word looked up") as a small
immutable event defined here, and other contexts react to it; things in
other contexts are referred to by ID (caption id, entry ID), never by
object.

Keep this small and stable: plain dataclasses and ID types, no logic, no
imports from any context (import-linter checks). Adding an event here is a
change to the published language between contexts, so review it as one.

- IDs and values: `EntryId`, `Level`, `WordStatus`.
- What Lexicon tells Learning about a word (decision 0002's example):
  `EntryFacts`, `WordInLine`.
- What Learning publishes for the server (protocol.md's `learning`
  message - entry IDs and times, never the sentence): `WordLookedUp`,
  `WordSaved`, `WordUnsaved`, `WordStatusChanged`.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import NewType

EntryId = NewType("EntryId", str)
"""A dictionary entry's identity, shared by Lexicon, Learning and the server:
the dictionary's name and ten characters, `cedict:y7p98nwvxq` (decision
0007). Opaque: never parse it. At most 64 characters, ASCII."""


@dataclass(frozen=True)
class Level:
    """A learner's level in a named scheme (glossary: level): `Level("hsk-2025",
    4)` is level 4 of HSK 3.0's 2025 exam syllabus; `Level("en-frequency",
    3)` the third English frequency band. Lexicon says which entries are at or below it; Learning
    keeps the learner's own."""

    scheme: str
    value: int


class WordStatus(StrEnum):
    """What the learner knows of an entry (glossary: word status). The
    values are protocol.md's."""

    NEW = "new"
    LEARNING = "learning"  # in the deck
    KNOWN = "known"
    IGNORED = "ignored"  # names, words they don't care about


@dataclass(frozen=True, slots=True)
class EntryFacts:
    """What Learning needs to know about a dictionary entry, from Lexicon:
    its level in the learner's level scheme (1 = the lowest; None if the
    scheme doesn't include it), its frequency rank (1 = the commonest) and
    whether it's a name (never shown as unfamiliar). `level_words` is
    about how many words a learner at its level knows, the levels below
    counted (1,000 at HSK 3); None if it has no level, or the scheme
    doesn't say - Learning places the word by it and its rank
    (`core.learning.levels.place`). `is_number`: a number written as a
    word made of numerals (二十, 十五) - known once its numerals are, not
    a word to point out (polyglotic-hq 360). `spoken_rank`: its rank in
    speech where the pack ranks it rarer in writing (谢谢: 6,361st written,
    82nd said), None otherwise; `is_filler`: a hesitation sound or
    interjection (嗯, "um") - everyday talk, which Learning's conversation
    words never light (polyglotic-hq 491); `spells_a_number`: a number
    spelled out in letters (fourteen, thousand) - a word to learn, but
    never what a conversation is about (491); `names_capitalised`: its
    language writes a word with a capital inside a sentence only for a
    name (English: "Julia" - not German, whose nouns all have one)."""

    entry_id: EntryId
    level: int | None
    frequency_rank: int | None
    is_name: bool
    level_words: int | None = None
    is_number: bool = False
    spoken_rank: int | None = None
    is_filler: bool = False
    spells_a_number: bool = False
    names_capitalised: bool = False


@dataclass(frozen=True, slots=True)
class WordInLine:
    """A dictionary word in a line of text - `line[start:end]` - and the
    entry it counts for ("running" counts for "run"). Lexicon finds them
    (the word split, for Chinese); Learning highlights and counts them."""

    start: int
    end: int
    entry: EntryFacts


@dataclass(frozen=True, slots=True)
class WordLookedUp:
    """A lookup was shown, on hover or pinned."""

    entry_id: EntryId
    at: datetime


@dataclass(frozen=True, slots=True)
class WordSaved:
    """The word was saved (into any category)."""

    entry_id: EntryId
    at: datetime


@dataclass(frozen=True, slots=True)
class WordUnsaved:
    """The word was removed from saved words."""

    entry_id: EntryId
    at: datetime


@dataclass(frozen=True, slots=True)
class WordStatusChanged:
    """The learner set a word's status - by a click, in the vocabulary
    list or by an import. Statuses Learning estimates (from the learner's
    level, or a lookup) aren't published: they're recomputed on any PC."""

    entry_id: EntryId
    status: WordStatus
    at: datetime


LearningEvent = WordLookedUp | WordSaved | WordUnsaved | WordStatusChanged
"""Learning data for the server, as entry IDs and times (DOMAIN.md: Data
and privacy). Learning publishes them; the connection sends them (D3)."""
