"""Words - today's Vocabulary, renamed (polyglotic-hq project 109's
structure, section 7; 049) - as plain Python, no Qt: what a word's row
shows, which rows a search finds, the learner's level in words, and the
page's sections, one per language learned (`language_groups`).

Every word comes from Learning (`Vocabulary`) and the dictionary, through
what `main` hands over (`WordsLearner`: today's learning tools). A row's
text is looked up only when the row is shown (`WordRows`), so a long list
costs nothing until it is scrolled to.
"""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from polyglotic_desktop.core.learning.levels import KnownLine
from polyglotic_desktop.core.learning.saved_words import SavedWord
from polyglotic_desktop.core.learning.vocabulary import EntryText, Vocabulary
from polyglotic_desktop.core.lexicon.entries import SCHEMES
from polyglotic_desktop.core.shared import EntryId
from polyglotic_desktop.ports.anki_deck import AnkiDeckWriter

MAX_ROWS = 300
"""Words listed at once (today's): filter or search for the rest."""
YOUR_WORDS_ROWS = 8
"""Your words lists this many until Show all - the search finds the rest.
Every word met, listed, ran the page's length (the user, polyglotic-hq
250: "only need to show several lines")."""
SAVED_WORDS_ROWS = 8
"""Saved words lists this many until Show all. Every saved word, listed,
ran the page's length as Your words had (polyglotic-hq 258, the user's
F24 in 250)."""
KEEP_HEARING_FIRST = 5
"""Words you keep hearing lists this many first; each Show more adds
`KEEP_HEARING_STEP` (up to `MAX_ROWS`). Twenty at once was a long list
before Your words (the user, polyglotic-hq 250: "should have a show more
button")."""
KEEP_HEARING_STEP = 10


class WordsLearner(Protocol):
    """What Words needs of the learning tools (`ui.learning.LearningTools`,
    handed over by `main`)."""

    @property
    def vocabulary(self) -> Vocabulary: ...

    @property
    def is_chinese(self) -> bool: ...

    @property
    def language(self) -> str:
        """The language these words are in: `zh`, `en`, or a pack
        language's code (`ru`; decision 0175)."""
        ...

    @property
    def deck_writer(self) -> AnkiDeckWriter | None: ...

    @property
    def reading_ahead(self) -> bool:
        """What Words reads for every word met is being read at the start:
        Words says so until it's back (polyglotic-hq 220)."""
        ...

    def describe(self, entry_id: EntryId) -> EntryText | None:
        """A word's text from the dictionary - read ahead for every word met
        at the start, so a search reads nothing (polyglotic-hq 220)."""
        ...

    def band_sizes(self) -> tuple[list[int], Mapping[int, int]]: ...


@dataclass(frozen=True, slots=True)
class WordText:
    """A word's row: the headword, its other form (traditional, or none),
    the reading and a short meaning."""

    headword: str
    other: str
    reading: str
    meaning: str

    def matches(self, query: str) -> bool:
        """`query` (lower case, trimmed) is in the word, its other form, the
        reading or the meaning; an empty one matches everything."""
        if not query:
            return True
        return any(
            query in text.lower()
            for text in (self.headword, self.other, self.reading, self.meaning)
        )

    @property
    def search_text(self) -> str:
        """What a search looks in: the four, in lower case, a line each. A
        query without a line break is in it just when it `matches`: it can
        only be found within one line, and each line is part of one text."""
        return SEARCH_LINES.join(
            (self.headword, self.other, self.reading, self.meaning)
        ).lower()


SEARCH_LINES = "\n"
"""Between a word's texts in its `WordText.search_text`."""


def word_text(text: EntryText | None, saved: SavedWord | None) -> WordText | None:
    """The dictionary's text for a word (`WordsLearner.describe`), or what
    was kept when it was saved (the dictionary may have dropped it); None if
    neither has it."""
    if text is not None:
        return WordText(text.headword, text.traditional, text.reading, text.meaning)
    if saved is not None:
        return WordText(saved.headword, saved.traditional, saved.reading, saved.meaning)
    return None


class WordRows:
    """Rows of words, each one's text looked up the first time it is asked
    for and kept (a dictionary entry doesn't change while the app runs) -
    and, once searched, each word's `search_text`: one look per word, not
    four (polyglotic-hq 220)."""

    def __init__(self, text: Callable[[EntryId], WordText | None]) -> None:
        self._text = text
        self._known: dict[EntryId, WordText | None] = {}
        self._searched: dict[EntryId, str] = {}

    def text(self, entry_id: EntryId) -> WordText | None:
        if entry_id not in self._known:
            self._known[entry_id] = self._text(entry_id)
        return self._known[entry_id]

    def found(self, entry_ids: Sequence[EntryId], query: str) -> list[EntryId]:
        """The words `query` finds, in order - every word with text if the
        query is empty (looked up only when shown)."""
        query = query.strip().lower()
        if not query:
            return list(entry_ids)
        if SEARCH_LINES in query:  # pasted: could span two of a word's texts
            return [
                entry_id
                for entry_id in entry_ids
                if (text := self.text(entry_id)) is not None and text.matches(query)
            ]
        searched, found = self._searched, []
        for entry_id in entry_ids:
            search_text = searched.get(entry_id)
            if search_text is None:
                text = self._known.get(entry_id) or self._text(entry_id)
                search_text = searched[entry_id] = text.search_text if text else ""
            if query in search_text:
                found.append(entry_id)
        return found


@dataclass(frozen=True, slots=True)
class LanguageGroup:
    """A language's section of Words: open or not, and whether it opens and
    closes at all."""

    language: str
    open: bool
    folds: bool


def language_groups(
    languages: Sequence[str], opened: Mapping[str, bool]
) -> list[LanguageGroup]:
    """Words' sections, one per language learned, in order (polyglotic-hq
    250, the user's F23). With one, it's simply open: nothing to fold. With
    several, each opens and closes and stays as the learner left it
    (`opened`, kept between runs); one never touched is open if it's the
    first - the language learned now - and closed otherwise (polyglotic-hq
    248: one language open at a time to start with)."""
    if len(languages) <= 1:
        return [LanguageGroup(language, True, False) for language in languages]
    return [
        LanguageGroup(language, opened.get(language, n == 0), True)
        for n, language in enumerate(languages)
    ]


@dataclass(frozen=True, slots=True)
class LevelLine:
    """The learner's level as Words says it: not picked; a scheme just
    starting; or a scheme and a level's name. `scheme` is the scheme's
    name (or its ID, if it isn't one this version knows)."""

    picked: bool
    scheme: str = ""
    level: str = ""
    """The level's name; empty: just starting (or the scheme unknown)."""
    words: int | None = None
    """A line said in words (polyglotic-hq 323): about this many of the
    most common ones; None for a level of a scheme."""


def level_line(line: KnownLine | None) -> LevelLine:
    if line is None:
        return LevelLine(False)
    if not line.by_level:
        return LevelLine(True, words=line.known)
    scheme = SCHEMES.get(line.scale)
    level = line.known
    if scheme is None:
        return LevelLine(True, line.scale, str(level))
    if level == 0:
        return LevelLine(True, scheme.name)
    return LevelLine(
        True, scheme.name, scheme.levels[min(level, len(scheme.levels)) - 1]
    )
