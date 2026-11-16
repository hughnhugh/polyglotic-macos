"""Russian's own rules for its pack: stress marks, ё, and which of a
headword's listed forms are its inflections.

Wiktionary (English edition) writes Russian the way learners' dictionaries
do: its headword line and inflection tables mark the stress ("рука́",
"ру́ку"), as does each "form of" link ("accusative singular of рука́").
Captions don't: a caption says "руку". So:
- every written form is looked up without its stress marks (`unstressed`);
- an entry's reading is its headword with the stress marked (`stressed`):
  how the word is said, in the scheme Russian learners use; and each
  inflected form keeps its own (`form_readings`), since the stress moves
  as a word inflects (рука́, ру́ку) and two forms can be written alike
  (ру́ки, руки́);
- a written form with ё is also found spelled with е, as most Russian text
  writes it ("еще" is ещё): the е spelling is one more form of the same
  word (`spellings`).

Each personal pronoun's page carries the table of them all (я's lists
её, она's), so those tables are left out: each form's own page says whose
it is ("меня: genitive of я").

A headword's `forms` also list words that aren't its inflections: its
aspect partner (говорить's perfective, сказать), derived words (собака's
diminutive собачка, its relational adjective собачий), a female
equivalent (кот's кошка), romanisations inside the tables (jestʹ). Only
inflections and other spellings count (`is_inflection`); the rest are
words of their own, with entries of their own.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Iterator, Mapping

STRESS_MARKS = ("\u0301", "\u0300")
"""The acute (main stress) and grave (secondary stress) accents, as
combining marks."""

INFLECTION_TAGS = frozenset(
    {
        "nominative",
        "genitive",
        "dative",
        "accusative",
        "instrumental",
        "prepositional",
        "locative",
        "partitive",
        "vocative",
        "count-form",
        "singular",
        "plural",
        "past",
        "present",
        "future",
        "imperative",
        "participle",
        "first-person",
        "second-person",
        "third-person",
        "short-form",
        "comparative",
        "superlative",
        "alternative",
    }
)
"""A listed form with one of these tags is the headword itself, inflected
or spelled another way. Without one it is another word: an aspect
partner ("perfective"), a derived word ("diminutive", "adjective
relational", "abstract-noun") or a female equivalent ("feminine")."""

DERIVED = frozenset(
    {
        "noun-from-verb",
        "diminutive",
        "augmentative",
        "endearing",
        "abbreviation",
        "initialism",
        "acronym",
        "clipping",
    }
)
"""A "form of" sense with one of these tags is a word of its own, its gloss
its meaning: стоимость is "verbal noun of стоить: cost, value"; палочка
"diminutive of палка: (small) stick"; США (plural) "initialism of
Соединённые Штаты Америки". Wiktionary links each to the word it comes
from, which would otherwise make it that word's form - or, where it comes
from a phrase, nothing at all."""

WORD_OF_ITS_OWN = DERIVED | {"feminine", "pejorative"}
"""As `DERIVED`, when the sense has no inflection's tag too: царица is
"female equivalent of царь: tsarina"; "feminine nominative singular of
новый" is новый's form."""

_FOLD = str.maketrans("ёЁ", "еЕ")


def unstressed(text: str) -> str:
    """`text` without its stress marks: "ру́ку" -> "руку". ё and й stay."""
    decomposed = unicodedata.normalize("NFD", text)
    for mark in STRESS_MARKS:
        decomposed = decomposed.replace(mark, "")
    return unicodedata.normalize("NFC", decomposed)


def spellings(word: str) -> tuple[str, ...]:
    """How `word` is written: as it is, and with е for ё ("ещё", "еще")."""
    return tuple(dict.fromkeys((word, word.translate(_FOLD))))


def _cyrillic(text: str) -> bool:
    """Letters, all Cyrillic (a hyphen allowed: "по-новому")."""
    letters = [ch for ch in text if ch != "-"]
    return bool(letters) and all(
        ch.isalpha() and "CYRILLIC" in unicodedata.name(ch, "") for ch in letters
    )


def _expanded(form: str) -> tuple[str, ...]:
    """A table's optional prefix spelled out: "(по)новее" -> "новее",
    "поновее"."""
    if form.startswith("(") and ")" in form:
        prefix, _, rest = form[1:].partition(")")
        return (rest, prefix + rest)
    return (form,)


def is_inflection(tags: frozenset[str]) -> bool:
    return bool(tags & INFLECTION_TAGS)


def _dicts(value: object) -> list[dict[str, object]]:
    return [v for v in value if isinstance(v, dict)] if isinstance(value, list) else []


def _tags(obj: Mapping[str, object]) -> frozenset[str]:
    tags = obj.get("tags")
    return (
        frozenset(t for t in tags if isinstance(t, str))
        if isinstance(tags, list)
        else frozenset()
    )


def stressed(obj: Mapping[str, object]) -> str:
    """How the headword is said: its headword line's form with the stress
    marked ("рука́"; two stresses as Wiktionary gives them: "тво́рог,
    творо́г"). "" where there is nothing to mark - one syllable ("дом"), or
    ё, which is always stressed ("ещё")."""
    word = obj.get("word")
    found = [
        str(f["form"])
        for f in _dicts(obj.get("forms"))
        if "canonical" in _tags(f) and isinstance(f.get("form"), str)
    ]
    found = [f for f in dict.fromkeys(found) if unstressed(f) == word and f != word]
    return ", ".join(found)


def form_readings(obj: Mapping[str, object]) -> Iterator[tuple[str, str]]:
    """(written form, the form with its stress marked) for each of a raw
    object's inflections that marks one - "руку", "ру́ку" from рука's table
    - and for a "form of" page's own headword ("руку"'s page: "ру́ку"). Read
    before `cleaned` takes the marks off."""
    for form in _dicts(obj.get("forms")):
        text = form.get("form")
        tags = _tags(form)
        if not isinstance(text, str) or {"personal", "pronoun"} <= tags:
            continue
        if not (is_inflection(tags) or "canonical" in tags):
            continue
        for marked in _expanded(text):
            plain = unstressed(marked)
            if plain != marked and _cyrillic(plain):
                for spelling in spellings(plain):
                    yield spelling, marked


def is_letter(obj: Mapping[str, object]) -> bool:
    """The entry for a letter of the alphabet: я's "the thirty-third letter"
    and "the name of the letter", which would come before я's "I" (a word's
    entries keep Wiktionary's order, and its letter comes first)."""
    word, pos = obj.get("word"), obj.get("pos")
    if pos in ("character", "symbol"):
        return True
    if pos != "noun" or not isinstance(word, str) or len(word) != 1:
        return False
    glosses = [" ".join(_strs(s.get("glosses"))) for s in _dicts(obj.get("senses"))]
    return bool(glosses) and all("letter" in g for g in glosses)


def _heading(sense: Mapping[str, object]) -> bool:
    """A sense that is only a heading over the next ones: в's "[with
    prepositional]", before "[with prepositional] in, at, on"."""
    glosses = _strs(sense.get("glosses"))
    return len(glosses) == 1 and glosses[0].startswith("[") and glosses[0].endswith("]")


def _strs(value: object) -> list[str]:
    return [v for v in value if isinstance(v, str)] if isinstance(value, list) else []


def cleaned(obj: dict[str, object]) -> dict[str, object]:
    """One kaikki object made ready for `kaikki.read_language`: forms and
    "form of" links without stress marks, only inflections and other
    spellings among its forms (each also spelled with е for ё), and the
    headword's own е spelling as one more form. A letter's entry
    (`is_letter`) is left without senses: no entry."""
    word = obj.get("word")
    out = dict(obj)
    if is_letter(obj):
        out["senses"] = []
    forms: list[dict[str, object]] = []
    for form in _dicts(obj.get("forms")):
        text = form.get("form")
        tags = _tags(form)
        if "canonical" in tags or "romanization" in tags:
            forms.append(form)  # read for the reading, never as a form
            continue
        if not isinstance(text, str) or not is_inflection(tags):
            continue
        if {"personal", "pronoun"} <= tags:
            continue  # the table of every personal pronoun, on each one's page
        for marked in _expanded(text):
            for spelling in spellings(unstressed(marked)):
                if _cyrillic(spelling):
                    forms.append({**form, "form": spelling})
    if isinstance(word, str):
        for spelling in spellings(word)[1:]:
            forms.append({"form": spelling, "tags": ["alternative"]})
    out["forms"] = forms
    senses = []
    for sense in _dicts(out.get("senses")):
        if _heading(sense):
            continue
        sense = dict(sense)
        tags = _tags(sense)
        if tags & DERIVED or (tags & WORD_OF_ITS_OWN and not is_inflection(tags)):
            # "verbal noun of стоить: cost": a meaning, not a link
            sense.pop("form_of", None)
            sense.pop("alt_of", None)
            sense["tags"] = sorted(tags - {"form-of", "alt-of"})
        for link in ("form_of", "alt_of"):
            targets = _dicts(sense.get(link))
            if targets:
                sense[link] = [
                    {**t, "word": unstressed(str(t.get("word") or ""))} for t in targets
                ]
        senses.append(sense)
    out["senses"] = senses
    return out


# -- participles ----------------------------------------------------------------
# A verb's table gives each participle once, as its masculine nominative
# ("рассматривающий"); in a sentence it is declined like an adjective
# ("рассматривающее"), and Wiktionary has a page for few of those forms.

_SOFT = (
    "ий",
    ("его", "ему", "им", "ем", "ая", "ей", "ую", "ее", "ие", "их", "ими", "ею"),
)
"""A participle in -щий or -вший (always after a hush or в): говорящий."""
_HARD = (
    "ый",
    ("ого", "ому", "ым", "ом", "ая", "ой", "ую", "ое", "ые", "ых", "ыми", "ою"),
)
"""A passive participle in -мый, -нный or -тый: сказанный."""
_SHORT = {"нный": "н", "мый": "м", "тый": "т"}
"""A passive participle's short form, stem and ending: сказан, сказана,
сказано, сказаны ("как сказано")."""


def participles(obj: Mapping[str, object]) -> list[tuple[str, str]]:
    """(participle, verb) for a cleaned verb's participles that decline:
    not the adverbial ones (говоря), which don't."""
    word = obj.get("word")
    if obj.get("pos") != "verb" or not isinstance(word, str):
        return []
    out = []
    for form in _dicts(obj.get("forms")):
        tags = _tags(form)
        text = form.get("form")
        if "participle" in tags and "adverbial" not in tags and isinstance(text, str):
            out.append((text, word))
    return out


def declined(participle: str) -> tuple[str, ...]:
    """A participle's other forms, declined as an adjective:
    "рассматривающий" -> "рассматривающего", ... "рассматривающее"; a
    reflexive one keeps its -ся ("находящийся" -> "находящегося"); a passive
    one has short forms too ("сказанный" -> "сказан", "сказано")."""
    stem, reflexive = participle, ""
    if stem.endswith("ся"):
        stem, reflexive = stem[:-2], "ся"
    for ending, endings in (_SOFT, _HARD):
        if stem.endswith(ending):
            base = stem[: -len(ending)]
            out = [base + e + reflexive for e in endings]
            for long, short in _SHORT.items():
                if stem.endswith(long) and not reflexive:
                    root = stem[: -len(long)] + short
                    out += [root + e for e in ("", "а", "о", "ы")]
            return tuple(out)
    return ()
