"""Compare public replay frame dumps, and audit the reference's own invariants."""

import argparse
import json
import math
import re
from collections import Counter, defaultdict
from collections.abc import Iterator
from itertools import combinations, zip_longest
from pathlib import Path

from tools.video_motion.ink import audit, late, row_ink

POSITION_PX = 2.0
EVENT_FRAMES = 1
SPEED_FRACTION = 0.10
ALPHA_TOLERANCE = 1 / 255  # one eight-bit coverage level
VISIBLE_ALPHA = 0.002  # the reference drawRow's cutoff
EPS = 1e-7  # floating-point noise in pixel differences


def visible_rows(frame: dict) -> list[dict]:
    return [r for r in frame["rows"] if r["alpha"] > VISIBLE_ALPHA and r["text"]]


def visible(frame: dict) -> dict[tuple, dict]:
    return {
        (r["id"], r["kind"], r["index"], r["phase"] == "ghost"): r
        for r in visible_rows(frame)
    }


def overlaps(a: dict, b: dict, width: float, height: float) -> bool:
    return (
        min(width, a["x"] + a["w"], b["x"] + b["w"]) > max(0, a["x"], b["x"]) + EPS
        and min(height, a["y"] + a["h"], b["y"] + b["h"]) > max(0, a["y"], b["y"]) + EPS
    )


def premature_cuts(dump: dict, max_wait: float) -> Iterator[tuple[str, int]]:
    """A cut before the reading wait cap is a release failure, even during a fade."""
    starts = {e["frame"] for e in dump.get("events", []) if e["text"] == "wait starts"}
    ends = {e["frame"] for e in dump.get("events", []) if e["text"] == "wait ends"}
    cuts = {e["frame"] for e in dump.get("events", []) if "is cut short" in e["text"]}
    waiting = None
    for frame in sorted(starts | ends | cuts):
        if frame in starts:
            waiting = frame
        if (
            frame in cuts
            and max_wait > 0
            and (waiting is None or frame - waiting < max_wait * dump["fps"] - EPS)
        ):
            yield "unread cut before cap", frame
        if frame in ends:
            waiting = None


def invariants(dump: dict, settings: dict) -> Iterator[tuple[str, int]]:
    if "catchupMs" in settings:
        if "ink" not in dump and "glyphInk" not in dump:
            yield "missing word ink", 0
        else:
            exposures, _ = audit(dump)
            for item in late(exposures, settings["catchupMs"] / 1000):
                frame = (
                    math.ceil(item.clock * dump["fps"] - EPS)
                    if math.isfinite(item.clock)
                    else dump["frames"][-1]["frame"]
                )
                yield "word ink late or missing", frame
    if "maxWait" in settings:
        yield from premature_cuts(dump, settings["maxWait"])
    previous: dict[tuple, dict] = {}
    settled: dict[tuple, int] = {}
    previous_mode = dump.get("mode")
    previous_sides = [True, True]
    ink = row_ink(dump)
    shown = set()
    for frame in dump["frames"]:
        f, rows = frame["frame"], visible(frame)
        mode = frame.get("mode", previous_mode)
        sides = frame.get("sides", previous_sides)
        if frame.get("inkOverlap"):
            yield "glyph ink overlap", f
        if frame.get("readingInkClipped"):
            yield "reading glyph ink clipped vertically", f
        if frame.get("duplicateInk"):
            yield "duplicate glyph ink", f
        if any(
            overlaps(a, b, settings["W"], settings["H"])
            and not (
                "minHold" not in settings
                and a["id"] == b["id"]
                and {a["phase"], b["phase"]} == {"ghost", "settled"}
            )
            for a, b in combinations(visible_rows(frame), 2)
        ):
            yield "overlap", f
        if mode == previous_mode and sides == previous_sides and "minHold" in settings:
            for key, start in settled.items():
                if (f - start) / dump["fps"] + EPS >= settings["minHold"]:
                    continue
                previous_row, new = previous[key], rows.get(key)
                if (
                    new is None
                    or any(
                        abs(new[axis] - previous_row[axis]) > EPS for axis in ("x", "y")
                    )
                    or new["text"].rstrip() != previous_row["text"].rstrip()
                ):
                    yield "finished line moved before minimum settle", f
        settled = {
            key: settled.get(key, f)
            if (
                (mode == previous_mode and sides == previous_sides)
                or (
                    (before := previous.get(key)) is not None
                    and before["text"].rstrip() == r["text"].rstrip()
                    and all(abs(before[a] - r[a]) <= EPS for a in ("x", "y"))
                )
            )
            else f
            for key, r in rows.items()
            if r["phase"] == "settled"
        }
        for key, r in rows.items():
            if r.get("inkClipped"):
                yield "vertical glyph ink clipped", f
            if settled_ink_clipped(r, ink, settings["W"]):
                yield "settled glyph ink clipped horizontally", f
            if (
                r["phase"] == "live"
                and "scrolling" in r
                and not r["scrolling"]
                and horizontal_ink_clipped(r, ink, settings["W"])
            ):
                yield "live glyph ink clipped horizontally", f
            if r["y"] < -EPS or r["y"] + r["h"] > settings["H"] + EPS:
                yield "row clipped vertically", f
            if r["kind"] == "original" and r["phase"] != "ghost":
                shown.add(r["id"])
            old = previous.get(key)
            if (
                old
                and r["phase"] == old["phase"] == "live"
                and "catchupStep" in settings
                and abs(r["x"] - old["x"]) > settings["catchupStep"] + EPS
            ):
                yield "one-frame glide exceeds cap", f
            if old and r["y"] > old["y"] + EPS:
                yield "downward", f
            if (
                old
                and mode == previous_mode == "instant"
                and abs(r["x"] - old["x"]) > EPS
            ):
                yield "Instant sideways movement", f
            if r["px"] != settings["origPx" if r["kind"] == "original" else "transPx"]:
                yield "squeeze", f
        previous = rows
        previous_mode, previous_sides = mode, sides
    if any(c["id"] not in shown for c in dump.get("source", [])):
        yield "caption never shown", dump["frames"][-1]["frame"]


def settled_ink_clipped(row: dict, ink: dict | list | None, width: int) -> bool:
    if row["phase"] != "settled" or row.get("compact"):
        return False
    return horizontal_ink_clipped(row, ink, width)


def horizontal_ink_clipped(row: dict, ink: dict | list | None, width: int) -> bool:
    left, right = row.get("horizontalClip", (0, width))
    left, right = max(0, left), min(width, right)
    if ink is None:
        return row["x"] < left - EPS or row["x"] + row["w"] > right + EPS
    key = row.get("inkIndex", (row["kind"], False, row["text"]))
    return any(
        row["x"] + start < left - EPS or row["x"] + end > right + EPS
        for _, start, end in ink[key]
    )


def return_invariants(dump: dict, scenario: dict) -> Iterator[tuple[str, int]]:
    """Audit the interaction independently of the two renderers' positions."""
    actions = scenario["actions"]
    first = actions["live"]
    frames = dump["frames"]
    for action, state in (
        ("scroll", "history"),
        ("hold", "holding"),
        ("leave", "history"),
        ("live", "live"),
    ):
        f = actions[action]
        if frames[f].get("view") != state:
            yield f"view after {action}", f

    width, height = dump["size"]
    ink = row_ink(dump)
    watched = scenario["wrappedCaption"]
    translation = next(c["zh"] for c in dump["source"] if c["id"] == watched)
    wrapped = False
    for frame in frames:
        f = frame["frame"]
        rows = visible_rows(frame)
        if any(settled_ink_clipped(row, ink, width) for row in rows):
            yield "settled glyph ink clipped horizontally", f
        if any(
            row["phase"] == "settled"
            and (
                row.get("inkClipped")
                or row["y"] < -EPS
                or row["y"] + row["h"] > height + EPS
            )
            for row in rows
        ):
            yield "settled glyph ink clipped vertically", f
        if f < first:
            continue
        if frame.get("inkOverlap"):
            yield "glyph ink overlaps after returning live", f
        if frame.get("duplicateInk"):
            yield "caption painted twice after returning live", f
        if any(overlaps(a, b, width, height) for a, b in combinations(rows, 2)):
            yield "overlap after returning live", f
        target = [
            row
            for row in rows
            if row["id"] == watched
            and row["kind"] == "translation"
            and row["phase"] == "settled"
            and not row.get("compact")
        ]
        if len(target) > 1:
            text = " ".join(
                row["text"].strip() for row in sorted(target, key=lambda r: r["index"])
            )
            wrapped |= text == translation and not any(
                settled_ink_clipped(row, ink, width) or row.get("inkClipped")
                for row in target
            )
    if not wrapped and dump.get("mode") != "scrolling":
        yield "return never showed the complete wrapped translation", first


def geometry_events(dump: dict) -> dict[tuple, list[int]]:
    """Transitions independently visible in the reference and app paint data."""
    times: defaultdict[tuple, list[int]] = defaultdict(list)
    previous: dict[tuple, dict] = {}
    moving: set[tuple] = set()
    for frame in dump["frames"]:
        f, rows = frame["frame"], visible(frame)
        for key, r in rows.items():
            if key[1:] != ("original", 0, False):
                continue
            old = previous.get(key)
            if not times[(key[0], "first words")]:
                times[(key[0], "first words")].append(f)
            if r["phase"] == "settled" and (not old or old["phase"] != "settled"):
                times[(key[0], "settle")].append(f)
            lifting = old and old["y"] - r["y"] > EPS
            if lifting and key not in moving:
                times[(key[0], "lift start")].append(f)
                moving.add(key)
            if not lifting and key in moving:
                times[(key[0], "lift end")].append(f)
                moving.remove(key)
            if (
                old
                and old["alpha"] >= 1 - EPS
                and r["alpha"] < old["alpha"] - EPS
                and lifting
            ):
                times[(key[0], "pass")].append(f)
        for key in tuple(moving):
            if key not in rows:
                times[(key[0], "lift end")].append(f)
                moving.remove(key)
        previous = rows
    return dict(times)


def first_words(dump: dict) -> dict[tuple, int]:
    """First inclusion in a painted row; its tail can extend beyond the viewport."""
    first: dict[tuple, int] = {}
    for frame in dump["frames"]:
        groups: defaultdict[tuple, list[str]] = defaultdict(list)
        for r in visible(frame).values():
            if r["phase"] != "ghost":
                groups[r["id"], r["kind"]].append(r["text"])
        for key, lines in groups.items():
            # Include repeats and individual unspaced Han characters.
            seen: Counter = Counter()
            for word in re.findall(
                r"[\u3400-\u9fff]|[^\s\u3400-\u9fff]+", " ".join(lines)
            ):
                seen[word] += 1
                first.setdefault((*key, word, seen[word]), frame["frame"])
    return first


def compare(reference: dict, app: dict) -> Iterator[tuple[str, int]]:
    settings = reference["settings"]
    if (
        app.get("size") != [settings["W"], settings["H"]]
        or app["fps"] != reference["fps"]
    ):
        yield "viewport or frame rate", 0
    previous: dict[tuple, tuple[dict, dict]] = {}
    for expected, actual in zip_longest(reference["frames"], app["frames"]):
        if not expected or not actual or expected["frame"] != actual["frame"]:
            yield "missing frame", (expected or actual)["frame"]
            continue
        f = actual["frame"]
        target, measured = visible(expected), visible(actual)
        if target.keys() != measured.keys():
            yield "missing or extra rows", f
        current = {}
        for key in target.keys() & measured.keys():
            a, b = target[key], measured[key]
            if a["text"] != b["text"]:
                yield "text", f
            if abs(a["alpha"] - b["alpha"]) > ALPHA_TOLERANCE:
                yield "opacity", f
            if (
                "fadeWidth" in a
                and abs(a["fadeWidth"] - b.get("fadeWidth", 0)) > POSITION_PX
            ):
                yield "edge fade", f
            if a["phase"] != b["phase"]:
                yield "phase", f
            if any(abs(a[v] - b[v]) > POSITION_PX + EPS for v in ("x", "y", "h")):
                yield "position", f
            if key in previous:
                last_a, last_b = previous[key]
                for axis, name in (("x", "glide speed"), ("y", "lift speed")):
                    da, db = a[axis] - last_a[axis], b[axis] - last_b[axis]
                    # At fixed FPS, comparing signed px/frame is equivalent to px/s.
                    if abs(da - db) > SPEED_FRACTION * abs(da) + EPS:
                        yield name, f
            current[key] = a, b
        previous = current
    measured_words = first_words(app)
    for key, f in first_words(reference).items():
        if measured_words.get(key, math.inf) > f:
            yield "word late or missing", f
    target_events, actual_events = geometry_events(reference), geometry_events(app)
    for key in target_events.keys() | actual_events.keys():
        for expected_f, actual_f in zip_longest(
            target_events.get(key, []), actual_events.get(key, [])
        ):
            if (
                expected_f is None
                or actual_f is None
                or abs(expected_f - actual_f) > EVENT_FRAMES
            ):
                yield (
                    "event " + key[1],
                    expected_f if expected_f is not None else actual_f,
                )

    # Wait/cut are scheduler decisions. Never infer a successful cut solely
    # from a missing row: the scheduler must emit its actual decision.
    def holds(dump: dict) -> dict[str, list[int]]:
        times: defaultdict[str, list[int]] = defaultdict(list)
        for e in dump.get("events", []):
            if "wait" in e["text"] or "cut short" in e["text"]:
                times[e["text"]].append(e["frame"])
        return times

    target_holds, actual_holds = holds(reference), holds(app)
    for label in target_holds.keys() | actual_holds.keys():
        for a_hold, b_hold in zip_longest(
            target_holds.get(label, []), actual_holds.get(label, [])
        ):
            if a_hold is None or b_hold is None or abs(a_hold - b_hold) > EVENT_FRAMES:
                yield "event wait/cut", a_hold if a_hold is not None else b_hold
    yield from invariants(app, settings)


def counts(failures: Iterator[tuple[str, int]]) -> dict:
    frames: defaultdict[str, set[int]] = defaultdict(set)
    for label, f in failures:
        frames[label].add(f)
    return {
        label: {"frames": len(found), "first": min(found)}
        for label, found in sorted(frames.items())
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folders", type=Path, nargs="+")
    parser.add_argument("--reference-only", action="store_true")
    args = parser.parse_args()
    failed = False
    for folder in args.folders:
        ref = json.loads((folder / "reference.json").read_text(encoding="utf-8"))
        scenario = ref.get("scenario")
        returning = scenario and "live" in scenario["actions"]
        result = {
            "reference": counts(
                return_invariants(ref, scenario)
                if returning
                else invariants(ref, ref["settings"])
            )
        }
        if not args.reference_only:
            actual = json.loads((folder / "app.json").read_text(encoding="utf-8"))
            result["app"] = counts(
                return_invariants(actual, scenario)
                if returning
                else compare(ref, actual)
            )
        failed |= any(result.values())
        (folder / "comparison.json").write_text(
            json.dumps(result, indent=2), encoding="utf-8"
        )
        print(folder.name, {side: len(count) for side, count in result.items()})
    raise SystemExit(int(failed))
