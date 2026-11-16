"""Word links "past what you know", measured on real captions (polyglotic-hq
338): how many of a caption's words are linked, and every linked word the
learner's line says they know, with why.

    uv run python -m tools.links_measured [zh en ru] [--lines 500 1000 ...]
        [--dictionaries build/dictionaries] [--pack ru=PATH] [--show 15]

The captions: 100 FLEURS sentences per language, the same in each -
`tools/captions_probe/<code>.txt` for Chinese and English, the coverage
probe's `tools/dictionaries/probe/<code>.txt` for the rest (read speech,
not conversation - see their READMEs).

Each sentence is linked as the server links it (`server_links`: its word
split - Chinese by the same rule as the desktop's, other text in runs of
letters and digits - each word a link of its own, grammar words left out,
key or minor by the server's lists; polyglotic-server
`core/translation/links.py`, read 2026-11-15). Real alignments join some
neighbouring words into one link and leave others out; a measure needs no
aligner this way, and each word is judged on its own - as a learner reads
the underline.

Then the caption window's own marks (`CaptionMarks`, the real path: the
learner's tools, their line and choices, the word split, the dictionary,
`views.links`) for a learner of that language with "past what you know",
who knows the `line` most common words - and once more with no level set
(`--lines` takes `start`: the line every learner is estimated at until they
set one, and every language added since 323 starts with). A basic
dictionary's language (`--pack`) is learned beside Chinese, the main one.

For each line it says how many links are drawn, and lists each drawn link
whose word is placed inside the line (`place`: its frequency rank, or its
syllabus level's size where that's smaller) with why it was drawn - the
target is none. Then the drawn links past the line, those whose words the
dictionary hasn't got, and those it can't place. Caption text is FLEURS's
public sentences, never a learner's.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from PySide6.QtGui import QTextCharFormat

from polyglotic_desktop.adapters.sqlite_dictionary import SqliteDictionary
from polyglotic_desktop.adapters.sqlite_learning import SqliteLearningStore
from polyglotic_desktop.core.learning.levels import (
    UNKNOWN_LEVEL_LINKS_FROM,
    KnownLine,
    LanguageChoices,
    LinkChoice,
    place,
)
from polyglotic_desktop.core.learning.vocabulary import Vocabulary
from polyglotic_desktop.core.lexicon.basic import BasicDictionary
from polyglotic_desktop.core.lexicon.chinese import ChineseDictionary, is_han
from polyglotic_desktop.core.lexicon.english import EnglishDictionary
from polyglotic_desktop.core.lexicon.entries import (
    DEFAULT_CHINESE_SCHEME,
    ENGLISH_FREQUENCY,
    SCHEMES,
)
from polyglotic_desktop.core.listening.captions import Language
from polyglotic_desktop.core.listening.display import (
    CaptionRow,
    LinkedWords,
    RowKind,
    WordLinks,
)
from polyglotic_desktop.core.listening.sources import SourceId
from polyglotic_desktop.core.shared import EntryFacts, EntryId, WordInLine
from polyglotic_desktop.ui.learning import LearningTools
from polyglotic_desktop.ui_next.caption_layout import LINK_MARK
from polyglotic_desktop.ui_next.caption_marks import CaptionMarks
from polyglotic_desktop.ui_next.views.captions import Line

PROBES = (
    Path(__file__).parent / "captions_probe",
    Path(__file__).parent / "dictionaries" / "probe",
)
"""Where each language's sentences are: Chinese and English in
`captions_probe`, the rest beside the coverage probe (the same sentences:
a change to that folder rebuilds every pack in CI)."""
REPO = Path(__file__).resolve().parents[1]
LINES: tuple[int | str, ...] = (500, 1000, 2000, 5000, "start")
START = "start"
"""No level set: the line the learner is estimated at (`KnownLine.starting`)."""

# The server's word split and lists (polyglotic-server core/translation/links.py)
_WORD = re.compile(r"[^\W_]+(?:['’][^\W_]+)*")
_GRAMMAR_HAN = frozenset("的了吗呢吧啊呀嘛哦嗯呃哎哈")
_GRAMMAR_EN = frozenset({"a", "an", "the", "of", "to", "s"})
_MINOR_HAN = frozenset("就是这那个也都还在有和跟把被给让对很太我你他她它们说然后其实")
_MINOR_EN = frozenset(
    [
        "a",
        "an",
        "the",
        "to",
        "of",
        "it",
        "its",
        "is",
        "am",
        "are",
        "was",
        "were",
        "be",
        "been",
        "will",
        "would",
        "have",
        "has",
        "and",
        "or",
        "in",
        "on",
        "at",
        "for",
        "with",
        "this",
        "that",
        "i",
        "you",
        "me",
        "my",
        "your",
        "s",
        "so",
        "just",
        "like",
        "do",
    ]
)


def _han(word: str) -> bool:
    return any(is_han(c) for c in word)


def _grammar(word: str) -> bool:
    if _han(word):
        return all(c in _GRAMMAR_HAN for c in word if is_han(c))
    return word.lower() in _GRAMMAR_EN


def _minor(word: str) -> bool:
    if _han(word):
        return all(c in _GRAMMAR_HAN or c in _MINOR_HAN for c in word if is_han(c))
    return word.lower() in _GRAMMAR_EN or word.lower() in _MINOR_EN


def server_links(
    text: str, split: Callable[[str], list[tuple[int, int]]]
) -> tuple[LinkedWords, ...]:
    """`text`'s words as the server links them, each a link of its own:
    Chinese runs by `split` (the desktop's word split, which the server's
    follows rule for rule), other text in runs of letters and digits;
    grammar words never linked; minor words not key."""
    spans: list[tuple[int, int]] = []
    i, n = 0, len(text)
    while i < n:
        j = i
        if is_han(text[i]):
            while j < n and is_han(text[j]):
                j += 1
            spans += [(i + a, i + b) for a, b in split(text[i:j])]
        else:
            while j < n and not is_han(text[j]):
                j += 1
            spans += [(i + m.start(), i + m.end()) for m in _WORD.finditer(text[i:j])]
        i = j
    kept = [(a, b) for a, b in spans if not _grammar(text[a:b])]
    return tuple(
        LinkedWords(a, b, k, not _minor(text[a:b])) for k, (a, b) in enumerate(kept)
    )


@dataclass(frozen=True)
class Inside:
    """A drawn link whose word is placed inside the line."""

    word: str
    place: int
    why: str


@dataclass
class Measured:
    """One language at one line."""

    code: str
    line: int | str
    links: int = 0
    drawn: int = 0
    inside: list[Inside] = field(default_factory=list)
    no_entry: Counter[str] = field(default_factory=Counter)
    no_place: Counter[str] = field(default_factory=Counter)
    past: dict[str, int] = field(default_factory=dict)

    @property
    def share(self) -> float:
        return self.drawn / self.links if self.links else 0.0

    def __str__(self) -> str:
        known = f"{self.line:,}" if isinstance(self.line, int) else "no level set"
        return (
            f"{self.code} at {known}: {self.drawn} of {self.links} words linked "
            f"({100 * self.share:.0f} %); {len(self.inside)} inside the line"
        )


def _why(facts: EntryFacts, words: Sequence[WordInLine], word: str) -> str:
    """Why a word placed inside the line was linked, as far as can be told."""
    said = []
    if facts.is_name:
        said.append("a name")
    if len(words) > 1 or (words and words[0].end - words[0].start != len(word)):
        said.append("split differently from the link")
    return ", ".join(said) or "the line doesn't know it"


def _level_words(scheme: str, level: int) -> int | None:
    found = SCHEMES.get(scheme)
    return found.words_at(level) if found else None


def learner_tools(
    dictionary: ChineseDictionary | EnglishDictionary,
    scheme: str,
    basic: Mapping[str, BasicDictionary],
) -> LearningTools:
    def facts(entry_id: EntryId, scheme: str) -> EntryFacts | None:
        return dictionary.facts(entry_id, scheme)

    if isinstance(dictionary, ChineseDictionary):
        dictionary.prepare()
    vocabulary = Vocabulary(
        SqliteLearningStore(":memory:"), facts, scheme, level_words=_level_words
    )
    return LearningTools(vocabulary, dictionary, basic=dict(basic))


def measure(
    code: str,
    sentences: Sequence[str],
    make_tools: Callable[[], LearningTools],
    lines: Sequence[int | str] = LINES,
) -> list[Measured]:
    """Each line's measure of `sentences` in `code`, for a learner whose
    tools `make_tools` makes afresh (its main language's; `code` learned,
    with "past what you know")."""
    language = Language(code)
    past = LanguageChoices(links=LinkChoice.PAST_KNOWN)
    found = []
    for known in lines:
        tools = make_tools()
        ours = tools.of(language)
        vocabulary = ours.vocabulary
        basic = tools.is_basic(language)
        if basic:  # no level kept: links start where the learner chose
            at = known if isinstance(known, int) else None
            past = LanguageChoices(links=LinkChoice.PAST_KNOWN, links_from=at)
        elif isinstance(known, int):
            vocabulary.set_known_words(known)
        tools.set_choices(
            past if tools.language == code else LanguageChoices(), {code: past}
        )
        line = vocabulary.line or KnownLine.starting(vocabulary.scheme)
        words_known = (
            known
            if isinstance(known, int)
            else UNKNOWN_LEVEL_LINKS_FROM
            if basic
            else line.words_known(_level_words)
        )
        chinese = (
            tools.dictionary
            if isinstance(tools.dictionary, ChineseDictionary)
            else None
        )
        split = chinese.split if chinese else _each_character
        rows = [
            CaptionRow(
                text, RowKind.ORIGINAL, language, 0, True, server_links(text, split)
            )
            for text in sentences
        ]
        marks = CaptionMarks(tools)
        marks.set_look(WordLinks.COLOURS, marks.introductions)
        result = Measured(code, known)
        for n, row in enumerate(rows):
            caption = Line(n, SourceId("probe"), False, (row,), False, False, _AT)
            drawn = {
                (start, end)
                for start, end, format_ in marks(caption, 0)
                if isinstance(format_, QTextCharFormat)
                and format_.hasProperty(LINK_MARK)
            }
            words = (
                tools.words_in(row.text, language)
                if ours.learns(language)
                else (
                    tools.basic[code].words_in(row.text, "")
                    if code in tools.basic
                    else []
                )
            )
            for link in row.links:
                result.links += 1
                if (link.start, link.end) not in drawn:
                    continue
                result.drawn += 1
                word = row.text[link.start : link.end]
                under = [w for w in words if w.start < link.end and link.start < w.end]
                places = [p for p in (place(w.entry) for w in under) if p is not None]
                if not under:
                    result.no_entry[word] += 1
                elif not places:
                    result.no_place[word] += 1
                elif words_known is not None and max(places) <= words_known:
                    first = under[0].entry
                    result.inside.append(
                        Inside(word, max(places), _why(first, under, word))
                    )
                else:
                    result.past[word] = min(places)
        found.append(result)
    return found


_AT = datetime(2026, 11, 15, tzinfo=UTC)


def _each_character(run: str) -> list[tuple[int, int]]:
    """The server's split of Chinese without a word list."""
    return [(k, k + 1) for k in range(len(run))]


def sentences(code: str) -> list[str]:
    path = next(p / f"{code}.txt" for p in PROBES if (p / f"{code}.txt").is_file())
    return [s for s in path.read_text("utf-8").splitlines() if s]


def report(found: Sequence[Measured], show: int) -> str:
    out = []
    for m in found:
        out.append(str(m))
        for inside, n in Counter(m.inside).most_common(show):
            out.append(
                f"    inside: {inside.word} x{n} (place {inside.place}: {inside.why})"
            )
        if m.no_entry:
            words = ", ".join(f"{w} x{n}" for w, n in m.no_entry.most_common(show))
            out.append(f"    not in the dictionary: {m.no_entry.total()} ({words})")
        if m.no_place:
            words = ", ".join(f"{w} x{n}" for w, n in m.no_place.most_common(show))
            out.append(f"    no place: {m.no_place.total()} ({words})")
        if m.past:
            commonest = sorted(m.past, key=m.past.__getitem__)[:show]
            words = ", ".join(f"{w} ({m.past[w]:,})" for w in commonest)
            out.append(f"    past the line, the commonest: {words}")
    return "\n".join(out)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m tools.links_measured")
    parser.add_argument("codes", nargs="*", default=["zh", "en"])
    parser.add_argument(
        "--dictionaries", type=Path, default=REPO / "build/dictionaries"
    )
    parser.add_argument("--pack", action="append", default=[], help="code=PATH")
    parser.add_argument("--lines", nargs="*", default=[str(n) for n in LINES])
    parser.add_argument("--show", type=int, default=15)
    args = parser.parse_args(argv)
    lines = [n if n == START else int(n) for n in args.lines]
    packs = dict(p.split("=", 1) for p in args.pack)
    from polyglotic_desktop.main import open_pack  # the app's own

    for code in args.codes:
        if code == "en":
            dictionary: ChineseDictionary | EnglishDictionary = EnglishDictionary(
                SqliteDictionary(args.dictionaries / "ecdict.sqlite")
            )
            scheme, basic = ENGLISH_FREQUENCY.id, {}
        else:
            dictionary = ChineseDictionary(
                SqliteDictionary(args.dictionaries / "cedict.sqlite")
            )
            scheme = DEFAULT_CHINESE_SCHEME.id
            basic = (
                {code: open_pack(Path(packs[code]), code)[0]} if code != "zh" else {}
            )

        def make(
            dictionary: ChineseDictionary | EnglishDictionary = dictionary,
            scheme: str = scheme,
            basic: Mapping[str, BasicDictionary] = basic,
        ) -> LearningTools:
            return learner_tools(dictionary, scheme, basic)

        print(report(measure(code, sentences(code), make, lines), args.show))
    return 0


if __name__ == "__main__":
    sys.exit(main())
