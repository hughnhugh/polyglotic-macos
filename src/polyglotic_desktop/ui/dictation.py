"""Dictation in the running app: hold the key, speak, let go - the words typed where the cursor is.

polyglotic-hq 283 and decision 0073. `Dictating` holds core's `Dictation`
(the holds, their pieces in order, what the sign says) and does what it
decides, on the interface's thread:
- **the key** (`key_down` / `key_up`, from the key's own thread): the mic
  opened at the press - after asking `main` for a listening session
  (`session`, False when signed out: "Sign in to dictate") - and closed
  `TAIL_SEC` after the release; a press under 0.3 s drops it. When the
  caption pipeline already hears the source, the hold follows its finished
  lines and uses the captions' results without opening this recorder (703);
- **the pieces** the mic hands on (`HeldMic`): each one's request and
  speech to `send` (`main` puts them where the listening session takes
  speech), the window that had the keyboard noted for it;
- **the answers** (`answered`, from the session's thread): the text typed
  (`TypeText`) only into the window it was meant for, in order - and
  never while the key is held: text ready during a new hold waits for it
  to come up, so it never lands with Ctrl held (polyglotic-hq 289);
- **a shortcut** (`key_other`): another key went down with a key held
  alone (Right Ctrl + C) - the hold dropped quietly, nothing sent or said;
- **Esc** (read, not taken - `KeyState`) cancels whatever isn't typed;
  a piece unanswered for 10 s is given up; a hold of 5 minutes ends;
- **the listening session** (`connection_changed`): in a state that can't
  be answered - the server out of reach, the session closed or refused -
  a hold under way is given up at once and the sign says why, and a press
  then opens no mic (polyglotic-hq 299: it said "No answer" after 10 s).
  What was given up and still waits to be sent is dropped
  (`forget_unsent`), so nothing said is sent once nothing is to be typed;
- **the sign** (`sign_changed`): Listening with the mic's level, Working,
  then what happened - the interface draws it (`ui_next.dictation_sign`).

`session_wanted` says whether dictation needs a listening session now: a
hold under way, or one answered less than a minute ago. Off
(`settings.dictation`), the key does nothing. Logs what happened and how
long it took - never the words or the audio.
"""

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass

from PySide6.QtCore import QObject, QTimer, Signal, Slot

from polyglotic_desktop.core.listening.caption_hold import CaptionResults
from polyglotic_desktop.core.listening.captions import CaptionUpdate, Language
from polyglotic_desktop.core.listening.dictation import (
    MAX_HOLD_SEC,
    SESSION_IDLE_SEC,
    TAIL_SEC,
    Dictation,
    Said,
    Stage,
    ToType,
)
from polyglotic_desktop.core.listening.timing import CaptionId, TranscriptionRequest
from polyglotic_desktop.ports.capture import HeldMic, MicPiece
from polyglotic_desktop.ports.system import KeyboardWindow, KeyState, TypeText
from polyglotic_desktop.ui.app import ConnectionState
from polyglotic_desktop.ui.settings import Settings

log = logging.getLogger(__name__)

LEVEL_MS = 80
"""How often the sign's meter follows the mic while the key is held."""
ESC_MS = 50
"""How often Esc is read while dictation is under way."""
OVERDUE_MS = 1000

UNANSWERED: dict[ConnectionState, Said] = {
    ConnectionState.WAITING: Said.NO_SERVER,
    ConnectionState.SERVER_BUSY: Said.NO_SERVER,
    ConnectionState.UPDATE_NEEDED: Said.NO_SERVER,
    ConnectionState.MOVED: Said.NO_SERVER,
    ConnectionState.PLUS_ENDED: Said.NO_SERVER,
    ConnectionState.STOPPED: Said.NO_SERVER,
    ConnectionState.SIGN_IN_NEEDED: Said.SIGN_IN,
}
"""The listening session's states no answer comes in, and what the sign
says then; Home's state line says why (polyglotic-hq 299). Connecting,
listening - and not connected, before a press opens a session - may be
answered."""


@dataclass(slots=True)
class HeldCaptions:
    """A typing hold borrowing one of the caption pipeline's sources."""

    results: CaptionResults
    finished: Callable[[float], tuple[TranscriptionRequest, ...] | None]
    stop: Callable[[], None]
    level: Callable[[], float]
    text: Callable[[tuple[CaptionUpdate, ...]], str]
    end: float | None = None
    piece: CaptionId | None = None


class Dictating(QObject):
    """The dictation key's holds, from the key to the text typed."""

    sign_changed = Signal(str, float)
    """What the sign shows: a `Stage` ("listening", with the mic's level 0
    to 1; "working") or, once nothing more is coming, a `Said` - "idle"
    for nothing to say."""
    _down = Signal()
    _up = Signal()
    _other = Signal()
    _piece = Signal(object)
    _answer = Signal(object)

    def __init__(
        self,
        settings: Settings,
        mic: HeldMic,
        send: Callable[[TranscriptionRequest, bytes], None],
        type_text: TypeText,
        keyboard_window: KeyboardWindow,
        keys: KeyState,
        session: Callable[[bool], bool],
        clock: Callable[[], float] = time.monotonic,
        parent: QObject | None = None,
        mic_held: Callable[[bool, float], None] = lambda _held, _tail: None,
        forget_unsent: Callable[[], None] = lambda: None,
        typing_allowed: Callable[[], bool] = lambda: True,
        *,
        holds: Dictation | None = None,
        from_speakers: bool = False,
        type_text_for: Callable[[str, int], bool] | None = None,
        window_is_ours: Callable[[int], bool] = lambda _window: False,
        copy_text: Callable[[str], None] | None = None,
        share_captions: Callable[[float], HeldCaptions | None] = lambda _start: None,
    ) -> None:
        """`send`: a piece's request and its speech, to the listening
        session. `session(True)`: dictation needs a listening session now -
        False if it can't have one (signed out); `session(False)`: it no
        longer does. `clock`: monotonic seconds. `mic_held(True, 0)`: the
        mic is in use for dictation; `mic_held(False, tail)`: it's let go
        `tail` seconds from now. `forget_unsent`: the
        pieces given up that still wait to be sent are dropped.
        `share_captions`: use an existing caption capture for the hold, if
        one covers this audio. It uses the same clock as the capture.
        `typing_allowed`: whether the OS lets the app type (a Mac's
        Accessibility, polyglotic-hq 438) - asked when typing fails, so the
        sign says why."""
        super().__init__(parent)
        self.settings = settings
        self.dictation = holds if holds is not None else Dictation()
        self._from_speakers = from_speakers
        self._window_is_ours = window_is_ours
        self._copy_text = copy_text
        self._mic, self._send = mic, send
        self._type = type_text_for or (lambda text, _window: type_text(text))
        self._window, self._keys = keyboard_window, keys
        self._session, self._clock = session, clock
        self._mic_held = mic_held
        self._forget_unsent = forget_unsent
        self._typing_allowed = typing_allowed
        self._share_captions = share_captions
        self._shared: dict[int, HeldCaptions] = {}
        self._unanswered: Said | None = None
        """Why the listening session can't answer now; None: it may."""
        self._live: set[int] = set()
        """The holds whose pieces are still wanted (not cancelled or dropped)."""
        self._targets: dict[int, int] = {}
        """Each hold's window, as the key came up."""
        self._pressed_at = 0.0
        self._last_activity: float | None = None
        self._waiting_to_type: list[ToType] = []
        """Text ready while the key is held: typed once it comes up, so it
        never lands with Ctrl (or Alt, Win) held down (polyglotic-hq 289)."""
        self._key_held = False
        """The key is down - for dictation or, after `key_other`, a
        shortcut."""
        self._down.connect(self._key_down)
        self._up.connect(self._key_up)
        self._other.connect(self._key_other)
        self._piece.connect(self._cut)
        self._answer.connect(self._answered)
        self._level = QTimer(self, interval=LEVEL_MS)
        self._level.timeout.connect(self._show_level)
        self._esc = QTimer(self, interval=ESC_MS)
        self._esc.timeout.connect(self._read_esc)
        self._overdue = QTimer(self, interval=OVERDUE_MS)
        self._overdue.timeout.connect(self._check_overdue)
        self._longest = QTimer(self, singleShot=True, interval=int(MAX_HOLD_SEC * 1000))
        self._longest.timeout.connect(
            self._key_other if from_speakers else self._key_up
        )
        # a second over: a timer may fire a little early
        self._idle = QTimer(
            self, singleShot=True, interval=int(SESSION_IDLE_SEC * 1000) + 1000
        )
        self._idle.timeout.connect(self._session_idle)

    # -- from other threads -----------------------------------------------------------

    def key_down(self) -> None:
        """The dictation key went down (any thread)."""
        self._down.emit()

    def key_up(self) -> None:
        """The dictation key came up (any thread)."""
        self._up.emit()

    def key_other(self) -> None:
        """Another key went down with a key held alone (any thread): a
        shortcut, not dictation."""
        self._other.emit()

    def answered(self, update: CaptionUpdate) -> None:
        """The server's answer to a piece (the session's thread)."""
        self._answer.emit(update)

    @Slot(object)
    def caption_received(self, update: CaptionUpdate) -> None:
        for hold in self._shared.values():
            hold.results.received(update)

    @Slot(object)
    def caption_applied(self, update: CaptionUpdate) -> None:
        for hold in self._shared.values():
            hold.results.applied(update)

    @Slot(str)
    def caption_dropped(self, caption_id: str) -> None:
        for hold in self._shared.values():
            hold.results.dropped(CaptionId(caption_id))

    def connection_changed(self, state: ConnectionState) -> None:
        """The listening session's state, on the interface thread: one no
        answer comes in (`UNANSWERED`) gives a hold under way up at once."""
        self._unanswered = UNANSWERED.get(state)
        if self._unanswered is not None:
            self._give_up(self._unanswered)

    @property
    def session_wanted(self) -> bool:
        """Dictation needs a listening session now: a hold under way, or
        one answered less than `SESSION_IDLE_SEC` ago."""
        if self.dictation.stage is not Stage.IDLE:
            return True
        last = self._last_activity
        return last is not None and self._clock() - last < SESSION_IDLE_SEC

    def stop(self) -> None:
        """Dictation turned off, or the app ending: the mic closed, what
        waits dropped quietly."""
        for timer in (self._level, self._esc, self._overdue, self._longest, self._idle):
            timer.stop()
        self._drop_mic()
        self._live.clear()
        self._targets.clear()
        self._waiting_to_type.clear()
        self._key_held = False
        self._last_activity = None
        if self.dictation.cancel():
            self.dictation.said = None
        self.sign_changed.emit(Stage.IDLE.value, 0.0)

    # -- on the interface's thread -------------------------------------------------------

    @Slot()
    def _key_down(self) -> None:
        value = self.settings.value
        enabled = value.type_theirs if self._from_speakers else value.dictation
        if self._key_held or not enabled:
            return
        self._key_held = True
        now = self._clock()
        if not self._session(True):
            self.dictation.said = Said.SIGN_IN
            self._show()
            return
        if self._unanswered is not None and self.dictation.stage is Stage.IDLE:
            self.dictation.said = self._unanswered  # said now, no mic opened
            log.info("dictation: %s at the press", self._unanswered.value)
            self._show()
            return
        if not self.dictation.press(now):
            return
        hold = self.dictation.hold
        self._pressed_at = now
        shared = self._share_captions(now)
        if shared is None:
            self._live.add(hold)
            self._mic.open(hold, self._piece.emit)
        else:
            self._shared[hold] = shared
        self._mic_held(True, 0.0)
        self._level.start()
        self._esc.start()
        self._longest.start()
        self._idle.stop()
        self._show()

    @Slot()
    def _key_up(self) -> None:
        self._longest.stop()
        self._level.stop()
        self._key_held = False
        if self.dictation.stage is not Stage.LISTENING:
            if self._waiting_to_type:  # after a shortcut (`_key_other`)
                self._type_waiting()
                self._show()
            return
        hold = self.dictation.hold
        now = self._clock()
        held = now - self._pressed_at
        if self.dictation.release(now):
            window = self._window()
            if (
                self._copy_text is None
                and self._from_speakers
                and self._window_is_ours(window)
            ):
                self._drop_capture(hold)
                self.dictation.nothing_cut(hold)
                self.dictation.not_typed(Said.OWN_WINDOW)
                self._done()
                return
            tail = 0.0 if self._from_speakers else TAIL_SEC
            shared = self._shared.get(hold)
            if shared is None:
                self._targets[hold] = window
                self._mic.close(tail)
            else:
                shared.end = now + tail
                shared.piece = self.dictation.wait_for_captions(now, window)
            self._mic_held(False, tail)
            self._overdue.start()
            self._check_caption_holds()
        else:
            self._drop_capture(hold)
            log.info("dictation: %s (%.1f s held)", Said.TOO_SHORT.value, held)
        self._type_waiting()
        self._show()

    @Slot()
    def _key_other(self) -> None:
        """A shortcut with the key held alone (Right Ctrl + C): the hold
        dropped quietly, the mic closed - nothing sent or said."""
        hold = self.dictation.hold
        if not self.dictation.withdraw():
            return
        self._drop_capture(hold)
        self._targets.pop(hold, None)
        self._level.stop()
        self._longest.stop()
        log.info("dictation: withdrawn - a shortcut")
        self._done()

    @Slot(object)
    def _cut(self, piece: MicPiece) -> None:
        """A piece of a hold from the mic: sent, unless the hold was
        cancelled."""
        if piece.hold not in self._live:
            return
        if piece.last:
            self._live.discard(piece.hold)
        if piece.speech is None:
            self.dictation.nothing_cut(piece.hold, piece.mic_failed)
            self._targets.pop(piece.hold, None)
            self._done()
            return
        target = self._targets.pop(piece.hold, None) if piece.last else None
        request = self.dictation.cut(
            piece.start,
            piece.end,
            self._clock(),
            self._window() if target is None else target,
            piece.last,
            piece.hold,
        )
        self._send(request, piece.speech)
        self._overdue.start()
        self._show()

    @Slot(object)
    def _answered(self, update: CaptionUpdate) -> None:
        value = self.settings.value
        chosen = (
            Language(value.dictation_language) if value.dictation_language else None
        )
        ready = self.dictation.answer(update, value.dictation_australian, chosen)
        self._waiting_to_type.extend(ready)
        if not self._key_held:
            self._type_waiting()
        if update.processing_ms is not None and ready:
            log.info(
                "dictation: %d piece(s) answered, server %d ms",
                len(ready),
                update.processing_ms,
            )
        self._last_activity = self._clock()
        self._done()

    def _check_caption_holds(self) -> None:
        """Take the shown lines once the source and its answers reach release."""
        completed = []
        for hold, shared in self._shared.items():
            if shared.end is None or shared.piece is None:
                continue
            requests = shared.finished(shared.end)
            lines = None if requests is None else shared.results.lines(requests)
            if lines is None:
                continue
            self._waiting_to_type.extend(
                self.dictation.answer_text(shared.piece, shared.text(lines))
            )
            completed.append(hold)
        for hold in completed:
            self._shared.pop(hold).stop()
        if completed:
            if not self._key_held:
                self._type_waiting()
            self._done()

    def _type_waiting(self) -> None:
        """The text ready, typed in order - each only into the window it
        was meant for."""
        ready, self._waiting_to_type = self._waiting_to_type, []
        for text in ready:
            if self._copy_text is not None:
                self._copy_text(text.text)
                self.dictation.not_typed(Said.COPIED)
                continue
            window = self._window()
            if self._from_speakers and self._window_is_ours(window):
                self.dictation.not_typed(Said.OWN_WINDOW)
            elif window != text.target or (self._from_speakers and not text.target):
                self.dictation.not_typed(Said.WINDOW_CHANGED)
            elif not self._type(text.text, text.target):
                self.dictation.not_typed(
                    Said.NOT_TYPED if self._typing_allowed() else Said.NOT_ALLOWED
                )

    @Slot()
    def _read_esc(self) -> None:
        if self.dictation.stage is Stage.IDLE:
            self._esc.stop()
            return
        if self._keys("escape") and self.dictation.cancel():
            self._drop_mic()
            self._forget_unsent()
            self._live.clear()
            self._waiting_to_type.clear()
            self._targets.clear()
            self._level.stop()
            self._longest.stop()
            self._done()
        else:
            self._check_caption_holds()

    @Slot()
    def _check_overdue(self) -> None:
        if self.dictation.overdue(self._clock()):
            self._forget_unsent()
            self._targets.clear()
            for hold, shared in list(self._shared.items()):
                if shared.end is not None:
                    self._shared.pop(hold).stop()
            self._done()
        elif self.dictation.stage is Stage.IDLE:
            self._overdue.stop()

    @Slot()
    def _show_level(self) -> None:
        if self.dictation.stage is Stage.LISTENING:
            self.sign_changed.emit(Stage.LISTENING.value, self._capture_level())

    @Slot()
    def _session_idle(self) -> None:
        if not self.session_wanted:
            self._session(False)

    def _give_up(self, said: Said) -> None:
        """No answer can come: the hold under way and every piece waiting
        given up now, and `said` shown."""
        if not self.dictation.no_server():
            return
        self.dictation.said = said
        self._drop_mic()
        self._forget_unsent()
        self._live.clear()
        self._waiting_to_type.clear()
        self._targets.clear()
        self._level.stop()
        self._longest.stop()
        self._done()

    def _drop_mic(self) -> None:
        """Cancel the recorder and every outstanding caption hold."""
        self._mic.drop()
        for hold in self._shared.values():
            hold.stop()
        self._shared.clear()
        self._mic_held(False, 0.0)

    def _drop_capture(self, hold: int) -> None:
        shared = self._shared.pop(hold, None)
        if shared is None:
            self._mic.drop()
            self._live.discard(hold)
        else:
            shared.stop()
        self._mic_held(False, 0.0)

    def _capture_level(self) -> float:
        shared = self._shared.get(self.dictation.hold)
        return self._mic.level() if shared is None else shared.level()

    def _done(self) -> None:
        """Something finished: the sign told, and - once nothing is under
        way - the timers stopped and the session's idle wait begun."""
        if self.dictation.stage is Stage.IDLE:
            self._overdue.stop()
            self._esc.stop()
            if self.dictation.said is not None:
                log.info("dictation: %s", self.dictation.said.value)
            self._last_activity = self._clock()
            self._idle.start()
        self._show()

    def _show(self) -> None:
        stage = self.dictation.stage
        if stage is Stage.LISTENING:
            self.sign_changed.emit(stage.value, self._capture_level())
        elif stage is Stage.WORKING:
            self.sign_changed.emit(stage.value, 0.0)
        else:
            said = self.dictation.said
            self.sign_changed.emit(said.value if said else Stage.IDLE.value, 0.0)
