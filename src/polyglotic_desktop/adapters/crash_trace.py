"""The crash trace (polyglotic-hq 997): where a fatal error - an access
violation inside Qt, say - leaves every Python thread's stack. Nothing else
records one: the process is dying, and the log's own crash hook
(`main.CrashLog`) sees only Python's exceptions.

It's `faulthandler`, writing to `logs/crash.log` in the data folder. What it
writes is the error's kind ("Windows fatal exception: access violation")
and, for each thread, each frame's file, line and function - never a
value, so never a caption, a word or a setting - and the names of the
extension modules loaded. The files' paths are the app's own and Python's,
which sit under the user's own folder, so the file stays on this PC: a
report's log (`app_log.read_log`) reads `polyglotic.log` only.

On Windows, faulthandler also writes a trace for some errors a library
catches and carries on from, so a trace isn't always a crash, and a run
could write many: past `CRASH_TRACE_BYTES` the file starts again
(`keep_small`), as it does at each start after one that wrote a trace.
`CRASH_TRACE_FILES` files are kept, this run's among them.
"""

import faulthandler
import logging
from pathlib import Path
from typing import TextIO

log = logging.getLogger(__name__)

CRASH_TRACE_NAME = "crash.log"
CRASH_TRACE_FILES = 3
"""Files kept (count, 1-10): this run's and the two before it that held a
trace - enough to see a crash that comes back, each a few kB."""
CRASH_TRACE_BYTES = 1_000_000
"""Past this a run's file starts again (bytes, 100 kB - 10 MB): a crash's
trace is a few kB; only traces a library carried on from could fill it."""
CRASH_TRACE_CHECK_MS = 60_000
"""How often `keep_small` is asked (ms, 10 s - 10 min)."""


class CrashTrace:
    """faulthandler on for the whole run, to `folder`'s `crash.log`."""

    def __init__(
        self,
        folder: Path,
        files: int = CRASH_TRACE_FILES,
        most: int = CRASH_TRACE_BYTES,
    ) -> None:
        self.folder = folder
        self.files = max(1, files)
        self.most = most
        self.path = folder / CRASH_TRACE_NAME
        self._stream: TextIO | None = None

    def start(self) -> bool:
        """On, the last file kept if it held a trace. False if the file
        can't be opened: the app runs on without one."""
        try:
            self.folder.mkdir(parents=True, exist_ok=True)
            self._rotate()
            # faulthandler writes to the file's descriptor, unbuffered, until
            # the process ends; the object is held here and by faulthandler
            stream = self.path.open("w", encoding="utf-8")
        except OSError as error:
            log.warning("no crash trace: %s", type(error).__name__)
            return False
        faulthandler.enable(stream, all_threads=True)
        self._stream = stream
        return True

    def keep_small(self) -> None:
        """This run's file started again if it's past `most`."""
        if self._stream is None:
            return
        try:
            if self.path.stat().st_size <= self.most:
                return
        except OSError:
            return
        log.warning("the crash trace passed %d bytes: started again", self.most)
        self.stop()  # an open file can't be renamed on Windows
        self.start()

    def stop(self) -> None:
        if self._stream is None:
            return
        faulthandler.disable()
        self._stream.close()
        self._stream = None

    def _rotate(self) -> None:
        """crash.log to crash.log.1 and so on, the oldest dropped - unless
        it's empty (the last run didn't crash): then it's used again."""
        try:
            if self.path.stat().st_size == 0:
                return
        except FileNotFoundError:
            return
        for index in range(self.files - 1, 0, -1):
            newer = self.path if index == 1 else self._numbered(index - 1)
            if newer.exists():
                newer.replace(self._numbered(index))

    def _numbered(self, index: int) -> Path:
        return self.folder / f"{CRASH_TRACE_NAME}.{index}"
