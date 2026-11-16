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
from collections.abc import Iterable, Iterator
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
            meanings = tuple(
                m.strip() for m in row["translation"].split("\\n") if m.strip()
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


def lemmas(rows: Iterable[EcdictRow], kept: set[str]) -> dict[str, str]:
    """Inflected form -> its lemma, for lemmas we keep: from each lemma's
    list of forms ("p:ran/i:running/3:runs"), then each form's own "0:",
    which wins."""
    rows = list(rows)
    out: dict[str, str] = {}
    for row in rows:
        if row.word in kept and row.lemma is None:
            for kind in FORM_KINDS:
                for form in row.exchange.get(kind, "").split(","):
                    if form and form != row.word:
                        out.setdefault(form, row.word)
    for row in rows:
        if row.lemma and row.lemma in kept:
            out[row.word] = row.lemma
    return out
