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
  other always-on-top panels showing (the dictation sign, a settings
  popover) set so too, where they are.
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

Nothing here captures the screen or reads what is on it: only the app's
own windows are asked and set.
"""

import ctypes
import ctypes.util
import logging
from collections.abc import Callable, Sequence
from functools import cache

from polyglotic_desktop.platform.macos import objc

log = logging.getLogger(__name__)

LEVEL = 1000
"""`NSScreenSaverWindowLevel`: above full-screen apps (Apple's DTS; the
floating (3), status bar (25) and modal panel (8) levels stay below)."""
QT_ON_TOP_LEVEL = 8
"""`NSModalPanelWindowLevel`: where Qt puts an always-on-top window - the
dictation sign and a settings popover too, which the interface doesn't
hand to `put_on_top`."""

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


def above_everything(window: int) -> bool:
    """Sets an `NSWindow` as `put_on_top` wants it; True if anything
    changed. Each is asked first, and set only if it differs."""
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
    if panel and not style & NONACTIVATING_PANEL:  # a panel's alone
        objc.send(
            window,
            "setStyleMask:",
            style | NONACTIVATING_PANEL,
            restype=None,
            argtypes=[ctypes.c_ulong],
        )
        changed = True
    if _number(window, "level") != LEVEL:
        objc.send(window, "setLevel:", LEVEL, restype=None, argtypes=[ctypes.c_long])
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

    def game_in_front(self) -> bool:
        """Always: Qt sets a window's level again whenever its flags change,
        so the windows are set whenever the interface asks."""
        return True

    def put_on_top(self, windows: Sequence[int]) -> None:
        """`windows` (native handles: `NSView`s, bottom first) above
        everything, on every Space, in that order - none activated, nothing
        moved or resized."""
        with objc.pool():
            for view in windows:
                window = window_of(view)
                if not window:
                    continue
                above_everything(window)
                objc.send(window, "orderFrontRegardless", restype=None)
            for window in left_at_qts_level():
                above_everything(window)


def left_at_qts_level() -> list[int]:
    """The app's other always-on-top panels showing at Qt's level (the
    dictation sign, a settings popover)."""
    panel = objc.cls("NSPanel")
    return [
        window
        for window in objc.items(objc.send(_app(), "windows"))
        if _flag(window, "isVisible")
        and _number(window, "level") == QT_ON_TOP_LEVEL
        and objc.send(
            window,
            "isKindOfClass:",
            panel,
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
