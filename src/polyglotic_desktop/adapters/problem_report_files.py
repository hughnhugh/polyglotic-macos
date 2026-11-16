"""Problem reports waiting to be sent: one file each, in the data folder's `problem-reports` folder.

`ProblemReportFolder` implements `WaitingProblemReports`. Each report is
kept as the request body it will be sent as (protocol.md, Problem
reports), written whole - to a temporary name, then renamed - so a crash
or a closed app loses nothing; it's deleted once the server has it. At
most `KEEP` wait - each can be a few MB of audio - and past that the
oldest go.

They hold what the tester sent: their words, the log, and the captions and
audio they left ticked - in the user's own data folder, like their
settings; deleting `%APPDATA%\\Polyglotic` deletes them, and so do signing
out and deleting listening data.
"""

import logging
import os
from collections.abc import Sequence
from pathlib import Path

KEEP = 5
log = logging.getLogger(__name__)


class ProblemReportFolder:
    def __init__(self, folder: Path) -> None:
        self.folder = folder

    def add(self, report_id: str, body: bytes) -> None:
        self.folder.mkdir(parents=True, exist_ok=True)
        path = self.folder / f"{report_id}.json"
        part = path.with_suffix(".part")
        part.write_bytes(body)
        os.replace(part, path)
        for old in self._files()[:-KEEP]:
            old.unlink(missing_ok=True)
            log.info("a waiting problem report was dropped for room")

    def waiting(self) -> Sequence[tuple[str, bytes]]:
        found = []
        for path in self._files():
            try:
                found.append((path.stem, path.read_bytes()))
            except OSError as e:
                log.warning(
                    "a waiting problem report couldn't be read (%s)", type(e).__name__
                )
        return found

    def remove(self, report_id: str) -> None:
        (self.folder / f"{report_id}.json").unlink(missing_ok=True)

    def clear(self) -> int:
        files = self._files()
        for path in files:
            path.unlink(missing_ok=True)
        return len(files)

    def _files(self) -> list[Path]:
        if not self.folder.is_dir():
            return []
        return sorted(self.folder.glob("*.json"), key=lambda p: p.stat().st_mtime_ns)
