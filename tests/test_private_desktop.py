"""Real windows on a desktop of their own (`tools/private_desktop.py`,
polyglotic-hq 205): Windows never displays it, so nothing here reaches the
user's screen. The tool itself - a command's windows are there and never
on the test's own desktop, stopping it ends whatever it started, and
pictures come from the program's own `grab()` - then the real app from
source, started and ended with the learner's Quit there
(`tests/app_on_a_desktop.py`)."""

import ctypes
import json
import os
import sys
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

import pytest

if sys.platform != "win32":
    pytest.skip("Windows only: desktops are Windows'", allow_module_level=True)

from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication
from tests.ui.test_check_install import sample_dictionaries
from tools.private_desktop import (
    PrivateDesktop,
    Started,
    Window,
    can_show_windows,
    windows_here,
)
from tools.stand_in_taskbar import StandInTaskbar, TrayIcon

from tools import private_desktop, window_icon

ROOT = Path(__file__).resolve().parents[1]
QT = dict(os.environ, QT_QPA_PLATFORM="windows")  # real windows, not offscreen
WINDOW = """
import sys
from PySide6.QtWidgets import QApplication, QLabel
app = QApplication(sys.argv)
label = QLabel("205")
label.setStyleSheet("background: #c03030")
label.resize(200, 80)
label.show()
{then}
sys.exit(app.exec())
"""
SYNCHRONIZE = 0x00100000
SHOWN = can_show_windows()
"""False on the CI runners: a service's window station never shows a window,
so whether one is visible, and what the mouse would reach, is checked only
in the signed-in user's session (an agent's shell)."""


_FROM_HICON = "fromHICON"


def _from_hicon(icon: object) -> QImage:
    """`QImage.fromHICON`: Qt has it on Windows only, and so do PySide6's
    type stubs - asked for by name so the types check on any machine."""
    image: QImage = getattr(QImage, _FROM_HICON)(icon)
    return image


def _until(found: Callable[[], object], seconds: float, what: str, log: Path) -> None:
    end = time.monotonic() + seconds
    while not found():
        if time.monotonic() > end:
            raise AssertionError(f"no {what} in {seconds:g} s: {_tail(log)}")
        time.sleep(0.2)


class _Icons(Protocol):
    def icons(self) -> list[TrayIcon]: ...


def _tray_icon(taskbar: _Icons, seconds: float, log: Path) -> TrayIcon:
    """The app's one tray icon once Qt has told the taskbar all of it: Qt
    adds the icon (`NIM_ADD`), then sets its clicks' version
    (`NIM_SETVERSION`) in a second call. Read between the two, the icon has
    version 0 (CI, #427 and #425, 2026-11-08), so this waits for the
    version, not just the icon."""
    _until(lambda: [i for i in taskbar.icons() if i.version], seconds, "tray icon", log)
    (icon,) = taskbar.icons()
    return icon


def _tail(log: Path) -> str:
    return log.read_text(errors="replace")[-3000:] if log.exists() else "(no output)"


def _qt_windows(desktop: PrivateDesktop, started: Started) -> list[Window]:
    return [
        w
        for w in desktop.windows(started)
        if w.class_name.startswith("Qt") and w.class_name.endswith("QWindowIcon")
    ]


def _shows_the_app_icon(hwnd: int) -> bool:
    """Windows draws Polyglotic's icon for this window, small and big - its
    title bar, the taskbar's button, Alt-Tab - not the plain application
    icon Qt's window classes carry (polyglotic-hq 245). Read from outside
    the app (`tools/window_icon.py`)."""
    if QApplication.instance() is None:  # the app icon's pixmaps need one
        _OFFSCREEN.append(QApplication(["test", "-platform", "offscreen"]))
    icons = window_icon.icons_of(hwnd)
    return all(
        window_icon.is_the_app_icon(window_icon.picture(icons.shown(which)))
        for which in ("small", "big")
    )


_OFFSCREEN: list[QApplication] = []


def _ended(pid: int) -> bool:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    handle = kernel32.OpenProcess(SYNCHRONIZE, False, pid)
    if not handle:
        return True  # gone already
    try:
        return bool(kernel32.WaitForSingleObject(handle, 5000) == 0)
    finally:
        kernel32.CloseHandle(handle)


def test_a_commands_window_is_on_its_desktop_and_never_here(tmp_path: Path) -> None:
    """Shown there, and - where windows can be visible - what the mouse would
    reach at its middle."""
    with PrivateDesktop() as desktop:
        started = desktop.start(
            [sys.executable, "-c", WINDOW.format(then="")],
            env=QT,
            output=tmp_path / "out.txt",
        )
        _until(
            lambda: [
                w for w in _qt_windows(desktop, started) if w.visible or not SHOWN
            ],
            60,
            "window",
            tmp_path / "out.txt",
        )
        (shown,) = _qt_windows(desktop, started)
        assert shown.rect[2] > shown.rect[0] and shown.rect[3] > shown.rect[1]
        assert shown.dpi > 0
        assert windows_here(started) == []  # the test's desktop: the user's
        if SHOWN:
            assert shown.visible
            assert desktop.window_at(*_middle(shown)) == shown.hwnd
        started.stop()
        assert started.wait(10) is not None


def test_speaker_caption_reaches_the_focused_text_box(tmp_path: Path) -> None:
    output = tmp_path / "speaker-typing.txt"
    shot = tmp_path / "speaker-typing.png"
    with PrivateDesktop() as desktop:
        started = desktop.start(
            [sys.executable, "-m", "tests.type_theirs_on_a_desktop", str(shot)],
            env=QT,
            output=output,
        )
        assert started.wait(25) == 0, _tail(output)
    assert not QImage(str(shot)).isNull()


def test_stopping_ends_what_it_started_too(tmp_path: Path) -> None:
    child_pid = tmp_path / "child.txt"
    starts_a_child = (
        "import subprocess, sys, time, pathlib;"
        "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)']);"
        f"pathlib.Path(r'{child_pid}').write_text(str(child.pid));"
        "time.sleep(120)"
    )
    with PrivateDesktop() as desktop:
        started = desktop.start(
            [sys.executable, "-c", starts_a_child], output=tmp_path / "out.txt"
        )
        _until(child_pid.exists, 30, "child", tmp_path / "out.txt")
        started.stop()
        assert started.wait(10) is not None
    assert _ended(int(child_pid.read_text()))


def test_pictures_come_from_the_programs_own_grab(tmp_path: Path) -> None:
    then = "from PySide6.QtCore import QTimer; QTimer.singleShot(3000, app.quit)"
    program = tmp_path / "window.py"
    program.write_text(WINDOW.format(then=then), encoding="utf-8")
    shots = tmp_path / "shots"

    code = private_desktop.main(
        ["python", "--shots", str(shots), "--grab-after", "0.5", "--timeout", "60"]
        + ["--", str(program)]
    )

    assert code == 0
    (picture,) = shots.glob("*.png")
    image = QImage(str(picture))
    assert image.width() >= 200 and image.pixelColor(10, 10).name() == "#c03030"


@pytest.mark.windows_only  # main() itself: the OS's adapters
def test_the_app_starts_and_quits_on_a_desktop_of_its_own(tmp_path: Path) -> None:
    """A first run answered, the main window shown and painted, three
    caption windows up, then the learner's Quit, pressed once: the app ends
    by itself with 0 and leaves no window. With caption windows up is when
    Qt's `quit()` gave up and the app ran on, its tray icon gone
    (polyglotic-hq 141, 215). Every window is deleted before `main()`
    ends, not left for Python to tear down as it stops (261, 269)."""
    out, data, updates = tmp_path / "out", tmp_path / "data", tmp_path / "updates"
    for folder in (out, data, updates):
        folder.mkdir()
    command = [sys.executable, "-m", "tests.app_on_a_desktop", str(out)]
    command += ["--data", str(data), "--server", "http://127.0.0.1:9"]
    command += ["--dictionaries", str(sample_dictionaries(tmp_path / "dictionaries"))]
    command += ["--updates", str(updates)]
    command += ["--credentials", f"Polyglotic-test-205-{uuid.uuid4().hex}"]  # none
    log = tmp_path / "app.txt"

    with PrivateDesktop() as desktop:
        started = desktop.start(command, env=QT, cwd=ROOT, output=log)
        try:
            _until(
                lambda: (out / "shown.json").exists() or started.wait(0) is not None,
                90,
                "main window",
                log,
            )
            assert (out / "shown.json").exists(), _tail(log)
            shown = json.loads((out / "shown.json").read_text(encoding="utf-8"))
            # language first, then consent; no level asked (polyglotic-hq 293, 658)
            assert shown["asked"][:2] == ["LanguagePicker", "ConsentDialog"]
            (main,) = [w for w in desktop.windows(started) if w.hwnd == shown["main"]]
            assert main.visible or not SHOWN  # a service's session shows none
            assert main.cloaked in (0, None)  # None: DWM wouldn't say
            assert main.rect[2] - main.rect[0] > 300 and main.dpi > 0
            assert _shows_the_app_icon(main.hwnd)
            assert shown["taskbar_id"] == "Polyglotic.Desktop"  # not python.exe's (245)
            assert windows_here(started) == []
            (picture_file,) = out.glob("*-MainWindow.png")
            picture = QImage(str(picture_file))
            assert picture.width() > 300
            across = range(0, picture.width(), 7)
            assert len({picture.pixel(x, picture.height() // 2) for x in across}) > 3

            (out / "captions").touch()  # an app captioned: its window up
            _until(
                lambda: (out / "captions.json").exists() or started.wait(0) is not None,
                30,
                "caption window",
                log,
            )
            captions = json.loads((out / "captions.json").read_text(encoding="utf-8"))
            up = [w for w in desktop.windows(started) if w.hwnd in captions["windows"]]
            assert len(up) == 3
            assert all(w.visible for w in up) or not SHOWN
            assert all(_shows_the_app_icon(w.hwnd) for w in up)

            (out / "quit").touch()  # the learner's Quit
            assert started.wait(30) == 0, _tail(log)
            assert [w for w in desktop.windows(started) if w.visible] == []
            ended = json.loads((out / "ended.json").read_text(encoding="utf-8"))
            assert ended["alive"] == []  # deleted while Qt and Python were up
        finally:
            started.stop()


def _app_command(tmp_path: Path) -> tuple[list[str], Path]:
    """The real app from source through `tests/app_on_a_desktop.py`: its
    command, and the folder it and the test talk through."""
    out, data, updates = tmp_path / "out", tmp_path / "data", tmp_path / "updates"
    for folder in (out, data, updates):
        folder.mkdir()
    command = [sys.executable, "-m", "tests.app_on_a_desktop", str(out)]
    command += ["--data", str(data), "--server", "http://127.0.0.1:9"]
    command += ["--dictionaries", str(sample_dictionaries(tmp_path / "dictionaries"))]
    command += ["--updates", str(updates)]
    command += ["--credentials", f"Polyglotic-test-215-{uuid.uuid4().hex}"]  # none
    return command, out


def test_the_tray_icon_is_read_once_qt_has_set_its_version(tmp_path: Path) -> None:
    """Qt tells the taskbar an icon in two calls, the icon then its clicks'
    version; a taskbar read between them has the icon at version 0. The
    tray tests read it once the version is there (CI, #427 and #425)."""

    class HalfTold:  # the icon, then its version two reads later
        reads = 0

        def icons(self) -> list[TrayIcon]:
            self.reads += 1
            return [TrayIcon(1, 0, callback=0x8065, version=4 if self.reads > 2 else 0)]

    icon = _tray_icon(HalfTold(), 5, tmp_path / "app.txt")
    assert icon.version == 4


@pytest.mark.windows_only  # main() itself: the OS's adapters
def test_the_tray_icon_its_menu_and_quit_from_it_on_a_stand_in_taskbar(
    tmp_path: Path,
) -> None:
    """The app's tray icon reaches a stand-in taskbar on its desktop
    (`tools/stand_in_taskbar.py`) with its tooltip, its picture and the
    message its clicks come as, and Qt finds where it is; the taskbar's
    right click opens the tray's menu upwards from the icon, wholly on the
    work area; its Quit, with caption windows up, ends the app with 0 and
    takes the icon away (141: Quit from the tray, the menu over the
    taskbar)."""
    command, out = _app_command(tmp_path)
    log = tmp_path / "app.txt"
    with PrivateDesktop() as desktop, StandInTaskbar(desktop) as taskbar:
        started = desktop.start(command, env=QT, cwd=ROOT, output=log)
        try:
            icon = _tray_icon(taskbar, 90, log)
            assert started.owns(icon.pid)  # the app's own window gets its clicks
            assert icon.tip.startswith("Polyglotic"), icon.tip
            assert icon.version == 4 and icon.callback
            picture = _from_hicon(icon.icon)
            assert picture.width() >= 16
            assert len({picture.pixel(x, x) for x in range(picture.width())}) > 1

            _until(lambda: (out / "shown.json").exists(), 90, "main window", log)
            (out / "captions").touch()
            _until(lambda: (out / "captions.json").exists(), 30, "caption windows", log)
            (out / "tray").write_text("app.quit", encoding="utf-8")
            taskbar.click(icon, "context")  # a right click: the tray's menu
            _until(lambda: (out / "tray.json").exists(), 30, "tray menu", log)
            tray = json.loads((out / "tray.json").read_text(encoding="utf-8"))
            assert tray["menu"][0] == "Open Polyglotic" and tray["menu"][-1] == "Quit"
            left, top, right, bottom = (
                round(n / tray["ratio"]) for n in taskbar.icon_rect
            )
            assert tray["icon"] == [left, top, right - left, bottom - top]
            x, y, width, height = tray["rect"]
            ax, ay, aw, ah = tray["area"]
            assert ax <= x and x + width <= ax + aw  # wholly on the work area
            assert ay <= y and y + height <= ay + ah
            assert y + height <= (top + bottom) // 2  # upwards, as Windows' own

            assert started.wait(30) == 0, _tail(log)  # Quit, clicked in the menu
            assert [m[0] for m in taskbar.messages][-1] == "delete"
            assert taskbar.icons() == []
            assert [w for w in desktop.windows(started) if w.visible] == []
        finally:
            started.stop()


@pytest.mark.windows_only  # main() itself: the OS's adapters
def test_the_tray_icon_shows_pause_and_a_click_brings_the_window_back(
    tmp_path: Path,
) -> None:
    """Pause from the tray's menu changes the icon's picture (141: a
    different icon for paused); with the main window closed to the tray, a
    click on the icon brings it back (141: a click on the icon opens the
    main window). On a stand-in taskbar (`tools/stand_in_taskbar.py`)."""
    command, out = _app_command(tmp_path)
    log = tmp_path / "app.txt"
    with PrivateDesktop() as desktop, StandInTaskbar(desktop) as taskbar:
        started = desktop.start(command, env=QT, cwd=ROOT, output=log)
        try:
            _until(lambda: (out / "shown.json").exists(), 90, "main window", log)
            before = _tray_icon(taskbar, 30, log)
            idle = _from_hicon(before.icon)

            (out / "tray").write_text("app.pause", encoding="utf-8")
            taskbar.click(before, "context")
            _until(lambda: not (out / "tray").exists(), 30, "Pause clicked", log)
            _until(
                lambda: taskbar.icons()[0].icon != before.icon, 30, "paused icon", log
            )
            paused = _from_hicon(taskbar.icons()[0].icon)
            assert paused.size() == idle.size() and paused != idle

            def main_shown() -> bool:  # as Qt has it: a service's session shows none
                said = json.loads((out / "main.json").read_text(encoding="utf-8"))
                return bool(said["shows"])

            # Keep the old state open through the next write, as a polling
            # reader can on Windows. The driver must still publish the hide.
            with (out / "main.json").open("rb"):
                (out / "hide").touch()
                _until(
                    lambda: (out / "main.json.part").exists(), 30, "pending hide", log
                )
            _until(lambda: not main_shown(), 30, "main window hidden", log)
            taskbar.click(taskbar.icons()[0], "select")  # a left click on the icon
            _until(main_shown, 30, "main window back", log)

            (out / "quit").touch()
            assert started.wait(30) == 0, _tail(log)
        finally:
            started.stop()


@pytest.mark.windows_only  # main() itself: the OS's adapters
def test_a_second_start_brings_the_window_back_from_the_tray_and_minimised(
    tmp_path: Path,
) -> None:
    """Only one copy runs (polyglotic-hq 310): the app started again on its
    data folder ends with 0 and shows nothing of its own, and the first
    copy's main window comes back - closed to the tray, then minimised -
    shown, in front of the desktop's other windows."""
    command, out = _app_command(tmp_path)
    again = [*command[:3], str(tmp_path / "second"), *command[4:]]
    log, second_log = tmp_path / "app.txt", tmp_path / "second.txt"

    def said() -> dict[str, bool]:
        found: dict[str, bool] = json.loads((out / "main.json").read_text("utf-8"))
        return found

    def started_again(desktop: PrivateDesktop) -> None:
        second = desktop.start(again, env=QT, cwd=ROOT, output=second_log)
        try:
            assert second.wait(60) == 0, _tail(second_log)
        finally:
            second.stop()
        assert not (tmp_path / "second" / "shown.json").exists()

    with PrivateDesktop() as desktop:
        started = desktop.start(command, env=QT, cwd=ROOT, output=log)
        try:
            _until(lambda: (out / "shown.json").exists(), 90, "main window", log)
            main = json.loads((out / "shown.json").read_text(encoding="utf-8"))["main"]
            # said on the driver's next step after shown.json (CI, 2026-11-14)
            _until(lambda: (out / "main.json").exists(), 30, "main.json", log)

            (out / "hide").touch()  # closed: kept in the tray
            _until(lambda: not said()["shows"], 30, "main window hidden", log)
            started_again(desktop)
            _until(lambda: said()["shows"], 30, "main window back", log)
            (shown,) = [w for w in desktop.windows(started) if w.hwnd == main]
            assert shown.visible or not SHOWN
            on_top = [w for w in desktop.windows() if w.visible and not w.topmost]
            assert not SHOWN or on_top[0].hwnd == main  # in front of the rest

            (out / "minimise").touch()
            _until(lambda: said()["minimised"], 30, "main window minimised", log)
            started_again(desktop)
            _until(lambda: not said()["minimised"], 30, "main window restored", log)

            (out / "quit").touch()
            assert started.wait(30) == 0, _tail(log)
        finally:
            started.stop()


def _middle(window: Window) -> tuple[int, int]:
    left, top, right, bottom = window.rect
    return (left + right) // 2, (top + bottom) // 2
