"""The caption windows above everything on Linux (polyglotic-hq 546, 547,
550) - `platform/windows/on_top.py`'s and the Mac's counterpart.

The app runs as an X11 program everywhere (XWayland on GNOME's and KDE's
Wayland sessions), and every caption window, popover and card is an
**override-redirect** window (`Qt.X11BypassWindowManagerHint`, set by the
interface's own window flags on Linux: `ui_next/above_all.py`). 547's
runs found it the only arrangement that never failed - first shown, after
a lock or an unlock, translucent, clicks passing through - on GNOME 46
and 51 and KDE 6.8, above a focused full-screen window, where Qt's
always-on-top flag alone was hidden by KWin under every focused full-screen
window (0/52) and lost by GNOME after a lock (21 times in 55), with
`raise_()` never bringing it back.

The window manager then doesn't manage these windows at all: no focus, and
no order among them but the one they're raised in. So, as the Mac's
`lifted` does:
- `LinuxOnTop.put_on_top` raises the windows it's given, bottom first -
  the caption windows, then the lookup card - and then the app's other
  override-redirect windows showing (a caption window's settings popover,
  its language chip's, a strip's tip, a menu), so a caption window shown
  again never covers the popover it opened. Raising doesn't activate.
- `LinuxOnTop.game_in_front` is always True: the interface's
  `keep_on_top` then puts them in order whenever it asks - a window shown
  or hidden, and at most once a second with captions.

Nothing here captures the screen or reads what is on it: only the app's
own windows are asked and raised.
"""

from collections.abc import Mapping, Sequence

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication, QWindow

ABOVE = (
    Qt.WindowType.X11BypassWindowManagerHint,
    Qt.WindowType.Popup,
    Qt.WindowType.ToolTip,
)
"""What makes one of the app's windows one the window manager doesn't
order: the interface's own flag on Linux, and Qt's pop-ups and tips."""


def _above(window: QWindow) -> bool:
    flags = window.flags()
    kind = flags & Qt.WindowType.WindowType_Mask
    return bool(flags & ABOVE[0]) or kind in (ABOVE[1], ABOVE[2])


def raising_order(given: Sequence[int], shown: Mapping[int, bool]) -> list[int]:
    """The windows to raise, bottom first: those `given` that show, then the
    app's other windows showing that the window manager doesn't order
    (`shown`: each showing window's number, and whether it's such a one),
    in the order Qt lists them."""
    lifted = [
        number for number, above in shown.items() if above and number not in given
    ]
    return [number for number in given if number in shown] + lifted


class LinuxOnTop:
    """`OnTop` for override-redirect windows: their order kept by hand."""

    def game_in_front(self) -> bool:
        return True

    def put_on_top(self, windows: Sequence[int]) -> None:
        shown = {
            int(window.winId()): window
            for window in QGuiApplication.topLevelWindows()
            if window.isVisible()
        }
        above = {number: _above(window) for number, window in shown.items()}
        for number in raising_order([int(w) for w in windows], above):
            shown[number].raise_()
