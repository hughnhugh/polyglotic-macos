"""An English word's meanings in English (polyglotic-hq 447, decision 0211):
for `ecdict-en.sqlite`, the English dictionary with ECDICT's entries,
inflections and ranks but meanings an English reader can read.

Each entry's meanings, from the first of these that has the word:
1. **Our own** (`english_core.txt`): short everyday definitions written for
   this app, for the words WordNet has nothing or the wrong first sense
   for - "the", "of", "you", "can" (WordNet's first "can" is a tin), "he"
   (helium), "I" (iodine), "like" as a preposition. They replace WordNet's
   for that word.
2. **Open English WordNet** (`oewn`), its senses grouped by part of
   speech: the part of speech English text uses the word as most first -
   counted in a treebank (`treebanks`, UD English-EWT; only counts) - each
   part of speech's senses in WordNet's order (its commonest first). The
   first two senses are the commonest part of speech's; another part of
   speech used at least `ALSO_SHOWN` of the time has its first sense next,
   so the card's three show it.
3. **An inflected form's own entry** with neither ("ran", "children"):
   what it is a form of ("past tense of run"), from ECDICT's inflections.
   (The card shows the form's lemma's entry first anyway: `EnglishDictionary.lookup`.)

A definition is cut at WordNet's "; " where what comes first stands alone,
and the first sense carries an example where WordNet gives a short one
that uses the word. Each meaning starts with its part of speech, as the
packs' do ("(verb) ...").
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path

from tools.dictionaries import oewn
from tools.dictionaries.ecdict import EcdictRow

CORE = Path(__file__).parent / "english_core.txt"
MAX_MEANINGS = 8  # per entry: the card shows three; the rest is size
ALSO_SHOWN = 0.2
"""The share of a word's uses (in the treebank) another part of speech
needs for its first sense to be among the card's three."""
SHORT_EXAMPLE = 70
"""The longest example a first sense carries, in characters."""
SHORTEST_CUT = 12
"""The least a definition keeps when cut at its first "; "."""
TREEBANK_PARTS = {
    "NOUN": "noun",
    "PROPN": "noun",
    "VERB": "verb",
    "AUX": "verb",
    "ADJ": "adj",
    "DET": "adj",  # WordNet's quantifiers are adjectives: some, many, every
    "NUM": "noun",  # ...and its numbers nouns first: "two"
    "ADV": "adv",
}
"""The treebank's parts of speech, as the WordNet part of speech they count for."""
CARD_PARTS = {"noun": "noun", "verb": "verb", "adjective": "adj", "adverb": "adv"}
"""WordNet's parts of speech as the card names them (the packs' names)."""
FORMS = {
    "p": ("verb", "past tense"),
    "d": ("verb", "past participle"),
    "i": ("verb", "-ing form"),
    "3": ("verb", "present tense (he, she, it)"),
    "r": ("adj", "comparative"),
    "t": ("adj", "superlative"),
    "s": ("noun", "plural"),
}
"""ECDICT's kinds of inflected form (`exchange`), as the card says them."""

Core = Mapping[str, Sequence[tuple[str, str, str]]]
"""Word -> its own senses: (part of speech, definition, example)."""
Uses = Mapping[str, Mapping[str, int]]
"""Word (lower case) -> how often the treebank uses it as each part of speech."""


def read_core(path: Path = CORE) -> dict[str, list[tuple[str, str, str]]]:
    """`english_core.txt`: "word | part of speech | definition | example"
    (the example may be empty), one sense a line in the order shown; "#"
    lines are notes."""
    out: dict[str, list[tuple[str, str, str]]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        word, pos, definition, example = (part.strip() for part in line.split("|"))
        out.setdefault(word, []).append((pos, definition, example))
    return out


def short(definition: str) -> str:
    """WordNet's definition up to its first "; " if what comes first is a
    definition of its own: "have the quality of being; (copula, used with
    an adjective or a predicate noun)" is "have the quality of being"."""
    first, sep, _ = definition.partition("; ")
    return first if sep and len(first) >= SHORTEST_CUT else definition


def said(pos: str, definition: str, example: str = "") -> str:
    """A meaning as the card shows it: "(verb) run fast: "example"."""
    shown = f"({pos}) {definition}"
    return f'{shown}: "{example}"' if example else shown


def example_for(word: str, examples: Iterable[str]) -> str:
    """The first of a sense's examples that is short and uses the word (or
    a form starting like it: "ran" doesn't, "running" does). WordNet gives
    a meaning group's examples, which often use another of its words:
    "big" had "a large city"."""
    stem = re.escape(word.lower()[: max(3, len(word) - 2)])
    for example in examples:
        text = example.strip().strip('"').strip()
        if len(text) <= SHORT_EXAMPLE and re.search(rf"\b{stem}", text.lower()):
            return text
    return ""


def from_wordnet(
    word: str, senses: Sequence[oewn.Sense], uses: Mapping[str, int] | None
) -> tuple[str, ...]:
    """A word's WordNet senses as the card's meanings: parts of speech in
    the order the treebank uses the word (`uses`: tag -> count; no count
    for any: WordNet's order), then as `ALSO_SHOWN` says."""
    by_part: dict[str, list[oewn.Sense]] = {}
    for sense in senses:
        by_part.setdefault(CARD_PARTS[sense.pos], []).append(sense)
    counts: dict[str, int] = {}
    for tag, n in (uses or {}).items():
        part = TREEBANK_PARTS.get(tag)
        if part is not None:
            counts[part] = counts.get(part, 0) + n
    order = sorted(by_part, key=lambda part: -counts.get(part, 0))  # stable
    total = sum(counts.get(part, 0) for part in order)
    also = [
        by_part[part][0]
        for part in order[1:]
        if total and counts.get(part, 0) / total >= ALSO_SHOWN
    ]
    ordered = [*by_part[order[0]][:2], *also]
    ordered += [s for part in order for s in by_part[part] if s not in ordered]
    out = []
    for n, sense in enumerate(ordered[:MAX_MEANINGS]):
        example = example_for(word, sense.examples) if n == 0 else ""
        out.append(said(CARD_PARTS[sense.pos], short(sense.definition), example))
    return tuple(dict.fromkeys(out))


def inflections(rows: Iterable[EcdictRow]) -> dict[str, list[tuple[str, str]]]:
    """Each inflected form -> (kind, lemma) for each lemma whose ECDICT row
    lists it ("was": [("p", "be")]): ECDICT's "was" has no inflections of
    its own, "be" lists it."""
    out: dict[str, list[tuple[str, str]]] = {}
    for row in rows:
        for kind, forms in row.exchange.items():
            if kind not in FORMS:
                continue
            for form in forms.split(","):
                if form and form != row.word:
                    out.setdefault(form, []).append((kind, row.word))
    return out


def form_of(
    row: EcdictRow, forms: Mapping[str, Sequence[tuple[str, str]]]
) -> tuple[str, ...]:
    """An inflected form's own meaning ("(verb) past tense and past
    participle of leave"): from the lemma rows that list it, else from its
    own row's "0:" and "1:"."""
    found = list(forms.get(row.word, ()))
    if not found and row.lemma is not None:
        found = [(k, row.lemma) for k in row.exchange.get("1", "") if k in FORMS]
    if not found:
        return ()
    lemma = found[0][1]
    kinds = [FORMS[k] for k, of in found if of == lemma]
    names = list(dict.fromkeys(name for _, name in kinds))
    return (said(kinds[0][0], f"{' and '.join(names)} of {lemma}"),)


def meanings_of(
    row: EcdictRow,
    senses: Mapping[str, list[oewn.Sense]],
    core: Core,
    uses: Uses,
    forms: Mapping[str, Sequence[tuple[str, str]]],
) -> tuple[str, ...]:
    """`row`'s meanings in English (the module's order of sources); () if
    none has the word."""
    own = core.get(row.word)
    if own:
        return tuple(
            said(pos, definition, example if n == 0 else "")
            for n, (pos, definition, example) in enumerate(own[:MAX_MEANINGS])
        )
    found = list(oewn.senses_of(senses, row.word))
    if found:
        return from_wordnet(row.word, found, uses.get(row.word.lower()))
    return form_of(row, forms)
