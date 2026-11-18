"""The caption windows over full-screen apps and on every Space, on a Mac
(polyglotic-hq 429, decision 0201) - `platform/windows/on_top.py`'s
counterpart.

Qt's always-on-top flag puts a window at the modal-panel level (8), which
stays below another app's full-screen Space, and on one Space only
(polyglotic-hq 171; QTBUG-39212). Apple's way (its Developer Technical
Support, 2026-05, tested on macOS 26 with Safari, QuickTime and full-screen
YouTube): a non-activating panel at the screen-saver level, joining every
Space and full-screen apps' as an auxiliary, in an app that is an
*accessory* (no Dock icon). GitHub's Mac showed the last part is about the
window's start (polyglotic-hq 429's run 2, 2026-11-17): a window first
shown while the app was in the Dock never joins a full-screen app's Space,
even once the app is an accessory; one first shown while the app is an
accessory does. So the app is an accessory for the whole of its run -
`LSUIElement` in the packed app's Info.plist, and `MacOnTop` made (before
the interface makes any caption window) when run from source.

- `MacOnTop.put_on_top`: each window - Qt's tool windows are panels
  (`QNSPanel`): the caption windows, the joined window, the lookup card -
  set so (`above_everything`), never hidden when the app isn't active,
  then ordered to the front without activating the app; and the app's
  other always-on-top panels showing - a caption window's settings
  popover and its language chip's, a strip's tip, the copy tip, the
  dictation sign, a menu - set so one level higher (`ABOVE`) and ordered
  to the front too: above the caption windows they came from
  (`lifted`). Qt makes a popover at its caption window's own level, and
  the caption windows are ordered to the front at every caption, so at the
  same level a popover went behind its window within a second of opening
  (the user, 2026-11-18, on 0.1.8: "caption settings modal is behind
  overlay / caption window"; polyglotic-hq 515).
- `MacOnTop.game_in_front` is always True: Qt puts a window back at its
  own level whenever its flags change (locking hides and shows it), so
  the interface's `keep_on_top` sets the windows again each time it asks -
  when another app comes to the front, a window is shown or hidden, and a
  caption comes (at most once a second). A window already set is only
  ordered front.
- `FrontWatch` (the `ForegroundWatch`): macOS's notifications - another
  app active, the Space changed, one of the app's own windows shown or
  hidden - each call `changed`, on the interface's thread (macOS posts
  them there).

Every window `put_on_top` sets is also never resized by macOS itself
(`RESIZABLE`, polyglotic-hq 515): the app's own edges and corners resize a
caption window, as on Windows.

Nothing here captures the screen or reads what is on it: only the app's
own windows are asked and set.
"""

import ctypes
import ctypes.util
import logging
from collections.abc import Callable, Collection, Sequence
from dataclasses import dataclass
from functools import cache

from polyglotic_desktop.platform.macos import objc

log = logging.getLogger(__name__)

LEVEL = 1000
"""`NSScreenSaverWindowLevel`: above full-screen apps (Apple's DTS; the
floating (3), status bar (25) and modal panel (8) levels stay below)."""
QT_ON_TOP_LEVEL = 8
"""`NSModalPanelWindowLevel`: where Qt puts an always-on-top window - the
dictation sign, and a settings popover made while its caption window was
still at Qt's level - which the interface doesn't hand to `put_on_top`."""
POP_UP_MENU_LEVEL = 101
"""`NSPopUpMenuWindowLevel`: where Qt puts a pop-up (a menu)."""
ABOVE = LEVEL + 1
"""The app's other always-on-top panels showing (`lifted`): one level above
the caption windows, so ordering those to the front never covers them."""
LIFTED_FROM = frozenset({QT_ON_TOP_LEVEL, POP_UP_MENU_LEVEL, LEVEL, ABOVE})
"""The levels an always-on-top panel of Qt's is at: Qt's own, a pop-up's,
the screen saver's (a tool tip's, and a window's made with a caption window
as its parent: Qt starts a window at least at its parent's level) - or
already lifted. An ordinary window or a dialog (0) and a plain tool window
(the floating level, 3) are left where they are, as on Windows."""

CAN_JOIN_ALL_SPACES = 1 << 0
MOVE_TO_ACTIVE_SPACE = 1 << 1
STATIONARY = 1 << 4
"""Left in place by Mission Control, as the desktop is."""
PARTICIPATES_IN_CYCLE = 1 << 5
IGNORES_CYCLE = 1 << 6
"""Not one of the windows Command-` steps through."""
FULL_SCREEN_PRIMARY = 1 << 7
FULL_SCREEN_AUXILIARY = 1 << 8
"""Allowed on another app's full-screen Space."""
FULL_SCREEN_NONE = 1 << 9
CAN_JOIN_ALL_APPLICATIONS = 1 << 18
"""On every app's Space, full-screen ones included (macOS 13)."""
NONACTIVATING_PANEL = 1 << 7
"""`NSWindowStyleMaskNonactivatingPanel`: a click on it doesn't activate
the app (which would take a full-screen app out of its Space)."""
RESIZABLE = 1 << 3
"""`NSWindowStyleMaskResizable`, which Qt gives every window that isn't of
a fixed size - a frameless one too. macOS then resized a caption window
itself from a press a few pixels inside its edge, before the app heard of
it: past the app's least size (to 1 px wide, GitHub's Mac, polyglotic-hq
515's run 1), past the screen's edge, and never remembered - at the next
start the window came back at its old size. Cleared, every press reaches
the app's own edges and corners (`placement.edges_at`), as on Windows."""


def style_mask(current: int, panel: bool) -> int:
    """A window's style as `put_on_top` wants it: a panel non-activating,
    and not resizable by macOS (the app resizes it)."""
    wanted = current & ~RESIZABLE
    return wanted | NONACTIVATING_PANEL if panel else wanted


ACCESSORY = 1
"""`NSApplicationActivationPolicyAccessory`: no Dock icon, no menu bar of
its own (the menu-bar icon stays), and its windows allowed over a
full-screen app's Space."""

WATCHED = (
    ("workspace", "NSWorkspaceDidActivateApplicationNotification"),
    ("workspace", "NSWorkspaceActiveSpaceDidChangeNotification"),
    ("app", "NSWindowDidChangeOcclusionStateNotification"),
)
"""What `FrontWatch` hears: another app active, another Space, and one of
the app's own windows shown, hidden or covered."""


def collection_behaviour(current: int) -> int:
    """A window's collection behaviour as the caption windows want it: on
    every Space and every app's (a full-screen one's as an auxiliary),
    left in place by Mission Control, out of Command-`'s cycle - and not
    what conflicts with those (macOS refuses a window that both joins
    every Space and moves to the active one)."""
    cleared = current & ~(
        MOVE_TO_ACTIVE_SPACE
        | FULL_SCREEN_PRIMARY
        | FULL_SCREEN_NONE
        | PARTICIPATES_IN_CYCLE
    )
    return (
        cleared
        | CAN_JOIN_ALL_SPACES
        | CAN_JOIN_ALL_APPLICATIONS
        | FULL_SCREEN_AUXILIARY
        | STATIONARY
        | IGNORES_CYCLE
    )


@cache
def _appkit() -> ctypes.CDLL:
    path = ctypes.util.find_library("AppKit")
    if path is None:
        raise OSError("macOS's AppKit framework isn't here")
    return ctypes.CDLL(path)


def _constant(name: str) -> int:
    """One of AppKit's named strings (a notification's name)."""
    found = ctypes.c_void_p.in_dll(_appkit(), name).value
    if not found:
        raise OSError(f"macOS: {name} isn't set")
    return int(found)


def _flag(receiver: int, selector: str) -> bool:
    return bool(objc.send(receiver, selector, restype=ctypes.c_bool))


def _number(receiver: int, selector: str) -> int:
    return int(objc.send(receiver, selector, restype=ctypes.c_long))


def _app() -> int:
    _appkit()
    return int(objc.send(objc.cls("NSApplication"), "sharedApplication") or 0)


def above_everything(window: int, level: int = LEVEL) -> bool:
    """Sets an `NSWindow` as `put_on_top` wants it, at `level`; True if
    anything changed. Each is asked first, and set only if it differs."""
    changed = False
    behaviour = _number(window, "collectionBehavior")
    wanted = collection_behaviour(behaviour)
    if wanted != behaviour:
        objc.send(
            window,
            "setCollectionBehavior:",
            wanted,
            restype=None,
            argtypes=[ctypes.c_ulong],
        )
        changed = True
    panel = objc.send(
        window,
        "isKindOfClass:",
        objc.cls("NSPanel"),
        restype=ctypes.c_bool,
        argtypes=[ctypes.c_void_p],
    )
    style = _number(window, "styleMask")
    wanted_style = style_mask(style, bool(panel))
    if wanted_style != style:
        objc.send(
            window,
            "setStyleMask:",
            wanted_style,
            restype=None,
            argtypes=[ctypes.c_ulong],
        )
        changed = True
    if _number(window, "level") != level:
        objc.send(window, "setLevel:", level, restype=None, argtypes=[ctypes.c_long])
        changed = True
    if _flag(window, "hidesOnDeactivate"):  # Qt's tool windows hide otherwise
        objc.send(
            window,
            "setHidesOnDeactivate:",
            False,
            restype=None,
            argtypes=[ctypes.c_bool],
        )
        changed = True
    return changed


def window_of(view: int) -> int:
    """The `NSWindow` of a Qt window's native handle (an `NSView`); 0 if it
    has none yet."""
    return int(objc.send(view, "window") or 0)


def be_an_accessory() -> bool:
    """The app an accessory from now on (if it isn't already: the packed
    app is, from its Info.plist); True if it is."""
    app = _app()
    if _number(app, "activationPolicy") != ACCESSORY:
        objc.send(
            app,
            "setActivationPolicy:",
            ACCESSORY,
            restype=ctypes.c_bool,
            argtypes=[ctypes.c_long],
        )
    return _number(app, "activationPolicy") == ACCESSORY


class MacOnTop:
    """The caption windows above everything on a Mac (the interface's
    `OnTop`). Made once, before the interface makes any caption window: the
    app is an accessory from then on (`be_an_accessory`)."""

    def __init__(self, accessory: Callable[[], bool] = be_an_accessory) -> None:
        if not accessory():
            log.warning(
                "macOS kept the app in the Dock: captions stay below full-screen apps"
            )
        self._handed: set[int] = set()
        """The window numbers `put_on_top` has been handed: the caption
        windows, the joined window, the lookup card - numbers, which the
        window server hands out afresh, not `NSWindow`s, whose memory a
        later window may reuse. Every other panel showing is `lifted`."""

    def game_in_front(self) -> bool:
        """Always: Qt sets a window's level again whenever its flags change,
        so the windows are set whenever the interface asks."""
        return True

    def put_on_top(self, windows: Sequence[int]) -> None:
        """`windows` (native handles: `NSView`s, bottom first) above
        everything, on every Space, in that order - none activated, nothing
        moved or resized; then the app's other always-on-top panels showing
        above them (`lifted`)."""
        with objc.pool():
            for view in windows:
                window = window_of(view)
                if not window:
                    continue
                self._handed.add(_number(window, "windowNumber"))
                above_everything(window)
                objc.send(window, "orderFrontRegardless", restype=None)
            for window in lifted(panels_showing(), self._handed):
                above_everything(window, ABOVE)
                objc.send(window, "orderFrontRegardless", restype=None)


@dataclass(frozen=True)
class Panel:
    """One of the app's panels showing: its `NSWindow`, number and level."""

    window: int
    number: int
    level: int


def lifted(showing: Sequence[Panel], handed: Collection[int]) -> list[int]:
    """The panels showing that go above the caption windows: every one at an
    always-on-top level of Qt's (`LIFTED_FROM`) that isn't one `put_on_top`
    was handed (`handed`: window numbers) - a settings popover, a strip's
    tip, the dictation sign, a menu. A dialog or a plain tool window stays
    where it is."""
    return [
        panel.window
        for panel in showing
        if panel.number not in handed and panel.level in LIFTED_FROM
    ]


def panels_showing() -> list[Panel]:
    """The app's panels (Qt's tool windows, pop-ups and tips) showing now."""
    kind = objc.cls("NSPanel")
    return [
        Panel(window, _number(window, "windowNumber"), _number(window, "level"))
        for window in objc.items(objc.send(_app(), "windows"))
        if _flag(window, "isVisible")
        and objc.send(
            window,
            "isKindOfClass:",
            kind,
            restype=ctypes.c_bool,
            argtypes=[ctypes.c_void_p],
        )
    ]


class FrontWatch:
    """Calls `changed` - on the interface's thread, where macOS posts them -
    whenever another app comes to the front, the Space changes, or one of
    the app's own windows is shown or hidden."""

    def __init__(self, changed: Callable[[], None]) -> None:
        self._changed = changed
        self._block: objc.Block | None = None
        self._observers: list[tuple[int, int]] = []
        """(notification centre, the observer it gave) for each watched."""
        self.watching = False

    def start(self) -> bool:
        """Starts watching; False if macOS wouldn't say."""
        if self._block is not None:
            raise RuntimeError("already started")
        self._block = objc.Block(self._heard)
        try:
            _appkit()
            with objc.pool():
                workspace = objc.send(
                    objc.send(objc.cls("NSWorkspace"), "sharedWorkspace"),
                    "notificationCenter",
                )
                app = objc.send(objc.cls("NSNotificationCenter"), "defaultCenter")
                centres = {"workspace": int(workspace or 0), "app": int(app or 0)}
                for centre, name in WATCHED:
                    observer = objc.send(
                        centres[centre],
                        "addObserverForName:object:queue:usingBlock:",
                        _constant(name),
                        None,
                        None,
                        self._block.address,
                        argtypes=[ctypes.c_void_p] * 4,
                    )
                    if observer:  # kept by the centre until removed
                        objc.send(int(observer), "retain")
                        self._observers.append((centres[centre], int(observer)))
        except OSError:
            log.exception("macOS wouldn't say when the front app changes")
        self.watching = len(self._observers) == len(WATCHED)
        return self.watching

    def stop(self) -> None:
        with objc.pool():
            for centre, observer in self._observers:
                objc.send(
                    centre,
                    "removeObserver:",
                    observer,
                    restype=None,
                    argtypes=[ctypes.c_void_p],
                )
                objc.send(observer, "release", restype=None)
        self._observers = []
        self.watching = False

    def _heard(self, _notification: int) -> None:
        try:
            self._changed()
        except Exception:  # never out into macOS's call
            log.exception("the front watch's call failed")
