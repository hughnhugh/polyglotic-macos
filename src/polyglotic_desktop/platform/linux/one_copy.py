"""One copy of the app per user and data folder on Linux (polyglotic-hq
310, 550; `ports.one_copy`, decision 0101), as the Mac keeps it
(`platform/macos/one_copy.py`) and Windows' named mutex does.

- `FileLock` is the `CopyLock`: an exclusive `flock` on a file named for
  the copy, in `$XDG_RUNTIME_DIR/Polyglotic` (`system.runtime_folder`).
  Linux lets the lock go when the process ends, however it ends, so a
  crash leaves no stale lock. A second start finds it locked and closes
  its own file at once.
- `let_to_front` does nothing: the copy that runs raises its own window
  when asked (`ui/one_copy.py`'s local socket).
"""

import logging
import os
import sys
from pathlib import Path

from polyglotic_desktop.platform.linux.system import runtime_folder

log = logging.getLogger(__name__)


class FileLock:
    """`CopyLock` as an exclusive `flock` on `<folder>/<name>.lock`."""

    def __init__(self, name: str, folder: Path | None = None) -> None:
        self.path = (folder or runtime_folder()) / f"{name}.lock"
        self._fd: int | None = None

    def take(self) -> bool:
        if self._fd is not None:
            return True
        if sys.platform == "win32":
            raise OSError("flock is Linux's and macOS's")
        import fcntl

        try:
            self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o600)
        except OSError as e:  # Linux wouldn't say: this copy runs rather than none
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
    """`LetToFront`: nothing to hand on, on Linux."""
