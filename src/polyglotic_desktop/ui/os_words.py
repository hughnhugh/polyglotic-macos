"""The words of the OS the app runs on (polyglotic-hq 409): where a string
says PC or Windows, a Mac shows its own - "Everything the Mac plays",
macOS's System Settings - each translated as any string is (decision
0034). Both are written at the call, `pc_or_mac(_tr("..PC.."),
_tr("..Mac.."))`, so the extractor finds both and each language drafts
both; Windows' text is unchanged. Where the PC's words name Windows itself
- Task Manager, the tray, Windows' Settings - Linux gets a third set,
`pc_mac_or_linux(...)` (polyglotic-hq 571).

`ui` and `ui_next` each have this module (they don't import each other).
"""

import sys

from polyglotic_desktop.core.listening.hotkeys import Platform


def on_a_mac() -> bool:
    return sys.platform == "darwin"


def platform() -> Platform:
    """The platform whose keys the app's own hotkeys follow (polyglotic-hq
    567): the one place each interface tells core which OS it is - Linux's
    own since 570."""
    if on_a_mac():
        return Platform.MAC
    return Platform.LINUX if sys.platform.startswith("linux") else Platform.WINDOWS


def pc_or_mac(pc: str, mac: str) -> str:
    """`mac` on a Mac, else `pc` - both already translated."""
    return mac if on_a_mac() else pc


def on_linux() -> bool:
    """Linux (polyglotic-hq 550): the PC's words, but where a string names
    Windows itself - each such string Linux shows gets its own words."""
    return sys.platform.startswith("linux")


def pc_mac_or_linux(pc: str, mac: str, linux: str) -> str:
    """`linux` on Linux, `mac` on a Mac, else `pc` - all already translated
    (polyglotic-hq 571): for the strings whose PC words name Windows."""
    if on_linux():
        return linux
    return pc_or_mac(pc, mac)
