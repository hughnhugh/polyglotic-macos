"""The parts of Mac capture that need no Mac (polyglotic-hq 411): Core Audio's
pieces mixed to mono, resampled to 16kHz and stamped; telling a permission
not given from a quiet source; grouping an app's helper processes; the
known apps by bundle ID; the devices; and the capture threads, run against
stand-in taps and mics. What only a Mac proves - catap's taps and PortAudio
on real Core Audio - is in 411's report, for 410's macOS job."""

import sys
import threading
import time
from collections.abc import Callable
from typing import Any

import numpy as np
import pytest

from polyglotic_desktop.core.listening.sources import known_app_id
from polyglotic_desktop.platform.macos import apps, capture, categories, devices
from polyglotic_desktop.platform.macos.apps import AudioProcess
from polyglotic_desktop.platform.macos.capture import (
    AppCapture,
    EverythingElseCapture,
    Format,
    MicCapture,
    Permission,
    Resampler,
    SilenceWatch,
    Stamper,
    Stream,
    SystemCapture,
    TapTarget,
    mono_float,
    taps_supported,
)
from polyglotic_desktop.platform.windows import categories as windows_categories
from polyglotic_desktop.ports.capture import NOT_ALLOWED, SourceCategory

SR = 16000


def tone(hz: float, rate: float, seconds: float, level: float = 0.5) -> np.ndarray:
    t = np.arange(round(rate * seconds)) / rate
    return (level * np.sin(2 * np.pi * hz * t)).astype(np.float32)


# -- formats ------------------------------------------------------------------


def test_stereo_float_is_mixed_to_mono() -> None:
    stereo = np.array([[0.5, 0.1], [-0.2, -0.4]], dtype="<f4")
    out = mono_float(stereo.tobytes(), Format(48000, 2))
    assert out.dtype == np.float32
    assert out.tolist() == pytest.approx([0.3, -0.3])


def test_integer_samples_are_scaled_to_one() -> None:
    data = np.array([16384, -32768], dtype="<i2").tobytes()
    out = mono_float(data, Format(44100, 1, is_float=False, bits=16))
    assert out.tolist() == pytest.approx([0.5, -1.0])


def test_packed_24_bit_samples_are_read() -> None:
    half = (2**22).to_bytes(3, "little", signed=True)  # 0.5 of full scale
    low = (-(2**23)).to_bytes(3, "little", signed=True)  # -1.0
    out = mono_float(half + low, Format(48000, 1, is_float=False, bits=24))
    assert out.tolist() == pytest.approx([0.5, -1.0])


def test_a_partial_frame_is_dropped() -> None:
    data = np.array([0.1, 0.2, 0.3], dtype="<f4").tobytes()
    assert len(mono_float(data, Format(48000, 2))) == 1


# -- resampling ---------------------------------------------------------------


def _in_pieces(resampler: Resampler, audio: np.ndarray, sizes: list[int]) -> np.ndarray:
    out, at, i = [], 0, 0
    while at < len(audio):
        size = sizes[i % len(sizes)]
        out.append(resampler(audio[at : at + size]))
        at, i = at + size, i + 1
    return np.concatenate(out)


@pytest.mark.parametrize("rate", [48000, 44100, 96000, 24000])
def test_resampled_speech_band_keeps_its_shape_and_length(rate: int) -> None:
    """A 1kHz tone at the device's rate comes out a 1kHz tone at 16kHz, one
    second long, whatever the pieces' sizes (Core Audio's vary)."""
    audio = tone(1000, rate, 1.0)
    out = _in_pieces(Resampler(rate), audio, [512, 471, 1024, 7])
    assert abs(len(out) - SR) <= 1
    delay = (capture.FILTER_TAPS - 1) // 2 / rate  # the filter's, in seconds
    times = np.arange(len(out)) / SR - delay
    expected = 0.5 * np.sin(2 * np.pi * 1000 * times)
    middle = slice(200, len(out) - 200)
    assert np.max(np.abs(out[middle] - expected[middle])) < 0.03


def test_pieces_give_the_same_audio_as_one_piece() -> None:
    audio = tone(440, 48000, 0.5) + tone(3000, 48000, 0.5, 0.2)
    whole = Resampler(48000)(audio)
    pieced = _in_pieces(Resampler(48000), audio, [480, 333, 1, 2048])
    assert len(pieced) == len(whole)
    assert np.allclose(pieced, whole, atol=1e-6)


def test_sound_above_8khz_does_not_fold_back_into_speech() -> None:
    """Read at 16kHz with no filter, a 12kHz tone would come back as a 4kHz
    one at full strength: the low-pass keeps it out."""
    out = Resampler(48000)(tone(12000, 48000, 1.0))
    rms = float(np.sqrt(np.mean(out[200:] ** 2)))
    assert rms < 0.01  # the tone's own is 0.35


def test_16khz_passes_through() -> None:
    audio = tone(300, SR, 0.1)
    assert np.array_equal(Resampler(SR)(audio), audio)


# -- stamps -------------------------------------------------------------------


def test_stamps_count_on_through_jittery_arrivals() -> None:
    stamp = Stamper()
    first = stamp(10.010, 0.010)
    second = stamp(10.035, 0.010)  # arrived 15ms late
    third = stamp(10.028, 0.010)
    assert first == pytest.approx(10.0)
    assert second == pytest.approx(10.01) and third == pytest.approx(10.02)


def test_stamps_start_again_after_a_stall() -> None:
    stamp = Stamper()
    stamp(10.01, 0.01)
    assert stamp(11.0, 0.01) == pytest.approx(10.99)  # 1s lost: from its arrival


# -- a permission not given ---------------------------------------------------


def test_only_zeros_while_something_plays_is_not_allowed() -> None:
    watch = SilenceWatch(Permission(), after=3.0)
    for _ in range(2):
        watch.heard(np.zeros(160, np.float32))
        assert not watch.checked(1.0, playing=True)
    watch.heard(np.zeros(160, np.float32))
    assert watch.checked(1.0, playing=True)


def test_only_zeros_while_nothing_plays_is_just_quiet() -> None:
    watch = SilenceWatch(Permission(), after=3.0)
    for _ in range(10):
        watch.heard(np.zeros(160, np.float32))
        assert not watch.checked(1.0, playing=False)


def test_sound_once_heard_proves_the_permission_for_every_capture() -> None:
    permission = Permission()
    heard, later = SilenceWatch(permission, after=1.0), SilenceWatch(permission, 1.0)
    heard.heard(np.array([0.0, 0.01], np.float32))
    assert permission.given
    assert not later.checked(5.0, playing=True)  # its own zeros: just quiet


def test_sound_after_being_judged_not_allowed_clears_it() -> None:
    watch = SilenceWatch(Permission(), after=1.0)
    assert watch.checked(1.0, playing=True)
    watch.heard(np.array([0.2], np.float32))
    assert not watch.not_allowed and not watch.checked(1.0, playing=True)


@pytest.mark.parametrize(
    ("version", "supported"),
    [("14.2", True), ("14.2.1", True), ("15.0", True), ("26.7.2", True),
     ("14.1.2", False), ("13.6", False), ("", False), ("x", False)],
)  # fmt: skip
def test_taps_need_macos_14_2(version: str, supported: bool) -> None:
    assert taps_supported(version) is supported


# -- the apps playing -----------------------------------------------------------

CHROME = "/Applications/Google Chrome.app"
HELPER = (
    CHROME + "/Contents/Frameworks/Google Chrome Framework.framework/Versions/131/"
    "Helpers/Google Chrome Helper.app/Contents/MacOS/Google Chrome Helper"
)
BUNDLES = {
    CHROME: ("com.google.Chrome", "Google Chrome"),
    "/Applications/Discord.app": ("com.hnc.Discord", "Discord"),
    "/Applications/Polyglotic.app": ("app.polyglotic", "Polyglotic"),
    "/Users/me/Applications/My Game.app": ("com.example.mygame", "My Game"),
    "/System/Library/CoreServices/ControlCenter.app": (
        "com.apple.controlcenter",
        "Control Center",
    ),
}


def info(app: str) -> tuple[str | None, str | None]:
    return BUNDLES.get(app, (None, None))


@pytest.fixture(autouse=True)
def bundles(monkeypatch: pytest.MonkeyPatch) -> None:
    """The apps' Info.plists, as `info` has them: no Mac here."""
    monkeypatch.setattr(apps, "bundle_info", info)


def proc(
    object_id: int,
    pid: int,
    bundle_id: str | None,
    path: str | None,
    playing: bool = False,
    name: str = "Something",
) -> AudioProcess:
    return AudioProcess(object_id, pid, bundle_id, name, playing, path)


def test_outer_app_is_the_bundle_a_helper_lives_in() -> None:
    assert apps.outer_app(HELPER) == CHROME
    assert apps.outer_app("/usr/bin/afplay") is None
    assert apps.outer_app(None) is None


def test_a_helper_belongs_to_its_app() -> None:
    helper = proc(2, 202, "com.google.Chrome.helper", HELPER)
    assert apps.app_key(helper, info) == "com.google.Chrome"


def test_webkits_media_process_is_safaris() -> None:
    gpu = proc(3, 303, "com.apple.WebKit.GPU", "/System/Library/.../WebKit.GPU")
    assert apps.app_key(gpu, info) == "com.apple.Safari"


def test_a_tool_with_no_bundle_is_known_by_its_executable() -> None:
    assert apps.app_key(proc(4, 404, None, "/usr/bin/afplay"), info) == "afplay"
    assert apps.app_key(proc(4, 404, None, None, name="afplay"), info) == "afplay"


def _found(this_pid: int = 999) -> list[AudioProcess]:
    return [
        proc(1, 100, "com.google.Chrome", CHROME + "/Contents/MacOS/Google Chrome"),
        proc(2, 202, "com.google.Chrome.helper", HELPER, playing=True),
        proc(5, 500, "com.hnc.Discord", "/Applications/Discord.app/Contents/MacOS/Discord"),
        proc(6, 600, "com.apple.controlcenter",
             "/System/Library/CoreServices/ControlCenter.app/Contents/MacOS/ControlCenter"),
        proc(7, 700, "app.polyglotic",
             "/Applications/Polyglotic.app/Contents/MacOS/Polyglotic", playing=True),
        proc(8, this_pid, "org.python.python", "/usr/local/bin/python3.12", playing=True),
        proc(9, 900, "com.example.mygame",
             "/Users/me/Applications/My Game.app/Contents/MacOS/game", playing=True),
    ]  # fmt: skip


def test_the_apps_playing_are_one_entry_per_app() -> None:
    found = apps.playing_apps(_found(), this=999, info=info)
    assert [(a.name, a.process_id, a.playing) for a in found] == [
        ("com.google.Chrome", 100, True),  # its helper plays
        ("com.example.mygame", 900, True),
        ("com.hnc.Discord", 500, False),  # installed, quiet: listed
    ]
    chrome, game, discord = found
    assert (chrome.title, chrome.category, chrome.known_name) == (
        "Google Chrome",
        SourceCategory.BROWSER,
        "Google Chrome",
    )
    assert (game.title, game.known_name, game.category) == (
        "My Game",  # its bundle's own name, for the learner's eyes only
        None,
        SourceCategory.OTHER,
    )
    assert discord.category is SourceCategory.CALL


def test_polyglotic_and_macos_own_quiet_helpers_are_never_listed() -> None:
    names = {a.name for a in apps.playing_apps(_found(), this=999, info=info)}
    assert "app.polyglotic" not in names  # another copy, by its executable
    assert "org.python.python" not in names  # this process, from source
    assert "com.apple.controlcenter" not in names  # macOS' own, quiet


def test_one_look_at_core_audio_serves_every_capture_for_a_moment() -> None:
    reads: list[int] = []

    def read() -> list[AudioProcess]:
        reads.append(1)
        return []

    snapshot = apps._Snapshot(read)
    snapshot(), snapshot(), snapshot()
    assert len(reads) == 1


@pytest.mark.skipif(sys.platform == "win32", reason="os.kill ends a process on Windows")
def test_a_process_that_ended_is_not_alive() -> None:
    import os

    assert apps.alive(os.getpid())
    assert not apps.alive(2**22 + 12345)  # no such process


# -- known apps -----------------------------------------------------------------


def test_every_public_name_is_one_windows_list_and_the_tracking_plan_have() -> None:
    """A Mac app's public name may leave the Mac only if the tracking plan
    lists it (DECISIONS.md #30): Windows' list is tied to the plan by its
    own test, so the Mac's must be a part of Windows'."""
    windows = {known_app_id(n) for n in windows_categories.known_names()}
    assert {known_app_id(n) for n in categories.known_names()} <= windows


def test_mac_only_apps_have_a_category_but_no_public_name() -> None:
    assert categories.category_of("com.apple.Safari") is SourceCategory.BROWSER
    assert categories.known_name("com.apple.Safari") is None
    assert categories.shown_name("com.apple.Safari") == "Safari"
    assert categories.known_name("com.hnc.Discord") == "Discord"
    assert categories.known_name("com.example.private") is None


def test_games_are_told_by_their_folder() -> None:
    path = "/Users/me/Library/Application Support/Steam/steamapps/common/X/x.app"
    assert categories.category_of("com.example.x", path) is SourceCategory.GAME
    assert categories.category_of(None, "/usr/bin/afplay") is SourceCategory.OTHER


def test_the_common_apps_are_known_apps() -> None:
    for app in categories.COMMON_APPS:
        assert categories.category_of(app.name) is not SourceCategory.OTHER


# -- devices --------------------------------------------------------------------

AIRPODS = devices.AudioDevice("airpods", "AirPods Pro", True, True, False, True)
SPEAKERS = devices.AudioDevice("builtin-out", "MacBook Speakers", True, False, True)
BLACKHOLE = devices.AudioDevice("bh", "BlackHole 2ch", True, True)


def test_speakers_and_mics_are_listed_with_the_defaults() -> None:
    found = devices.listed([SPEAKERS, AIRPODS, BLACKHOLE])
    assert [d.name for d in found.speakers] == [
        "AirPods Pro",
        "BlackHole 2ch",
        "MacBook Speakers",
    ]
    assert [d.id for d in found.mics] == ["airpods", "bh"]
    assert (found.default_speaker, found.default_mic) == ("builtin-out", "airpods")


def test_portaudio_finds_a_mic_by_its_name() -> None:
    portaudio = [("MacBook Speakers", 0), ("AirPods Pro", 1), ("BlackHole 2ch", 2)]
    listed = [SPEAKERS, AIRPODS, BLACKHOLE]
    assert devices.portaudio_index("airpods", listed, portaudio) == 1
    assert devices.portaudio_index(None, listed, portaudio) is None
    assert devices.portaudio_index("gone", listed, portaudio) is None
    twice = [("AirPods Pro", 1), ("AirPods Pro", 1)]
    assert devices.portaudio_index("airpods", listed, twice) is None  # default


# -- the capture threads, against stand-ins --------------------------------------


ALIVE = lambda pid: True


class FakeStream(Stream):
    """A tap or mic delivering 10ms pieces at 48kHz as fast as asked."""

    def __init__(self, sound: bool = True) -> None:
        super().__init__()
        self.sound = sound
        self.closed = False
        self._at = time.perf_counter()

    def pieces(self, wait: float) -> list[capture.Piece]:
        time.sleep(0.005)
        audio = tone(500, 48000, 0.01) if self.sound else np.zeros(480, np.float32)
        self._at += 0.01
        return [(self._at, audio.tobytes(), Format(48000, 1))]

    def close(self) -> None:
        self.closed = True


@pytest.fixture(autouse=True)
def quick(monkeypatch: pytest.MonkeyPatch) -> None:
    """Checks every 20ms, judged not allowed after 100ms, and permissions
    unknown in each test."""
    monkeypatch.setattr(capture, "DEVICE_POLL_SEC", 0.02)
    monkeypatch.setattr(capture, "NOT_ALLOWED_AFTER_SEC", 0.1)
    monkeypatch.setattr(capture.AppCapture, "_permission", Permission())
    monkeypatch.setattr(capture._GlobalCapture, "_permission", Permission())
    monkeypatch.setattr(capture.MicCapture, "_permission", Permission())


def opening(opened: list[Any]) -> Callable[[TapTarget], Stream]:
    """Opens a stand-in tap, keeping what it was asked for in `opened`."""

    def open_tap(target: TapTarget) -> Stream:
        opened.append(target)
        return FakeStream()

    return open_tap


class Heard:
    def __init__(self) -> None:
        self.pieces: list[tuple[float, bytes]] = []
        self.lock = threading.Lock()

    def __call__(self, start: float, samples: bytes) -> None:
        with self.lock:
            self.pieces.append((start, samples))

    def seconds(self) -> float:
        with self.lock:
            return sum(len(s) for _, s in self.pieces) / 4 / SR


def wait_for(condition: Callable[[], bool], seconds: float = 3.0) -> None:
    end = time.monotonic() + seconds
    while not condition():
        assert time.monotonic() < end, "timed out"
        time.sleep(0.01)


def test_an_apps_capture_taps_all_its_processes_and_delivers_16khz() -> None:
    found = _found()
    opened: list[Any] = []

    def open_tap(target: TapTarget) -> Stream:
        opened.append(target)
        return FakeStream()

    cap = AppCapture(
        100,
        "com.google.Chrome",
        processes=lambda: found,
        open_tap=open_tap,
        alive=ALIVE,
    )
    heard = Heard()
    cap.start(heard)
    try:
        wait_for(lambda: heard.seconds() > 0.1)
        assert cap.capturing == "com.google.Chrome" and cap.error is None
    finally:
        cap.stop()
    assert opened[0] == TapTarget(frozenset({1, 2}), leave_out=False)
    starts = [start for start, _ in heard.pieces]
    assert starts == sorted(starts)  # continuous: times only move forward
    assert all(len(s) % 4 == 0 for _, s in heard.pieces)


def test_a_new_helper_reopens_the_tap_with_it() -> None:
    found = _found()[:2]
    opened: list[Any] = []
    cap = AppCapture(
        100,
        "com.google.Chrome",
        processes=lambda: list(found),
        open_tap=opening(opened),
        alive=ALIVE,
    )
    cap.start(Heard())
    try:
        wait_for(lambda: len(opened) == 1)
        found.append(proc(10, 1000, "com.google.Chrome.helper", HELPER, playing=True))
        wait_for(lambda: len(opened) == 2)
    finally:
        cap.stop()
    assert opened[1].processes == frozenset({1, 2, 10})


def test_an_app_that_closed_ends_with_silence_to_finish_its_speech() -> None:
    found = _found()[:2]
    running = threading.Event()
    running.set()
    cap = AppCapture(
        100,
        "com.google.Chrome",
        processes=lambda: list(found) if running.is_set() else [],
        open_tap=lambda t: FakeStream(),
        alive=lambda pid: running.is_set(),
    )
    heard = Heard()
    cap.start(heard)
    try:
        wait_for(lambda: heard.seconds() > 0.05)
        running.clear()
        wait_for(lambda: cap.error == "The app has closed.")
    finally:
        cap.stop()
    assert set(heard.pieces[-1][1]) == {0} and cap.capturing is None


def test_a_tap_that_hears_only_zeros_while_the_app_plays_says_not_allowed() -> None:
    found = _found()[:2]  # Chrome's helper plays
    cap = AppCapture(
        100,
        "com.google.Chrome",
        processes=lambda: found,
        open_tap=lambda t: FakeStream(sound=False),
        alive=ALIVE,
    )
    cap.start(Heard())
    try:
        wait_for(lambda: cap.error == NOT_ALLOWED)
        assert cap.capturing == "com.google.Chrome"  # still running
    finally:
        cap.stop()


def test_a_tap_macos_holds_while_the_app_plays_says_not_allowed() -> None:
    """polyglotic-hq 419: with the permission never asked, the tap's start
    waited on macOS (its prompt, unanswered) and the capture said nothing at
    all. The watch goes on through that wait; once it opens with sound the
    capture is allowed and running."""
    found = _found()[:2]  # Chrome's helper plays
    answered = threading.Event()
    streams: list[FakeStream] = []

    def open_tap(target: TapTarget) -> Stream:
        answered.wait(5)
        streams.append(FakeStream())
        return streams[-1]

    cap = AppCapture(
        100,
        "com.google.Chrome",
        processes=lambda: found,
        open_tap=open_tap,
        alive=ALIVE,
    )
    heard = Heard()
    cap.start(heard)
    try:
        wait_for(lambda: cap.error == NOT_ALLOWED)
        assert cap.capturing is None and not streams
        answered.set()
        wait_for(lambda: heard.seconds() > 0.05)
        wait_for(lambda: cap.error is None)
        assert cap.capturing == "com.google.Chrome"
    finally:
        answered.set()
        cap.stop()


def test_a_tap_that_opens_after_its_capture_stopped_is_closed() -> None:
    found = _found()[:2]
    answered = threading.Event()
    streams: list[FakeStream] = []

    def open_tap(target: TapTarget) -> Stream:
        answered.wait(5)
        streams.append(FakeStream())
        return streams[-1]

    cap = AppCapture(
        100,
        "com.google.Chrome",
        processes=lambda: found,
        open_tap=open_tap,
        alive=ALIVE,
    )
    cap.start(Heard())
    time.sleep(0.05)
    began = time.monotonic()
    cap.stop()
    assert time.monotonic() - began < 1.0  # stopping doesn't wait on macOS
    answered.set()
    wait_for(lambda: len(streams) == 1 and streams[0].closed)


def test_a_tap_of_a_quiet_app_is_just_quiet() -> None:
    found = [proc(1, 100, "com.google.Chrome", CHROME + "/Contents/MacOS/x")]
    cap = AppCapture(
        100,
        "com.google.Chrome",
        processes=lambda: found,
        open_tap=lambda t: FakeStream(sound=False),
        alive=ALIVE,
    )
    cap.start(Heard())
    try:
        time.sleep(0.3)  # three times what judges it not allowed
        assert cap.error is None
    finally:
        cap.stop()


def test_everything_else_leaves_out_the_app_and_polyglotic() -> None:
    found = _found()
    opened: list[Any] = []
    cap = EverythingElseCapture(
        100,
        processes=lambda: found,
        open_tap=opening(opened),
    )
    cap.start(Heard())
    try:
        wait_for(lambda: len(opened) == 1)
        # named once the open has returned to the capture's thread, a moment
        # after: GitHub's Mac read it in between (polyglotic-hq 420)
        wait_for(lambda: cap.capturing == "everything else")
    finally:
        cap.stop()
    # Chrome and its helper; Polyglotic's other copy; not this process (from
    # source its group is Python's, and this test isn't it)
    assert opened[0].leave_out and {1, 2, 7} <= opened[0].processes
    assert 5 not in opened[0].processes and 9 not in opened[0].processes


def test_the_whole_system_on_an_output_unplugged_falls_back_to_every_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    opened: list[Any] = []
    monkeypatch.setattr(devices, "audio_devices", lambda: [SPEAKERS])
    plugged = ["usb-dac"]
    cap = SystemCapture(
        "usb-dac",
        processes=list,
        open_tap=opening(opened),
        outputs=lambda: list(plugged),
    )
    cap.start(Heard())
    try:
        wait_for(lambda: len(opened) == 1)
        plugged.clear()
        wait_for(lambda: len(opened) == 2)
    finally:
        cap.stop()
    assert [t.device for t in opened] == ["usb-dac", None]


def test_a_mic_that_wont_open_is_not_retried_until_another_is_wanted() -> None:
    tries: list[str] = []
    mics = ["usb-mic"]

    def open_mic(uid: str) -> tuple[Stream, str]:
        tries.append(uid)
        if uid == "usb-mic":
            raise OSError("Couldn't open the mic: PortAudioError")
        return FakeStream(), "AirPods Pro"

    cap = MicCapture("usb-mic", open_mic, lambda: list(mics), lambda: "airpods")
    cap.start(Heard())
    try:
        wait_for(lambda: cap.error is not None)
        time.sleep(0.1)
        assert tries == ["usb-mic"] and cap.capturing is None
        mics.clear()  # unplugged: the default is wanted
        wait_for(lambda: cap.capturing == "AirPods Pro")
    finally:
        cap.stop()
    assert tries == ["usb-mic", "airpods"] and cap.error is None


def test_a_mic_giving_only_zeros_says_not_allowed() -> None:
    cap = MicCapture(
        None, lambda uid: (FakeStream(sound=False), "Mic"), list, lambda: None
    )
    cap.start(Heard())
    try:
        wait_for(lambda: cap.error == NOT_ALLOWED)
    finally:
        cap.stop()


def test_a_tap_core_audio_stops_is_opened_again() -> None:
    """catap fails a capture it can't go on with (a format change, a lost
    aggregate device): the capture says so and opens a new tap."""
    opened: list[FakeStream] = []

    def open_tap(target: TapTarget) -> Stream:
        stream = FakeStream()
        stream.failed = not opened  # the first one fails at once
        opened.append(stream)
        return stream

    cap = EverythingElseCapture(100, processes=lambda: _found(), open_tap=open_tap)
    heard = Heard()
    cap.start(heard)
    try:
        wait_for(lambda: len(opened) == 2 and heard.seconds() > 0.05)
    finally:
        cap.stop()
    assert opened[0].closed and cap.error is None


def test_apples_own_apps_are_listed_quiet_too() -> None:
    music = proc(11, 1100, "com.apple.Music",
                 "/System/Applications/Music.app/Contents/MacOS/Music")  # fmt: skip
    [found] = apps.playing_apps([music], this=999, info=info)
    assert (found.name, found.playing, found.title) == (
        "com.apple.Music",
        False,
        "Apple Music",
    )
