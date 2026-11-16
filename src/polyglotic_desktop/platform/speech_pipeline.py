"""From captured audio to speech ready to send, for every source at once.

For each source: its audio goes into an `AudioBuffer` (the last 30s) and
through a `SpeechDetector` - the same for every source, but the mic's
raises quiet audio less (`MIC_GAIN_MAX`, decision 0145); each frame's result goes to core's
`CaptionTiming`; each transcription request it makes is cut from the
buffer (padded 0.2s each side) and encoded as Ogg Opus; and the result
waits in core's `PendingSpeech` (latest wins) until the connection takes
it. The mic's speech is checked for mic bleed against the whole system's
audio (decision 0004), and each stretch checked is a line of numbers in
the caption log, written after the lock is let go (`mic_bleed.log_line`).

Runs on the captures' own threads; one lock keeps the timing and the
queue consistent across them. The lock is held for the timing's decisions
only, never while speech is cut and encoded (tens of milliseconds a time),
and `hearing` - asked ten times a second from the interface thread for the
listening mark - reads a snapshot without it (polyglotic-hq project 136:
the mark's poll blocked the interface for 62-79 ms). Each source's
detector is made on its capture's thread at its first audio, so adding a
source never waits for the speech-detection model. Everything stays in
memory.

**The app's own sound is left out** (polyglotic-hq 286, decision 0077):
while a looked-up word is said aloud (`hush`), the sources that hear the
PC's mix - everything the PC plays, everything else, and the mic, which can
hear the speakers (`hears_the_app`) - hear silence from `HUSH_BEFORE_SEC`
before it to `HUSH_AFTER_SEC` after it: their speech detector, their buffer
and so the speech sent. An app captioned on its own never hears this app.

**What's dictated is dictation's alone** (polyglotic-hq 299): while the
dictation key is held, and its tail after (`dictation_holds`,
`dictation_lets_go`), the mic's captions hear silence - the same as a hush,
for the mic only - so a dictation is never also a "You" line, nor counted
twice. A "You" line under way as the key goes down is finished with what
was said before it: the silence ends its speech, as a pause would.
"""

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import replace
from typing import Protocol

import numpy as np

from polyglotic_desktop.core.listening.check import SourceActivity
from polyglotic_desktop.core.listening.delays import CAPTION_LOG
from polyglotic_desktop.core.listening.pending import PendingSpeech
from polyglotic_desktop.core.listening.recent_speech import HeldSpeech, RecentSpeech
from polyglotic_desktop.core.listening.sources import Source, SourceId
from polyglotic_desktop.core.listening.timing import (
    VAD_SAMPLE_RATE,
    CaptionId,
    CaptionTiming,
    Decision,
    SpeechKind,
    TimingRules,
    TranscriptionRequest,
)
from polyglotic_desktop.platform.audio_buffer import AudioBuffer
from polyglotic_desktop.platform.mic_bleed import MicBleed, log_line
from polyglotic_desktop.platform.opus import encode_ogg_opus
from polyglotic_desktop.platform.speech_detection import Audio, FrameResult
from polyglotic_desktop.ports.capture import NOT_ALLOWED, AudioCapture, SourceCategory

SOUND_PEAK = 0.001
"""A frame of audio whose loudest sample is above this (about -60 dB) is
sound, not silence: what the "no captions?" check counts."""

caption_log = logging.getLogger(CAPTION_LOG)

Ready = tuple[Decision, bytes | None]
"""A decision and, for a transcription request, its speech as Ogg Opus."""

HUSH_BEFORE_SEC = 0.05
"""Silence from this long before the app's own sound starts: the clocks'
jitter (WASAPI's packet times are 9-12 ms behind, decision 0006)."""
HUSH_AFTER_SEC = 0.4
"""...to this long after it ends: the output's own delay, and the room's
for the mic - Bluetooth speakers add 0.1-0.3 s."""
HUSHES_KEPT_SEC = 60.0
"""A hush older than this is forgotten: audio arrives within a second."""
UNTIL_LET_GO = float("inf")
"""The end of a dictation's span while its key is still held."""


class FrameDetector(Protocol):
    """Speech detection for one stream (`SpeechDetector`, or a stand-in)."""

    def feed(self, start: float, audio: Audio) -> list[FrameResult]: ...


class SpeechPipeline:
    """The sources of one listening session, turned into speech to send."""

    def __init__(
        self,
        new_detector: Callable[[], FrameDetector],
        timing: CaptionTiming,
        on_ready: Callable[[], None] = lambda: None,
        recent: RecentSpeech | None = None,
        outputs_playing: Callable[[], int | None] = lambda: None,
        new_mic_detector: Callable[[], FrameDetector] | None = None,
    ) -> None:
        """`on_ready` is called (on a capture thread) whenever something new
        is waiting; `take` returns it. Each finished caption `take` hands
        over is also kept in `recent` (audio as sent, in memory only).
        `outputs_playing` says how many outputs play sound now (None: not
        known), for the caption log's line on each mic-bleed check.
        `new_mic_detector` makes the mic's speech detection (its gain at
        most `MIC_GAIN_MAX`, decision 0145); `new_detector` every other
        source's, and the mic's when it's not given."""
        self._outputs_playing = outputs_playing
        self.recent = recent or RecentSpeech(time.monotonic)
        self._new_detector = new_detector
        self._new_mic_detector = new_mic_detector or new_detector
        self.timing = timing
        self._pending: PendingSpeech[bytes | None] = PendingSpeech()
        self._on_ready = on_ready
        self._lock = threading.Lock()
        self._captures: dict[SourceId, AudioCapture] = {}
        self._buffers: dict[SourceId, AudioBuffer] = {}
        self._references: list[tuple[AudioBuffer, AudioCapture]] = []
        self._activity: dict[SourceId, SourceActivity] = {}
        self._hearing: frozenset[SourceId] = frozenset()
        """`timing.hearing()` as of the last change, for `hearing`."""
        self._hushes: tuple[tuple[float, float], ...] = ()
        """When the app's own sound plays, margins included (`hush`):
        replaced whole, so a capture thread reads it without a lock."""
        self._dictated: tuple[tuple[float, float], ...] = ()
        """When dictation has the mic (`dictation_holds`): the mic's captions
        hear silence then. Replaced whole, as `_hushes`."""
        self._hush_lock = threading.Lock()  # for the writers

    def activity(self) -> dict[SourceId, SourceActivity]:
        """Per source: when it started, when sound and speech were first
        and last heard (`time.monotonic` seconds), and whether its capture
        says the OS doesn't allow it (`NOT_ALLOWED`). From any thread."""
        with self._lock:
            found = dict(self._activity)
            captures = dict(self._captures)
        for source_id, act in found.items():
            capture = captures.get(source_id)
            if capture is not None and capture.error == NOT_ALLOWED:
                found[source_id] = replace(act, not_allowed=True)
        return found

    def add_source(
        self,
        source: Source,
        capture: AudioCapture,
        bleed_reference: AudioBuffer | None = None,
        hears_the_app: bool = False,
    ) -> AudioBuffer:
        """Starts captioning `source` from `capture`. `bleed_reference` is
        what the PC played, for the mic. `hears_the_app`: the capture can
        hear this app's own sound (the PC's mix, or the mic), so it's silent
        while that plays (`hush`). Returns the source's buffer."""
        buffer = AudioBuffer()
        detector: FrameDetector | None = None  # made at the first audio
        bleed = (
            MicBleed(buffer, bleed_reference) if bleed_reference is not None else None
        )
        the_mic = source.category is SourceCategory.MIC
        new_detector = self._new_mic_detector if the_mic else self._new_detector
        with self._lock:
            self.timing.add_source(source, bleed)

        def on_audio(start: float, samples: bytes) -> None:
            nonlocal detector
            if detector is None:  # on the capture's thread, not the caller's
                detector = new_detector()
            audio = np.frombuffer(samples, dtype=np.float32)
            if hears_the_app and self._hushes:
                audio = _silenced(start, audio, self._hushes)
            if the_mic and self._dictated:  # dictation's alone (299)
                audio = _silenced(start, audio, self._dictated)
            buffer.append(start, audio)
            frames = detector.feed(start, audio)
            self._note(source.id, audio, any(f.speech for f in frames))
            if not frames:
                return
            with self._lock:
                decisions = [
                    decision
                    for frame in frames
                    for decision in self.timing.frame(
                        source.id, frame.end, frame.speech, frame.level
                    )
                ]
                self._hearing = self.timing.hearing()
            if bleed is not None:
                self._log_checked(bleed)
            if not decisions:
                return
            # cut and encoded with the lock free: a request's speech is in
            # its source's buffer already (the buffer has its own lock) - this
            # source's, or another's that a turn cut finished
            ready = [
                (decision, self._speech(decision, buffer, source.id))
                for decision in decisions
            ]
            with self._lock:
                for decision, speech in ready:
                    self._pending.put(decision, speech)
            self._on_ready()

        with self._lock:
            self._activity[source.id] = SourceActivity(time.monotonic())
        self._captures[source.id] = capture
        self._buffers[source.id] = buffer
        capture.start(on_audio)
        return buffer

    def _log_checked(self, bleed: MicBleed) -> None:
        """The caption log's line for each stretch `bleed` checked since
        last time - numbers only - with the lock let go."""
        checked = bleed.checked()
        if checked:
            outputs = self._outputs_playing()
            for each in checked:
                caption_log.info(log_line(each, outputs))

    def _note(self, source_id: SourceId, audio: Audio, speech: bool) -> None:
        loud = len(audio) > 0 and float(np.max(np.abs(audio))) > SOUND_PEAK
        if not loud and not speech:
            return
        now = time.monotonic()
        with self._lock:
            kept = self._activity.get(source_id)
            if kept is None:
                return
            self._activity[source_id] = SourceActivity(
                kept.started,
                kept.first_sound or (now if loud else None),
                now if loud else kept.last_sound,
                now if speech else kept.last_speech,
            )

    def hush(self, start: float, seconds: float) -> None:
        """The app's own sound plays from `start` (`time.perf_counter`, the
        captures' clock) for `seconds` - a word said aloud: the sources that
        hear the app hear silence then, margins included. From any thread
        (the speaker's)."""
        span = (start - HUSH_BEFORE_SEC, start + seconds + HUSH_AFTER_SEC)
        with self._hush_lock:
            kept = tuple(h for h in self._hushes if h[1] > start - HUSHES_KEPT_SEC)
            self._hushes = (*kept, span)

    def dictation_holds(self, start: float) -> None:
        """The dictation key went down at `start` (`time.perf_counter`, the
        captures' clock): the mic is dictation's from then until
        `dictation_lets_go` - the mic's captions hear silence. From any
        thread (polyglotic-hq 299)."""
        with self._hush_lock:
            kept = tuple(d for d in self._dictated if d[1] > start - HUSHES_KEPT_SEC)
            self._dictated = (*kept, (start, UNTIL_LET_GO))

    def dictation_lets_go(self, at: float) -> None:
        """Dictation's mic closes at `at` (the captures' clock: the key's
        release and its tail, or now for a hold dropped): the mic's captions
        hear it again from then. From any thread."""
        with self._hush_lock:
            self._dictated = tuple(
                (low, at if high == UNTIL_LET_GO else high)
                for low, high in self._dictated
            )

    def add_reference(self, capture: AudioCapture) -> AudioBuffer:
        """Captures audio only to compare with the mic (decision 0004): it
        is buffered, never detected, encoded or sent."""
        buffer = AudioBuffer()
        capture.start(
            lambda start, samples: buffer.append(
                start, np.frombuffer(samples, np.float32)
            )
        )
        self._references.append((buffer, capture))
        return buffer

    def remove_reference(self, buffer: AudioBuffer) -> None:
        """Stops the reference capture `add_reference` returned `buffer` for."""
        for kept in [r for r in self._references if r[0] is buffer]:
            kept[1].stop()
            self._references.remove(kept)

    def remove_source(self, source_id: SourceId) -> None:
        capture = self._captures.pop(source_id, None)
        if capture is not None:
            capture.stop()
        self._buffers.pop(source_id, None)
        with self._lock:
            self._activity.pop(source_id, None)
            self.timing.remove_source(source_id)
            self.recent.remove_source(source_id)
            self._hearing = self.timing.hearing()

    def hold_speech(self, holding: bool) -> None:
        """False while the server is away for a planned maintenance window:
        nothing is kept to send after it (`PendingSpeech.hold`;
        polyglotic-hq 319). From any thread."""
        with self._lock:
            self._pending.hold(holding)

    def take(self) -> Ready | None:
        """The next decision to send, with its speech; None if none waits."""
        with self._lock:
            ready = self._pending.take()
            if ready is not None:
                self._keep_recent(*ready)
            return ready

    def get(self, caption_id: CaptionId) -> HeldSpeech | None:
        """A finished caption's audio as sent, or None: not held any more
        (`RecentSpeechPort`, for "Looks wrong?"). From any thread."""
        with self._lock:
            return self.recent.get(caption_id)

    def held_speech(self) -> tuple[HeldSpeech, ...]:
        """Every finished caption's audio held now, as sent ("Report a
        problem", polyglotic-hq 275). From any thread."""
        with self._lock:
            return self.recent.held()

    def forget_recent(self) -> None:
        """Empties the recent-speech store (listening data deleted). From
        any thread."""
        with self._lock:
            self.recent.clear()

    def _keep_recent(self, decision: Decision, speech: bytes | None) -> None:
        if (
            isinstance(decision, TranscriptionRequest)
            and decision.kind is SpeechKind.FINISHED
            and speech is not None
        ):
            self.recent.add(
                HeldSpeech(
                    decision.caption_id,
                    decision.source.id,
                    decision.source.category,
                    decision.speech_start,
                    decision.speech_end,
                    speech,
                ),
                decision.replaces,
            )

    def hearing(self) -> frozenset[SourceId]:
        """The sources whose speech is under way (`CaptionTiming.hearing`),
        as of the last frame or change. From any thread, without waiting:
        a snapshot, never the lock."""
        return self._hearing

    def set_paused(self, paused: bool) -> None:
        """Pause or resume: nothing is sent while paused. From any thread."""
        with self._lock:
            self.timing.paused = paused
            self._hearing = self.timing.hearing()

    def set_paused_sources(self, sources: frozenset[SourceId]) -> None:
        """These sources paused on their own - caption windows hidden past
        the learner's limit (polyglotic-hq 335) - and every other resumed:
        nothing is sent for them. From any thread."""
        with self._lock:
            self.timing.paused_sources = sources
            self._hearing = self.timing.hearing()

    def set_timing(
        self,
        rules: TimingRules,
        live_update_interval: float | None,
        max_wait: float | None,
    ) -> None:
        """The timing rules and live-update interval of the learner's caption
        mode (None: no live updates), and their longest wait for text
        (`CaptionTiming.max_wait`), from the next frame on. From any
        thread."""
        with self._lock:
            self.timing.change(rules, live_update_interval)
            self.timing.max_wait = max_wait
            self._hearing = self.timing.hearing()

    def set_pace_hint(self, seconds: float | None) -> None:
        """The server's pace hint: live updates at most every `seconds`
        (None: as the user chose). From any thread."""
        with self._lock:
            self.timing.pace_hint = seconds

    def stop(self) -> None:
        for source_id in list(self._captures):
            self.remove_source(source_id)
        for _, capture in self._references:
            capture.stop()
        self._references.clear()
        self.forget_recent()

    def _speech(
        self, decision: Decision, own: AudioBuffer, own_id: SourceId
    ) -> bytes | None:
        """A request's speech, cut from its source's buffer: `own` for the
        source whose frame made the decision, else that source's (a turn
        cut finishes another source's speech - `CaptionTiming._turn_cuts`);
        None if the source is gone, or nothing of it is buffered."""
        if not isinstance(decision, TranscriptionRequest):
            return None
        buffer = (
            own
            if decision.source.id == own_id
            else self._buffers.get(decision.source.id)
        )
        if buffer is None:
            return None
        before, after = decision.pads  # no margin at a cut (polyglotic-hq 291)
        audio = buffer.slice(
            decision.speech_start, decision.speech_end, before, pad_after=after
        )
        return encode_ogg_opus(audio) if audio is not None else None


def _silenced(
    start: float, audio: Audio, spans: tuple[tuple[float, float], ...]
) -> Audio:
    """`audio`, captured from `start`, with what falls in `spans` silent:
    a copy if anything does."""
    end = start + len(audio) / VAD_SAMPLE_RATE
    quiet = None
    for low, high in spans:
        if high <= start or low >= end:
            continue
        if quiet is None:
            quiet = audio.copy()
        first = max(0, round((low - start) * VAD_SAMPLE_RATE))
        last = min(len(audio), round((min(high, end) - start) * VAD_SAMPLE_RATE))
        quiet[first:last] = 0.0
    return audio if quiet is None else quiet
