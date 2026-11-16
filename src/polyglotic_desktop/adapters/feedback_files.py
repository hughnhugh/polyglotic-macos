"""Reports waiting to be sent: one JSON file each, in the data folder's `feedback` folder.

`FeedbackFolder` implements `WaitingReports`. Each report is written whole
(to a temporary name, then renamed) as soon as the user sends it, so a
crash or a closed app loses nothing; it's deleted once the server has it.
At most `KEEP` wait - past that the oldest go. A file that can't be read
is deleted rather than stopping the others.

They hold what the user wrote, and the log they chose to attach - in the
user's own data folder, like their settings; deleting `%APPDATA%\\Polyglotic`
deletes them.
"""

import json
import logging
import os
from collections.abc import Sequence
from dataclasses import asdict, fields
from pathlib import Path

from polyglotic_desktop.ports.feedback import Report

KEEP = 20
log = logging.getLogger(__name__)
_FIELDS = {f.name for f in fields(Report)}


class FeedbackFolder:
    def __init__(self, folder: Path) -> None:
        self.folder = folder

    def add(self, report: Report) -> None:
        self.folder.mkdir(parents=True, exist_ok=True)
        path = self.folder / f"{report.id}.json"
        part = path.with_suffix(".part")
        part.write_text(json.dumps(asdict(report), ensure_ascii=False), "utf-8")
        os.replace(part, path)
        for old in self._files()[:-KEEP]:
            old.unlink(missing_ok=True)
            log.info("a waiting report was dropped for room")

    def waiting(self) -> Sequence[Report]:
        found: list[Report] = []
        for path in self._files():
            try:
                data = json.loads(path.read_text("utf-8"))
                found.append(Report(**{k: data[k] for k in _FIELDS}))
            except (OSError, ValueError, KeyError, TypeError) as e:
                log.warning("a waiting report couldn't be read (%s)", type(e).__name__)
                path.unlink(missing_ok=True)
        return sorted(found, key=lambda r: r.at)

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
