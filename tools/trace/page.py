"""The viewer's page: what a stretch of caption timelines says, an overview, and a close-up of each of the worst hangs.

Drawn as SVG with the colours written in (so Qt's renderer can make the
same close-ups PNGs) and class names the page's own style recolours for
dark mode. The 8 segment groups take the 8 categorical slots in a fixed
order (the dataviz skill's reference palette); the pause is neutral.
Each source's stretches of sound without speech (polyglotic-hq 549) have
a lane of their own, under the moments the screen changed.
"""

import html
import itertools
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

from polyglotic_desktop.perf.trace import APP_STAGES, UNHEARD
from polyglotic_desktop.perf.trace_summary import (
    SEGMENTS,
    Hang,
    Summary,
    percentile,
    segments,
    shown_at,
)

GROUPS: tuple[tuple[str, str, str, str], ...] = (
    # (class, label, light, dark)
    ("g1", "capture", "#2a78d6", "#3987e5"),
    ("g2", "detect and encode", "#eb6834", "#d95926"),
    ("g3", "send loop", "#1baf7a", "#199e70"),
    ("g4", "network", "#eda100", "#c98500"),
    ("g5", "server queue", "#e87ba4", "#d55181"),
    ("g6", "server work", "#008300", "#0ca30c"),
    ("g7", "interface thread", "#6250d6", "#9085e9"),
    ("g8", "window hold and paint", "#e34948", "#e66767"),
)
PAUSE = ("gp", "waiting for the pause (finished speech)", "#d4d3cd", "#4a4945")
UNSPLIT = ("gu", "not split (an older log)", "#a9a8a2", "#6b6a64")
PACE = ("gc", "the caption mode's pace (Steady's playout)", "#bcb9ae", "#58564f")
"""A paced mode's planned wait (polyglotic-hq 551): neutral, as the pause
is - the mode's own, not a delay."""
UNHEARD_LANE = ("gs", "sound without speech", "#9c8a6e", "#8a7a60")
HANG = "#c62828"
BURST = "#eb6834"
UNHEARD_CLOSEUPS = 3
"""The longest stretches of sound without speech given a close-up each,
beside the worst other hangs."""

_ENDS_IN = {  # the stage a span ends at -> its group's class
    "heard": "gp",
    "delivered": "g1",
    "detected": "g2",
    "encoded": "g2",
    "taken": "g3",
    "sent": "g3",
    "handed": "g7",
    "applied": "g7",
    "released": "gc",
    "windowed": "g8",
    "painted": "g8",
}
_COLOUR = {c: light for c, _, light, _ in (*GROUPS, PAUSE, PACE, UNSPLIT, UNHEARD_LANE)}

WIDTH = 1100
LEFT = 96
RIGHT = 16
ROW = 7
ROW_GAP = 3
SCREEN = 16
LANE = 9


def _x(at: float, start: float, end: float) -> float:
    return LEFT + (at - start) / max(end - start, 1e-6) * (WIDTH - LEFT - RIGHT)


def spans(record: Mapping[str, Any]) -> list[tuple[float, float, str]]:
    """The record's time from the sound to the screen as (start, end,
    group class) spans, in order."""
    times: Mapping[str, float] = record.get("t") or {}
    present = [s for s in APP_STAGES if s in times]
    found: list[tuple[float, float, str]] = []
    for a, b in itertools.pairwise(present):
        ta, tb = float(times[a]), float(times[b])
        if tb <= ta:
            continue
        adjacent = APP_STAGES.index(b) - APP_STAGES.index(a) == 1 or (a, b) == (
            "applied",
            "windowed",  # a mode without a pace: no `released` between (551)
        )
        if (a, b) == ("sent", "received") and record.get("srv"):
            found.extend(_round_trip(ta, tb, record["srv"]))
        elif (a, b) == ("sent", "received"):
            found.append((ta, tb, "g4"))
        elif adjacent and b in _ENDS_IN:
            found.append((ta, tb, _ENDS_IN[b]))
        else:
            found.append((ta, tb, "gu"))
    return found


def _round_trip(
    sent: float, received: float, server: Mapping[str, int]
) -> list[tuple[float, float, str]]:
    """The round trip: half the network, the server's queue and work, the
    other half - the server's times are durations, so they're placed."""
    total = received - sent
    on_server = min(total, server.get("server", server.get("processing", 0)) / 1000)
    queued = min(on_server, server.get("waited", 0) / 1000)
    half = (total - on_server) / 2
    marks = [sent, sent + half, sent + half + queued, sent + half + on_server, received]
    parts = []
    for (a, b), group in zip(
        itertools.pairwise(marks), ("g4", "g5", "g6", "g4"), strict=False
    ):
        if b > a:
            parts.append((a, b, group))
    return parts


def window_svg(
    records: Sequence[Mapping[str, Any]],
    start: float,
    end: float,
    hangs: Sequence[Hang],
    bursts: Sequence[tuple[float, int]],
    title: str,
) -> str:
    """A close-up of `start` to `end`: per source, the moments the screen
    changed (ticks; hangs as red bands, bursts as orange marks), its
    stretches of sound without speech, and each update as a bar from the
    sound to the screen."""
    inside = [
        r
        for r in records
        if (r.get("t") or {}) and _first(r) <= end and _last(r) >= start
    ]
    unheard = [r for r in inside if r.get("kind") == UNHEARD]
    inside = [r for r in inside if r.get("kind") != UNHEARD]
    sources = sorted({str(r.get("src") or "?") for r in (*inside, *unheard)}) or ["-"]
    rows_of: dict[str, list[list[float]]] = {s: [] for s in sources}
    placed: list[tuple[str, int, Mapping[str, Any]]] = []
    for r in sorted(inside, key=_first):
        lanes = rows_of[str(r.get("src") or "?")]
        row = next(
            (i for i, last in enumerate(lanes) if last[0] < _first(r) - 0.02), None
        )
        if row is None:
            lanes.append([0.0])
            row = len(lanes) - 1
        lanes[row][0] = _last(r)
        placed.append((str(r.get("src") or "?"), row, r))
    top = 34
    lane_top: dict[str, float] = {}
    y = top
    for s in sources:
        lane_top[s] = y
        y += SCREEN + LANE + 10 + max(1, len(rows_of[s])) * (ROW + ROW_GAP) + 14
    height = y + 54
    out = [
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} {height:.0f}"'
            f' width="{WIDTH}" height="{height:.0f}" font-family="Segoe UI"'
            ' font-size="11">'
        ),
        f'<rect class="bg" width="{WIDTH}" height="{height:.0f}" fill="#fcfcfb"/>',
        (
            f'<text class="ink" x="{LEFT}" y="14" font-size="13" font-weight="600"'
            f' fill="#0b0b0b">{html.escape(title)}</text>'
        ),
    ]
    out += _axis(start, end, top - 8, height - 48)
    for s in sources:
        ly = lane_top[s]
        out.append(
            f'<text class="ink2" x="6" y="{ly + 11:.0f}" fill="#52514e">'
            f"{html.escape(s)}</text>"
        )
        out.append(
            f'<text class="ink3" x="6" y="{ly + SCREEN + LANE + 3:.0f}"'
            ' fill="#8a8984" font-size="10">no speech heard</text>'
        )
        out.append(
            f'<text class="ink3" x="6" y="{ly + SCREEN + LANE + 20:.0f}"'
            ' fill="#8a8984" font-size="10">updates</text>'
        )
        out += _unheard_lane(
            [r for r in unheard if str(r.get("src") or "?") == s],
            start,
            end,
            ly + SCREEN + 3,
        )
        out.append(
            f'<rect class="track" x="{LEFT}" y="{ly}" width="{WIDTH - LEFT - RIGHT}"'
            f' height="{SCREEN}" fill="#f0efec"/>'
        )
        for h in hangs:
            if h.source != s or h.at < start or h.at - h.seconds > end:
                continue
            x0 = _x(max(start, h.at - h.seconds), start, end)
            x1 = _x(min(end, h.at), start, end)
            out.append(
                f'<rect x="{x0:.1f}" y="{ly}" width="{max(1.0, x1 - x0):.1f}"'
                f' height="{SCREEN}" fill="{HANG}" fill-opacity="0.22">'
                f"<title>hang {h.seconds:.1f} s: {h.cause}</title></rect>"
            )
            out.append(
                f'<text x="{x0 + 3:.1f}" y="{ly + 12}" fill="{HANG}" font-size="10"'
                f' font-weight="600">hang {h.seconds:.1f} s: {h.cause}</text>'
            )
    for source, row, r in placed:
        ly = lane_top[source] + SCREEN + LANE + 10 + row * (ROW + ROW_GAP)
        tip = _tip(r)
        out.append(f"<g><title>{html.escape(tip)}</title>")
        for a, b, group in spans(r):
            if b < start or a > end:
                continue
            x0, x1 = _x(max(a, start), start, end), _x(min(b, end), start, end)
            out.append(
                f'<rect class="{group}" x="{x0:.1f}" y="{ly:.1f}"'
                f' width="{max(0.8, x1 - x0):.1f}" height="{ROW}"'
                f' fill="{_COLOUR[group]}"/>'
            )
        shown = shown_at(r)
        if shown is None and _last(r) <= end:  # dropped: an x at its end
            x = _x(_last(r), start, end)
            out.append(
                f'<path class="ink2" d="M{x - 3:.1f},{ly:.1f}l6,{ROW}m0,-{ROW}l-6,{ROW}"'
                ' stroke="#52514e" stroke-width="1.5"/>'
            )
        out.append("</g>")
        if shown is not None and start <= shown <= end:
            x = _x(shown, start, end)
            sy = lane_top[source]
            out.append(
                f'<line class="tick" x1="{x:.1f}" x2="{x:.1f}" y1="{sy + 2}"'
                f' y2="{sy + SCREEN - 2}" stroke="#0b0b0b" stroke-width="1.5"/>'
            )
    for at, n in bursts:
        if start <= at <= end:
            x = _x(at, start, end)
            out.append(
                f'<circle cx="{x:.1f}" cy="{top - 4}" r="4" fill="{BURST}">'
                f"<title>burst: {n} shown within 0.3 s</title></circle>"
            )
    out += _legend(height - 6)
    out.append("</svg>")
    return "\n".join(out)


def _unheard_lane(
    stretches: Sequence[Mapping[str, Any]], start: float, end: float, y: float
) -> list[str]:
    """A source's stretches of sound without speech, as bars at `y`."""
    out = []
    cls, _, light, _ = UNHEARD_LANE
    for r in stretches:
        times = r.get("t") or {}
        a, b = float(times.get("began", 0.0)), float(times.get("ended", 0.0))
        if b < start or a > end:
            continue
        x0, x1 = _x(max(a, start), start, end), _x(min(b, end), start, end)
        out.append(
            f'<rect class="{cls}" x="{x0:.1f}" y="{y:.1f}"'
            f' width="{max(1.0, x1 - x0):.1f}" height="{LANE}" fill="{light}">'
            f"<title>{html.escape(unheard_tip(r))}</title></rect>"
        )
    return out


def unheard_tip(r: Mapping[str, Any]) -> str:
    """A stretch of sound without speech in a line."""
    times = r.get("t") or {}
    seconds = float(times.get("ended", 0.0)) - float(times.get("began", 0.0))
    p10, p50, p90 = r.get("dbfs") or (None, None, None)
    resets = int(r.get("resets") or 0)
    after = r.get("after_reset")
    last = (
        f", the last {after} s before its end" if resets and after is not None else ""
    )
    return (
        f"sound without speech {seconds:.1f} s ({r.get('end')}): level"
        f" p10/p50/p90 {p10}/{p50}/{p90} dBFS; speech detection forgot its"
        f" state {resets} times in it{last}"
    )


def _axis(start: float, end: float, y0: float, y1: float) -> list[str]:
    span = end - start
    step = next(
        s for s in (0.5, 1, 2, 5, 10, 30, 60, 300, 600, 1800, 3600) if span / s <= 14
    )
    out = []
    t = 0.0
    while t <= span + 1e-9:
        x = _x(start + t, start, end)
        out.append(
            f'<line class="grid" x1="{x:.1f}" x2="{x:.1f}" y1="{y0}" y2="{y1}"'
            ' stroke="#e6e5e0" stroke-width="1"/>'
        )
        label = f"{t:g} s" if step < 60 else f"{t / 60:g} min"
        out.append(
            f'<text class="ink3" x="{x:.1f}" y="{y1 + 12}" text-anchor="middle"'
            f' fill="#8a8984" font-size="10">{label}</text>'
        )
        t += step
    return out


def _legend(y: float) -> list[str]:
    """The segment groups' colours, in two rows from `y - 14`."""
    out = []
    x, row_y = float(LEFT), y - 14
    for cls, label, light, _ in (*GROUPS, PAUSE, PACE, UNHEARD_LANE):
        width = 13 + 6.0 * len(label) + 16
        if x + width > WIDTH - RIGHT:
            x, row_y = float(LEFT), row_y + 14
        out.append(
            f'<rect class="{cls}" x="{x:.0f}" y="{row_y - 8}" width="10" height="8"'
            f' fill="{light}"/>'
        )
        out.append(
            f'<text class="ink2" x="{x + 13:.0f}" y="{row_y}" fill="#52514e"'
            f' font-size="10">{html.escape(label)}</text>'
        )
        x += width
    return out


def _first(r: Mapping[str, Any]) -> float:
    return min(float(v) for v in (r.get("t") or {"_": 0.0}).values())


def _last(r: Mapping[str, Any]) -> float:
    return max(float(v) for v in (r.get("t") or {"_": 0.0}).values())


def _tip(r: Mapping[str, Any]) -> str:
    parts = segments(r)
    said = ", ".join(f"{k} {round(v)} ms" for k, v in parts.items() if v >= 1)
    held = f", held by the {r['held']}" if r.get("held") else ""
    return (
        f"#{r.get('seq')} {r.get('kind')} {r.get('src')} ({r.get('end')}{held}): {said}"
    )


def overview_svg(
    records: Sequence[Mapping[str, Any]], found: Summary, wall: float | None
) -> str:
    """The whole stretch: per source, each update's time from the sound to
    the screen as a line (the worst in each pixel), hangs as red marks,
    stretches of sound without speech as a band under the lane."""
    times = [shown_at(r) for r in records]
    shown = [(t, r) for t, r in zip(times, records, strict=False) if t is not None]
    unheard = [r for r in records if r.get("kind") == UNHEARD and r.get("t")]
    if not shown and not unheard:
        return "<p>Nothing was shown.</p>"
    edges = [t for t, _ in shown]
    edges += [_first(r) for r in unheard] + [_last(r) for r in unheard]
    start, end = min(edges), max(edges)
    sources = sorted(
        {str(r.get("src") or "?") for _, r in shown}
        | {str(r.get("src") or "?") for r in unheard}
    )
    lane = 96
    height = 34 + lane * len(sources) + 30
    out = [
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} {height}"'
            f' width="{WIDTH}" height="{height}" font-family="Segoe UI"'
            ' font-size="11">'
        ),
        f'<rect class="bg" width="{WIDTH}" height="{height}" fill="#fcfcfb"/>',
        (
            f'<text class="ink" x="{LEFT}" y="14" font-size="13" font-weight="600"'
            f' fill="#0b0b0b">From the sound to the screen, each update (the worst in'
            f" each pixel); hangs in red - {_clock(start, wall)} to {_clock(end, wall)}"
            "</text>"
        ),
    ]
    out += _axis(start, end, 24, height - 30)
    worst = max((segments(r).get("total", 0.0) for _, r in shown), default=1.0)
    top_ms = max(2000.0, min(worst, 6000.0))
    for i, s in enumerate(sources):
        y0 = 30 + i * lane
        base = y0 + lane - 10
        out.append(
            f'<text class="ink2" x="6" y="{y0 + 14}" fill="#52514e">{html.escape(s)}'
            f'</text><text class="ink3" x="6" y="{base}" fill="#8a8984"'
            f' font-size="10">0 - {top_ms / 1000:g} s</text>'
        )
        pixels: dict[int, float] = {}
        for t, r in shown:
            if str(r.get("src") or "?") != s:
                continue
            px = round(_x(t, start, end))
            total = segments(r).get("total", 0.0)
            pixels[px] = max(pixels.get(px, 0.0), total)
        for px, total in sorted(pixels.items()):
            bar = min(1.0, total / top_ms) * (lane - 40)
            out.append(
                f'<line class="g1" x1="{px}" x2="{px}" y1="{base}" y2="{base - bar:.1f}"'
                ' stroke="#2a78d6" stroke-width="1"/>'
            )
        out += _unheard_lane(
            [r for r in unheard if str(r.get("src") or "?") == s],
            start,
            end,
            y0 + 18,  # under the name, above the tallest bar
        )
        for h in found.hangs:
            if h.source == s:
                x = _x(h.at, start, end)
                out.append(
                    f'<path d="M{x:.1f},{y0 + 2}l-4,-7h8z" fill="{HANG}">'
                    f"<title>hang {h.seconds:.1f} s at {_clock(h.at, wall)}:"
                    f" {h.cause}</title></path>"
                )
    out.append("</svg>")
    return "\n".join(out)


def _clock(at: float, wall: float | None) -> str:
    """`at` (the app's clock) as a time of day, if the source had one."""
    if wall is None:
        return f"{at:.1f} s"
    return datetime.fromtimestamp(at + wall).strftime("%H:%M:%S")


def page(
    records: Sequence[Mapping[str, Any]],
    found: Summary,
    kind: str,
    name: str,
    wall: float | None,
    worst: int = 12,
) -> tuple[str, list[tuple[str, str]]]:
    """The page, and its close-ups as (name, svg) for pictures."""
    closeups = []
    longest = sorted(found.hangs, key=lambda h: -h.seconds)
    picked = [h for h in longest if h.cause != UNHEARD][:worst]
    picked += [h for h in longest if h.cause == UNHEARD][:UNHEARD_CLOSEUPS]
    for n, h in enumerate(picked):
        start = h.at - h.seconds - 3.0
        end = h.at + 2.0
        title = (
            f"Hang {h.seconds:.1f} s at {_clock(h.at, wall)} ({h.source}): {h.cause}"
        )
        closeups.append(
            (
                f"hang-{n + 1:02d}",
                window_svg(records, start, end, found.hangs, found.bursts, title),
            )
        )
    last = [shown_at(r) for r in records]
    end_at = max((t for t in last if t is not None), default=0.0)
    closeups.append(
        (
            "last-30s",
            window_svg(
                records,
                end_at - 30,
                end_at + 0.5,
                found.hangs,
                found.bursts,
                f"The last 30 s, to {_clock(end_at, wall)}",
            ),
        )
    )
    causes = found.hang_causes()
    rows = "".join(
        f"<tr><td>{html.escape(s)}</td>"
        + "".join(
            f"<td>{_ms(percentile(found.by_segment.get(s, []), p))}</td>"
            for p in (50, 95, 99)
        )
        + f"<td>{causes.get(s, 0) or ''}</td></tr>"
        for s in (*SEGMENTS, "total")
        if s in found.by_segment
    )
    drops = ", ".join(f"{k} {v}" for k, v in found.drops.most_common()) or "none"
    held = ", ".join(f"{k} {v}" for k, v in found.held.most_common()) or "none"
    other = ", ".join(
        f"{c} {n}" for c, n in causes.most_common() if c not in found.by_segment
    )
    body = [
        f"<h1>Caption timelines: {html.escape(name)}</h1>",
        f"<p class=note>From {html.escape(kind)}."
        + (
            " The older caption log has the send, the answer and the moment a"
            " caption was applied only: what comes before the send and after"
            " the apply isn't split (grey)."
            if kind == "caption log"
            else ""
        )
        + " Times and counts only.</p>",
        '<div class="tiles">'
        + _tile("updates", found.updates)
        + _tile("shown", found.shown)
        + _tile("hangs over 2 s", len(found.hangs))
        + _tile("bursts", len(found.bursts))
        + _tile("dropped", sum(found.drops.values()))
        + _tile("sound without speech", found.unheard.stretches)
        + "</div>",
        f"<p>Dropped: {html.escape(drops)}. Held by a caption window:"
        f" {html.escape(held)}."
        + (f" Hangs not put down to a segment: {html.escape(other)}." if other else "")
        + "</p>",
        (
            "<p>Sound without speech (over 3 s of sound at -45 dBFS or more"
            " that speech detection never heard as speech - music, a game's"
            f" sound, or speech it missed): {html.escape(found.unheard.said())}."
            " Heard just after the reset: speech heard within a second of"
            " speech detection forgetting its state, so it had most likely"
            " stopped hearing it.</p>"
        ),
        "<h2>Where the time went</h2>",
        (
            "<table><tr><th>segment</th><th>p50</th><th>p95</th><th>p99</th>"
            f"<th>hangs it held</th></tr>{rows}</table>"
        ),
        "<h2>Overview</h2>",
        overview_svg(records, found, wall),
        "<h2>The worst hangs, close up</h2>"
        if found.hangs
        else "<h2>No hangs over 2 s</h2>",
        (
            "<p class=note>Each bar is one update, from the end of its speech to"
            " the screen; each tick on a source's track is a moment the screen"
            " changed. A red band: nothing new shown for over 2 s while the"
            " speech went on, or sound went on that wasn't heard as speech"
            " (the lane under it). Hover a bar for its segments.</p>"
        ),
        *(svg for _, svg in closeups),
    ]
    return _document(name, "\n".join(body)), closeups


def _tile(label: str, value: int) -> str:
    return f'<div class="tile"><b>{value}</b><span>{label}</span></div>'


def _ms(value: float | None) -> str:
    return "-" if value is None else f"{round(value)} ms"


def _document(name: str, body: str) -> str:
    dark = "".join(
        f".{c}{{fill:{d};stroke:{d}}}"
        for c, _, _, d in (*GROUPS, PAUSE, PACE, UNSPLIT, UNHEARD_LANE)
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Caption timelines</title>
<style>
:root {{ --bg:#fcfcfb; --ink:#0b0b0b; --ink2:#52514e; --line:#e6e5e0; }}
@media (prefers-color-scheme: dark) {{
  :root {{ --bg:#1a1a19; --ink:#f0efec; --ink2:#c3c2b7; --line:#3a3936; }}
  svg .bg {{ fill:#1a1a19 }} svg .ink {{ fill:#f0efec }} svg .ink2 {{ fill:#c3c2b7; stroke:#c3c2b7 }}
  svg .ink3 {{ fill:#9a9990 }} svg .track {{ fill:#26261f }} svg .grid {{ stroke:#2e2d2a }}
  svg .tick {{ stroke:#f0efec }} {dark}
}}
body {{ background:var(--bg); color:var(--ink); font:14px/1.45 "Segoe UI", sans-serif;
  margin:0 auto; padding:16px; max-width:1140px; }}
h1 {{ font-size:20px; margin:8px 0 }} h2 {{ font-size:16px; margin:24px 0 8px }}
.note {{ color:var(--ink2) }}
svg {{ max-width:100%; height:auto; display:block; margin:8px 0 18px }}
table {{ border-collapse:collapse; font-variant-numeric:tabular-nums }}
td, th {{ padding:3px 12px 3px 0; text-align:right; border-bottom:1px solid var(--line) }}
td:first-child, th:first-child {{ text-align:left }}
.tiles {{ display:flex; gap:12px; flex-wrap:wrap; margin:12px 0 }}
.tile {{ border:1px solid var(--line); border-radius:8px; padding:8px 14px; min-width:96px }}
.tile b {{ display:block; font-size:22px }} .tile span {{ color:var(--ink2); font-size:12px }}
</style></head><body>
<!-- {html.escape(name)} -->
{body}
</body></html>
"""
