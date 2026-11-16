"""Marking the commonest words known at once, and taking it back
(polyglotic-hq 342; the user, 2026-11-15: "a quick select option to mark
first x thousand words as known, make this resettable too").

**One place to say it.** "Mark the first 3,000 words known" moves the
learner's known line (`levels.KnownLine`) to 3,000: the line already is
"I know about the N most common words", and it is what Learning's "Your
level" says. No status is written per word - thousands of rows, each sent
to the server - so marking, undoing and resetting are each one change of
the line. A word's status set by hand always wins over the line
(`statuses`), so none of the three touches the learner's own marks: a word
they made new again stays new, one they marked known stays known.

Only forward: a number at or below what the line holds already marks
nothing new (`marks_more`); lowering the line is the level picker's.

**Undo** is offered right after a quick mark, for that session: back to
the line just before it. **Reset** takes the language back to its line
before the first quick mark since the learner last said their level
another way (the level picker), and is kept between sessions
(`QuickMarks.reset_to`, as the settings keep it). Before any line was set,
"back" is no line at all: words are estimated at the starting level again,
and Learning says the level isn't set.
"""

from dataclasses import dataclass

from polyglotic_desktop.core.learning.levels import WORDS, KnownLine

FIRST_KNOWN = (1000, 2000, 3000, 5000, 10000)
"""The quick choices, in words (the user, 2026-11-15: "first x thousand
words"); any other number can be typed."""

MOST_KNOWN = 50_000
"""The most a typed number can be: a guard against a slip of the keyboard,
well past the words a learner is likely to know."""


def marks_more(known_now: int | None, first: int) -> bool:
    """Whether marking the first `first` words known moves the line
    forward from `known_now` words (None: not known in words - a level
    scheme this version doesn't know - so any number may be marked)."""
    return first > 0 and (known_now is None or first > known_now)


@dataclass(frozen=True)
class Before:
    """A language's line as it was before a quick mark. `line` None: none
    was set - words were estimated at the starting level."""

    line: KnownLine | None

    def to_stored(self) -> dict[str, object]:
        """As the settings keep it: {} for no line."""
        if self.line is None:
            return {}
        return {"scale": self.line.scale, "known": self.line.known}

    @classmethod
    def from_stored(cls, stored: object) -> "Before | None":
        """From what the settings keep; None for nothing kept, or anything
        not valid (a reset point lost is better than a wrong line)."""
        if not isinstance(stored, dict):
            return None
        if not stored:
            return cls(None)
        scale, known = stored.get("scale"), stored.get("known")
        if not isinstance(scale, str) or not scale:
            return None
        if not isinstance(known, int) or isinstance(known, bool) or known < 0:
            return None
        return cls(
            KnownLine.words(known) if scale == WORDS else KnownLine(scale, known)
        )


@dataclass(frozen=True)
class QuickMarks:
    """For one language: where Reset goes back to (`reset_to`, kept), and
    where Undo goes back to (`undo_to`, this session only). None: not
    offered."""

    reset_to: Before | None = None
    undo_to: Before | None = None

    def marked(self, before: KnownLine | None) -> "QuickMarks":
        """After a quick mark from the line `before`: Undo goes back to
        it; Reset to where it already went, or to it for a first mark."""
        return QuickMarks(self.reset_to or Before(before), Before(before))

    def undone(self) -> "tuple[Before, QuickMarks] | None":
        """Undo: the line to go back to, and what's offered after - Reset
        still, unless undoing went back to where it would. None: no Undo
        is offered."""
        if self.undo_to is None:
            return None
        reset_to = None if self.reset_to == self.undo_to else self.reset_to
        return self.undo_to, QuickMarks(reset_to)

    def reset(self) -> "tuple[Before, QuickMarks] | None":
        """Reset: the line to go back to; nothing is offered after. None:
        no Reset is offered."""
        if self.reset_to is None:
            return None
        return self.reset_to, QuickMarks()
