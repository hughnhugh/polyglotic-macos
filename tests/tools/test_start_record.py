"""The start's parts (`perf.start_parts`) and main's record of them
(`tools/start_record.py`): a start that grew says which part grew
(polyglotic-hq 314)."""

from pathlib import Path

import pytest
from tools.start_record import Record, grew, table, typical

from polyglotic_desktop.perf import start_parts
from tools import start_record

MAIN = {"learner": 120.0, "page_home": 20.0, "page_settings": 30.0, "first_paint": 30.0}


def test_each_mark_ends_a_part_and_they_add_up() -> None:
    start_parts.begin()
    start_parts.done("learner")
    start_parts.done("page_home")
    start_parts.done("page_home")  # marked twice: added up
    found = start_parts.parts()
    start_parts.end()
    start_parts.done("first_paint")  # after the end: nothing

    assert list(found) == ["learner", "page_home"]  # in the order marked
    assert all(ms >= 0 for ms in found.values())
    assert start_parts.parts() == found


def test_a_mark_before_the_start_begins_does_nothing() -> None:
    """A `Hub` built by a test or the UI lab, not by `main`."""
    start_parts.begin()
    start_parts.end()
    before = start_parts.parts()

    start_parts.done("page_home")

    assert start_parts.parts() == before == {}


def test_a_parts_name_is_a_constant_never_text() -> None:
    start_parts.begin()
    try:
        with pytest.raises(ValueError, match="lower-case"):
            start_parts.done("你好 world")
    finally:
        start_parts.end()


def test_the_typical_start_is_each_parts_median() -> None:
    starts = [
        {"learner": 100.0, "page_home": 20.0},
        {"learner": 140.0, "page_home": 22.0},
        {"learner": 120.0, "page_home": 90.0},  # one slow start
    ]
    assert typical(starts) == {"learner": 120.0, "page_home": 22.0}


def test_15_ms_added_to_one_part_names_that_part() -> None:
    now = dict(MAIN, page_settings=45.0)

    found = grew(now, MAIN)

    assert list(found) == ["page_settings"]
    assert 12 < found["page_settings"] < 15  # 15, less the whole start's growth


def test_a_start_slower_all_round_names_no_part() -> None:
    """A busier PC: every part 30 % slower."""
    assert grew({name: ms * 1.3 for name, ms in MAIN.items()}, MAIN) == {}


def test_a_new_part_grew_by_all_of_it_and_a_small_one_isnt_named() -> None:
    now = dict(MAIN, page_new=25.0, tray=2.0)
    assert list(grew(now, MAIN)) == ["page_new"]


def test_the_table_sets_each_part_beside_mains_and_marks_what_grew() -> None:
    now = {"learner": 120.0, "page_settings": 45.0, "first_paint": 30.0, "tray": 1.0}
    record = Record("0123456789abcdef", 200.0, MAIN)

    text = table(now, record)

    lines = text.splitlines()
    assert lines[0] == (
        "the start's parts (196 ms in all) beside main's at 01234567 (200 ms):"
    )
    assert "GREW" not in lines[1] and "(main 120)" in lines[1]  # learner
    assert "page_settings" in lines[2] and "GREW by 16 ms at this load" in lines[2]
    assert "(new)" in lines[4]  # tray
    assert lines[5] == "  no longer a part: page_home"


def test_with_no_record_the_table_is_the_parts_alone() -> None:
    text = table({"learner": 120.0}, None)
    assert "no record of main's" in text and "GREW" not in text
    assert "learner" in text.splitlines()[1]


def test_mains_record_is_kept_and_the_newest_account_s_is_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Each runner's account writes a file of its own (it can read the
    other's, not write it); the newest is main's last."""
    import os

    monkeypatch.setenv("POLYGLOTIC_START_RECORD", str(tmp_path / "ci"))
    assert start_record.load() is None  # none yet
    monkeypatch.setenv("USERNAME", "runner one")
    assert start_record.save(MAIN, 200.4, "a" * 40)
    monkeypatch.setenv("USERNAME", "runner-two")
    assert start_record.save(dict(MAIN, learner=100.0), 180.0, "b" * 40)
    first = tmp_path / "ci" / "start-parts-main-runnerone.json"
    second = tmp_path / "ci" / "start-parts-main-runnertwo.json"
    os.utime(first, (1_000_000, 1_000_000))  # the older
    os.utime(second, (2_000_000, 2_000_000))

    assert start_record.load() == Record("b" * 40, 180.0, dict(MAIN, learner=100.0))


def test_a_record_that_cant_be_read_or_written_is_left_alone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = tmp_path / "ci"
    folder.mkdir()
    monkeypatch.setenv("POLYGLOTIC_START_RECORD", str(folder))
    (folder / "start-parts-main-x.json").write_text("{not json", encoding="utf-8")
    assert start_record.load() is None
    (folder / "start-parts-main-x.json").write_text('{"commit": 1}', encoding="utf-8")
    assert start_record.load() is None

    monkeypatch.setenv(
        "POLYGLOTIC_START_RECORD", str(folder / "start-parts-main-x.json")
    )
    assert not start_record.save(MAIN, 200.0, "c" * 40)  # a file where the folder goes


def test_only_cis_push_to_main_records() -> None:
    main = {"GITHUB_EVENT_NAME": "push", "GITHUB_REF": "refs/heads/main"}
    assert start_record.on_main(main)
    assert not start_record.on_main(dict(main, GITHUB_EVENT_NAME="pull_request"))
    assert not start_record.on_main(dict(main, GITHUB_REF="refs/heads/314-x"))
    assert not start_record.on_main({})


def test_each_kind_of_start_has_a_record_of_its_own(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The start with real windows beside the gate's (polyglotic-hq 322):
    neither is read as the other's."""
    monkeypatch.setenv("POLYGLOTIC_START_RECORD", str(tmp_path / "ci"))
    real = start_record.with_after(dict(MAIN, first_paint=40.0), 230.0)
    assert list(real)[-1] == start_record.AFTER_PAINT  # after the last part
    assert start_record.with_after(MAIN, None) == MAIN  # it never went on

    assert start_record.save(MAIN, 200.0, "a" * 40)
    assert start_record.save(real, 210.0, "a" * 40, start_record.REAL_WINDOWS)

    assert start_record.load() == Record("a" * 40, 200.0, MAIN)
    assert start_record.load(start_record.REAL_WINDOWS) == Record("a" * 40, 210.0, real)
    text = table(
        real, start_record.load(start_record.REAL_WINDOWS), "with real windows"
    )
    # the whole of each: its parts and the time after the paint
    assert text.splitlines()[0] == (
        "with real windows (440 ms in all) beside main's at aaaaaaaa (440 ms):"
    )


def test_mains_runs_are_kept_in_order_and_the_oldest_go(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("POLYGLOTIC_START_RECORD", str(tmp_path / "ci"))
    monkeypatch.setattr(start_record, "HISTORY_ROWS", 3)
    kind = start_record.REAL_WINDOWS
    assert start_record.history(kind) == []  # none yet
    for account, at in (("one", "2026-11-14T10:00:00"), ("two", "2026-11-14T09:00:00")):
        monkeypatch.setenv("USERNAME", account)
        for n in range(4):
            row = {"at": f"{at[:-1]}{n}", "window_ms": 700.0 + n, "busy": 0.2}
            assert start_record.keep_in_history(row, kind)

    rows = start_record.history(kind)

    assert len(rows) == 6  # each account's last three
    taken = [str(row["at"]) for row in rows]
    assert taken == sorted(taken)
    assert rows[0]["window_ms"] == 701.0  # two's oldest went
    assert start_record.history(start_record.OFFSCREEN) == []  # another kind's

    (tmp_path / "ci" / f"start-{kind}-history-x.jsonl").write_text("{no", "utf-8")
    assert start_record.history(kind) == []  # unreadable: left alone
