"""What a stretch of caption timelines says: where the time went, the hangs, the bursts, the drops.

Reads the records `perf.trace` makes (as JSON) - the session's, the last
5 minutes' or a trace file's - and gives (polyglotic-hq 543, decision
0255):

- **Segments** of each update, in milliseconds: `pause` (finished
  speech waiting for the pause that ends it; 0 for a live update),
  `capture` (the sound to the capture callback), `detect` (speech detection and the timing),
  `encode`, `app_queue` (waiting for the send loop), `send`, `network`
  (the round trip less the server's time; from a server before its
  decision 0104, less its `processing_ms` only - its queue counted in
  here), `server_queue` (waiting behind other frames on the
  server), `server_work`, `interface_queue` (the answer waiting for the
  interface thread), `apply`, `pace` (a paced mode's playout keeping it
  for its words' moments: Steady's own delay, polyglotic-hq 551),
  `window_hold` (a caption window keeping it: the mouse over it, the
  Lab's gap) and `paint`; and `total`, from the sound to the screen.
- **Hangs:** a source showing nothing new for over `HANG_SEC` while its
  speech went on - from the last update shown, or from the next one's
  speech starting if that came later, until the next one shows. In a
  paced mode a word is meant to show its pace after it was said: the
  speech's start counts from then, so a hang is only what's beyond the
  pace (551: Steady's 1.75 s at the start of every utterance had made
  2.0-2.8 s "hangs" of the window's). A source's first update, with none
  before it, is measured from its speech's start, and is a hang only when
  something held it - any cause but `not_asked` (polyglotic-hq 566: a
  problem report's first update on a source, held 20.8 s under the mouse,
  was missed). Each is put down to one **cause**: `dropped` (an update in
  between never showed: overtaken in the app or on the server, or lost),
  `not_asked` (nothing was asked in between - the next one showed within
  `QUICK_SEC` of its decision, its pace aside: the speech paused, or the
  caption mode's schedule, as Steady's whole sentences), or the segment
  that held the next one longest - never the pace. A stretch of **sound
  without speech** (`perf.trace.Unheard`, polyglotic-hq 549) is a hang of
  its own, put down to `sound_unheard`: sound went on and nothing was
  heard as speech - music, a game's sound, or speech that detection
  missed; the stretch's levels and resets help tell which.
- **Bursts:** `BURST_SIZE` or more updates shown within `BURST_SEC`.
- **Drops:** updates that ended without being shown, by why.

Plain Python: numbers in, numbers out; nothing here reads a clock.
"""

import json
import math
import random
import threading
from collections import Counter, deque
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from polyglotic_desktop.perf.trace import APP_STAGES, UNHEARD, Tracer

HANG_SEC = 2.0
"""Nothing new shown for longer than this while the speech goes on."""
BURST_SEC = 0.3
BURST_SIZE = 3
"""This many updates shown within `BURST_SEC`: a burst."""
QUICK_SEC = 1.0
"""An update shown within this long of its decision wasn't held anywhere:
a hang before it was nothing asked."""
SAMPLES_KEPT = 4096
"""Each segment's values kept for its percentiles, at most."""
MIN_UNHEARD_SEC = 3.0
"""A stretch of sound without speech over this long counts
(`platform.sound_unheard.MIN_SEC`, which this module can't import)."""
HEARD_AFTER_RESET_SEC = 1.0
"""A stretch of sound without speech that ended with speech this soon
after speech detection forgot its state (decision 0254) was most likely
speech the detector had stopped hearing."""

SEGMENTS = (
    "pause",
    "capture",
    "detect",
    "encode",
    "app_queue",
    "send",
    "network",
    "server_queue",
    "server_work",
    "interface_queue",
    "apply",
    "pace",
    "window_hold",
    "paint",
)
"""An update's segments, in the order it passes them."""

_SPANS = {
    "pause": ("captured", "heard"),
    "capture": ("heard", "delivered"),
    "detect": ("delivered", "detected"),
    "encode": ("detected", "encoded"),
    "app_queue": ("encoded", "taken"),
    "send": ("taken", "sent"),
    "interface_queue": ("received", "handed"),
    "apply": ("handed", "applied"),
    "pace": ("applied", "released"),
    "window_hold": ("released", "windowed"),
    "paint": ("windowed", "painted"),
}

SHOWN_ENDS = ("painted", "applied")


def shown_at(record: Mapping[str, Any]) -> float | None:
    """When the update showed: painted, else windowed, else applied."""
    times = record.get("t") or {}
    for stage in ("painted", "windowed", "applied"):
        if stage in times:
            return float(times[stage])
    return None


def segments(record: Mapping[str, Any]) -> dict[str, float]:
    """The update's segments it passed, in milliseconds (`total` too)."""
    times: Mapping[str, float] = record.get("t") or {}
    found: dict[str, float] = {}
    for name, (start, end) in _SPANS.items():
        if start == "released" and start not in times:
            start = "applied"  # a mode without a pace: held by the window alone
        if start in times and end in times:
            found[name] = max(0.0, (times[end] - times[start]) * 1000)
    if "sent" in times and "received" in times:
        trip = max(0.0, (times["received"] - times["sent"]) * 1000)
        server: Mapping[str, int] = record.get("srv") or {}
        if "server" in server:
            found["network"] = max(0.0, trip - server["server"])
            found["server_queue"] = float(server.get("waited", 0))
            found["server_work"] = max(
                0.0, float(server["server"]) - server.get("waited", 0)
            )
        elif "processing" in server:  # a server before its decision 0104
            found["network"] = max(0.0, trip - server["processing"])  # and its queue
            found["server_work"] = float(server["processing"])
        else:
            found["network"] = trip  # the round trip, unsplit
    shown = shown_at(record)
    if shown is not None and "captured" in times:
        found["total"] = max(0.0, (shown - times["captured"]) * 1000)
    return found


def percentile(values: Sequence[float], p: float) -> float | None:
    """The `p`th percentile (nearest rank); None for no values."""
    if not values:
        return None
    ordered = sorted(values)
    rank = max(0, min(len(ordered) - 1, math.ceil(p / 100 * len(ordered)) - 1))
    return ordered[rank]


@dataclass(frozen=True)
class Hang:
    """A source showing nothing new for `seconds` while its speech went on,
    ending at `at` (the app's clock) with update `seq`, put down to `cause`."""

    at: float
    seconds: float
    source: str
    cause: str
    seq: int | None


@dataclass
class Summary:
    """A stretch of timelines, summarised as they come (module docstring):
    `add` each done record in the order they're done - the tracer's
    order, or a file's. Keeps at most `SAMPLES_KEPT` of each segment's
    values (every one until then, then a fair sample), so a long session
    stays small."""

    updates: int = 0
    shown: int = 0
    by_segment: dict[str, list[float]] = field(default_factory=dict)
    hangs: list[Hang] = field(default_factory=list)
    bursts: list[tuple[float, int]] = field(default_factory=list)
    drops: Counter[str] = field(default_factory=Counter)
    held: Counter[str] = field(default_factory=Counter)
    unheard: "UnheardCounts" = field(default_factory=lambda: UnheardCounts())
    _seen: dict[str, int] = field(default_factory=dict)
    _last: dict[str, tuple[float, Mapping[str, Any]]] = field(default_factory=dict)
    _lost: dict[str, deque[float]] = field(default_factory=dict)
    _recent: deque[float] = field(default_factory=lambda: deque(maxlen=BURST_SIZE * 4))
    _burst_open: float | None = None
    _random: random.Random = field(default_factory=lambda: random.Random(543))

    def add(self, record: Mapping[str, Any]) -> None:
        """One done record."""
        if record.get("kind") == UNHEARD:
            self._unheard(record)
            return
        self.updates += 1
        end = str(record.get("end") or "")
        source = str(record.get("src") or "")
        if record.get("held"):
            self.held[str(record["held"])] += 1
        at = shown_at(record)
        if at is None or end not in SHOWN_ENDS:
            self.drops[end.split(":", 1)[-1] or "lost"] += 1
            captured = (record.get("t") or {}).get("captured")
            if captured is not None:
                self._lost.setdefault(source, deque(maxlen=64)).append(float(captured))
            return
        self.shown += 1
        for name, ms in segments(record).items():
            self._sample(name, ms)
        self._hang(source, at, record)
        self._burst(at)

    def p(self, segment: str, pct: float) -> float | None:
        return percentile(self.by_segment.get(segment, []), pct)

    def hang_causes(self) -> Counter[str]:
        return Counter(h.cause for h in self.hangs)

    def _sample(self, name: str, ms: float) -> None:
        values = self.by_segment.setdefault(name, [])
        seen = self._seen[name] = self._seen.get(name, 0) + 1
        if len(values) < SAMPLES_KEPT:
            values.append(ms)
        else:  # a fair sample of all of them (reservoir sampling)
            slot = self._random.randrange(seen)
            if slot < SAMPLES_KEPT:
                values[slot] = ms

    def _unheard(self, record: Mapping[str, Any]) -> None:
        """A stretch of sound without speech: a hang put down to it."""
        times = record.get("t") or {}
        if "ended" not in times or "began" not in times:
            return
        ended, seconds = (
            float(times["ended"]),
            float(times["ended"]) - float(times["began"]),
        )
        self.unheard.add(record, seconds)
        self.hangs.append(
            Hang(ended, seconds, str(record.get("src") or ""), UNHEARD, None)
        )

    def _hang(self, source: str, at: float, record: Mapping[str, Any]) -> None:
        last = self._last.get(source)
        if last is not None and at < last[0]:
            return  # done late (no window showed it): not in the source's line
        self._last[source] = (at, record)
        start = _speech_start(record)
        if start is None:
            return
        start += float(record.get("pace") or 0.0)  # when it was meant to show
        # nothing new on the screen since the last update showed, or since
        # this one's speech began, whichever came later; the source's first
        # from its speech's start (566)
        since = start if last is None else max(last[0], start)
        if at - since <= HANG_SEC:
            return
        cause = _cause(record, since, at, self._lost.get(source, ()))
        if last is None and cause == "not_asked":
            return  # nothing held it: the caption mode's schedule, the speech
        self.hangs.append(Hang(at, at - since, source, cause, record.get("seq")))

    def _burst(self, at: float) -> None:
        self._recent.append(at)
        within = [t for t in self._recent if at - t <= BURST_SEC]
        if len(within) < BURST_SIZE:
            self._burst_open = None
            return
        if self._burst_open is None or at - self._burst_open > BURST_SEC:
            self._burst_open = within[0]
            self.bursts.append((within[0], len(within)))
        else:
            self.bursts[-1] = (self.bursts[-1][0], self.bursts[-1][1] + 1)


@dataclass
class UnheardCounts:
    """The stretches of sound without speech in a stretch of timelines:
    how many, their seconds, the longest; how many had speech detection
    forget its state in them (`with_reset`, decision 0254), and how many
    ended with speech within `HEARD_AFTER_RESET_SEC` of that
    (`heard_after_reset`: the detector most likely deaf until then)."""

    stretches: int = 0
    seconds: float = 0.0
    longest: float = 0.0
    with_reset: int = 0
    heard_after_reset: int = 0

    def add(self, record: Mapping[str, Any], seconds: float) -> None:
        self.stretches += 1
        self.seconds += seconds
        self.longest = max(self.longest, seconds)
        if record.get("resets"):
            self.with_reset += 1
            after = record.get("after_reset")
            if (
                record.get("end") == "speech"
                and after is not None
                and float(after) <= HEARD_AFTER_RESET_SEC
            ):
                self.heard_after_reset += 1

    def said(self) -> str:
        """In a few words, for a summary line."""
        if not self.stretches:
            return "sound unheard: none"
        return (
            f"sound unheard {self.stretches} over 3 s ({self.seconds:.0f} s,"
            f" longest {self.longest:.1f} s; {self.with_reset} with the reset,"
            f" {self.heard_after_reset} heard just after it)"
        )


def summarise(records: Iterable[Mapping[str, Any]]) -> Summary:
    """Segments, hangs, bursts and drops of `records`, taken in the order
    they were done (module docstring)."""
    found = Summary()
    for record in sorted(records, key=_done_at):
        found.add(record)
    return found


def _done_at(record: Mapping[str, Any]) -> float:
    times = record.get("t") or {}
    return max((float(v) for v in times.values()), default=0.0)


def _speech_start(record: Mapping[str, Any]) -> float | None:
    times = record.get("t") or {}
    if "captured" not in times:
        return None
    return float(times["captured"]) - float(record.get("audio") or 0.0)


def _cause(
    b: Mapping[str, Any], since: float, shown: float, lost: Iterable[float]
) -> str:
    """Why nothing new showed from `since` until `b` did at `shown` (module
    docstring): an update in between dropped; nothing asked (`b` itself
    showed within `QUICK_SEC` of its decision, its pace aside); or `b`'s
    longest segment but its pace."""
    times = b.get("t") or {}
    if any(since < c < shown for c in lost):
        return "dropped"
    # the frame that decided it; an older log has only the send, just after
    decided = float(times.get("heard", times.get("sent", times.get("captured", shown))))
    parts = segments(b)
    paced = parts.pop("pace", 0.0) / 1000
    if shown - decided - paced < QUICK_SEC:
        return "not_asked"
    parts.pop("total", None)
    if not parts:
        return "unknown"
    return max(parts.items(), key=lambda kv: kv[1])[0]


USAGE_SEGMENTS = (
    "capture",
    "detect",
    "app_queue",
    "network",
    "server_queue",
    "server_work",
    "interface_queue",
    "window_hold",
    "total",
)
"""The segments the usage statistics carry, p50 and p95 each."""

HANG_CAUSES = (
    "dropped",
    "not_asked",
    *(s for s in SEGMENTS if s != "pace"),
    "unknown",
    UNHEARD,
)
"""A hang's causes - never the pace (a paced mode's own; polyglotic-server's
tracking plan has no `hangs_pace`)."""


def usage_properties(found: Summary, stalls: int) -> dict[str, int]:
    """The tracking plan's `caption_timeline_summarised` properties:
    whole milliseconds and counts only (polyglotic-server's
    docs/tracking-plan.yaml)."""
    props: dict[str, int] = {
        "updates": found.updates,
        "shown": found.shown,
        "hangs": len(found.hangs),
        "bursts": len(found.bursts),
        "drops": sum(found.drops.values()),
        "held_mouse": found.held.get("mouse", 0),
        "held_gap": found.held.get("gap", 0),
        "interface_stalls": stalls,
    }
    for segment in USAGE_SEGMENTS:
        for pct in (50, 95):
            value = found.p(segment, pct)
            if value is not None:
                props[f"{segment}_p{pct}_ms"] = round(value)
    causes = found.hang_causes()
    for cause in HANG_CAUSES:
        if causes.get(cause):
            props[f"hangs_{cause}"] = causes[cause]
    return props


class SessionTimelines:
    """A listening session's caption timelines, summarised as they're done
    (the tracer's listener) - for its usage statistics. From any thread."""

    def __init__(self, tracer: Tracer) -> None:
        self._tracer = tracer
        self._lock = threading.Lock()
        self.summary = Summary()
        self.started: float | None = None
        self.stopped: float | None = None

    def start(self) -> None:
        self.started = self._tracer.clock()
        self._tracer.listen(self._add)

    def stop(self) -> None:
        """The session's end: its updates already shown but not done yet
        (waiting for a paint, or no window showed their source) are counted
        as they stand; those still on their way aren't. So is a stretch of
        sound without speech going on, from the session's start at the
        earliest."""
        if self.started is None or self.stopped is not None:
            return
        self.stopped = self._tracer.clock()
        self._tracer.unlisten(self._add)
        for record in self._tracer.open_now():
            taken = (record.get("t") or {}).get("taken")  # sent in this session
            if (
                record["end"] == "applied"
                and taken is not None
                and taken >= self.started
            ):
                self._add(record)
        for record in self._tracer.sounding_now():
            times = record.get("t") or {}
            if float(times.get("ended", 0.0)) - self.started > MIN_UNHEARD_SEC:
                began = max(float(times.get("began", 0.0)), self.started)
                self._add({**record, "t": {**times, "began": began}})

    def stalls(self) -> int:
        """The interface thread's stalls while the session listened."""
        if self.started is None:
            return 0
        end = self.stopped if self.stopped is not None else self._tracer.clock()
        return sum(
            1 for at, _ in list(self._tracer.stalls) if self.started <= at <= end
        )

    def seconds(self) -> float:
        if self.started is None:
            return 0.0
        end = self.stopped if self.stopped is not None else self._tracer.clock()
        return max(0.0, end - self.started)

    def _add(self, record: Mapping[str, Any]) -> None:
        with self._lock:
            self.summary.add(record)


REPORT_HEADER = "--- caption timelines (perf.trace): times and counts only ---"
"""Where the timelines start in a problem report's log (tools.trace reads it)."""


def compact(record: Mapping[str, Any]) -> list[Any]:
    """One record as a short JSON array for a problem report: `[seq,
    caption, kind, section, source, audio, end, held, captured, [each
    APP_STAGES' milliseconds after captured, or null], server, pace]`; a
    stretch of sound without speech as `["sound_unheard", source, began,
    ended, [dBFS p10, p50, p90], resets, after_reset, end]`."""
    times: Mapping[str, float] = record.get("t") or {}
    if record.get("kind") == UNHEARD:
        return [
            UNHEARD,
            record.get("src"),
            round(float(times.get("began", 0.0)), 3),
            round(float(times.get("ended", 0.0)), 3),
            record.get("dbfs"),
            record.get("resets"),
            record.get("after_reset"),
            record.get("end"),
        ]
    zero = times.get("captured")
    offsets = [
        None
        if zero is None or stage not in times
        else round((float(times[stage]) - zero) * 1000)
        for stage in APP_STAGES
    ]
    return [
        record.get("seq"),
        record.get("cap"),
        record.get("kind"),
        record.get("sec"),
        record.get("src"),
        record.get("audio"),
        record.get("end"),
        record.get("held"),
        None if zero is None else round(float(zero), 3),
        offsets,
        record.get("srv") or {},
        record.get("pace"),
    ]


_BEFORE_PACE = tuple(stage for stage in APP_STAGES if stage != "released")
"""The stages a report's rows have from an app before 551's `released`."""


def expand(row: Sequence[Any]) -> dict[str, Any]:
    """A `compact` row back as a record - an older app's too (no pace)."""
    if row and row[0] == UNHEARD:
        _, src, began, ended, levels, resets, after, end = row
        return {
            "kind": UNHEARD,
            "src": src,
            "t": {"began": began, "ended": ended},
            "len": round(ended - began, 2),
            "dbfs": levels,
            "resets": resets,
            "after_reset": after,
            "end": end,
        }
    seq, cap, kind, sec, src, audio, end, held, zero, offsets, server = row[:11]
    pace = row[11] if len(row) > 11 else None
    stages = APP_STAGES if len(offsets) == len(APP_STAGES) else _BEFORE_PACE
    times: dict[str, float] = {}
    if zero is not None:
        for stage, ms in zip(stages, offsets, strict=False):
            if ms is not None:
                times[stage] = float(zero) + ms / 1000
    found: dict[str, Any] = {
        "seq": seq,
        "cap": cap,
        "kind": kind,
        "sec": sec,
        "src": src,
        "audio": audio,
        "t": times,
        "end": end,
    }
    if server:
        found["srv"] = dict(server)
    if held is not None:
        found["held"] = held
    if pace is not None:
        found["pace"] = pace
    return found


def report_text(records: Sequence[Mapping[str, Any]], limit: int) -> str:
    """The timelines for a problem report's log, at most `limit`
    characters: a header, a line of what they say, then one `compact` row
    a line - the newest that fit."""
    found = summarise(records)
    causes = ", ".join(f"{c} {n}" for c, n in found.hang_causes().most_common())
    total50, total95 = found.p("total", 50), found.p("total", 95)
    said = (
        f"# {found.updates} updates, {found.shown} shown,"
        f" {len(found.hangs)} hangs ({causes or 'none'}), {len(found.bursts)} bursts,"
        f" {sum(found.drops.values())} drops;"
        f" sound to screen p50 {_ms(total50)} p95 {_ms(total95)};"
        f" {found.unheard.said()}"
    )
    head = [REPORT_HEADER, said]
    rows: list[str] = []
    size = sum(len(line) + 1 for line in head)
    for record in reversed(records):
        line = json.dumps(compact(record), separators=(",", ":"))
        if size + len(line) + 1 > limit:
            break
        rows.append(line)
        size += len(line) + 1
    if len(rows) < len(records):  # the note of what's left out fits too
        note = ""
        while rows:
            note = f"# the oldest {len(records) - len(rows)} left out (size)"
            if size + len(note) + 1 <= limit:
                break
            size -= len(rows.pop()) + 1  # the oldest kept
        head.append(note or f"# the oldest {len(records)} left out (size)")
    return "\n".join([*head, *reversed(rows)]) + "\n"


def _ms(value: float | None) -> str:
    return "-" if value is None else f"{round(value)} ms"
