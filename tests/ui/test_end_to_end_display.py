"""The whole path to the screen, headless: replayed audio -> speech pipeline
-> listening session -> a stand-in server on a real WebSocket -> caption
updates on the session's thread -> `main`'s `QtListener` -> the caption
history on the Qt thread -> the app's caption window and its transcript.
Synthetic "speech" only."""

import time
from collections.abc import Callable
from functools import partial
from types import SimpleNamespace
from typing import Any

import pytest
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from tests import fake_server
from tests.fake_server import FakeServer
from tests.fakes import MemoryCredentialStore
from tests.test_connection import Heard
from tests.test_end_to_end import speech
from tests.test_session import SIGNED_IN, Speech
from tests.test_speech_pipeline import LoudnessDetector
from tests.ui.fakes import FakeAppList, MemorySettingsStore

from polyglotic_desktop.adapters.sqlite_outbox import SqliteOutbox
from polyglotic_desktop.connection import protocol
from polyglotic_desktop.connection import session as session_module
from polyglotic_desktop.connection.app import AppInfo
from polyglotic_desktop.connection.exchange import DataExchange
from polyglotic_desktop.connection.reconnect import Reconnects
from polyglotic_desktop.connection.session import ListeningSession, Timings
from polyglotic_desktop.core.listening.sources import MIC, Source, SourceId
from polyglotic_desktop.core.listening.timing import (
    CaptionId,
    CaptionTiming,
    SpeechKind,
    TranscriptionRequest,
)
from polyglotic_desktop.main import (
    QtListener,
    caption_connection,
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


@pytest.mark.parametrize(
    ("language", "original", "wpm"),
    [("en", "Five birds fly over water.", 100), ("ja", "小鳥が青い空を飛ぶ。", 120)],
)
def test_untimed_finished_speech_reaches_the_pace_label(
    qapp: QApplication,
    monkeypatch: pytest.MonkeyPatch,
    language: str,
    original: str,
    wpm: int,
) -> None:
    caption_for = fake_server.caption_for

    def answer(header: protocol.SpeechHeader) -> dict[str, Any]:
        reply = caption_for(header)
        reply.update(language=language, languages_heard=[language])
        reply["clauses"][0]["original"] = original
        return reply

    monkeypatch.setattr(fake_server, "caption_for", answer)
    now = time.perf_counter()
    monkeypatch.setattr(
        session_module,
        "time",
        SimpleNamespace(perf_counter=lambda: now, monotonic=time.monotonic),
    )
    server = FakeServer()
    outbox = SqliteOutbox(":memory:")
    store = MemorySettingsStore({"apps": ["Video Player"], "targets": ["zh"]})
    desktop = DesktopApp(store, None, FakeAppList())
    windows = CaptionWindows(store, MIC, lambda: [Rect(0, 0, 1920, 1040)])
    wire_caption_windows(windows, desktop, lambda: None)
    windows.set_captioned([("Video Player", APP)])
    shown = windows.windows["Video Player"]
    listener = QtListener(desktop, None)
    connection = caption_connection(
        server.url,
        MemoryCredentialStore(SIGNED_IN),
        AppInfo("0.1.0", "windows-11"),
        DataExchange(outbox, outbox, Heard(), "cedict"),
        listener,
        windows,
    )
    timer = listener.findChild(QTimer, "speaking_pace_timer")
    assert timer is not None
    speech = Speech()

    def displayed(expected: CaptionId) -> bool:
        return any(
            c.caption_id == expected for c in shown.view.captions_of(shown.view.lines)
        )

    try:
        session = connection.start_listening(
            listening_settings(desktop.settings.value, windows.targets()), speech.take
        )
        process_until(timer.isActive)
        observed = []
        for number in range(10):
            now += 3
            caption_id = CaptionId(f"birds-{number}")
            speech.put(
                TranscriptionRequest(
                    caption_id,
                    SpeechKind.FINISHED,
                    Source(APP, SourceCategory.VIDEO),
                    now - 3,
                    now,
                    voiced_seconds=2.0,
                ),
                b"opus",
            )
            session.speech_ready()
            process_until(partial(displayed, caption_id))
            qapp.processEvents()
            assert shown.pace.isVisible()
            observed.append(shown.pace.text())
        assert observed == [f"{wpm} wpm · avg {wpm}"] * 10
        assert (
            shown.pace.them_row.accessibleName()
            == f"Them: {wpm} words a minute, average {wpm}"
        )
        line = shown.view.lines[-1]
        assert line.has_pace and line.label.endswith(f" · {wpm} wpm")
        assert len(line.label.split(" · ")[-2]) == 5  # HH:MM
        shown.set_show_pace(False)
        assert not shown.view.lines[-1].has_pace
        assert "wpm" not in shown.view.lines[-1].label
        shown.set_show_pace(True)
        assert shown.view.lines[-1].label == line.label
        assert session._summary.pace(now)[2:] == (0, 0)
        now += 2.0
        assert session._summary.pace(now)[:2] == (wpm, wpm)
        assert shown.pace.text() == f"{wpm} wpm · avg {wpm}"
        now += 5.5
        process_until(lambda: shown.pace.text() == f"{round(wpm / 2)} wpm · avg {wpm}")
        now += 2.5
        process_until(lambda: shown.pace.text() == f"0 wpm · avg {wpm}")

        now += 0.5
        short = CaptionId("short")
        speech.put(
            TranscriptionRequest(
                short,
                SpeechKind.FINISHED,
                Source(APP, SourceCategory.VIDEO),
                now - 0.5,
                now,
                voiced_seconds=0.5,
            ),
            b"opus",
        )
        session.speech_ready()
        process_until(partial(displayed, short))
        assert "wpm" not in shown.view.lines[-1].label
    finally:
        connection.close()
        server.stop()
        windows.close()
        desktop.close()
        outbox.close()
