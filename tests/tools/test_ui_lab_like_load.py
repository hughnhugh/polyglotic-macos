"""A pull request's timings beside main's at like load (polyglotic-hq 381,
decision 0169): main's record is scaled by the state's reference step now
over its step in main's run, so a busy PC running unchanged code is "over
its budget as main is", and a change that doubles an action fails on a
calm or a busy PC alike. The PC's speed is set here (the reference step's
time), never read."""

from pathlib import Path

import pytest
from PySide6.QtWidgets import QLabel, QWidget
from tests.tools.test_ui_lab import LabClock, clicks_taking
from tools.ui_lab import __main__ as cli
from tools.ui_lab import lab, new_parts, reference

from tools import busy_pc, timing_record

MAIN = timing_record.kind(100, "normal", "en")
CLICK = "ui_next.clicks: click"
STEP = f"ui_next.clicks: {reference.NAME}"


def gate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    state: lab.State,
    event: str,
    step_ms: float,
    cpu_load: float,
    capsys: pytest.CaptureFixture[str],
) -> tuple[int, str]:
    """The lab's gate on `state` alone, as CI runs it on a pull request or
    a push to main, the reference step taking `step_ms`: its exit code and
    what it said. The synthetic reference duration and absolute CPU load
    are independent: the former models relative machine speed, while the
    latter decides whether this run is safe to measure."""
    monkeypatch.setattr(new_parts, "STATES", [state])
    monkeypatch.setattr(cli, "new_states", lambda: list(new_parts.STATES))
    monkeypatch.setattr(cli.goldens, "GOLDENS", None)  # the budgets alone
    monkeypatch.setattr(reference, "time_step", lambda app: step_ms)
    monkeypatch.setattr(lab, "time", LabClock())
    monkeypatch.setattr(busy_pc, "busy_share", lambda seconds=0.2: cpu_load)
    monkeypatch.setattr(busy_pc, "wait_for_calm", lambda *args, **kwargs: cpu_load)
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.setenv("POLYGLOTIC_TIMING_RECORD", str(tmp_path / "records"))
    monkeypatch.setenv("GITHUB_EVENT_NAME", event)
    monkeypatch.setenv(
        "GITHUB_REF", "refs/heads/main" if event == "push" else "refs/pull/1/merge"
    )
    monkeypatch.setenv("GITHUB_SHA", "abcdef1234567890")
    code = cli.main(["--gate", "--out", str(tmp_path / "out")])
    return code, capsys.readouterr().err


def mains_record(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, step: bool) -> None:
    """Main's clicks at 30 ms - on a PC whose reference step took 2 ms, if
    `step` (a record kept before 0169 has none)."""
    monkeypatch.setenv("POLYGLOTIC_TIMING_RECORD", str(tmp_path / "records"))
    timings = {CLICK: timing_record.Timing(30.0, 30.0)}
    if step:
        timings[STEP] = timing_record.Timing(2.0, 2.0)
    timing_record.save(MAIN, timings, "1234abcd")


@pytest.mark.parametrize(
    ("click_ms", "step_ms", "fails"),
    [(50.0, 3.4, 0), (100.0, 3.4, 1), (60.0, 2.0, 1)],
    ids=[
        "slower reference, unchanged",
        "slower reference, twice as slow",
        "same reference, twice as slow",
    ],
)
def test_a_pull_request_is_judged_beside_main_at_like_load(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    click_ms: float,
    step_ms: float,
    fails: int,
) -> None:
    """367: Settings' section switch at 9.9 ms on a loaded pull request
    against main's calm 5.33 ms - 1.86x, over 0136's 1.5x - with nothing
    changed. Main's clicks at 30 ms with its step at 2 ms. On a PC 1.7x as
    slow (the step at 3.4 ms), clicks at 50 ms are main's code there. With
    the explicit quiet CPU sample these remain measurable: over
    their budget as main is, not failed. Twice main's at that load (100
    ms), or twice main's on a calm PC (60 ms, the step as main's), fail."""
    mains_record(tmp_path, monkeypatch, step=True)
    code, said = gate(
        tmp_path,
        monkeypatch,
        clicks_taking(click_ms),
        "pull_request",
        step_ms,
        0.1,
        capsys,
    )
    assert code == fails, said
    if fails:
        assert f"over budget - {CLICK}" in said
        assert f"slower than main's - {CLICK}" in said
    else:
        assert f"over its budget as main is - {CLICK} - median" in said
        assert "the PC 1.70x as slow as for main's" in said


def test_a_record_kept_before_the_reference_step_is_compared_as_it_was(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Main's record from before 0169 has no step: 0136 as it was, so a
    slower-reference pull request's clicks at 1.67x main's still fail until main's next
    run keeps one."""
    mains_record(tmp_path, monkeypatch, step=False)
    code, said = gate(
        tmp_path, monkeypatch, clicks_taking(50), "pull_request", 3.4, 0.1, capsys
    )
    assert code == 1 and f"over budget - {CLICK}" in said


def test_main_keeps_each_gated_states_reference_step_in_its_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    gate(tmp_path, monkeypatch, clicks_taking(5), "push", 2.5, 0.1, capsys)
    record = timing_record.load(MAIN)
    assert record is not None
    assert record.timings[STEP] == timing_record.Timing(2.5, 2.5)
    assert CLICK in record.timings


def test_genuinely_busy_samples_are_warned_and_not_recorded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    code, said = gate(
        tmp_path, monkeypatch, clicks_taking(60), "pull_request", 2.0, 0.4, capsys
    )
    assert code == 0
    assert "timing not measured (busy)" in said
    assert timing_record.load(MAIN) is None


def test_the_reference_step_is_timed_before_a_gated_state_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    timed: list[str] = []

    def step(app: object) -> float:
        timed.append("step")
        return 2.0

    monkeypatch.setattr(reference, "time_step", step)

    def state(lab_: lab.Lab) -> QWidget:
        timed.append("state")
        return QLabel("state")

    gated, recorded = lab.run(
        [
            lab.State("ui.gated", state, gated=True),
            lab.State("ui.not", state, gated=False),
        ],
        tmp_path,
    )
    assert timed == ["step", "state", "state"]
    assert gated.reference_ms == 2.0 and recorded.reference_ms is None


def test_the_reference_step_takes_a_few_milliseconds() -> None:
    """The real step: short enough to time before every gated state."""
    step = reference.time_step(lab.application())
    assert 0 < step < 50


def test_a_states_load_scale_is_its_neighbours_median_step() -> None:
    """One state's step alone varies by about a fifth on one load: each
    state's scale is the median of its own and its neighbours' steps, now
    over main's, so one slow step among them moves nothing."""
    record = timing_record.Record(
        "1234abcd",
        {f"s{n}: {reference.NAME}": timing_record.Timing(2.0, 2.0) for n in range(13)},
    )
    now = {f"s{n}: {reference.NAME}": timing_record.Timing(3.0, 3.0) for n in range(13)}
    now[f"s6: {reference.NAME}"] = timing_record.Timing(10.0, 10.0)  # one slow step
    now[f"new: {reference.NAME}"] = timing_record.Timing(3.0, 3.0)  # not in main's
    scales = cli.load_scales(now, record)
    assert set(scales) == {f"s{n}" for n in range(13)}
    assert all(scale == pytest.approx(1.5) for scale in scales.values())
