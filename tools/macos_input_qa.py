"""Keyboard actions in a synthetic TextEdit document and denied-permission UI."""

from __future__ import annotations

import importlib
import subprocess
import tempfile
from functools import partial
from pathlib import Path
from typing import Any
from unittest.mock import patch

from PySide6.QtWidgets import QLabel

from polyglotic_desktop.core.listening.check import SourceActivity, Step, Ticked
from polyglotic_desktop.core.listening.sources import MIC, WHOLE_SYSTEM
from tools import app_tour as kit
from tools.macos_full_screen_checks import Ax
from tools.macos_quartz import SETTLE, Evidence, Pointer


def permissions(evidence: Evidence, home: Any) -> kit.Step:
    from tests.test_caption_check import NOW, facts

    hub = kit.hub()
    settings = hub.settings
    home.go_to("settings")
    settings.show_section("dictation")
    with patch.object(settings, "typing_allowed", return_value=False):
        settings.show_typing_permission()
        warning = settings.typing_not_allowed
        settings.ensureWidgetVisible(warning)
        before = home.frameGeometry()
        yield kit.pause(SETTLE)
        text = " ".join(label.text() for label in warning.findChildren(QLabel))
        evidence.record(
            "denied-accessibility",
            home,
            before,
            "one visible permission explanation and enabled System Settings button",
            warning.isVisible()
            and "Accessibility" in text
            and settings.typing_settings.isEnabled(),
            input="denied permission fixture",
        )
    settings.show_typing_permission()
    home.go_to("help")
    help_page = hub.help
    for source, words in (
        (Ticked(WHOLE_SYSTEM, "system-audio", "system"), "System Audio Recording"),
        (Ticked(MIC, "microphone", "mic"), "Microphone"),
    ):
        name = source.name
        inputs = facts(
            ticked=[source],
            activity={source.id: SourceActivity(NOW - 12, not_allowed=True)},
        )
        with patch.object(help_page, "_facts", return_value=inputs):
            before = home.frameGeometry()
            help_page.refresh()
            fix = help_page.fixes[Step.SOUND]
            help_page.ensureWidgetVisible(fix)
            yield kit.pause(SETTLE)
            evidence.record(
                "denied-" + name,
                home,
                before,
                "one visible recovery instruction naming " + words,
                fix.isVisible() and words in fix.text() and "Privacy" in fix.text(),
                input="capture not_allowed fixture",
            )
    help_page.refresh()


def keyboard(evidence: Evidence, pointer: Pointer, home: Any) -> kit.Step:
    from polyglotic_desktop.platform.macos import hold_key, text_input

    q = pointer.q
    ax = Ax()

    def changed(pid: int, previous: str | None) -> bool:
        value = ax.text(pid)
        return (
            value is not None
            and previous is not None
            and value[len(previous) :].strip() == kit.CAPTION
        )

    desktop = kit.STATE["desktop"]
    desktop.settings.update(dictation=True, dictation_key="f9")
    with tempfile.TemporaryDirectory(prefix="keyboard-qa-") as folder:
        document = Path(folder) / "Polyglotic QA.txt"
        document.write_text("", encoding="utf-8")
        subprocess.run(
            ["open", "-a", "TextEdit", str(document)], check=True, timeout=15
        )
        yield kit.pause(1)
        cocoa = importlib.import_module("AppKit")
        editor = cocoa.NSRunningApplication.runningApplicationsWithBundleIdentifier_(
            "com.apple.TextEdit"
        )[0]
        pid = editor.processIdentifier()
        editor.activateWithOptions_(cocoa.NSApplicationActivateIgnoringOtherApps)
        yield kit.wait(
            lambda: editor.isActive() and ax.text(pid) == "", 5, "empty QA editor"
        )
        for name, key in (("type-what-they-said", "f8"), ("dictation", "f9")):
            before = home.frameGeometry()
            old = ax.text(pid)
            code = hold_key.KEY_CODES[key]
            if text_input.allowed(ask=False) and editor.isActive() and old is not None:
                q.CGEventPost(
                    q.kCGHIDEventTap, q.CGEventCreateKeyboardEvent(None, code, True)
                )
                yield kit.pause(3)
                q.CGEventPost(
                    q.kCGHIDEventTap, q.CGEventCreateKeyboardEvent(None, code, False)
                )
                yield kit.wait(partial(changed, pid, old), 8, "")
            after = ax.text(pid)
            addition = (after or "")[len(old or "") :].strip()
            evidence.record(
                name,
                home,
                before,
                "one new replay sentence typed in TextEdit after key-up",
                old is not None
                and after is not None
                and after.startswith(old)
                and addition == kit.CAPTION,
                key=key,
                initial_length=len(old or ""),
                added_length=len(addition),
                permission=text_input.allowed(ask=False),
            )
        if editor.isActive():
            # Save this already-named temporary document, then close its window.
            for command in (1, 13):  # ANSI S, W
                for down in (True, False):
                    event = q.CGEventCreateKeyboardEvent(None, command, down)
                    q.CGEventSetFlags(event, q.kCGEventFlagMaskCommand)
                    q.CGEventPost(q.kCGHIDEventTap, event)
                yield kit.pause(SETTLE)
