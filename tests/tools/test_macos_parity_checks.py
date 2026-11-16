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
        "voice_heard",
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
