"""Hearing a looked-up word (polyglotic-hq 286, decision 0077): the lookup
card's speaker button over the `Speaker` port, on the interface thread.

`main` hands it the PC's speaker and the speech pipeline's `hush`, so the
word the app says is never captioned. One word at a time: a click says the
card's word at its own pace, every time (`views.speech`); a click while
it speaks stops it, and the card closing stops it too. A word played in a
basic voice brings the card's better-voice notice (`notice`, 518). The
speaker's thread is never waited for: what it says comes back as a queued
signal. Nothing is sent anywhere.

Holds the word being said: never logged.
"""

from collections.abc import Callable, Sequence

from PySide6.QtCore import QObject, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices

from polyglotic_desktop.ports.speaker import RECORDED, Sounding, Speaker, Voice
from polyglotic_desktop.ui_next.os_words import on_linux, pc_or_mac
from polyglotic_desktop.ui_next.views.speech import (
    MAC_SPEECH_SETTINGS,
    NORMAL,
    SPEECH_SETTINGS,
    BetterVoice,
    Say,
    system_voice,
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
        recorded: Callable[[Voice, str], bool] = lambda _voice, _word: False,
        recorded_voices: Callable[[], tuple[Voice, ...]] | None = None,
        better: BetterVoice | None = None,
    ) -> None:
        """`hush`: told when the app's own sound plays (the speech
        pipeline's), from the speaker's thread; `open_url`: opens Windows'
        speech settings; `recorded`: whether a recorded voice has this word
        (`platform.recorded_voices.Recordings.has`); `recorded_voices`: the
        recorded voices now (`Recordings.voices`) - asked each time, so a
        pack's recordings that arrive while the app runs are said from the
        next card, not once the speaker's list of voices (kept a few seconds)
        is looked at again (polyglotic-hq 453). None: the speaker's list.
        `better`: when a better voice is worth adding (518); None: never."""
        super().__init__(parent)
        self.speaker = speaker
        self._recorded = recorded
        self._recorded_voices = recorded_voices
        self.hush = hush
        self._open_url = open_url
        self._ended.connect(self._on_ended)
        self._serial = 0
        self.speaking: str | None = None
        """The key (`key`) of the word being said, if any."""
        self._better = better
        self.notice: str | None = None
        """The key (`key`) of the word last played in a basic voice, while
        the card says a better one can be added (polyglotic-hq 518)."""
        self._seen: tuple[Voice, ...] = ()
        self._recheck = QTimer(self, singleShot=True, interval=RECHECK_MS)
        self._recheck.timeout.connect(self._look_again)

    @staticmethod
    def key(text: str, language: str) -> str:
        return f"{language}\n{text}"

    def voice(
        self, language: str, text: str = "", recorded_as: Sequence[str] = ()
    ) -> Voice | None:
        """The voice that says `text` in `language` now: the language's
        recorded voice if it has the word (decision 0133), else one of the
        PC's; with none, asked again shortly. `recorded_as`: the forms the
        word's recording may be kept under, best first, in place of `text`
        (a Traditional form's Simplified ones: `views.lookup.Card.simplified`,
        polyglotic-hq 439)."""
        chosen = self._choose(language, text, recorded_as)
        return chosen[0] if chosen is not None else None

    def _choose(
        self, language: str, text: str, recorded_as: Sequence[str]
    ) -> tuple[Voice, str] | None:
        """`voice`, and what it is asked to say: the form it has recorded,
        else `text` as written."""
        if self._recorded_voices is not None:
            recorded = voice_for(self._recorded_voices(), language) if text else None
            if recorded is not None:
                said = next(
                    (f for f in recorded_as or (text,) if self._recorded(recorded, f)),
                    None,
                )
                if said is not None:
                    return recorded, said
        voices = self.speaker.voices()
        self._seen = voices
        if self._recorded_voices is None:
            ours = tuple(v for v in voices if v.id.startswith(RECORDED))
            recorded = voice_for(ours, language) if text else None
            if recorded is not None:
                said = next(
                    (f for f in recorded_as or (text,) if self._recorded(recorded, f)),
                    None,
                )
                if said is not None:
                    return recorded, said
        found = voice_for(
            tuple(v for v in voices if not v.id.startswith(RECORDED)), language
        )
        if found is None and not self._recheck.isActive():
            self._recheck.start()
        return (found, text) if found is not None else None

    def state(self, text: str, language: str, recorded_as: Sequence[str] = ()) -> Say:
        if self.voice(language, text, recorded_as) is None:
            return Say.NO_VOICE
        return Say.SPEAKING if self.speaking == self.key(text, language) else Say.READY

    def toggle(self, text: str, language: str, recorded_as: Sequence[str] = ()) -> None:
        """A click on the button (or its key): says the word, or stops it.
        A recording kept under one of `recorded_as` is played (`voice`)."""
        key = self.key(text, language)
        if self.speaking == key:
            self.stop()
            return
        chosen = self._choose(language, text, recorded_as)
        if chosen is None:
            return
        voice, said = chosen
        due = self._better is not None and self._better.due(voice, language)
        self.notice = key if due else None
        self._serial += 1
        serial = self._serial
        self.speaking = key
        self.speaker.say(
            said,
            voice,
            NORMAL,
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
        """The card closed, or shows another word: it stops, and its notice
        goes."""
        self.stop()
        self.notice = None

    def dismiss(self, never_again: bool) -> None:
        """The notice's Dismiss: it goes - for good in the word's language
        with "Don't show again" ticked."""
        if self.notice is None:
            return
        if never_again and self._better is not None:
            language = self.notice.partition("\n")[0]  # as `key` puts it
            self._better.silence(language)
        self.notice = None
        self.changed.emit()

    def add_voice(self) -> None:
        """Windows' speech settings, where Add voices is; a Mac's Spoken
        Content, where Manage Voices is. Linux has no such page: its steps
        are in words (591)."""
        if not on_linux():
            self._open_url(pc_or_mac(SPEECH_SETTINGS, MAC_SPEECH_SETTINGS))

    def system_voice(self) -> bool:
        """Whether the PC's own voices answer (`views.speech.system_voice`)."""
        return system_voice(self.speaker.voices())

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
        elif not getattr(self.speaker, "listed", True):
            self._recheck.start()
