"""Which of a caption's word links show, by what the learner knows
(polyglotic-hq 323; the user, 2026-11-14: "didn't want basic words to be
linked ... estimate 3000 words known = linkage only occurs on 3000+").

A word link pairs words of what was said with words of its translation.
Each row of the pair may have a say, when its language is one the learner
learns and chose how its words are linked (`RowLinks`):

- **every word**: the link shows;
- **words past what I know**: it shows unless every word under it on that
  row is one the learner knows (`known`: the spans of those words). A word
  the dictionary doesn't have or can't place - most names, a foreign
  word - is not known: linked (nothing says the learner knows it, and its
  translation is what they'd look up). A number is no word: not linked.
  In a language with no full dictionary nothing says which words are
  common, so only key links show (`key_only`: content words, as the
  server marks them) - fewer links, honestly got;
- **off**: it doesn't.

A link shows when no row has a say (neither language is learned: as
before 323). Else the **captioned language decides** (the user,
2026-11-15: "it should be determined by captioned language not by
translated language"; polyglotic-hq 338): when the learner learns the
language heard, its row's say alone shows or hides the link; a
translation row's say counts only when the language heard isn't learned
(hearing Japanese, learning Chinese: the Chinese translation's words
decide). Before, any row with a say that kept a link showed it: a learner
of Chinese and English saw 目前 kept by "currently" at 5,000 Chinese
words, "is" kept by 身处 on English speech, and every link of an English
caption kept by the Chinese translation's "every word".

Qt-free: the caption windows' marks draw what this says. Links "On hover"
aren't asked: the learner pointed at the word.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from polyglotic_desktop.core.listening.display import CaptionRow, LinkedWords, RowKind

Span = tuple[int, int]


@dataclass(frozen=True)
class RowLinks:
    """What a row's language says about linking its words."""

    known: Sequence[Span] = ()
    """The words the learner knows, as spans of the row's text."""
    every: bool = False
    """Every word: each link shows, a number's too."""
    key_only: bool = False
    """Only key links: no dictionary says which words are common."""
    off: bool = False
    """No links on this language's words."""


def _all_known(text: str, word: LinkedWords, known: Sequence[Span]) -> bool:
    """Whether every letter under the link's word is in a known word. A
    number has no letters: 1940 and 100 don't need their translation, and
    were linked for every learner (polyglotic-hq 338)."""
    return all(
        any(start <= at < end for start, end in known)
        for at in range(word.start, min(word.end, len(text)))
        if text[at].isalpha()
    )


def _keeps(row: CaptionRow, words: Sequence[LinkedWords], say: RowLinks) -> bool:
    if say.every:
        return True
    if say.off or (say.key_only and not any(w.key for w in words)):
        return False
    return not all(_all_known(row.text, w, say.known) for w in words)


def hidden_links(
    rows: Sequence[CaptionRow], says: Sequence[RowLinks | None]
) -> set[tuple[int, int]]:
    """The links that don't show, each as (its clause, its number): `says`
    has each row's say, None for a row whose language has none."""
    heard = {  # clauses whose heard language has a say: it alone decides
        row.clause
        for row, say in zip(rows, says, strict=True)
        if say is not None and row.kind is RowKind.ORIGINAL
    }
    verdicts: dict[tuple[int, int], bool] = {}
    for row, say in zip(rows, says, strict=True):
        if say is None or (row.kind is not RowKind.ORIGINAL and row.clause in heard):
            continue
        by_link: dict[int, list[LinkedWords]] = {}
        for word in row.links:
            by_link.setdefault(word.link, []).append(word)
        for link, words in by_link.items():
            key = (row.clause, link)
            verdicts[key] = verdicts.get(key, False) or _keeps(row, words, say)
    return {key for key, kept in verdicts.items() if not kept}
