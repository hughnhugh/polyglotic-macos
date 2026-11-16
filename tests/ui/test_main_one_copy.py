"""Only one copy of the app runs per user and data folder (polyglotic-hq 310,
decision 0101): `main.this_copy`, first thing at start. A second start
brings the first's window forward and ends with 0 - before Velopack, whose
update ends every copy running from the install folder, and before it
opens the settings, the outbox, the log or a window. The installer's hooks
and `--check-install` don't take part.

The last test is the app itself, from source and offscreen, started again
beside itself: before 310 the second copy ran too."""

import json
import os
import subprocess
import sys
import time
import uuid
from collections.abc import Callable, Iterator
from functools import partial
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from polyglotic_desktop import main
from polyglotic_desktop.adapters.json_settings import ReadOnlySettings
from polyglotic_desktop.perf import start_parts
from polyglotic_desktop.ui import one_copy
from polyglotic_desktop.ui.settings import Settings


class FakeLock:
    def __init__(self, held: bool) -> None:
        self.held = held
        self.tries = 0

    def take(self) -> bool:
        self.tries += 1
        return not self.held

    def release(self) -> None:
        pass


class FakeOs:
    """The OS's adapters `this_copy` and `main`'s first lines use."""

    def __init__(self, data: Path, held: bool) -> None:
        self.data = data
        self.lock = FakeLock(held)
        self.names: list[str] = []
        self.boxes: list[tuple[str, str]] = []

    def data_folder(self) -> Path:
        return self.data

    def copy_lock(self, name: str) -> FakeLock:
        self.names.append(name)
        return self.lock

    def let_to_front(self, pid: int) -> None:
        pass

    def show_error(self, title: str, text: str) -> None:
        self.boxes.append((title, text))

    def store_package(self) -> None:
        return None


@pytest.fixture(autouse=True)
def _start_parts_ended() -> Iterator[None]:
    """`main()` begins the start's record (`perf.start_parts`); these tests
    end it before any first paint, so it's ended here, as that paint would."""
    yield
    start_parts.end()


@pytest.fixture
def data(tmp_path: Path) -> Path:
    return tmp_path / "data"  # not made: a second start makes nothing


def _os(monkeypatch: pytest.MonkeyPatch, data: Path, held: bool) -> FakeOs:
    fake = FakeOs(data, held)
    monkeypatch.setattr(main, "os_adapters", lambda system=sys.platform: fake)
    return fake


def _started(monkeypatch: pytest.MonkeyPatch, outcome: one_copy.Start) -> list[bool]:
    """`one_copy.start` saying `outcome`: whether each start asked to show."""
    asked: list[bool] = []

    def start(take: object, ask: object, show: bool) -> one_copy.Start:
        asked.append(show)
        return outcome

    monkeypatch.setattr(one_copy, "start", start)
    return asked


def _exit_code(call: Callable[[], object]) -> object:
    with pytest.raises(SystemExit) as ended:
        call()
    return ended.value.code


# --- This copy, or the one that runs --------------------------------------------


def test_with_no_copy_running_this_one_runs_holding_its_data_folders_lock(
    monkeypatch: pytest.MonkeyPatch, data: Path
) -> None:
    fake = _os(monkeypatch, data, held=False)

    copy = main.this_copy(["--data", str(data)])

    assert copy == main.FirstCopy(one_copy.copy_name(data, one_copy.user()), fake.lock)
    assert fake.names == [copy.name]


def test_the_data_folder_is_the_apps_own_unless_one_is_given(
    monkeypatch: pytest.MonkeyPatch, data: Path
) -> None:
    fake = _os(monkeypatch, data, held=False)
    copy = main.this_copy([])
    assert copy is not None
    assert copy.name == one_copy.copy_name(data, one_copy.user())
    assert fake.names == [copy.name]


def test_a_second_start_has_the_first_shown_and_ends_with_0_having_opened_nothing(
    monkeypatch: pytest.MonkeyPatch, data: Path
) -> None:
    fake = _os(monkeypatch, data, held=True)
    asked = _started(monkeypatch, one_copy.Start.SHOWN)

    assert _exit_code(partial(main.this_copy, ["--data", str(data)])) == 0
    assert asked == [True]
    assert fake.boxes == []
    assert not data.exists()  # no log, settings, outbox or crash note


def test_started_in_the_tray_while_a_copy_runs_it_ends_showing_nothing(
    monkeypatch: pytest.MonkeyPatch, data: Path
) -> None:
    """Windows starts the app in the tray at sign-in (176)."""
    fake = _os(monkeypatch, data, held=True)
    asked = _started(monkeypatch, one_copy.Start.ALREADY)

    code = _exit_code(partial(main.this_copy, ["--data", str(data), "--in-tray"]))

    assert code == 0
    assert asked == [False]  # nothing is asked to show
    assert fake.boxes == []


def test_a_copy_that_doesnt_answer_is_said_in_the_learners_language(
    monkeypatch: pytest.MonkeyPatch, data: Path, qapp: QApplication
) -> None:
    """The box, not a silent end. The settings are read for the interface
    language, never written - not even set aside when unreadable: the file
    is the running copy's."""
    fake = _os(monkeypatch, data, held=True)
    _started(monkeypatch, one_copy.Start.NO_ANSWER)
    data.mkdir()
    settings = data / "settings.json"
    settings.write_bytes(json.dumps({"interface_language": "de"}).encode())
    languages: list[str | None] = []

    def language(app: QApplication, store: ReadOnlySettings) -> list[object]:
        assert app is qapp
        languages.append(Settings(store).value.interface_language)
        store.save({"interface_language": "en"})  # as anything might
        return []

    monkeypatch.setattr(main, "QApplication", lambda argv: qapp)
    monkeypatch.setattr(main, "start_interface_language", language)

    assert _exit_code(partial(main.this_copy, ["--data", str(data)])) == 1
    assert fake.boxes == [("Polyglotic", one_copy.not_answering())]
    assert languages == ["de"]
    assert settings.read_bytes() == json.dumps({"interface_language": "de"}).encode()


def test_a_second_start_reads_an_unreadable_settings_file_without_setting_it_aside(
    data: Path,
) -> None:
    data.mkdir()
    settings = data / "settings.json"
    settings.write_text("{not json", encoding="utf-8")
    store = ReadOnlySettings(settings)

    assert store.load() == {}
    store.save({"interface_language": "de"})

    assert [p.name for p in data.iterdir()] == ["settings.json"]
    assert settings.read_text(encoding="utf-8") == "{not json"


# --- What doesn't take part ---------------------------------------------------------


def _no_os(monkeypatch: pytest.MonkeyPatch) -> None:
    def never(system: str = sys.platform) -> main.OsAdapters:
        raise AssertionError("the OS's adapters weren't to be asked")

    monkeypatch.setattr(main, "os_adapters", never)


@pytest.mark.parametrize(
    "hook",
    [
        "--veloapp-install",
        "--veloapp-updated",
        "--veloapp-obsolete",
        "--veloapp-uninstall",
    ],
)
def test_the_installers_hooks_never_wait_for_one_copy(
    monkeypatch: pytest.MonkeyPatch, hook: str
) -> None:
    """Velopack starts the app with them while installing, updating and
    uninstalling - with a copy running or on its way out."""
    _no_os(monkeypatch)
    assert main.this_copy([hook, "1.2.3"]) is None
    monkeypatch.setattr(sys, "argv", ["Polyglotic.exe", hook, "1.2.3"])
    assert main.this_copy() is None


def test_the_install_check_doesnt_take_part(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`--check-install` builds everything in a folder of its own."""
    _no_os(monkeypatch)
    assert main.this_copy(["--check-install", str(tmp_path / "report.json")]) is None


def test_an_os_without_adapters_holds_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    def none_here(system: str = sys.platform) -> main.OsAdapters:
        raise main.NoOsAdapters("none here")

    monkeypatch.setattr(main, "os_adapters", none_here)
    assert main.this_copy([]) is None


class Velopack(Exception):
    """Velopack's start-up was reached."""


def test_a_hook_reaches_velopack_while_a_copy_runs(
    monkeypatch: pytest.MonkeyPatch, data: Path
) -> None:
    fake = _os(monkeypatch, data, held=True)

    def hooks() -> None:
        raise Velopack

    monkeypatch.setattr(main, "run_installer_hooks", hooks)
    with pytest.raises(Velopack):
        main.main(["--veloapp-updated", "1.2.3"])
    assert fake.lock.tries == 0


def test_a_second_start_never_reaches_velopack(
    monkeypatch: pytest.MonkeyPatch, data: Path
) -> None:
    """With a downloaded update waiting, Velopack's start-up applies it, and
    its apply ends every process running from the install folder - the copy
    the learner was using, unsaved (decision 0101)."""
    _os(monkeypatch, data, held=True)
    _started(monkeypatch, one_copy.Start.SHOWN)
    reached: list[str] = []
    monkeypatch.setattr(main, "run_installer_hooks", lambda: reached.append("velopack"))

    assert _exit_code(partial(main.main, ["--data", str(data)])) == 0
    assert reached == []


# --- The app itself, twice -------------------------------------------------------

STARTED = "interface: "  # the log's line once the copy answers second starts


def _log(data: Path) -> str:
    try:
        return (data / "logs" / "polyglotic.log").read_text(encoding="utf-8")
    except OSError:
        return ""


def _until_logged(data: Path, times: int, run: subprocess.Popen[str]) -> None:
    end = time.monotonic() + 90
    while _log(data).count(STARTED) < times:
        assert run.poll() is None, f"ended {run.returncode}: {_log(data)[-2000:]}"
        assert time.monotonic() < end, _log(data)[-2000:]
        time.sleep(0.2)


@pytest.fixture
def app_runs(tmp_path: Path) -> Iterator[list[subprocess.Popen[str]]]:
    """Each copy started, ended at the test's end (by its own process)."""
    runs: list[subprocess.Popen[str]] = []
    yield runs
    for run in runs:
        if run.poll() is None:
            run.kill()
        run.communicate()


@pytest.mark.windows_only  # main() itself: the OS's adapters
def test_the_app_started_again_brings_the_first_forward_and_ends(
    tmp_path: Path, app_runs: list[subprocess.Popen[str]]
) -> None:
    """The app from source, offscreen, sitting at its first run's question.
    Started again on its data folder: the second ends with 0 within seconds,
    having logged nothing, and the first brings its question forward; in
    the tray (as Windows starts it) the second ends showing nothing. Another
    data folder runs beside it. The first crashed (killed): nothing stale,
    the next start runs."""
    empty = tmp_path / "no-dictionaries"
    empty.mkdir()
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")

    def command(data: Path) -> list[str]:
        return [
            sys.executable,
            "-m",
            "polyglotic_desktop.main",
            "--data",
            str(data),
            "--dictionaries",
            str(empty),
            "--server",
            "http://127.0.0.1:9",
            "--updates",
            str(tmp_path),
            "--credentials",
            f"Polyglotic-test-310-{uuid.uuid4().hex}",
        ]

    def start(data: Path, *more: str) -> subprocess.Popen[str]:
        with (tmp_path / f"run-{len(app_runs)}.txt").open("w") as output:
            run = subprocess.Popen(
                [*command(data), *more],
                env=env,
                stdout=output,
                stderr=subprocess.STDOUT,
                text=True,
            )
        app_runs.append(run)
        return run

    data, other = tmp_path / "data", tmp_path / "other"
    first = start(data)
    _until_logged(data, 1, first)

    began = time.monotonic()
    second = start(data)
    assert second.wait(30) == 0, (tmp_path / "run-1.txt").read_text()
    assert time.monotonic() - began < 20
    forward = "a second start: the main window brought forward"
    end = time.monotonic() + 10
    while forward not in _log(data) and time.monotonic() < end:
        time.sleep(0.1)
    assert _log(data).count(forward) == 1
    assert _log(data).count("taskbar ID") == 1  # the second logged nothing

    in_tray = start(data, "--in-tray")
    assert in_tray.wait(30) == 0
    assert _log(data).count(forward) == 1 and _log(data).count(STARTED) == 1

    beside = start(other)  # a data folder of its own: runs
    _until_logged(other, 1, beside)
    assert first.poll() is None and beside.poll() is None
    beside.kill()

    first.kill()  # as a crash: TerminateProcess
    first.wait(30)
    again = start(data)
    _until_logged(data, 2, again)  # nothing stale: it runs
    assert again.poll() is None
