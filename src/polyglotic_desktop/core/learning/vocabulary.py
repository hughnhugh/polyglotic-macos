"""The learner's vocabulary: their level, word statuses, saved words and
exposures - Learning's rules in one place, kept through the
`LearningStore` port.

The UI and the connection talk to Learning through `Vocabulary`:
- the lookup popup reports lookups, saves words and sets statuses;
- finished captions are counted as exposures and towards the day's
  coverage and listening time, and their highlights asked for (saved
  words, unfamiliar words under the cap, words in the deck);
- the vocabulary page lists statuses, saved words, "words you keep
  hearing", and exports saved words and deck words for Anki.

Learning doesn't know Lexicon (decision 0002): words arrive as
`WordInLine`s, and the facts about entries it needs to list them - level,
rank, name flag - come through `facts`, a function `main` wires to the
dictionary.

Every change is published to listeners: learning data for the server
(`core.shared`'s `LearningEvent`s - entry IDs and times only) and
`VocabularyChanged` for views to redraw. The learning load (`load`: a Lab
viewing mode, polyglotic-hq 324) and our curriculum's active set
(`curriculum`, polyglotic-hq 477) are told of finished captions, statuses
and the line here, and changed through here. The quiet view's chosen
words (`set_chosen`, `chosen`) are kept as the named word set `quiet`,
and every change of a status and of the known line is kept in order
(474's store hooks) - on this PC only. What comes back from the server -
statuses and saved words set on another PC - is applied by
`apply_from_server` without being published again; `delete_learning_data`
empties the learner's data on this PC. Finished days' exposure counts are
handed over once (`take_finished_exposure_days`) for the connection to
share, if the learner opted in, and kept on this PC for
`KEEP_DAILY_WEEKS` (decision 0041). Not thread-safe: use it from one
thread (the UI's).
"""

import uuid
from collections.abc import Callable, Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta
from enum import StrEnum

from polyglotic_desktop.core.learning import exposures as exposure_rules
from polyglotic_desktop.core.learning.anki import (
    AnkiNote,
    anki_csv,
    deck_notes,
    deck_sentences,
    sentence_note,
)
from polyglotic_desktop.core.learning.bands import MetWord
from polyglotic_desktop.core.learning.coverage import (
    RECENT_DAYS,
    Coverage,
    CoverageCounter,
    coverage_of,
)
from polyglotic_desktop.core.learning.curriculum import (
    EDGE_PER_CAPTION,
    ChosenWords,
    Curriculum,
    CurriculumStore,
)
from polyglotic_desktop.core.learning.deck_words import DeckWord
from polyglotic_desktop.core.learning.exposures import (
    ExposureChange,
    ExposureCount,
    ExposureCounter,
)
from polyglotic_desktop.core.learning.highlights import (
    WordIntroductions,
    unfamiliar_words,
)
from polyglotic_desktop.core.learning.knowledge import Knowledge
from polyglotic_desktop.core.learning.known_chance import (
    NO_EVIDENCE,
    Band,
    Evidence,
    KnownChances,
)
from polyglotic_desktop.core.learning.known_map import (
    evidence_then,
    line_then,
    statuses_then,
)
from polyglotic_desktop.core.learning.levels import (
    KnownLine,
    LearningWindow,
    LevelWords,
    WindowSize,
    place,
)
from polyglotic_desktop.core.learning.listening_time import ListeningCounter
from polyglotic_desktop.core.learning.load import LearningLoad, LoadRules, LoadStore
from polyglotic_desktop.core.learning.lookups import (
    DEEP_WITHIN,
    TURNS_NEW_AFTER,
    LookupContext,
    LookupCount,
)
from polyglotic_desktop.core.learning.saved_words import (
    DEFAULT_CATEGORIES,
    NEW_CATEGORY_COLORS,
    Category,
    CategoryId,
    SavedSpan,
    SavedWord,
    SavedWordMatcher,
)
from polyglotic_desktop.core.learning.sentences import (
    Found,
    SavedSentence,
    SentenceId,
    SentenceLink,
    SentencePart,
    SentenceSearch,
    saved_words_in,
)
from polyglotic_desktop.core.learning.statuses import (
    StatusRecord,
    StatusSource,
    estimated_status,
    status_of,
)
from polyglotic_desktop.core.learning.theme import everyday, known_by_speech
from polyglotic_desktop.core.shared import (
    EntryFacts,
    EntryId,
    LearningEvent,
    Level,
    WordInLine,
    WordLookedUp,
    WordSaved,
    WordStatus,
    WordStatusChanged,
    WordUnsaved,
)
from polyglotic_desktop.ports.anki_deck import DeckNote, DeckSentence
from polyglotic_desktop.ports.learning import (
    LearningStore,
    StoredAnkiExport,
    StoredCategory,
    StoredCoverage,
    StoredDeckWord,
    StoredExposures,
    StoredLevel,
    StoredLineChange,
    StoredListening,
    StoredLookups,
    StoredSavedWord,
    StoredSentence,
    StoredSentencePart,
    StoredSetWord,
    StoredStatus,
    StoredStatusChange,
)

KEEP_DAILY_WEEKS = 8
"""Daily counts per entry are kept on this PC this long, then deleted
(decision 0041; polyglotic-hq DECISIONS.md #64 may change it)."""

QUIET_SET = "quiet"
"""The named word set the quiet view's chosen words are kept as (474's
store hooks): what a later learning mode reads."""

FROM_SERVER = "server"
"""A status change's source in the history when it came from the server
(set on another PC, or this one before)."""


class LineSource(StrEnum):
    """How the known line moved, in its history (474)."""

    PICKED = "picked"  # a level picked
    WORDS = "words"  # "I know about N words"
    FIRST_KNOWN = "first_known"  # "Mark the first N words known" (342)
    RESTORED = "restored"  # Undo or Reset after a quick mark


KEEP_HEARING_MIN = 2
"""A word is in "words you keep hearing" once heard in this many captions
(a guess, to tune)."""

FactsLookup = Callable[[EntryId, str], EntryFacts | None]
"""The facts about an entry for a learner in a level scheme (entry ID,
scheme ID) - None if the dictionary no longer has it."""


@dataclass(frozen=True)
class EntryText:
    """What a saved word keeps from its dictionary entry: the headword, its
    traditional form, the reading and a short meaning."""

    headword: str
    traditional: str
    reading: str
    meaning: str


PlacedWords = Callable[[int, int, str], Sequence[tuple[int, EntryFacts]]]
"""The dictionary's words placed past a place on the words scale
(`levels.place`), each with its place, earliest first, about so many, with
their facts in a level scheme (place, limit, scheme ID) - what the
learning load takes in. Empty when there are no more, or for a dictionary
without ranks."""

Describe = Callable[[EntryId], EntryText | None]
"""An entry's text from this PC's dictionary - None if it hasn't got it."""


class Changed(StrEnum):
    LEVEL = "level"
    STATUSES = "statuses"
    SAVED_WORDS = "saved_words"  # saved words or categories
    EXPOSURES = "exposures"  # exposures, or the days' coverage or listening
    LOAD = "load"  # the learning load: its words, their stages, its rules
    SENTENCES = "sentences"  # saved sentences (459)
    CURRICULUM = "curriculum"  # our curriculum's set, or the chosen words (477)


@dataclass(frozen=True)
class VocabularyChanged:
    """Something views show has changed; not sent anywhere. For the
    learning load (`Changed.LOAD`), `entries` are the words whose stage a
    caption shows changed - none when only meetings were counted - or
    None: every word's may have."""

    what: Changed
    entries: frozenset[EntryId] | None = None


Listener = Callable[[LearningEvent | VocabularyChanged], None]


@dataclass(frozen=True)
class LineHighlights:
    """What a line of a finished caption shows: saved words (in their
    category's colour), unfamiliar words, and words in the deck."""

    saved: list[SavedSpan]
    unfamiliar: list[WordInLine]
    in_deck: list[WordInLine]


@dataclass(frozen=True)
class VocabularyRow:
    """A word the learner has met (heard, looked up, saved or set), as the
    vocabulary list shows it."""

    entry_id: EntryId
    status: StatusRecord
    exposures: ExposureCount
    saved: SavedWord | None


@dataclass(frozen=True)
class FactsRead:
    """Words' facts read ahead, in the scheme `scheme`
    (`Vocabulary.facts_to_read`): only those the dictionary had."""

    scheme: str
    found: Mapping[EntryId, EntryFacts]


class AnkiFormat(StrEnum):
    """The kind of file an Anki export writes. Each remembers its own
    exports (polyglotic-hq 368): "only words not exported yet" is the words
    not yet in a file of that kind - a learner who keeps a deck file for
    Anki and a CSV for something else wants each to get every word once,
    and the CSV after a deck file came out empty."""

    DECK = "deck"
    CSV = "csv"


@dataclass(frozen=True)
class AnkiExport:
    """The words for Anki as a CSV file's text and as notes for a deck
    file (same words, same GUIDs), and the entries in them - to mark as
    exported (`Vocabulary.mark_exported`) once the file is written."""

    text: str
    notes: tuple[DeckNote, ...]
    entry_ids: tuple[EntryId, ...]
    """The words' entries, then each saved sentence's `sentence_key`."""
    sentences: tuple[DeckSentence, ...] = ()

    @property
    def counts(self) -> tuple[int, int]:
        """How many words, and how many sentences, it holds."""
        return words_and_sentences(self.entry_ids)


def sentence_key(sentence_id: SentenceId) -> EntryId:
    """A saved sentence as Anki exports remember it, beside the words'
    entries (`Vocabulary.mark_exported`): `sentence:<its ID>`, which no
    dictionary entry ID is (they start with their dictionary's name)."""
    return EntryId(f"sentence:{sentence_id}")


def words_and_sentences(entry_ids: Iterable[EntryId]) -> tuple[int, int]:
    """How many of `entry_ids` are words, and how many sentences
    (`sentence_key`)."""
    ids = tuple(entry_ids)
    sentences = sum(1 for e in ids if e.startswith("sentence:"))
    return len(ids) - sentences, sentences


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _local_day(at: datetime) -> date:
    """The day `at` falls on by the PC's own clock: the learner's day."""
    return at.astimezone().date()


_NEVER = datetime.min.replace(tzinfo=UTC)


@dataclass(frozen=True)
class AnkiWords:
    """What an Anki export is made from, copied from the vocabulary
    (`Vocabulary.anki_words`): the categories' names, the statuses, the
    saved words, the words in the deck, and those to leave out (exported
    already, if only new ones are wanted). Its own copies: made into the
    file on another thread while the vocabulary changes."""

    category_names: Mapping[CategoryId, str]
    statuses: Mapping[EntryId, StatusRecord]
    saved: Mapping[EntryId, SavedWord]
    deck: Mapping[EntryId, DeckWord]
    leave_out: frozenset[EntryId]
    sentences: Sequence[SavedSentence] = ()
    """The saved sentences (polyglotic-hq 459), those exported already left
    out if only new ones are wanted."""

    def export(
        self,
        describe: Describe | None = None,
        pack_language: str | None = None,
        language: str = "",
    ) -> AnkiExport:
        """The saved words and the words in the deck as a CSV file's text
        for Anki (`anki`) and a deck file's notes - a pack language's
        learning data's in that language's note type and sub-deck
        (`pack_language`: its code; None for Chinese's and English's,
        `anki.deck_note`). A word's sentence is the
        line it went into the deck with, else the one it was saved from.
        One put in the deck on another PC has none here, and its text comes
        from `describe` (this PC's dictionary); one `describe` doesn't know
        is left out. A note's `changed` is the latest time of what it's
        made from: the deck word's, the saved word's, or the status's for
        text from `describe`. (A category change isn't counted: the note's
        tags then change only with its word.)"""
        learning = {
            e for e, s in self.statuses.items() if s.status is WordStatus.LEARNING
        }
        notes = []
        for entry_id in sorted(learning | set(self.saved)):
            if entry_id in self.leave_out:
                continue
            saved = self.saved.get(entry_id)
            deck = self.deck.get(entry_id) if entry_id in learning else None
            status = self.statuses.get(entry_id)
            status_at = (status.at if status else None) or _NEVER
            changes = []
            if deck is not None and deck.sentence:
                sentence, translation = deck.sentence, deck.translation
                changes.append(deck.learned_at)
            elif saved is not None:
                sentence, translation = saved.source_sentence, saved.source_translation
                changes.append(saved.saved_at)
            else:
                sentence = translation = ""
            text = saved or deck or (describe(entry_id) if describe else None)
            if text is None:
                continue
            changes.append(
                saved.saved_at if saved else deck.learned_at if deck else status_at
            )
            added = saved.saved_at if saved else None
            if deck is not None:
                added = min(deck.learned_at, added or deck.learned_at)
            notes.append(
                AnkiNote(
                    entry_id,
                    text.headword,
                    text.traditional,
                    text.reading,
                    text.meaning,
                    sentence,
                    translation,
                    self.category_names.get(saved.category_id, "") if saved else "",
                    added or status_at,
                    max(changes),
                )
            )
        saved_words = list(self.saved.values())
        sentences = [
            sentence_note(
                s,
                saved_words_in(s, saved_words),
                self.category_names.get(s.category_id, ""),
            )
            for s in self.sentences
        ]
        return AnkiExport(
            anki_csv(notes, sentences),
            deck_notes(notes, pack_language),
            (
                *(EntryId(n.entry_id) for n in notes),
                *(sentence_key(s.sentence_id) for s in sentences),
            ),
            deck_sentences(sentences, language or pack_language or "en"),
        )


class Vocabulary:
    def __init__(
        self,
        store: LearningStore,
        facts: FactsLookup,
        default_scheme: str,
        clock: Callable[[], datetime] = _utc_now,
        placed: PlacedWords | None = None,
        day_of: Callable[[datetime], date] = _local_day,
        level_words: LevelWords | None = None,
        starting: KnownLine | None = None,
    ) -> None:
        """`default_scheme` is the level scheme for this learner until they
        pick a level (`hsk-2025` for Chinese learners, `en-frequency` for
        English learners). `placed`: the dictionary's words in the order
        of their places, for the learning load (None: no load); `day_of`: the day a
        time falls on for the learner - the PC's own - for meetings
        counted once a day; `level_words`: about how many words a level of
        a scheme stands for, so a line kept as a level places word links
        by how common words are (`needs_no_link`; None: by level alone);
        `starting`: the line words are estimated on until the learner sets
        theirs (None: the scheme's middle level, `KnownLine.starting`) - a
        number of words for a language with no levels (decision 0175)."""
        self._store = store
        self._day_of = day_of
        self._level_words = level_words
        self._window_size: WindowSize | None = None
        """The learning window's size the learner chose for this language
        (`set_window_size`); None: the default."""
        self._starting = starting or KnownLine.starting(default_scheme)
        self._facts = facts
        self._default_scheme = default_scheme
        self._clock = clock
        self._listeners: list[Listener] = []
        self._counter = ExposureCounter()
        self._covering = CoverageCounter()
        self._listening_runs = ListeningCounter()
        self._looked_up: dict[tuple[EntryId, str], EntryFacts | None] = {}
        """Facts read from the dictionary (`_facts_of`): the same while the
        app runs, and each a dictionary read - Words asks for every word
        met at each refresh (polyglotic-hq project 163)."""
        data = store.load()
        self._line = (
            KnownLine.stored(data.level.scheme, data.level.midpoint)
            if data.level
            else None
        )
        self._statuses = {
            EntryId(s.entry_id): StatusRecord(
                WordStatus(s.status), StatusSource(s.source), s.at
            )
            for s in data.statuses
        }
        self._categories = [
            Category(c.id, c.name, c.color)
            for c in sorted(data.categories, key=lambda c: c.position)
        ]
        if not self._categories:
            for category in DEFAULT_CATEGORIES:
                self._categories.append(category)
                self._store_category(category)
        self._saved = {
            EntryId(w.entry_id): SavedWord(
                EntryId(w.entry_id),
                w.headword,
                w.traditional,
                w.reading,
                w.meaning,
                w.category_id,
                w.source_sentence,
                w.source_translation,
                w.saved_at,
            )
            for w in data.saved_words
        }
        self._exposures = {
            EntryId(e.entry_id): ExposureCount(
                e.heard,
                e.heard_by_you,
                e.heard_in_deck,
                e.first_heard,
                e.days_heard,
                e.last_heard,
            )
            for e in data.exposures
        }
        self._deck = {
            EntryId(w.entry_id): DeckWord(
                EntryId(w.entry_id),
                w.headword,
                w.traditional,
                w.reading,
                w.meaning,
                w.sentence,
                w.translation,
                w.learned_at,
            )
            for w in data.deck_words
        }
        self._exported: dict[AnkiFormat, dict[EntryId, datetime]] = {
            file: {} for file in AnkiFormat
        }
        """When each word was last written to each kind of Anki file (368)."""
        kinds = {file.value: file for file in AnkiFormat}
        for export in data.anki_exports:
            file = kinds.get(export.kind)  # None: a kind this app doesn't make
            if file is not None:
                self._exported[file][EntryId(export.entry_id)] = export.exported_at
        self._coverage = {
            c.day: Coverage(c.known, c.deck, c.new) for c in data.coverage
        }
        self._listening: dict[tuple[date, str], float] = {}
        for e in data.listening:
            key = (e.day, e.category)
            self._listening[key] = self._listening.get(key, 0.0) + e.seconds
        self._matcher = SavedWordMatcher(self._saved.values())
        self._saved_sentences: SentenceSearch | None = None
        """The saved sentences, read when first wanted (`_sentences`)."""
        self.knowledge = Knowledge(
            self._statuses.get,
            lambda: self._line,
            self._starting,
            level_words,
        )
        """What the learner knows in this language (polyglotic-hq 349, 373):
        the one answer per word. Word links read it (`needs_no_link`); the
        other readers (`status`: marks, the load, coverage, Words) still
        work theirs out until 349's step 3, which waits for the user's
        word (DECISIONS #176)."""
        self._lookups = {
            EntryId(k.entry_id): LookupCount(
                k.pinned, k.hovered, k.last_at, k.pinned_since_known
            )
            for k in data.lookups
        }
        for entry_id in [
            e for e, own in self._statuses.items() if self._one_click(e, own)
        ]:
            del self._statuses[entry_id]  # kept in the file; not evidence (397)
        self.chances = KnownChances(self.knowledge, self._evidence, clock, day_of)
        """How well the learner knows each word, 0 to 1 (polyglotic-hq 489,
        decision 0226): Learning colours' captions and the map."""
        self.load = LearningLoad(
            data.load_words,
            LoadStore(store.save_load_words, store.delete_load_words),
            self._facts_of,
            self.could_be_in_load,
            lambda after, limit: placed(after, limit, self.scheme) if placed else (),
            lambda: 0 if self._estimating.by_level else self._estimating.known,
            day_of,
        )
        """The learning load (polyglotic-hq 324): read it here; change it
        through `set_load_rules`, `check_word`, `add_to_load`,
        `add_next_to_load` and `set_aside_from_load`."""
        self.curriculum = Curriculum(
            data.curriculum_words,
            CurriculumStore(store.save_curriculum_words, store.delete_curriculum_words),
            self._facts_of,
            self.could_be_in_load,
            lambda: ((e, c.heard) for e, c in self._exposures.items()),
            lambda after, limit: placed(after, limit, self.scheme) if placed else (),
            lambda: 0 if self._estimating.by_level else self._estimating.known,
            day_of,
            reaches=lambda facts: self.learning_window.reaches(facts),
            known_words=self._known_words,
            known=self._knows,
        )
        """Our curriculum's active set (polyglotic-hq 477): on while the
        quiet view's chosen words include it (`set_chosen`); the
        conversation's words light in it (491), and retire once known
        (496)."""
        self._chosen: frozenset[ChosenWords] = frozenset()
        self._quiet_set: dict[EntryId, StoredSetWord] = {
            EntryId(w.entry_id): w for w in data.set_words if w.name == QUIET_SET
        }
        """The quiet view's chosen words as kept (`QUIET_SET`)."""

    def subscribe(self, listener: Listener) -> None:
        self._listeners.append(listener)

    def _publish(self, event: LearningEvent | VocabularyChanged) -> None:
        for listener in self._listeners:
            listener(event)

    # -- the level ---------------------------------------------------------------

    @property
    def line(self) -> KnownLine | None:
        """The learner's known line, or None until they set one (Learning's
        or Words' Change your level; the first run doesn't ask - 293):
        words are estimated at a middle level meanwhile."""
        return self._line

    @property
    def estimating(self) -> KnownLine:
        """The line words' statuses are estimated on now: the learner's,
        or the starting level until they set one."""
        return self._estimating

    @property
    def _estimating(self) -> KnownLine:
        """The line words' statuses are estimated on: the learner's, or
        until they set one a middle level (`KnownLine.starting`) - the
        first run doesn't ask (polyglotic-hq 293)."""
        return self._line or self._starting

    @property
    def scheme(self) -> str:
        """The level scheme words' levels are read in for this learner:
        the one their line is kept in, or - for a line said in words, or
        none yet - the language's own."""
        if self._line is not None and self._line.by_level:
            return self._line.scale
        return self._default_scheme

    def window(self, size: WindowSize | None = None) -> LearningWindow:
        """The learning window past the learner's line: its next `size`
        words (None: the default size), or every word past it."""
        return self._estimating.window(size)

    @property
    def learning_window(self) -> LearningWindow:
        """The learning window at the size the learner chose for this
        language (`set_window_size`): our curriculum's and the quiet view's
        words at your edge (polyglotic-hq 496; 491 used the default)."""
        return self.window(self._window_size)

    def set_window_size(self, size: WindowSize | None) -> None:
        """The learning window's size the learner chose for this language
        (a setting, `LanguageChoices.window_size`; None: the default).
        Words already in our curriculum's set stay; what enters next, and
        which words are at your edge, follow it."""
        self._window_size = size

    def _known_words(self) -> int:
        """About how many words the learner knows (0 if their line says
        no number)."""
        return self._estimating.words_known(self._level_words) or 0

    def set_level(self, level: Level) -> None:
        """The level picker's choice: words at or below `level` count as
        known from now on, unless the learner set them otherwise."""
        self._set_line(KnownLine.picked(level), LineSource.PICKED)

    def set_known_words(
        self, known: int, source: LineSource = LineSource.WORDS
    ) -> None:
        """ "I know about the `known` most common words": they count as
        known from now on, unless the learner set them otherwise.
        `source`: how, for the line's history."""
        self._set_line(KnownLine.words(known), source)

    def restore_line(self, line: KnownLine | None) -> None:
        """The line as it was before a quick mark (`first_known`: Undo or
        Reset): `line`, or None - none set, words estimated at the
        starting level again. Statuses set by hand are kept, as always."""
        self._set_line(line, LineSource.RESTORED)

    def _set_line(self, line: KnownLine | None, source: LineSource) -> None:
        self._line = line
        now = self._clock()
        if line is None:
            self._store.clear_level()
        else:
            self._store.save_level(StoredLevel(line.scale, line.midpoint))
        self._store.add_line_change(
            StoredLineChange(
                line.scale if line else None,
                line.midpoint if line else None,
                source.value,
                now,
            )
        )
        moved = self.load.line_moved()
        if self.load.refill(now) or moved:
            self._load_changed()
        if self.curriculum.line_moved(now):
            self._curriculum_changed()
        self._publish(VocabularyChanged(Changed.LEVEL))

    # -- statuses -------------------------------------------------------------------

    def status(self, facts: EntryFacts) -> StatusRecord:
        return status_of(facts, self._statuses.get(facts.entry_id), self._estimating)

    def needs_no_link(self, facts: EntryFacts, links_from: int | None = None) -> bool:
        """Whether the word is one the learner knows too well to link to
        its translation (word links "past what I know", polyglotic-hq 323):
        what `knowledge` answers - known or ignored - as if their line
        were at `links_from`, if they moved where links start. A name is
        placed as any word is (338); a number in numerals is known (360)."""
        return self.knowledge.of(facts, links_from).known

    def status_of_entry(self, entry_id: EntryId) -> StatusRecord:
        """A word's status by its entry ID alone; an entry the dictionary no
        longer has keeps its explicit status, or counts as new."""
        facts = self._facts_of(entry_id)
        if facts is None:
            return self._statuses.get(
                entry_id, StatusRecord(WordStatus.NEW, StatusSource.ESTIMATED)
            )
        return self.status(facts)

    def set_status(
        self,
        entry_id: EntryId,
        status: WordStatus,
        source: StatusSource = StatusSource.LEARNER,
    ) -> None:
        """Sets a word's status explicitly - one click in a caption or the
        lookup, or a correction in the vocabulary list. A word going into
        the deck starts counting its exposures in the deck from zero."""
        self.set_statuses((entry_id,), status, source)

    def set_statuses(
        self,
        entry_ids: Iterable[EntryId],
        status: WordStatus,
        source: StatusSource = StatusSource.LEARNER,
    ) -> None:
        """Sets several words' status at once - words picked together in a
        list (polyglotic-hq 342): each as `set_status` would, each sent to
        the server as its own, but views hear of it once and the learning
        load refills once."""
        at = self._clock()
        left = gone = False
        history: list[StoredStatusChange] = []
        for entry_id in dict.fromkeys(entry_ids):
            history.append(self._set_one(entry_id, status, source, at))
            left = self.load.status_set(entry_id, status, at) or left
            gone = self.curriculum.status_set(entry_id, _leaves(status)) or gone
        self._store.add_status_changes(history)
        self._publish(VocabularyChanged(Changed.STATUSES))
        if self.load.refill(at) or left:
            self._load_changed()
        if gone:
            self._curriculum_changed()

    def _set_one(
        self, entry_id: EntryId, status: WordStatus, source: StatusSource, at: datetime
    ) -> StoredStatusChange:
        """Sets one word's status; what it changed, for the history."""
        before = self.status_of_entry(entry_id).status
        self._statuses[entry_id] = StatusRecord(status, source, at)
        self._store.save_status(StoredStatus(entry_id, status.value, source.value, at))
        if status is WordStatus.LEARNING and before is not WordStatus.LEARNING:
            count = self._exposures.get(entry_id)
            if count is not None and count.heard_in_deck:
                self._save_counts({entry_id: count._replace(heard_in_deck=0)}, [])
        if status is not WordStatus.LEARNING:
            self._leave_deck(entry_id)
        looked = self._lookups.get(entry_id)
        if source is StatusSource.LEARNER and looked and looked.pinned_since_known:
            self._keep_lookups(entry_id, looked.said())  # the check starts again
        if source is not StatusSource.ESTIMATED:
            self._publish(WordStatusChanged(entry_id, status, at))
        return StoredStatusChange(
            entry_id, before.value, status.value, source.value, at
        )

    # -- the learning load (polyglotic-hq 324) -------------------------------------

    def _load_changed(self) -> None:
        touched = self.load.take_touched()
        self._publish(VocabularyChanged(Changed.LOAD, touched))
        if touched != frozenset() and ChosenWords.LOAD in self._chosen:
            self._keep_chosen()

    # -- the quiet view's chosen words, our curriculum (polyglotic-hq 477) -----------

    def set_chosen(
        self, chosen: frozenset[ChosenWords], curriculum_size: int, fill: bool = True
    ) -> None:
        """Which words the quiet view shows in blue - our curriculum's set,
        the learning load's words, saved words - and the set's size. Our
        curriculum is kept up only while it is chosen (the load's own
        rules turn it on: `set_load_rules`). `fill` False: a set turned on
        here fills at `fill_curriculum` - the app's start leaves that until
        its window is up (polyglotic-hq 509)."""
        size = curriculum_size if ChosenWords.CURRICULUM in chosen else None
        moved = self.curriculum.set_size(size, self._clock(), fill)
        if chosen == self._chosen and not moved:
            return
        self._chosen = chosen
        self._curriculum_changed()

    def fill_curriculum(self) -> None:
        """Our curriculum's set brought up to its size now, if it's on: the
        words heard most first, then the load's order (`Curriculum.fill`).
        It looks through every word heard - 30,000 met took 31 ms on the
        main PC at the start (polyglotic-hq 509) - so the app does this
        after its window is up, not as it starts."""
        if self.curriculum.fill(self._clock()):
            self._curriculum_changed()

    @property
    def chosen_words(self) -> frozenset[ChosenWords]:
        return self._chosen

    def chosen(self, word: EntryFacts) -> bool:
        """Whether the word is among the quiet view's chosen words: in what's
        chosen of our curriculum's set, the load, saved words and words at
        your edge (saved words are found in a line by `saved_spans`, by
        their forms too). A caption shows them as `lit` says."""
        return self._chosen_set(word) or (
            ChosenWords.EDGE in self._chosen and self.at_edge(word)
        )

    def lit(
        self, words: Sequence[EntryFacts], capitalised: Collection[int] = ()
    ) -> set[int]:
        """Which of a caption's words (in order) the quiet view shows in
        blue, by their places in `words`: every word of our curriculum's
        set, the load and saved words that's chosen; and words at your edge
        while the caption has fewer than `EDGE_PER_CAPTION` blue words, the
        commonest first (polyglotic-hq 496). `capitalised`: the places of
        words written with a capital inside their sentence - in a language
        whose capitals there mark only names (`names_capitalised`: "Agency"
        of the Central Intelligence Agency) such a word is part of a name,
        never lit as at your edge. A word said as a name here (`is_name`:
        万里 of 黄万里) is never blue, whatever set holds the word."""
        blue = {
            n
            for n, word in enumerate(words)
            if not word.is_name and self._chosen_set(word)
        }
        if ChosenWords.EDGE not in self._chosen:
            return blue
        edge = sorted(
            (
                n
                for n, word in enumerate(words)
                if n not in blue
                and not (n in capitalised and word.names_capitalised)
                and self.at_edge(word)
            ),
            key=lambda n: (place(words[n]) is None, place(words[n]) or 0, n),
        )
        for n in edge:
            if len(blue) >= EDGE_PER_CAPTION:
                break
            blue.add(n)
        return blue

    def _chosen_set(self, word: EntryFacts) -> bool:
        """In what's chosen of the three sets: our curriculum's, the load's
        and saved words."""
        chosen = self._chosen
        entry_id = word.entry_id
        return (
            (ChosenWords.CURRICULUM in chosen and self.curriculum.active(entry_id))
            or (ChosenWords.LOAD in chosen and self.load.stage(entry_id) is not None)
            or (ChosenWords.SAVED in chosen and entry_id in self._saved)
        )

    def at_edge(self, word: EntryFacts) -> bool:
        """Whether the word is at the learner's edge (polyglotic-hq 496):
        in their learning window (`learning_window` reaches it) and new or
        in the deck - never a name, a number (in numerals or spelled out),
        everyday talk or a filler (`theme.everyday`), or a word heard so
        often they know it (`theme.known_by_speech`): 491's filters."""
        if word.is_name or word.is_number or word.spells_a_number:
            return False
        if everyday(word) or known_by_speech(word, self._known_words()):
            return False
        return self.learning_window.reaches(word) and self.could_be_in_load(word)

    def _knows(self, word: EntryFacts) -> bool:
        """Whether the learner knows the word now: its chance is green
        (polyglotic-hq 489's `KnownChances`, 0.85 or more)."""
        found = self.chances.of(word)
        return found is not None and found.band is Band.MASTERED

    def _curriculum_changed(self) -> None:
        self._publish(VocabularyChanged(Changed.CURRICULUM))
        self._keep_chosen()

    def _chosen_now(self) -> dict[EntryId, tuple[str, ...]]:
        """The chosen words now, each with where it came from."""
        found: dict[EntryId, list[str]] = {}
        chosen = self._chosen
        if ChosenWords.CURRICULUM in chosen and self.curriculum.on:
            for word in self.curriculum.members():
                found.setdefault(word.entry_id, []).append(ChosenWords.CURRICULUM)
        if ChosenWords.LOAD in chosen and self.load.on:
            for loaded in self.load.members():
                found.setdefault(loaded.entry_id, []).append(ChosenWords.LOAD)
        if ChosenWords.SAVED in chosen:
            for entry_id in self._saved:
                found.setdefault(entry_id, []).append(ChosenWords.SAVED)
        return {e: tuple(sources) for e, sources in found.items()}

    def _keep_chosen(self) -> None:
        """The named word set `QUIET_SET` brought into step with the chosen
        words: only what changed is written."""
        now_ = self._chosen_now()
        kept = self._quiet_set
        gone = [e for e in kept if e not in now_]
        at = self._clock()
        changed = [
            StoredSetWord(QUIET_SET, e, sources, kept[e].added_at if e in kept else at)
            for e, sources in now_.items()
            if e not in kept or kept[e].sources != sources
        ]
        for entry_id in gone:
            del kept[entry_id]
        for word in changed:
            kept[EntryId(word.entry_id)] = word
        if gone:
            self._store.delete_set_words(QUIET_SET, gone)
        if changed:
            self._store.save_set_words(changed)

    def could_be_in_load(self, facts: EntryFacts) -> bool:
        """Whether a word may be in the load: not a name, and new or in
        the deck - not known (by the line or by hand), not ignored."""
        if facts.is_name:
            return False
        return self.status(facts).status in (WordStatus.NEW, WordStatus.LEARNING)

    def set_load_rules(self, rules: LoadRules | None) -> None:
        """The load's rules for this language, or None: the mode is off -
        what it holds is kept, and nothing is counted."""
        if self.load.set_rules(rules, self._clock()):
            self._load_changed()

    def check_word(self, entry_id: EntryId, knows: bool) -> None:
        """The check's answer for a word ready to check: "I know this"
        graduates it (its status known, set by the learner, and the next
        word takes its place); "Not yet" sends it back."""
        if not self.load.check(entry_id, knows, self._clock()):
            return
        if knows:
            self.set_status(entry_id, WordStatus.KNOWN)  # refills, and says so
        else:
            self._load_changed()

    def add_to_load(self, entry_id: EntryId) -> bool:
        """One word into the load by hand; the load's size (`load.rules`)
        goes up by it. False if it can't be in it (known, ignored, a name,
        in it already, or the load is off)."""
        facts = self._facts_of(entry_id)
        if facts is None or not self.load.add(facts, self._clock()):
            return False
        self._load_changed()
        return True

    def add_next_to_load(self, count: int) -> None:
        """The next `count` words by frequency into the load now; its size
        (`load.rules`) goes up by them."""
        if self.load.add_next(count, self._clock()):
            self._load_changed()

    def set_aside_from_load(self, entry_id: EntryId) -> None:
        """ "Not now": the word leaves the load, the next takes its place,
        and it comes back only by hand."""
        if self.load.set_aside(entry_id):
            self.load.refill(self._clock())
            self._load_changed()

    def learn(self, entry_id: EntryId, text: EntryText, context: LookupContext) -> None:
        """Puts a word in the deck from a caption or a lookup ("Learn"),
        keeping the line it was in, that line's translation and the time,
        on this PC (`DeckWord`). The word on its own is no line: Words
        hands its lookup the headword as its context when it has no line,
        and the card would show the word twice. A word put in the deck
        again keeps the line it has unless this time brings one; a word
        taken out of the deck loses it (`set_status`). Its time is when it
        last changed: put in again with the same line and text, it keeps
        the time it has, so its Anki note isn't updated over the learner's
        own edits (`export_anki`)."""
        self.set_status(entry_id, WordStatus.LEARNING)
        alone = context.sentence.strip() in {text.headword, text.traditional}
        sentence = "" if alone else context.sentence
        translation = "" if alone else context.translation
        old = self._deck.get(entry_id)
        if old is not None and not sentence:
            return
        word = DeckWord(
            entry_id,
            text.headword,
            text.traditional,
            text.reading,
            text.meaning,
            sentence,
            translation,
            self._clock(),
        )
        if old is not None and replace(word, learned_at=old.learned_at) == old:
            return
        self._deck[entry_id] = word
        self._store.save_deck_word(_stored_deck_word(word))

    def deck_word(self, entry_id: EntryId) -> DeckWord | None:
        return self._deck.get(entry_id)

    def _leave_deck(self, entry_id: EntryId) -> None:
        if self._deck.pop(entry_id, None) is not None:
            self._store.delete_deck_word(entry_id)

    # -- lookups ----------------------------------------------------------------------

    def looked_up(self, facts: EntryFacts, pinned: bool) -> None:
        """A lookup was shown: counted, with its time, on this PC
        (`lookups`; polyglotic-hq 373). Pinned lookups (clicks) are
        evidence the learner doesn't know the word, from the
        `TURNS_NEW_AFTER`th: one only estimated known turns back to new
        then. One click alone isn't - it selects a word, opens its card to
        hear it, or misses (polyglotic-hq 397: "the", "that" and "you",
        clicked once each, were dotted as new) - and no number of clicks
        is, for a word deep within the line (`_deep_within`): "the" for
        someone who knows 2,000 words. The learner's own choices are never
        changed: a word they said they know, looked up pinned again, is
        offered in a check instead (`to_check`)."""
        at = self._clock()
        self._publish(WordLookedUp(facts.entry_id, at))
        current = self.status(facts)
        said_known = current.source is StatusSource.LEARNER and (
            current.status is WordStatus.KNOWN
        )
        before = self._lookups.get(facts.entry_id, LookupCount())
        after = before.looked_up(pinned, at, said_known)
        self._keep_lookups(facts.entry_id, after)
        if not pinned or after.pinned < TURNS_NEW_AFTER or self._deep_within(facts):
            return
        if not current.is_learners_own and current.status is WordStatus.KNOWN:
            self.set_status(facts.entry_id, WordStatus.NEW, StatusSource.ESTIMATED)

    def _deep_within(self, facts: EntryFacts) -> bool:
        """Whether the word is placed in the first `DEEP_WITHIN` of the
        learner's line (the starting line's until they set one): clicks
        don't make it new (397). A line that says no number of words
        (HSK 3.0's 2021 standard) has no such part."""
        known, at = self.knowledge.known_words, place(facts)
        return known is not None and at is not None and at <= known * DEEP_WITHIN

    def _one_click(self, entry_id: EntryId, own: StatusRecord) -> bool:
        """A status "new" kept from fewer pinned lookups than
        `TURNS_NEW_AFTER`: what one click did before 397 (and every such
        status from before lookups were counted, which the learning file's
        version 8 counted as one each). Not read as evidence - the word is
        as the line says - and left in the file as it is."""
        return (
            own.source is StatusSource.ESTIMATED
            and own.status is WordStatus.NEW
            and self._lookups.get(entry_id, LookupCount()).pinned < TURNS_NEW_AFTER
        )

    def lookups(self, entry_id: EntryId) -> LookupCount:
        """How often the word was looked up on this PC, and when last."""
        return self._lookups.get(entry_id, LookupCount())

    def to_check(self) -> list[EntryId]:
        """Words the learner said they know and has since looked up, pinned,
        `lookups.CHECK_AFTER` times: offered in a check ("Still know
        it?"), most recently looked up first. Their status stays known
        until the learner says otherwise (DECISIONS #176 (d))."""
        found = [
            (count.last, entry_id)
            for entry_id, count in self._lookups.items()
            if count.to_check
            and (own := self._statuses.get(entry_id)) is not None
            and own.source is StatusSource.LEARNER
            and own.status is WordStatus.KNOWN
        ]
        return [entry_id for _, entry_id in sorted(found, key=_latest_first)]

    def _keep_lookups(self, entry_id: EntryId, count: LookupCount) -> None:
        self._lookups[entry_id] = count
        if count.last is not None:
            self._store.save_lookups(
                StoredLookups(
                    entry_id,
                    count.pinned,
                    count.hovered,
                    count.last,
                    count.pinned_since_known,
                )
            )

    # -- saved words and categories ------------------------------------------------------

    @property
    def categories(self) -> list[Category]:
        return list(self._categories)

    def category(self, category_id: CategoryId) -> Category | None:
        return next((c for c in self._categories if c.id == category_id), None)

    @property
    def saved_words(self) -> list[SavedWord]:
        """Newest first."""
        return sorted(self._saved.values(), key=lambda w: w.saved_at, reverse=True)

    def saved_word(self, entry_id: EntryId) -> SavedWord | None:
        return self._saved.get(entry_id)

    def save(
        self,
        entry_id: EntryId,
        headword: str,
        traditional: str,
        reading: str,
        meaning: str,
        category_id: CategoryId,
        context: LookupContext,
    ) -> None:
        """Saves a word into a category - or moves it there if it's saved
        already, keeping when it was first saved and its source sentence."""
        if self.category(category_id) is None:
            raise ValueError(f"no category {category_id!r}")
        old = self._saved.get(entry_id)
        if old is not None:
            word = replace(old, category_id=category_id)
        else:
            word = SavedWord(
                entry_id,
                headword,
                traditional,
                reading,
                meaning,
                category_id,
                context.sentence,
                context.translation,
                self._clock(),
            )
        self._saved[entry_id] = word
        self._store.save_word(_stored_word(word))
        self._matcher = SavedWordMatcher(self._saved.values())
        if old is None:
            self._publish(WordSaved(entry_id, word.saved_at))
        self._publish(VocabularyChanged(Changed.SAVED_WORDS))

    def unsave(self, entry_id: EntryId) -> None:
        if self._saved.pop(entry_id, None) is None:
            return
        self._store.delete_word(entry_id)
        self._matcher = SavedWordMatcher(self._saved.values())
        self._publish(WordUnsaved(entry_id, self._clock()))
        self._publish(VocabularyChanged(Changed.SAVED_WORDS))

    def add_category(self, name: str, color: str | None = None) -> Category:
        used = {c.color for c in self._categories}
        color = color or next(
            (c for c in NEW_CATEGORY_COLORS if c not in used), NEW_CATEGORY_COLORS[0]
        )
        category = Category(uuid.uuid4().hex[:8], name, color)
        self._categories.append(category)
        self._store_category(category)
        self._publish(VocabularyChanged(Changed.SAVED_WORDS))
        return category

    def change_category(
        self, category_id: CategoryId, name: str | None = None, color: str | None = None
    ) -> None:
        """Renames or recolours a category."""
        for i, category in enumerate(self._categories):
            if category.id == category_id:
                self._categories[i] = Category(
                    category.id, name or category.name, color or category.color
                )
                self._store_category(self._categories[i])
                self._publish(VocabularyChanged(Changed.SAVED_WORDS))
                return

    def remove_category(self, category_id: CategoryId) -> None:
        """Deletes a category and the words saved in it. The last category
        can't be deleted."""
        if len(self._categories) <= 1 or self.category(category_id) is None:
            return
        self._categories = [c for c in self._categories if c.id != category_id]
        gone = [
            w.entry_id for w in self._saved.values() if w.category_id == category_id
        ]
        self._store.delete_category(category_id)
        at = self._clock()
        for entry_id in gone:
            del self._saved[entry_id]
            self._publish(WordUnsaved(entry_id, at))
        self._matcher = SavedWordMatcher(self._saved.values())
        gone_too: list[SentenceId] = []
        kept = self._saved_sentences
        if kept is not None:  # not read yet: they went from the store with it
            gone_too = [s.id for s in kept.sentences() if s.category_id == category_id]
            for sentence_id in gone_too:
                kept.remove(sentence_id)
        self._publish(VocabularyChanged(Changed.SAVED_WORDS))
        if gone_too:
            self._publish(VocabularyChanged(Changed.SENTENCES))

    # -- saved sentences (polyglotic-hq 459) -------------------------------------------

    def _sentences(self) -> SentenceSearch:
        """The saved sentences, read from the store the first time they're
        wanted - never at the start (`LearningStore.saved_sentences`)."""
        if self._saved_sentences is None:
            self._saved_sentences = SentenceSearch(
                _sentence(s) for s in self._store.saved_sentences()
            )
        return self._saved_sentences

    @property
    def sentences(self) -> list[SavedSentence]:
        """Newest first."""
        return self._sentences().sentences()

    def sentence(self, sentence_id: SentenceId) -> SavedSentence | None:
        return self._sentences().get(sentence_id)

    def save_sentence(
        self,
        parts: Sequence[SentencePart],
        original: str,
        translation: str,
        category_id: CategoryId,
        translation_language: str = "",
    ) -> SavedSentence:
        """Saves what the learner selected - `parts`, each a clause, and the
        text of each side joined - into a category. Kept on this PC only:
        nothing is published to the server."""
        if self.category(category_id) is None:
            raise ValueError(f"no category {category_id!r}")
        if not original.strip() and not translation.strip():
            raise ValueError("an empty sentence")
        sentence = SavedSentence(
            uuid.uuid4().hex,
            original,
            translation,
            tuple(parts),
            category_id,
            self._clock(),
            translation_language,
        )
        self._keep_sentence(sentence)
        return sentence

    def move_sentence(self, sentence_id: SentenceId, category_id: CategoryId) -> None:
        """Moves a saved sentence into another category."""
        old = self._sentences().get(sentence_id)
        if old is None or old.category_id == category_id:
            return
        if self.category(category_id) is None:
            raise ValueError(f"no category {category_id!r}")
        self._keep_sentence(replace(old, category_id=category_id))

    def _keep_sentence(self, sentence: SavedSentence) -> None:
        self._sentences().add(sentence)
        self._store.save_sentence(_stored_sentence(sentence))
        self._publish(VocabularyChanged(Changed.SENTENCES))

    def unsave_sentence(self, sentence_id: SentenceId) -> None:
        sentences = self._sentences()
        if sentences.get(sentence_id) is None:
            return
        sentences.remove(sentence_id)
        self._store.delete_sentence(sentence_id)
        self._publish(VocabularyChanged(Changed.SENTENCES))

    def find_sentences(
        self,
        query: str = "",
        category_id: CategoryId | None = None,
        word: EntryId | None = None,
    ) -> list[Found]:
        """The saved sentences `query` finds, best first - with at least half
        of its words (each Chinese character a word) in what was said or
        its translation (`SentenceSearch.search`); only a category's, or
        only those with the saved `word` in them, if given."""
        saved = self._saved.get(word) if word is not None else None
        if word is not None and saved is None:
            return []
        return self._sentences().search(query, category_id, saved)

    def _store_category(self, category: Category) -> None:
        position = self._categories.index(category)
        self._store.save_category(
            StoredCategory(category.id, category.name, category.color, position)
        )

    # -- dictionary updates -------------------------------------------------------

    def follow_merged_entries(self, merged_ids: Iterable[EntryId]) -> int:
        """Moves what the learner has under an entry ID that a dictionary
        update merged into another entry (decision 0007) to that entry:
        its status and saved word - unless the entry has its own, then the
        later one wins - and its exposure and lookup counts, added together. The
        learner's own statuses and saves are published again under the
        new ID, with their old times, so the server's latest-wins rule
        keeps the right state. Returns how many entries moved. Call it
        once at start, after the listeners subscribe, with the IDs the
        dictionary merged (`merged_ids`): only the learner's among them
        are looked up - every word met's took 0.35 s before the window at
        30,000 words met on CC-CEDICT (polyglotic-hq 220)."""
        met = set(self._statuses) | set(self._saved) | set(self._exposures)
        met |= set(self._lookups)
        moved = 0
        for old_id in sorted(met.intersection(merged_ids)):
            facts = self._facts(old_id, self.scheme)
            if facts is None or facts.entry_id == old_id:
                continue
            self._move(old_id, facts.entry_id)
            moved += 1
        if moved:
            self._matcher = SavedWordMatcher(self._saved.values())
            self.load.refill(self._clock())
            for what in (Changed.STATUSES, Changed.SAVED_WORDS, Changed.EXPOSURES):
                self._publish(VocabularyChanged(what))
            self._load_changed()
            self._curriculum_changed()
        return moved

    def _move(self, old_id: EntryId, new_id: EntryId) -> None:
        status = self._statuses.pop(old_id, None)
        if status is not None:
            current = self._statuses.get(new_id)
            if current is None or (current.at or _NEVER) < (status.at or _NEVER):
                self._statuses[new_id] = status
                at = status.at or self._clock()
                self._store.save_status(
                    StoredStatus(new_id, status.status.value, status.source.value, at)
                )
                if status.is_learners_own:
                    self._publish(WordStatusChanged(new_id, status.status, at))
        deck = self._deck.pop(old_id, None)
        if deck is not None:
            current_deck = self._deck.get(new_id)
            if current_deck is None or current_deck.learned_at < deck.learned_at:
                moved_deck = replace(deck, entry_id=new_id)
                self._deck[new_id] = moved_deck
                self._store.save_deck_word(_stored_deck_word(moved_deck))
        for file, exports in self._exported.items():
            exported = exports.pop(old_id, None)
            if exported is not None:
                kept = max(exported, exports.get(new_id, exported))
                exports[new_id] = kept
                self._store.save_anki_exports(
                    [StoredAnkiExport(new_id, kept, file.value)]
                )
        word = self._saved.pop(old_id, None)
        if word is not None:
            current_word = self._saved.get(new_id)
            if current_word is None or current_word.saved_at < word.saved_at:
                moved = replace(word, entry_id=new_id)
                self._saved[new_id] = moved
                self._store.save_word(_stored_word(moved))
                if current_word is None:
                    self._publish(WordSaved(new_id, word.saved_at))
        count = self._exposures.pop(old_id, None)
        if count is not None:
            into = self._exposures.get(new_id, ExposureCount())
            self._save_counts(
                {
                    new_id: ExposureCount(
                        into.heard + count.heard,
                        into.heard_by_you + count.heard_by_you,
                        into.heard_in_deck + count.heard_in_deck,
                        min(
                            (d for d in (into.first_heard, count.first_heard) if d),
                            default=None,
                        ),
                        # the days of each may be the same: the more of the two
                        max(into.days_heard, count.days_heard),
                        max(
                            (d for d in (into.last_heard, count.last_heard) if d),
                            default=None,
                        ),
                    )
                },
                [],
            )
        looked = self._lookups.pop(old_id, None)
        if looked is not None:
            self._keep_lookups(new_id, looked.joined(self.lookups(new_id)))
        self.load.moved(old_id, new_id)
        self.curriculum.moved(old_id, new_id)
        self._quiet_set.pop(old_id, None)  # brought into step below
        self._store.forget_entry(old_id)

    # -- learning data from the server, and deleting it --------------------------------

    def apply_from_server(
        self, events: Sequence[LearningEvent], describe: Describe
    ) -> int:
        """Statuses and saved words as the server has them - set on another
        PC, or this one - applied by protocol.md's rule (the latest `at`
        wins) and **not published again**. A status from the server is the
        learner's own, so it also wins over one Learning only estimated. A
        word saved elsewhere is saved here into the first category, with
        its text from this PC's dictionary (`describe`) and no source
        sentence (that stays on the PC it was saved on); one this
        dictionary hasn't got is left out. Returns how many entries
        changed."""
        changed: set[Changed] = set()
        count = 0
        for event in events:
            if isinstance(event, WordStatusChanged):
                applied = self._status_from_server(event)
                what = Changed.STATUSES
            elif isinstance(event, WordSaved):
                applied = self._saved_from_server(event, describe)
                what = Changed.SAVED_WORDS
            elif isinstance(event, WordUnsaved):
                applied = self._unsaved_from_server(event)
                what = Changed.SAVED_WORDS
            else:
                continue
            if applied:
                changed.add(what)
                count += 1
                if isinstance(event, WordStatusChanged) and self.load.status_set(
                    event.entry_id, event.status, event.at
                ):
                    changed.add(Changed.LOAD)
                if isinstance(event, WordStatusChanged) and self.curriculum.status_set(
                    event.entry_id, _leaves(event.status)
                ):
                    changed.add(Changed.CURRICULUM)
        if Changed.STATUSES in changed and self.load.refill(self._clock()):
            changed.add(Changed.LOAD)
        if Changed.SAVED_WORDS in changed:
            self._matcher = SavedWordMatcher(self._saved.values())
        for what in sorted(changed - {Changed.LOAD, Changed.CURRICULUM}):
            self._publish(VocabularyChanged(what))
        if Changed.LOAD in changed:
            self._load_changed()
        if Changed.CURRICULUM in changed:
            self._curriculum_changed()
        elif Changed.SAVED_WORDS in changed:
            self._keep_chosen()
        return count

    def _status_from_server(self, event: WordStatusChanged) -> bool:
        local = self._statuses.get(event.entry_id)
        if (
            local is not None
            and local.is_learners_own
            and (local.at or _NEVER) >= event.at
        ):
            return False
        source = StatusSource.LEARNER
        before = self.status_of_entry(event.entry_id).status
        self._store.add_status_changes(
            [
                StoredStatusChange(
                    event.entry_id,
                    before.value,
                    event.status.value,
                    FROM_SERVER,
                    event.at,
                )
            ]
        )
        self._statuses[event.entry_id] = StatusRecord(event.status, source, event.at)
        if event.status is not WordStatus.LEARNING:
            self._leave_deck(event.entry_id)
        self._store.save_status(
            StoredStatus(event.entry_id, event.status.value, source.value, event.at)
        )
        return True

    def _saved_from_server(self, event: WordSaved, describe: Describe) -> bool:
        if event.entry_id in self._saved or not self._categories:
            return False
        text = describe(event.entry_id)
        if text is None:
            return False
        word = SavedWord(
            event.entry_id,
            text.headword,
            text.traditional,
            text.reading,
            text.meaning,
            self._categories[0].id,
            "",
            "",
            event.at,
        )
        self._saved[event.entry_id] = word
        self._store.save_word(_stored_word(word))
        return True

    def _unsaved_from_server(self, event: WordUnsaved) -> bool:
        saved = self._saved.get(event.entry_id)
        if saved is None or saved.saved_at >= event.at:
            return False
        del self._saved[event.entry_id]
        self._store.delete_word(event.entry_id)
        return True

    def learning_state(self) -> list[LearningEvent]:
        """The whole learning state the server keeps, as Learning's events:
        every status the learner set or imported (a word in the deck is
        `learning`) and every saved word, each at the time it was set - for
        sending again after the server's store was restored (polyglotic-hq
        project 166). Statuses Learning only estimated stay out, as when
        they're set. Safe to call from the connection's thread: it takes
        copies of the two maps (one step each under the GIL) and reads
        only those."""
        statuses = dict(self._statuses)
        saved = dict(self._saved)
        events: list[LearningEvent] = [
            WordStatusChanged(entry_id, record.status, record.at)
            for entry_id, record in statuses.items()
            if record.is_learners_own and record.at is not None
        ]
        events += [
            WordSaved(entry_id, word.saved_at) for entry_id, word in saved.items()
        ]
        return events

    def delete_learning_data(self) -> None:
        """Deletes the learner's learning data on this PC - statuses, saved
        words and sentences, exposure counts, lookups, the days' coverage and listening, and any
        copy of it set aside after damage, the learning load's words - once
        they've confirmed; nothing
        is published (the server's copy goes by its own request). The level
        and the categories stay."""
        self._store.delete_learning_data()
        self._statuses.clear()
        self._saved.clear()
        self._deck.clear()
        for exports in self._exported.values():
            exports.clear()
        self._exposures.clear()
        self._lookups.clear()
        self._counter = ExposureCounter()
        self._coverage.clear()
        self._covering = CoverageCounter()
        self._listening.clear()
        self._listening_runs = ListeningCounter()
        self._matcher = SavedWordMatcher(())
        self._saved_sentences = SentenceSearch()
        self.load.clear()
        self.load.refill(self._clock())  # the mode still on: a new load
        self._quiet_set.clear()
        self.curriculum.clear(self._clock())  # chosen still: a new set
        for what in (
            Changed.STATUSES,
            Changed.SAVED_WORDS,
            Changed.SENTENCES,
            Changed.EXPOSURES,
        ):
            self._publish(VocabularyChanged(what))
        self._load_changed()
        self._curriculum_changed()

    def take_finished_exposure_days(self, today: date) -> dict[date, Mapping[str, int]]:
        """The daily counts of every UTC day before `today` not handed over
        yet, handed over once: the connection shares them if the learner
        opted in, and drops them if not. Here they're kept, marked as handed
        over, until they're `KEEP_DAILY_WEEKS` old, then deleted (decision
        0041)."""
        days = [day for day in self._store.days_to_hand_over() if day < today]
        taken = {day: self._store.daily_exposures(day) for day in days}
        self._store.mark_handed_over(days)
        oldest = today - timedelta(weeks=KEEP_DAILY_WEEKS)
        self._store.forget_daily_exposures(
            [day for day in self._store.exposure_days() if day < oldest]
        )
        return {day: counts for day, counts in taken.items() if counts}

    def export_anki(
        self,
        describe: Describe | None = None,
        only_new: bool = False,
        file: AnkiFormat = AnkiFormat.DECK,
    ) -> AnkiExport:
        """The saved words and the words in the deck as a CSV file's text
        for Anki (`anki`) - only those not in a `file` of that kind yet if
        `only_new` (`AnkiWords.export` says how each note is made)."""
        return self.anki_words(only_new, file).export(describe)

    def anki_words(
        self, only_new: bool = False, file: AnkiFormat = AnkiFormat.DECK
    ) -> AnkiWords:
        """What an Anki export is made from, as it is now - copied, so it
        can be made into the file on another thread while this vocabulary
        changes (polyglotic-hq 273: the deck file took 5.4 s on the
        interface thread). Quick: no dictionary, no store. `only_new`: the
        words not yet written to that kind of `file` (368) - and the
        sentences (459)."""
        leave_out = frozenset(self._exported[file]) if only_new else frozenset()
        return AnkiWords(
            {c.id: c.name for c in self._categories},
            dict(self._statuses),
            dict(self._saved),
            dict(self._deck),
            leave_out,
            tuple(
                s
                for s in reversed(self._sentences().sentences())
                if sentence_key(s.id) not in leave_out
            ),
        )

    def mark_exported(
        self, entry_ids: Iterable[EntryId], file: AnkiFormat = AnkiFormat.DECK
    ) -> None:
        """Remembers that these words were written to that kind of Anki
        `file`, so its "only words not exported yet" leaves them out next
        time - the other kind's still has them (368)."""
        at = self._clock()
        ids = list(entry_ids)
        for entry_id in ids:
            self._exported[file][entry_id] = at
        self._store.save_anki_exports(StoredAnkiExport(e, at, file.value) for e in ids)

    def is_exported(self, entry_id: EntryId) -> bool:
        """Whether the word was written to an Anki file of either kind."""
        return any(entry_id in exports for exports in self._exported.values())

    # -- finished captions ------------------------------------------------------------

    def highlights(
        self,
        lines: Sequence[tuple[str, Sequence[WordInLine]]],
        introductions: WordIntroductions = WordIntroductions.A_FEW,
        window_size: WindowSize | None = None,
    ) -> list[LineHighlights]:
        """For a finished caption - each line with its words - what each
        line shows. `introductions`: how many of the new words in the
        learning window it points out (none, a few, or every one);
        `window_size`: that window's size (None: the default; a number,
        or unlimited). Saved words
        and words in the deck show whichever it is."""
        unfamiliar: list[list[WordInLine]] = (
            [[] for _ in lines]
            if introductions is WordIntroductions.OFF
            else unfamiliar_words(
                [words for _, words in lines],
                lambda facts: self.status(facts).status,
                self.window(window_size),
                lambda entry_id: self.exposures(entry_id).heard,
                introductions is WordIntroductions.A_FEW,
            )
        )
        return [
            LineHighlights(
                saved=self._matcher.spans(text, words),
                unfamiliar=new,
                in_deck=[
                    w
                    for w in words
                    if self.status(w.entry).status is WordStatus.LEARNING
                ],
            )
            for (text, words), new in zip(lines, unfamiliar, strict=True)
        ]

    def saved_spans(self, line: str, words: Sequence[WordInLine]) -> list[SavedSpan]:
        """The saved words in any line - a live update's too."""
        return self._matcher.spans(line, words)

    def caption_finished(
        self,
        caption_id: str,
        words: Sequence[WordInLine],
        by_you: bool,
        source: str = "",
        forms: Sequence[str] = (),
    ) -> None:
        """Counts a finished caption's words as exposures and towards the
        day's coverage (by their statuses now), once per caption (a join
        finishing it again counts only the difference). `by_you`: from the
        user's own mic - no coverage. `source`: the source it came from,
        `forms`: each word as said - for our curriculum's conversation
        words (polyglotic-hq 491)."""
        now = self._clock()
        day = now.date()
        covered = Coverage() if by_you else coverage_of(words, self._status_now)
        self._counted(
            self._covering.finished(caption_id, covered, day),
            self._counter.finished(caption_id, words, by_you, day),
        )
        # the load's meetings: what the PC played only; a caption finished
        # again as the user's own speech takes back what it counted
        if self.load.caption_finished(caption_id, () if by_you else words, now):
            self._load_changed()
        if not by_you and self.curriculum.caption_finished(
            words, now, caption_id, source, forms
        ):
            self._curriculum_changed()

    def caption_withdrawn(self, caption_id: str) -> None:
        self.curriculum.caption_withdrawn(caption_id)
        self._counted(
            self._covering.withdrawn(caption_id), self._counter.withdrawn(caption_id)
        )
        if self.load.caption_withdrawn(caption_id, self._clock()):
            self._load_changed()

    def _counted(
        self, coverage: Mapping[date, Coverage], exposures: Sequence[ExposureChange]
    ) -> None:
        self._cover(coverage)
        self._count(exposures)
        if coverage or exposures:
            self._publish(VocabularyChanged(Changed.EXPOSURES))

    def _status_now(self, facts: EntryFacts) -> WordStatus:
        return self.status(facts).status

    def _cover(self, changes: Mapping[date, Coverage]) -> None:
        if not changes:
            return
        for day, change in changes.items():
            self._coverage[day] = self._coverage.get(day, Coverage()) + change
        self._store.add_coverage(
            [StoredCoverage(d, c.known, c.deck, c.new) for d, c in changes.items()]
        )

    def coverage(self, days: int = RECENT_DAYS) -> Coverage:
        """The coverage of the last `days` UTC days, today included."""
        today = self._clock().date()
        first = today - timedelta(days=days - 1)
        total = Coverage()
        for day, coverage in self._coverage.items():
            if first <= day <= today:
                total += coverage
        return total

    def listened(self, category: str) -> None:
        """A finished caption from a source of `category` (`video`, `game`,
        ...) arrived now - not from the user's own mic: the time since the
        one before counts as listening, if it was a short gap
        (`listening_time`)."""
        counted = self._listening_runs.heard(self._clock(), category)
        if counted is None:
            return
        key = (counted.day, counted.category)
        self._listening[key] = self._listening.get(key, 0.0) + counted.seconds
        self._store.add_listening(
            [StoredListening(counted.day, counted.category, counted.seconds)]
        )
        self._publish(VocabularyChanged(Changed.EXPOSURES))

    def listening(self, days: int | None = None) -> float:
        """Seconds of listening with captions on: in all, or in the last
        `days` UTC days, today included."""
        today = self._clock().date()
        first = date.min if days is None else today - timedelta(days=days - 1)
        return sum(s for (day, _), s in self._listening.items() if first <= day)

    def _count(self, changes: Sequence[ExposureChange]) -> None:
        if not changes:
            return
        counts: dict[EntryId, ExposureCount] = {}
        today = self._day_of(self._clock())
        for change in changes:
            count = counts.get(change.entry_id) or self.exposures(change.entry_id)
            in_deck = (
                self.status_of_entry(change.entry_id).status is WordStatus.LEARNING
            )
            counts[change.entry_id] = exposure_rules.apply(
                count, change, in_deck, today
            )
        self._save_counts(counts, [c for c in changes if not c.by_you])

    def _save_counts(
        self, counts: dict[EntryId, ExposureCount], shared: Sequence[ExposureChange]
    ) -> None:
        self._exposures.update(counts)
        daily: dict[date, dict[str, int]] = {}
        for change in shared:
            day = daily.setdefault(change.day, {})
            day[change.entry_id] = day.get(change.entry_id, 0) + change.delta
        self._store.save_exposures(
            [
                StoredExposures(
                    e,
                    c.heard,
                    c.heard_by_you,
                    c.heard_in_deck,
                    c.first_heard,
                    c.days_heard,
                    c.last_heard,
                )
                for e, c in counts.items()
            ],
            daily,
        )

    def _evidence(self, entry_id: EntryId) -> Evidence:
        """What the learner did with a word, for `chances`."""
        heard = self._exposures.get(entry_id)
        looked = self._lookups.get(entry_id)
        saved = self._saved.get(entry_id)
        if heard is None and looked is None and saved is None:
            return NO_EVIDENCE
        return Evidence(
            heard.days_heard if heard else 0,
            heard.last_heard if heard else None,
            looked,
            saved is not None,
            saved.saved_at if saved else None,
        )

    def chances_as_of(self, at: datetime) -> KnownChances:
        """How well each word was known at `at` - a week ago, for the map's
        "this week" (polyglotic-hq 489): the statuses and the line rebuilt
        from their histories, the days heard less those with a daily count
        since, lookups and saves made since left out (`known_map`)."""
        today = self._clock().date()
        heard_since: dict[EntryId, int] = {}
        day = at.date()  # the UTC days from `at`'s on: this week's
        while day <= today:
            for entry_id, count in self._store.daily_exposures(day).items():
                if count > 0:
                    key = EntryId(entry_id)
                    heard_since[key] = heard_since.get(key, 0) + 1
            day += timedelta(days=1)
        line = line_then(self._line, self._store.line_changes(), at)
        knowledge = Knowledge(
            statuses_then(self._statuses, self._store.status_changes(), at),
            lambda: line,
            self._starting,
            self._level_words,
        )
        return KnownChances(
            knowledge,
            evidence_then(self._evidence, heard_since, at, self._day_of(at)),
            lambda: at,
            self._day_of,
        )

    def exposures(self, entry_id: EntryId) -> ExposureCount:
        return self._exposures.get(entry_id, ExposureCount())

    def keep_hearing(self, limit: int = 50) -> list[tuple[EntryId, ExposureCount]]:
        """Words you keep hearing: unfamiliar words heard in at least
        `KEEP_HEARING_MIN` captions, most heard first - to add to the deck.
        Names never; the user's own mic doesn't count."""
        found: list[tuple[EntryId, ExposureCount]] = []
        often = [
            (-count.heard, entry_id, count)
            for entry_id, count in self._exposures.items()
            if count.heard >= KEEP_HEARING_MIN
        ]
        often.sort()  # most heard first: the counts never compare (IDs differ)
        explicit, line = self._statuses, self._estimating
        for _, entry_id, count in often:
            if len(found) >= limit:
                break
            facts = self._facts_of(entry_id)
            if facts is None or facts.is_name:
                continue
            own = explicit.get(facts.entry_id)  # `status`, without a record each
            if (own.status if own else estimated_status(facts, line)) is WordStatus.NEW:
                found.append((entry_id, count))
        return found

    def _facts_of(self, entry_id: EntryId) -> EntryFacts | None:
        """The entry's facts in the learner's scheme, read once a run."""
        key = (entry_id, self.scheme)
        if key not in self._looked_up:
            self._looked_up[key] = self._facts(entry_id, key[1])
        return self._looked_up[key]

    def facts_to_read(self) -> Callable[[], FactsRead]:
        """The facts Words asks for - every word met's, in the learner's
        scheme, those not read yet - as a read to run on another thread: it
        touches nothing here, only the dictionary (the facts lookup). Hand
        what it returns to `know_facts`, on this one. Read at start, Words'
        first show reads nothing from the dictionary - 50 ms at 10,000
        words met (polyglotic-hq project 212)."""
        scheme, lookup = self.scheme, self._facts
        met = set(self._exposures) | set(self._statuses) | set(self._saved)
        wanted = [e for e in met if (e, scheme) not in self._looked_up]

        def read() -> FactsRead:
            found = {}
            for entry_id in wanted:
                facts = lookup(entry_id, scheme)
                if facts is not None:
                    found[entry_id] = facts
            return FactsRead(scheme, found)

        return read

    def know_facts(self, read: FactsRead) -> None:
        """Facts read ahead (`facts_to_read`). Facts read since are kept; a
        word the read didn't find is asked for again when wanted - the
        dictionary may have been out."""
        for entry_id, facts in read.found.items():
            self._looked_up.setdefault((entry_id, read.scheme), facts)

    def new_words(self, days: int = RECENT_DAYS) -> int:
        """How many words were first heard in the last `days` UTC days,
        today included (words heard before the app kept the day aren't)."""
        first = self._clock().date() - timedelta(days=days - 1)
        return sum(
            1
            for count in self._exposures.values()
            if count.first_heard is not None and count.first_heard >= first
        )

    def met_words(self) -> list[MetWord]:
        """Every word met - heard in a finished caption from what the PC
        played; names never are - that the dictionary has, with its status
        now: for the words-met count and the bands (`bands`)."""
        found = []
        explicit, line = self._statuses, self._estimating
        for entry_id, count in self._exposures.items():
            if count.heard <= 0:
                continue
            facts = self._facts_of(entry_id)
            if facts is None or facts.is_name:
                continue
            own = explicit.get(facts.entry_id)  # `status`, without a record each
            found.append((facts, own.status if own else estimated_status(facts, line)))
        return found

    def vocabulary_list(self, status: WordStatus | None = None) -> list[VocabularyRow]:
        """Every word the learner has met - heard, saved, or given a status
        - with its status, most heard first; only those with `status` if
        given."""
        return [self.vocabulary_row(e) for e in self.met_entries(status)]

    def met_entries(self, status: WordStatus | None = None) -> list[EntryId]:
        """The words of `vocabulary_list`, in its order, without a row for
        each: Words shows the first few hundred (`vocabulary_row`) - a row
        and a status for each of 10,000 words met took 15 ms
        (polyglotic-hq project 212)."""
        exposures = self._exposures
        heard = [(-c.heard, -c.heard_by_you, e) for e, c in exposures.items()]
        others = (set(self._statuses) | set(self._saved)).difference(exposures)
        heard += [(0, 0, e) for e in others]  # never heard: no exposures
        if status is not None:
            heard = [row for row in heard if self._status_by_id(row[2]) is status]
        heard.sort()  # most heard first, then by ID
        return [entry_id for _, _, entry_id in heard]

    def vocabulary_row(self, entry_id: EntryId) -> VocabularyRow:
        """A word met, as `vocabulary_list` has it."""
        return VocabularyRow(
            entry_id,
            self.status_of_entry(entry_id),
            self.exposures(entry_id),
            self._saved.get(entry_id),
        )

    def _status_by_id(self, entry_id: EntryId) -> WordStatus:
        """`status_of_entry(entry_id).status`, without a record for each."""
        facts = self._facts_of(entry_id)
        own = self._statuses.get(facts.entry_id if facts else entry_id)
        if own is not None:
            return own.status
        return estimated_status(facts, self._estimating) if facts else WordStatus.NEW


def _leaves(status: WordStatus) -> bool:
    """A status that takes a word out of our curriculum's set."""
    return status in (WordStatus.KNOWN, WordStatus.IGNORED)


def _latest_first(found: tuple[datetime | None, EntryId]) -> tuple[float, str]:
    at, entry_id = found
    return (-(at.timestamp() if at else 0.0), entry_id)


def _stored_deck_word(word: DeckWord) -> StoredDeckWord:
    return StoredDeckWord(
        word.entry_id,
        word.headword,
        word.traditional,
        word.reading,
        word.meaning,
        word.sentence,
        word.translation,
        word.learned_at,
    )


def _stored_word(word: SavedWord) -> StoredSavedWord:
    return StoredSavedWord(
        word.entry_id,
        word.headword,
        word.traditional,
        word.reading,
        word.meaning,
        word.category_id,
        word.source_sentence,
        word.source_translation,
        word.saved_at,
    )


def _stored_sentence(sentence: SavedSentence) -> StoredSentence:
    return StoredSentence(
        sentence.id,
        sentence.original,
        sentence.translation,
        tuple(
            StoredSentencePart(
                p.original,
                p.translation,
                tuple((*k.original, *k.translation, k.key) for k in p.links),
                p.speaker,
            )
            for p in sentence.parts
        ),
        sentence.translation_language,
        sentence.category_id,
        sentence.saved_at,
    )


def _sentence(stored: StoredSentence) -> SavedSentence:
    return SavedSentence(
        stored.id,
        stored.original,
        stored.translation,
        tuple(
            SentencePart(
                p.original,
                p.translation,
                tuple(SentenceLink((a, b), (c, d), key) for a, b, c, d, key in p.links),
                p.speaker,
            )
            for p in stored.parts
        ),
        stored.category_id,
        stored.saved_at,
        stored.translation_language,
    )
