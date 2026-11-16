"""The coverage probe: the share of a caption language's words a pack
finds (polyglotic-hq project 157's rule for the basic tier).

    uv run python -m tools.dictionaries.coverage [es ja ru]

Reads `probe/<code>.txt` (100 FLEURS sentences per language), splits each
with the pack's word split, and looks each content word up the way a
caption's word is looked up (`BasicDictionary`). Words without a letter
(numbers) aren't counted. `packs` runs it after each build, records the
share in the file's `info` and fails below the tier's floor; CI runs it
again (`.github/workflows/dictionary-packs.yml`).

A build check, `top_words`, asks that each of wordfreq's 200 commonest
words in the language's script is found as the installed app finds it
(without simplemma, decision 0123), unless `EXEMPT` says why not: Polish's
"i" ("and", 2.7 % of its running words) had had no entry, since kaikki's
extracts file it under a split page's title (polyglotic-hq 390, 399).

A second measure, `running_words`, counts every word as often as it is
used: the share of wordfreq's list for the language, each word weighed by
its frequency, that a lookup finds (polyglotic-hq 298: Russian's target is
95 % of running words). Function words count, as they do in speech;
words in another script (English in Russian text) don't.
"""

from __future__ import annotations

import argparse
import sys
import unicodedata
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from polyglotic_desktop.adapters.japanese_split import JapaneseSplit
from polyglotic_desktop.adapters.spaced_split import ELIDED, SpacedSplit, unelided
from polyglotic_desktop.adapters.sqlite_dictionary import SqliteDictionary
from polyglotic_desktop.core.lexicon.basic import BasicDictionary
from polyglotic_desktop.core.lexicon.thai import ThaiSplit
from polyglotic_desktop.core.lexicon.vietnamese import VietnameseSplit
from polyglotic_desktop.ports.dictionary import DictionaryFile
from polyglotic_desktop.ports.word_split import SplitWord, WordSplit

PROBE = Path(__file__).parent / "probe"
REPO = Path(__file__).resolve().parents[2]
FLOORS = {"basic": 0.90}
"""The least share of content words a tier's dictionary must find (157)."""
SCRIPTS = {
    **dict.fromkeys(("de", "es", "fr", "id", "it", "ms", "pl", "pt", "tr"), "LATIN"),
    **dict.fromkeys(("cs", "da", "fi", "hu", "nl", "ro", "sv", "tl"), "LATIN"),
    **dict.fromkeys(("ar", "fa"), "ARABIC"),
    "el": "GREEK",
    "hi": "DEVANAGARI",
    **dict.fromkeys(("mk", "ru", "uk"), "CYRILLIC"),
}
"""The script a language's running words are written in: words in
another are left out of `running_words`."""


TOP_WORDS = 200
"""How many of wordfreq's commonest words a pack must find (`top_words`)."""
TOP_FROM_COUNTED = {"th": "commonvoice-th"}
"""Languages wordfreq has no list for, and the list their pack's reader
counts (`Draft.counted`) whose commonest words `top_words` checks instead:
Thai's Common Voice sentences, cut by the app's word split (polyglotic-hq
394, 396). Its words are the pack's own, so the check asks that each is
found as the installed app looks it up - kept, not cut, not a letter left
without an entry - not that the pack has every common word."""
EXEMPT: dict[str, dict[str, str]] = {
    "pt": {
        "the": "English, in Portuguese web text",
        "of": "English, likewise",
        "to": "English, likewise (and tô, estou, without its accent)",
    },
    "id": {
        "nya": "the ending -nya written apart: the split guesses it off words",
        "d": "a letter (d/a, an address's 'care of')",
        "yg": "chat shorthand for yang, which captions of speech write whole",
    },
    "de": {
        "s": "the 's of geht's and gibt's, cut off by wordfreq",
        "a": "in foreign names and phrases (à la, a cappella)",
    },
    "ru": {"н": "a letter, in abbreviations (н. э.)"},
    "pl": {
        "the": "English, in Polish web text",
        "r": "a letter: r. is short for rok (year) after a date",
    },
    # The packs of 387 and 388 met #744's check on the train (394); the
    # words it found missing that a learner meets were filled in 396.
    "nl": {
        "t": "'t, het elided ('t is), cut off by wordfreq",
        "the": "English, in Dutch web text",
        "m": "a letter (m for metre; 'm, hem elided)",
    },
    "uk": {
        "с": "Russian's с (with), in Ukrainian web text: Ukrainian writes з",
        "и": "Russian's и (and), likewise: Ukrainian writes і",
        "р": "a letter: р. is short for рік (year) after a date",
        "м": "a letter: м. is short for місто (city) and метр",
    },
    "fa": {
        "ی": "a letter: the ending ی (ezafe, 'a') written apart",
        "اینکه": "این که (that) written closed up: English Wiktionary has no "
        "page for it under any spelling (اینکه, این‌که, این که; 2026-11-16), "
        "and a pack makes up no meanings; این and که are found",
        "نداره": "colloquial ندارد (hasn't), as web text writes speech",
        "ام": "the ending -am (I am; my) written apart: Wiktionary's suffix ـم",
    },
    "ro": {
        # its clitics written short (i, ți, s, l, n, m, într) are found as
        # the whole words since 399 (`packs.ROMANIAN`)
        "d": "a letter",
        "nr": "nr., short for număr (number)",
    },
    "el": {
        **dict.fromkeys(("σ", "κ", "μ", "ν", "β", "γ"), "a letter, in abbreviations"),
        "ελλάδα": "Ελλάδα (Greece), a name, in lower case in wordfreq",
        "ειναι": "είναι without its accent, as informal web text writes it",
    },
    "tl": {
        "nag": "the prefix nag- written apart (nag aral)",
        "i": "a letter",
        **dict.fromkeys(
            ("of", "the", "and", "to", "in", "for"), "English, in Taglish web text"
        ),
    },
    "mk": {
        "твитер": "Twitter, a name",
    },
    "tr": {
        **dict.fromkeys(("d", "a", "i", "e"), "a letter"),
    },
    "ms": {
        "al": "al-, the Arabic article in names (al-Quran)",
        **dict.fromkeys(("in", "the"), "English, in Malay web text"),
    },
}
"""Per language, the commonest words a pack needn't find, and why."""


@dataclass(frozen=True)
class Coverage:
    found: int
    counted: int
    misses: Counter[str]

    @property
    def share(self) -> float:
        return self.found / self.counted if self.counted else 0.0

    def __str__(self) -> str:
        commonest = ", ".join(f"{w} ({n})" for w, n in self.misses.most_common(12))
        return (
            f"{100 * self.share:.1f} % of {self.counted} content words found; "
            f"commonest misses: {commonest}"
        )


def split_for(language: str, file: DictionaryFile, simplemma: bool = True) -> WordSplit:
    """The word split a language's pack (`file`) uses: Vietnamese's and
    Thai's are by the pack's own words. `simplemma`: False splits as the
    installed app."""
    if language == "ja":
        return JapaneseSplit()
    if language == "vi":
        return VietnameseSplit(file)
    if language == "th":
        return ThaiSplit(file)
    return SpacedSplit(language, simplemma)


def sentences(language: str) -> list[str]:
    text = (PROBE / f"{language}.txt").read_text(encoding="utf-8")
    return [line for line in text.splitlines() if line.strip()]


def measure(
    dictionary: BasicDictionary, split: WordSplit, lines: Iterable[str]
) -> Coverage:
    found = counted = 0
    misses: Counter[str] = Counter()
    for line in lines:
        for word in split.words(line):
            text = line[word.start : word.end]
            if not word.content or not any(ch.isalpha() for ch in text):
                continue
            counted += 1
            if dictionary.lookup_split(text, word):
                found += 1
            else:
                misses[text] += 1
    return Coverage(found, counted, misses)


def probe(pack_file: Path, language: str) -> Coverage:
    file = SqliteDictionary(pack_file)
    split = split_for(language, file)
    try:
        return measure(
            BasicDictionary(file, split, language), split, sentences(language)
        )
    finally:
        file.close()


@dataclass(frozen=True)
class RunningWords:
    """The share of running words found: `found` and `counted` are sums of
    frequencies (wordfreq's share of all words), `words` how many word
    forms were counted."""

    found: float
    counted: float
    words: int
    misses: dict[str, float]

    @property
    def share(self) -> float:
        return self.found / self.counted if self.counted else 0.0

    def __str__(self) -> str:
        commonest = ", ".join(
            f"{w} ({100 * f / self.counted:.2f} %)"
            for w, f in sorted(self.misses.items(), key=lambda m: -m[1])[:12]
        )
        return (
            f"{100 * self.share:.1f} % of running words found ({self.words} word "
            f"forms, weighed by frequency); commonest misses: {commonest}"
        )


def in_script(word: str, script: str | None) -> bool:
    """`word` has a letter, and every letter is in `script` (any, if None)."""
    letters = [ch for ch in word if ch.isalpha()]
    return bool(letters) and (
        script is None or all(script in unicodedata.name(ch, "") for ch in letters)
    )


def running_words(
    dictionary: BasicDictionary, frequencies: Mapping[str, float], language: str
) -> RunningWords:
    """How much of `frequencies` (word -> its share of all words, wordfreq's
    lower-case list) `dictionary` finds, each word as a caption might write
    it: as listed, capitalised (a name: "сша" is США), or in capitals."""
    script = SCRIPTS.get(language)
    found = counted = 0.0
    words = 0
    misses: dict[str, float] = {}
    for word, share in frequencies.items():
        if not in_script(word, script):
            continue
        words += 1
        counted += share
        if finds(dictionary, word):
            found += share
        else:
            misses[word] = share
    return RunningWords(found, counted, words, misses)


def finds(dictionary: BasicDictionary, word: str) -> bool:
    """Whether a lookup finds `word` (wordfreq's, in lower case) as a
    caption might write it: as listed, capitalised (a name, a German noun)
    or in capitals - and an elided word with its apostrophe, as captions
    write it (wordfreq cuts French's "l'homme" into "l" and "homme")."""
    spellings = (word, word.capitalize(), word.upper())
    if any(dictionary.lookup(w) for w in dict.fromkeys(spellings)):
        return True
    if word not in ELIDED.get(dictionary.language, ()):
        return False
    elided = f"{word}'"  # as the split gives it before a word: "l'" of l'homme
    split = SplitWord(0, len(elided), guesses=unelided(elided))
    return bool(dictionary.lookup_split(elided, split))


@dataclass(frozen=True)
class TopWords:
    """Of wordfreq's `TOP_WORDS` commonest words in a language's script:
    those a pack doesn't find (with their place in the list), and those
    it needn't (`EXEMPT`)."""

    missing: list[tuple[int, str]]
    exempt: list[tuple[int, str]]

    def __str__(self) -> str:
        said = ", ".join(f"{w} ({n})" for n, w in self.missing) or "none"
        excused = ", ".join(f"{w} ({n})" for n, w in self.exempt) or "none"
        return f"missing {said}; exempt {excused}"


def top_words(
    dictionary: BasicDictionary,
    frequencies: Mapping[str, float],
    language: str,
    top: int = TOP_WORDS,
) -> TopWords:
    """Which of the `top` commonest words of `frequencies` (wordfreq's list,
    commonest first) in the language's script `dictionary` doesn't find."""
    script = SCRIPTS.get(language)
    exempt = EXEMPT.get(language, {})
    words = [w for w in frequencies if in_script(w, script)][:top]
    gaps = [(n, w) for n, w in enumerate(words, 1) if not finds(dictionary, w)]
    return TopWords(
        [(n, w) for n, w in gaps if w not in exempt],
        [(n, w) for n, w in gaps if w in exempt],
    )


def probe_top_words(pack_file: Path, language: str, wordfreq: Path) -> TopWords:
    """`top_words` over wordfreq's list for `language`, looked up as the
    installed app looks up (no simplemma)."""
    from tools.dictionaries import wordfreq_ranks

    return probe_top_words_of(
        pack_file, language, wordfreq_ranks.frequencies(wordfreq, language)
    )


def probe_top_words_of(
    pack_file: Path, language: str, frequencies: Mapping[str, float]
) -> TopWords:
    """`top_words` over `frequencies` (any order: commonest first is
    taken here), looked up as the installed app looks up."""
    ranked = dict(sorted(frequencies.items(), key=lambda item: -item[1]))
    file = SqliteDictionary(pack_file)
    try:
        split = split_for(language, file, simplemma=False)
        return top_words(BasicDictionary(file, split, language), ranked, language)
    finally:
        file.close()


def probe_running_words(pack_file: Path, language: str, wordfreq: Path) -> RunningWords:
    """`running_words` over wordfreq's list for `language`."""
    from tools.dictionaries import wordfreq_ranks

    file = SqliteDictionary(pack_file)
    try:
        return running_words(
            BasicDictionary(file, split_for(language, file), language),
            wordfreq_ranks.frequencies(wordfreq, language),
            language,
        )
    finally:
        file.close()


def main(argv: Sequence[str] | None = None) -> int:
    from tools.dictionaries.packs import PACKS

    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("languages", nargs="*", default=list(PACKS))
    parser.add_argument(
        "--packs", type=Path, default=REPO / "build" / "dictionaries" / "packs"
    )
    args = parser.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    failed = 0
    for language in args.languages:
        pack = PACKS[language]
        result = probe(args.packs / f"{pack.name}.sqlite", language)
        floor = FLOORS["basic"]
        ok = result.share >= floor
        failed += not ok
        print(
            f"{pack.name} ({language}): {result} - {'pass' if ok else 'FAIL'} "
            f"(floor {100 * floor:.0f} %)"
        )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
