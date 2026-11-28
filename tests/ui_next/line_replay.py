"""Measure the painted caption list with 346's row identities and jump thresholds.

The display's instrument grew from this (`tools/scene_replay`, polyglotic-hq
982): it plays the same streams into every surface on a patched clock and
keeps every character's place. The glyph reader and the streams' adapter
live there now; this module keeps 827's counters over the caption window.
"""

import json
from collections.abc import Callable
from dataclasses import dataclass, replace
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, cast
from unittest.mock import patch

import shiboken6
from PySide6.QtWidgets import QApplication
from tests.ui_next.test_caption_window import window_of
from tools.scene_replay.drive import glyphs  # noqa: F401 - 969's tests read it here
from tools.scene_replay.streams import line_update

from polyglotic_desktop.core.lexicon.readings import Reading
from polyglotic_desktop.core.listening.display import RowKind, WordLinks
from polyglotic_desktop.ui_next.caption_surface import PAD
from polyglotic_desktop.ui_next.caption_window import CaptionWindow
from polyglotic_desktop.ui_next.views.caption_window import CaptionLook

FRAME = 1 / 60
JUMP_PX, JUMP_SPEED = 6.0, 360.0
FIXTURES = Path(__file__).parents[1] / "fixtures" / "lines"


@dataclass(frozen=True)
class Box:
    top: float
    left: float
    height: float
    width: float
    start: int
    end: int


RowId = tuple[int, int, RowKind]


@dataclass(frozen=True)
class Row:
    text: str
    boxes: tuple[Box, ...]
    visible: tuple[Box, ...]


@dataclass
class Metrics:
    jump: float = 0
    peak_speed: float = 0
    orphaned: int = 0
    vanished: int = 0
    rewrap: int = 0
    x_shift: float = 0
    bursts: int = 0
    fill: float = 0
    worst: tuple[float, RowId] | None = None


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _rows(window: CaptionWindow) -> dict[RowId, Row]:
    canvas = window.canvas
    result: dict[RowId, Row] = {}
    for line, laid, rect in canvas.placed:
        for row in laid.rows:
            boxes = []
            for i in range(row.layout.lineCount()):
                part = row.layout.lineAt(i)
                ink = part.naturalTextRect()
                boxes.append(
                    Box(
                        rect.y() + row.top + part.y(),
                        rect.x() + ink.x(),
                        part.height(),
                        ink.width(),
                        row.source_index(part.textStart()),
                        row.source_index(part.textStart() + part.textLength()),
                    )
                )
            top = canvas.clear_top
            foot = min(rect.bottom(), PAD + canvas._seen_height())
            visible = tuple(b for b in boxes if b.top + b.height > top and b.top < foot)
            key = (line.key, row.row.clause, row.row.kind)
            previous = result.get(key, Row(line.rows[row.index].text, (), ()))
            result[key] = Row(
                previous.text, previous.boxes + tuple(boxes), previous.visible + visible
            )
    return result


@dataclass(frozen=True)
class Letter:
    char: str
    line: tuple[int, int]
    x: float
    shown: bool


def _letters(window: CaptionWindow) -> dict[tuple[int, RowKind], list[Letter]]:
    """Sample glyph positions at content edits, including text moved to a new clause."""
    result: dict[tuple[int, RowKind], list[Letter]] = {}
    canvas = window.canvas
    for line, laid, rect in canvas.placed:
        for row in laid.rows:
            letters = result.setdefault((line.key, row.row.kind), [])
            for n in range(row.layout.lineCount()):
                part = row.layout.lineAt(n)
                start, end = part.textStart(), part.textStart() + part.textLength()
                top = rect.y() + row.top + part.y()
                shown = top + part.height() > canvas.clear_top and top < min(
                    rect.bottom(), PAD + canvas._seen_height()
                )
                # Qt cursor positions are UTF-16 offsets, also for supplementary Han.
                text = (
                    row.layout.text()
                    .encode("utf-16-le")[2 * start : 2 * end]
                    .decode("utf-16-le")
                )
                cursor = start
                for char in text:
                    x, _ = cast(tuple[float, float], part.cursorToX(cursor))
                    letters.append(
                        Letter(
                            char,
                            (row.row.clause, row.visual_line + n),
                            rect.x() + x,
                            shown,
                        )
                    )
                    cursor += 1 + (ord(char) > 0xFFFF)
    return result


def _compare_letters(
    before: dict[tuple[int, RowKind], list[Letter]],
    after: dict[tuple[int, RowKind], list[Letter]],
    result: Metrics,
) -> None:
    for key in before.keys() & after.keys():
        old, new = before[key], after[key]
        matches = SequenceMatcher(
            None,
            "".join(x.char for x in old),
            "".join(x.char for x in new),
            autojunk=False,
        )
        for a, b, size in matches.get_matching_blocks():
            for i in range(size):
                prev, curr = old[a + i], new[b + i]
                if prev.shown:
                    result.rewrap += int(curr.line != prev.line)
                    result.x_shift = max(result.x_shift, abs(curr.x - prev.x))


def _compare(
    previous: dict[RowId, Row],
    rows: dict[RowId, Row],
    result: Metrics,
    now: float,
    clip: tuple[float, float],
    resting: bool,
) -> None:
    for key, old in previous.items():
        if not old.visible:
            continue
        new = rows.get(key)
        if new is None or not new.visible:
            b = old.visible[0]
            if b.top > clip[0] + 1.5 * b.height and b.top + b.height < clip[1] - 2:
                replaced = any(
                    other[2] == key[2]
                    and any(abs(x.top - b.top) <= 2 for x in row.visible)
                    for other, row in rows.items()
                )
                result.vanished += int(not replaced)
            continue
        for a, b in zip(old.boxes, new.boxes, strict=False):
            if a not in old.visible or b not in new.visible:
                continue
            dy = abs(b.top - a.top)
            result.peak_speed = max(result.peak_speed, dy / FRAME)
            if dy > JUMP_PX and dy / FRAME > JUMP_SPEED and dy > result.jump:
                result.jump, result.worst = dy, (now, key)
            if (
                old.text[: a.start + 1] == new.text[: a.start + 1]
                and a.start == b.start
            ):
                result.x_shift = max(result.x_shift, abs(a.left - b.left))
    if resting:
        for (caption_key, clause, kind), row in rows.items():
            if not row.visible:
                continue
            if row.visible[0] != row.boxes[0]:
                result.orphaned += 1
            if kind is RowKind.TRANSLATION:
                original = rows.get((caption_key, clause, RowKind.ORIGINAL))
                if original and not original.visible:
                    result.orphaned += 1


def measure(
    replay: dict[str, Any],
    qapp: QApplication,
    *,
    planted_step: bool = False,
    observe: Callable[[CaptionWindow, float], None] | None = None,
) -> Metrics:
    options = replay["window"]
    look = CaptionLook()
    readings = {}
    for event in replay["events"]:
        for clause in event["clauses"]:
            if clause["reading"]:
                text = clause["said"]
                han = [i for i, c in enumerate(text) if "\u3400" <= c <= "\u9fff"]
                readings[text] = [
                    Reading(i, i + 1, r)
                    for i, r in zip(han, clause["reading"], strict=True)
                ]
    look = replace(
        look,
        reading_lines=("zh",) if readings else (),
        word_links=WordLinks.ARROWS if options.get("arrows") else look.word_links,
        lab=replace(
            look.lab,
            own_right=options.get("own_right", True),
            arrival_gap=0,
            line_gap=0,
        ),
    )
    window = window_of(qapp, captions=0, look=look, show_mic=True)
    try:
        window.canvas.engine.readings = lambda text, lang: readings.get(text)
        window.resize(options["width"], options["height"])
        qapp.processEvents()
        now = 0.0
        window.clock = lambda: now
        note = window._note_arrivals

        def old_reflow(*, revealed_line: bool = False) -> None:
            if not revealed_line and window._known == {
                ln.key for ln in window.canvas.lines_in_view()
            }:
                window.canvas.at_rest = window.canvas.rest_rows()
                return
            note(revealed_line=revealed_line)

        events = iter(replay["events"])
        event = next(events, None)
        previous: dict[RowId, Row] = {}
        closed: dict[tuple[RowId, int], float] = {}
        result = Metrics()
        with (
            patch(
                "polyglotic_desktop.ui_next.caption_window.reduced_motion",
                return_value=False,
            ),
            patch.object(
                window, "_note_arrivals", old_reflow if planted_step else note
            ),
        ):
            for frame in range(round((replay["events"][-1]["t"] + 3) / FRAME) + 1):
                now = frame * FRAME
                changed = event is not None and event["t"] <= now + 1e-8
                letters = _letters(window) if changed else {}
                while event is not None and event["t"] <= now + 1e-8:
                    window.receive(line_update(event))
                    event = next(events, None)
                window._tick()
                window.canvas.repaint()
                rows = _rows(window)
                clip = (window.canvas.clear_top, PAD + window.canvas._seen_height())
                if result.bursts == window.bursts:
                    _compare(previous, rows, result, now, clip, not window.arriving)
                    if letters:
                        _compare_letters(letters, _letters(window), result)
                result.bursts = window.bursts
                newest = window.view.lines[-1] if window.view.lines else None
                open_clause = (
                    max((r.clause for r in newest.rows), default=-1) if newest else -1
                )
                for rid, row in rows.items():
                    for i, box in enumerate(row.boxes):
                        if box in row.visible and (
                            not newest
                            or rid[0] != newest.key
                            or not newest.live
                            or rid[1] < open_clause
                            or i < len(row.boxes) - 1
                        ):
                            closed[rid, i] = box.width / window.canvas._width()
                if observe:
                    observe(window, now)
                previous = rows
                if event is None and not window.arriving and not changed:
                    break
        result.fill = sum(closed.values()) / len(closed) if closed else 0.0
        return result
    finally:
        window.close()
        shiboken6.delete(window)
