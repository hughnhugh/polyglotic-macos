"""The caption windows over a full-screen app and dictation's typing, proven
on GitHub's Mac (polyglotic-hq 429): the macOS job's `parity` part. Each
check prints a pass, fail or unknown line and goes in a JSON file; the job
fails only on a fail - unknown is what the machine didn't let us see.

    uv run --no-sync python -m tools.macos_full_screen_checks OUT.json
    uv run --no-sync python -m tools.macos_full_screen_checks OUT.json --dry-run  # any OS: the plan

A real caption window (`ui_next.caption_window.CaptionWindow`) on macOS's
own windows (Qt's cocoa), and TextEdit with a new plain-text file. Where a
window is, is read from macOS's window list - each window's number, level
and owner, front to back (`platform.macos.window_list`): never a picture.

- full_screen_qt_only: the caption window shown with Qt's flags alone,
  then TextEdit made full-screen (its own Space): is it on that Space,
  above TextEdit? (171 expects not: the baseline, never a failure.)
- full_screen: the same with the Mac's `MacOnTop` (the screen saver's
  level, every Space, a non-activating panel; the app an accessory from
  before its first window, as the app is): on screen above TextEdit's
  full-screen window, TextEdit still in front and still full-screen.
- shown_after_full_screen: TextEdit full-screen first, then the window
  shown there.
- locked: the window locked while TextEdit is full-screen (Qt hides it and
  shows it again at its own level); the front watch hears it and the
  window is set again: at the screen saver's level, letting clicks
  through.
- sign: the dictation sign shown over the full-screen app (the interface
  never hands it over): shown although the app isn't active, and set by
  the watch's call too, above TextEdit.
- popover_in_front: the caption window's settings popover opened over
  it: in front of it in the window list as it opens, after the windows are
  put on top again (what a caption's arrival does) and a moment later
  (polyglotic-hq 515: it went behind).
- click: unlocked, a click on it (System Events' `click at`): TextEdit
  stays in front and full-screen.
- typed: dictation's `type_text` types "héllo 你好 😀" into TextEdit, read
  back through Accessibility; `keyboard_window` is TextEdit's window.
- hover_in_background: TextEdit in front, the real mouse (cliclick) moved
  over the caption window with the app's `PointerWatch` on: the window
  hears it and shows its strip (polyglotic-hq 515: Qt drops the mouse of an
  app that isn't active, so the strip never showed).
- key_combination: dictation's key Control+Command+D registered through
  Carbon; System Events presses it: down, then up, and TextEdit gets no
  "d"; whether the same combination is refused a second time (a fact).
- key_alone: Left Command held alone (System Events' `key down command`):
  down, then up, read from the modifiers' state.
- escape_cancels: dictation listening (`ui.dictation.Dictating` on
  stand-ins for the mic and the server, the Mac's `keys.MacKeys` for Esc),
  TextEdit in front; System Events presses Esc: the hold is cancelled
  (polyglotic-hq 438). Facts: whether this machine lets the app read keys
  (Accessibility; Input Monitoring's preflight, never asked for).
- click_elsewhere: a caption window's settings popover open (its `keys`
  the Mac's); cliclick (Homebrew's) clicks in TextEdit's window - a real
  mouse event, which System Events' `click at` isn't: the popover closes
  (438).
- resize_by_mouse: the caption window's bottom-right corner dragged 40 x 30
  by cliclick from 2 px inside its edge: it grows, through the app's own
  resizing - the window's remembered place follows (polyglotic-hq 515:
  macOS resized it itself, past the app's least size, and nothing was
  remembered).
- accessibility_settings: Settings > Dictation's "Open System Settings"
  (`text_input.Permission.open_settings`): System Settings opens (438).

Never the user's PC: this runs only on GitHub's macOS machine. It types
and presses keys into TextEdit there, through the app's own dictation
file and System Events.
"""

from __future__ import annotations

import argparse
import ctypes
import ctypes.util
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

PASS, FAIL, UNKNOWN = "pass", "fail", "unknown"
TYPED = "héllo 你好 😀 ok"


@dataclass
class Result:
    check: str
    outcome: str
    said: str
    facts: dict[str, Any] = field(default_factory=dict)


def above(listed: list[Any], ours: int, theirs_pid: int) -> tuple[bool, bool]:
    """Whether window `ours` is on screen, and whether it comes before
    (above) every on-screen window of process `theirs_pid`."""
    numbers = [w.number for w in listed]
    if ours not in numbers:
        return False, False
    mine = numbers.index(ours)
    theirs = [i for i, w in enumerate(listed) if w.pid == theirs_pid]
    return True, bool(theirs) and all(mine < i for i in theirs)


def full_screen_verdict(
    on_screen: bool, is_above: bool, front_kept: bool, still_full: bool
) -> tuple[str, str]:
    if not still_full:
        return UNKNOWN, "TextEdit wasn't full-screen when read"
    if on_screen and is_above and front_kept:
        return PASS, "on screen above the full-screen app, which stayed in front"
    if not front_kept:
        return FAIL, "the full-screen app lost the front"
    return FAIL, "on screen" if on_screen else "not on the full-screen app's Space"


def exit_code(results: list[Result]) -> int:
    return 1 if any(r.outcome == FAIL for r in results) else 0


def report(results: list[Result], facts: dict[str, Any]) -> dict[str, Any]:
    counts = {o: sum(r.outcome == o for r in results) for o in (PASS, FAIL, UNKNOWN)}
    return {"summary": counts, "facts": facts, "checks": [asdict(r) for r in results]}


def plan() -> list[str]:
    return [line.split(":")[0].strip("- ") for line in __doc__.split("\n- ")[1:]]


# -- macOS (only on a Mac) ----------------------------------------------------------


class _MemoryStore:
    """Dictation's settings, kept in memory."""

    def __init__(self, values: dict[str, object]) -> None:
        self.values = dict(values)

    def load(self) -> dict[str, object]:
        return dict(self.values)

    def save(self, values: Any) -> None:
        self.values = dict(values)


class _StandInMic:
    """Dictation's mic: opened and closed, never listening."""

    def open(self, hold: int, on_piece: Callable[[Any], None]) -> None:
        pass

    def close(self, tail: float) -> None:
        pass

    def drop(self) -> None:
        pass

    def level(self) -> float:
        return 0.0


def _pid_of(name: str) -> int:
    done = subprocess.run(
        ["pgrep", "-x", name], check=False, capture_output=True, text=True
    )
    found = done.stdout.split()
    return int(found[0]) if found else 0


def _cliclick() -> str | None:
    """cliclick (a click as a mouse makes it), installed from Homebrew on
    GitHub's Mac if it isn't there; None if it can't be."""
    found = shutil.which("cliclick")
    if found is None and shutil.which("brew"):
        subprocess.run(
            ["brew", "install", "--quiet", "cliclick"],
            check=False,
            capture_output=True,
            timeout=300,
            env={**os.environ, "HOMEBREW_NO_AUTO_UPDATE": "1"},
        )
        found = shutil.which("cliclick")
    return found


def _application_services() -> ctypes.CDLL:
    path = ctypes.util.find_library("ApplicationServices")
    if path is None:
        raise OSError("no ApplicationServices")
    return ctypes.CDLL(path)


def _listen_access() -> bool | None:
    """Input Monitoring's preflight (asks nothing): a fact for the report."""
    lib = _application_services()
    try:
        call = lib.CGPreflightListenEventAccess
    except AttributeError:
        return None
    call.restype = ctypes.c_bool
    return bool(call())


def _escape_state() -> bool:
    """Quartz's key state for Esc: a fact (the app doesn't read keys so)."""
    lib = _application_services()
    lib.CGEventSourceKeyState.restype = ctypes.c_bool
    lib.CGEventSourceKeyState.argtypes = [ctypes.c_int32, ctypes.c_uint16]
    return bool(lib.CGEventSourceKeyState(0, 0x35))


class Ax:
    """TextEdit's window and text through Accessibility (the runner has the
    permission): full-screen on or off, and the text it holds."""

    def __init__(self) -> None:
        from polyglotic_desktop.platform.macos import cf

        self.cf = cf
        lib = ctypes.CDLL(ctypes.util.find_library("ApplicationServices") or "")
        p = ctypes.c_void_p
        lib.AXUIElementCreateApplication.restype = p
        lib.AXUIElementCreateApplication.argtypes = [ctypes.c_int]
        lib.AXUIElementCopyAttributeValue.restype = ctypes.c_int32
        lib.AXUIElementCopyAttributeValue.argtypes = [p, p, ctypes.POINTER(p)]
        lib.AXUIElementSetAttributeValue.restype = ctypes.c_int32
        lib.AXUIElementSetAttributeValue.argtypes = [p, p, p]
        self.lib = lib

    def _copy(self, element: int, name: str) -> int | None:
        attr = self.cf.create_string(name)
        out = ctypes.c_void_p()
        with self.cf.owned(attr):
            status = self.lib.AXUIElementCopyAttributeValue(
                element, attr, ctypes.byref(out)
            )
        return int(out.value) if status == 0 and out.value else None

    def window(self, pid: int) -> int | None:
        app = self.lib.AXUIElementCreateApplication(pid)
        return self._copy(app, "AXFocusedWindow") or self._copy(app, "AXMainWindow")

    def full_screen(self, pid: int, on: bool) -> bool:
        window = self.window(pid)
        if window is None:
            return False
        attr = self.cf.create_string("AXFullScreen")
        value = self.cf.libraries().constant(
            "kCFBooleanTrue" if on else "kCFBooleanFalse", "cf"
        )
        with self.cf.owned(attr):
            return self.lib.AXUIElementSetAttributeValue(window, attr, value) == 0

    def is_full_screen(self, pid: int) -> bool:
        window = self.window(pid)
        value = self._copy(window, "AXFullScreen") if window else None
        true = self.cf.libraries().constant("kCFBooleanTrue", "cf")
        return value == true

    def text(self, pid: int) -> str | None:
        app = self.lib.AXUIElementCreateApplication(pid)
        focused = self._copy(app, "AXFocusedUIElement")
        return self.cf.text(self._copy(focused, "AXValue")) if focused else None


def server_entry(number: int) -> dict[str, Any]:
    """What the window server says of one window, on screen or not: its
    layer and whether it's on screen (the window list, never a picture)."""
    from polyglotic_desktop.platform.macos import cf, window_list

    g = window_list._graphics()
    including_window = 1 << 3  # kCGWindowListOptionIncludingWindow
    array = g.cg.CGWindowListCopyWindowInfo(including_window, number)
    if not array:
        return {}
    with cf.owned(array):
        if g.count(array) < 1:
            return {}
        info = g.at(array, 0)
        onscreen_key = ctypes.c_void_p.in_dll(g.cg, "kCGWindowIsOnscreen").value
        flag = cf.value(info, onscreen_key) if onscreen_key else None
        true = cf.libraries().constant("kCFBooleanTrue", "cf")
        return {
            "layer": window_list._integer(info, g.keys["Layer"]),
            "on_screen": flag == true,
        }


class Heard:
    """Every notification `FrontWatch` listens for, by name, as it comes."""

    def __init__(self) -> None:
        from polyglotic_desktop.platform.macos import objc, on_top

        self.names: list[str] = []
        self._block = objc.Block(self._heard)
        workspace = objc.send(
            objc.send(objc.cls("NSWorkspace"), "sharedWorkspace"), "notificationCenter"
        )
        app = objc.send(objc.cls("NSNotificationCenter"), "defaultCenter")
        centres = {"workspace": int(workspace or 0), "app": int(app or 0)}
        for centre, name in on_top.WATCHED:
            observer = objc.send(
                centres[centre],
                "addObserverForName:object:queue:usingBlock:",
                on_top._constant(name),
                None,
                None,
                self._block.address,
                argtypes=[ctypes.c_void_p] * 4,
            )
            if observer:
                objc.send(int(observer), "retain")

    def _heard(self, notification: int) -> None:
        from polyglotic_desktop.platform.macos import objc

        name = objc.text(objc.send(notification, "name")) if notification else None
        self.names.append((name or "?").replace("Notification", "").replace("NS", ""))


class Run:
    def __init__(self, out: Path) -> None:
        self.out = out
        self.results: list[Result] = []
        self.facts: dict[str, Any] = {
            "mac": platform.mac_ver()[0],
            "machine": platform.machine(),
        }

    def add(self, check: str, outcome: str, said: str, **facts: Any) -> None:
        self.results.append(Result(check, outcome, said, facts))
        print(f"{outcome:7} {check}: {said}", flush=True)

    def guarded(self, check: str, step: Callable[[], None]) -> None:
        try:
            step()
        except Exception as error:  # noqa: BLE001 - one check's crash isn't the run's
            self.add(
                check,
                UNKNOWN,
                f"{type(error).__name__}: {error}",
                trace=traceback.format_exc(),
            )

    def wait(self, seconds: float) -> None:
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            self.qapp.processEvents()
            time.sleep(0.02)

    def until(self, done: Callable[[], bool], seconds: float) -> bool:
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            self.qapp.processEvents()
            if done():
                return True
            time.sleep(0.05)
        return done()

    def script(
        self, *lines: str, during: Callable[[], None] | None = None
    ) -> tuple[bool, str]:
        """osascript, with Qt's events going (Carbon's come through them);
        `during` called every few milliseconds while it runs."""
        args = ["osascript"]
        for line in lines:
            args += ["-e", line]
        process = subprocess.Popen(
            args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
        )
        while process.poll() is None:
            self.qapp.processEvents()
            if during is not None:
                during()
            time.sleep(0.005 if during is not None else 0.02)
        said = (process.stdout.read() if process.stdout else "").strip()
        return process.returncode == 0, said

    def run_quietly(self, args: list[str]) -> tuple[bool, str]:
        """A command, with Qt's events going meanwhile."""
        process = subprocess.Popen(
            args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
        )
        while process.poll() is None:
            self.qapp.processEvents()
            time.sleep(0.02)
        said = (process.stdout.read() if process.stdout else "").strip()
        return process.returncode == 0, said

    # -- setting up ------------------------------------------------------------------

    def start(self) -> None:
        from PySide6.QtWidgets import QApplication

        from polyglotic_desktop.platform.macos import on_top, text_input

        app = QApplication.instance() or QApplication(["parity"])
        assert isinstance(app, QApplication)
        self.qapp = app
        self.facts["platform"] = self.qapp.platformName()
        self.heard = Heard()
        self.facts["accessibility"] = text_input.allowed(ask=False)
        self.ax = Ax()
        folder = Path(tempfile.mkdtemp(prefix="parity-"))
        self.document = folder / "parity.txt"
        self.document.write_text("", encoding="utf-8")
        subprocess.run(
            ["open", "-a", "TextEdit", str(self.document)], check=True, timeout=30
        )
        self.textedit = 0
        self.until(lambda: bool(self._textedit_pid()), 20)
        self.textedit = self._textedit_pid()
        self.until(lambda: self.ax.window(self.textedit) is not None, 20)
        self.facts["textedit_pid"] = self.textedit
        self.on_top = on_top.MacOnTop()  # the app an accessory, as main makes it
        self.facts["policy_before_the_first_window"] = self.policy()
        self.window = self._caption_window()

    def _textedit_pid(self) -> int:
        done = subprocess.run(
            ["pgrep", "-x", "TextEdit"], check=False, capture_output=True, text=True
        )
        found = done.stdout.split()
        return int(found[0]) if found else 0

    def _caption_window(self) -> Any:
        from polyglotic_desktop.core.listening.sources import SourceId, SourceLabel
        from polyglotic_desktop.ui_next.caption_window import CaptionWindow
        from polyglotic_desktop.ui_next.views.caption_window import WindowChoices
        from polyglotic_desktop.ui_next.views.placement import Rect

        window = CaptionWindow(
            "parity",
            SourceId("app"),
            WindowChoices(),
            SourceLabel("TextEdit", "#4dd0e1"),
            areas=lambda: [Rect(0, 0, 1200, 700)],
        )
        window.setGeometry(100, 100, 600, 160)
        return window

    # -- reading ----------------------------------------------------------------------

    def ns_window(self) -> int:
        from polyglotic_desktop.platform.macos import on_top

        return on_top.window_of(int(self.window.winId()))

    def window_facts(self) -> dict[str, Any]:
        from polyglotic_desktop.platform.macos import objc

        ns = self.ns_window()
        if not ns:
            return {}

        def number(selector: str) -> int:
            return int(objc.send(ns, selector, restype=ctypes.c_long))

        def flag(selector: str) -> bool:
            return bool(objc.send(ns, selector, restype=ctypes.c_bool))

        return {
            "class": objc.text(objc.send(ns, "className")),
            "number": number("windowNumber"),
            "level": number("level"),
            "collection_behaviour": number("collectionBehavior"),
            "style_mask": number("styleMask"),
            "visible": flag("isVisible"),
            "hides_on_deactivate": flag("hidesOnDeactivate"),
            "ignores_mouse": flag("ignoresMouseEvents"),
            "can_become_key": flag("canBecomeKeyWindow"),
            "on_active_space": flag("isOnActiveSpace"),
            "occlusion_visible": bool(number("occlusionState") & 2),
            "server": server_entry(number("windowNumber")),
        }

    def where(self) -> dict[str, Any]:
        from polyglotic_desktop.platform.macos import window_list

        listed = window_list.on_screen()
        facts = self.window_facts()
        on_screen, is_above = above(listed, facts.get("number", -1), self.textedit)
        return {
            "window": facts,
            "on_screen": on_screen,
            "above_textedit": is_above,
            "front_pid": window_list.front_pid(),
            "textedit_full_screen": self.ax.is_full_screen(self.textedit),
            "list": [
                (w.layer, "ours" if w.number == facts.get("number") else w.pid)
                for w in listed[:12]
            ],
        }

    def policy(self) -> int:
        """The app's activation policy (1: an accessory)."""
        from polyglotic_desktop.platform.macos import objc, on_top

        app = on_top._app()
        return int(objc.send(app, "activationPolicy", restype=ctypes.c_long))

    def to_front(self) -> None:
        subprocess.run(["open", "-a", "TextEdit"], check=False, timeout=30)
        self.wait(1.5)

    def full_screen(self, on: bool) -> bool:
        if self.ax.is_full_screen(self.textedit) != on:
            self.ax.full_screen(self.textedit, on)
        done = self.until(lambda: self.ax.is_full_screen(self.textedit) == on, 10)
        self.wait(2.5)  # the Space's animation
        return done

    # -- the checks -------------------------------------------------------------------

    def over_full_screen(self, check: str, adapter: bool) -> None:
        self.full_screen(False)
        self.window.hide()
        self.wait(0.5)
        self.window.show()
        self.wait(0.3)
        if adapter:
            self.on_top.put_on_top([int(self.window.winId())])
        self.wait(0.5)
        on_desktop = self.where()
        self.to_front()
        full = self.full_screen(True)
        where = self.where()
        where["on_the_desktop_before"] = {
            "on_screen": on_desktop["on_screen"],
            "window": on_desktop["window"],
            "list": on_desktop["list"],
        }
        where["policy"] = self.policy()
        front_kept = where["front_pid"] == self.textedit
        outcome, said = full_screen_verdict(
            where["on_screen"], where["above_textedit"], front_kept, full
        )
        if not adapter:  # the baseline: said as found, never a failure
            outcome = UNKNOWN if outcome == UNKNOWN else PASS
            said = f"Qt alone: {'above' if where['above_textedit'] else 'not above'} the full-screen app"
        self.add(check, outcome, said, **where)

    def shown_after_full_screen(self) -> None:
        """TextEdit full-screen first, then the caption window shown and
        set while its Space is the active one."""
        self.window.hide()
        self.to_front()
        full = self.full_screen(True)
        self.window.show()
        self.on_top.put_on_top([int(self.window.winId())])
        self.wait(1.0)
        where = self.where()
        outcome, said = full_screen_verdict(
            where["on_screen"],
            where["above_textedit"],
            where["front_pid"] == self.textedit,
            full,
        )
        self.add("shown_after_full_screen", outcome, said, **where)

    def locked(self) -> None:
        from polyglotic_desktop.platform.macos import on_top

        heard: list[float] = []

        def changed() -> None:  # as the interface's keep_on_top does
            heard.append(time.monotonic())
            self.on_top.put_on_top([int(self.window.winId())])

        watch = on_top.FrontWatch(changed)
        self.facts["front_watch"] = watch.start()
        self.full_screen(True)
        self.window.set_locked(True)
        self.until(lambda: self.window_facts().get("level") == on_top.LEVEL, 3)
        where = self.where()
        where["notifications"] = len(heard)
        ok = (
            where["window"].get("level") == on_top.LEVEL
            and where["window"].get("ignores_mouse")
            and where["above_textedit"]
        )
        self.add(
            "locked",
            PASS if ok else FAIL,
            "set again after Qt's re-show; clicks pass through"
            if ok
            else "not set again",
            **where,
        )
        self.window.set_locked(False)
        self.wait(1.0)
        self.watch = watch

    def sign(self) -> None:
        """The dictation sign, which the interface never hands over, shown
        over the full-screen app: the watch hears it and `put_on_top` sets
        it too."""
        from polyglotic_desktop.platform.macos import objc, on_top, window_list
        from polyglotic_desktop.ui_next.dictation_sign import DictationSign

        self.full_screen(True)
        sign = DictationSign()
        sign.setGeometry(200, 300, 240, 60)
        sign.show()
        ns = on_top.window_of(int(sign.winId()))

        def level() -> int:
            return int(objc.send(ns, "level", restype=ctypes.c_long))

        # the caption windows' level, or above them (515: `on_top.ABOVE`)
        self.until(lambda: level() >= on_top.LEVEL, 3)
        number = int(objc.send(ns, "windowNumber", restype=ctypes.c_long))
        shown, is_above = above(window_list.on_screen(), number, self.textedit)
        ok = level() >= on_top.LEVEL and shown and is_above
        self.add(
            "sign",
            PASS if ok else FAIL,
            "set when shown, above the full-screen app" if ok else "left at Qt's level",
            level=level(),
            on_screen=shown,
            above_textedit=is_above,
        )
        sign.hide()
        sign.deleteLater()

    def popover_in_front(self) -> None:
        """A caption window's settings popover open over it: in front of its
        window in macOS's window list as it opens, after the caption windows
        are put on top again (what a caption's arrival does, at most once a
        second) and a moment later (polyglotic-hq 515: Qt made the popover
        at its window's level, and ordering the window to the front put it
        behind)."""
        from polyglotic_desktop.platform.macos import objc, on_top, window_list

        self.full_screen(False)
        self.window.set_locked(False)
        self.window.setGeometry(100, 100, 600, 160)
        self.window.show()
        self.on_top.put_on_top([int(self.window.winId())])
        self.wait(0.5)
        self.window.toggle_settings()
        popover = self.window.popover
        self.until(lambda: popover is not None and popover.isVisible(), 2)
        if popover is None or not popover.isVisible():
            self.add("popover_in_front", UNKNOWN, "the popover didn't open")
            return

        def number(widget: Any) -> int:
            ns = on_top.window_of(int(widget.winId()))
            return int(objc.send(ns, "windowNumber", restype=ctypes.c_long))

        def order() -> dict[str, Any]:
            listed = [w.number for w in window_list.on_screen()]
            mine, theirs = number(self.window), number(popover)
            return {
                "window": listed.index(mine) if mine in listed else None,
                "popover": listed.index(theirs) if theirs in listed else None,
            }

        self.wait(0.5)
        rows = {"opened": order()}
        self.on_top.put_on_top([int(self.window.winId())])
        self.wait(0.3)
        rows["put on top"] = order()
        self.wait(1.5)
        rows["after"] = order()
        front = all(
            r["popover"] is not None and r["window"] is not None
            and r["popover"] < r["window"]
            for r in rows.values()
        )  # fmt: skip
        overlaps = popover.frameGeometry().intersects(self.window.frameGeometry())
        self.add(
            "popover_in_front",
            PASS if front else FAIL,
            "the popover stayed in front of its caption window"
            if front
            else "the popover went behind its caption window",
            rows=rows,
            overlaps=overlaps,
            popover=self.window_facts_of(popover),
        )
        popover.close()
        # as the checks after it expect: their own popover (with the key
        # watch they hand the window), TextEdit full-screen again
        self.window.popover = None
        popover.deleteLater()
        self.full_screen(True)
        self.wait(0.3)

    def window_facts_of(self, widget: Any) -> dict[str, Any]:
        from polyglotic_desktop.platform.macos import objc, on_top

        ns = on_top.window_of(int(widget.winId()))
        if not ns:
            return {}
        return {
            "level": int(objc.send(ns, "level", restype=ctypes.c_long)),
            "style_mask": int(objc.send(ns, "styleMask", restype=ctypes.c_ulong)),
        }

    def click(self) -> None:
        facts = self.window_facts()
        if not facts.get("visible"):
            self.add("click", UNKNOWN, "the window isn't showing")
            return
        geometry = self.window.frameGeometry()
        x, y = geometry.center().x(), geometry.center().y()
        ok, said = self.script(
            f'tell application "System Events" to click at {{{x}, {y}}}'
        )
        self.wait(1.0)
        where = self.where()
        if not ok:
            self.add(
                "click", UNKNOWN, f"System Events couldn't click: {said[:200]}", **where
            )
            return
        kept = where["front_pid"] == self.textedit and where["textedit_full_screen"]
        self.add(
            "click",
            PASS if kept else FAIL,
            "TextEdit kept the front and its full screen"
            if kept
            else "the click took the front",
            **where,
        )

    def typed(self) -> None:
        from polyglotic_desktop.platform.macos import text_input, window_list

        self.full_screen(False)
        self.to_front()
        if not self.facts.get("accessibility"):
            self.add(
                "typed",
                UNKNOWN,
                "this machine hasn't given the Accessibility permission",
            )
            return
        window = text_input.keyboard_window()
        expected = window_list.front_window(window_list.on_screen(), self.textedit)
        sent = text_input.type_text(TYPED)
        self.wait(1.0)
        got = self.ax.text(self.textedit)
        # TextEdit capitalises a sentence's first letter itself
        ok = sent and (got or "").casefold() == TYPED.casefold()
        self.add(
            "typed",
            PASS if ok else FAIL,
            "TextEdit holds the words typed" if ok else "TextEdit doesn't hold them",
            sent=sent,
            got=got,
            keyboard_window=window,
            textedit_window=expected,
        )
        self.add(
            "keyboard_window",
            PASS if window and window == expected else FAIL,
            "TextEdit's window" if window == expected else "another window",
            keyboard_window=window,
            textedit_window=expected,
        )

    def hover_in_background(self) -> None:
        from polyglotic_desktop.platform.macos import objc
        from polyglotic_desktop.ui_next.pointer_watch import PointerWatch

        clicker = _cliclick()
        if clicker is None:
            self.add("hover_in_background", UNKNOWN, "no cliclick on this machine")
            return
        self.full_screen(False)
        self.to_front()
        window = self.window
        window.set_locked(False)
        window.setGeometry(100, 100, 600, 160)  # where the later checks expect it
        window.show()
        self.on_top.put_on_top([int(window.winId())])
        watch = PointerWatch(lambda: [window], window)
        watch.start()
        self.wait(0.6)
        g = window.frameGeometry()
        self.run_quietly(
            [clicker, "-w", "60", f"m:{g.x() + 20},{g.y() - 80}",
             f"m:{g.center().x()},{g.center().y()}"]
        )  # fmt: skip
        self.until(lambda: bool(window.hovered), 2)
        app = objc.send(objc.cls("NSApplication"), "sharedApplication")
        active = bool(objc.send(app, "isActive", restype=ctypes.c_bool))
        facts = {
            "hovered": bool(window.hovered),
            "watching": watch.timer.isActive(),
            "app_active": active,
        }
        watch.timer.stop()
        watch.deleteLater()
        self.run_quietly([clicker, f"m:{g.x() + 20},{g.y() - 80}"])
        self.wait(0.6)
        if active:
            self.add("hover_in_background", UNKNOWN, "the app was active", **facts)
        else:
            self.add(
                "hover_in_background",
                PASS if facts["hovered"] else FAIL,
                "the window heard the mouse with TextEdit in front"
                if facts["hovered"]
                else "nothing heard with TextEdit in front",
                **facts,
            )

    def key_combination(self) -> None:
        from polyglotic_desktop.platform.macos.hold_key import MacHoldKey

        said: list[str] = []
        key = MacHoldKey(
            "ctrl+win+d", lambda: said.append("down"), lambda: said.append("up")
        )
        taken = key.start()
        second = MacHoldKey("ctrl+win+d", lambda: None, lambda: None)
        second_taken = second.start()
        second.stop()
        self.to_front()
        before = self.ax.text(self.textedit)
        ok, out = self.script(
            'tell application "System Events" to key code 2 using {command down, control down}'
        )
        self.until(lambda: said == ["down", "up"], 3)
        after = self.ax.text(self.textedit)
        key.stop()
        if not ok:
            self.add(
                "key_combination", UNKNOWN, f"System Events couldn't press: {out[:200]}"
            )
            return
        passed = taken and said == ["down", "up"] and before == after
        self.add(
            "key_combination",
            PASS if passed else FAIL,
            f"taken {taken}, heard {said}, TextEdit unchanged {before == after}",
            second_taker_refused=not second_taken,
        )

    def key_alone(self) -> None:
        from polyglotic_desktop.platform.macos import hold_key

        said: list[str] = []
        key = hold_key.MacHoldKey(
            "left_ctrl",
            lambda: said.append("down"),
            lambda: said.append("up"),
            lambda: said.append("other"),
        )
        key.start()
        flags: list[int] = []
        ok, out = self.script(
            'tell application "System Events" to key down command',
            "delay 0.6",
        )
        flags.append(hold_key.flags_now())
        self.script('tell application "System Events" to key up command')
        self.until(lambda: said == ["down", "up"], 3)
        key.stop()
        if not ok:
            self.add(
                "key_alone",
                UNKNOWN,
                f"System Events couldn't hold Command: {out[:200]}",
            )
            return
        self.add(
            "key_alone",
            PASS if said == ["down", "up"] else UNKNOWN,
            f"heard {said}",
            flags_while_held=hex(flags[0]),
        )

    def escape_cancels(self) -> None:
        from polyglotic_desktop.core.listening.dictation import Said, Stage
        from polyglotic_desktop.platform.macos import keys
        from polyglotic_desktop.ui.dictation import Dictating
        from polyglotic_desktop.ui.settings import Settings

        self.to_front()
        self.facts["input_monitoring_preflight"] = _listen_access()
        signs: list[str] = []
        dictating = Dictating(
            Settings(_MemoryStore({"dictation": True})),
            _StandInMic(),
            lambda _request, _speech: None,
            lambda _text: True,
            lambda: 1,
            keys.MacKeys(),
            lambda _wanted: True,
        )
        dictating.sign_changed.connect(lambda state, _level: signs.append(state))
        dictating.key_down()
        self.until(lambda: dictating.dictation.stage is Stage.LISTENING, 2)
        listening = dictating.dictation.stage is Stage.LISTENING
        self.wait(0.3)
        seen: list[bool] = []
        ok, out = self.script(
            'tell application "System Events" to key code 53',
            during=lambda: seen.append(_escape_state()),
        )
        self.until(lambda: dictating.dictation.stage is Stage.IDLE, 2)
        cancelled = dictating.dictation.said is Said.CANCELLED
        dictating.key_up()
        dictating.stop()
        dictating.deleteLater()
        if not ok:
            self.add(
                "escape_cancels", UNKNOWN, f"System Events couldn't press: {out[:200]}"
            )
            return
        facts = {
            "listening_before": listening,
            "signs": signs,
            "key_state_saw_escape": any(seen),
            "accessibility": self.facts.get("accessibility"),
        }
        if cancelled:
            self.add(
                "escape_cancels", PASS, "Esc in TextEdit cancelled the hold", **facts
            )
        elif not self.facts.get("accessibility"):
            self.add(
                "escape_cancels",
                UNKNOWN,
                "no Accessibility here: macOS hides other apps' keys",
                **facts,
            )
        else:
            self.add(
                "escape_cancels", FAIL, "Esc in TextEdit didn't cancel it", **facts
            )

    def click_elsewhere(self) -> None:
        from PySide6.QtGui import QCursor

        from polyglotic_desktop.platform.macos import keys

        self.full_screen(False)
        self.to_front()
        mac_keys = keys.MacKeys()
        heard: list[int] = []
        answers: list[str] = []
        listened = mac_keys._heard

        def heard_one(kind: int, code: int, modifiers: int) -> None:
            heard.append(kind)
            listened(kind, code, modifiers)

        setattr(mac_keys, "_heard", heard_one)  # noqa: B010 - before its first ask

        def asked(name: str) -> bool:
            said = mac_keys(name)
            if said:
                answers.append(name)
            return said

        self.window.keys = asked
        self.window.show()
        self.wait(0.5)
        self.window.toggle_settings()
        popover = self.window.popover
        self.until(lambda: popover is not None and popover.isVisible(), 2)
        opened = popover is not None and popover.isVisible()
        _ok, box = self.script(
            'tell application "System Events" to tell process "TextEdit" '
            "to get {position, size} of window 1"
        )
        try:
            x, y, w, h = (int(float(n)) for n in box.split(","))
        except ValueError:
            self.add(
                "click_elsewhere", UNKNOWN, f"TextEdit's window not found: {box[:200]}"
            )
            return
        # a point of TextEdit's window the popover doesn't cover: placed
        # beside its button, it can cover the window's lower right (515)
        frame = popover.frameGeometry() if popover is not None else None
        spots = [
            (x + w * a // 4, y + h * b // 4)
            for a, b in ((3, 3), (1, 3), (3, 1), (1, 1))
        ]
        target = next(
            (s for s in spots if frame is None or not frame.contains(*s)), spots[0]
        )
        inside = frame is not None and frame.contains(*target)
        before = QCursor.pos()
        # a real click (cliclick, from Homebrew): System Events' `click at`
        # moves no cursor and no mouse event reaches other apps' monitors
        # (438's run 2: the global monitor heard nothing)
        clicker = _cliclick()
        if clicker is None:
            self.add("click_elsewhere", UNKNOWN, "no cliclick on this machine")
            return
        heard.clear()
        clicked, said = self.run_quietly([clicker, f"c:{target[0]},{target[1]}"])
        self.until(lambda: popover is None or not popover.isVisible(), 2)
        closed = popover is None or not popover.isVisible()
        after = QCursor.pos()
        frame = popover.frameGeometry() if popover is not None else None
        facts = {
            "opened": opened,
            "target": target,
            "target_in_popover": inside,
            "popover": frame.getRect() if frame is not None else None,
            "cursor_before": (before.x(), before.y()),
            "cursor_after": (after.x(), after.y()),
            "monitor_heard_types": heard[-20:],
            "asked_and_true": answers[-20:],
            "listening": mac_keys.listening,
        }
        if not clicked:
            self.add(
                "click_elsewhere",
                UNKNOWN,
                f"cliclick couldn't click: {said[:200]}",
                **facts,
            )
        elif not opened or inside:
            self.add(
                "click_elsewhere",
                UNKNOWN,
                "the popover wasn't open, or was where the click went",
                **facts,
            )
        elif keys.LEFT_DOWN not in heard:
            self.add(
                "click_elsewhere",
                FAIL,
                "the global monitor missed the left mouse-down",
                **facts,
            )
        else:
            self.add(
                "click_elsewhere",
                PASS if closed else FAIL,
                "the click in TextEdit closed the popover"
                if closed
                else "the popover stayed open",
                **facts,
            )
        if popover is not None and popover.isVisible():
            popover.close()

    def resize_by_mouse(self) -> None:
        """The bottom-right corner dragged with the real mouse from 2 px
        inside: grown by the app's own resizing, and remembered."""
        clicker = _cliclick()
        if clicker is None:
            self.add("resize_by_mouse", UNKNOWN, "no cliclick on this machine")
            return
        self.full_screen(False)
        window = self.window
        window.set_locked(False)
        window.setGeometry(200, 200, 600, 160)
        window.show()
        self.on_top.put_on_top([int(window.winId())])
        self.wait(0.6)
        before = window.frameGeometry()
        x, y = before.x() + before.width() - 3, before.y() + before.height() - 3
        dragged, said = self.run_quietly(
            [clicker, "-w", "60", f"m:{x},{y}", f"dd:{x},{y}",
             f"dm:{x + 20},{y + 15}", f"dm:{x + 40},{y + 30}", f"du:{x + 40},{y + 30}"]
        )  # fmt: skip
        self.wait(0.8)
        after = window.frameGeometry()
        kept = window.choices.geometry
        grew = (
            after.width() - before.width() >= 20
            and after.height() - before.height() >= 15
        )
        remembered = kept is not None and (kept.width, kept.height) == (
            after.width(),
            after.height(),
        )
        facts = {
            "before": before.getRect(),
            "after": after.getRect(),
            "remembered": (kept.x, kept.y, kept.width, kept.height) if kept else None,
            "style_mask": self.window_facts().get("style_mask"),
        }
        if not dragged:
            self.add("resize_by_mouse", UNKNOWN, f"cliclick: {said[:200]}", **facts)
            return
        self.add(
            "resize_by_mouse",
            PASS if grew and remembered else FAIL,
            "grown by the app, and remembered"
            if grew and remembered
            else ("grown, but not by the app: not remembered" if grew else "not grown"),
            **facts,
        )

    def accessibility_settings(self) -> None:
        from polyglotic_desktop.platform.macos import text_input

        text_input.Permission().open_settings()
        opened = self.until(lambda: bool(_pid_of("System Settings")), 15)
        self.wait(2.0)
        _ok, pane = self.script(
            'tell application "System Settings" to get name of current pane'
        )
        self.script('tell application "System Settings" to quit')
        self.add(
            "accessibility_settings",
            PASS if opened else FAIL,
            "System Settings opened" if opened else "System Settings didn't open",
            pane=pane[:200],
        )

    def run(self) -> int:
        self.guarded("start", self.start)
        if not hasattr(self, "window"):
            return self.finish()
        self.guarded(
            "full_screen_qt_only",
            lambda: self.over_full_screen("full_screen_qt_only", False),
        )
        self.guarded("full_screen", lambda: self.over_full_screen("full_screen", True))
        self.guarded("shown_after_full_screen", self.shown_after_full_screen)
        self.guarded("locked", self.locked)
        self.guarded("sign", self.sign)
        self.guarded("popover_in_front", self.popover_in_front)
        self.guarded("click", self.click)
        self.guarded("typed", self.typed)
        self.guarded("hover_in_background", self.hover_in_background)
        self.guarded("key_combination", self.key_combination)
        self.guarded("key_alone", self.key_alone)
        self.guarded("escape_cancels", self.escape_cancels)
        self.guarded("click_elsewhere", self.click_elsewhere)
        self.guarded("resize_by_mouse", self.resize_by_mouse)
        self.guarded("accessibility_settings", self.accessibility_settings)
        return self.finish()

    def finish(self) -> int:
        try:
            if hasattr(self, "textedit") and self.textedit:
                self.ax.full_screen(self.textedit, False)
            if hasattr(self, "watch"):
                self.watch.stop()
            if hasattr(self, "heard"):
                self.facts["notifications"] = self.heard.names[-60:]
        except Exception as error:  # noqa: BLE001 - the results are written whatever
            print(f"tidying up: {error}", flush=True)
        self.out.parent.mkdir(parents=True, exist_ok=True)
        self.out.write_text(
            json.dumps(report(self.results, self.facts), indent=1, ensure_ascii=False),
            encoding="utf-8",
        )
        return exit_code(self.results)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("out", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    if args.dry_run:
        print("\n".join(plan()))
        return 0
    if sys.platform != "darwin":
        print("only on a Mac (GitHub's macOS job)")
        return 2
    return Run(args.out).run()


if __name__ == "__main__":
    sys.exit(main())
