"""The mic while the dictation key is held (platform.dictation_mic): pieces
in order, a long hold cut at its quiet moment, nothing after a drop - on a
stand-in capture, no device."""

import threading
from functools import partial

import numpy as np
import pytest

from polyglotic_desktop.platform.dictation_mic import (
    RESPEAK_GAIN,
    RESPEAK_PEAK,
    DictationMic,
    encode_respeaking,
    speaker_hold,
)
from polyglotic_desktop.ports.capture import AudioCallback, MicPiece

RATE = 16000


class StandInCapture:
    """An `AudioCapture` the test feeds by hand."""

    def __init__(self, error: str | None = None) -> None:
        self.on_audio: AudioCallback | None = None
        self.stopped = False
        self._error = error

    def start(self, on_audio: AudioCallback) -> None:
        self.on_audio = on_audio

    def stop(self) -> None:
        self.stopped = True

    @property
    def capturing(self) -> str | None:
        return None if self._error else "Microphone"

    @property
    def error(self) -> str | None:
        return self._error

    restarts = 0  # never fails (566)

    def feed(self, start: float, seconds: float, loudness: float = 0.1) -> None:
        assert self.on_audio is not None
        audio = np.full(round(seconds * RATE), loudness, dtype=np.float32)
        self.on_audio(start, audio.tobytes())


class Pieces:
    def __init__(self) -> None:
        self.got: list[MicPiece] = []
        self.last = threading.Event()

    def __call__(self, piece: MicPiece) -> None:
        self.got.append(piece)
        if piece.last:
            self.last.set()


def seconds_encoded(audio: np.ndarray) -> bytes:
    """A stand-in for Ogg Opus: the audio's length, readable back."""
    return str(len(audio) / RATE).encode()


def test_speaker_holds_use_the_configured_output_then_the_default() -> None:
    selected: list[str | None] = ["headphones"]
    devices: list[str | None] = []
    capture = StandInCapture()

    def loopback(device: str | None) -> StandInCapture:
        devices.append(device)
        return capture

    recorder = speaker_hold(loopback, lambda: selected[0])
    try:
        for hold in (1, 2):
            pieces = Pieces()
            recorder.open(hold, pieces)
            capture.feed(100, 1, loudness=0.0)
            recorder.close(0)
            assert pieces.last.wait(5)
            [piece] = pieces.got
            assert piece.speech is None and not piece.mic_failed
            selected[0] = None
        assert devices == ["headphones", None]
    finally:
        recorder.stop()


def test_speakers_send_one_bounded_piece_only_after_release() -> None:
    capture = StandInCapture()
    pieces = Pieces()
    recorder = DictationMic(
        lambda: capture, piece_max_sec=2, encode=seconds_encoded, single_piece=True
    )
    try:
        recorder.open(1, pieces)
        capture.feed(100, 1)
        capture.feed(101, 2)
        assert recorder.level() > 0
        assert not pieces.last.is_set() and not pieces.got
        recorder.close(0)
        capture.feed(103, 1)  # a packet whose callback arrives after release
        assert pieces.last.wait(5)
        [piece] = pieces.got
        assert piece == MicPiece(1, 100, 102, b"2.0", True)
    finally:
        recorder.stop()


def test_a_hold_is_handed_on_as_one_piece_after_its_tail() -> None:
    capture = StandInCapture()
    mic = DictationMic(lambda: capture, encode=seconds_encoded)
    pieces = Pieces()
    mic.open(1, pieces)
    capture.feed(100.0, 1.5)
    assert mic.level() > 0.5  # 0.1 loud, times the meter's gain
    mic.close(0.05)
    capture.feed(101.5, 0.05)  # the tail, still heard
    assert pieces.last.wait(5)
    mic.stop()
    assert capture.stopped
    [piece] = pieces.got
    assert (piece.hold, piece.last, piece.mic_failed) == (1, True, False)
    assert piece.start == 100.0
    assert abs(piece.end - 101.55) < 1e-6
    assert piece.speech == b"1.55"
    assert mic.level() == 0.0


def test_a_long_hold_is_cut_at_its_quiet_moment_and_carries_on() -> None:
    capture = StandInCapture()
    mic = DictationMic(lambda: capture, piece_max_sec=3.0, encode=seconds_encoded)
    pieces = Pieces()
    mic.open(7, pieces)
    capture.feed(0.0, 2.5)
    capture.feed(2.5, 0.2, loudness=0.0)  # a pause at 2.5 s
    capture.feed(2.7, 0.5)  # 3.2 s in all: cut at the pause
    capture.feed(3.2, 1.0)
    mic.close(0.0)
    assert pieces.last.wait(5)
    mic.stop()
    first, last = pieces.got
    assert (first.hold, first.last, first.start) == (7, False, 0.0)
    assert 2.5 <= first.end <= 2.7
    assert last.last and last.start == first.end
    assert abs(last.end - 4.2) < 1e-6


def test_a_dropped_hold_hands_nothing_on() -> None:
    capture = StandInCapture()
    mic = DictationMic(lambda: capture, encode=seconds_encoded)
    pieces = Pieces()
    mic.open(1, pieces)
    capture.feed(0.0, 1.0)
    mic.close(0.5)
    mic.drop()  # Esc, before the tail ended
    capture.feed(1.0, 0.5)  # what the capture still delivers is ignored
    mic.stop()
    assert pieces.got == []
    assert capture.stopped


def test_a_mic_that_gave_nothing_says_whether_it_failed() -> None:
    for error, failed in ((None, False), ("No microphone", True)):
        capture = StandInCapture(error)
        mic = DictationMic(partial(lambda c: c, capture), encode=seconds_encoded)
        pieces = Pieces()
        mic.open(3, pieces)
        mic.close(0.0)
        assert pieces.last.wait(5)
        mic.stop()
        assert pieces.got == [MicPiece(3, 0.0, 0.0, None, True, mic_failed=failed)]


def test_a_new_hold_drops_the_last_one() -> None:
    first, second = StandInCapture(), StandInCapture()
    captures = iter((first, second))
    mic = DictationMic(lambda: next(captures), encode=seconds_encoded)
    pieces = Pieces()
    mic.open(1, pieces)
    first.feed(0.0, 1.0)
    mic.open(2, pieces)
    assert first.stopped
    first.feed(1.0, 1.0)  # the old capture's late audio is ignored
    second.feed(5.0, 1.0)
    mic.close(0.0)
    assert pieces.last.wait(5)
    mic.stop()
    [piece] = pieces.got
    assert (piece.hold, piece.start, piece.speech) == (2, 5.0, b"1.0")


@pytest.mark.parametrize(
    ("peak", "expected"),
    [
        (0.0, 0.0),
        (0.001, 0.001 * RESPEAK_GAIN.default),
        (0.08, RESPEAK_PEAK.default),
        (0.7, 0.7),
    ],
)
def test_re_speaking_boosts_quiet_audio_without_overdriving_loud_audio(
    monkeypatch: pytest.MonkeyPatch, peak: float, expected: float
) -> None:
    from polyglotic_desktop.platform import dictation_mic

    def encode(audio: np.ndarray) -> bytes:
        assert max(abs(audio)) == pytest.approx(expected)
        return b"encoded"

    monkeypatch.setattr(dictation_mic, "encode_ogg_opus", encode)
    audio = np.array([-peak, peak, 0.0], dtype=np.float32)
    assert encode_respeaking(audio) == b"encoded"
    assert max(abs(audio)) == pytest.approx(peak)
