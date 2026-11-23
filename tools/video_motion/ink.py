"""Measure arrival against shaped word ink and the first unobstructed live row."""

import json
import math
import re
from collections import Counter, defaultdict
from collections.abc import Iterator
from dataclasses import dataclass
from statistics import median

TOKEN = re.compile(r"[\u3400-\u9fff]|[^\s\u3400-\u9fff]+")
EPS = 1e-7
VISIBLE_ALPHA = 0.002


def occurrences(text: str) -> Iterator[tuple[str, int]]:
    counts: Counter[str] = Counter()
    for token in TOKEN.findall(text):
        counts[token] += 1
        yield token, counts[token]


def _arrivals(caption: dict, live_translation: bool, kind: str):
    if "arrivals" in caption:
        yield from caption["arrivals"][kind]
        return
    if kind == "original":
        for update in caption["updates"]:
            yield update["t"], " ".join(w["t"] for w in update["words"])
        yield caption["finishT"], caption["en"]
    else:
        if live_translation:
            for reply in caption.get("tupdates", ()):
                if round(reply["t"], 9) < round(caption["finishT"], 9):
                    yield reply["t"], "".join(w["t"] for w in reply["chars"])
        yield caption["transT"], caption["zh"]


def clearance(dump: dict, caption: dict, arrival: float) -> float:
    """First eligible paint, before the new caption's entrance animation."""
    fps = dump["fps"]
    top = dump["liveTop"]
    first = math.ceil(arrival * fps - EPS)
    for frame in dump["frames"][first:]:
        admitted = frame.get("admitted")
        if admitted is not None:
            clear = caption["id"] in admitted
        else:
            clear = not any(
                row["id"] < caption["id"]
                and row["alpha"] > VISIBLE_ALPHA
                and row["y"] + row["h"] > top + EPS
                for row in frame["rows"]
            )
        if clear:
            return arrival if frame["frame"] == first else frame["frame"] / fps
    return math.inf


def _visible_words(
    rows: list[dict],
    ink: dict | list,
    width: int,
    prefixes: dict[tuple[int, str], str] | None = None,
):
    groups = defaultdict(list)
    for r in rows:
        if r["alpha"] > VISIBLE_ALPHA:
            phase = r["phase"] if prefixes is None else None
            groups[r["id"], r["kind"], phase].append(r)
    found = set()
    for (caption, kind, _phase), lines in groups.items():
        track = (caption, kind)
        first = min(r["start"] for r in lines) if prefixes is not None else 0
        text = (
            prefixes.get(track, "")[:first].ljust(first) if prefixes is not None else ""
        )
        hidden = []
        for r in sorted(lines, key=lambda row: row["index"]):
            if prefixes is not None:
                text = text[: r["start"]].ljust(r["start"])
            elif text and kind == "original":
                text += " "
            offset = len(text)
            text += r["text"]
            key = kind, r["phase"] != "settled", r["text"]
            for match, (word, left, right) in zip(
                TOKEN.finditer(r["text"]), ink[r.get("inkIndex", key)], strict=True
            ):
                if word != match.group():
                    raise ValueError("Mismatched ink measurement")
                if r["x"] + left < -EPS or r["x"] + right > width + EPS:
                    hidden.append((offset + match.start(), offset + match.end()))
        if prefixes is not None:
            prefixes[track] = text
        for match, identity in zip(
            TOKEN.finditer(text), occurrences(text), strict=True
        ):
            if match.start() >= first and not any(
                lo < match.end() and hi > match.start() for lo, hi in hidden
            ):
                found.add((caption, kind, *identity))
    return found


@dataclass
class Exposure:
    caption: int
    kind: str
    token: tuple[str, int]
    clock: float
    until: float
    shown: float | None = None


def row_ink(dump: dict) -> dict | list | None:
    if "glyphInk" in dump:
        return dump["glyphInk"]
    if "ink" in dump:
        return {tuple(json.loads(key)): value for key, value in dump["ink"].items()}
    return None


def audit(dump: dict) -> tuple[list[Exposure], list[float]]:
    """Coalesce superseded revisions in a blocked row at its clearance time."""
    ink = row_ink(dump)
    assert ink is not None
    fps = dump["fps"]
    exposures = []
    queues = []
    for c in dump["source"]:
        original = list(_arrivals(c, False, "original"))
        arrival = original[0][0]
        clear = clearance(dump, c, arrival)
        queues.append(clear - arrival)
        for kind in ("original", "translation"):
            active: dict[tuple[str, int], Exposure] = {}
            for at, text in _arrivals(
                c, dump["mode"] in ("live", "instant", "scrolling"), kind
            ):
                current = set(occurrences(text))
                for token in active.keys() - current:
                    active.pop(token).until = at
                for token in current - active.keys():
                    item = Exposure(c["id"], kind, token, max(clear, at), math.inf)
                    active[token] = item
                    exposures.append(item)

    def eligible(e: Exposure) -> bool:
        if math.isinf(e.clock):
            return True
        first = math.ceil(e.clock * fps - EPS)
        seconds = dump["settings"].get("catchupMs", 200) / 1000
        last = min(len(dump["frames"]), math.floor((e.clock + seconds) * fps + EPS) + 1)
        side = int(e.kind == "translation")
        return e.until > e.clock + EPS and all(
            frame.get("sides", [True, True])[side]
            for frame in dump["frames"][first:last]
        )

    exposures = [e for e in exposures if eligible(e)]
    by_word = defaultdict(list)
    for e in exposures:
        by_word[e.caption, e.kind, *e.token].append(e)
    prefixes: dict[tuple[int, str], str] | None = (
        {} if "minHold" in dump["settings"] else None
    )
    for frame in dump["frames"]:
        now = frame["frame"] / fps
        for word in _visible_words(frame["rows"], ink, dump["settings"]["W"], prefixes):
            for e in by_word.get(word, ()):
                if e.shown is None and e.clock - EPS <= now < e.until:
                    e.shown = now
    return exposures, queues


def late(exposures: list[Exposure], seconds: float) -> Iterator[Exposure]:
    return (
        e for e in exposures if e.shown is None or e.shown - e.clock > seconds + EPS
    )


def queue_ms(queues: list[float]) -> tuple[float, float]:
    return round(median(queues) * 1000, 2), round(max(queues) * 1000, 2)
