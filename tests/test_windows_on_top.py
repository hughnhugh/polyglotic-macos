"""Keeping the caption windows above a game that is itself always on top
(platform.windows.on_top; polyglotic-hq project 141): what counts as such a
game, putting windows at the top of Windows' always-on-top band in order,
and the foreground watch. No window is activated, and none is shown on the
user's screen: the ordering test shows its windows on a desktop of its own,
which Windows never displays."""

import ctypes
import os
import sys
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from ctypes import wintypes

import pytest

if sys.platform != "win32":
    pytest.skip("Windows only", allow_module_level=True)

from polyglotic_desktop.platform.windows.on_top import (
    ForegroundWatch,
    WindowsOnTop,
    is_game,
)

MONITOR = (0, 0, 2560, 1440)
ROOT = r"C:\Windows"
GAME = r"D:\Games\Some Game\game.exe"


def test_a_game_is_always_on_top_and_covers_its_monitor() -> None:
    assert is_game(True, MONITOR, MONITOR, GAME, ROOT)
    assert is_game(True, (-8, -8, 2568, 1448), MONITOR, GAME, ROOT)  # past the edges
    assert not is_game(False, MONITOR, MONITOR, GAME, ROOT)  # an ordinary window
    assert not is_game(True, (0, 0, 2560, 1392), MONITOR, GAME, ROOT)  # the work area
    assert not is_game(True, (200, 200, 900, 700), MONITOR, GAME, ROOT)  # a small one
    assert not is_game(True, MONITOR, MONITOR, None, ROOT)  # Windows won't say whose


def test_the_shell_is_never_a_game() -> None:
    """The Start menu, search, Task View and Alt+Tab stay above the captions."""
    for shell in (
        r"C:\Windows\explorer.exe",
        r"c:\windows\SystemApps\StartMenuExperienceHost\StartMenuExperienceHost.exe",
        r"C:\Windows\SystemApps\MicrosoftWindows.Client.CBS_cw5n1h2txyewy\SearchHost.exe",
    ):
        assert not is_game(True, MONITOR, MONITOR, shell, ROOT), shell
    assert is_game(True, MONITOR, MONITOR, r"C:\Windows\SystemAppsMore\x.exe", ROOT)


_user32 = ctypes.WinDLL("user32", use_last_error=True)
_user32.CreateWindowExW.argtypes = [
    wintypes.DWORD,
    wintypes.LPCWSTR,
    wintypes.LPCWSTR,
    wintypes.DWORD,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    wintypes.HWND,
    wintypes.HMENU,
    wintypes.HINSTANCE,
    wintypes.LPVOID,
]
_user32.CreateWindowExW.restype = wintypes.HWND
_user32.DestroyWindow.argtypes = [wintypes.HWND]
_user32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
_user32.GetWindow.restype = wintypes.HWND
_user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
_user32.GetWindowLongW.restype = ctypes.c_long
_user32.IsWindowVisible.argtypes = [wintypes.HWND]
_user32.GetForegroundWindow.restype = wintypes.HWND
_user32.GetActiveWindow.restype = wintypes.HWND
_user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
_user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
_user32.CreateDesktopW.argtypes = [
    wintypes.LPCWSTR,
    wintypes.LPCWSTR,
    wintypes.LPVOID,
    wintypes.DWORD,
    wintypes.DWORD,
    wintypes.LPVOID,
]
_user32.CreateDesktopW.restype = wintypes.HANDLE
_user32.SetThreadDesktop.argtypes = [wintypes.HANDLE]
_user32.CloseDesktop.argtypes = [wintypes.HANDLE]
WS_POPUP, GW_HWNDNEXT, GWL_EXSTYLE, WS_EX_TOPMOST = 0x80000000, 2, -20, 0x8
SW_SHOWNOACTIVATE, GENERIC_ALL = 4, 0x10000000


def _hidden_window() -> int:
    """A top-level window, not shown."""
    hwnd = _user32.CreateWindowExW(
        0, "STATIC", "146 test", WS_POPUP, 40, 30, 10, 10, None, None, None, None
    )
    assert hwnd
    return int(hwnd)


def _rect(hwnd: int) -> tuple[int, int, int, int]:
    rect = wintypes.RECT()
    assert _user32.GetWindowRect(hwnd, ctypes.byref(rect))
    return rect.left, rect.top, rect.right, rect.bottom


def _on_a_desktop_of_its_own(work: Callable[[], None]) -> None:
    """Runs `work` on a thread attached to a desktop made for it, which
    Windows never displays, so its windows can be shown as the caption
    windows are without reaching the user's screen. Hidden windows aren't
    enough: on the signed-in user's window station, Windows silently left
    the lower of two hidden windows out of the always-on-top band (every
    run in an agent's shell, 2026-11-08), while the CI runners' services
    took it (polyglotic-hq 197). The app only puts shown windows on top."""
    name = f"polyglotic-test-{os.getpid()}-{threading.get_ident()}"
    desktop = _user32.CreateDesktopW(name, None, None, 0, GENERIC_ALL, None)
    if not desktop:
        pytest.skip(
            f"Windows wouldn't make a desktop for the test "
            f"(error {ctypes.get_last_error()})"
        )

    def run() -> None:
        if not _user32.SetThreadDesktop(desktop):
            raise ctypes.WinError(ctypes.get_last_error())
        work()

    try:  # a thread of its own: one that owns windows can't change desktop
        with ThreadPoolExecutor(1, thread_name_prefix="test desktop") as pool:
            pool.submit(run).result(timeout=30)
    finally:
        _user32.CloseDesktop(desktop)


def _below(upper: int, lower: int) -> bool:
    """Whether `lower` comes after `upper` in Windows' z-order."""
    hwnd = _user32.GetWindow(upper, GW_HWNDNEXT)
    while hwnd:
        if int(hwnd) == lower:
            return True
        hwnd = _user32.GetWindow(hwnd, GW_HWNDNEXT)
    return False


def test_windows_go_on_top_in_order_without_being_activated_or_moved() -> None:
    foreground = _user32.GetForegroundWindow()

    def work() -> None:
        first, second = _hidden_window(), _hidden_window()
        try:
            for hwnd in (first, second):
                _user32.ShowWindow(hwnd, SW_SHOWNOACTIVATE)
            active, rects = _user32.GetActiveWindow(), [_rect(first), _rect(second)]
            on_top = WindowsOnTop()
            on_top.put_on_top([first, second])  # bottom first
            for hwnd in (first, second):
                assert _user32.GetWindowLongW(hwnd, GWL_EXSTYLE) & WS_EX_TOPMOST
            assert _below(second, first)
            on_top.put_on_top([second, first])
            assert _below(first, second)
            assert _user32.GetActiveWindow() == active
            assert [_rect(first), _rect(second)] == rects
        finally:
            _user32.DestroyWindow(first)
            _user32.DestroyWindow(second)

    _on_a_desktop_of_its_own(work)
    assert _user32.GetForegroundWindow() == foreground


def test_a_hidden_window_put_on_top_stays_hidden() -> None:
    hwnd = _hidden_window()
    try:
        WindowsOnTop().put_on_top([hwnd])
        assert not _user32.IsWindowVisible(hwnd)
    finally:
        _user32.DestroyWindow(hwnd)


def test_the_window_in_front_is_read_without_failing() -> None:
    assert isinstance(WindowsOnTop().game_in_front(), bool)


def test_the_foreground_watch_starts_calls_and_stops() -> None:
    called = threading.Event()
    watch = ForegroundWatch(called.set)
    assert watch.start()
    try:
        with pytest.raises(RuntimeError):
            watch.start()
        watch._event(0, 3, 0, 0, 0, 0, 0)  # as Windows calls it
        assert called.is_set()
    finally:
        watch.stop()
    watch.stop()  # twice: nothing more


def test_a_failing_call_doesnt_end_the_watch() -> None:
    def fails() -> None:
        raise RuntimeError("boom")

    watch = ForegroundWatch(fails)
    watch._event(0, 3, 0, 0, 0, 0, 0)  # logged, not raised
