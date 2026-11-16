"""Main's last runs of the start with real windows, as the recorded start
prints them (`test_start_with_real_windows.history_line`, polyglotic-hq
322): what whether it holds steady is read from (decision 0111)."""

from tests.ui.test_start_with_real_windows import LAST_RUNS, history_line


def test_with_no_runs_kept_it_says_so() -> None:
    assert "none kept" in history_line([])


def test_the_last_runs_median_and_range_and_how_many_were_calm() -> None:
    rows: list[dict[str, object]] = [
        {"window_ms": 5000.0, "answered_ms": 9000.0, "busy": 0.9}  # too old to count
    ]
    rows += [
        {
            "window_ms": 700.0 + n,
            "answered_ms": 900.0 + n,
            "busy": 0.1 if n % 2 else 0.6,
        }
        for n in range(LAST_RUNS)
    ]

    line = history_line(rows)

    assert f"last {LAST_RUNS} runs" in line
    assert "window 710 ms (700-719)" in line  # the median, then the range
    assert "answering by 910 ms (900-919)" in line
    assert f"{LAST_RUNS // 2} of them on a calm PC" in line


def test_a_run_that_never_answered_still_counts_its_window() -> None:
    line = history_line([{"window_ms": 800.0, "answered_ms": None, "busy": None}])
    assert "window 800 ms (800-800)" in line and "answering" not in line
    assert "0 of them on a calm PC" in line
