"""Re-speaking in the running app: hold the key, say what the other person said, let go - captioned as theirs.

polyglotic-hq 567 and decision 0274. `Respeaking` holds core's
`Respeaking` (the hold, its pieces, what the sign says) and does what it
decides, on the interface's thread:
- **the key** (`key_down` / `key_up` / `key_other`, from the key's own
  thread, through `main`'s `HoldKeys`): at the press, whose it is
  (`whose`: the watched window’s source, or None - nothing else is
  captioned, and the mic stays closed), and the listening session must be
  one that can answer; then the mic opens (`HeldMic`, its own), and while
  it's open the mic's own captions hear silence (`mic_held`), so what's
  re-spoken is never also a "You" line;
- **the pieces** the mic hands on: each one's request - a finished caption
  of that source - and speech to `send` (`main` puts them where the
  listening session takes speech, as dictation's);
- **the answers** (`answered`, the session's thread, for every caption
  update): those to its pieces end the hold; the captions themselves go
  to the caption windows and transcripts as every caption does, marked
  re-spoken (`is_respoken`, asked on the session's thread);
- **Esc** cancels; a piece unanswered for 10 s is given up; a hold of
  5 minutes ends; a session that can't be answered gives up at once;
- **the sign** (`sign_changed`): "Re-speaking for Discord" with the mic's
  level, "Working…", then why, if nothing was captioned.

Off (`settings.legacy_respeaking`), the key does nothing. Logs what happened -
never the words, the audio or whose it was.
"""

import logging
import time
from collections.abc import Callable
from typing import Protocol

from PySide6.QtCore import QObject, QTimer, Signal, Slot

from polyglotic_desktop.core.listening.captions import CaptionUpdate
from polyglotic_desktop.core.listening.dictation import (
    MAX_HOLD_SEC,
    TAIL_SEC,
    Stage,
)
from polyglotic_desktop.core.listening.respeaking import KeyGesture, Said, Use
from polyglotic_desktop.core.listening.respeaking import Respeaking as Holds
from polyglotic_desktop.core.listening.sources import Source, SourceId
from polyglotic_desktop.core.listening.timing import CaptionId, TranscriptionRequest
from polyglotic_desktop.ports.capture import HeldMic, MicPiece
from polyglotic_desktop.ports.system import KeyState
from polyglotic_desktop.ui.app import ConnectionState
from polyglotic_desktop.ui.settings import Settings

log = logging.getLogger(__name__)

LEVEL_MS = 80
ESC_MS = 50
OVERDUE_MS = 1000

ANSWERED = frozenset({ConnectionState.LISTENING, ConnectionState.CONNECTING})
"""The listening session's states a re-spoken piece may be answered in: it
needs the session that captions the other source, open (it never opens
one of its own)."""


class Respeaking(QObject):
    """The re-speaking key's holds, from the key to the caption back."""

    sign_changed = Signal(str, float, str)
    """What the sign shows: a `Stage` ("listening", with the mic's level 0
    to 1; "working") or a `Said` value - "idle" for nothing to say - and
    whose it is ("Discord")."""
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
        whose: Callable[[], tuple[Source, str] | None],
        keys: KeyState,
        clock: Callable[[], float] = time.monotonic,
        parent: QObject | None = None,
        mic_held: Callable[[bool, float], None] = lambda _held, _tail: None,
        available: Callable[[SourceId], bool] = lambda _source: True,
    ) -> None:
        """`whose`: the source to re-speak for now and its name ("Discord"),
        or None; `mic_held(True, 0)`: the mic is re-speaking's from now;
        `mic_held(False, tail)`: it's let go `tail` seconds from now."""
        super().__init__(parent)
        self.settings = settings
        self.holds = Holds()
        self._mic, self._send, self._whose = mic, send, whose
        self._available = available
        self._keys, self._clock, self._mic_held = keys, clock, mic_held
        self._state: ConnectionState | None = None
        self._name = ""
        self._hold = 0
        self._down.connect(self._key_down)
        self._up.connect(self._release)
        self._other.connect(self._key_other)
        self._piece.connect(self._cut)
        self._answer.connect(self._answered)
        self._level = QTimer(self, interval=LEVEL_MS)
        self._level.timeout.connect(self._show)
        self._esc = QTimer(self, interval=ESC_MS)
        self._esc.timeout.connect(self._read_esc)
        self._overdue = QTimer(self, interval=OVERDUE_MS)
        self._overdue.timeout.connect(self._check_overdue)
        self._longest = QTimer(self, singleShot=True, interval=int(MAX_HOLD_SEC * 1000))
        self._longest.timeout.connect(self._release)

    # -- from other threads -----------------------------------------------------------

    def key_down(self) -> None:
        self._down.emit()

    def key_up(self) -> None:
        self._up.emit()

    def key_other(self) -> None:
        """Another key with a key held alone: a shortcut - the hold dropped
        quietly (`key_up` follows)."""
        self._other.emit()

    def answered(self, update: CaptionUpdate) -> None:
        """Any caption update from the server (the session's thread)."""
        if self.holds.is_respoken(update.caption_id):
            self._answer.emit(update)

    def is_respoken(self, caption_id: CaptionId) -> bool:
        """Whether a caption was re-spoken here (any thread): its line is
        marked so."""
        return self.holds.is_respoken(caption_id)

    def connection_changed(self, state: ConnectionState) -> None:
        """The listening session's state, on the interface thread: one that
        can't answer gives a hold under way up at once."""
        self._state = state
        if state not in ANSWERED and self.holds.cancel(Said.NO_SERVER):
            self._drop_mic()
            self._done()

    def stop(self) -> None:
        """Re-speaking turned off, or the app ending: the mic closed, what
        waits dropped quietly."""
        for timer in (self._level, self._esc, self._overdue, self._longest):
            timer.stop()
        self._drop_mic()
        if self.holds.cancel():
            self.holds.said = None
        self.sign_changed.emit(Stage.IDLE.value, 0.0, "")

    # -- on the interface's thread -------------------------------------------------------

    @Slot()
    def _key_down(self) -> None:
        if (
            not self.settings.value.legacy_respeaking
            or self.holds.stage is not Stage.IDLE
        ):
            return
        found = self._whose()
        source, self._name = found if found is not None else (None, "")
        if source is not None and self._state not in ANSWERED:
            self.holds.said = Said.NO_SERVER
            log.info("re-speaking: %s at the press", Said.NO_SERVER.value)
            self._show()
            return
        if not self.holds.press(self._clock(), source):
            log.info("re-speaking: %s", Said.NO_SOURCE.value)
            self._show()
            return
        assert source is not None
        log.info("re-speaking: held, category %s", source.category.value)
        self._hold += 1
        self._mic.open(self._hold, self._piece.emit)
        self._mic_held(True, 0.0)
        self._keys("escape")  # forget an Esc pressed before this hold began
        self._level.start()
        self._esc.start()
        self._longest.start()
        self._show()

    @Slot()
    def _release(self) -> None:
        self._longest.stop()
        self._level.stop()
        if self.holds.stage is not Stage.LISTENING:
            return
        if self.holds.release(self._clock()):
            self._mic.close(TAIL_SEC)
            self._mic_held(False, TAIL_SEC)
            self._overdue.start()
        else:
            self._drop_mic()
        self._done()

    @Slot()
    def _key_other(self) -> None:
        """A shortcut with the key held alone (Right Ctrl + C): the hold
        dropped quietly, the mic closed - nothing sent or said."""
        if self.holds.stage is not Stage.LISTENING:
            return
        self.holds.cancel()
        self.holds.said = None
        self._drop_mic()
        log.info("re-speaking: withdrawn - a shortcut")
        self._done()

    @Slot(object)
    def _cut(self, piece: MicPiece) -> None:
        if piece.hold != self._hold or self.holds.stage is Stage.IDLE:
            return
        source = self.holds.source
        if source is None or not self._available(source.id):
            self.holds.cancel(Said.NO_SOURCE)
            self._drop_mic()
            self._done()
            return
        if piece.speech is None:
            self.holds.nothing_cut(piece.last, piece.mic_failed)
            self._done()
            return
        request = self.holds.cut(piece.start, piece.end, self._clock(), piece.last)
        self._send(request, piece.speech)
        self._overdue.start()
        self._show()

    @Slot(object)
    def _answered(self, update: CaptionUpdate) -> None:
        if self.holds.answer(update):
            log.info(
                "re-speaking: answered %s (%s), server %s ms",
                update.kind.value,
                update.reason.value if update.reason is not None else "no reason",
                update.processing_ms,
            )
        self._done()

    @Slot()
    def _read_esc(self) -> None:
        if self.holds.stage is Stage.IDLE:
            self._esc.stop()
            return
        if self._keys("escape") and self.holds.cancel():
            self._drop_mic()
            self._done()

    @Slot()
    def _check_overdue(self) -> None:
        if self.holds.overdue(self._clock()):
            self._done()
        elif self.holds.stage is Stage.IDLE:
            self._overdue.stop()

    def _drop_mic(self) -> None:
        self._mic.drop()
        self._mic_held(False, 0.0)

    def _done(self) -> None:
        if self.holds.stage is Stage.IDLE:
            for timer in (self._level, self._esc, self._overdue, self._longest):
                timer.stop()
            if self.holds.said is not None:
                log.info("re-speaking: %s", self.holds.said.value)
        self._show()

    @Slot()
    def _show(self) -> None:
        stage = self.holds.stage
        if stage is Stage.LISTENING:
            self.sign_changed.emit(stage.value, self._mic.level(), self._name)
        elif stage is Stage.WORKING:
            self.sign_changed.emit(stage.value, 0.0, self._name)
        else:
            said = self.holds.said
            shown = said.value if said and said is not Said.RESPOKEN else "idle"
            self.sign_changed.emit(shown, 0.0, self._name)


class Held(Protocol):
    """A key's three calls, as `Dictating` and `Respeaking` take them."""

    def key_down(self) -> None: ...

    def key_up(self) -> None: ...

    def key_other(self) -> None: ...


class SharedKey:
    """One key for dictation and re-speaking - optional (polyglotic-hq
    567): a hold dictates, as before; a tap, then a hold, re-speaks
    (`core.listening.respeaking.KeyGesture`). Its calls come on the key's
    own thread, as the key's do, and go on to the one the hold is for."""

    def __init__(
        self,
        dictating: Held,
        respeaking: Held,
        settings: Settings,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._dictating, self._respeaking = dictating, respeaking
        self._settings, self._clock = settings, clock
        self._gesture = KeyGesture()

    def _shared(self) -> bool:
        value = self._settings.value
        return (value.type_theirs or value.legacy_respeaking) and not value.respeak_key

    def down(self) -> None:
        use = self._gesture.down(
            self._clock(), self._settings.value.dictation, self._shared()
        )
        if use is Use.DICTATE:
            self._dictating.key_down()
        elif use is Use.RESPEAK:
            self._respeaking.key_down()

    def up(self) -> None:
        use, tap = self._gesture.up(self._clock())
        if use is Use.DICTATE:
            if tap and self._shared():  # half of a tap and a hold: nothing said
                self._dictating.key_other()
            self._dictating.key_up()
        elif use is Use.RESPEAK:
            self._respeaking.key_up()

    def other(self) -> None:
        """Another key with it held alone: a shortcut, for the one held."""
        self._gesture.other()
        if self._gesture.use is Use.DICTATE:
            self._dictating.key_other()
        elif self._gesture.use is Use.RESPEAK:
            self._respeaking.key_other()
