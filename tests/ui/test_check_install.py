"""`--check-install`: the packed app's self-check (D5), here from source on
sample dictionaries - nothing shown, captured or sent. A check that builds
the interface runs in a process of its own, as the packed app's does: it
leaves windows and timers behind it in this one (a later budget test once
took 480 ms - project 132)."""

import itertools
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

import pytest
from PySide6.QtWidgets import QApplication
from tests.budget_judge import Sampled, within
from tests.test_sqlite_dictionary import write_sample

from polyglotic_desktop import main
from polyglotic_desktop.adapters.json_settings import JsonSettingsStore
from polyglotic_desktop.adapters.sqlite_dictionary import write_dictionary
from polyglotic_desktop.main import check_install
from polyglotic_desktop.perf.budgets import START_FROM_SOURCE
from polyglotic_desktop.ports.dictionary import EntryRecord


def sample_dictionaries(folder: Path) -> Path:
    folder.mkdir()
    write_sample(folder / "cedict.sqlite")
    run = EntryRecord("ecdict:run", "run", "", "rʌn", ("v. 跑",), 202)
    write_dictionary(
        folder / "ecdict.sqlite",
        {"dictionary": "ecdict"},
        [run],
        {"run": ["ecdict:run"]},
    )
    return folder


def checked(
    tmp_path: Path,
    temp: Path | None = None,
    dictionaries: Path | None = None,
    data: Path | None = None,
) -> tuple[int, dict[str, Any]]:
    """`--check-install` from source in a fresh process, offscreen; with
    `temp`, its temporary folder there; on `dictionaries` if given, else
    the sample ones; the learner's data folder `data` if given, else an
    empty one - never this PC's own."""
    report = tmp_path / "report.json"
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    if temp is not None:
        env.update(TEMP=str(temp), TMP=str(temp), TMPDIR=str(temp))
    done = subprocess.run(
        [
            sys.executable,
            "-m",
            "polyglotic_desktop.main",
            "--check-install",
            str(report),
            "--dictionaries",
            str(dictionaries or sample_dictionaries(tmp_path / "dictionaries")),
            "--data",
            str(data or tmp_path / "data"),
        ],
        env=env,
        capture_output=True,
        timeout=120,
        check=False,
    )
    return done.returncode, json.loads(report.read_text(encoding="utf-8"))


def left_in(temporary: Path) -> list[str]:
    """Every file and folder left in `temporary`, not just its top: which
    one was still open (polyglotic-hq 578: GitHub's Windows machine left
    the check's folder once, and the failure named only the folder)."""
    return sorted(
        path.relative_to(temporary).as_posix() for path in temporary.rglob("*")
    )


@pytest.mark.windows_only  # a whole check: the OS's launch clock
def test_everything_the_app_needs_is_built_and_reported(tmp_path: Path) -> None:
    code, found = checked(tmp_path)
    assert code == 0, found
    assert found["ok"] is True
    assert (found["version"], found["channel"]) == ("0.0.0", "win-x64-alpha")
    assert found["frozen"] is False
    assert found["programs_library_path"] == "the system's"  # a link's browser (561)
    assert found["dictionaries"] == ["cedict.sqlite", "ecdict.sqlite"]
    assert found["dictionaries_out"] == {}
    assert found["learning_set_aside"] == []
    assert found["speech_frames"] == 0  # a second of silence
    assert found["opus_bytes"] > 0
    assert found["feed_signature_check"] is True  # RFC 8032 test 1, and a refusal
    assert found["checkbox_tick"] is True  # SVG imageformat plugin draws the tick (647)
    # a pack as a download leaves it: unpacked, opened, a form looked up (327);
    # from source simplemma is there, in the installed app it isn't (0123)
    assert found["dictionary_pack"] == {**main.PACK_CHECKED, "simplemma": True}
    assert found["installer_packs"] == {}  # from source: none (decision 0124)
    assert found["ready_seconds"] > 0
    # the interface as main builds it, every window once (project 132)
    assert found["windows"] == [
        "caption_window",
        "joined_window",
        "transcript",
        "lookup_card",
    ]


@pytest.mark.windows_only  # a whole check: the OS's launch clock
@pytest.mark.parametrize("with_tunables", [False, True], ids=["shipped", "override"])
def test_the_main_window_is_shown_within_its_budget(
    tmp_path: Path, with_tunables: bool
) -> None:
    """The check times the main window's first paint from its start (after
    Python's imports): within the budget from source (DECISIONS.md #53);
    the packed app's is held to START_PACKED by the build. A start is one
    run, a first time: over, it's started once more in a new process, and
    fails only if that's over too, naming both (`tests/budget_judge.py`)."""
    tries = itertools.count(1)

    def start() -> Sampled:
        folder = tmp_path / f"try-{next(tries)}"
        folder.mkdir()
        if with_tunables:
            data = folder / "data"
            data.mkdir()
            (data / "tunables.toml").write_text(
                "[dwell]\nread_least = 1.2\n", encoding="utf-8"
            )
        code, found = checked(folder)
        assert code == 0, found
        assert isinstance(found["window_seconds"], float)
        assert isinstance(found["ready_seconds"], float)
        assert 0 < found["window_seconds"] <= found["ready_seconds"]
        # from the process's launch, imports included: what the budget means;
        # recorded (project 136: 0.40-0.45 s offscreen on a quiet PC), not gated
        # here, since a busy CI runner doubles it
        assert found["launch_seconds"] > found["window_seconds"]
        return Sampled((found["window_seconds"] * 1000,))

    within(START_FROM_SOURCE, start)


def test_a_missing_part_fails_the_check_with_a_report(tmp_path: Path) -> None:
    """Here the dictionaries: named, with why (polyglotic-hq 199) - the
    rest built without them, so in a process of its own."""
    empty = tmp_path / "dictionaries"
    empty.mkdir()

    code, found = checked(tmp_path, dictionaries=empty)

    assert code == 1
    assert found["ok"] is False
    assert found["error"]
    assert found["dictionaries_out"] == {
        "cedict.sqlite": "missing",
        "ecdict.sqlite": "missing",
    }


@pytest.mark.windows_only  # a whole check: the OS's launch clock
def test_the_learning_stores_are_closed_and_the_temporary_folder_removed(
    tmp_path: Path,
) -> None:
    """Both learning stores are closed when the check ends, so its temporary
    folder can be removed: Windows refuses to delete an SQLite file still
    open (polyglotic-hq 121, 127)."""
    temporary = tmp_path / "temp"
    temporary.mkdir()
    code, _ = checked(tmp_path, temporary)
    assert code == 0
    assert left_in(temporary) == []


def test_after_a_failed_step_too(
    qapp: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A step failing after the stores opened (here, the app itself): they
    are closed all the same."""
    temporary = tmp_path / "temp"
    temporary.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(temporary))

    def broken(*args: object) -> None:
        raise RuntimeError("a step failed")

    monkeypatch.setattr(main, "DesktopApp", broken)
    report = tmp_path / "report.json"

    code = check_install(report, sample_dictionaries(tmp_path / "dictionaries"))

    assert code == 1
    assert left_in(temporary) == []


def test_a_save_still_being_written_is_in_before_the_folder_goes(
    qapp: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """polyglotic-hq 578: the check never closed its settings store, whose
    saves are written on a thread of their own. One still being written
    when the temporary folder was removed made the folder again and wrote
    settings.json into it - left behind (GitHub's Windows machine, 563 and
    578). Closed with the rest, its last write is in first."""
    temporary = tmp_path / "temp"
    temporary.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(temporary))
    real_write = JsonSettingsStore._write
    written = threading.Event()

    def slowly(store: JsonSettingsStore, values: dict[str, object]) -> None:
        time.sleep(0.3)  # a busy disk, or a scanner looking at the file
        real_write(store, values)
        written.set()

    def saves_then_fails(
        desktop: object, store: JsonSettingsStore, *args: Any, **kwargs: Any
    ) -> None:
        store.save({"saved": "as the interface does"})
        raise RuntimeError("a step failed after a save")

    monkeypatch.setattr(JsonSettingsStore, "_write", slowly)
    monkeypatch.setattr(main, "new_interface", saves_then_fails)

    code = check_install(
        tmp_path / "report.json", sample_dictionaries(tmp_path / "dictionaries")
    )

    assert code == 1
    assert written.wait(5.0)
    assert left_in(temporary) == []


def test_one_learner_is_opened_before_the_window_as_a_start_opens(
    qapp: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The check times the start a learner waits for (polyglotic-hq 400): a
    start opens its learner's dictionary and data before the window, and any
    other language's after the first paint. The check opened the English
    learner's too, before the window - 60-80 ms each, timed into
    `launch_seconds` though no start waits for it. It's checked after."""
    temporary = tmp_path / "temp"
    temporary.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(temporary))
    opened: list[bool] = []
    real = main.learner_tools

    def recorded(dictionaries: Path, english: bool, *args: Any, **kwargs: Any) -> Any:
        opened.append(english)
        return real(dictionaries, english, *args, **kwargs)

    def window_built(*args: object, **kwargs: object) -> None:
        raise RuntimeError(f"the window: {opened} opened before it")

    monkeypatch.setattr(main, "learner_tools", recorded)
    monkeypatch.setattr(main, "new_interface", window_built)

    code = check_install(
        tmp_path / "report.json", sample_dictionaries(tmp_path / "dictionaries")
    )

    assert code == 1  # stopped at the window, here
    assert opened == [False]  # the Chinese learner's alone


def test_checkbox_tick_check_fails_when_no_svg_tick_renders(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """647: check_checkbox_tick passes when the SVG plugin draws the tick and
    fails when no tick is rendered (as happened without libqsvg.so)."""
    from polyglotic_desktop.ui_next import style

    assert main.check_checkbox_tick() is True
    monkeypatch.setattr(style, "tick", lambda _colour: "")
    assert main.check_checkbox_tick() is False
