"""Word frequencies for a pack's ranks: the lists, and averaging them
(polyglotic-hq 325; decision 0120).

A list maps a written form, in lower case, to its share of all words.
Two kinds:
- wordfreq's (`wordfreq_ranks.frequencies`): subtitles, Wikipedia, news,
  books and social media blended, frozen at about 2021. Its tokenizer
  splits words at hyphens, so it has no hyphenated words
  (премьер-министр);
- a list of counts (`counted`): `word count` per line, as FrequencyWords
  publishes OpenSubtitles 2018's - speech, as captions are. Hyphenated
  words are counted whole.

A pack names its lists (`packs.Pack.frequency`); several are averaged
(`mean`). 325 measured Russian on held-out text: subtitles alone suit
conversation best and news worst, wordfreq the other way round, and their
mean keeps most of each.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from pathlib import Path


class Frequencies(dict[str, float]):
    """Written form (lower case) -> its share of all words in one list,
    or the mean of several."""

    def __init__(
        self,
        shares: Mapping[str, float] | Iterable[tuple[str, float]] = (),
        *,
        hyphenated: bool,
    ) -> None:
        super().__init__(shares)
        self.hyphenated = hyphenated
        """Whether hyphenated words are counted whole: a hyphenated word
        such a list hasn't got is rarer than every word it has
        (`floor`). A list without them (wordfreq's) says nothing about
        one."""
        self.floor = min(self.values(), default=0.0)
        """The least share a listed word has."""


def counted(path: Path) -> Frequencies:
    """A list of counts, `word count` per line (FrequencyWords' format),
    as shares; words in lower case, their counts added up."""
    counts: dict[str, int] = defaultdict(int)
    with path.open(encoding="utf-8") as f:
        for line in f:
            word, _, count = line.rstrip("\n").rpartition(" ")
            if word and count.isdigit():
                counts[word.lower()] += int(count)
    total = sum(counts.values()) or 1
    return Frequencies(
        ((word, n / total) for word, n in counts.items()), hyphenated=True
    )


def sentences_counted(
    path: Path, words: Callable[[str], Sequence[tuple[int, int]]]
) -> Frequencies:
    """A file of sentences, one per line, its words counted as shares: each
    word as `words` (the app's word split: start and end) finds it, in
    lower case. Common Voice's Persian sentences (polyglotic-hq 387)."""
    counts: dict[str, int] = defaultdict(int)
    with path.open(encoding="utf-8") as f:
        for line in f:
            for start, end in words(line):
                counts[line[start:end].lower()] += 1
    total = sum(counts.values()) or 1
    return Frequencies(
        ((word, n / total) for word, n in counts.items()), hyphenated=True
    )


def mean(lists: Sequence[Frequencies]) -> Frequencies:
    """Each word's mean share over the lists that could have it - every
    list for a word without a hyphen; for one with, those that count
    hyphenated words whole - a list that could have it but hasn't counting
    0. So a word common in both speech and writing comes before one common
    in only one."""
    if len(lists) == 1:
        return lists[0]
    whole = [f for f in lists if f.hyphenated]
    total: dict[str, float] = defaultdict(float)
    for f in lists:
        for word, share in f.items():
            if f.hyphenated or "-" not in word or not whole:
                total[word] += share
    return Frequencies(
        (
            (word, share / (len(whole) if "-" in word and whole else len(lists)))
            for word, share in total.items()
        ),
        hyphenated=bool(whole),
    )
