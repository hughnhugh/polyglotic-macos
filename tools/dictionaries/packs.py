"""The basic dictionary packs: one pipeline, a config per language.

    uv run python -m tools.dictionaries.packs            # every pack
    uv run python -m tools.dictionaries.packs es ja      # some

polyglotic-hq project 157 proposed "basic" dictionaries for the caption
languages beyond Chinese and English, from open data and one pipeline
(DECISIONS #65 asks the user whether they are a launch goal; until then
nothing here reaches learners: the installer ships `cedict` and `ecdict`
only, and `build` doesn't make these).

Each language's config names its sources and a reader that turns them
into a `Draft`: entries with English meanings (and Chinese ones where the
Chinese edition of Wiktionary has them), the written forms that find
them, and inflected forms -> their lemma. The rest is shared: entry IDs
(decision 0007, a registry per pack), frequency ranks from the pack's
frequency lists (`frequency`; decision 0120), the SQLite file in the
lookup's own format (decision 0009), its credits, and
the coverage probe (`coverage`): its share goes in the file's `info`, and
the build fails if a pack is under the basic tier's floor.

Each pack is written twice, once per meanings language: `<name>.sqlite`
(English) and `<name>-zh.sqlite` (Chinese where there is Chinese, else
English) - the same entries and IDs, so statuses don't care which.
Files go to `build/dictionaries/packs/` with `<name>.CREDITS.md`.
"""

from __future__ import annotations

import argparse
import csv
import heapq
import re
import sys
import time
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Callable, Collection, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field, replace
from functools import partial
from pathlib import Path

from polyglotic_desktop.adapters.spaced_split import ELIDED
from polyglotic_desktop.adapters.sqlite_dictionary import (
    FORMAT,
    RANKS,
    add_info,
    write_dictionary,
)
from polyglotic_desktop.adapters.traditional_table import read_table
from polyglotic_desktop.core.lexicon import arabic, english
from polyglotic_desktop.core.lexicon.traditional import TraditionalChinese
from polyglotic_desktop.core.lexicon.vietnamese import key as word_key
from polyglotic_desktop.ports.dictionary import EntryRecord
from polyglotic_desktop.ports.word_classes import SenseClasses
from tools.dictionaries import (
    cantonese,
    cedict,
    coverage,
    frequency,
    jmdict,
    kaikki,
    korean,
    rank_check,
    russian,
    sense_classes,
    spanish,
    thai,
    treebanks,
    vietnamese,
    wordfreq_ranks,
)
from tools.dictionaries.entry_ids import Registry, assign_ids
from tools.dictionaries.reviewed_classes import apply_reviews
from tools.dictionaries.sources import (
    CANTO_READINGS,
    CC0,
    CC_CANTO,
    CEDICT_FOR_CANTONESE,
    COMMONVOICE_FA,
    COMMONVOICE_TH,
    COUNTS_ONLY,
    FREQUENCYWORDS_RU,
    HKCANCOR,
    JLPT,
    JMDICT,
    KAIKKI_AR,
    KAIKKI_CS,
    KAIKKI_DE,
    KAIKKI_EL,
    KAIKKI_ES,
    KAIKKI_FA,
    KAIKKI_FR,
    KAIKKI_HI,
    KAIKKI_ID,
    KAIKKI_IT,
    KAIKKI_KO,
    KAIKKI_MK,
    KAIKKI_MS,
    KAIKKI_NL,
    KAIKKI_PL,
    KAIKKI_PT,
    KAIKKI_RO,
    KAIKKI_RU,
    KAIKKI_SV,
    KAIKKI_TH,
    KAIKKI_TL,
    KAIKKI_TR,
    KAIKKI_UK,
    KAIKKI_VI,
    KAIKKI_ZH,
    MIT,
    OPENSUBTITLES_VI,
    RIME_CHARS,
    RIME_WORDS,
    WORDFREQ,
    WORDFREQ_ZH,
    Source,
    fetch,
)

REPO = Path(__file__).resolve().parents[2]
REGISTRY = Path(__file__).parent / "registry"
CC_BY_SA = "https://creativecommons.org/licenses/by-sa/4.0/"
OTHER_CC = {
    "CC BY-SA 3.0": "https://creativecommons.org/licenses/by-sa/3.0/",
    "CC BY 4.0": "https://creativecommons.org/licenses/by/4.0/",
}
"""Licences of sources only counted (the treebanks): their notice names the
licence's own text."""


@dataclass
class DraftEntry:
    """One entry before it has an ID or a rank. `ranked_by`: the written
    forms whose frequencies are its own (inflections are added through
    the draft's `inflections`)."""

    key: str
    headword: str
    reading: str
    meanings: tuple[str, ...]
    ranked_by: tuple[str, ...]
    zh_meanings: tuple[str, ...] = ()
    levels: tuple[tuple[str, int], ...] = ()
    common: bool = False
    """The source marks it common (JMdict's priority lists): kept
    whatever wordfreq says."""
    source_pos: str = ""
    sense_classes: tuple[SenseClasses, ...] = ()
    zh_classes: tuple[SenseClasses, ...] = ()


@dataclass
class Draft:
    entries: list[DraftEntry]
    forms: dict[str, list[str]]
    """Written form -> entry keys, best first (the form's own entries)."""
    inflections: dict[str, set[str]] = field(default_factory=dict)
    """Inflected form -> the headwords it is a form of (all of them)."""
    imperative: set[tuple[str, str]] = field(default_factory=set)
    """(form, lemma) pairs that are only an imperative (`kaikki.Language`)."""
    verb_forms: set[tuple[str, str]] = field(default_factory=set)
    """(form, lemma) pairs where the form is the verb's inflection."""
    form_readings: dict[str, list[str]] = field(default_factory=dict)
    """Written form -> how it is said, where the source marks a form apart
    from its headword (Russian's stress), each way once, in order."""
    counted: dict[str, frequency.Frequencies] = field(default_factory=dict)
    """Frequency lists the reader counted itself, by their source's name
    (Vietnamese: every published list counts syllables, not words)."""
    lemma_first: dict[str, frozenset[str]] = field(default_factory=dict)
    """Form -> the lemmas Wiktionary gives it first as a form of, where it
    is no word of its own (`kaikki.Language.lemma_first`): that lemma comes
    before its own entries (`lemma_table`)."""
    split_shared_forms: bool = False
    """A form of several lemmas gives each a share of its frequency, in
    proportion to the lemma's own (`shares`): Italian's "sono" is essere's
    far more than suonare's, and Portuguese's "no" - wrongly the
    comparative in two adjectives' tables - had made austro-húngaro the
    12th word (polyglotic-hq 380). The older readers (Spanish, Russian)
    keep giving each lemma the whole until their ranks are measured again;
    Spanish's were, by polyglotic-hq 461's audit."""
    keep_unranked: bool = False
    """Every entry is kept, ranked or not: a language whose word split is
    by the pack's own words (Thai) needs them all, or a word the pack
    lacks is cut into shorter ones it has - กาแล็กซี (galaxy), never said
    in Common Voice, read as กา (crow) + แล็ก + ซี (polyglotic-hq 389)."""
    capitalised: dict[str, frozenset[str]] = field(default_factory=dict)
    """Entry keys of nouns whose capital is their spelling (German's), with
    their own declension's forms: such a noun takes its lower-case
    frequency where its forms show it is the word in use (`DECLINED`)."""
    came_through: dict[tuple[str, str], set[str]] = field(default_factory=dict)
    """(form, lemma) -> the parts of speech that link them
    (`kaikki.Language.came_through`): a form with no entry of its own opens
    on its lemma's entries in those first (`opened_through`)."""
    own_first: frozenset[str] = frozenset()
    """Forms with entries of their own that come before a verb they are a
    form of, whatever that verb's frequency (`own_first`)."""
    own_verbs: frozenset[str] = frozenset()
    """Forms that are a verb of their own: they come before a verb they are
    a form of where they are the commoner (`own_first`)."""
    elided: frozenset[str] = frozenset()
    """Forms that are only another word written short (`Spelling.elided`):
    their frequency is that word's, not their own entries'."""
    lemma_used: dict[str, frozenset[str]] = field(default_factory=dict)
    """Form with entries of its own -> the lemmas it is used as far more
    than as its own entries, by the treebanks (`lemma_used`): those come
    first (`lemma_table`)."""
    elisions: frozenset[str] = frozenset()
    """The words the app's split cuts off as elided, without the apostrophe
    (`spaced_split.ELIDED`: French's "l", Italian's "dell"): such a word
    takes wordfreq's frequency without it (`elided_frequency`)."""
    uses: kaikki.Uses | None = None
    """The treebanks' counts of each word's parts of speech, where the
    language has them: they decide which a capitalised word opens on
    (`capitals_first`)."""
    written: kaikki.Uses | None = None
    """...and of each word as written alone (`treebanks.uses`' `forms_only`):
    which of a form's lemmas it opens on (`used_as_lemma`). Turkish's
    treebanks give a verb's stem as its lemma, so by lemma "geliş" (arrival,
    gelmek's) was gelişmek's (to develop) 18 times (polyglotic-hq 416)."""


@dataclass(frozen=True)
class Pack:
    """One language's pack: `name` is the file's name and the entry IDs'
    prefix (lower-case letters and digits: the server's pattern)."""

    language: str
    name: str
    title: str
    sources: tuple[Source, ...]
    read: Callable[[Mapping[str, Path]], Draft]
    level_schemes: str
    about: str  # what we changed, for the credits
    frequency: tuple[str, ...] = ("wordfreq",)
    """The sources whose word frequencies give the ranks, averaged
    (`tools.dictionaries.frequency`): "wordfreq", or a list of counts."""
    meanings: tuple[str, ...] = ("en", "zh")
    """The meanings languages it is written in, a file each: English, and
    Chinese where the Chinese edition of Wiktionary is read
    (`tools.package.publish_packs` publishes each)."""


# -- Spanish: Wiktionary --------------------------------------------------------


def chinese_for(
    word: str, pos: str, first: bool, zh: Mapping[str, list[str]]
) -> tuple[str, ...]:
    """The Chinese edition's meanings for one entry: those under the same
    part of speech; for a word's first entry, failing that, those under
    any (the Chinese edition often has none: casa is "unknown" there)."""
    if f"{word}|{pos}" in zh:
        return tuple(zh[f"{word}|{pos}"][: kaikki.MAX_MEANINGS])
    if not first:
        return ()
    found = [g for key, gs in zh.items() if key.split("|")[0] == word for g in gs]
    return tuple(dict.fromkeys(found))[: kaikki.MAX_MEANINGS]


def chinese_classes(
    word: str, pos: str, zh: Mapping[str, list[str]]
) -> tuple[SenseClasses, ...]:
    """The Chinese edition's own class for an exact same-POS gloss.

    The spelling-only fallbacks in `chinese_for` remain pending.
    """
    cls = sense_classes.wikt(pos)
    return (cls,) * len(zh.get(f"{word}|{pos}", ())[: kaikki.MAX_MEANINGS])


def read_spanish(paths: Mapping[str, Path]) -> Draft:
    uses = treebanks.uses_for("es", paths)
    words = kaikki.read_language(kaikki.lines(paths["kaikki-es"], "es"), uses=uses)
    # pronominal verbs: levantarse, and the forms with te/se/nos it gets
    found = spanish.pronominal(words)
    words.entries += found.entries
    for entry in found.entries:
        words.forms.pop(entry.word, None)  # its own entry, not levantar's
    for form, verb in found.forms.items():
        words.forms[form] = {verb}
        words.verb_forms.add((form, verb))
    zh = kaikki.glosses_by_word(kaikki.lines(paths["kaikki-zh"], "es"))
    zh_by_word: dict[str, dict[str, list[str]]] = defaultdict(dict)
    for key, glosses in zh.items():
        zh_by_word[key.split("|")[0]][key] = glosses
    written = treebanks.uses_for("es", paths, forms_only=True)
    draft = with_treebanks(draft_of(words, zh_by_word), words, uses, written)
    # "mercedes" (Mercedes; merced's plural) had made mercedar, whose form
    # it also is, the 4,283rd word (polyglotic-hq 448, 461)
    draft.split_shared_forms = True
    return draft


def with_treebanks(
    draft: Draft,
    words: kaikki.Language,
    uses: kaikki.Uses | None,
    written: kaikki.Uses | None,
) -> Draft:
    """`draft` with what the treebanks say of its forms, for a reader of its
    own (Spanish's, Russian's) as the generic one has it: which forms keep
    their own entries before a verb's (`own_first`), which open on their
    lemma (`lemma_used`), and the counts for capitalised words
    (`capitals_first`). Spanish's "nueva" had opened on "news", not nuevo's
    "new"; Russian's "хотя" ("although") on хотеть, "to want"
    (polyglotic-hq 413). `written`: each form's own uses (`lemma_used`)."""
    draft.own_first, draft.own_verbs = own_first(words, uses)
    draft.lemma_used = lemma_used(words, written)
    draft.uses = uses
    draft.written = written
    return draft


def draft_of(
    words: kaikki.Language,
    zh_by_word: Mapping[str, Mapping[str, list[str]]] | None = None,
) -> Draft:
    """A Wiktionary language's draft: each entry with its part of speech
    before each meaning, found by its headword and its inflections; Chinese
    meanings from `zh_by_word` (the Chinese edition's, by word, then
    `word|pos`) where it has them."""
    entries = []
    forms: dict[str, list[str]] = defaultdict(list)
    for e in words.entries:
        entries.append(
            DraftEntry(
                key=e.key,
                headword=e.word,
                reading=e.reading,
                meanings=tuple(f"({e.pos}) {m}" if e.pos else m for m in e.meanings),
                ranked_by=(e.word,),
                source_pos=e.pos,
                zh_classes=chinese_classes(e.word, e.pos, zh_by_word.get(e.word, {}))
                if zh_by_word
                else (),
                zh_meanings=chinese_for(
                    e.word, e.pos, not forms[e.word], zh_by_word.get(e.word, {})
                )
                if zh_by_word
                else (),
            )
        )
        forms[e.word].append(e.key)
    return Draft(
        entries,
        dict(forms),
        {f: set(ls) for f, ls in words.forms.items()},
        words.imperative,
        words.verb_forms,
        lemma_first=words.lemma_first,
    )


# -- Any spaced language: Wiktionary ---------------------------------------------


@dataclass(frozen=True)
class Spelling:
    """How a language's Wiktionary is read where it differs from French's:
    the default reads every spaced language whose captions write words as
    Wiktionary writes its headwords (polyglotic-hq 380)."""

    written: Callable[[str], str] | None = None
    """A form as captions write it ("كُتُب" -> "كتب": Arabic's inflection
    tables mark the vowels, captions don't). Headwords are page titles,
    already written so."""
    reading: Callable[[Mapping[str, object]], str] = kaikki.first_ipa
    """An entry's reading (IPA unless said)."""
    nouns_capitalised: bool = False
    also: Callable[[str], set[str]] | None = None
    """Other ways text writes a word, found as its forms where the pack
    hasn't got them as words or forms already (`also_written`)."""
    """Nouns are written with a capital (German): it is their spelling, not
    a name's mark (`Draft.capitalised`)."""
    derived: frozenset[str] = frozenset()
    """Tags of form-of senses that make a word of its own where the gloss
    says what it means (`kaikki.read_language`'s `derived`): Turkish's
    causatives, passives and verbal nouns."""
    linked: bool = False
    """A word takes a linker on its end (Filipino's -ng after a vowel, -g
    after n: isa, isang; noon, noong): each such spelling is a form of its
    word (`linked_forms`)."""
    elided: Mapping[str, str] = field(default_factory=dict)
    """Words written short onto the next or the last with a hyphen, as
    written short -> the word (`with_elided`)."""
    phrase_heads: frozenset[str] = frozenset()
    """The first words of two-word adpositions whose second word is no
    word of a caption alone: each such second word gets the phrase's
    meanings (`phrase_words`)."""
    prepared: Callable[[Iterable[dict[str, object]]], Iterable[dict[str, object]]] = (
        lambda objects: objects
    )
    """The extract's objects as the language's rules read them (Korean's
    `korean.prepared`)."""


AS_WRITTEN = Spelling()
"""Wiktionary read as it is: captions write what it writes."""
FILIPINO = Spelling(linked=True)
"""Filipino: its linker written onto a word (`linked_forms`)."""
ROMANIZED = Spelling(reading=kaikki.romanization)
"""A language in another script: its reading is Wiktionary's romanization
("laṛkā"), which a learner reads before IPA."""
_HINDI_Y = re.compile("(?<=[ऀ-ॿ])(?<!्)य(ें|ीं|े|ी)")
_HINDI_VOWEL = {"े": ("ए",), "ें": ("एँ", "एं"), "ी": ("ई",), "ीं": ("ईं",)}


def hindi_spellings(word: str) -> set[str]:
    """Other ways Hindi text writes `word`: ए for ये and ई for यी after a
    letter, not in a cluster (बनायेगी as बनाएगी, गये as गए; not प्यार). Wiktionary's inflection tables
    write the य forms and captions the vowels, so every verb's future
    ("बनाएगी", will make) found nothing (polyglotic-hq 448, 461)."""
    out = {word}
    for found in _HINDI_Y.finditer(word):
        out |= {
            w[: found.start()] + vowel + w[found.end() :]
            for w in out
            if w[found.start() : found.end()] == found.group()
            for vowel in _HINDI_VOWEL[found.group(1)]
        }
    out.discard(word)
    return out


HINDI = Spelling(
    reading=kaikki.romanization,
    also=hindi_spellings,
    phrase_heads=frozenset({"के", "की"}),
)
"""Hindi: read by romanization; its tables' य forms written with vowels too
(`hindi_spellings`); के लिए's and के साथ's second word a word of its own
(`phrase_words`)."""
GERMAN = Spelling(nouns_capitalised=True)
"""German: its nouns' capitals are spelling (Mensch, Abend)."""


def arabic_spellings(word: str) -> set[str]:
    """Other ways Arabic text writes `word` (polyglotic-hq 390): alif
    without its hamza (أنت as انت, إلى as الى), and a final ya and alif
    maqsura for each other (في as فى) - five of Arabic's 200 commonest
    words in wordfreq's list were written so, and found nothing."""
    bare = word.translate(_HAMZA_ON_ALIF)
    out = {bare}
    for w in (word, bare):
        if w[-1:] in _FINAL_YA:
            out.add(w[:-1] + _FINAL_YA[w[-1]])
    out.discard(word)
    return out


_HAMZA_ON_ALIF = str.maketrans("أإآ", "ااا")
_FINAL_YA = {"ي": "ى", "ى": "ي"}
ARABIC = Spelling(
    written=arabic.plain, reading=kaikki.romanization, also=arabic_spellings
)
"""Arabic: forms without their vowel marks, as captions write them
(`core.lexicon.arabic`); read by romanization ("kitāb")."""
TURKISH = Spelling(derived=kaikki.DERIVATIONS)
"""Turkish: a causative, passive or verbal noun that Wiktionary glosses
is a word of its own (araştırmak, to research; araştırma, research), not
a form of the verb it is made from (araşmak, to call each other)."""


STRESSED = Spelling(written=russian.unstressed, reading=russian.stressed)
"""Ukrainian: its inflection tables mark the stress ("яки́й"), captions
don't - without it, 54.8 % of the probe's words were found in the
installed app (polyglotic-hq 387); read by the headword with its stress
marked ("хоро́ший"), as Russian's pack is."""


def iranian_romanization(obj: Mapping[str, object]) -> str:
    """A Persian word's romanization as Iran says it ("ketâb"), where
    Wiktionary gives the classical one first ("kitāb"): the first written
    with â, else the first (`kaikki.romanization`). Captions are Iran's
    Persian (FLEURS's is fa_ir; polyglotic-hq 387)."""
    forms = obj.get("forms")
    said = [
        str(f["form"])
        for f in (forms if isinstance(forms, list) else [])
        if isinstance(f, dict)
        and "romanization" in (f.get("tags") or [])
        and isinstance(f.get("form"), str)
    ]
    return next((r for r in said if "â" in r), "") or kaikki.romanization(obj)


PERSIAN = Spelling(written=arabic.plain, reading=iranian_romanization)
"""Persian: forms without the vowel marks its tables write ("کُن" is کن),
as Arabic's; read by Iran's romanization."""


_LATIN_J = str.maketrans({"j": "ј", "J": "Ј"})


def cyrillic_j(form: str) -> str:
    """A Cyrillic form with the Latin j its table was typed with put back
    as Cyrillic ј: Wiktionary's tables for Macedonian's свој (own), мој
    and твој write "своjот", "своjата", so the pack had no својот or
    својата, words in Macedonian's top 200 (polyglotic-hq 394, 396). A
    Latin word is left as it is."""
    letters = [ch for ch in form if ch.isalpha()]
    if not any("CYRILLIC" in unicodedata.name(ch, "") for ch in letters):
        return form
    return form.translate(_LATIN_J)


MACEDONIAN = Spelling(written=cyrillic_j)
"""Macedonian: forms in Cyrillic throughout (`cyrillic_j`)."""
ROMANIAN = Spelling(
    elided={
        "i": "îi",
        "ți": "îți",
        "mi": "îmi",
        "l": "îl",
        "m": "mă",
        "s": "se",
        "v": "vă",
        "n": "nu",
        "într": "în",
        "dintr": "din",
        "printr": "prin",
    }
)
"""Romanian: its clitics written short onto a verb with a hyphen (i-am
spus: îi am; ți-am, l-am, m-am, s-a, v-am, n-am; într-o). wordfreq cuts
words at hyphens, so its "i", "ți", "s", "l" are these, in Romanian's top
200, and had no entry or a letter's; in the app a hyphenated word the
pack hasn't got whole is looked up by its pieces (`core.lexicon.
compounds`), so "dă-i" (give him) is dă + îi (polyglotic-hq 396, 399).
Not "și" (and), a word far commoner than își written short (și-a)."""


def read_wiktionary(
    language: str,
    paths: Mapping[str, Path],
    spelling: Spelling = AS_WRITTEN,
    sentences: str = "",
) -> Draft:
    """A spaced language's Wiktionary words (`kaikki-<language>`) with their
    English meanings, reading and inflections - French, German, Polish...
    A new language is a `wiktionary_pack` in `PACKS` and, if its captions
    need them, its word split's rules in the app (`adapters.spaced_split`:
    elided words, clitics); not a module of its own. A letter of the
    alphabet is no word of a caption (`russian.is_letter`): it had shared
    its word's rank and come first on its card - Persian's و, "and", the
    commonest word, showed "the thirtieth letter of the Persian alphabet"
    (polyglotic-hq 387)."""
    objects: Iterable[dict[str, object]] = (
        obj
        for obj in spelling.prepared(
            kaikki.lines(paths[f"kaikki-{language}"], language)
        )
        if not russian.is_letter(obj)
    )
    if spelling.phrase_heads:
        read = list(objects)
        objects = [*read, *phrase_words(read, spelling.phrase_heads)]
    uses = treebanks.uses_for(language, paths, spelling.written)
    words = kaikki.read_language(
        objects, spelling.reading, uses=uses, derived=spelling.derived, chain=True
    )
    if spelling.written:
        words = rewritten(words, spelling.written)
    if spelling.also:
        words = also_written(words, spelling.also)
    if spelling.linked:
        words.forms.update(linked_forms(words))
    draft = draft_of(words)
    draft.came_through = dict(words.came_through)
    draft.elisions = ELIDED.get(language, frozenset())
    draft.own_first, draft.own_verbs = own_first(words, uses)
    written = treebanks.uses_for(language, paths, spelling.written, forms_only=True)
    named = treebanks.lemmas_for(language, paths, spelling.written)
    draft.lemma_used = lemma_used(words, written, named)
    draft.uses = uses
    draft.written = written
    if spelling.elided:
        draft = with_elided(draft, spelling.elided)
    draft.split_shared_forms = True
    if spelling.nouns_capitalised:
        draft.capitalised = capitalised_nouns(words)
    if sentences:  # a source of sentences: its words counted by the app's split
        draft.counted[sentences] = frequency.sentences_counted(
            paths[sentences], english.words
        )
    return draft


def phrase_words(
    objects: Sequence[Mapping[str, object]], heads: frozenset[str]
) -> list[dict[str, object]]:
    """An entry of its own, as Wiktionary's lines are, for the second word
    of each two-word adposition whose first is one of `heads`, with the
    phrase's meanings: Hindi's के लिए ("for") gives लिए "के लिए: ... for".
    A caption's words are looked up one by one, and लिए, the 12th
    commonest word in Hindi's test sentences, had opened on लेना, "to
    take", whose form it also is (polyglotic-hq 448, 461)."""
    out: list[dict[str, object]] = []
    for obj in objects:
        words = str(obj.get("word") or "").split()
        pos = obj.get("pos")
        if len(words) != 2 or words[0] not in heads or pos not in kaikki.ADPOSITIONS:
            continue
        phrase = " ".join(words)
        senses = []
        listed = obj.get("senses")
        for sense in listed if isinstance(listed, list) else ():
            glosses = sense.get("glosses") if isinstance(sense, dict) else None
            if isinstance(glosses, list) and glosses and isinstance(glosses[0], str):
                senses.append({"glosses": [f"{phrase}: {glosses[0]}"]})
        if senses:
            out.append({"word": words[1], "pos": pos, "senses": senses})
    return out


def linked_forms(words: kaikki.Language) -> dict[str, set[str]]:
    """Each word with Filipino's linker on it, as a form of the word: isang
    (a, one) is isa's, noong (when) noon's. Its frequency is then isa's,
    and a name spelled the same gives way (Isang, a diminutive of Isabel,
    had been the pack's 8th word; Kong and Pang the 74th and 55th:
    polyglotic-hq 387). A spelling that is a word or form of its own is
    left as it is."""
    taken = {e.word for e in words.entries} | set(words.forms)
    out: dict[str, set[str]] = {}
    for e in words.entries:
        word = e.word
        if not word.isalpha() or not word.islower():
            continue
        linked = (
            word + "ng"
            if word[-1] in "aeiou"
            else word + "g"
            if word[-1] == "n"
            else ""
        )
        if linked and linked not in taken:
            out.setdefault(linked, set()).add(word)
    return out


def capitalised_nouns(words: kaikki.Language) -> dict[str, frozenset[str]]:
    """German's nouns written as words are (Mensch; not IM or AN,
    initialisms), each with its own declension's forms (`Draft.capitalised`)."""
    return {
        e.key: e.forms
        for e in words.entries
        if e.pos == "noun" and e.word[:1].isupper() and e.word[1:] == e.word[1:].lower()
    }


def also_written(
    words: kaikki.Language, also: Callable[[str], set[str]]
) -> kaikki.Language:
    """`words` with each headword's and form's other spellings (`Spelling.
    also`) as forms of the same lemmas - never one the pack already has as
    a word or a form, so what a real spelling finds doesn't change."""
    headwords = {e.word for e in words.entries}
    added: dict[str, set[str]] = defaultdict(set)
    for e in words.entries:
        for other in also(e.word):
            added[other].add(e.word)
    for form, lemmas in words.forms.items():
        for other in also(form):
            added[other] |= lemmas
    for other, lemmas in added.items():
        if other not in headwords and other not in words.forms:
            words.forms[other] = lemmas
    return words


def rewritten(words: kaikki.Language, written: Callable[[str], str]) -> kaikki.Language:
    """`words` with every inflected form as captions write it (`Spelling.
    written`); a form that is its own lemma once rewritten is dropped."""
    forms: dict[str, set[str]] = defaultdict(set)
    for form, lemmas in words.forms.items():
        plain = written(form)
        forms[plain] |= {lemma for lemma in lemmas if lemma != plain}
    words.forms = {f: ls for f, ls in forms.items() if ls}
    words.imperative = {(written(f), lemma) for f, lemma in words.imperative}
    words.verb_forms = {(written(f), lemma) for f, lemma in words.verb_forms}
    came: dict[tuple[str, str], set[str]] = defaultdict(set)
    for (form, lemma), parts in words.came_through.items():
        came[(written(form), lemma)] |= parts
    words.came_through = came
    kinds: dict[tuple[str, str], set[str]] = defaultdict(set)
    for (form, lemma), kind in words.link_kinds.items():
        kinds[(written(form), lemma)] |= kind
    words.link_kinds = kinds
    return words


def own_first(
    words: kaikki.Language, uses: kaikki.Uses | None
) -> tuple[frozenset[str], frozenset[str]]:
    """The forms of a verb whose own entries may come first (`lemma_table`):
    those the treebanks use more as their own entries' other parts of speech
    than as a verb (Dutch's zij, "she", zijn's subjunctive), and those that
    are a verb of their own (German's sein, "to be", which werden's table
    lists), which come first where they are the commoner verb; and a
    verb's participle that is an adjective of its own (German's "fehlend",
    "missing", had opened on fehlen, "to be absent"; Czech's "zděděný",
    "inherited", on zdědit: polyglotic-hq 448, 461). A shared
    pronoun table had hidden both: its pronoun had been their commonest
    lemma, so the verb never came first (polyglotic-hq 399)."""
    own: dict[str, set[str]] = defaultdict(set)
    for e in words.entries:
        if e.standing == 0:
            own[e.word].add(e.pos)
    linked: dict[str, set[str]] = defaultdict(set)
    for (form, _), parts in words.came_through.items():
        if form in own:
            linked[form] |= parts
    used, verbs = set(), set()
    for form, parts in linked.items():
        if "verb" not in parts:
            continue
        counts = uses.get(form.lower(), {}) if uses else {}
        if sum(counts.values()) >= kaikki.MIN_USES and kaikki.used_as(
            counts, own[form] - {"verb"}
        ) > kaikki.used_as(counts, {"verb"}):
            used.add(form)
        if "verb" in own[form]:
            verbs.add(form)
    for (form, _), kinds in words.link_kinds.items():
        if "participle" in kinds and "adj" in own.get(form, ()):
            used.add(form)  # fehlend, "missing", before fehlen
    return frozenset(used), frozenset(verbs)


def lemma_used(
    words: kaikki.Language,
    uses: kaikki.Uses | None,
    named: kaikki.Uses | None = None,
) -> dict[str, frozenset[str]]:
    """Forms with entries of their own that the treebanks use (`uses`: each
    form as written, `treebanks.uses`' `forms_only`) as another
    word's form far more (`kaikki.LEAD` times) than as those entries' parts
    of speech, each with the lemmas they are used as: those lemmas come
    first (`lemma_table`). The mirror of `own_first`. A common word's form
    that is also a rare word of its own had opened on that word: French's
    "est" (être's "is") on "east", "la" and "les" on the pronoun "her";
    Portuguese's "é" (ser's "is") on an interjection, "boa" (bom's "good")
    on "an interesting story", "toda" (todo's "all") on the Toda people of
    India (polyglotic-hq 402, 413). The lemma's side counts only the parts
    of speech the form has no entry in; the form's, all of its own:
    Portuguese's "a" is o's article and pronoun and its own pronoun and
    preposition - the article 3,646 times, its own 1,090. Italian's "il" is
    lo's article and pronoun, and its own article: used as the pronoun
    alone, it stays il. The lemma's side counts only parts of speech the
    lemma has a word's entry in, at least `kaikki.MIN_USES` times, and the
    form's every entry, a name's too: Indonesian's "Indonesia", in baja's
    noun table by a slip, is a name 79 times and a noun twice; Italian's
    treebank calls "tutti" an adjective 8 times, and tutto has no adjective.

    Where the counts can't tell the form from the lemma (polyglotic-hq 416):
    - the lemma's side must be at least `kaikki.MIN_SHARE` of the form's
      uses: Hindi's पहले ("before") is पहला's (first) as an adjective 10
      times in 45, and mostly a postposition, which neither has an entry
      for; it had opened on "first";
    - a form's own adposition counts its uses as a noun too where the form
      is the noun's oblique case: treebanks tag a noun's case form used as
      a postposition a noun, so Turkish's "içinde" (inside, iç's locative),
      "hakkında" (about) and "üzerinde" (on) had opened on iç (inner), hak
      (justice) and üzeri. Not a plural: Spanish's "veces" (vez's "times")
      stays vez's, not its own "times (multiplication)";
    - a degree of comparison stays its own (`kaikki.Language.link_kinds`)
      where its own entry is in a part of speech it came through: Swedish's
      "mindre" (adjective) says "smaller; less", and had opened on lite's
      "a little"; Czech's "starší" (older) is a noun of its own, "a church
      elder", and opens on starý, "old";
    - a form that is an adposition's with a pronoun attached counts for it
      only where the treebanks name the adposition as its lemma (`named`:
      `treebanks.lemmas`): they split such a word in two, so a word they
      keep whole is usually another - Arabic's "لكن" is "but" (lemma لكن,
      though tagged ADP), and had opened on ل, "to", whose "لَكُنَّ" ("to
      you") is written the same; "علي" (lemma على) is على, "on";
    - a possessive counts as the form's determiner where it has one
      (`kaikki.resolved`): Swedish's "din" ("your") had opened on ditt's
      "you (vocative ...)"."""
    if not uses:
        return {}
    own: dict[str, set[str]] = defaultdict(set)  # every entry: a name's too
    words_of: dict[str, set[str]] = defaultdict(set)  # its word's entries
    for e in words.entries:
        own[e.word].add(e.pos)
        if e.standing == 0:
            words_of[e.word].add(e.pos)
    out: dict[str, set[str]] = defaultdict(set)
    for (form, lemma), parts in words.came_through.items():
        kinds = words.link_kinds.get((form, lemma), set())
        if form not in own or (kinds & kaikki.DEGREES and own[form] & parts):
            continue
        if "pronoun" in kinds and not (named or {}).get(form.lower(), {}).get(lemma):
            continue
        counts = kaikki.resolved(uses.get(form.lower(), {}), own[form])
        postposition = own[form] & kaikki.ADPOSITIONS and "case" in kinds
        mine_as = own[form] | ({"noun"} if postposition else set())
        theirs = kaikki.used_as(counts, (parts & words_of[lemma]) - mine_as)
        mine = kaikki.used_as(counts, mine_as)
        if (
            theirs >= kaikki.MIN_USES
            and theirs >= kaikki.LEAD * mine
            and theirs >= kaikki.MIN_SHARE * sum(counts.values())
        ):
            out[form].add(lemma)
    return {form: frozenset(lemmas) for form, lemmas in out.items()}


def with_elided(draft: Draft, elided: Mapping[str, str]) -> Draft:
    """`draft` with each word written short (`Spelling.elided`) a form of
    the word, the one it opens on, and its frequency that word's alone - not
    its own entries' (a letter's, Romanian's "i" an old word for "and") -
    where the pack has the word."""
    for short, word in elided.items():
        if word in draft.forms:
            draft.inflections[short] = {word}
            draft.lemma_first[short] = frozenset({word})
    draft.elided = frozenset(s for s, w in elided.items() if w in draft.forms)
    return draft


def wiktionary_pack(
    language: str,
    title: str,
    source: Source,
    spelling: Spelling = AS_WRITTEN,
    *,
    sentences: Source | None = None,
) -> Pack:
    """A spaced language's pack from its Wiktionary (`read_wiktionary`),
    English meanings only (DECISIONS #175: every language paired with
    English first), ranked by wordfreq (polyglotic-hq 374: it wins or ties
    in 23 caption languages) - and, where `sentences` is given, by the mean
    of wordfreq's and those sentences' words counted (374: Persian's ranks
    are better so, with Common Voice's)."""
    said = "IPA" if spelling.reading is kaikki.first_ipa else "readings"
    counted = (sentences.name,) if sentences else ()
    ranks = "wordfreq and the words of Common Voice's sentences" if sentences else ""
    return Pack(
        language=language,
        name=f"wikt{language}",
        title=title,
        sources=(
            source,
            WORDFREQ,
            *treebanks.of(language),
            *((sentences,) if sentences else ()),
        ),
        read=partial(
            read_wiktionary, language, spelling=spelling, sentences=",".join(counted)
        ),
        level_schemes=f"{language}-frequency",
        about=(
            f"Wiktionary's {title} words with their English meanings, {said} and "
            "inflections, cut to the words wordfreq ranks, with frequency ranks "
            f"from {ranks or 'wordfreq'}"
        ),
        frequency=("wordfreq", *counted),
        meanings=("en",),
    )


# -- Korean: Wiktionary, its words counted with their particles -------------------


def read_korean(paths: Mapping[str, Path]) -> Draft:
    """Korean's Wiktionary (`read_wiktionary`, its romanization the
    reading) as Korean's rules read it (`tools.dictionaries.korean`):
    - a predicate ranked by its stem and fused past, as wordfreq counts
      Korean (`korean.predicate_counts`), and its stem one of its forms
      where the stem is no word (있 for 있다: polyglotic-hq 510);
    - a particle alone opening on the dictionary's particle, and the
      commonest homographs on their predicate (`korean.PARTICLE_FIRST`,
      `korean.OPENS_ON`): 마다, "every"; 대한, 대하다's "about";
    - a word's own adverb, determiner or other small word's entry kept
      first (하지만, "but"), and a predicate's own dictionary form
      (들리다, "to be heard", not 듣다's passive);
    - the commonest words' first meanings (`korean.FIRST_SENSES`), and
      words English Wiktionary has only under their hanja
      (`korean.hanja_words`: 해상, "maritime") (polyglotic-hq 516).
    Every entry is kept, ranked or not: wordfreq's Korean list stops at
    30,000 parts, and a word past it (재건, reconstruction) is kept, as
    Thai's are."""
    added = korean.hanja_words(kaikki.lines(paths["kaikki-ko"], "ko"))
    spelling = replace(ROMANIZED, prepared=partial(korean.prepared, added=added))
    draft = read_wiktionary("ko", paths, spelling)
    by_headword: dict[str, list[DraftEntry]] = defaultdict(list)
    for entry in draft.entries:
        by_headword[entry.headword].append(entry)
    words = {  # headwords with an entry a learner meets
        word
        for word, own in by_headword.items()
        if not all(korean.no_word(e.meanings) for e in own)
    }
    lemma_used = dict(draft.lemma_used)
    entries = []
    for entry in draft.entries:
        if korean.no_word(entry.meanings):
            entry = replace(entry, ranked_by=())  # 랑 (浪): the particle's count
        if part_of_speech(entry.meanings) in korean.PREDICATES:
            counted = korean.predicate_counts(entry.headword, words, by_headword)
            entry = replace(entry, ranked_by=(*entry.ranked_by, *counted))
            if stem := korean.stem_forms(entry.headword, words, by_headword):
                draft.inflections.setdefault(stem, set()).add(entry.headword)
                if stem in by_headword:  # 크: a jamo's name, then 크다
                    lemma_used[stem] = frozenset({entry.headword})
        entries.append(entry)
    draft.entries = entries
    for word in korean.PARTICLE_FIRST:
        if f"-{word}" in by_headword and word in by_headword:
            draft.inflections.setdefault(word, set()).add(f"-{word}")
            lemma_used[word] = frozenset({f"-{word}"})
    for word, predicate in korean.OPENS_ON.items():
        if predicate in by_headword and word in by_headword:
            draft.inflections.setdefault(word, set()).add(predicate)
            lemma_used[word] = frozenset({predicate})
    for word in korean.NO_STEM - set(by_headword):
        draft.inflections.pop(word, None)  # 째, -째's count: not 째다's form
    for word, lemmas in draft.inflections.items():
        if word in korean.SMALL and f"-{word}" in lemmas and word not in by_headword:
            # 는, whose page only points to -는: the particle's, not 이거's
            # (whose table lists 는) - which had become the commonest word
            draft.inflections[word] = {f"-{word}"}
    draft.lemma_used = lemma_used
    shared = {korean.stem(w) for w in korean.STEM_SHARED} - set(korean.OPENS_ON)
    draft.own_first = (
        draft.own_first
        | {w for w in shared if w}
        | {
            word
            for word, own in by_headword.items()
            if word in draft.inflections
            and any(
                part_of_speech(e.meanings) in korean.OWN_FIRST_POS
                or (
                    korean.stem(word)
                    and part_of_speech(e.meanings) in korean.PREDICATES
                )
                for e in own
            )
        }
    )
    first_senses(draft, korean.FIRST_SENSES)
    draft.keep_unranked = True
    return draft


def first_senses(draft: Draft, table: Mapping[str, tuple[str, ...]]) -> None:
    """Each word in `table` opening on its meanings there (Thai's
    `thai.first_senses`, on a draft; each meaning the start of one of
    Wiktionary's): the entry with the first meaning comes first among the
    word's own entries, and those of its meanings listed, first in it;
    every entry's key (its ID) stays. A meaning the word no longer has
    stops the build (ValueError), so a new extract can't quietly undo the
    order."""

    def said(meaning: str) -> str:
        return meaning.split(") ", 1)[1] if meaning.startswith("(") else meaning

    def place(meaning: str, meanings: tuple[str, ...]) -> int | None:
        return next(
            (n for n, m in enumerate(meanings) if said(meaning).startswith(m)), None
        )

    at = {e.key: n for n, e in enumerate(draft.entries)}
    for word, meanings in table.items():
        keys = draft.forms.get(word, [])
        own = [draft.entries[at[k]] for k in keys if k in at]
        if not own:
            continue  # a word the extract hasn't got
        first = next(
            (e for e in own if any(place(m, meanings) == 0 for m in e.meanings)), None
        )
        if first is None:
            raise ValueError(f"{word}: no meaning {meanings[0]!r} in Wiktionary")
        listed = [m for m in first.meanings if place(m, meanings) is not None]
        listed.sort(key=lambda m: place(m, meanings) or 0)
        draft.entries[at[first.key]] = replace(
            first, meanings=(*listed, *(m for m in first.meanings if m not in listed))
        )
        draft.forms[word] = [first.key, *(k for k in keys if k != first.key)]


# -- Malay: Wiktionary, and Indonesian's words it shares ---------------------------


SHARED = " (as in Indonesian)"
"""How a meaning taken from Indonesian's Wiktionary ends in the Malay pack."""


def read_malay(paths: Mapping[str, Path]) -> Draft:
    """Malay's Wiktionary words, then Indonesian's that Malay's hasn't got
    (polyglotic-hq 388): the two are one language's standard forms, and
    Wiktionary has 6,634 Malay entries to Indonesian's 14,740, so
    "penting" (important), "dokumen" and "sikap" had no entry. A word
    counts as shared where it is written alike and Malay text uses it - it
    is kept only if Malay's frequency list has it (`assemble`'s cut). Its
    meanings are Indonesian's, each marked so (`SHARED`): a word
    written alike may still differ in sense (Indonesian's "kereta" is a
    carriage, Malay's a car), and that is said, not hidden. Names aren't
    taken, nor a word written with a capital (Indonesian's initialisms:
    "TV" is tanda vital there, "AL" its navy). Inflected
    forms come from Malay's tables first. Indonesian's entries are ordered
    by Indonesian's treebanks, as in its own pack (polyglotic-hq 394, 396);
    Malay has none."""
    malay = read_wiktionary("ms", paths)
    indonesian = read_wiktionary("id", paths)
    have = {e.headword.lower() for e in malay.entries} | {
        f.lower() for f in malay.inflections
    }
    for e in indonesian.entries:
        if (
            e.headword.lower() in have
            or e.headword != e.headword.lower()
            or all(m.startswith("(name) ") for m in e.meanings)
        ):
            continue
        malay.entries.append(
            replace(e, meanings=tuple(m + SHARED for m in e.meanings), source_pos="")
        )
        malay.forms.setdefault(e.headword, []).append(e.key)
    words = {e.headword for e in malay.entries}
    for form, lemmas in indonesian.inflections.items():
        if form.lower() not in have and form not in words:
            malay.inflections.setdefault(form, set()).update(lemmas)
    return malay


# -- Russian: Wiktionary ---------------------------------------------------------


def read_russian(paths: Mapping[str, Path]) -> Draft:
    """Wiktionary's Russian words with English meanings, readings with the
    stress marked, and inflections found without their stress marks
    (`russian`); Chinese meanings as Spanish's."""
    participles: list[tuple[str, str]] = []
    form_readings: dict[str, list[str]] = defaultdict(list)

    def objects() -> Iterator[dict[str, object]]:
        for obj in kaikki.lines(paths["kaikki-ru"], "ru"):
            for form, marked in russian.form_readings(obj):
                if marked not in form_readings[form]:
                    form_readings[form].append(marked)
            obj = russian.cleaned(obj)
            participles.extend(russian.participles(obj))
            yield obj

    uses = treebanks.uses_for("ru", paths)
    words = kaikki.read_language(objects(), reading=russian.stressed, uses=uses)
    # a participle's declined forms count for its verb, unless the
    # participle is an adjective of its own (следующий: next) or the form
    # is already another word's
    headwords = {e.word for e in words.entries}
    for participle, verb in participles:
        if participle in headwords:
            continue
        for form in russian.declined(participle):
            if form not in words.forms and form not in headwords:
                words.forms[form].add(verb)
                words.verb_forms.add((form, verb))
    # a form of a form: "используется" is использоваться's, a passive
    # given only as "passive of использовать"; "лучшая" is лучший's, given
    # only as "superlative of хороший" - each counts for the word with an
    # entry
    for form, lemmas in words.forms.items():
        for lemma in [x for x in lemmas if x not in headwords]:
            for further in words.forms.get(lemma, set()) & headwords:
                lemmas.add(further)
                if (form, lemma) in words.verb_forms:
                    words.verb_forms.add((form, further))
    zh = kaikki.glosses_by_word(kaikki.lines(paths["kaikki-zh"], "ru"))
    zh_by_word: dict[str, dict[str, list[str]]] = defaultdict(dict)
    for key, glosses in zh.items():  # the Chinese edition may mark stress
        plain = russian.unstressed(key)
        found = zh_by_word[plain.split("|")[0]].setdefault(plain, [])
        found += [g for g in glosses if g not in found]
    entries = []
    forms: dict[str, list[str]] = defaultdict(list)
    for e in words.entries:
        entries.append(
            DraftEntry(
                key=e.key,
                headword=e.word,
                reading=e.reading,
                meanings=tuple(f"({e.pos}) {m}" if e.pos else m for m in e.meanings),
                ranked_by=(e.word,),
                source_pos=e.pos,
                zh_classes=chinese_classes(e.word, e.pos, zh_by_word.get(e.word, {})),
                zh_meanings=chinese_for(
                    e.word, e.pos, not forms[e.word], zh_by_word.get(e.word, {})
                ),
            )
        )
        forms[e.word].append(e.key)
    draft = Draft(
        entries,
        dict(forms),
        {f: set(ls) for f, ls in words.forms.items()},
        words.imperative,
        words.verb_forms,
        dict(form_readings),
        lemma_first=words.lemma_first,
    )
    written = treebanks.uses_for("ru", paths, forms_only=True)
    return with_treebanks(draft, words, uses, written)


# -- Vietnamese: Wiktionary ------------------------------------------------------


NOT_A_WORD = frozenset({"character", "romanization", "soft-redirect"})
"""Wiktionary's Vietnamese parts of speech that are no word of a caption: a
Hán Nôm character, a romanisation of one."""


def read_vietnamese(paths: Mapping[str, Path]) -> Draft:
    """Wiktionary's Vietnamese words in the Latin script (`vietnamese`),
    each of one or more syllables ("học sinh"), with their English
    meanings and IPA, and other spellings (hoà for hòa) as forms of the
    word; their frequencies counted in subtitles by the word split
    (decision 0121). English meanings only: meanings in other languages
    are to come as files of their own (polyglotic-hq 326)."""
    objects = (
        obj
        for obj in kaikki.lines(paths["kaikki-vi"], "vi")
        if obj.get("pos") not in NOT_A_WORD
        and vietnamese.is_latin(str(obj.get("word") or ""))
    )
    words = kaikki.read_language(
        objects, spaced_words=True, uses=treebanks.uses_for("vi", paths)
    )
    entries = []
    forms: dict[str, list[str]] = defaultdict(list)
    for e in words.entries:
        entries.append(
            DraftEntry(
                key=e.key,
                headword=e.word,
                reading=e.reading,
                meanings=tuple(f"({e.pos}) {m}" if e.pos else m for m in e.meanings),
                ranked_by=(e.word,),
                source_pos=e.pos,
            )
        )
        forms[e.word].append(e.key)
    # another spelling ("bất kỳ" for bất kì, "hoà" for hòa) is written in
    # captions as often as its word: a form of its own, so the word split
    # finds it (it splits by the dictionary's written forms) and a lookup
    # shows its word's entries
    for spelling, lemmas in words.forms.items():
        if spelling not in forms:
            for lemma in sorted(lemmas):
                forms[spelling] += [
                    k for k in forms.get(lemma, ()) if k not in forms[spelling]
                ]
            if not forms[spelling]:
                del forms[spelling]
    split_words = {word_key(w) for w in forms} | {word_key(w) for w in words.forms}
    counted = vietnamese.counted_words(paths["opensubtitles-vi"], split_words)
    return Draft(
        entries,
        dict(forms),
        {f: set(ls) for f, ls in words.forms.items()},
        counted={"opensubtitles-vi": counted},
    )


# -- Thai: Wiktionary ------------------------------------------------------------


def read_thai(paths: Mapping[str, Path]) -> Draft:
    """Wiktionary's Thai words (`thai.words`) with their English meanings
    and Paiboon romanization, and other spellings as forms of their own
    (as Vietnamese's); their frequencies counted in Common Voice's Thai
    sentences by the app's word split (`thai.counted_words`; decision
    0173). English meanings only (DECISIONS #175). A word's commonest part
    of speech first, by Thai's treebanks (`treebanks.uses_for`; decision
    0176): กับ is "with" before "trap"; the commonest words' first
    meanings as read by hand (`thai.first_senses`): โลก is "world", not
    "land; country" (polyglotic-hq 461)."""
    words = kaikki.read_language(
        thai.words(kaikki.lines(paths["kaikki-th"], "th")),
        kaikki.romanization,
        uses=treebanks.uses_for("th", paths),
        short_forms=True,
    )
    words.entries = thai.first_senses(words.entries)
    draft = draft_of(words)
    draft.split_shared_forms = True
    draft.keep_unranked = True
    draft.forms = {f: keys for f, keys in draft.forms.items() if thai.caption_word(f)}
    for spelling, lemmas in words.forms.items():
        if spelling not in draft.forms and thai.caption_word(spelling):
            found = [k for lemma in sorted(lemmas) for k in draft.forms.get(lemma, ())]
            if found:
                draft.forms[spelling] = list(dict.fromkeys(found))
    draft.counted = {
        "commonvoice-th": thai.counted_words(paths["commonvoice-th"], draft.forms)
    }
    return draft


# -- Cantonese: CC-Canto and CC-CEDICT ------------------------------------------


CANTONESE_RANKS = "hkcancor+wordfreq-zh"
"""The Cantonese pack's frequency list (`Draft.counted`): HKCanCor's words as
spoken, averaged with wordfreq's written Chinese where speech bears it out
(`cantonese.Said`)."""


def read_cantonese(paths: Mapping[str, Path]) -> Draft:
    """The Cantonese pack's draft from its sources (`cantonese_draft`)."""
    counts = cantonese.hkcancor_counts(paths["hkcancor"])
    total = sum(counts.values()) or 1
    canto = cantonese.read_canto(paths["cc-canto"])
    cedict_lines = cedict.read(paths["cedict"])
    utterances = cantonese.hkcancor_utterances(paths["hkcancor"])
    forms = {line.traditional for line in canto} | {
        line.traditional for line in cedict_lines
    }
    return cantonese_draft(
        canto,
        cantonese.read_readings(paths["canto-readings"]),
        cedict_lines,
        cantonese.Everyday(
            cantonese.read_rime_words(paths["rime-words"]),
            cantonese.read_rime_chars(paths["rime-chars"]),
            cantonese.heard_readings(utterances),
        ),
        {word: n / total for word, n in counts.items()},
        wordfreq_ranks.frequencies(paths["wordfreq"], "zh"),
        cantonese.said(utterances, cantonese.captions(), forms),
    )


def cantonese_draft(
    canto: Sequence[cantonese.CantoLine],
    readings: Mapping[tuple[str, str, str], list[str]],
    cedict_lines: Sequence[cedict.CedictLine],
    everyday: cantonese.ReadsEveryday,
    spoken: Mapping[str, float],
    written: Mapping[str, float],
    said: cantonese.Said,
    senses: Mapping[str, tuple[str, ...]] = cantonese.FIRST_SENSES,
    own: Mapping[str, tuple[str, ...]] = cantonese.OWN_SENSES,
) -> Draft:
    """Cantonese words (decision 0160; polyglotic-hq 371 and 450): CC-Canto's
    entries (Cantonese words, Jyutping, English meanings), then CC-CEDICT's
    entries with their Cantonese reading - of the readings file's
    (`readings`), the everyday one (`everyday`: rime-cantonese's) where it
    gives several; where it gives none, rime-cantonese's own. A CC-CEDICT
    entry CC-Canto has with the same reading is left to CC-Canto's if they
    have a meaning in common (CC-Canto adapted it) or it only points
    elsewhere (`POINTER`: "variant of", "used in", a surname); else it is
    kept, after CC-Canto's (四 "four" beside CC-Canto's "(slang) labourer";
    polyglotic-hq 467).

    Headwords in Traditional characters, as Cantonese captions come; the
    Simplified form finds the same entries, unless it is a Traditional
    headword of its own (系, "system", isn't 係's). A form's entries:
    those read its everyday way first (嘅 is ge3 before koi3); then
    one that only says "variant of" last, and before it one that is only
    slang or a surname (四 "four" before "(slang) labourer", 年 "year" before
    "surname Nian"; polyglotic-hq 467); then CC-Canto's before CC-CEDICT's.
    Then the commonest words open on the meanings a learner hears
    (`cantonese.FIRST_SENSES`).
    Jyutping with its tones raised (`cantonese.raised`). Every entry is
    kept, ranked or not: the word split is by the pack's own words.

    Ranks: HKCanCor's words (`spoken`: speech) and wordfreq's written
    Chinese (`written`, by each headword's Simplified form), averaged -
    Cantonese's own words (佢哋, 嘅) are ranked by HKCanCor alone, written
    ones by both. A word written far more often than speech says it
    (`said`: HKCanCor's and real captions' words, `cantonese.Said.written`)
    counts in writing only as often as it is said (polyglotic-hq 467): 的,
    是 and 他 are Mandarin's, where Cantonese says 嘅, 係 and 佢."""
    entries: list[DraftEntry] = []
    simplified: dict[str, str] = {}
    order: dict[str, tuple[str, int]] = {}  # a key -> (Jyutping, origin)
    by_key: dict[str, int] = {}
    # (Traditional, Jyutping) of CC-Canto's -> its meanings, in pieces
    in_canto: dict[tuple[str, str], set[str]] = defaultdict(set)

    lines_of: dict[str, list[tuple[str, ...]]] = defaultdict(list)

    def add(
        key: str,
        traditional: str,
        simple: str,
        jyutping: str,
        meanings: tuple[str, ...],
        origin: int,
    ) -> None:
        lines_of[key].append(meanings)
        if key in by_key:  # a line again: one entry of both (`one_entry`)
            return
        by_key[key] = len(entries)
        entries.append(
            DraftEntry(
                key=key,
                headword=traditional,
                reading=cantonese.raised(jyutping),
                meanings=meanings,
                ranked_by=(traditional,),
            )
        )
        simplified.setdefault(traditional, simple)
        order[key] = (jyutping, origin)

    for line in canto:
        if line.meanings and line.jyutping:
            key = f"canto|{line.traditional} {line.simplified} {{{line.jyutping}}}"
            add(
                key,
                line.traditional,
                line.simplified,
                line.jyutping,
                line.meanings,
                0,
            )
            in_canto[(line.traditional, line.jyutping)] |= cantonese.meaning_pieces(
                line.meanings
            )
    for entry in cedict_lines:
        found = readings.get(
            (entry.traditional, entry.simplified, cantonese.pinyin_key(entry.pinyin))
        )
        if not found:
            usual = everyday(entry.traditional, None)
            if usual is None:
                continue
            found = [usual]
        jyutping = everyday(entry.traditional, found) or found[0]
        canto_has = in_canto.get((entry.traditional, jyutping))
        if canto_has is not None and (
            canto_has & cantonese.meaning_pieces(entry.meanings)
            or all(m.lower().startswith(POINTER) for m in entry.meanings)
        ):
            continue
        add(
            f"cedict|{entry.key}",
            entry.traditional,
            entry.simplified,
            jyutping,
            entry.meanings,
            1,
        )
    forms: dict[str, list[str]] = defaultdict(list)

    for key, lines in lines_of.items():
        if len(lines) > 1:
            n = by_key[key]
            entries[n] = replace(entries[n], meanings=cantonese.one_entry(lines))
    said_as: dict[str, set[str]] = defaultdict(set)  # a headword -> its readings
    for e in entries:
        said_as[e.headword].add(order[e.key][0])
    usual_of = {word: everyday(word, ways) for word, ways in said_as.items()}

    def place(e: DraftEntry) -> tuple[int, int, int, int]:
        """Where an entry goes among its form's: by its reading (the
        everyday one of those the word's entries have), then by its meanings
        once every line of it is in (polyglotic-hq 467: CC-Canto's 曾 has a
        line of only "Chinese surname" before its line of "once")."""
        jyutping, origin = order[e.key]
        variant = all(m.startswith(VARIANT_OF) for m in e.meanings)
        aside = all(m.lower().startswith(cantonese.ASIDE) for m in e.meanings)
        return int(jyutping != usual_of[e.headword]), int(variant), int(aside), origin

    ordered = sorted(entries, key=place)
    for e in ordered:
        forms[e.headword].append(e.key)
    headwords = set(forms)
    for e in ordered:
        simple = simplified[e.headword]
        if simple != e.headword and simple not in headwords:
            forms[simple].append(e.key)
    open_on(entries, forms, senses, own)
    pointers = cantonese.pointer_only(
        ((e.headword, e.meanings) for e in entries), VARIANT_OF
    )
    for form, keys in forms.items():
        target = pointers.get(form)
        if (
            target in forms
            and target != form
            and all(entries[by_key[k]].headword == form for k in keys)
        ):
            keys[:0] = [k for k in forms[target] if k not in keys]
    averaged = frequency.Frequencies(
        (
            (
                word,
                (
                    spoken.get(word, 0.0)
                    + (
                        0.0
                        if word in pointers
                        else said.written(word, written.get(simple, 0.0))
                    )
                )
                / 2,
            )
            for word, simple in simplified.items()
            if word in spoken or (simple in written and word not in pointers)
        ),
        hyphenated=True,
    )
    draft = Draft(entries, dict(forms), counted={CANTONESE_RANKS: averaged})
    draft.keep_unranked = True
    return draft


VARIANT_OF = ("variant of ", "old variant of ", "archaic variant of ", "see ")
"""How CC-CEDICT starts a meaning that only points to another entry."""

POINTER = (*VARIANT_OF, "used in ", "surname ")
"""How CC-CEDICT starts a meaning that only points to another word (in
lower case): variants, "used in 胡同", surnames."""


def open_on(
    entries: list[DraftEntry],
    forms: Mapping[str, list[str]],
    senses: Mapping[str, tuple[str, ...]],
    own: Mapping[str, tuple[str, ...]],
) -> None:
    """Each word in `senses` opening on its meanings there, and each in
    `own` on its own meanings before them (`cantonese.FIRST_SENSES`,
    `cantonese.OWN_SENSES`), in place: of the word's entries read as its
    first is, the one with the first meaning moves first in every form that
    finds the word, those meanings first in it. Every key stays (no entry
    ID changes). A word the sources haven't got is passed over; a meaning
    a word no longer has stops the build (ValueError), so new sources
    can't quietly undo the order."""
    at = {e.key: i for i, e in enumerate(entries)}

    def put_first(word: str, key: str) -> None:
        for form in {word, *(f for f, keys in forms.items() if key in keys)}:
            keys = forms.get(form, [])
            if key not in keys:
                continue
            ours = [k for k in keys if entries[at[k]].headword == word]
            keys.remove(key)
            keys.insert(keys.index(ours[0]) if ours[0] != key else 0, key)

    def lead(key: str, meanings: tuple[str, ...]) -> None:
        e = entries[at[key]]
        rest = tuple(m for m in e.meanings if m not in meanings)
        entries[at[key]] = replace(e, meanings=(*meanings, *rest))

    for word, meanings in senses.items():
        keys = forms.get(word)
        if not keys:
            continue
        reading = entries[at[keys[0]]].reading
        first = next(
            (
                k
                for k in keys
                if entries[at[k]].reading == reading
                and meanings[0] in entries[at[k]].meanings
            ),
            None,
        )
        missing = [
            m for m in meanings if first and m not in entries[at[first]].meanings
        ]
        if first is None or missing:
            raise ValueError(f"{word}: no {reading} entry with {meanings!r}")
        lead(first, meanings)
        put_first(word, first)
    for word, added in own.items():
        mine = [k for k in forms.get(word, []) if entries[at[k]].headword == word]
        if mine:
            lead(mine[0], added)


# -- Japanese: JMdict -----------------------------------------------------------


def jlpt_levels(path: Path) -> dict[tuple[str, str], int]:
    """(written form, reading) -> level, 1 for N5 (the lowest) to 5 for N1.
    A word in kana alone has itself as its written form."""
    out: dict[tuple[str, str], int] = {}
    with path.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            n = int(row["Level"])
            key = (row["Kanji"].strip(), row["Reading"].strip())
            out[key] = min(out.get(key, 9), 6 - n)
    return out


def chinese_for_japanese(
    word: jmdict.JmdictWord,
    zh: Mapping[str, list[str]],
    kana_owner: Mapping[str, str],
) -> tuple[str, ...]:
    """The Chinese edition's meanings for a JMdict entry: those of its
    first kanji form the edition has (年's entries share 年's), else those
    of its kana if it owns the kana (`kana_owners`): かみ could be 神, 髪
    or 紙, but する is 為る, usually written する."""
    form = chinese_form_for_japanese(word, zh, kana_owner)
    return tuple(zh.get(form, ())[: jmdict.MAX_MEANINGS])


def chinese_form_for_japanese(
    word: jmdict.JmdictWord,
    zh: Mapping[str, list[str]],
    kana_owner: Mapping[str, str],
) -> str:
    return next(
        (
            form
            for form in (*word.kanji, *word.kana)
            if form in zh and (form in word.kanji or kana_owner.get(form) == word.seq)
        ),
        "",
    )


def japanese_chinese_classes(
    word: jmdict.JmdictWord,
    glosses: Sequence[str],
    evidence: Mapping[str, set[SenseClasses]],
) -> tuple[SenseClasses, ...]:
    allowed = {cls for labels in word.sense_classes for cls in labels or ()}
    classes: list[SenseClasses] = []
    for gloss in glosses:
        candidates = evidence.get(gloss, set())
        cls = next(iter(candidates)) if len(candidates) == 1 else None
        classes.append(cls if cls and set(cls) <= allowed else None)
    return tuple(classes)


def kana_owners(words: Sequence[jmdict.JmdictWord]) -> dict[str, str]:
    """Kana -> the entry its meanings belong to: the only entry written
    with it; or else the only common entry usually written in it (する:
    為る, not 掏る, "to pickpocket")."""
    written: dict[str, list[jmdict.JmdictWord]] = defaultdict(list)
    for w in words:
        for kana in w.kana:
            written[kana].append(w)
    owners = {}
    for kana, found in written.items():
        if len(found) == 1:
            owners[kana] = found[0].seq
            continue
        usual = [w for w in found if w.headword == kana and w.common]
        if len(usual) == 1:
            owners[kana] = usual[0].seq
    return owners


def usual_in_kana(word: jmdict.JmdictWord, kana_owner: Mapping[str, str]) -> bool:
    """Whether the kana it's usually written in is this entry's to count:
    it owns the kana (`kana_owners`), or no entry does and JMdict marks
    this one common (なる is both 成る, "to become", and 生る, "to bear
    fruit"). 掏る, "to pickpocket", is usually written する too, but rare."""
    owner = kana_owner.get(word.headword)
    return owner == word.seq or (owner is None and word.common)


def ranked_by(
    word: jmdict.JmdictWord, kana_owner: Mapping[str, str]
) -> tuple[str, ...]:
    """The forms whose frequency is a JMdict entry's: its headword - a
    kana headword only if it's this entry's to count (`usual_in_kana`);
    else its kanji's."""
    if word.headword not in word.kana or usual_in_kana(word, kana_owner):
        return (word.headword,)
    return word.kanji[:1]


def japanese(paths: Mapping[str, Path]) -> Draft:
    _, words = jmdict.read(paths["jmdict"])
    zh = kaikki.glosses_by_word(kaikki.lines(paths["kaikki-zh"], "ja"))
    zh_by_word: dict[str, list[str]] = defaultdict(list)
    labels: dict[str, dict[str, set[SenseClasses]]] = defaultdict(
        lambda: defaultdict(set)
    )
    for word_pos, glosses in zh.items():
        word, _, pos = word_pos.rpartition("|")
        zh_by_word[word] += [g for g in glosses if g not in zh_by_word[word]]
        for gloss in glosses:
            labels[word][gloss].add(sense_classes.wikt(pos))
    owners = kana_owners(words)
    counts = Counter(form for word in words for form in word.written)
    levels = jlpt_levels(paths["jlpt"])
    entries = []
    forms: dict[str, list[str]] = defaultdict(list)
    for w in words:
        # a word listed in kana alone is the entry that owns the kana
        pairs = [(k, kana) for k in w.kanji for kana in w.kana]
        if w.headword in w.kana and usual_in_kana(w, owners):
            pairs.append((w.headword, w.headword))
        level = min((levels[p] for p in pairs if p in levels), default=None)
        chinese_form = chinese_form_for_japanese(w, zh_by_word, owners)
        zh_meanings = tuple(zh_by_word.get(chinese_form, ())[: jmdict.MAX_MEANINGS])
        entries.append(
            DraftEntry(
                key=w.seq,
                headword=w.headword,
                reading=w.reading,
                meanings=w.meanings,
                ranked_by=ranked_by(w, owners),
                zh_meanings=zh_meanings,
                levels=(("jlpt", level),) if level else (),
                common=w.common,
                sense_classes=w.sense_classes,
                zh_classes=japanese_chinese_classes(
                    w, zh_meanings, labels[chinese_form]
                )
                if counts[chinese_form] == 1 and len(w.kana) == 1
                else (),
            )
        )
        for written in w.written:
            forms[written].append(w.seq)
    return Draft(entries, dict(forms))


PACKS = {
    "es": Pack(
        language="es",
        name="wiktes",
        title="Spanish",
        sources=(KAIKKI_ES, KAIKKI_ZH, WORDFREQ, *treebanks.of("es")),
        read=read_spanish,
        level_schemes="es-frequency",
        about=(
            "Wiktionary's Spanish words with their English meanings (and the "
            "Chinese edition's Chinese meanings in the -zh file), IPA and "
            "inflections, cut to the words wordfreq ranks, with frequency ranks "
            "from wordfreq"
        ),
    ),
    "fr": wiktionary_pack("fr", "French", KAIKKI_FR),
    # the first batch paired with English, by popularity (DECISIONS #175)
    "de": wiktionary_pack("de", "German", KAIKKI_DE, GERMAN),
    "pt": wiktionary_pack("pt", "Portuguese", KAIKKI_PT),
    "it": wiktionary_pack("it", "Italian", KAIKKI_IT),
    "id": wiktionary_pack("id", "Indonesian", KAIKKI_ID),
    "ar": wiktionary_pack("ar", "Arabic", KAIKKI_AR, ARABIC),
    "hi": wiktionary_pack("hi", "Hindi", KAIKKI_HI, HINDI),
    "pl": wiktionary_pack("pl", "Polish", KAIKKI_PL),
    "tr": wiktionary_pack("tr", "Turkish", KAIKKI_TR, TURKISH),
    "ms": Pack(
        language="ms",
        name="wiktms",
        title="Malay",
        sources=(KAIKKI_MS, KAIKKI_ID, WORDFREQ, *treebanks.of("id")),
        read=read_malay,
        level_schemes="ms-frequency",
        about=(
            "Wiktionary's Malay words with their English meanings, IPA and "
            "inflections, and the Indonesian words Malay writes alike and "
            'Malay text uses (their meanings marked "as in Indonesian"); '
            "cut to the words wordfreq ranks, with frequency ranks from "
            "wordfreq's Malay list"
        ),
        meanings=("en",),
    ),
    # the second batch (polyglotic-hq 387)
    "nl": wiktionary_pack("nl", "Dutch", KAIKKI_NL),
    "uk": wiktionary_pack("uk", "Ukrainian", KAIKKI_UK, STRESSED),
    "fa": wiktionary_pack(
        "fa", "Persian", KAIKKI_FA, PERSIAN, sentences=COMMONVOICE_FA
    ),
    "sv": wiktionary_pack("sv", "Swedish", KAIKKI_SV),
    "cs": wiktionary_pack("cs", "Czech", KAIKKI_CS),
    "ro": wiktionary_pack("ro", "Romanian", KAIKKI_RO, ROMANIAN),
    "el": wiktionary_pack("el", "Greek", KAIKKI_EL),
    "tl": wiktionary_pack("tl", "Filipino", KAIKKI_TL, FILIPINO),
    "mk": wiktionary_pack("mk", "Macedonian", KAIKKI_MK, MACEDONIAN),
    # wave 0's last (polyglotic-hq 448, 510)
    "ko": Pack(
        language="ko",
        name="wiktko",
        title="Korean",
        sources=(KAIKKI_KO, WORDFREQ),
        read=lambda paths: read_korean(paths),
        level_schemes="ko-frequency",
        about=(
            "Wiktionary's Korean words with their English meanings, Revised "
            "Romanization and conjugations, cut to the words wordfreq ranks, "
            "with frequency ranks from wordfreq (its words with their "
            "particles and endings counted for the word they are made from)"
        ),
        meanings=("en",),
    ),
    "th": Pack(
        language="th",
        name="wiktth",
        title="Thai",
        sources=(KAIKKI_TH, COMMONVOICE_TH, *treebanks.of("th")),
        read=read_thai,
        level_schemes="th-frequency",
        about=(
            "Wiktionary's Thai words with their English meanings, Paiboon "
            "romanization and other spellings, with frequency ranks from the "
            "words of Common Voice's Thai sentences, counted by the app's word "
            "split (words never met there are kept, unranked)"
        ),
        frequency=("commonvoice-th",),
        meanings=("en",),
    ),
    "ru": Pack(
        language="ru",
        name="wiktru",
        title="Russian",
        sources=(
            KAIKKI_RU,
            KAIKKI_ZH,
            WORDFREQ,
            FREQUENCYWORDS_RU,
            *treebanks.of("ru"),
        ),
        read=read_russian,
        level_schemes="ru-frequency",
        about=(
            "Wiktionary's Russian words with their English meanings (and the "
            "Chinese edition's Chinese meanings in the -zh file), the stress "
            "marked as Wiktionary marks it, and inflections, found without "
            "their stress marks and with е for ё; cut to the words ranked, "
            "with frequency ranks from wordfreq's and OpenSubtitles' word "
            "frequencies averaged"
        ),
        # captions are speech: subtitles' counts beside wordfreq's mostly
        # written blend (polyglotic-hq 325 measured each on held-out text)
        frequency=("wordfreq", "frequencywords-ru"),
    ),
    "vi": Pack(
        language="vi",
        name="wiktvi",
        title="Vietnamese",
        sources=(KAIKKI_VI, OPENSUBTITLES_VI, *treebanks.of("vi")),
        read=read_vietnamese,
        level_schemes="vi-frequency",
        about=(
            "Wiktionary's Vietnamese words in the Latin script, of one or more "
            "syllables, with their English meanings, IPA and other spellings; "
            "cut to the words ranked, with frequency ranks from the words of "
            "OpenSubtitles' Vietnamese subtitles, counted by the app's word "
            "split"
        ),
        frequency=("opensubtitles-vi",),
        meanings=("en",),
    ),
    "ja": Pack(
        language="ja",
        name="jmdict",
        title="Japanese",
        sources=(JMDICT, KAIKKI_ZH, JLPT, WORDFREQ),
        read=japanese,
        level_schemes="jlpt ja-frequency",
        about=(
            "JMdict's words with their kana readings and English meanings (and "
            "the Chinese edition of Wiktionary's Chinese meanings in the -zh "
            "file), unofficial JLPT levels, and frequency ranks from wordfreq"
        ),
    ),
    "yue": Pack(
        language="yue",
        name="canto",
        title="Cantonese",
        sources=(
            CC_CANTO,
            CANTO_READINGS,
            CEDICT_FOR_CANTONESE,
            RIME_WORDS,
            RIME_CHARS,
            HKCANCOR,
            WORDFREQ_ZH,
        ),
        read=read_cantonese,
        level_schemes="yue-frequency",
        about=(
            "CC-Canto's Cantonese words with their Jyutping and English "
            "meanings, then CC-CEDICT's words with their Cantonese readings "
            "(the readings file's, else rime-cantonese's), in Traditional "
            "characters with Jyutping's tones raised, each word's everyday "
            "reading first (by rime-cantonese); with frequency ranks from "
            "HKCanCor's spoken words and wordfreq's written Chinese, averaged "
            "(words met in neither are kept, unranked)"
        ),
        frequency=(CANTONESE_RANKS,),
        meanings=("en",),
    ),
}


# -- shared ---------------------------------------------------------------------


JOINED = 10.0
"""How much rarer a hyphenated word is than the phrase of its parts, for a
list without hyphenated words (wordfreq's): wordfreq's own factor for a
word it joins from parts (its INFERRED_SPACE_FACTOR, used for Chinese).
Without it Portuguese's tem-tem was its 69th word, Indonesian's ada-ada its
28th and German's Über-Ich its 63rd (polyglotic-hq 380): every part
common, so the phrase of them looked as common as a word."""


REPEATED = 1e-8
"""The frequency of a word made of one word repeated with a hyphen
(Filipino's ang-ang, Indonesian's orang-orang): wordfreq's rarest
listed words' (its large lists stop at 10^-8). Its parts say nothing of
how often it is used - the phrase "ang ang" is no real use - and as the
phrase of its parts over `JOINED` Filipino's stutters "ang-ang" and
"at-at" had been its 30th and 62nd words (polyglotic-hq 387, 390). So it
is kept, as rare as can be: looked up, never counted as common."""


def no_word(word: str) -> bool:
    """An affix, a word with a digit or a capital letter alone: never a
    word a learner learns, so it takes no rank (`frequency_of`), not even
    from its forms (`frequencies`). wordfreq's "s" or "d" is the letter,
    or an elided word: German's letter-nouns S and D had come into its top
    300 once 387 dropped the letters' own entries (polyglotic-hq 390)."""
    return (
        word.startswith("-")
        or word.endswith("-")
        or any(c.isdigit() for c in word)
        or (len(word) == 1 and word.isupper())
    )


DOTTED_I = "i̇"
"""Python's lower case of İ (Turkish's capital i): i with a combining dot,
which no frequency list writes - İngiltere, İstanbul and İngilizce had no
frequency and were cut from the Turkish pack (polyglotic-hq 388)."""


def listed(word: str, freq: Mapping[str, float]) -> float:
    """`word`'s share in a list, in lower case or as the list folds it:
    wordfreq folds German's ß to ss (Unicode case folding), so "straße"
    and "gleichermaßen" had no frequency and were cut from the pack
    (polyglotic-hq 380)."""
    return (
        freq.get(word, 0.0)
        or freq.get(word.casefold(), 0.0)
        or freq.get(word.replace(DOTTED_I, "i"), 0.0)
    )


ELISION = "'’"
"""The apostrophes an elided word ends in."""


def elided_frequency(
    word: str, freq: Mapping[str, float], elided: frozenset[str]
) -> float:
    """An elided word's frequency ("dell'", "n'"): wordfreq's tokens drop the
    apostrophe, so it is listed as "dell". Italian's dell', nell' and sull'
    had no frequency and were cut from the pack: "dell'anno" opened nothing
    (polyglotic-hq 402, 413). Only the words the app's split cuts off as
    elided (`Draft.elisions`): German's genitive "Paris'" is no elision, and
    "champ'" (champagne) isn't "champ". 0 for any other word."""
    short = word[:-1]
    if word[-1:] not in ELISION or short.lower() not in elided:
        return 0.0
    return frequency_of(short, freq)


def frequency_of(word: str, freq: Mapping[str, float]) -> float:
    """`word`'s frequency in a frequency list, in lower case.

    - An affix ("в-", "-ить") is never a word in a caption: 0. wordfreq
      has no hyphens, so it had been given its stem's frequency - "в-" was
      Russian's commonest entry, and 79 of its top 1,000 were affixes
      (polyglotic-hq 325).
    - A hyphenated word the list hasn't got whole gets what wordfreq gives
      a phrase of its parts - one over the sum of one over each part's -
      over `JOINED`, or 0 if a part is missing: wordfreq's tokens split at hyphens
      (премьер-министр). A list counting hyphenated words whole puts it
      no higher than its rarest word (`frequency.Frequencies.hyphenated`):
      "у-т" and "так-с", made of common parts, had been in Russian's top
      100 (polyglotic-hq 325). One word repeated (ang-ang) gets
      `REPEATED`.
    - A word with a digit ("311", "9-3", "4x4") is no word a learner
      learns (numerals aren't pointed out as new, polyglotic-hq 360):
      0. wordfreq writes digits as 0s, and a hyphenated one took its
      parts' frequencies: seven were in French's top 1,000 (polyglotic-hq
      374)."""
    if no_word(word):
        return 0.0
    word = word.lower()
    if word in freq or "-" not in word:
        return listed(word, freq)
    pieces = [p for p in word.split("-") if p]
    parts = [listed(p, freq) for p in pieces]
    if not parts or not all(parts):
        return 0.0
    if len(set(pieces)) == 1 and len(pieces) > 1:
        return REPEATED  # ang-ang, at-at: no list says how often
    estimate = 1 / sum(1 / f for f in parts)
    if isinstance(freq, frequency.Frequencies) and freq.hyphenated:
        return min(estimate, freq.floor)
    return estimate / JOINED


def frequencies(draft: Draft, freq: Mapping[str, float]) -> dict[str, float]:
    """Entry key -> its frequency: the forms it is written in plus those of
    its inflections that have no entry of their own (a form with one
    counts for that entry only: "casa", house, doesn't make casar, to
    marry, common).

    Frequency lists are in lower case, so a capitalised entry whose word
    in lower case is another entry's or an inflected form ("Или", the
    river Ili: или, "or"; "Земля", Earth: земля, earth) doesn't take that
    word's frequency, nor its own forms' that are lower-case words too
    ("Земли" is земли) - but a name takes the share the treebanks use the
    word as a name (`name_frequency`: Paris, also pari's plural "paris",
    polyglotic-hq 416). A name's other forms count: Polska (Poland), whose
    "polska" is polski's, is found by "Polsce" ("in Poland"), Polish's
    167th word - it had been cut from the pack (polyglotic-hq 390).
    Nor does a form in capitals give its word that frequency: "NO", an
    abbreviation of noroeste, had made "northwest" Spanish's tenth word,
    with "no" (polyglotic-hq 325).

    Two exceptions (polyglotic-hq 380):
    - where capitals are spelling (`Draft.capitalised`: German's nouns),
      the capitalised word and its forms take the frequency too: Mensch,
      Menschen and Abend had none, for a rare pronoun and an old spelling;
    - a word that is only a name and also another word's form (Hindi's
      गया, the city Gaya and "went"; Arabic's الأرض, the planet and "the
      earth") gives the form's frequency to that word, not the name.
    """
    names = name_only(draft)
    headword = {e.key: e.headword for e in draft.entries}
    forms_of = inflections_of(draft)
    declined = {
        key
        for key, forms in draft.capitalised.items()
        if in_use(headword[key], forms, freq)
    }
    declined_forms = {f for key in declined for f in draft.capitalised[key]}
    nouns: dict[str, str] = {}  # a declined noun's spelling -> its headword
    for key in declined:
        nouns[headword[key]] = headword[key]
        for spelling in draft.capitalised[key]:
            nouns.setdefault(spelling, headword[key])
    by_headword: dict[str, list[str]] = defaultdict(list)
    lower_case = {
        e.headword for e in draft.entries if e.headword == e.headword.lower()
    } | {f for f in draft.inflections if f == f.lower()}
    look_alike = set()
    gives_way: set[str] = set()
    total: dict[str, float] = {}
    for e in draft.entries:
        by_headword[e.headword].append(e.key)
        word = e.headword
        if (
            word != word.lower()
            and word.lower() in lower_case
            and e.key not in declined
        ):
            look_alike.add(e.key)
        own_words = () if e.key in look_alike else set(e.ranked_by)
        total[e.key] = sum(frequency_of(w, freq) for w in own_words)
        if e.key in look_alike and word in names:
            total[e.key] = name_frequency(word, freq, draft.uses)
        if not total[e.key] and part_of_speech(e.meanings) not in kaikki.NO_WORD_POS:
            total[e.key] = sum(
                elided_frequency(w, freq, draft.elisions) for w in own_words
            )
    taken, kept = shared_spellings(
        draft, total, freq, look_alike & set(draft.capitalised), by_headword
    )
    # only an inflection: a noun's own headword (Bisschen) or a name (Soleil,
    # Jean) says nothing of how often the lower-case word is met
    inflected = declined_forms - {headword[key] for key in declined}
    cut = looked_like(draft, total, freq, inflected, forms_of)
    alone = {
        word: max(total[k] for k in keys) for word, keys in by_headword.items()
    }  # each word's own frequency, before its forms'
    for form, lemmas in draft.inflections.items():
        look_alike_form = (
            form != form.lower()
            and form.lower() in lower_case
            and form not in declined_forms  # Menschen; not "So" (Sonntag's)
        )
        own = form in by_headword and form not in names and form not in draft.elided
        f = (
            0.0
            if own or look_alike_form
            else frequency_of(form, freq)
            or elided_frequency(form, freq, draft.elisions)
        )
        f = max(0.0, f - taken.get(form, 0.0))  # Wasser's share of "wasser"
        if form in draft.elided:
            gives_way.update(by_headword.get(form, ()))  # Romanian's "i": îi's
        if form in names and any(lemma not in names for lemma in lemmas):
            gives_way.update(by_headword[form])  # the name gives way
        # a lower-case form of a word cut down as a look-alike, that is a
        # noun's spelling in capitals ("herz", herzen's imperative, is Herz),
        # shares with that noun, whose part is counted already (`declined`):
        # herzen had taken Herz's
        capital = form[:1].upper() + form[1:]
        noun = (
            nouns.get(capital)
            if form == form.lower() and capital != form and lemmas & cut
            else None
        )
        sharing = lemmas | {noun} if noun and noun in by_headword else lemmas
        if f:
            for lemma, share in shares(draft, sharing, by_headword, alone).items():
                if lemma not in lemmas:
                    continue
                for key in by_headword[lemma]:
                    total[key] += f * share
    for key in gives_way | {
        k for k in look_alike if headword[k] not in names and k not in kept
    }:
        total[key] = 0.0  # only a name keeps its own forms' (Polska's Polsce)
    for e in draft.entries:
        if no_word(e.headword):  # "4x4" had taken quatre-quatre's (380)
            total[e.key] = 0.0
    return total


def shared_spellings(
    draft: Draft,
    total: dict[str, float],
    freq: Mapping[str, float],
    look_alike: Collection[str],
    by_headword: Mapping[str, Sequence[str]],
) -> tuple[dict[str, float], set[str]]:
    """German nouns whose lower case is only another word's inflected form,
    not a word of its own (`look_alike`: capitalised nouns not in use by
    their own forms): each takes, of that spelling's frequency, at most
    1 / `DECLINED` times its own forms' that are no other word's (Wassers,
    Endes, Glücks), in `total`. Returns
    each such spelling -> what the nouns took of it (its lemmas share the
    rest), and the nouns' keys. A lower-case list can't tell "wasser"
    (wassern's imperative) from Wasser, so Wasser had no frequency and was
    cut from the pack, and "Wasser" opened on wassern, "to land on water";
    so did Ende (enden), Glück (glücken) and Titel (titeln) (polyglotic-hq
    461). A noun with no such forms (Habe, "belongings": "habe" is haben's)
    or whose lower case is a word (Essen, essen) keeps none, as before."""
    words = {e.headword for e in draft.entries if e.headword == e.headword.lower()}
    taken: dict[str, float] = {}
    kept: set[str] = set()
    for e in draft.entries:
        low = e.headword.lower()
        if e.key not in look_alike or low in words or low not in draft.inflections:
            continue
        met = sum(
            frequency_of(form, freq)
            for form in draft.capitalised.get(e.key, ())
            if form.lower() != low
            and form.lower() not in words
            and form.lower() not in draft.inflections
        )
        share = min(frequency_of(low, freq), met / DECLINED)
        if share:
            total[e.key] = share
            taken[low] = taken.get(low, 0.0) + share
            kept.add(e.key)
    return taken, kept


def inflections_of(draft: Draft) -> dict[str, list[str]]:
    """Each lemma -> its inflected forms (`Draft.inflections` turned round)."""
    out: dict[str, list[str]] = defaultdict(list)
    for form, lemmas in draft.inflections.items():
        for lemma in lemmas:
            out[lemma].append(form)
    return out


def met_as_forms(
    word: str,
    forms_of: Mapping[str, Sequence[str]],
    freq: Mapping[str, float],
    others: Collection[str] = (),
) -> float:
    """How often `word`'s inflected forms other than itself are met, leaving
    out those that are, in lower case, another word (`others`): German
    tables list a verb's auxiliary, "haben", and herzen's imperative
    "herz" is Herz."""
    return sum(
        frequency_of(f, freq)
        for f in forms_of.get(word, ())
        if f.lower() != word.lower() and f.lower() not in others
    )


def looked_like(
    draft: Draft,
    total: dict[str, float],
    freq: Mapping[str, float],
    capitalised: Collection[str],
    forms_of: Mapping[str, Sequence[str]],
) -> set[str]:
    """`total` with a lower-case word's own frequency cut down where its
    spelling, capitalised, is a German noun's inflected form in use, where
    it is a verb
    (`capitalised`) and its own forms are met less than `DECLINED` times
    as often as its spelling: a lower-case list counts the noun's uses as
    its own. It keeps at most 1 / `DECLINED` times its forms' frequency.
    German's "herzen" (to hug) took Herzen's (hearts) and was 502nd;
    "ketten" (to chain) took Ketten's, "titeln" Titeln's (polyglotic-hq
    448, 461). Not where the capitalised spelling is a name or a noun's
    own headword: Soleil, Jean and Bisschen had cut soleil, jean and
    bisschen out of their packs' top 1,000; nor where it is no verb (danke,
    whose capital is Dank's dative, had dropped to 44,972nd; gewesen, out
    of the top 1,000). A word without forms keeps its
    own: nothing says how often it is met. Returns the words cut down: of
    their forms, those spelled as a noun share with it (`frequencies`)."""
    cut: set[str] = set()
    others = {e.headword.lower() for e in draft.entries} | {
        c.lower() for c in capitalised
    }
    for e in draft.entries:
        word = e.headword
        capital = word[:1].upper() + word[1:]
        if (
            word != word.lower()
            or capital == word
            or capital not in capitalised
            or part_of_speech(e.meanings) != "verb"
        ):
            continue  # a verb's spelling: "danke" and "gewesen" are words in use
        met = met_as_forms(word, forms_of, freq, others - {word})
        if met and total[e.key] > met / DECLINED:
            total[e.key] = met / DECLINED
            cut.add(word)
    return cut


def name_frequency(
    name: str, freq: Mapping[str, float], uses: kaikki.Uses | None
) -> float:
    """A name's frequency where its lower case is another word too: its
    share of the word's, as the treebanks use the word as a name, if they
    use it at least `kaikki.MIN_USES` times and as a name in at least
    `kaikki.MIN_SHARE` of them; else 0, as before. French's Paris is also
    "paris", pari's plural "bets": wordfreq can't tell them apart, so the
    city had no frequency, was cut from the pack, and opened on "bet"; the
    treebanks use "paris" as a name 34 times in 35 (polyglotic-hq 416).
    Only a name used alone counts, not a word of a name of several
    (`treebanks.IN_NAME`): Italian's "stati" is a name only in "Stati
    Uniti", not the surname Stati, whose card had opened for "Stati"."""
    counts = uses.get(name.lower(), {}) if uses else {}
    every = sum(counts.values())
    named = counts.get("PROPN", 0)
    if every < kaikki.MIN_USES or named < kaikki.MIN_SHARE * every:
        return 0.0
    return frequency_of(name, freq) * named / every


DECLINED = 0.1
"""A capitalised noun's own forms (Menschen, Häuser) must be met at least
this often for every time its lower-case spelling is, for that spelling's
frequency to be the noun's: wordfreq is in lower case, so "mensch" can't
say whether it is Mensch or the rare pronoun mensch, but "menschen" can.
On German's real list (polyglotic-hq 380): Mensch 4.8, Haus 0.92, Abend
0.26, Morgen 0.15, Leben 0.11 take it; the nouns Essen 0.009, Ich (the
ego) 0.001, Habe (belongings), Ja and Des (D-flat) don't."""


def in_use(word: str, forms: frozenset[str], freq: Mapping[str, float]) -> bool:
    """Whether a capitalised noun's own forms show it is the word its
    lower-case frequency counts (`DECLINED`)."""
    alone = frequency_of(word, freq)
    others = sum(frequency_of(f, freq) for f in forms if f.lower() != word.lower())
    return alone > 0 and others >= DECLINED * alone


def shares(
    draft: Draft,
    lemmas: set[str],
    by_headword: Mapping[str, list[str]],
    own: Mapping[str, float],
) -> dict[str, float]:
    """Each of a form's lemmas (those with entries) and the share of the
    form's frequency it takes: all of it each, or - where the draft splits
    shared forms - in proportion to each lemma's own frequency (equal if
    none has one)."""
    known = sorted(lemma for lemma in lemmas if lemma in by_headword)
    weights = [own[lemma] for lemma in known]
    if not draft.split_shared_forms or len(known) < 2:
        return dict.fromkeys(known, 1.0)
    whole = sum(weights)
    return {
        lemma: (w / whole if whole else 1 / len(known))
        for lemma, w in zip(known, weights, strict=True)
    }


def name_only(draft: Draft) -> set[str]:
    """Headwords whose every entry is a name ("(name) ...")."""
    meanings: dict[str, list[str]] = defaultdict(list)
    for e in draft.entries:
        meanings[e.headword] += e.meanings or [""]
    return {
        word
        for word, ms in meanings.items()
        if all(m.startswith("(name) ") for m in ms)
    }


def ranks(draft: Draft, total: Mapping[str, float]) -> dict[str, int]:
    """Entry key -> frequency rank (1 = commonest), by `frequencies`. A rank
    is one word: a headword's entries share it (в "in" and в the letter's
    name), as CC-CEDICT's do (还 hái and huán), so "the top 1,000" is a
    thousand words - Russian's had been about 700 (polyglotic-hq 325).
    Ties keep the source's order. Unranked entries are left out."""
    order = {e.key: n for n, e in enumerate(draft.entries)}  # ties: the source's
    headword = {e.key: e.headword for e in draft.entries}
    ranked = sorted(
        (k for k in total if total[k] > 0), key=lambda k: (-total[k], order[k])
    )
    words: dict[str, int] = {}
    for key in ranked:
        words.setdefault(headword[key], len(words) + 1)
    return {key: words[headword[key]] for key in ranked}


IMPERATIVE_WEIGHT = 0.01
"""How much an imperative-only link counts when a form has several lemmas:
"sé" is saber's "I know" far more often than ser's "be!", though ser is
the commoner verb (polyglotic-hq 174's hard forms)."""


def lemma_table(
    draft: Draft,
    kept: set[str],
    total: Mapping[str, float],
    freq: Mapping[str, float],
) -> tuple[dict[str, str], dict[str, str]]:
    """Inflected form -> the lemma it counts for (decision 0035):
    - of its lemmas the pack keeps, the commonest - an imperative-only
      link weighed down (`IMPERATIVE_WEIGHT`);
    - a form with an entry of its own too ("era": an age, and ser's "was")
      gets its lemma first only if it is that verb's inflection and the
      verb's other forms are at least as common as the form itself - "era"
      counts for ser; "casa" stays a house, not casar's "marries"; a noun's
      or adjective's forms and other spellings keep their own entry first
      ("gafas", glasses; "neta", truth);
    - a form whose page starts with it as that lemma's form, and that is no
      word of its own (`Draft.lemma_first`), gets its lemma first: Spanish's "su" showed
      "about, approximately" before suyo's "his, her", "una" "one (a
      pronoun)" before un's "a" (polyglotic-hq 393).
    The lookup shows the lemma's entries, then the form's own. Returns
    that table, and form -> the lemma to show *after* the form's own
    entries, for the forms that keep theirs first ("casa": house, then
    casar)."""
    family: dict[str, float] = {}
    for e in draft.entries:
        if e.key in kept:
            family[e.headword] = max(family.get(e.headword, 0.0), total[e.key])
    out, after = {}, {}
    moved: set[str] = set()  # forms that count for a lemma by `lemma_used`
    for form, lemmas in draft.inflections.items():

        def weight(lemma: str, form: str = form) -> float:
            down = IMPERATIVE_WEIGHT if (form, lemma) in draft.imperative else 1.0
            return family[lemma] * down

        found = sorted((lemma for lemma in lemmas if lemma in family), key=str)
        if not found:
            continue
        best = max(found, key=weight)
        own = form in draft.forms and any(k in kept for k in draft.forms[form])
        named = [lemma for lemma in found if lemma in draft.lemma_first.get(form, ())]
        used = [lemma for lemma in found if lemma in draft.lemma_used.get(form, ())]
        if not own or (
            (form, best) in draft.verb_forms
            and weight(best) >= freq.get(form.lower(), 0.0)
            and form not in draft.own_first
            and not (form in draft.own_verbs and family.get(form, 0.0) >= weight(best))
        ):
            out[form] = (
                used_as_lemma(form, found, draft.came_through, draft.written) or best
            )
        elif named:  # "una" starts as uno's: uno, not the commoner un
            out[form] = max(named, key=weight)
        elif used:  # "est" is être's far more than "east" (413)
            out[form] = max(used, key=weight)
            moved.add(form)
        else:
            after[form] = best
    return chained_lemmas(out, draft.came_through, moved), after


def used_as_lemma(
    form: str,
    lemmas: Sequence[str],
    came_through: Mapping[tuple[str, str], set[str]],
    uses: kaikki.Uses | None,
) -> str | None:
    """Of a form's `lemmas`, the one whose parts of speech it came through
    the treebanks use it as, at least `kaikki.MIN_USES` times and
    `kaikki.LEAD` times as often as each other's; None where they don't
    say. Portuguese's "melhor" is bom's comparative (better) and bem's
    (better, as an adverb): written as an adjective 25 times and an
    adverb 8, it had opened on the commoner bem, "well"; Italian's "c'" is
    ci's (us, there) and che's (that), used as a pronoun 10 times, and had
    opened on che (polyglotic-hq 416)."""
    counts = uses.get(form.lower(), {}) if uses else {}
    used = sorted(
        (
            (kaikki.used_as(counts, came_through.get((form, lemma), set())), lemma)
            for lemma in lemmas
        ),
        reverse=True,
    )
    if len(used) < 2 or used[0][0] < kaikki.MIN_USES:
        return None
    (most, lemma), (next_most, _) = used[0], used[1]
    return lemma if most >= kaikki.LEAD * next_most else None


def chained_lemmas(
    lemmas: dict[str, str],
    came_through: Mapping[tuple[str, str], set[str]],
    moved: set[str],
) -> dict[str, str]:
    """`lemmas` (form -> the lemma it counts for) with a form whose lemma
    counts for another word, and that is that word's form too in a part of
    speech it is its lemma's in, counting for that word: the lookup shows
    only the lemma's own entries, not its lemma's. French's "l'" and "les"
    are la's and le's, as article and pronoun; la counts for le (the
    article), and they had opened on la's pronoun, "her" (polyglotic-hq 402,
    413). Not a form of the lemma alone (Portuguese's "la" is a's, the
    pronoun "her", not o's, which a counts for), nor one that is the other
    word's in another part of speech: French's "traces" is trace's plural
    (a noun) and tracer's "you draw" - trace counts for tracer, and traces
    had opened on "to draw". Only through a lemma `lemma_used` moved
    (`moved`): Portuguese's pesado counts for pesar, the verb whose
    participle it is too, but "pesada" stays pesado's, "heavy". Only where
    the reader says how forms came (`Draft.came_through`)."""
    out = {}
    for form, lemma in lemmas.items():
        further = lemmas.get(lemma) if lemma in moved else None
        shared = (
            came_through.get((form, lemma), set())
            & came_through.get((form, further), set())
            if further and further != form
            else set()
        )
        out[form] = further if shared and further else lemma
    return out


def opened_through(
    draft: Draft,
    forms: Mapping[str, list[str]],
    lemmas: Mapping[str, str],
    pos_of: Mapping[str, tuple[str, str]],
) -> dict[str, list[str]]:
    """The forms whose card opens on their lemma's entries in the parts of
    speech the form came through (`Draft.came_through`), and those entry
    IDs, in that order: form -> its lemma's IDs, those first. Only a form
    with no entry of its own, whose lemma's first entry is in another part
    of speech: Romanian's vă is in the pronoun voi's table, and its card
    opened on the verb voi, "to want" (polyglotic-hq 396, 399). The form
    gets a row of its own with them, in place of its lemma's (`lemma_table`,
    whose entries the lookup would show first); `pos_of`: entry ID -> its
    word and part of speech. `forms`: each word's own row, without another
    word's shown after it (`own_entries_only`); only the lemma's own entries
    come first (Polish's momencikom is momencik's, not moment's).

    Not a form that is its lemma said twice (Indonesian's and Malay's
    indah-indah): Wiktionary lists it in a noun's table as the plural, but
    an adjective's or a verb's said twice is that word made strong or
    repeated, so it keeps its lemma's commonest entry first. In a sample
    of 30 changed cards per pack, 11 of the 26 such read worse by their
    table, 7 better (indah-indah, "really beautiful", had opened on
    "infant feces"; polyglotic-hq 407)."""
    out = {}
    for form, lemma in lemmas.items():
        through = draft.came_through.get((form, lemma))
        shown = forms.get(lemma, [])
        if not through or form in forms or not shown or pos_of[shown[0]][1] in through:
            continue
        if form == f"{lemma}-{lemma}":  # said twice: not by its table (407)
            continue
        first = [i for i in shown if pos_of[i][0] == lemma and pos_of[i][1] in through]
        if first:
            out[form] = first + [i for i in shown if i not in first]
    return out


def opened_as_used(
    draft: Draft,
    forms: Mapping[str, list[str]],
    lemmas: Mapping[str, str],
    pos_of: Mapping[str, tuple[str, str]],
) -> dict[str, list[str]]:
    """The forms that count for a lemma by `lemma_used`, each with a row of
    its own: the lemma's entries in the parts of speech the form came
    through and has none of its own in first (those the treebanks use it
    as), then the lemma's others, then the form's own. Italian's "tutti" is
    tutto's determiner, "all", but tutto's row starts with the noun,
    "whole"; German's "seiner" is sein's determiner, "his", but sein's row
    starts with the verb "to be".

    The forms looked up through such a form, which would show them that row,
    get a row of their own with what they showed before: its own entries,
    then theirs. Portuguese's "la" is a's pronoun, "her"; a, used as o's
    article, opens on "the". `forms`: each word's own row; `pos_of`: entry
    ID -> its word and part of speech."""
    out = {}
    for form, lemma in lemmas.items():
        if lemma not in draft.lemma_used.get(form, ()):
            continue
        mine = forms.get(form, [])
        used = draft.came_through.get((form, lemma), set()) - {
            pos_of[i][1] for i in mine
        }
        shown = forms.get(lemma, [])
        first = [i for i in shown if pos_of[i][0] == lemma and pos_of[i][1] in used]
        row = first + [i for i in shown if i not in first]
        out[form] = row + [i for i in mine if i not in row]
    for form, lemma in lemmas.items():
        if lemma in out and form not in out:
            mine = forms.get(lemma, [])
            out[form] = mine + [i for i in forms.get(form, []) if i not in mine]
    return out


def own_entries_only(
    draft: Draft,
    own: Mapping[str, list[str]],
    lemmas: Mapping[str, str],
    after: Mapping[str, str],
    pos_of: Mapping[str, tuple[str, str]],
) -> dict[str, list[str]]:
    """The forms reached through a lemma whose row shows another word's
    entries after its own (`lemma_table`'s `after`: "casa", a house, then
    casar), and the rows that show only the lemma's: form -> its lemma's
    own entry IDs, then the form's own (`own`: each word's row before
    `after`'s). The lookup showed the lemma's whole row, so Ukrainian's нам
    (ми's) showed мі, the note mi, after "we", and тобі (ти's) той, "that"
    (polyglotic-hq 399, 407). The form gets a row of its own in place of
    its lemma's, as in `opened_through`.

    Only where the word shown after has no entry in a part of speech the
    form came through (`Draft.came_through`; `pos_of`: entry ID -> its
    word and part of speech): нам is in ми's pronoun table, and мі is only
    a noun. Where it has one, it may be the form's word too: French's
    "iles" is ile's plural, and ile only a spelling of île (island), a
    noun; "traitée" is traité's, the participle of traiter (to treat). The
    generic reader's only: where a reader says nothing of how forms came
    (Russian's, Spanish's), such forms keep their lemma. These do too:
    - a form of the word shown after too ("casas" is casar's as well as
      casa's: house, then to marry);
    - a form other forms are looked up through, which would show them its
      lemma's entries."""
    through = set(lemmas.values())
    out = {}
    for form, lemma in lemmas.items():
        if lemma not in after or form in through:
            continue
        if after[lemma] in draft.inflections.get(form, ()):
            continue
        way = draft.came_through.get((form, lemma), set())
        if not way or {pos_of[i][1] for i in own.get(after[lemma], ())} & way:
            continue
        first = own[lemma]
        out[form] = first + [i for i in own.get(form, ()) if i not in first]
    return out


def part_of_speech(meanings: Sequence[str]) -> str:
    """The part of speech a record's first meaning starts with ("(verb) to
    be": "verb"), or ""."""
    first = meanings[0] if meanings else ""
    return first[1 : first.index(")")] if first.startswith("(") and ")" in first else ""


COMMON = 1000
"""The rank a lower-case word needs, where no treebank says, to come before
a capitalised spelling's own entries (`capitals_first`): a sentence's first
word is seldom a rare one, and a name often looks like one - Portuguese's
Khartoum had opened on cartune, "cartoon", and Russian's Максиме (Maxim's
dative) on максима, "maxim", the 3,725th word (polyglotic-hq 413)."""


COMMONEST = 100
"""How many of the frequency list's commonest words come before even a
name's own headword where no treebank says (`capitals_first`): a
sentence's first word that is one of a language's hundred commonest is
that word far more often than a name. Ukrainian's "Того" (того, "of
that") had opened on Togo; Tournai (tourner's "I turned") stays the
city. The word itself, not its lemma: Ukrainian's "Кім" stays the
surname Kim, though кім is a form of хто ("who"). Not where the name's
lower case is the same word (Україна; Filipino's "Isa", Jesus, though
isa is "one") (polyglotic-hq 416)."""


def capitals_first(
    forms: Mapping[str, list[str]],
    lemmas: Mapping[str, str],
    rank: Mapping[str, int],
    said: Mapping[str, tuple[str, str]],
    uses: kaikki.Uses | None,
    spelled: bool = False,
    commonest: frozenset[str] = frozenset(),
) -> dict[str, list[str]]:
    """The capitalised spellings (a sentence's first word: "May", "A") whose
    card opens on what the word in lower case opens on, then on their own:
    capitalised -> its row. The lookup tries a word as written before its
    lower case and stops at the first it finds, so a capitalised spelling
    Wiktionary gives a name or a letter opened on that: Filipino's "May"
    (there is, has) on Mayo, the month; Portuguese's "A" on á, "wing", an
    old name of the letter; Ukrainian's "Мене" (me) on Maine; French's
    "Cette" (this) on the town Sète (polyglotic-hq 402, 413).

    Which comes first: where the treebanks use the word (in lower case) at
    least `kaikki.MIN_USES` times and the two first entries are in different
    parts of speech, the one they use it as more (a name is PROPN: Brazil
    stays Brasil; German's Zeit stays "time", but Gut, "property", gives
    way to gut, "good"); otherwise the better ranked where the lower case
    is a common word (`COMMON`) and the capitalised spelling isn't a name's
    own headword: Mayo's "May" gives way to may, but Ève stays Eve, not
    éwé (the Ewe language), Komodo the island, and Liège and Tournai
    (whose lower case is tourner's "I turned") the cities; nor a form of a
    name whose lower case is the same word's: Ukrainian's "Україні" (in
    Ukraine) had opened on україна, "a land", a noun Wiktionary keeps, ranked
    as Ukraine is, since wordfreq is in lower case - unless the lower case
    is itself one of the commonest words (`commonest`, `COMMONEST`):
    Ukrainian's "Того" opens on той ("that"), not Togo. `said`: entry
    ID -> its headword and its first meaning's part of speech. `spelled`:
    the language writes its nouns with a capital (German, `Draft.capitalised`),
    so only the treebanks decide - by rank, Eingriff (intervention) had
    opened on eingreifen, Güter (goods) on gut.
    Only a word with a capital and lower case after it, whose lower case
    finds something else first."""

    def row(word: str) -> list[str]:
        through = forms.get(lemmas[word], []) if word in lemmas else []
        return list(dict.fromkeys([*through, *forms.get(word, [])]))

    out = {}
    for word in {*forms, *lemmas}:
        lower = word.lower()
        if word == lower or not word[:1].isupper() or word[1:] != word[1:].lower():
            continue
        mine, theirs = row(word), row(lower)
        if not mine or not theirs or mine[0] == theirs[0]:
            continue
        counts = uses.get(lower, {}) if uses else {}
        pos_mine, pos_theirs = said[mine[0]][1], said[theirs[0]][1]
        if sum(counts.values()) >= kaikki.MIN_USES and pos_mine != pos_theirs:
            lower_first = kaikki.used_as(counts, {pos_theirs}) > kaikki.used_as(
                counts, {pos_mine}
            )
        elif spelled:
            lower_first = False
        else:
            best = min(rank[i] for i in theirs)
            name = said[mine[0]][1] == "name"
            named = name and (
                # Liège, Tournai: their own headword, unless the lower case is
                # one of the commonest words (Того: того, "of that")
                (said[mine[0]][0] == word and lower not in commonest)
                or said[mine[0]][0].lower() == said[theirs[0]][0].lower()
            )  # Україні: Україна's, whose lower case україна ("land") is a rare noun
            lower_first = (
                not named and best <= COMMON and best < min(rank[i] for i in mine)
            )
        if lower_first:
            out[word] = list(dict.fromkeys([*theirs, *mine]))
    return out


def through_capitals(
    forms: Mapping[str, list[str]],
    lemmas: Mapping[str, str],
    capitals: Mapping[str, list[str]],
) -> dict[str, list[str]]:
    """The words in lower case looked up through a capitalised word whose
    row `capitals_first` changes, each with a row of its own: what it
    showed before (that word's row, then its own). Ukrainian's "Того" opens
    on той ("that"), but "тоголезький" (Togolese) is still Togo's
    (polyglotic-hq 416). Not a capitalised form, which goes as its word
    goes: Czech's "Hlavou" opens on hlava (head), as "Hlava" does, not the
    surname."""
    return {
        form: list(dict.fromkeys([*forms.get(lemma, []), *forms.get(form, [])]))
        for form, lemma in lemmas.items()
        if lemma in capitals and form not in capitals and form == form.lower()
    }


@dataclass(frozen=True)
class Built:
    records: list[EntryRecord]
    forms: dict[str, list[str]]
    lemmas: dict[str, str]
    zh: dict[str, tuple[str, ...]]
    """Entry ID -> its Chinese meanings (none: it keeps its English)."""
    form_readings: dict[str, str]
    """Written form -> how it is said ("ру́ки, руки́"), for the forms a
    lookup shows as another word's (inflections, other spellings) that
    wordfreq has met."""
    stats: dict[str, object]
    zh_classes: dict[str, tuple[SenseClasses, ...]] = field(default_factory=dict)


def entry_record(entry: DraftEntry, entry_id: str, rank: int | None) -> EntryRecord:
    classes, prefixes = sense_classes.legacy_wikt(entry.meanings, entry.source_pos)
    return EntryRecord(
        entry_id=entry_id,
        headword=entry.headword,
        traditional="",
        reading=entry.reading,
        meanings=entry.meanings,
        frequency_rank=rank,
        levels=entry.levels,
        sense_classes=entry.sense_classes or classes,
        sense_prefixes=prefixes,
    )


def frequency_lists(
    pack: Pack, paths: Mapping[str, Path], draft: Draft
) -> frequency.Frequencies:
    """The pack's frequency lists (`Pack.frequency`), averaged: wordfreq's,
    one the reader counted (`Draft.counted`), or a list of counts."""
    lists = []
    for name in pack.frequency:
        if name == "wordfreq":
            shares = wordfreq_ranks.frequencies(paths[name], pack.language)
            lists.append(frequency.Frequencies(shares, hyphenated=False))
        elif name in draft.counted:
            lists.append(draft.counted[name])
        else:
            lists.append(frequency.counted(paths[name]))
    return frequency.mean(lists)


def assemble(
    pack: Pack, draft: Draft, registry: Registry, paths: Mapping[str, Path]
) -> Built:
    """IDs, ranks and the cut: entries with a frequency rank (the words a
    learner can meet), a level, or the source's own "common" mark."""
    freq = frequency_lists(pack, paths, draft)
    total = frequencies(draft, freq)
    rank_of = ranks(draft, total)
    kept_entries = [
        e
        for e in draft.entries
        if e.key in rank_of or e.levels or e.common or draft.keep_unranked
    ]
    kept = {e.key for e in kept_entries}
    ids = assign_ids(registry, kept)
    records = [entry_record(e, ids[e.key], rank_of.get(e.key)) for e in kept_entries]
    record_rank = {ids[k]: rank_of.get(k, 1 << 30) for k in kept}
    forms = {}
    for form, keys in draft.forms.items():
        found = [ids[k] for k in keys if k in kept]
        if found:
            # the commonest entry first; the source's order breaks ties
            forms[form] = sorted(found, key=lambda i: record_rank[i])
    # each word's own row: the word shown after a word shows only its own
    # entries, not those of the word shown after it in turn (407)
    own = {form: list(shown) for form, shown in forms.items()}
    lemmas, after = lemma_table(draft, kept, total, freq)
    for form, lemma in after.items():
        forms[form] = own[form] + [i for i in own.get(lemma, ()) if i not in own[form]]
    reached = set(lemmas)  # forms looked up through a lemma
    if draft.came_through:  # Wiktionary's: a key is word|pos|etymology
        pos_of = {ids[e.key]: (e.headword, e.key.split("|")[1]) for e in kept_entries}
        for form, shown in opened_as_used(draft, own, lemmas, pos_of).items():
            forms[form] = shown
            del lemmas[form]
        for form, shown in opened_through(draft, own, lemmas, pos_of).items():
            forms[form] = shown
            del lemmas[form]
        for form, shown in own_entries_only(draft, own, lemmas, after, pos_of).items():
            forms[form] = shown
            del lemmas[form]
    said = {r.entry_id: (r.headword, part_of_speech(r.meanings)) for r in records}
    commonest = frozenset(heapq.nlargest(COMMONEST, freq, key=freq.__getitem__))
    capitals = capitals_first(
        forms, lemmas, record_rank, said, draft.uses, bool(draft.capitalised), commonest
    )
    for form, shown in through_capitals(forms, lemmas, capitals).items():
        forms[form] = shown
        del lemmas[form]
    for form, shown in capitals.items():
        forms[form] = shown
        lemmas.pop(form, None)
    headwords = {r.headword for r in records}
    form_readings = {
        form: ", ".join(said)
        for form, said in sorted(draft.form_readings.items())
        if (form in reached or (form in forms and form not in headwords))
        and frequency_of(form, freq) > 0
    }
    with_zh = sum(1 for e in kept_entries if e.zh_meanings)
    stats: dict[str, object] = {
        "entries": len(records),
        "of source entries": len(draft.entries),
        "ranked": sum(1 for r in records if r.frequency_rank),
        "with a level": sum(1 for r in records if r.levels),
        "written forms": len(forms),
        "inflected forms": len(lemmas),
        "forms with their own reading": len(form_readings),
    }
    if "zh" in pack.meanings:
        share = 100 * with_zh / max(1, len(records))
        stats["with Chinese meanings"] = f"{with_zh} ({share:.1f} %)"
    zh = {ids[e.key]: e.zh_meanings for e in kept_entries}
    zh_classes = {ids[e.key]: e.zh_classes for e in kept_entries if e.zh_classes}
    return Built(records, forms, lemmas, zh, form_readings, stats, zh_classes)


def records_for(built: Built, gloss_language: str) -> list[EntryRecord]:
    if gloss_language != "zh":
        return built.records
    return [
        replace(
            record,
            meanings=translated,
            sense_classes=built.zh_classes.get(record.entry_id, ()),
            sense_prefixes=(),
        )
        if (translated := built.zh.get(record.entry_id))
        and translated != record.meanings
        else record
        for record in built.records
    ]


def info(pack: Pack, meanings: str, ranked: int) -> dict[str, str]:
    """The pack's `info`; `ranked`: how many entries have a rank."""
    return {
        "dictionary": pack.name,
        "language": pack.language,
        "tier": "basic",
        "meanings_language": meanings,
        "licence": "CC BY-SA 4.0",
        "sources": "; ".join(
            f"{s.name} {s.version} sha256:{s.sha256}" for s in pack.sources
        ),
        "frequency_source": "+".join(pack.frequency),
        "ranks": RANKS,
        "ranked_entries": str(ranked),
        "level_schemes": pack.level_schemes,
        "credits": f"{pack.name}.CREDITS.md, next to this file",
    }


def write_pack(
    pack: Pack, built: Built, out: Path, reviews: Path | None = None
) -> tuple[dict[str, Path], dict[str, dict[str, int]]]:
    """`<name>.sqlite` (English meanings) and, if the pack has Chinese
    (`Pack.meanings`), `<name>-zh.sqlite` (an entry the Chinese edition
    hasn't got keeps its English)."""
    paths = {}
    counts = {}
    for meanings in pack.meanings:
        records = records_for(built, meanings)
        path = out / (
            f"{pack.name}.sqlite" if meanings == "en" else f"{pack.name}-zh.sqlite"
        )
        final, provenance, verified = apply_reviews(
            records,
            reviews if pack.language == "yue" else None,
            path.stem,
            pack.language,
            meanings,
        )
        traditional = {}
        if pack.language == "ja" and meanings == "zh":
            converter = TraditionalChinese(read_table())
            for record, english in zip(final, built.records, strict=True):
                if record.meanings != english.meanings:
                    converted = tuple(
                        converter.convert(gloss) for gloss in record.meanings
                    )
                    if converted != record.meanings:
                        traditional[record.entry_id] = converted
        write_dictionary(
            path,
            {
                **info(pack, meanings, sum(1 for r in records if r.frequency_rank)),
                **provenance,
            },
            final,
            built.forms,
            lemmas=built.lemmas,
            form_readings=built.form_readings,
            with_sense_classes=True,
            traditional_glosses=traditional,
        )
        paths[meanings] = path
        counts[meanings] = sense_classes.coverage(final, verified)
    return paths, counts


def credits(pack: Pack) -> str:
    lines = [
        f"# {pack.title} dictionary pack - credits",
        "",
        (
            f"`{pack.name}.sqlite` and `{pack.name}-zh.sqlite` are plain SQLite files,"
            if "zh" in pack.meanings
            else f"`{pack.name}.sqlite` is a plain SQLite file,"
        ),
        "separate from the app: you may open, copy and reuse them under",
        f"**CC BY-SA 4.0** ({CC_BY_SA}).",
        f"Made from: {pack.about}. Changes: converted to SQLite; entries given IDs;",
        'senses that only say "form of" turned into links to their lemma;',
        "rare and old senses put after a word's others"
        + (
            ", and a word's entries in the order its commonest part of speech "
            "first, by the treebanks below."
            if any(s.name.startswith("ud-") for s in pack.sources)
            else "."
        ),
        "",
    ]
    if pack.language == "ja" and "zh" in pack.meanings:
        lines += [
            "The optional Chinese meanings riders contain machine-drafted glosses",
            "from [Tomoshi (Y1Z)]",
            "(https://github.com/tomoshi-app/tomoshi-dict-data/releases/tag/v2026-11-16),",
            f"licensed [CC BY-SA 4.0]({CC_BY_SA}). They translate",
            "[JMdict](https://www.edrdg.org/jmdict/j_jmdict.html), the property of",
            "the Electronic Dictionary Research and Development Group (EDRDG),",
            f"also licensed [CC BY-SA 4.0]({CC_BY_SA}).",
            "",
            "The Chinese edition includes Traditional display forms derived with Polyglotic's",
            "[OpenCC](https://github.com/BYVoid/OpenCC) table (Apache-2.0), with Taiwan forms",
            "from [CC-CEDICT](https://cc-cedict.org/wiki/) (CC BY-SA 4.0).",
            "",
        ]
    for source in pack.sources:
        lines += [
            f"## {source.title}",
            "",
            f"- Used for: {source.used_for}",
            f"- Version: {source.version}",
            f"- From: {source.url}",
            f"- SHA-256: `{source.sha256}`",
            f"- Home: {source.homepage}",
            f"- Licence: {source.licence}",
            "",
        ]
        if source.licence == "MIT":
            lines += [source.notice, "", MIT, ""]
        elif source.licence == "CC BY":
            lines += [f"{source.notice}.", ""]
        elif source.licence in OTHER_CC:
            licence = source.licence
            lines += [
                f"{source.notice}. Licensed under {licence}: {OTHER_CC[licence]}",
                "",
            ]
        elif source.licence == CC0:
            lines += [
                (
                    f"{source.notice}. Only word counts made from it are in the "
                    "pack, as frequency ranks - none of its text. Dedicated to "
                    "the public domain: "
                    "https://creativecommons.org/publicdomain/zero/1.0/"
                ),
                "",
            ]
        elif source.licence == COUNTS_ONLY:
            lines += [
                (
                    f"{source.notice}. Only word counts made from it are in the "
                    "pack, as frequency ranks - none of its text. Its publisher "
                    "states no licence and asks for a link to "
                    "http://www.opensubtitles.org/ and a citation."
                ),
                "",
            ]
        else:
            lines += [f"{source.notice}. Licensed under CC BY-SA 4.0: {CC_BY_SA}", ""]
    return "\n".join(lines)


def build(
    pack: Pack, paths: Mapping[str, Path], out: Path, reviews: Path | None = None
) -> dict[str, object]:
    registry_path = REGISTRY / f"{pack.name}.tsv"
    registry = Registry.load(registry_path, pack.name)
    before = (dict(registry.ids), dict(registry.merged))
    draft = pack.read(paths)
    built = assemble(pack, draft, registry, paths)
    files, counts = write_pack(pack, built, out, reviews)
    (out / f"{pack.name}.CREDITS.md").write_text(
        credits(pack), encoding="utf-8", newline="\n"
    )
    if (registry.ids, registry.merged) != before:
        registry.save(registry_path)
        print(f"  ! {registry_path.name} changed (a hash was salted): commit it")
    stats = dict(built.stats)
    stats["sense classes by gloss language"] = counts
    probed = coverage.probe(files["en"], pack.language)
    added = {"coverage": f"{probed.share:.4f}"}
    if pack.language in coverage.SCRIPTS:
        running = coverage.probe_running_words(
            files["en"], pack.language, paths["wordfreq"]
        )
        added["running_words"] = f"{running.share:.4f}"
        stats["running words"] = str(running)
    for path in files.values():
        add_info(path, added)
    stats["coverage"] = str(probed)
    stats["passes the basic floor"] = probed.share >= coverage.FLOORS["basic"]
    counted = draft.counted.get(coverage.TOP_FROM_COUNTED.get(pack.language, ""))
    if pack.language in coverage.SCRIPTS or counted is not None:
        top = (
            coverage.probe_top_words_of(files["en"], pack.language, counted)
            if counted is not None
            else coverage.probe_top_words(files["en"], pack.language, paths["wordfreq"])
        )
        stats["top words"] = str(top)
        stats["finds its commonest words"] = not top.missing
        if draft.written:  # how the top running words open, against their use
            ranked = (
                counted
                if counted is not None
                else wordfreq_ranks.frequencies(paths["wordfreq"], pack.language)
            )
            opened = coverage.probe_opened_as_used(
                files["en"], pack.language, ranked, draft.written
            )
            stats["top words opened as used"] = not opened.mismatched
            if opened.mismatched:
                stats["top words opened otherwise"] = str(opened)
    junk = rank_check.problems(built.records, pack.language)
    stats["ranks pass the junk check"] = not junk
    if junk:
        stats["rank problems"] = "; ".join(junk)
    for path in files.values():
        stats[f"{path.name}"] = f"{path.stat().st_size / 1e6:.1f} MB"
    return stats


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("languages", nargs="*", default=list(PACKS))
    parser.add_argument(
        "--sources", type=Path, default=REPO / "build" / "dictionary-sources"
    )
    parser.add_argument(
        "--out", type=Path, default=REPO / "build" / "dictionaries" / "packs"
    )
    parser.add_argument(
        "--class-reviews",
        type=Path,
        help="folder of reviewed 746 drafts and frozen packs",
    )
    args = parser.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    args.out.mkdir(parents=True, exist_ok=True)
    failed = 0
    for language in args.languages:
        pack = PACKS[language]
        paths = {s.name: fetch(s, args.sources) for s in pack.sources}
        started = time.perf_counter()
        stats = build(pack, paths, args.out, args.class_reviews)
        print(
            f"{pack.name} ({language}), format {FORMAT}: "
            f"{time.perf_counter() - started:.0f}s"
        )
        for key, value in stats.items():
            print(f"  {key}: {value}")
        failed += not (
            stats["passes the basic floor"]
            and stats["ranks pass the junk check"]
            and stats.get("finds its commonest words", True)
        )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
