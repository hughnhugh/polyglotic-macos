r"""The desktop's manners on Linux (polyglotic-hq 571): the tray and its menu,
or - where the desktop has none - the window back from the launcher.

    uv run --no-sync python -m tools.linux_manners_check OUT --tray yes|no

The app from source, signed in to a stand-in server on the machine, as
`tools/app_tour.py` starts it (its stand-ins: nothing of the session's
sound or keyring, no account, nothing leaves the machine) - but with the
OS's own one-copy lock, so a second start finds it running.

- `--tray yes` (KDE's watcher, XFCE's panel): the desktop has a tray; the
  menu is the tray's; another process reads it over D-Bus as the desktop's
  tray does (`tools/linux_tray_menu.py`) and every item the app shows is
  there; clicking Pause captions there pauses the app.
- `--tray no` (GNOME's own, without its extension): no tray; closing the
  window asks once (the box, pictured), then hides it; a second start - the
  launcher's - brings it back; Quit at the foot of its sidebar ends the app.

OUT gets `checks.json` and pictures by each window's own `grab()` - never a
picture of the screen. Exits 0 when every check passed. GitHub's runners
only (`.github/workflows/linux-manners.yml`).
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import shutil
import subprocess
import sys
import time
import traceback
from pathlib import Path
from typing import Any

from PySide6.QtCore import QPoint, QTimer
from PySide6.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon
from tests import fake_server

from tools import app_tour as tour
from tools.app_tour import Step, check, extra, hub, modal, pause, picture, wait

PAUSE = "Pause captions"
"""The tray menu's item clicked from the desktop's side."""


def manners(expect_tray: bool, second_start: list[str]) -> Step:
    yield from first_questions()
    yield wait(tour.ready, 60, "Home, signed in")
    desktop = tour.STATE["desktop"]
    window = hub().window
    tray = desktop.tray
    tour.RESULTS["facts"] |= {
        "desktop": os.environ.get("XDG_CURRENT_DESKTOP", ""),
        "session": os.environ.get("XDG_SESSION_TYPE", ""),
        "tray_available": QSystemTrayIcon.isSystemTrayAvailable(),
        "tray_made": tray is not None,
    }
    extra(window, "home", "Home")
    desk_hints()
    if expect_tray:
        yield from with_tray(desktop, window, tray)
    else:
        yield from without_tray(desktop, window, second_start)


def first_questions() -> Step:
    """The first run's questions, answered as a learner would (as
    `tools/app_tour.py` answers them)."""
    for _ in range(5):
        yield wait(
            lambda: QApplication.activeModalWidget() or tour.ready(),
            120,
            "the first question or the main window",
        )
        question = QApplication.activeModalWidget()
        if question is None:
            return
        name = type(question).__name__
        tour.STATE.setdefault("asked", []).append(name)
        if name == "ConsentDialog" and getattr(question, "agree", None) is not None:
            question.agree.setChecked(True)  # type: ignore[attr-defined]
        if name in ("LanguagePicker", "ConsentDialog", "LevelPicker"):
            question.accept()  # type: ignore[attr-defined]
        else:
            check(f"no {name} on a signed-in start", False)
            question.close()
        yield pause(1.0)


def with_tray(desktop: Any, window: Any, tray: Any) -> Step:
    if not check("the desktop has a tray", tray is not None):
        return
    menu = desktop.tray_menu
    check("the menu is the tray's, for the desktop to show", tray.contextMenu() is menu)
    yield pause(2.0)  # the panel draws the icon
    desk_picture("desk-panel")
    menu.popup(QPoint(400, 300))  # as Qt draws it: the picture of what's in it
    yield pause(1.0)
    picture(menu, "tray-menu", "the tray's menu")
    menu.hide()
    out = tour.OUT / "tray-dbus.json"
    was = desktop.pause.isChecked()
    shown = [  # before the tray's click turns Pause captions into Resume
        a.text().split("\t", 1)[0].replace("&", "")
        for a in menu.actions()
        if a.isVisible() and not a.isSeparator()
    ]
    reader = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "tools.linux_tray_menu",
            str(out),
            "--pid",
            str(os.getpid()),
            "--click",
            PAUSE,
        ]
    )
    yield wait(lambda: reader.poll() is not None, 60, "the tray's menu read over D-Bus")
    found = json.loads(out.read_text(encoding="utf-8")) if out.exists() else {}
    tour.RESULTS["facts"]["tray_dbus"] = {
        k: v for k, v in found.items() if k not in ("layout",)
    }
    if found.get("watcher") is False:  # an X11 tray (XEmbed): Qt's menu at the click
        yield from at_the_icon(desktop, tray, menu)
        return
    layout = found.get("layout")
    check("the desktop's tray read the menu", layout, found.get("error", ""))
    if not isinstance(layout, dict):
        return
    seen = labels(layout)
    missing = [text for text in shown if text not in seen]
    check("every item the menu shows is in the tray's", not missing, missing or seen)
    submenus = [a.menu() for a in menu.actions() if a.menu() is not None]
    for sub in submenus:
        inner = [a.text() for a in sub.actions() if a.isVisible() and a.text()]
        check(
            f"its submenu {sub.title()!r} has its items",
            all(t in seen for t in inner),
            inner,
        )
    yield wait(
        lambda: desktop.pause.isChecked() != was, 10, f"{PAUSE} clicked in the tray"
    )
    check(
        f"{PAUSE} in the desktop's tray pauses captions",
        desktop.pause.isChecked() != was,
    )
    desktop.pause.setChecked(was)


def at_the_icon(desktop: Any, tray: Any, menu: Any) -> Step:
    """An X11 tray's icon (XEmbed): right-clicked as a person would, the
    menu opens there; Pause captions clicked in it."""
    rect = tray.geometry()
    tour.RESULTS["facts"]["tray_icon"] = [
        rect.x(),
        rect.y(),
        rect.width(),
        rect.height(),
    ]
    xdotool = shutil.which("xdotool")
    placed = check("an X11 tray: the icon is placed", rect.isValid() and xdotool, rect)
    if not placed or xdotool is None:
        return
    at = rect.center()
    subprocess.run(
        [xdotool, "mousemove", str(at.x()), str(at.y()), "click", "3"], check=False
    )
    yield wait(menu.isVisible, 10, "the menu at a right-click on the icon")
    picture(menu, "tray-menu-at-the-icon", "the tray's menu, opened from its icon")
    desk_picture("desk-tray-menu")
    was = desktop.pause.isChecked()
    item = next((a for a in menu.actions() if a.text().startswith(PAUSE)), None)
    if item is not None and menu.isVisible():
        spot = menu.mapToGlobal(menu.actionGeometry(item).center())
        subprocess.run(
            [xdotool, "mousemove", str(spot.x()), str(spot.y()), "click", "1"],
            check=False,
        )
    yield wait(lambda: desktop.pause.isChecked() != was, 10, f"{PAUSE} clicked")
    check(
        f"{PAUSE} in the tray's menu pauses captions", desktop.pause.isChecked() != was
    )
    desktop.pause.setChecked(was)
    menu.hide()


def desk_hints() -> None:
    """What the desktop says over D-Bus (light or dark, metered) beside
    what Qt and the app made of it; with `POLYGLOTIC_COLOR_SCHEME` set (the
    workflow's gsettings), the portal must say it."""
    from PySide6.QtGui import QGuiApplication

    from polyglotic_desktop.platform.linux import hints
    from polyglotic_desktop.ui import theme

    found = {
        "portal_color_scheme": hints.color_scheme(),
        "light_panel": hints.light_panel(),
        "metered": hints.metered(),
        "qt_color_scheme": QGuiApplication.styleHints().colorScheme().name,
        "app_mode": theme.current,
    }
    tour.RESULTS["facts"]["hints"] = found
    wanted = os.environ.get("POLYGLOTIC_COLOR_SCHEME", "")
    expected = {"prefer-light": "light", "prefer-dark": "dark"}.get(wanted)
    if expected:
        said = hints.prefers() == expected
        check("the portal says the desktop's light or dark", said, found)
        check("the app follows it (Like this PC)", theme.current == expected, found)
    check("NetworkManager's absence isn't metered", found["metered"] is False, found)


def desk_picture(name: str) -> None:
    """The runner's own X screen (Xvfb: Xfce's panel), never a person's -
    for the record, never a failed check."""
    found = shutil.which("import")
    if os.environ.get("XDG_CURRENT_DESKTOP") != "XFCE" or found is None:
        return
    done = subprocess.run(
        [found, "-window", "root", str(tour.OUT / f"{name}.png")],
        check=False,
        capture_output=True,
    )
    if done.returncode == 0:
        tour.RESULTS["pictures"].append({"file": f"{name}.png", "what": "the X screen"})


def labels(item: dict[str, Any]) -> list[str]:
    found = [item["label"]] if item.get("label") and item.get("visible", True) else []
    for child in item.get("children", []):
        found += labels(child)
    return found


def without_tray(desktop: Any, window: Any, second_start: list[str]) -> Step:
    check("the desktop has no tray", desktop.tray is None)
    check("the window knows there's none", window.no_tray)
    QTimer.singleShot(0, window.close)  # the learner closes it
    yield wait(lambda: modal("QMessageBox"), 15, "the box on closing without a tray")
    box = QApplication.activeModalWidget()
    if isinstance(box, QMessageBox):
        picture(box, "no-tray-box", "the box on closing without a tray")
        extra(window, "no-tray-box-over-home", "the window under the box")
        box.defaultButton().click()  # Keep running
    yield wait(lambda: not window.isVisible(), 10, "the window hidden")
    check("closing hid the window and the app runs on", not window.isVisible())
    starter = launcher(second_start)
    began = time.monotonic()
    yield wait(window.isVisible, 90, "the window back from the launcher")
    check(
        "a start from the launcher brings the window back",
        window.isVisible(),
        f"{time.monotonic() - began:.1f} s, {starter}",
    )
    yield wait(
        lambda: starter["process"].poll() is not None, 30, "the second start ended"
    )
    check(
        "the second start ended at once",
        starter["process"].poll() == 0,
        starter["process"].poll(),
    )
    window.close()  # asked once already: hidden at once
    yield pause(1.0)
    check(
        "closing again just hides it",
        not window.isVisible() and modal("QMessageBox") is None,
    )
    window.show()
    yield pause(0.5)
    tour.STATE["quit_from_window"] = True
    window.quit_button.click()  # Quit, at the foot of the sidebar
    yield wait(lambda: False, 30, "")  # the app ends


def launcher(second_start: list[str]) -> dict[str, Any]:
    """The app started again as the desktop's launcher starts it: through
    a desktop file and `gio launch` where there's one, else straight."""
    entry = tour.OUT / "launcher" / "io.polyglotic.ManneredCheck.desktop"
    entry.parent.mkdir(parents=True, exist_ok=True)
    entry.write_text(
        "[Desktop Entry]\nType=Application\nName=Polyglotic (check)\n"
        f"Exec={' '.join(second_start)}\nTerminal=false\n",
        encoding="utf-8",
    )
    gio = shutil.which("gio")
    command = [gio, "launch", str(entry)] if gio else second_start
    log = (tour.OUT / "second-start.log").open("w", encoding="utf-8")
    process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
    return {"process": process, "how": "gio launch" if gio else "straight"}


class Driver(tour.Driver):
    def __init__(self, limit: float, steps: Step) -> None:
        super().__init__(limit)
        self.steps = steps


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m tools.linux_manners_check")
    parser.add_argument("out", type=Path)
    parser.add_argument("--tray", choices=("yes", "no"), required=True)
    parser.add_argument("--limit", type=float, default=240.0, help="seconds")
    parser.add_argument("--dictionaries", default="build/dictionaries")
    args = parser.parse_args(argv)
    tour.OUT = args.out
    tour.OUT.mkdir(parents=True, exist_ok=True)
    data = tour.OUT / "data"
    tour.seed_settings(data)
    seeded = json.loads((data / "settings.json").read_text(encoding="utf-8"))
    seeded["window_theme"] = "system"  # Like this PC: the desktop's light or dark
    (data / "settings.json").write_text(json.dumps(seeded), encoding="utf-8")
    sample = tour.sample_file("zh")
    if sample is None:
        check("the app's FLEURS sample is there", False)
        tour.write_results()
        return 1
    audio = tour.join([tour.read_clip(sample)], gap=1.0)
    fake_server.caption_for = tour.caption_for
    server = fake_server.FakeServer()
    given = [
        "--server",
        server.url,
        "--data",
        str(data),
        "--dictionaries",
        args.dictionaries,
    ]
    second = [sys.executable, "-m", "polyglotic_desktop.main", *given]
    driver = Driver(args.limit, manners(args.tray == "yes", second))

    class Driven(QApplication):
        def __init__(self, qt_argv: list[str]) -> None:
            super().__init__(qt_argv)
            driver.start()

    real_interface = tour.app.new_interface

    def new_interface(*a: Any, **k: Any) -> Any:
        tour.STATE["interface"] = real_interface(*a, **k)
        return tour.STATE["interface"]

    class Recorded(tour.app.DesktopApp):
        def __init__(self, *a: Any, **k: Any) -> None:
            super().__init__(*a, **k)
            tour.STATE["desktop"] = self

    real = tour.app.os_adapters
    swapped = tour.adapters(real, audio)

    def os_adapters(system: str = sys.platform) -> Any:  # the real copy lock
        found = real(system)
        return dataclasses.replace(
            swapped(system), copy_lock=found.copy_lock, let_to_front=found.let_to_front
        )

    tour.app.os_adapters = os_adapters
    tour.app.QApplication = Driven  # type: ignore[misc, assignment]
    tour.app.new_interface = new_interface
    tour.app.DesktopApp = Recorded  # type: ignore[misc]
    try:
        tour.app.main(given)
    except SystemExit:
        pass
    except Exception:  # noqa: BLE001 - said in the results
        check("the app started", False, traceback.format_exc()[-1500:])
    if args.tray == "no":
        check(
            "Quit at the foot of the window ended the app",
            tour.STATE.get("quit_from_window"),
        )
    tour.write_results()
    server.stop()
    failed = [c["check"] for c in tour.RESULTS["checks"] if not c["ok"]]
    print(
        f"manners: {len(tour.RESULTS['checks']) - len(failed)} passed, {len(failed)} failed"
    )
    return 1 if failed else 0


if __name__ == "__main__":
    code = main()
    sys.stdout.flush()
    os._exit(code)
