"""The coverage probe: the share of a caption language's words a pack
finds (polyglotic-hq project 157's rule for the basic tier).

    uv run python -m tools.dictionaries.coverage [es ja ru]

Reads `probe/<code>.txt` (100 FLEURS sentences per language), splits each
with the pack's word split, and looks each content word up the way a
caption's word is looked up (`BasicDictionary`). Words without a letter
(numbers) aren't counted. A word the pack hasn't got whole but whose card
shows it by its parts, every part found, counts as found, in every
language (German's Arbeitsplatz is Arbeit + Platz; Korean's 국립공원 is
국립 + 공원): Thai's, Vietnamese's and Cantonese's word splits already cut
such a word into the pack's words (polyglotic-hq DECISIONS #227, 533). `packs` runs it after each build, records the
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
from polyglotic_desktop.core.lexicon.han import HanSplit
from polyglotic_desktop.core.lexicon.thai import ThaiSplit
from polyglotic_desktop.core.lexicon.vietnamese import VietnameseSplit
from polyglotic_desktop.ports.dictionary import DictionaryFile
from polyglotic_desktop.ports.word_split import SplitWord, WordSplit
from tools.dictionaries import kaikki

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
    by_parts: int = 0
    """How many of `found` the card shows by their parts (`measure`)."""

    @property
    def share(self) -> float:
        return self.found / self.counted if self.counted else 0.0

    def __str__(self) -> str:
        commonest = ", ".join(f"{w} ({n})" for w, n in self.misses.most_common(12))
        return (
            f"{100 * self.share:.1f} % of {self.counted} content words found "
            f"({self.by_parts} by their parts); commonest misses: {commonest}"
        )


def split_for(language: str, file: DictionaryFile, simplemma: bool = True) -> WordSplit:
    """The word split a language's pack (`file`) uses: Vietnamese's, Thai's and
    Cantonese's are by the pack's own words. `simplemma`: False splits as the
    installed app."""
    if language == "ja":
        return JapaneseSplit()
    if language == "vi":
        return VietnameseSplit(file)
    if language == "th":
        return ThaiSplit(file)
    if language == "yue":
        return HanSplit(file)
    return SpacedSplit(language, simplemma)


def sentences(language: str) -> list[str]:
    text = (PROBE / f"{language}.txt").read_text(encoding="utf-8")
    return [line for line in text.splitlines() if line.strip()]


def measure(
    dictionary: BasicDictionary, split: WordSplit, lines: Iterable[str]
) -> Coverage:
    """How many of `lines`' content words a caption's lookup finds: whole,
    or shown by its parts with every part found (`shown_by_parts`)."""
    found = counted = by_parts = 0
    misses: Counter[str] = Counter()
    for line in lines:
        for word in split.words(line):
            text = line[word.start : word.end]
            if not word.content or not any(ch.isalpha() for ch in text):
                continue
            counted += 1
            if dictionary.lookup_split(text, word):
                found += 1
            elif shown_by_parts(dictionary, text):
                found += 1
                by_parts += 1
            else:
                misses[text] += 1
    return Coverage(found, counted, misses, by_parts)


def shown_by_parts(dictionary: BasicDictionary, word: str) -> bool:
    """Whether the card shows `word`, which the pack hasn't got whole, by
    its parts, each a word the pack has (`core.lexicon.compounds`): a
    hyphenated word's piece the pack hasn't got (T-Rex's "Rex") leaves it
    not found."""
    parts = dictionary.parts(word)
    return bool(parts) and all(part.found for part in parts)


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


USED_AS = 0.5
"""The share of a word's uses the treebanks must give one part of speech for
`opened_as_used` to hold its card to it."""


@dataclass(frozen=True)
class OpenedAs:
    """Of the `TOP_WORDS` commonest running words: those whose card opens on
    an entry in a part of speech the treebanks seldom use the word as, each
    as (place, word, the entry it opens on, how the treebanks use it)."""

    mismatched: list[tuple[int, str, str, str]]

    def __str__(self) -> str:
        return (
            ", ".join(
                f"{w} ({n}): {opened}, used as {used}"
                for n, w, opened, used in self.mismatched
            )
            or "none"
        )


def opened_as_used(
    dictionary: BasicDictionary,
    frequencies: Mapping[str, float],
    language: str,
    uses: kaikki.Uses,
    top: int = TOP_WORDS,
) -> OpenedAs:
    """Which of the `top` commonest words of `frequencies` (running words,
    commonest first: forms as captions write them, not headwords) open, as
    a caption's word is looked up, on an entry in a part of speech the
    treebanks (`uses`, each form as written) don't use it as, where they
    use it at least `kaikki.MIN_USES` times and one part of speech in
    `USED_AS` of them. The top-words check (`top_words`) asks only whether
    a word is found: Hindi's लिए, the 12th commonest, was - on लेना, "to
    take", though it is the postposition of के लिए, "for" (polyglotic-hq
    448, 461)."""
    script = SCRIPTS.get(language)
    words = [w for w in frequencies if in_script(w, script)][:top]
    out = []
    for n, word in enumerate(words, 1):
        counts = uses.get(word.lower(), {})
        if sum(counts.values()) < kaikki.MIN_USES:
            continue
        spellings = dict.fromkeys((word, word.capitalize(), word.upper()))
        entries = next((e for w in spellings if (e := dictionary.lookup(w))), [])
        if not entries:
            continue
        first = entries[0].meanings[0] if entries[0].meanings else ""
        pos = (
            first[1 : first.index(")")]
            if first.startswith("(") and ")" in first
            else ""
        )
        resolved = kaikki.resolved(counts, {pos})
        tag, most = max(resolved.items(), key=lambda item: item[1])
        used = most >= USED_AS * sum(resolved.values())
        if pos and used and tag not in kaikki.UD_POS.get(pos, ()):
            out.append((n, word, f"{entries[0].headword} ({pos})", tag))
    return OpenedAs(out)


def probe_opened_as_used(
    pack_file: Path, language: str, frequencies: Mapping[str, float], uses: kaikki.Uses
) -> OpenedAs:
    """`opened_as_used` over `frequencies` (any order), looked up as the
    installed app looks up."""
    ranked = dict(sorted(frequencies.items(), key=lambda item: -item[1]))
    file = SqliteDictionary(pack_file)
    try:
        split = split_for(language, file, simplemma=False)
        return opened_as_used(
            BasicDictionary(file, split, language), ranked, language, uses
        )
    finally:
        file.close()


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
