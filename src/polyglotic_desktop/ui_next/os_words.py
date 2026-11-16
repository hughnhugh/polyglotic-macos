"""The words of the OS the app runs on (polyglotic-hq 409): where a string
says PC or Windows, a Mac shows its own - "Everything the Mac plays",
macOS's System Settings - each translated as any string is (decision
0034). Both are written at the call, `pc_or_mac(_tr("..PC.."),
_tr("..Mac.."))`, so the extractor finds both and each language drafts
both; Windows' text is unchanged.

The app's hotkeys are named in the texts as Windows writes them
("Ctrl+Alt+L"; German "Strg+Alt+L"); `hotkeys_here` writes them as a Mac
does, "⌃⌘L" (polyglotic-hq 428): the symbols are the same in every
language, so no language drafts them again.

`ui` and `ui_next` each have this module (they don't import each other).
"""

import re
import sys

_HOTKEY = re.compile(r"\b(?:Ctrl|Strg)\+Alt\+([LPH])\b")
"""One of the app's hotkeys (`ui.app.DesktopApp.hotkeys`) as a translated
text names it on Windows."""


def on_a_mac() -> bool:
    return sys.platform == "darwin"


def pc_or_mac(pc: str, mac: str) -> str:
    """`mac` on a Mac, else `pc` - both already translated."""
    return mac if on_a_mac() else pc


def hotkeys_here(text: str) -> str:
    """`text` (already translated) with the app's hotkeys as this OS writes
    them: on a Mac Control+Command, "⌃⌘L"; elsewhere as it is."""
    return _HOTKEY.sub(r"⌃⌘\1", text) if on_a_mac() else text
