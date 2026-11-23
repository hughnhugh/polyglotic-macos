"""English: words in a line, lookups, and inflected forms to their entry.

Word statuses and exposures are counted per entry, so "running", "ran"
and "runs" in a caption all count for "run" (`entry_for_word`), using
ECDICT's inflection data. A form with meanings of its own ("left": 左边的)
is still looked up too: `lookup` shows its lemma's entry first, then its
own - unless the dictionary file lists its own first, where that's the
commoner meaning ("a bit" is 一点, not a bite: polyglotic-hq 464).

A name is an entry written capitalised (`entry_from_record`). Where a name
is also a word ("Bill"), the dictionary has the word first: a sentence's
first word is looked up as the word, a capitalised one inside a sentence
as the name (`names_first`).

Where a meanings file in the learner's language is beside ECDICT
(`explain_in`; decision 0234), an entry it has is shown with those
meanings; one it hasn't keeps the dictionary's own (English, or Chinese).

How a word sounds, respelled for learners (KAY-oss, ri-SEET: stressed
syllable in capitals), is the dictionary's form reading of it - the
10,000 commonest words, from CMUdict by 471's rules (DECISIONS #200: TYME,
uu, ee) - read by the reading line over English (`readings`; polyglotic-hq
511). A heteronym shows its commoner sense (record: REK-erd).
"""

import re
import unicodedata
from collections.abc import Mapping, Sequence

from polyglotic_desktop.core.lexicon import spoken
from polyglotic_desktop.core.lexicon.entries import (
    DictionaryEntry,
    explained,
    words_in_runs,
)
from polyglotic_desktop.core.lexicon.readings import Reading
from polyglotic_desktop.core.shared import EntryFacts, EntryId, WordInLine
from polyglotic_desktop.ports.dictionary import (
    DictionaryFile,
    EntryRecord,
    MeaningsFile,
)

# A word in a spaced language: letters, it's, well-known. Chinese
# characters aren't its letters: in 用iPhone打 the word is iPhone (133).
_LETTER = r"[^\W\d_\u3007\u3400-\u9fff\uf900-\ufaff\U00020000-\U0002ffff]"


def _marks() -> str:
    """A character class of the combining marks a letter carries inside a
    word: Devanagari's vowel signs (हिंदी), Arabic's vowel marks, a
    combining accent. Python's \\w hasn't got them, so a Hindi word had
    been cut at each vowel sign (polyglotic-hq 380). From their blocks
    only (0300-1DFF, and the combining marks for symbols and half marks),
    so the start pays for a few thousand characters, not all of Unicode."""
    found = [
        c
        for block in ((0x0300, 0x1E00), (0x20D0, 0x2100), (0xFE20, 0xFE30))
        for c in range(*block)
        if unicodedata.category(chr(c)).startswith("M")
    ]
    ranges: list[list[int]] = []
    for c in found:
        if ranges and ranges[-1][1] == c - 1:
            ranges[-1][1] = c
        else:
            ranges.append([c, c])
    return "[" + "".join(f"{chr(a)}-{chr(b)}" for a, b in ranges) + "]"


_LETTERS = rf"{_LETTER}(?:{_LETTER}|{_marks()})*"
"""A letter, then letters and the marks they carry."""
_JOINERS = "\u200c\u200d"
"""The zero-width non-joiner and joiner: inside a word, never between two.
Persian writes its plurals and its verbs' prefix with one (داستان‌ها,
می‌کنم): they had been cut there, so "های" was a word of its own
(polyglotic-hq 387)."""
_WORD = re.compile(rf"{_LETTERS}(?:['’{_JOINERS}-]{_LETTERS})*")


def entry_from_record(record: EntryRecord) -> DictionaryEntry:
    """An ECDICT entry. A capitalised headword (other than "I") is a proper
    noun - a name, place, language or day - not shown as unfamiliar. Its
    rank in speech and whether it's a filler: `spoken.ENGLISH`."""
    return DictionaryEntry(
        entry_id=EntryId(record.entry_id),
        headword=record.headword,
        traditional=record.traditional,
        reading=record.reading,
        meanings=record.meanings,
        sense_classes=record.sense_classes,
        sense_prefixes=record.sense_prefixes,
        frequency_rank=record.frequency_rank,
        levels=record.levels,
        is_name=record.headword[:1].isupper() and len(record.headword) > 1,
        spoken_rank=spoken.ENGLISH.rank(record.headword),
        is_filler=spoken.ENGLISH.is_filler(record.headword),
        spells_a_number=record.headword in spoken.ENGLISH_NUMBERS,
        names_capitalised=True,
    )


_CONTRACTED = {
    "can't": "can",
    "won't": "will",
    "shan't": "shall",
    "cannot": "can",
    "gonna": "going",
    "wanna": "want",
    "gotta": "got",
}
"""Contractions whose word isn't their start, and the spoken forms ECDICT
hasn't got: "cannot" is can not, "gonna" going to (going: go's), "wanna"
want to, "gotta" got to (polyglotic-hq 462, 463)."""
_CONTRACTIONS = ("n't", "'re", "'ll", "'ve", "'m", "'d")


def base_words(word: str) -> list[str]:
    """The words a form the dictionary hasn't got may be made from, most
    likely first, for `lookup` to try in turn: a contraction's word (don't:
    do; they're: they), and a regular plural's or verb form's base
    (thousands: thousand; chilies: chili; cities: city; flavorings:
    flavoring). ECDICT's inflection table misses these, so a caption's
    "thousands" or "don't" was in no dictionary: linked at every known
    line, and "Not in the dictionary" on its card (polyglotic-hq 338)."""
    w = word.lower()
    if w in _CONTRACTED:
        return [_CONTRACTED[w]]
    for ending in _CONTRACTIONS:
        if w.endswith(ending) and len(w) > len(ending):
            return [word[: -len(ending)]]  # as written: I'm is I
    if len(w) < 4 or not w.isalpha():
        return []
    found: list[str] = []
    if w.endswith("s") and not w.endswith("ss"):
        found.append(w[:-1])
        if w.endswith("ies"):
            found.append(w[:-3] + "y")
        if w.endswith("es"):
            found.append(w[:-2])
    elif w.endswith("ied"):
        found.append(w[:-3] + "y")
    elif w.endswith("ed"):
        found += [w[:-1], w[:-2]]
    elif w.endswith("ing"):
        found += [w[:-3], w[:-3] + "e"]
    return found


_OPENERS = "\"'“‘«([{-–—  "
"""What may stand between a sentence's end and its first word: spaces,
opening quotes and brackets, a dialogue line's dash."""
_ENDS = ".!?…:;。！？"
"""What ends a sentence, or may be followed by one ("He said: Will...")."""
_QUOTES = '"“‘«'
"""Opening quotes: what follows one starts a sentence ('said "Will you')."""


def inside_sentence(text: str, start: int) -> bool:
    """Whether the word at `start` of `text` is inside a sentence, not its
    first word: something comes before it, the last thing before it (past
    spaces, brackets and dashes) isn't a sentence's end, and no opening
    quote stands between. A line's first word counts as a sentence's: a
    caption's row can begin one ("Will you...")."""
    before = text[:start].rstrip(_OPENERS)
    between = text[len(before) : start]
    return (
        bool(before)
        and before[-1] not in _ENDS
        and not any(q in between for q in _QUOTES)
    )


def is_capitalised(word: str) -> bool:
    """Written with a capital and then lower case ("John", "McDonald",
    "Bill's") - not in capitals ("TV") nor a lone letter ("I")."""
    return word[:1].isupper() and any(c.islower() for c in word[1:])


def names_first(entries: Sequence[DictionaryEntry], word: str) -> list[DictionaryEntry]:
    """`entries` for `word` as written inside a sentence: if it's
    capitalised there, its names first ("and Bill said": Bill, a name, then
    bill, 帐单) - in their order otherwise (polyglotic-hq 464)."""
    if not is_capitalised(word):
        return list(entries)
    return sorted(entries, key=lambda e: not e.is_name)


def words(text: str) -> list[tuple[int, int]]:
    """(start, end) of each word in `text`: runs of letters, with
    apostrophes and hyphens inside ("it's", "well-known")."""
    return [m.span() for m in _WORD.finditer(text)]


def word_at(text: str, index: int) -> tuple[int, int] | None:
    """(start, end) of the word at `index` - None on a space, digit or
    punctuation."""
    for start, end in words(text):
        if start <= index < end:
            return start, end
    return None


class EnglishDictionary:
    """ECDICT for English learners: lookups, and the entry a word in a
    caption counts for. Nothing is loaded up front."""

    def __init__(self, file: DictionaryFile) -> None:
        self._file = file
        self._meanings: MeaningsFile | None = None

    def explain_in(self, meanings: MeaningsFile | None) -> None:
        """Entries are shown with `meanings`' meanings from now on, where it
        has them (None: the dictionary's own; decision 0234)."""
        self._meanings = meanings

    @property
    def ready(self) -> bool:
        """Always: nothing is loaded up front (`ChineseDictionary.ready`)."""
        return True

    @property
    def has_sense_classes(self) -> bool:
        return getattr(self._file, "has_sense_classes", True)

    def class_entries(self, word: str) -> list[DictionaryEntry]:
        """Whole forms only. WordNet can omit the numerical use of a number."""
        found = list(self._entries(word.replace("’", "'"), for_classes=True).values())
        return [] if any(entry.spells_a_number for entry in found) else found

    def lookup(self, word: str, inside: bool = False) -> list[DictionaryEntry]:
        """The entries for `word` as written, trying lower case too
        ("Running" at the start of a sentence): its lemma's entry first if
        it's an inflected form ("running" -> run), then its own. A
        possessive the dictionary hasn't got ("the game's graphics") is its
        word's: ECDICT has no "game's", and the card said "Not in the
        dictionary" (polyglotic-hq 329). `inside`: written so inside a
        sentence, where a capitalised word is a name first (`names_first`):
        the dictionary has "Bill" as the word bill, then the name."""
        word = word.replace("’", "'")
        found = self._entries(word)
        if not found and len(word) > 2 and word[-2:].lower() == "'s":
            found = self._entries(word[:-2])
        for base in () if found else base_words(word):
            found = self._entries(base)
            if found:
                break
        entries = list(found.values())
        return names_first(entries, word) if inside else entries

    def _entries(
        self, word: str, *, for_classes: bool = False
    ) -> dict[str, DictionaryEntry]:
        """`word` as written, then in lower case, then - written in lower
        case and found neither way - capitalised: ECDICT has "North",
        "I" and "Mr" only so, and a lower-case caption's "north", "i'm"
        or "mr" was in no dictionary (polyglotic-hq 462). Never the other
        way round: a name finds its own entry before a word's. A lone
        letter other than "i" isn't: the "s" of "the 1990s" isn't "S",
        sulphur. (Words ECDICT has only in capitals, "TV", are found in
        lower case by the dictionary's own forms: polyglotic-hq 463.)"""
        found: dict[str, DictionaryEntry] = {}
        tried = [word, word.lower()]
        if word.islower() and (len(word) > 1 or word == "i"):
            tried.append(word.capitalize())
        for form in dict.fromkeys(tried):
            if for_classes and found and form != word.lower():
                break
            lemma = self._file.lemma(form)
            for record in [
                *(self._file.records(lemma) if lemma else ()),
                *self._file.records(form),
            ]:
                if record.entry_id not in found:
                    entry = entry_from_record(record)
                    found[record.entry_id] = (
                        entry if for_classes else explained(entry, self._meanings)
                    )
            if found and not for_classes:
                break
        return found

    def entry_for_word(self, word: str, inside: bool = False) -> DictionaryEntry | None:
        """The entry `word` counts for in statuses and exposures: its
        lemma's if it's an inflected form, else its own (or a name's, as
        `lookup` has it `inside` a sentence); None if the dictionary doesn't
        have it."""
        entries = self.lookup(word, inside)
        return entries[0] if entries else None

    def words_in(self, text: str, scheme_id: str) -> list[WordInLine]:
        """The words in `text` the dictionary has, each with the entry it
        counts for and the facts Learning needs for a learner in
        `scheme_id` - for highlights and exposures. A capitalised word
        inside a sentence counts as a name, if it's one ("and Bill said")."""
        found = []
        for start, end in words(text):
            entry = self.entry_for_word(text[start:end], inside_sentence(text, start))
            if entry is not None:
                found.append(WordInLine(start, end, entry.facts(scheme_id)))
        return found

    def entry(self, entry_id: EntryId) -> DictionaryEntry | None:
        """The entry with this ID - or the one it was merged into."""
        record = self._file.record(entry_id)
        if record is None:
            return None
        return explained(entry_from_record(record), self._meanings)

    def facts(self, entry_id: EntryId, scheme_id: str) -> EntryFacts | None:
        """`entry(entry_id).facts(scheme_id)`: what Learning asks for every
        word met (as `ChineseDictionary.facts`)."""
        entry = self.entry(entry_id)
        return entry.facts(scheme_id) if entry else None

    def words_in_ranks(self, runs: Sequence[tuple[int, int]]) -> list[int]:
        """How many words (written forms) each run of frequency ranks
        (first, last) has - the sizes of Words' bands."""
        last = max((last for _, last in runs), default=0)
        return words_in_runs(self._file.words_ranked(last), runs)

    def words_past(
        self, after: int, limit: int, scheme_id: str
    ) -> list[tuple[int, EntryFacts]]:
        """The words placed past `after`, earliest first, at most `limit`:
        each with its place - its frequency rank: English has no syllabus
        to place a word earlier - and its entry's facts: what a learning
        load takes in (polyglotic-hq 324). An inflected form with a rank of
        its own ("ran") is left out: a caption counts it for its lemma's
        entry (`entry_for_word`), which has its own place."""
        found: list[tuple[int, EntryFacts]] = []
        while not found:
            ranked = self._file.headwords_ranked(after, limit)
            if not ranked:
                break
            for headword, rank in ranked:
                entry = self.entry_for_word(headword)
                if entry is not None and entry.headword == headword:
                    found.append((rank, entry.facts(scheme_id)))
            after = ranked[-1][1]
        return found

    def words_at_levels(self, scheme_id: str) -> Mapping[int, int]:
        """How many headwords the level scheme puts at each level."""
        return self._file.words_at_levels(scheme_id)

    def merged_ids(self) -> list[EntryId]:
        """The entry IDs merged into other entries (decision 0007): what
        `Vocabulary.follow_merged_entries` checks at start."""
        return [EntryId(old) for old in self._file.merged_ids()]

    def respelling(self, word: str) -> str:
        """How `word` sounds, respelled for learners ("chaos": KAY-oss) -
        "" where the dictionary hasn't it (a rarer word, or a dictionary
        built before 511)."""
        return self._file.form_reading(word.replace("’", "'").lower())

    def readings(self, text: str) -> list[Reading]:
        """The reading line over English `text`: each word's respelling
        over it, where the dictionary has one - a hyphenated word it
        hasn't whole, each part's over that part (well-known)."""
        found = []
        for start, end in words(text):
            word = text[start:end]
            said = self.respelling(word)
            if said or "-" not in word:
                found += [Reading(start, end, said)] if said else []
                continue
            at = start
            for part in word.split("-"):
                said = self.respelling(part) if part else ""
                if said:
                    found.append(Reading(at, at + len(part), said))
                at += len(part) + 1
        return found
