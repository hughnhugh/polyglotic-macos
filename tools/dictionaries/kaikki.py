"""Reading Wiktionary as kaikki.org extracts it (wiktextract JSONL).

One JSON object per line: a word in one language, one part of speech and
etymology - `word`, `pos`, `etymology_number`, `senses` (each with
`glosses`, `tags`, and `form_of` when the sense is "inflection of X"),
`forms` (a lemma's inflection table: `form` with `tags`) and `sounds`
(`ipa`). The English edition glosses every language's words in English;
the Chinese edition glosses them in Chinese.

An entry's reading is its first IPA, unless the language says otherwise
(Russian: its headword with the stress marked, `russian.stressed`).

A line is split here into the two things a dictionary needs:
- an **entry**, from its senses of its own ("casa": house);
- **form relations**, from its "form of" senses ("casas": plural of casa)
  and from a lemma's inflection table (hablar: hablo, hablé...). Each
  says "this written form is an inflection of that lemma".

Glosses are data, never markup: they are kept as text, one per meaning.
"""

from __future__ import annotations

import gzip
import json
import re
from collections import defaultdict
from collections.abc import Callable, Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path

# Tags on a form-of sense or a form that say it is no word of its own
_FORM_OF_TAGS = frozenset({"form-of", "alt-of"})
# a short way of writing a word, not a form of it: wordfreq can't tell "D"
# (dame) or "a" (German's Ar) from the letter, so they took its frequency
_SHORT_FOR = frozenset({"abbreviation", "initialism", "acronym", "symbol"})
# ...but kaikki tags contractions and elisions "abbreviation" too: "do" (de
# + o), "au" (à + le), "l'" are words
_SHORTENED = frozenset({"contraction", "apocopic", "clipping", "elided"})
# Tags on a lemma's `forms` that aren't inflections: table headings, the
# template's name, spellings in another script, the lemma itself
_NOT_A_FORM = frozenset(
    {
        "table-tags",
        "inflection-template",
        "class",
        "romanization",
        "transliteration",
        "canonical",
        "infinitive",
        "error-unknown-tag",
    }
)
# "decir combined with indirect object me and direct object lo" -> decir
_COMBINED = re.compile(r"\s+combined with\b.*$")
# what kaikki writes after a form-of target's word: Russian's aspect ("стать
# pf"), a gender ("uovo m", "grande m or f by sense")
_ANNOTATION = re.compile(r"(?:\s+(?:pf|impf|m|f|n|mf|pl|or|by sense))+$")
_AND = re.compile(r"\s+and(?:\s+|$)")
_PRONOUN = re.compile(r"\b(me|te|se|nos|os|lo|la|le|los|las|les)\b")
_REFLEXIVE_TAGS = frozenset({"reflexive", "pronominal"})
# a derived word's gloss that says what it means: "causative of azalmak:
# to decrease", "verbal noun of tartışmak; discussion", "diminutive of söz
# (“speech”)" - not just "causative of cezalanmak"
_SAYS_WHAT = re.compile(r"[:;]\s*\S|\(“")
DERIVATIONS = frozenset(
    {"causative", "passive", "reciprocal", "reflexive", "noun-from-verb", "diminutive"}
)
"""Tags of a form-of sense that make a word of its own, not an inflection
(`read_language`'s `derived`)."""

# a gloss's trailing grammar note in the Chinese edition: [接 con ...]
_NOTE = re.compile(r"\s*\[[^\]]*\]\s*$")
SHORT = 2
"""A form this short in an inflection table never counts: its own page
says what it is a form of (Spanish's "va", "sé"). A broken template
listed "ii" and "i" as forms of Romanian's vârtejire (whirlwind), its 47th
word; some nouns list bare endings ("ei", "le"); German's Rallye lists
"n" (polyglotic-hq 387, 390)."""
MAX_MEANINGS = 8  # per entry: the card shows three; the rest is size

RARE = frozenset(
    {
        "obsolete",
        "archaic",
        "dated",
        "historical",
        "dialectal",
        "uncommon",
        "poetic",
        "nonstandard",
        "proscribed",
    }
)
"""A sense's tags that say a learner will seldom meet it: such a sense
comes after its entry's others, and an entry of only such senses after its
word's other entries (polyglotic-hq 393). Not "rare": kaikki gives a
sense its construction's notes, so German's denken "to think" was "rare"
for its rare transitive use."""
NO_WORD_POS = frozenset(
    {
        "character",
        "symbol",
        "letter",
        "prefix",
        "suffix",
        "infix",
        "interfix",
        "circumfix",
        "affix",
    }
)
"""Parts of speech that are no word of a caption: a letter, an affix."""
_LETTER = re.compile(
    r"\bletter\b.*\b(?:alphabet|script)\b|\bname of the\b.*\bletter\b"
    r"|\b(?:Greek|Latin|Cyrillic|Hebrew|Arabic|Thai)\b letter\b",
    re.IGNORECASE,
)
"""A letter's gloss: "The fifth letter of the Spanish alphabet", "The name
of the Latin script letter D/d.", "mu; the Greek letter Μ, μ" (Spanish's
mi, "my")."""
UD_POS = {
    "noun": ("NOUN",),
    "verb": ("VERB", "AUX"),
    "adj": ("ADJ",),
    "adv": ("ADV",),
    "prep": ("ADP",),
    "postp": ("ADP",),
    "conj": ("CCONJ", "SCONJ"),
    "pron": ("PRON",),
    "det": ("DET",),
    "article": ("DET",),
    "num": ("NUM",),
    "particle": ("PART", "INTJ"),
    "intj": ("INTJ",),
    "name": ("PROPN",),
}
"""Wiktionary's parts of speech as Universal Dependencies tags them. A
classifier has no tag of its own (Thai's treebanks call it a noun), so it
takes no share."""
LEMMA_FIRST = 1
"""The most everyday meanings a form may have of its own for its lemma to
come first (`Language.lemma_first`). At 2, Spanish's "chica" (girl, maid)
and "roja" showed chico and rojo first (polyglotic-hq 393)."""
LEAD = 1.5
"""A part of speech comes first only if the treebanks use the word so at
least this many times as often as Wiktionary's first entry's (`in_order`):
Spanish's mañana is a noun (the morning) about as often as an adverb
(tomorrow), so Wiktionary's "tomorrow" stays first; Thai's คุณ is "you"
(17 uses) more than "attribute" (9). At 2, คุณ, German's genau and
tatsächlich kept their adjective first; at 1.5 nothing measured got worse
(polyglotic-hq 393)."""
MIN_SHARE = 0.25
"""...and in at least this share of the word's uses."""
NAME = 2
"""A name's `standing`."""
MIN_USES = 5
"""A word the treebanks use fewer times than this keeps Wiktionary's order
of parts of speech."""

Uses = Mapping[str, Mapping[str, int]]
"""Word form (lower case) -> how often treebanks use it as each part of
speech (`treebanks.uses`)."""


@dataclass(frozen=True)
class WiktEntry:
    """A word's own meanings in one part of speech and etymology. `key` is
    `word|pos|etymology number` (kaikki has no IDs; decision 0007 hashes
    this key)."""

    key: str
    word: str
    pos: str
    meanings: tuple[str, ...]
    reading: str = ""
    """How it's said, as the pack shows it: IPA ("/saˈbeɾ/"), or the
    language's own reading (`read_language`'s `reading`)."""
    forms: frozenset[str] = frozenset()
    """Its own inflection table's forms ("Menschen" for Mensch)."""
    standing: int = 0
    """Where it goes among its word's entries, before parts of speech are
    weighed (`in_order`): 0 a word, 1 only rare senses (`RARE`), 2 a name
    (in a script with capitals: `cased`), 3 no word (a letter, an affix: `NO_WORD_POS`)."""


@dataclass
class Language:
    """What one language's lines give: entries, and which lemmas each
    written form is an inflection of."""

    entries: list[WiktEntry] = field(default_factory=list)
    forms: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    """Written form -> the lemmas it is an inflection of."""
    imperative: set[tuple[str, str]] = field(default_factory=set)
    """(form, lemma) pairs only ever given as an imperative ("sé" is
    saber's "I know" but only ser's "be!") - rarer in speech than the
    same form's other uses."""
    verb_forms: set[tuple[str, str]] = field(default_factory=set)
    """(form, lemma) pairs where the form is a verb's inflection ("era" of
    ser) - not a noun's or adjective's form or another spelling ("pibe"
    is listed under piba, "güey" is a spelling of buey)."""
    combined: list[Combined] = field(default_factory=list)
    lemma_first: dict[str, frozenset[str]] = field(default_factory=dict)
    """Form -> the lemmas its page starts with it as a form of (its first
    entry's first sense), where that lemma's card should come first. Spanish's "su" is "apocopic form of
    suyo" before "about, approximately"; "una" is first "feminine of uno",
    "mi" "apocopic form of mío", before a pronoun, a note's name - so the
    lookup shows the lemma first (`packs.lemma_table`; polyglotic-hq 393).
    Not where the form is a word of its own (`lemma_first`)."""
    """Forms with pronouns attached ("levántate": levantar with te)."""
    reflexive: dict[str, list[str]] = field(default_factory=dict)
    """Entry key -> its senses marked reflexive or pronominal ("to get up",
    under levantar), which a language's rules may make an entry of their
    own."""


@dataclass(frozen=True)
class Combined:
    """A verb form with pronouns attached, as a form-of sense says it:
    "levántate" is levantar's second-person singular imperative "combined
    with te". `pronouns` in the order given; `tags` the sense's."""

    form: str
    lemma: str
    pronouns: tuple[str, ...]
    tags: frozenset[str]


def lines(path: Path, lang_code: str) -> Iterator[dict[str, object]]:
    """The objects for one language (`lang_code`, e.g. "es") in a kaikki
    file, gzipped or not."""
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as f:
        yield from lines_of(f, lang_code)


def lines_of(text: Iterable[str], lang_code: str) -> Iterator[dict[str, object]]:
    """The objects for one language in lines of JSON. Lines that aren't
    JSON objects are skipped (the extracts carry a few)."""
    needle = f'"lang_code": "{lang_code}"'
    for line in text:
        if needle not in line:  # cheap filter before parsing
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and obj.get("lang_code") == lang_code:
            yield obj


def _strs(value: object) -> list[str]:
    return [v for v in value if isinstance(v, str)] if isinstance(value, list) else []


def _dicts(value: object) -> list[dict[str, object]]:
    return [v for v in value if isinstance(v, dict)] if isinstance(value, list) else []


def lemma_of(form_of: str) -> str:
    """The lemma a form-of target names: "decir combined with indirect
    object me and direct object lo" -> "decir"."""
    return _COMBINED.sub("", form_of).strip()


def lemmas_of(form_of: str, two: bool = True) -> list[str]:
    """The lemmas a form-of target names, without what kaikki writes after
    them: "стать pf" -> стать; "uovo m" -> uovo; and, with `two`, "fondare
    and fondere" (a form of both) -> fondare, fondere; "avere and" ->
    avere. A phrase stays one ("di la", "por favor"). Without this a
    target with an aspect or a gender looked like a phrase, so its form
    became a word of its own: Russian's "стали" was "plural past
    indicative of стать pf", its 683rd word (polyglotic-hq 390)."""
    lemma = _ANNOTATION.sub("", lemma_of(form_of))
    pieces = [p for p in _AND.split(lemma) if p] if two else [lemma]
    if pieces != [lemma] and all(" " not in p for p in pieces):
        return pieces
    return [lemma] if lemma else []


TWO_LEMMAS = frozenset({"verb", "noun", "adj"})
"""The parts of speech whose form-of target "X and Y" is a form of both
(Italian's fonderò, of fondare and fondere). A small word's is what it
means: Spanish's pronoun "lo", "accusative of él and usted"; its
contraction "col", "of con and el" (polyglotic-hq 390)."""


def first_ipa(obj: Mapping[str, object]) -> str:
    """The object's first IPA transcription ("/saˈbeɾ/"), or ""."""
    return next(
        (
            str(s["ipa"])
            for s in _dicts(obj.get("sounds"))
            if isinstance(s.get("ipa"), str)
        ),
        "",
    )


def romanization(obj: Mapping[str, object]) -> str:
    """The object's romanization as Wiktionary gives it ("kitāb", "laṛkā"),
    else its first IPA: a learner of a language in another script reads the
    Latin letters first (polyglotic-hq 380)."""
    return next(
        (
            str(f["form"])
            for f in _dicts(obj.get("forms"))
            if "romanization" in _strs(f.get("tags")) and isinstance(f.get("form"), str)
        ),
        first_ipa(obj),
    )


def read_language(
    objects: Iterable[dict[str, object]],
    reading: Callable[[Mapping[str, object]], str] = first_ipa,
    *,
    spaced_words: bool = False,
    uses: Uses | None = None,
    derived: frozenset[str] = frozenset(),
    short_forms: bool = False,
) -> Language:
    """Entries and form relations from one language's objects (`lines`),
    each entry's reading by `reading` (its first IPA unless said).
    `spaced_words`: a headword or form with spaces in it is a word, not a
    phrase - Vietnamese writes every syllable apart ("học sinh").
    `derived`: tags of form-of senses that are a word of their own when
    the gloss says what it means (`DERIVATIONS`; Turkish's "araştırmak:
    causative of araşmak: to research" is no form of araşmak, "to call
    each other", which its lookup had shown: polyglotic-hq 388) - a
    meaning, not a form relation.
    `short_forms`: a table form of `SHORT` letters or fewer counts - in
    Thai's script two letters are a word (ไท, an older spelling of ไทย),
    and its pack cuts lone letters itself (`thai.caption_word`;
    polyglotic-hq 389, 394).

    A card shows a word's entries and meanings in the order given here, so
    the commonest comes first (polyglotic-hq 393): an entry's rare senses
    after its others; a word's entries by `in_order`, its commonest part of
    speech first where `uses` (treebank counts) say which."""
    out = Language()
    seen: dict[str, int] = defaultdict(int)
    begun: set[str] = set()  # words whose first object has been read
    starts_as_form: dict[str, tuple[frozenset[str], str, frozenset[str]]] = {}
    # ...and it starts with a form-of: (its lemmas, its part of speech, tags)
    form_pos: dict[str, set[str]] = defaultdict(set)  # parts of speech of forms
    moods: dict[tuple[str, str], set[bool]] = defaultdict(set)  # imperative?
    for obj in objects:
        word = obj.get("word")
        if not isinstance(word, str) or not word.strip():
            continue
        if " " in word.strip() and not spaced_words:
            continue  # phrases aren't looked up from a caption's words
        pos = str(obj.get("pos") or "")
        own: list[str] = []
        reflexive: list[str] = []
        rare: set[str] = set()  # glosses only ever given rare senses' tags
        common: set[str] = set()
        no_word = True  # every own sense a letter's or an affix's
        senses = _dicts(obj.get("senses"))
        first_object = bool(senses) and word not in begun
        if senses:
            begun.add(word)
        for n, sense in enumerate(senses):
            targets = [
                lemma
                for t in _dicts(sense.get("form_of")) + _dicts(sense.get("alt_of"))
                for lemma in lemmas_of(str(t.get("word") or ""), pos in TWO_LEMMAS)
            ]
            tags = set(_strs(sense.get("tags")))
            if targets and not spaced_words and all(" " in t for t in targets):
                targets = []  # "della": "contraction of di la" - a meaning
                tags -= _FORM_OF_TAGS
            if tags & derived and _SAYS_WHAT.search(
                " ".join(_strs(sense.get("glosses")))
            ):
                targets = []  # "causative of azalmak: to decrease" - a meaning
                tags -= _FORM_OF_TAGS
            if (
                "alt-of" in tags
                and tags & _SHORT_FOR
                and not tags & _SHORTENED
                and len(word) <= SHORT
            ):
                continue  # "D", abbreviation of dame: neither a form nor a meaning
            if first_object and n == 0 and targets:
                said = " ".join(_strs(sense.get("glosses")))
                equivalent = {"equivalent"} if _EQUIVALENT.match(said) else set()
                starts_as_form[word] = (
                    frozenset(targets),
                    pos,
                    frozenset(tags | equivalent),
                )
            if targets:
                form_pos[word].add(pos)
            if targets or _FORM_OF_TAGS & tags:
                # "... of levantar combined with te": in the target, or the gloss
                said = " ".join(_strs(sense.get("glosses")))
                for target in _dicts(sense.get("form_of")):
                    named = str(target.get("word") or "")
                    combined = named if " combined with " in named else said
                    if " combined with " in combined and pos == "verb":
                        attached = combined.split(" combined with ", 1)[1]
                        out.combined.append(
                            Combined(
                                word,
                                lemma_of(named),
                                tuple(_PRONOUN.findall(attached)),
                                frozenset(tags),
                            )
                        )
                for lemma in targets:
                    if lemma and lemma != word:
                        out.forms[word].add(lemma)
                        if pos == "verb" and "alt-of" not in tags:
                            out.verb_forms.add((word, lemma))
                        if tags - _FORM_OF_TAGS:  # not a heading over its senses
                            moods[(word, lemma)].add("imperative" in tags)
                continue
            glosses = _strs(sense.get("glosses"))
            if glosses:
                gloss = " ".join(glosses[-1].split())
                if gloss:
                    (rare if tags & RARE else common).add(gloss)
                    no_word = no_word and bool(
                        {"letter", "morpheme"} & tags or _LETTER.search(gloss)
                    )
                if gloss and gloss not in own:
                    own.append(gloss)
                    if tags & _REFLEXIVE_TAGS:
                        reflexive.append(gloss)
        table: set[str] = set()
        for form in _dicts(obj.get("forms")):
            text = form.get("form")
            tags = set(_strs(form.get("tags")))
            if (
                isinstance(text, str)
                and text
                and text != word
                and (spaced_words or " " not in text)
                and not tags & _NOT_A_FORM
                and not text.startswith("-")  # a bare ending ("-lor")
                and (short_forms or len(text) > SHORT)
            ):
                out.forms[text].add(word)
                table.add(text)
                moods[(text, word)].add("imperative" in tags)
                if pos == "verb":
                    out.verb_forms.add((text, word))
        if not own:
            continue
        rare -= common
        own.sort(key=lambda gloss: gloss in rare)  # stable: the rest keep order
        number = obj.get("etymology_number")
        key = f"{word}|{pos}|{number if isinstance(number, int) else ''}"
        seen[key] += 1
        if seen[key] > 1:  # the same word, part of speech and etymology twice
            key = f"{key}|{seen[key]}"
        out.entries.append(
            WiktEntry(
                key,
                word,
                pos,
                tuple(own[:MAX_MEANINGS]),
                reading(obj),
                frozenset(table),
                standing=(
                    3
                    if pos in NO_WORD_POS or no_word
                    else NAME
                    if pos == "name" and cased(word)
                    else 1
                    if all(g in rare for g in own)
                    else 0
                ),
            )
        )
        if reflexive:
            out.reflexive[key] = reflexive
    out.imperative = {pair for pair, kinds in moods.items() if kinds == {True}}
    out.entries = in_order(out.entries, uses)
    out.lemma_first = lemma_first(out.entries, starts_as_form, form_pos, uses)
    return out


DERIVED = frozenset(
    {"noun-from-verb", "agent", "gerund", "diminutive", "augmentative", "equivalent"}
)
"""A form-of sense's tags that name a word made from another, not a form of
it: Arabic's وقت (time) starts "verbal noun of وَقَتَ", German's Vertreter
(representative) "agent noun of vertreten", Abkommen (agreement) "gerund
of abkommen", Spanish's novia (girlfriend) "female equivalent of novio"
("equivalent": `_EQUIVALENT`)."""
_EQUIVALENT = re.compile(r"^(?:fe)?male equivalent of\b", re.IGNORECASE)


def lemma_first(
    entries: list[WiktEntry],
    starts: Mapping[str, tuple[frozenset[str], str, frozenset[str]]],
    form_pos: Mapping[str, set[str]],
    uses: Uses | None,
) -> dict[str, frozenset[str]]:
    """The forms whose lemma comes first (`Language.lemma_first`): the page
    starts with the form as its lemma's, and the form is no word of its own -
    - not a verb's form (a verb form's lemma comes first by its own rule,
      `packs.lemma_table`; German's "danke" is thanks before danken's);
    - not a derived word (`DERIVED`);
    - at most `LEMMA_FIRST` everyday meanings of its own ("chica", girl and
      maid, stays; "nos", us, too);
    - and the treebanks don't use it more as one of its own entries' parts
      of speech than as its forms' (German's "meist" starts "superlative of
      viel" but is the adverb "mostly"; Arabic's أثناء is "during")."""
    meanings: dict[str, int] = defaultdict(int)
    own_pos: dict[str, set[str]] = defaultdict(set)
    for e in entries:
        if e.standing == 0:
            meanings[e.word] += len(e.meanings)
            own_pos[e.word].add(e.pos)
    out = {}
    for word, (lemmas, pos, tags) in starts.items():
        if pos == "verb" or tags & DERIVED or meanings[word] > LEMMA_FIRST:
            continue
        counts = uses.get(word.lower(), {}) if uses else {}
        if sum(counts.values()) >= MIN_USES and used_as(
            counts, own_pos[word] - form_pos[word]
        ) > used_as(counts, form_pos[word]):
            continue
        out[word] = lemmas
    return out


def used_as(counts: Mapping[str, int], parts: set[str]) -> int:
    """How often the treebanks use a word as any of Wiktionary's `parts` of
    speech (each tag once: a determiner and an article are both DET)."""
    return sum(
        counts.get(tag, 0) for tag in {t for p in parts for t in UD_POS.get(p, ())}
    )


def cased(word: str) -> bool:
    """Written in a script with capitals. There a name under a lower-case
    word is seldom the word met (Russian's у, "Wu (language)"); in Arabic
    or Thai, which have none, it often is (مصر, Egypt), so it keeps its
    place."""
    return any(c.lower() != c.upper() for c in word)


def shares(word: str, uses: Uses | None) -> dict[str, float]:
    """Each of Wiktionary's parts of speech -> its share of `word`'s uses in
    the treebanks; empty if they use it fewer than `MIN_USES` times."""
    counts = uses.get(word.lower()) if uses else None
    total = sum(counts.values()) if counts else 0
    if not counts or total < MIN_USES:
        return {}
    return {
        pos: sum(counts.get(tag, 0) for tag in tags) / total
        for pos, tags in UD_POS.items()
    }


def in_order(entries: list[WiktEntry], uses: Uses | None = None) -> list[WiktEntry]:
    """`entries` with each word's own in the order its card shows them:
    by `standing` (a word, then only rare senses, a name, a letter or an
    affix); then, where `uses` (treebank counts) say clearly that another
    part of speech is the word's commonest (`LEAD`, `MIN_SHARE`), that
    entry first; otherwise Wiktionary's order. Each word's entries take the
    places they had, so other words' order (ranks' ties) and every key stay
    as they were.

    Wiktionary lists a word's entries by etymology: Thai's กับ showed
    "trap" before "with", มัน "fat" before "it"; Spanish's "de" showed "the
    name of the letter D" before "of" (polyglotic-hq 393)."""
    places: dict[str, list[int]] = defaultdict(list)
    for i, e in enumerate(entries):
        places[e.word].append(i)
    out = list(entries)
    for word, at in places.items():
        if len(at) < 2:
            continue
        ordered = sorted((entries[i] for i in at), key=lambda e: e.standing)
        share = shares(word, uses)
        # a name may come first too, where the treebanks say it is the word
        # (Arabic's مصر, Egypt; محمد): only a letter, an affix or a rare
        # entry can't
        lead = [e for e in ordered if e.standing in (ordered[0].standing, NAME)]
        best = max(lead, key=lambda e: share.get(e.pos, 0.0))
        mine = share.get(best.pos, 0.0)
        if mine >= LEAD * share.get(ordered[0].pos, 0.0) and mine >= MIN_SHARE:
            ordered.remove(best)
            ordered.insert(0, best)
        for i, e in zip(at, ordered, strict=True):
            out[i] = e
    return out


def glosses_by_word(objects: Iterable[dict[str, object]]) -> dict[str, list[str]]:
    """Another edition's glosses (the Chinese edition's, for Chinese
    speakers), by `word|pos`: its own senses only, grammar notes trimmed.
    Form-of senses and redirects carry no meaning of their own."""
    out: dict[str, list[str]] = {}
    for obj in objects:
        word, pos = obj.get("word"), obj.get("pos")
        if not isinstance(word, str) or not isinstance(pos, str):
            continue
        found = out.setdefault(f"{word}|{pos}", [])
        for sense in _dicts(obj.get("senses")):
            if sense.get("form_of") or _FORM_OF_TAGS & set(_strs(sense.get("tags"))):
                continue
            glosses = _strs(sense.get("glosses"))
            gloss = _NOTE.sub("", " ".join(glosses[-1].split())) if glosses else ""
            if gloss and gloss not in found:
                found.append(gloss)
        if not found:
            del out[f"{word}|{pos}"]
    return out
