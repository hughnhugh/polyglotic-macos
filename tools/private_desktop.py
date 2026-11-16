r"""Real windows without the user's screen: a command run on a Windows
desktop object of its own (polyglotic-hq project 205).

Windows shows one desktop of the signed-in user's window station, the
input desktop (`WinSta0\Default`), and never one made with `CreateDesktop`
unless something switches to it; nothing here does. A process started on
such a desktop makes its windows there: real windows (Qt's `windows`
platform, not `offscreen`), with Windows' own z-order and always-on-top
band, hit-testing (click-through), activation and DPI, and none of them
reaches the user's screen. What it can't stand in for (205's report):
- **the tray:** that desktop has no taskbar (`Shell_TrayWnd`), so a tray
  icon has nowhere to go - and can't reach the user's - unless a test puts
  a stand-in there (`tools/stand_in_taskbar.py`);
- **hotkeys:** Windows keeps one hotkey table for the whole session, so a
  hotkey taken there is taken from the user too: run the app with its
  hotkeys swapped out (as `tests/app_on_a_desktop.py` does);
- **input:** `SendInput` and the like go to the user's desktop; never use
  them. Drive Qt from inside, or post messages to a window;
- **the cursor:** it belongs to the user's desktop - reading it there is
  refused (`GetCursorPos`: access denied), so Qt's `QCursor.pos()` isn't
  the mouse, and hover that follows the pointer can't be checked;
- **the foreground:** Windows has one, on the input desktop; there, read
  each thread's active window instead (`Window.active`);
- **pictures:** only of the program's own windows, by Qt's `grab()` inside
  it (`python` below, `grab_windows`) - never a screen capture;
- **a service's session:** only the signed-in user's window station shows
  windows; in a service's (the CI runners'), windows are made and painted
  but never visible to Windows (`can_show_windows`).

    uv run python -m tools.private_desktop run [--timeout S] [--windows FILE] -- COMMAND ...
    uv run python -m tools.private_desktop python --shots DIR [--grab-after S]
        [--timeout S] [--windows FILE] -- -m MODULE ... | SCRIPT ...

`run` starts COMMAND on a new desktop and waits for it; at the timeout it
ends it and everything it started (a job object). With `--windows`, the
desktop's windows are listed every second (`Window`, top of the z-order
first) into FILE as JSON. Then the command's output is printed and the
desktop closed. `python` runs a Python program the same way, by this
Python, and saves a picture of each of its shown windows into DIR once,
`--grab-after` seconds after its QApplication exists.

In code: `with PrivateDesktop() as desktop: started = desktop.start([...])`,
then `desktop.windows()`, `desktop.window_at(x, y)`, `started.wait()`.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import msvcrt
import os
import runpy
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from ctypes import wintypes
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import IO, Self, TypeVar

if sys.platform != "win32":
    raise ImportError("tools.private_desktop needs Windows: desktops are Windows'")

T = TypeVar("T")

GENERIC_ALL = 0x10000000
CREATE_SUSPENDED, CREATE_UNICODE_ENVIRONMENT = 0x00000004, 0x00000400
CREATE_NO_WINDOW = 0x08000000
STARTF_USESTDHANDLES = 0x00000100
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
WAIT_OBJECT_0, INFINITE = 0, 0xFFFFFFFF
STILL_ACTIVE = 259
UOI_FLAGS, UOI_NAME = 1, 2
WSF_VISIBLE = 0x0001
GW_HWNDNEXT, GA_ROOT = 2, 2
GWL_EXSTYLE = -20
WS_EX_TOPMOST, WS_EX_TRANSPARENT = 0x00000008, 0x00000020
WS_EX_TOOLWINDOW, WS_EX_LAYERED = 0x00000080, 0x00080000
WS_EX_NOACTIVATE = 0x08000000
DWMWA_CLOAKED = 14
PER_MONITOR_AWARE_V2 = -4
"""DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2: rectangles in real pixels."""


class _STARTUPINFOW(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("lpReserved", wintypes.LPWSTR),
        ("lpDesktop", wintypes.LPWSTR),
        ("lpTitle", wintypes.LPWSTR),
        ("dwX", wintypes.DWORD),
        ("dwY", wintypes.DWORD),
        ("dwXSize", wintypes.DWORD),
        ("dwYSize", wintypes.DWORD),
        ("dwXCountChars", wintypes.DWORD),
        ("dwYCountChars", wintypes.DWORD),
        ("dwFillAttribute", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("wShowWindow", wintypes.WORD),
        ("cbReserved2", wintypes.WORD),
        ("lpReserved2", ctypes.c_void_p),
        ("hStdInput", wintypes.HANDLE),
        ("hStdOutput", wintypes.HANDLE),
        ("hStdError", wintypes.HANDLE),
    ]


class _PROCESS_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("hProcess", wintypes.HANDLE),
        ("hThread", wintypes.HANDLE),
        ("dwProcessId", wintypes.DWORD),
        ("dwThreadId", wintypes.DWORD),
    ]


class _IO_COUNTERS(ctypes.Structure):
    _fields_ = [
        (name, ctypes.c_ulonglong) for name in ("r", "w", "o", "rb", "wb", "ob")
    ]


class _JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_longlong),
        ("PerJobUserTimeLimit", ctypes.c_longlong),
        ("LimitFlags", wintypes.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", wintypes.DWORD),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", wintypes.DWORD),
        ("SchedulingClass", wintypes.DWORD),
    ]


class _JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", _JOBOBJECT_BASIC_LIMIT_INFORMATION),
        ("IoInfo", _IO_COUNTERS),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


class _USEROBJECTFLAGS(ctypes.Structure):
    _fields_ = [
        ("fInherit", wintypes.BOOL),
        ("fReserved", wintypes.BOOL),
        ("dwFlags", wintypes.DWORD),
    ]


class _GUITHREADINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("hwndActive", wintypes.HWND),
        ("hwndFocus", wintypes.HWND),
        ("hwndCapture", wintypes.HWND),
        ("hwndMenuOwner", wintypes.HWND),
        ("hwndMoveSize", wintypes.HWND),
        ("hwndCaret", wintypes.HWND),
        ("rcCaret", wintypes.RECT),
    ]


_user32 = ctypes.WinDLL("user32", use_last_error=True)
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_dwmapi = ctypes.WinDLL("dwmapi")

_user32.CreateDesktopW.argtypes = [
    wintypes.LPCWSTR,
    wintypes.LPCWSTR,
    wintypes.LPVOID,
    wintypes.DWORD,
    wintypes.DWORD,
    wintypes.LPVOID,
]
_user32.CreateDesktopW.restype = wintypes.HANDLE
_user32.CloseDesktop.argtypes = [wintypes.HANDLE]
_user32.SetThreadDesktop.argtypes = [wintypes.HANDLE]
_user32.GetProcessWindowStation.restype = wintypes.HANDLE
_user32.GetUserObjectInformationW.argtypes = [
    wintypes.HANDLE,
    ctypes.c_int,
    wintypes.LPVOID,
    wintypes.DWORD,
    ctypes.POINTER(wintypes.DWORD),
]
_user32.SetThreadDpiAwarenessContext.argtypes = [wintypes.HANDLE]
_user32.SetThreadDpiAwarenessContext.restype = wintypes.HANDLE
_user32.GetTopWindow.argtypes = [wintypes.HWND]
_user32.GetTopWindow.restype = wintypes.HWND
_user32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
_user32.GetWindow.restype = wintypes.HWND
_user32.GetWindowThreadProcessId.argtypes = [
    wintypes.HWND,
    ctypes.POINTER(wintypes.DWORD),
]
_user32.GetWindowThreadProcessId.restype = wintypes.DWORD
_user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
_user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
_user32.IsWindowVisible.argtypes = [wintypes.HWND]
_user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
_user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
_user32.GetWindowLongW.restype = ctypes.c_long
_user32.GetDpiForWindow.argtypes = [wintypes.HWND]
_user32.GetDpiForWindow.restype = wintypes.UINT
_user32.GetGUIThreadInfo.argtypes = [wintypes.DWORD, ctypes.POINTER(_GUITHREADINFO)]
_user32.WindowFromPoint.argtypes = [wintypes.POINT]
_user32.WindowFromPoint.restype = wintypes.HWND
_user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
_user32.GetAncestor.restype = wintypes.HWND
_user32.EnumWindows.argtypes = [ctypes.c_void_p, wintypes.LPARAM]
_dwmapi.DwmGetWindowAttribute.argtypes = [
    wintypes.HWND,
    wintypes.DWORD,
    wintypes.LPVOID,
    wintypes.DWORD,
]
_dwmapi.DwmGetWindowAttribute.restype = ctypes.c_long
_kernel32.CreateProcessW.argtypes = [
    wintypes.LPCWSTR,
    wintypes.LPWSTR,
    wintypes.LPVOID,
    wintypes.LPVOID,
    wintypes.BOOL,
    wintypes.DWORD,
    wintypes.LPVOID,
    wintypes.LPCWSTR,
    ctypes.POINTER(_STARTUPINFOW),
    ctypes.POINTER(_PROCESS_INFORMATION),
]
_kernel32.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
_kernel32.CreateJobObjectW.restype = wintypes.HANDLE
_kernel32.SetInformationJobObject.argtypes = [
    wintypes.HANDLE,
    ctypes.c_int,
    wintypes.LPVOID,
    wintypes.DWORD,
]
_kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
_kernel32.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
_kernel32.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
_kernel32.ResumeThread.argtypes = [wintypes.HANDLE]
_kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
_kernel32.WaitForSingleObject.restype = wintypes.DWORD
_kernel32.GetExitCodeProcess.argtypes = [
    wintypes.HANDLE,
    ctypes.POINTER(wintypes.DWORD),
]
_kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
_kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
_kernel32.OpenProcess.restype = wintypes.HANDLE
_kernel32.IsProcessInJob.argtypes = [
    wintypes.HANDLE,
    wintypes.HANDLE,
    ctypes.POINTER(wintypes.BOOL),
]
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

_WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


def _check(ok: object) -> None:
    if not ok:
        raise ctypes.WinError(ctypes.get_last_error())


@dataclass(frozen=True)
class Window:
    """A top-level window as Windows has it, read from outside its process."""

    hwnd: int
    pid: int
    class_name: str
    title: str
    rect: tuple[int, int, int, int]
    """Left, top, right, bottom, in real pixels."""
    visible: bool
    topmost: bool
    """In Windows' always-on-top band."""
    click_through: bool
    """Layered and transparent: the mouse goes to what's underneath."""
    no_activate: bool
    tool: bool
    """A tool window: no taskbar button."""
    active: bool
    """Its thread's active window (the keyboard's, within that thread)."""
    cloaked: int | None
    """DWM's cloaked reason (0: not cloaked); None if DWM wouldn't say."""
    dpi: int
    z: int
    """Its place in the desktop's z-order: 0 is the top."""


def _station() -> str:
    """This process's window station's name (`WinSta0` when signed in)."""
    name = ctypes.create_unicode_buffer(256)
    needed = wintypes.DWORD()
    _check(
        _user32.GetUserObjectInformationW(
            _user32.GetProcessWindowStation(),
            UOI_NAME,
            name,
            ctypes.sizeof(name),
            ctypes.byref(needed),
        )
    )
    return name.value


def can_show_windows() -> bool:
    """Whether this process's window station can show windows at all. Only
    the signed-in user's, `WinSta0`, can: a service's in session 0 - as the
    CI runners are - can't, so a window shown there is never visible to
    Windows (205: CI, 2026-11-08), nor found by hit-testing. The desktops
    made here are that window station's."""
    flags = _USEROBJECTFLAGS()
    needed = wintypes.DWORD()
    _check(
        _user32.GetUserObjectInformationW(
            _user32.GetProcessWindowStation(),
            UOI_FLAGS,
            ctypes.byref(flags),
            ctypes.sizeof(flags),
            ctypes.byref(needed),
        )
    )
    return bool(flags.dwFlags & WSF_VISIBLE)


def _facts(hwnd: int, z: int) -> Window:
    """What Windows says about one window, on a thread of its desktop."""
    pid = wintypes.DWORD()
    thread = _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    name, title = ctypes.create_unicode_buffer(256), ctypes.create_unicode_buffer(256)
    _user32.GetClassNameW(hwnd, name, 256)
    _user32.GetWindowTextW(hwnd, title, 256)
    rect = wintypes.RECT()
    _user32.GetWindowRect(hwnd, ctypes.byref(rect))
    style = _user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    info = _GUITHREADINFO(cbSize=ctypes.sizeof(_GUITHREADINFO))
    active = bool(_user32.GetGUIThreadInfo(thread, ctypes.byref(info))) and (
        (info.hwndActive or 0) == hwnd
    )
    cloaked = wintypes.DWORD()
    said = _dwmapi.DwmGetWindowAttribute(
        hwnd, DWMWA_CLOAKED, ctypes.byref(cloaked), ctypes.sizeof(cloaked)
    )
    layered_and_transparent = WS_EX_LAYERED | WS_EX_TRANSPARENT
    return Window(
        hwnd=hwnd,
        pid=pid.value,
        class_name=name.value,
        title=title.value,
        rect=(rect.left, rect.top, rect.right, rect.bottom),
        visible=bool(_user32.IsWindowVisible(hwnd)),
        topmost=bool(style & WS_EX_TOPMOST),
        click_through=style & layered_and_transparent == layered_and_transparent,
        no_activate=bool(style & WS_EX_NOACTIVATE),
        tool=bool(style & WS_EX_TOOLWINDOW),
        active=active,
        cloaked=cloaked.value if said == 0 else None,
        dpi=_user32.GetDpiForWindow(hwnd),
        z=z,
    )


def _top_down() -> list[int]:
    """The calling thread's desktop's top-level windows, top first."""
    found, hwnd = [], _user32.GetTopWindow(None)
    while hwnd:
        found.append(int(hwnd))
        hwnd = _user32.GetWindow(hwnd, GW_HWNDNEXT)
    return found


def windows_here(started: Started) -> list[int]:
    """The windows anything `started` started has on the calling thread's
    desktop - in a test, the one it runs on (the user's, outside CI): none,
    when all is well."""
    found: list[int] = []

    def each(hwnd: int, _: int) -> bool:
        owner = wintypes.DWORD()
        _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if started.owns(owner.value):
            found.append(int(hwnd))
        return True

    _user32.EnumWindows(_WNDENUMPROC(each), 0)
    return found


@dataclass
class Started:
    """A command started on a private desktop, in a job of its own: ending
    it ends whatever it started too."""

    pid: int
    _process: int
    _job: int

    def wait(self, timeout: float | None = None) -> int | None:
        """Its exit code once it ends; None if it's still running after
        `timeout` seconds (None: as long as it takes)."""
        ms = INFINITE if timeout is None else max(0, int(timeout * 1000))
        if _kernel32.WaitForSingleObject(self._process, ms) != WAIT_OBJECT_0:
            return None
        code = wintypes.DWORD()
        _check(_kernel32.GetExitCodeProcess(self._process, ctypes.byref(code)))
        return int(code.value)

    def owns(self, pid: int) -> bool:
        """Whether process `pid` is it or something it started (its job's)."""
        if pid == self.pid:
            return True
        process = _kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not process:
            return False
        try:
            inside = wintypes.BOOL()
            ok = _kernel32.IsProcessInJob(process, self._job, ctypes.byref(inside))
            return bool(ok and inside.value)
        finally:
            _kernel32.CloseHandle(process)

    def stop(self) -> None:
        """Ends it and everything it started, now."""
        if self._job:
            _kernel32.TerminateJobObject(self._job, 1)
            self.wait(10)

    def close(self) -> None:
        """Ends it if it's still running and lets go of its handles."""
        self.stop()
        for handle in (self._process, self._job):
            if handle:
                _kernel32.CloseHandle(handle)
        self._process = self._job = 0


def _environment(env: Mapping[str, str]) -> ctypes.Array[ctypes.c_wchar]:
    block = "".join(
        f"{k}={v}\0" for k, v in sorted(env.items(), key=lambda i: i[0].upper())
    )
    return ctypes.create_unicode_buffer(block + "\0")


class PrivateDesktop:
    """A desktop of this window station that Windows never displays, for as
    long as the `with` lasts. Whatever was started on it is ended and the
    desktop closed at the end."""

    def __init__(self, name: str | None = None) -> None:
        self.name = name or f"polyglotic-{os.getpid()}-{uuid.uuid4().hex[:8]}"
        self.path = f"{_station()}\\{self.name}"
        self._handle = 0
        self._started: list[Started] = []

    def __enter__(self) -> Self:
        handle = _user32.CreateDesktopW(self.name, None, None, 0, GENERIC_ALL, None)
        _check(handle)
        self._handle = handle
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    @property
    def handle(self) -> int:
        """The desktop's handle, for a thread of the caller's to join it
        (`SetThreadDesktop`; `tools/stand_in_taskbar.py`)."""
        if not self._handle:
            raise RuntimeError("the desktop isn't open: use `with PrivateDesktop()`")
        return int(self._handle)

    def close(self) -> None:
        for started in self._started:
            started.close()
        self._started.clear()
        if self._handle:
            _user32.CloseDesktop(self._handle)
            self._handle = 0

    def start(
        self,
        command: Sequence[str],
        *,
        env: Mapping[str, str] | None = None,
        cwd: Path | None = None,
        output: Path | None = None,
    ) -> Started:
        """Starts `command` on this desktop, without a console window; its
        output (both streams) to `output`, else nowhere."""
        if not self._handle:
            raise RuntimeError("the desktop isn't open: use `with PrivateDesktop()`")
        job = _kernel32.CreateJobObjectW(None, None)
        _check(job)
        limits = _JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not _kernel32.SetInformationJobObject(
            job,
            JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
            ctypes.byref(limits),
            ctypes.sizeof(limits),
        ):
            error = ctypes.WinError(ctypes.get_last_error())
            _kernel32.CloseHandle(job)
            raise error
        # closed below, once the command has its own copies of them
        streams: list[IO[bytes]] = [open(os.devnull, "rb")]  # noqa: SIM115
        streams.append(open(output or os.devnull, "wb"))  # noqa: SIM115
        try:
            handles = [msvcrt.get_osfhandle(s.fileno()) for s in streams]
            for handle in handles:
                os.set_handle_inheritable(handle, True)
            info = _STARTUPINFOW(cb=ctypes.sizeof(_STARTUPINFOW))
            info.lpDesktop = self.path
            info.dwFlags = STARTF_USESTDHANDLES
            info.hStdInput, info.hStdOutput, info.hStdError = (
                handles[0],
                handles[1],
                handles[1],
            )
            process = _PROCESS_INFORMATION()
            line = ctypes.create_unicode_buffer(subprocess.list2cmdline(command))
            block = _environment(os.environ if env is None else env)
            created = _kernel32.CreateProcessW(
                None,
                line,
                None,
                None,
                True,
                CREATE_SUSPENDED | CREATE_NO_WINDOW | CREATE_UNICODE_ENVIRONMENT,
                block,
                str(cwd) if cwd else None,
                ctypes.byref(info),
                ctypes.byref(process),
            )
            failed = None if created else ctypes.WinError(ctypes.get_last_error())
        finally:
            for stream in streams:
                stream.close()
        if failed is not None:
            _kernel32.CloseHandle(job)
            raise failed
        # in the job before it runs a line: ending the job ends all it starts
        started = Started(process.dwProcessId, process.hProcess, job)
        self._started.append(started)
        if not _kernel32.AssignProcessToJobObject(job, process.hProcess):
            error = ctypes.WinError(ctypes.get_last_error())
            _kernel32.TerminateProcess(process.hProcess, 1)
            _kernel32.CloseHandle(process.hThread)
            raise error
        _kernel32.ResumeThread(process.hThread)
        _kernel32.CloseHandle(process.hThread)
        return started

    def on_desktop(self, work: Callable[[], T]) -> T:
        """`work`'s result, run on a new thread attached to this desktop
        (one that owns windows can't change desktop), seeing rectangles in
        real pixels."""
        result: list[T] = []
        failed: list[BaseException] = []

        def run() -> None:
            try:
                _check(_user32.SetThreadDesktop(self._handle))
                _user32.SetThreadDpiAwarenessContext(PER_MONITOR_AWARE_V2)
                result.append(work())
            except BaseException as error:  # noqa: BLE001 - raised on the caller's
                failed.append(error)

        thread = threading.Thread(target=run, name=f"on {self.name}")
        thread.start()
        thread.join(30)
        if failed:
            raise failed[0]
        if not result:
            raise TimeoutError(f"nothing back from {self.name} in 30 s")
        return result[0]

    def windows(self, of: Started | None = None) -> list[Window]:
        """The desktop's top-level windows (only those of what `of` started,
        if given: a venv's `python.exe` starts the real one), top of the
        z-order first."""

        def read() -> list[Window]:
            listed = [_facts(hwnd, z) for z, hwnd in enumerate(_top_down())]
            return [w for w in listed if of is None or of.owns(w.pid)]

        return self.on_desktop(read)

    def window_at(self, x: int, y: int) -> int | None:
        """The top-level window the mouse would reach at (x, y) in real
        pixels - a click-through window lets it past - or None. Nothing is
        clicked."""

        def at() -> int | None:
            hwnd = _user32.WindowFromPoint(wintypes.POINT(x, y))
            root = _user32.GetAncestor(hwnd, GA_ROOT) if hwnd else None
            return int(root) if root else None

        return self.on_desktop(at)


# --- inside the program: pictures by its own grab() --------------------------


def grab_windows(folder: Path) -> list[Path]:
    """Saves a picture of each shown top-level window of this process's Qt
    interface into `folder` (Qt's own `grab()`: the window's own painting,
    nothing else of the screen). Call on the interface's thread."""
    from PySide6.QtWidgets import QApplication

    folder.mkdir(parents=True, exist_ok=True)
    saved = []
    shown = [w for w in QApplication.topLevelWidgets() if w.isVisible()]
    for n, widget in enumerate(shown):
        path = folder / f"{n:02d}-{type(widget).__name__}.png"
        if widget.grab().save(str(path)):
            saved.append(path)
    return saved


def _grab_once(folder: Path, after: float) -> None:
    """On a thread of its own: once the program's QApplication exists, waits
    `after` seconds, then has the interface's thread save its windows."""
    from PySide6.QtCore import QObject, Qt, Signal, Slot
    from PySide6.QtWidgets import QApplication

    while (app := QApplication.instance()) is None:
        time.sleep(0.1)
    time.sleep(after)
    done = threading.Event()

    class Grabber(QObject):
        wanted = Signal()

        @Slot()
        def grab(self) -> None:
            saved = grab_windows(folder)
            print(f"private_desktop: {len(saved)} pictures in {folder}", flush=True)
            done.set()

    grabber = Grabber()
    grabber.moveToThread(app.thread())
    grabber.wanted.connect(grabber.grab, Qt.ConnectionType.QueuedConnection)
    grabber.wanted.emit()
    done.wait(30)


def _inside(folder: Path, after: float, argv: list[str]) -> None:
    """Runs a Python program as `python ARGV...` would, grabbing its
    windows once along the way."""
    # Qt first, on this thread: two threads' first imports of PySide6 can
    # meet half-way, and its DLLs then don't load
    from PySide6 import QtWidgets  # noqa: F401

    threading.Thread(target=_grab_once, args=(folder, after), daemon=True).start()
    if argv[0] == "-m":
        sys.argv = [argv[1], *argv[2:]]
        runpy.run_module(argv[1], run_name="__main__", alter_sys=True)
    else:
        sys.argv = argv
        runpy.run_path(argv[0], run_name="__main__")


# --- the command line ---------------------------------------------------------


def run(
    command: Sequence[str],
    timeout: float,
    windows: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> int:
    """Runs `command` on a desktop of its own and prints its output; its
    exit code (124 if it was ended at the timeout)."""
    with tempfile.TemporaryDirectory(prefix="private-desktop-") as folder:
        log = Path(folder) / "output.txt"
        snapshots: list[dict[str, object]] = []
        with PrivateDesktop() as desktop:
            print(f"private_desktop: {desktop.path}", flush=True)
            started = desktop.start(command, env=env, output=log)
            began = time.monotonic()
            code = started.wait(0)
            while code is None:
                if windows is not None:
                    listed = [asdict(w) for w in desktop.windows()]
                    snapshots.append(
                        {"at": round(time.monotonic() - began, 1), "windows": listed}
                    )
                if time.monotonic() - began > timeout:
                    print(f"private_desktop: ended at the timeout ({timeout:g} s)")
                    started.stop()
                    code = 124
                    break
                code = started.wait(1.0)
        if windows is not None:
            windows.write_text(json.dumps(snapshots, indent=1), encoding="utf-8")
        print(log.read_text(encoding="utf-8", errors="replace"), end="")
        return code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m tools.private_desktop")
    sub = parser.add_subparsers(dest="what", required=True)
    for name in ("run", "python"):
        each = sub.add_parser(name)
        each.add_argument("--timeout", type=float, default=120.0)
        each.add_argument("--windows", type=Path, help="the windows listed, as JSON")
        if name == "python":
            each.add_argument("--shots", type=Path, required=True)
            each.add_argument("--grab-after", type=float, default=3.0)
        each.add_argument("command", nargs=argparse.REMAINDER)
    inside = sub.add_parser("inside", help=argparse.SUPPRESS)
    inside.add_argument("shots", type=Path)
    inside.add_argument("after", type=float)
    inside.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("a command is needed after --")
    if args.what == "inside":
        _inside(args.shots, args.after, command)
        return 0
    if args.what == "python":
        args.shots.mkdir(parents=True, exist_ok=True)
        command = [
            sys.executable,
            "-m",
            "tools.private_desktop",
            "inside",
            str(args.shots.resolve()),
            str(args.grab_after),
            "--",
            *command,
        ]
    env = dict(os.environ, QT_QPA_PLATFORM="windows")  # real windows, not offscreen
    return run(command, args.timeout, args.windows, env)


if __name__ == "__main__":
    sys.exit(main())
