"""The learning load as Learning's card shows it (polyglotic-hq 324), as
plain Python: its numbers, and its words in four lists - ready to check,
in the load, next to enter, graduated - each word with what it has been
heard and what it still needs. Facts, not words; the card words them.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from polyglotic_desktop.core.learning.load import (
    LearningLoad,
    LoadProgress,
    LoadRules,
    LoadWord,
    Stage,
)
from polyglotic_desktop.core.learning.vocabulary import EntryText
from polyglotic_desktop.core.shared import EntryId


class Listed(StrEnum):
    """The card's lists."""

    READY = "ready"
    IN_LOAD = "in_load"
    NEXT = "next"
    GRADUATED = "graduated"


LIMITS = (0, 25, 50, 100)
"""The most words in one colour the card offers; 0: no limit."""

ROWS = 20
"""The words a list shows before "Show more"."""


@dataclass(frozen=True)
class LoadRow:
    """A word in one of the card's lists. `stage`: its colour, for a word
    in the load (None: next to enter, or graduated); `heard` of `step`
    meetings in that stage."""

    entry_id: EntryId
    word: str
    reading: str
    meaning: str
    stage: Stage | None = None
    heard: int = 0
    step: int = 0

    @property
    def held(self) -> bool:
        """Heard enough, but the next colour is full: it waits for room."""
        return (
            self.stage is not None
            and self.stage < Stage.READY
            and self.heard >= self.step > 0
        )


@dataclass(frozen=True)
class LoadView:
    """What the card shows. `available`: the dictionary has frequencies, so
    there is a load. `more`: the words a list holds beyond its rows."""

    available: bool
    rules: LoadRules
    progress: LoadProgress
    rows: tuple[LoadRow, ...] = ()
    more: int = 0


Describe = Callable[[EntryId], EntryText | None]


def load_view(
    load: LearningLoad,
    describe: Describe,
    now: datetime,
    listed: Listed,
    rows: int = ROWS,
) -> LoadView | None:
    """The card for a load that is on; None while it is off. Only the
    `rows` words of the list shown are read from the dictionary."""
    rules = load.rules
    if rules is None:
        return None
    progress = load.progress(now)
    step = rules.step

    def row(entry_id: EntryId, word: LoadWord | None = None) -> LoadRow | None:
        text = describe(entry_id)
        if text is None:
            return None  # gone from the dictionary: not listed
        if word is None or not word.in_load:
            return LoadRow(entry_id, text.headword, text.reading, text.meaning)
        return LoadRow(
            entry_id,
            text.headword,
            text.reading,
            text.meaning,
            word.stage,
            word.meetings,
            step,
        )

    if listed is Listed.NEXT:
        ahead = load.waiting(rows + 1)
        found = [row(facts.entry_id) for _, facts in ahead[:rows]]
        more = len(ahead) - rows if len(ahead) > rows else 0
    elif listed is Listed.GRADUATED:
        found = [row(w.entry_id) for w in load.graduated(rows)]
        more = max(0, progress.graduated - rows)
    else:
        ready = listed is Listed.READY
        members = [w for w in load.members() if w.ready is ready]
        found = [row(w.entry_id, w) for w in members[:rows]]
        more = max(0, len(members) - rows)
    available = progress.words > 0 or progress.graduated > 0 or bool(load.waiting(1))
    return LoadView(available, rules, progress, tuple(r for r in found if r), more)


__all__ = [
    "LIMITS",
    "ROWS",
    "Listed",
    "LoadRow",
    "LoadView",
    "load_view",
]
