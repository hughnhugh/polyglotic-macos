r"""One copy of the app per user and data folder (polyglotic-hq 310,
`ports.one_copy`, decision 0101), as Windows keeps it.

- `NamedMutex` is the `CopyLock`: a mutex named for the copy, in this
  session's own namespace (`Local\`). The first copy creates it and keeps
  its handle until the process ends; Windows deletes it with the last
  handle, so a crash or an end in Task Manager leaves nothing behind - a
  lock file would. A second start finds it there and closes its own
  handle at once, so it never keeps the mutex alive for a copy that has
  ended.
- `let_to_front` is `AllowSetForegroundWindow`: Windows lets a program
  bring its window in front only while it's the one the learner is
  using, and the second start (just opened) is; this hands that on to
  the copy that runs.
"""

import ctypes
import logging
from ctypes import wintypes

log = logging.getLogger(__name__)

NAMESPACE = "Local\\"  # this session's: two people signed in each have their own
ERROR_ALREADY_EXISTS = 183
ERROR_ACCESS_DENIED = 5
"""The mutex is there but this process may not open it: an elevated copy
made it (an administrator's run). Held all the same."""

_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
_kernel32.CreateMutexW.restype = wintypes.HANDLE
_kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
_kernel32.CloseHandle.restype = wintypes.BOOL
_user32 = ctypes.WinDLL("user32", use_last_error=True)
_user32.AllowSetForegroundWindow.argtypes = [wintypes.DWORD]
_user32.AllowSetForegroundWindow.restype = wintypes.BOOL


class NamedMutex:
    """`CopyLock` as a named mutex, `Local\\<name>`."""

    def __init__(self, name: str) -> None:
        self.name = NAMESPACE + name
        self._handle: int | None = None

    def take(self) -> bool:
        if self._handle is not None:
            return True
        handle = _kernel32.CreateMutexW(None, False, self.name)
        error = ctypes.get_last_error()
        if not handle:
            if error == ERROR_ACCESS_DENIED:
                return False
            # Windows wouldn't say: this copy runs rather than none at all
            log.warning("one copy: no mutex (error %d), running regardless", error)
            return True
        if error == ERROR_ALREADY_EXISTS:
            _kernel32.CloseHandle(handle)  # never kept: it would outlive its copy
            return False
        self._handle = handle
        return True

    def release(self) -> None:
        if self._handle is not None:
            _kernel32.CloseHandle(self._handle)
            self._handle = None


def let_to_front(pid: int) -> None:
    """`LetToFront` - refused quietly when this process may not hand it on
    (it isn't the one in front itself)."""
    _user32.AllowSetForegroundWindow(pid)
