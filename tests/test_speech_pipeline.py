"""From captured audio to speech ready to send (platform.speech_pipeline).

The whole path on synthetic audio: a fake capture delivers it, a stand-in
calls any loud frame speech (as the proof of concept's
test_vad_segmentation did), and the real timing rules, slicing and Opus
encoding do the rest.
"""

import io
import logging
import re
import threading
from collections.abc import Callable

import numpy as np
import pytest
import soundfile as sf

from polyglotic_desktop.core.listening.delays import CAPTION_LOG
from polyglotic_desktop.core.listening.sources import Source, SourceId
from polyglotic_desktop.core.listening.timing import (
    FRAME_SAMPLES,
    CaptionId,
    CaptionMode,
    CaptionTiming,
    Decision,
    SpeechKind,
    TimingRules,
    TranscriptionRequest,
)
from polyglotic_desktop.perf import trace
from polyglotic_desktop.platform import speech_pipeline
from polyglotic_desktop.platform.speech_detection import Audio, FrameResult
from polyglotic_desktop.platform.speech_pipeline import Ready, SpeechPipeline, stopped
from polyglotic_desktop.ports.capture import (
    APP_CLOSED,
    NOT_ALLOWED,
    AudioCallback,
    SourceCategory,
)

SR = 16000
T0 = 500.0
APP = Source(SourceId("app"), SourceCategory.VIDEO)
MIC = Source(SourceId("mic"), SourceCategory.MIC)


class LoudnessDetector:
    """Any frame with a sample above 0.1 is speech."""

    def __init__(self) -> None:
        self._leftover = np.zeros(0, dtype=np.float32)

    def feed(self, start: float, audio: Audio) -> list[FrameResult]:
        buffer = np.concatenate([self._leftover, audio])
        count = len(buffer) // FRAME_SAMPLES
        self._leftover = buffer[count * FRAME_SAMPLES :]
        first_end = start + (FRAME_SAMPLES - (len(buffer) - len(audio))) / SR
        return [
            FrameResult(
                first_end + i * FRAME_SAMPLES / SR,
                bool(
                    np.abs(buffer[i * FRAME_SAMPLES : (i + 1) * FRAME_SAMPLES]).max()
                    > 0.1
                ),
            )
            for i in range(count)
        ]


class FakeCapture:
    """Delivers its audio in 10ms pieces when started, then stops."""

    def __init__(self, audio: Audio) -> None:
        self.audio = audio
        self.stopped = False

    def start(self, on_audio: AudioCallback) -> None:
        piece = SR // 100
        for i in range(0, len(self.audio), piece):
            on_audio(
                T0 + i / SR, self.audio[i : i + piece].astype(np.float32).tobytes()
            )

    def stop(self) -> None:
        self.stopped = True

    @property
    def capturing(self) -> str | None:
        return "fake"

    @property
    def error(self) -> str | None:
        return None

    restarts = 0  # never fails (566)


def pattern(*stretches: tuple[float, bool]) -> Audio:
    rng = np.random.default_rng(0)
    return np.concatenate(
        [
            rng.uniform(-0.5, 0.5, int(s * SR)) if loud else np.zeros(int(s * SR))
            for s, loud in stretches
        ]
    ).astype(np.float32)


def drain(pipeline: SpeechPipeline) -> list[Ready]:
    out = []
    while (item := pipeline.take()) is not None:
        out.append(item)
    return out


def test_capture_status_distinguishes_silence_from_sound_without_speech() -> None:
    pipeline = SpeechPipeline(LoudnessDetector, CaptionTiming())
    pipeline.add_source(MIC, FakeCapture(np.zeros(SR, dtype=np.float32)))
    pipeline.add_source(APP, FakeCapture(np.full(SR, 0.01, dtype=np.float32)))
    assert not pipeline.hearing()
    assert pipeline.capture_status() == {APP.id: None}


def test_speech_comes_out_as_requests_with_ogg_opus() -> None:
    ready: list[int] = []
    timing = CaptionTiming(live_update_interval=1.5)
    pipeline = SpeechPipeline(
        LoudnessDetector, timing, on_ready=lambda: ready.append(1)
    )
    capture = FakeCapture(pattern((0.5, False), (4.0, True), (1.5, False)))
    pipeline.add_source(APP, capture)
    out = drain(pipeline)
    kinds = [d.kind for d, _ in out if isinstance(d, TranscriptionRequest)]
    # Nothing was taken while it ran, so the finished caption cancelled its
    # waiting live updates (latest wins).
    assert kinds == [SpeechKind.FINISHED] and ready
    finished, speech = out[0]
    assert isinstance(finished, TranscriptionRequest) and speech is not None
    decoded, rate = sf.read(io.BytesIO(speech), dtype="float32")
    expected = finished.speech_end - finished.speech_start + 0.4  # padded each side
    assert rate == SR and abs(len(decoded) / SR - expected) < 0.05
    pipeline.stop()
    assert capture.stopped


def test_finished_speech_never_sent_is_told_so_its_caption_ends() -> None:
    """polyglotic-hq 557 (529's B3): finished speech dropped before it was
    sent - held through a planned maintenance window, or waiting too long -
    left its live caption provisional for good. Each is told (`dropped`),
    from whichever thread dropped it, with the lock let go."""
    told: list[CaptionId] = []
    pipeline = SpeechPipeline(LoudnessDetector, CaptionTiming(), dropped=told.append)
    pipeline.hold_speech(False)  # the server away for a planned window
    pipeline.add_source(
        APP, FakeCapture(pattern((0.5, False), (1.5, True), (1.0, False)))
    )
    assert drain(pipeline) == []
    assert len(told) == 1
    pipeline.hold_speech(True)
    pipeline.add_source(
        MIC, FakeCapture(pattern((0.5, False), (1.5, True), (1.0, False)))
    )
    finished = [
        d
        for d, _ in drain(pipeline)
        if isinstance(d, TranscriptionRequest) and d.kind is SpeechKind.FINISHED
    ]
    assert len(finished) == 1 and len(told) == 1  # sent: nothing more told


def test_the_pieces_of_a_cut_meet_without_overlapping() -> None:
    """polyglotic-hq 291: nonstop speech cut at Steady's 6s limit was sent
    with 0.2s more audio each side of every cut, so 0.4s - a word or two of
    fast speech - went to both pieces. Now the audio has no margin at a cut:
    the pieces' audio adds up to the whole stretch, with its two margins."""
    timing = CaptionTiming(None, rules=CaptionMode.WHOLE.rules)
    pipeline = SpeechPipeline(LoudnessDetector, timing)
    pipeline.add_source(
        APP, FakeCapture(pattern((0.5, False), (13.0, True), (1.5, False)))
    )
    pieces = [
        (d, speech)
        for d, speech in drain(pipeline)
        if isinstance(d, TranscriptionRequest) and d.kind is SpeechKind.FINISHED
    ]
    assert len(pieces) == 3
    assert all(s is not None for _, s in pieces)
    heard = [
        len(sf.read(io.BytesIO(s or b""), dtype="float32")[0]) / SR for _, s in pieces
    ]
    whole = pieces[-1][0].speech_end - pieces[0][0].speech_start + 0.4
    assert sum(heard) == pytest.approx(whole, abs=0.05)
    pipeline.stop()


def test_silence_sends_nothing() -> None:
    pipeline = SpeechPipeline(LoudnessDetector, CaptionTiming())
    pipeline.add_source(APP, FakeCapture(pattern((3.0, False))))
    assert drain(pipeline) == []


def test_the_mic_is_checked_against_the_reference() -> None:
    played = pattern((0.5, False), (4.0, True), (1.5, False))
    # The mic hears the PC's audio, quieter and a little late.
    leaked = np.concatenate([np.zeros(int(0.1 * SR), dtype=np.float32), 0.3 * played])
    leaked = leaked[: len(played)]

    def run(with_reference: bool) -> list[Decision]:
        pipeline = SpeechPipeline(
            LoudnessDetector, CaptionTiming(live_update_interval=1.5)
        )
        reference = (
            pipeline.add_reference(FakeCapture(played)) if with_reference else None
        )
        pipeline.add_source(MIC, FakeCapture(leaked), bleed_reference=reference)
        return [d for d, _ in drain(pipeline)]

    assert run(with_reference=False)  # the same audio is sent without the check
    assert run(with_reference=True) == []  # mic bleed: nothing shown, nothing sent


def test_each_mic_check_is_a_line_of_numbers_in_the_caption_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """polyglotic-hq 290: so the next "my speakers are captioned as me" can
    be seen without content - each stretch of the mic checked for bleed is
    one line in the caption log: its seconds, the best correlation and its
    lag, whether what played was silent, how many outputs played, and the
    verdict. Numbers and fixed words only."""
    played = pattern((0.5, False), (4.0, True), (1.5, False))
    leaked = np.concatenate([np.zeros(int(0.1 * SR), dtype=np.float32), 0.3 * played])
    pipeline = SpeechPipeline(
        LoudnessDetector,
        CaptionTiming(live_update_interval=1.5),
        outputs_playing=lambda: 2,
    )
    reference = pipeline.add_reference(FakeCapture(played))
    with caplog.at_level(logging.INFO, logger=CAPTION_LOG):
        pipeline.add_source(MIC, FakeCapture(leaked[: len(played)]), reference)
    lines = [r.getMessage() for r in caplog.records if r.name == CAPTION_LOG]
    assert lines and all(line.startswith("mic bleed_check ") for line in lines)
    assert all(
        re.fullmatch(r"mic bleed_check( [a-z_]+=[a-z0-9.\-]+)+", line) for line in lines
    )
    assert "outputs_playing=2" in lines[-1] and "bleed=yes" in lines[-1]
    assert "played=sound" in lines[-1]


def test_several_apps_each_have_their_own_detection_and_timing() -> None:
    """Two apps at once (project 054): each speaks on its own, and each
    caption comes from its own source - their speech isn't joined."""
    pipeline = SpeechPipeline(
        LoudnessDetector, CaptionTiming(live_update_interval=None)
    )
    first = Source(SourceId("app-1"), SourceCategory.CALL)
    second = Source(SourceId("app-2"), SourceCategory.VIDEO)
    pipeline.add_source(
        first, FakeCapture(pattern((0.5, False), (2.0, True), (1.5, False)))
    )
    pipeline.add_source(second, FakeCapture(pattern((3.0, True), (1.5, False))))
    finished = [d for d, _ in drain(pipeline) if isinstance(d, TranscriptionRequest)]
    assert sorted(d.source.id for d in finished) == ["app-1", "app-2"]
    assert all(not d.replaces for d in finished)


def test_a_turn_cut_sends_the_other_sources_own_audio() -> None:
    """With the turn-cut rule on, a source starting to speak finishes the
    other's hanging speech: that finished caption's audio is cut from the
    other source's buffer, not the speaker's (polyglotic-hq 142)."""
    rules = TimingRules(turn_cut=0.2)
    pipeline = SpeechPipeline(
        LoudnessDetector, CaptionTiming(live_update_interval=None, rules=rules)
    )
    first = Source(SourceId("app-1"), SourceCategory.CALL)
    second = Source(SourceId("app-2"), SourceCategory.CALL)
    # the first speaks for 2 s, then is quiet - its segment hangs, its
    # hangover (0.8 s) not yet over, when the second starts speaking
    pipeline.add_source(first, FakeCapture(pattern((2.0, True), (0.5, False))))
    pipeline.add_source(second, FakeCapture(pattern((2.6, False), (1.0, True))))
    out = {
        d.source.id: (d, s)
        for d, s in drain(pipeline)
        if isinstance(d, TranscriptionRequest) and d.kind is SpeechKind.FINISHED
    }
    cut, speech = out[first.id]
    assert cut.replaces == () and speech is not None
    assert 2.0 < cut.speech_end - cut.speech_start < 2.6  # its 2 s, with the lead-in
    decoded, _ = sf.read(io.BytesIO(speech), dtype="float32")
    # the first app's speech, not the second's silence over those seconds
    assert float(np.abs(decoded).max()) > 0.1


def test_a_reference_can_be_stopped_on_its_own() -> None:
    pipeline = SpeechPipeline(LoudnessDetector, CaptionTiming())
    kept = FakeCapture(pattern((1.0, False)))
    dropped = FakeCapture(pattern((1.0, False)))
    pipeline.add_reference(kept)
    buffer = pipeline.add_reference(dropped)
    pipeline.remove_reference(buffer)
    assert dropped.stopped and not kept.stopped
    pipeline.stop()
    assert kept.stopped


def test_the_pipeline_notes_when_sound_and_speech_were_heard() -> None:
    """Project 096: what the "no captions?" check looks at, per source."""
    pipeline = SpeechPipeline(LoudnessDetector, CaptionTiming())
    pipeline.add_source(APP, FakeCapture(pattern((2.0, False))))
    quiet = pipeline.activity()[APP.id]
    assert quiet.started > 0 and quiet.last_sound is None and quiet.last_speech is None
    pipeline.add_source(MIC, FakeCapture(pattern((0.5, False), (2.0, True))))
    heard = pipeline.activity()[MIC.id]
    assert heard.first_sound is not None and heard.last_speech is not None
    pipeline.remove_source(MIC.id)
    assert MIC.id not in pipeline.activity()


class NotAllowedCapture(FakeCapture):
    """A capture the OS gives only silence, saying it isn't allowed (411)."""

    @property
    def error(self) -> str | None:
        return NOT_ALLOWED


def test_a_capture_the_os_does_not_allow_is_noted_for_the_check() -> None:
    """polyglotic-hq 411: macOS records silence when its permission isn't
    given; the capture says so, and the "no captions?" check hears it."""
    pipeline = SpeechPipeline(LoudnessDetector, CaptionTiming())
    pipeline.add_source(APP, NotAllowedCapture(pattern((1.0, False))))
    pipeline.add_source(MIC, FakeCapture(pattern((1.0, False))))
    activity = pipeline.activity()
    assert activity[APP.id].not_allowed and not activity[MIC.id].not_allowed


class StateCapture(FakeCapture):
    """A capture in a given state: what it captures, and its error."""

    def __init__(self, capturing: str | None, error: str | None) -> None:
        super().__init__(pattern((0.1, False)))
        self._state = (capturing, error)

    @property
    def capturing(self) -> str | None:
        return self._state[0]

    @property
    def error(self) -> str | None:
        return self._state[1]


def test_a_capture_that_failed_is_noted_as_stopped_for_the_check() -> None:
    """polyglotic-hq 557 (529's B1): a capture whose thread failed captured
    nothing while the check said the app was quiet. It has stopped - and is
    trying again (decision 0266) - when it captures nothing and gives an
    error other than not being allowed or its app having closed."""
    assert stopped(StateCapture(None, "Capture stopped: RuntimeError"))
    assert stopped(StateCapture(None, "Couldn't capture the app: 0x80070005"))
    assert not stopped(StateCapture("My Game", None))
    assert not stopped(StateCapture(None, None))  # between devices, or none plugged
    assert not stopped(StateCapture(None, APP_CLOSED))
    assert not stopped(StateCapture(None, NOT_ALLOWED))
    assert not stopped(StateCapture("Mic", "a stream lost a moment ago"))
    pipeline = SpeechPipeline(LoudnessDetector, CaptionTiming())
    pipeline.add_source(APP, StateCapture(None, "Capture stopped: RuntimeError"))
    pipeline.add_source(MIC, FakeCapture(pattern((1.0, False))))
    activity = pipeline.activity()
    assert activity[APP.id].stopped and not activity[MIC.id].stopped


def test_the_captures_restarts_are_taken_once_each_removed_sources_too() -> None:
    """polyglotic-hq 566: each listening session's summary counts the
    times its captures failed and started again (decision 0266), so the
    pipeline gives those since it was last asked - a source removed
    meanwhile (the learner chose another app) included, none twice."""
    pipeline = SpeechPipeline(LoudnessDetector, CaptionTiming())
    app, mic = FakeCapture(pattern((0.1, False))), FakeCapture(pattern((0.1, False)))
    pipeline.add_source(APP, app)
    pipeline.add_source(MIC, mic)
    assert pipeline.take_restarts() == 0
    app.restarts, mic.restarts = 2, 1
    assert pipeline.take_restarts() == 3
    assert pipeline.take_restarts() == 0
    app.restarts = 5
    pipeline.remove_source(APP.id)
    assert pipeline.take_restarts() == 3
    pipeline.add_source(APP, FakeCapture(pattern((0.1, False))))  # a new capture
    mic.restarts = 2
    assert pipeline.take_restarts() == 1
    pipeline.stop()


def test_finished_speech_is_kept_as_sent_and_cleared_on_delete_and_close() -> None:
    pipeline = SpeechPipeline(LoudnessDetector, CaptionTiming(live_update_interval=1.5))
    pipeline.recent._clock = lambda: T0 + 8.0
    pipeline.add_source(
        APP, FakeCapture(pattern((0.5, False), (4.0, True), (1.5, False)))
    )
    (request, speech), *_ = drain(pipeline)
    assert isinstance(request, TranscriptionRequest) and speech is not None
    held = pipeline.recent.get(request.caption_id)
    assert held is not None and held.audio == speech
    assert (held.start, held.end) == (request.speech_start, request.speech_end)
    assert held.source_id == APP.id and held.category == APP.category
    pipeline.forget_recent()
    assert pipeline.recent.get(request.caption_id) is None


def test_live_updates_and_closing_leave_nothing_held() -> None:
    pipeline = SpeechPipeline(LoudnessDetector, CaptionTiming(live_update_interval=1.0))
    pipeline.recent._clock = lambda: T0 + 8.0
    pipeline.add_source(APP, FakeCapture(pattern((0.5, False), (3.0, True))))
    out = drain(pipeline)
    assert out and all(
        d.kind is SpeechKind.LIVE for d, _ in out if isinstance(d, TranscriptionRequest)
    )
    assert pipeline.recent.size() == 0
    pipeline = SpeechPipeline(LoudnessDetector, CaptionTiming())
    pipeline.recent._clock = lambda: T0 + 8.0
    pipeline.add_source(
        APP, FakeCapture(pattern((0.5, False), (4.0, True), (1.5, False)))
    )
    drain(pipeline)
    assert pipeline.recent.size() > 0
    pipeline.stop()
    assert pipeline.recent.size() == 0


# -- the interface thread never waits on the pipeline (polyglotic-hq 136) ------------------


class LaterCapture(FakeCapture):
    """Delivers its audio when `deliver` is called, on a thread of its own."""

    def start(self, on_audio: AudioCallback) -> None:
        self._on_audio = on_audio

    def deliver(self) -> int:
        """Delivers, and returns the delivering thread's id."""
        thread = threading.Thread(
            target=lambda: super(LaterCapture, self).start(self._on_audio)
        )
        thread.start()
        thread.join(10)
        return thread.ident or 0


def test_the_detector_is_made_on_the_captures_thread_at_its_first_audio() -> None:
    """Adding a source (on the interface thread) never waits for the
    speech-detection model: the detector is made where the audio arrives."""
    made: list[int] = []

    def new_detector() -> LoudnessDetector:
        made.append(threading.get_ident())
        return LoudnessDetector()

    pipeline = SpeechPipeline(new_detector, CaptionTiming())
    capture = LaterCapture(pattern((0.5, False), (2.0, True), (1.5, False)))
    pipeline.add_source(APP, capture)
    assert made == []
    delivering = capture.deliver()
    assert made == [delivering]
    assert any(isinstance(d, TranscriptionRequest) for d, _ in drain(pipeline))


def test_adding_a_source_prepares_the_speech_model_before_its_first_audio() -> None:
    """The speech model loads once something is captioned, not at the app's
    start (polyglotic-hq 513): adding a source starts it loading, so it's
    loading while the capture starts; nothing before that asks for it."""
    calls: list[str] = []
    pipeline = SpeechPipeline(
        lambda: calls.append("detector") or LoudnessDetector(),  # type: ignore[func-returns-value]
        CaptionTiming(),
        preparing=lambda: calls.append("preparing"),
    )
    assert calls == []
    capture = LaterCapture(pattern((0.5, False), (2.0, True), (1.5, False)))
    pipeline.add_source(APP, capture)
    assert calls == ["preparing"]
    capture.deliver()
    assert calls == ["preparing", "detector"]


def test_speech_is_encoded_with_the_lock_free(monkeypatch: object) -> None:
    """Encoding takes tens of milliseconds a time; nothing that takes the
    lock (the interface's pause, another source's frames, the connection's
    `take`) waits on it."""
    pipeline = SpeechPipeline(LoudnessDetector, CaptionTiming())
    locked_while_encoding: list[bool] = []
    real = speech_pipeline.encode_ogg_opus

    def encode(audio: Audio) -> bytes:
        locked_while_encoding.append(pipeline._lock.locked())
        return real(audio)

    assert isinstance(monkeypatch, pytest.MonkeyPatch)
    monkeypatch.setattr(speech_pipeline, "encode_ogg_opus", encode)
    pipeline.add_source(
        APP, FakeCapture(pattern((0.5, False), (4.0, True), (1.5, False)))
    )
    assert locked_while_encoding and not any(locked_while_encoding)
    assert drain(pipeline)


def test_the_listening_mark_reads_hearing_without_the_lock() -> None:
    """`hearing` is asked ten times a second from the interface thread: a
    snapshot kept with each frame, answered even while a capture thread
    holds the lock."""
    pipeline = SpeechPipeline(
        LoudnessDetector, CaptionTiming(live_update_interval=None)
    )
    pipeline.add_source(APP, FakeCapture(pattern((0.5, False), (2.0, True))))
    assert pipeline.hearing() == {APP.id}
    answers: list[frozenset[SourceId]] = []
    with pipeline._lock:  # a capture thread's turn, held long
        asking = threading.Thread(target=lambda: answers.append(pipeline.hearing()))
        asking.start()
        asking.join(1)
    assert answers == [frozenset({APP.id})]
    pipeline.set_paused(True)
    assert pipeline.hearing() == frozenset()
    pipeline.set_paused(False)
    assert pipeline.hearing() == {APP.id}
    pipeline.remove_source(APP.id)
    assert pipeline.hearing() == frozenset()


# -- the app's own word left out (polyglotic-hq 286, decision 0077) -------------------

SYSTEM = Source(SourceId("system"), SourceCategory.SYSTEM)
WORD_AT, WORD_SEC = T0 + 1.0, 0.6
"""A looked-up word said aloud by the app, in the PC's mix."""


def requests(
    source: Source, audio: Audio, hears_the_app: bool, hushed: bool
) -> tuple[list[TranscriptionRequest], Audio | None]:
    """What `source` sends of `audio`, and what its buffer kept of the word."""
    pipeline = SpeechPipeline(
        LoudnessDetector, CaptionTiming(live_update_interval=None)
    )
    if hushed:
        pipeline.hush(WORD_AT, WORD_SEC)  # the speaker's `sounding`
    buffer = pipeline.add_source(
        source, FakeCapture(audio), hears_the_app=hears_the_app
    )
    sent = [d for d, _ in drain(pipeline) if isinstance(d, TranscriptionRequest)]
    kept = buffer.slice(WORD_AT, WORD_AT + WORD_SEC, pad=0)
    pipeline.stop()
    return sent, kept


def test_the_apps_own_word_isnt_captioned_from_the_pcs_mix() -> None:
    """Everything the PC plays hears the word the app says: without the
    hush it comes back as a caption; with it, nothing is sent and the
    buffer holds silence where the word was."""
    word = pattern((1.0, False), (WORD_SEC, True), (2.0, False))
    sent, kept = requests(SYSTEM, word, hears_the_app=True, hushed=False)
    assert [r.kind for r in sent] == [SpeechKind.FINISHED]  # the bug, unhushed
    sent, kept = requests(SYSTEM, word, hears_the_app=True, hushed=True)
    assert sent == []
    assert kept is not None and len(kept) and not np.any(kept)


def test_an_app_on_its_own_and_a_source_not_told_are_never_hushed() -> None:
    """An app captioned on its own (process loopback) can't hear this app:
    its speech at the same moment is still captioned."""
    speech = pattern((1.0, False), (WORD_SEC, True), (2.0, False))
    sent, kept = requests(APP, speech, hears_the_app=False, hushed=True)
    assert [r.kind for r in sent] == [SpeechKind.FINISHED]
    assert kept is not None and np.any(kept)


def test_the_mic_hearing_the_speakers_is_hushed_too() -> None:
    leaked = 0.3 * pattern((1.0, False), (WORD_SEC, True), (2.0, False))
    assert requests(MIC, leaked, hears_the_app=True, hushed=False)[0]
    assert requests(MIC, leaked, hears_the_app=True, hushed=True)[0] == []


def test_a_line_around_the_word_is_captioned_without_it() -> None:
    """The game talks before and after the word: it's still captioned - the
    pause the hush makes ends a caption, and the timing rules may send it
    again joined with what follows - and every speech sent is silent where
    the word was."""
    game = pattern((0.5, False), (4.0, True), (2.0, False))
    game[int((WORD_AT - T0) * SR) : int((WORD_AT - T0 + WORD_SEC) * SR)] = 0.9
    pipeline = SpeechPipeline(
        LoudnessDetector, CaptionTiming(live_update_interval=None)
    )
    pipeline.hush(WORD_AT, WORD_SEC)
    buffer = pipeline.add_source(SYSTEM, FakeCapture(game), hears_the_app=True)
    sent = [
        (d, speech)
        for d, speech in drain(pipeline)
        if isinstance(d, TranscriptionRequest) and speech is not None
    ]
    assert sent and sent[-1][0].speech_end > WORD_AT + 2  # the game after it
    low = WORD_AT - speech_pipeline.HUSH_BEFORE_SEC
    high = WORD_AT + WORD_SEC + speech_pipeline.HUSH_AFTER_SEC
    for request, speech in sent:
        decoded, _ = sf.read(io.BytesIO(speech), dtype="float32")
        cut_from = request.speech_start - 0.2  # padded each side
        game_part = decoded[: max(0, round((low - cut_from) * SR))]
        word_part = decoded[
            max(0, round((low + 0.05 - cut_from) * SR)) : max(
                0, round((high - 0.05 - cut_from) * SR)
            )
        ]
        assert np.abs(word_part).max(initial=0.0) < 0.01  # silent where the word was
        assert np.abs(game_part).max() > 0.2  # the game before it, kept
    longest = max(
        min(r.speech_end + 0.2, high) - max(r.speech_start - 0.2, low) for r, _ in sent
    )
    assert longest > WORD_SEC  # the word's span was in what was sent
    silent = buffer.slice(low + 0.01, high - 0.01, pad=0)
    assert silent is not None and not np.any(silent)
    pipeline.stop()


def test_old_hushes_are_forgotten() -> None:
    pipeline = SpeechPipeline(LoudnessDetector, CaptionTiming())
    pipeline.hush(T0, 0.5)
    pipeline.hush(T0 + 1, 0.5)
    assert len(pipeline._hushes) == 2
    pipeline.hush(T0 + speech_pipeline.HUSHES_KEPT_SEC + 10, 0.5)
    assert len(pipeline._hushes) == 1


# -- legacy re-speaking still suppresses own speech (polyglotic-hq 567) -------------

HELD_AT, LET_GO_AT = T0 + 2.0, T0 + 5.0
"""A re-speaking hold starts 2 s in, and its mic closes 3 s later."""


def test_the_mic_captions_nothing_while_legacy_respeaking_has_it() -> None:
    """The learner talks, holds the re-speaking key and repeats, lets go and
    talks on: what was said before the key went down is a "You" line,
    finished as a pause would finish it; what was repeated never is; what
    follows the tail is captioned again."""
    talk = pattern((0.5, False), (4.0, True), (2.0, False), (2.0, True), (2.0, False))
    pipeline = SpeechPipeline(
        LoudnessDetector, CaptionTiming(live_update_interval=None)
    )
    pipeline.respeaking_holds(HELD_AT)
    pipeline.respeaking_lets_go(LET_GO_AT)
    buffer = pipeline.add_source(MIC, FakeCapture(talk), hears_the_app=True)
    sent = [d for d, _ in drain(pipeline) if isinstance(d, TranscriptionRequest)]
    finished = [r for r in sent if r.kind is SpeechKind.FINISHED]
    assert finished  # before the key, and after the tail
    for request in sent:  # nothing from the hold, padding aside
        held = min(request.speech_end, LET_GO_AT) - max(request.speech_start, HELD_AT)
        assert held <= 0.05
    assert any(r.speech_end <= HELD_AT + 0.05 for r in finished)  # the line before
    assert any(r.speech_start >= LET_GO_AT - 0.05 for r in finished)  # and after
    silent = buffer.slice(HELD_AT + 0.01, LET_GO_AT - 0.01, pad=0)
    assert silent is not None and not np.any(silent)
    pipeline.stop()


def test_while_the_key_is_held_the_mic_captions_nothing_to_its_end() -> None:
    """The key still down (no let go yet): silence from the press on."""
    talk = pattern((0.5, False), (6.0, True), (1.0, False))
    pipeline = SpeechPipeline(
        LoudnessDetector, CaptionTiming(live_update_interval=None)
    )
    pipeline.respeaking_holds(HELD_AT)
    pipeline.add_source(MIC, FakeCapture(talk), hears_the_app=True)
    sent = [d for d, _ in drain(pipeline) if isinstance(d, TranscriptionRequest)]
    assert sent and all(r.speech_end <= HELD_AT + 0.05 for r in sent)
    pipeline.stop()


def test_legacy_respeaking_never_silences_an_app() -> None:
    """Only the mic is re-speaking's: an app talking at the same time is
    still captioned."""
    talk = pattern((0.5, False), (6.0, True), (1.0, False))
    pipeline = SpeechPipeline(
        LoudnessDetector, CaptionTiming(live_update_interval=None)
    )
    pipeline.respeaking_holds(HELD_AT)
    pipeline.respeaking_lets_go(LET_GO_AT)
    buffer = pipeline.add_source(APP, FakeCapture(talk))
    sent = [d for d, _ in drain(pipeline) if isinstance(d, TranscriptionRequest)]
    assert any(r.speech_start < HELD_AT < r.speech_end for r in sent)
    kept = buffer.slice(HELD_AT, LET_GO_AT, pad=0)
    assert kept is not None and np.any(kept)
    pipeline.stop()


@pytest.mark.parametrize("source", [APP, MIC])
@pytest.mark.parametrize("mode", list(CaptionMode))
def test_watching_a_hold_keeps_the_caption_schedule_and_audio(
    source: Source, mode: CaptionMode
) -> None:
    class PushedCapture(FakeCapture):
        def start(self, on_audio: AudioCallback) -> None:
            self.push = on_audio

    def capture(typing: bool) -> tuple[list[Ready], tuple[TranscriptionRequest, ...]]:
        ids = (CaptionId(str(n)) for n in range(100))
        timing = CaptionTiming(
            mode.live_update_interval(1.5), lambda: next(ids), rules=mode.rules
        )
        pipeline = SpeechPipeline(LoudnessDetector, timing)
        active = PushedCapture(np.empty(0, dtype=np.float32))
        pipeline.add_source(source, active)
        other_source = APP if source == MIC else MIC
        other = PushedCapture(np.empty(0, dtype=np.float32))
        pipeline.add_source(other_source, other)
        span = pipeline.watch_captions(source.id, T0 + 1.0) if typing else None
        assert (span is not None) == typing
        # Words straddle both key boundaries. The end waits for the usual
        # caption boundary, while work for the other window continues.
        audio = pattern(
            (0.5, False), (3.0, True), (2.0, False), (2.0, True), (2.0, False)
        )
        end = T0 + 2.5
        sent: list[Ready] = []
        requests: tuple[TranscriptionRequest, ...] | None = None
        step = SR // 100
        try:
            for i in range(0, len(audio), step):
                now = T0 + i / SR
                piece = audio[i : i + step].tobytes()
                active.push(now, piece)
                other.push(now, piece)
                sent.extend(drain(pipeline))
                if span is not None and requests is None and now >= end:
                    requests = pipeline.finished_captions(span, end)
                    if now == end:
                        assert requests is None
            assert not typing or requests
            return sent, requests or ()
        finally:
            pipeline.stop()

    plain, _ = capture(False)
    held, requests = capture(True)
    # Compare timing and decoded samples, since Ogg stream IDs are random.
    assert [decision for decision, _ in held] == [decision for decision, _ in plain]
    for (_, before), (_, after) in zip(plain, held, strict=True):
        if before is not None and after is not None:
            np.testing.assert_array_equal(
                sf.read(io.BytesIO(before))[0], sf.read(io.BytesIO(after))[0]
            )
        else:
            assert before is after
    assert all(r.source == source and r.speech_start < T0 + 2.5 for r in requests)
    assert all(r.speech_end > T0 + 1.0 for r in requests)
    assert {r.source for r, _ in held if isinstance(r, TranscriptionRequest)} == {
        APP,
        MIC,
    }


def test_paused_and_absent_sources_cannot_supply_a_hold() -> None:
    pipeline = SpeechPipeline(LoudnessDetector, CaptionTiming())
    assert pipeline.watch_captions(APP.id, T0) is None
    pipeline.add_source(APP, FakeCapture(np.empty(0, dtype=np.float32)))
    try:
        pipeline.set_paused_sources(frozenset({APP.id}))
        assert pipeline.watch_captions(APP.id, T0) is None
        pipeline.set_paused_sources(frozenset())
        span = pipeline.watch_captions(APP.id, T0)
        assert span is not None
        pipeline.remove_source(APP.id)
        assert pipeline.finished_captions(span, T0 + 1) == ()
    finally:
        pipeline.stop()


def test_the_mic_has_a_detector_of_its_own_and_every_other_source_the_same() -> None:
    """polyglotic-hq 352, decision 0145: the mic's speech detection raises
    quiet audio less (`new_mic_detector`); every other source's is made by
    `new_detector`. Without a mic's own, the mic's is `new_detector`'s too."""
    made: list[str] = []

    def detector(kind: str) -> Callable[[], LoudnessDetector]:
        def make() -> LoudnessDetector:
            made.append(kind)
            return LoudnessDetector()

        return make

    sound = pattern((0.1, True))
    timing = CaptionTiming(live_update_interval=None)
    pipeline = SpeechPipeline(
        detector("every source"), timing, new_mic_detector=detector("the mic")
    )
    pipeline.add_source(APP, FakeCapture(sound))
    pipeline.add_source(MIC, FakeCapture(sound))
    assert made == ["every source", "the mic"]

    made.clear()
    alone = SpeechPipeline(detector("every source"), CaptionTiming(None))
    alone.add_source(MIC, FakeCapture(sound))
    assert made == ["every source"]


class DeafDetector:
    """Hears nothing as speech, and gives each frame's level as the real
    detector does (root mean square)."""

    def __init__(self) -> None:
        self._leftover = np.zeros(0, dtype=np.float32)

    def feed(self, start: float, audio: Audio) -> list[FrameResult]:
        buffer = np.concatenate([self._leftover, audio])
        count = len(buffer) // FRAME_SAMPLES
        self._leftover = buffer[count * FRAME_SAMPLES :]
        first_end = start + (FRAME_SAMPLES - (len(buffer) - len(audio))) / SR
        return [
            FrameResult(
                first_end + i * FRAME_SAMPLES / SR,
                False,
                float(
                    np.sqrt(
                        np.mean(
                            np.square(
                                buffer[i * FRAME_SAMPLES : (i + 1) * FRAME_SAMPLES]
                            )
                        )
                    )
                ),
            )
            for i in range(count)
        ]


def test_sound_heard_as_not_speech_goes_to_the_caption_timelines() -> None:
    """polyglotic-hq 549: a stretch over 3 s of sound nothing heard as
    speech is in the timelines - done when the sound stops, as it stands
    while it goes on, and done as stopped when its source is removed."""
    made = trace.Tracer(clock=lambda: T0 + 10.0)  # the captures' clock
    before = trace.use(made)
    try:
        pipeline = SpeechPipeline(DeafDetector, CaptionTiming())
        pipeline.add_source(APP, FakeCapture(pattern((5.0, True), (2.0, False))))
        [done] = made.recent()
        assert (done["kind"], done["src"], done["end"]) == (
            "sound_unheard",
            "video",
            "quiet",
        )
        assert done["len"] == pytest.approx(5.0, abs=0.05)
        game = Source(SourceId("game"), SourceCategory.GAME)
        pipeline.add_source(game, FakeCapture(pattern((6.0, True))))
        assert [r["end"] for r in made.recent() if r["src"] == "game"] == ["open"]
        pipeline.remove_source(game.id)
        assert [r["end"] for r in made.recent() if r["src"] == "game"] == ["stopped"]
        assert drain(pipeline) == []  # nothing heard, nothing sent
        pipeline.stop()
        assert len(made.recent()) == 2
    finally:
        trace.use(before)
