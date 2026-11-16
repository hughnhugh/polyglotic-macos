"""LearningStore: the learner's own learning data, kept on this PC.

The learner's level, the word statuses they set (and those Learning
estimated from a lookup), saved words with their categories and source
sentences, exposure counts, each day's coverage and listening time, and
the learning load's words.
Core's Learning reads it all once at start
and writes each change through this port; it gives the values their
meaning (statuses, sources, the known line).

Privacy (DOMAIN.md, "Data and privacy"): a saved word's source sentence,
the exposure counts and the days' coverage and listening stay on this PC. What goes to the server - entry
IDs and times - is sent by the connection, not read from here.
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from pathlib import Path
from typing import NamedTuple, Protocol


@dataclass(frozen=True)
class StoredLevel:
    """The learner's level, as two values (from when it was a curve):
    `words` and how many of the most common words they know; or a level
    scheme (`hsk-2025`) and the point half a level above the level picked
    (`core.learning.levels.KnownLine.stored`)."""

    scheme: str
    midpoint: float


@dataclass(frozen=True)
class StoredStatus:
    """A word status set explicitly - `status` is `new`, `learning`,
    `known` or `ignored`; `source` is `estimated`, `learner` or
    `imported`. `at` is timezone-aware (UTC)."""

    entry_id: str
    status: str
    source: str
    at: datetime


@dataclass(frozen=True)
class StoredCategory:
    """A category of saved words: its name and colour (`#rrggbb`), shown in
    `position` order."""

    id: str
    name: str
    color: str
    position: int


@dataclass(frozen=True)
class StoredSavedWord:
    """A saved word, with what it was saved with: its headword and
    traditional form, reading, a short meaning, and the line it was saved
    from with that line's translation (the user's own data)."""

    entry_id: str
    headword: str
    traditional: str
    reading: str
    meaning: str
    category_id: str
    source_sentence: str
    source_translation: str
    saved_at: datetime


@dataclass(frozen=True)
class StoredDeckWord:
    """A word the learner put in the deck, with the line it was in when they
    did (`sentence`, `translation`: the user's own data, kept on this PC)
    and what it says about the entry, so it can be exported even if the
    word was never saved."""

    entry_id: str
    headword: str
    traditional: str
    reading: str
    meaning: str
    sentence: str
    translation: str
    learned_at: datetime


@dataclass(frozen=True)
class StoredAnkiExport:
    """When a word was last written to an Anki file of a kind (`kind`:
    "deck" or "csv" - each remembers its own, polyglotic-hq 368)."""

    entry_id: str
    exported_at: datetime
    kind: str = "deck"


@dataclass(frozen=True)
class StoredLookups:
    """How often a word was looked up on this PC and when last
    (polyglotic-hq 373, version 8): pinned (a click) and on hover;
    `pinned_since_known`: pinned lookups since the learner last said they
    know it."""

    entry_id: str
    pinned: int
    hovered: int
    last_at: datetime
    pinned_since_known: int = 0


class StoredExposures(NamedTuple):
    """How many finished captions an entry was heard in: from what the PC
    played (`heard`), from the user's own mic (`heard_by_you`), and from
    the PC since it last went into the deck (`heard_in_deck`).

    A named tuple, not a dataclass like the rest: there's one for every
    word met, all read at start - 30,000 for a long-time learner - and a
    frozen dataclass takes about three times as long to make
    (polyglotic-hq 314)."""

    entry_id: str
    heard: int
    heard_by_you: int
    heard_in_deck: int
    first_heard: date | None = None
    """The UTC day it was first heard from what the PC played; None if not,
    or before the app kept it."""


@dataclass(frozen=True)
class StoredCoverage:
    """A UTC day's coverage: the tokens of its finished captions from what
    the PC played that were known (names included), in the deck and new
    as each caption finished - or a change to them (negative when a join
    or a withdrawal takes a caption's back). Never sent anywhere."""

    day: date
    known: int
    deck: int
    new: int


@dataclass(frozen=True)
class StoredListening:
    """Seconds of listening with captions on, on a UTC day, from a source
    category (`browser`, `video`, `call`, `game`, `music`, `system`,
    `other`) - or seconds to add to them. Never sent anywhere."""

    day: date
    category: str
    seconds: float


class StoredLoadWord(NamedTuple):
    """A word the learning load keeps (polyglotic-hq 324;
    `core.learning.load`): whether it is in the load (`standing`: `in`,
    `waiting`, `set_aside`, `graduated`), its stage (0 red, 1 orange, 2
    yellow, 3 green, 4 ready to check), the meetings in that stage,
    whether the learner added it by hand, its place on the words scale
    when it entered, and when it entered, last counted a meeting and graduated
    (UTC). Never sent anywhere.

    A named tuple: a load is 500 of them, read at start."""

    entry_id: str
    standing: str
    stage: int
    meetings: int
    by_hand: bool
    place: int | None
    entered_at: datetime
    last_met: datetime | None = None
    graduated_at: datetime | None = None


@dataclass(frozen=True)
class LearningSnapshot:
    """Everything stored, as read at start. `level` is None until the
    learner has picked one (first run)."""

    level: StoredLevel | None
    statuses: Sequence[StoredStatus]
    categories: Sequence[StoredCategory]
    saved_words: Sequence[StoredSavedWord]
    exposures: Sequence[StoredExposures]
    deck_words: Sequence[StoredDeckWord] = ()
    anki_exports: Sequence[StoredAnkiExport] = ()
    coverage: Sequence[StoredCoverage] = ()
    listening: Sequence[StoredListening] = ()
    load_words: Sequence[StoredLoadWord] = ()
    lookups: Sequence[StoredLookups] = ()


class LearningDataProblem(StrEnum):
    """Why the learning data file couldn't be read (polyglotic-hq 206).
    Content-free: the log and `--check-install`'s report carry it as it
    is."""

    DAMAGED = "damaged"
    """Not readable as SQLite, or SQLite's own check finds it damaged: cut
    off, or overwritten in places."""
    NOT_LEARNING_DATA = "not_learning_data"
    """A SQLite file, but not the app's learning data."""
    FOLDER = "folder"
    """A folder where the file should be."""


@dataclass(frozen=True)
class SetAsideLearningData:
    """A learning data file that couldn't be read, renamed aside - never
    deleted or written over - with a new one started in its place
    (polyglotic-hq 206)."""

    path: Path
    """Where it's kept now, beside the new one:
    `learning.sqlite.damaged-<UTC time>`."""
    problem: LearningDataProblem


class LearningStore(Protocol):
    """Where the learner's learning data is kept on the PC."""

    def load(self) -> LearningSnapshot:
        """Everything stored that can be read. A new store holds no level
        and nothing else. A row that can't be read - garbled, or with a
        value this app doesn't know - is left out and kept as it is
        (polyglotic-hq 207); a store with more of them than a few garbled
        rows explain is refused, by raising."""
        ...

    def save_level(self, level: StoredLevel) -> None: ...

    def clear_level(self) -> None:
        """No level kept any more - the learner took back a quick mark
        made before they set one (polyglotic-hq 342): `load` reads None,
        and so does a store started again."""
        ...

    def save_status(self, status: StoredStatus) -> None:
        """Adds or replaces the entry's status."""
        ...

    def save_category(self, category: StoredCategory) -> None:
        """Adds or replaces the category."""
        ...

    def delete_category(self, category_id: str) -> None:
        """Deletes the category and every word saved in it."""
        ...

    def save_word(self, word: StoredSavedWord) -> None:
        """Adds or replaces the saved word."""
        ...

    def delete_word(self, entry_id: str) -> None: ...

    def save_deck_word(self, word: StoredDeckWord) -> None:
        """Adds or replaces the entry's deck word."""
        ...

    def delete_deck_word(self, entry_id: str) -> None: ...

    def save_anki_exports(self, exports: Iterable[StoredAnkiExport]) -> None:
        """Adds or replaces these entries' export times."""
        ...

    def save_load_words(self, words: Sequence[StoredLoadWord]) -> None:
        """Adds or replaces these words of the learning load, together."""
        ...

    def delete_load_words(self, entry_ids: Sequence[str]) -> None:
        """Deletes these words of the learning load."""
        ...

    def save_lookups(self, lookups: StoredLookups) -> None:
        """Adds or replaces a word's lookups (polyglotic-hq 373)."""
        ...

    def forget_entry(self, entry_id: str) -> None:
        """Deletes the entry's status, saved word, deck word, export time,
        exposure counts, lookups and its place in the learning load (not
        its daily counts) - for an entry merged into another, once its data
        has been saved under the new ID."""
        ...

    def save_exposures(
        self, counts: Sequence[StoredExposures], daily: Mapping[date, Mapping[str, int]]
    ) -> None:
        """Replaces these entries' counts, and adds `daily` - per UTC date,
        per entry, a change in the number of captions it was heard in from
        what the PC played (not the mic) - to the daily counts kept for
        sharing, if the learner opts in (protocol.md's `exposures`)."""
        ...

    def daily_exposures(self, day: date) -> Mapping[str, int]:
        """The daily counts for `day` (UTC), per entry; entries at 0 left out."""
        ...

    def exposure_days(self) -> Sequence[date]:
        """The UTC dates daily counts are kept for, oldest first."""
        ...

    def days_to_hand_over(self) -> Sequence[date]:
        """The UTC dates with daily counts not handed over yet, oldest first."""
        ...

    def mark_handed_over(self, days: Iterable[date]) -> None:
        """These days' counts were handed over (shared if the learner opted
        in): kept, and not handed over again."""
        ...

    def forget_daily_exposures(self, days: Iterable[date]) -> None:
        """Deletes these days' daily counts, and that they were handed over
        (once they're 8 weeks old)."""
        ...

    def add_coverage(self, changes: Iterable[StoredCoverage]) -> None:
        """Adds each change to its day's coverage (a day not kept yet starts
        at 0)."""
        ...

    def add_listening(self, listened: Iterable[StoredListening]) -> None:
        """Adds the seconds to their day's and category's (a day not kept yet
        starts at 0)."""
        ...

    def delete_learning_data(self) -> None:
        """Deletes every status, saved word, deck word, export time, exposure
        count, daily count, day's coverage and listening, lookup count, and
        the learning load's words - the learner
        deleted their learning data. The level and the categories stay.
        None of what's deleted stays readable in the store's files, and any
        copy of the store set aside after damage (`SetAsideLearningData`) is
        deleted whole: it holds the same data (polyglotic-hq 207)."""
        ...
