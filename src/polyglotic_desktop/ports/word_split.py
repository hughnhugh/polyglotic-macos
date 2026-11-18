"""WordSplit: the words in a line of one language, and the dictionary forms
to look each up as.

Chinese is split by core's own longest match over the dictionary's
headwords (`core.lexicon.chinese`) and English by its letters; the basic
dictionaries' languages need more (polyglotic-hq project 157): Japanese
has no spaces and inflects ("食べました" is 食べる), Spanish inflects
("hablábamos" is hablar). An analyser for each is an adapter behind this
port - Sudachi for Japanese, simplemma for spaced languages - loaded only
when its dictionary pack is used.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class SplitWord:
    """One word of a line: `text[start:end]`.

    `lemmas` are dictionary forms the analyser found for it in its line,
    best first ("食べ" in 食べました -> ("食べる",)): looked up before the
    word itself. `guesses` are lemmas from a table, out of context
    (simplemma: "vengo" -> vengar, though it's mostly venir): looked up
    only when the dictionary knows nothing better. Neither repeats the
    word. `content` is False for a particle, an auxiliary or a symbol -
    words a probe of the dictionary's coverage doesn't count. `kana` is how
    the analyser read the word in its line, in katakana, where it says
    (Japanese: 食べ in 食べました -> タベ; furigana, polyglotic-hq 511) -
    "" where it doesn't.
    """

    start: int
    end: int
    lemmas: tuple[str, ...] = ()
    guesses: tuple[str, ...] = ()
    content: bool = True
    kana: str = ""


class WordSplit(Protocol):
    """Splits lines of one language into words."""

    def words(self, text: str) -> Sequence[SplitWord]:
        """Every word in `text`, in order; spaces and punctuation are not
        words."""
        ...
