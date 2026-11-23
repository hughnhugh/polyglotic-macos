"""Count sudden movement in project 553's recorded Video frames.

Run with python -m tools.subtitle_motion_critic RECORD_DIR. A continuous
movement of a caption row counts once. Compare its position, text height,
and the width of unchanged text. Retained text changing visual lines also
moves, even when the paragraph's outer rectangle stays still.
"""

import argparse
import json
import math
from collections import Counter
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QPointF, QRectF

from polyglotic_desktop.ui_next.views.cards import GLIDE_FASTEST

if TYPE_CHECKING:
    from polyglotic_desktop.ui_next.caption_window import CaptionWindow


def painted_sizes(window: "CaptionWindow") -> dict[str, int]:
    """553 recorder state for Video. Compare each visible visual line with
    its own language's requested font, including during fades and resizes."""
    canvas = window.canvas
    counts = {"lines": 0, "wrong": 0}
    if not window.video_enabled:
        return counts
    from polyglotic_desktop.ui_next.caption_surface import PAD

    viewport = QRectF(
        0,
        canvas.clear_top,
        canvas.width(),
        PAD + canvas._seen_height() - canvas.clear_top,
    )
    for line, laid, rect in [
        *canvas.placed,
        *((line, laid, rect) for line, laid, rect, _ in canvas.turning),
    ]:
        # Re-measure this line with the same engine and the user's two sizes,
        # independently of the layout that was actually sent to the painter.
        reference = canvas.engine.laid(line, canvas._width(), window.view.text_size)
        expected = {r.index: r.layout.font().pixelSize() for r in reference.rows}
        for row in laid.rows:
            actual = row.layout.font().pixelSize()
            origin = rect.topLeft() + row.layout.position() + QPointF(0, row.top)
            for i in range(row.layout.lineCount()):
                box = row.layout.lineAt(i).naturalTextRect().translated(origin)
                if box.intersects(viewport):
                    counts["lines"] += 1
                    counts["wrong"] += actual != expected[row.index]
    return counts


def size_changes(records: Iterable[dict[str, Any]]) -> dict[str, int] | None:
    """Count visible line/frame observations at a different configured size.
    Older recordings lack font observations and cannot establish a zero."""
    last: dict[str, list[dict[str, int]]] = {}
    total = wrong = 0
    for record in records:
        window = record["w"]
        if not record.get("same"):
            last[window] = [
                state["subtitle_sizes"]
                for state in record.get("st", {}).values()
                if "subtitle_sizes" in state
            ]
        if record["s"] == "f":
            for sample in last.get(window, []):
                total += sample["lines"]
                wrong += sample["wrong"]
    return {"size_changes": wrong, "visible_line_frames": total} if total else None


# The recorder rounds to tenths of a pixel. Opposite rounding at both
# ends of a displacement can change each axis by one unit.
PRECISION_PX = 0.1
ERROR_PX = math.sqrt(2) * PRECISION_PX
ACTION_LEAD_SEC = 0.05
ACTION_TAIL_SEC = 1.0  # the interval used by 553's provoked_by


@dataclass(frozen=True)
class Box:
    x: float
    y: float
    width: float
    height: float
    start: int
    end: int

    def origin_step(self, other: "Box") -> float:
        return max(
            abs(self.height - other.height),
            math.hypot(self.x - other.x, self.y - other.y),
        )


@dataclass(frozen=True)
class Row:
    text: str
    boxes: tuple[Box, ...]

    def step(self, other: "Row") -> float:
        if self == other:
            return 0.0
        distance = self.boxes[0].origin_step(other.boxes[0])
        if self.text.startswith(other.text) or other.text.startswith(self.text):
            matches = [(0, 0, min(len(self.text), len(other.text)))]
        else:
            matches = list(
                SequenceMatcher(
                    None, self.text, other.text, autojunk=False
                ).get_matching_blocks()
            )
        for a, b, length in matches:
            for old in self.boxes:
                for new in other.boxes:
                    if max(0, old.start - a, new.start - b) >= min(
                        length, old.end - a, new.end - b
                    ):
                        continue
                    # A character shared by these visual lines has at
                    # least their vertical displacement. With the same
                    # start we also know its exact left-edge displacement.
                    distance = max(
                        distance, abs(old.y - new.y), abs(old.height - new.height)
                    )
                    if old.start - a == new.start - b:
                        distance = max(distance, old.origin_step(new))
                        if (
                            self.text[old.start : old.end]
                            == other.text[new.start : new.end]
                        ):
                            distance = max(
                                distance,
                                math.hypot(
                                    old.width - new.width, old.height - new.height
                                ),
                            )
        return distance


Key = tuple[str, int, int, str, int]
Frame = tuple[float, dict[Key, Row]]


def frames(
    records: Iterable[dict[str, Any]],
) -> Iterator[tuple[str, Frame, tuple[int, int]]]:
    """Sample the geometry in the film, including stationary grabs."""
    last: dict[str, dict[Key, Row]] = {}
    sizes: dict[str, tuple[int, int]] = {}
    for record in records:
        window = record["w"]
        if not record.get("same"):
            sizes[window] = (record["sz"][0], record["sz"][1])
            rows = {}
            sides: Counter[tuple[str, int, int, str]] = Counter()
            for row in record["rows"]:
                col, key, index, side, _, tag, text, lines = row[:8]
                clause = row[8] if len(row) > 8 else index
                encoded = text.encode("utf-16-le")
                clip = record["clip"].get(f"{col}/{tag}")
                boxes = []
                for x, y, width, height, start, length in lines:
                    if clip and (y + height <= clip[0] or y >= clip[1]):
                        continue
                    first = len(encoded[: 2 * start].decode("utf-16-le"))
                    end = len(encoded[: 2 * (start + length)].decode("utf-16-le"))
                    boxes.append(Box(x, y, width, height, first, end))
                same_side = col, key, clause, side
                if boxes:
                    rows[(*same_side, sides[same_side])] = Row(text, tuple(boxes))
                sides[same_side] += 1
            last[window] = rows
        if record["s"] == "f" and window in last:
            yield window, (record["t"], last[window]), sizes[window]


@dataclass
class Movement:
    at: float
    steps: int = 0
    peak: float = 0.0
    slowest: float = math.inf
    over_at: float | None = None

    def add(self, distance: float, dt: float, now: float, limit: float) -> None:
        self.steps += 1
        speed = (distance - ERROR_PX) / dt
        if speed > limit and self.over_at is None:
            self.over_at = now
        self.peak = max(self.peak, speed)
        self.slowest = min(self.slowest, (distance + ERROR_PX) / dt)


def episodes(track: Iterable[Frame], speed: float) -> list[dict[str, Any]]:
    active: dict[Key, Movement] = {}
    previous: dict[Key, Row] = {}
    then = 0.0
    found = []

    def finish(key: Key) -> None:
        run = active.pop(key)
        fast = run.peak > speed
        # A one-step teleport, or a move at a single speed between
        # stationary frames, has no observable easing frame.
        abrupt = run.steps == 1 or run.slowest >= run.peak
        if fast or abrupt:
            found.append(
                {
                    "at": run.at if run.over_at is None else run.over_at,
                    "started": run.at,
                    "row": key,
                    "steps": run.steps,
                    "peak_px_s": round(run.peak, 1),
                    "over_limit": fast,
                    "no_easing": abrupt,
                }
            )

    for now, rows in track:
        moving = set()
        for key in rows.keys() & previous.keys():
            distance = previous[key].step(rows[key])
            if distance <= ERROR_PX or now <= then:
                continue
            moving.add(key)
            active.setdefault(key, Movement(now)).add(distance, now - then, now, speed)
        for key in active.keys() - moving:
            finish(key)
        previous, then = rows, now
    for key in list(active):
        finish(key)
    return found


def judge(folder: Path) -> dict[str, Any]:
    with (folder / "geometry.jsonl").open(encoding="utf-8") as source:
        tracks: dict[str, list[Frame]] = {}
        resized: set[tuple[str, float]] = set()
        previous_size: dict[str, tuple[int, int]] = {}
        for window, frame, size in frames(json.loads(line) for line in source):
            if window in previous_size and previous_size[window] != size:
                resized.add((window, frame[0]))
            previous_size[window] = size
            tracks.setdefault(window, []).append(frame)
    actions = [
        json.loads(line)
        for line in (folder / "events.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    counts: Counter[str] = Counter()
    events = []
    for window, track in tracks.items():
        for event in episodes(track, GLIDE_FASTEST.value):
            action = next(
                (
                    a["label"]
                    for a in reversed(actions)
                    if a["t"] - ACTION_LEAD_SEC
                    <= event["at"]
                    <= a["t"] + a.get("dur", 0) + ACTION_TAIL_SEC
                ),
                None,
            )
            counts["after_action" if action else "unprovoked"] += 1
            events.append(
                {
                    "window": window,
                    "action": action,
                    "window_resized": (window, event["at"]) in resized,
                    **event,
                }
            )
    with (folder / "geometry.jsonl").open(encoding="utf-8") as source:
        sizes = size_changes(json.loads(line) for line in source)
    return {
        "subtitle_sizes": sizes,
        "limit_px_s": GLIDE_FASTEST.value,
        "unprovoked": counts["unprovoked"],
        "after_action": counts["after_action"],
        "events": events,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("record", type=Path)
    print(json.dumps(judge(parser.parse_args().record), indent=2))
