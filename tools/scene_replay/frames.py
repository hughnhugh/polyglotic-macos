"""What one frame of a replay holds, and how two replays are compared.

Plain values, no Qt: the rule properties (`properties.py`) and the diff read
these, and so can a later scene that is replayed without a window.

A frame is what the surfaces say they placed after a paint: each row's
identity, its box, its opacity, and every visible character's left and top.
No text is kept (the characters are a place in the caption and a glyph
number). Every length is a whole number of 1/64 px, so two runs are either
the same or differ by something a learner could in principle see.
"""

import hashlib
import json
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from typing import Any

UNIT = 64
"""Lengths are kept in 1/64 px: Qt's own fixed-point grid for text."""

FRAME = 1 / 60
"""The replay's frame, in seconds."""


def q(value: float) -> int:
    """`value` px on the 1/64 px grid."""
    return round(value * UNIT)


def px(value: int) -> float:
    return value / UNIT


@dataclass(frozen=True)
class Char:
    """One visible character: its place in its caption's row text, the
    glyph drawn for it, and where its ink starts."""

    index: int
    glyph: int | str
    """A glyph number, or a reading's own text (made up or public)."""
    left: int
    top: int


@dataclass(frozen=True)
class Row:
    surface: str
    """Which canvas: `panel`, `zone`, `list`, or `col0.panel` in a joined
    window."""
    key: int
    """Its caption line's key."""
    kind: str
    """`original`, `translation`, or `label`."""
    clause: int
    visual: int
    """Which painted line of its clause's row this is."""
    nth: int
    """Tells apart rows that share everything above."""
    lines: int
    """How many lines its own layout holds: 1 unless the row wrapped."""
    top: int
    left: int
    width: int
    height: int
    opacity: int
    """0-64."""
    scale: int
    """64 unless a card is turning."""
    ink: tuple[int, int, int, int]
    """Its visible ink: left, top, right, bottom; all 0 when none shows."""
    chars: tuple[Char, ...]
    readings: tuple[Char, ...] = ()

    @property
    def id(self) -> tuple[str, int, str, int, int, int]:
        return (self.surface, self.key, self.kind, self.clause, self.visual, self.nth)


@dataclass(frozen=True)
class Surface:
    name: str
    top: int
    """Text above this is not shown (the bar, a notice, the pace line)."""
    foot: int
    width: int
    height: int


@dataclass(frozen=True)
class Frame:
    n: int
    surfaces: tuple[Surface, ...]
    rows: tuple[Row, ...]
    bursts: int = 0
    """How many times so far a window put everything in place at once
    because too much arrived together (`CaptionWindow.bursts`)."""

    @property
    def t(self) -> float:
        return self.n * FRAME

    def chars(self) -> dict[tuple[str, int, str, int, int, int | str], Char]:
        """Every visible character by who it is: surface, line, kind,
        clause, place in the text, glyph. The key 969's test uses."""
        found = {}
        for row in self.rows:
            if row.opacity <= 0:
                continue
            for char in (*row.chars, *row.readings):
                found[
                    (row.surface, row.key, row.kind, row.clause, char.index, char.glyph)
                ] = char
        return found

    def placed_chars(self) -> dict[tuple[object, ...], Char]:
        """Every visible character by the row it is on as well: a character
        that a new line break moves to another row is another key."""
        found: dict[tuple[object, ...], Char] = {}
        for row in self.rows:
            if row.opacity <= 0:
                continue
            for char in (*row.chars, *row.readings):
                found[(*row.id, char.index, char.glyph)] = char
        return found


def _plain(frame: Frame) -> list[Any]:
    return [
        frame.n,
        frame.bursts,
        [[s.name, s.top, s.foot, s.width, s.height] for s in frame.surfaces],
        [
            [
                r.surface,
                r.key,
                r.kind,
                r.clause,
                r.visual,
                r.nth,
                r.lines,
                r.top,
                r.left,
                r.width,
                r.height,
                r.opacity,
                r.scale,
                list(r.ink),
                [[c.index, c.glyph, c.left, c.top] for c in r.chars],
                [[c.index, c.glyph, c.left, c.top] for c in r.readings],
            ]
            for r in frame.rows
        ],
    ]


def to_json(frame: Frame) -> str:
    return json.dumps(_plain(frame), separators=(",", ":"), ensure_ascii=True)


def from_json(text: str) -> Frame:
    n, bursts, surfaces, rows = json.loads(text)
    return Frame(
        n,
        tuple(Surface(*s) for s in surfaces),
        tuple(
            Row(
                surface=r[0],
                key=r[1],
                kind=r[2],
                clause=r[3],
                visual=r[4],
                nth=r[5],
                lines=r[6],
                top=r[7],
                left=r[8],
                width=r[9],
                height=r[10],
                opacity=r[11],
                scale=r[12],
                ink=(r[13][0], r[13][1], r[13][2], r[13][3]),
                chars=tuple(Char(*c) for c in r[14]),
                readings=tuple(Char(*c) for c in r[15]),
            )
            for r in rows
        ),
        bursts,
    )


def body(frame: Frame) -> str:
    """The frame without its number: two frames with the same body show the
    same thing."""
    return json.dumps(_plain(frame)[1:], separators=(",", ":"), ensure_ascii=True)


@dataclass(frozen=True)
class Summary:
    """One run, small enough to keep for every run of the matrix: how many
    frames, a digest of them all, and a short digest of each frame that
    differs from the one before."""

    run: str
    frames: int
    digest: str
    changed: tuple[tuple[int, str], ...]
    paths: tuple[str, ...] = ()
    """The layout paths that ran (`drive.PATHS`)."""

    def to_plain(self) -> dict[str, Any]:
        return {
            "run": self.run,
            "frames": self.frames,
            "digest": self.digest,
            "changed": [list(item) for item in self.changed],
            "paths": list(self.paths),
        }

    @staticmethod
    def from_plain(plain: dict[str, Any]) -> "Summary":
        return Summary(
            plain["run"],
            plain["frames"],
            plain["digest"],
            tuple((n, digest) for n, digest in plain["changed"]),
            tuple(plain.get("paths", ())),
        )


def summarise(run: str, frames: Iterable[Frame], paths: Sequence[str] = ()) -> Summary:
    whole = hashlib.sha256()
    changed = []
    before = None
    count = 0
    for frame in frames:
        count += 1
        now = body(frame)
        if now != before:
            digest = hashlib.sha256(now.encode()).hexdigest()[:16]
            changed.append((frame.n, digest))
            whole.update(f"{frame.n}:{digest};".encode())
            before = now
    whole.update(f"frames={count}".encode())
    return Summary(run, count, whole.hexdigest(), tuple(changed), tuple(paths))


@dataclass(frozen=True)
class Difference:
    run: str
    frame: int
    what: str

    def describe(self) -> str:
        return (
            f"{self.run}: frame {self.frame} ({self.frame * FRAME:.3f} s): {self.what}"
        )


def first_difference(base: Summary, candidate: Summary) -> Difference | None:
    """Where two runs of one fixture first part, from their summaries."""
    if base.digest == candidate.digest:
        return None
    for (n, a), (m, b) in zip(base.changed, candidate.changed, strict=False):
        if n != m:
            return Difference(
                base.run, min(n, m), f"the picture changes at frame {n} against {m}"
            )
        if a != b:
            return Difference(base.run, n, "the frames differ")
    if len(base.changed) != len(candidate.changed):
        longer = (
            base.changed
            if len(base.changed) > len(candidate.changed)
            else candidate.changed
        )
        n = longer[min(len(base.changed), len(candidate.changed))][0]
        return Difference(base.run, n, "one side changes again, the other is still")
    return Difference(
        base.run, min(base.frames, candidate.frames), "the runs differ in length"
    )


def explain(base: Frame, candidate: Frame) -> Iterator[str]:
    """What differs between two frames, row by row, in px."""
    old = {row.id: row for row in base.rows}
    new = {row.id: row for row in candidate.rows}
    for rid in sorted(old.keys() - new.keys(), key=str):
        yield f"row {rid} is only in the base"
    for rid in sorted(new.keys() - old.keys(), key=str):
        yield f"row {rid} is only in the candidate"
    for rid in sorted(old.keys() & new.keys(), key=str):
        a, b = old[rid], new[rid]
        if a == b:
            continue
        for name in ("top", "left", "width", "height"):
            was, now = getattr(a, name), getattr(b, name)
            if was != now:
                yield f"row {rid}: {name} {px(was):.4f} -> {px(now):.4f} px"
        if a.opacity != b.opacity:
            yield f"row {rid}: opacity {a.opacity / UNIT:.3f} -> {b.opacity / UNIT:.3f}"
        if a.lines != b.lines:
            yield f"row {rid}: {a.lines} line(s) -> {b.lines}"
        moved = [
            (c, d)
            for c, d in zip(a.chars, b.chars, strict=False)
            if (c.left, c.top) != (d.left, d.top)
        ]
        if moved:
            c, d = moved[0]
            yield (
                f"row {rid}: {len(moved)} character(s) moved; the first by"
                f" ({px(d.left - c.left):+.4f}, {px(d.top - c.top):+.4f}) px"
            )
        if len(a.chars) != len(b.chars):
            yield f"row {rid}: {len(a.chars)} visible characters -> {len(b.chars)}"
    if base.surfaces != candidate.surfaces:
        yield f"surfaces: {base.surfaces} -> {candidate.surfaces}"
