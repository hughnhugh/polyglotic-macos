"""Capturing on Linux (polyglotic-hq 546, 547, 550, 561): what each capture
records - the default output's monitor by name, the output chosen, the mic
but never an output's monitor, one app's streams each from its output's
monitor, everything else's - and how it follows the sound server's
changes, through a stand-in server. The real one is `linux_desktop`:
PipeWire's pulse server on GitHub's Ubuntu runner (`linux.yml`)."""

import json
import os
import shutil
import struct
import subprocess
import threading
import time
from collections.abc import Callable
from pathlib import Path

import numpy as np
import pytest

from polyglotic_desktop.platform.linux import apps, capture, devices, pulse
from polyglotic_desktop.platform.linux.capture import MicCapture, SystemCapture
from polyglotic_desktop.ports.capture import (
    AppCaptureSupport,
    PlayingApp,
    SourceCategory,
)

SPEAKERS = pulse.Device(
    "alsa_output.speakers", "Speakers", 1, True, monitor="alsa_output.speakers.monitor"
)
HEADPHONES = pulse.Device(
    "bluez_output.phones", "Headphones", 2, False, monitor="bluez_output.phones.monitor"
)
SPEAKERS_MONITOR = pulse.Device(
    "alsa_output.speakers.monitor", "Monitor of Speakers", 3, True, monitor_of=1
)
MIC = pulse.Device("alsa_input.mic", "Built-in Mic", 4, False)
USB_MIC = pulse.Device("alsa_input.usb", "USB Mic", 5, False)


class FakeRecording:
    def __init__(self, source: str, monitor_of: int | None = None) -> None:
        self.source = source
        self.monitor_of = monitor_of
        self.pieces: list[tuple[float, bytes]] = []
        self.failed = False
        self.closed = False

    def take(self) -> list[tuple[float, bytes]]:
        pieces, self.pieces = self.pieces, []
        return pieces

    def close(self) -> None:
        self.closed = True


class FakeServer:
    """The sound server as a capture sees it: its devices and defaults, which
    a test changes (counted as the server's changes)."""

    def __init__(self) -> None:
        self.outputs = [SPEAKERS, HEADPHONES]
        self.inputs = [SPEAKERS_MONITOR, MIC, USB_MIC]
        self.default_output: str | None = SPEAKERS.name
        self.default_input: str | None = MIC.name
        self.changes = 0
        self.alive = True
        self.recordings: list[FakeRecording] = []
        self.refuse: set[str] = set()
        self.closed = 0
        self.playing: list[pulse.PlayingStream] = []
        self.watched: list[int] = []

    def server_info(self) -> pulse.Defaults:
        if not self.alive:
            raise OSError("gone")
        return pulse.Defaults(
            "PulseAudio (on PipeWire 1.0.5)", self.default_output, self.default_input
        )

    def sinks(self) -> list[pulse.Device]:
        return list(self.outputs)

    def sources(self) -> list[pulse.Device]:
        return list(self.inputs)

    def streams(self) -> list[pulse.PlayingStream]:
        return list(self.playing)

    def watch(self, what: int = pulse.DEVICES) -> None:
        self.watched.append(what)

    def record(self, source: str, monitor_of: int | None = None) -> FakeRecording:
        if source in self.refuse or (
            monitor_of is not None and f"#{monitor_of}" in self.refuse
        ):
            raise OSError("The sound server didn't start recording that device")
        recording = FakeRecording(source, monitor_of)
        self.recordings.append(recording)
        return recording

    def run(self, seconds: float) -> None:
        time.sleep(min(seconds, 0.01))

    def close(self) -> None:
        self.closed += 1

    def change(self, **values: object) -> None:
        for key, value in values.items():
            setattr(self, key, value)
        self.changes += 1


def wait_for(condition: Callable[[], object], seconds: float = 3.0) -> None:
    end = time.monotonic() + seconds
    while not condition():
        assert time.monotonic() < end, "timed out"
        time.sleep(0.01)


def started(
    make: Callable[..., capture._Capture], server: FakeServer, device: str | None = None
) -> tuple[capture._Capture, list[tuple[float, bytes]]]:
    heard: list[tuple[float, bytes]] = []
    made = make(device, connect=lambda: server)
    made.start(lambda at, data: heard.append((at, data)))
    return made, heard


def test_everything_the_pc_plays_is_the_default_outputs_monitor_by_name() -> None:
    server = FakeServer()
    system, _ = started(SystemCapture, server)
    try:
        wait_for(lambda: server.recordings)
        assert server.recordings[0].source == "alsa_output.speakers.monitor"
        wait_for(lambda: system.capturing == "Speakers")
    finally:
        system.stop()


def test_a_new_default_output_is_followed() -> None:
    """Headphones plugged in become the default: the next recording is their
    monitor, the speakers' closed."""
    server = FakeServer()
    system, _ = started(SystemCapture, server)
    try:
        wait_for(lambda: server.recordings)
        server.change(default_output=HEADPHONES.name)
        wait_for(lambda: len(server.recordings) == 2)
        assert server.recordings[1].source == "bluez_output.phones.monitor"
        assert server.recordings[0].closed
    finally:
        system.stop()


def test_the_output_chosen_while_its_plugged_in() -> None:
    server = FakeServer()
    system, _ = started(SystemCapture, server, HEADPHONES.name)
    try:
        wait_for(lambda: server.recordings)
        assert server.recordings[0].source == "bluez_output.phones.monitor"
        server.change(outputs=[SPEAKERS])  # unplugged: the default then
        wait_for(lambda: len(server.recordings) == 2)
        assert server.recordings[1].source == "alsa_output.speakers.monitor"
    finally:
        system.stop()


def test_speaker_hold_does_not_use_a_different_output_when_one_is_selected() -> None:
    server = FakeServer()
    assert capture.output_monitor(server, HEADPHONES.name, strict_device=True) == (
        HEADPHONES.monitor,
        HEADPHONES.description,
    )
    server.outputs = [SPEAKERS]
    assert capture.output_monitor(server, HEADPHONES.name, strict_device=True) is None
    assert capture.output_monitor(server, None, strict_device=True) == (
        SPEAKERS.monitor,
        SPEAKERS.description,
    )


def test_no_output_at_all_says_so() -> None:
    server = FakeServer()
    server.outputs, server.default_output = [], None
    system, _ = started(SystemCapture, server)
    try:
        wait_for(lambda: system.error == capture.NO_OUTPUT)
        assert not server.recordings and system.capturing is None
    finally:
        system.stop()


def test_the_mic_is_the_default_input() -> None:
    server = FakeServer()
    mic, _ = started(MicCapture, server)
    try:
        wait_for(lambda: server.recordings)
        assert server.recordings[0].source == "alsa_input.mic"
        assert mic.capturing == "Built-in Mic"
    finally:
        mic.stop()


def test_the_mic_chosen_while_its_plugged_in() -> None:
    server = FakeServer()
    mic, _ = started(MicCapture, server, USB_MIC.name)
    try:
        wait_for(lambda: server.recordings)
        assert server.recordings[0].source == "alsa_input.usb"
    finally:
        mic.stop()


def test_a_default_input_that_is_an_outputs_monitor_is_no_microphone() -> None:
    """A PC with no mic gets its output's monitor as the default source
    (547): captioning it as the learner's own speech would caption the game.
    Nothing is recorded; the capture says why - and a monitor chosen by
    name isn't taken either."""
    server = FakeServer()
    server.inputs, server.default_input = [SPEAKERS_MONITOR], SPEAKERS_MONITOR.name
    for chosen in (None, SPEAKERS_MONITOR.name):
        mic, _ = started(MicCapture, server, chosen)
        try:
            wait_for(lambda m=mic: m.error == capture.NO_MIC)  # type: ignore[misc]
            assert not server.recordings and mic.capturing is None
        finally:
            mic.stop()
    server.change(inputs=[SPEAKERS_MONITOR, MIC], default_input=MIC.name)
    mic, _ = started(MicCapture, server)
    try:
        wait_for(lambda: server.recordings)
        assert server.recordings[0].source == MIC.name
    finally:
        mic.stop()


def floats(*values: float) -> bytes:
    return struct.pack(f"<{len(values)}f", *values)


def test_audio_is_delivered_as_it_came_stamped_on_the_apps_clock() -> None:
    server = FakeServer()
    system, heard = started(SystemCapture, server)
    try:
        wait_for(lambda: server.recordings)
        now = time.perf_counter()
        piece = floats(*([0.25] * 320))  # 20 ms at 16kHz
        server.recordings[0].pieces += [(now, piece), (now + 0.02, piece)]
        wait_for(lambda: sum(len(d) for _, d in heard) >= 2 * len(piece))
        sound = [(at, data) for at, data in heard if any(np.frombuffer(data, "<f4"))]
        assert sound[0][1] == piece
        assert sound[1][0] == pytest.approx(sound[0][0] + 0.02, abs=1e-6)
        assert sound[0][0] == pytest.approx(now - 0.02, abs=0.01)
    finally:
        system.stop()


def test_silence_fills_in_while_nothing_plays() -> None:
    """Once audio has started, a quiet output still gives continuous audio
    (the port's promise): zeros, on the app's clock."""
    server = FakeServer()
    system, heard = started(SystemCapture, server)
    try:
        wait_for(lambda: server.recordings)
        server.recordings[0].pieces.append((time.perf_counter(), floats(0.5)))
        wait_for(lambda: sum(len(d) for _, d in heard) > 16_000)  # over 0.25 s
        starts = [at for at, _ in heard]
        assert starts == sorted(starts)
    finally:
        system.stop()


def test_a_recording_whose_device_went_is_opened_again() -> None:
    server = FakeServer()
    system, _ = started(SystemCapture, server)
    try:
        wait_for(lambda: server.recordings)
        server.recordings[0].failed = True
        wait_for(lambda: len(server.recordings) == 2)
        assert server.recordings[1].source == "alsa_output.speakers.monitor"
    finally:
        system.stop()


def test_a_device_that_wont_record_is_said_and_tried_again() -> None:
    server = FakeServer()
    server.refuse.add("alsa_output.speakers.monitor")
    system, _ = started(SystemCapture, server)
    try:
        wait_for(lambda: system.error and "didn't start" in system.error)
        server.refuse.clear()
        server.change()
        wait_for(lambda: server.recordings, 4.0)
        wait_for(lambda: system.error is None)
    finally:
        system.stop()


def test_no_sound_server_is_said_and_connected_again(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(capture, "RECONNECT_SEC", 0.05)
    server = FakeServer()
    tries: list[int] = []

    def connect() -> FakeServer:
        tries.append(1)
        if len(tries) < 3:
            raise OSError("No sound server to connect to")
        return server

    system = SystemCapture(connect=connect)
    system.start(lambda *_a: None)
    try:
        wait_for(lambda: server.recordings)
        assert system.restarts == 2
        assert len(tries) == 3
    finally:
        system.stop()


def test_a_server_that_goes_away_is_connected_to_again(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(capture, "RECONNECT_SEC", 0.05)
    first, second = FakeServer(), FakeServer()
    servers = iter([first, second])
    system = SystemCapture(connect=lambda: next(servers))
    system.start(lambda *_a: None)
    try:
        wait_for(lambda: first.recordings)
        first.alive = False
        first.recordings[0].failed = True
        wait_for(lambda: second.recordings)
        assert first.closed == 1
    finally:
        system.stop()


def test_stop_ends_the_thread_and_closes_the_connection() -> None:
    server = FakeServer()
    system, _ = started(SystemCapture, server)
    wait_for(lambda: server.recordings)
    system.stop()
    assert server.recordings[0].closed and server.closed == 1
    assert system.capturing is None


class CheckedLibrary:
    """libpulse's calls a record stream makes, each argument checked as
    ctypes checks it against the call's declared types (`pulse._SIGNATURES`)
    - so a call ctypes would refuse fails here too, on any OS."""

    def __init__(self) -> None:
        self.called: list[str] = []

    def __getattr__(self, name: str) -> Callable[..., object]:
        _result, arguments = pulse._SIGNATURES[name]

        def call(*given: object) -> object:
            for kind, value in zip(arguments, given, strict=True):
                if hasattr(kind, "from_param"):
                    kind.from_param(value)  # TypeError, as ctypes would raise
            self.called.append(name)
            return {"pa_stream_new": 1, "pa_stream_get_state": 3}.get(name, 0)

        return call


def test_a_record_stream_closes_without_an_error() -> None:
    """Closing took the callbacks away with None, which ctypes refuses for
    a callback's type: closing raised, the stream was never let go, and the
    capture's thread ended with "Capture stopped: ArgumentError" - at a new
    default output, or as an app's stream ended (561's first runs)."""
    lib = CheckedLibrary()
    recording = pulse.Recording(lib, 1, "alsa_output.speakers.monitor")
    recording.close()
    assert lib.called[-3:] == [
        "pa_stream_set_read_callback",
        "pa_stream_set_state_callback",
        "pa_stream_unref",
    ]


# --- the device lists ---------------------------------------------------------


def test_the_devices_listed_never_count_a_monitor_as_a_mic() -> None:
    found = devices.listed(
        [HEADPHONES, SPEAKERS],
        [SPEAKERS_MONITOR, USB_MIC, MIC],
        pulse.Defaults("x", SPEAKERS.name, SPEAKERS_MONITOR.name),
    )
    assert [d.name for d in found.speakers] == ["Headphones", "Speakers"]
    assert [d.id for d in found.mics] == ["alsa_input.mic", "alsa_input.usb"]
    assert found.default_speaker == SPEAKERS.name
    assert found.default_mic is None  # the monitor: no mic


def test_no_sound_server_lists_nothing() -> None:
    def none() -> FakeServer:
        raise OSError("no server")

    assert devices.sound_devices(none).speakers == ()
    assert devices.outputs_playing(none) is None


def test_outputs_playing_counts_the_running_ones() -> None:
    server = FakeServer()
    assert devices.outputs_playing(lambda: server) == 1
    assert server.closed == 1


# --- one app at a time (561) -----------------------------------------------------

FIREFOX_A = pulse.PlayingStream(11, 1, False, "Firefox", "firefox", 100)
FIREFOX_B = pulse.PlayingStream(12, 1, True, "Firefox", "firefox", 101)
VLC = pulse.PlayingStream(21, 2, False, "VLC media player (LibVLC 3.0.20)", "vlc", 200)


def own_stream(index: int = 31) -> pulse.PlayingStream:
    return pulse.PlayingStream(index, 1, False, "Polyglotic", "python3.12", os.getpid())


def test_a_streams_app_is_its_own_else_its_clients() -> None:
    """A native PipeWire player puts its executable and process only on its
    client (547); the process the server saw connect comes first - a
    sandboxed app's own number is the sandbox's."""
    native = pulse.playing_stream(
        5, 1, False, {"application.name": "pw-play"},
        {"application.process.binary": "pw-play", "application.process.id": "77"},
    )  # fmt: skip
    assert (native.app_name, native.binary, native.process_id) == (
        "pw-play",
        "pw-play",
        77,
    )
    sandboxed = pulse.playing_stream(
        6, 1, False,
        {"application.process.binary": "firefox", "application.process.id": "2"},
        {"pipewire.sec.pid": "4321"},
    )  # fmt: skip
    assert sandboxed.process_id == 4321 and sandboxed.binary == "firefox"
    assert pulse.playing_stream(7, 1, False, {}, {}).process_id is None


def test_the_apps_playing_are_one_entry_per_app() -> None:
    streams = [FIREFOX_A, FIREFOX_B, VLC, own_stream()]
    listed = apps.playing_apps(streams, os.getpid(), lambda _pid: None)
    assert [a.name for a in listed] == ["firefox", "vlc"]  # Polyglotic's own: never
    firefox, vlc = listed
    assert (firefox.process_id, firefox.playing, firefox.title) == (
        100,
        True,
        "Firefox",
    )
    assert (
        firefox.category is SourceCategory.BROWSER and firefox.known_name == "Firefox"
    )
    assert vlc.title == "VLC" and vlc.category is SourceCategory.VIDEO
    paused = pulse.PlayingStream(41, 1, True, "Rhythmbox", "rhythmbox", 300)
    later = apps.playing_apps([paused, VLC], os.getpid(), lambda _pid: None)
    assert [(a.name, a.playing) for a in later] == [("vlc", True), ("rhythmbox", False)]
    assert later[1].known_name is None and later[1].title == "Rhythmbox"


def test_a_program_under_wine_is_known_by_its_own_name() -> None:
    """Every Windows game through Proton runs as Wine's executable: each is
    its own app, a game by where it's installed."""
    game = pulse.PlayingStream(51, 1, False, "eldenring.exe", "wine64-preloader", 500)
    other = pulse.PlayingStream(52, 1, False, "notepad.exe", "wine64-preloader", 501)
    steam = (
        "/home/a/.steam/steam/steamapps/common/Proton 9.0/files/bin/wine64-preloader"
    )
    listed = apps.playing_apps(
        [game, other], 1, lambda pid: steam if pid == 500 else None
    )
    named = {a.name: a for a in listed}
    assert set(named) == {"eldenring.exe", "notepad.exe"}
    assert named["eldenring.exe"].category is SourceCategory.GAME
    assert named["notepad.exe"].category is SourceCategory.OTHER


def test_speech_dispatchers_streams_are_never_an_app_to_caption() -> None:
    """591: speech-dispatcher, started to say a word, keeps a stream for each
    voice while it runs - its dummy's never paused - as GitHub's Ubuntu
    24.04 runner listed them. Never on Home's list."""
    espeak = pulse.PlayingStream(
        71, 1, False, "speech-dispatcher-espeak-ng", "speech-dispatcher", 700
    )
    dummy = pulse.PlayingStream(
        72, 1, False, "speech-dispatcher-dummy", "sd_dummy", 701
    )
    listed = apps.playing_apps([espeak, dummy, VLC], 1, lambda _pid: None)
    assert [a.name for a in listed] == ["vlc"]


def test_the_packed_app_is_never_listed_by_its_executable() -> None:
    packed = pulse.PlayingStream(61, 1, False, "Polyglotic", "Polyglotic", 999)
    assert apps.playing_apps([packed, VLC], 1, lambda _pid: None)[0].name == "vlc"
    assert len(apps.playing_apps([packed], 1, lambda _pid: None)) == 0


def test_one_app_alone_wherever_the_sound_servers_library_is() -> None:
    assert capture.app_capture_support(lambda: None) is AppCaptureSupport.YES

    def missing() -> None:
        raise OSError("libpulse isn't installed (libpulse.so.0)")

    assert capture.app_capture_support(missing) is AppCaptureSupport.NO


def one_app(
    server: FakeServer, name: str = "firefox", alive: bool = True
) -> tuple[capture.AppCapture, list[tuple[float, bytes]]]:
    heard: list[tuple[float, bytes]] = []
    made = capture.AppCapture(
        100, name, None, lambda: server, lambda _pid: alive, lambda _key: alive
    )
    made.start(lambda at, data: heard.append((at, data)))
    return made, heard


def test_one_app_is_each_of_its_streams_from_its_outputs_monitor() -> None:
    server = FakeServer()
    server.playing = [FIREFOX_A, FIREFOX_B, VLC]
    made, _ = one_app(server)
    try:
        wait_for(lambda: len(server.recordings) == 2)
        assert {(r.source, r.monitor_of) for r in server.recordings} == {
            (SPEAKERS.monitor, 11),
            (SPEAKERS.monitor, 12),
        }
        assert server.watched == [pulse.STREAMS]  # the apps' streams followed
        assert made.capturing == "firefox" and made.error is None
    finally:
        made.stop()


def test_an_apps_stream_that_ends_is_followed_to_its_next() -> None:
    """With DONT_MOVE the record stream fails as the app's stream ends (547):
    the capture takes the app's next stream, never the mic."""
    server = FakeServer()
    server.playing = [FIREFOX_A]
    made, _ = one_app(server)
    try:
        wait_for(lambda: len(server.recordings) == 1)
        first = server.recordings[0]
        server.playing = [pulse.PlayingStream(13, 2, False, "Firefox", "firefox", 100)]
        first.failed = True
        wait_for(lambda: len(server.recordings) == 2)
        assert first.closed
        assert (server.recordings[1].source, server.recordings[1].monitor_of) == (
            HEADPHONES.monitor,
            13,
        )
    finally:
        made.stop()


def test_one_stream_goes_straight_on_and_several_are_summed() -> None:
    server = FakeServer()
    server.playing = [FIREFOX_A]
    made, heard = one_app(server)
    try:
        wait_for(lambda: len(server.recordings) == 1)
        now = time.perf_counter()
        server.recordings[0].pieces.append((now, floats(*[0.25] * 320)))
        wait_for(lambda: any(np.frombuffer(d, "<f4").max() > 0 for _, d in heard))
        server.change(playing=[FIREFOX_A, FIREFOX_B])
        time.sleep(0.3)  # both stamped from their arrival, not counted on
        wait_for(lambda: len(server.recordings) == 2)
        later = time.perf_counter()
        for kept in server.recordings:
            kept.pieces.append((later, floats(*[0.25] * 320)))
        wait_for(lambda: any(np.frombuffer(d, "<f4").max() > 0.4 for _, d in heard), 3)
    finally:
        made.stop()
    loudest = max(float(np.frombuffer(d, "<f4").max()) for _, d in heard)
    assert loudest == pytest.approx(0.5)


def test_the_mixer_sums_on_the_apps_clock_within_full_scale() -> None:
    mixer = capture.Mixer()
    mixer.add(10.0, np.full(1600, 0.75, np.float32))  # 0.1 s
    mixer.add(10.05, np.full(1600, 0.75, np.float32))  # half a piece later
    assert mixer.take(10.1) == []  # not yet MIX_BEHIND_SEC old
    ((start, data),) = mixer.take(10.4)
    summed = np.frombuffer(data, "<f4")
    assert start == 10.0 and len(summed) == 2400
    assert summed[0] == pytest.approx(0.75) and summed[1000] == 1.0  # clipped
    mixer.add(10.0, np.full(160, 0.5, np.float32))  # too late: already on
    assert mixer.take(11.0) == []


def test_an_app_that_plays_nothing_now_is_silence_not_the_end() -> None:
    server = FakeServer()
    server.playing = [FIREFOX_A]
    made, heard = one_app(server)
    try:
        wait_for(lambda: len(server.recordings) == 1)
        server.recordings[0].pieces.append((time.perf_counter(), floats(*[0.1] * 320)))
        wait_for(lambda: heard)
        server.change(playing=[])
        server.recordings[0].failed = True
        wait_for(lambda: made.capturing is None)
        time.sleep(0.4)
        assert made.error is None and made._thread is not None  # still going
        assert sum(len(d) for _, d in heard) > 320 * 4  # silence filled in
    finally:
        made.stop()


def test_the_app_closing_ends_the_capture() -> None:
    server = FakeServer()
    server.playing = [FIREFOX_A]
    made, heard = one_app(server, alive=False)
    try:
        wait_for(lambda: len(server.recordings) == 1)
        server.recordings[0].pieces.append((time.perf_counter(), floats(*[0.1] * 320)))
        wait_for(lambda: heard)
        server.change(playing=[])
        wait_for(lambda: made.error == capture.APP_CLOSED)
        assert made.capturing is None
        assert len(heard[-1][1]) == 16_000 * 4  # a second of silence: speech ends
    finally:
        made.stop()


def test_an_app_whose_process_changed_hasnt_closed() -> None:
    """A player started again for each file, a browser's audio process
    restarted: the process the app was chosen by is gone, another of it
    runs - the capture goes on, and takes the new process's stream."""
    server = FakeServer()
    server.playing = [FIREFOX_A]
    made = capture.AppCapture(
        100, "firefox", None, lambda: server, lambda _pid: False, lambda key: True
    )
    made.start(lambda _at, _data: None)
    try:
        wait_for(lambda: len(server.recordings) == 1)
        server.change(playing=[])
        server.recordings[0].failed = True
        time.sleep(0.3)
        assert made.error is None
        server.change(
            playing=[pulse.PlayingStream(14, 1, False, "Firefox", "firefox", 150)]
        )
        wait_for(lambda: [r.monitor_of for r in server.recordings] == [11, 14])
    finally:
        made.stop()


def test_an_apps_processes_are_found_by_executable_or_own_name(tmp_path: Path) -> None:
    """A zombie (ended, not yet collected by its parent) runs no more: the
    first run on GitHub's runner kept a capture open on one (561)."""
    for pid, comm, state in (
        (10, "bash", "S"),
        (11, "eldenring.exe", "R"),
        (12, "ts3client_linux", "S"),
        (13, "pw-cat", "Z"),
    ):
        (tmp_path / str(pid)).mkdir()
        (tmp_path / str(pid) / "comm").write_text(comm + "\n", encoding="utf-8")
        stat = f"{pid} ({comm}) {state} 1 {pid} {pid} 0 -1 4194560"
        (tmp_path / str(pid) / "stat").write_text(stat, encoding="utf-8")
    assert apps.running("eldenring.exe", tmp_path)
    assert apps.running("ts3client_linux_amd64", tmp_path)  # the kernel keeps 15
    assert not apps.running("firefox", tmp_path)
    assert not apps.running("pw-cat", tmp_path)  # a zombie
    assert apps.alive(11, tmp_path) and not apps.alive(13, tmp_path)
    assert not apps.alive(99, tmp_path) and not apps.alive(0, tmp_path)


def test_everything_else_leaves_out_the_app_and_polyglotic() -> None:
    server = FakeServer()
    server.playing = [FIREFOX_A, FIREFOX_B, VLC, own_stream()]
    heard: list[tuple[float, bytes]] = []
    made = capture.EverythingElseCapture(101, None, lambda: server)  # a helper's
    made.start(lambda at, data: heard.append((at, data)))
    try:
        wait_for(lambda: len(server.recordings) == 1)
        time.sleep(0.2)
        assert [r.monitor_of for r in server.recordings] == [21]
        assert made.capturing == "everything else"
    finally:
        made.stop()


def test_the_app_list_asks_the_server_once_per_snapshot() -> None:
    reads: list[int] = []

    def read() -> list[pulse.PlayingStream]:
        reads.append(1)
        return [VLC]

    snapshot = apps._Snapshot(read)
    assert snapshot() == [VLC] and snapshot() == [VLC] and len(reads) == 1

    def gone() -> list[pulse.PlayingStream]:
        raise OSError("No sound server to connect to")

    assert apps._Snapshot(gone)() == []


# --- the real sound server (GitHub's Ubuntu runner) -----------------------------


def play(seconds: float, hz: float) -> subprocess.Popen[bytes]:
    """A tone on the default output, through the server's own player."""
    player = shutil.which("pw-play") or shutil.which("paplay")
    assert player, "pw-play or paplay"
    rate = 48_000
    t = np.arange(int(seconds * rate)) / rate
    tone = (0.3 * np.sin(2 * np.pi * hz * t)).astype("<f4").tobytes()
    if player.endswith("pw-play"):
        args = [player, "--rate", str(rate), "--channels", "1", "--format", "f32", "-"]
    else:
        args = [
            player,
            "--raw",
            "--rate",
            str(rate),
            "--channels",
            "1",
            "--format",
            "float32le",
        ]
    process = subprocess.Popen(args, stdin=subprocess.PIPE)
    sink = process.stdin
    assert sink is not None

    def feed() -> None:
        sink.write(tone)
        sink.close()

    threading.Thread(target=feed, daemon=True).start()
    return process


@pytest.mark.linux_desktop
def test_the_real_server_names_its_defaults_and_devices() -> None:
    server = pulse.PulseServer("Polyglotic tests")
    try:
        defaults = server.server_info()
        assert "PulseAudio" in defaults.server
        outputs = server.sinks()
        assert defaults.output in {sink.name for sink in outputs}
        assert all(sink.monitor for sink in outputs)
        monitors = [s for s in server.sources() if s.monitor_of is not None]
        assert {m.name for m in monitors} == {sink.monitor for sink in outputs}
    finally:
        server.close()


@pytest.mark.linux_desktop
def test_a_real_record_stream_closes_and_its_capture_goes_on() -> None:
    """A record stream on the real server closes without an error (561)."""
    server = pulse.PulseServer("Polyglotic tests")
    try:
        output = server.server_info().output
        monitor = next(s.monitor for s in server.sinks() if s.name == output)
        assert monitor
        recording = server.record(monitor)
        server.run(0.2)
        recording.close()
        assert server.alive
    finally:
        server.close()


@pytest.mark.linux_desktop
def test_everything_the_pc_plays_is_heard_through_the_real_server() -> None:
    """A tone played on the default output comes back through the system
    capture as 16kHz float32, loud, about as long as it played."""
    heard: list[tuple[float, bytes]] = []
    system = SystemCapture()
    system.start(lambda at, data: heard.append((at, data)))
    try:
        wait_for(lambda: system.capturing is not None, 10)
        player = play(2.0, 440)
        player.wait(timeout=20)
        time.sleep(0.5)
    finally:
        system.stop()
    samples = np.frombuffer(b"".join(d for _, d in heard), "<f4")
    assert len(samples) > 16_000  # over a second
    assert float(np.sqrt(np.mean(samples**2))) > 0.02
    starts = [at for at, _ in heard]
    assert starts == sorted(starts)


# --- one app at a time on the real sound server (561) ----------------------------


def play_with(player: str, seconds: float, hz: float) -> subprocess.Popen[bytes]:
    """A tone on the default output through one player: `pw-play` (a native
    PipeWire client: its executable and process only on its client) or
    `paplay` (libpulse's) - two apps, as the sound server sees them."""
    found = shutil.which(player)
    assert found, player
    rate = 48_000
    t = np.arange(int(seconds * rate)) / rate
    tone = (0.3 * np.sin(2 * np.pi * hz * t)).astype("<f4").tobytes()
    if player == "pw-play":
        args = [found, "--rate", str(rate), "--channels", "1", "--format", "f32", "-"]
    else:
        args = [found, "--raw", "--rate", str(rate), "--channels", "1",
                "--format", "float32le"]  # fmt: skip
    process = subprocess.Popen(args, stdin=subprocess.PIPE)
    sink = process.stdin
    assert sink is not None

    def feed() -> None:
        sink.write(tone)
        sink.close()

    threading.Thread(target=feed, daemon=True).start()
    return process


def level(samples: np.ndarray, hz: float) -> float:
    """The tone at `hz` in `samples` (16kHz), in dB of full scale: the
    strongest bin within 3 Hz of it."""
    spectrum = np.abs(np.fft.rfft(samples * np.hanning(len(samples))))
    freqs = np.fft.rfftfreq(len(samples), 1 / 16_000)
    near = spectrum[(freqs > hz - 3) & (freqs < hz + 3)]
    peak = float(near.max()) / (len(samples) / 4) if len(near) else 0.0
    return 20 * float(np.log10(max(peak, 1e-12)))


def listed_app(name: str, seconds: float = 10.0) -> PlayingApp:
    """The app `name` in the real app list, once it plays."""
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        found = [a for a in apps.LinuxAppList().playing_apps() if a.name == name]
        if found:
            return found[0]
        time.sleep(0.2)
    raise AssertionError(f"{name} never listed: {apps.LinuxAppList().playing_apps()}")


@pytest.mark.linux_desktop
def test_one_app_is_heard_alone_through_the_real_server() -> None:
    """Two players, two tones: one app's capture hears its own tone and not
    the other's; everything else hears the other's and not its own. The
    native PipeWire player is listed by its client's executable and process."""
    native = play_with("pw-play", 8.0, 440)
    pulse_player = play_with("paplay", 8.0, 1000)
    heard: dict[str, list[tuple[float, bytes]]] = {"app": [], "else": []}
    try:
        app = listed_app("pw-cat")  # pw-play is a link to pw-cat
        assert app.process_id == native.pid and app.playing
        # paplay is a link to pacat; the session's mic feed is a pacat too, so
        # the app's process is the older of the two (561's first run)
        assert listed_app("pacat").playing
        one = capture.AppCapture(app.process_id, app.name)
        rest = capture.EverythingElseCapture(app.process_id)
        one.start(lambda at, data: heard["app"].append((at, data)))
        rest.start(lambda at, data: heard["else"].append((at, data)))
        try:
            wait_for(lambda: one.capturing and rest.capturing, 10)
            time.sleep(3.0)
        finally:
            one.stop()
            rest.stop()
    finally:
        for player in (native, pulse_player):
            player.kill()
            player.wait(5)  # collected: no zombie left for the next test
    alone = np.frombuffer(b"".join(d for _, d in heard["app"]), "<f4")[-32_000:]
    others = np.frombuffer(b"".join(d for _, d in heard["else"]), "<f4")[-32_000:]
    assert len(alone) == len(others) == 32_000  # two seconds each
    own, leaked = level(alone, 440), level(alone, 1000)
    rest_own, rest_leaked = level(others, 1000), level(others, 440)
    measured = {
        "one_app_440_dbfs": round(own, 1),
        "one_app_1000_dbfs": round(leaked, 1),
        "everything_else_1000_dbfs": round(rest_own, 1),
        "everything_else_440_dbfs": round(rest_leaked, 1),
    }
    if os.environ.get("OUT"):  # kept by linux.yml's artifact
        found = Path(os.environ["OUT"]) / "one-app-isolation.json"
        found.write_text(json.dumps(measured, indent=2), encoding="utf-8")
    assert own > -30 and own - leaked > 60, measured
    assert rest_own > -30 and rest_own - rest_leaked > 60, measured


@pytest.mark.linux_desktop
def test_one_apps_capture_ends_when_the_app_closes() -> None:
    native = play_with("pw-play", 30.0, 440)
    try:
        app = listed_app("pw-cat")  # pw-play is a link to pw-cat
        one = capture.AppCapture(app.process_id, app.name)
        one.start(lambda _at, _data: None)
        try:
            wait_for(lambda: one.capturing, 10)
            native.kill()
            native.wait(5)
            end = time.monotonic() + 5
            while one.error != capture.APP_CLOSED and time.monotonic() < end:
                time.sleep(0.05)
            assert one.error == capture.APP_CLOSED, (
                one.error,
                one.capturing,
                apps.alive(app.process_id),
                apps.running(app.name),
                [a.name for a in apps.LinuxAppList().playing_apps()],
            )
        finally:
            one.stop()
    finally:
        native.kill()
        native.wait(5)


# --- the known apps (561) ---------------------------------------------------------


def test_every_public_name_is_one_windows_list_and_the_tracking_plan_have() -> None:
    """A Linux app's public name may leave the PC only if the tracking plan
    lists it (DECISIONS.md #30): Windows' list is tied to the plan by its
    own test, so Linux's must be a part of Windows'."""
    from polyglotic_desktop.core.listening.sources import known_app_id
    from polyglotic_desktop.platform.linux import categories
    from polyglotic_desktop.platform.windows import categories as windows_categories

    windows = {known_app_id(n) for n in windows_categories.known_names()}
    assert {known_app_id(n) for n in categories.known_names()} <= windows


def test_linux_only_apps_have_a_category_but_no_public_name() -> None:
    from polyglotic_desktop.platform.linux import categories

    assert categories.category_of("totem") is SourceCategory.VIDEO
    assert categories.known_name("totem") is None
    assert categories.shown_name("totem") == "Videos"
    assert categories.known_name("Discord") == "Discord"  # any case
    common = {a.name for a in categories.COMMON_APPS}
    assert all(categories.known_name(name) for name in common)  # each a public one
