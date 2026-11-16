"""`--check-capture` (polyglotic-hq 412): the packed app's capture tried once
on GitHub's Mac, proving catap's and PortAudio's libraries load inside the
bundle - counts and a level in its report, never the audio, and refused on
Windows, where it would hear the PC it runs on (the user's)."""

import json
from pathlib import Path

import numpy as np

from polyglotic_desktop import main
from polyglotic_desktop.ports.capture import AudioCallback


class FakeCapture:
    """Delivers `level` once when started."""

    made = 0

    def __init__(self, level: float, error: str | None = None) -> None:
        FakeCapture.made += 1
        self.level = level
        self._error = error
        self.stopped = False

    def start(self, on_audio: AudioCallback) -> None:
        on_audio(0.0, np.full(1600, self.level, dtype="<f4").tobytes())

    def stop(self) -> None:
        self.stopped = True

    @property
    def capturing(self) -> str | None:
        return "BlackHole 2ch"

    @property
    def error(self) -> str | None:
        return self._error


def test_each_source_heard_is_reported_without_its_audio(tmp_path: Path) -> None:
    report = tmp_path / "capture.json"
    made: list[FakeCapture] = []

    def source(level: float, error: str | None = None) -> FakeCapture:
        made.append(FakeCapture(level, error))
        return made[-1]

    code = main.check_capture(
        report,
        "macos-26",
        {"system": lambda: source(0.25), "mic": lambda: source(0.0, "not allowed")},
        seconds=0.02,
    )
    found = json.loads(report.read_text(encoding="utf-8"))
    assert code == 1 and found["ok"] is False  # the mic heard nothing
    assert found["system"] == {
        "capturing": "BlackHole 2ch",
        "error": None,
        "pieces": 1,
        "seconds": 0.1,
        "peak": 0.25,
        "heard": True,
    }
    assert found["mic"]["heard"] is False and found["mic"]["error"] == "not allowed"
    assert all(m.stopped for m in made)


def test_a_capture_that_cannot_start_is_named_by_its_type(tmp_path: Path) -> None:
    def broken() -> FakeCapture:
        raise OSError("Couldn't start the tap: NativeCoreAudioUnavailable")

    report = tmp_path / "capture.json"
    assert main.check_capture(report, "macos-26", {"system": broken}, 0.01) == 1
    assert (
        json.loads(report.read_text(encoding="utf-8"))["system"]["error"] == "OSError"
    )


def test_every_source_heard_passes(tmp_path: Path) -> None:
    sources = {"system": lambda: FakeCapture(0.1), "mic": lambda: FakeCapture(0.2)}
    assert main.check_capture(tmp_path / "c.json", "macos-15", sources, 0.01) == 0


def test_it_is_refused_on_windows_without_starting_anything(tmp_path: Path) -> None:
    """The self-hosted runners are the user's own PC: their real audio."""
    FakeCapture.made = 0
    report = tmp_path / "capture.json"
    code = main.check_capture(
        report, "windows-11", {"system": lambda: FakeCapture(0.5)}, 0.01
    )
    assert code == 1 and FakeCapture.made == 0
    assert (
        "refused on Windows" in json.loads(report.read_text(encoding="utf-8"))["error"]
    )


def test_the_flag_is_there_hidden_and_takes_no_copy_lock() -> None:
    args = main.arguments(["--check-capture", "out.json"])
    assert args.check_capture == Path("out.json")
    assert main.this_copy(["--check-capture", "out.json"]) is None
