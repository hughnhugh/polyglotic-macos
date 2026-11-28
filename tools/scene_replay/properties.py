"""The rules as properties of a replay's frames.

Each function reads the frames of one run and returns what breaks the rule:
an empty list means the rule held at every frame. They are plain Python over
`frames.Frame`, so the same property judges a later scene, or the Rust one,
from recorded frames with no window open.

One property per rule, named by the rule's id in `rules.toml`
(`PROPERTIES`).
"""

import itertools
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from tools.scene_replay.frames import FRAME, UNIT, Frame, Row, px

SLACK = 1
"""A move this small, in 1/64 px, is rounding, not a move."""

GLIDE_FASTEST = 300.0
"""Px a second: the approved glide's top speed (`views.cards.GLIDE_FASTEST`,
552 and 583; the tests check the product's own value is still this)."""
JUMP_PX = 6.0
JUMP_SPEED = 360.0
"""A jump: more than 6 px in one frame at more than 360 px a second (346's
thresholds, kept by 827's line replay)."""
OVERLAP_PX = 1.0
"""Two rows' ink overlaps when it shares more than this, both ways, in px."""


@dataclass(frozen=True)
class Broken:
    """One place a rule did not hold."""

    frame: int
    what: str

    def __str__(self) -> str:
        return f"frame {self.frame} ({self.frame * FRAME:.3f} s): {self.what}"


def _same_room(before: Frame, after: Frame) -> bool:
    """The window's size and the top of its text did not change: 969's
    condition for "no movement is asked for"."""
    return before.surfaces == after.surfaces


def never_fall(frames: Sequence[Frame]) -> list[Broken]:
    """No character that stays on screen is lower than it was a frame ago,
    while the window's size and the top of its text are unchanged."""
    broken = []
    for before, after in itertools.pairwise(frames):
        if before.rows is after.rows or not _same_room(before, after):
            continue
        old, new = before.chars(), after.chars()
        fell = [
            (new[key].top - old[key].top, key)
            for key in old.keys() & new.keys()
            if new[key].top > old[key].top + SLACK
        ]
        if fell:
            most, key = max(fell, key=lambda item: item[0])
            broken.append(
                Broken(
                    after.n,
                    f"{len(fell)} character(s) fell, one by {px(most):.2f} px"
                    f" (line {key[1]}, {key[2]}, on {key[0]})",
                )
            )
    return broken


def single_line(frames: Sequence[Frame]) -> list[Broken]:
    """Every row is one line of text: none holds a wrapped second line."""
    broken = []
    seen: set[tuple[str, int, str, int, int, int]] = set()
    for frame in frames:
        for row in frame.rows:
            if row.lines > 1 and row.id not in seen:
                seen.add(row.id)
                broken.append(
                    Broken(
                        frame.n,
                        f"a row holds {row.lines} lines"
                        f" (line {row.key}, {row.kind}, on {row.surface})",
                    )
                )
    return broken


def no_sideways_slide(frames: Sequence[Frame]) -> list[Broken]:
    """No character travels sideways: its left edge never changes in two
    frames running. (One step, when its caption's text is laid out again,
    is not a slide.)"""
    broken = []
    moved_before: set[Any] = set()
    for before, after in itertools.pairwise(frames):
        if before.rows is after.rows:
            moved_before = set()
            continue
        old, new = before.chars(), after.chars()
        moved = {
            key
            for key in old.keys() & new.keys()
            if abs(new[key].left - old[key].left) > SLACK
        }
        twice = moved & moved_before
        if twice:
            key = min(twice, key=str)
            broken.append(
                Broken(
                    after.n,
                    f"{len(twice)} character(s) moved sideways two frames running,"
                    f" one by {px(new[key].left - old[key].left):+.2f} px"
                    f" (line {key[1]}, {key[2]}, on {key[0]})",
                )
            )
        moved_before = moved
    return broken


def approved_glide(frames: Sequence[Frame]) -> list[Broken]:
    """A row that moves up or down never moves faster than the glide's top
    speed, and never jumps - except in the frame where a window put a
    burst of captions in place at once. A character that a new line break
    moves to another row is not this rule's (it is wrapping's)."""
    broken = []
    for before, after in itertools.pairwise(frames):
        if (
            before.rows is after.rows
            or before.bursts != after.bursts
            or not _same_room(before, after)
        ):
            continue
        old, new = before.placed_chars(), after.placed_chars()
        most = max(
            (abs(new[key].top - old[key].top) for key in old.keys() & new.keys()),
            default=0,
        )
        speed = px(most) / FRAME
        if px(most) > JUMP_PX and speed > JUMP_SPEED:
            broken.append(Broken(after.n, f"a jump of {px(most):.1f} px in one frame"))
        elif speed > GLIDE_FASTEST + SLACK / UNIT / FRAME:
            broken.append(
                Broken(after.n, f"text moving at {speed:.0f} px/s, over the glide's")
            )
    return broken


def _overlap(a: Row, b: Row) -> bool:
    across = min(a.ink[2], b.ink[2]) - max(a.ink[0], b.ink[0])
    down = min(a.ink[3], b.ink[3]) - max(a.ink[1], b.ink[1])
    return across > OVERLAP_PX * UNIT and down > OVERLAP_PX * UNIT


def waits_then_fades(frames: Sequence[Frame]) -> list[Broken]:
    """A row that is fading in never lies over other text and never moves
    while it fades; and no row ever appears on top of another's ink."""
    broken = []
    reported: set[object] = set()
    before_rows: dict[object, Row] = {}
    last: object = None
    for frame in frames:
        if frame.rows is last:
            continue
        last = frame.rows
        inked = [
            row for row in frame.rows if row.opacity > 0 and row.ink[2] > row.ink[0]
        ]
        for i, row in enumerate(inked):
            was = before_rows.get(row.id)
            fading = row.opacity < UNIT
            if (
                fading
                and was is not None
                and was.opacity > 0
                and (abs(was.top - row.top) > SLACK or abs(was.left - row.left) > SLACK)
                and ("moved", row.id) not in reported
            ):
                reported.add(("moved", row.id))
                broken.append(
                    Broken(
                        frame.n,
                        f"a row moved while fading in (line {row.key}, {row.kind},"
                        f" on {row.surface})",
                    )
                )
            for other in inked[i + 1 :]:
                pair = (row.id, other.id)
                if (
                    other.surface == row.surface
                    and pair not in reported
                    and _overlap(row, other)
                ):
                    reported.add(pair)
                    broken.append(
                        Broken(
                            frame.n,
                            f"two rows' ink overlaps on {row.surface}: line"
                            f" {row.key} {row.kind} and line {other.key} {other.kind}",
                        )
                    )
        before_rows = {row.id: row for row in frame.rows}
    return broken


PROPERTIES: dict[str, Callable[[Sequence[Frame]], list[Broken]]] = {
    "movement.words-never-fall": never_fall,
    "wrapping.every-row-is-a-single-line": single_line,
    "movement.no-sideways-slide": no_sideways_slide,
    "movement.the-approved-glide": approved_glide,
    "movement.a-new-row-waits-then-fades-in": waits_then_fades,
}
"""Each rule's property, by its id in `tests/ui_next/rules/rules.toml`."""
