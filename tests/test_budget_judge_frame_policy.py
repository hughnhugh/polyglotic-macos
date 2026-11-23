"""The frame budget on the shared Linux PR runner (Polyglotic HQ 711)."""

import os
from pathlib import Path

import pytest
from tests import budget_judge
from tests.budget_judge import Sampled, within

from polyglotic_desktop.perf import budgets
from tools import timing_record


@pytest.fixture(autouse=True)
def shared_linux_pull_request(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(budget_judge.sys, "platform", "linux")
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("GITHUB_EVENT_NAME", "pull_request")
    monkeypatch.setenv("RUNNER_ENVIRONMENT", "self-hosted")
    monkeypatch.setenv("POLYGLOTIC_TIMING_RECORD", str(tmp_path))
    monkeypatch.setattr(budget_judge, "JUDGED", [])


def test_quiet_linux_pr_reports_a_frame_median_miss(
    capsys: pytest.CaptureFixture[str],
) -> None:
    within(budgets.FRAME, lambda: Sampled((8.2, 8.8, 50.0), busy=0.1))
    (judged,) = budget_judge.JUDGED
    assert judged.passed and judged.notice
    assert "timing notice" in budget_judge.summary_lines()[0]
    assert "frame 8 | 8.8 | 50.0" in budget_judge.summary_markdown()
    assert "::warning title=Timing notice::" in capsys.readouterr().out


def keep_main_timing() -> None:
    test = os.environ["PYTEST_CURRENT_TEST"].split(" (")[0]
    assert timing_record.save(
        budget_judge.RECORD_KIND, {test: timing_record.Timing(9.0, 51.0)}, "main"
    )


@pytest.mark.parametrize(
    "metadata",
    [
        {"RUNNER_ENVIRONMENT": "github-hosted"},
        {"GITHUB_EVENT_NAME": "push"},
        {"platform": "win32"},
        {"GITHUB_ACTIONS": ""},
    ],
    ids=("github-hosted", "linux-push", "windows-train", "local"),
)
def test_frame_median_misses_elsewhere_fail(
    monkeypatch: pytest.MonkeyPatch, metadata: dict[str, str]
) -> None:
    for name, value in metadata.items():
        if name == "platform":
            monkeypatch.setattr(budget_judge.sys, name, value)
        else:
            monkeypatch.setenv(name, value)
    keep_main_timing()
    with pytest.raises(AssertionError, match="frame over its 8 ms"):
        within(budgets.FRAME, lambda: Sampled((9.0,), busy=0.1))


def test_linux_pr_still_fails_a_frame_slot_miss() -> None:
    keep_main_timing()
    with pytest.raises(AssertionError, match="any one run 50 ms"):
        within(budgets.FRAME, lambda: Sampled((7.0, 7.0, 51.0), busy=0.1))


def test_linux_pr_still_fails_other_median_misses() -> None:
    with pytest.raises(AssertionError, match="new_caption over its 4 ms"):
        within(budgets.NEW_CAPTION, lambda: Sampled((5.0,), busy=0.1))
