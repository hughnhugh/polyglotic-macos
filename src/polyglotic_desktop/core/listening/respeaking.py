"""Re-speaking: hold a key and say what the other person said - captioned and translated as theirs.

polyglotic-hq 567 and the desktop's decision 0274 (the user, 2026-11-20:
"Dictation for other user input ... arguably better than self-dictate").
A call's voice too faint or garbled, a game's chat over its music, a
friend in the room: the learner repeats what they heard into their own
mic, and it's captioned **as the other person's** - in their window, under
their label, on their side, heard as their language and translated into
the learner's - and kept in their transcript, marked re-spoken.

- **Whose:** the watched caption window’s captured source (`respoken_for`) -
  an app, everything the PC plays, the sample - never the mic or
  dictation. With nothing else captioned there's no one to re-speak for:
  the press says so and the mic stays closed.
- **As theirs, on the wire too:** each piece goes to the server as a
  finished caption of that source (`Respeaking.cut`): its id and category,
  so the server hears it in that source's spoken language, translates it
  into that source's targets and keeps it in that source's context - and
  its mic-bleed check doesn't drop it as an echo of their speech, as it
  would a "You" line. No protocol change: the caption ids are the app's,
  and `Respeaking.respoken` names those it sent, so their lines are marked.
- **One hold, one piece**, as dictation's (`dictation.MIN_HOLD_SEC`,
  `PIECE_MAX_SEC` cuts, `MAX_HOLD_SEC`): sent when the key is let go, so
  the speech model sees the whole sentence; a longer hold is cut.
- **The key** (`KeyGesture`): its own by default, or dictation's: a
  hold dictates as before, a tap then a hold re-speaks. Dictation's own
  holds are unchanged; a stray tap no longer says "Hold the key while you
  speak" while re-speaking is on (it's half of a tap-and-hold).
- **The sign** says whose it's for while held ("Re-speaking for Discord"),
  then nothing once it's captioned - the caption shows - or why not
  (`Said`).

No I/O here: the key, the mic, the session and the sign are `main`'s and
the interface's.
"""

import uuid
from collections import deque
from collections.abc import Callable, Iterable
from enum import StrEnum

from polyglotic_desktop.core.listening.captions import CaptionKind, CaptionUpdate
from polyglotic_desktop.core.listening.dictation import (
    ANSWER_WITHIN_SEC,
    MIN_HOLD_SEC,
    Stage,
)
from polyglotic_desktop.core.listening.sources import DICTATION, MIC, Source, SourceId
from polyglotic_desktop.core.listening.timing import (
    CaptionId,
    SpeechKind,
    TranscriptionRequest,
    WithdrawalReason,
)
from polyglotic_desktop.core.shared.tunables import tunable

DEFAULT_RESPEAK_KEY = "f8"
"""Layout-independent hold key, separate from dictation and AltGr."""

RESPEAK_PEAK = tunable(
    "respeaking.peak_target",
    0.25,
    "fraction of full scale",
    (0.05, 0.95),
    source="626 held microphone audio; leave headroom for peaks",
)
RESPEAK_GAIN = tunable(
    "respeaking.max_gain",
    8.0,
    "linear gain",
    (1.0, 16.0),
    source="626 held microphone audio; bound amplification of quiet recordings",
)


TAP_GAP_SEC = 0.4
"""With one key for both: a hold that starts this soon after a tap (a
press shorter than `MIN_HOLD_SEC`) re-speaks."""
RESPOKEN_KEPT = 500
"""The caption ids re-spoken that are remembered, newest kept - far more
than a caption window or transcript lists at once from re-speaking."""


class Use(StrEnum):
    """What a hold of the key is for."""

    DICTATE = "dictate"
    RESPEAK = "respeak"


class KeyGesture:
    """Which a hold is, when one key does both (polyglotic-hq 567): a hold
    dictates; a tap then a hold re-speaks. With dictation off, every hold
    re-speaks; with re-speaking off, every hold dictates."""

    def __init__(self) -> None:
        self._down_at: float | None = None
        self._tapped_at: float | None = None
        """When the last tap (a press under `MIN_HOLD_SEC`) came up."""
        self.use: Use | None = None
        """What the hold under way is for; None: the key is up."""

    def down(self, now: float, dictation: bool, respeaking: bool) -> Use | None:
        """The key went down: what this hold is for - None if neither is on
        or a hold is already under way (key auto-repeat)."""
        if self._down_at is not None:
            return None
        tapped = self._tapped_at is not None and now - self._tapped_at <= TAP_GAP_SEC
        self._tapped_at = None
        self._down_at = now
        if respeaking and (tapped or not dictation):
            self.use = Use.RESPEAK
        elif dictation:
            self.use = Use.DICTATE
        else:
            self.use = None
        return self.use

    def other(self) -> None:
        """A shortcut using this key does not count as a tap."""
        self._down_at = self._tapped_at = None

    def up(self, now: float) -> tuple[Use | None, bool]:
        """The key came up: what the hold was for, and whether it was a tap
        (shorter than `MIN_HOLD_SEC`) - which a hold may follow."""
        use, self.use = self.use, None
        tap = self._down_at is not None and now - self._down_at < MIN_HOLD_SEC
        self._tapped_at = now if tap else None
        self._down_at = None
        return use, tap


def respoken_for(
    captured: Iterable[SourceId], watched: Iterable[SourceId]
) -> SourceId | None:
    """The pointed-at or most recently visited eligible window, then the first."""
    others = tuple(s for s in captured if s not in (MIC, DICTATION))
    return next((s for s in watched if s in others), next(iter(others), None))


def recognition_missed(update: CaptionUpdate) -> bool:
    """A final answer with no words, or a recognition the server discarded as empty or invented."""
    if update.kind is CaptionKind.FINISHED:
        return not any(clause.original.strip() for clause in update.clauses)
    return update.kind is CaptionKind.WITHDRAWN and update.reason in (
        WithdrawalReason.EMPTY,
        WithdrawalReason.NEAR_SILENCE_PHRASE,
    )


class Said(StrEnum):
    """What the sign says once a hold is over and nothing more is coming."""

    RESPOKEN = "respoken"  # captioned: the caption shows, nothing to say
    NOTHING_HEARD = "nothing_heard"
    NO_MIC = "no_mic"
    TOO_SHORT = "too_short"
    CANCELLED = "cancelled"
    NO_ANSWER = "no_answer"
    NO_SERVER = "no_server"
    NO_SOURCE = "no_source"  # nothing else is captioned: no one to re-speak for


class Respeaking:
    """The holds of the re-speaking key, from the press to the caption back:
    at most one hold at a time (the mic is one), each hold's pieces sent as
    finished captions of the source it's for."""

    def __init__(self, new_id: Callable[[], str] = lambda: str(uuid.uuid4())) -> None:
        self._new_id = new_id
        self.stage = Stage.IDLE
        self.said: Said | None = None
        self.source: Source | None = None
        """Whose the hold under way is (`press`)."""
        self._pressed = 0.0
        self._last_in = False
        """The hold's last piece is cut (or had no audio)."""
        self._waiting: dict[CaptionId, float] = {}
        """The pieces sent and not answered yet, and when each was sent."""
        self._heard = False
        """A piece of the hold under way was captioned."""
        self._respoken: deque[CaptionId] = deque(maxlen=RESPOKEN_KEPT)
        self._respoken_set: set[CaptionId] = set()

    def press(self, now: float, source: Source | None) -> bool:
        """The key went down, for `source`: True if the mic should open.
        None: nothing else is captioned (`Said.NO_SOURCE`)."""
        if self.stage is not Stage.IDLE:
            return False
        self.said = None
        self.source = source
        if source is None:
            self.said = Said.NO_SOURCE
            return False
        self.stage = Stage.LISTENING
        self._pressed = now
        self._last_in = False
        self._heard = False
        return True

    def release(self, now: float) -> bool:
        """The key came up: True if what was said goes on (the mic's tail,
        then the last piece); False - and over - if it was too short."""
        if self.stage is not Stage.LISTENING:
            return False
        if now - self._pressed < MIN_HOLD_SEC:
            self._over(Said.TOO_SHORT)
            return False
        self.stage = Stage.WORKING
        return True

    def cut(
        self, start: float, end: float, now: float, last: bool
    ) -> TranscriptionRequest:
        """A piece of the hold under way, from `start` to `end` on the app's
        clock (`last`: its last): the request to send - a finished caption
        of its source."""
        assert self.source is not None
        caption_id = CaptionId(self._new_id())
        self._waiting[caption_id] = now
        self._last_in = self._last_in or last
        self._respoken.append(caption_id)
        self._respoken_set = set(self._respoken)
        return TranscriptionRequest(
            caption_id, SpeechKind.FINISHED, self.source, start, end
        )

    def nothing_cut(self, last: bool, mic_failed: bool = False) -> None:
        """A piece had no audio; `last`: the hold's last."""
        self._last_in = self._last_in or last
        self._settle(mic_failed)

    def answer(self, update: CaptionUpdate) -> bool:
        """The server's answer to a caption: True if it was a piece of a
        hold's (live updates aside)."""
        if update.caption_id not in self._waiting or update.kind is CaptionKind.LIVE:
            return False
        del self._waiting[update.caption_id]
        if update.kind is CaptionKind.FINISHED and not recognition_missed(update):
            self._heard = True
        self._settle()
        return True

    def overdue(self, now: float) -> bool:
        """A piece unanswered for `ANSWER_WITHIN_SEC`: the hold given up
        (`Said.NO_ANSWER`). True if it was."""
        late = any(now - sent > ANSWER_WITHIN_SEC for sent in self._waiting.values())
        if late:
            self._waiting.clear()
            self._over(Said.NO_ANSWER)
        return late

    def cancel(self, said: Said = Said.CANCELLED) -> bool:
        """Esc, or the session can't answer (`Said.NO_SERVER`): the hold
        under way and what it waits for given up. True if there was one."""
        if self.stage is Stage.IDLE:
            return False
        self._waiting.clear()
        self._over(said)
        return True

    def is_respoken(self, caption_id: CaptionId) -> bool:
        """Whether `caption_id` was re-spoken here (one of the newest
        `RESPOKEN_KEPT`) - its line is marked so."""
        return caption_id in self._respoken_set

    def _settle(self, mic_failed: bool = False) -> None:
        """Let go, its last piece in and every piece answered: over."""
        if self.stage is Stage.WORKING and self._last_in and not self._waiting:
            self._over(
                Said.RESPOKEN
                if self._heard
                else Said.NO_MIC
                if mic_failed
                else Said.NOTHING_HEARD
            )

    def _over(self, said: Said) -> None:
        self.stage = Stage.IDLE
        self.said = said
        self._last_in = False
