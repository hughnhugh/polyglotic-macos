"""Writes `core/lexicon/spoken_ranks.py`: how often Mandarin's and English's
words are said, beside how often the packs say they are written
(polyglotic-hq 491; desktop decision 0227).

The packs rank words by written text (Chinese by jieba's counts, English by
wordfreq's blend), which places everyday speech far too rare: 嗯 at 3,570,
就是说 at 11,167, 谢谢 at 6,361, "um" past 5,000 (polyglotic-hq 485). Our
curriculum's conversation words (`core.learning.theme`) must never light
those. So each word gets its rank in speech too: its place among the words
OpenSubtitles 2018 counts (FrequencyWords' lists, the same source and pin
as Russian's ranks, polyglotic-hq 325) - separate data, never the
conversations the theme is measured on.

Kept: the `TOP` commonest spoken words that the pack has, are not names,
and that the pack ranks rarer than speech does (a word ranked at least as
common in writing gains nothing: its written place is the smaller). English
words are counted by the pack's lemma, as the app counts them.

    uv run python -m tools.spoken_ranks        (the packs in build/dictionaries)
"""

from __future__ import annotations

import re
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

from tools.dictionaries.sources import Source, fetch

ROOT = Path(__file__).resolve().parents[1]
PACKS = ROOT / "build" / "dictionaries"
SOURCES = ROOT / "build" / "sources"
OUT = ROOT / "src" / "polyglotic_desktop" / "core" / "lexicon" / "spoken_ranks.py"

TOP = 5000
"""Spoken ranks kept: a line past 5,000 words is past nearly every
learner's; there the subtitles' own bias (police, guns, "sir") grows."""

_PIN = "525f9b560de45753a5ea01069454e72e9aa541c6"
_NOTICE = (
    "FrequencyWords by Hermit Dave (content CC BY-SA 4.0; code MIT), word "
    "counts from OPUS OpenSubtitles 2018 (P. Lison, J. Tiedemann and M. "
    "Kouylekov, LREC 2018, https://opus.nlpl.eu/), whose subtitles come from "
    "http://www.opensubtitles.org/"
)


def _source(code: str, path: str, sha256: str) -> Source:
    return Source(
        name=f"frequencywords-{code}",
        title=f"FrequencyWords: {code}, OpenSubtitles 2018 (the 50,000 commonest words)",
        version=f"commit {_PIN} (2022-02-07), content/2018/{path}",
        url=(
            "https://raw.githubusercontent.com/hermitdave/FrequencyWords/"
            f"{_PIN}/content/2018/{path}"
        ),
        sha256=sha256,
        filename=f"frequencywords-{code}_50k-{_PIN[:7]}.txt",
        homepage="https://github.com/hermitdave/FrequencyWords",
        licence="CC BY-SA 4.0",
        notice=_NOTICE,
        used_for="spoken ranks: everyday talk our curriculum never lights",
    )


MANDARIN = _source(
    "zh_cn",
    "zh_cn/zh_cn_50k.txt",
    "25599e00347b893e55c3058a748819b3fe19403291cd12f7c03af128e7f3fe45",
)
ENGLISH = _source(
    "en",
    "en/en_50k.txt",
    "5351ff405b1126ef555791dd4d9798a48e3e9a501a9fc481a9da957752cfb458",
)

_ENGLISH_WORD = re.compile(r"[a-z]+(?:-[a-z]+)?")


def _pack(name: str, english: bool) -> tuple[dict[str, int], dict[str, str]]:
    """The pack's headwords that aren't only names, each with its best
    rank; for English its forms' lemmas too."""
    con = sqlite3.connect(f"file:{PACKS / name}?mode=ro", uri=True)
    ranks: dict[str, int] = {}
    named: dict[str, bool] = {}
    for head, reading, rank in con.execute(
        "select headword, reading, frequency_rank from entries"
    ):
        if english:
            is_name = head[:1].isupper() and len(head) > 1
        else:
            is_name = reading[:1].isupper()
        named[head] = named.get(head, True) and is_name
        if rank is not None and (head not in ranks or rank < ranks[head]):
            ranks[head] = rank
    lemmas: dict[str, str] = {}
    if english:
        lemmas = {
            form.lower(): lemma
            for form, lemma in con.execute("select form, lemma from lemmas")
        }
    con.close()
    return {h: r for h, r in ranks.items() if not named.get(h)}, lemmas


def spoken_ranks(
    counts_file: Path, ranks: dict[str, int], lemmas: dict[str, str], english: bool
) -> list[tuple[str, int]]:
    """(word, its rank in speech) for the `TOP` commonest spoken words the
    pack has, kept only where the pack ranks them rarer than that."""
    counts: dict[str, int] = defaultdict(int)
    with counts_file.open(encoding="utf-8") as f:
        for line in f:
            word, _, count = line.rstrip("\n").rpartition(" ")
            if not word or not count.isdigit():
                continue
            if english:
                if not _ENGLISH_WORD.fullmatch(word):
                    continue
                word = lemmas.get(word, word)
            if word in ranks:
                counts[word] += int(count)
    order = sorted(counts, key=lambda w: (-counts[w], w))[:TOP]
    return [(w, n) for n, w in enumerate(order, 1) if ranks[w] > n]


def _module(found: dict[str, list[tuple[str, int]]]) -> str:
    def block(pairs: list[tuple[str, int]]) -> str:
        tokens = [f"{w} {n}" for w, n in pairs]
        lines, line = [], ""
        for token in tokens:
            if len(line) + len(token) > 70:
                lines.append(f'    "{line}"')
                line = ""
            line += token + " "
        if line:
            lines.append(f'    "{line}"')
        return "\n".join(lines)

    return (
        '"""Generated by `tools/spoken_ranks.py` - do not edit by hand.\n\n'
        "Each word's rank in speech (OpenSubtitles 2018's counts, FrequencyWords,\n"
        "CC BY-SA 4.0; THIRD_PARTY_NOTICES.md), where the pack ranks it rarer:\n"
        '`word rank` pairs, commonest first (polyglotic-hq 491)."""\n\n'
        f"MANDARIN = (\n{block(found['zh'])}\n)\n\n"
        f"ENGLISH = (\n{block(found['en'])}\n)\n"
    )


def main() -> int:
    found: dict[str, list[tuple[str, int]]] = {}
    for code, pack, source, english in (
        ("zh", "cedict.sqlite", MANDARIN, False),
        ("en", "ecdict.sqlite", ENGLISH, True),
    ):
        ranks, lemmas = _pack(pack, english)
        found[code] = spoken_ranks(fetch(source, SOURCES), ranks, lemmas, english)
        print(f"{code}: {len(found[code])} words kept")
    OUT.write_bytes(_module(found).encode("utf-8"))
    print(f"wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
