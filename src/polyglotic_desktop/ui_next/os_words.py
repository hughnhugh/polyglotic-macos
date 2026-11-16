"""The words of the OS the app runs on (polyglotic-hq 409): where a string
says PC or Windows, a Mac shows its own - "Everything the Mac plays",
macOS's System Settings - each translated as any string is (decision
0034). Both are written at the call, `pc_or_mac(_tr("..PC.."),
_tr("..Mac.."))`, so the extractor finds both and each language drafts
both; Windows' text is unchanged.

`ui` and `ui_next` each have this module (they don't import each other).
"""

import sys


def on_a_mac() -> bool:
    return sys.platform == "darwin"


def pc_or_mac(pc: str, mac: str) -> str:
    """`mac` on a Mac, else `pc` - both already translated."""
    return mac if on_a_mac() else pc
