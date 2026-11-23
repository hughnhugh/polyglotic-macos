"""The playout: a caption's words shown one by one, each a constant delay
after it was said (Steady; polyglotic-hq 526, decision 0245).

Live updates arrive in bursts - a second's words at once - and their newest
word is the one most often reheard differently. Audio and video solve the
same problem with presentation times: play each thing at its own moment
plus a fixed delay, and the bursts become the speaker's rhythm again. The
playout does that for words. It stands between the caption updates the
server sends and whoever shows them, as a pure state machine with no clock
of its own:

- **Heard:** each live or finished update goes in (`heard`). Its words get
  the moment they were said: the server's own word times where the update
  carries them (`Clause.words`), else an estimate - the words new in this
  update were said between the end of the speech the update before answered
  and the end of this one's, spread by their syllables, less the lateness
  measured for that guess (`ESTIMATE_LATE_SEC`). A word keeps its moment
  once given.
- **Released:** a word is shown at its moment plus the delay
  (`PlayoutRules.delay`), never two closer than `MIN_GAP_SEC`, one caption
  of a source after another. A word that arrives after its moment is shown
  at once. A live update's newest word is held back until the next update
  confirms it (`hold_back`) unless the server already calls it established;
  a finished caption's words are all released, still at their moments.
- **Shown stays shown:** a word once shown stays while the newer hearing
  still has it. A hearing that changes shown words changes them in place -
  the caption display's quiet correction (`established`).
- **What comes out** (`heard` and `release` return them, to be shown at
  once) are caption updates again: a live update whose clauses stop at the
  last word shown and whose `established` count covers every word shown, so
  the display draws them as final; and, when a finished caption's last word
  is shown, the server's finished update itself. A clause's translation and
  word links come with it once the complete original is visible: one
  translation per clause, where a live caption's was rewritten with every
  update. With `Ahead.WAITING` (karaoke), the complete original can already
  be visible in faint ink. Its confirmed translation comes with it unless
  the reading path delays it. The `established` count gives the lit prefix.
  `Ahead.ALL` adds the held-back newest word.

Holds caption text: never log it.
"""

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from difflib import SequenceMatcher
from enum import StrEnum

from polyglotic_desktop.core.listening.captions import (
    CaptionKind,
    CaptionUpdate,
    Clause,
)
from polyglotic_desktop.core.listening.sources import SourceId
from polyglotic_desktop.core.listening.timing import CaptionId

DELAY_SEC = 1.75
"""The default delay between a word being said and being shown. With the
newest word held back, a word is first safe to show about a live update's
interval and the server's answer after it was said; at 1.75 s 80-94 % of
words land on their moment (polyglotic-hq 528, updates every 1.0 s)."""

EAGER_DELAY_SEC = 1.5
"""The delay that goes with showing the newest word too (`hold_back` 0):
a quarter second sooner, for about twice the shown words later changed."""

DELAY_RANGE = (1.0, 3.0)

MIN_GAP_SEC = 0.06
"""Never two words closer than this: words that arrive late in a clump
still come one after another."""

ESTIMATE_LATE_SEC = 0.3
"""How much later than the truth the syllable estimate puts a word, taken
off it: 0.27-0.42 s on six recorded streams (polyglotic-hq 528)."""

STALE_SEC = 8.0
"""A caption that was never finished stops holding back the captions after
it once it has had no update for this long."""

_KEPT_DONE = 3  # finished captions kept per source, for a join onto them

_PIECES = re.compile(r"[^\W_]+(?:['’\-][^\W_]+)*|(?:[\W_])+")
_VOWELS = re.compile(r"[aeiouy]+")
_TRAILING = " ,.!?;:。，！？、；：…"


class Ahead(StrEnum):
    """Which words not yet at their moment are in the updates the playout
    gives, for the display to draw faint (karaoke)."""

    NONE = "none"
    WAITING = "waiting"  # the words that will be released
    ALL = "all"  # and the held-back newest word


class ReadingPath(StrEnum):
    """What a learner reads first in a paced mode (decision 0253; the
    user's words for them on polyglotic-hq DECISIONS #230)."""

    FOLLOW = "follow"
    """The translation leads: to follow what is going on."""
    ACQUISITION = "acquisition"
    """What was said first; its translation a moment after each clause."""
    BOTH = "both"
    """Both together, a clause's translation as it ends. The default."""


TRANSLATION_AFTER_SEC = 2.0
"""Acquisition: how long after a clause is shown its translation comes,
unless the learner chooses (526's `paths-*` videos used 2 s)."""
TRANSLATION_AFTER_RANGE = (0.5, 6.0)


@dataclass(frozen=True, slots=True)
class PlayoutRules:
    delay: float = DELAY_SEC
    hold_back: int = 1
    """How many of a live update's newest words wait for the next update."""
    ahead: Ahead = Ahead.NONE
    established_only: bool = False
    """Only the words the server calls established are released while a
    caption is live (Calm): later, and the fewest shown words changed."""
    translation_after: float = 0.0
    """Seconds a clause's translation and links wait after its last word
    is shown (Acquisition: what was said first; decision 0253). 0: with
    its last word."""


Split = Callable[[str], Sequence[tuple[int, int]]]
"""A run of unspaced writing as words: spans `[start, end)` that cover it in
order (a dictionary's word split)."""


def _unspaced(char: str) -> bool:
    """A character of a writing without spaces between words: Chinese
    characters and kana."""
    return "㐀" <= char <= "䶿" or "一" <= char <= "鿿" or "぀" <= char <= "ヿ"


def each_character(run: str) -> Sequence[tuple[int, int]]:
    """Every character a word: the split used when no dictionary is given."""
    return [(i, i + 1) for i in range(len(run))]


@dataclass(frozen=True, slots=True)
class _Word:
    text: str  # with the punctuation and spaces after it (and, for a clause's first, before)
    key: str  # what two hearings of it share: letters and digits, lower case
    units: float  # about its syllables
    clause: int
    start: int  # where its text starts in the clause's original


def _units(bare: str, key: str) -> float:
    if _unspaced(bare[0]):
        return float(len(bare))
    if bare[0].isdigit():
        return min(4.0, float(len(bare)))
    vowels = len(_VOWELS.findall(key))
    if vowels:
        return float(min(5, max(1, vowels - (key.endswith("e") and len(key) > 3))))
    return float(min(5, max(1, round(len(key) / 2.5))))


def _runs(piece: str) -> list[str]:
    """`piece` cut where spaced and unspaced writing meet (我come)."""
    out: list[str] = []
    for char in piece:
        if out and _unspaced(out[-1][0]) == _unspaced(char):
            out[-1] += char
        else:
            out.append(char)
    return out


def _clause_words(text: str, clause: int, split: Split) -> list[_Word]:
    """`text` as words whose texts end to end are `text`."""
    found: list[list[str]] = []  # [shown, bare]
    lead = ""
    for match in _PIECES.finditer(text):
        piece = match.group()
        if not piece[0].isalnum():
            if found:
                found[-1][0] += piece
            else:
                lead += piece
            continue
        for run in _runs(piece):
            parts = [run[a:b] for a, b in split(run)] if _unspaced(run[0]) else [run]
            for part in parts:
                if part:
                    found.append([lead + part, part])
                    lead = ""
    if lead:  # nothing but punctuation: one word, so that it is shown at all
        found.append([lead, lead])
    words = []
    start = 0
    for shown, bare in found:
        key = "".join(c.lower() for c in bare if c.isalnum())
        words.append(
            _Word(shown, key, _units(bare, key) if key else 1.0, clause, start)
        )
        start += len(shown)
    return words


def word_beats(
    text: str, split: Split, clause: Clause | None = None
) -> tuple[tuple[int, ...], tuple[float, ...]]:
    """Steady's word boundaries and their spoken offsets from the first
    word, when this original carries word times. No times for translations."""
    words = _clause_words(text, 0, split)
    ends = tuple(word.start + len(word.text) for word in words)
    moments = _true_moments((clause,), words) if clause is not None else None
    offsets = tuple(t - moments[0] for t in moments) if moments else ()
    return ends, offsets


def _within(words: Sequence[_Word], chars: int) -> int:
    """How many of `words` lie in the first `chars` characters of their
    text - the word itself, whatever punctuation follows it."""
    count = at = 0
    for word in words:
        if at + len(word.text.rstrip(_TRAILING)) > chars:
            break
        at += len(word.text)
        count += 1
    return count


def _matched(old: Sequence[str], new: Sequence[str]) -> dict[int, int]:
    """Each word of `new` that is a word of `old`, in order: new index to old."""
    if list(old) == list(new[: len(old)]):
        return {i: i for i in range(len(old))}
    blocks = SequenceMatcher(
        None, list(old), list(new), autojunk=False
    ).get_matching_blocks()
    return {j + k: i + k for i, j, size in blocks for k in range(size)}


def carried(old: Sequence[str], new: Sequence[str], shown: int) -> int:
    """How many of `new`'s words are shown, given `shown` of `old`'s were:
    a word once shown stays shown while the newer hearing still has it,
    wherever it moved to - so, up to the last shown word the new hearing
    kept. Nothing alike: as many as were shown."""
    if shown <= 0:
        return 0
    was = list(old[:shown])
    if list(new[:shown]) == was:
        return shown
    end = 0
    for _a, b, size in SequenceMatcher(
        None, was, list(new), autojunk=False
    ).get_matching_blocks():
        if size:
            end = max(end, b + size)
    return end or min(shown, len(new))


@dataclass(slots=True)
class _Caption:
    update: CaptionUpdate
    words: list[_Word]
    moments: list[float]
    shown: int
    releasable: int
    heard_at: float
    speech_end: float
    given: object = None  # what was last given out, to give only changes
    sent_replacements: CaptionKind | None = None  # first draft and first final
    announced: bool = False  # whether an update of it has been given out
    whole_at: dict[str, float] = field(default_factory=dict)
    """When each clause, by its text, was shown whole (`translation_after`)."""
    revealed: set[str] = field(default_factory=set)
    """The clauses, by their text, whose translation has been given."""
    passed: bool = False  # never finished, and no longer waited for (`STALE_SEC`)

    @property
    def finished(self) -> bool:
        return self.update.kind is CaptionKind.FINISHED

    @property
    def done(self) -> bool:
        return self.finished and self.shown >= len(self.words)


@dataclass(slots=True)
class _Source:
    captions: dict[CaptionId, _Caption] = field(default_factory=dict)  # oldest first
    last_release: float = float("-inf")


class Playout:
    """The playout of every source's captions. Feed it each caption update
    with the time it came (`heard`), ask when the next word is due (`due`)
    and call `release` then; show what either returns. Times are seconds
    on the clock the updates' `times` are on (`time.perf_counter`).
    Not thread-safe: one caller at a time."""

    def __init__(
        self, rules: PlayoutRules | None = None, split: Split = each_character
    ) -> None:
        self.rules = rules or PlayoutRules()
        self._split = split
        self._sources: dict[SourceId, _Source] = {}

    def change(self, rules: PlayoutRules) -> None:
        """New rules, from the next word on."""
        self.rules = rules

    def clear(self) -> tuple[CaptionUpdate, ...]:
        """Stop pacing: every caption's latest update as the server sent
        it, to show now (the learner chose another mode mid-speech)."""
        out = tuple(
            c.update
            for source in self._sources.values()
            for c in source.captions.values()
            if not c.done
        )
        self._sources.clear()
        return out

    # -- in ------------------------------------------------------------------------

    def heard(self, update: CaptionUpdate, at: float) -> tuple[CaptionUpdate, ...]:
        """A caption update that came at `at`: what to show now."""
        out = list(self.release(at))
        source = self._sources.setdefault(update.source_id, _Source())
        if update.kind is CaptionKind.WITHDRAWN:
            gone = source.captions.pop(update.caption_id, None)
            if gone is None or gone.announced:
                out.append(update)  # one never shown is never taken back
            return tuple(out)
        before = source.captions.get(update.caption_id)
        old_keys: list[str] = []
        old_moments: list[float] = []
        shown = 0
        speech_start, speech_end = self._speech(update, at)
        previous_end = speech_start
        announced = False
        if before is not None:
            old_keys = [w.key for w in before.words]
            old_moments = list(before.moments)
            shown, previous_end, announced = (
                before.shown,
                before.speech_end,
                before.announced,
            )
        for other in update.replaces:  # a join: what its captions showed is carried
            joined = (
                source.captions.pop(other, None) if other != update.caption_id else None
            )
            if joined is not None:
                old_keys = old_keys[:shown] + [
                    w.key for w in joined.words[: joined.shown]
                ]
                old_moments = old_moments[:shown] + joined.moments[: joined.shown]
                shown += joined.shown
        words = [
            word
            for index, clause in enumerate(update.clauses)
            for word in _clause_words(clause.original, index, self._split)
        ]
        keys = [w.key for w in words]
        moments = self._moments(
            update, words, old_keys, old_moments, speech_start, speech_end, previous_end
        )
        kept = carried(old_keys, keys, shown)
        finished = update.kind is CaptionKind.FINISHED
        if finished:
            releasable = len(words)
        else:
            held = len(words) if self.rules.established_only else self.rules.hold_back
            releasable = max(
                kept, _within(words, update.established), len(words) - held
            )
        caption = _Caption(
            update,
            words,
            moments,
            kept,
            releasable,
            at,
            speech_end,
            announced=announced,
        )
        if before is not None:
            caption.given = before.given
            caption.whole_at = before.whole_at
            caption.revealed = before.revealed
            source.captions[update.caption_id] = caption  # keeps its place
        else:
            source.captions[update.caption_id] = caption
        out += self._changes(source)
        self._forget(source)
        return tuple(out)

    @staticmethod
    def _speech(update: CaptionUpdate, at: float) -> tuple[float, float]:
        if update.times is None:  # speech this app didn't send: as if just said
            return at, at
        return update.times.speech_start, update.times.speech_end

    def _moments(
        self,
        update: CaptionUpdate,
        words: Sequence[_Word],
        old_keys: Sequence[str],
        old_moments: Sequence[float],
        speech_start: float,
        speech_end: float,
        previous_end: float,
    ) -> list[float]:
        true = _true_moments(update.clauses, words)
        if true is not None:
            return true
        # the estimate: a word heard before keeps its moment; the new ones
        # were said since the last update's speech ended, by their syllables
        pairs = _matched(old_keys, [w.key for w in words])
        moments: list[float | None] = [
            old_moments[pairs[j]] if j in pairs else None for j in range(len(words))
        ]
        known = [j for j, moment in enumerate(moments) if moment is not None]
        tail = known[-1] + 1 if known else 0
        start = speech_start
        if known:
            start = max(previous_end, old_moments[pairs[known[-1]]] + ESTIMATE_LATE_SEC)
        total = sum(w.units for w in words[tail:]) or 1.0
        run = 0.0
        for j in range(tail, len(words)):
            run += words[j].units
            moments[j] = (
                start + max(0.0, speech_end - start) * run / total - ESTIMATE_LATE_SEC
            )
        out: list[float] = []
        floor = speech_start - ESTIMATE_LATE_SEC
        for moment in moments:
            floor = max(floor, moment) if moment is not None else floor
            out.append(floor)
        return out

    # -- out -----------------------------------------------------------------------

    def due(self) -> float | None:
        """When the next word is to be shown; None while none waits."""
        times = [
            t
            for source in self._sources.values()
            if (t := self._due(source)) is not None
        ]
        times += [
            caption.heard_at + STALE_SEC
            for source in self._sources.values()
            if (caption := self._blocking(source)) is not None
        ]
        times += [
            when
            for source in self._sources.values()
            for caption in source.captions.values()
            for when in self._reveals(caption)
        ]
        return min(times) if times else None

    def _reveals(self, caption: _Caption) -> list[float]:
        """When each translation still held back is due (`translation_after`)."""
        after = self.rules.translation_after
        if after <= 0.0:
            return []
        return [
            whole + after
            for text, whole in caption.whole_at.items()
            if text not in caption.revealed
        ]

    def _note_whole(self, caption: _Caption, when: float) -> None:
        """The clauses of `caption` shown whole as of its last shown word."""
        words, shown = caption.words, caption.shown
        if not shown:
            return
        clause = words[shown - 1].clause
        last = clause if shown == len(words) else clause - 1
        if shown < len(words) and words[shown].clause > clause:
            last = clause
        if shown == len(words) and not caption.finished:
            last = clause - 1  # a live caption's last clause may still grow
        for each in caption.update.clauses[: last + 1]:
            caption.whole_at.setdefault(each.original, when)

    def release(self, at: float) -> tuple[CaptionUpdate, ...]:
        """Advance each source by one due word and reveal due translations."""
        out: list[CaptionUpdate] = []
        for source in self._sources.values():
            changed = False
            while (blocked := self._blocking(source)) is not None:
                if blocked.heard_at + STALE_SEC > at:
                    break
                blocked.passed = True
                changed = True
            if (when := self._due(source)) is not None and when <= at:
                caption = self._current(source)
                assert caption is not None
                caption.shown += 1
                source.last_release = at
                changed = True
                self._note_whole(caption, at)
            for caption in source.captions.values():
                for text, whole in caption.whole_at.items():
                    due = whole + self.rules.translation_after
                    if text not in caption.revealed and due <= at:
                        caption.revealed.add(text)
                        changed = True
            if changed:
                out += self._changes(source)
                self._forget(source)
        return tuple(out)

    def _current(self, source: _Source) -> _Caption | None:
        """The caption whose words are being shown: the oldest not done."""
        for caption in source.captions.values():
            if not caption.done and not caption.passed:
                return caption
        return None

    def _due(self, source: _Source) -> float | None:
        caption = self._current(source)
        if caption is None or caption.shown >= caption.releasable:
            return None
        moment = caption.moments[caption.shown]
        gap = MIN_GAP_SEC
        if caption.shown and moment + self.rules.delay <= source.last_release:
            # Keep the speaker's word intervals when an answer or a paint
            # tick is late. The speech clock itself keeps longer pauses.
            gap = max(
                gap, min(moment - caption.moments[caption.shown - 1], self.rules.delay)
            )
        return max(
            moment + self.rules.delay,
            source.last_release + gap,
            caption.heard_at,
        )

    def _blocking(self, source: _Source) -> _Caption | None:
        """An unfinished caption with no releasable word and another caption
        waiting behind it. Its deadline wakes the window even in silence."""
        caption = self._current(source)
        if (
            caption is None
            or caption.finished
            or caption.shown < caption.releasable
            or caption is next(reversed(source.captions.values()))
        ):
            return None
        return caption

    def _changes(self, source: _Source) -> list[CaptionUpdate]:
        out = []
        current = self._current(source)
        for caption in source.captions.values():
            shown = caption.shown
            if not shown and caption is not current:
                continue  # waiting ink belongs to the caption being spoken
            upto = shown
            if self.rules.ahead is Ahead.WAITING:
                upto = max(shown, caption.releasable)
            elif self.rules.ahead is Ahead.ALL:
                upto = len(caption.words)
            if not upto:
                continue
            held = self.rules.translation_after > 0.0
            update = caption.update if caption.done else _partial(caption, upto, held)
            if held and caption.done:
                update = _withheld(caption)
            # A translation or its links can arrive between two word ticks.
            state = (
                update.kind,
                update.established,
                update.clauses,
                caption.update if caption.done else None,
            )
            if caption.given == state:
                continue
            caption.given = state
            if update.replaces:
                # The deck can take over placed words on the first draft.
                # A caption history retires replaced IDs only at the finish.
                if update.display_member is None:
                    sent = caption.announced  # an ordinary audio join is announced once
                else:
                    sent = caption.sent_replacements is update.kind
                if sent:
                    update = replace(update, replaces=())
                caption.sent_replacements = update.kind
            caption.announced = True
            out.append(update)
        return out

    def _forget(self, source: _Source) -> None:
        done = [
            key
            for key, c in source.captions.items()
            if (c.done or c.passed) and not self._reveals(c)
        ]
        for key in done[:-_KEPT_DONE]:
            del source.captions[key]


def _true_moments(
    clauses: Sequence[Clause], words: Sequence[_Word]
) -> list[float] | None:
    """Each word's moment from the server's word times (`Clause.words`): the
    start of the first timed span that touches it; a word without one, the
    moment of the word before. None when the update carries no times."""
    if not any(clause.words for clause in clauses):
        return None
    out: list[float] = []
    floor = float("-inf")
    for word in words:
        lo, hi = word.start, word.start + len(word.text)
        starts = [
            t.start
            for t in clauses[word.clause].words
            if t.original[0] < hi and t.original[1] > lo
        ]
        floor = max(floor, min(starts)) if starts else floor
        out.append(floor)
    first = next((t for t in out if t != float("-inf")), None)
    if first is None:
        return None
    return [first if t == float("-inf") else t for t in out]


def _withheld(caption: _Caption) -> CaptionUpdate:
    """A finished caption, all shown, without the translations and links
    still held back (`PlayoutRules.translation_after`) - itself once none
    is."""
    update = caption.update
    if all(clause.original in caption.revealed for clause in update.clauses):
        return update
    return replace(
        update,
        clauses=tuple(
            clause
            if clause.original in caption.revealed
            else Clause(clause.original, written_in=clause.written_in)
            for clause in update.clauses
        ),
    )


def _partial(caption: _Caption, upto: int, held: bool = False) -> CaptionUpdate:
    """The caption as a live update that stops at its `upto`th word, the
    `shown` first of them established. A clause's translation and links
    come with the complete visible clause, or at its reveal deadline
    when `held` (`PlayoutRules.translation_after`)."""
    update, words, shown = caption.update, caption.words, caption.shown
    last_clause = words[upto - 1].clause
    confirmed_end = caption.finished or (
        upto == len(words) and _within(words, update.established) == upto
    )
    clauses: list[Clause] = []
    for index, clause in enumerate(update.clauses[: last_clause + 1]):
        original = clause.original
        if index == last_clause:
            original = "".join(w.text for w in words[:upto] if w.clause == index)
        # In karaoke, the complete original can already be visible in
        # waiting ink. Its supplied translation can occupy the paired row
        # immediately. Acquisition still waits for the spoken words.
        visible = original == clause.original
        confirmed = confirmed_end or index < len(update.clauses) - 1
        if visible and confirmed and (not held or clause.original in caption.revealed):
            clauses.append(clause)
        else:  # no space left hanging at the end of what is shown
            clauses.append(
                Clause(original.rstrip() if index == last_clause else original)
            )
    established = sum(len(w.text) for w in words[:shown])
    established = min(established, sum(len(c.original) for c in clauses))
    return replace(
        update, kind=CaptionKind.LIVE, clauses=tuple(clauses), established=established
    )
