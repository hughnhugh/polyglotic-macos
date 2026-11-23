"""Linux's voice heard for real (polyglotic-hq 591): on GitHub's Ubuntu
runner, in `linux.yml`'s desktop session (PipeWire's pulse server, an
output "Speakers"), with Ubuntu's own speech-dispatcher and espeak-ng -
what plays is recorded at the default output's monitor, 20 ms at a time,
and measured: when sound came after the ask, for how long, how loud, and
whether the captions' hush covered all of it. `linux_desktop`: skipped
everywhere else. The stand-in speech-dispatcher is `test_linux_voices.py`.

Each test prints its measures (`-s` shows them in the job's log)."""

import json
import math
import os
import struct
import threading
import time
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Self

import numpy as np
import pytest

from polyglotic_desktop.platform.linux import pulse, sound
from polyglotic_desktop.platform.linux.voices import (
    NOT_INSTALLED,
    DispatcherVoices,
    Ssip,
    connect,
)
from polyglotic_desktop.platform.recorded_voices import RecordedVoices, Recordings
from polyglotic_desktop.platform.speaking import Clip, SpeakerThread
from polyglotic_desktop.platform.speech_pipeline import HUSH_AFTER_SEC, HUSH_BEFORE_SEC
from polyglotic_desktop.ports.speaker import RECORDED, Quality, Voice
from polyglotic_desktop.ui_next.views.speech import voice_for

LOUD_DBFS = -45.0
"""A 20 ms piece louder than this is sound (the null sink's silence is
digital zero)."""
PIECE_SEC = 0.02
pytestmark = pytest.mark.linux_desktop


class Monitor:
    """The default output's monitor, recorded on a thread of its own: each
    piece's arrival (`time.perf_counter`, the speaker's clock) and level."""

    def __init__(self) -> None:
        self.levels: list[tuple[float, float]] = []
        self._stop = threading.Event()
        self._ready = threading.Event()
        self.error: str | None = None
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        try:
            server = pulse.PulseServer("Polyglotic voice check")
        except OSError as error:
            self.error = str(error)
            self._ready.set()
            return
        try:
            output = server.server_info().output
            monitor = next(s.monitor for s in server.sinks() if s.name == output)
            assert monitor is not None
            recording = server.record(monitor)
            self._ready.set()
            while not self._stop.is_set():
                server.run(PIECE_SEC)
                for arrival, data in recording.take():
                    samples = np.frombuffer(data, dtype="<f4")
                    rms = float(np.sqrt(np.mean(samples.astype(np.float64) ** 2)))
                    level = 20 * math.log10(rms) if rms > 1e-9 else -120.0
                    self.levels.append((arrival, level))
            recording.close()
        except Exception as error:  # noqa: BLE001 - reported by the test
            self.error = f"{type(error).__name__}: {error}"
        finally:
            server.close()
            self._ready.set()

    def __enter__(self) -> Self:
        self._thread.start()
        assert self._ready.wait(10) and self.error is None, self.error
        time.sleep(0.3)  # the stream settles
        return self

    def __exit__(self, *_: object) -> None:
        time.sleep(0.5)  # the tail
        self._stop.set()
        self._thread.join(5)

    def loud(self, after: float = 0.0) -> list[tuple[float, float]]:
        return [(at, db) for at, db in self.levels if db > LOUD_DBFS and at >= after]


def measures(monitor: Monitor, asked: float) -> dict[str, float]:
    """When sound came after the ask, for how long, and how loud."""
    loud = monitor.loud(asked)
    assert loud, f"nothing heard at the monitor: {monitor.levels[-10:]}"
    return {
        "first_sound_after_ask_ms": round((loud[0][0] - PIECE_SEC - asked) * 1000),
        "sound_seconds": round(loud[-1][0] - loud[0][0] + PIECE_SEC, 2),
        "loud_pieces": len(loud),
        "peak_piece_dbfs": round(max(db for _, db in loud), 1),
    }


def unhushed(
    monitor: Monitor, spans: list[tuple[float, float]], asked: float
) -> list[float]:
    """The loud pieces (by when they began) the captions' hush didn't cover:
    each span with the pipeline's own margins (`SpeechPipeline.hush`)."""
    covered = [(s - HUSH_BEFORE_SEC, s + n + HUSH_AFTER_SEC) for s, n in spans]
    return [
        round(at - PIECE_SEC - asked, 3)
        for at, _ in monitor.loud(asked)
        if not any(low <= at - PIECE_SEC <= high for low, high in covered)
    ]


@contextmanager
def speaker_over(voices: DispatcherVoices | RecordedVoices) -> Iterator[SpeakerThread]:
    made = SpeakerThread(voices, sound.PulseOutput)
    try:
        made.look_for_voices()
        give_up = time.monotonic() + 15
        while not made.listed:
            assert time.monotonic() < give_up
            time.sleep(0.05)
        yield made
    finally:
        made.close()


class Said:
    def __init__(self) -> None:
        self.spans: list[tuple[float, float]] = []
        self.ended: list[bool] = []
        self.done = threading.Event()

    def say(self, speaker: SpeakerThread, text: str, voice: Voice) -> float:
        def ended(heard: bool) -> None:
            self.ended.append(heard)
            self.done.set()

        asked = time.perf_counter()
        speaker.say(text, voice, 1.0, lambda s, n: self.spans.append((s, n)), ended)
        return asked


def report(name: str, found: Mapping[str, object]) -> None:
    """Printed, and kept in `$OUT/voice-heard.jsonl` where the job keeps
    its findings (linux.yml)."""
    print(f"591 {name}: {json.dumps(found)}")
    out = os.environ.get("OUT")
    if out:
        with (Path(out) / "voice-heard.jsonl").open("a", encoding="utf-8") as file:
            file.write(json.dumps({"check": name, **found}) + "\n")


def test_speech_dispatchers_voices_are_listed_plain_and_basic() -> None:
    voices = DispatcherVoices()
    try:
        began = time.perf_counter()
        found = voices.found()
        took = time.perf_counter() - began
        again = time.perf_counter()
        voices.found()
        second = time.perf_counter() - again
    finally:
        voices.close()
    tags = {v.language for v in found}
    report("voices", {"count": len(found), "first_listing_s": round(took, 2),
                      "next_listing_s": round(second, 3), "languages": len(tags)})  # fmt: skip
    assert {"en-US", "zh-CN", "zh-HK", "fr-FR", "es-ES", "ja", "ko", "vi"} <= tags
    assert {v.quality for v in found} == {Quality.BASIC}
    assert all("+" not in v.name for v in found) and len(found) < 400
    assert voice_for(found, "zh") is not None and voice_for(found, "yue") is not None


def test_a_word_said_by_speech_dispatcher_is_heard_and_hushed_throughout() -> None:
    said = Said()
    with speaker_over(DispatcherVoices()) as speaker:
        english = voice_for(speaker.voices(), "en")
        assert english is not None and english.id.startswith("speechd:")
        with Monitor() as monitor:
            asked = said.say(speaker, "Hello, this is the system voice.", english)
            assert said.done.wait(15)
        found = measures(monitor, asked)
        missed = unhushed(monitor, said.spans, asked)
        last_sound = monitor.loud(asked)[-1][0]
        hushed_to = max(s + n for s, n in said.spans) + HUSH_AFTER_SEC
        found.update(
            hush_spans=len(said.spans),
            hush_past_last_sound_s=round(hushed_to - last_sound, 2),
            unhushed=len(missed),
            heard_to_its_end=said.ended == [True],
        )
        report("speech-dispatcher word", found)
    assert said.ended == [True]
    assert found["sound_seconds"] >= 0.8 and found["peak_piece_dbfs"] > -30
    assert found["first_sound_after_ask_ms"] < 1500
    assert missed == []  # never captioned: hushed all the time it played
    assert hushed_to - last_sound < 1.5  # and not much longer


def test_a_word_stopped_stops_its_sound() -> None:
    said = Said()
    with speaker_over(DispatcherVoices()) as speaker:
        english = voice_for(speaker.voices(), "en")
        assert english is not None
        long = "This is a much longer sentence, one that is stopped before it ends."
        with Monitor() as monitor:
            asked = said.say(speaker, long, english)
            give_up = time.perf_counter() + 5
            while not monitor.loud(asked):
                assert time.perf_counter() < give_up
                time.sleep(0.02)
            time.sleep(0.6)
            stopped = time.perf_counter()
            speaker.stop()
            assert said.done.wait(5)
        last = monitor.loud(asked)[-1][0]
        found = {"sound_after_stop_ms": round((last - stopped) * 1000),
                 **measures(monitor, asked)}  # fmt: skip
        report("speech-dispatcher stopped", found)
    assert said.ended == [False]
    assert last - stopped < 0.35


def tone(seconds: float, rate: int, amplitude: float = 0.5, hz: float = 440) -> Clip:
    count = round(seconds * rate)
    samples = (
        round(amplitude * 32767 * math.sin(2 * math.pi * hz * i / rate))
        for i in range(count)
    )
    return Clip(struct.pack(f"<{count}h", *samples), rate)


class Recorded:
    """A pack's recorded words: "bonjour" only (its sound made by `decode`)."""

    def clip(self, word: str) -> bytes | None:
        return b"ogg" if word == "bonjour" else None


def recorded_voices(dispatcher: DispatcherVoices) -> RecordedVoices:
    recordings = Recordings()
    recordings.use("fr", "fr-FR", "Kokoro", Recorded())
    decode: Callable[[bytes], Clip] = lambda _data: tone(0.8, 24_000)
    return RecordedVoices(dispatcher, recordings, decode=decode)


def test_a_recorded_word_plays_through_the_sound_server() -> None:
    said = Said()
    with speaker_over(recorded_voices(DispatcherVoices())) as speaker:
        ours = next(v for v in speaker.voices() if v.id.startswith(RECORDED))
        with Monitor() as monitor:
            asked = said.say(speaker, "bonjour", ours)
            assert said.done.wait(10)
        found = measures(monitor, asked)
        missed = unhushed(monitor, said.spans, asked)
        found.update(unhushed=len(missed), clip_seconds=0.8)
        report("recording", found)
    assert said.ended == [True] and missed == []
    # a 0.8 s tone at half scale: RMS -9 dBFS
    assert 0.65 <= found["sound_seconds"] <= 1.0
    assert -12 < found["peak_piece_dbfs"] < -6


def test_without_speech_dispatcher_a_recording_still_plays() -> None:
    def missing(_path: Path) -> object:
        raise FileNotFoundError(2, "No such file or directory")

    def no_dispatcher() -> Ssip:
        return connect({"XDG_RUNTIME_DIR": "/nonexistent-591"}, which=lambda _: None,
                       open_socket=missing)  # type: ignore[arg-type]  # fmt: skip

    with pytest.raises(OSError, match=NOT_INSTALLED):
        no_dispatcher()
    said = Said()
    with speaker_over(
        recorded_voices(DispatcherVoices(connection=no_dispatcher))
    ) as speaker:
        voices = speaker.voices()
        assert [v.id for v in voices] == [f"{RECORDED}fr"]
        with Monitor() as monitor:
            asked = said.say(speaker, "bonjour", voices[0])
            assert said.done.wait(10)
        found = measures(monitor, asked)
        report("recording without speech-dispatcher", found)
    assert said.ended == [True] and found["sound_seconds"] >= 0.65


def test_homes_sample_is_played_aloud_and_stops() -> None:
    rate = 16_000
    audio = (0.5 * np.sin(2 * np.pi * 330 * np.arange(rate * 2) / rate)).astype(
        "float32"
    )
    aloud = sound.PlayAloud()
    with Monitor() as monitor:
        asked = time.perf_counter()
        assert aloud.play(audio, rate)
        time.sleep(0.8)
        stopped = time.perf_counter()
        aloud.stop()
        time.sleep(0.5)
    found = measures(monitor, asked)
    last = monitor.loud(asked)[-1][0]
    found["sound_after_stop_ms"] = round((last - stopped) * 1000)
    report("Home's sample", found)
    assert found["sound_seconds"] >= 0.5 and last - stopped < 0.35
    assert -12 < found["peak_piece_dbfs"] < -6
