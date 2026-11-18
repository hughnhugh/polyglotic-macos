"""The English dictionary's English meanings checked (polyglotic-hq 447,
decision 0211): how many running words an English learner's card explains.

    uv run python -m tools.dictionaries.english_check [--top 200]

Reads `build/dictionaries/ecdict-en.sqlite` and looks words up as the app
does for an English learner (`EnglishDictionary`: an inflected form opens
on its lemma). A word counts as explained when its card's first entry has
a meaning. Three measures:
- **FLEURS** (`probe/en.txt`, 100 sentences of the test split): the share
  of its words with a letter that are explained - the packs' basic-tier
  floor, 90 % (`coverage.FLOORS`), applies;
- **running words**: wordfreq's English list, each word weighed by its
  frequency;
- **the top words**: wordfreq's commonest `--top`, each with its card's
  first meaning, printed for a person to read (`--show`), and any without
  one listed.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from polyglotic_desktop.adapters.sqlite_dictionary import SqliteDictionary
from polyglotic_desktop.core.lexicon.english import EnglishDictionary, words
from tools.dictionaries.coverage import FLOORS, PROBE, REPO, sentences

DICTIONARY = REPO / "build" / "dictionaries" / "ecdict-en.sqlite"
WORDFREQ = REPO / "build" / "dictionary-sources" / "wordfreq-3.1.1-py3-none-any.whl"


def first_meaning(dictionary: EnglishDictionary, word: str) -> str:
    """The first meaning on `word`'s card, or "" (none, or not found)."""
    entries = dictionary.lookup(word)
    return entries[0].meanings[0] if entries and entries[0].meanings else ""


@dataclass(frozen=True)
class Explained:
    found: float
    counted: float
    misses: Mapping[str, float]
    """Each word not explained: how often (in the FLEURS lines), or its
    share of all words in % (in wordfreq's list)."""

    @property
    def share(self) -> float:
        return self.found / self.counted if self.counted else 0.0

    def __str__(self) -> str:
        commonest = sorted(self.misses.items(), key=lambda m: -m[1])[:12]
        missed = ", ".join(f"{w} ({n:g})" for w, n in commonest)
        return f"{100 * self.share:.1f} % explained; commonest misses: {missed}"


def in_lines(dictionary: EnglishDictionary, lines: Iterable[str]) -> Explained:
    """Of the words with a letter in `lines`, as the app splits them."""
    found = counted = 0
    misses: Counter[str] = Counter()
    for line in lines:
        for start, end in words(line):
            word = line[start:end]
            if not any(ch.isalpha() for ch in word):
                continue
            counted += 1
            if first_meaning(dictionary, word):
                found += 1
            else:
                misses[word] += 1
    return Explained(found, counted, misses)


def running(
    dictionary: EnglishDictionary, frequencies: Mapping[str, float]
) -> Explained:
    """Of wordfreq's list, each word weighed by its share of all words, and
    looked up as listed or capitalised (a name)."""
    found = counted = 0.0
    misses: dict[str, float] = {}
    for word, share in frequencies.items():
        if not any(ch.isalpha() for ch in word):
            continue
        counted += share
        if first_meaning(dictionary, word) or first_meaning(
            dictionary, word.capitalize()
        ):
            found += share
        else:
            misses[word] = round(100 * share, 3)
    return Explained(found, counted, misses)


def top(
    dictionary: EnglishDictionary, frequencies: Mapping[str, float], count: int
) -> list[tuple[int, str, str]]:
    """wordfreq's `count` commonest words with a letter: place, word, and
    its card's first meaning."""
    ranked = sorted(
        (w for w in frequencies if any(ch.isalpha() for ch in w)),
        key=lambda w: -frequencies[w],
    )[:count]
    return [(n, w, first_meaning(dictionary, w)) for n, w in enumerate(ranked, 1)]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("dictionary", type=Path, nargs="?", default=DICTIONARY)
    parser.add_argument("--wordfreq", type=Path, default=WORDFREQ)
    parser.add_argument("--top", type=int, default=200)
    parser.add_argument("--show", action="store_true", help="print the top words")
    args = parser.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    from tools.dictionaries import wordfreq_ranks

    file = SqliteDictionary(args.dictionary)
    try:
        dictionary = EnglishDictionary(file)
        fleurs = in_lines(dictionary, sentences("en"))
        print(f"FLEURS ({PROBE / 'en.txt'}): {fleurs}")
        frequencies = wordfreq_ranks.frequencies(args.wordfreq, "en")
        print(f"running words: {running(dictionary, frequencies)}")
        listed = top(dictionary, frequencies, args.top)
        if args.show:
            for n, word, meaning in listed:
                print(f"{n}\t{word}\t{meaning}")
        missing = [f"{word} ({n})" for n, word, meaning in listed if not meaning]
        print(f"top {args.top}: without a meaning: {', '.join(missing) or 'none'}")
    finally:
        file.close()
    return 0 if fleurs.share >= FLOORS["basic"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
