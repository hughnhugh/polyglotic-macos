"""The real app from source, through its start and the learner's Quit - run
by `tests/test_private_desktop.py` on a desktop of its own, which Windows
never displays (polyglotic-hq 205; `tools/private_desktop.py`).

    python -m tests.app_on_a_desktop OUT [main's options...]   (from the repo root)

`main()` itself, with real windows, on the data folder given: signed out,
so nothing is captured. The following OS adapters are swapped because
they'd reach the user's session from any desktop:
- **hotkeys:** Windows keeps one hotkey table for the whole session, so the
  app's Ctrl+Alt+L, P and H would be taken from the user while it runs;
- **held keys:** model Windows refusing the dictation or speaker key, as on
  the CI runners, without registering a key in the user's session;
- **the app list:** the PC's apps with sound are the user's.

A first run is answered as a learner would (the yes - no language
or level: polyglotic-hq 293); the sign-in is closed. Once the main
window has shown with no question over it, OUT gets `shown.json` (the windows' handles, the
questions asked and the ID the taskbar knows the app by) and each shown window's picture (Qt's own `grab()`). The
test says what's next by a file in OUT, so it can look from outside first:
- `captions`: caption windows show, as when three apps are captioned
  while signed in - the app's own windows, told they're signed in
  (`CaptionWindows.set_connection`), for apps picked as Home's + picks
  them (`adding_app`) - and
  OUT gets `captions.json` (their handles). Quit has to end the app with
  them up: Qt's `quit()` gave up when the main window, kept in the tray,
  came before one of them in Qt's order of windows, and the app ran on
  (polyglotic-hq 141, 215).
- `tray` (holding an action's name, `app.quit`, `app.pause`): once the
  tray's menu shows (a stand-in taskbar's right click on the icon,
  `tools/stand_in_taskbar.py`), OUT gets `tray.json` (the menu, where it
  is, the work area, where Qt says the icon is), that action is clicked
  in it, and `tray` goes.
- `hide`: the main window closed - kept in the tray, it hides - and
  `hide` goes. Whether it shows is in `main.json`, each time it changes.
- `minimise`: the main window minimised, and `minimise` goes; `main.json`
  says that too (polyglotic-hq 310: a second start brings it back).
- `quit`: the app's own Quit, the action the tray and the window use -
  pressed once, as a learner does: after it the tray icon is gone, so a
  Quit the app turned down is one the learner can't press again (205's
  driver pressed it every 100 ms, and the second always worked).

When `main()` ends, OUT gets `ended.json`: the windows still alive then,
which Python would tear down as it stops - with panels bound to their
views, the crash 261's tests hit at exit (polyglotic-hq 269).
"""

from __future__ import annotations

import dataclasses
import json
import sys
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import ClassVar

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QWidget
from tools.private_desktop import grab_windows

from polyglotic_desktop import main as app
from polyglotic_desktop.platform.windows import taskbar
from polyglotic_desktop.ports.capture import PlayingApp
from polyglotic_desktop.ui.app import DesktopApp
from polyglotic_desktop.ui_next.caption_windows import CaptionWindows
from polyglotic_desktop.ui_next.main_window import MainWindow

OUT = Path(sys.argv[1])
QUIET_SEC = 1.5
"""How long the main window shows with no question over it before it counts
as started (the sign-in comes just after the event loop starts)."""
GIVE_UP_SEC = 90.0
"""Quit anyway if the test never says to: nothing is left running."""


class NoHotkeys:
    def __init__(self, keys: Mapping[str, Callable[[], None]]) -> None:
        self.keys = keys

    def start(self) -> list[str]:
        return []

    def stop(self) -> None:
        pass


class UnavailableHoldKey:
    def start(self) -> bool:
        return False

    def stop(self) -> None:
        pass


class NoApps:
    def playing_apps(self) -> list[PlayingApp]:
        return []


class Recorded(DesktopApp):
    """The app's own, kept where the driver can press its Quit."""

    made: ClassVar[list[DesktopApp]] = []

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        Recorded.made.append(self)


class Driven(QApplication):
    """The app's QApplication, with a step every 100 ms on its own thread -
    in the questions' own event loops too."""

    def __init__(self, argv: list[str]) -> None:
        super().__init__(argv)
        self.asked: list[str] = []
        self.began = time.monotonic()
        self.quiet_since: float | None = None
        self.shown = False
        self.captioned = False
        self.quit_pressed = False
        self.main_shows: tuple[bool, bool] | None = None
        self.startTimer(100)

    def timerEvent(self, _: object) -> None:
        modal = self.activeModalWidget()
        if isinstance(modal, QDialog):
            self.quiet_since = None
            self.answer(modal)
            return
        if not self.shown:
            if self.main_window() is None:
                return
            now = time.monotonic()
            self.quiet_since = self.quiet_since or now
            if now - self.quiet_since >= QUIET_SEC:
                self.started()
            return
        if self.quit_pressed:
            return
        self.say_whether_main_shows()
        if (OUT / "quit").exists() or time.monotonic() - self.began > GIVE_UP_SEC:
            self.quit_pressed = True  # once, as a learner: then the tray icon is gone
            Recorded.made[0].quit.trigger()
        elif (OUT / "captions").exists() and not (OUT / "captions.json").exists():
            self.caption_window()
        elif (OUT / "tray").exists():
            self.from_the_tray((OUT / "tray").read_text(encoding="utf-8").strip())
        elif (OUT / "hide").exists():
            (OUT / "hide").unlink()
            main = self.main_window()
            if main is not None:
                main.close()  # kept in the tray: it hides
        elif (OUT / "minimise").exists():
            (OUT / "minimise").unlink()
            main = self.main_window()
            if main is not None:
                main.showMinimized()

    def say_whether_main_shows(self) -> None:
        """`main.json` says whether the main window shows, and whether it's
        minimised, as Qt has it - each time that changes (a service's
        session never shows a window to Windows, so the test can't look
        from outside there)."""
        main = self.main_window()
        said = (main is not None, main is not None and main.isMinimized())
        if said != self.main_shows:
            try:
                _write(OUT / "main.json", {"shows": said[0], "minimised": said[1]})
            except PermissionError as error:
                # Windows can deny replacement while the test reads the previous
                # state. Leave it unpublished and try again on the next timer tick.
                if getattr(error, "winerror", None) not in (5, 32):  # Windows' only
                    raise
                return
            self.main_shows = said

    def from_the_tray(self, name: str) -> None:
        """Once the taskbar's right click has opened the tray's menu: its
        facts in `tray.json`, then the action named `name` in it clicked -
        Qt's own click, from inside (`QTest`), never the real mouse. Quit
        once; any other, each time `tray` says it."""
        desktop = Recorded.made[0]
        menu = desktop.tray_menu
        if not menu.isVisible() or desktop.tray is None:
            return
        (OUT / "tray").unlink()
        screen = QGuiApplication.screenAt(menu.geometry().center())
        area = (screen or QGuiApplication.primaryScreen()).availableGeometry()
        facts = {
            "menu": [a.text() for a in menu.actions() if not a.isSeparator()],
            "window": int(menu.winId()),
            "rect": _rect(menu.geometry()),
            "area": _rect(area),
            "icon": _rect(desktop.tray.geometry()),
            "ratio": menu.devicePixelRatioF(),
        }
        _write(OUT / "tray.json", facts)
        (action,) = [a for a in menu.actions() if a.objectName() == name]
        self.quit_pressed = action is desktop.quit
        at = menu.actionGeometry(action).center()
        QTest.mouseClick(menu, Qt.MouseButton.LeftButton, pos=at)

    def caption_window(self) -> None:
        """Caption windows up, as when apps are captioned signed in;
        `captions.json` once they show."""
        desktop = Recorded.made[0]
        windows = desktop.findChild(CaptionWindows)
        assert windows is not None
        if not self.captioned:
            self.captioned = True
            # a later session: the tray's one-time note was said in the first
            desktop.settings.update(tray_note_shown=True)
            windows.set_connection(None, None)  # signed in, as far as they know
            # three apps picked, as Home's + picks them: the windows follow the
            # settings, so a later change of any setting leaves them up. Put up
            # behind the settings' back, they went at the next one - "Caption
            # my own speech", turned by the windows themselves (478) - to the
            # settings' own choice: none, or everything the PC plays (484;
            # polyglotic-hq 500)
            for name in ("discord", "chrome", "zoom"):
                picked = app.adding_app(desktop.settings.value, name)
                assert picked is not None
                desktop.settings.update(**picked)
            return
        if windows.joined_window is not None:
            # three windows of their own, as a learner who separated them has:
            # they start joined (polyglotic-hq 554), and Quit is checked with
            # several of the app's windows up (141, 215)
            windows.separate()
            return
        shown = [int(w.winId()) for w in windows.windows.values() if w.isVisible()]
        if shown:
            _write(OUT / "captions.json", {"windows": shown})

    def answer(self, question: QDialog) -> None:
        name = type(question).__name__
        if not self.asked or self.asked[-1] != name:
            self.asked.append(name)
        if name == "ConsentDialog":
            agree = getattr(question, "agree", None)
            if agree is not None:
                agree.setChecked(True)  # the yes to the agreement
        if name in ("LanguagePicker", "LevelPicker", "ConsentDialog"):
            question.accept()
        else:  # the sign-in, or anything not expected: closed
            question.reject()

    def main_window(self) -> QWidget | None:
        for widget in self.topLevelWidgets():
            if isinstance(widget, MainWindow) and widget.isVisible():
                return widget
        return None

    def started(self) -> None:
        self.shown = True
        main = self.main_window()
        assert main is not None
        pictures = grab_windows(OUT)
        shown = [w for w in self.topLevelWidgets() if w.isVisible()]
        facts = {
            "main": int(main.winId()),
            "windows": {type(w).__name__: int(w.winId()) for w in shown},
            "asked": self.asked,
            "pictures": [p.name for p in pictures],
            "tray": Recorded.made[0].tray is not None,
            "seconds": round(time.monotonic() - self.began, 1),
            "taskbar_id": taskbar.explicit_app_id(),  # as Windows has it (245)
        }
        _write(OUT / "shown.json", facts)


def _rect(rect: QRect) -> list[int]:
    return [rect.x(), rect.y(), rect.width(), rect.height()]


def _write(path: Path, facts: object) -> None:
    """`facts` as JSON at `path`, whole when it's there."""
    written = path.with_name(path.name + ".part")
    written.write_text(json.dumps(facts), encoding="utf-8")
    written.replace(path)


def os_adapters(system: str = sys.platform) -> app.OsAdapters:
    real = REAL_ADAPTERS(system)
    return dataclasses.replace(
        real,
        hotkeys=NoHotkeys,
        hold_key=lambda *_: UnavailableHoldKey(),
        app_list=NoApps,
    )


REAL_ADAPTERS = app.os_adapters

if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    app.os_adapters = os_adapters
    app.QApplication = Driven  # type: ignore[misc,assignment]
    app.DesktopApp = Recorded  # type: ignore[misc]
    try:
        app.main(sys.argv[2:])
    finally:  # main() ends with sys.exit: the windows Python would still tear down
        alive = QApplication.topLevelWidgets()
        _write(OUT / "ended.json", {"alive": sorted(type(w).__name__ for w in alive)})
