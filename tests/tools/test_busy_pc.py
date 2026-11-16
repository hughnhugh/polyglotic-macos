"""How busy the PC is (`tools.busy_pc`, decision 0040): read from the
system's own CPU counters on Windows and Linux, and only a saturated PC
earns an action over budget more tries."""

import sys

import pytest

from tools import busy_pc


@pytest.mark.skipif(
    sys.platform not in ("win32", "linux"), reason="reads Windows' or Linux's counters"
)
def test_the_load_is_read_as_a_share_of_the_cpu() -> None:
    share = busy_pc.busy_share(0.05)
    assert share is not None and 0.0 <= share <= 1.0


def test_only_a_saturated_pc_counts() -> None:
    assert busy_pc.saturated(0.5) and busy_pc.saturated(1.0)
    assert not busy_pc.saturated(0.49)  # busy, not saturated
    assert not busy_pc.saturated(None)  # unknown: no more tries


def test_the_load_is_said_in_words() -> None:
    assert busy_pc.describe(0.966) == "the PC 97% busy"
    assert busy_pc.describe(None) == "the PC's load unknown"


def test_a_calm_pc_is_waited_for_and_given_up_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The start's tries wait for a calm PC (decision 0103): until a
    reading is under the level, or the wait is up - then the last reading."""
    readings = iter([0.6, 0.45, 0.2, 0.9])
    monkeypatch.setattr(busy_pc, "busy_share", lambda seconds: next(readings))
    assert busy_pc.wait_for_calm(0.3, most_seconds=60, sample=0) == 0.2
    monkeypatch.setattr(busy_pc, "busy_share", lambda seconds: 0.7)
    assert busy_pc.wait_for_calm(0.3, most_seconds=0, sample=0) == 0.7  # given up
    monkeypatch.setattr(busy_pc, "busy_share", lambda seconds: None)
    assert busy_pc.wait_for_calm(0.3, most_seconds=60, sample=0) is None  # unknown


def test_a_level_below_saturated_counts_as_busy_where_a_test_says() -> None:
    assert busy_pc.saturated(0.35, busy_pc.CALM)
    assert not busy_pc.saturated(0.29, busy_pc.CALM)
    assert not busy_pc.saturated(0.35)  # saturated is still half


def test_the_rest_of_the_pc_leaves_this_process_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Over a span of 100 units of the PC's CPU time, 30 idle and 70 busy,
    20 of them this process's own: the rest of the PC was 50 % busy."""
    unit = busy_pc._seconds_per_unit()
    times = iter([(1000.0, 5000.0), (1030.0, 5100.0)])
    own = iter([2.0, 2.0 + 20 * unit])
    monkeypatch.setattr(busy_pc, "_cpu_times", lambda: next(times))
    monkeypatch.setattr(busy_pc.time, "process_time", lambda: next(own))
    assert busy_pc.OthersMeanwhile().share() == pytest.approx(0.5)


@pytest.mark.skipif(
    sys.platform not in ("win32", "linux"), reason="reads Windows' or Linux's counters"
)
def test_the_rest_of_the_pc_is_read_as_a_share() -> None:
    others = busy_pc.OthersMeanwhile()
    sum(range(2_000_000))  # this process's own work, left out
    share = others.share()
    assert share is None or 0.0 <= share <= 1.0  # None: too short to tick
