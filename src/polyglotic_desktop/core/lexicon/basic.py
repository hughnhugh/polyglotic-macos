"""Basic dictionaries: lookups in a caption language beyond Chinese and
English, from a dictionary pack (decision 0035; polyglotic-hq project
157's "basic" tier - open data, no human check of the meanings).

A pack is a dictionary file like CC-CEDICT's, plus a word split for its
language (`ports.word_split`): Sudachi for Japanese, letters and
simplemma for Spanish. A word in a caption is looked up as, in order:
1. the dictionary forms the word split found for it in its line
   (Japanese: "食べ" in 食べました is 食べる);
2. the pack's own inflection table, then the word's own entries - as
   written, then in lower case (Spanish: "supe" is saber; "casa" is
   house);
3. the word split's out-of-context guesses (simplemma's lemma, then a
   word without its clitics: والكتاب, كتاب), if nothing else was found -
   the first guess that finds anything, so a likelier guess's entries
   aren't shown beside a far-fetched one's (polyglotic-hq 380).

A word none of these finds may still be made of words the pack has: a
hyphenated word, or a German compound (`parts`, `core.lexicon.compounds`).
Its lookup still finds nothing - it isn't in the dictionary as a whole -
but the card shows its parts, and a caption's words (`words_in`) are its
parts, each over its own letters, so a link over it is known only when
every part is (polyglotic-hq 390).

Entries keep their pack's IDs (`jmdict:`, `wiktes:`), so statuses and
lookups reach the server as they do for Chinese and English.

A pack's meanings are in its own language (English). Where a meanings file
in the learner's language is beside it (`explain_in`; decision 0234), an
entry it has is shown with those meanings instead; one it hasn't keeps the
pack's.

A pack's language being learned keeps learning data of its own (decision
0175; polyglotic-hq 391): the pack is then that learner's dictionary, as
CC-CEDICT is a Chinese learner's - `facts`, `words_past`, `words_in_ranks`
and the rest answer what Learning asks of one, from the pack's frequency
ranks (a pack has no levels: the line is a number of words, DECISIONS
#176).
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import replace

from polyglotic_desktop.core.lexicon import compounds, furigana
from polyglotic_desktop.core.lexicon.english import entry_from_record as english_entry
from polyglotic_desktop.core.lexicon.entries import (
    DictionaryEntry,
    explained,
    words_in_runs,
)
from polyglotic_desktop.core.shared import EntryFacts, EntryId, WordInLine
from polyglotic_desktop.ports.dictionary import (
    DictionaryFile,
    EntryRecord,
    MeaningsFile,
)
from polyglotic_desktop.ports.word_split import SplitWord, WordSplit

NAME = "(name) "
"""How a pack's meanings start for a name: packs write "(pos) meaning"."""
SMALL_WORDS = ("(article) ", "(pron) ", "(det) ", "(conj) ")
"""How a pack's meanings start for a small word, which is no part of a
closed compound: "schreienden" isn't schreien + den (polyglotic-hq 390)."""
PARTS_KEPT = 2048
"""How many words' parts a dictionary keeps worked out (`parts`)."""


def entry_from_record(record: EntryRecord) -> DictionaryEntry:
    """A pack's entry. A name is what the pack says is one - every meaning
    a name's - not a capitalised headword, as English's rule has it:
    German writes every noun with a capital, and its nouns had all been
    names, never pointed out as new nor counted as heard (polyglotic-hq
    380). No spoken ranks: those are English's and Mandarin's (491)."""
    return replace(
        english_entry(record),
        is_name=bool(record.meanings)
        and all(m.startswith(NAME) for m in record.meanings),
        spoken_rank=None,
        is_filler=False,
        spells_a_number=False,
        names_capitalised=False,  # German capitalises its nouns
    )


class BasicDictionary:
    """One language's pack: lookups, the word split, and the entry a word
    in a caption counts for. `language` is the caption language it serves
    ("ja", "es")."""

    def __init__(self, file: DictionaryFile, split: WordSplit, language: str) -> None:
        self._file = file
        self._split = split
        self.language = language
        self._parts: dict[str, list[compounds.Part]] = {}
        self._meanings: MeaningsFile | None = None

    def explain_in(self, meanings: MeaningsFile | None) -> None:
        """Entries are shown with `meanings`' meanings from now on, where it
        has them (None: the pack's own; decision 0234)."""
        self._meanings = meanings

    def _entry(self, record: EntryRecord) -> DictionaryEntry:
        return explained(entry_from_record(record), self._meanings)

    @property
    def ready(self) -> bool:
        """Always: nothing is read up front (`ChineseDictionary.ready`)."""
        return True

    @property
    def word_split(self) -> WordSplit:
        """The language's word split."""
        return self._split

    @property
    def is_absent(self) -> bool:
        """Whether this dictionary stands in for a pack that isn't installed."""
        return isinstance(self._split, _NoSplit)

    @property
    def has_sense_classes(self) -> bool:
        return getattr(self._file, "has_sense_classes", True)

    def class_entries(self, word: str, split: SplitWord) -> list[DictionaryEntry]:
        """Entries from the exact token and trusted routes, with its reading."""
        found = self._lookup_split(word, split, for_classes=True)
        if self.language != "ja" or not found:
            return found
        readings = {
            furigana.hiragana(entry.reading or entry.headword) for entry in found
        }
        if len(readings) == 1 and not split.kana:
            return found
        kana = furigana.hiragana(split.kana)
        return [
            entry
            for entry in found
            if kana and furigana.hiragana(entry.reading or entry.headword) == kana
        ]

    def words(self, text: str) -> list[tuple[int, int]]:
        """(start, end) of each word in `text`, by the word split."""
        return [(w.start, w.end) for w in self._split.words(text)]

    def split(self, text: str) -> Sequence[SplitWord]:
        """Each word in `text` as the word split saw it in its line - with
        its reading, where the split gives one (Japanese's furigana,
        `furigana`)."""
        return self._split.words(text)

    def word_at(self, text: str, index: int) -> tuple[int, int] | None:
        """(start, end) of the word at `index`, or None between words."""
        for word in self._split.words(text):
            if word.start <= index < word.end:
                return word.start, word.end
        return None

    def lookup(self, word: str) -> list[DictionaryEntry]:
        """The entries for `word` (a word or phrase as the learner picked
        it), best first. A single word is split first, for the dictionary
        form its analyser finds."""
        split = self._split.words(word)
        if len(split) == 1 and (split[0].start, split[0].end) == (0, len(word)):
            return self.lookup_split(word, split[0])
        return self.lookup_split(word, SplitWord(0, len(word)))

    def lookup_split(self, word: str, split: SplitWord) -> list[DictionaryEntry]:
        """The entries for `word` as the word split saw it in its line
        (see the module's order), best first."""
        return self._lookup_split(word, split)

    def _lookup_split(
        self, word: str, split: SplitWord, *, for_classes: bool = False
    ) -> list[DictionaryEntry]:
        word = word.replace("’", "'")
        found: dict[str, DictionaryEntry] = {}
        entry = entry_from_record if for_classes else self._entry

        def add(records: Sequence[EntryRecord]) -> None:
            for record in records:
                if record.entry_id not in found:
                    found[record.entry_id] = entry(record)

        for lemma in split.lemmas:
            add(self._file.records(lemma))
        for form in dict.fromkeys((word, word.lower())):
            inflected_from = self._file.lemma(form)
            if inflected_from:
                add(self._file.records(inflected_from))
            add(self._file.records(form))
            if found and not for_classes:
                break
        for guess in () if for_classes else split.guesses:
            for form in dict.fromkeys((guess, guess.lower())):
                if found:
                    break
                inflected_from = self._file.lemma(form)
                if inflected_from:
                    add(self._file.records(inflected_from))
                add(self._file.records(form))
        return list(found.values())

    def parts(self, word: str) -> list[compounds.Part]:
        """The words `word` is made of, if the pack hasn't got it whole and
        it's a hyphenated word or a compound of words it has (Blog-Erfahrung;
        Internetmaterialien: Internet, Materialien) - [] otherwise."""
        word = word.replace("’", "'")
        if word not in self._parts:
            if len(self._parts) >= PARTS_KEPT:
                self._parts.clear()
            found = compounds.parts(word, self.language, self._find)
            self._parts[word] = found if found and not self.lookup(word) else []
        return self._parts[word]

    def _find(self, form: str, names_too: bool) -> int | None:
        """The rank of the commonest entry `form`, as written, finds (an
        inflection's lemma's or its own), or None if it finds none
        (`compounds.Find`). A closed compound's part is no name and no
        small word (`SMALL_WORDS`)."""
        inflected_from = self._file.lemma(form)
        records = [
            *(self._file.records(inflected_from) if inflected_from else ()),
            *self._file.records(form),
        ]
        if not names_too:
            records = [
                r
                for r in records
                if not entry_from_record(r).is_name
                and not all(m.startswith(SMALL_WORDS) for m in r.meanings)
            ]
        if not records:
            return None
        ranks = [r.frequency_rank for r in records if r.frequency_rank]
        return min(ranks, default=compounds.UNRANKED)

    def form_reading(self, word: str) -> str:
        """How `word` itself is said, as written or in lower case, where the
        pack marks it ("руку": "ру́ку"; Russian's stress moves as a word
        inflects) - "" if it doesn't."""
        word = word.replace("’", "'")
        for form in dict.fromkeys((word, word.lower())):
            reading = self._file.form_reading(form)
            if reading:
                return reading
        return ""

    def words_in(self, text: str, scheme_id: str) -> list[WordInLine]:
        """The words in `text` the pack has, each with the entry it counts
        for and the facts Learning needs - as `EnglishDictionary.words_in`."""
        out = []
        for split in self._split.words(text):
            word = text[split.start : split.end]
            entries = self.lookup_split(word, split)
            if entries:
                out.append(
                    WordInLine(split.start, split.end, entries[0].facts(scheme_id))
                )
                continue
            for part in self.parts(word):
                found = self.lookup(part.form) if part.found else []
                if found:
                    out.append(
                        WordInLine(
                            split.start + part.start,
                            split.start + part.end,
                            found[0].facts(scheme_id),
                        )
                    )
        return out

    def entry(self, entry_id: EntryId) -> DictionaryEntry | None:
        """The entry with this ID - or the one it was merged into."""
        record = self._file.record(entry_id)
        return self._entry(record) if record else None

    def facts(self, entry_id: EntryId, scheme_id: str) -> EntryFacts | None:
        """`entry(entry_id).facts(scheme_id)`: what Learning asks for every
        word met (as `EnglishDictionary.facts`)."""
        entry = self.entry(entry_id)
        return entry.facts(scheme_id) if entry else None

    def words_in_ranks(self, runs: Sequence[tuple[int, int]]) -> list[int]:
        """How many words each run of frequency ranks (first, last) has -
        the sizes of Words' bands."""
        last = max((last for _, last in runs), default=0)
        return words_in_runs(self._file.words_ranked(last), runs)

    def words_past(
        self, after: int, limit: int, scheme_id: str
    ) -> list[tuple[int, EntryFacts]]:
        """The words ranked past `after`, most common first, at most
        `limit`, each with its rank and its entry's facts: what a learning
        load takes in (as `EnglishDictionary.words_past`). A form a caption
        counts for another entry (an inflected form with a rank of its
        own) is left out: its entry has its own place."""
        found: list[tuple[int, EntryFacts]] = []
        while not found:
            ranked = self._file.headwords_ranked(after, limit)
            if not ranked:
                break
            for headword, rank in ranked:
                entries = self.lookup(headword)
                if entries and entries[0].headword == headword:
                    found.append((rank, entries[0].facts(scheme_id)))
            after = ranked[-1][1]
        return found

    def words_at_levels(self, scheme_id: str) -> Mapping[int, int]:
        """How many headwords the level scheme puts at each level (a pack
        has levels only where its language has a syllabus in it)."""
        return self._file.words_at_levels(scheme_id)

    def merged_ids(self) -> list[EntryId]:
        """The entry IDs merged into other entries (decision 0007): what
        `Vocabulary.follow_merged_entries` checks when the pack opens."""
        return [EntryId(old) for old in self._file.merged_ids()]


class _NoFile:
    """A pack that isn't on this PC, as a `DictionaryFile`: it has nothing."""

    def headwords(self) -> Iterable[str]:
        return ()

    def frequency_ranks(self) -> Mapping[str, int]:
        return {}

    def records(self, word: str) -> Sequence[EntryRecord]:
        return ()

    def records_by_meaning(
        self, english_word: str, limit: int
    ) -> Sequence[EntryRecord]:
        return ()

    def lemma(self, word: str) -> str | None:
        return None

    def form_reading(self, word: str) -> str:
        return ""

    def record(self, entry_id: str) -> EntryRecord | None:
        return None

    def merged_ids(self) -> Sequence[str]:
        return ()

    def words_ranked(self, last: int) -> Sequence[int]:
        return ()

    def headwords_ranked(self, after: int, limit: int) -> Sequence[tuple[str, int]]:
        return ()

    def headwords_at_levels(self, scheme: str) -> Sequence[tuple[str, int, int | None]]:
        return ()

    def words_at_levels(self, scheme: str) -> Mapping[int, int]:
        return {}


class _NoSplit:
    def words(self, text: str) -> Sequence[SplitWord]:
        return ()


def absent(language: str) -> BasicDictionary:
    """`language`'s dictionary while its pack isn't on this PC - removed
    during the run, or not downloaded again yet - for a learner who keeps
    learning data in it (decision 0175): it finds no word, so their saved
    words show from their own text and nothing new is counted or marked,
    until the pack is back."""
    return BasicDictionary(_NoFile(), _NoSplit(), language)
