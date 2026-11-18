"""English's words with meanings in each learner's own language
(polyglotic-hq 448, 510; decision 0234): the meanings files riding with
ECDICT, `ecdict-<language>.meanings`, one per interface language, so a
Spanish speaker learning English reads Spanish, not Chinese.

    uv run python -m tools.dictionaries.english_pairs            # every language
    uv run python -m tools.dictionaries.english_pairs es ja vi   # some

Human-made meanings only, from two of Wiktionary's sources (CC BY-SA 4.0),
as kaikki.org extracted them on 2026-10-30:
1. **English Wiktionary's translation tables** (`KAIKKI_EN`): each sense
   of an English word, the words other languages say it with - one line
   per sense, "(noun) banco, banca". One source for every language.
2. **The language's own Wiktionary's English words** (`EDITIONS`): their
   definitions written in that language - "(verb) Correr". None for Hindi,
   Ukrainian or Filipino; Indonesian's and Malay's are small.

For each language, the source that has more of English's commonest
`COMMONEST` words is read first, and the other fills the words it hasn't
got (`PRIMARY`'s order, measured; see `main`'s report).

The order of an entry's lines is what makes its first click right
(polyglotic-hq 448: "Wiktionary's first sense isn't the commonest"):
- parts of speech in the order `ecdict-en.sqlite` has them - the one
  English text uses the word as most first (decision 0211);
- within each, the senses most languages have a translation for first
  (`Sense.weight`): a sense the world needs words for is a common one -
  "bank" opens on the institution, not the embankment, and "go" on moving,
  not on making a sound, whatever order the page has them in;
- an edition's lines likewise: of its first part of speech, the line that
  says the tables' first sense's words first ("ngân hàng").

Each line starts with its part of speech, as `ecdict-en.sqlite`'s and the
packs' do. An entry neither source has isn't in the file: the card shows
the dictionary's own (English). A word's forms ("ran") have no lines of
their own: the card opens on their lemma's entry.
"""

from __future__ import annotations

import argparse
import gzip
import json
import re
import sqlite3
import sys
import time
import unicodedata
from collections import defaultdict
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from polyglotic_desktop.adapters.meanings_file import SUFFIX, write_meanings
from tools.dictionaries import wordfreq_ranks
from tools.dictionaries.sources import (
    KAIKKI_EN,
    WIKTIONARY_EDITIONS,
    WORDFREQ,
    Source,
    fetch,
)

REPO = Path(__file__).resolve().parents[2]
LANGUAGES = (
    *("es", "pt", "ja", "ko", "vi", "id", "tr", "ru", "fr", "de"),
    *("it", "hi", "th", "pl", "uk", "nl", "cs", "ms", "fil"),
)
"""The interface languages English's meanings are made in, in 448's order
(English learners' demand first, then our interface's languages)."""
TRANSLATION_CODES = {"fil": ("fil", "tl")}
"""The codes English Wiktionary's tables give a language by, where they
aren't its own: Filipino is mostly under Tagalog's."""
COMMONEST = 5000
"""Coverage is measured over English's this many commonest words."""
MAX_LINES = 6  # per entry: the card shows three; the rest is size
MAX_WORDS = 3  # per translation line
LONGEST = 110  # characters, an edition's line
LEFT_OUT_TAGS = frozenset({"obsolete", "archaic", "rare", "nonstandard", "misspelling"})
FORM_TAGS = frozenset({"form-of", "alt-of", "abbreviation", "misspelling"})
POS = {
    "noun": "noun",
    "verb": "verb",
    "adj": "adj",
    "adv": "adv",
    "pron": "pron",
    "prep": "prep",
    "conj": "conj",
    "det": "det",
    "article": "article",
    "intj": "intj",
    "num": "num",
    "particle": "particle",
    "name": "name",
    "phrase": "phrase",
    "prep_phrase": "phrase",
    "contraction": "phrase",
    "abbrev": "abbrev",
}
"""kaikki's parts of speech as the card names them; others are left out
(affixes, symbols, characters)."""
_POS_OF_LINE = re.compile(r"^\(([^)]*)\) ")
_ARABIC = re.compile("[\u0600-\u06ff]")
"""Arabic script, which none of the languages here writes: Malay's tables
give its Jawi spelling beside its Rumi one."""
_CN_POS = re.compile(r"^(?:\[[^\]]*\]\s*|[a-z]+\.\s*)+")
"""ECDICT's part of speech before a line of meanings: "n. ", "vt. ", "[医] "."""
_CN_ITEMS = re.compile(r"[,;，；]\s*")
_CN_PARTS = {
    **dict.fromkeys(("n",), "noun"),
    **dict.fromkeys(("v", "vt", "vi", "aux"), "verb"),
    **dict.fromkeys(("a", "adj"), "adj"),
    **dict.fromkeys(("ad", "adv"), "adv"),
    "prep": "prep",
    "conj": "conj",
    "pron": "pron",
    "num": "num",
    "int": "intj",
    "interj": "intj",
    "art": "article",
}
"""ECDICT's parts of speech as the card names them."""


def _cn_part(line: str) -> str:
    """The part of speech an ECDICT line of meanings starts with ("vt. 藏"),
    or "" (a field's line: "[计] 隐藏")."""
    start = re.match(r"([a-z]+)\.", line)
    return _CN_PARTS.get(start.group(1), "") if start else ""


_QUALIFIED = re.compile(r"\((disused|obsolete|archaic|dated|rare|dialectal)\)")
"""A table's word marked out of use in a note of its own: "et (disused)"."""
ALSO = {"det": "adj", "num": "noun"}
"""Wiktionary's parts of speech `ecdict-en.sqlite` files under another:
WordNet's quantifiers are adjectives (any, some, every), its numbers nouns."""
_ASIDE = re.compile(r"[。;；]?\s*\bcf\.")
"""Where an edition's definition goes on to a cross-reference: "走る。cf.walk"."""
_TRAILING = " .。;；,，:："


@dataclass(frozen=True)
class Headword:
    """An ECDICT entry as `ecdict-en.sqlite` has it."""

    entry_id: str
    word: str
    rank: int | None
    parts: tuple[str, ...]
    """Its parts of speech in its English meanings' order."""
    form_only: bool
    """Every meaning says what it's a form of ("past tense of run")."""
    card: str = ""
    """The entry its card opens on (`EnglishDictionary.lookup`): its
    lemma's, for a form ECDICT lists one of ("told": tell); else its own."""
    chinese: tuple[tuple[str, str], ...] = ()
    """ECDICT's own Chinese meanings, one word or phrase each with its line's
    part of speech, in its order - the commonest sense first ("n. 账单,
    清单, 钞票, 鸟嘴" for bill)."""


@dataclass
class Sense:
    """One sense's line from one source: its part of speech, what it
    means in English (a table's heading; an edition has none), the words,
    and how many languages the table has words in for it (an edition's: 0)."""

    pos: str
    english: str
    text: str
    weight: int = 0
    chinese: tuple[str, ...] = ()
    """The table's Mandarin words for the sense (an edition's: none)."""


@dataclass
class Found:
    """Each headword's senses from one source, in the page's order."""

    senses: dict[str, list[Sense]] = field(default_factory=lambda: defaultdict(list))


_FORM = re.compile(
    r"^(past tense|past participle|present participle|plural|comparative|"
    r"superlative|third-person singular|.* form) of ",
    re.IGNORECASE,
)


def read_english(path: Path, chinese: Path | None = None) -> list[Headword]:
    """`ecdict-en.sqlite`'s entries, commonest first (unranked last), each
    with the entry its card opens on and, from `chinese` (`ecdict.sqlite`:
    the same entries), ECDICT's Chinese meanings."""
    in_chinese: dict[str, tuple[tuple[str, str], ...]] = {}
    if chinese is not None:
        db = sqlite3.connect(f"{chinese.resolve().as_uri()}?mode=ro", uri=True)
        try:
            for entry_id, meanings in db.execute("SELECT id, meanings FROM entries"):
                in_chinese[entry_id] = tuple(
                    (_cn_part(line), item.strip())
                    for line in (meanings or "").split("\n")
                    for item in _CN_ITEMS.split(_CN_POS.sub("", line))
                    if item.strip()
                )
        finally:
            db.close()
    db = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    try:
        rows = db.execute(
            "SELECT id, headword, frequency_rank, meanings FROM entries "
            "ORDER BY frequency_rank IS NULL, frequency_rank, n"
        ).fetchall()
        lemmas = dict(db.execute("SELECT form, lemma FROM lemmas").fetchall())
    finally:
        db.close()
    first_id: dict[str, str] = {}
    for entry_id, word, _, _ in rows:
        first_id.setdefault(word, entry_id)
    out = []
    for entry_id, word, rank, meanings in rows:
        lines = meanings.split("\n") if meanings else []
        parts = tuple(
            dict.fromkeys(
                m.group(1) for line in lines if (m := _POS_OF_LINE.match(line))
            )
        )
        form_only = bool(lines) and all(
            _FORM.match(_POS_OF_LINE.sub("", line)) for line in lines
        )
        card = first_id.get(lemmas.get(word, ""), entry_id)
        out.append(
            Headword(
                entry_id,
                word,
                rank,
                parts,
                form_only,
                card,
                in_chinese.get(entry_id, ()),
            )
        )
    return out


def _lines(path: Path) -> Iterator[str]:
    with gzip.open(path, "rt", encoding="utf-8") as text:
        yield from text


def _clean(word: str) -> str:
    return " ".join(word.split()).strip(_TRAILING)


def read_tables(
    path: Path,
    words: Iterable[str],
    languages: Sequence[str],
    frequency: Mapping[str, Mapping[str, float]] | None = None,
) -> dict[str, Found]:
    """English Wiktionary's translation tables for `words`: per language,
    each word's senses in the page's order (entry-level tables, then those
    wiktextract placed on a sense), a line of at most `MAX_WORDS` words
    each (`commonest_first`, by the language's `frequency`). Obsolete,
    archaic and rare words are left out."""
    frequency = frequency or {}
    wanted = set(words)
    codes = {
        code: language
        for language in languages
        for code in TRANSLATION_CODES.get(language, (language,))
    }
    found = {language: Found() for language in languages}
    for line in _lines(path):
        if '"translations"' not in line:
            continue
        entry = json.loads(line)
        word, pos = entry.get("word"), POS.get(entry.get("pos", ""))
        if word not in wanted or pos is None or entry.get("lang_code") != "en":
            continue
        items = list(entry.get("translations") or ())
        for sense in entry.get("senses") or ():
            items += sense.get("translations") or ()
        groups: dict[tuple[str, str], list[str]] = {}
        weights: dict[str, set[str]] = defaultdict(set)
        mandarin: dict[str, set[str]] = defaultdict(set)
        for item in items:
            code = item.get("lang_code") or item.get("code") or ""
            weights[item.get("sense") or ""].add(code)
            if code in ("cmn", "zh") and item.get("word"):
                mandarin[item.get("sense") or ""].add(item["word"])
            language = codes.get(code)
            text = _clean(item.get("word") or "")
            if (
                language is None
                or not text
                or LEFT_OUT_TAGS & set(item.get("tags") or ())
                or len(text) > 40
                or _QUALIFIED.search(text)
                or _ARABIC.search(text)
            ):
                continue
            said = groups.setdefault((language, item.get("sense") or ""), [])
            if text not in said:
                said.append(text)
        for (language, english), said in groups.items():
            said = commonest_first(said, frequency.get(language, {}))
            found[language].senses[word].append(
                Sense(
                    pos,
                    english,
                    ", ".join(said[:MAX_WORDS]),
                    len(weights[english]),
                    tuple(sorted(mandarin[english])),
                )
            )
    return found


def commonest_first(words: Sequence[str], frequency: Mapping[str, float]) -> list[str]:
    """A sense's words, the language's commonest first (wordfreq's), and a
    plain word wordfreq hasn't got left out where one it has is there:
    "correr, apeonar" is "correr"; "cosa, volancheje" is "cosa". A word
    with alternatives or a note counts as its first word ("necesitar/precisar
    (de)" as necesitar), a phrase as its first; a language without a list
    keeps the table's order."""
    if not frequency:
        return list(words)

    def often(word: str) -> float:
        plain = _STRESS.sub("", unicodedata.normalize("NFD", word.lower()))
        head = _ALTERNATIVE.split(unicodedata.normalize("NFC", plain), 1)[0].split()
        return frequency.get(head[0], 0.0) if head else 0.0

    said = sorted(words, key=lambda w: -often(w))
    if any(often(w) for w in said):
        said = [w for w in said if often(w) or not _PLAIN.fullmatch(w)]
    return said


_ALTERNATIVE = re.compile(r"[/(]")
_STRESS = re.compile("(?<=[\u0400-\u04ff])[\u0300\u0301]")
"""A stress mark on a Cyrillic letter (Russian's and Ukrainian's tables
write хоте́ть; wordfreq хотеть)."""
_PLAIN = re.compile(r"\w+")


_WORD_AT_START = re.compile(r'^\{"word": "((?:[^"\\]|\\.)*)"')


def read_edition(path: Path, words: Iterable[str]) -> Found:
    """A language's own Wiktionary's English words among `words`: each
    sense's first definition, in that language, in the page's order -
    leaving out forms, alternative spellings and obsolete senses."""
    wanted = set(words)
    found = Found()
    for line in _lines(path):
        start = _WORD_AT_START.match(line)
        if start is None or '"lang_code": "en"' not in line:
            continue
        if json.loads(f'"{start.group(1)}"') not in wanted:
            continue
        entry = json.loads(line)
        word, pos = entry["word"], POS.get(entry.get("pos", ""))
        if pos is None or entry.get("lang_code") != "en":
            continue
        for sense in entry.get("senses") or ():
            tags = set(sense.get("tags") or ())
            if (
                tags & (FORM_TAGS | LEFT_OUT_TAGS)
                or sense.get("form_of")
                or sense.get("alt_of")
                or not sense.get("glosses")
            ):
                continue
            text = _short(_clean(_ASIDE.split(sense["glosses"][-1])[0]))
            if text:
                found.senses[word].append(Sense(pos, "", text))
    return found


def _short(text: str) -> str:
    """At most `LONGEST` characters, cut at a word or a comma."""
    if len(text) <= LONGEST:
        return text
    cut = text[:LONGEST]
    for mark in ("; ", "；", ", ", "，", " "):
        if mark in cut:
            return cut[: cut.rindex(mark)].rstrip(_TRAILING) + "…"
    return cut + "…"


def ordered(senses: Sequence[Sense], headword: Headword) -> list[Sense]:
    """`senses` with their parts of speech in `headword`'s order (others
    after, as the page has them), and within each, first the senses in
    ECDICT's order - a table's sense whose Mandarin words ECDICT's Chinese
    meanings have, the earlier the commoner (`in_ecdict`: "bill" is an
    invoice, then a banknote, then a beak; two it says alike in the page's
    order) - then those with words in the most languages (`Sense.weight`);
    an edition's keep the page's order."""
    rank = {pos: n for n, pos in enumerate(headword.parts)}
    for pos, same in ALSO.items():
        if pos not in rank and same in rank:
            rank[pos] = rank[same]
    unsaid = len(headword.chinese)

    def key(n: int) -> tuple[int, int, int]:
        sense = senses[n]
        said = in_ecdict(sense, headword)
        # two senses ECDICT says alike (隐藏: hide, hide oneself) keep the
        # page's order; those it doesn't say, the most languages' first
        return (
            rank.get(sense.pos, len(rank)),
            said,
            (n if said < unsaid else -sense.weight),
        )

    return [senses[n] for n in sorted(range(len(senses)), key=key)]


def in_ecdict(sense: Sense, headword: Headword) -> int:
    """Where ECDICT's Chinese meanings of `sense`'s part of speech first say
    it (its Mandarin words, or one inside the other: 钞票, 纸币) - hide's
    躲藏处, a hiding place, isn't hiding oneself; past them all if they
    don't."""
    parts = {sense.pos, ALSO.get(sense.pos, sense.pos), ""}
    for n, (pos, item) in enumerate(headword.chinese):
        if pos not in parts:
            continue
        for word in sense.chinese:
            if word == item or (
                len(word) > 1 and len(item) > 1 and (word in item or item in word)
            ):
                return n
    return len(headword.chinese)


def agreeing(senses: Sequence[Sense], first: Sense | None) -> list[Sense]:
    """An edition's senses (`ordered` already) with, of the first part of
    speech, the first that has one of `first`'s words - the table's
    commonest sense - moved first: "bank" in Vietnamese opens on "ngân
    hàng", not the embankment its page lists first."""
    out = list(senses)
    if not out or first is None:
        return out
    words = [w.strip().lower() for w in first.text.split(",") if w.strip()]
    for n, sense in enumerate(out):
        if sense.pos != out[0].pos:
            break
        if any(w in sense.text.lower() for w in words):
            out.insert(0, out.pop(n))
            break
    return out


def lines_for(
    headword: Headword, tables: Found, edition: Found | None, primary: str
) -> tuple[str, ...]:
    """The entry's lines in one language: from the `primary` source
    ("tables" or "edition") if it has the word, else the other's."""
    from_tables = ordered(tables.senses.get(headword.word, ()), headword)
    from_edition = (
        agreeing(
            ordered(edition.senses.get(headword.word, ()), headword),
            from_tables[0] if from_tables else None,
        )
        if edition is not None
        else []
    )
    sources = (
        (from_tables, from_edition)
        if primary == "tables"
        else (from_edition, from_tables)
    )
    chosen = next((s for s in sources if s), [])
    shown: list[str] = []
    for sense in chosen:
        line = f"({sense.pos}) {sense.text}"
        if line not in shown:
            shown.append(line)
    return tuple(shown[:MAX_LINES])


def coverage(headwords: Sequence[Headword], rows: Mapping[str, Sequence[str]]) -> float:
    """The share of English's `COMMONEST` commonest words (each rank's
    first entry; not a lone letter) whose card opens on an entry with
    lines in `rows` - a form's on its lemma's ("told": tell)."""
    first: dict[int, Headword] = {}
    for h in headwords:
        if h.rank and h.rank <= COMMONEST and len(h.word) > 1:
            first.setdefault(h.rank, h)
    counted = list(first.values())
    covered = sum(1 for h in counted if rows.get(h.card or h.entry_id))
    return covered / max(1, len(counted))


def info(language: str, used: Sequence[Source], share: float) -> dict[str, str]:
    return {
        "dictionary": "ecdict",
        "language": "en",
        "meanings_language": language,
        "licence": "CC BY-SA 4.0",
        "sources": "; ".join(f"{s.title} ({s.version})" for s in used),
        "commonest": str(COMMONEST),
        "share_of_commonest": f"{share:.4f}",
        "credits": " ".join(s.notice for s in used),
    }


def build(
    headwords: Sequence[Headword],
    tables: Mapping[str, Found],
    editions: Mapping[str, Found],
    languages: Sequence[str],
    out: Path,
) -> dict[str, dict[str, object]]:
    """Writes `ecdict-<language>.meanings` for each language; what each holds."""
    stats: dict[str, dict[str, object]] = {}
    for language in languages:
        edition = editions.get(language)
        shares = {}
        for primary in ("tables", "edition") if edition is not None else ("tables",):
            rows = {
                h.entry_id: lines
                for h in headwords
                if (lines := lines_for(h, tables[language], edition, primary))
            }
            shares[primary] = (coverage(headwords, rows), rows)
        alone = {
            "tables": tables[language],
            **({"edition": edition} if edition else {}),
        }
        only = {
            name: coverage(
                headwords,
                {
                    h.entry_id: ("x",)
                    for h in headwords
                    if not h.form_only and h.word in source.senses
                },
            )
            for name, source in alone.items()
        }
        primary = max(only, key=lambda name: (only[name], name == "tables"))
        share, rows = shares[primary]
        used = [KAIKKI_EN] + (
            [WIKTIONARY_EDITIONS[language]] if edition is not None else []
        )
        path = out / f"ecdict-{language}{SUFFIX}"
        write_meanings(
            path,
            {**info(language, used, share), "read_first": primary},
            ((entry_id, lines, False) for entry_id, lines in rows.items()),
        )
        stats[language] = {
            "file": path.name,
            "entries": len(rows),
            f"of the commonest {COMMONEST}": f"{100 * share:.1f} %",
            "tables alone": f"{100 * only['tables']:.1f} %",
            "edition alone": (
                f"{100 * only['edition']:.1f} %" if "edition" in only else "-"
            ),
            "read first": primary,
            "size": f"{path.stat().st_size / 1e6:.2f} MB",
        }
    return stats


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("languages", nargs="*", help=f"some of {' '.join(LANGUAGES)}")
    parser.add_argument(
        "--sources", type=Path, default=REPO / "build" / "dictionary-sources"
    )
    parser.add_argument(
        "--dictionaries",
        type=Path,
        default=REPO / "build" / "dictionaries",
        help="where `ecdict-en.sqlite` is (`tools.dictionaries.build`)",
    )
    parser.add_argument(
        "--out", type=Path, default=REPO / "build" / "dictionaries" / "meanings"
    )
    args = parser.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    languages = args.languages or list(LANGUAGES)
    if set(languages) - set(LANGUAGES):
        parser.error(f"not one of {' '.join(LANGUAGES)}")
    headwords = read_english(
        args.dictionaries / "ecdict-en.sqlite", args.dictionaries / "ecdict.sqlite"
    )
    words = {h.word for h in headwords}
    started = time.perf_counter()
    wheel = fetch(WORDFREQ, args.sources)
    frequency = {}
    for language in languages:
        try:
            frequency[language] = wordfreq_ranks.frequencies(wheel, language)
        except KeyError:  # wordfreq has no list (Thai): the table's order
            continue
    tables = read_tables(fetch(KAIKKI_EN, args.sources), words, languages, frequency)
    print(f"translation tables read ({time.perf_counter() - started:.0f} s)")
    editions = {}
    for language in languages:
        source = WIKTIONARY_EDITIONS.get(language)
        if source is not None:
            started = time.perf_counter()
            editions[language] = read_edition(fetch(source, args.sources), words)
            print(f"{language} edition read ({time.perf_counter() - started:.0f} s)")
    args.out.mkdir(parents=True, exist_ok=True)
    for language, stats in build(
        headwords, tables, editions, languages, args.out
    ).items():
        print(f"English in {language}:")
        for key, value in stats.items():
            print(f"  {key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
