"""Keeping the caption windows above a game that is itself always on top.

Windows keeps always-on-top windows in a band above the rest, ordered
among themselves by which came up last. A borderless full-screen game that
is itself always on top goes above the caption windows the moment it is
clicked, and stays there (polyglotic-hq project 141). The caption windows
never take the focus, so they can't come back by being activated; they are
put back at the top of the band instead, without activating them, so the
game keeps the keyboard (`WindowsOnTop.put_on_top`) - when it matters:

- `WindowsOnTop.game_in_front`: the foreground window is another app's
  always-on-top window covering its whole monitor (a borderless
  full-screen game), and not the shell's: the Start menu, search, Task
  View, Alt+Tab and the like come and go above everything, and stay above
  the captions;
- `ForegroundWatch`: Windows says when the foreground window changes
  (`SetWinEventHook`, out of context: nothing is injected into other apps,
  and nothing is read but that it changed), on a thread of its own with
  its own message loop, as the hotkeys are; `main` hands the call to the
  interface's thread.

Nothing here captures the screen or logs what is on it.
"""

import ctypes
import logging
import os
import threading
from collections.abc import Callable, Sequence
from ctypes import wintypes
from pathlib import PureWindowsPath

log = logging.getLogger(__name__)

Box = tuple[int, int, int, int]
"""A rectangle as Windows gives it: left, top, right, bottom."""

HWND_TOPMOST = wintypes.HWND(-1)
SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE = 0x0001, 0x0002, 0x0010
GWL_EXSTYLE, WS_EX_TOPMOST = -20, 0x00000008
MONITOR_DEFAULTTONEAREST = 2
EVENT_SYSTEM_FOREGROUND = 0x0003
WINEVENT_OUTOFCONTEXT, WINEVENT_SKIPOWNPROCESS = 0x0000, 0x0002
WM_QUIT = 0x0012
_PM_NOREMOVE = 0x0000
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


class _MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", wintypes.RECT),
        ("rcWork", wintypes.RECT),
        ("dwFlags", wintypes.DWORD),
    ]


_WinEventProc = ctypes.WINFUNCTYPE(
    None,
    wintypes.HANDLE,
    wintypes.DWORD,
    wintypes.HWND,
    wintypes.LONG,
    wintypes.LONG,
    wintypes.DWORD,
    wintypes.DWORD,
)

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_user32.SetWindowPos.argtypes = [
    wintypes.HWND,
    wintypes.HWND,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    wintypes.UINT,
]
_user32.SetWindowPos.restype = wintypes.BOOL
_user32.GetForegroundWindow.restype = wintypes.HWND
_user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
_user32.GetWindowLongW.restype = ctypes.c_long
_user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
_user32.GetWindowRect.restype = wintypes.BOOL
_user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
_user32.MonitorFromWindow.restype = wintypes.HMONITOR
_user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(_MONITORINFO)]
_user32.GetMonitorInfoW.restype = wintypes.BOOL
_user32.GetWindowThreadProcessId.argtypes = [
    wintypes.HWND,
    ctypes.POINTER(wintypes.DWORD),
]
_user32.GetWindowThreadProcessId.restype = wintypes.DWORD
_user32.SetWinEventHook.argtypes = [
    wintypes.DWORD,
    wintypes.DWORD,
    wintypes.HMODULE,
    _WinEventProc,
    wintypes.DWORD,
    wintypes.DWORD,
    wintypes.DWORD,
]
_user32.SetWinEventHook.restype = wintypes.HANDLE
_user32.UnhookWinEvent.argtypes = [wintypes.HANDLE]
_user32.UnhookWinEvent.restype = wintypes.BOOL
_user32.GetMessageW.argtypes = [
    ctypes.POINTER(wintypes.MSG),
    wintypes.HWND,
    wintypes.UINT,
    wintypes.UINT,
]
_user32.GetMessageW.restype = wintypes.BOOL
_user32.PeekMessageW.argtypes = [
    ctypes.POINTER(wintypes.MSG),
    wintypes.HWND,
    wintypes.UINT,
    wintypes.UINT,
    wintypes.UINT,
]
_user32.PeekMessageW.restype = wintypes.BOOL
_user32.PostThreadMessageW.argtypes = [
    wintypes.DWORD,
    wintypes.UINT,
    wintypes.WPARAM,
    wintypes.LPARAM,
]
_user32.PostThreadMessageW.restype = wintypes.BOOL
_kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
_kernel32.OpenProcess.restype = wintypes.HANDLE
_kernel32.QueryFullProcessImageNameW.argtypes = [
    wintypes.HANDLE,
    wintypes.DWORD,
    wintypes.LPWSTR,
    ctypes.POINTER(wintypes.DWORD),
]
_kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
_kernel32.CloseHandle.argtypes = [wintypes.HANDLE]


def is_game(
    topmost: bool, window: Box, monitor: Box, path: str | None, system_root: str
) -> bool:
    """Whether a foreground window is a game the captions should stay above:
    always on top, covering the whole of its `monitor`, and not the shell's
    (Explorer, or Windows' own apps under `system_root`'s SystemApps: Start,
    search, the notification centre). `path`: its program's; None when
    Windows won't say (a process of another user, or gone) - not counted
    as a game."""
    if not topmost or path is None:
        return False
    left, top, right, bottom = window
    m_left, m_top, m_right, m_bottom = monitor
    if left > m_left or top > m_top or right < m_right or bottom < m_bottom:
        return False
    program = PureWindowsPath(path)  # compared without regard to case
    if program.name.lower() == "explorer.exe":
        return False
    return not program.is_relative_to(PureWindowsPath(system_root) / "SystemApps")


def _box(rect: wintypes.RECT) -> Box:
    return (rect.left, rect.top, rect.right, rect.bottom)


def _program(hwnd: int) -> str | None:
    pid = wintypes.DWORD()
    _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if not pid.value or pid.value == os.getpid():
        return None
    handle = _kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
    if not handle:
        return None
    try:
        size = wintypes.DWORD(1024)
        buffer = ctypes.create_unicode_buffer(size.value)
        ok = _kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size))
        return buffer.value if ok else None
    finally:
        _kernel32.CloseHandle(handle)


class WindowsOnTop:
    """Windows' always-on-top band, for the caption windows (the interface's
    `OnTop`)."""

    def __init__(self) -> None:
        self._system_root = os.environ.get("SYSTEMROOT", r"C:\Windows")

    def game_in_front(self) -> bool:
        """Whether the foreground window is another app's always-on-top
        window covering its monitor, not the shell's (`is_game`)."""
        hwnd = _user32.GetForegroundWindow()
        if not hwnd:
            return False
        topmost = bool(_user32.GetWindowLongW(hwnd, GWL_EXSTYLE) & WS_EX_TOPMOST)
        if not topmost:
            return False  # most of the time: nothing more to ask
        rect = wintypes.RECT()
        info = _MONITORINFO()
        info.cbSize = ctypes.sizeof(info)
        monitor = _user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST)
        if not (
            _user32.GetWindowRect(hwnd, ctypes.byref(rect))
            and _user32.GetMonitorInfoW(monitor, ctypes.byref(info))
        ):
            return False
        return is_game(
            topmost,
            _box(rect),
            _box(info.rcMonitor),
            _program(hwnd),
            self._system_root,
        )

    def put_on_top(self, windows: Sequence[int]) -> None:
        """`windows` (native handles, bottom first) at the top of the
        always-on-top band, in that order - none activated, nothing moved
        or resized. A window's own windows (a caption window's settings
        popover) come with it."""
        for hwnd in windows:
            _user32.SetWindowPos(
                hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE
            )


class ForegroundWatch:
    """Calls `changed` - on its own thread - whenever another app's window
    comes to the foreground."""

    def __init__(self, changed: Callable[[], None]) -> None:
        self._changed = changed
        self._thread: threading.Thread | None = None
        self._thread_id = 0
        self._ready = threading.Event()
        self.watching = False
        """Whether Windows took the hook (it says so at `start`)."""

    def start(self) -> bool:
        """Starts watching; False if Windows wouldn't say."""
        if self._thread is not None:
            raise RuntimeError("already started")
        self._thread = threading.Thread(
            target=self._run, name="foreground", daemon=True
        )
        self._thread.start()
        self._ready.wait()
        return self.watching

    def stop(self) -> None:
        thread = self._thread
        if thread is None:
            return
        _user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
        thread.join(timeout=5)
        self._thread = None

    def _event(
        self,
        hook: int,
        event: int,
        hwnd: int,
        object_id: int,
        child_id: int,
        thread_id: int,
        time_ms: int,
    ) -> None:
        try:
            self._changed()
        except Exception:  # a failing call must not end the watch
            log.exception("the foreground watch's call failed")

    def _run(self) -> None:
        msg = wintypes.MSG()
        # the thread's message queue exists from its first message call:
        # before it, a stop's WM_QUIT would be lost
        _user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, _PM_NOREMOVE)
        self._thread_id = threading.get_native_id()
        proc = _WinEventProc(self._event)  # kept alive while the hook is
        hook = _user32.SetWinEventHook(
            EVENT_SYSTEM_FOREGROUND,
            EVENT_SYSTEM_FOREGROUND,
            None,
            proc,
            0,
            0,
            WINEVENT_OUTOFCONTEXT | WINEVENT_SKIPOWNPROCESS,
        )
        self.watching = bool(hook)
        if not hook:
            log.warning("Windows didn't take the foreground watch")
        self._ready.set()
        if not hook:
            return
        try:
            while _user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                pass  # out-of-context events arrive while this thread waits here
        finally:
            _user32.UnhookWinEvent(hook)
