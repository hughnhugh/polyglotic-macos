"""Say it: a selection read aloud (polyglotic-hq 495, 488's design; decision
0229) - the sentence card's "Say it" row and the transcript's "Say it"
menu, over the `Reader` port, on the interface thread.

- **A button a language:** what was said, or its translation, each by its
  language's own name ("中文", "English") - the side used last first,
  remembered app-wide (`first`, `remember`: the settings').
- **What is read:** the side in its spoken form (`core.listening.read_aloud`:
  mended at caption cuts, fillers out, years as years), a sentence at a
  time, in the PC's voice for its language (`views.speech.voice_for`). No
  voice: the button says so, and leads to the OS's speech settings.
- **Stopping:** a click on the playing button; Esc, a click elsewhere or a
  new selection (the selection goes: `stop_for`); another Say it, or the
  lookup card's say it (one speaker for both); the card going; dictation
  starting (`stop`, from `main`). Never started while dictation's key is
  held (`blocked`).
- **A basic voice** (a Mac's compact one) brings the better-voice notice
  where Say it was asked (`notice`, polyglotic-hq 518).
- **The word being said** is told (`lit`) to the window that asked, which
  lights it.
- **Kept out of the captions:** each sentence's sound is handed to the
  captions' hush as it starts (decision 0077), so stopping half-way hushes
  no more.

Nothing is sent anywhere: made and played on the PC; the sound of the last
readings is kept in memory only (`platform.speaking.KEPT_BYTES`). Holds
caption text while reading it: never logged.
"""

from collections.abc import Callable

from PySide6.QtCore import QObject, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices

from polyglotic_desktop.core.listening.display import RowKind
from polyglotic_desktop.core.listening.read_aloud import ReadAloud, read_aloud
from polyglotic_desktop.ports.speaker import RECORDED, Reader, Sounding, Voice
from polyglotic_desktop.ui_next.os_words import pc_or_mac
from polyglotic_desktop.ui_next.views.sentences import SideAloud
from polyglotic_desktop.ui_next.views.speech import (
    MAC_SPEECH_SETTINGS,
    NORMAL,
    SPEECH_SETTINGS,
    BetterVoice,
    Say,
    voice_for,
)

SAID_NOW = QColor(255, 214, 102, 140)
"""Behind the word being read aloud, in a caption window or a transcript
(488's mock-up's amber), over the selection's blue."""
RECHECK_MS = 600
"""A side with no voice is asked about again this long after: the speaker
looks for voices behind (one just added in Windows' settings)."""


def _open(url: str) -> None:
    QDesktopServices.openUrl(QUrl(url))


class SelectionReading(QObject):
    """Reads a selection's side aloud, one at a time, app-wide. `changed`:
    what a Say it button shows may have; `lit`: `(owner, {line key:
    [Words]})`, the words being said now in `owner`'s window - empty when
    the reading is over."""

    changed = Signal()
    lit = Signal(object, object)
    _spoken = Signal(int, int, int, int)  # from the speaker's thread: queued
    _ended = Signal(int, bool)

    def __init__(
        self,
        reader: Reader,
        hush: Sounding | None = None,
        blocked: Callable[[], bool] = lambda: False,
        first: Callable[[], RowKind] = lambda: RowKind.ORIGINAL,
        remember: Callable[[RowKind], None] = lambda _kind: None,
        open_url: Callable[[str], None] = _open,
        parent: QObject | None = None,
        better: BetterVoice | None = None,
    ) -> None:
        """`hush`: told as each sentence's sound starts (the speech
        pipeline's); `blocked`: whether dictation's key is held; `first`:
        the side used last; `remember`: a side was used; `open_url`: opens
        the OS's speech settings; `better`: when a better voice is worth
        adding (518; None: never)."""
        super().__init__(parent)
        self.reader = reader
        self.hush = hush
        self._blocked = blocked
        self._first = first
        self._remember = remember
        self._open_url = open_url
        self._better = better
        self.notice: tuple[object, str] | None = None
        """Whose reading played in a basic voice, and its language, while
        that window says a better voice can be added (518)."""
        self._serial = 0
        self.reading: tuple[object, SideAloud, ReadAloud] | None = None
        """Whose side is being read, and its spoken form."""
        self._seen: tuple[Voice, ...] = ()
        self._recheck = QTimer(self, singleShot=True, interval=RECHECK_MS)
        self._recheck.timeout.connect(self._look_again)
        self._spoken.connect(self._on_spoken)
        self._ended.connect(self._on_ended)

    def ordered(self, sides: tuple[SideAloud, ...]) -> tuple[SideAloud, ...]:
        """`sides` with the one used last first."""
        first = self._first()
        return tuple(sorted(sides, key=lambda side: side.kind is not first))

    def voice(self, side: SideAloud) -> Voice | None:
        """The PC's voice for the side's language; with none, asked again
        shortly. Never a recorded voice: those say only a dictionary's
        words."""
        voices = self.reader.voices()
        self._seen = voices
        found = voice_for(
            tuple(v for v in voices if not v.id.startswith(RECORDED)), side.language
        )
        if found is None and not self._recheck.isActive():
            self._recheck.start()
        return found

    def state(self, owner: object, side: SideAloud) -> Say:
        if self.voice(side) is None:
            return Say.NO_VOICE
        return Say.SPEAKING if self.reads(owner, side) else Say.READY

    def reads(self, owner: object, side: SideAloud) -> bool:
        """Whether `side` of `owner`'s selection is being read now."""
        reading = self.reading
        return reading is not None and reading[0] is owner and reading[1] == side

    def toggle(self, owner: object, side: SideAloud) -> None:
        """A click on a side's button: reads it, or stops it reading; with
        no voice, opens the OS's speech settings."""
        if self.reads(owner, side):
            self.stop()
            return
        voice = self.voice(side)
        if voice is None:
            self.add_voice()
            return
        if self._blocked():
            return  # dictation's key is held: the mic hears the PC
        made = read_aloud(side.stretches, side.language)
        if not made.chunks:
            return
        self._remember(side.kind)
        due = self._better is not None and self._better.due(voice, side.language)
        self.notice = (owner, side.language) if due else None
        self._serial += 1
        serial = self._serial
        before = self.reading
        self.reading = (owner, side, made)
        if before is not None:  # its words lit no more
            self.lit.emit(before[0], {})
        self.reader.read(
            made.chunk_texts(),
            voice,
            NORMAL,
            self._sounding,
            lambda heard: self._ended.emit(serial, heard),
            lambda chunk, start, end: self._spoken.emit(serial, chunk, start, end),
        )
        self.changed.emit()

    def stop(self) -> None:
        """Stops the reading, if one is on (dictation starting, Esc)."""
        reading = self.reading
        if reading is None:
            return
        self.reading = None
        self._serial += 1  # what the speaker still tells is about the old one
        self.reader.stop()
        self.lit.emit(reading[0], {})
        self.changed.emit()

    def stop_for(self, owner: object) -> None:
        """Stops the reading if it is `owner`'s: its selection or card went
        (its notice with it)."""
        if self.notice is not None and self.notice[0] is owner:
            self.notice = None
        if self.reading is not None and self.reading[0] is owner:
            self.stop()

    def notice_for(self, owner: object) -> str | None:
        """The language of `owner`'s better-voice notice, if it shows one."""
        notice = self.notice
        return notice[1] if notice is not None and notice[0] is owner else None

    def dismiss(self, never_again: bool) -> None:
        """The notice's Dismiss: it goes - for good in its language with
        "Don't show again" ticked."""
        notice = self.notice
        if notice is None:
            return
        if never_again and self._better is not None:
            self._better.silence(notice[1])
        self.notice = None
        self.changed.emit()

    def add_voice(self) -> None:
        """Windows' speech settings, where Add voices is; a Mac's Spoken
        Content, where Manage Voices is."""
        self._open_url(pc_or_mac(SPEECH_SETTINGS, MAC_SPEECH_SETTINGS))

    def _sounding(self, start: float, seconds: float) -> None:
        if self.hush is not None:
            self.hush(start, seconds)

    def _on_spoken(self, serial: int, chunk: int, start: int, end: int) -> None:
        reading = self.reading
        if serial != self._serial or reading is None:
            return
        owner, side, made = reading
        self.lit.emit(owner, side.lit(made.came_from(chunk, start, end)))

    def _on_ended(self, serial: int, heard: bool) -> None:
        reading = self.reading
        if serial != self._serial or reading is None:
            return
        self.reading = None
        self.lit.emit(reading[0], {})
        self.changed.emit()

    def _look_again(self) -> None:
        if self.reader.voices() != self._seen:
            self.changed.emit()
