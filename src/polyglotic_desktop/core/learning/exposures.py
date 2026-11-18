"""Exposures: how often the learner heard each word, counted on this PC.

An exposure is one finished caption in which the learner heard a word -
once per caption, however often the word came up in it (glossary). Counted
per entry ("ran" counts for "run"), in total and since the word went into
the deck; captions from the user's own mic are counted separately, and
never shared. Names aren't counted: they say who was talked about.

A caption id can be finished more than once - a joined caption keeps the
earlier caption's id and replaces its text (protocol.md) - and a caption
can be withdrawn after it finished. Either way the counts follow the
latest finished text: `ExposureCounter` remembers what it counted for the
last `RECENT_CAPTIONS` captions and counts only the difference.

Each entry also keeps the UTC day it was first heard from what the PC
played (`first_heard`, for "new in the last 7 days"): set when its count
goes from 0 to 1, cleared if a withdrawal takes it back to 0, and unknown
(None) for a word heard before the app kept it (polyglotic-hq 163).

And the separate days it was heard on from what the PC played
(`days_heard`) and the last of them (`last_heard`) - the learner's own
days, the PC's, as our curriculum's (polyglotic-hq 489: how well a word
is known rises with the days it was heard on, `known_chance`). A day
counts when its first caption with the word finishes; a withdrawal that
takes the count back to 0 clears both, and any other leaves them (the
day may have had other captions with the word). Before version 11 of the
learning file only the last 8 weeks' days were kept (`daily_exposures`):
the days then are counted from those, and at least 1 for a word heard.

The counts stay on this PC; daily counts per entry go to the server only
if the learner opts in to sharing them (D3b sends them).
"""

from collections import OrderedDict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from typing import NamedTuple

from polyglotic_desktop.core.shared import EntryId, WordInLine

RECENT_CAPTIONS = 100
"""Captions remembered for joins and withdrawals - joins come within 2s,
so this is plenty."""


class ExposureCount(NamedTuple):
    """One entry's counts. A named tuple: there's one for every word met,
    all made at start, and a frozen dataclass takes about three times as
    long to make (polyglotic-hq 314)."""

    heard: int = 0  # captions from what the PC played
    heard_by_you: int = 0  # captions from the user's own mic
    heard_in_deck: int = 0  # from what the PC played, since it went into the deck
    first_heard: date | None = None  # UTC day; None: not heard, or before it was kept
    days_heard: int = 0  # separate days heard from what the PC played (489)
    last_heard: date | None = None  # the last of them, the learner's day


@dataclass(frozen=True)
class ExposureChange:
    """One entry's change from one caption: +1 when it's newly heard in a
    caption, -1 when a join or withdrawal takes it back out."""

    entry_id: EntryId
    delta: int
    by_you: bool
    day: date  # the UTC date of the caption it came from


@dataclass(frozen=True)
class _Counted:
    entries: frozenset[EntryId]
    by_you: bool
    day: date


class ExposureCounter:
    """Turns finished and withdrawn captions into changes in exposure
    counts, once per caption."""

    def __init__(self) -> None:
        self._recent: OrderedDict[str, _Counted] = OrderedDict()

    def finished(
        self, caption_id: str, words: Iterable[WordInLine], by_you: bool, day: date
    ) -> list[ExposureChange]:
        """A finished caption (or one finished again by a join): the
        entries newly heard in it, and those its new text no longer has."""
        entries = frozenset(w.entry.entry_id for w in words if not w.entry.is_name)
        before = self._recent.pop(caption_id, None)
        self._recent[caption_id] = _Counted(entries, by_you, day)
        while len(self._recent) > RECENT_CAPTIONS:
            self._recent.popitem(last=False)
        return _difference(before, _Counted(entries, by_you, day))

    def withdrawn(self, caption_id: str) -> list[ExposureChange]:
        """A caption taken back: whatever it counted is taken back too."""
        return _difference(self._recent.pop(caption_id, None), None)


def _difference(
    before: _Counted | None, after: _Counted | None
) -> list[ExposureChange]:
    changes = []
    if before is not None:
        kept = (
            after.entries
            if after is not None and after.by_you == before.by_you
            else frozenset()
        )
        changes += [
            ExposureChange(e, -1, before.by_you, before.day)
            for e in sorted(before.entries - kept)
        ]
    if after is not None:
        had = (
            before.entries
            if before is not None and before.by_you == after.by_you
            else frozenset()
        )
        changes += [
            ExposureChange(e, +1, after.by_you, after.day)
            for e in sorted(after.entries - had)
        ]
    return changes


def in_learned_language(caption_language: str | None, learning: str) -> bool:
    """Whether a caption whose language is `caption_language` (protocol.md's
    code: `zh`, `zh-hant`, `yue`, `en`...) is in the language being learned
    (`zh`, `en`) - the same language whatever its script or region, so
    `zh-hant` is Chinese but `yue` (Cantonese) isn't Mandarin. Only those
    count as heard: the learner's dictionary finds its own words in other
    languages too (the English one claims 38 % of a Spanish line's words -
    de, el, que; polyglotic-hq 174). An unknown language counts for nothing."""
    if not caption_language:
        return False
    return caption_language.lower().split("-")[0] == learning


def apply(
    count: ExposureCount,
    change: ExposureChange,
    in_deck: bool,
    today: date | None = None,
) -> ExposureCount:
    """`count` after `change`; `in_deck` says whether the word is in the
    deck now, `today` is the learner's day (the PC's; None: the caption's
    UTC day). Never below zero."""
    today = change.day if today is None else today
    if change.by_you:
        return count._replace(heard_by_you=max(0, count.heard_by_you + change.delta))
    heard = max(0, count.heard + change.delta)
    first = count.first_heard
    days, last = count.days_heard, count.last_heard
    if heard == 0:
        first, days, last = None, 0, None
    elif count.heard == 0:
        first = change.day
    if change.delta > 0 and last != today:
        days, last = days + 1, today
    return ExposureCount(
        heard,
        count.heard_by_you,
        max(0, count.heard_in_deck + change.delta) if in_deck else count.heard_in_deck,
        first,
        days,
        last,
    )
