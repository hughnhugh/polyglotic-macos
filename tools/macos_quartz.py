"""Real pointer input and paired evidence on an ephemeral GitHub-hosted Mac."""

from __future__ import annotations

import hashlib
import importlib
import json
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

from PySide6.QtCore import QPoint, QRect
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication, QWidget

from tools import app_tour as kit
from tools.macos_ui_lab import hosted_mac

# Logical screen points on the primary display. The outset allows a native
# window frame to hear the mouse. Caption windows own the inner hit area.
X_DRAG = 120
Y_DRAG = 32
TOLERANCE = 2
INSIDE = 2
FRAME_INSET = 1
INPUT_INTERVAL = 0.06  # seconds between intermediate Quartz events
SETTLE = 0.45  # seconds after mouse-up for Qt and the window server
SIDES = (
    "right",
    "left",
    "top",
    "bottom",
    "top-left",
    "top-right",
    "bottom-left",
    "bottom-right",
    "move",
)


def frame_values(frame: QRect) -> tuple[int, int, int, int]:
    return frame.x(), frame.y(), frame.width(), frame.height()


def motion(
    frame: QRect, side: str, native: bool, inset: int | None = None
) -> tuple[QPoint, QPoint, QRect]:
    """Mouse origin, requested translation, and independent frame expectation."""
    x, y, width, height = frame_values(frame)
    if inset is None:
        inset = FRAME_INSET if native else INSIDE
    if side == "move":
        start = QPoint(x + width // 3, y + (12 if native else height - 18))
        return start, QPoint(35, 20), frame.translated(35, 20)
    horizontal = int("right" in side) - int("left" in side)
    vertical = int("bottom" in side) - int("top" in side)
    # One third keeps the joined window's centre divider out of this test.
    sx = x + (
        inset if horizontal < 0 else width - 1 - inset if horizontal else width // 3
    )
    sy = y + (
        inset if vertical < 0 else height - 1 - inset if vertical else height // 2
    )
    dx, dy = horizontal * X_DRAG, vertical * Y_DRAG
    expected = frame.adjusted(min(0, dx), min(0, dy), max(0, dx), max(0, dy))
    return QPoint(sx, sy), QPoint(dx, dy), expected


def native_cursor() -> dict[str, Any]:
    """Read the visible WindowServer image as well as the app's current cursor."""
    cocoa = importlib.import_module("AppKit")

    def signature(cursor: Any) -> str | None:
        if cursor is None:
            return None
        rep = cocoa.NSBitmapImageRep.imageRepWithData_(
            cursor.image().TIFFRepresentation()
        )
        png = rep.representationUsingType_properties_(
            cocoa.NSBitmapImageFileTypePNG, {}
        )
        image = QImage.fromData(bytes(png)).convertToFormat(
            QImage.Format.Format_RGBA8888
        )
        return hashlib.sha256(bytes(image.constBits())).hexdigest()[:16]

    return {
        "system": signature(cocoa.NSCursor.currentSystemCursor()),
        "app": signature(cocoa.NSCursor.currentCursor()),
        "arrow": signature(cocoa.NSCursor.arrowCursor()),
        "active": bool(cocoa.NSRunningApplication.currentApplication().isActive()),
    }


class Pointer:
    def __init__(self) -> None:
        if not hosted_mac():
            raise RuntimeError("Quartz QA requires a GitHub-hosted Mac")
        self.q = importlib.import_module("Quartz")
        self.error: Exception | None = None

    def post(self, kind: int, at: QPoint, *, right: bool = False) -> None:
        q = self.q
        event = q.CGEventCreateMouseEvent(
            None,
            kind,
            (at.x(), at.y()),
            q.kCGMouseButtonRight if right else q.kCGMouseButtonLeft,
        )
        q.CGEventPost(q.kCGHIDEventTap, event)

    def drag(self, start: QPoint, delta: QPoint) -> kit.Step:
        # Cocoa tracks native drags in a nested event loop. Another thread
        # delivers mouse-up even while the Qt application's timer is blocked.
        def send() -> None:
            q = self.q
            self.error = None
            try:
                self.post(q.kCGEventMouseMoved, start)
                time.sleep(INPUT_INTERVAL)
                self.post(q.kCGEventLeftMouseDown, start)
                for n in range(1, 7):
                    time.sleep(INPUT_INTERVAL)
                    at = start + QPoint(
                        round(delta.x() * n / 6), round(delta.y() * n / 6)
                    )
                    self.post(q.kCGEventLeftMouseDragged, at)
            except Exception as error:  # noqa: BLE001 - transfer the input thread failure
                self.error = error
            finally:
                self.post(q.kCGEventLeftMouseUp, start + delta)

        thread = threading.Thread(target=send, daemon=True)
        thread.start()
        yield kit.wait(lambda: not thread.is_alive(), 5, "Quartz drag finished")
        if self.error:
            raise self.error
        yield kit.pause(SETTLE)

    def click(self, point: QPoint, *, right: bool = False) -> kit.Step:
        q = self.q
        self.post(q.kCGEventMouseMoved, point)
        yield kit.pause(INPUT_INTERVAL)
        self.post(
            q.kCGEventRightMouseDown if right else q.kCGEventLeftMouseDown,
            point,
            right=right,
        )
        self.post(
            q.kCGEventRightMouseUp if right else q.kCGEventLeftMouseUp,
            point,
            right=right,
        )
        yield kit.pause(SETTLE)

    def scroll(self, at: QPoint) -> kit.Step:
        q = self.q
        self.post(q.kCGEventMouseMoved, at)
        yield kit.pause(INPUT_INTERVAL)
        event = q.CGEventCreateScrollWheelEvent(None, q.kCGScrollEventUnitLine, 1, -8)
        q.CGEventSetLocation(event, (at.x(), at.y()))
        q.CGEventPost(q.kCGHIDEventTap, event)
        yield kit.pause(SETTLE)


class Evidence:
    def __init__(self, out: Path) -> None:
        if not hosted_mac():
            raise RuntimeError("Screenshots require a GitHub-hosted Mac")
        self.out = out
        self.out.mkdir(parents=True, exist_ok=True)
        self.steps: list[dict[str, Any]] = []

    def record(
        self,
        name: str,
        widget: QWidget,
        before: QRect,
        expected: str,
        ok: bool,
        **facts: Any,
    ) -> None:
        after = widget.frameGeometry()
        grab = self.out / f"{name}-app.png"
        screen = self.out / f"{name}-desktop.jpg"
        app_ok = widget.isVisible() and widget.grab().save(str(grab))
        shot = subprocess.run(
            ["/usr/sbin/screencapture", "-x", "-C", "-m", "-t", "jpg", str(screen)],
            capture_output=True,
            timeout=10,
            check=False,
        )
        screen_ok = (
            shot.returncode == 0 and screen.is_file() and screen.stat().st_size > 0
        )
        row = {
            "step": name,
            "before": before.getRect(),
            "after": after.getRect(),
            "expected": expected,
            "result": "pass" if ok and app_ok and screen_ok else "fail",
            "app": grab.name if app_ok else None,
            "desktop": screen.name if screen_ok else None,
            "facts": facts,
        }
        self.steps.append(row)
        (self.out / "steps.json").write_text(
            json.dumps(self.steps, indent=2), encoding="utf-8"
        )
        kit.check(
            name,
            row["result"] == "pass",
            f"{expected}; measured {after.getRect()}, {facts}",
        )

    def inactive_cursors(self, pointer: Pointer, name: str, window: Any) -> kit.Step:
        from polyglotic_desktop.ui_next.views.placement import Edge
        from tools.macos_settings_sweep import activate

        cocoa = importlib.import_module("AppKit")
        finder = cocoa.NSRunningApplication.runningApplicationsWithBundleIdentifier_(
            "com.apple.finder"
        )[0]
        finder.activateWithOptions_(cocoa.NSApplicationActivateIgnoringOtherApps)
        yield kit.pause(SETTLE)
        before = window.frameGeometry()
        for side in SIDES[:-1]:
            at, _, _ = motion(before, side, False, inset=6)
            pointer.post(pointer.q.kCGEventMouseMoved, centre(window))
            yield kit.pause(0.15)
            pointer.post(pointer.q.kCGEventMouseMoved, at)
            yield kit.pause(SETTLE)
            hint = next(
                (
                    h
                    for h in window.findChildren(QWidget, "caption.resize_hint")
                    if h.isVisible()
                ),
                None,
            )
            direction = hint.edge if hint else Edge.NONE
            expected_edge = Edge.NONE
            for component in side.split("-"):
                expected_edge |= Edge[component.upper()]
            expected = (
                "SizeFDiagCursor"
                if side in ("top-left", "bottom-right")
                else "SizeBDiagCursor"
                if "-" in side
                else "SizeVerCursor"
                if side in ("top", "bottom")
                else "SizeHorCursor"
            )
            self.record(
                f"{name}-inactive-{side}",
                window,
                before,
                f"visible {expected} affordance with Finder still active",
                direction == expected_edge and finder.isActive(),
                visible_cue=direction.name,
                native=native_cursor(),
            )
        pointer.post(pointer.q.kCGEventMouseMoved, centre(window))
        yield kit.pause(SETTLE)
        self.record(
            name + "-inactive-centre",
            window,
            before,
            "no resize cue off the edge",
            not any(
                h.isVisible()
                for h in window.findChildren(QWidget, "caption.resize_hint")
            ),
        )
        activate()
        yield kit.pause(SETTLE)

    def resize(self, pointer: Pointer, name: str, window: Any) -> kit.Step:
        native = name in {"main", "transcript"}
        area = window.screen().availableGeometry()
        # Leave room around every tested edge, including the macOS menu bar.
        width = max(window.minimumWidth(), 550)
        height = max(window.minimumHeight(), 168)
        for side in SIDES:
            # Place the full window on screen. Leave room on the side being
            # pulled. The desktop boundary can limit a wide joined window.
            x = min(X_DRAG + 4 if "left" in side else 4, area.width() - width)
            window.setGeometry(area.x() + max(0, x), area.y() + 78, width, height)
            yield kit.pause(SETTLE)
            before = window.frameGeometry()
            start, delta, target = motion(before, side, native)
            if not native and side != "move":
                target = target.intersected(area)
            if name in {"caption", "joined", "main"} and side != "move":
                # Probe inside the client, beyond Cocoa's narrow outer frame.
                inside, _, _ = motion(window.geometry(), side, False, inset=6)
                pointer.post(pointer.q.kCGEventMouseMoved, centre(window))
                yield kit.pause(0.12)
                pointer.post(pointer.q.kCGEventMouseMoved, inside)
                yield kit.pause(SETTLE)
                widget = QApplication.widgetAt(inside)
                observed = widget.cursor().shape().name if widget else ""
                expected_cursor = {
                    "top": "SizeVerCursor",
                    "bottom": "SizeVerCursor",
                    "right": "SizeHorCursor",
                    "left": "SizeHorCursor",
                    "top-left": "SizeFDiagCursor",
                    "bottom-right": "SizeFDiagCursor",
                    "top-right": "SizeBDiagCursor",
                    "bottom-left": "SizeBDiagCursor",
                }[side]
                os_cursor = native_cursor()
                self.record(
                    f"{name}-cursor-{side}",
                    window,
                    before,
                    f"{expected_cursor} six points inside the client; visible pointer differs from arrow",
                    observed == expected_cursor
                    and os_cursor["system"] is not None
                    and os_cursor["system"] != os_cursor["arrow"]
                    and (name == "main" or os_cursor["system"] == os_cursor["app"]),
                    point=inside.toTuple(),
                    observed=observed,
                    receiver=type(widget).__name__,
                    native=os_cursor,
                )
                start = inside
            yield from pointer.drag(start, delta)
            after = window.frameGeometry()
            wanted, actual = frame_values(target), frame_values(after)
            ok = all(
                abs(a - b) <= TOLERANCE for a, b in zip(wanted, actual, strict=True)
            )
            saved = None
            if not native:
                where = window.choices.geometry
                saved = (where.x, where.y, where.width, where.height) if where else None
                ok = ok and actual == saved
            self.record(
                f"{name}-{side}",
                window,
                before,
                f"frame {wanted} within {TOLERANCE} points",
                ok,
                saved=saved,
                start=start.toTuple(),
                delta=delta.toTuple(),
                minimum=window.minimumSize().toTuple(),
                available=area.getRect(),
            )
        if name == "main":
            window.setGeometry(area.left() + 8, area.top() + 52, 825, 555)
            yield kit.pause(SETTLE)
            before = window.frameGeometry()
            start, _, _ = motion(window.geometry(), "bottom-right", False, inset=6)
            yield from pointer.drag(start, QPoint(-420, -280))
            self.record(
                "home-smallest",
                window,
                before,
                "drag to 560 by 360 content points; sidebar and Home are reachable",
                window.size().toTuple() == (560, 360),
                client=window.size().toTuple(),
                minimum=window.minimumSize().toTuple(),
                sidebar=window.sidebar.width(),
            )
        if name in {"caption", "joined", "main"}:
            # Begin at the wide size a learner actually wants to reduce.
            window.setGeometry(area.left(), area.top() + 78, area.width(), height)
            yield kit.pause(SETTLE)
            before = window.frameGeometry()
            point, _, _ = motion(before, "right", native)
            yield from pointer.drag(point, QPoint(-X_DRAG, 0))
            target = before.adjusted(0, 0, -X_DRAG, 0)
            actual = window.frameGeometry()
            self.record(
                f"{name}-shrink",
                window,
                before,
                f"right edge moves inward {X_DRAG} +/- {TOLERANCE} points",
                all(
                    abs(a - b) <= TOLERANCE
                    for a, b in zip(actual.getRect(), target.getRect(), strict=True)
                ),
                minimum=window.minimumWidth(),
                expected_frame=target.getRect(),
            )


def centre(widget: QWidget) -> QPoint:
    return widget.mapToGlobal(widget.rect().center())
