"""The desktop's whole path, headless: replayed audio to captions on the listener.

Replay source -> speech pipeline (a loudness stand-in for Silero, the real
timing rules, real Ogg Opus) -> listening session -> a stand-in server on
a real WebSocket -> caption updates back. MVP.md's "end to end, stand-in
models" test layer, on the app's side; against the real server it's run
by hand (`harness listen --replay`), since the server repo is private.
"""

import numpy as np
from tests.fake_server import FakeServer, wait_until
from tests.fakes import MemoryCredentialStore
from tests.test_session import Listener
from tests.test_speech_pipeline import LoudnessDetector

from polyglotic_desktop.connection.app import AppInfo
from polyglotic_desktop.connection.reconnect import Reconnects
from polyglotic_desktop.connection.session import ListeningSession, Timings
from polyglotic_desktop.core.listening.captions import CaptionKind, Language
from polyglotic_desktop.core.listening.settings import ListeningSettings
from polyglotic_desktop.core.listening.sources import Source, SourceId
from polyglotic_desktop.core.listening.timing import CaptionTiming
from polyglotic_desktop.platform.replay import ReplayCapture, join
from polyglotic_desktop.platform.speech_pipeline import SpeechPipeline
from polyglotic_desktop.ports.capture import SourceCategory
from polyglotic_desktop.ports.credentials import DeviceCredentials

SR = 16000


def speech(seconds: float) -> np.ndarray:
    return (
        np.random.default_rng(1)
        .uniform(-0.5, 0.5, int(seconds * SR))
        .astype(np.float32)
    )


def test_replayed_speech_comes_back_as_captions() -> None:
    server = FakeServer()
    listener = Listener()
    sessions: list[ListeningSession] = []  # wired as main does: pipeline <-> session
    pipeline = SpeechPipeline(
        LoudnessDetector,
        CaptionTiming(live_update_interval=1.5),
        on_ready=lambda: sessions[0].speech_ready(),
    )
    session = ListeningSession(
        server.url,
        MemoryCredentialStore(DeviceCredentials("install", "pgd_" + "t" * 43)),
        AppInfo("0.1.0", "windows-11"),
        ListeningSettings(targets=(Language("zh"),)),
        pipeline.take,
        listener,
        timings=Timings(answer_within=2, close_within=1),
        reconnects=Reconnects(random=lambda: 0.0),
    )
    sessions.append(session)
    # Three stretches of "speech" 3s apart (no joins), replayed in real time
    # so live updates go out while each one is still being spoken.
    audio = join([speech(2.5), speech(3.0), speech(1.0)], gap=3.0)
    replay = ReplayCapture(audio, speed=1.0)
    try:
        session.start()
        wait_until(listener.listening)
        pipeline.add_source(Source(SourceId("app"), SourceCategory.VIDEO), replay)
        assert replay.finished.wait(30)
        wait_until(
            lambda: sum(c.kind is CaptionKind.FINISHED for c in listener.captions) == 3
        )
    finally:
        pipeline.stop()
        session.stop()
        server.stop()
    finished = [c for c in listener.captions if c.kind is CaptionKind.FINISHED]
    live = [c for c in listener.captions if c.kind is CaptionKind.LIVE]
    assert len({c.caption_id for c in finished}) == 3
    assert live, "live updates while the longer stretches were spoken"
    assert {c.caption_id for c in live} <= {c.caption_id for c in finished}
    assert all(
        h.codec == "ogg_opus" and h.source.category == "video" for h, _ in server.speech
    )
    assert all(audio_bytes.startswith(b"OggS") for _, audio_bytes in server.speech)
    assert server.types()[0] == "settings"


def test_the_samples_first_caption_comes_within_seconds() -> None:
    """polyglotic-hq 176: Home's sample, through the whole path - the real
    speech detection (Silero), Quick preview's rules (the default until
    260; Steady's first caption is its first finished one, held to the same
    10 s), a stand-in server - shows its first caption a few seconds after
    it's turned on, not whenever the learner finds something to play. The
    stand-in answers at once; the real models add about 0.2 s (145)."""
    import time

    from polyglotic_desktop.core.listening.timing import CaptionMode
    from polyglotic_desktop.platform.sample import SampleCapture, sample_file
    from polyglotic_desktop.platform.speech_detection import SpeechDetector, load_model

    found = sample_file("zh")
    assert found is not None
    model = load_model()
    server = FakeServer()
    listener = Listener()
    sessions: list[ListeningSession] = []
    mode = CaptionMode.PREVIEW
    pipeline = SpeechPipeline(
        lambda: SpeechDetector(model),
        CaptionTiming(mode.live_update_interval(1.5), rules=mode.rules),
        on_ready=lambda: sessions[0].speech_ready(),
    )
    session = ListeningSession(
        server.url,
        MemoryCredentialStore(DeviceCredentials("install", "pgd_" + "t" * 43)),
        AppInfo("0.1.0", "windows-11"),
        ListeningSettings(targets=(Language("en"),)),
        pipeline.take,
        listener,
        timings=Timings(answer_within=2, close_within=1),
        reconnects=Reconnects(random=lambda: 0.0),
    )
    sessions.append(session)
    sample = SampleCapture(found)  # real time, as it's heard; not aloud here
    try:
        session.start()
        wait_until(listener.listening)
        turned_on = time.monotonic()
        pipeline.add_source(Source(SourceId("sample"), SourceCategory.OTHER), sample)
        wait_until(lambda: bool(listener.captions), timeout=15)
        first = time.monotonic() - turned_on
        wait_until(
            lambda: any(c.kind is CaptionKind.FINISHED for c in listener.captions),
            timeout=15,
        )
        finished = time.monotonic() - turned_on
    finally:
        pipeline.stop()
        session.stop()
        server.stop()
    print(
        f"the sample's first caption: {first:.2f} s; first finished: {finished:.2f} s"
    )
    assert first < 4.0  # the preview line: 1.5 s into the first sentence
    assert finished < 10.0
