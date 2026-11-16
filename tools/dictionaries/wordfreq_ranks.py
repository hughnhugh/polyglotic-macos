"""Frequency ranks from wordfreq's data (https://github.com/rspeer/wordfreq).

wordfreq blends subtitles (SUBTLEX, OpenSubtitles), Wikipedia, books
(Google Books Ngram), web text and more into one frequency per word form,
frozen at about 2021. Project 019 prefers it to ECDICT's own columns,
whose corpus isn't named.

Only `wordfreq/data/large_<language>.msgpack.gz` is read (English for
ECDICT; Spanish and Japanese for their packs) - or, for a language
wordfreq has no large list of, `small_<language>` (Indonesian, Korean,
Turkish, Hindi, Malay, Danish, Filipino, Persian, Greek, Hungarian and
Romanian among the caption languages) - from the package's wheel as a zip
archive; its code is never run. A small list stops at about 20,000-30,000
words; polyglotic-hq 374 measured it against the large one in English and
Spanish: the same top 1,000 (99.8 % and 98.3 %) and top 5,000 (99.3 % and
97.4 %). That file is a gzipped
MessagePack list: a header (`{"format": "cB", "version": 1}`), then one
list of words per centibel - list i holds the words whose frequency is
10^(-i/100). A small decoder for just those types is below, rather than a
dependency.

Ranks are per entry: an entry's frequency is its own word's plus its
inflected forms' ("run" counts "runs", "ran", "running"), since statuses
are kept per entry.
"""

from __future__ import annotations

import gzip
import zipfile
from collections.abc import Iterable, Mapping
from pathlib import Path

DATA = "wordfreq/data/{size}_{language}.msgpack.gz"
SIZES = ("large", "small")
"""The lists read, the first the wheel has."""
CODES = {"tl": "fil"}
"""A caption language's wordfreq code, where it differs: the app calls
Filipino "tl" (the speech server's and kaikki's code), wordfreq "fil"
(polyglotic-hq 387)."""


class _Reader:
    """Just enough MessagePack for wordfreq's file: lists, maps, strings,
    small integers. Anything else is an error, not a guess."""

    def __init__(self, data: bytes) -> None:
        self.data = data
        self.at = 0

    def _take(self, n: int) -> bytes:
        chunk = self.data[self.at : self.at + n]
        if len(chunk) != n:
            raise ValueError("wordfreq data ends early")
        self.at += n
        return chunk

    def _length(self, size: int) -> int:
        return int.from_bytes(self._take(size), "big")

    def value(self) -> object:
        kind = self._take(1)[0]
        if kind <= 0x7F:
            return kind
        if 0x80 <= kind <= 0x8F:
            return self._map(kind & 0x0F)
        if 0x90 <= kind <= 0x9F:
            return self._list(kind & 0x0F)
        if 0xA0 <= kind <= 0xBF:
            return self._take(kind & 0x1F).decode("utf-8")
        lengths = {0xD9: 1, 0xDA: 2, 0xDB: 4}  # strings
        if kind in lengths:
            return self._take(self._length(lengths[kind])).decode("utf-8")
        if kind in (0xDC, 0xDD):
            return self._list(self._length(2 if kind == 0xDC else 4))
        if kind in (0xDE, 0xDF):
            return self._map(self._length(2 if kind == 0xDE else 4))
        raise ValueError(f"unexpected MessagePack type 0x{kind:02x} in wordfreq data")

    def _list(self, n: int) -> list[object]:
        return [self.value() for _ in range(n)]

    def _map(self, n: int) -> dict[object, object]:
        return {self.value(): self.value() for _ in range(n)}


def frequencies(wheel: Path, language: str = "en") -> dict[str, float]:
    """Each word form's frequency (a share of all words) in `language`,
    from its large list, else its small one (`SIZES`)."""
    language = CODES.get(language, language)
    with zipfile.ZipFile(wheel) as archive:
        names = set(archive.namelist())
        found = [
            name
            for size in SIZES
            if (name := DATA.format(size=size, language=language)) in names
        ]
        if not found:
            raise KeyError(f"wordfreq has no list for {language!r}")
        data = gzip.decompress(archive.read(found[0]))
    top = _Reader(data).value()
    if not isinstance(top, list) or top[:1] != [{"format": "cB", "version": 1}]:
        raise ValueError("not wordfreq's cB format, version 1")
    out: dict[str, float] = {}
    for centibels, words in enumerate(top[1:]):
        if not isinstance(words, list):
            raise TypeError("a wordfreq bucket that isn't a list")
        for word in words:
            out.setdefault(str(word), 10 ** (-centibels / 100))
    return out


def frequency_ranks(
    wheel: Path, words: Iterable[str], lemmas: Mapping[str, str], language: str = "en"
) -> dict[str, int]:
    """Ranks for `words` (1 = commonest): each word's frequency plus its
    inflected forms' (`lemmas`: form -> lemma), looked up in lower case.
    Words wordfreq doesn't have get no rank."""
    freq = frequencies(wheel, language)
    words = list(words)
    kept = set(words)
    total = {word: freq.get(word.lower(), 0.0) for word in words}
    for form, lemma in lemmas.items():
        if lemma in kept:  # a form with its own entry ("running") counts for both
            total[lemma] += freq.get(form.lower(), 0.0)
    ranked = sorted((w for w in words if total[w] > 0), key=lambda w: (-total[w], w))
    return {word: n for n, word in enumerate(ranked, start=1)}
