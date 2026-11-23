"""Words of a spaced language, with simplemma's lemma for each: the
`WordSplit` port for Spanish (and later the other languages written with
spaces).

A word is a run of letters, with apostrophes and hyphens inside - the
same rule as English's (`core.lexicon.english.words`). simplemma (MIT;
dictionary data, 54 languages) gives a lemma: "hablábamos" -> hablar. The
dictionary pack's own inflection table is asked first (it's Wiktionary's,
and knows "supe" is saber), so simplemma's lemma is a guess (`guesses`):
the fallback for a form the table hasn't got.

simplemma is imported only when a pack that needs it is used - and the
split works without it: the installed app leaves it out (decision 0123),
and a word is then looked up through the pack's own table alone (Russian:
96.4 % of running words found without it, 96.6 % with; polyglotic-hq 327).

French elides: "l'homme", "qu'il", "j'ai" are two words each, written as
one run of letters. A run is cut after its first apostrophe when what
stands before it is one of the language's elided words (`ELIDED`), so
"homme" is the word a learner points at and "l'" the one before it;
"aujourd'hui" stays whole (polyglotic-hq 341: a split of its own name in
the packs list, `elided`, so an app from before it is never offered a
French pack it would cut wrongly). Italian elides the same way
("l'uomo", "dell'anno", "c'è"; polyglotic-hq 380).

Some languages write small words onto the next or the last one without
an apostrophe: Arabic's "and", "the", "with" (والكتاب is و + ال +
كتاب), Indonesian's "-nya" (rumahnya, his house). A word the pack hasn't
got is then looked up as what is left without them (`CLITICS`): guesses,
after simplemma's, tried only when nothing else is found, so a word the
pack has whole (وزير, minister, not و + زير) is never cut. Indonesian's
and Hindi's regular endings and prefixes are guessed off the same way
(polyglotic-hq 380). The split's own name in the packs list (`clitics`)
keeps an app without these from a pack that needs them.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from polyglotic_desktop.core.lexicon import arabic, korean_forms, turkish
from polyglotic_desktop.core.lexicon.english import words as letter_runs
from polyglotic_desktop.ports.word_split import SplitWord

ELIDED = {
    "fr": frozenset(
        {"l", "d", "j", "m", "t", "s", "n", "c", "qu", "jusqu", "lorsqu", "puisqu"}
    ),
    "it": frozenset(
        {
            "l",
            "un",
            "dell",
            "all",
            "dall",
            "nell",
            "sull",
            "coll",
            "d",
            "c",
            "m",
            "t",
            "s",
            "v",
            "n",
            "quest",
            "quell",
            "bell",
            "sant",
            "nessun",
            "buon",
            "anch",
            "com",
            "dov",
            "cos",
            "tutt",
        }
    ),
}
"""Per language, the words that lose their vowel before a vowel and are
written onto the next word with an apostrophe (lower case, without it)."""
_APOSTROPHES = "'’"


_AR_BEFORE = (
    "وال",
    "فال",
    "بال",
    "كال",
    "ولل",
    "فلل",
    "لل",
    "ال",
    "و",
    "ف",
    "ب",
    "ل",
    "ك",
)
"""Arabic's small words written onto the next one, longest first: and,
so, with, for, like, the - and لل, ل + ال ("for the")."""
_AR_AFTER = ("هما", "كما", "هم", "هن", "ها", "كم", "كن", "نا", "ني", "ه", "ك", "ي")
"""Its pronouns written onto the end: his, her, their, your, our, my."""
_ID_AFTER = ("nya", "lah", "kah", "pun", "ku", "mu")
"""Indonesian's: his/her/its/the, emphasis, the question, too, my, your."""


def arabic_bases(word: str) -> tuple[str, ...]:
    """What an Arabic word may be without its small words, likeliest first:
    the word without vowel marks, then without the words before it, then
    without a pronoun after it (a ت left at the end is ة's: مدرسته is
    مدرسة + ه). Two letters at least are left."""
    plain = arabic.plain(word)
    out = [plain] if plain != word else []
    stems = [plain] + [plain[len(p) :] for p in _AR_BEFORE if plain.startswith(p)]
    for stem in stems:
        if stem != plain and len(stem) >= 2:
            out.append(stem)
    for stem in stems:
        for ending in _AR_AFTER:
            base = stem[: -len(ending)]
            if stem.endswith(ending) and len(base) >= 2:
                out += [base] + ([base[:-1] + "ة"] if base.endswith("ت") else [])
    return tuple(dict.fromkeys(w for w in out if w != word))


_ID_SUFFIXES = ("kan", "an", "i")
"""Its suffixes that make a word of another (tulis: tuliskan, tulisan)."""
_ID_PREFIXES = (
    ("meny", "s", "s"),
    ("meng", "k", ""),
    ("mem", "p", ""),
    ("men", "t", ""),
    ("me", "", ""),
    ("peny", "s", "s"),
    ("peng", "k", ""),
    ("pem", "p", ""),
    ("pen", "t", ""),
    ("per", "", ""),
    ("pe", "", ""),
    ("ber", "", ""),
    ("be", "", ""),
    ("ter", "", ""),
    ("di", "", ""),
    ("ke", "", ""),
    ("se", "", ""),
)
"""Its prefixes, longest first, each with the stem's first letter its
nasal took, before a vowel and before a consonant: menulis is tulis,
memukul pukul, mengirim kirim, menyapu sapu - but membaca is baca,
mendengar dengar."""
_VOWELS = frozenset("aeiou")


def indonesian_bases(word: str) -> tuple[str, ...]:
    """What an Indonesian word may be made from, likeliest first: a
    doubled word's first half (lain-lain, tumbuh-tumbuhan), the word
    without the small word on its end (rumahnya: rumah), then without a
    suffix, a prefix or both (berpenduduk: penduduk; ditempati: tempat;
    pengukiran: ukir) - three letters at least left. Guesses only: tried
    when the pack hasn't got the word itself."""
    lower = word.lower()
    if "-" in lower:
        return (lower.split("-")[0],)
    out = [
        lower[: -len(e)]
        for e in _ID_AFTER
        if lower.endswith(e) and len(lower) - len(e) >= 3
    ]
    stems = [lower, *out]
    for stem in list(stems):
        stems += [stem[: -len(s)] for s in _ID_SUFFIXES if stem.endswith(s)]
    for stem in stems:
        for prefix, before_vowel, before_consonant in _ID_PREFIXES:
            if stem.startswith(prefix) and len(stem) > len(prefix):
                rest = stem[len(prefix) :]
                took = before_vowel if rest[0] in _VOWELS else before_consonant
                out += [took + rest] + ([rest] if took else [])
                break  # the longest prefix only
    out += stems[1:]
    return tuple(dict.fromkeys(w for w in out if len(w) >= 3 and w != lower))


_HI_A_STEM = ("े", "ी")
"""Hindi's ā-stem endings: a noun's or adjective's -ā is -e or -ī as it
agrees (लड़के, उनकी, वाले)."""


def hindi_bases(word: str) -> tuple[str, ...]:
    """What a Hindi word's dictionary form may be, likeliest first: an
    ā-stem's -ā for its -e or -ī (उनके: उनका), the stem without an oblique
    plural's -oṃ or -eṃ (लोगों: लोग; बातें: बात), -ī for -iyoṃ (लड़कियों:
    लड़की). Guesses only: tried when the pack hasn't got the word."""
    out = []
    if word.endswith(_HI_A_STEM) and len(word) > 2:
        out.append(word[:-1] + "ा")
    for ending, then in (
        ("ियों", ("ी",)),
        ("ियाँ", ("ी",)),
        ("ों", ("", "ा")),
        ("ें", ("", "ा")),
    ):
        if word.endswith(ending) and len(word) > len(ending) + 1:
            out += [word[: -len(ending)] + t for t in then]
    return tuple(dict.fromkeys(out))


_ZWNJ = "\u200c"
_FA_LETTERS = str.maketrans({"ي": "ی", "ك": "ک", "ى": "ی"})
"""Arabic's yeh and kaf as Persian writes them: web text and some speech
models write the Arabic letters (wordfreq's Persian list has كه beside
که); Wiktionary writes Persian's."""
_FA_VERB_BEFORE = ("نمی", "می")
"""The present's prefix (and its negative): می‌کنم is کنم, a form of کردن."""
_FA_AFTER = (
    "هایی",
    "هایم",
    "هایت",
    "هایش",
    "های",
    "ها",
    "ترین",
    "تر",
    "شان",
    "تان",
    "مان",
    "ای",
    "ان",
    "ات",
    "ام",
    "اش",
    "ی",
    "ش",
    "م",
    "ت",
)
"""Persian's endings on a noun or adjective, longest first: the plurals
(-hā, -hā-ye, -ān, Arabic loans' -āt), the comparative and superlative,
the possessives and the ezafe or indefinite -i."""


def persian_bases(word: str) -> tuple[str, ...]:
    """What a Persian word may be, likeliest first: the word without vowel
    marks and with Persian's yeh and kaf; then, written with a zero-width
    non-joiner, without the present's prefix (می‌کنم: کنم) or an ending
    (داستان‌های: داستان); written without one, the same with the joiner put
    in (میکنم: می‌کنم) or the ending taken off (کشورهای: کشور). Two letters
    at least left. Guesses only (polyglotic-hq 387)."""
    plain = arabic.plain(word).translate(_FA_LETTERS)
    out = [plain]
    if _ZWNJ in plain:
        first, _, rest = plain.partition(_ZWNJ)
        if first in _FA_VERB_BEFORE:
            out.append(rest)
        head, _, last = plain.rpartition(_ZWNJ)
        if last in _FA_AFTER:
            out.append(head)
    else:
        for prefix in _FA_VERB_BEFORE:
            if plain.startswith(prefix) and len(plain) - len(prefix) >= 2:
                rest = plain[len(prefix) :]
                out += [prefix + _ZWNJ + rest, rest]
                break
        for ending in _FA_AFTER:
            if plain.endswith(ending) and len(plain) - len(ending) >= 2:
                out.append(plain[: -len(ending)])
    return tuple(dict.fromkeys(w for w in out if w != word))


_TL_VOWELS = frozenset("aeiou")
_TL_PREFIXES = (
    "nakikipag",
    "makikipag",
    "nakapag",
    "makapag",
    "nakipag",
    "makipag",
    "ipinag",
    "pinaka",
    "napaka",
    "pinag",
    "nakaka",
    "makaka",
    "pagka",
    "pagpa",
    "nagpa",
    "magpa",
    "naka",
    "maka",
    "pang",
    "nag",
    "mag",
    "pag",
    "pam",
    "pan",
    "ika",
    "ipa",
    "ma",
    "na",
    "pa",
    "ka",
    "i",
)
"""Tagalog's prefixes, longest first: verbs' (nag-, mag-, naka-, ipinag-),
nouns' (pag-, pagka-), adjectives' (ma-, napaka-, pinaka-), ordinals' (ika-)."""
_TL_SUFFIXES = ("han", "hin", "an", "in")


def _tl_core(stem: str) -> list[str]:
    """A Tagalog stem without its infix (-in-, -um-: tinawag, kumilos), then
    without its first syllable doubled (tatawag, lalakbay, aalis): each
    step's result."""
    out = []
    if len(stem) > 4 and stem[1:3] in ("in", "um") and stem[0] not in _TL_VOWELS:
        stem = stem[0] + stem[3:]
        out.append(stem)
    elif len(stem) > 4 and stem[:2] in ("in", "um"):
        stem = stem[2:]
        out.append(stem)
    if len(stem) > 4 and stem[:2] == stem[2:4]:  # ta-tawag
        out.append(stem[2:])
    elif len(stem) > 3 and stem[0] == stem[1] and stem[0] in _TL_VOWELS:  # a-alis
        out.append(stem[1:])
    return out


def tagalog_bases(word: str) -> tuple[str, ...]:
    """What a Tagalog word may be made from, likeliest first: without the
    linker written onto it (isang: isa; noong: noon; pang: pa), a doubled
    word's first half (libo-libong: libo), the part after a prefix's
    hyphen (pag-ukit: ukit); then without a prefix, an infix, a doubled
    first syllable or a suffix (paglalakbay: lakbay; tinatawag: tawag;
    kumikilos: kilos). Guesses only: tried when the pack hasn't got the
    word (polyglotic-hq 387). Two letters at least are left by the linker,
    three by the rest."""
    lower = word.lower().replace("’", "'")
    lower = lower.removesuffix("'t")  # iba't: iba at
    linked = []
    if lower.endswith("ng") and len(lower) >= 4:
        linked = [w for w in (lower[:-2], lower[:-1]) if len(w) >= 2]  # isa-ng, noon-g
    stems = [lower, *linked]
    if "-" in lower:
        first, _, rest = lower.partition("-")
        stems += [first] if rest.startswith(first) else [rest, first]
    made = []
    for stem in (s for s in stems if "-" not in s):
        for prefix in _TL_PREFIXES:
            if stem.startswith(prefix) and len(stem) - len(prefix) >= 3:
                rest = stem[len(prefix) :]
                made += [rest, *_tl_core(rest)]
                break
        made += _tl_core(stem)
    for stem in [*stems, *made]:
        for suffix in _TL_SUFFIXES:
            if stem.endswith(suffix) and len(stem) - len(suffix) >= 3:
                made.append(stem[: -len(suffix)])
                break
    out = [*stems[1:], *(w for w in made if len(w) >= 3)]
    if lower != word.lower():
        out.insert(0, lower)
    return tuple(dict.fromkeys(w for w in out if w != word.lower()))


def czech_bases(word: str) -> tuple[str, ...]:
    """A Czech word without its negative ne- (neměl: měl; nejsou: jsou), or
    a superlative's nej- (nejsnadněji: snadněji). Three letters at least
    left, so není isn't ní ("her"). Guesses only (polyglotic-hq 387)."""
    lower = word.lower()
    return tuple(
        lower[len(p) :]
        for p in ("ne", "nej")
        if lower.startswith(p) and len(lower) - len(p) >= 3
    )


_EL_ENDINGS = (
    ("ούν", "ώ"),
    ("ουν", "ω"),
    ("ονται", "ομαι"),
    ("εται", "ομαι"),
    ("ής", "ή"),
    ("ας", "α"),
)
"""Greek's endings its tables often lack, to the dictionary form's: a
verb's present (διαθέτουν: διαθέτω; κρατούν: κρατώ; μάχονται: μάχομαι)
and a feminine's genitive in -ή or -α (πληροφορικής: πληροφορική; χώρας:
χώρα), whose accent stays where it is. A genitive in -ου isn't guessed:
its accent moves (Νοτίου is νότιος)."""


def greek_bases(word: str) -> tuple[str, ...]:
    """A Greek word's dictionary form for a form Wiktionary's tables haven't
    got (Greek's conjugations are pages of their own). Guesses only
    (polyglotic-hq 387)."""
    lower = word.lower()
    return tuple(
        lower[: -len(ending)] + then
        for ending, then in _EL_ENDINGS
        if lower.endswith(ending) and len(lower) > len(ending) + 1
    )


CLITICS: dict[str, Callable[[str], tuple[str, ...]]] = {
    "ar": arabic_bases,
    "cs": czech_bases,
    "el": greek_bases,
    "fa": persian_bases,
    "hi": hindi_bases,
    "id": indonesian_bases,
    "ko": korean_forms.bases,
    "ms": indonesian_bases,
    "tl": tagalog_bases,
    "tr": turkish.bases,
}
"""Per language, what a word may be without the small words written onto
it, likeliest first (guesses: tried only when nothing else is found)."""

NAMES: dict[str, Callable[[str], tuple[str, ...]]] = {"tr": turkish.name_bases}
AFTER_A_BRACKET: dict[str, Callable[[str], tuple[str, ...]]] = {
    "ko": korean_forms.bases_after_bracket
}
"""Per language, the dictionary forms of a word written right after a
closing bracket or quote, as its lemmas in its line: Korean's particle
there is the word's inside (대성당(성지)이: -이, the subject particle, not
이, "this"; polyglotic-hq 516)."""
CLOSING = frozenset(")]}\"'”’」』》〉")
"""Per language whose names take their suffixes after an apostrophe, what
a capitalised word inside a sentence may be: a name, cut no further than
its own rules allow (Turkish's Atlantik is no form of atlamak, to jump;
polyglotic-hq 388). The first word of a sentence takes `CLITICS`'."""
_SENTENCE_ENDS = ".!?…"


def starts_sentence(text: str, start: int) -> bool:
    """Whether the word at `start` is the first of its sentence: the first
    in `text`, or after a full stop, question or exclamation mark (and any
    quotation marks or brackets after it)."""
    before = text[:start].rstrip().rstrip("\"'“”‘’«»()[]").rstrip()
    return not before or before[-1] in _SENTENCE_ENDS


def unelided(word: str) -> tuple[str, ...]:
    """An elided word whole, for a pack that lists only the whole word
    (Italian's "dell'" is della or dello): its letters with each vowel."""
    return tuple(word[:-1] + vowel for vowel in "oaei")


def cut_elided(text: str, start: int, end: int, elided: frozenset[str]) -> int | None:
    """Where the run `text[start:end]` is cut in two: just after its first
    apostrophe, if an elided word stands before it; else None."""
    for at in range(start, end):
        if text[at] in _APOSTROPHES:
            cut = at + 1
            return cut if cut < end and text[start:at].lower() in elided else None
    return None


NO_SIMPLEMMA = frozenset({"ko"})
"""Languages simplemma has no data for: it raises on them, so they are
split without it wherever it's installed (Korean's guesses are its own:
`CLITICS`; polyglotic-hq 510)."""


class SpacedSplit:
    """Words by letters, lemmas by simplemma, for `language` ("es").
    `simplemma`: False to split as the installed app does, without it
    (decision 0123) even where it's installed - a pack's build checks its
    commonest words so (polyglotic-hq 390)."""

    def __init__(self, language: str, simplemma: bool = True) -> None:
        self.language = language
        self.simplemma = simplemma and language not in NO_SIMPLEMMA

    def words(self, text: str) -> Sequence[SplitWord]:
        lemmatize = _lemmatizer() if self.simplemma else None
        elided = ELIDED.get(self.language)
        runs: list[tuple[int, int]] = []
        for start, end in letter_runs(text):
            cut = cut_elided(text, start, end, elided) if elided else None
            runs += [(start, end)] if cut is None else [(start, cut), (cut, end)]
        clitics = CLITICS.get(self.language)
        names = NAMES.get(self.language)
        out = []
        for start, end in runs:
            word = text[start:end]
            lemma = lemmatize(word, lang=self.language) if lemmatize else ""
            guesses: tuple[str, ...] = (lemma,) if lemma and lemma != word else ()
            bases = clitics
            if names and word[:1].isupper() and not starts_sentence(text, start):
                bases = names
            if bases:
                guesses = tuple(dict.fromkeys(guesses + bases(word)))
            if elided and word[-1:] in _APOSTROPHES:
                guesses += unelided(word)
            attached = AFTER_A_BRACKET.get(self.language)
            lemmas = (
                attached(word)
                if attached and text[start - 1 : start] in CLOSING
                else ()
            )
            out.append(SplitWord(start, end, lemmas=lemmas, guesses=guesses))
        return out


def _lemmatizer() -> Callable[..., str] | None:
    """simplemma's `lemmatize`, or None where it isn't installed (the
    installed app: decision 0123)."""
    try:
        from simplemma import lemmatize
    except ImportError:
        return None
    return lemmatize
