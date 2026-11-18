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

from tools.dictionaries.russian import is_letter
from tools.dictionaries.treebanks import IN_NAME, POSSESSIVE

# Tags on a form-of sense or a form that say it is no word of its own
_FORM_OF_TAGS = frozenset({"form-of", "alt-of"})
# a short way of writing a word, not a form of it: wordfreq can't tell "D"
# (dame) or "a" (German's Ar) from the letter, so they took its frequency
_SHORT_FOR = frozenset({"abbreviation", "initialism", "acronym", "symbol"})
# ...but kaikki tags contractions and elisions "abbreviation" too: "do" (de
# + o), "au" (à + le), "l'" are words
_SHORTENED = frozenset({"contraction", "apocopic", "clipping", "elided"})
# Tags on a lemma's `forms` that aren't inflections: table headings, the
# template's name, spellings in another script, the lemma itself, the verb
# a table conjugates (Spanish's "se" names saber: "saber" had become se's
# form, and its card opened on the pronoun se; polyglotic-hq 407)
_NOT_A_FORM = frozenset(
    {
        "base-form",
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
ASPECTS = frozenset({"perfective", "imperfective"})
_QUALIFIERS = frozenset(
    {
        "rare",
        "dialectal",
        "obsolete",
        "archaic",
        "colloquial",
        "determinate",
        "indeterminate",
    }
)
"""A table row tagged with an aspect and nothing else but these is the verb's
partner of the other aspect, not its inflection: Polish's zacząć lists
zaczynać ("imperfective"), Ukrainian's розповісти розповідати - another
verb, with its own page. As a form, its card had opened on the partner
before its own entry (polyglotic-hq 448, 461)."""


def aspect_partner(tags: set[str]) -> bool:
    """Whether a table row's `tags` make it the verb's aspect partner
    (`ASPECTS`), not one of its forms."""
    return bool(tags & ASPECTS) and tags <= ASPECTS | _QUALIFIERS


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
SMALL_WORDS = frozenset({"pron", "det", "article", "particle"})
"""Parts of speech whose tables' short forms count all the same: a
pronoun's table is where Romanian's clitics le, îl, ne, vă and te are
forms (their pages say "them", "him", but name no lemma), and Ukrainian's
їм (to them) and же (ж's other spelling) - words in their languages' top
200 that `SHORT` had cut (polyglotic-hq 394, 396). Where the short form's
own page, in the same part of speech, names its lemmas, only those count:
Ukrainian's personal pronouns share one table, so їм is listed under я
and ти too, but its page says "dative of вони́". A mark is no small
word: Persian's ezafe hamza ٔ lists ی, so ی (the ending written apart)
had made the bare mark its 193rd word."""
_STRESS = str.maketrans("", "", "\u0301\u0300")
"""Stress marks over Cyrillic letters, which no precomposed letter holds:
Ukrainian's form-of targets carry them ("вони́"), its headwords don't -
31,755 of its 34,449 targets, so nearly every page's form link was dead
and Ukrainian found its forms through tables alone (polyglotic-hq 396,
399; `unmarked`). Macedonian's carry them on 676."""
PERSON = frozenset(
    {
        "first-person",
        "second-person",
        "third-person",
        "singular",
        "plural",
        "masculine",
        "feminine",
        "neuter",
        "formal",
        "informal",
        "reflexive",
        "possessive",
    }
)
"""The tags that say which pronoun a row of a personal pronouns' table is
(`pronoun_rows`)."""
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
    "pron": ("PRON", POSSESSIVE),
    "det": ("DET",),
    "article": ("DET",),
    "num": ("NUM",),
    "particle": ("PART", "INTJ"),
    "intj": ("INTJ",),
    "name": ("PROPN", IN_NAME),
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
    came_through: dict[tuple[str, str], set[str]] = field(
        default_factory=lambda: defaultdict(set)
    )
    """(form, lemma) -> the parts of speech of the pages and tables that
    link them: Romanian's vă is in the pronoun voi's table, so its card
    opens on voi "you", not the verb voi "to want" (`packs.assemble`;
    polyglotic-hq 396, 399)."""
    link_kinds: dict[tuple[str, str], set[str]] = field(
        default_factory=lambda: defaultdict(set)
    )
    """(form, lemma) -> what the link says the form is, where a treebank's
    counts can't tell it from the lemma's other uses (`link_kind`): a
    degree of comparison ("comparative": Swedish's "mindre" of lite), an
    adposition with a pronoun attached ("pronoun": Arabic's لَكُنَّ, ل
    "to" with "you"), or an oblique case ("case": Turkish's "içinde", iç's
    locative) (`packs.lemma_used`; polyglotic-hq 416)."""
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
    """The objects for one language in lines of JSON, each under the word
    its page is about (`page_word`). Lines that aren't JSON objects are
    skipped (the extracts carry a few)."""
    needle = f'"lang_code": "{lang_code}"'
    for line in text:
        if needle not in line:  # cheap filter before parsing
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and obj.get("lang_code") == lang_code:
            word = obj.get("word")
            if isinstance(word, str) and _SUBPAGE.search(word):
                obj["word"] = page_word(word)
                if is_letter(obj):
                    continue  # a split page's letter: see `page_word`
            yield obj


_SUBPAGE = re.compile(r"/languages [A-Z] to [A-Z]$")


def page_word(title: str) -> str:
    """The word a page is about. English Wiktionary splits its longest
    pages by language, and kaikki keeps the part's title: Polish's "i"
    ("and", 2.7 % of its running words), Czech's, Swedish's and Italian's
    are under "i/languages A to L" or "i/languages M to Z", so they had no
    entry and the packs wrote them by hand (polyglotic-hq 390, 396, 399).
    Such a page's letter is left out, as a letter is no word of a caption
    (`russian.is_letter`): the readers that keep letters (Spanish's,
    Vietnamese's) had made "i" their 419th and 191st word."""
    return _SUBPAGE.sub("", title)


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


_ELIDED_OF = re.compile(
    r"^(?:(?:elided|prevocalic|apocopic|clitic) form|elision) of (\w+)", re.IGNORECASE
)


def elided_of(sense: Mapping[str, object]) -> list[str]:
    """The word an elided word's sense says it is written short for, where
    Wiktionary gives it in words only, with no form-of link: French's n'
    ("Prevocalic form of ne."), m' and t' ("elided form of te"), s'
    ("Elision of se before a word beginning with a vowel."). They had been
    read as words whose meaning is that sentence, with no frequency of their
    own, and cut: "n'" opened nothing (polyglotic-hq 413)."""
    glosses = _strs(sense.get("glosses"))
    found = _ELIDED_OF.match(" ".join(glosses[-1].split())) if glosses else None
    return [found.group(1)] if found else []


_REFERS = re.compile(
    r"^(?!(?:an?|the|any|some|one|kind|type|sort)\b)"
    r"(?P<what>[^:;()]*?\b(?:form|spelling|noun|plural|singular|participle|gerund"
    r"|genitive|dative|accusative|locative|ablative|instrumental|vocative"
    r"|indicative|subjunctive|imperative|conditional|infinitive))"
    r" of (?P<target>[^\s,;:()]+)(?: \([^)]*\))?\s*\.?$",
    re.IGNORECASE,
)


def referred_to(sense: Mapping[str, object]) -> list[str]:
    """The word a sense only refers to, where its gloss is that reference
    and nothing else and kaikki gave it no form-of link - a word saying
    which kind of form or spelling it is: Hindi's इश्क,
    "nuqtaless form of इश्क़ (iśq)"; Italian's possiamo, "first-person
    plural present indicative/present subjunctive of potere"; Tagalog's
    turnilyo, "superseded, pre-2014 spelling of tornilyo"; Thai's
    ความชั่วช้า, "abstract noun of ชั่วช้า". Its card had shown that line
    and no meaning (polyglotic-hq 448, 461). Not "a form of government",
    nor a gloss that goes on to say what it means ("abstract noun of
    ปลอดภัย: safety")."""
    glosses = _strs(sense.get("glosses"))
    found = _REFERS.match(" ".join(glosses[-1].split())) if glosses else None
    if not found or " " not in found.group("what"):
        return []  # "form of address": no word says which form
    return [found.group("target")]


def said_for_several(sense: Mapping[str, object]) -> bool:
    """A form-of sense that names several words and says what it means
    after them (kaikki's `extra`): Romanian's își, "unstressed reflexive
    dative of el, ea, ei and ele: (to) himself/herself/themselves". Like a
    small word's "X and Y" (`TWO_LEMMAS`), it is what it means, not a form
    of any one of them: își had no entry, so și-a ("contraction of își +
    a") found nothing (polyglotic-hq 399, 407). A form of one word ("dich:
    accusative of du; you") stays that word's form."""
    targets = _dicts(sense.get("form_of"))
    return (
        "form-of" in _strs(sense.get("tags"))
        and len({str(t.get("word") or "") for t in targets}) > 1
        and any(t.get("extra") for t in targets)
        and bool(_SAYS_WHAT.search(" ".join(_strs(sense.get("glosses")))))
    )


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
    chain: bool = False,
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
    polyglotic-hq 389, 394). Without it, such a form counts only in a
    small word's table (`SMALL_WORDS`).
    `chain`: a form of a word whose page gives no entry counts for that
    word's own lemmas (`chained`): Czech's není (is not) is a form of
    nebýt, whose page is only "negative form of být" (polyglotic-hq 396).
    The generic reader's (`packs.read_wiktionary`); not Russian's, whose
    participles find their verbs by a rule of their own.

    Whatever the language: a link to a stress-marked word with no page is a
    link to its page without the marks (`_unmarked`); a row of a personal
    pronouns' table is its own pronoun's form (`pronoun_rows`); a small
    word's sense tagged a form of nothing is a meaning (Romanian's îi, "to
    him"), and so is one naming several words that says what it means
    (`said_for_several`: Romanian's își); and each link keeps the parts of
    speech it came through (`Language.came_through`).

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
    page_names: dict[tuple[str, str], set[str]] = defaultdict(set)
    # (word, part of speech) -> the lemmas its own page names, unstressed
    small: list[tuple[str, str, str]] = []  # short small words' table forms
    form_of: dict[str, set[str]] = defaultdict(set)  # its page's form-of lemmas
    tabled: dict[str, set[str]] = defaultdict(set)  # lemmas whose table has it
    pages: set[str] = set()  # every word with a page
    for obj in objects:
        word = obj.get("word")
        if not isinstance(word, str) or not word.strip():
            continue
        if " " in word.strip() and not spaced_words:
            continue  # phrases aren't looked up from a caption's words
        pages.add(word)
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
            if not targets and word[-1:] in "'’":
                targets = elided_of(sense)  # French's n': "Prevocalic form of ne."
            if targets and not spaced_words and all(" " in t for t in targets):
                targets = []  # "della": "contraction of di la" - a meaning
                tags -= _FORM_OF_TAGS
            if tags & derived and _SAYS_WHAT.search(
                " ".join(_strs(sense.get("glosses")))
            ):
                targets = []  # "causative of azalmak: to decrease" - a meaning
                tags -= _FORM_OF_TAGS
            if pos in SMALL_WORDS and said_for_several(sense):
                targets = []  # "... dative of el, ea, ei and ele: (to) himself"
                tags -= _FORM_OF_TAGS
            if (
                "alt-of" in tags
                and tags & _SHORT_FOR
                and not tags & _SHORTENED
                and len(word) <= SHORT
            ):
                continue  # "D", abbreviation of dame: neither a form nor a meaning
            page_names[(word, pos)].update(t.translate(_STRESS) for t in targets)
            if "alt-of" not in tags:
                form_of[word].update(targets)
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
            if not targets and not tags & _FORM_OF_TAGS:
                for lemma in referred_to(sense):
                    # its target first, its own line after: the entry (its
                    # ID) stays, as a form's whose page starts as one
                    # (`lemma_first`), or a verb's form (`verb_forms`)
                    if lemma != word:
                        out.forms[word].add(lemma)
                        out.came_through[(word, lemma)].add(pos)
                        form_of[word].add(lemma)
                        if pos == "verb":
                            out.verb_forms.add((word, lemma))
                        elif first_object and n == 0:
                            starts_as_form[word] = (
                                frozenset({lemma}),
                                pos,
                                frozenset(),
                            )
            said_alone = not targets and pos in SMALL_WORDS and "alt-of" not in tags
            # Romanian's îi, îți, vă: "to him", "to you", "you", tagged a form
            # of no word - their meanings (polyglotic-hq 399)
            if targets or (_FORM_OF_TAGS & tags and not said_alone):
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
                        out.came_through[(word, lemma)].add(pos)
                        if kind := link_kind(pos, tags):
                            out.link_kinds[(word, lemma)] |= kind
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
        small_word = pos in SMALL_WORDS and any(ch.isalpha() for ch in word)
        rows = _dicts(obj.get("forms"))
        whose = pronoun_rows(word, rows)
        for n, form in enumerate(rows):
            text = form.get("form")
            tags = set(_strs(form.get("tags")))
            owner = whose.get(n, word)
            if (
                isinstance(text, str)
                and text
                and text != word
                and owner is not None
                and text.translate(_STRESS) != owner
                and (spaced_words or " " not in text)
                and not tags & _NOT_A_FORM
                and not aspect_partner(tags)
                and not text.startswith("-")  # a bare ending ("-lor")
                and (short_forms or len(text) > SHORT or small_word)
            ):
                if not short_forms and len(text) <= SHORT:
                    small.append((text, owner, pos))
                out.forms[text].add(owner)
                out.came_through[(text, owner)].add(pos)
                if kind := link_kind(pos, tags):
                    out.link_kinds[(text, owner)] |= kind
                tabled[text].add(owner)
                if owner == word:
                    table.add(text)
                moods[(text, owner)].add("imperative" in tags)
                if pos == "verb":
                    out.verb_forms.add((text, owner))
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
    for text, word, pos in small:  # its own page says whose form it is
        says = page_names.get((text, pos))
        if says and word.translate(_STRESS) not in says:
            out.forms[text].discard(word)
            moods.pop((text, word), None)
            out.came_through.pop((text, word), None)
            out.link_kinds.pop((text, word), None)
    _unmarked(out, pages, moods, form_of, starts_as_form)
    if chain:
        chained(out, form_of, tabled)
    out.forms = defaultdict(set, {f: ls for f, ls in out.forms.items() if ls})
    out.imperative = {pair for pair, kinds in moods.items() if kinds == {True}}
    out.entries = in_order(out.entries, uses)
    out.lemma_first = lemma_first(out.entries, starts_as_form, form_pos, uses)
    return out


DEGREES = frozenset({"comparative", "superlative"})
"""Tags of a link that is a degree of comparison."""
PERSONS = frozenset({"first-person", "second-person", "third-person"})
"""Tags of a link with a person: on an adposition's form, a pronoun attached."""
OBLIQUE = frozenset(
    {"locative", "dative", "ablative", "instrumental", "genitive", "essive"}
)
"""Tags of a link in an oblique case: a noun so may be used as an adposition."""
ADPOSITIONS = frozenset({"prep", "postp"})
"""Wiktionary's parts of speech for adpositions."""


def link_kind(pos: str, tags: set[str]) -> set[str]:
    """What a link (a form-of sense's or a table row's `tags`, through `pos`)
    says its form is, for `Language.link_kinds`: "comparative" or
    "superlative"; "pronoun" where an adposition's form has a person
    (Arabic's لَكُنَّ, "to you", second-person feminine plural of ل); "case"
    where it is in an oblique case (Turkish's "içinde", iç's locative);
    "participle" where it is a verb's participle (German's "fehlend")."""
    kind = set(tags & DEGREES)
    if pos in ADPOSITIONS and tags & PERSONS:
        kind.add("pronoun")
    if tags & OBLIQUE:
        kind.add("case")
    if "participle" in tags:
        kind.add("participle")
    return kind


def pronoun_rows(word: str, rows: list[dict[str, object]]) -> dict[int, str | None]:
    """Whose form each row of a personal pronouns' table is, by its place
    in `rows` (a page's `forms`): Ukrainian's and Swedish's personal
    pronouns share one table, on each one's page, so нам ("to us") was
    я's form as well as ми's, and its card opened on я, "I" (polyglotic-hq
    396, 399). A row is its pronoun's by its person, number, gender and
    the like (`PERSON`): the pronoun is the one nominative among such rows,
    else the page's own word if it is one of them (Ukrainian's себе, whose
    nominative is "-"), else nobody's (None: its own page says). A row
    that isn't a personal pronoun's is left out: the page's word's."""
    nominatives: dict[frozenset[str], set[str]] = defaultdict(set)
    written: dict[frozenset[str], set[str]] = defaultdict(set)
    person: dict[int, frozenset[str]] = {}
    for n, row in enumerate(rows):
        tags = set(_strs(row.get("tags")))
        text = row.get("form")
        if not {"personal", "pronoun"} <= tags or not isinstance(text, str):
            continue
        person[n] = frozenset(tags & PERSON)
        plain = text.translate(_STRESS)
        written[person[n]].add(plain)
        if "nominative" in tags and plain.strip("-"):
            nominatives[person[n]].add(plain)
    out: dict[int, str | None] = {}
    for n, key in person.items():
        nominative = nominatives.get(key, set())
        out[n] = (
            next(iter(nominative))
            if len(nominative) == 1
            else word
            if word in written[key]
            else None
        )
    return out


def _unmarked(
    language: Language,
    pages: set[str],
    moods: dict[tuple[str, str], set[bool]],
    form_of: dict[str, set[str]],
    starts: dict[str, tuple[frozenset[str], str, frozenset[str]]],
) -> None:
    """Each link to a stress-marked word that has no page made a link to
    the word without its marks, where that has one (`_STRESS`): Ukrainian's
    "вони́" is the page вони."""

    def found(lemma: str) -> str:
        if lemma in pages:
            return lemma
        plain = lemma.translate(_STRESS)
        return plain if plain in pages else lemma

    for form, lemmas in language.forms.items():
        if any(found(lemma) != lemma for lemma in lemmas):
            plain = {found(lemma) for lemma in lemmas} - {form}
            lemmas.clear()
            lemmas.update(plain)
    for lemmas in form_of.values():
        if any(found(lemma) != lemma for lemma in lemmas):
            plain = {found(lemma) for lemma in lemmas}
            lemmas.clear()
            lemmas.update(plain)
    language.verb_forms = {
        (form, found(lemma))
        for form, lemma in language.verb_forms
        if found(lemma) != form
    }
    _repointed(moods, found)
    _repointed(language.came_through, found)
    _repointed(language.link_kinds, found)
    for word, (named, pos, tags) in list(starts.items()):
        starts[word] = (frozenset(found(lemma) for lemma in named), pos, tags)


def _repointed[T](
    pairs: dict[tuple[str, str], set[T]], found: Callable[[str], str]
) -> None:
    """`pairs`, (form, lemma) -> what is known of the link, with each lemma
    as `found` says, in place."""
    for form, lemma in [p for p in pairs if found(p[1]) != p[1]]:
        kinds = pairs.pop((form, lemma))
        if found(lemma) != form:
            pairs.setdefault((form, found(lemma)), set()).update(kinds)


def chained(
    language: Language,
    form_of: Mapping[str, set[str]],
    tabled: Mapping[str, set[str]],
) -> None:
    """Each form of a word whose page gives no entry counts for the lemmas
    that page says it is a form of (`form_of`: a page's form-of senses'
    lemmas, not its other spellings'), one step: Czech's není (is not, its
    66th word) is nebýt's, and nebýt's page is only "negative form of
    být", so není had found nothing (polyglotic-hq 394, 396).
    - Only a form none of whose lemmas has an entry: one that found an
      entry is left as it was.
    - Not from or through another spelling (an alt-of sense): Italian's
      "r" (the letter's frequency) is a spelling of er, a form of el, which
      it had made the 385th word; Swiss German's
      "massnahmen" would have become maßnehmen's (to take measure), its
      frequency Maßnahmen's; French's T-N-L, through the initialism TNL,
      had made Terre-Neuve-et-Labrador its 716th word.
    - A form's own table counts as its page; a lemma's table doesn't:
      Ukrainian's shared pronoun table lists вони́
      (stress-marked, no page) as я's."""
    words = {e.word for e in language.entries}
    before = {form: frozenset(lemmas) for form, lemmas in language.forms.items()}
    for form, lemmas in language.forms.items():
        if before[form] & words:
            continue
        for lemma in before[form] - words:
            if lemma not in form_of.get(form, ()) and lemma not in tabled.get(form, ()):
                continue  # another spelling: Italian's "r" is er's, er el's
            further = frozenset(form_of.get(lemma, ())) - {form, lemma}
            lemmas |= further
            if (form, lemma) in language.verb_forms:
                language.verb_forms.update((form, f) for f in further)


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


def resolved(counts: Mapping[str, int], parts: set[str]) -> Mapping[str, int]:
    """A word's treebank `counts` with its uses as a possessive
    (`treebanks.POSSESSIVE`, a pronoun attached as a determiner) as a
    determiner's where Wiktionary has the word as one (`parts`: its own
    entries'); otherwise they stay its pronoun's (`UD_POS`). Italian's
    "mio" is a determiner ("my") and a pronoun ("mine"): "il mio libro"
    is the determiner (polyglotic-hq 416)."""
    n = counts.get(POSSESSIVE, 0)
    if not n or not parts & {"det", "article"}:
        return counts
    out = {tag: c for tag, c in counts.items() if tag != POSSESSIVE}
    out["DET"] = out.get("DET", 0) + n
    return out


def shares(
    word: str, uses: Uses | None, parts: set[str] | None = None
) -> dict[str, float]:
    """Each of Wiktionary's parts of speech -> its share of `word`'s uses in
    the treebanks; empty if they use it fewer than `MIN_USES` times.
    `parts`: the word's own entries' (`resolved`)."""
    counts = uses.get(word.lower()) if uses else None
    if counts and parts:
        counts = resolved(counts, parts)
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
        share = shares(word, uses, {e.pos for e in ordered})
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
