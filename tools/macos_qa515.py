r"""515's look at the caption windows on GitHub's Mac, as a user meets them
(polyglotic-hq 515): the app from source with the Mac's own staying-on-top
(`MacOnTop`, `FrontWatch`) and key watch, signed in to the stand-in server
and captioning the app's FLEURS sample, as `tools.app_tour` runs it - then:

- hover: the real mouse (cliclick, Homebrew's: real mouse events through
  macOS's window server) moved over the caption window, with another app
  in front and with the app active: does the strip show?
- resize: each corner and edge dragged with the real mouse: the window's
  size before and after; the same drag through Qt alone (QTest), and with
  the window told to take every click (`setIgnoresMouseEvents:NO`).
- order: the settings popover, the language chip's, the lookup card, a
  strip tip and the copy tip opened from a caption window: where each is
  in macOS's window list (front to back) against its caption window, as
  opened, after the interface puts the windows on top again (what a
  caption's arrival does) and after captions arrive; macOS's
  `screencapture` of the place.

    uv run --no-sync python -m tools.macos_qa515 OUT [--dictionaries DIR] [--limit S]

Only on GitHub's Mac: it moves the mouse and opens TextEdit there.
"""

from __future__ import annotations

import argparse
import ctypes
import dataclasses
import json
import os
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path
from typing import Any

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QAbstractButton, QApplication, QWidget

from tools import app_tour as kit

START = QRect(360, 300, 640, 220)
"""Where the caption window is put before each try: room on every side."""
HANDLES = {
    "bottom_right": (1, 1),
    "bottom_left": (-1, 1),
    "top_right": (1, -1),
    "top_left": (-1, -1),
    "right": (1, 0),
    "left": (-1, 0),
    "bottom": (0, 1),
    "top": (0, -1),
}
FINDINGS: dict[str, Any] = {"resize": [], "order": [], "hover": [], "facts": {}}


# -- macOS --------------------------------------------------------------------------


def ns_window(widget: QWidget) -> int:
    from polyglotic_desktop.platform.macos import on_top

    return on_top.window_of(int(widget.winId()))


def ns_facts(widget: QWidget | None) -> dict[str, Any]:
    from polyglotic_desktop.platform.macos import objc

    if widget is None:
        return {}
    ns = ns_window(widget)
    if not ns:
        return {"ns": None}

    def number(selector: str) -> int:
        return int(objc.send(ns, selector, restype=ctypes.c_long))

    def flag(selector: str) -> bool:
        return bool(objc.send(ns, selector, restype=ctypes.c_bool))

    return {
        "class": objc.text(objc.send(ns, "className")),
        "number": number("windowNumber"),
        "level": number("level"),
        "style_mask": number("styleMask"),
        "visible": flag("isVisible"),
        "opaque": flag("isOpaque"),
        "ignores_mouse": flag("ignoresMouseEvents"),
        "alpha": float(objc.send(ns, "alphaValue", restype=ctypes.c_double)),
        "geometry": widget.frameGeometry().getRect(),
    }


def app_active() -> bool:
    from polyglotic_desktop.platform.macos import objc

    app = objc.send(objc.cls("NSApplication"), "sharedApplication")
    return bool(objc.send(app, "isActive", restype=ctypes.c_bool))


def activate() -> None:
    from polyglotic_desktop.platform.macos import objc

    app = objc.send(objc.cls("NSApplication"), "sharedApplication")
    objc.send(
        app,
        "activateIgnoringOtherApps:",
        True,
        restype=None,
        argtypes=[ctypes.c_bool],
    )


def take_every_click(widget: QWidget) -> None:
    from polyglotic_desktop.platform.macos import objc

    objc.send(
        ns_window(widget),
        "setIgnoresMouseEvents:",
        False,
        restype=None,
        argtypes=[ctypes.c_bool],
    )


def listed_order(widgets: dict[str, QWidget | None]) -> dict[str, Any]:
    """Each named widget's place in macOS's window list (0 the front), its
    level and number; and the app windows in front of it."""
    from polyglotic_desktop.platform.macos import window_list

    listed = window_list.on_screen()
    numbers = [w.number for w in listed]
    out: dict[str, Any] = {}
    for name, widget in widgets.items():
        if widget is None or not widget.isVisible():
            out[name] = None
            continue
        facts = ns_facts(widget)
        n = facts.get("number")
        out[name] = {
            "index": numbers.index(n) if n in numbers else None,
            "level": facts.get("level"),
            "number": n,
            "geometry": facts.get("geometry"),
        }
    return out


def in_front(order: dict[str, Any], top: str, under: str) -> bool | None:
    a, b = order.get(top), order.get(under)
    if not a or not b or a["index"] is None or b["index"] is None:
        return None
    return bool(a["index"] < b["index"])


def overlap(a: QWidget, b: QWidget) -> bool:
    return a.frameGeometry().intersects(b.frameGeometry())


def picture_of_screen(name: str, rect: QRect) -> None:
    """macOS's screencapture of `rect` (GitHub's Mac only: what's in front
    of what is the point)."""
    path = kit.OUT / f"{name}.png"
    r = rect.adjusted(-30, -30, 30, 30)
    subprocess.run(
        ["screencapture", "-x", "-R", f"{r.x()},{r.y()},{r.width()},{r.height()}",
         str(path)],
        check=False, timeout=20, capture_output=True,
    )  # fmt: skip
    kit.RESULTS["pictures"].append({"file": path.name, "what": name, "screen": True})


_CLICLICK: list[str] = []


def cliclick(*commands: str) -> subprocess.Popen[str]:
    if not _CLICLICK:
        from tools.macos_full_screen_checks import _cliclick

        found = _cliclick()
        _CLICLICK.append(found or "")
    return subprocess.Popen(
        [_CLICLICK[0], "-w", "60", *commands],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


def done(process: subprocess.Popen[str]) -> bool:
    return process.poll() is not None


# -- the steps ------------------------------------------------------------------------


def first_run() -> kit.Step:
    for _ in range(5):
        yield kit.wait(lambda: QApplication.activeModalWidget() or kit.ready(), 90,
                       "the first question or the main window")  # fmt: skip
        question = QApplication.activeModalWidget()
        if question is None:
            break
        name = type(question).__name__
        if name == "ConsentDialog" and getattr(question, "agree", None) is not None:
            question.agree.setChecked(True)  # type: ignore[attr-defined]
        if name in ("ConsentDialog", "LevelPicker"):
            question.accept()  # type: ignore[attr-defined]
        else:
            question.close()
        yield kit.pause(1.0)
    yield kit.wait(kit.ready, 60, "the main window")


def hover(state: str, captions: Any) -> kit.Step:
    g = captions.frameGeometry()
    moving = cliclick(
        f"m:{g.x() - 60},{g.y() - 60}", f"m:{g.center().x()},{g.center().y() + 30}"
    )
    yield kit.wait(lambda: done(moving), 10, "cliclick")
    yield kit.pause(0.8)
    facts = {
        "state": state,
        "app_active": app_active(),
        "hovered": bool(captions.hovered),
        "band_shown": bool(captions.band_shown),
        "cursor_shape": str(captions.cursor().shape()),
    }
    FINDINGS["hover"].append(facts)
    kit.check(f"{state}: the strip shows as the mouse comes over",
              captions.band_shown or captions.hovered, facts)  # fmt: skip


def resize(state: str, captions: Any, how: str) -> kit.Step:
    for name, (sx, sy) in HANDLES.items():
        captions.setGeometry(START)
        yield kit.pause(0.5)
        g = captions.frameGeometry()
        px = g.x() + (2 if sx < 0 else g.width() - 3 if sx > 0 else g.width() // 2)
        py = g.y() + (2 if sy < 0 else g.height() - 3 if sy > 0 else g.height() // 2)
        dx, dy = 40 * sx, 30 * sy
        local = QPoint(px - g.x(), py - g.y())
        image = captions.grab().toImage()
        ratio = image.devicePixelRatio() or 1.0
        alpha = image.pixelColor(int(local.x() * ratio), int(local.y() * ratio)).alpha()
        if how == "qt":
            QTest.mousePress(captions, Qt.MouseButton.LeftButton, pos=local)
            QTest.mouseMove(captions, local + QPoint(dx // 2, dy // 2))
            QTest.mouseMove(captions, local + QPoint(dx, dy))
            QTest.mouseRelease(
                captions, Qt.MouseButton.LeftButton, pos=local + QPoint(dx, dy)
            )
        else:
            dragging = cliclick(f"m:{px},{py}", f"dd:{px},{py}",
                                f"dm:{px + dx // 2},{py + dy // 2}",
                                f"dm:{px + dx},{py + dy}", f"du:{px + dx},{py + dy}")  # fmt: skip
            yield kit.wait(lambda d=dragging: done(d), 10, "cliclick")
        yield kit.pause(0.6)
        after = captions.frameGeometry()
        wide = after.width() - g.width()
        high = after.height() - g.height()
        ok = (wide >= 20 if sx else abs(wide) < 5) and (
            high >= 15 if sy else abs(high) < 5
        )
        facts = {
            "state": state, "how": how, "handle": name, "pressed": (px, py),
            "alpha_there": alpha, "before": g.getRect(), "after": after.getRect(),
            "app_active": app_active(),
        }  # fmt: skip
        FINDINGS["resize"].append({**facts, "ok": ok})
        kit.check(f"{state} {how}: {name} resizes", ok, facts)


def order_check(
    name: str, opened: QWidget | None, captions: Any, about: str
) -> kit.Step:
    """`opened` against its caption window: as opened, after keep_on_top, and
    after 3 s of captions."""
    interface = kit.STATE["interface"]
    if opened is None or not opened.isVisible():
        kit.check(f"{name}: opened", False, about)
        return
    rows = []
    yield kit.pause(0.6)
    rows.append(("as opened", listed_order({"it": opened, "captions": captions})))
    picture_of_screen(
        f"{name}-as-opened", captions.frameGeometry().united(opened.frameGeometry())
    )
    interface.windows.keep_on_top()
    yield kit.pause(0.6)
    rows.append(
        ("after keep_on_top", listed_order({"it": opened, "captions": captions}))
    )
    yield kit.pause(3.0)
    rows.append(("after 3 s", listed_order({"it": opened, "captions": captions})))
    picture_of_screen(
        f"{name}-after", captions.frameGeometry().united(opened.frameGeometry())
    )
    fronts = [in_front(order, "it", "captions") for _when, order in rows]
    facts = {"about": about, "overlap": overlap(opened, captions), "rows": rows,
             "it": ns_facts(opened), "captions": ns_facts(captions)}  # fmt: skip
    FINDINGS["order"].append({"name": name, "fronts": fronts, **facts})
    kit.check(f"{name}: in front of its caption window throughout",
              all(f is True for f in fronts), facts)  # fmt: skip


def popovers(state: str, captions: Any) -> kit.Step:
    captions.setGeometry(START)
    yield kit.pause(0.5)
    # as a user: over the window, then a click on the settings button
    g = captions.frameGeometry()
    moving = cliclick(f"m:{g.center().x()},{g.center().y() + 30}")
    yield kit.wait(lambda: done(moving), 10, "cliclick")
    yield kit.pause(0.8)
    button = captions.buttons.get("settings")
    how = "code"
    if button is not None and button.isVisible():
        at = button.mapToGlobal(button.rect().center())
        clicking = cliclick(f"c:{at.x()},{at.y()}")
        yield kit.wait(lambda: done(clicking), 10, "cliclick")
        yield kit.wait(lambda: captions.popover is not None and captions.popover.isVisible(),
                       3, "")  # fmt: skip
        how = "a real click on the settings button"
    if captions.popover is None or not captions.popover.isVisible():
        captions.toggle_settings()
        how = "toggle_settings()"
        yield kit.pause(0.5)
    yield from order_check(f"{state}-settings-popover", captions.popover, captions, how)
    kit.extra(
        captions.popover, f"{state}-settings-popover-grab", "the settings popover"
    )
    captions.close_settings()
    yield kit.pause(0.5)

    if hasattr(captions, "toggle_languages"):
        captions.toggle_languages()
        yield kit.pause(0.5)
        yield from order_check(f"{state}-language-popover", captions.languages, captions,
                               "toggle_languages()")  # fmt: skip
        captions.close_settings()
        yield kit.pause(0.5)

    # a strip tip: the mouse resting on a strip button
    if button is not None:
        moving = cliclick(f"m:{g.center().x()},{g.center().y() + 30}")
        yield kit.wait(lambda: done(moving), 10, "cliclick")
        yield kit.pause(0.5)
        at = button.mapToGlobal(button.rect().center())
        moving = cliclick(f"m:{at.x()},{at.y()}")
        yield kit.wait(lambda: done(moving), 10, "cliclick")
        yield kit.pause(1.6)
        tip = next((w for w in QApplication.topLevelWidgets()
                    if w.objectName() == "strip_tip" and w.isVisible()), None)  # fmt: skip
        if tip is not None:
            yield from order_check(
                f"{state}-strip-tip", tip, captions, "resting on settings"
            )
        else:
            kit.check(f"{state}-strip-tip: shown on resting", False, "no strip tip")

    # the lookup card: a real click on a word
    spot = None
    try:
        spot = kit.a_word(captions)
    except Exception:  # noqa: BLE001
        spot = None
    card = interface_card()
    if spot is not None:
        at = captions.mapToGlobal(spot.toPoint())
        clicking = cliclick(f"c:{at.x()},{at.y()}")
        yield kit.wait(lambda: done(clicking), 10, "cliclick")
        yield kit.wait(lambda: interface_card() is not None and interface_card().isVisible(),
                       5, "")  # fmt: skip
        card = interface_card()
        yield from order_check(
            f"{state}-lookup-card", card, captions, "a real click on a word"
        )
        if card is not None:
            card.hide()
        yield kit.pause(0.4)
        # the copy tip: a right-click on a caption
        clicking = cliclick(f"rc:{at.x()},{at.y()}")
        yield kit.wait(lambda: done(clicking), 10, "cliclick")
        yield kit.pause(0.4)
        tip = next((w for w in QApplication.topLevelWidgets()
                    if type(w).__name__ == "QTipLabel" and w.isVisible()), None)  # fmt: skip
        if tip is not None:
            yield from order_check(f"{state}-copy-tip", tip, captions, "a right-click")
        else:
            FINDINGS["order"].append(
                {"name": f"{state}-copy-tip", "said": "no tip seen"}
            )
    else:
        kit.check(f"{state}: a word to click", False, "none found")


def interface_card() -> Any:
    return kit.STATE["interface"].windows.card


def textedit_in_front() -> kit.Step:
    folder = Path(tempfile.mkdtemp(prefix="qa515-"))
    document = folder / "qa515.txt"
    document.write_text("", encoding="utf-8")
    subprocess.Popen(["open", "-a", "TextEdit", str(document)])
    from polyglotic_desktop.platform.macos import window_list

    def textedit_front() -> bool:
        found = subprocess.run(["pgrep", "-x", "TextEdit"], check=False,
                               capture_output=True, text=True).stdout.split()  # fmt: skip
        return bool(found) and window_list.front_pid() == int(found[0])

    yield kit.wait(textedit_front, 20, "TextEdit in front")
    yield kit.pause(1.0)


def qa() -> kit.Step:
    yield from first_run()
    window = kit.hub().window
    window.go_to("home")
    if kit.caption_window() is None:
        button = window.findChild(QAbstractButton, f"picker.add.{kit.PLAYER}")
        if button is not None:
            button.click()
    yield kit.wait(lambda: kit.caption_window() is not None
                   and kit.caption_window().isVisible(), 30, "the caption window")  # fmt: skip
    yield kit.wait(lambda: len(kit.finished_lines()) >= 1, 90, "a finished caption")
    captions = kit.caption_window()
    captions.setGeometry(START)
    yield kit.pause(1.0)
    FINDINGS["facts"]["caption_window_at_start"] = ns_facts(captions)
    FINDINGS["facts"]["main_window"] = ns_facts(window)
    window.hide()  # as a learner does, watching something else
    yield from textedit_in_front()
    FINDINGS["facts"]["app_active_with_textedit_in_front"] = app_active()
    picture_of_screen("start", captions.frameGeometry())

    for state in ("inactive", "active"):
        if state == "active":
            activate()
            yield kit.pause(1.0)
        yield from guarded(f"{state} hover", hover(state, captions))
        yield from guarded(f"{state} resize", resize(state, captions, "mouse"))
        yield from guarded(f"{state} popovers", popovers(state, captions))
        if state == "inactive":
            yield from textedit_in_front()
    yield from guarded("qt resize", resize("active", captions, "qt"))
    # the same real drags once the window takes every click
    take_every_click(captions)
    FINDINGS["facts"]["after_take_every_click"] = ns_facts(captions)
    yield from textedit_in_front()
    yield from guarded(
        "every-click resize", resize("inactive-every-click", captions, "mouse")
    )
    # locked and unlocked once (Qt sets ignoresMouseEvents NO then)
    captions.set_locked(True)
    yield kit.pause(0.6)
    captions.set_locked(False)
    yield kit.pause(0.6)
    FINDINGS["facts"]["after_lock_unlock"] = ns_facts(captions)


def guarded(what: str, steps: kit.Step) -> kit.Step:
    try:
        yield from steps
    except Exception:  # noqa: BLE001
        kit.check(f"{what} ran", False, traceback.format_exc()[-1500:])


class Driver(kit.Driver):
    def __init__(self, limit: float) -> None:
        super().__init__(limit)
        self.steps = qa()

    def end(self) -> None:
        (kit.OUT / "findings.json").write_text(
            json.dumps(FINDINGS, indent=1, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
        super().end()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m tools.macos_qa515")
    parser.add_argument("out", type=Path)
    parser.add_argument("--dictionaries", default="build/dictionaries")
    parser.add_argument("--limit", type=float, default=300.0, help="seconds")
    args = parser.parse_args(argv)
    if sys.platform != "darwin":
        print("only on GitHub's Mac")
        return 2
    kit.OUT = args.out
    kit.OUT.mkdir(parents=True, exist_ok=True)
    data = kit.OUT / "data"
    kit.seed_settings(data)
    from tests import fake_server

    import polyglotic_desktop
    from polyglotic_desktop import main as app
    from polyglotic_desktop.platform.replay import join, read_clip
    from polyglotic_desktop.platform.sample import sample_file

    FINDINGS["facts"]["source"] = str(Path(polyglotic_desktop.__file__).parent)
    sample = sample_file("zh")
    assert sample is not None
    audio = join([read_clip(sample)], gap=1.0)
    fake_server.caption_for = kit.caption_for
    server = fake_server.FakeServer()
    driver = Driver(args.limit)

    class Driven(QApplication):
        def __init__(self, qt_argv: list[str]) -> None:
            super().__init__(qt_argv)
            driver.start()

    real = app.os_adapters
    swapped = kit.adapters(real, audio)

    def os_adapters(system: str = sys.platform) -> Any:
        found = swapped(system)
        own = real(system)
        return dataclasses.replace(
            found,
            on_top=own.on_top,
            foreground_watch=own.foreground_watch,
            keys=own.keys,
        )

    real_interface = app.new_interface

    def new_interface(*a: Any, **k: Any) -> Any:
        kit.STATE["interface"] = real_interface(*a, **k)
        return kit.STATE["interface"]

    class Recorded(app.DesktopApp):  # type: ignore[misc, valid-type]
        def __init__(self, *a: Any, **k: Any) -> None:
            super().__init__(*a, **k)
            kit.STATE["desktop"] = self

    app.os_adapters = os_adapters
    app.QApplication = Driven  # type: ignore[misc, assignment]
    app.new_interface = new_interface
    app.DesktopApp = Recorded  # type: ignore[misc]
    try:
        app.main(["--server", server.url, "--data", str(data),
                  "--dictionaries", str(args.dictionaries)])  # fmt: skip
    except SystemExit:
        pass
    except Exception:  # noqa: BLE001
        kit.check("the app started", False, traceback.format_exc()[-1500:])
    kit.write_results()
    (kit.OUT / "findings.json").write_text(
        json.dumps(FINDINGS, indent=1, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    server.stop()
    failed = [c["check"] for c in kit.RESULTS["checks"] if not c["ok"]]
    print(
        f"qa515: {len(kit.RESULTS['checks']) - len(failed)} passed, {len(failed)} failed"
    )
    for c in kit.RESULTS["checks"]:
        print(("pass " if c["ok"] else "FAIL ") + c["check"], flush=True)
    return 0


if __name__ == "__main__":
    code = main()
    sys.stdout.flush()
    os._exit(code)
