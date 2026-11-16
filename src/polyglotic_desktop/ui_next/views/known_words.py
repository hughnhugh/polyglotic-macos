"""About how many words do you know? - the one question a language asks
when it's added, and what "Change your level" asks after (polyglotic-hq
323; the user, 2026-11-14: "each dictionary a user adds should require
them to configure ... number of words to set as known"). Plain Python:
the choices, the one a learner's line is nearest, and "not sure".

A choice is a number of the most common words (`KnownLine.words`). For
Chinese the numbers are HSK 3.0's levels, each named beside its number
(the 2025 exam syllabus: a learner at HSK 3 knows about 1,000 words), so a
level is another way to say the same line. For English they're round
numbers. "Not sure" takes `NOT_SURE`: the middle level words were
estimated at before 323 when none was set (HSK 3; the 3,000 most common
English words).

A level kept from before 323 (`KnownLine.by_level`) is shown as the words
its level holds, and the picker opens on the nearest choice; choosing -
even the same - makes it a line in words.
"""

from dataclasses import dataclass

from polyglotic_desktop.core.learning.levels import (
    UNKNOWN_LEVEL_LINKS_FROM,
    KnownLine,
)
from polyglotic_desktop.core.lexicon.entries import (
    HSK_2021,
    HSK_2025,
    SCHEMES,
)

ENGLISH = (0, 500, 1000, 2000, 3000, 5000, 8000, 12000)
"""English's choices; the last reads "12,000 or more"."""

NOT_SURE = {"zh": 1000, "en": 3000}
"""What "Not sure" takes, by language."""

HSK_2021_WORDS = (500, 1239, 2190, 3157, 4209, 5327, 10896)
"""The words up to each level of HSK 3.0's 2021 standard, as counted in
the Chinese pack of 2026-09-27 (polyglotic-hq 323): only to show a level
kept in that scheme as a number of words."""


@dataclass(frozen=True)
class Choice:
    """ "About `known` words" - `level`: the syllabus level that is the
    same line ("3" for HSK 3), or ""; `or_more`: the last of the list."""

    known: int
    level: str = ""
    or_more: bool = False


def choices(code: str) -> tuple[Choice, ...]:
    """What the picker offers for the language `code`, fewest first; the
    first is "just starting"."""
    if code == "zh":
        levels = zip(HSK_2025.sizes, HSK_2025.levels, strict=True)
        return (Choice(0), *(Choice(size, name) for size, name in levels))
    return tuple(Choice(n, or_more=n == ENGLISH[-1]) for n in ENGLISH)


def not_sure(code: str) -> int:
    """What "Not sure" takes in the language `code` - a pack language's
    (decision 0175): the words estimated known until its line is set."""
    return NOT_SURE.get(code, UNKNOWN_LEVEL_LINKS_FROM)


def words_known(line: KnownLine) -> int | None:
    """About how many words `line` says the learner knows: its own number,
    or the words up to its level; None for a scheme this version doesn't
    know."""
    if not line.by_level:
        return line.known
    if line.known <= 0:
        return 0
    if line.scale == HSK_2021.id:
        sizes: tuple[int, ...] = HSK_2021_WORDS
    else:
        scheme = SCHEMES.get(line.scale)
        sizes = (scheme.sizes or scheme.cutoffs) if scheme else ()
    return sizes[min(line.known, len(sizes)) - 1] if sizes else None


def nearest(offered: tuple[Choice, ...], known: int) -> int:
    """The index of the choice nearest `known` words (the lower, on a tie)."""
    return min(range(len(offered)), key=lambda i: (abs(offered[i].known - known), i))


def opens_on(offered: tuple[Choice, ...], line: KnownLine | None) -> int | None:
    """The choice the picker opens on for a learner whose line is `line`:
    the nearest to it; None ("Not sure") with no line, or one in a scheme
    this version doesn't know."""
    known = words_known(line) if line is not None else None
    return None if known is None else nearest(offered, known)
