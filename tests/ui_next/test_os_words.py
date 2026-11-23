"""The words of the OS the app runs on (polyglotic-hq 409): where a string
says PC or Windows, a Mac shows its own, and Windows' text is unchanged.
The guard: every interface string that says PC or Windows has a Mac
counterpart through `pc_or_mac` - unless it's for a feature the Mac build
hides - and no Mac counterpart says PC or Windows. Since 451 it hears
Windows' other words too: the tray (a Mac's icon sits in the menu bar),
Task Manager, the Win key and Right Ctrl; and a shortcut with Ctrl says
Command's on a Mac. Since 571 Linux has its own words where the PC's name
Windows itself - its Settings, Task Manager, the tray (GNOME has none
without an extension) - through `pc_mac_or_linux`."""

import ast
import re
import sys
from pathlib import Path

import pytest

from polyglotic_desktop.core.listening.hotkeys import Platform
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


HIDDEN_ON_LINUX = {
    # dictation's key and its words: slice 8 (OsAdapters.hold_key is
    # not_yet on Linux)
    "Win",
    "Right Win",
    "That key types. Hold it with Ctrl, Alt or Win, or choose another.",
    "Windows keeps that one for itself: choose another.",
    "The tray's menu switches it too.",
    (
        "On their own, only Right Ctrl or Ctrl + Win work: hold Ctrl, Alt or Shift "
        "with a key."
    ),
    # the Microsoft Store's copy: Windows only
    (
        "the Microsoft Store updates this copy - open the Store, go to Library and "
        "choose Get updates"
    ),
    "Version {version}, from the Microsoft Store, which keeps it up to date.",
    # Linux has its own line before it (home.py: "the only choice on Linux")
    "instead of apps (the only choice on this version of Windows)",
    # Linux has no speech settings to open: the card says why there's no
    # voice, with no button (lookup_card._no_voice, 591)
    "Opens Windows' Settings, where voices are added",
    # Linux's own line before it (pack_row.py: on_linux)
    "Paused: Windows says this connection is metered. {size} left to download.",
}
"""Strings naming Windows that Linux never shows, and why (571)."""
LINUX_HIDES_PREFIXES = (
    "No {language} voice on this PC yet. Windows adds",  # Linux's own (591)
    "Hold {key} and speak; let go, and your words are typed where",  # Dictation topic
    "Turn on Dictation in Settings > Dictation, or in the tray menu.",  # slice 8
    "Click, then press the key or combination you want to hold:",  # slice 8
)
NAMES_WINDOWS = re.compile(r"\bWindows\b|\btray\b|Task Manager|\bWin\b|Microsoft")
"""What Linux mustn't say: Windows' own names (a PC is a PC on Linux too)."""


@pytest.mark.parametrize("module", [os_words, ui_os_words])
def test_a_mac_reads_its_own_words(
    monkeypatch: pytest.MonkeyPatch, module: object
) -> None:
    pick = module.pc_or_mac  # type: ignore[attr-defined]
    monkeypatch.setattr(sys, "platform", "win32")
    assert pick("PC", "Mac") == "PC"
    monkeypatch.setattr(sys, "platform", "darwin")
    assert pick("PC", "Mac") == "Mac"


@pytest.mark.parametrize("module", [os_words, ui_os_words])
def test_linux_reads_its_own_words_where_the_pcs_name_windows(
    monkeypatch: pytest.MonkeyPatch, module: object
) -> None:
    """A third set for Linux (571); the PC's words otherwise (550)."""
    pick = module.pc_mac_or_linux  # type: ignore[attr-defined]
    monkeypatch.setattr(sys, "platform", "win32")
    assert pick("PC", "Mac", "Linux") == "PC"
    monkeypatch.setattr(sys, "platform", "darwin")
    assert pick("PC", "Mac", "Linux") == "Mac"
    monkeypatch.setattr(sys, "platform", "linux")
    assert pick("PC", "Mac", "Linux") == "Linux"
    assert module.pc_or_mac("PC", "Mac") == "PC"  # type: ignore[attr-defined]


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
                ("pc_or_mac", "pc_mac_or_linux")
            ):  # `pc_or_mac(...)`, `os_words.pc_or_mac(...)`, or with Linux's
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


@pytest.mark.parametrize(
    ("text", "linux"),
    [
        (
            "Lock all (Ctrl+Alt+L); Pause is Ctrl+Alt+P.",
            "Lock all (Ctrl+Alt+Shift+L); Pause is Ctrl+Alt+Shift+P.",
        ),
        ("Drücke Strg+Alt+H.", "Drücke Strg+Alt+Umschalt+H."),  # Qt's German
        ("Ctrl+Alt+D", "Ctrl+Alt+D"),  # dictation's key: not one of the hotkeys
        ("Bigger text (Ctrl+wheel)", "Bigger text (Ctrl+wheel)"),  # Ctrl is Ctrl
    ],
)
def test_linux_names_its_own_hotkeys(
    monkeypatch: pytest.MonkeyPatch, text: str, linux: str
) -> None:
    """Ctrl+Alt+Shift on Linux (polyglotic-hq 570, decision 0293), in every
    language."""
    monkeypatch.setattr(sys, "platform", "linux")
    assert os_words.platform() is Platform.LINUX
    assert os_words.hotkeys_here(text) == linux


@pytest.mark.parametrize(
    ("system", "platform"),
    [("win32", Platform.WINDOWS), ("darwin", Platform.MAC), ("linux", Platform.LINUX)],
)
def test_each_os_tells_core_its_own(
    monkeypatch: pytest.MonkeyPatch, system: str, platform: Platform
) -> None:
    from polyglotic_desktop.ui import os_words as ui_os_words

    monkeypatch.setattr(sys, "platform", system)
    assert os_words.platform() is platform
    assert ui_os_words.platform() is platform


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


def _hidden_on_linux(text: str) -> bool:
    return text in HIDDEN_ON_LINUX or text.startswith(LINUX_HIDES_PREFIXES)


def test_every_windows_string_has_linux_words() -> None:
    """Every interface string naming Windows itself - its Settings, Task
    Manager, the tray, the Win key, the Store - has Linux's own words through
    `pc_mac_or_linux`, unless Linux never shows it (HIDDEN_ON_LINUX, with
    why); and no Linux text names them (571)."""
    alone, linux_says_windows = [], []
    for path in sorted(SOURCE.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        paired: set[int] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and ast.unparse(node.func).endswith(
                "pc_mac_or_linux"
            ):
                paired.update(id(arg) for arg in node.args)
                linux = node.args[2]
                if isinstance(linux, ast.Call) and _wrapper(linux):
                    text = _text(linux.args[0]) or ""
                    if NAMES_WINDOWS.search(text):
                        linux_says_windows.append(f"{path.name}:{linux.lineno}")
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and _wrapper(node) and id(node) not in paired:
                text = _text(node.args[0]) or ""
                if NAMES_WINDOWS.search(text) and not _hidden_on_linux(text):
                    alone.append(f"{path.name}:{node.lineno} {text[:60]}")
    assert alone == [], (
        "say it on Linux too: pc_mac_or_linux(_tr(pc), _tr(mac), _tr(linux))"
    )
    assert linux_says_windows == []


def test_linux_names_no_windows_place(monkeypatch: pytest.MonkeyPatch) -> None:
    """What a learner reads on Linux - Help's topics and fixes, Home's lines,
    a caption window's notices and lock tips, the tray's note, a second
    start that gets no answer, the fall-back from apps - names Home and
    "quit Polyglotic", never Windows' Settings, Task Manager or the tray,
    which GNOME doesn't have without an extension (571). The PC's words on
    Windows are unchanged."""
    from polyglotic_desktop.core.listening.check import Problem
    from polyglotic_desktop.main import fell_back_text
    from polyglotic_desktop.ui.one_copy import not_answering
    from polyglotic_desktop.ui_next import help_page, home
    from polyglotic_desktop.ui_next.caption_window import (
        Notice,
        lock_tip,
        locked_text,
        notice_text,
    )
    from polyglotic_desktop.ui_next.views.home import Detail

    def said() -> list[str]:
        texts = []
        for hotkeys in ((), help_page.HOTKEYS):
            texts += [t for pair in help_page.set_up(hotkeys) for t in pair]
            texts += [help_page.problem(p, "Discord", hotkeys)[1] for p in Problem]
        for key in (True, False):
            texts += [home._detail(Detail.RESUME, None, key)]
        texts += [home._detail(Detail.START_AGAIN, None)]
        texts += [f() for f in home._UPDATE_DETAILS.values()]
        texts += [home._UNREACHABLE_DETAILS[Detail.SET_THE_CLOCK]()]
        texts += [home.clock_looks_wrong_notice()]
        texts += [notice_text(n, None) for n in Notice]
        texts += [locked_text(""), lock_tip(""), fell_back_text(), not_answering()]
        return texts

    monkeypatch.setattr(sys, "platform", "linux")
    on_linux = [t for t in said() if not _hidden_on_linux(t)]
    assert [t for t in on_linux if NAMES_WINDOWS.search(t)] == []
    assert sum(bool(re.search("[Qq]uit Polyglotic", t)) for t in on_linux) >= 4
    assert "Locked - unlock on Home" in on_linux
    monkeypatch.setattr(sys, "platform", "win32")
    on_windows = said()
    assert "Locked - unlock on Home or from the tray" in on_windows
    assert sum("from the tray" in t for t in on_windows) >= 4
