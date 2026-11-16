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
import sys
import time
from collections import defaultdict
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field, replace
from functools import partial
from pathlib import Path

from polyglotic_desktop.adapters.sqlite_dictionary import (
    FORMAT,
    RANKS,
    add_info,
    write_dictionary,
)
from polyglotic_desktop.core.lexicon import arabic, english
from polyglotic_desktop.core.lexicon.vietnamese import key as word_key
from polyglotic_desktop.ports.dictionary import EntryRecord
from tools.dictionaries import (
    coverage,
    frequency,
    jmdict,
    kaikki,
    rank_check,
    russian,
    spanish,
    thai,
    treebanks,
    vietnamese,
    wordfreq_ranks,
)
from tools.dictionaries.entry_ids import Registry, assign_ids
from tools.dictionaries.sources import (
    CC0,
    COMMONVOICE_FA,
    COMMONVOICE_TH,
    COUNTS_ONLY,
    FREQUENCYWORDS_RU,
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
    WORDFREQ,
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
    keep giving each lemma the whole until their ranks are measured again."""
    keep_unranked: bool = False
    """Every entry is kept, ranked or not: a language whose word split is
    by the pack's own words (Thai) needs them all, or a word the pack
    lacks is cut into shorter ones it has - กาแล็กซี (galaxy), never said
    in Common Voice, read as กา (crow) + แล็ก + ซี (polyglotic-hq 389)."""
    capitalised: dict[str, frozenset[str]] = field(default_factory=dict)
    """Entry keys of nouns whose capital is their spelling (German's), with
    their own declension's forms: such a noun takes its lower-case
    frequency where its forms show it is the word in use (`DECLINED`)."""


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


def read_spanish(paths: Mapping[str, Path]) -> Draft:
    words = kaikki.read_language(
        kaikki.lines(paths["kaikki-es"], "es"), uses=treebanks.uses_for("es", paths)
    )
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
    return draft_of(words, zh_by_word)


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


AS_WRITTEN = Spelling()
"""Wiktionary read as it is: captions write what it writes."""
FILIPINO = Spelling(linked=True)
"""Filipino: its linker written onto a word (`linked_forms`)."""
ROMANIZED = Spelling(reading=kaikki.romanization)
"""A language in another script: its reading is Wiktionary's romanization
("laṛkā"), which a learner reads before IPA."""
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
    objects = (
        obj
        for obj in kaikki.lines(paths[f"kaikki-{language}"], language)
        if not russian.is_letter(obj)
    )
    uses = treebanks.uses_for(language, paths, spelling.written)
    words = kaikki.read_language(
        objects, spelling.reading, uses=uses, derived=spelling.derived
    )
    if spelling.written:
        words = rewritten(words, spelling.written)
    if spelling.also:
        words = also_written(words, spelling.also)
    if spelling.linked:
        words.forms.update(linked_forms(words))
    draft = draft_of(words)
    draft.split_shared_forms = True
    if spelling.nouns_capitalised:
        draft.capitalised = capitalised_nouns(words)
    if sentences:  # a source of sentences: its words counted by the app's split
        draft.counted[sentences] = frequency.sentences_counted(
            paths[sentences], english.words
        )
    return draft


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
    return words


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
    forms come from Malay's tables first."""
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
        malay.entries.append(replace(e, meanings=tuple(m + SHARED for m in e.meanings)))
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

    words = kaikki.read_language(
        objects(), reading=russian.stressed, uses=treebanks.uses_for("ru", paths)
    )
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
                zh_meanings=chinese_for(
                    e.word, e.pos, not forms[e.word], zh_by_word.get(e.word, {})
                ),
            )
        )
        forms[e.word].append(e.key)
    return Draft(
        entries,
        dict(forms),
        {f: set(ls) for f, ls in words.forms.items()},
        words.imperative,
        words.verb_forms,
        dict(form_readings),
        lemma_first=words.lemma_first,
    )


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
    0176): กับ is "with" before "trap"."""
    words = kaikki.read_language(
        thai.words(kaikki.lines(paths["kaikki-th"], "th")),
        kaikki.romanization,
        uses=treebanks.uses_for("th", paths),
        short_forms=True,
    )
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
    for kanji in word.kanji:
        if kanji in zh:
            return tuple(zh[kanji][: jmdict.MAX_MEANINGS])
    for kana in word.kana:
        if kana in zh and kana_owner.get(kana) == word.seq:
            return tuple(zh[kana][: jmdict.MAX_MEANINGS])
    return ()


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
    for word_pos, glosses in zh.items():
        word = word_pos.split("|")[0]
        zh_by_word[word] += [g for g in glosses if g not in zh_by_word[word]]
    owners = kana_owners(words)
    levels = jlpt_levels(paths["jlpt"])
    entries = []
    forms: dict[str, list[str]] = defaultdict(list)
    for w in words:
        # a word listed in kana alone is the entry that owns the kana
        pairs = [(k, kana) for k in w.kanji for kana in w.kana]
        if w.headword in w.kana and usual_in_kana(w, owners):
            pairs.append((w.headword, w.headword))
        level = min((levels[p] for p in pairs if p in levels), default=None)
        entries.append(
            DraftEntry(
                key=w.seq,
                headword=w.headword,
                reading=w.reading,
                meanings=w.meanings,
                ranked_by=ranked_by(w, owners),
                zh_meanings=chinese_for_japanese(w, zh_by_word, owners),
                levels=(("jlpt", level),) if level else (),
                common=w.common,
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
    "hi": wiktionary_pack("hi", "Hindi", KAIKKI_HI, ROMANIZED),
    "pl": wiktionary_pack("pl", "Polish", KAIKKI_PL),
    "tr": wiktionary_pack("tr", "Turkish", KAIKKI_TR, TURKISH),
    "ms": Pack(
        language="ms",
        name="wiktms",
        title="Malay",
        sources=(KAIKKI_MS, KAIKKI_ID, WORDFREQ),
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
    "ro": wiktionary_pack("ro", "Romanian", KAIKKI_RO),
    "el": wiktionary_pack("el", "Greek", KAIKKI_EL),
    "tl": wiktionary_pack("tl", "Filipino", KAIKKI_TL, FILIPINO),
    "mk": wiktionary_pack("mk", "Macedonian", KAIKKI_MK),
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
}


# -- pages the source hasn't got --------------------------------------------------


@dataclass(frozen=True)
class Supplied:
    """An entry written here for a word whose Wiktionary page kaikki's
    extracts haven't got: its meanings as the page gives them, in short."""

    word: str
    pos: str
    meanings: tuple[str, ...]
    ipa: str


MISSING_PAGES: dict[str, tuple[Supplied, ...]] = {
    "pl": (Supplied("i", "conj", ("and", "also, too; even"), "/i/"),),
    "it": (
        Supplied(
            "i", "article", ("the (masculine plural, before most consonants)",), "/i/"
        ),
    ),
    "cs": (Supplied("i", "conj", ("and; as well as", "even; also"), "/ɪ/"),),
    "hr": (Supplied("i", "conj", ("and", "also, too; even"), "/i/"),),
    "ca": (Supplied("i", "conj", ("and",), "/i/"),),
    "da": (Supplied("i", "prep", ("in", "into; at; for (a time)"), "/i/"),),
    "sv": (Supplied("i", "prep", ("in", "into; at; for (a time)"), "/iː/"),),
    "nb": (Supplied("i", "prep", ("in", "into; at; for (a time)"), "/iː/"),),
}
"""Per language, words English Wiktionary has whose pages are missing from
kaikki's extracts of 2026-10-30: the page "i" is in none of them (kaikki's
own site has no "i" for Polish, Czech, Danish or Spanish), so Polish's "i"
("and", 2.7 % of its running words) had no entry (polyglotic-hq 380, 390).
An entry takes kaikki's key (`word|pos|`), and steps aside once the
source has the word: its ID is then the source's own."""


def supplied(draft: Draft, language: str) -> Draft:
    """`draft` with its language's `MISSING_PAGES` entries it hasn't got."""
    for s in MISSING_PAGES.get(language, ()):
        if s.word in draft.forms:
            continue
        key = f"{s.word}|{s.pos}|"
        draft.entries.append(
            DraftEntry(
                key=key,
                headword=s.word,
                reading=s.ipa,
                meanings=tuple(f"({s.pos}) {m}" for m in s.meanings),
                ranked_by=(s.word,),
            )
        )
        draft.forms[s.word] = [key]
    return draft


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
    ("Земли" is земли). A name's other forms count: Polska (Poland), whose
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
    declined = {
        key
        for key, forms in draft.capitalised.items()
        if in_use(headword[key], forms, freq)
    }
    declined_forms = {f for key in declined for f in draft.capitalised[key]}
    by_headword: dict[str, list[str]] = defaultdict(list)
    lower_case = {
        e.headword for e in draft.entries if e.headword == e.headword.lower()
    } | {f for f in draft.inflections if f == f.lower()}
    look_alike = set()
    gives_way = set()
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
    alone = {
        word: max(total[k] for k in keys) for word, keys in by_headword.items()
    }  # each word's own frequency, before its forms'
    for form, lemmas in draft.inflections.items():
        look_alike_form = (
            form != form.lower()
            and form.lower() in lower_case
            and form not in declined_forms  # Menschen; not "So" (Sonntag's)
        )
        own = form in by_headword and form not in names
        f = 0.0 if own or look_alike_form else frequency_of(form, freq)
        if form in names and any(lemma not in names for lemma in lemmas):
            gives_way.update(by_headword[form])  # the name gives way
        if f:
            for lemma, share in shares(draft, lemmas, by_headword, alone).items():
                for key in by_headword[lemma]:
                    total[key] += f * share
    for key in gives_way | {k for k in look_alike if headword[k] not in names}:
        total[key] = 0.0  # only a name keeps its own forms' (Polska's Polsce)
    for e in draft.entries:
        if no_word(e.headword):  # "4x4" had taken quatre-quatre's (380)
            total[e.key] = 0.0
    return total


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
        if not own or (
            (form, best) in draft.verb_forms
            and weight(best) >= freq.get(form.lower(), 0.0)
        ):
            out[form] = best
        elif named:  # "una" starts as uno's: uno, not the commoner un
            out[form] = max(named, key=weight)
        else:
            after[form] = best
    return out, after


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
    records = [
        EntryRecord(
            entry_id=ids[e.key],
            headword=e.headword,
            traditional="",
            reading=e.reading,
            meanings=e.meanings,
            frequency_rank=rank_of.get(e.key),
            levels=e.levels,
        )
        for e in kept_entries
    ]
    record_rank = {ids[k]: rank_of.get(k, 1 << 30) for k in kept}
    forms = {}
    for form, keys in draft.forms.items():
        found = [ids[k] for k in keys if k in kept]
        if found:
            # the commonest entry first; the source's order breaks ties
            forms[form] = sorted(found, key=lambda i: record_rank[i])
    lemmas, after = lemma_table(draft, kept, total, freq)
    for form, lemma in after.items():
        then = [i for i in forms.get(lemma, ()) if i not in forms[form]]
        forms[form] = forms[form] + then
    headwords = {r.headword for r in records}
    form_readings = {
        form: ", ".join(said)
        for form, said in sorted(draft.form_readings.items())
        if (form in lemmas or (form in forms and form not in headwords))
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
    return Built(records, forms, lemmas, zh, form_readings, stats)


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


def write_pack(pack: Pack, built: Built, out: Path) -> dict[str, Path]:
    """`<name>.sqlite` (English meanings) and, if the pack has Chinese
    (`Pack.meanings`), `<name>-zh.sqlite` (an entry the Chinese edition
    hasn't got keeps its English)."""
    paths = {}
    for meanings in pack.meanings:
        records = built.records
        if meanings == "zh":
            records = [
                replace(r, meanings=built.zh[r.entry_id] or r.meanings) for r in records
            ]
        path = out / (
            f"{pack.name}.sqlite" if meanings == "en" else f"{pack.name}-zh.sqlite"
        )
        write_dictionary(
            path,
            info(pack, meanings, sum(1 for r in records if r.frequency_rank)),
            records,
            built.forms,
            lemmas=built.lemmas,
            form_readings=built.form_readings,
        )
        paths[meanings] = path
    return paths


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
    if MISSING_PAGES.get(pack.language):
        words = ", ".join(f'"{s.word}"' for s in MISSING_PAGES[pack.language])
        lines += [
            (
                f"Written here from Wiktionary's own pages, which kaikki's "
                f"extracts lack: the entries for {words}."
            ),
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


def build(pack: Pack, paths: Mapping[str, Path], out: Path) -> dict[str, object]:
    registry_path = REGISTRY / f"{pack.name}.tsv"
    registry = Registry.load(registry_path, pack.name)
    before = (dict(registry.ids), dict(registry.merged))
    draft = supplied(pack.read(paths), pack.language)
    built = assemble(pack, draft, registry, paths)
    files = write_pack(pack, built, out)
    (out / f"{pack.name}.CREDITS.md").write_text(
        credits(pack), encoding="utf-8", newline="\n"
    )
    if (registry.ids, registry.merged) != before:
        registry.save(registry_path)
        print(f"  ! {registry_path.name} changed (a hash was salted): commit it")
    stats = dict(built.stats)
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
    if pack.language in coverage.SCRIPTS:
        top = coverage.probe_top_words(files["en"], pack.language, paths["wordfreq"])
        stats["top words"] = str(top)
        stats["finds its commonest words"] = not top.missing
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
    args = parser.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    args.out.mkdir(parents=True, exist_ok=True)
    failed = 0
    for language in args.languages:
        pack = PACKS[language]
        paths = {s.name: fetch(s, args.sources) for s in pack.sources}
        started = time.perf_counter()
        stats = build(pack, paths, args.out)
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
