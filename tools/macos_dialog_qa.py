"""Photograph the localized Cocoa sign-out alert and exercise its native Cancel button."""

from __future__ import annotations

import importlib
import json
import subprocess
import time
from pathlib import Path
from typing import Any

from tools.macos_ui_lab import hosted_mac

STATE = "ui_next.qt_dialog"


def check(language: str, out: Path) -> int:
    if not hosted_mac():
        raise RuntimeError("Requires a disposable hosted Mac")

    from PySide6.QtWidgets import QMessageBox

    from polyglotic_desktop.ui import interface_language
    from polyglotic_desktop.ui.sign_in import sign_out_question
    from tools.ui_lab.lab import application

    out.mkdir(parents=True, exist_ok=True)
    app = application()
    interface_language.install(app, language)
    box = sign_out_question(None, unsent=True)
    cancel = QMessageBox.StandardButton.Cancel
    expected = [
        box.button(b).text().replace("&", "")
        for b in (cancel, QMessageBox.StandardButton.Yes)
    ]
    cocoa = importlib.import_module("AppKit")
    native = cocoa.NSApplication.sharedApplication()
    deadline = time.monotonic() + 15
    facts: dict[str, Any] = {"matched_buttons": 0, "photographed": False}

    def photograph(name: str, *args: str) -> bool:
        path = out / name
        photo = subprocess.run(
            ["screencapture", "-x", *args, str(path)], check=False, timeout=8
        )
        return photo.returncode == 0 and path.is_file() and path.stat().st_size > 0

    def observe(timer: Any) -> None:
        # NSAlert owns the modal event loop and its buttons. A Qt widget grab
        # cannot see them. This timer also runs in AppKit's modal mode.
        if time.monotonic() > deadline:
            timer.invalidate()
            photograph(STATE + ".desktop.jpg", "-m", "-t", "jpg")
            box.reject()
            return
        for window in native.windows():
            if not window.isVisible() or not window.contentView():
                continue
            buttons = {}
            stack = [window.contentView()]
            while stack:
                view = stack.pop()
                if view.isKindOfClass_(cocoa.NSButton):
                    buttons[str(view.title())] = view
                stack.extend(view.subviews())
            matched = sum(label in buttons for label in expected)
            facts["matched_buttons"] = max(facts["matched_buttons"], matched)
            if matched != len(expected):
                continue
            timer.invalidate()
            facts["window_level"] = window.level()
            facts["photographed"] = photograph(
                STATE + ".png", "-o", "-l", str(window.windowNumber())
            ) and photograph(STATE + ".desktop.jpg", "-m", "-t", "jpg")
            buttons[expected[0]].performClick_(None)
            return

    timer = cocoa.NSTimer.timerWithTimeInterval_repeats_block_(0.25, True, observe)
    loop = cocoa.NSRunLoop.currentRunLoop()
    for mode in (cocoa.NSDefaultRunLoopMode, cocoa.NSModalPanelRunLoopMode):
        loop.addTimer_forMode_(timer, mode)
    try:
        cancelled = box.exec() == cancel
    finally:
        timer.invalidate()
    ok = facts["photographed"] and cancelled
    facts.update(
        state=STATE,
        native_cancel_verified=ok,
        findings=[]
        if ok
        else [
            {
                "check": "native_dialog",
                "where": "NSAlert",
                "detail": "Expected two localized Cocoa buttons, paired pictures and a Cancel result",
            }
        ],
    )
    (out / (STATE + ".json")).write_text(json.dumps(facts, indent=1), encoding="utf-8")
    return int(not ok)
