"""The app's own sound on Linux (polyglotic-hq 591): a recorded word's clip
and Home's sample, each on a thread of its own that answers the sound
server as it asks, through a stand-in server, on any OS. The real one,
heard at the output's monitor, is `test_linux_voices_heard.py`."""

import threading
import time
from collections.abc import Callable
from typing import ClassVar

import numpy as np
import pytest

from polyglotic_desktop.platform.linux import sound
from polyglotic_desktop.platform.linux.sound import PlayAloud, PulseOutput, pcm16
from polyglotic_desktop.platform.speaking import Clip


class Playback:
    def __init__(self, pcm: bytes, rate: int, channels: int, seconds: float) -> None:
        self.pcm, self.rate, self.channels = pcm, rate, channels
        self.remaining = seconds
        self.closed = False
        self.failed = False

    @property
    def done(self) -> bool:
        return self.remaining <= 0

    def close(self) -> None:
        self.closed = True


class Server:
    """A stand-in sound server: a clip plays for `seconds`, on the thread
    that connected - which is checked."""

    made: ClassVar[list["Server"]] = []

    def __init__(self, seconds: float = 0.2, refuses: bool = False) -> None:
        self.seconds = seconds
        self.refuses = refuses
        self.thread = threading.current_thread()
        self.playbacks: list[Playback] = []
        self.runs = 0
        self.closed = False
        Server.made.append(self)

    def play(self, pcm: bytes, rate: int, channels: int = 1) -> Playback:
        assert threading.current_thread() is self.thread
        if self.refuses:
            raise OSError("The sound server didn't start playing")
        made = Playback(pcm, rate, channels, self.seconds)
        self.playbacks.append(made)
        return made

    def run(self, seconds: float) -> None:
        assert threading.current_thread() is self.thread
        self.runs += 1
        time.sleep(seconds)
        # A delayed scheduler wake-up does not service extra audio buffers.
        self.playbacks[-1].remaining -= seconds

    def close(self) -> None:
        self.closed = True


@pytest.fixture(autouse=True)
def fresh() -> None:
    Server.made = []


def output(server: Callable[[], Server]) -> PulseOutput:
    return PulseOutput(server)  # type: ignore[arg-type]


def clip(seconds: float = 0.2) -> Clip:
    return Clip(b"\x00\x10" * round(16_000 * seconds), 16_000)


def test_a_clip_plays_to_its_end_on_a_thread_of_its_own() -> None:
    out = output(lambda: Server(0.2))
    began = time.monotonic()
    assert out.start(clip())
    [server] = Server.made
    assert server.thread is not threading.current_thread()
    assert out.playing()
    while out.playing():
        assert time.monotonic() - began < 2
        time.sleep(0.01)
    assert time.monotonic() - began >= 0.2
    assert server.playbacks[0].closed and server.closed
    assert server.runs >= 5  # the server's asks answered all along
    out.stop()


def test_a_clip_stopped_stops_at_once() -> None:
    out = output(lambda: Server(5.0))
    assert out.start(clip(5.0))
    began = time.monotonic()
    out.stop()
    assert time.monotonic() - began < 0.5 and not out.playing()
    [server] = Server.made
    assert server.playbacks[0].closed and server.closed


def test_no_sound_server_or_a_refusal_plays_nothing() -> None:
    def none() -> Server:
        raise OSError("No sound server to connect to")

    out = output(none)
    assert not out.start(clip()) and not out.playing()
    refused = output(lambda: Server(refuses=True))
    assert not refused.start(clip())
    deadline = time.monotonic() + 1
    while refused.playing():
        assert time.monotonic() < deadline
        time.sleep(0.01)
    assert Server.made[0].closed


def test_homes_sample_plays_as_16_bit_and_stops() -> None:
    aloud = PlayAloud(lambda: output(lambda: Server(5.0)))
    audio = np.array([0.0, 0.5, -1.0, 2.0], dtype=np.float32)
    assert aloud.play(audio, 16_000)
    played = Server.made[0].playbacks[0]
    assert played.rate == 16_000 and played.channels == 1
    assert played.pcm == pcm16(audio)
    assert aloud.play(audio, 16_000)  # a second stops the first
    assert played.closed
    aloud.stop()
    assert Server.made[1].playbacks[0].closed


def test_samples_are_clipped_to_16_bit() -> None:
    out = np.frombuffer(pcm16(np.array([0.5, 1.5, -1.5], dtype=np.float32)), "<i2")
    assert out.tolist() == [16383, 32767, -32767]


def test_a_sound_waits_for_its_start_at_most_a_while(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sound, "STARTED_SEC", 0.1)

    def slow() -> Server:
        time.sleep(0.5)
        raise OSError("The sound server didn't answer")

    began = time.monotonic()
    assert not output(slow).start(clip())
    assert time.monotonic() - began < 0.4
