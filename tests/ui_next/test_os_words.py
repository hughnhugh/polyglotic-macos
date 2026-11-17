"""The words of the OS the app runs on (polyglotic-hq 409): where a string
says PC or Windows, a Mac shows its own, and Windows' text is unchanged.
The guard: every interface string that says PC or Windows has a Mac
counterpart through `pc_or_mac` - unless it's for a feature the Mac build
hides - and no Mac counterpart says PC or Windows. Since 451 it hears
Windows' other words too: the tray (a Mac's icon sits in the menu bar),
Task Manager, the Win key and Right Ctrl; and a shortcut with Ctrl says
Command's on a Mac."""

import ast
import re
import sys
from pathlib import Path

import pytest

from polyglotic_desktop.ui import os_words as ui_os_words
from polyglotic_desktop.ui_next import os_words
from polyglotic_desktop.ui_next.sound_card import default_name

SOURCE = Path(__file__).resolve().parents[2] / "src" / "polyglotic_desktop"
WINDOWS_WORDS = re.compile(
    r"\bWindows\b|\bPCs?\b|\bPC's\b|\btray\b|Task Manager|\bWin\b|Right Ctrl"
)
WRAPPERS = ("_tr", "_trn", "_tr_app", "tr")
HIDDEN_ON_A_MAC = {
    # a metered connection: macOS isn't asked (OsAdapters.metered)
    "Paused: Windows says this connection is metered. {size} left to download.",
    # dictation's key: not held on a Mac (OsAdapters.hold_key)
    "Windows keeps that one for itself: choose another.",
    # a key's name: a Mac names its modifiers itself (dictation_key._mac_name)
    "Win",
    "Right Win",
    "Right Ctrl",
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
            if isinstance(node, ast.Call) and ast.unparse(node.func).endswith(
                "pc_or_mac"
            ):  # `pc_or_mac(...)` or `os_words.pc_or_mac(...)`
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


@pytest.mark.parametrize(
    ("text", "mac"),
    [
        ("Hidden - Ctrl+Alt+H", "Hidden - ⌃⌘H"),
        (
            "Lock all (Ctrl+Alt+L); Pause is Ctrl+Alt+P.",
            "Lock all (⌃⌘L); Pause is ⌃⌘P.",
        ),
        ("Drücke Strg+Alt+H.", "Drücke ⌃⌘H."),  # German's translation
        ("Ctrl+Alt+D", "Ctrl+Alt+D"),  # dictation's key: not one of the hotkeys
        # Qt's Ctrl is Command on a Mac (451)
        ("Bigger text (Ctrl+wheel)", "Bigger text (⌘+wheel)"),
        ("Größere Schrift (Strg+Mausrad)", "Größere Schrift (⌘+Mausrad)"),
        (
            "Copy the word, its reading and meaning (Ctrl+C)",
            "Copy the word, its reading and meaning (⌘C)",
        ),
    ],
)
def test_a_mac_names_the_hotkeys_its_own_way(
    monkeypatch: pytest.MonkeyPatch, text: str, mac: str
) -> None:
    """Control+Command on a Mac (polyglotic-hq 428), in every language."""
    monkeypatch.setattr(sys, "platform", "win32")
    assert os_words.hotkeys_here(text) == text
    monkeypatch.setattr(sys, "platform", "darwin")
    assert os_words.hotkeys_here(text) == mac


def test_no_text_names_windows_hotkeys_on_a_mac(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every text that names Ctrl+Alt+L, P or H (Help's topics and fixes,
    Home's paused line, the lock button's tip) says ⌃⌘ on a Mac (428)."""
    from polyglotic_desktop.core.listening.check import Problem
    from polyglotic_desktop.ui_next import help_page, home
    from polyglotic_desktop.ui_next.caption_window import lock_tip
    from polyglotic_desktop.ui_next.views.home import Detail

    monkeypatch.setattr(sys, "platform", "darwin")
    texts = [text for _, text in help_page.set_up()]
    texts += [help_page.problem(p, "Discord")[1] for p in Problem]
    texts += [home._detail(Detail.RESUME, None), lock_tip("⌃⌘L")]
    assert not [t for t in texts if re.search(r"(Ctrl|Strg)\+Alt\+[LPH]", t)]
    assert sum("⌃⌘" in t for t in texts) >= 5


def test_every_ctrl_shortcut_is_said_the_macs_way() -> None:
    """A text naming a shortcut with Ctrl ("Ctrl+wheel", "Ctrl+C") goes
    through `hotkeys_here`, so a Mac says Command's (polyglotic-hq 451)."""
    alone = []
    for path in sorted(SOURCE.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        said: set[int] = set()
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "hotkeys_here"
            ):
                said.update(id(n) for n in ast.walk(node))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and _wrapper(node) and id(node) not in said:
                text = _text(node.args[0]) or ""
                if re.search(r"\bCtrl\+(?!Alt\+[LPH]\b)", text):
                    alone.append(f"{path.name}:{node.lineno} {text[:60]}")
    assert alone == [], "say it as a Mac does: hotkeys_here(_tr(...))"
