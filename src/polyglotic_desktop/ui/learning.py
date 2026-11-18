"""What the learning views share: the learner's vocabulary and dictionary,
and a Qt signal when either changes.

`LearningTools` is handed to every learning view (the lookup popup, the
vocabulary page, the developer view). It holds no rules of its own: it
asks Lexicon for the words in a line and Learning (`Vocabulary`) for
everything about the learner, and turns `Vocabulary`'s change events into
the `changed` signal views redraw on.

One `LearningTools` per language learned that has a dictionary here - a
full one (Chinese, English) or a pack's (Russian, Spanish...: decision
0175) - each with its own
dictionary and learning data; the main language's holds the others
(`also`, DECISIONS #110, decision 0095). A view asks the main one for the
tools of a line's language (`of`): a Chinese line is looked up, split,
marked, counted and saved in Chinese's, an English one in English's,
whichever is main. Their changes reach the main one's `changed` and
`dictionary_ready`, so a view connects to the main one only.
"""

import bisect
import threading
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass

from PySide6.QtCore import QObject, Signal, Slot

from polyglotic_desktop.core.learning.bands import FREQUENCY_BANDS
from polyglotic_desktop.core.learning.exposures import in_learned_language
from polyglotic_desktop.core.learning.knowledge import Knowledge
from polyglotic_desktop.core.learning.languages import learned_code
from polyglotic_desktop.core.learning.levels import (
    UNKNOWN_LEVEL_LINKS_FROM,
    WORDS,
    LanguageChoices,
)
from polyglotic_desktop.core.learning.load import LoadRules
from polyglotic_desktop.core.learning.vocabulary import (
    Changed,
    EntryText,
    FactsRead,
    Vocabulary,
    VocabularyChanged,
)
from polyglotic_desktop.core.lexicon import compounds
from polyglotic_desktop.core.lexicon.basic import BasicDictionary, absent
from polyglotic_desktop.core.lexicon.chinese import (
    ChineseDictionary,
    as_names,
    has_han,
)
from polyglotic_desktop.core.lexicon.english import EnglishDictionary
from polyglotic_desktop.core.lexicon.english import word_at as english_word_at
from polyglotic_desktop.core.lexicon.entries import DictionaryEntry
from polyglotic_desktop.core.lexicon.meanings import short_meaning
from polyglotic_desktop.core.lexicon.scripts import fits, written_in
from polyglotic_desktop.core.shared import (
    EntryFacts,
    EntryId,
    LearningEvent,
    WordInLine,
)
from polyglotic_desktop.ports.anki_deck import AnkiDeckWriter
from polyglotic_desktop.ports.dictionary import DictionaryProblem
from polyglotic_desktop.ports.learning import SetAsideLearningData

_BASIC_KNOWLEDGE = Knowledge.by_line(UNKNOWN_LEVEL_LINKS_FROM)
"""What the learner knows in a basic dictionary's language: a line alone
(`LearningTools.knowledge_of`)."""


@dataclass(frozen=True)
class _ReadAhead:
    """What `prepare`'s thread read for Words: facts, and the bands' sizes
    (the scheme, by frequency, by level)."""

    facts: FactsRead
    band_sizes: tuple[str, list[int], Mapping[int, int]]


class PlacedAhead:
    """The dictionary's words in the order of their places, kept once
    read, for the learning load (polyglotic-hq 324): the load asks on the
    interface thread, and a read of the dictionary's file is 50-100 ms
    there (measured 2026-11-14). `LearningTools.set_load_rules` reads what
    a load will ask for on a thread of its own first (`__call__` from
    there); the load's own asking is then answered from what is kept.
    What it doesn't hold yet is read where it is asked - the interface
    thread, for a load that outran what was read ahead.

    It keeps one run of words: those placed past `_start` up to `_end`,
    every one of them. Asked from inside that run, it answers from it and
    reads on from its end; asked from anywhere else (the known line
    moved, another level scheme), it starts again from there. An answer
    ends at a place's last word, as the dictionary's own do."""

    BATCH = 200
    """The fewest words read from the dictionary at a time."""

    def __init__(
        self, read: Callable[[int, int, str], Sequence[tuple[int, EntryFacts]]]
    ) -> None:
        self._read = read
        self._lock = threading.Lock()
        self._scheme: str | None = None
        self._start = self._end = 0
        self._words: list[tuple[int, EntryFacts]] = []
        self._all = False  # the dictionary has no more

    def __call__(
        self, after: int, limit: int, scheme: str
    ) -> Sequence[tuple[int, EntryFacts]]:
        with self._lock:
            if scheme != self._scheme or not self._start <= after <= self._end:
                self._scheme, self._start, self._end = scheme, after, after
                self._words, self._all = [], False
            first = bisect.bisect_right(self._words, after, key=lambda word: word[0])
            while len(self._words) - first < limit and not self._all:
                batch = self._read(self._end, max(limit, self.BATCH), scheme)
                if not batch:
                    self._all = True
                    break
                self._words += batch
                self._end = max(self._end, batch[-1][0])
            last = first + limit
            if last >= len(self._words):
                return self._words[first:]
            place = self._words[last - 1][0]
            while last < len(self._words) and self._words[last][0] == place:
                last += 1
            return self._words[first:last]

    def holds(self, after: int, limit: int, scheme: str) -> bool:
        """Whether `limit` words past `after` are answered without a read."""
        with self._lock:
            if scheme != self._scheme or not self._start <= after <= self._end:
                return False
            first = bisect.bisect_right(self._words, after, key=lambda word: word[0])
            return self._all or len(self._words) - first >= limit


class LearningTools(QObject):
    changed = Signal(str)  # a core.learning.vocabulary.Changed value
    dictionary_out = Signal()
    """The learner's dictionary went out after the start: a query failed on
    a damaged file (polyglotic-hq 199) - `dictionary_problem` says why.
    Emitted on the thread whose query failed - connect queued."""
    learning_damaged = Signal(object)
    """The learning data was found damaged after the start - a save or a
    read failed (polyglotic-hq 206): nothing more is saved on this PC this
    session. Its `SetAsideLearningData`, or None if it couldn't be set
    aside. Emitted on the store's thread - connect queued."""
    learning_deleted = Signal()
    """The learner's learning data on this PC was deleted, with the files
    set aside from it (polyglotic-hq 207): `learning_set_aside` no longer
    names one that's gone (213). Emitted on the store's thread - connect
    queued."""
    learning_not_deleted = Signal()
    """That deletion left some of this language's learning data on this PC
    - the store couldn't be emptied, or a file set aside from it couldn't
    be deleted (polyglotic-hq 306): Home says which language. Emitted on
    the store's thread, after `learning_deleted` - connect queued."""
    dictionary_ready = Signal()
    """The word split's data is read (`prepare`): captions' words can be
    counted and marked. Sent too when the read failed - the split then reads
    it when first asked, rather than captions waiting for good
    (polyglotic-hq 142). Emitted on the reading thread - connect queued."""
    read_ahead_done = Signal()
    """`prepare`'s read of what Words reads is back (`read_ahead`) - or
    failed, and Words reads what it needs itself. Emitted on this thread."""
    load_changed = Signal(object)
    """The learning load changed (polyglotic-hq 324): the entry IDs whose
    stage a caption shows changed (a frozenset - empty when only meetings
    were counted), or None: every word's may have. Sent before `changed`
    says "load"."""
    load_rules_raised = Signal()
    """Words added to the load by hand raised its size
    (`vocabulary.load.rules`): the settings keep it."""
    _read = Signal(object)  # a _ReadAhead or None, from `prepare`'s thread
    _load_words_read = Signal()  # from `set_load_rules`' thread
    _described = Signal(object)  # {EntryId: EntryText}, from `prepare`'s thread

    def __init__(
        self,
        vocabulary: Vocabulary,
        dictionary: ChineseDictionary | EnglishDictionary | BasicDictionary,
        parent: QObject | None = None,
        deck_writer: AnkiDeckWriter | None = None,
        basic: dict[str, BasicDictionary] | None = None,
        dictionary_problem: Callable[[], DictionaryProblem | None] | None = None,
        learning_data_new: bool = False,
        learning_set_aside: SetAsideLearningData | None = None,
        load_words: PlacedAhead | None = None,
        pack: str | None = None,
    ) -> None:
        """`pack`: these are a pack language's (its code, "ru"): the
        learner's dictionary is that language's pack, whichever is open
        now (`dictionary`; decision 0175). `dictionary_problem`: why the learner's dictionary file is out, if
        it is (`main` hands over the file's; polyglotic-hq 199).
        `learning_data_new`: the learning data was started at this start -
        new, or its file set aside (polyglotic-hq 206); `learning_set_aside`:
        that file, if it was. `load_words`: the words the vocabulary's
        learning load takes in, as `main` gave them to it - read ahead
        off the interface thread (`set_load_rules`); None: the load reads
        where it is asked."""
        super().__init__(parent)
        self._load_words = load_words
        self._load_wanted: LoadRules | None = None
        self._load_reader: threading.Thread | None = None
        self._load_words_read.connect(self._load_read)  # queued: from the thread
        self.learning_data_new = learning_data_new
        """The learning data on this PC was started at this start: what the
        server keeps syncs back from the start (polyglotic-hq 206)."""
        self.learning_set_aside = learning_set_aside
        """The learning data file that couldn't be read at this start, or
        was found damaged since, kept where this says - Home and Help tell
        the learner (polyglotic-hq 206)."""
        self.learning_unsaved = False
        """Found damaged since the start: nothing is saved on this PC until
        the next start (`learning_damaged`)."""
        self.learning_damaged.connect(self._learning_damaged)
        self.learning_deleted.connect(self._learning_deleted)
        self.vocabulary = vocabulary
        self._dictionary = dictionary
        self._pack = pack
        self._absent: BasicDictionary | None = None
        self.choices = LanguageChoices()
        """What the learner chose for this language (the learning window's
        size, which words are linked): the settings', handed over by `main`
        (`set_choices`)."""
        self._choices_by_language: dict[str, LanguageChoices] = {}
        """And for every language learned, by its code (`choices_of`)."""
        self._problem = dictionary_problem or (lambda: None)
        self.deck_writer = deck_writer  # None: no deck file export
        self._band_sizes: tuple[str, list[int], Mapping[int, int]] | None = None
        self.read_ahead = False
        """What Words reads for every word met has been read ahead
        (`prepare`) and handed over."""
        self.reading_ahead = False
        """That read is under way: Words, opened meanwhile, says it's reading
        rather than reading it all itself alongside (polyglotic-hq 220: 425
        ms at 10,000 words met on CC-CEDICT), until `read_ahead_done`."""
        self._read.connect(self._ahead)  # queued: emitted on `prepare`'s thread
        self._texts: dict[EntryId, EntryText] = {}
        self.texts_read_ahead = False
        """Every word met's text (`describe`) has been read ahead (`prepare`)
        and handed over: Words' first search reads nothing from the
        dictionary (polyglotic-hq 220)."""
        self._described.connect(self._know_texts)  # queued, as `_read`
        self.basic: dict[str, BasicDictionary] = basic if basic is not None else {}
        """Basic dictionaries by caption language, for lookups only (decision
        0035): `main`'s own, not a copy - a pack downloaded during the run
        is looked up from the next hover (decision 0122). Every language's
        tools open beside these hold the same dict (306)."""
        self._beside = False
        """Open beside another language's tools (`learn_beside`): the basic
        packs it shares are warmed by those."""
        self.also: dict[str, LearningTools] = {}
        """The other full languages learned, by code, each open beside this
        one with its own dictionary and learning data (`learn_beside`);
        empty in each of them."""
        vocabulary.subscribe(self._on_event)

    @property
    def dictionary(self) -> ChineseDictionary | EnglishDictionary | BasicDictionary:
        """The learner's dictionary. A pack language's is its pack as the
        lookups hold it now (`basic`): one downloaded again during the run
        is the dictionary from then on, and one removed leaves a
        dictionary that finds nothing (`lexicon.basic.absent`) - the
        learning data stays open either way."""
        if self._pack is None:
            return self._dictionary
        found = self.basic.get(self._pack)
        if found is not None:
            return found
        if self._absent is None:
            self._absent = absent(self._pack)
        return self._absent

    def learn_beside(self, other: "LearningTools") -> None:
        """`other` - another language's tools - open beside these: a
        line in its language goes to it (`of`); its changes and its word
        split's readiness come out of these (`changed`, `dictionary_ready`)
        too, so views connect to these alone. A line in a pack's language
        that isn't learned stays with these (`of`). Each language once;
        never these' own."""
        code = other.language
        if code == self.language or code in self.also:
            return
        self.also[code] = other
        other._beside = True
        other.set_choices(  # its own window and links (323), as these hold them
            self._choices_by_language.get(code, LanguageChoices()),
            self._choices_by_language,
        )
        other.changed.connect(self.changed)
        other.dictionary_ready.connect(self.dictionary_ready)

    def of(self, language: str | None) -> "LearningTools":
        """The tools for a line in `language`: its own language's if that's
        learned too and open (`also`: a full dictionary's, or a pack's),
        else these - the main language's, which also look up a pack's
        language that isn't learned and say "Learn it too?". Unknown
        (None): these."""
        if language is not None:
            found = self.also.get(learned_code(language))
            if found is not None:
                return found
        return self

    def word_language(self, word: str, language: str | None) -> str | None:
        """The language `word`, in a row in `language`, is looked up in: the
        one its script says (`lexicon.scripts.written_in`) - a Chinese word
        in an English row, an English one in a Chinese row, a Russian one
        in either - when that language is learned and has its dictionary
        here: a full one open (these' or `also`), or a basic pack opened
        (`basic`) for a language learned (`choices_of`). Else the row's
        (polyglotic-hq 337)."""
        own = written_in(word, language)
        if own is None:
            return language
        if own == self.language or own in self.also:
            return own
        if own in self.basic and self.choices_of(own) is not None:
            return own
        return language

    def has_dictionary(self, language: str | None) -> bool:
        """Whether a word in `language` can be looked up here: its full
        dictionary is open (these' or `also`), or its basic pack is."""
        if not language:
            return False
        code = learned_code(language)
        other = self.also.get(code)
        return (
            code == self.language
            or (other is not None and other._pack is None)
            or language in self.basic
            or code in self.basic
        )

    def dictionaries_for(
        self, word: str, language: str | None, fallbacks: Sequence[str] = ()
    ) -> list[str]:
        """The languages `word`, in a row in `language`, is looked up in, in
        turn, until one has it (the user, 2026-11-15; polyglotic-hq 337):
        1. its own script's language, where that's learned
           (`word_language`);
        2. the row's language;
        3. and 4. `fallbacks`: the window's translation target, then its
           second translation language;
        5. every other language learned with a dictionary here whose
           writing fits the word (`lexicon.scripts.fits`).
        Only those with a dictionary here (`has_dictionary`), each once;
        Chinese's only for a word with Chinese characters - another is
        "Chinese for it", never a Latin headword of CC-CEDICT's."""
        learned = [self.language, *self.also] + [
            code for code in self.basic if self.choices_of(code) is not None
        ]
        steps = [
            self.word_language(word, language),
            language,
            *fallbacks,
            *(code for code in learned if fits(word, code)),
        ]
        chain: list[str] = []
        for code in steps:
            if not self.has_dictionary(code):
                continue
            assert code is not None
            if learned_code(code) in {learned_code(c) for c in chain}:
                continue
            if (
                learned_code(code) == "zh"
                and code not in self.basic
                and not has_han(word)
            ):
                continue
            chain.append(code)
        return chain

    def found_in(
        self, word: str, language: str | None, fallbacks: Sequence[str] = ()
    ) -> str | None:
        """The first language of `dictionaries_for` whose dictionary has
        `word`; None if none has it."""
        return next(
            (
                code
                for code in self.dictionaries_for(word, language, fallbacks)
                if self.lookup(word, code)
            ),
            None,
        )

    @property
    def every(self) -> "tuple[LearningTools, ...]":
        """These, then each other full language's (`also`), in order."""
        return (self, *self.also.values())

    @Slot(object)
    def _learning_damaged(self, aside: SetAsideLearningData | None) -> None:
        self.learning_unsaved = True
        if aside is not None:
            self.learning_set_aside = aside

    @Slot()
    def _learning_deleted(self) -> None:
        """Forgotten once it's gone: one that couldn't be deleted (in use),
        or a folder set aside (kept: what's in it may not be the app's), is
        still named. `learning_unsaved` stays: the store is still out until
        a restart."""
        aside = self.learning_set_aside
        if aside is not None and not aside.path.exists():
            self.learning_set_aside = None

    def _on_event(self, event: LearningEvent | VocabularyChanged) -> None:
        if isinstance(event, VocabularyChanged):
            if event.what is Changed.LOAD:
                self.load_changed.emit(event.entries)
            self.changed.emit(event.what.value)

    LOAD_MARGIN = 400
    """The words read ahead past a load's size: the next to enter that
    Learning lists, "Add the next 50", and some two hundred graduations."""

    def set_load_rules(self, rules: LoadRules | None) -> None:
        """The learning load's rules (`Vocabulary.set_load_rules`; None: the
        mode off, at once). A load turned on or made larger reads the
        dictionary's words in order - 50-100 ms: that is read on a thread
        of its own first, and the rules are set when it is back, on this
        thread. Asked again meanwhile, the last rules asked for are set."""
        self._load_wanted = rules
        vocabulary, ahead = self.vocabulary, self._load_words
        if rules is None or rules == vocabulary.load.rules or ahead is None:
            vocabulary.set_load_rules(rules)
            return
        if self._load_reader is not None:
            return  # reading: `_load_read` sets what is wanted then
        line = vocabulary.line
        after = line.known if line is not None and line.scale == WORDS else 0
        wanted, scheme = rules.size + self.LOAD_MARGIN, vocabulary.scheme
        if ahead.holds(after, wanted, scheme):
            vocabulary.set_load_rules(rules)
            return

        def read() -> None:
            try:
                ahead(after, wanted, scheme)
            finally:  # failed too: the load then reads what it needs itself
                self._load_words_read.emit()

        self._load_reader = threading.Thread(target=read, name="load", daemon=True)
        self._load_reader.start()

    @Slot()
    def _load_read(self) -> None:
        """The read is back: the rules wanted now are set. Larger since, or
        the read failed: the load reads the rest itself."""
        self._load_reader = None
        if self._load_wanted is not None:
            self.vocabulary.set_load_rules(self._load_wanted)

    def load_rules_settled(self, timeout: float = 5.0) -> None:
        """Waits for a read `set_load_rules` started and sets the rules it
        was for - for a test, and for closing."""
        reader = self._load_reader
        if reader is not None:
            reader.join(timeout)
            self._load_read()

    def add_to_load(self, entry_id: EntryId) -> bool:
        """One word into the learning load by hand; its size goes up by
        it, which the settings then keep (`load_rules_raised`)."""
        added = self.vocabulary.add_to_load(entry_id)
        if added:
            self.load_rules_raised.emit()
        return added

    def add_next_to_load(self, count: int) -> None:
        """The next `count` words into the learning load now; its size
        goes up by them, which the settings then keep."""
        self.vocabulary.add_next_to_load(count)
        self.load_rules_raised.emit()

    @property
    def dictionary_problem(self) -> DictionaryProblem | None:
        """Why the learner's dictionary is out - None while it answers.
        While it's out, it answers nothing: captions run without word marks
        or counting, and a lookup says what's wrong and how to fix it."""
        return self._problem()

    @property
    def ready(self) -> bool:
        """Whether every word split - these' and each other full language's
        (`also`) - answers without reading its dictionary first
        (`ChineseDictionary.ready`; an English dictionary always)."""
        return all(tools.dictionary.ready for tools in self.every)

    def prepare(self) -> None:
        """Reads ahead, on a thread of its own: what the word split needs
        (about 0.2 s for CC-CEDICT), then `dictionary_ready`; then what
        Words reads for every word met - each one's facts and the bands'
        sizes - handed back to this thread (`read_ahead`), then each one's
        text, which Words' search reads (`texts_read_ahead`: about 150 ms more
        at 10,000 words met on CC-CEDICT, polyglotic-hq 220). Until the split's
        data is read a caption shows at once, its words counted and marked
        when it's read - never waiting on the interface thread
        (polyglotic-hq project 136: the first Chinese caption froze the
        interface for up to 0.9 s); Words opened first says it's reading
        (`reading_ahead`) until it's back. Each other full language's
        (`also`) reads on a thread of its own the same way."""
        if self.basic and not self._beside:  # the packs are shared: once
            threading.Thread(
                target=self._warm_basic, name="basic dictionaries", daemon=True
            ).start()
        for other in self.also.values():
            other.prepare()
        dictionary = self.dictionary
        splits = isinstance(dictionary, ChineseDictionary) and not dictionary.ready
        facts = self.vocabulary.facts_to_read()
        scheme = self.vocabulary.scheme
        met = [e for e in self.vocabulary.met_entries() if e not in self._texts]

        def read() -> None:
            ahead = None
            try:
                if splits and isinstance(dictionary, ChineseDictionary):
                    try:
                        dictionary.prepare()
                    finally:  # failed too: see `dictionary_ready`
                        self.dictionary_ready.emit()
                sizes = (
                    scheme,
                    dictionary.words_in_ranks(FREQUENCY_BANDS),
                    dictionary.words_at_levels(scheme),
                )
                ahead = _ReadAhead(facts(), sizes)
            finally:  # failed too: Words isn't left waiting
                self._read.emit(ahead)
            texts = {}
            for entry_id in met:
                text = _text(dictionary, entry_id)
                if text is not None:
                    texts[entry_id] = text
            self._described.emit(texts)

        self.reading_ahead = True
        threading.Thread(target=read, name="dictionary", daemon=True).start()

    @Slot(object)
    def _ahead(self, ahead: _ReadAhead | None) -> None:
        if ahead is not None:
            self.vocabulary.know_facts(ahead.facts)
            if self._band_sizes is None:
                self._band_sizes = ahead.band_sizes
            self.read_ahead = True
        self.reading_ahead = False
        self.read_ahead_done.emit()

    @Slot(object)
    def _know_texts(self, texts: Mapping[EntryId, EntryText]) -> None:
        """Texts read ahead. A word the read didn't find is asked for again
        when wanted - the dictionary may have been out."""
        for entry_id, text in texts.items():
            self._texts.setdefault(entry_id, text)
        self.texts_read_ahead = True

    def _warm_basic(self) -> None:
        """Each basic dictionary's word split reads its data on first use -
        simplemma's Spanish about 0.5 s - so a first word here, off the
        interface thread, keeps the first hover from waiting on it."""
        for basic in self.basic.values():
            basic.words("a")

    @property
    def is_chinese(self) -> bool:
        """For a Chinese learner (CC-CEDICT), not an English one (ECDICT)."""
        return isinstance(self.dictionary, ChineseDictionary)

    @property
    def language(self) -> str:
        """The language being learned: `zh`, `en`, or a pack's (`ru`)."""
        if self._pack is not None:
            return self._pack
        return "zh" if self.is_chinese else "en"

    def learns(self, caption_language: str | None) -> bool:
        """Whether a caption in `caption_language` counts as heard - its
        exposures, coverage and listening time: only one in the language
        being learned (`exposures.in_learned_language`)."""
        return in_learned_language(caption_language, self.language)

    def set_choices(
        self,
        choices: LanguageChoices,
        learned: Mapping[str, LanguageChoices] | None = None,
    ) -> None:
        """The learner's choices for this language, from the settings, and
        (`learned`) for each other language they learn, by its code: what
        captions mark and link follows, as it does a change of level
        (`changed`). Each other full language open beside these (`also`)
        gets its own, so its lines follow its window and links (306)."""
        by_language = {**(learned or {}), self.language: choices}
        # our curriculum and the quiet view's words at your edge follow the
        # window's size the learner chose (polyglotic-hq 496)
        self.vocabulary.set_window_size(choices.window_size)
        if (choices, by_language) != (self.choices, self._choices_by_language):
            self.choices, self._choices_by_language = choices, by_language
            self.changed.emit(Changed.LEVEL.value)
        for other in self.also.values():  # each open beside: its own (306)
            other.set_choices(
                by_language.get(other.language, LanguageChoices()), learned
            )

    def choices_of(self, language: str | None) -> LanguageChoices | None:
        """What the learner chose for a row in `language`; None if it isn't
        a language they learn."""
        if not language:
            return None
        return self._choices_by_language.get(learned_code(language))

    def band_sizes(self) -> tuple[list[int], Mapping[int, int]]:
        """How many words each of Words' frequency bands has
        (`FREQUENCY_BANDS`), and each level of the learner's scheme - read
        from the dictionary once per scheme (about 40 ms for CC-CEDICT)."""
        scheme = self.vocabulary.scheme
        if self._band_sizes is None or self._band_sizes[0] != scheme:
            self._band_sizes = (
                scheme,
                self.dictionary.words_in_ranks(FREQUENCY_BANDS),
                self.dictionary.words_at_levels(scheme),
            )
        return self._band_sizes[1], self._band_sizes[2]

    def words_in(
        self,
        line: str,
        language: str | None = None,
        said: Iterable[tuple[int, int, str]] = (),
    ) -> list[WordInLine]:
        """The words of a line in `language` (None: the main language's), by
        the word split of its own language's tools (`of`) - or, for a
        pack's language not learned, of its pack, with its ranks (word
        links, 338). `said`: what a translation says for words of the line
        (start, end, its word link's words): a Chinese word it writes by
        its sound is a name (`ChineseDictionary.named_by_sound`: 万里 of
        黄万里, "Huang Wanli"; polyglotic-hq 496)."""
        if language is not None and self.is_basic(language):
            return self.basic[language].words_in(line, self.vocabulary.scheme)
        tools = self.of(language)
        found = tools.dictionary.words_in(line, tools.vocabulary.scheme)
        dictionary = tools.dictionary
        if not isinstance(dictionary, ChineseDictionary):
            return found
        return as_names(found, dictionary.named_by_sound(line, said))

    def is_basic(self, language: str | None) -> bool:
        """Whether a row in `language` is looked up in a pack only - no
        learning data is open for it (it isn't learned, or its pack came
        after the start and its data opens in a moment): nothing is kept
        of its words. A pack's language learned and open is its own tools'
        (`of`), like Chinese and English (decision 0175)."""
        if language is None or language not in self.basic:
            return False
        code = learned_code(language)
        return code != self.language and code not in self.also

    def knowledge_of(self, language: str | None) -> Knowledge | None:
        """What the learner knows in a row's `language` - the one answer
        per word (`Knowledge.of`, polyglotic-hq 349, 373): its own full
        language's (`of`); a pack's language that isn't learned, its ranks
        and a line only (nothing is kept for it; "Start links at" moves
        it, `UNKNOWN_LEVEL_LINKS_FROM` until then);
        None where no dictionary here knows its words."""
        if self.is_basic(language):
            return _BASIC_KNOWLEDGE
        tools = self.of(language)
        return tools.vocabulary.knowledge if tools.learns(language) else None

    def word_at(
        self, line: str, index: int, language: str | None = None
    ) -> tuple[int, int] | None:
        """The word a lookup shows at `line[index]` of a row in `language`
        (None: not known): by a basic dictionary's word split if there's
        one for it; else a Chinese word by the word split, or a word of
        any spaced language. A character whose script is another language
        learned here is split by that language's (`word_language`; polyglotic-hq
        337): a Chinese word in an English or Russian row is found, a
        Russian one in an English row by its pack's. A basic row keeps its
        own split for its own words and for Latin ones (Japanese's splits
        "OKです" where English's wouldn't)."""
        here = self.word_language(line[index : index + 1], language)
        if language is not None and language in self.basic and here in (language, "en"):
            return self.basic[language].word_at(line, index)
        if here is not None and here in self.basic:
            return self.basic[here].word_at(line, index)
        dictionary = self.of(here).dictionary
        if isinstance(dictionary, ChineseDictionary) and has_han(
            line[index : index + 1]
        ):
            return dictionary.word_at(line, index)
        return english_word_at(line, index)

    def lookup(self, word: str, language: str | None = None) -> list[DictionaryEntry]:
        """The entries for `word` from a row in `language`: in its basic
        dictionary if there's one, else its own full language's if that's
        learned (`of`), else the main language's."""
        if language is not None and language in self.basic:
            return self.basic[language].lookup(word)
        return self.of(language).dictionary.lookup(word)

    def form_reading(self, word: str, language: str | None = None) -> str:
        """How `word` itself is said, where a basic dictionary's pack marks
        it (Russian's stress on an inflected form) - "" otherwise."""
        if language is not None and language in self.basic:
            return self.basic[language].form_reading(word)
        return ""

    def parts(self, word: str, language: str | None = None) -> list[compounds.Part]:
        """The words a word a basic dictionary hasn't got is made of (a
        hyphenated word, a German compound: `BasicDictionary.parts`) - []
        in any other row."""
        if language is not None and language in self.basic:
            return self.basic[language].parts(word)
        return []

    def entry(self, entry_id: EntryId) -> DictionaryEntry | None:
        return self.dictionary.entry(entry_id)

    def describe(self, entry_id: EntryId) -> EntryText | None:
        """An entry's text from the dictionary - Words' rows and its search,
        and words in the Anki file that were put in the deck without a
        lookup here: read ahead for every word met (`prepare`), else read
        now."""
        text = self._texts.get(entry_id)
        return text if text is not None else _text(self.dictionary, entry_id)

    def facts(self, entry: DictionaryEntry) -> EntryFacts:
        return entry.facts(self.vocabulary.scheme)


def _text(
    dictionary: ChineseDictionary | EnglishDictionary | BasicDictionary,
    entry_id: EntryId,
) -> EntryText | None:
    """An entry's text (`LearningTools.describe`), read from the dictionary."""
    entry = dictionary.entry(entry_id)
    if entry is None:
        return None
    return EntryText(
        entry.headword, entry.traditional, entry.reading, short_meaning([entry])
    )
