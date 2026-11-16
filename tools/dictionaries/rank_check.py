"""A pack's ranks checked for junk before the pack is used (polyglotic-hq 374).

Ranks are the one "known" line in every language (polyglotic-hq DECISIONS
#176): a learner who says "I know about 1,000 words" is assumed to know the
pack's top 1,000, so junk there marks real words wrongly. polyglotic-hq 325
found each kind below in a built pack; `packs.frequencies` now keeps most of
it out, and this check refuses a pack where any comes back - from a new
language's list, a new source or a change to the builder:

- an affix ("в-", "-ить"): wordfreq has no hyphens, so a prefix had taken its
  stem's frequency - 79 of Russian's top 1,000 were affixes;
- a number: wordfreq writes digits as 0s ("00", "0000"), which a list of
  written forms can carry into a pack with numeral entries;
- names, past a share: 28 of Russian's top 1,000 had been names spelled like
  common words ("По", "Или"); real names (Россия, Москва) stay, a few;
- words in the Latin alphabet in a language not written in it (an English
  "the" in a Russian list), past a share;
- a list of syllables, not words, in a language that writes a word's
  syllables apart (Vietnamese: wordfreq's and FrequencyWords' lists count
  "học" and "sinh", never "học sinh"), when too few of the top words have a
  space.

A word is a headword: its entries share one rank (`packs.ranks`).
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable, Sequence

from polyglotic_desktop.ports.dictionary import EntryRecord

TOP = 1000
"""How far down the check looks: the first line a learner is offered."""
NAMES = 40
"""At most this many of the top 1,000 words may be names (a count, so a
small pack is held to the same line). Built packs on
2026-11-16: Russian 9 of 1,000 (Россия, Москва, США...), Vietnamese 0,
French (polyglotic-hq 341's) 15 (polyglotic-hq 374). Raised from 30 by
polyglotic-hq 380: Hindi's (wordfreq's small, news-heavy list) has 31,
every one a real name - India, Delhi, Pakistan, Gandhi, its states and
parties - none spelled like a common word."""
LATIN_WORDS = 10
"""At most this many may be Latin-alphabet words in a language that isn't
written in it."""
SPACED_SHARE = 0.05
"""At least this share of the top words must have a space, in a language
that writes a word's syllables apart. Vietnamese's pack has 32.9 % (374)."""

WRITTEN_IN_LATIN = frozenset(
    [
        "cs",
        "da",
        "de",
        "en",
        "es",
        "fi",
        "fil",
        "fr",
        "hu",
        "id",
        "it",
        "ms",
        "nl",
        "pl",
        "pt",
        "ro",
        "sv",
        "tl",
        "tr",
        "vi",
    ]
)
"""The caption languages written in the Latin alphabet (Filipino as the app
and its pack call it, "tl", and as wordfreq does, "fil")."""
SYLLABLES_APART = frozenset({"vi"})
"""Languages that write each syllable of a word apart ("học sinh")."""
LATIN = re.compile(r"^[A-Za-z]+$")
NAME = "(name) "
"""How a pack's meanings start for a name (`packs` writes "(pos) meaning")."""


def ranked_words(records: Iterable[EntryRecord]) -> list[tuple[str, list[EntryRecord]]]:
    """Each ranked headword with its entries, commonest first."""
    by_word: dict[str, list[EntryRecord]] = defaultdict(list)
    rank: dict[str, int] = {}
    for r in records:
        if r.frequency_rank:
            by_word[r.headword].append(r)
            rank[r.headword] = min(
                rank.get(r.headword, r.frequency_rank), r.frequency_rank
            )
    return [(w, by_word[w]) for w in sorted(rank, key=lambda w: (rank[w], w))]


def is_name(entries: Sequence[EntryRecord]) -> bool:
    """Every entry of the word is a name, as the pack's meanings say."""
    return all(m.startswith(NAME) for e in entries for m in e.meanings) and any(
        e.meanings for e in entries
    )


def problems(records: Iterable[EntryRecord], language: str) -> list[str]:
    """What is wrong with the ranks' top words, one line each; none: they pass."""
    top = ranked_words(records)[:TOP]
    n = len(top) or 1
    words = [w for w, _ in top]
    out = []

    def found(what: str, bad: Sequence[str], limit: int = 0) -> None:
        if len(bad) <= limit:
            return
        allowed = f" (at most {limit})" if limit else ""
        out.append(
            f"{len(bad)} {what} in the top {len(top):,}{allowed}: {' '.join(bad[:10])}"
        )

    found("affixes", [w for w in words if w.startswith("-") or w.endswith("-")])
    found("numbers", [w for w in words if any(c.isdigit() for c in w)])
    found("names", [w for w, entries in top if is_name(entries)], NAMES)
    if language not in WRITTEN_IN_LATIN:
        found("Latin-alphabet words", [w for w in words if LATIN.match(w)], LATIN_WORDS)
    if language in SYLLABLES_APART and top:
        spaced = sum(1 for w in words if " " in w) / n
        if spaced < SPACED_SHARE:
            out.append(
                f"only {spaced:.1%} of the top {len(top):,} have a space (at least "
                f"{SPACED_SHARE:.0%}): the list ranks syllables, not words"
            )
    return out
