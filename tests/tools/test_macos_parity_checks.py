"""The macOS job's parity part (polyglotic-hq 428): its plan, its picture of
the menu-bar icon and its place in the job - here on any OS; the checks
themselves run on GitHub's Mac (.github/workflows/macos.yml)."""

from collections.abc import Iterator
from pathlib import Path

import pytest
import yaml
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

from tools import macos_parity_checks as parity

WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "macos.yml"


@pytest.fixture
def qapp() -> Iterator[QApplication]:
    app = QApplication.instance() or QApplication(["test"])
    assert isinstance(app, QApplication)
    yield app


def test_the_plan_names_each_check() -> None:
    assert parity.main(["build/parity", "--dry-run"]) == 0
    steps = parity.plan(Path("dist/Polyglotic.app"))
    names = [step.split(":", 1)[0] for step in steps]
    assert names == [
        "hotkeys_pressed",
        "hotkeys_taken",
        "menu_keys",
        "voices_listed",
        "voice_made",
        "voice_moved",
        "voice_heard",
        "said_recorded",
        "said_by_macos",
        "menu_bar",
        "login_item",
    ]
    assert "login_item" not in "".join(parity.plan(None))


def test_the_keys_are_pressed_with_control_and_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: list[list[str]] = []

    def run(command: list[str], _seconds: int) -> dict[str, object]:
        sent.append(command)
        return {}

    monkeypatch.setattr(parity, "run", run)
    parity.keystroke("L")
    assert sent[0][:2] == ["osascript", "-e"]
    assert 'keystroke "l" using {control down, command down}' in sent[0][2]


def test_the_picture_draws_the_template_light_and_dark(
    qapp: QApplication, tmp_path: Path
) -> None:
    picture = tmp_path / "menu-bar.png"
    parity.drawn_as_macos(picture)
    image = QImage(str(picture))
    # the listening icon's square: black on the light bar, white on the dark
    assert image.pixelColor(12 + 18, 12 + 18).name() == "#000000"
    assert image.pixelColor(12 + 18, 60 + 12 + 18).name() == "#ffffff"


def test_the_job_runs_the_parity_part_by_default() -> None:
    job = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    inputs = job[True]["workflow_dispatch"]["inputs"]  # "on" reads as True
    assert inputs["parity"]["default"] is True
    steps = job["jobs"]["macos"]["steps"]
    step = next(s for s in steps if "macos_parity_checks" in s.get("run", ""))
    assert "inputs.parity" in step["if"]


def test_voice_heard_keeps_why_the_speaker_gave_up() -> None:
    """443: `voice_heard` failed with "ended [False]" in two GitHub Mac runs
    of five and nothing said why; the speaker's warning is kept now."""
    import logging

    speaking = logging.getLogger("polyglotic_desktop.platform.speaking")
    with parity.warnings_of("polyglotic_desktop.platform.speaking") as why:
        speaking.warning("couldn't play a word: %s", "no output device")
        speaking.info("not a warning")
    speaking.warning("after: not kept")
    assert why == ["couldn't play a word: no output device"]


# -- sound out (polyglotic-hq 523) ------------------------------------------------------


def _tone(seconds: float, hz: float = parity.TONE_HZ, level: float = 0.3) -> object:
    import numpy as np

    rate = parity.HEARD_RATE
    t = np.arange(int(seconds * rate)) / rate
    quiet = np.zeros(rate // 2)
    return np.concatenate([quiet, level * np.sin(2 * np.pi * hz * t), quiet])


def test_a_word_heard_as_made_has_no_problem() -> None:
    found = parity.listened(_tone(parity.TONE_SEC), parity.HEARD_RATE)
    assert found["voiced_sec"] == pytest.approx(parity.TONE_SEC, abs=0.03)
    assert found["pitch_hz"] == pytest.approx(parity.TONE_HZ, rel=0.01)
    assert parity.sound_problems(found, parity.TONE_SEC, parity.TONE_HZ) == []


def test_silence_clipping_quiet_and_a_wrong_rate_are_each_said() -> None:
    import numpy as np

    def problems(samples: object) -> list[str]:
        found = parity.listened(samples, parity.HEARD_RATE)
        return parity.sound_problems(found, parity.TONE_SEC, parity.TONE_HZ)

    assert problems(np.zeros(parity.HEARD_RATE)) == ["nothing heard: silent"]
    clipped = np.clip(_tone(parity.TONE_SEC, level=3.0), -1.0, 1.0)  # type: ignore[call-overload]
    assert any(p.startswith("clipped") for p in problems(clipped))
    assert any(p.startswith("too quiet") for p in problems(_tone(0.7, level=0.004)))
    # played at twice the rate: half as long, an octave up
    fast = problems(_tone(parity.TONE_SEC / 2, hz=2 * parity.TONE_HZ))
    assert [p.split(": ")[-1] for p in fast] == ["the wrong speed", "the wrong rate"]


def test_a_voice_is_judged_on_its_length_alone() -> None:
    """macOS's voices have no one pitch: a quarter longer or shorter is
    still their own pace; more is a wrong rate."""
    found = parity.listened(_tone(1.1), parity.HEARD_RATE)
    assert parity.sound_problems(found, 1.0, None) == []
    found = parity.listened(_tone(1.5), parity.HEARD_RATE)
    assert parity.sound_problems(found, 1.0, None) == [
        "1.5 s heard of 1.000 s made: the wrong speed"
    ]


def test_the_stand_in_recording_decodes_as_the_packs_words_do() -> None:
    """The tone goes through the recorded words' own decoder (libsndfile,
    Ogg Opus at 24 kHz), as a pack's word does."""
    from polyglotic_desktop.platform.recorded_voices import clip_of_ogg

    clip = clip_of_ogg(parity.tone_ogg())
    assert clip.rate == 24_000 and clip.channels == 1
    assert parity.voiced_seconds_of_clip(clip) == pytest.approx(
        parity.TONE_SEC, abs=0.04
    )
