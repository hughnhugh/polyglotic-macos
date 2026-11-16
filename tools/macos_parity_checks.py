"""The caption windows over a full-screen app and dictation's typing, proven
on GitHub's Mac (polyglotic-hq 429): the macOS job's `parity` part. Each
check prints a pass, fail or unknown line and goes in a JSON file; the job
fails only on a fail - unknown is what the machine didn't let us see.

    uv run --no-sync python -m tools.macos_parity_checks OUT.json
    uv run --no-sync python -m tools.macos_parity_checks OUT.json --dry-run  # any OS: the plan

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
- sign: a panel with the dictation sign's flags shown over the
  full-screen app, which the interface never hands over: set by the
  watch's call too, above TextEdit.
- click: unlocked, a click on it (System Events' `click at`): TextEdit
  stays in front and full-screen.
- typed: dictation's `type_text` types "héllo 你好 😀" into TextEdit, read
  back through Accessibility; `keyboard_window` is TextEdit's window.
- key_combination: dictation's key Control+Command+D registered through
  Carbon; System Events presses it: down, then up, and TextEdit gets no
  "d"; whether the same combination is refused a second time (a fact).
- key_alone: Left Command held alone (System Events' `key down command`):
  down, then up, read from the modifiers' state.

Never the user's PC: this runs only on GitHub's macOS machine. It types
and presses keys into TextEdit there, through the app's own dictation
file and System Events.
"""

from __future__ import annotations

import argparse
import ctypes
import ctypes.util
import json
import platform
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

    def script(self, *lines: str) -> tuple[bool, str]:
        """osascript, with Qt's events going (Carbon's come through them)."""
        args = ["osascript"]
        for line in lines:
            args += ["-e", line]
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
        """A panel the interface doesn't hand over (the dictation sign's
        flags), shown over the full-screen app: the watch hears it and
        `put_on_top` sets it too."""
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QWidget

        from polyglotic_desktop.platform.macos import objc, on_top, window_list

        self.full_screen(True)
        sign = QWidget(
            None,
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowDoesNotAcceptFocus
            | Qt.WindowType.WindowTransparentForInput,
        )
        sign.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        sign.setGeometry(200, 300, 240, 60)
        sign.show()
        ns = on_top.window_of(int(sign.winId()))

        def level() -> int:
            return int(objc.send(ns, "level", restype=ctypes.c_long))

        self.until(lambda: level() == on_top.LEVEL, 3)
        number = int(objc.send(ns, "windowNumber", restype=ctypes.c_long))
        shown, is_above = above(window_list.on_screen(), number, self.textedit)
        ok = level() == on_top.LEVEL and shown and is_above
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
        self.guarded("click", self.click)
        self.guarded("typed", self.typed)
        self.guarded("key_combination", self.key_combination)
        self.guarded("key_alone", self.key_alone)
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
