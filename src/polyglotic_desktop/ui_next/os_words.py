"""The words of the OS the app runs on (polyglotic-hq 409): where a string
says PC or Windows, a Mac shows its own - "Everything the Mac plays",
macOS's System Settings - each translated as any string is (decision
0034). Both are written at the call, `pc_or_mac(_tr("..PC.."),
_tr("..Mac.."))`, so the extractor finds both and each language drafts
both; Windows' text is unchanged.

The app's hotkeys are named in the texts as Windows writes them
("Ctrl+Alt+L"; German "Strg+Alt+L"); `hotkeys_here` writes them as a Mac
does, "⌃⌘L" (polyglotic-hq 428): the symbols are the same in every
language, so no language drafts them again. Qt's Ctrl is Command on a Mac,
so a shortcut with Ctrl alone ("Ctrl+C", "Ctrl+wheel") is Command's there:
"⌘C", "⌘+wheel" (polyglotic-hq 451).

`ui` and `ui_next` each have this module (they don't import each other).
"""

import re
import sys

_HOTKEY = re.compile(r"\b(?:Ctrl|Strg)\+Alt\+([LPH])\b")
"""One of the app's hotkeys (`ui.app.DesktopApp.hotkeys`) as a translated
text names it on Windows."""
_COMMAND_KEY = re.compile(r"\b(?:Ctrl|Strg)\+(?=[A-Z0-9]\b)")
"""Ctrl with a key ("Ctrl+C"): a Mac's menus write Command's "⌘C"."""
_COMMAND = re.compile(r"\b(?:Ctrl|Strg)\+(?!Alt\+)")
"""Ctrl with anything else ("Ctrl+wheel"): "⌘+wheel" on a Mac. Not Ctrl+Alt
with a key: dictation's own key is named by `dictation_key.key_words`."""


def on_a_mac() -> bool:
    return sys.platform == "darwin"


def pc_or_mac(pc: str, mac: str) -> str:
    """`mac` on a Mac, else `pc` - both already translated."""
    return mac if on_a_mac() else pc


def hotkeys_here(text: str) -> str:
    """`text` (already translated) with the app's hotkeys and Ctrl's
    shortcuts as this OS writes them: on a Mac the hotkeys are
    Control+Command, "⌃⌘L", and Ctrl is Command, "⌘C", "⌘+wheel";
    elsewhere as it is."""
    if not on_a_mac():
        return text
    text = _HOTKEY.sub(r"⌃⌘\1", text)
    return _COMMAND.sub("⌘+", _COMMAND_KEY.sub("⌘", text))
