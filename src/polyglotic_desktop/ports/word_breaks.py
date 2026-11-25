"""WordBreaks: places where an unspaced caption may wrap between words.

The language analyser stays outside caption layout.  It supplies character
offsets through this port, so layout neither guesses that every Han character
is a word nor depends on a particular segmenter.
"""

from typing import Protocol

from polyglotic_desktop.ports.word_split import SplitWord


class WordBreaks(Protocol):
    """Word boundaries in one language's text."""

    def words(self, text: str, language: str | None) -> tuple[SplitWord, ...] | None:
        """Words in ``text``, or ``None`` when no language pack is available.

        The language is the language of this side of the caption, not the
        learner's target language.  ``None`` deliberately asks core to retain
        its character fallback for unspaced scripts.
        """
        ...
