"""Word statuses: estimated from the known line unless set explicitly.

Every word the learner meets has a status - new, learning (in the deck),
known or ignored (glossary). Most are never stored: they're estimated from
the learner's known line (`levels`). Only explicit statuses are stored per
entry, each with a source: set by the learner (a click, the vocabulary
list), imported (later: Anki, Pleco), or estimated - pinned lookups of a
word only assumed known turn it back to new (two: polyglotic-hq 397). The learner's own choices
never change by themselves (project 019, agreed 2026-11-04).
"""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from polyglotic_desktop.core.learning.levels import KnownLine
from polyglotic_desktop.core.shared import EntryFacts, WordStatus


class StatusSource(StrEnum):
    """Where a word's status came from."""

    ESTIMATED = "estimated"  # from the level, or from what the learner did
    LEARNER = "learner"  # set by the learner
    IMPORTED = "imported"  # from another tool (after the MVP)


@dataclass(frozen=True)
class StatusRecord:
    """A word's status and where it came from; `at` is when it was set
    (None for one computed now)."""

    status: WordStatus
    source: StatusSource
    at: datetime | None = None

    @property
    def is_learners_own(self) -> bool:
        """Set by the learner or imported - never changed by Learning."""
        return self.source is not StatusSource.ESTIMATED


def estimated_status(facts: EntryFacts, line: KnownLine | None) -> WordStatus:
    """The status a word has until one is set: ignored for a name; known
    for a number in numerals (二十: polyglotic-hq 360) and up to the
    learner's known line; otherwise new. With no line, every other word is
    new."""
    if facts.is_name:
        return WordStatus.IGNORED
    if facts.is_number:
        return WordStatus.KNOWN
    if line is not None and line.knows(facts):
        return WordStatus.KNOWN
    return WordStatus.NEW


def status_of(
    facts: EntryFacts, explicit: StatusRecord | None, line: KnownLine | None
) -> StatusRecord:
    """A word's status: the explicit one if there is one, else estimated."""
    if explicit is not None:
        return explicit
    return StatusRecord(estimated_status(facts, line), StatusSource.ESTIMATED)
