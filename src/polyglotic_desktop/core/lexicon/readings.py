"""Reading lines: how the words of a text are read, placed over its
characters (polyglotic-hq 364 and 369, decision 0155).

A reading is a small line a learner reads beside the text itself: pinyin
over Chinese characters, later furigana over Japanese. Each language's
dictionary says how its text is read; a layout draws what it is given and
knows no language.

Plain values. A reading holds caption text's sound: never log it.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Reading:
    """Characters `[start, end)` of a text are read `text`. `ends_word`:
    the last of its word - a layout may leave a little more room after
    it, so the words show in a script written without spaces."""

    start: int
    end: int
    text: str
    ends_word: bool = True
    mark: bool = False
    """A mark on its character rather than a reading above it - Russian's
    stress, an accent over the vowel (polyglotic-hq 511): drawn in the
    text's own size, where an accent on that letter would be."""


Readings = Callable[[str, str | None], Sequence[Reading] | None]
"""The readings of a text in a language (its code, None if not known):
none for a language without a reading line - and None while they can't
be said yet (the dictionary still being read): ask again."""
