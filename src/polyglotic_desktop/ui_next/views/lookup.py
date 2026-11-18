"""W3, the lookup, as plain Python: what the card shows and what its
actions do (polyglotic-hq project 109's structure, section 6; project 113).

`Lookup` is the card's model (109's `LookupModel`): the word looked up and
its context, hover or pinned, the parts drilled into (Back returns), and
the commands - Add to deck, Known, Save to a category (or a new one),
Remove, a part, Back, Close. `card()` is what the card shows now, as
facts (`Card`); the words around them are the card's, through Qt's
translations. Today's content (`ui.lookup`), in 109's shape:
- **hover**: the headword, its reading, its status and its first sense -
  no actions;
- **pinned** (a click, or a drag across a phrase): up to `READINGS`
  readings with up to `SENSES` senses each ("+N more readings"), measure
  words, chengyu, the saved category, "heard in N captions", the actions,
  the parts ("Inside this word", each a click away - Back returns) and
  the context line: the caption's row and its translation;
- **not in the dictionary**: for Chinese, a best-guess reading and the
  words' meanings joined ("Not in the dictionary as a whole - ..."), with
  its words and characters; otherwise "Not in the dictionary";
- **an English word in a Chinese learner's caption**: "Chinese for it";
- **the learner's dictionary out** (missing or damaged on the PC;
  polyglotic-hq 199): the word, and what's wrong - the card says how to
  fix it. A basic dictionary's words are still looked up.

A word is looked up in its row's own full dictionary when that language
is learned - main or added - and reported, put in the deck and saved in
that language's learning data, with its categories (DECISIONS #110,
decision 0095): a Chinese row in CC-CEDICT, an English one in ECDICT.

A pinned word in a language not being learned, with a dictionary, asks
once (`LanguagesOffer`; DECISIONS.md #65, polyglotic-hq 262): "Learn
Japanese too" adds it to Learning's list; "Not now" isn't asked again.

A word looked up in a finished caption line says what it is in the
translation shown with that line - "Here: ngân hàng" (polyglotic-hq 328,
326's stage 1): first under the word, hovered or pinned, whatever kind
of card; the main content where the row's language has no dictionary.
From the line's word links (`with_counterpart`): nothing read, nothing
sent, nothing kept - not with a saved word, not in Anki, not in the
learning events.

Every lookup shown is reported to Learning (`Vocabulary.looked_up`); a
pinned one is evidence the learner doesn't know the word (as today). A
command returns the entry it changed, so the caption windows repaint only
the captions holding it.

`copy_text`: what the card's Copy puts on the clipboard - the word, its
readings and senses (polyglotic-hq 333).

`place`: where the card goes - above the word, centred on it; below when
there's no room above; never over the row being read; on the work area.

Holds caption text (the context): never log it.
"""

import re
import unicodedata
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import Protocol

from polyglotic_desktop.core.learning.knowledge import Knowledge
from polyglotic_desktop.core.learning.languages import Tier, learned_code, tier_of
from polyglotic_desktop.core.learning.levels import LanguageChoices
from polyglotic_desktop.core.learning.load import Stage
from polyglotic_desktop.core.learning.lookups import LookupContext
from polyglotic_desktop.core.learning.saved_words import Category
from polyglotic_desktop.core.learning.vocabulary import EntryText, Vocabulary
from polyglotic_desktop.core.lexicon import compounds
from polyglotic_desktop.core.lexicon.basic import BasicDictionary
from polyglotic_desktop.core.lexicon.chinese import ChineseDictionary, has_han, is_han
from polyglotic_desktop.core.lexicon.english import (
    EnglishDictionary,
    inside_sentence,
    names_first,
)
from polyglotic_desktop.core.lexicon.entries import DictionaryEntry
from polyglotic_desktop.core.lexicon.meanings import (
    definitions,
    meaning_of,
    short_meaning,
)
from polyglotic_desktop.core.listening.display import CaptionRow, counterpart
from polyglotic_desktop.core.listening.history import Caption
from polyglotic_desktop.core.shared import EntryFacts, EntryId, WordInLine, WordStatus
from polyglotic_desktop.ports.dictionary import DictionaryProblem
from polyglotic_desktop.ui_next.views.placement import Rect, Size

READINGS = 3
"""Readings (dictionary entries) a pinned card shows; the rest are counted."""
SENSES = 3
"""Senses shown per reading."""
PARTS = 8
"""Parts, or Chinese words for an English one, a pinned card lists."""
HOVER_CHINESE_FOR = 3
CHINESE_FOR_ROWS = frozenset({"en", "zh", "yue"})
"""The rows whose words without a Han character get "Chinese for it" - a
search of CC-CEDICT's English meanings: English's, and a Latin word on a
Chinese line ("OK", "iPhone"). A word on another language's line isn't
English: on a Vietnamese line "ngân" (silver, a bank's first syllable)
matched a name's meaning and showed 阮晋勇 (polyglotic-hq 329). Such a
word says its language has no dictionary here instead."""
GAP = 6
"""Pixels between the card and the row it's about."""
MARGIN = 8
"""Pixels the card keeps from the work area's edges."""


_POS = re.compile(r"^\([^)]*\)\s*")
"""A basic pack's part of speech before a meaning: "(noun) house"."""
_STRESS = ("\u0301", "\u0300")  # Russian's stress marks: combining accents


def said(entry: DictionaryEntry) -> str:
    """An entry's headword and how it's said, for the line naming the entry
    an inflected form belongs to: "saber  /saˈbeɾ/", "食べる  たべる". A
    reading that is the headword with its stress marked is said once:
    "рука́", not "рука  рука́"."""
    marked = unicodedata.normalize("NFD", entry.reading)
    for mark in _STRESS:
        marked = marked.replace(mark, "")
    plain = unicodedata.normalize("NFC", marked)
    if entry.reading and all(p == entry.headword for p in plain.split(", ")):
        return entry.reading
    return f"{entry.headword}  {entry.reading}".strip()


class Learner(Protocol):
    """What the lookup and the caption windows' marks need of the learning
    tools (`ui.learning.LearningTools`, handed over by `main`): the
    learner's vocabulary, the dictionary and the word split - the main
    language's, and through `of` each other full language's learned
    (DECISIONS #110, decision 0095)."""

    @property
    def vocabulary(self) -> Vocabulary: ...

    @property
    def dictionary(
        self,
    ) -> ChineseDictionary | EnglishDictionary | BasicDictionary: ...

    @property
    def choices(self) -> LanguageChoices:
        """What the learner chose for this language: the learning
        window's size, and which words are linked (polyglotic-hq 323)."""
        ...

    def choices_of(self, language: str | None) -> LanguageChoices | None:
        """What the learner chose for a row in `language`, whatever its
        dictionary; None if it isn't a language they learn."""
        ...

    @property
    def ready(self) -> bool:
        """Whether the word split can answer without reading the dictionary
        first (`ChineseDictionary.ready`): until then, marks that need it
        wait for `dictionary_ready` rather than the interface thread."""
        ...

    def of(self, language: str | None) -> "Learner":
        """The learner for a row in `language`: its own full language's
        dictionary and learning data if it's learned too, else these."""
        ...

    def word_language(self, word: str, language: str | None) -> str | None:
        """The language `word`, in a row in `language`, is looked up in: the
        full language its script says, where that's learned too - an
        English word in a Chinese row - else the row's (polyglotic-hq 337)."""
        ...

    def found_in(
        self, word: str, language: str | None, fallbacks: Sequence[str] = ()
    ) -> str | None:
        """The first language whose dictionary has `word`, of: its own
        script's (learned), the row's (`language`), `fallbacks` (the
        window's translation target and second language), then every other
        learned one whose writing fits it - None if none has it
        (polyglotic-hq 337)."""
        ...

    def words_in(
        self,
        line: str,
        language: str | None = None,
        said: Iterable[tuple[int, int, str]] = (),
    ) -> list[WordInLine]:
        """The words of a line in `language`; `said`: what a translation
        says for words of it - a word it writes by its sound is a name
        (polyglotic-hq 496)."""
        ...

    def has_dictionary(self, language: str | None) -> bool:
        """Whether a word in `language` can be looked up here: its full
        dictionary is open, or its basic pack is."""
        ...

    def learns(self, language: str | None) -> bool:
        """Whether a row in `language` is in the language being learned -
        the only rows Learning marks."""
        ...

    def word_at(
        self, line: str, index: int, language: str | None = None
    ) -> tuple[int, int] | None: ...

    def lookup(self, word: str, language: str | None = None) -> list[DictionaryEntry]:
        """The entries for `word` from a row in `language` (None: the
        learner's dictionary)."""
        ...

    def is_basic(self, language: str | None) -> bool:
        """Whether a row in `language` is looked up in a pack whose
        language isn't learned: a lookup only, kept out of the learner's
        data. A pack's language learned has its own learner (`of`;
        decision 0175)."""
        ...

    def knowledge_of(self, language: str | None) -> Knowledge | None:
        """What the learner knows in a row's `language`: the one answer per
        word (polyglotic-hq 373) - None where no dictionary here knows its
        words."""
        ...

    def form_reading(self, word: str, language: str | None = None) -> str:
        """How `word` itself is said, where a basic dictionary marks it
        apart from its entry (Russian: "руку" is "ру́ку"), else ""."""
        ...

    def parts(self, word: str, language: str | None = None) -> list[compounds.Part]:
        """The words a word a basic dictionary hasn't got is made of
        (Blog-Erfahrung; Internetmaterialien), else [] (polyglotic-hq 390)."""
        ...

    def facts(self, entry: DictionaryEntry) -> EntryFacts: ...

    def add_to_load(self, entry_id: EntryId) -> bool:
        """One word into the learning load by hand (polyglotic-hq 324)."""
        ...

    @property
    def dictionary_problem(self) -> DictionaryProblem | None:
        """Why the learner's dictionary is out (None: it answers)."""
        ...


class LanguagesOffer(Protocol):
    """What the card asks of the languages being learned (`main`'s, kept in
    the settings): which language a pinned word's row offers to learn too,
    and the two answers."""

    def asks_about(self, caption_language: str | None) -> str | None:
        """The language to ask about for a row in `caption_language` (a
        learned language's code), or None."""
        ...

    def learn_too(self, code: str) -> None: ...

    def not_now(self, code: str) -> None: ...

    def pack_size(self, code: str) -> int:
        """The download of `code`'s dictionary pack, in bytes, if Learning
        offers one (decision 0122); 0 when there's none to download."""
        ...


class Shows(StrEnum):
    """What kind of card it is."""

    ENTRY = "entry"
    NOT_FOUND = "not_found"
    CHINESE_FOR = "chinese_for"
    """An English word in a Chinese learner's caption: Chinese words for it."""
    DICTIONARY_OUT = "dictionary_out"
    """The learner's dictionary is out: what's wrong (`Card.problem`)."""
    NO_DICTIONARY = "no_dictionary"
    """A word the learner's dictionary hasn't got, in a row whose language
    has no dictionary on this PC yet (Thai; Japanese without its pack):
    said so, not "not in the dictionary" (polyglotic-hq 248's 3.3, 262).
    Also one in a row whose full dictionary isn't open (Chinese, not
    learned, while English is - the first run asks no language, 293): it
    opens once that language is learned too."""


class PartsTitle(StrEnum):
    INSIDE = "inside"  # "Inside this word"
    WORDS_AND_CHARACTERS = "words_and_characters"  # not in the dictionary
    CHINESE_FOR = "chinese_for"  # "Chinese for it"


@dataclass(frozen=True)
class Reading:
    """One dictionary entry's reading (pinyin, or IPA as "/.../" after the
    entry's word when it isn't the word looked up), senses and measure
    words."""

    reading: str
    senses: tuple[str, ...]
    measure_words: tuple[str, ...] = ()


@dataclass(frozen=True)
class Part:
    """A word inside the one looked up (or a Chinese word for an English
    one): a click looks it up. `reading` and `meaning` are "" when the
    dictionary hasn't got it."""

    word: str
    reading: str
    meaning: str


@dataclass(frozen=True)
class Card:
    """What the card shows (`Lookup.card`)."""

    word: str
    shows: Shows
    pinned: bool
    traditional: bool = False
    """The word is a traditional form (its headword font)."""
    other: str = ""
    """The word's other form: traditional or simplified."""
    simplified: tuple[str, ...] = ()
    """Where a Chinese word that isn't written in Simplified is found in
    Simplified, best first (polyglotic-hq 439): its first entry's headword -
    the reading the card shows first - then the Traditional converter's
    form. A recorded word is kept under its Simplified form (decision
    0197), so a Traditional learner's card plays that recording. () for a
    word read as written (`Lookup._simplified`)."""
    base: str = ""
    """An inflected English word's entry ("ran" counts for "run")."""
    chengyu: bool = False
    status: WordStatus | None = None
    saved_in: Category | None = None
    readings: tuple[Reading, ...] = ()
    more_readings: int = 0
    guess: str = ""
    """Not in the dictionary (Chinese): a best-guess reading."""
    meaning: str = ""
    """Not in the dictionary (Chinese): its words' meanings joined."""
    heard: int = 0
    load_stage: Stage | None = None
    """Its stage in the learning load, while the mode is on and it is in
    it (polyglotic-hq 324), with its meetings in that stage of those a
    stage takes; `load_offer`: it isn't in it and could be added."""
    load_heard: int = 0
    load_step: int = 0
    load_offer: bool = False
    parts_title: PartsTitle | None = None
    parts: tuple[Part, ...] = ()
    categories: tuple[Category, ...] = ()
    back_to: str = ""
    """The word Back returns to; "" for none."""
    context: LookupContext | None = None
    found_at: tuple[int, int] | None = None
    """Where the word is in the context's sentence."""
    basic: bool = False
    """From a dictionary pack (decision 0035): marked so - open data, its
    meanings checked by no person. Its language learned, the card has a
    status and the actions like any entry (decision 0175); not learned,
    nothing to do with it but read."""
    language: str | None = None
    """A pack's language (for its script's font); None for Chinese's and
    English's own dictionaries."""
    problem: DictionaryProblem | None = None
    """Why the learner's dictionary is out (`Shows.DICTIONARY_OUT`)."""
    offer: str = ""
    """A language this word's row is in that isn't being learned: "Learn
    it too?" (its code; "" for none)."""
    added: str = ""
    """The language just added from this card (its code): said once."""
    added_pack: int = 0
    """Its dictionary's download, in bytes, offered on Learning (0: none)."""
    counterpart: str = ""
    """What the word is in its line's translation - "Here: ngân hàng"
    (polyglotic-hq 328) - hovered or pinned, whatever else the card
    shows; "" for none, and for a part looked into (Back returns it)."""
    counterpart_language: str = ""
    """The counterpart's language code, for its font ("" if unknown)."""
    answered_by: str = ""
    """The language whose dictionary answered, when it isn't the row's -
    "From the English dictionary" (polyglotic-hq 337); "" when it is, and
    for a part looked into."""

    @property
    def actions(self) -> bool:
        """The actions show: pinned, on an entry of a language learned -
        one with a status (a pack's word in a language not learned has
        none)."""
        return self.pinned and self.shows is Shows.ENTRY and self.status is not None

    @property
    def known(self) -> bool:
        return self.status is WordStatus.KNOWN

    @property
    def in_deck(self) -> bool:
        return self.status is WordStatus.LEARNING


def copy_text(card: Card) -> str:
    """What the card's Copy puts on the clipboard (polyglotic-hq 333): the
    word (and its other form), then each reading the card shows with its
    senses, one a line - "yín háng: bank; banking". Plain text to paste
    anywhere, without the card's own words. Holds a word: never log it."""
    lines = [f"{card.word} {card.other}" if card.other else card.word]
    for reading in card.readings:
        line = ": ".join(p for p in (reading.reading, "; ".join(reading.senses)) if p)
        if line:
            lines.append(line)
    return "\n".join(lines)


@dataclass(frozen=True)
class WordAt:
    """A word (or a phrase dragged across) in a caption window, to look up:
    the text, its context - the caption's row and its translation - where
    it is in the row (`at`), and where it is on the screen (`rect`), in
    which row (`row`), on which work area (`area`). `key`: the caption's
    line key, the row and `at` - the same word again is the same key."""

    word: str
    context: LookupContext
    at: tuple[int, int]
    rect: Rect
    row: Rect
    area: Rect
    key: tuple[int, int, int, int]
    language: str | None = None
    """The row's language, if known - it picks a basic dictionary."""
    fallbacks: tuple[str, ...] = ()
    """The window's translation target and second language: dictionaries
    tried after the row's (polyglotic-hq 337)."""


def with_counterpart(
    context: LookupContext,
    caption: Caption | None,
    rows: Sequence[CaptionRow],
    index: int,
    span: tuple[int, int],
) -> LookupContext:
    """`context` with the counterpart of the word at `span` in `rows[index]`
    (`caption`'s rows as a caption window or transcript shows them): what
    the card's "Here:" line says (polyglotic-hq 328). From what the caption
    already holds - nothing read, nothing sent."""
    found = counterpart(caption, rows, index, span) if caption is not None else None
    if found is None:
        return context
    return replace(
        context, counterpart=found.words, counterpart_language=found.language or ""
    )


@dataclass
class _Shown:
    word: str
    context: LookupContext
    at: tuple[int, int] | None
    history: list[str] = field(default_factory=list)
    language: str | None = None
    """The language it's looked up in (`Lookup.show`)."""
    added: str = ""
    answered_by: str = ""
    """That language, when its dictionary has the word and it isn't the
    row's (`Card.answered_by`)."""


class Lookup:
    """The lookup card's model: what's looked up, and its commands."""

    def __init__(self, learner: Learner, offer: LanguagesOffer | None = None) -> None:
        """`offer`: the languages being learned, for "Learn it too?" (none:
        never asked)."""
        self.learner = learner
        self.offer = offer
        self.pinned = False
        self._shown: _Shown | None = None

    @property
    def word(self) -> str:
        return self._shown.word if self._shown else ""

    @property
    def showing(self) -> bool:
        return self._shown is not None

    @property
    def is_chinese(self) -> bool:
        """The word shown is looked up in CC-CEDICT, not ECDICT."""
        return isinstance(self._tools().dictionary, ChineseDictionary)

    def _tools(self) -> Learner:
        """The learner for the word shown: its row's own full language's if
        that's learned too, else the main language's (`Learner.of`) - so a
        word is looked up, reported and saved in its own language's
        dictionary and learning data (DECISIONS #110)."""
        shown = self._shown
        return self.learner.of(shown.language if shown is not None else None)

    # -- what's looked up ---------------------------------------------------------------

    def show(
        self,
        word: str,
        context: LookupContext,
        pinned: bool,
        at: tuple[int, int] | None = None,
        language: str | None = None,
        fallbacks: Sequence[str] = (),
    ) -> None:
        """`word`, from a caption row (`context`; at `at` in its sentence;
        in `language` if known), shown on hover or pinned - from the first
        dictionary that has it (`Learner.found_in`): its own script's
        language's if learned, the row's, the window's translation
        languages (`fallbacks`), then any other learned one it fits
        (polyglotic-hq 337). None has it: the row's, or its script's
        (`word_language`), says so."""
        found = self.learner.found_in(word, language, fallbacks)
        row = learned_code(language or "")
        answered = (
            learned_code(found)
            if found is not None and learned_code(found) != row
            else ""
        )
        chosen = (
            found if found is not None else self.learner.word_language(word, language)
        )
        self._shown = _Shown(word, context, at, language=chosen, answered_by=answered)
        self.pinned = pinned
        self._report()

    @property
    def basic(self) -> bool:
        """The word shown is looked up in a pack whose language isn't
        learned: nothing is reported or kept."""
        return self._shown is not None and self.learner.is_basic(self._shown.language)

    @property
    def from_pack(self) -> bool:
        """The word shown is looked up in a dictionary pack - its language
        learned or not."""
        return self.basic or isinstance(self._tools().dictionary, BasicDictionary)

    def close(self) -> None:
        self._shown = None
        self.pinned = False

    def part(self, index: int) -> None:
        """Looks up the card's `index`th part (or Chinese word) - Back
        returns. The context stays the line it was found in."""
        parts = self.card().parts
        if self._shown is None or not 0 <= index < len(parts):
            return
        self._shown.history.append(self._shown.word)
        self._shown.word = parts[index].word
        self._report()

    def back(self) -> bool:
        """Back to the word before the part shown; False if there's none."""
        if self._shown is None or not self._shown.history:
            return False
        self._shown.word = self._shown.history.pop()
        return True

    def _report(self) -> None:
        entry = self.entry()
        if entry is not None:
            tools = self._tools()
            tools.vocabulary.looked_up(tools.facts(entry), self.pinned)

    def entry(self) -> DictionaryEntry | None:
        """The entry shown: the word's everyday reading. None from a pack
        whose language isn't learned: nothing of it is reported or kept."""
        if self._shown is None or self.basic:
            return None
        entries = self._entries(self._shown.word)
        return entries[0] if entries else None

    def _entries(self, word: str) -> list[DictionaryEntry]:
        """`word`'s entries in its learner's dictionary. The word shown,
        capitalised inside its sentence, has its names first, as its
        caption counted it ("and Bill said": the name, then bill, 帐单 -
        `names_first`, polyglotic-hq 464)."""
        entries = self._tools().lookup(word)
        shown = self._shown
        if (
            shown is not None
            and not shown.history
            and word == shown.word
            and shown.at is not None
            and inside_sentence(shown.context.sentence, shown.at[0])
        ):
            return names_first(entries, word)
        return entries

    # -- the commands --------------------------------------------------------------------

    def learn_too(self) -> None:
        """ "Learn X too": the language this card asks about is learned too
        (Learning's list), and the card says so."""
        code = self.card().offer
        if code and self.offer is not None and self._shown is not None:
            self.offer.learn_too(code)
            self._shown.added = code

    def not_now(self) -> None:
        """ "Not now": not asked about this language again."""
        code = self.card().offer
        if code and self.offer is not None:
            self.offer.not_now(code)

    def add_to_deck(self) -> DictionaryEntry | None:
        """Into the deck, keeping the line it was in and that line's
        translation (for the Anki file) - or, in it already, out of it
        (back to new). The entry changed, or None."""
        entry = self.entry()
        if entry is None or self._shown is None:
            return None
        vocabulary = self._tools().vocabulary
        if self._status(entry) is WordStatus.LEARNING:
            vocabulary.set_status(entry.entry_id, WordStatus.NEW)
        else:
            vocabulary.learn(entry.entry_id, self._text(entry), self._shown.context)
        return entry

    def load_check(self, knows: bool) -> DictionaryEntry | None:
        """The learning load's check for a word ready to check: "I know
        this" graduates it, "Not yet" sends it back (polyglotic-hq 324)."""
        entry = self.entry()
        if entry is not None:
            self._tools().vocabulary.check_word(entry.entry_id, knows)
        return entry

    def load_add(self) -> DictionaryEntry | None:
        """ "Add to my load"."""
        entry = self.entry()
        if entry is not None:
            self._tools().add_to_load(entry.entry_id)
        return entry

    def known(self) -> DictionaryEntry | None:
        """Known - or, known already, back to new."""
        entry = self.entry()
        if entry is None:
            return None
        known = self._status(entry) is WordStatus.KNOWN
        self._tools().vocabulary.set_status(
            entry.entry_id, WordStatus.NEW if known else WordStatus.KNOWN
        )
        return entry

    def save_to(self, category_id: str) -> DictionaryEntry | None:
        """Saved into a category, or moved there if saved already."""
        entry = self.entry()
        vocabulary = self._tools().vocabulary
        if (
            entry is None
            or self._shown is None
            or vocabulary.category(category_id) is None
        ):
            return None
        text = self._text(entry)
        vocabulary.save(
            entry.entry_id,
            text.headword,
            text.traditional,
            text.reading,
            text.meaning,
            category_id,
            self._shown.context,
        )
        return entry

    def new_category(self, name: str) -> DictionaryEntry | None:
        """A new category, named `name` (numbered if that's taken) in the
        next colour, with the word saved in it - one click, nothing typed:
        the card never takes the keyboard. Renamed on the Words page."""
        if self.entry() is None:
            return None
        vocabulary = self._tools().vocabulary
        taken = {c.name for c in vocabulary.categories}
        named, n = name, 2
        while named in taken:
            named, n = f"{name} {n}", n + 1
        return self.save_to(vocabulary.add_category(named).id)

    def remove(self) -> DictionaryEntry | None:
        """Out of the saved words."""
        entry = self.entry()
        if entry is None:
            return None
        self._tools().vocabulary.unsave(entry.entry_id)
        return entry

    def _status(self, entry: DictionaryEntry) -> WordStatus:
        tools = self._tools()
        return tools.vocabulary.status(tools.facts(entry)).status

    def _text(self, entry: DictionaryEntry) -> EntryText:
        """What the deck and saved words keep of it."""
        dictionary = self._tools().dictionary
        word = self.word
        meaning = (
            meaning_of(dictionary, word)
            if isinstance(dictionary, ChineseDictionary)
            else short_meaning(self._entries(word))
        )
        return EntryText(entry.headword, entry.traditional, entry.reading, meaning)

    # -- what it shows -------------------------------------------------------------------

    def card(self) -> Card:
        """What the card shows now. The learner's dictionary out, it says
        so - not "not in the dictionary", which it can't know. Asked after
        the card's own lookups: one of them may be what finds the file
        damaged (polyglotic-hq 199)."""
        shown = self._shown
        if shown is None:
            return Card("", Shows.NOT_FOUND, False)
        found = self._found(shown)
        if self._no_dictionary(found, shown.language):
            found = Card(
                shown.word,
                Shows.NO_DICTIONARY,
                self.pinned,
                back_to=found.back_to,
                language=learned_code(shown.language or ""),
            )
        problem = self._tools().dictionary_problem
        if problem is not None and not found.basic:
            found = Card(shown.word, Shows.DICTIONARY_OUT, self.pinned, problem=problem)
        if shown.answered_by and not shown.history:
            found = replace(found, answered_by=shown.answered_by)
        if shown.context.counterpart and not shown.history:  # not a part's
            found = replace(
                found,
                counterpart=shown.context.counterpart,
                counterpart_language=shown.context.counterpart_language,
            )
        offer = self.offer
        asked = offer.asks_about(shown.language) if offer and self.pinned else None
        if asked or shown.added:
            size = offer.pack_size(shown.added) if offer and shown.added else 0
            return replace(found, offer=asked or "", added=shown.added, added_pack=size)
        return found

    def _no_dictionary(self, found: Card, language: str | None) -> bool:
        """Nothing found for a word in a row whose language has no
        dictionary here: neither a full one (the learner's, or the other one
        - "Chinese for it" on an English row) nor its basic pack. Or not
        found in a row whose full dictionary isn't open: a full language
        not learned (293). Or a pack language learned whose pack was
        removed: its learning data is open, its dictionary isn't here."""
        nothing = found.shows is Shows.NOT_FOUND or (
            found.shows is Shows.CHINESE_FOR and not found.parts
        )
        if not nothing or language is None:
            return False
        if found.basic:  # a pack's: only one removed since (decision 0175)
            return not self.learner.has_dictionary(language)
        code = learned_code(language)
        if tier_of(code) is not Tier.FULL:
            return True
        looked_in = (
            "zh" if isinstance(self._tools().dictionary, ChineseDictionary) else "en"
        )
        return found.shows is Shows.NOT_FOUND and code != looked_in

    def _found(self, shown: _Shown) -> Card:
        word, pinned = shown.word, self.pinned
        back_to = shown.history[-1] if shown.history and pinned else ""
        if self.from_pack:
            return self._learned(shown, self._basic(word, back_to))
        dictionary = self._tools().dictionary
        if (
            isinstance(dictionary, ChineseDictionary)
            and not has_han(word)
            and (
                shown.language is None
                or learned_code(shown.language) in CHINESE_FOR_ROWS
            )
        ):
            return self._chinese_for(dictionary, word, back_to)
        entries = self._entries(word)
        context = shown.context if pinned and not shown.history else None
        found_at = shown.at if context is not None else None
        if not entries:
            return self._not_found(word, back_to, context, found_at)
        vocabulary = self._tools().vocabulary
        first = entries[0]
        saved = vocabulary.saved_word(first.entry_id)
        limit = READINGS if pinned else 1
        readings = tuple(self._reading(e, word, pinned) for e in entries[:limit])
        title, parts = (None, ()) if not pinned else self._parts(word, found=True)
        load = vocabulary.load
        in_load = load.word(first.entry_id) if pinned and load.rules else None
        if in_load is not None and not in_load.in_load:
            in_load = None
        return Card(
            word,
            Shows.ENTRY,
            pinned,
            traditional=any(
                e.traditional == word and e.headword != word for e in entries
            ),
            other=self._other(word, entries) if has_han(word) else "",
            simplified=self._simplified(word, entries),
            base=self._other(word, entries) if not has_han(word) else "",
            chengyu=any(e.idiom for e in entries),
            status=self._status(first),
            saved_in=vocabulary.category(saved.category_id) if saved else None,
            readings=readings,
            more_readings=max(0, len(entries) - limit) if pinned else 0,
            heard=vocabulary.exposures(first.entry_id).heard if pinned else 0,
            load_stage=in_load.stage if in_load else None,
            load_heard=in_load.meetings if in_load else 0,
            load_step=load.rules.step if load.rules else 0,
            load_offer=(
                pinned
                and load.rules is not None
                and in_load is None
                and vocabulary.could_be_in_load(self.learner.facts(first))
            ),
            parts_title=title,
            parts=parts,
            categories=tuple(vocabulary.categories) if pinned else (),
            back_to=back_to,
            context=context,
            found_at=found_at,
        )

    def _learned(self, shown: _Shown, card: Card) -> Card:
        """A pack's `card` with what the learner keeps of its word, where
        its language is learned (decision 0175): its status, category,
        times heard, place in the learning load and the line it was found
        in - as an entry of Chinese's or English's has them."""
        if self.basic or card.shows is not Shows.ENTRY:
            return card
        entry = self.entry()
        if entry is None:
            return card
        pinned = self.pinned
        tools = self._tools()
        vocabulary = tools.vocabulary
        saved = vocabulary.saved_word(entry.entry_id)
        load = vocabulary.load
        in_load = load.word(entry.entry_id) if pinned and load.rules else None
        if in_load is not None and not in_load.in_load:
            in_load = None
        context = shown.context if pinned and not shown.history else None
        return replace(
            card,
            status=self._status(entry),
            saved_in=vocabulary.category(saved.category_id) if saved else None,
            heard=vocabulary.exposures(entry.entry_id).heard if pinned else 0,
            load_stage=in_load.stage if in_load else None,
            load_heard=in_load.meetings if in_load else 0,
            load_step=load.rules.step if load.rules else 0,
            load_offer=(
                pinned
                and load.rules is not None
                and in_load is None
                and vocabulary.could_be_in_load(tools.facts(entry))
            ),
            categories=tuple(vocabulary.categories) if pinned else (),
            context=context,
            found_at=shown.at if context is not None else None,
        )

    def _basic(self, word: str, back_to: str) -> Card:
        """A word from a dictionary pack: its readings and senses, marked
        basic; no status, deck or categories (`_learned` adds them)."""
        assert self._shown is not None
        entries = self.learner.lookup(word, self._shown.language)
        language = self._shown.language
        if not entries:
            return self._basic_not_found(word, back_to, language)
        limit = READINGS if self.pinned else 1
        first = entries[0]
        # an inflected form: "supe -> saber /saˈber/", the reading the lemma's
        base = said(first) if first.headword != word else ""
        readings = []
        for n, entry in enumerate(entries[:limit]):
            # the reading as the pack has it: kana, IPA with its slashes, or
            # the word with its stress marked
            reading = entry.reading
            if entry.headword != word:
                # the form's own, where the pack marks it ("руку": "ру́ку")
                own = self.learner.form_reading(word, language)
                reading = own if n == 0 else said(entry)
            senses = definitions(entry)[0]
            readings.append(
                Reading(reading, tuple(senses[: SENSES if self.pinned else 1]))
            )
        return Card(
            word,
            Shows.ENTRY,
            self.pinned,
            base=base,
            readings=tuple(readings),
            more_readings=max(0, len(entries) - limit) if self.pinned else 0,
            back_to=back_to,
            basic=True,
            language=language,
        )

    def _reading(self, entry: DictionaryEntry, word: str, pinned: bool) -> Reading:
        senses, measure_words = definitions(entry)
        if self.is_chinese:
            reading = entry.reading
        else:  # IPA; and the entry's word, if it isn't the word looked up
            reading = f"/{entry.reading}/" if entry.reading else ""
            if entry.headword != word:
                reading = f"{entry.headword}  {reading}".strip()
        return Reading(
            reading,
            tuple(senses[: SENSES if pinned else 1]),
            tuple(measure_words) if pinned else (),
        )

    def _basic_not_found(self, word: str, back_to: str, language: str | None) -> Card:
        """A word the basic dictionary hasn't got: not in it as a whole -
        and, if it's made of words it has (a hyphenated word, a German
        compound), their first meanings joined ("internet + material") and,
        pinned, each part (polyglotic-hq 390)."""
        found = [
            (part.form, self.learner.lookup(part.form, language) if part.found else [])
            for part in self.learner.parts(word, language)
        ]
        meaning = " + ".join(
            _POS.sub("", next(iter(definitions(entries[0])[0]), "?"))
            if entries
            else "?"
            for _, entries in found
        )
        parts = tuple(self._basic_part(form, entries) for form, entries in found)
        return Card(
            word,
            Shows.NOT_FOUND,
            self.pinned,
            meaning=meaning if found else "",
            parts_title=PartsTitle.INSIDE if parts else None,
            parts=parts[:PARTS],
            back_to=back_to,
            basic=True,
            language=language,
        )

    @staticmethod
    def _basic_part(form: str, entries: Sequence[DictionaryEntry]) -> Part:
        """A part of a word, from a basic dictionary: the entry's word and
        reading if it isn't the part as written ("Material  /...") - else
        its reading - and its first meanings."""
        if not entries:
            return Part(form, "", "")
        first = entries[0]
        reading = said(first) if first.headword != form else first.reading
        return Part(form, reading, "; ".join(definitions(first)[0][:2]))

    def _simplified(
        self, word: str, entries: Sequence[DictionaryEntry]
    ) -> tuple[str, ...]:
        """`Card.simplified`: the dictionary's own pair first - the entry
        the card shows first, so a Traditional form written for two words
        (乾: 干 "dry", 乾 "heaven") is the word the card is about - then the
        converter's (藉口: CC-CEDICT's own headword, then 借口). A word that
        is a Simplified headword itself (乾 qián, 著 zhù) is read as written
        unless Traditional is shown - the converter writes it."""
        dictionary = self._tools().dictionary
        if not isinstance(dictionary, ChineseDictionary) or not has_han(word):
            return ()
        converted = dictionary.simplified(word)
        if converted == word and any(e.headword == word for e in entries):
            return ()
        forms = (entries[0].headword, *((converted,) if converted != word else ()))
        return () if forms == (word,) else tuple(dict.fromkeys(forms))

    @staticmethod
    def _other(word: str, entries: Sequence[DictionaryEntry]) -> str:
        return next(
            (
                f
                for e in entries
                for f in (e.headword, e.traditional)
                if f and f != word
            ),
            "",
        )

    def _not_found(
        self,
        word: str,
        back_to: str,
        context: LookupContext | None,
        found_at: tuple[int, int] | None,
    ) -> Card:
        dictionary = self._tools().dictionary
        if not isinstance(dictionary, ChineseDictionary):
            return Card(word, Shows.NOT_FOUND, self.pinned, back_to=back_to)
        title, parts = (None, ()) if not self.pinned else self._parts(word, found=False)
        return Card(
            word,
            Shows.NOT_FOUND,
            self.pinned,
            guess=dictionary.pinyin_of(word),
            meaning=meaning_of(dictionary, word),
            parts_title=title,
            parts=parts,
            back_to=back_to,
            context=context,
            found_at=found_at,
        )

    def _parts(
        self, word: str, found: bool
    ) -> tuple[PartsTitle | None, tuple[Part, ...]]:
        """The shorter words and the characters inside a Chinese word."""
        dictionary = self._tools().dictionary
        if not isinstance(dictionary, ChineseDictionary) or len(word) < 2:
            return None, ()
        words = dictionary.parts(word) + list(
            dict.fromkeys(c for c in word if is_han(c))
        )
        if not words:
            return None, ()
        title = PartsTitle.INSIDE if found else PartsTitle.WORDS_AND_CHARACTERS
        return title, tuple(self._part(w) for w in words[:PARTS])

    def _part(self, word: str) -> Part:
        entries = self._tools().lookup(word)
        if not entries:
            return Part(word, "", "")
        readings = " / ".join(dict.fromkeys(e.reading for e in entries[:3]))
        return Part(word, readings, "; ".join(definitions(entries[0])[0][:2]))

    def _chinese_for(
        self, dictionary: ChineseDictionary, word: str, back_to: str
    ) -> Card:
        limit = PARTS if self.pinned else HOVER_CHINESE_FOR
        found = list(
            dict.fromkeys(e.headword for e in dictionary.reverse_lookup(word, limit))
        )
        return Card(
            word,
            Shows.CHINESE_FOR,
            self.pinned,
            parts_title=PartsTitle.CHINESE_FOR,
            parts=tuple(self._part(w) for w in found),
            back_to=back_to,
        )


def place(word: Rect, row: Rect, size: Size, area: Rect) -> tuple[Rect, bool]:
    """Where a card of `size` goes for `word` (on screen), in `row` - the
    row being read - on the work area `area`; and whether it's above.

    Above the row, centred on the word; below the row when there's no room
    above; kept on the work area. If it fits on neither side whole, the
    side with more room, held on the area (it may then cover the row)."""
    x = word.x + word.width // 2 - size.width // 2
    x = min(max(x, area.x + MARGIN), area.right - MARGIN - size.width)
    above = row.y - GAP - size.height
    if above >= area.y + MARGIN:
        return Rect(x, above, size.width, size.height), True
    below = row.bottom + GAP
    if below + size.height <= area.bottom - MARGIN:
        return Rect(x, below, size.width, size.height), False
    if row.y - area.y >= area.bottom - row.bottom:
        return Rect(x, area.y + MARGIN, size.width, size.height), True
    y = max(area.y + MARGIN, area.bottom - MARGIN - size.height)
    return Rect(x, y, size.width, size.height), False
