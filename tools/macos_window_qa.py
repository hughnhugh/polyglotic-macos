"""Exercise the running desktop app on GitHub's Cocoa desktop with Quartz input."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from typing import Any

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QAbstractButton, QApplication, QScrollArea, QWidget

from polyglotic_desktop.core.listening.sources import SourceId
from tools import app_tour as kit
from tools.macos_input_qa import keyboard, permissions
from tools.macos_quartz import SETTLE, Evidence, Pointer, centre
from tools.macos_settings_sweep import activate, first_run, guarded, run_app
from tools.macos_ui_lab import hosted_mac
from tools.macos_visual_qa import anki, font_sheet, sign_in


class WindowChecks:
    def __init__(self, out: Path, focus: str = "") -> None:
        self.focus = focus
        self.evidence = Evidence(out)
        self.pointer = Pointer()

    def click(self, button: QWidget | None) -> kit.Step:
        if button is None or not button.isVisible() or not button.isEnabled():
            raise AssertionError("the control is missing, hidden or disabled")
        parent = button.parentWidget()
        while parent:
            if isinstance(parent, QScrollArea):
                parent.ensureWidgetVisible(button)
            parent = parent.parentWidget()
        yield kit.pause(0.12)
        yield from self.pointer.click(centre(button))

    def captions(self, window: Any) -> kit.Step:
        before = window.frameGeometry()
        self.pointer.post(self.pointer.q.kCGEventMouseMoved, centre(window))
        yield kit.pause(1)
        self.evidence.record(
            "caption-hover",
            window,
            before,
            "one visible settings button",
            window.buttons["settings"].isVisible(),
        )
        for name, button, popover in (
            ("settings", window.buttons["settings"], "popover"),
            ("modes", window.preset_chip, "presets"),
        ):
            yield from self.click(button)
            popup = getattr(window, popover)
            opened = popup is not None and popup.isVisible()
            self.evidence.record(
                "caption-" + name,
                popup if opened else window,
                before,
                "one visible popover",
                opened,
            )
            if not opened:
                continue
            if name == "modes":
                video = popup.findChild(QAbstractButton, "presets.preset.video")
                yield from self.click(video)
                yield kit.pause(1)
                selected = kit.STATE["interface"].windows.preset_menu.chosen
                self.evidence.record(
                    "video-mode",
                    window,
                    before,
                    "selected preset equals video",
                    selected == "video",
                    selected=selected,
                )
            window.close_settings()
            self.pointer.post(self.pointer.q.kCGEventMouseMoved, centre(window))
            yield kit.pause(1)

    def pages(self, window: Any) -> kit.Step:
        for key in window.nav_buttons:
            before = window.frameGeometry()
            yield from self.click(window.nav_buttons[key])
            self.evidence.record(
                "page-" + key,
                window,
                before,
                f"selected page equals {key}",
                window.current == key,
                selected=window.current,
            )
            if key == "settings":
                page = window.pages[key]
                for scroll in [page, *page.findChildren(QScrollArea)]:
                    if not isinstance(scroll, QScrollArea):
                        continue
                    bar = scroll.verticalScrollBar()
                    if scroll.isVisible() and bar.maximum() > bar.value():
                        initial = bar.value()
                        yield from self.pointer.scroll(centre(scroll.viewport()))
                        self.evidence.record(
                            "settings-scroll",
                            window,
                            before,
                            "scroll offset increases by at least one",
                            bar.value() > initial,
                            initial=initial,
                            final=bar.value(),
                        )
                        break
                else:
                    self.evidence.record(
                        "settings-scroll",
                        window,
                        before,
                        "one scrollable settings view",
                        False,
                    )
            if key == "account":
                buttons = [
                    b
                    for b in window.findChildren(QAbstractButton)
                    if b.isVisible() and b.text().replace("&", "").lower() == "upgrade"
                ]
                if buttons:
                    yield from self.click(buttons[0])
                self.evidence.record(
                    "upgrade",
                    window,
                    before,
                    "selected page equals upgrade",
                    window.current == "upgrade",
                    buttons=len(buttons),
                )

    def tray(self, window: Any) -> kit.Step:
        tray = kit.STATE["desktop"].tray
        before = window.frameGeometry()
        icon = tray.geometry()
        if icon.isEmpty():
            self.evidence.record(
                "menu-bar",
                window,
                before,
                "one menu-bar icon with a click target",
                False,
                icon=icon.getRect(),
            )
            return
        menu = kit.STATE["desktop"].tray_menu
        yield from self.pointer.click(icon.center(), right=True)
        count = len([action for action in menu.actions() if action.isVisible()])
        self.evidence.record(
            "menu-bar",
            menu if menu.isVisible() else window,
            before,
            "one open menu with at least one item",
            menu.isVisible() and count > 0,
            items=count,
            icon=icon.getRect(),
        )
        menu.close()

    def return_to_icon(self, home: Any, caption: Any) -> kit.Step:
        """Open through the status item, then return the pointer to precisely that item."""
        import importlib

        from polyglotic_desktop.platform.macos import on_top

        cocoa = importlib.import_module("AppKit")
        objc = importlib.import_module("objc")
        desktop = kit.STATE["desktop"]
        icon = desktop.tray.geometry().center()
        finder = cocoa.NSRunningApplication.runningApplicationsWithBundleIdentifier_(
            "com.apple.finder"
        )[0]
        triggered: list[str] = []
        desktop.tray_menu.triggered.connect(
            lambda action: triggered.append(action.objectName() or action.text())
        )
        # A real document can actually cover Home; Finder's empty desktop cannot.
        import subprocess

        document = kit.OUT / "status-item-test.txt"
        document.write_text("Status item QA", encoding="utf-8")
        subprocess.run(
            ["open", "-a", "TextEdit", str(document)], check=True, timeout=10
        )
        yield kit.pause(1)
        editor = cocoa.NSRunningApplication.runningApplicationsWithBundleIdentifier_(
            "com.apple.TextEdit"
        )[0]
        for case in (
            "primary",
            "open-action",
            "show-captions",
            "primary-covered",
            "open-action-covered",
            "show-captions-covered",
        ):
            triggered.clear()
            home.go_to("home")
            home.hide()
            desktop.hide_windows.setChecked(True)
            other = editor if case.endswith("-covered") else finder
            other.activateWithOptions_(cocoa.NSApplicationActivateIgnoringOtherApps)
            yield kit.pause(SETTLE)
            origin = str(
                cocoa.NSWorkspace.sharedWorkspace()
                .frontmostApplication()
                .bundleIdentifier()
            )
            operation = case.removesuffix("-covered")
            window = caption if operation == "show-captions" else home
            rect = window.frameGeometry()
            yield from self.pointer.click(icon, right=operation != "primary")
            if operation != "primary":
                menu = desktop.tray_menu
                action = (
                    desktop.hide_windows
                    if operation == "show-captions"
                    else desktop.open_window
                )
                self.evidence.record(
                    "tray-menu-" + case,
                    menu if menu.isVisible() else home,
                    rect,
                    "status menu remains open from Finder until its action is chosen",
                    menu.isVisible(),
                    icon=icon.toTuple(),
                    action=menu.actionGeometry(action).getRect(),
                    menu=menu.frameGeometry().getRect(),
                    front=str(
                        cocoa.NSWorkspace.sharedWorkspace()
                        .frontmostApplication()
                        .bundleIdentifier()
                    ),
                )
                if menu.isVisible():
                    point = menu.mapToGlobal(menu.actionGeometry(action).center())
                    yield from self.pointer.click(point)
            yield kit.pause(SETTLE)
            native = objc.objc_object(c_void_p=on_top.window_of(int(window.winId())))

            def sample(window: Any = window, native: Any = native) -> dict[str, Any]:
                return {
                    "qt_visible": window.isVisible(),
                    "native_visible": bool(native.isVisible()),
                    "minimized": bool(native.isMiniaturized()),
                    "active_space": bool(native.isOnActiveSpace()),
                    "showing": bool(
                        native.occlusionState() & cocoa.NSWindowOcclusionStateVisible
                    ),
                }

            def visible(s: dict[str, Any]) -> bool:
                return bool(
                    s["qt_visible"]
                    and s["native_visible"]
                    and not s["minimized"]
                    and s["active_space"]
                    and s["showing"]
                )

            initial = sample()
            self.evidence.record(
                "tray-open-" + case,
                window,
                rect,
                "one on-screen window after opening from status item",
                visible(initial),
                native=initial,
                origin=origin,
                triggered=list(triggered),
                menu_open=desktop.tray_menu.isVisible(),
                hide_captions=desktop.hide_windows.isChecked(),
                front=str(
                    cocoa.NSWorkspace.sharedWorkspace()
                    .frontmostApplication()
                    .bundleIdentifier()
                ),
            )
            before = window.frameGeometry()
            start = centre(window)
            self.pointer.post(self.pointer.q.kCGEventMouseMoved, start)
            yield kit.pause(SETTLE)
            path = []
            for n in range(1, 13):
                self.pointer.post(
                    self.pointer.q.kCGEventMouseMoved, start + (icon - start) * (n / 12)
                )
                yield kit.pause(0.07)
                path.append(sample())
            yield kit.pause(2)
            path.append(sample())
            self.evidence.record(
                "tray-return-" + case,
                window,
                before,
                "zero hidden or minimized samples returning to the same menu-bar icon",
                visible(initial)
                and all(visible(s) for s in path)
                and window.frameGeometry() == before,
                path=path,
            )
        desktop.hide_windows.setChecked(True)
        home.show()
        activate()
        yield kit.pause(SETTLE)

    def home_at_menu_bar(self, home: Any, overlays: bool) -> kit.Step:
        """Check native visibility too: Qt can still see a window on a different Space."""
        import importlib

        from polyglotic_desktop.platform.macos import on_top

        cocoa = importlib.import_module("AppKit")
        objc = importlib.import_module("objc")
        native = objc.objc_object(c_void_p=on_top.window_of(int(home.winId())))
        current = cocoa.NSRunningApplication.currentApplication()
        finder = cocoa.NSRunningApplication.runningApplicationsWithBundleIdentifier_(
            "com.apple.finder"
        )[0]

        def state() -> dict[str, Any]:
            return {
                "visible": home.isVisible(),
                "minimized": home.isMinimized() or native.isMiniaturized(),
                "active_space": bool(native.isOnActiveSpace()),
                "active": bool(current.isActive()),
                "showing": bool(
                    native.occlusionState() & cocoa.NSWindowOcclusionStateVisible
                ),
                "full": bool(native.styleMask() & cocoa.NSWindowStyleMaskFullScreen),
            }

        home.go_to("home")
        prefix = "menu-bar-overlays-" if overlays else "menu-bar-"
        for case in ("focused", "unfocused", "full-screen"):
            home.showNormal()
            home.raise_()
            home.activateWindow()
            activate()
            if case == "unfocused":
                finder.activateWithOptions_(
                    cocoa.NSApplicationActivateIgnoringOtherApps
                )
            elif case == "full-screen":
                home.showFullScreen()
            yield kit.pause(2)
            before = home.frameGeometry()
            start = centre(home)
            self.pointer.post(self.pointer.q.kCGEventMouseMoved, start)
            yield kit.pause(SETTLE)
            initial = state()
            prepared = initial["active"] == (case != "unfocused") and initial[
                "full"
            ] == (case == "full-screen")
            self.evidence.record(
                prefix + case + "-before",
                home,
                before,
                "Home in requested focus and Space, visible, zero minimized windows",
                prepared and initial["showing"] and not initial["minimized"],
                **initial,
            )
            # Cross the title bar into the system menu; no press during this journey.
            journey = []
            destination = (
                kit.STATE["desktop"].tray.geometry().center().x()
                if overlays
                else start.x()
            )
            for n in range(1, 13):
                self.pointer.post(
                    self.pointer.q.kCGEventMouseMoved,
                    QPoint(
                        round(start.x() + (destination - start.x()) * n / 12),
                        round(start.y() * (1 - n / 12)),
                    ),
                )
                yield kit.pause(0.06)
                journey.append(state())
            yield kit.pause(1)
            end = state()
            self.evidence.record(
                prefix + case,
                home,
                before,
                "Home stays visible and unminimized on the same Space and at the same size",
                prepared
                and end["visible"]
                and not end["minimized"]
                and end["active_space"]
                and end["showing"]
                and initial["full"] == end["full"]
                and all(
                    s["visible"]
                    and not s["minimized"]
                    and s["active_space"]
                    and s["showing"]
                    for s in journey
                )
                and before == home.frameGeometry(),
                initial=initial,
                final=end,
                journey=journey,
            )
        home.showNormal()
        yield kit.pause(1)

    def run(self) -> kit.Step:
        from polyglotic_desktop.ui_next import style

        yield from first_run()
        home = kit.hub().window
        assert QApplication.platformName() == "cocoa"
        activate()
        if not self.focus:
            self.evidence.record(
                "startup-scale",
                home,
                home.frameGeometry(),
                "standard Cocoa text uses the app's Normal size once",
                style.windows_text_scale() == 1.0,
                os_scale=style.windows_text_scale(),
                app_scale=style.app_text_size(),
                qt_points=QApplication.font().pointSizeF(),
            )
        windows = kit.STATE["interface"].windows
        if kit.caption_window() is None:
            button = home.findChild(QAbstractButton, f"picker.add.{kit.PLAYER}")
            if button is not None:
                yield from self.click(button)
        yield kit.wait(
            lambda: kit.caption_window() is not None, 12, "replay caption window"
        )
        caption = kit.caption_window()
        assert caption is not None
        kit.STATE["desktop"].lock_windows.setChecked(False)
        if self.focus == "status":
            yield from self.return_to_icon(home, caption)
            for overlays in (False, True):
                kit.STATE["desktop"].hide_windows.setChecked(not overlays)
                yield from self.home_at_menu_bar(home, overlays)
            return
        if self.focus == "anki":
            kit.STATE["desktop"].hide_windows.setChecked(True)
            yield from anki(self.evidence, self.pointer, home)
            return
        home.hide()
        yield kit.pause(SETTLE)
        yield from self.evidence.resize(self.pointer, "caption", caption)
        yield from self.evidence.inactive_cursors(self.pointer, "caption", caption)
        yield from guarded("caption controls", self.captions(caption))
        windows.set_captioned(
            [(kit.PLAYER, caption.source), ("Second player", SourceId("app:second"))]
        )
        windows.join(kit.PLAYER)
        yield kit.pause(SETTLE)
        joined = windows.joined_window
        if joined is not None:
            yield from self.evidence.resize(self.pointer, "joined", joined)
            yield from self.evidence.inactive_cursors(self.pointer, "joined", joined)
        else:
            kit.check("joined window shows", False)
        kit.STATE["desktop"].hide_windows.setChecked(True)
        home.show()
        home.raise_()
        activate()
        yield kit.pause(SETTLE)
        yield from self.evidence.resize(self.pointer, "main", home)
        if self.focus == "geometry":
            return
        if joined is not None:
            yield from guarded(
                "open from the status item", self.return_to_icon(home, joined)
            )
        for overlays in (False, True):
            kit.STATE["desktop"].hide_windows.setChecked(not overlays)
            yield kit.pause(SETTLE)
            yield from guarded(
                "Home at menu bar", self.home_at_menu_bar(home, overlays)
            )
        kit.STATE["desktop"].hide_windows.setChecked(True)
        yield from guarded("sidebar", self.pages(home))
        yield from guarded("tray", self.tray(home))
        yield from guarded("Anki export", anki(self.evidence, self.pointer, home))
        yield from guarded("caption fonts", font_sheet(self.evidence, home))
        yield from guarded("email sign-in", sign_in(self.evidence, self.pointer, home))
        yield from guarded("permission screens", permissions(self.evidence, home))
        yield from guarded(
            "F8 and dictation", keyboard(self.evidence, self.pointer, home)
        )
        home.hide()
        activate()
        kit.STATE["interface"].transcripts.show(kit.PLAYER)
        yield kit.pause(SETTLE)
        transcript = next(
            (
                w
                for w in QApplication.topLevelWidgets()
                if w.isVisible() and w.objectName() == "transcript_window"
            ),
            None,
        )
        if transcript is None:
            kit.check("transcript shows", False)
        else:
            transcript.raise_()
            transcript.activateWindow()
            yield kit.pause(SETTLE)
            yield from self.evidence.resize(self.pointer, "transcript", transcript)
            transcript.close()


def main(out: Path, focus: str = "") -> int:
    if not hosted_mac():
        raise SystemExit("Requires the ephemeral GitHub-hosted macOS desktop")
    os.environ["QT_QPA_PLATFORM"] = "cocoa"
    checks = WindowChecks(out, focus)
    driver = kit.Driver(360)
    driver.steps = checks.run()
    with tempfile.TemporaryDirectory(prefix="quartz-qa-") as scratch:
        from tests.test_open_beta_round_2 import PRICES
        from tests.ui.test_check_install import sample_dictionaries

        account = {
            "account_id": "qa-demo",
            "registered": True,
            "plan": "beta_free",
            "cohort": "open_beta",
            "percent_left": 85,
        }
        replies = {
            "/v1/accounts/me": account,
            "/v1/accounts/marketing-default": {"country": "AU"},
            "/v1/checkout/prices": PRICES,
        }
        dictionaries = sample_dictionaries(Path(scratch) / "dictionaries")
        run_app(
            Path(scratch),
            str(dictionaries),
            driver,
            http_replies=replies,
            native_keys=True,
        )
        (out / "checks.json").write_bytes((Path(scratch) / "checks.json").read_bytes())
    return int(
        not checks.evidence.steps or any(not c["ok"] for c in kit.RESULTS["checks"])
    )


if __name__ == "__main__":
    result = main(Path(sys.argv[1]), *sys.argv[2:])
    sys.stdout.flush()
    os._exit(result)
