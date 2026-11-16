"""The words of the OS the app runs on (polyglotic-hq 409): where a string
says PC or Windows, a Mac shows its own, and Windows' text is unchanged.
The guard: every interface string that says PC or Windows has a Mac
counterpart through `pc_or_mac` - unless it's for a feature the Mac build
hides - and no Mac counterpart says PC or Windows."""

import ast
import re
import sys
from pathlib import Path

import pytest

from polyglotic_desktop.ui import os_words as ui_os_words
from polyglotic_desktop.ui_next import os_words
from polyglotic_desktop.ui_next.sound_card import default_name

SOURCE = Path(__file__).resolve().parents[2] / "src" / "polyglotic_desktop"
WINDOWS_WORDS = re.compile(r"\bWindows\b|\bPCs?\b|\bPC's\b")
WRAPPERS = ("_tr", "_trn", "_tr_app", "tr")
HIDDEN_ON_A_MAC = {
    # starting at sign-in: no adapter on a Mac (OsAdapters.start_at_sign_in)
    "Start Polyglotic with Windows?",
    "Start with Windows",
    (
        "It waits in the tray, so captions are a click away when you play or "
        "watch. Windows' Startup apps can turn it off."
    ),
    # the word card's voice: no voices on a Mac (OsAdapters.speaker)
    (
        "No {language} voice on this PC yet. Windows adds one for free: Settings > "
        "Time & language > Speech > Add voices, then {language}."
    ),
    "No {language} voice on this PC",
    "Opens Windows' Settings, where voices are added",
    # a metered connection: macOS isn't asked (OsAdapters.metered)
    "Paused: Windows says this connection is metered. {size} left to download.",
    # dictation's key: not held on a Mac (OsAdapters.hold_key)
    "Windows keeps that one for itself: choose another.",
}


@pytest.mark.parametrize("module", [os_words, ui_os_words])
def test_a_mac_reads_its_own_words(
    monkeypatch: pytest.MonkeyPatch, module: object
) -> None:
    pick = module.pc_or_mac  # type: ignore[attr-defined]
    monkeypatch.setattr(sys, "platform", "win32")
    assert pick("PC", "Mac") == "PC"
    monkeypatch.setattr(sys, "platform", "darwin")
    assert pick("PC", "Mac") == "Mac"


def test_home_sound_says_this_macs_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    assert default_name(None) == "This PC's default"
    monkeypatch.setattr(sys, "platform", "darwin")
    assert default_name(None) == "This Mac's default"


def _text(node: ast.expr) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _wrapper(call: ast.Call) -> bool:
    name = (
        call.func.attr
        if isinstance(call.func, ast.Attribute)
        else (call.func.id if isinstance(call.func, ast.Name) else "")
    )
    return name in WRAPPERS and bool(call.args) and _text(call.args[0]) is not None


def test_every_pc_string_has_a_mac_one() -> None:
    alone, mac_says_pc = [], []
    for path in sorted(SOURCE.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        paired: set[int] = set()
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "pc_or_mac"
            ):
                for arg in node.args:
                    paired.add(id(arg))
                mac = node.args[1]
                if isinstance(mac, ast.Call) and _wrapper(mac):
                    text = _text(mac.args[0]) or ""
                    if WINDOWS_WORDS.search(text):
                        mac_says_pc.append(f"{path.name}:{mac.lineno} {text[:60]}")
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and _wrapper(node) and id(node) not in paired:
                text = _text(node.args[0]) or ""
                if WINDOWS_WORDS.search(text) and text not in HIDDEN_ON_A_MAC:
                    alone.append(f"{path.name}:{node.lineno} {text[:60]}")
    assert alone == [], "say it on a Mac too: pc_or_mac(_tr(pc), _tr(mac))"
    assert mac_says_pc == []
