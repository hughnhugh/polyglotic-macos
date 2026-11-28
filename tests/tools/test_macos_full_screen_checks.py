"""The Mac's parity checks (polyglotic-hq 429): where a caption window is
against a full-screen app, judged from the window list's order; the plan;
and the macOS job running them and keeping what they found."""

from pathlib import Path
from unittest.mock import Mock

import pytest
import yaml
from PySide6.QtCore import QPoint, QRect
from PySide6.QtGui import QCursor
from tools.macos_full_screen_checks import (
    FAIL,
    PASS,
    UNKNOWN,
    Result,
    Run,
    above,
    exit_code,
    full_screen_verdict,
    plan,
)

from polyglotic_desktop.platform.macos import keys
from polyglotic_desktop.platform.macos.window_list import Listed
from tools import macos_full_screen_checks

OURS, TEXTEDIT = 1, 2
BOX = (0.0, 0.0, 10.0, 10.0)


def test_a_caption_window_listed_before_the_full_screen_app_is_above_it() -> None:
    listed = [
        Listed(5, 1000, OURS, BOX),
        Listed(7, 0, TEXTEDIT, BOX),
        Listed(8, 25, 3, BOX),
    ]
    assert above(listed, 5, TEXTEDIT) == (True, True)


def test_listed_after_it_is_below() -> None:
    listed = [Listed(7, 0, TEXTEDIT, BOX), Listed(5, 8, OURS, BOX)]
    assert above(listed, 5, TEXTEDIT) == (True, False)


def test_not_listed_is_not_on_this_space() -> None:
    assert above([Listed(7, 0, TEXTEDIT, BOX)], 5, TEXTEDIT) == (False, False)
    assert above([Listed(5, 1000, OURS, BOX)], 5, TEXTEDIT) == (
        True,
        False,
    )  # no TextEdit


def test_the_verdicts() -> None:
    assert full_screen_verdict(True, True, True, True)[0] == PASS
    assert full_screen_verdict(False, False, True, True)[0] == FAIL
    assert full_screen_verdict(True, True, False, True)[0] == FAIL  # it took the front
    assert full_screen_verdict(True, True, True, False)[0] == UNKNOWN


def test_only_a_fail_fails_the_run() -> None:
    assert exit_code([Result("a", PASS, ""), Result("b", UNKNOWN, "")]) == 0
    assert exit_code([Result("a", FAIL, "")]) == 1


def test_the_plan_names_each_check() -> None:
    names = " ".join(plan())
    for check in (
        "full_screen_qt_only",
        "locked",
        "sign",
        "click",
        "shown_after_full_screen",
        "typed",
        "key_combination",
        "key_alone",
        "escape_cancels",
        "click_elsewhere",
        "accessibility_settings",
    ):
        assert check in names


@pytest.mark.parametrize("monitored", [True, False])
def test_click_elsewhere_requires_the_appkit_mouse_down(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, monitored: bool
) -> None:
    run = Run(tmp_path / "full-screen.json")
    window = Mock()
    popover = window.popover
    popover.isVisible.return_value = True
    popover.frameGeometry.return_value = QRect(0, 0, 20, 20)

    def close_popover() -> None:
        popover.isVisible.return_value = False

    popover.close.side_effect = close_popover
    window.toggle_settings.side_effect = lambda: window.keys("mouse")

    mac = Mock()
    mac.button_held.return_value = False
    mac_keys = keys.MacKeys(mac, clock=lambda: 0.0)
    adapter = keys._AppKit.__new__(keys._AppKit)

    def click(_args: list[str]) -> tuple[bool, str]:
        if monitored:
            adapter._heard = mac.add.call_args.args[0]
            adapter._event(1)
        else:
            mac.button_held.return_value = True
        if window.keys("mouse"):
            popover.close()
        return True, ""

    monkeypatch.setattr(keys, "MacKeys", lambda: mac_keys)
    monkeypatch.setattr(keys.objc, "send", lambda *_args, **_kwargs: keys.LEFT_DOWN)
    monkeypatch.setattr(QCursor, "pos", lambda: QPoint(175, 175))
    monkeypatch.setattr(macos_full_screen_checks, "_cliclick", lambda: "cliclick")
    monkeypatch.setattr(run, "window", window, raising=False)
    monkeypatch.setattr(run, "full_screen", Mock())
    monkeypatch.setattr(run, "to_front", Mock())
    monkeypatch.setattr(run, "wait", Mock())
    monkeypatch.setattr(run, "until", lambda done, _seconds: done())
    monkeypatch.setattr(run, "script", lambda *_args: (True, "100,100,100,100"))
    monkeypatch.setattr(run, "run_quietly", click)

    run.click_elsewhere()

    (result,) = run.results
    assert result.facts["monitor_heard_types"] == (
        [keys.LEFT_DOWN] if monitored else []
    )
    assert result.facts["asked_and_true"] == ["mouse"]
    assert result.outcome == (PASS if monitored else FAIL)


def test_the_macos_job_runs_them_by_default_and_keeps_what_they_found() -> None:
    workflow = yaml.safe_load(
        Path(".github/workflows/macos.yml").read_text(encoding="utf-8")
    )
    assert workflow[True]["workflow_dispatch"]["inputs"]["parity"]["default"] is True
    (job,) = workflow["jobs"].values()
    step = next(
        s for s in job["steps"] if "tools.macos_full_screen_checks" in s.get("run", "")
    )
    assert "inputs.parity" in step["if"]
    upload = next(
        s
        for s in job["steps"]
        if s.get("with", {}).get("name") == "macos-${{ github.run_id }}"
    )
    assert "parity/" in upload["with"]["path"]
