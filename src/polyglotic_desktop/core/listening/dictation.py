"""Dictation: hold a key, speak, let go - the words typed where the cursor is.

polyglotic-hq 283 and the desktop's decision 0073. The learner's mic,
while they hold the dictation key, is a source of its own on the listening
session (`DICTATION`, category mic): each piece of a hold goes to the
server as one finished caption, never translated (no targets), heard in
the language chosen for dictation or detected. Its answer becomes the text
typed into the program that has the keyboard - never a caption line,
never kept.

- **One hold, one piece of speech**, sent when the key is let go, so the
  speech model sees the whole of it and punctuates and capitalises it as a
  whole. The proof of concept typed phrase by phrase as the learner spoke,
  and every pause started a new "sentence" (the user's feedback,
  2026-11-09). A hold longer than `PIECE_MAX_SEC` is cut into pieces at
  its quietest moment near the limit (`quietest_cut`), each typed as its
  text comes back.
- **In order:** `Dictation` keeps every piece sent, and hands out text to
  type only once the pieces before it are answered, so a fast answer never
  jumps a slow one; a new hold can start while the last one's text is on
  its way.
- **What's typed** (`dictated_text`): the clauses joined, English fillers
  on their own taken out, Australian spelling if asked for, and a space
  after - none after Chinese or Japanese - so the next dictation doesn't
  run on.
- **Nothing typed** when the press was too short (`MIN_HOLD_SEC`), the
  server heard nothing worth typing (a withdrawn answer), Esc cancelled
  it, no answer came within `ANSWER_WITHIN_SEC` - or, at once, the
  listening session can't be answered (`no_server`: the server can't be
  reached, or the session is closed - polyglotic-hq 299; it waited the
  10 s before). `Dictation.said` names the outcome the sign shows.

No I/O here: the key, the mic, the session, the typing and the sign are
`main`'s and the interface's.
"""

import re
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum

from polyglotic_desktop.core.listening.australian import australian_spelling
from polyglotic_desktop.core.listening.captions import (
    CaptionKind,
    CaptionUpdate,
    Language,
)
from polyglotic_desktop.core.listening.history import is_cjk, join_text
from polyglotic_desktop.core.listening.sources import DICTATION, Source
from polyglotic_desktop.core.listening.spoken import SPOKEN_LANGUAGES
from polyglotic_desktop.core.listening.timing import (
    CaptionId,
    SpeechKind,
    TranscriptionRequest,
)
from polyglotic_desktop.ports.capture import SourceCategory

DICTATION_SOURCE = Source(DICTATION, SourceCategory.MIC)
"""Dictation's source: the learner's mic while the dictation key is held."""

MIN_HOLD_SEC = 0.3
"""A press shorter than this sends nothing: a stray tap of the key."""
TAIL_SEC = 0.2
"""The mic stays open this long after the key comes up, so a last word
said as the key is let go isn't clipped."""
PIECE_MAX_SEC = 30.0
"""The longest piece of speech sent: the server counts at most 30 s a
caption, and decodes at most 60 s."""
CUT_SEARCH_SEC = 4.0
"""A long hold is cut at its quietest moment in this many seconds before
`PIECE_MAX_SEC`."""
ANSWER_WITHIN_SEC = 10.0
"""A piece unanswered this long is given up, with every piece after it."""
SESSION_IDLE_SEC = 60.0
"""A listening session opened only for dictation closes this long after
the last dictation's answer."""
MAX_HOLD_SEC = 300.0
"""A hold this long ends as if the key came up: a key stuck down (or one
whose release was missed) never leaves the mic open."""

ENGLISH = Language("en")
_FILLERS = re.compile(r"\b(?:um+|uh+|erm|er|hmm+)\b[,.]?\s*", re.IGNORECASE)

DICTATION_LANGUAGES: tuple[Language, ...] = SPOKEN_LANGUAGES
"""Every language dictation can be set to: the spoken languages, the
speech model's own list (`core.listening.spoken`; polyglotic-hq 317 made
it every caption window's too). Set to one, the model is told the
language and never detects another; Mandarin comes back in Simplified
characters and Cantonese in Hong Kong Traditional (the server's
`core/translation/scripts.py`)."""


class Said(StrEnum):
    """What the sign says once a hold is over and nothing more is coming."""

    TYPED = "typed"
    NOTHING_HEARD = "nothing_heard"
    NO_MIC = "no_mic"  # the mic gave no audio, and said why
    TOO_SHORT = "too_short"
    CANCELLED = "cancelled"
    NO_ANSWER = "no_answer"
    NO_SERVER = "no_server"  # the session can't be answered now (299)
    WINDOW_CHANGED = "window_changed"
    NOT_TYPED = "not_typed"  # the OS took none of it
    NOT_ALLOWED = "not_allowed"  # the OS hasn't given the app leave to type (438)
    SIGN_IN = "sign_in"


class Stage(StrEnum):
    IDLE = "idle"
    LISTENING = "listening"  # the key is held
    WORKING = "working"  # let go: text on its way


@dataclass(frozen=True, slots=True)
class ToType:
    """A piece's text, ready to type, and where: `target` is the window
    that had the keyboard when the piece was cut (the OS's handle, opaque
    here) - typed only if it still has it."""

    text: str
    target: int


@dataclass(slots=True)
class _Piece:
    caption_id: CaptionId
    hold: int
    sent: float
    target: int
    last: bool  # the hold's last piece
    text: str | None = None  # "" when nothing worth typing was heard


class Dictation:
    """The learner's holds of the dictation key and their pieces, in order."""

    def __init__(self, new_id: Callable[[], CaptionId] | None = None) -> None:
        self._new_id = new_id or (lambda: CaptionId(str(uuid.uuid4())))
        self.hold = 0
        """The current (or last) hold's number, from 1."""
        self._pressed: float | None = None
        """When the key went down, while it's held."""
        self._released = False
        """The key came up on a hold whose last piece isn't cut yet."""
        self._waiting: list[_Piece] = []
        self._typed: set[int] = set()
        """The holds some of whose text was typed."""
        self.said: Said | None = None
        """The last outcome the sign should say; None once a new hold starts."""

    @property
    def stage(self) -> Stage:
        if self._pressed is not None:
            return Stage.LISTENING
        if self._waiting or self._released:
            return Stage.WORKING
        return Stage.IDLE

    def press(self, now: float) -> bool:
        """The key went down: a new hold, unless one is held already."""
        if self._pressed is not None:
            return False
        self._pressed, self._released = now, False
        self.hold += 1
        self.said = None
        return True

    def release(self, now: float) -> bool:
        """The key came up: True if the hold's speech is to be sent (its
        last piece follows, `cut(..., last=True)`), False if it was too short
        - nothing sent, `said` TOO_SHORT."""
        if self._pressed is None:
            return False
        held, self._pressed = now - self._pressed, None
        if held < MIN_HOLD_SEC:  # a piece is never cut before 30 s held
            self.said = Said.TOO_SHORT
            return False
        self._released = True
        return True

    def cut(
        self,
        start: float,
        end: float,
        now: float,
        target: int,
        last: bool,
        hold: int | None = None,
    ) -> TranscriptionRequest:
        """A piece of hold number `hold` (the current one if None) was cut,
        from `start` to `end` on the app's clock, while held or after the
        key came up (`last`): the request to send for it."""
        hold = self.hold if hold is None else hold
        piece = _Piece(self._new_id(), hold, now, target, last)
        self._waiting.append(piece)
        if last and hold == self.hold:
            self._released = False
        return TranscriptionRequest(
            piece.caption_id, SpeechKind.FINISHED, DICTATION_SOURCE, start, end
        )

    def nothing_cut(self, hold: int | None = None, mic_failed: bool = False) -> None:
        """Hold number `hold`'s last piece (the current one's if None) had
        no audio: the mic gave nothing - and said it failed, if
        `mic_failed` (`said` NO_MIC, not NOTHING_HEARD)."""
        hold = self.hold if hold is None else hold
        if hold == self.hold:
            if not self._released:
                return
            self._released = False
        if not any(p.hold == hold for p in self._waiting):
            self._over(hold)
            if mic_failed and self.said is Said.NOTHING_HEARD:
                self.said = Said.NO_MIC

    def answer(
        self,
        update: CaptionUpdate,
        australian: bool = False,
        chosen: Language | None = None,
    ) -> list[ToType]:
        """The server's answer to a piece: the text now ready to type, in
        order - none while an earlier piece waits. Answers to pieces this
        doesn't know (cancelled, given up) and live updates are ignored.
        `chosen`: the language dictation is set to (None: Detect) - its
        text rules apply whatever the server labels the line, so English
        set is English typed (Australian spelling too)."""
        if update.kind is CaptionKind.LIVE:
            return []
        piece = next(
            (p for p in self._waiting if p.caption_id == update.caption_id), None
        )
        if piece is None:
            return []
        language = chosen or update.language
        piece.text = (
            dictated_text([c.original for c in update.clauses], language, australian)
            if update.kind is CaptionKind.FINISHED
            else ""
        )
        ready = []
        while self._waiting and self._waiting[0].text is not None:
            done = self._waiting.pop(0)
            if done.text:
                ready.append(ToType(done.text, done.target))
                self._typed.add(done.hold)
            if done.last:
                self._over(done.hold)
        return ready

    def not_typed(self, said: Said) -> None:
        """The text handed out couldn't be typed (`WINDOW_CHANGED`): the
        sign says so, not TYPED."""
        self.said = said

    def cancel(self) -> bool:
        """Esc: everything not typed yet is dropped - the hold being held
        and every piece waiting. True if anything was."""
        if self.stage is Stage.IDLE:
            return False
        self._pressed, self._released, self._waiting = None, False, []
        self._typed.clear()
        self.said = Said.CANCELLED
        return True

    def withdraw(self) -> bool:
        """The key was part of a shortcut after all - another key went down
        with Right Ctrl (polyglotic-hq 289): the hold being held is dropped
        as if it never was - nothing sent, nothing said. Earlier holds'
        pieces still come. True if a hold was."""
        if self._pressed is None:
            return False
        self._pressed, self._released = None, False
        self._waiting = [p for p in self._waiting if p.hold != self.hold]
        self._typed.discard(self.hold)
        self.said = None
        return True

    def overdue(self, now: float) -> bool:
        """A piece unanswered for `ANSWER_WITHIN_SEC`: it and every piece
        after it are given up (`said` NO_ANSWER). True if any were."""
        if not self._waiting or now - self._waiting[0].sent < ANSWER_WITHIN_SEC:
            return False
        self._waiting, self._released = [], False
        self._typed.clear()
        if self._pressed is None:
            self.said = Said.NO_ANSWER
        return True

    def no_server(self) -> bool:
        """The listening session can't be answered now - the server can't
        be reached, or it closed the session: the hold being held and
        every piece waiting are given up at once (`said` NO_SERVER), not
        after `ANSWER_WITHIN_SEC`. True if anything was."""
        if self.stage is Stage.IDLE:
            return False
        self._pressed, self._released, self._waiting = None, False, []
        self._typed.clear()
        self.said = Said.NO_SERVER
        return True

    def _over(self, hold: int) -> None:
        """A hold's last piece is done: what the sign says, unless a newer
        hold is under way."""
        typed = hold in self._typed
        self._typed.discard(hold)
        if hold == self.hold and self._pressed is None:
            self.said = Said.TYPED if typed else Said.NOTHING_HEARD


def dictated_text(
    originals: Sequence[str], language: Language | None, australian: bool = False
) -> str:
    """A finished caption's clauses as the text typed: joined (no space
    beside Chinese or Japanese); in English, fillers on their own ("um",
    "uh", "erm", "er", "hmm") taken out and, if `australian`, Australian
    spelling; and a space after - none after Chinese or Japanese. "" if
    nothing is left."""
    text = join_text(originals)
    if language == ENGLISH:
        text = without_fillers(text)
        if australian:
            text = australian_spelling(text)
    if not text:
        return ""
    return text if is_cjk(text[-1]) else text + " "


def without_fillers(text: str) -> str:
    """English text without "um", "uh", "erm", "er" and "hmm" (with a
    comma or full stop after them), its first letter a capital again if it
    was."""
    capital = text[:1].isupper()
    out = _FILLERS.sub("", text)
    out = re.sub(r"\s+([,.!?])", r"\1", re.sub(r"\s+", " ", out)).strip()
    if capital and out:
        out = out[:1].upper() + out[1:]
    return out


def quietest_cut(levels: Sequence[float], step_sec: float) -> int:
    """Where to cut a long hold: the index into `levels` (the audio's
    loudness, one value every `step_sec`) of the quietest moment in its
    last `CUT_SEARCH_SEC` - the latest one, if several are as quiet."""
    if not levels:
        return 0
    first = max(0, len(levels) - round(CUT_SEARCH_SEC / step_sec))
    quietest = first
    for i in range(first, len(levels)):
        if levels[i] <= levels[quietest]:
            quietest = i
    return quietest
