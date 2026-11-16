r"""A stand-in for Windows' taskbar on a private desktop, for tests only
(polyglotic-hq 215; `tools/private_desktop.py`): the tray icon, its menu
and Quit from the tray, checked without the user's screen.

A desktop made with `CreateDesktop` has no taskbar, so an app's tray icon
has nowhere to go there (205). An app's `Shell_NotifyIcon` finds the
taskbar as a window of class `Shell_TrayWnd` on its own desktop and sends
it the icon as `WM_COPYDATA`. This makes a window of that class on the
private desktop, keeps what arrives (`icons`, `messages`), and sends an
icon what Windows' taskbar sends it when it's clicked (`click`).

**How sure:** the layout of what `Shell_NotifyIcon` sends isn't documented
by Microsoft. This one is the layout replacement taskbars rely on: a
signature (0x34753423), the `NIM_` message, then `NOTIFYICONDATAW` with
32-bit handles; `COPYDATASTRUCT.dwData` 1 for an icon, 3 for where an
icon is (`Shell_NotifyIconGetRect`). The tests check it against what the
app sent (its tooltip, its window, its picture, its clicks' message) and
where Qt says the icon is, so a Windows that changed it fails them
rather than passing wrongly. The answer to where an icon is (its size,
then its top left) was found by trying (`_icon_rect`).

What it can't stand in for: Windows' own drawing of the icon, the
overflow area, the icon's tooltip and balloon as Windows shows them, the
taskbar's light or dark, and the taskbar's own space: it never changes
the work area (`SPI_SETWORKAREA`, the user's), so a menu over the
taskbar can't be told from one beside it.

    with PrivateDesktop() as desktop, StandInTaskbar(desktop) as taskbar:
        ... start the app on `desktop` ...
        (icon,) = taskbar.icons()
        taskbar.click(icon, "context")  # a right click: the tray's menu
"""

from __future__ import annotations

import ctypes
import struct
import sys
import threading
from ctypes import wintypes
from dataclasses import dataclass, replace
from typing import Literal, Self

if sys.platform != "win32":
    raise ImportError("tools.stand_in_taskbar needs Windows: desktops are Windows'")

from tools.private_desktop import PrivateDesktop

TRAY_CLASS = "Shell_TrayWnd"
SIGNATURE = 0x34753423
"""What `Shell_NotifyIcon`'s data starts with (undocumented)."""
COPY_ICON, COPY_ICON_RECT = 1, 3
"""`COPYDATASTRUCT.dwData`: an icon's message, a question where it is."""
NIM = {0: "add", 1: "modify", 2: "delete", 3: "focus", 4: "version"}
NIF_MESSAGE, NIF_ICON, NIF_TIP, NIF_GUID = 0x01, 0x02, 0x04, 0x20
WM_CLOSE, WM_DESTROY, WM_COPYDATA, WM_CONTEXTMENU = 0x0010, 0x0002, 0x004A, 0x007B
WM_LBUTTONDOWN, WM_LBUTTONUP, WM_RBUTTONDOWN, WM_RBUTTONUP = 0x201, 0x202, 0x204, 0x205
NIN_SELECT = 0x0400
ICON_PX = 24
"""The stand-in icon's size, at the screen's bottom right."""

_LRESULT = ctypes.c_ssize_t
_WNDPROC = ctypes.WINFUNCTYPE(
    _LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM
)


class _COPYDATASTRUCT(ctypes.Structure):
    _fields_ = (
        ("dwData", ctypes.c_size_t),
        ("cbData", wintypes.DWORD),
        ("lpData", ctypes.c_void_p),
    )


class _WNDCLASSW(ctypes.Structure):
    _fields_ = (
        ("style", wintypes.UINT),
        ("lpfnWndProc", _WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HANDLE),
        ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
    )


_user32 = ctypes.WinDLL("user32", use_last_error=True)
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_user32.DefWindowProcW.argtypes = [
    wintypes.HWND,
    wintypes.UINT,
    wintypes.WPARAM,
    wintypes.LPARAM,
]
_user32.DefWindowProcW.restype = _LRESULT
_user32.RegisterClassW.argtypes = [ctypes.POINTER(_WNDCLASSW)]
_user32.RegisterClassW.restype = wintypes.ATOM
_user32.UnregisterClassW.argtypes = [wintypes.LPCWSTR, wintypes.HINSTANCE]
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
_user32.GetMessageW.argtypes = [
    ctypes.POINTER(wintypes.MSG),
    wintypes.HWND,
    wintypes.UINT,
    wintypes.UINT,
]
_user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
_user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
_user32.PostMessageW.argtypes = [
    wintypes.HWND,
    wintypes.UINT,
    wintypes.WPARAM,
    wintypes.LPARAM,
]
_user32.PostQuitMessage.argtypes = [ctypes.c_int]
_user32.SetThreadDesktop.argtypes = [wintypes.HANDLE]
_user32.GetSystemMetrics.argtypes = [ctypes.c_int]
_user32.GetWindowThreadProcessId.argtypes = [
    wintypes.HWND,
    ctypes.POINTER(wintypes.DWORD),
]
_kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
_kernel32.GetModuleHandleW.restype = wintypes.HMODULE


@dataclass(frozen=True)
class TrayIcon:
    """An icon as the taskbar has it: the app's window that gets its
    clicks (`hwnd`), its id there, the message the clicks come as, its
    tooltip, its picture (an `HICON`) and the click messages' version (4:
    Windows Vista's and later's)."""

    hwnd: int
    uid: int
    callback: int = 0
    tip: str = ""
    icon: int = 0
    version: int = 0

    @property
    def pid(self) -> int:
        """The process that owns the icon's window."""
        pid = wintypes.DWORD()
        _user32.GetWindowThreadProcessId(self.hwnd, ctypes.byref(pid))
        return pid.value


def _makelong(low: int, high: int) -> int:
    return (low & 0xFFFF) | ((high & 0xFFFF) << 16)


class StandInTaskbar:
    """`Shell_TrayWnd` on `desktop` for as long as the `with` lasts: what
    tray icons send is kept (`icons`, `messages`); `click` sends one an
    icon's click as Windows' taskbar does."""

    def __init__(self, desktop: PrivateDesktop) -> None:
        self.desktop = desktop
        self.hwnd = 0
        self.messages: list[tuple[str, int, int]] = []
        """Each icon message as it came: ("add", hwnd, uid), ..."""
        self.rect_questions: list[bytes] = []
        """Each time an app asked where its icon is, as it asked
        (`_icon_rect`)."""
        self._icons: dict[tuple[int, int], TrayIcon] = {}
        self._lock = threading.Lock()
        self._ready = threading.Event()
        self._failed: list[BaseException] = []
        self._proc = _WNDPROC(self._window_proc)  # kept: Windows calls it
        self._thread = threading.Thread(target=self._run, name="stand-in taskbar")
        width = _user32.GetSystemMetrics(0) or 1920  # SM_CXSCREEN
        height = _user32.GetSystemMetrics(1) or 1080  # SM_CYSCREEN
        self.icon_rect = (
            width - 2 * ICON_PX,
            height - ICON_PX,
            width - ICON_PX,
            height,
        )
        """Where the icon is (left, top, right, bottom): the screen's bottom
        right, as on Windows' taskbar - what an app asking is told, and
        where a click comes from."""

    def __enter__(self) -> Self:
        self._thread.start()
        if not self._ready.wait(10) or self._failed:
            raise RuntimeError(f"no stand-in taskbar: {self._failed}")
        return self

    def __exit__(self, *_: object) -> None:
        if self.hwnd:
            _user32.PostMessageW(self.hwnd, WM_CLOSE, 0, 0)
        self._thread.join(10)

    def icons(self) -> list[TrayIcon]:
        with self._lock:
            return list(self._icons.values())

    def click(self, icon: TrayIcon, what: Literal["context", "select"]) -> None:
        """A right click on `icon` ("context": its menu) or a left one
        ("select"), sent as the taskbar sends them: the buttons, then what
        they mean, at the icon's middle (version 4), or the buttons alone
        (before it)."""
        left, top, right, bottom = self.icon_rect
        at = _makelong((left + right) // 2, (top + bottom) // 2)
        down, up, meaning = (
            (WM_RBUTTONDOWN, WM_RBUTTONUP, WM_CONTEXTMENU)
            if what == "context"
            else (WM_LBUTTONDOWN, WM_LBUTTONUP, NIN_SELECT)
        )
        sent = [down, up, meaning] if icon.version >= 4 else [down, up]

        def post() -> None:
            for message in sent:
                if icon.version >= 4:
                    lparam = _makelong(message, icon.uid)
                    _user32.PostMessageW(icon.hwnd, icon.callback, at, lparam)
                else:
                    _user32.PostMessageW(icon.hwnd, icon.callback, icon.uid, message)

        self.desktop.on_desktop(post)  # from a thread on that desktop

    # --- the window, on its own thread on the desktop ------------------------

    def _run(self) -> None:
        try:
            if not _user32.SetThreadDesktop(self.desktop.handle):
                raise ctypes.WinError(ctypes.get_last_error())
            instance = _kernel32.GetModuleHandleW(None)
            kind = _WNDCLASSW(lpfnWndProc=self._proc, hInstance=instance)
            kind.lpszClassName = TRAY_CLASS
            if not _user32.RegisterClassW(ctypes.byref(kind)):
                raise ctypes.WinError(ctypes.get_last_error())
            hwnd = _user32.CreateWindowExW(
                0, TRAY_CLASS, None, 0, 0, 0, 0, 0, None, None, instance, None
            )  # never shown: Shell_NotifyIcon finds it hidden too
            if not hwnd:
                raise ctypes.WinError(ctypes.get_last_error())
            self.hwnd = hwnd
        except BaseException as error:  # noqa: BLE001 - raised by __enter__
            self._failed.append(error)
            self._ready.set()
            return
        self._ready.set()
        message = wintypes.MSG()
        while _user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
            _user32.TranslateMessage(ctypes.byref(message))
            _user32.DispatchMessageW(ctypes.byref(message))
        _user32.UnregisterClassW(TRAY_CLASS, instance)

    def _window_proc(self, hwnd: int, message: int, wparam: int, lparam: int) -> int:
        if message == WM_COPYDATA and lparam:
            data = _COPYDATASTRUCT.from_address(lparam)
            raw = ctypes.string_at(data.lpData, data.cbData) if data.lpData else b""
            if data.dwData == COPY_ICON:
                return self._icon_message(raw)
            if data.dwData == COPY_ICON_RECT:
                return self._icon_rect(raw)
            return 0
        if message == WM_CLOSE:
            _user32.DestroyWindow(hwnd)
            return 0
        if message == WM_DESTROY:
            _user32.PostQuitMessage(0)
            return 0
        return int(_user32.DefWindowProcW(hwnd, message, wparam, lparam))

    def _icon_message(self, raw: bytes) -> int:
        """`Shell_NotifyIcon`'s message: 1 if it's taken, as the taskbar
        answers."""
        if len(raw) < 32 or struct.unpack_from("<I", raw)[0] != SIGNATURE:
            return 0
        what = NIM.get(struct.unpack_from("<I", raw, 4)[0], "?")
        # NOTIFYICONDATAW after the signature and message, handles 32-bit
        _, hwnd, uid, flags, callback, icon = struct.unpack_from("<6I", raw, 8)
        key = (hwnd, uid)
        with self._lock:
            self.messages.append((what, hwnd, uid))
            if what == "delete":
                return int(self._icons.pop(key, None) is not None)
            found = self._icons.get(key, TrayIcon(hwnd, uid))
            if what == "add" and key in self._icons:
                return 0  # Windows' taskbar turns down an icon added twice
            if what in ("modify", "version") and key not in self._icons:
                return 0
            if flags & NIF_MESSAGE:
                found = replace(found, callback=callback)
            if flags & NIF_ICON:
                found = replace(found, icon=icon)
            if flags & NIF_TIP:
                tip = raw[32 : 32 + 256].decode("utf-16-le", "replace")
                found = replace(found, tip=tip.split("\0")[0])
            if what == "version" and len(raw) >= 812:
                found = replace(found, version=struct.unpack_from("<I", raw, 808)[0])
            self._icons[key] = found
        return 1

    def _icon_rect(self, raw: bytes) -> int:
        """Where an icon is (`Shell_NotifyIconGetRect`), packed as two
        numbers in one: Windows asks for its size (message 2: width and
        height), then its top left (message 1: x and y). Found by trying
        (215): corners for both, or x in the high half, left it failing."""
        if len(raw) < 8 or struct.unpack_from("<I", raw)[0] != SIGNATURE:
            return 0
        with self._lock:
            self.rect_questions.append(raw)
            if not self._icons:
                return 0
        left, top, right, bottom = self.icon_rect
        part = struct.unpack_from("<I", raw, 4)[0]
        if part == 1:
            return _makelong(left, top)
        if part == 2:
            return _makelong(right - left, bottom - top)
        return 0
