"""Start-up failures leave a trace (polyglotic-hq project 042, Medium 4):
an exception nothing caught is logged by its type and where it was raised -
never its message - and, before the interface runs, an installed app says
so in a box (here a stand-in: nothing is shown). A thread's is logged too."""

import io
import json
import logging
import os
import sqlite3
import subprocess
import sys
import threading
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QWidget
from tests.ui.fakes import Built

from polyglotic_desktop.adapters.signed_feed import public_keys
from polyglotic_desktop.adapters.sqlite_learning import VERSION as LEARNING_VERSION
from polyglotic_desktop.main import (
    CAPTION_LOG,
    CrashLog,
    LastCrash,
    last_crash,
    start_logging,
    where,
)

SECRET = "a caption: 你好, and C:\\Users\\someone\\private.txt"


def caught(error: BaseException) -> tuple[type[BaseException], BaseException, object]:
    def failing_at_start() -> None:
        raise error

    try:
        failing_at_start()
    except BaseException as e:  # noqa: BLE001 - the hook's input
        return type(e), e, e.__traceback__
    raise AssertionError("didn't raise")


def test_at_start_logged_by_type_and_place_and_the_box_shown(
    caplog: pytest.LogCaptureFixture,
) -> None:
    shown: list[str] = []
    crashes = CrashLog(lambda: shown.append("box"))

    with caplog.at_level(logging.ERROR):
        crashes.uncaught(*caught(ValueError(SECRET)))  # type: ignore[arg-type]

    assert "uncaught ValueError at start" in caplog.text
    assert "test_main_crashes.py:" in caplog.text
    assert "in failing_at_start" in caplog.text
    assert "你好" not in caplog.text and "someone" not in caplog.text
    assert shown == ["box"]


def test_while_running_logged_and_nothing_shown(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Qt hands a slot's exception to the hook and carries on: no box."""
    shown: list[str] = []
    crashes = CrashLog(lambda: shown.append("box"))
    crashes.running = True

    with caplog.at_level(logging.ERROR):
        crashes.uncaught(*caught(KeyError(SECRET)))  # type: ignore[arg-type]

    assert "uncaught KeyError while running" in caplog.text
    assert "你好" not in caplog.text
    assert shown == []


def test_from_source_no_box() -> None:
    CrashLog().uncaught(*caught(ValueError("x")))  # type: ignore[arg-type]


def test_a_threads_exception_is_logged_by_type_and_place(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "excepthook", sys.excepthook)
    monkeypatch.setattr(threading, "excepthook", threading.excepthook)
    CrashLog().install()

    def work() -> None:
        raise RuntimeError(SECRET)

    with caplog.at_level(logging.ERROR):
        thread = threading.Thread(target=work, name="worker")
        thread.start()
        thread.join()

    assert "uncaught RuntimeError on thread worker" in caplog.text
    assert "in work" in caplog.text
    assert "你好" not in caplog.text


def test_where_names_the_apps_own_frame_too() -> None:
    """Raised inside a library, the place in the app's code that called it
    is named as well."""
    try:
        public_keys(["not base64!"])
    except ValueError as e:
        place = where(e.__traceback__)
    assert place.startswith("base64.py:")
    assert ", from signed_feed.py:" in place and place.endswith(" in public_keys")
    try:
        json.loads("{")
    except ValueError as e:
        place = where(e.__traceback__)
    assert place.startswith("decoder.py:") and ", from " not in place
    assert where(None) == "an unknown place"


@pytest.mark.parametrize("from_source", [False, True])
def test_the_log_file_names_an_exception_by_type_and_place_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, from_source: bool
) -> None:
    """The log is a file in the user's data folder, installed or from
    source (project 062). An exception logged there - `log.exception` in
    the session and the hotkeys, or a library's - is its type and where it
    was raised: no traceback, whose file paths hold the user's Windows
    name, and no message, which may hold a caption or a path (polyglotic-hq
    project 053, "noted, not fixed"; project 061). From source the console
    still gets the whole traceback: it isn't on disk."""
    console = io.StringIO()
    monkeypatch.setattr(sys, "stderr", console if from_source else None)
    root = logging.getLogger()
    monkeypatch.setattr(root, "handlers", [])  # start_logging adds its own
    monkeypatch.setattr(root, "level", root.level)
    captions = logging.getLogger(CAPTION_LOG)  # its file handler, likewise
    monkeypatch.setattr(captions, "handlers", [])
    monkeypatch.setattr(captions, "propagate", True)
    start_logging(tmp_path)
    try:
        raise OSError(SECRET)

    except OSError:
        logging.getLogger("polyglotic_desktop.connection.session").exception(
            "the session failed"
        )
    for handler in (*root.handlers, *captions.handlers):
        handler.close()

    text = (tmp_path / "logs" / "polyglotic.log").read_text(encoding="utf-8")
    assert "the session failed" in text
    assert "OSError at test_main_crashes.py:" in text
    assert "Traceback" not in text and str(Path(__file__).parent) not in text
    assert "你好" not in text and "someone" not in text
    if from_source:
        assert "Traceback" in console.getvalue()


@pytest.mark.windows_only  # main() itself: the OS's adapters
def test_a_real_failure_at_start_is_logged_not_printed(tmp_path: Path) -> None:
    """The app itself, from source and offscreen, with learning data from a
    newer app: it fails building the learner's tools, refusing the file
    rather than damage it (RELEASING.md). (No dictionaries no longer stops
    it - polyglotic-hq 199 - nor a folder where its learning data file
    should be: that's set aside - 206.) The log -
    the console and the log file - gets the type and place; no
    traceback, which an installed app would have nowhere to print."""
    data = tmp_path / "data"
    data.mkdir()
    newer = sqlite3.connect(data / "learning.sqlite")
    newer.execute(f"PRAGMA user_version = {LEARNING_VERSION + 1}")
    newer.close()
    (data / "settings.json").write_text(json.dumps({"learning": "zh"}))
    empty = tmp_path / "no-dictionaries"
    empty.mkdir()
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")

    run = subprocess.run(
        [
            sys.executable,
            "-m",
            "polyglotic_desktop.main",
            "--data",
            str(data),
            "--dictionaries",
            str(empty),
            "--credentials",
            "Polyglotic-test-never-written",
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        timeout=120,
    )

    assert run.returncode == 1
    assert "uncaught " in run.stderr and " at start, at " in run.stderr
    assert "Traceback" not in run.stderr
    # from source the log goes to the data folder's file as well - what the
    # feedback form shows and attaches (polyglotic-hq project 062)
    log = (data / "logs" / "polyglotic.log").read_text(encoding="utf-8")
    assert "uncaught " in log and " at start, at " in log
    assert "Traceback" not in log
    # project 053: the next start can offer a report about it
    noted = json.loads((data / "crashed.json").read_text(encoding="utf-8"))
    assert noted["at_start"] is True and noted["what"]


# --- The next start offers a report (project 053) ---------------------------------


def test_an_error_is_noted_for_the_next_start_without_its_message(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    marker = tmp_path / "crashed.json"
    crashes = CrashLog(None, marker)
    crashes.session = lambda: "9e8d7c6b-5a4f-4e3d-8c2b-1a0f9e8d7c6b"
    with caplog.at_level(logging.ERROR):
        crashes.uncaught(*caught(ValueError(SECRET)))  # type: ignore[arg-type]
    text = marker.read_text(encoding="utf-8")
    assert "你好" not in text and "someone" not in text
    noted = json.loads(text)
    assert (noted["what"], noted["at_start"]) == ("ValueError", True)
    assert "in failing_at_start" in noted["where"]
    found = last_crash(marker)
    assert found == LastCrash(True, "9e8d7c6b-5a4f-4e3d-8c2b-1a0f9e8d7c6b")
    assert last_crash(marker) is None  # offered once: the note is gone


def test_a_threads_error_is_noted_as_while_running(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "excepthook", sys.excepthook)
    monkeypatch.setattr(threading, "excepthook", threading.excepthook)
    marker = tmp_path / "crashed.json"
    CrashLog(None, marker).install()

    def work() -> None:
        raise RuntimeError(SECRET)

    with caplog.at_level(logging.ERROR):
        thread = threading.Thread(target=work, name="worker")
        thread.start()
        thread.join()
    assert last_crash(marker) == LastCrash(False, None)


def test_no_note_or_a_broken_one_offers_nothing(tmp_path: Path) -> None:
    assert last_crash(tmp_path / "crashed.json") is None
    (tmp_path / "crashed.json").write_text("{not json", encoding="utf-8")
    assert last_crash(tmp_path / "crashed.json") is None
    assert not (tmp_path / "crashed.json").exists()


def test_home_offers_a_report_once_and_either_button_puts_it_away(
    qapp: QApplication,
) -> None:
    built = Built()
    wanted: list[bool] = []
    home = built.hub.home
    home.crash_report_wanted.connect(lambda: wanted.append(True))

    def offers() -> list[QWidget]:
        cards = (
            b.parentWidget() for b in home.findChildren(QPushButton, "home.crash.send")
        )
        return [c for c in cards if c is not None and c.isVisibleTo(home)]

    home.offer_crash_report(at_start=False)
    (card,) = offers()
    texts = " ".join(label.text() for label in card.findChildren(QLabel))
    assert "ran into an error last time" in texts
    send = card.findChild(QPushButton, "home.crash.send")
    assert send is not None
    send.click()
    assert wanted == [True] and offers() == []

    home.offer_crash_report(at_start=True)
    (card,) = offers()
    assert "couldn't start last time" in " ".join(
        label.text() for label in card.findChildren(QLabel)
    )
    dismiss = card.findChild(QPushButton, "home.crash.dismiss")
    assert dismiss is not None
    dismiss.click()
    assert offers() == [] and wanted == [True]
    built.close()
