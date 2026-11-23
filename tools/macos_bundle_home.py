"""Follow the pointer from Home to the menu bar in the built app on a hosted Mac."""

from __future__ import annotations

import importlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from polyglotic_desktop.adapters.sqlite_outbox import open_outbox
from polyglotic_desktop.core.shared.papers import TESTER_AGREEMENT_VERSION
from polyglotic_desktop.ports.consent import Agreement, ConsentChoice
from tools.macos_full_screen_checks import Ax, server_entry
from tools.macos_ui_lab import hosted_mac


def journeys(pid: int, out: Path) -> bool:
    cocoa = importlib.import_module("AppKit")
    q = importlib.import_module("Quartz")
    ax = Ax()
    finder = cocoa.NSRunningApplication.runningApplicationsWithBundleIdentifier_(
        "com.apple.finder"
    )[0]

    def home_info(title: str = "Polyglotic") -> dict[str, Any]:
        return next(
            (
                w
                for w in q.CGWindowListCopyWindowInfo(
                    q.kCGWindowListOptionOnScreenOnly, 0
                )
                if w.get("kCGWindowOwnerPID") == pid
                and w.get("kCGWindowName") == title
                and (title != "Polyglotic" or w.get("kCGWindowLayer") == 0)
            ),
            {},
        )

    start = time.monotonic()
    while time.monotonic() - start < 45 and not home_info():
        time.sleep(0.25)
    info = home_info()
    if not info:
        subprocess.run(
            ["screencapture", "-x", str(out / "startup.png")], check=True, timeout=10
        )
        return False
    app = cocoa.NSRunningApplication.runningApplicationWithProcessIdentifier_(pid)
    if app is None:
        raise RuntimeError(
            "WindowServer saw Home but NSWorkspace did not resolve its PID"
        )
    number = info["kCGWindowNumber"]

    def pump(seconds: float) -> None:
        cocoa.NSRunLoop.currentRunLoop().runUntilDate_(
            cocoa.NSDate.dateWithTimeIntervalSinceNow_(seconds)
        )

    def click(x: float, y: float) -> None:
        for kind in (q.kCGEventLeftMouseDown, q.kCGEventLeftMouseUp):
            q.CGEventPost(
                q.kCGHIDEventTap, q.CGEventCreateMouseEvent(None, kind, (x, y), 0)
            )
            pump(0.1)

    # Home exists before the returning signed-out user is offered a code. Wait
    # for the actual modal rather than sending an early Escape to another app.
    app.activateWithOptions_(cocoa.NSApplicationActivateIgnoringOtherApps)
    for _ in range(35):
        pump(0.2)
        if home_info("Sign in"):
            break
    results = []
    for case in ("focused", "unfocused", "full-screen"):
        app.activateWithOptions_(cocoa.NSApplicationActivateIgnoringOtherApps)
        for _ in range(30):
            pump(0.1)
            active = cocoa.NSWorkspace.sharedWorkspace().frontmostApplication()
            if active and active.processIdentifier() == pid and ax.window(pid):
                break
        for _ in range(3):
            dialog = home_info("Sign in")
            if not dialog:
                break
            bounds = dialog["kCGWindowBounds"]
            # The sign-in is a floating Qt dialog above Home. Use the Cancel
            # button, on the right beside Sign in, to return its rejected result.
            click(
                bounds["X"] + bounds["Width"] - 156, bounds["Y"] + bounds["Height"] - 30
            )
            pump(0.4)
        bounds = home_info()["kCGWindowBounds"]
        click(bounds["X"] + bounds["Width"] / 2, bounds["Y"] + 13)
        if case == "unfocused":
            finder.activateWithOptions_(cocoa.NSApplicationActivateIgnoringOtherApps)
        elif case == "full-screen":
            for _ in range(5):
                ax.full_screen(pid, True)
                pump(1)
                if ax.is_full_screen(pid):
                    break
        # NSRunningApplication caches state until the caller pumps its main
        # loop. This observer runs outside the Qt application under test.
        pump(2)
        foreground = cocoa.NSWorkspace.sharedWorkspace().frontmostApplication()
        front_pid = foreground.processIdentifier() if foreground else None
        frame = dict(home_info().get("kCGWindowBounds", {}))
        prepared = (
            bool(frame)
            and not home_info("Sign in")
            and (
                front_pid == pid
                if case != "unfocused"
                else front_pid == finder.processIdentifier()
            )
            and ax.is_full_screen(pid) == (case == "full-screen")
        )
        samples = []
        pictures = []
        if frame:
            x = frame["X"] + frame["Width"] / 2
            y = frame["Y"] + frame["Height"] / 2
            for n in range(13):
                q.CGEventPost(
                    q.kCGHIDEventTap,
                    q.CGEventCreateMouseEvent(
                        None, q.kCGEventMouseMoved, (x, round(y * (1 - n / 12))), 0
                    ),
                )
                time.sleep(0.07)
                samples.append(server_entry(number).get("on_screen", False))
            time.sleep(1)
            for suffix, options in (
                ("window", ["-l", str(number)]),
                ("desktop", ["-m"]),
            ):
                path = out / f"{case}-{suffix}.jpg"
                done = subprocess.run(
                    ["screencapture", "-x", "-t", "jpg", *options, str(path)],
                    timeout=10,
                    check=False,
                )
                pictures.append(
                    done.returncode == 0 and path.is_file() and path.stat().st_size > 0
                )
        after = dict(home_info().get("kCGWindowBounds", {}))
        results.append(
            {
                "case": case,
                "before": frame,
                "after": after,
                "prepared": prepared,
                "sign_in_obstructs": bool(home_info("Sign in")),
                "foreground": str(foreground.bundleIdentifier())
                if foreground
                else None,
                "app_is_active": bool(app.isActive()),
                "native_fullscreen": ax.is_full_screen(pid),
                "on_screen": samples,
                "ok": prepared
                and len(samples) == 13
                and all(samples)
                and after == frame
                and all(pictures),
            }
        )
        (out / "home.json").write_text(json.dumps(results, indent=1), encoding="utf-8")
    return all(r["ok"] for r in results)


def main(bundle: Path, out: Path) -> int:
    if not hosted_mac():
        raise SystemExit("Requires a GitHub-hosted Mac")
    from tests.fake_server import FakeServer

    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="packed-home-") as scratch:
        data = Path(scratch)
        (data / "settings.json").write_text(
            '{"learning":"zh","apps":[],"whole_system":false}', encoding="utf-8"
        )
        (data / "feed").mkdir()
        db = open_outbox(data / "outbox.sqlite")
        now = datetime.now(UTC)
        db.save_consent(
            ConsentChoice(
                str(uuid4()),
                now,
                False,
                False,
                False,
                Agreement(TESTER_AGREEMENT_VERSION, now),
            )
        )
        db.close()
        server = FakeServer(http_replies={})
        try:
            proc = subprocess.Popen(
                [
                    str(bundle / "Contents/MacOS/Polyglotic"),
                    "--server",
                    server.url,
                    "--data",
                    str(data),
                    *(
                        []
                        if bundle.name == "Polyglotic Preview.app"
                        else ["--updates", str(data / "feed")]
                    ),
                ],
                env={**os.environ, "QT_QPA_PLATFORM": "cocoa"},
            )
            try:
                return int(not journeys(proc.pid, out))
            finally:
                marker = data / "crashed.json"
                if marker.exists():
                    error = json.loads(marker.read_text(encoding="utf-8"))
                    (out / "start-failure.json").write_text(
                        json.dumps(
                            {k: error.get(k) for k in ("what", "where", "at_start")}
                        ),
                        encoding="utf-8",
                    )
                log = data / "logs" / "polyglotic.log"
                if log.is_file():
                    contents = log.read_text(encoding="utf-8", errors="replace")
                    (out / "staging.json").write_text(
                        json.dumps(
                            {
                                "staging_id_write_warnings": contents.count(
                                    "Couldn\u0027t write out staging userId"
                                )
                            }
                        ),
                        encoding="utf-8",
                    )
                    frames = re.findall(
                        r'File "([^"]+)", line (\d+), in (\w+)',
                        contents,
                    )
                    (out / "stack.json").write_text(
                        json.dumps(
                            [(Path(f).name, line, fn) for f, line, fn in frames]
                        ),
                        encoding="utf-8",
                    )
                proc.terminate()
                try:
                    proc.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
        finally:
            server.stop()


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1]), Path(sys.argv[2])))
