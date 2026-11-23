"""The parts of Windows capture that need no audio device: keeping captured
audio continuous, which device to capture, app categories, and tracing a
browser's audio process to its main one. (The captures themselves were
checked by hand on Windows 11 - project 016's report.)"""

import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

import pytest

if sys.platform != "win32":
    pytest.skip("Windows only", allow_module_level=True)

from polyglotic_desktop.platform import capture_restarts
from polyglotic_desktop.platform.windows import apps, capture, system
from polyglotic_desktop.platform.windows.apps import (
    WindowsAppList,
    app_peak,
    in_tree,
    own_name,
    top_process,
)
from polyglotic_desktop.platform.windows.capture import (
    MAX_FILL_SEC,
    Timeline,
    _Capture,
    wanted_device,
)
from polyglotic_desktop.platform.windows.categories import category_of, known_name
from polyglotic_desktop.platform.windows.devices import AudioDevice, outputs_playing
from polyglotic_desktop.ports.capture import (
    AppCaptureSupport,
    PlayingApp,
    SourceCategory,
    TrialOutcome,
)

SR = 16000


def samples(seconds: float) -> bytes:
    return b"\x01\x00\x00\x00" * round(seconds * SR)


def seconds(data: bytes) -> float:
    return len(data) / 4 / SR


def test_continuous_packets_pass_through() -> None:
    timeline = Timeline()
    out = timeline.packet(10.0, samples(0.01)) + timeline.packet(10.0101, samples(0.01))
    assert [start for start, _ in out] == pytest.approx([10.0, 10.01])
    assert timeline.end == pytest.approx(10.02)


def test_a_gap_becomes_silence() -> None:
    timeline = Timeline()
    timeline.packet(10.0, samples(0.01))
    out = timeline.packet(10.51, samples(0.01))
    (gap_start, gap), (start, _) = out
    assert gap_start == pytest.approx(10.01) and seconds(gap) == pytest.approx(0.5)
    assert set(gap) == {0} and start == pytest.approx(10.51)


def test_a_long_outage_is_filled_only_partly_then_skipped() -> None:
    timeline = Timeline()
    timeline.packet(10.0, samples(0.01))
    (_, gap), (start, _) = timeline.packet(70.0, samples(0.01))
    assert seconds(gap) == pytest.approx(MAX_FILL_SEC) and start == pytest.approx(70.0)


def test_an_overlap_is_dropped_so_time_only_moves_forward() -> None:
    timeline = Timeline()
    timeline.packet(10.0, samples(0.5))
    ((start, rest),) = timeline.packet(10.3, samples(0.3))
    assert start == pytest.approx(10.5) and seconds(rest) == pytest.approx(0.1)
    assert timeline.packet(10.0, samples(0.1)) == []


def test_idle_fills_silence_up_to_shortly_before_now() -> None:
    timeline = Timeline()
    assert timeline.idle(5.0) == []  # nothing captured yet
    timeline.packet(10.0, samples(0.01))
    assert timeline.idle(10.12) == []  # within the margin
    ((start, gap),) = timeline.idle(11.0)
    assert start == pytest.approx(10.01) and seconds(gap) == pytest.approx(0.89)


def test_an_ending_source_gets_enough_silence_to_finish_its_speech() -> None:
    timeline = Timeline()
    assert timeline.ending() == []  # nothing captured: nothing to finish
    timeline.packet(10.0, samples(0.5))
    ((start, tail),) = timeline.ending()
    assert start == pytest.approx(10.5) and set(tail) == {0}
    assert seconds(tail) > 0.8  # the pause that finishes a speech segment


def test_wanted_device_follows_the_proof_of_concept() -> None:
    assert wanted_device("usb", lambda: ["usb", "jack"], lambda: "jack") == "usb"
    assert wanted_device("usb", lambda: ["jack"], lambda: "jack") == "jack"  # unplugged
    assert wanted_device(None, lambda: ["usb", "jack"], lambda: "jack") == "jack"

    def broken() -> list[str]:
        raise OSError("no audio service")

    assert wanted_device("usb", broken, lambda: "jack") is None


def test_speaker_hold_uses_the_configured_loopback_or_an_unset_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    default = AudioDevice("default", "Default speakers")
    other = AudioDevice("headphones", "Headphones")
    active = [default, other]
    monkeypatch.setattr(capture, "active_devices", lambda _flow: active)
    monkeypatch.setattr(capture, "default_device", lambda _flow: default)
    selected = capture.SystemCapture(other.id, strict_device=True)
    assert selected._target() == other.id
    active.remove(other)
    assert selected._target() is None
    assert capture.SystemCapture(strict_device=True)._target() == default.id


@pytest.mark.parametrize(
    ("exe", "path", "category"),
    [
        ("chrome.exe", None, SourceCategory.BROWSER),
        ("Discord.exe", None, SourceCategory.CALL),
        ("vlc.exe", None, SourceCategory.VIDEO),
        ("Spotify.exe", None, SourceCategory.MUSIC),
        (
            "eldenring.exe",
            r"D:\SteamLibrary\steamapps\common\ELDEN RING\eldenring.exe",
            SourceCategory.GAME,
        ),
        ("notepad.exe", r"C:\Windows\notepad.exe", SourceCategory.OTHER),
        ("unknown.exe", None, SourceCategory.OTHER),
    ],
)
def test_categories(exe: str, path: str | None, category: SourceCategory) -> None:
    assert category_of(exe, path) is category


def test_known_apps_have_their_public_name_and_no_other_app_has_one() -> None:
    """The known-apps list (polyglotic-hq DECISIONS.md #30): a listed app's
    public name; any other app - a game found by its folder included -
    has none, so its name can't leave the PC."""
    assert known_name("Discord.exe") == "Discord"
    assert known_name(r"C:\Program Files\Google\Chrome\chrome.exe") == "Google Chrome"
    assert known_name("VALORANT-Win64-Shipping.exe") == "Valorant"
    assert known_name("notepad.exe") is None
    assert known_name("MyPrivateGame.exe") is None
    assert (
        category_of(
            "MyPrivateGame.exe",
            r"D:\SteamLibrary\steamapps\common\Mine\MyPrivateGame.exe",
        )
        is SourceCategory.GAME
    )


def test_an_unknown_app_shows_its_own_name_not_its_file_name(tmp_path: Path) -> None:
    """polyglotic-hq 133: an app not on the known-apps list showed as
    "mygame.exe" in the picker and on its window. It shows what its
    executable calls itself - its description, as Task Manager does - on
    this PC only; a known app keeps its public name."""
    notepad = Path(os.environ.get("SYSTEMROOT", r"C:\Windows")) / "System32/notepad.exe"
    assert own_name(str(notepad)) == "Notepad"
    no_resource = tmp_path / "mygame.exe"
    no_resource.write_bytes(b"MZ" + bytes(64))
    assert own_name(str(no_resource)) is None
    assert own_name(str(tmp_path / "gone.exe")) is None and own_name(None) is None

    unknown = PlayingApp(1, "mygame.exe", True, SourceCategory.GAME, None, "My Game")
    assert unknown.title == "My Game"
    known = PlayingApp(2, "Discord.exe", True, SourceCategory.CALL, "Discord", "Disc")
    assert known.title == "Discord"
    silent = PlayingApp(3, "tool.exe", True, SourceCategory.OTHER)
    assert silent.title == "tool.exe"  # it says nothing of itself


def test_top_process_climbs_only_through_the_same_executable() -> None:
    processes = {
        1: (0, "explorer.exe"),
        10: (1, "chrome.exe"),
        11: (10, "chrome.exe"),
        12: (11, "chrome.exe"),
        20: (1, "discord.exe"),
    }
    assert top_process(12, processes) == 10
    assert top_process(20, processes) == 20
    assert top_process(99, processes) == 99  # exited


def test_top_process_survives_a_loop_of_reused_ids() -> None:
    assert top_process(5, {5: (6, "a.exe"), 6: (5, "a.exe")}) in (5, 6)


def test_polyglotic_never_lists_itself_or_another_copy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """368: its own sample or a word's sound made it "Polyglotic - playing"
    under Add an app, as did a preview install beside it. Neither is an app
    to caption: this copy (from source, Python and its child) and any
    packed copy (Polyglotic.exe) are left out; another Python app isn't."""
    processes = {
        1: (0, "explorer.exe"),
        10: (1, "python.exe"),  # this copy, from source
        11: (10, "python.exe"),  # its child, whose session plays the sample
        20: (1, "Polyglotic.exe"),  # a preview install
        30: (1, "vlc.exe"),
        40: (1, "python.exe"),  # someone else's Python app
    }
    sessions = [(11, True), (20, True), (30, True), (40, False)]
    monkeypatch.setattr(apps, "_processes", lambda: processes)
    monkeypatch.setattr(
        apps, "active_devices", lambda flow: [AudioDevice("out", "Speakers")]
    )
    monkeypatch.setattr(apps, "_sessions", lambda device_id: sessions)
    monkeypatch.setattr(apps, "_path", lambda pid: None)
    monkeypatch.setattr(os, "getpid", lambda: 11)
    found = WindowsAppList().playing_apps()
    assert [(a.process_id, a.name) for a in found] == [
        (30, "vlc.exe"),
        (40, "python.exe"),
    ]


class _FakeStream:
    """Stands in for `_Stream`: one packet of audio each time it's asked."""

    def __init__(self) -> None:
        self.closed = False
        self._at = 10.0

    def wait(self) -> bool:
        time.sleep(0.01)
        return True

    def packets(self) -> list[tuple[float, bytes]]:
        self._at += 0.01
        return [(self._at, samples(0.01))]

    def close(self) -> None:
        self.closed = True


class _FakeCapture(_Capture):
    def __init__(self) -> None:
        super().__init__()
        self.stream = _FakeStream()

    def _target(self) -> str | None:
        return "fake"

    def _open(self, target: str) -> tuple[Any, str]:
        return self.stream, "A fake device"


def test_a_failing_audio_callback_ends_the_capture_and_says_so() -> None:
    capture = _FakeCapture()

    def on_audio(start: float, audio: bytes) -> None:
        raise ValueError("the pipeline is broken")

    capture.start(on_audio)
    deadline = time.monotonic() + 3
    while capture.capturing != "A fake device" and time.monotonic() < deadline:
        time.sleep(0.01)
    while capture.capturing is not None and time.monotonic() < deadline:
        time.sleep(0.01)
    try:
        assert capture.capturing is None  # not "A fake device" with nothing arriving
        assert capture.error is not None
        assert capture.stream.closed
        assert "pipeline" not in capture.error  # the exception itself isn't quoted
    finally:
        capture.stop()


# The known apps polyglotic-server's tracking plan lists for
# `listening_session_ended.known_app` (docs/tracking-plan.yaml): exactly
# these. An app goes there first - a server that doesn't list it drops the
# whole summary - and the server is deployed before the app.
TRACKING_PLAN_KNOWN_APPS = frozenset(
    {
        "aimp", "apex-legends", "apple-music", "arc", "brave", "chromium",
        "counter-strike-2", "deezer", "discord", "dota-2", "elden-ring",
        "final-fantasy-xiv", "firefox", "foobar2000", "fortnite", "genshin-impact",
        "google-chrome", "grand-theft-auto-v", "honkai-star-rail",
        "internet-explorer", "itunes", "kakaotalk", "kodi", "kugou",
        "league-of-legends", "librewolf", "line", "media-player", "microsoft-edge",
        "microsoft-teams", "minecraft", "movies-tv", "mpc-be", "mpc-hc", "mpv",
        "mumble", "musicbee", "netease-cloud-music", "opera", "overwatch-2", "plex",
        "potplayer", "pubg-battlegrounds", "qq", "qq-music", "roblox",
        "rocket-league", "signal", "skype", "slack", "spotify", "steam", "teamspeak",
        "teamspeak-3", "telegram", "tidal", "valorant", "viber", "vivaldi", "vlc",
        "waterfox", "webex", "wechat", "whatsapp", "windows-media-player",
        "world-of-warcraft", "zen-browser", "zoom",
    }
)  # fmt: skip


def test_everything_else_asks_windows_to_leave_the_apps_tree_out() -> None:
    """Process loopback's two modes (Windows' `PROCESS_LOOPBACK_MODE`): an
    app's capture includes its process tree (0); everything else excludes
    it (1) - so the two together hear everything once (polyglotic-hq
    project 139 checked it on build 26200 with the test player)."""
    from polyglotic_desktop.platform.windows.capture import loopback_params

    app = loopback_params(4242)
    rest = loopback_params(4242, leave_out=True)
    assert (app.ActivationType, app.TargetProcessId, app.ProcessLoopbackMode) == (
        1,
        4242,
        0,
    )
    assert (rest.TargetProcessId, rest.ProcessLoopbackMode) == (4242, 1)


# -- one app alone where Windows doesn't promise it (285, decision 0076) -------------


@pytest.mark.parametrize(
    ("build", "support"),
    [
        (26200, AppCaptureSupport.YES),  # this PC: Windows 11 25H2
        (22000, AppCaptureSupport.YES),  # Windows 11's first
        (20348, AppCaptureSupport.YES),  # Microsoft's documented minimum
        (20347, AppCaptureSupport.TRY),
        (19045, AppCaptureSupport.TRY),  # Windows 10 22H2, its last
        (19041, AppCaptureSupport.TRY),  # Windows 10 2004, OBS's minimum
        (19040, AppCaptureSupport.NO),
        (18363, AppCaptureSupport.NO),  # Windows 10 1909
    ],
)
def test_one_app_alone_is_promised_tried_or_not_by_build(
    build: int, support: AppCaptureSupport
) -> None:
    assert capture.app_capture_support(build) is support


def test_this_pc_is_as_before() -> None:
    """CI's two Windows PCs: the user's (Windows 11, build 26200) is promised
    one app's capture, so no trial is ever made there; the second PC's
    (Windows 10 22H2, build 19045; polyglotic-hq 504, decision 0232) tries
    it. A build older than the trial's means a new machine: say which."""
    build = sys.getwindowsversion().build
    if build >= 22000:
        assert capture.app_capture_support() is AppCaptureSupport.YES
    else:
        assert build >= capture.APP_CAPTURE_TRY_BUILD, f"build {build}: a new machine"
        assert capture.app_capture_support() is AppCaptureSupport.TRY


def test_a_refusal_is_windows_code_never_the_errors_text() -> None:
    refused = OSError(None, "Couldn't capture My Secret Game", None, -2004287480)
    assert capture.refusal(refused) == TrialOutcome(False, "refused 0x88890008")
    timed_out = OSError("Windows didn't finish starting My Secret Game's capture")
    assert capture.refusal(timed_out) == TrialOutcome(False, "no answer")


def test_the_trials_first_outcome_stands() -> None:
    trial = capture.Trial()
    assert trial.outcome is None
    trial.tell(TrialOutcome(False, "silent"))
    trial.tell(TrialOutcome(True))
    assert trial.outcome == TrialOutcome(False, "silent")


class _Packets:
    """Stands in for a started `_Stream`: packets of `sound` or of silence
    (zeros), or none at all."""

    def __init__(self, sound: bool, packets: bool = True) -> None:
        self.sound, self.give, self.closed = sound, packets, False
        self._at = 10.0

    def wait(self) -> bool:
        time.sleep(0.005)
        return self.give

    def packets(self) -> list[tuple[float, bytes]]:
        if not self.give:
            return []
        self._at += 0.01
        return [(self._at, samples(0.01) if self.sound else bytes(640))]

    def close(self) -> None:
        self.closed = True


def _app_capture(
    monkeypatch: pytest.MonkeyPatch,
    stream: _Packets | OSError,
    trial: capture.Trial | None,
    peak: float,
) -> tuple[capture.AppCapture, list[int]]:
    """An app's capture (of this test's own process, so it isn't gone) with
    Windows stood in for: the activation, the stream and the meter."""
    monkeypatch.setattr(capture, "DEVICE_POLL_SEC", 0.01)
    monkeypatch.setattr(capture, "SILENT_AFTER_SEC", 0.1)

    def activate(process_id: int, leave_out: bool = False) -> object:
        if isinstance(stream, OSError):
            raise stream
        return object()

    monkeypatch.setattr(capture, "_activate_process_loopback", activate)
    monkeypatch.setattr(capture, "_Stream", lambda client, loopback: stream)
    asked: list[int] = []

    def meter(process_id: int) -> float:
        asked.append(process_id)
        return peak

    return capture.AppCapture(os.getpid(), "My Game", trial, meter), asked


def _run(app: capture.AppCapture, until: Any, seconds: float = 2.0) -> list[bytes]:
    got: list[bytes] = []
    app.start(lambda start, audio: got.append(audio))
    deadline = time.monotonic() + seconds
    try:
        while not until() and time.monotonic() < deadline:
            time.sleep(0.01)
    finally:
        app.stop()
    return got


def test_sound_through_an_apps_capture_is_it_working(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trial = capture.Trial()
    app, _ = _app_capture(monkeypatch, _Packets(sound=True), trial, peak=0.5)
    _run(app, lambda: trial.outcome is not None)
    assert trial.outcome == TrialOutcome(True)


def test_windows_refusing_an_apps_capture_is_told_by_its_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trial = capture.Trial()
    refused = OSError(None, "Couldn't capture the app: 0x80070005", None, -2147024891)
    app, _ = _app_capture(monkeypatch, refused, trial, peak=0.5)
    _run(app, lambda: trial.outcome is not None)
    assert trial.outcome == TrialOutcome(False, "refused 0x80070005")
    assert app.capturing is None and app.error is not None


@pytest.mark.parametrize("packets", [True, False], ids=["zeros", "nothing"])
def test_silence_while_windows_hears_the_app_play_is_it_failing(
    monkeypatch: pytest.MonkeyPatch, packets: bool
) -> None:
    """Silence from the capture - zeros, or no packets at all - while
    Windows' meter of the app's sessions says it plays (HEARD_PEAK and
    over) for SILENT_AFTER_SEC: not working here."""
    trial = capture.Trial()
    stream = _Packets(sound=False, packets=packets)
    app, asked = _app_capture(monkeypatch, stream, trial, peak=0.5)
    _run(app, lambda: trial.outcome is not None)
    assert trial.outcome == TrialOutcome(False, "silent")
    assert set(asked) == {os.getpid()}


def test_silence_while_the_app_is_quiet_tells_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The app keeps a stream open and plays nothing (its meter under
    HEARD_PEAK): silence is right, so the trial goes on."""
    trial = capture.Trial()
    quiet = capture.HEARD_PEAK / 2
    app, asked = _app_capture(monkeypatch, _Packets(sound=False), trial, peak=quiet)
    _run(app, lambda: len(asked) > 30)
    assert len(asked) > 30 and trial.outcome is None


def test_without_a_trial_an_apps_capture_is_as_before(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Windows 11: no trial - the meter is never read, and the audio
    delivered is the same, silence or sound."""
    for sound in (False, True):
        app, asked = _app_capture(monkeypatch, _Packets(sound=sound), None, peak=0.5)
        got = _run(app, lambda: False, seconds=0.3)
        assert got and asked == []
        assert any(any(audio) for audio in got) is sound


def _said(caplog: pytest.LogCaptureFixture) -> str:
    """What the captures logged, as the log file has it - messages only."""
    return "\n".join(r.getMessage() for r in caplog.records)


def test_a_capture_whose_callback_fails_starts_again_and_says_so(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """polyglotic-hq 557 (529's B1): an error nobody foresaw on the capture's
    thread - in the speech detection its callback runs, say - ended the
    thread for good, with nothing in the log and `error` read by nobody.
    Now it's logged by the capture's kind and the error's type (never its
    text), and the capture starts again after `Backoff`'s wait."""
    monkeypatch.setattr(capture_restarts, "FIRST_SEC", 0.05)
    app, _ = _app_capture(monkeypatch, _Packets(sound=True), None, peak=0.5)
    got: list[bytes] = []
    while_down: list[tuple[str | None, str | None]] = []

    def on_audio(start: float, audio: bytes) -> None:
        got.append(audio)
        if len(got) == 3:
            while_down.append((app.capturing, app.error))
            raise RuntimeError("a caption's text")

    caplog.set_level(logging.INFO, logger=capture.__name__)
    app.start(on_audio)
    try:
        deadline = time.monotonic() + 3
        while len(got) < 30 and time.monotonic() < deadline:
            time.sleep(0.01)
    finally:
        app.stop()
    assert len(got) >= 30, "the capture never started again"
    assert app.error is None and app.restarts == 1  # counted for the summary (566)
    said = _said(caplog)
    assert "app capture stopped (RuntimeError); starting again in 0s" in said
    assert said.count("app capture open") == 2
    assert "caption" not in said and "My Game" not in said


def test_an_apps_capture_that_failed_to_open_is_tried_again(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """529's B1: a failed open was never tried again for that app (its
    target is always its name). Now it is, after `Backoff`'s wait, and each
    failure is logged by Windows' code - never the app's name."""
    monkeypatch.setattr(capture_restarts, "FIRST_SEC", 0.02)
    app, _ = _app_capture(monkeypatch, _Packets(sound=True), None, peak=0.5)
    tries: list[int] = []

    def activate(process_id: int, leave_out: bool = False) -> object:
        tries.append(process_id)
        if len(tries) < 3:
            raise OSError(None, "Couldn't capture My Game", None, -2004287480)
        return object()

    monkeypatch.setattr(capture, "_activate_process_loopback", activate)
    caplog.set_level(logging.INFO, logger=capture.__name__)
    named: list[str | None] = []

    def opened() -> bool:
        named.append(app.capturing)
        return app.capturing is not None

    _run(app, opened)
    assert len(tries) == 3 and named[-1] == "My Game" and app.error is None
    assert app.restarts == 2  # each failed open, for the summary (566)
    said = _said(caplog)
    assert said.count("app capture couldn't open (OSError 0x88890008)") == 2
    assert "app capture open after 2 failed tries" in said
    assert "My Game" not in said


class _Failing(_Packets):
    """A stream that fails as soon as it's read: the device went away."""

    def packets(self) -> list[tuple[float, bytes]]:
        raise OSError(None, "the device went away", None, -2004287480)


def test_a_stream_that_keeps_failing_is_reopened_after_a_wait_not_at_once(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """557: a stream lost mid-way was reopened at once, every time - one that
    fails as it opens spun, and with its line in the log would have filled
    it. It waits `Backoff`'s time between reopenings."""
    monkeypatch.setattr(capture_restarts, "FIRST_SEC", 0.2)
    app, _ = _app_capture(monkeypatch, _Failing(sound=True), None, peak=0.5)
    opens: list[int] = []
    activate = capture._activate_process_loopback

    def counted(process_id: int, leave_out: bool = False) -> object:
        opens.append(process_id)
        return activate(process_id, leave_out)

    monkeypatch.setattr(capture, "_activate_process_loopback", counted)
    caplog.set_level(logging.INFO, logger=capture.__name__)
    _run(app, lambda: False, seconds=0.5)
    assert 2 <= len(opens) <= 3  # at 0, 0.2 and 0.6 s - not hundreds
    assert app.restarts >= len(opens) - 1  # each loss, for the summary (566)
    assert "app capture lost its stream (OSError 0x88890008); reopening in 0s" in (
        _said(caplog)
    )


def test_everything_else_tells_the_trial_only_of_a_refusal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trial = capture.Trial()

    def refuse(process_id: int, leave_out: bool = False) -> object:
        assert leave_out  # everything but the app
        raise OSError(None, "Couldn't capture", None, -2004287480)

    monkeypatch.setattr(capture, "_activate_process_loopback", refuse)
    rest = capture.EverythingElseCapture(os.getpid(), trial)
    rest.start(lambda start, audio: None)
    deadline = time.monotonic() + 2
    while trial.outcome is None and time.monotonic() < deadline:
        time.sleep(0.01)
    rest.stop()
    assert trial.outcome == TrialOutcome(False, "refused 0x88890008")


def test_in_tree_follows_parents_to_the_app() -> None:
    processes = {
        1: (0, "explorer.exe"),
        10: (1, "game.exe"),
        11: (10, "game.exe"),
        12: (11, "voice.exe"),  # a child of another name: still the tree
        20: (1, "chat.exe"),
    }
    assert in_tree(10, 10, processes) and in_tree(12, 10, processes)
    assert not in_tree(20, 10, processes) and not in_tree(1, 10, processes)
    assert not in_tree(99, 10, processes)  # exited
    assert not in_tree(5, 10, {5: (6, "a.exe"), 6: (5, "a.exe")})  # a loop


def test_an_apps_peak_is_a_number_and_never_fails() -> None:
    """Windows' meters, read for real: this test's own process plays
    nothing, so 0 - whatever the PC's devices."""
    assert app_peak(os.getpid()) == 0.0


def test_how_many_outputs_play_is_a_count_and_never_fails() -> None:
    """Windows' meters, read for real (polyglotic-hq 290): a count of the
    outputs playing - a number, whatever the PC plays - or None."""
    count = outputs_playing()
    assert count is None or 0 <= count <= 64


def test_windows_build_and_update() -> None:
    found = system.windows_build()
    build, _, update = found.partition(".")
    assert int(build) == sys.getwindowsversion().build
    assert update == "" or update.isdigit()


def test_every_known_name_is_one_the_tracking_plan_lists() -> None:
    from polyglotic_desktop.core.listening.sources import known_app_id
    from polyglotic_desktop.platform.windows.categories import known_names

    assert {known_app_id(n) for n in known_names()} == TRACKING_PLAN_KNOWN_APPS
    assert len(known_names()) == len(TRACKING_PLAN_KNOWN_APPS)  # no two alike
    assert known_app_id("Honkai: Star Rail") == "honkai-star-rail"
