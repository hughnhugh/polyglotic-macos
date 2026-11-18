"""How well the learner knows each word: a chance from 0 to 1 that they
know it (polyglotic-hq 489; the user, 2026-11-18: "every word has a
colour based on your knowledge of the language ... Progress is measured
by least amount of words that are red (or completely unknown) and most
words green (mastered word). everything in between represents exposure
or partial knowledge"; decision 0226).

The chance is worked out on the log-odds scale, `x`, and read as
`1 / (1 + e^-x)`. Two parts:

**Where the word starts** (`Start`), from `Knowledge.of` - the one answer
per word (polyglotic-hq 349) - and the line:

| What `Knowledge` says | Starts at (x) | Chance |
|---|---|---|
| The learner said known (a graduation too) | +4.0 | 0.98 |
| Known by an import (Anki) | +3.0 | 0.95 |
| A number in numerals (二十) | +3.0 | 0.95 |
| Placed (its place on the words scale, `levels.place`) | `SLOPE` x ln(line / place), from -3.0 to +4.0 | 0.05 - 0.98 |
| Known by the words it is made of | +1.5 | 0.82 |
| In the deck (learning), said or imported | -1.0 | 0.27 |
| Turned new by lookups (two pinned, polyglotic-hq 397) | -1.0 | 0.27 |
| Not known by the words it is made of | -1.5 | 0.18 |
| The learner said new ("don't know"), or an import did | -3.0 | 0.05 |
| Nothing places it, nor its parts: as if the `UNPLACED`th (30,000th) word | the curve there | 0.05 under a line of 7,000; 0.30 at 20,000 |
| Ignored, or a name | not coloured | - |

**The curve, not a step.** A placed word's chance falls smoothly with
its place: 0.5 at the line ("I know about N words": the line is where the
learner knows about half the words - 019), and `SLOPE` = 2.13 is 019's
simulation's spread, 0.8 in natural-log rank (a probit with sigma 0.8 is
a logistic of slope 1.702 / 0.8). So a word at half the line's place is
0.82, at a quarter 0.95; at twice the line 0.18, at four times 0.05. A
learner of 1,000 words: green (`MASTERED`) up to about the 440th word,
red (`UNKNOWN`) past about the 2,260th. Where the curve and `Knowledge`
meet, they agree: within the line is 0.5 or more, past it under 0.5.

**A compound is no rarer than its parts let it be** (`parts`; Chinese:
its characters, each a word of its own): placed at the smaller of its own
place and `PARTS_FACTOR` times its rarest part's - 输掉 is the 83,039th
word in CC-CEDICT's list, but 输 is the 2,836th and 掉 the 987th, so it's
placed at 5,672. A learner who knows 输 and 掉 understands 输掉; a list
that counts words as a corpus split them doesn't say so. Only where every
part is placed; else its own place, or `UNPLACED`. Word links still ask
`Knowledge`, which doesn't yet read parts (349's step 2): a compound can
be coloured as more likely known than its link says.

**What moves it from there** (`Moved`), each at most once, in this
order:

| Evidence | Moves x by |
|---|---|
| Heard (from what the PC played, never the mic) on separate days before today | +0.5 a day, at most +2.5 (5 days) |
| Saved (in a category) | +0.5 |
| Looked up (pinned), and then heard on a later day without looking it up again | +1.0 |
| Looked up (pinned) in the last `FRESH` days | -1.5 |
| Looked up (pinned) `CHECK_AFTER` times since the learner said they know it | -1.5 |

**Met isn't unknown** (the user: red is "completely unknown"; "everything
in between represents exposure"): a word heard, saved or looked up is at
least `MET` (0.16), just past red - before a fresh lookup lowers it.

**Today's hearing counts from tomorrow.** Every word of a caption has
just been heard: counted at once, no caption word could ever be red, and
a word's colour would change while it was being read. So a day heard
counts once it's over - "heard on separate days" is the evidence, a word
that came back - and so does "heard again after a lookup". A lookup or a
save counts at once (the learner did it; a lookup lowers).

**Hearing isn't knowing:** what raises a word (the first three) never
takes it past `EXPOSURE_CAP` (0.80): exposure and partial knowledge are
the colours between; only what the learner said, or the line, makes a
word green. Nor does it lower a word that started higher. What lowers it
does so from wherever it is. The result is kept within `LOWEST` and
`HIGHEST` (0.01 - 0.99): nothing is ever certain.

**Not yet** (the brief's evidence that has no data yet): a review's or a
test's answer (474's review and 019's test) - each will be what the
learner said, a `Start`; "Not yet" in the load's check leaves no trace
but the word's stage.

**The bands** (`Band`): red under `UNKNOWN_BELOW` (0.15), green from
`MASTERED_FROM` (0.85), between them exposure and partial knowledge -
019's thresholds (0.85 "sure"), mirrored on the log-odds scale.

Cheap enough to colour every word of every caption: a few dictionary
reads and one logarithm a word (`tests/learning/test_known_chance.py`
measures it). Plain rules: no storage, no Qt.
"""

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import IntEnum, StrEnum

from polyglotic_desktop.core.learning.knowledge import (
    BaseWords,
    Knowledge,
    Knows,
    Reason,
)
from polyglotic_desktop.core.learning.levels import place
from polyglotic_desktop.core.learning.lookups import CHECK_AFTER, LookupCount
from polyglotic_desktop.core.shared import EntryFacts, EntryId, WordStatus

SLOPE = 2.13
"""How steeply the chance falls with a word's place, per natural-log step
of it: 1.702 / 0.8 - 019's simulation's word-by-word spread (0.8 in
log-rank units) as a logistic."""

SAID_KNOWN = 4.0
IMPORTED_KNOWN = 3.0
NUMBER = 3.0
BY_PARTS = 1.5
LEARNING = -1.0
LOOKED_UP_NEW = -1.0
NOT_BY_PARTS = -1.5
UNKNOWN = -3.0
"""Where words start (x): see the module's table."""

CURVE = (UNKNOWN, SAID_KNOWN)
"""A placed word's start is kept within these: no line makes a word less
known than one the learner said they don't know, nor more known than one
they said they know."""

PARTS_FACTOR = 2
"""A compound is placed at most this many times further than its rarest
part (a guess, to tune: rarer than its parts, not much rarer)."""

UNPLACED = 30_000
"""A word nothing places (a form the frequency list splits otherwise:
输掉, 三柱门) is taken as rarer than any word on Learning's map: red for a
learner of a few thousand words, between for a near-native one, green for
a native - not red for everyone (489, real captions)."""

LEVEL_KNOWN, LEVEL_NEW = 2.0, -2.0
"""A line kept in a scheme that says no number of words (HSK 3.0's 2021
standard) has no curve: within it or past it."""

PER_DAY = 0.5
DAYS = 5
SAVED = 0.5
NOT_AGAIN = 1.0
FRESH_LOOKUP = -1.5
SINCE_KNOWN = -1.5
"""What moves a word (x): see the module's table."""

FRESH = timedelta(days=3)
"""A pinned lookup this recent says the learner didn't know the word
just now; older, and the word heard on a later day without another, says
they've kept it."""

MET = 0.16
"""A word the learner has met - heard, saved, looked up - is at least
this: no longer red, "completely unknown"."""

EXPOSURE_CAP = 0.80
"""What raises a word never takes it past this chance: hearing it,
saving it and keeping it after a lookup are exposure and partial
knowledge, never mastery."""

LOWEST, HIGHEST = 0.01, 0.99

UNKNOWN_BELOW = 0.15
MASTERED_FROM = 0.85


def _logit(p: float) -> float:
    return math.log(p / (1.0 - p))


_CAP = _logit(EXPOSURE_CAP)
_MET = _logit(MET)
_LOW, _HIGH = _logit(LOWEST), _logit(HIGHEST)


class Band(IntEnum):
    """The user's three: red, the colours between, green."""

    UNKNOWN = 0  # red: never met, or far past the line
    PARTIAL = 1  # between: exposure, or partial knowledge
    MASTERED = 2  # green


def band(chance: float) -> Band:
    if chance < UNKNOWN_BELOW:
        return Band.UNKNOWN
    if chance >= MASTERED_FROM:
        return Band.MASTERED
    return Band.PARTIAL


class Start(StrEnum):
    """Where a word's chance starts - one a learner could be told."""

    SAID_KNOWN = "said_known"
    IMPORTED_KNOWN = "imported_known"
    NUMBER = "number"
    LINE = "line"  # placed, against the line the learner set
    STARTING_LINE = "starting_line"  # placed, against the line assumed meanwhile
    BY_PARTS = "by_parts"
    LEARNING = "learning"  # in the deck
    LOOKED_UP = "looked_up"  # turned new by pinned lookups
    NOT_BY_PARTS = "not_by_parts"
    SAID_NEW = "said_new"
    NOT_PLACED = "not_placed"


class Moved(StrEnum):
    """What moved a word's chance from its start."""

    HEARD = "heard"  # on separate days
    SAVED = "saved"
    NOT_AGAIN = "not_again"  # looked up, then heard without another lookup
    FRESH_LOOKUP = "fresh_lookup"
    SINCE_KNOWN = "since_known"  # looked up since they said they know it


@dataclass(frozen=True, slots=True)
class Chance:
    """How well the learner knows one word: `chance` (0-1), where it
    started (`start`, and `place` for a placed word) and what moved it,
    each with how far (on the log-odds scale)."""

    chance: float
    start: Start
    moved: tuple[tuple[Moved, float], ...] = ()
    place: int | None = None
    days_heard: int = 0

    @property
    def band(self) -> Band:
        return band(self.chance)


@dataclass(frozen=True, slots=True)
class Evidence:
    """What the learner did with a word besides saying what they know of
    it: the separate days they heard it on (`days_heard`) and the last
    (the learner's own day), their lookups, whether it is saved and when
    (`saved_at`: for the map's week ago)."""

    days_heard: int = 0
    last_heard: date | None = None
    lookups: LookupCount | None = None
    saved: bool = False
    saved_at: datetime | None = None


NO_EVIDENCE = Evidence()


class KnownChances:
    """How well the learner knows each word of one language."""

    def __init__(
        self,
        knowledge: Knowledge,
        evidence: Callable[[EntryId], Evidence],
        now: Callable[[], datetime],
        day_of: Callable[[datetime], date],
    ) -> None:
        """`knowledge`: the one answer per word (statuses, the line);
        `evidence`: what the learner did with a word; `now` and `day_of`:
        the time, and the learner's day a time falls on (the PC's own)."""
        self.knowledge = knowledge
        self._evidence = evidence
        self._now = now
        self._day_of = day_of
        self.parts: BaseWords | None = None
        """The words a word is made of - for Chinese its characters, each
        a word of its own - set by the wiring (`main`); None: none."""

    def of(self, word: EntryFacts) -> Chance | None:
        """How well the learner knows `word` - None for a word not to
        colour: a name, or one they said to ignore."""
        return self.each((word,))[0]

    def each(self, words: Sequence[EntryFacts]) -> list[Chance | None]:
        """`of` for every word of a caption, the time read once."""
        now = self._now()
        today = self._day_of(now)
        line = self.knowledge.known_words
        set_ = self.knowledge.line_set
        return [
            None
            if word.is_name
            else _chance(
                word,
                self.knowledge.of(word),
                line,
                set_,
                self._evidence(word.entry_id),
                now,
                today,
                self._day_of,
                self.parts,
            )
            for word in words
        ]


def _chance(
    word: EntryFacts,
    knows: Knows,
    line: int | None,
    line_set: bool,
    evidence: Evidence,
    now: datetime,
    today: date,
    day_of: Callable[[datetime], date],
    parts: BaseWords | None = None,
) -> Chance | None:
    started = _start(word, knows, line, line_set, parts)
    if started is None:
        return None
    start, x, at = started
    moved: list[tuple[Moved, float]] = []
    raised = x
    # today's hearing counts from tomorrow: a caption's words were all just
    # heard, and what was heard today is the same day, not another
    days = evidence.days_heard - (1 if evidence.last_heard == today else 0)
    last = evidence.last_heard if evidence.last_heard != today else None
    if days > 0:
        step = PER_DAY * min(days, DAYS)
        moved.append((Moved.HEARD, step))
        raised += step
    if evidence.saved:
        moved.append((Moved.SAVED, SAVED))
        raised += SAVED
    lookups = evidence.lookups
    fresh = False
    if lookups is not None and lookups.pinned and lookups.last is not None:
        fresh = now - lookups.last < FRESH
        if not fresh and last is not None and last > day_of(lookups.last):
            moved.append((Moved.NOT_AGAIN, NOT_AGAIN))
            raised += NOT_AGAIN
    met = days > 0 or evidence.saved or bool(lookups and lookups.pinned)
    if met:
        raised = max(raised, _MET)
    if raised > x:  # never past the cap, nor below where it started
        x = max(x, min(raised, _CAP))
    if fresh:
        moved.append((Moved.FRESH_LOOKUP, FRESH_LOOKUP))
        x += FRESH_LOOKUP
    if (
        lookups is not None
        and start is Start.SAID_KNOWN
        and lookups.pinned_since_known >= CHECK_AFTER
    ):
        moved.append((Moved.SINCE_KNOWN, SINCE_KNOWN))
        x += SINCE_KNOWN
    x = min(max(x, _LOW), _HIGH)
    return Chance(1.0 / (1.0 + math.exp(-x)), start, tuple(moved), at, max(0, days))


def _start(
    word: EntryFacts,
    knows: Knows,
    line: int | None,
    line_set: bool,
    parts: BaseWords | None = None,
) -> tuple[Start, float, int | None] | None:
    """Where the word starts: why, x, and its place if placed."""
    reason, status = knows.reason, knows.status
    if status is WordStatus.IGNORED:
        return None
    if reason in (Reason.SAID, Reason.IMPORTED):
        if status is WordStatus.KNOWN:
            if reason is Reason.SAID:
                return Start.SAID_KNOWN, SAID_KNOWN, None
            return Start.IMPORTED_KNOWN, IMPORTED_KNOWN, None
        if status is WordStatus.LEARNING:
            return Start.LEARNING, LEARNING, None
        return Start.SAID_NEW, UNKNOWN, None
    if reason is Reason.LOOKED_UP:
        return Start.LOOKED_UP, LOOKED_UP_NEW, None
    if reason is Reason.NUMBER:
        return Start.NUMBER, NUMBER, None
    if reason is Reason.PARTS:
        if status is WordStatus.KNOWN:
            return Start.BY_PARTS, BY_PARTS, None
        return Start.NOT_BY_PARTS, NOT_BY_PARTS, None
    start = Start.LINE if line_set else Start.STARTING_LINE
    at = _placed(word, parts)
    if reason is Reason.NOT_PLACED:
        if line is None:  # a line said by level alone: no curve
            return Start.NOT_PLACED, UNKNOWN, None
        if at is None:  # nor its parts
            return Start.NOT_PLACED, _curve(UNPLACED, line), None
        return start, _curve(at, line), at
    # by the line: within it, or placed past it
    if line is None or at is None:  # a line said by level alone
        known = status is WordStatus.KNOWN
        return start, LEVEL_KNOWN if known else LEVEL_NEW, at
    return start, _curve(at, line), at


def _placed(word: EntryFacts, parts: BaseWords | None) -> int | None:
    """The word's place - or its rarest part's, `PARTS_FACTOR` times, where
    that is nearer and every part is placed."""
    at = place(word)
    found = parts(word) if parts is not None else ()
    if len(found) < 2:
        return at
    each = [place(part) for part in found]
    if any(p is None for p in each):
        return at
    by_parts = PARTS_FACTOR * max(p for p in each if p is not None)
    return by_parts if at is None else min(at, by_parts)


def _curve(at: int, line: int) -> float:
    if line <= 0:  # "just starting": nothing known yet
        return UNKNOWN
    x = SLOPE * math.log(line / max(at, 1))
    return min(max(x, CURVE[0]), CURVE[1])


def curve(at: int, line: int) -> float:
    """The chance of a word placed `at` with nothing but a line of `line`
    words to go on."""
    return 1.0 / (1.0 + math.exp(-_curve(at, line)))
