"""One copy of the app per user and data folder on a Mac (polyglotic-hq
310, `ports.one_copy`, decision 0101), as Windows' named mutex keeps it on
Windows (`platform/windows/one_copy.py`).

- `FileLock` is the `CopyLock`: an exclusive `flock` on a file named for
  the copy, in `~/Library/Application Support/Polyglotic/locks`. macOS
  lets the lock go when the process ends, however it ends, so a crash
  leaves no stale lock - the file stays, unlocked, and the next start
  takes it. A second start finds it locked and closes its own file at once.
- `let_to_front` does nothing: macOS has no hand-over like Windows'
  `AllowSetForegroundWindow`; the copy that runs raises its own window
  when asked (`ui/one_copy.py`'s local socket, Qt's on each OS).
"""

import logging
import os
import sys
from pathlib import Path

from polyglotic_desktop.platform.macos.system import data_folder

log = logging.getLogger(__name__)


def locks_folder() -> Path:
    return data_folder() / "locks"


class FileLock:
    """`CopyLock` as an exclusive `flock` on `<folder>/<name>.lock`."""

    def __init__(self, name: str, folder: Path | None = None) -> None:
        self.path = (folder or locks_folder()) / f"{name}.lock"
        self._fd: int | None = None

    def take(self) -> bool:
        if self._fd is not None:
            return True
        if sys.platform == "win32":
            raise OSError("flock is macOS's and Linux's")
        import fcntl

        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o600)
        except OSError as e:  # macOS wouldn't say: this copy runs rather than none
            log.warning("one copy: no lock file (%s), running regardless", e.strerror)
            return True
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(fd)  # never kept: another copy holds it
            return False
        except OSError as e:
            os.close(fd)
            log.warning("one copy: no lock (%s), running regardless", e.strerror)
            return True
        self._fd = fd
        return True

    def release(self) -> None:
        if self._fd is not None:
            os.close(self._fd)  # closing it lets the lock go
            self._fd = None


def let_to_front(_pid: int) -> None:
    """`LetToFront`: nothing to hand on, on a Mac."""
