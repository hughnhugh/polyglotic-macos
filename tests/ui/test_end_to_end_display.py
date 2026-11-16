"""The whole path to the screen, headless: replayed audio -> speech pipeline
-> listening session -> a stand-in server on a real WebSocket -> caption
updates on the session's thread -> `main`'s `QtListener` -> the caption
history on the Qt thread -> the app's caption window and its transcript.
Synthetic "speech" only."""

import time
from collections.abc import Callable

from PySide6.QtWidgets import QApplication
from tests.fake_server import FakeServer
from tests.fakes import MemoryCredentialStore
from tests.test_end_to_end import speech
from tests.test_speech_pipeline import LoudnessDetector
from tests.ui.fakes import FakeAppList, MemorySettingsStore

from polyglotic_desktop.connection.app import AppInfo
from polyglotic_desktop.connection.reconnect import Reconnects
from polyglotic_desktop.connection.session import ListeningSession, Timings
from polyglotic_desktop.core.listening.sources import MIC, Source, SourceId
from polyglotic_desktop.core.listening.timing import CaptionTiming
from polyglotic_desktop.main import (
    QtListener,
    listening_settings,
    wire_caption_windows,
    wire_transcripts,
)
from polyglotic_desktop.platform.replay import ReplayCapture, join
from polyglotic_desktop.platform.speech_pipeline import SpeechPipeline
from polyglotic_desktop.ports.capture import SourceCategory
from polyglotic_desktop.ports.credentials import DeviceCredentials
from polyglotic_desktop.ui.app import ConnectionState, DesktopApp
from polyglotic_desktop.ui_next.caption_windows import CaptionWindows
from polyglotic_desktop.ui_next.transcripts import Transcripts
from polyglotic_desktop.ui_next.views.placement import Rect

APP = SourceId("app")


def process_until(condition: Callable[[], bool], timeout: float = 20.0) -> None:
    deadline = time.monotonic() + timeout
    while not condition():
        if time.monotonic() > deadline:
            raise AssertionError("timed out waiting")
        QApplication.processEvents()
        time.sleep(0.02)


def test_replayed_speech_reaches_the_caption_window_and_transcript(
    qapp: QApplication,
) -> None:
    server = FakeServer()
    store = MemorySettingsStore({"apps": ["Video Player"], "targets": ["zh"]})
    desktop = DesktopApp(store, None, FakeAppList())
    windows = CaptionWindows(store, MIC, lambda: [Rect(0, 0, 1920, 1040)])
    transcripts = Transcripts(windows, store)
    wire_caption_windows(windows, desktop, lambda: None)
    wire_transcripts(transcripts, desktop)
    windows.set_captioned([("Video Player", APP)])
    sessions: list[ListeningSession] = []
    pipeline = SpeechPipeline(
        LoudnessDetector,
        CaptionTiming(live_update_interval=1.5),
        on_ready=lambda: sessions[0].speech_ready(),
    )
    session = ListeningSession(
        server.url,
        MemoryCredentialStore(DeviceCredentials("install", "pgd_" + "t" * 43)),
        AppInfo("0.1.0", "windows-11"),
        listening_settings(desktop.settings.value, windows.targets()),
        pipeline.take,
        QtListener(desktop, pipeline),
        timings=Timings(answer_within=2, close_within=1),
        reconnects=Reconnects(random=lambda: 0.0),
    )
    sessions.append(session)
    replay = ReplayCapture(join([speech(2.5), speech(1.0)], gap=3.0), speed=None)
    try:
        session.start()
        process_until(lambda: desktop.connection is ConnectionState.LISTENING)
        pipeline.add_source(Source(APP, SourceCategory.VIDEO), replay)
        process_until(lambda: sum(not c.live for c in desktop.history.captions) == 2)
    finally:
        pipeline.stop()
        session.stop()
        server.stop()
    QApplication.processEvents()
    lines = windows.windows["Video Player"].view.lines
    assert [line.key for line in lines] == [c.key for c in desktop.history.captions]
    # the stand-in translation, under what was said
    assert lines[0].rows[-1].text.startswith("[zh] ")
    transcript = transcripts.transcripts["Video Player"].lines
    assert (
        sum(r.text.startswith("[zh] ") for line in transcript for r in line.rows) == 2
    )
    transcripts.close()
    windows.close()
    desktop.close()
