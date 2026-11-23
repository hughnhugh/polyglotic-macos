"""The mic while the dictation key is held (`ports.capture.HeldMic`; polyglotic-hq 283, decision 0073).

Opened when the key goes down, closed `tail` seconds after it comes up -
the only time dictation hears anything. Its audio stays in memory until
its piece is handed on as Ogg Opus (decision 0005), and is then dropped:
nothing is written anywhere.

A hold longer than `PIECE_MAX_SEC` is cut while it goes on, at its
quietest moment in the last few seconds (core's `quietest_cut`), and the
piece handed on at once; the rest carries on into the next. Pieces are
encoded and handed on by one worker thread of the mic's own, in order -
never on the capture's thread, which mustn't wait.

`level` is the loudness of the latest audio, 0 to 1, for the sign's meter.
"""

import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

import numpy as np

from polyglotic_desktop.core.listening.dictation import PIECE_MAX_SEC, quietest_cut
from polyglotic_desktop.core.listening.respeaking import RESPEAK_GAIN, RESPEAK_PEAK
from polyglotic_desktop.core.listening.timing import VAD_SAMPLE_RATE
from polyglotic_desktop.core.listening.type_theirs import SILENCE_PEAK
from polyglotic_desktop.platform.opus import encode_ogg_opus
from polyglotic_desktop.platform.speech_detection import Audio
from polyglotic_desktop.ports.capture import AudioCapture, MicPiece

STEP_SEC = 0.1
"""The loudness is measured in steps this long to find where to cut."""
LEVEL_GAIN = 12.0
"""Speech's loudness (RMS around 0.02-0.08) times this fills the meter."""


def encode_respeaking(audio: Audio) -> bytes:
    """Bring quiet held-mic audio up before encoding, with a gain limit."""
    peak = float(np.max(np.abs(audio), initial=0.0))
    if 0.0 < peak < RESPEAK_PEAK.configured:
        audio = audio * min(RESPEAK_GAIN.configured, RESPEAK_PEAK.configured / peak)
    return encode_ogg_opus(audio)


def encode_speakers(audio: Audio) -> bytes | None:
    """Skip near-silence. Normalise quiet audio before encoding."""
    if float(np.max(np.abs(audio), initial=0.0)) < SILENCE_PEAK.configured:
        return None
    return encode_respeaking(audio)


class DictationMic:
    """The mic for dictation's holds, one at a time."""

    def __init__(
        self,
        new_capture: Callable[[], AudioCapture],
        piece_max_sec: float = PIECE_MAX_SEC,
        encode: Callable[[Audio], bytes | None] = encode_ogg_opus,
        *,
        single_piece: bool = False,
    ) -> None:
        """`new_capture`: the mic's capture, made for each hold (the
        learner's chosen mic, or Windows' default)."""
        self._new_capture = new_capture
        self._piece_max = round(piece_max_sec * VAD_SAMPLE_RATE)
        self._encode = encode
        self._single_piece = single_piece
        self._lock = threading.Lock()
        self._worker = ThreadPoolExecutor(1, thread_name_prefix="dictation-mic")
        self._capture: AudioCapture | None = None
        self._hold = 0
        self._on_piece: Callable[[MicPiece], None] = lambda _piece: None
        self._chunks: list[Audio] = []
        self._start: float | None = None  # the current piece's first sample
        self._samples = 0
        self._level = 0.0
        self._closing: threading.Timer | None = None

    def open(self, hold: int, on_piece: Callable[[MicPiece], None]) -> None:
        self.drop()
        capture = self._new_capture()
        with self._lock:
            self._capture, self._hold, self._on_piece = capture, hold, on_piece
            self._chunks, self._start, self._samples = [], None, 0
            self._level = 0.0
        capture.start(lambda start, samples: self._heard(capture, start, samples))

    def close(self, tail: float) -> None:
        with self._lock:
            capture = self._capture
            if capture is None or self._closing is not None:
                return
            if tail:
                self._closing = threading.Timer(tail, self._finish, args=(capture,))
                self._closing.daemon = True
                self._closing.start()
                return
        self._finish(capture)

    def drop(self) -> None:
        with self._lock:
            capture, self._capture = self._capture, None
            if self._closing is not None:
                self._closing.cancel()
                self._closing = None
            self._chunks, self._start, self._samples = [], None, 0
            self._level = 0.0
        if capture is not None:
            capture.stop()

    def level(self) -> float:
        return self._level

    def stop(self) -> None:
        """At the app's end: the mic closed, the worker's last piece out."""
        self.drop()
        self._worker.shutdown(wait=True)

    def _heard(self, capture: AudioCapture, start: float, samples: bytes) -> None:
        """A capture thread's audio: kept, measured, and cut once the piece
        is long enough."""
        audio = np.frombuffer(samples, dtype=np.float32)
        level = float(np.sqrt(np.mean(audio**2))) if len(audio) else 0.0
        with self._lock:
            if capture is not self._capture:
                return  # dropped, or a newer hold's
            self._level = min(1.0, level * LEVEL_GAIN)
            if self._single_piece:
                # The server accepts a bounded finished caption. Keep one
                # clip, and continue to meter until the key is released.
                audio = audio[: self._piece_max - self._samples]
                if not len(audio):
                    return
            if self._start is None:
                self._start = start
            self._chunks.append(audio)
            self._samples += len(audio)
            if self._single_piece or self._samples < self._piece_max:
                return
            audio_now = np.concatenate(self._chunks)
            at = _cut_at(audio_now)
            piece_start, hold = self._start, self._hold
            self._chunks = [audio_now[at:]]
            self._samples = len(audio_now) - at
            self._start = piece_start + at / VAD_SAMPLE_RATE
            on_piece = self._on_piece
        self._hand_on(on_piece, hold, piece_start, audio_now[:at], last=False)

    def _finish(self, capture: AudioCapture) -> None:
        """The tail is over: the capture closed, the last piece handed on."""
        with self._lock:
            if capture is not self._capture:
                return
            self._capture, self._closing = None, None
            chunks, start, hold = self._chunks, self._start, self._hold
            self._chunks, self._start, self._samples = [], None, 0
            self._level = 0.0
            on_piece = self._on_piece

        def finish() -> None:
            if self._single_piece:
                capture.stop()
            if start is None or not chunks:
                on_piece(
                    MicPiece(hold, 0.0, 0.0, None, True, capture.error is not None)
                )
                return
            audio = np.concatenate(chunks)
            end = start + len(audio) / VAD_SAMPLE_RATE
            try:
                speech = self._encode(audio)
            except (OSError, ValueError):
                on_piece(MicPiece(hold, start, end, None, True, mic_failed=True))
            else:
                on_piece(MicPiece(hold, start, end, speech, True))

        if not self._single_piece:
            capture.stop()
        self._worker.submit(finish)

    def _hand_on(
        self,
        on_piece: Callable[[MicPiece], None],
        hold: int,
        start: float,
        audio: Audio,
        last: bool,
    ) -> None:
        end = start + len(audio) / VAD_SAMPLE_RATE

        def encode_and_hand_on() -> None:
            on_piece(MicPiece(hold, start, end, self._encode(audio), last))

        self._worker.submit(encode_and_hand_on)


def _cut_at(audio: Audio) -> int:
    """Where to cut `audio`, in samples: at the start of its quietest
    `STEP_SEC` near the end (core's `quietest_cut`)."""
    step = round(STEP_SEC * VAD_SAMPLE_RATE)
    whole = len(audio) // step
    if whole == 0:
        return len(audio)
    steps = audio[: whole * step].reshape(whole, step)
    levels = np.sqrt(np.mean(steps**2, axis=1))
    return max(step, quietest_cut([float(x) for x in levels], STEP_SEC) * step)


def speaker_hold(
    loopback: Callable[[str | None], AudioCapture], selected: Callable[[], str | None]
) -> DictationMic:
    """Read the Speakers setting when the hold starts, including OS default."""
    return DictationMic(
        lambda: loopback(selected()), encode=encode_speakers, single_piece=True
    )
