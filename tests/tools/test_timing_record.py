"""`tools/timing_record.py`: main's last timings on this PC, and whether an
action is slower than them (polyglotic-hq 344, decision 0136)."""

from pathlib import Path

import pytest
from tools.timing_record import Timing

from tools import timing_record


@pytest.fixture(autouse=True)
def records(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("POLYGLOTIC_TIMING_RECORD", str(tmp_path))
    return tmp_path


def test_twice_as_slow_is_slower_at_the_median_or_the_longest_run() -> None:
    main = Timing(76.0, 99.0)  # the theme change on main, 2026-11-14
    assert Timing(152.0, 99.0).slower_than(main)  # every change twice as slow
    assert Timing(76.0, 198.0).slower_than(main)  # one stall twice as long
    assert not Timing(95.0, 120.0).slower_than(main)  # a busy PC's run of it


def test_main_s_record_is_kept_and_read_back() -> None:
    kind = timing_record.kind(200, "largest", "zh_CN")
    assert kind == "lab-200-largest-zh_CN"
    assert timing_record.load(kind) is None
    assert timing_record.save(
        kind, {"ui_next.w4_theme_change: theme": Timing(76.5, 99.9)}, "f8b0c015"
    )
    record = timing_record.load(kind)
    assert record is not None and record.commit == "f8b0c015"
    assert record.timings == {"ui_next.w4_theme_change: theme": Timing(76.5, 99.9)}


def test_a_record_that_cant_be_read_is_none(records: Path) -> None:
    (records / "timings-lab-100-normal-en-main-ci.json").write_text(
        "{not json", encoding="utf-8"
    )
    assert timing_record.load("lab-100-normal-en") is None


def test_off_windows_the_record_is_in_the_runners_home_not_its_checkout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    r"""CI's Linux runner cleans the job's checkout for each job: a record
    kept there (`C:\ProgramData` is a relative folder on Linux) would be
    gone by the next pull request (polyglotic-hq 563)."""
    monkeypatch.delenv("POLYGLOTIC_TIMING_RECORD")
    assert timing_record._folder("linux") == Path.home() / ".polyglotic-ci"
    assert timing_record._folder("win32") == timing_record.start_record.RECORD_FOLDER
