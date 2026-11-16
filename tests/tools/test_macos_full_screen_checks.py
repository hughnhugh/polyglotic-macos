"""The Mac's parity checks (polyglotic-hq 429): where a caption window is
against a full-screen app, judged from the window list's order; the plan;
and the macOS job running them and keeping what they found."""

from pathlib import Path

import yaml
from tools.macos_full_screen_checks import (
    FAIL,
    PASS,
    UNKNOWN,
    Result,
    above,
    exit_code,
    full_screen_verdict,
    plan,
)

from polyglotic_desktop.platform.macos.window_list import Listed

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
