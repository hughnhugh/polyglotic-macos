"""`main`'s wiring, with fakes for capture and the session: the session's
calls reach the interface on the Qt thread, its states show on Home, the
settings become the server's settings, and the sources follow the user's
choice. Made-up apps only."""

import threading
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock

import pytest
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QApplication, QDialog, QWidget
from tests.ui.fakes import FakeAppList, MemorySettingsStore

from polyglotic_desktop.connection.reconnect import StopReason
from polyglotic_desktop.connection.session import SessionState, Status
from polyglotic_desktop.core.listening.captions import (
    CaptionKind,
    CaptionUpdate,
    Clause,
    Language,
)
from polyglotic_desktop.core.listening.playout import ReadingPath
from polyglotic_desktop.core.listening.recent_speech import HeldSpeech
from polyglotic_desktop.core.listening.recheck import RecheckOutcome, RecheckResult
from polyglotic_desktop.core.listening.settings import ListeningSettings
from polyglotic_desktop.core.listening.sources import (
    Capture,
    CaptureMode,
    Source,
    SourceId,
)
from polyglotic_desktop.core.listening.timing import CaptionId, CaptionMode
from polyglotic_desktop.main import (
    QtListener,
    SourcePlan,
    Sources,
    connection_state,
    listening_settings,
    once_running,
    plan_sources,
    plus_is_back,
    start_notice,
    wire_continuation_refresh,
)
from polyglotic_desktop.platform.audio_buffer import AudioBuffer
from polyglotic_desktop.ports.capture import (
    AppList,
    AudioCallback,
    PlayingApp,
    SourceCategory,
)
from polyglotic_desktop.ui.app import ConnectionState, DesktopApp
from polyglotic_desktop.ui.recorded_captions import clause, finished
from polyglotic_desktop.ui.settings import AppSettings
from polyglotic_desktop.ui_next.views.plan import PlanLine, PlanWords

BROWSER = PlayingApp(20, "Web Browser", True, SourceCategory.BROWSER)
CHAT = PlayingApp(30, "Chat App", True, SourceCategory.CALL)


class FakeCapture:
    def __init__(self, name: str) -> None:
        self.name = name

    def start(self, on_audio: AudioCallback) -> None: ...

    def stop(self) -> None: ...

    @property
    def capturing(self) -> str | None:
        return self.name

    @property
    def error(self) -> str | None:
        return None

    restarts = 0  # never fails (566)


class FakePipeline:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.pace: float | None = None
        self.references: dict[int, str] = {}
        self.sources: list[Source] = []
        self.hear_the_app: dict[str, bool] = {}
        self.holding = True  # speech kept to send (False: a planned window, 319)

    def hold_speech(self, holding: bool) -> None:
        self.holding = holding

    def add_source(
        self,
        source: Source,
        capture: FakeCapture,
        reference: AudioBuffer | None = None,
        hears_the_app: bool = False,
    ) -> AudioBuffer:
        self.calls.append(
            f"{source.id}:{source.category}:{capture.name}:{bool(reference)}"
        )
        self.sources.append(source)
        self.hear_the_app[source.id] = hears_the_app
        return AudioBuffer()

    def add_reference(self, capture: FakeCapture) -> AudioBuffer:
        self.calls.append(f"reference:{capture.name}")
        buffer = AudioBuffer()
        self.references[id(buffer)] = capture.name
        return buffer

    def remove_source(self, source_id: str) -> None:
        self.calls.append(f"remove:{source_id}")

    def remove_reference(self, buffer: AudioBuffer) -> None:
        self.calls.append(f"remove reference:{self.references.pop(id(buffer))}")

    def stop(self) -> None:
        self.calls.append("stop")

    def set_pace_hint(self, seconds: float | None) -> None:
        self.pace = seconds


def test_the_settings_become_the_servers_settings() -> None:
    value = AppSettings(
        targets=("en", "zh"),
        second_languages={"en": "zh"},
        spoken_language="zh",
        spelling_hints=("Caleb",),
        caption_mode_chosen="live",
    )
    settings = listening_settings(value)
    assert settings.targets == (Language("en"), Language("zh"))
    # Chinese's English by default (polyglotic-hq 555), English's chosen
    assert settings.second_languages == {
        Language("en"): Language("zh"),
        Language("zh"): Language("en"),
    }
    assert settings.spoken_language == Language("zh") and settings.translate_live
    assert settings.spelling_hints == ("Caleb",)
    assert listening_settings(AppSettings()).spoken_language is None


@pytest.mark.parametrize("mode", ["words", "calm"])
def test_which_modes_lines_are_translated_live(mode: str) -> None:
    """Paced clauses translate regardless of the Instant-only switch."""
    on = AppSettings(caption_mode_chosen=mode, translate_live=True)
    assert listening_settings(on).translate_live
    off = AppSettings(caption_mode_chosen=mode, translate_live=False)
    assert listening_settings(off).translate_live


@pytest.mark.parametrize("mode", ["live", "scrolling"])
def test_video_requests_the_same_live_translation_as_everyday_instant(
    mode: str,
) -> None:
    everyday = AppSettings(
        caption_mode_chosen="live", targets=("zh",), translate_live=False
    )
    video = replace(everyday, preset="video", caption_mode_chosen=mode)
    assert listening_settings(video) == listening_settings(everyday)
    assert listening_settings(video).translate_live


@pytest.mark.parametrize(
    ("stored", "preset", "mode", "path", "expected"),
    [
        ({}, "everyday", "live", "both", True),
        ({"translate_live": False}, "everyday", "live", "follow", True),
        ({"translate_live": False}, "video", "live", "both", True),
        ({"translate_live": False}, "video", "scrolling", "both", True),
        ({}, "learning", "words", "follow", True),
        ({}, "learning", "words", "acquisition", False),
        ({}, "learning", "words", "both", True),
    ],
)
def test_open_windows_decide_whether_the_session_translates_live(
    stored: dict[str, object],
    preset: str,
    mode: str,
    path: str,
    expected: bool,
) -> None:
    """Fresh and pre-0.1.10 settings follow what the open window displays."""
    value = replace(
        AppSettings.from_stored(stored),
        preset=preset,
        caption_mode_chosen=mode,
        caption_path=path,
    )
    shown = {SourceId("app"): (Language("zh"),)}
    assert listening_settings(value, shown).translate_live is expected
    assert not listening_settings(value, {SourceId("app"): ()}).translate_live


def test_each_open_windows_own_timing_path_and_lines_decide_live_translation() -> None:
    """Global Steady + Acquisition cannot suppress an Instant window."""
    value = AppSettings(caption_mode_chosen="words", caption_path="acquisition")
    targets = {
        SourceId("everyday"): (Language("zh"),),
        SourceId("video"): (),
    }
    reading = {
        SourceId("everyday"): (CaptionMode.INSTANT, ReadingPath.BOTH),
        SourceId("video"): (CaptionMode.SCROLLING, ReadingPath.BOTH),
    }
    assert listening_settings(value, targets, window_reading=reading).translate_live

    learning = {SourceId("learning"): (Language("zh"),)}
    acquisition = {SourceId("learning"): (CaptionMode.STEADY, ReadingPath.ACQUISITION)}
    assert not listening_settings(
        value, learning, window_reading=acquisition
    ).translate_live


def test_the_sessions_states_as_home_shows_them() -> None:
    assert connection_state(Status(SessionState.LISTENING)) == (
        ConnectionState.LISTENING,
        None,
    )
    assert connection_state(Status(SessionState.WAITING, retry_in=3.0)) == (
        ConnectionState.WAITING,
        3.0,
    )
    stopped = Status(SessionState.STOPPED, stopped=StopReason.SIGN_IN_NEEDED)
    assert connection_state(stopped)[0] is ConnectionState.SIGN_IN_NEEDED
    update = Status(SessionState.STOPPED, stopped=StopReason.UPDATE_REQUIRED)
    assert connection_state(update)[0] is ConnectionState.UPDATE_NEEDED
    assert connection_state(Status(SessionState.STOPPED))[0] is ConnectionState.STOPPED
    moved = Status(SessionState.STOPPED, stopped=StopReason.LISTENING_MOVED)
    assert connection_state(moved) == (ConnectionState.MOVED, None)
    # 4009: the server closed listening because Plus ended - said as that,
    # not "Stopped" (polyglotic-hq 185)
    ended = Status(SessionState.STOPPED, stopped=StopReason.LIMIT_REACHED)
    assert connection_state(ended) == (ConnectionState.PLUS_ENDED, None)
    # the server full: said as that, not the learner's connection (203, 208)
    busy = Status(SessionState.WAITING, retry_in=24.0, server_busy=True)
    assert connection_state(busy) == (ConnectionState.SERVER_BUSY, 24.0)
    trying = Status(SessionState.CONNECTING)
    assert connection_state(trying, ConnectionState.SERVER_BUSY) == (
        ConnectionState.SERVER_BUSY,
        None,
    )


def test_each_try_while_reconnecting_still_says_reconnecting() -> None:
    """A server down: the session waits, tries (CONNECTING), waits... The
    learner sees Reconnecting throughout - the caption windows' notice
    doesn't go blank for each try (polyglotic-hq 133: about a quarter of
    an outage) - with no countdown while it tries. The first connection
    still says Connecting."""
    trying = Status(SessionState.CONNECTING)
    assert connection_state(trying, ConnectionState.WAITING) == (
        ConnectionState.WAITING,
        None,
    )
    assert connection_state(trying, ConnectionState.NOT_CONNECTED) == (
        ConnectionState.CONNECTING,
        None,
    )
    back = Status(SessionState.LISTENING)
    assert (
        connection_state(back, ConnectionState.WAITING)[0] is ConnectionState.LISTENING
    )
    # Plus ended: "Plus has ended" stays while the session asks again
    # whether the account has Plus (polyglotic-hq 203), then Listening
    assert connection_state(trying, ConnectionState.PLUS_ENDED) == (
        ConnectionState.PLUS_ENDED,
        None,
    )
    assert (
        connection_state(back, ConnectionState.PLUS_ENDED)[0]
        is ConnectionState.LISTENING
    )


def test_update_needed_stays_while_the_session_asks_again() -> None:
    """Refused for its version, the session asks the server again every
    few minutes (polyglotic-hq 137): each try still says "Update needed",
    and listening again once the server takes the version."""
    trying = Status(SessionState.CONNECTING)
    assert connection_state(trying, ConnectionState.UPDATE_NEEDED) == (
        ConnectionState.UPDATE_NEEDED,
        None,
    )
    back = Status(SessionState.LISTENING)
    assert connection_state(back, ConnectionState.UPDATE_NEEDED)[0] is (
        ConnectionState.LISTENING
    )


def test_the_sessions_calls_reach_the_interface_on_the_qt_thread(
    qapp: QApplication,
) -> None:
    chosen = MemorySettingsStore({"app_name": "Web Browser"})
    desktop = DesktopApp(chosen, None, FakeAppList())
    pipeline = FakePipeline()
    listener = QtListener(desktop, pipeline)  # type: ignore[arg-type]

    def session_thread() -> None:
        listener.status_changed(Status(SessionState.LISTENING))
        listener.caption_updated(finished("a", clause("你好。", "Hello.")))
        listener.pace_changed(2.0)

    thread = threading.Thread(target=session_thread)
    thread.start()
    thread.join()
    assert desktop.history.version == 0  # waiting for the Qt thread
    assert pipeline.pace == 2.0  # the pipeline is thread-safe
    QApplication.processEvents()
    assert [c.original for c in desktop.history.captions] == ["你好。"]
    assert desktop.connection is ConnectionState.LISTENING
    desktop.close()


def test_minutes_and_notices_reach_home_on_the_qt_thread(qapp: QApplication) -> None:
    """project 027's "What's left": the server's `minutes` and `notice` were
    only logged; now Home shows them (and the caption windows a notice,
    briefly)."""
    desktop = DesktopApp(
        MemorySettingsStore({"whole_system": False}), None, FakeAppList()
    )
    listener = QtListener(desktop, FakePipeline())  # type: ignore[arg-type]
    minutes: list[tuple[float, object]] = []
    notices: list[str] = []
    desktop.minutes_changed.connect(lambda used, left: minutes.append((used, left)))
    desktop.home_notice.connect(notices.append)

    def session_thread() -> None:
        listener.minutes_changed(42.5, None)
        listener.notice("models_warming_up")

    thread = threading.Thread(target=session_thread)
    thread.start()
    thread.join()
    assert minutes == [] and notices == []  # not yet
    QApplication.processEvents()
    assert minutes == [(42.5, None)]
    assert len(notices) == 1 and "speech model is starting" in notices[0]
    desktop.close()


def test_captions_failing_reach_the_qt_thread_in_order_with_captions(
    qapp: QApplication,
) -> None:
    """`processing_failed` from the session's thread: two in a row say
    captions are failing; a caption after them, queued behind, ends it."""
    desktop = DesktopApp(
        MemorySettingsStore({"whole_system": False}), None, FakeAppList()
    )
    listener = QtListener(desktop, FakePipeline())  # type: ignore[arg-type]
    failing: list[bool] = []
    desktop.captions_failing.connect(failing.append)

    def session_thread() -> None:
        listener.caption_failed()
        listener.caption_failed()
        listener.caption_updated(finished("c1", clause("你好。")))

    thread = threading.Thread(target=session_thread)
    thread.start()
    thread.join()
    assert failing == []  # not yet
    QApplication.processEvents()
    assert failing == [True, False]
    desktop.close()


def test_the_sources_the_settings_ask_for() -> None:
    apps = [BROWSER, CHAT]
    chosen = AppSettings(whole_system=False, apps=("Web Browser",))
    assert plan_sources(chosen, apps, per_app=True).apps == (
        (20, "Web Browser", SourceCategory.BROWSER),
    )
    several = AppSettings(whole_system=False, apps=("Chat App", "Web Browser", "Gone"))
    assert plan_sources(several, apps, per_app=True).apps == (
        (30, "Chat App", SourceCategory.CALL),
        (20, "Web Browser", SourceCategory.BROWSER),
    )  # in the order picked; one not open joins when it opens
    assert plan_sources(chosen, [], per_app=True) == plan_sources(
        AppSettings(whole_system=False, apps=("Gone",)), apps, True
    )  # not open: nothing until it is
    assert not plan_sources(chosen, [], per_app=True).whole_system
    assert plan_sources(chosen, apps, per_app=False).whole_system  # Windows 10
    everything = replace(several, whole_system=True, caption_mic=True)
    plan = plan_sources(everything, apps, per_app=True)
    assert plan.whole_system and plan.mic and plan.apps == ()


class ChangingAppList:
    """Apps that open and close as a test says."""

    def __init__(self, *apps: PlayingApp) -> None:
        self.apps = list(apps)

    def playing_apps(self) -> list[PlayingApp]:
        return list(self.apps)


def sources_with(pipeline: FakePipeline, apps: AppList) -> Sources:
    return Sources(
        pipeline,  # type: ignore[arg-type]
        apps,
        True,
        lambda pid, name: FakeCapture(f"app {pid}"),
        lambda: FakeCapture("system"),
        lambda: FakeCapture("mic"),
        everything_else_capture=lambda pid: FakeCapture(f"all but {pid}"),
    )


def test_nothing_is_captured_until_the_learner_picks() -> None:
    """polyglotic-hq DECISIONS.md #25 (accepted 2026-11-05): the first run
    starts paused - nothing picked, nothing captured, on Windows 10 too.
    Before, the whole system was captured until an app was picked (#18).
    The mic follows its own switch."""
    nothing = SourcePlan((), False, False)
    assert (
        plan_sources(AppSettings(whole_system=False), [BROWSER], per_app=True)
        == nothing
    )
    assert (
        plan_sources(AppSettings(whole_system=False), [BROWSER], per_app=False)
        == nothing
    )
    assert plan_sources(AppSettings(caption_mic=True), [], True).mic
    assert not AppSettings(whole_system=False).source_chosen
    assert AppSettings().source_chosen  # a new learner's: everything (484)
    assert AppSettings(whole_system=False, apps=("Web Browser",)).source_chosen
    assert AppSettings(whole_system=True).source_chosen
    pipeline = FakePipeline()
    sources = sources_with(pipeline, FakeAppList())
    sources.follow(AppSettings(whole_system=False))
    assert pipeline.calls == []  # no capture started


def test_nothing_is_captured_while_signed_out() -> None:
    """polyglotic-hq 133: on a first run left at "Not signed in", an app
    added was captured and run through speech detection on the PC. Audio is
    taken only to serve the learner, and a signed-out app serves nothing:
    capture starts on signing in, and stops on signing out (137)."""
    pipeline = FakePipeline()
    sources = sources_with(pipeline, FakeAppList())
    sources.signed_in = False  # as `main` builds it with no device token
    value = AppSettings(whole_system=False, apps=("Web Browser",), caption_mic=True)
    sources.follow(value)
    assert pipeline.calls == []  # an app picked, the mic on: nothing captured
    sources.set_signed_in(True)
    assert pipeline.calls == [
        f"app-1:{SourceCategory.BROWSER}:app 20:False",
        "reference:system",
        f"mic:{SourceCategory.MIC}:mic:True",
    ]
    pipeline.calls.clear()
    sources.set_signed_in(False)  # signed out, or the token refused
    assert pipeline.calls == ["remove:app-1", "remove:mic", "remove reference:system"]


def test_sources_follow_the_settings_and_only_restart_on_a_change() -> None:
    pipeline = FakePipeline()
    sources = sources_with(pipeline, FakeAppList())
    value = AppSettings(whole_system=False, apps=("Web Browser",), caption_mic=True)
    sources.follow(value)
    assert pipeline.calls == [
        f"app-1:{SourceCategory.BROWSER}:app 20:False",
        "reference:system",  # the mic's bleed check needs what the PC played
        f"mic:{SourceCategory.MIC}:mic:True",
    ]
    pipeline.calls.clear()
    sources.follow(value)  # nothing changed: nothing restarted
    assert pipeline.calls == []
    sources.follow(replace(value, whole_system=True))
    assert pipeline.calls == [
        "remove:app-1",
        "remove:mic",  # its reference changes
        "remove reference:system",
        f"system:{SourceCategory.SYSTEM}:system:False",
        f"mic:{SourceCategory.MIC}:mic:True",  # the system's own buffer as reference
    ]


def test_an_app_closing_or_opening_leaves_the_other_sources_running() -> None:
    """Several apps at once (project 054): ticking, unticking, an app
    closing and opening again each start or stop only that app's source -
    the others keep their speech in progress - and an app keeps its source
    id, which is never its name."""
    pipeline = FakePipeline()
    apps = ChangingAppList(BROWSER, CHAT)
    sources = sources_with(pipeline, apps)
    value = AppSettings(
        whole_system=False, apps=("Web Browser", "Chat App"), caption_mic=True
    )
    sources.follow(value)
    assert pipeline.calls == [
        f"app-1:{SourceCategory.BROWSER}:app 20:False",
        f"app-2:{SourceCategory.CALL}:app 30:False",
        "reference:system",
        f"mic:{SourceCategory.MIC}:mic:True",
    ]
    pipeline.calls.clear()
    apps.apps = [BROWSER]  # the chat app closed
    sources.follow(value)
    assert pipeline.calls == ["remove:app-2"]
    pipeline.calls.clear()
    apps.apps = [BROWSER, replace(CHAT, process_id=31)]  # and opened again
    sources.follow(value)
    assert pipeline.calls == [f"app-2:{SourceCategory.CALL}:app 31:False"]
    pipeline.calls.clear()
    sources.follow(replace(value, apps=("Chat App",)))  # the browser unticked
    assert pipeline.calls == ["remove:app-1"]
    pipeline.calls.clear()
    sources.follow(replace(value, apps=("Chat App", "Web Browser")))
    assert pipeline.calls == [f"app-1:{SourceCategory.BROWSER}:app 20:False"]
    assert sources.ids == {"Web Browser": "app-1", "Chat App": "app-2"}
    pipeline.calls.clear()
    sources.follow(replace(value, caption_mic=False))
    assert pipeline.calls == ["remove:mic", "remove reference:system"]


def test_two_instances_of_one_app_keep_one_source_whatever_their_order() -> None:
    """Two processes of one app (two browser windows of their own, say):
    Windows lists them in no fixed order, and the app list is polled every
    few seconds. The one captured is the same each time - one playing
    before one that isn't, then the lowest process id - so the source
    isn't restarted, dropping speech in progress, when only the order
    changes (polyglotic-hq project 059, Low 6)."""
    other = replace(BROWSER, process_id=25)
    assert plan_sources(
        AppSettings(whole_system=False, apps=("Web Browser",)),
        [other, BROWSER],
        per_app=True,
    ).apps == ((20, "Web Browser", SourceCategory.BROWSER),)
    silent = replace(BROWSER, playing=False)
    assert plan_sources(
        AppSettings(whole_system=False, apps=("Web Browser",)),
        [silent, other],
        per_app=True,
    ).apps == ((25, "Web Browser", SourceCategory.BROWSER),)  # the one playing
    pipeline = FakePipeline()
    apps = ChangingAppList(other, BROWSER)
    sources = sources_with(pipeline, apps)
    value = AppSettings(whole_system=False, apps=("Web Browser",))
    sources.follow(value)
    assert pipeline.calls == [f"app-1:{SourceCategory.BROWSER}:app 20:False"]
    pipeline.calls.clear()
    apps.apps = [BROWSER, other]  # the same two, listed the other way round
    sources.follow(value)
    assert pipeline.calls == []


def test_everything_else_leaves_its_app_out_so_nothing_is_heard_twice() -> None:
    """polyglotic-hq DECISIONS.md #59 (project 139): everything else is
    captured leaving its one app out, by the app's process id; while the
    app isn't open it is the whole system's audio, and it restarts leaving
    the app out when the app opens again. The mic's bleed check still has
    what the whole PC played. The usage statistics are told the mode."""
    pipeline = FakePipeline()
    apps = ChangingAppList(CHAT)
    told: list[Capture] = []
    sources = Sources(
        pipeline,  # type: ignore[arg-type]
        apps,
        True,
        lambda pid, name: FakeCapture(f"app {pid}"),
        lambda: FakeCapture("system"),
        lambda: FakeCapture("mic"),
        on_capture=told.append,
        everything_else_capture=lambda pid: FakeCapture(f"all but {pid}"),
    )
    value = AppSettings(
        whole_system=False, apps=("Chat App",), everything_else=True, caption_mic=True
    )
    sources.follow(value)
    assert pipeline.calls == [
        f"app-1:{SourceCategory.CALL}:app 30:False",
        f"everything_else:{SourceCategory.SYSTEM}:all but 30:False",
        "reference:system",  # not everything else's: the app's is apart
        f"mic:{SourceCategory.MIC}:mic:True",
    ]
    assert told[-1] == Capture(CaptureMode.APPS_PLUS_REST, 1, my_speech=True)
    pipeline.calls.clear()
    apps.apps = []  # the app closed: everything else is everything
    sources.follow(value)
    assert pipeline.calls == [
        "remove:app-1",
        "remove:everything_else",
        f"everything_else:{SourceCategory.SYSTEM}:system:False",
    ]
    pipeline.calls.clear()
    apps.apps = [replace(CHAT, process_id=31)]  # and opened again
    sources.follow(value)
    assert pipeline.calls == [
        "remove:everything_else",
        f"app-1:{SourceCategory.CALL}:app 31:False",
        f"everything_else:{SourceCategory.SYSTEM}:all but 31:False",
    ]
    pipeline.calls.clear()
    sources.follow(replace(value, everything_else=False))  # turned off
    assert pipeline.calls == ["remove:everything_else"]
    assert told[-1] == Capture(CaptureMode.APPS, 1, my_speech=True)


def test_the_sources_that_can_hear_the_app_are_hushed_while_it_speaks() -> None:
    """A looked-up word said aloud (polyglotic-hq 286): everything the PC
    plays, everything else and the mic can hear the app, so they're added
    as hearing it - silent while it speaks; an app on its own can't."""
    pipeline = FakePipeline()
    sources = sources_with(pipeline, ChangingAppList(CHAT))
    sources.follow(
        AppSettings(
            whole_system=False,
            apps=("Chat App",),
            everything_else=True,
            caption_mic=True,
        )
    )
    assert pipeline.hear_the_app == {
        "app-1": False,
        "everything_else": True,
        "mic": True,
    }
    pipeline.hear_the_app.clear()
    sources.follow(AppSettings(whole_system=True, caption_mic=True))
    assert pipeline.hear_the_app == {"system": True, "mic": True}


def test_everything_else_is_never_beside_two_apps_or_on_windows_10() -> None:
    """Windows leaves one app out of a capture: with two apps (kept on from
    before) it isn't captured - it would hear the second app twice."""
    pipeline = FakePipeline()
    sources = sources_with(pipeline, ChangingAppList(BROWSER, CHAT))
    sources.follow(
        AppSettings(
            whole_system=False, apps=("Chat App", "Web Browser"), everything_else=True
        )
    )
    assert not any("everything_else" in call for call in pipeline.calls)
    value = AppSettings(whole_system=False, apps=("Chat App",), everything_else=True)
    assert plan_sources(value, [CHAT], per_app=False) == SourcePlan((), True, False)


def test_sources_say_which_app_each_source_is_for_its_label() -> None:
    """Each source labelled (project 054): after a change, the interface is
    told each app's source id, its name and what it's called on screen -
    its public name if it's a known app - also once it has closed."""
    shown: list[dict[SourceId, tuple[str, str]]] = []
    known = replace(CHAT, known_name="Chat")
    apps = ChangingAppList(BROWSER, known)
    pipeline = FakePipeline()
    sources = Sources(
        pipeline,  # type: ignore[arg-type]
        apps,
        True,
        lambda pid, name: FakeCapture(f"app {pid}"),
        lambda: FakeCapture("system"),
        lambda: FakeCapture("mic"),
        lambda found: shown.append(dict(found)),
        everything_else_capture=lambda pid: FakeCapture(f"all but {pid}"),
    )
    sources.follow(AppSettings(whole_system=False, apps=("Chat App", "Web Browser")))
    assert shown[-1] == {
        "app-1": ("Chat App", "Chat"),
        "app-2": ("Web Browser", "Web Browser"),
    }
    apps.apps = [BROWSER]  # closed: its captions keep their label
    sources.follow(AppSettings(whole_system=False, apps=("Chat App", "Web Browser")))
    assert shown[-1][SourceId("app-1")] == ("Chat App", "Chat")
    # the known app, as the tracking plan names it, rides with its source - for the summary
    # only (DECISIONS.md #30); an app not on the list has none
    assert [(x.id, x.known_app) for x in pipeline.sources] == [
        ("app-1", "chat"),
        ("app-2", None),
    ]


def test_quit_while_the_first_runs_sign_in_shows_ends_the_app(
    qapp: QApplication,
) -> None:
    """The tray's Quit while the first run's sign-in dialog shows (polyglotic-hq
    133): the dialog runs in the app's loop, so Quit closes it and the app
    ends - before, Qt ignored the quit and the app carried on, its tray gone."""
    desktop = DesktopApp(None, None, None)
    answers: list[int] = []

    def sign_in() -> None:
        dialog = QDialog()
        QTimer.singleShot(50, desktop.quit.trigger)  # the tray's Quit
        answers.append(dialog.exec())

    once_running(sign_in)
    assert answers == []  # not before the loop runs
    guard = QTimer(singleShot=True, interval=5000)
    guard.timeout.connect(lambda: qapp.exit(9))
    guard.start()
    assert qapp.exec() == 0
    guard.stop()
    assert answers == [0]


class KeptOpen(QWidget):
    """A window that refuses to close and stays shown."""

    def closeEvent(self, event: QCloseEvent) -> None:
        event.ignore()


def test_quit_ends_the_app_even_if_a_window_refuses_to_close(
    qapp: QApplication,
) -> None:
    """The tray's (or the main window's) Quit isn't a request a window can
    turn down. Qt 6's quit() gives up when a window refuses to close while
    another shows: on a real screen the main window, kept in the tray,
    refused, and the caption windows stayed up - the app ran on, its tray
    icon gone (polyglotic-hq 141)."""
    desktop = DesktopApp(None, None, None)
    refusing = KeptOpen()
    refusing.show()
    caption_window = QWidget(None, Qt.WindowType.Tool)
    caption_window.show()
    QTimer.singleShot(50, desktop.quit.trigger)
    guard = QTimer(singleShot=True, interval=3000)
    guard.timeout.connect(lambda: qapp.exit(9))
    guard.start()
    try:
        assert qapp.exec() == 0  # 9: Quit was ignored
    finally:
        guard.stop()
        refusing.hide()
        caption_window.hide()


def test_home_says_once_at_start_what_was_reset_or_taken_off(
    qapp: QApplication,
) -> None:
    """A settings file set aside (133) and saved languages taken off the
    list (DECISIONS.md #40, 144): one notice on Home's banner, or none."""
    assert start_notice(None, ()) == ""
    taken = start_notice(None, ("mn", "kk"))
    assert "Mongolian and Kazakh" in taken and "aren't offered any more" in taken
    both = start_notice(Path("settings.unreadable.json"), ("kk",))
    assert both.startswith("Your settings couldn't be read") and "Kazakh" in both


def test_listening_starts_again_once_a_plan_with_plus_arrives() -> None:
    """polyglotic-hq 185: stopped by 4009, then a code redeemed or Plus
    bought - the next plan says Plus, and listening starts by itself."""
    back = PlanLine(PlanWords.RENEWS, has_plus=True)
    still_ended = PlanLine(PlanWords.ENDED, get_plus=True, has_plus=False)
    assert plus_is_back(ConnectionState.PLUS_ENDED, back)
    assert not plus_is_back(ConnectionState.PLUS_ENDED, still_ended)
    assert not plus_is_back(ConnectionState.STOPPED, back)  # stopped for another reason
    assert not plus_is_back(ConnectionState.LISTENING, back)


def test_the_accounts_cohort_reaches_the_interface_from_welcome(
    qapp: QApplication,
) -> None:
    """polyglotic-hq 275: alpha testers get "Report a problem" with
    everything attached; the cohort comes with every session's `welcome`."""
    desktop = DesktopApp(MemorySettingsStore({}), None, FakeAppList())
    listener = QtListener(desktop, FakePipeline())  # type: ignore[arg-type]
    seen: list[str] = []
    listener.cohort_seen.connect(seen.append)
    thread = threading.Thread(
        target=lambda: listener.status_changed(
            Status(SessionState.LISTENING, cohort="alpha")
        )
    )
    thread.start()
    thread.join()
    QApplication.processEvents()
    assert seen == ["alpha"]
    listener.status_changed(Status(SessionState.WAITING, retry_in=1.0))
    QApplication.processEvents()
    assert seen == ["alpha"]  # only a welcome says it
    desktop.close()


@pytest.mark.parametrize("overtaken", [False, True])
def test_invalidated_display_group_refreshes_only_its_later_audio(
    qapp: QApplication, overtaken: bool
) -> None:
    desktop = DesktopApp(MemorySettingsStore({}), None, None)
    pipeline, connection = Mock(), Mock()
    listener = QtListener(desktop, None)
    feed = desktop.feed
    first = finished("a", clause("目前在。", "Currently at."))
    whole = replace(
        finished("b", clause("目前在上海。", "Currently in Shanghai.")),
        continues=first.caption_id,
    )
    audio = HeldSpeech(
        whole.caption_id, whole.source_id, SourceCategory.BROWSER, 5, 6, b"later audio"
    )
    pipeline.get.return_value = audio
    connection.recheck.return_value = True
    wire_continuation_refresh(
        feed,
        listener,
        pipeline,
        connection,
        lambda: ListeningSettings(targets=(Language("en"),)),
    )
    received: list[CaptionUpdate] = []
    feed.received.connect(received.append)
    try:
        feed.apply(first)
        feed.apply(whole)
        feed.apply(
            CaptionUpdate(first.caption_id, first.source_id, CaptionKind.WITHDRAWN)
        )
        pipeline.get.assert_called_once_with(whole.caption_id)
        request = connection.recheck.call_args.args[0]
        assert (
            request.caption_id,
            request.audio,
            request.speech_start,
            request.speech_end,
        ) == (
            whole.caption_id,
            audio.audio,
            audio.start,
            audio.end,
        )
        if overtaken:
            feed.apply(finished("b", clause("北京。", "Beijing.")))
        heard = len(received)
        listener.rechecked(
            RecheckResult(CaptionId("b"), RecheckOutcome.CHECKED, (Clause("上海。"),))
        )
        qapp.processEvents()
        assert [c.original for c in feed.history.captions] == (
            ["北京。"] if overtaken else ["上海。"]
        )
        assert len(received) == heard
    finally:
        desktop.close()
        desktop.deleteLater()
