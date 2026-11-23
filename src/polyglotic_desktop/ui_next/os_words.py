"""The words of the OS the app runs on (polyglotic-hq 409): where a string
says PC or Windows, a Mac shows its own - "Everything the Mac plays",
macOS's System Settings - each translated as any string is (decision
0034). Both are written at the call, `pc_or_mac(_tr("..PC.."),
_tr("..Mac.."))`, so the extractor finds both and each language drafts
both; Windows' text is unchanged. Where the PC's words name Windows itself
- its Settings, Task Manager, the tray - Linux gets a third set,
`pc_mac_or_linux(...)` (polyglotic-hq 571): Home and "quit Polyglotic"
rather than the tray, which GNOME doesn't have without an extension.

The app's hotkeys are named in the texts as Windows writes them
("Ctrl+Alt+L"; German "Strg+Alt+L"); `hotkeys_here` writes them as a Mac
does, "⌃⌘L" (polyglotic-hq 428): the symbols are the same in every
language, so no language drafts them again. Qt's Ctrl is Command on a Mac,
so a shortcut with Ctrl alone ("Ctrl+C", "Ctrl+wheel") is Command's there:
"⌘C", "⌘+wheel" (polyglotic-hq 451). On Linux the hotkeys are Ctrl+Alt+Shift
with the letter (570), Shift named as Qt names it there ("Umschalt" beside
German's "Strg").

`ui` and `ui_next` each have this module (they don't import each other).
"""

import re
import sys

from polyglotic_desktop.core.listening.hotkeys import Platform

_HOTKEY = re.compile(r"\b(Ctrl|Strg)\+Alt\+([LPH])\b")
"""One of the app's hotkeys (`ui.app.DesktopApp.hotkeys`) as a translated
text names it on Windows."""
_COMMAND_KEY = re.compile(r"\b(?:Ctrl|Strg)\+(?=[A-Z0-9]\b)")
"""Ctrl with a key ("Ctrl+C"): a Mac's menus write Command's "⌘C"."""
_COMMAND = re.compile(r"\b(?:Ctrl|Strg)\+(?!Alt\+)")
"""Ctrl with anything else ("Ctrl+wheel"): "⌘+wheel" on a Mac. Not Ctrl+Alt
with a key: dictation's own key is named by `dictation_key.key_words`."""


def on_a_mac() -> bool:
    return sys.platform == "darwin"


def on_linux() -> bool:
    """Linux (polyglotic-hq 550): the PC's words, but where a string names
    Windows itself - each such string Linux shows gets its own words."""
    return sys.platform.startswith("linux")


def platform() -> Platform:
    """The platform whose keys the app's own hotkeys follow (polyglotic-hq
    567): the one place each interface tells core which OS it is - Linux's
    own since 570."""
    if on_a_mac():
        return Platform.MAC
    return Platform.LINUX if on_linux() else Platform.WINDOWS


def pc_or_mac(pc: str, mac: str) -> str:
    """`mac` on a Mac, else `pc` - both already translated."""
    return mac if on_a_mac() else pc


def pc_mac_or_linux(pc: str, mac: str, linux: str) -> str:
    """`linux` on Linux, `mac` on a Mac, else `pc` - all already translated
    (polyglotic-hq 571): for the strings whose PC words name Windows."""
    if on_linux():
        return linux
    return pc_or_mac(pc, mac)


def hotkeys_here(text: str) -> str:
    """`text` (already translated) with the app's hotkeys and Ctrl's
    shortcuts as this OS writes them: on a Mac the hotkeys are
    Control+Command, "⌃⌘L", and Ctrl is Command, "⌘C", "⌘+wheel";
    on Linux the hotkeys are Ctrl+Alt+Shift (570); elsewhere as it is."""
    if platform() is Platform.LINUX:
        return _HOTKEY.sub(_linux_hotkey, text)
    if not on_a_mac():
        return text
    text = _HOTKEY.sub(r"⌃⌘\2", text)
    return _COMMAND.sub("⌘+", _COMMAND_KEY.sub("⌘", text))


def _linux_hotkey(found: re.Match[str]) -> str:
    """Linux's hotkey for one Windows' names: Shift beside Ctrl+Alt, in the
    text's own word for Ctrl."""
    ctrl, key = found[1], found[2]
    shift = "Umschalt" if ctrl == "Strg" else "Shift"
    return f"{ctrl}+Alt+{shift}+{key}"
