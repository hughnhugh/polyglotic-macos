"""Hearing a looked-up word (polyglotic-hq 286, decision 0077): the lookup
card's speaker button over the `Speaker` port, on the interface thread.

`main` hands it the PC's speaker and the speech pipeline's `hush`, so the
word the app says is never captioned. One word at a time: a click says the
card's word (its own pace, then slower on the next click - `views.speech`),
a click while it speaks stops it, and the card closing stops it too. The
speaker's thread is never waited for: what it says comes back as a queued
signal. Nothing is sent anywhere.

Holds the word being said: never logged.
"""

from collections.abc import Callable

from PySide6.QtCore import QObject, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices

from polyglotic_desktop.ports.speaker import Sounding, Speaker, Voice
from polyglotic_desktop.ui_next.os_words import pc_or_mac
from polyglotic_desktop.ui_next.views.speech import (
    MAC_SPEECH_SETTINGS,
    SPEECH_SETTINGS,
    Say,
    pace,
    voice_for,
)

RECHECK_MS = 600
"""A word with no voice is asked about again this long after: the speaker
looks for voices behind (a voice just added in Windows' settings)."""


def _open(url: str) -> None:
    QDesktopServices.openUrl(QUrl(url))


class WordSpeech(QObject):
    """The card's "say it". `changed`: what the button shows may have."""

    changed = Signal()
    _ended = Signal(int, bool)  # from the speaker's thread: queued

    def __init__(
        self,
        speaker: Speaker,
        hush: Sounding | None = None,
        open_url: Callable[[str], None] = _open,
        parent: QObject | None = None,
    ) -> None:
        """`hush`: told when the app's own sound plays (the speech
        pipeline's), from the speaker's thread; `open_url`: opens Windows'
        speech settings."""
        super().__init__(parent)
        self.speaker = speaker
        self.hush = hush
        self._open_url = open_url
        self._ended.connect(self._on_ended)
        self._serial = 0
        self.speaking: str | None = None
        """The key (`key`) of the word being said, if any."""
        self._said: tuple[str, int] = ("", 0)
        """The last word said on this card, and how many times."""
        self._seen: tuple[Voice, ...] = ()
        self._recheck = QTimer(self, singleShot=True, interval=RECHECK_MS)
        self._recheck.timeout.connect(self._look_again)

    @staticmethod
    def key(text: str, language: str) -> str:
        return f"{language}\n{text}"

    def voice(self, language: str) -> Voice | None:
        """The voice for `language` now; with none, asked again shortly."""
        voices = self.speaker.voices()
        self._seen = voices
        found = voice_for(voices, language)
        if found is None and not self._recheck.isActive():
            self._recheck.start()
        return found

    def state(self, text: str, language: str) -> Say:
        if self.voice(language) is None:
            return Say.NO_VOICE
        return Say.SPEAKING if self.speaking == self.key(text, language) else Say.READY

    def times_said(self, text: str, language: str) -> int:
        """How many times this word has been said on this card."""
        key = self.key(text, language)
        return self._said[1] if self._said[0] == key else 0

    def toggle(self, text: str, language: str) -> None:
        """A click on the button (or its key): says the word, or stops it."""
        key = self.key(text, language)
        if self.speaking == key:
            self.stop()
            return
        voice = self.voice(language)
        if voice is None:
            return
        times = self.times_said(text, language)
        self._said = (key, times + 1)
        self._serial += 1
        serial = self._serial
        self.speaking = key
        self.speaker.say(
            text,
            voice,
            pace(times),
            self._sounding,
            lambda heard: self._ended.emit(serial, heard),
        )
        self.changed.emit()

    def stop(self) -> None:
        if self.speaking is not None:
            self.speaking = None
            self.speaker.stop()
            self.changed.emit()

    def forget(self) -> None:
        """The card closed, or shows another word: it stops, and the next
        word starts at its own pace."""
        self.stop()
        self._said = ("", 0)

    def add_voice(self) -> None:
        """Windows' speech settings, where Add voices is; a Mac's Spoken
        Content, where Manage Voices is."""
        self._open_url(pc_or_mac(SPEECH_SETTINGS, MAC_SPEECH_SETTINGS))

    def _sounding(self, start: float, seconds: float) -> None:
        if self.hush is not None:
            self.hush(start, seconds)

    def _on_ended(self, serial: int, heard: bool) -> None:
        if serial == self._serial and self.speaking is not None:
            self.speaking = None
            self.changed.emit()

    def _look_again(self) -> None:
        if self.speaker.voices() != self._seen:
            self.changed.emit()
