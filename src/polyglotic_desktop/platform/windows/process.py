"""When Windows started this process: how long the app took from its
launch to its window, the interpreter's own start and the imports included
- what the start budget counts (perf.budgets.START_FROM_SOURCE; project
136). `--check-install` reports it."""

import ctypes
from ctypes import wintypes

_kernel32 = ctypes.windll.kernel32
_kernel32.GetCurrentProcess.restype = ctypes.c_void_p
_kernel32.GetProcessTimes.argtypes = [ctypes.c_void_p] + [ctypes.c_void_p] * 4
_kernel32.GetSystemTimeAsFileTime.argtypes = [ctypes.c_void_p]


def _ticks(filetime: wintypes.FILETIME) -> int:
    return (filetime.dwHighDateTime << 32) | filetime.dwLowDateTime


def seconds_since_launch() -> float:
    """Seconds since Windows created this process."""
    created, ended, kernel, user = (wintypes.FILETIME() for _ in range(4))
    if not _kernel32.GetProcessTimes(
        _kernel32.GetCurrentProcess(),
        ctypes.byref(created),
        ctypes.byref(ended),
        ctypes.byref(kernel),
        ctypes.byref(user),
    ):
        raise ctypes.WinError()
    now = wintypes.FILETIME()
    _kernel32.GetSystemTimeAsFileTime(ctypes.byref(now))
    return (_ticks(now) - _ticks(created)) / 10_000_000  # 100 ns ticks
