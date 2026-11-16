"""The learning load: a fixed number of words being learned, each moving
through four colours as it is met, checked with one click, and replaced
by the next (polyglotic-hq 324, the user, 2026-11-14; decision 0117).

An alternate way to see captions, in the Lab and off by default. While it
is on:

- **The load** is `LoadRules.size` words (500 until the learner says):
  the next ones past the learner's known line, by their place
  (`levels.place`: a word's frequency rank, or its syllabus level's size
  where that is smaller - the learning window's own words, in order),
  names and words they set known or ignored left out. Saved words and
  words in the deck are in it like any other: they are words being
  learned.
- **Stages.** A word enters red and moves to orange, yellow and green,
  one stage for every `LoadRules.step` meetings (3 until the learner
  says). After green and the same number again it is **ready to check**.
- **A meeting** is the word heard in a finished caption from what the PC
  played (never the user's own mic), counted as `Counting` says: every
  time it is heard (the default: "objective count"), or at most once a
  caption, a session or a day. Meetings count from the moment a word
  enters the load: what was heard before doesn't.
- **"At most this many in a colour"** (`LoadRules.stage_limit`; 0: no
  limit) holds orange, yellow and green: a word that has had its meetings
  waits in its colour until the next has room, the one with the most
  meetings first. Red has no limit of its own: the load's size is its
  limit. Ready to check has none: the learner empties it.
- **The check.** "I know this" graduates the word: it leaves the load,
  its status is known (set by the learner, so it syncs as any status
  does), and the next word by frequency takes its place. "Not yet" sends
  it back to `NOT_YET` (yellow: half the way again). A real quiz would
  replace who answers, not what the answer does (`LearningLoad.check`).
- **By hand.** The learner can add the next words ahead of graduations,
  or one word; either raises the load's size by what was added, so the
  size is always the number of words in a full load. A word set aside
  ("not now") leaves and isn't brought back by itself. A word set known
  anywhere graduates; a word set ignored leaves.
- **The size can change at any time.** Raised, the next words come in at
  once. Lowered, words leave from the far end: red before orange, the
  fewest meetings first, the rarest first, words added by hand last.
  They wait with their meetings kept, and come back with them.

When the known line moves, words it now covers leave (kept, with their
meetings, in case it moves back), words not yet met give way to commoner
ones, and the load fills again.

Kept on this PC with the rest of the learning data (`ports.learning`'s
`StoredLoadWord`), and deleted with it. Only a graduation leaves the PC,
as the status "known".

Plain rules here; `LearningLoad` is the load itself, which `Vocabulary`
holds and tells of finished captions, statuses and the line.
"""

from collections import Counter, OrderedDict
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from enum import IntEnum, StrEnum

from polyglotic_desktop.core.learning.levels import place
from polyglotic_desktop.core.shared import EntryFacts, EntryId, WordInLine, WordStatus
from polyglotic_desktop.ports.learning import StoredLoadWord

DEFAULT_SIZE = 500
"""The load's size until the learner says (the user: "e.g. 500 words")."""

SIZES = (100, 250, 500, 1000)
"""The sizes offered; any number between `MIN_SIZE` and `MAX_SIZE` is kept
(adding by hand makes others)."""

MIN_SIZE, MAX_SIZE = 1, 5000

DEFAULT_STEP = 3
"""Meetings to move one stage on (the user: "after 2-3 times")."""

STEPS = (1, 2, 3, 5, 8)
"""The steps offered."""

ADD_SIZES = (10, 25, 50)
"""How many of the next words "Add the next ..." offers."""

SESSION_GAP = timedelta(minutes=30)
"""No finished caption for this long ends a session, for "once a
session"; so does closing the app."""

RECENT_CAPTIONS = 100
"""Captions remembered for joins and withdrawals (as `exposures`)."""

WEEK = timedelta(days=7)


class Stage(IntEnum):
    """Where a word in the load stands. The four colours, then ready to
    check (shown in green's colour, with its own cue)."""

    RED = 0
    ORANGE = 1
    YELLOW = 2
    GREEN = 3
    READY = 4


NOT_YET = Stage.YELLOW
"""Where "Not yet" sends a word: half the way again (two stages of
meetings before it is asked about again)."""

COLOURS = (Stage.RED, Stage.ORANGE, Stage.YELLOW, Stage.GREEN)


class Counting(StrEnum):
    """What counts as a meeting."""

    EVERY = "every"  # each time the word is heard
    CAPTION = "caption"  # at most once a caption
    SESSION = "session"  # at most once a session (`SESSION_GAP`)
    DAY = "day"  # at most once a day, the PC's own


@dataclass(frozen=True)
class LoadRules:
    """The learner's choices for the load, per language."""

    size: int = DEFAULT_SIZE
    step: int = DEFAULT_STEP
    counting: Counting = Counting.EVERY
    stage_limit: int = 0
    """At most this many words in orange, in yellow and in green; 0: no
    limit."""

    def __post_init__(self) -> None:
        object.__setattr__(self, "size", min(MAX_SIZE, max(MIN_SIZE, self.size)))
        object.__setattr__(self, "step", max(1, self.step))
        object.__setattr__(self, "stage_limit", max(0, self.stage_limit))


class Standing(StrEnum):
    """Whether a word the load keeps is in it."""

    IN = "in"
    WAITING = "waiting"
    """Left when the load shrank or the known line moved over it; comes
    back, with its meetings, when its turn comes."""
    SET_ASIDE = "set_aside"
    """ "Not now": taken out by the learner; back only by their hand."""
    GRADUATED = "graduated"


@dataclass(frozen=True)
class LoadWord:
    """A word the load keeps. `meetings` are those in its stage (a word
    held by a full colour keeps counting); `place` its place on the words
    scale when it entered (`levels.place`; None: added by hand, a word
    with neither a rank nor a level)."""

    entry_id: EntryId
    standing: Standing
    stage: Stage
    meetings: int
    by_hand: bool
    place: int | None
    entered_at: datetime
    last_met: datetime | None = None
    graduated_at: datetime | None = None

    @property
    def in_load(self) -> bool:
        return self.standing is Standing.IN

    @property
    def ready(self) -> bool:
        return self.in_load and self.stage is Stage.READY

    def needs(self, step: int) -> int:
        """Meetings still needed to move on; 0 for a word that has had
        them (held by a full colour) or is ready to check."""
        return 0 if self.stage is Stage.READY else max(0, step - self.meetings)


@dataclass(frozen=True)
class LoadProgress:
    """The load in numbers: words in each stage, ready to check, graduated
    in the last 7 days and in all, and the size it is filled to."""

    stages: tuple[int, int, int, int]
    ready: int
    graduated_week: int
    graduated: int
    size: int

    @property
    def words(self) -> int:
        """The words in the load now (fewer than `size` when the
        dictionary has no more to give)."""
        return sum(self.stages) + self.ready


class MeetingCounter:
    """Turns finished and withdrawn captions into meetings, as `Counting`
    says. A caption finished again (a join) or withdrawn changes only the
    difference, as exposures do."""

    def __init__(self, day_of: Callable[[datetime], date]) -> None:
        self._day_of = day_of
        self._recent: OrderedDict[str, dict[EntryId, int]] = OrderedDict()
        self._credit: dict[EntryId, tuple[object, str]] = {}
        """Per word, the session or day it last counted in, and the
        caption it counted for."""
        self._session = 0
        self._last_caption: datetime | None = None

    def finished(
        self,
        caption_id: str,
        words: Iterable[WordInLine],
        now: datetime,
        counting: Counting,
        last_met: Callable[[EntryId], datetime | None],
    ) -> dict[EntryId, int]:
        """The change in meetings a finished caption makes, per word.
        `last_met` answers for a word in the load (when it last counted;
        None: never) and raises `KeyError` for any other word."""
        if self._last_caption is None or now - self._last_caption > SESSION_GAP:
            self._session += 1
        self._last_caption = now
        heard = Counter(w.entry.entry_id for w in words if not w.entry.is_name)
        before = self._recent.pop(caption_id, {})
        credited: dict[EntryId, int] = {}
        for entry_id, times in heard.items():
            try:
                met = last_met(entry_id)
            except KeyError:
                continue
            credited[entry_id] = self._wanted(
                entry_id, caption_id, times, now, counting, met
            )
        self._recent[caption_id] = credited
        while len(self._recent) > RECENT_CAPTIONS:
            self._recent.popitem(last=False)
        return self._difference(caption_id, before, credited)

    def withdrawn(self, caption_id: str) -> dict[EntryId, int]:
        return self._difference(caption_id, self._recent.pop(caption_id, {}), {})

    def _wanted(
        self,
        entry_id: EntryId,
        caption_id: str,
        times: int,
        now: datetime,
        counting: Counting,
        met: datetime | None,
    ) -> int:
        if counting is Counting.EVERY:
            return times
        if counting is Counting.CAPTION:
            return 1
        period: object = (
            self._session if counting is Counting.SESSION else self._day_of(now)
        )
        credit = self._credit.get(entry_id)
        if credit is not None and credit[0] == period:
            return 1 if credit[1] == caption_id else 0
        if (
            credit is None
            and counting is Counting.DAY
            and met is not None
            and self._day_of(met) == period
        ):
            return 0  # counted today, before the app last started
        self._credit[entry_id] = (period, caption_id)
        return 1

    def _difference(
        self,
        caption_id: str,
        before: Mapping[EntryId, int],
        after: Mapping[EntryId, int],
    ) -> dict[EntryId, int]:
        changes = {}
        for entry_id in before.keys() | after.keys():
            delta = after.get(entry_id, 0) - before.get(entry_id, 0)
            if delta:
                changes[entry_id] = delta
            if not after.get(entry_id):
                credit = self._credit.get(entry_id)
                if credit is not None and credit[1] == caption_id:
                    del self._credit[entry_id]
        return changes


def leaving_order(word: LoadWord) -> tuple[bool, int, int, int]:
    """Sorts the words that leave first when the load shrinks: not added
    by hand, the lowest stage, the fewest meetings, the rarest."""
    return (word.by_hand, word.stage, word.meetings, -(word.place or 10**9))


class LoadStore:
    """What `LearningLoad` needs kept: the two calls of `LearningStore`."""

    def __init__(
        self,
        save: Callable[[Sequence[StoredLoadWord]], None],
        delete: Callable[[Sequence[str]], None],
    ) -> None:
        self.save = save
        self.delete = delete


class LearningLoad:
    """The load of one language. Off (`rules` None) it keeps what it has
    and counts nothing.

    `facts` gives a word's facts (None if the dictionary hasn't got it);
    `eligible` says whether a word may be in the load now (not a name, not
    known, not ignored); `placed(after, limit)` gives the dictionary's
    words placed past `after`, each with its place, earliest first, about
    `limit` of them - empty when it has no more, or no ranks at all: that
    language has no load. `line_place` gives the place the known line
    stands at (0 for a line kept as a level: every word is read, and the
    known ones passed over). The
    methods that change the load return whether anything changed."""

    def __init__(
        self,
        stored: Iterable[StoredLoadWord],
        store: LoadStore,
        facts: Callable[[EntryId], EntryFacts | None],
        eligible: Callable[[EntryFacts], bool],
        placed: Callable[[int, int], Sequence[tuple[int, EntryFacts]]],
        line_place: Callable[[], int],
        day_of: Callable[[datetime], date],
    ) -> None:
        self._store = store
        self._facts = facts
        self._eligible = eligible
        self._placed = placed
        self._line_place = line_place
        self._day_of = day_of
        self._words: dict[EntryId, LoadWord] = {}
        for row in stored:
            try:
                word = _from_stored(row)
            except ValueError:
                continue  # a newer app's value: left as it is in the store
            self._words[word.entry_id] = word
        self._members = sum(1 for w in self._words.values() if w.in_load)
        self._counter = MeetingCounter(day_of)
        self.rules: LoadRules | None = None
        self._ahead: list[tuple[int, EntryFacts]] = []
        """Words read ahead from the dictionary: the next to come in."""
        self._ahead_after: int | None = None
        """The place read up to; None: nothing read, start at the line."""
        self._exhausted = False
        self._touched: set[EntryId] = set()
        self._all_touched = False

    # -- reading ---------------------------------------------------------------

    @property
    def on(self) -> bool:
        return self.rules is not None

    def word(self, entry_id: EntryId) -> LoadWord | None:
        return self._words.get(entry_id)

    def stage(self, entry_id: EntryId) -> Stage | None:
        """The stage of a word in the load; None for any other word, and
        for every word while the load is off."""
        if self.rules is None:
            return None
        word = self._words.get(entry_id)
        return word.stage if word is not None and word.in_load else None

    def members(self) -> list[LoadWord]:
        """The words in the load: furthest on first, then the most
        meetings, then the commonest."""
        return sorted(
            (w for w in self._words.values() if w.in_load),
            key=lambda w: (-w.stage, -w.meetings, w.place or 10**9, w.entry_id),
        )

    def graduated(self, limit: int = 50) -> list[LoadWord]:
        """The words graduated, latest first."""
        found = [
            (w.graduated_at, w.entry_id, w)
            for w in self._words.values()
            if w.standing is Standing.GRADUATED and w.graduated_at is not None
        ]
        found.sort(key=lambda row: row[:2], reverse=True)
        return [w for _, _, w in found[:limit]]

    def progress(self, now: datetime) -> LoadProgress:
        stages = [0, 0, 0, 0]
        ready = week = graduated = 0
        for word in self._words.values():
            if word.in_load:
                if word.stage is Stage.READY:
                    ready += 1
                else:
                    stages[word.stage] += 1
            elif word.standing is Standing.GRADUATED:
                graduated += 1
                at = word.graduated_at
                week += at is not None and at >= now - WEEK
        size = self.rules.size if self.rules else DEFAULT_SIZE
        return LoadProgress(
            (stages[0], stages[1], stages[2], stages[3]), ready, week, graduated, size
        )

    def take_touched(self) -> frozenset[EntryId] | None:
        """The words whose stage, or being in the load at all, changed
        since this was last asked - what a caption shows of them did; None:
        every word's may have (the load turned on or off, or was emptied).
        A meeting that moved no word changes none."""
        touched = None if self._all_touched else frozenset(self._touched)
        self._touched, self._all_touched = set(), False
        return touched

    def waiting(self, limit: int) -> list[tuple[int, EntryFacts]]:
        """The next words to enter, each with its place, earliest first. Nothing while the load is off."""
        if self.rules is None:
            return []
        self._read_ahead(limit)
        return [(r, f) for r, f in self._ahead if self._can_enter(f)][:limit]

    # -- the learner's choices -----------------------------------------------------

    def set_rules(self, rules: LoadRules | None, now: datetime) -> bool:
        """Turns the load on, changes its rules, or (None) turns it off."""
        if rules == self.rules:
            return False
        if (rules is None) != (self.rules is None):
            self._all_touched = True
        self.rules = rules
        self.refill(now)
        return True

    def refill(self, now: datetime) -> bool:
        """Brings the load to its size: words past the size leave from the
        far end (`leaving_order`), the next words come in; then whoever a
        full colour was holding moves if there is room."""
        rules = self.rules
        if rules is None:
            return False
        changed: dict[EntryId, LoadWord] = {}
        dropped = False
        over = self._members - rules.size
        if over > 0:
            members = [w for w in self._words.values() if w.in_load]
            for word in sorted(members, key=leaving_order)[:over]:
                self._leave(word, changed)
            dropped = True
            self.reset_ahead()  # they are the next to come back
        need = rules.size - self._members
        while need > 0:
            self._read_ahead(need)
            ahead, self._ahead = self._ahead, []
            for n, (at, facts) in enumerate(ahead):
                if need == 0:
                    self._ahead = ahead[n:]
                    break
                if self._can_enter(facts):
                    self._enter(facts, at, now, False, changed)
                    need -= 1
            if self._exhausted and not self._ahead:
                break
        self._make_room(changed)
        return self._save(changed) or dropped

    def add_next(self, count: int, now: datetime) -> bool:
        """The next `count` words now, ahead of graduations: the load's
        size goes up by them."""
        if self.rules is None or count <= 0:
            return False
        self.rules = replace(self.rules, size=self.rules.size + count)
        self.refill(now)
        return True

    def add(self, entry: EntryFacts, now: datetime) -> bool:
        """One word added by hand; the load's size goes up by it. A word
        that waited comes back with its meetings; one set aside or
        graduated (and new again since) starts again in red."""
        word = self._words.get(entry.entry_id)
        if self.rules is None or (word is not None and word.in_load):
            return False
        if not self._eligible(entry):
            return False
        self.rules = replace(self.rules, size=self.rules.size + 1)
        self._enter(entry, place(entry), now, True, None)
        return True

    def set_aside(self, entry_id: EntryId) -> bool:
        """ "Not now": out of the load until added by hand again. The
        caller refills."""
        word = self._words.get(entry_id)
        if word is None or not word.in_load:
            return False
        self._put(replace(word, standing=Standing.SET_ASIDE), None)
        return True

    def check(self, entry_id: EntryId, knows: bool, now: datetime) -> bool:
        """The answer to "Do you know this word?" for a word ready to
        check - the learner's click today, a quiz's result later. Knowing
        it graduates it; not yet sends it back to `NOT_YET`. The caller
        sets the status known and refills."""
        word = self._words.get(entry_id)
        if word is None or not word.ready:
            return False
        if knows:
            word = replace(word, standing=Standing.GRADUATED, graduated_at=now)
        else:
            word = replace(word, stage=NOT_YET, meetings=0)
        self._put(word, None)
        return True

    def status_set(self, entry_id: EntryId, status: WordStatus, now: datetime) -> bool:
        """A word's status was set, here or on another PC. Known: it
        graduates if it is in the load. Ignored: the load forgets it. New
        or in the deck: a word graduated before may come in again. The
        caller refills."""
        word = self._words.get(entry_id)
        changed = False
        if word is not None and status is WordStatus.KNOWN:
            if word.in_load:
                self._put(
                    replace(word, standing=Standing.GRADUATED, graduated_at=now), None
                )
                changed = True
        elif word is not None and (
            status is WordStatus.IGNORED or word.standing is Standing.GRADUATED
        ):
            self._drop(entry_id)
            changed = True
        if status in (WordStatus.NEW, WordStatus.LEARNING):
            self._offer(entry_id)
        return changed

    def _offer(self, entry_id: EntryId) -> None:
        """A word that may enter now (set new again) takes its place among
        the words read ahead, if they were read past it."""
        facts = self._facts(entry_id)
        at = place(facts) if facts is not None else None
        if facts is None or at is None or self._ahead_after is None:
            return
        if not self._line_place() < at <= self._ahead_after:
            return
        if all(f.entry_id != entry_id for _, f in self._ahead):
            self._ahead.append((at, facts))
            self._ahead.sort(key=lambda pair: pair[0])

    def line_moved(self) -> bool:
        """The known line moved: words in the load it now covers wait
        (with their meetings, in case it moves back), and words never met
        give way to commoner ones. The caller refills."""
        changed: dict[EntryId, LoadWord] = {}
        gone = False
        for word in [w for w in self._words.values() if w.in_load]:
            if _untouched(word):
                self._drop(word.entry_id)
                gone = True
                continue
            facts = self._facts(word.entry_id)
            if facts is not None and not self._eligible(facts):
                self._leave(word, changed)
        self.reset_ahead()
        return self._save(changed) or gone

    def moved(self, old_id: EntryId, new_id: EntryId) -> None:
        """A dictionary update merged an entry into another: what the load
        kept under the old ID is the new one's, unless it has its own."""
        word = self._words.get(old_id)
        if word is None:
            return
        self._drop(old_id)
        if new_id not in self._words:
            self._put(replace(word, entry_id=new_id), None)

    def clear(self) -> None:
        """The learner deleted their learning data: the store's rows went
        with it. The caller refills."""
        self._words.clear()
        self._members = 0
        self._all_touched = True
        self.reset_ahead()
        self._counter = MeetingCounter(self._day_of)

    # -- meetings -------------------------------------------------------------------

    def caption_finished(
        self, caption_id: str, words: Iterable[WordInLine], now: datetime
    ) -> bool:
        if self.rules is None:
            return False
        return self._met(
            self._counter.finished(
                caption_id, words, now, self.rules.counting, self._last_met
            ),
            now,
        )

    def caption_withdrawn(self, caption_id: str, now: datetime) -> bool:
        if self.rules is None:
            return False
        return self._met(self._counter.withdrawn(caption_id), now)

    def _last_met(self, entry_id: EntryId) -> datetime | None:
        word = self._words[entry_id]
        if not word.in_load or word.stage is Stage.READY:
            raise KeyError(entry_id)
        return word.last_met

    def _met(self, deltas: Mapping[EntryId, int], now: datetime) -> bool:
        if not deltas:
            return False
        changed: dict[EntryId, LoadWord] = {}
        for entry_id, delta in deltas.items():
            word = self._words.get(entry_id)
            if word is None or not word.in_load or word.stage is Stage.READY:
                continue
            word = replace(
                word,
                meetings=max(0, word.meetings + delta),
                last_met=now if delta > 0 else None,
            )
            self._words[entry_id] = changed[entry_id] = word
        self._make_room(changed)
        return self._save(changed)

    # -- inside ------------------------------------------------------------------------

    def _make_room(self, changed: dict[EntryId, LoadWord]) -> None:
        """Moves every word that has had its meetings on, while the next
        colour has room: from green down, so a word leaving a colour lets
        the one behind it in; the most meetings first, then the commonest.
        Again until nothing moves: a word heard many times in one caption
        can move more than one stage."""
        rules = self.rules
        if rules is None:
            return
        by_stage: dict[Stage, list[LoadWord]] = {stage: [] for stage in Stage}
        due = False
        for word in self._words.values():
            if word.in_load:
                by_stage[word.stage].append(word)
                due = due or (
                    word.meetings >= rules.step and word.stage is not Stage.READY
                )
        while due:
            due = False
            for stage in reversed(COLOURS):
                onward = Stage(stage + 1)
                waiting = sorted(
                    (w for w in by_stage[stage] if w.meetings >= rules.step),
                    key=lambda w: (-w.meetings, w.place or 10**9, w.entry_id),
                )
                for word in waiting:
                    if (
                        rules.stage_limit
                        and onward is not Stage.READY
                        and len(by_stage[onward]) >= rules.stage_limit
                    ):
                        break
                    moved = replace(
                        word, stage=onward, meetings=word.meetings - rules.step
                    )
                    by_stage[stage].remove(word)
                    by_stage[onward].append(moved)
                    self._words[word.entry_id] = changed[word.entry_id] = moved
                    self._touched.add(word.entry_id)
                    due = True

    def _read_ahead(self, wanted: int) -> None:
        """Reads the dictionary on until `wanted` words that can enter
        wait in `_ahead`, or it has no more."""
        if self._ahead_after is None:
            self._ahead_after = self._line_place()
        have = sum(1 for _, f in self._ahead if self._can_enter(f))
        batch_size = max(200, 2 * (wanted - have))
        while have < wanted and not self._exhausted:
            batch = self._placed(self._ahead_after, batch_size)
            if not batch:
                self._exhausted = True
                break
            self._ahead_after = max(self._ahead_after + 1, max(at for at, _ in batch))
            for at, facts in batch:
                if self._can_enter(facts):
                    self._ahead.append((at, facts))
                    have += 1
            batch_size *= 2  # a line kept as a level: many known words to pass

    def reset_ahead(self) -> None:
        """What was read ahead is out of date (the line moved, a status
        changed, words left to wait): read again from the line when next
        wanted."""
        self._ahead, self._ahead_after, self._exhausted = [], None, False

    def _can_enter(self, facts: EntryFacts) -> bool:
        word = self._words.get(facts.entry_id)
        if word is not None and word.standing in (Standing.IN, Standing.SET_ASIDE):
            return False
        return self._eligible(facts)  # a graduated word: only if new again

    def _enter(
        self,
        facts: EntryFacts,
        at: int | None,
        now: datetime,
        by_hand: bool,
        changed: dict[EntryId, LoadWord] | None,
    ) -> None:
        word = self._words.get(facts.entry_id)
        if word is not None and word.standing is Standing.WAITING:
            word = replace(word, standing=Standing.IN, by_hand=word.by_hand or by_hand)
        else:
            word = LoadWord(
                facts.entry_id,
                Standing.IN,
                Stage.RED,
                0,
                by_hand,
                at,
                now,
            )
        self._put(word, changed)

    def _leave(self, word: LoadWord, changed: dict[EntryId, LoadWord]) -> None:
        """Out of the load, to wait: a word never met and not added by
        hand isn't worth a row."""
        if _untouched(word):
            self._drop(word.entry_id)
            changed.pop(word.entry_id, None)
        else:
            self._put(replace(word, standing=Standing.WAITING), changed)

    def _put(self, word: LoadWord, changed: dict[EntryId, LoadWord] | None) -> None:
        old = self._words.get(word.entry_id)
        self._members += word.in_load - (old.in_load if old else 0)
        if _shown(old) != _shown(word):
            self._touched.add(word.entry_id)
        self._words[word.entry_id] = word
        if changed is None:
            self._store.save([_stored(word)])
        else:
            changed[word.entry_id] = word

    def _drop(self, entry_id: EntryId) -> None:
        word = self._words.pop(entry_id, None)
        if word is not None:
            self._members -= word.in_load
            if word.in_load:
                self._touched.add(entry_id)
            self._store.delete([entry_id])

    def _save(self, changed: Mapping[EntryId, LoadWord]) -> bool:
        if changed:
            self._store.save([_stored(w) for w in changed.values()])
        return bool(changed)


def _shown(word: LoadWord | None) -> Stage | None:
    return word.stage if word is not None and word.in_load else None


def _untouched(word: LoadWord) -> bool:
    return (
        word.in_load
        and word.stage is Stage.RED
        and word.meetings == 0
        and not word.by_hand
    )


def _stored(word: LoadWord) -> StoredLoadWord:
    return StoredLoadWord(
        word.entry_id,
        word.standing.value,
        int(word.stage),
        word.meetings,
        word.by_hand,
        word.place,
        word.entered_at,
        word.last_met,
        word.graduated_at,
    )


def _from_stored(row: StoredLoadWord) -> LoadWord:
    return LoadWord(
        EntryId(row.entry_id),
        Standing(row.standing),
        Stage(row.stage),
        max(0, row.meetings),
        row.by_hand,
        row.place,
        row.entered_at,
        row.last_met,
        row.graduated_at,
    )
