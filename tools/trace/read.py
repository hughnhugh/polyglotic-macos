"""The caption timelines from whatever holds them: a trace file, a logs folder, a problem report's log, or the older caption log."""

import json
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from polyglotic_desktop.perf.trace_summary import REPORT_HEADER, expand

TRACE_NAME = "trace.jsonl"
CAPTION_LOG_NAME = "captions.log"

_CAPTION_LINE = re.compile(r"^(\S+ \S+) caption (\w+) id=(\S+)(.*)$")


def load(path: Path) -> tuple[list[dict[str, Any]], str]:
    """The records `path` holds, and what kind of source it was: `trace`,
    `report` or `caption log` (fewer stages: sent, answered, shown)."""
    if path.is_dir():
        traces = _rotated(path, TRACE_NAME)
        if traces:
            return _trace_files(traces), "trace"
        return _caption_log(_rotated(path, CAPTION_LOG_NAME)), "caption log"
    text = path.read_text(encoding="utf-8", errors="replace")
    if REPORT_HEADER in text:
        return _report(text), "report"
    if path.name.startswith(CAPTION_LOG_NAME):
        return _caption_log([path]), "caption log"
    return _trace_lines(text.splitlines()), "trace"


def _rotated(folder: Path, name: str) -> list[Path]:
    """`name`, `name.1`, ... oldest first."""
    found = [p for p in folder.glob(name + "*") if p.is_file()]

    def age(p: Path) -> int:
        suffix = p.name[len(name) :].lstrip(".")
        return int(suffix) if suffix.isdigit() else 0

    return sorted(found, key=age, reverse=True)


def _trace_files(paths: list[Path]) -> list[dict[str, Any]]:
    lines: list[str] = []
    for path in paths:
        lines.extend(path.read_text(encoding="utf-8", errors="replace").splitlines())
    return _trace_lines(lines)


def _trace_lines(lines: list[str]) -> list[dict[str, Any]]:
    records = []
    for line in lines:
        start = line.find("{")  # after the time of day the app writes first
        if start < 0:
            continue
        try:
            records.append(json.loads(line[start:]))
        except ValueError:
            continue  # a line cut short when the app stopped
    return records


def _report(text: str) -> list[dict[str, Any]]:
    after = text[text.index(REPORT_HEADER) + len(REPORT_HEADER) :]
    records = []
    for line in after.splitlines():
        line = line.strip()
        if line.startswith("["):
            try:
                records.append(expand(json.loads(line)))
            except (ValueError, TypeError):
                continue
    return records


def _caption_log(paths: list[Path]) -> list[dict[str, Any]]:
    """The caption log's sent, answered and shown lines as records (polyglotic-hq
    271's log, before the trace): each speech frame sent, its answer - the
    latest answer of the same caption and kind after it - and its shown
    line. Times are the log's wall clock, in seconds; only differences
    matter."""
    events: list[tuple[float, str, str, dict[str, str]]] = []
    for path in paths:
        for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
            m = _CAPTION_LINE.match(raw)
            if not m:
                continue
            at = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S,%f").timestamp()
            fields = dict(f.split("=", 1) for f in m.group(4).split() if "=" in f)
            events.append((at, m.group(2), m.group(3), fields))
    events.sort(key=lambda e: e[0])
    open_sends: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    answered: dict[tuple[str, str], dict[str, Any]] = {}
    records: list[dict[str, Any]] = []
    seq = 0
    for at, event, caption, fields in events:
        kind = fields.get("kind", "")
        key = (caption, kind)
        if event == "sent":
            since = int(fields.get("since_end_ms", "0")) / 1000
            record: dict[str, Any] = {
                "seq": seq,
                "cap": caption[:8],
                "kind": kind,
                "sec": int(fields["section"]) if "section" in fields else None,
                "src": fields.get("source", ""),
                "audio": float(fields.get("audio_s", "0") or 0),
                "t": {"captured": at - since, "sent": at},
                "end": "lost",
            }
            seq += 1
            records.append(record)
            open_sends[key].append(record)
        elif event == "answered" and open_sends.get(key):
            waiting = open_sends[key]
            record = waiting[-1]  # answers the newest sent (the log can't tell)
            for older in waiting[:-1]:
                older["end"] = "unanswered:overtaken"
            open_sends[key] = []
            record["t"]["received"] = at
            server = fields.get("server_ms")
            if server and server != "None":
                record["srv"] = {"processing": int(server)}  # no queue in it
            answered[key] = record
        elif event == "shown" and key in answered:
            record = answered.pop(key)
            record["t"]["applied"] = at
            record["end"] = "applied"
    return records
