"""Reading ECDICT's CSV (https://github.com/skywind3000/ECDICT), cut to the
commonest words, with its inflections and a frequency rank.

Columns used: word, phonetic, translation (Chinese meanings, lines
separated by a literal `\\n`), tag (exam lists), bnc and frq (frequency
ranks in two corpora), exchange (inflections). Never read: `collins` and
`oxford` (from publishers' products - project 008), nor `definition`,
`detail`, `audio`.
"""

from __future__ import annotations

import csv
import re
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from tools.dictionaries.entry_ids import SourceEntry

# Inflection kinds in `exchange`: past, past participle, -ing, third person,
# comparative, superlative, plural. ("0" is the lemma, "1" the kind of form.)
FORM_KINDS = ("p", "d", "i", "3", "r", "t", "s")
THRESHOLDS = (0.0,)  # case changes only: "Internet" -> "internet"
_WORD = re.compile(r"[\w']+")


@dataclass(frozen=True)
class EcdictRow:
    word: str
    phonetic: str
    meanings: tuple[str, ...]
    tags: tuple[str, ...]
    bnc: int  # 0: not ranked
    frq: int  # 0: not ranked
    exchange: dict[str, str]

    @property
    def lemma(self) -> str | None:
        """What this word is an inflected form of, per ECDICT ("0:run")."""
        lemma = self.exchange.get("0")
        return lemma if lemma and lemma != self.word else None

    def source_entry(self) -> SourceEntry:
        words = frozenset(w for m in self.meanings for w in _WORD.findall(m))
        return SourceEntry(self.word, (self.word.lower(),), words)


def _rank(text: str) -> int:
    return int(text) if text.isdigit() else 0


def read(path: Path) -> Iterator[EcdictRow]:
    with path.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            exchange = {}
            for part in row["exchange"].split("/"):
                kind, _, value = part.partition(":")
                if value:
                    exchange[kind] = value
            meanings = tuple(  # "a" ends a line in a literal "\r" too
                text
                for m in row["translation"].split("\\n")
                if (text := m.replace("\\r", "").strip())
            )
            yield EcdictRow(
                word=row["word"],
                phonetic=row["phonetic"],
                meanings=meanings,
                tags=tuple(row["tag"].split()),
                bnc=_rank(row["bnc"]),
                frq=_rank(row["frq"]),
                exchange=exchange,
            )


def is_common(row: EcdictRow) -> bool:
    """The cut (decision 0009): words ranked in either corpus (about the
    commonest 50,000 in each), or on an exam list - with meanings."""
    return bool(row.meanings) and (row.frq > 0 or row.bnc > 0 or bool(row.tags))


def cut(rows: Iterable[EcdictRow]) -> list[EcdictRow]:
    return [row for row in rows if is_common(row)]


def frequency_ranks(rows: Iterable[EcdictRow]) -> dict[str, int]:
    """English frequency ranks from ECDICT's own columns: each word by the
    better of its two corpus ranks, then numbered 1, 2, 3... Words in
    neither corpus have none. One function, so another source (wordfreq,
    a learner's list) can replace it without touching anything else."""
    ranked = sorted(
        (min(r for r in (row.frq, row.bnc) if r > 0), row.word)
        for row in rows
        if row.frq > 0 or row.bnc > 0
    )
    return {word: n for n, (_, word) in enumerate(ranked, start=1)}


MISSING_FORMS = {"am": "be"}
"""Forms ECDICT hasn't got in lower case: it has "am" only as "AM" (with
be's meaning), and be's own list of forms leaves it out - so a caption's
"am" was in neither English dictionary (polyglotic-hq 447's top-200 check)."""
IN_CAPITALS = frozenset(
    {
        *("TV", "UK", "OK", "ST", "USA", "PC", "CD", "DJ", "DIY", "VIP", "IQ"),
        *("DNA", "RNA", "TB", "BC", "NY", "FBI", "CIA", "NASA", "BBC", "NATO"),
        *("NHS", "IBM", "FIFA", "UFC", "USSR", "UAE", "UNESCO", "IMF", "GMT"),
        *("HQ", "CPU", "ROM", "MB", "GB", "LAN", "URL", "ATM", "FAX", "CCTV"),
        *("APP", "CORE", "ELF", "MAG", "LP", "KO"),
    }
)
"""Entries ECDICT has only in capitals whose meaning is what the word means
in lower case, among wordfreq's commonest 15,000: a caption's "tv", "ok"
or "uk" was in no dictionary (polyglotic-hq 462, 463). Each is found in
lower case as well (`lower_case_forms`). Chosen by a person, not by rule:
trying every lower-case word in capitals opened "alice" on ALICE (a
computing term), "pm" on PM (出纳员, a cashier), "adams" on ADAMS rather
than Adam, and "ain't" on AI. "ST" carries our own meaning
(`ecdict_first.txt`): ECDICT's are computing and chemistry terms."""


def lower_case_forms(kept: set[str]) -> dict[str, str]:
    """`IN_CAPITALS`' lower-case spellings -> the entry, for the entries
    kept, where no entry is written so ("tv": "TV")."""
    return {
        word.lower(): word
        for word in sorted(IN_CAPITALS)
        if word in kept and word.lower() not in kept
    }


NOT_FORMS = frozenset({"number", "evening", "feed"})
"""Words ECDICT makes a form of a word they aren't a form of: its "number"
says "0:numb" (numb's comparative), so a caption's "number" opened numb,
麻木的, in both English dictionaries (polyglotic-hq 463's top-500 check);
"evening" opened even (polyglotic-hq 464) and "feed" fee."""

OWN_FIRST = frozenset(
    {
        *("bit", "later", "latest", "further", "ground", "lay", "shot"),
        *("building", "meeting", "training", "wedding", "marketing"),
        *("engineering", "amazing", "interesting", "interested", "limited"),
        "fucking",
    }
)
"""Forms whose own entry is the meaning they're commonly used in: "a bit"
is 一点, not a bite; "later" is 以后, not "more late"; "training" isn't
train, 火车. Each opens on its own entry, its lemma's second, and a caption
counts it for its own entry (polyglotic-hq 464). Chosen by a person from
the commonest 2,000 forms with entries of their own, where UD English-EWT
names the form itself as its lemma more often than ECDICT's lemma (or
uses "later" as an adverb, 66 of 70). Not "left": EWT's are leave's 70
times in 81."""


def own_first(lemmas: Mapping[str, str]) -> tuple[dict[str, str], dict[str, str]]:
    """`lemmas` without `OWN_FIRST`'s forms, and those forms -> their
    lemma: the entry their card shows second."""
    return (
        {form: lemma for form, lemma in lemmas.items() if form not in OWN_FIRST},
        {form: lemma for form, lemma in lemmas.items() if form in OWN_FIRST},
    )


_NAME_KINDS = {
    "男子名": "a man's name",
    "男名": "a man's name",
    "男人名": "a man's name",
    "女子名": "a woman's name",
    "女名": "a woman's name",
    "姓氏": "a family name",
    "人名": "a person's name",
}
_NAMED = re.compile(
    f"(?:{'|'.join(_NAME_KINDS)})(?![单册])"
)  # not 候选人名单, a shortlist
_LABEL = re.compile(r"(?:a|adj|v|vt|vi|adv|abbr|prep|conj|pron|int|num|art)\.")


def name_kinds(meaning: str) -> list[str]:
    """What kinds of name a Chinese meaning says its word is, in English,
    in its order: "n. 詹姆斯（姓氏, 男子名）" is a family name, then a man's."""
    return list(dict.fromkeys(_NAME_KINDS[m] for m in _NAMED.findall(meaning)))


NOT_NAMES = frozenset(
    {"lense", "herpe", "raman", "bonker", "ande", "dicken", "witt", "courty", "jock"}
)
"""Rare surnames ECDICT makes a commoner word a form of: "lenses" is
lense's, (Lense)人名; "herpes" herpe's, "ramen" raman's, "bonkers"
bonker's, "andes" ande's, "dickens" dicken's, "witted" witt's, "courtier"
courty's. As names, those words would never be counted as heard. And
"jock", a word first (苏格兰高原地方的士兵), then 乔克（男子名）. Found by a
person among the commonest 50,000 words (polyglotic-hq 464)."""


def names(rows: Iterable[EcdictRow], lemmas: Mapping[str, str]) -> dict[str, str]:
    """Words ECDICT writes in lower case whose meaning is a person's name
    ("mary": 玛丽（女子名）) -> how the dictionary writes them: capitalised,
    so they're names (`core.lexicon.english`: never shown as unfamiliar,
    never counted as heard) and "Mary" finds its own entry. Their first
    line names them, as a noun; not a form of another word ("weeks":
    威克斯（姓氏）, and week's), nor a word ECDICT has capitalised too,
    nor one of `NOT_NAMES`. The entry keeps its ID (polyglotic-hq 464)."""
    rows = list(rows)
    written = {row.word for row in rows}
    return {
        row.word: row.word.capitalize()
        for row in rows
        if row.word.isalpha()
        and row.word.islower()
        and _NAMED.search(row.meanings[0])
        and not _LABEL.match(row.meanings[0])
        and row.word not in lemmas
        and row.word not in NOT_NAMES
        and row.word.capitalize() not in written
    }


NAMES = Path(__file__).parent / "english_names.txt"
_KIND = {"m": "男子名", "f": "女子名", "n": "人名"}


@dataclass(frozen=True)
class GivenName:
    """A name of `english_names.txt`: one ECDICT has only as a word."""

    name: str
    chinese: str
    kind: str  # m, f or n
    word_first: bool
    """Its lower-case word is common: a sentence's first word is the word."""

    @property
    def meaning(self) -> str:
        """Its Chinese meaning, as ECDICT writes a name's."""
        return f"n. {self.chinese}（{_KIND[self.kind]}）"


def read_names(path: Path = NAMES) -> list[GivenName]:
    """`english_names.txt`: "name | Chinese | m/f/n | name or word"."""
    found = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        name, chinese, kind, first = (part.strip() for part in line.split("|"))
        if kind not in _KIND or first not in ("name", "word"):
            raise ValueError(f"{path.name}: {line!r}")
        found.append(GivenName(name, chinese, kind, first == "word"))
    return found


_VERB = re.compile(r"(?:v|vt|vi|aux)\b")


def lemmas(rows: Iterable[EcdictRow], kept: set[str]) -> dict[str, str]:
    """Inflected form -> its lemma, for lemmas we keep: from each lemma's
    list of forms ("p:ran/i:running/3:runs"), then each form's own "0:",
    which wins unless another lemma that lists the form is the likelier
    one (`_likelier_listing`): ECDICT's "does" says "0:doe", and "do"
    lists it (polyglotic-hq 462). `NOT_FORMS` have none."""
    rows = list(rows)
    by_word = {row.word: row for row in rows}
    listed: dict[str, list[tuple[str, str]]] = {}
    for row in rows:
        if row.word in kept and row.lemma is None:
            for kind in FORM_KINDS:
                for form in row.exchange.get(kind, "").split(","):
                    if form and form != row.word:
                        listed.setdefault(form, []).append((row.word, kind))
    out = {form: lemmas[0][0] for form, lemmas in listed.items()}
    for row in rows:
        if row.lemma and row.lemma in kept:
            out[row.word] = (
                _likelier_listing(row, listed.get(row.word, []), by_word) or row.lemma
            )
    for form, lemma in MISSING_FORMS.items():
        if lemma in kept:
            out.setdefault(form, lemma)
    for word in NOT_FORMS:
        out.pop(word, None)
    return out


def _likelier_listing(
    form: EcdictRow, listings: Sequence[tuple[str, str]], rows: Mapping[str, EcdictRow]
) -> str | None:
    """The lemma that lists `form` and is likelier than its own "0:" one,
    if any: commoner in ECDICT's corpora, `form` its regular inflection of
    that kind, and a verb if the kind is a verb's. Its own stands when its
    Chinese meaning names it ("pall的过去式"). So "does" is do's (not doe's,
    the deer), "ruined" ruin's (not "ruine"'s), "routed" route's; "feeding"
    stays feed's though "fee" lists it (not fee's regular -ing), "tinged"
    tinge's (rarer "ting"), "bathed" bathe's ("bath" has no verb)."""
    own = form.lemma
    if own is None or any(f"{own}的" in m for m in form.meanings):
        return None
    likelier = [
        lemma
        for lemma, kind in listings
        if lemma != own
        and _corpus_rank(rows[lemma]) < _corpus_rank(rows[own])
        and form.word in regular_forms(lemma, kind)
        and (kind not in "pdi3" or any(_VERB.match(m) for m in rows[lemma].meanings))
    ]
    return min(likelier, key=lambda lemma: _corpus_rank(rows[lemma]), default=None)


def _corpus_rank(row: EcdictRow) -> float:
    """The better of its two corpus ranks; unranked last."""
    return min((r for r in (row.frq, row.bnc) if r > 0), default=float("inf"))


def regular_forms(lemma: str, kind: str) -> set[str]:
    """The forms English's regular spelling rules make of `lemma` for an
    exchange kind (`FORM_KINDS`): walks, watches, cities, analyses; walked,
    loved, stopped, panicked, carried; walking, making, stopping, dying;
    and the comparatives' and superlatives' likewise."""
    last = lemma[-1:]
    doubled = lemma + last  # stop: stopped, stopping
    if kind in ("s", "3"):
        found = {lemma + "s", lemma + "es"}
        if lemma.endswith("y"):
            found.add(lemma[:-1] + "ies")
        if lemma.endswith("is"):
            found.add(lemma[:-2] + "es")
        return found
    if kind in ("p", "d"):
        found = {lemma + "ed", doubled + "ed"}
        if last == "e":
            found.add(lemma + "d")
        if last == "c":
            found.add(lemma + "ked")
        if last == "y":
            found.add(lemma[:-1] + "ied")
        return found
    if kind == "i":
        found = {lemma + "ing", doubled + "ing"}
        if last == "e":
            found.add(lemma[:-1] + "ing")
        if last == "c":
            found.add(lemma + "king")
        if lemma.endswith("ie"):
            found.add(lemma[:-2] + "ying")
        return found
    stems = {lemma, lemma[:-1] if last == "e" else lemma, lemma + last}
    if lemma.endswith("y"):
        stems.add(lemma[:-1] + "i")
    return {stem + end for stem in stems for end in ("er", "est")}
