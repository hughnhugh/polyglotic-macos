"""Each caption update's timeline, from the sound to the screen (polyglotic-hq 543, decision 0255).

The user, 2026-11-20: "it will often delay and then process it all at
once ... Can we measure end to end from client to server and render?"
The caption log (`core.listening.delays`) had the round trip and the
moment a caption was applied, but not what came before the send or after
the apply. A **trace** is one record per speech frame the timing asked
for - a live update or finished speech - with the moment it passed each
stage, on the app's monotonic clock (`time.perf_counter`, the captures'
own):

- `captured` - the end of its speech: when the last sample was heard
  (WASAPI's packet time);
- `heard` - the end of the frame that made the timing decide: the same
  for a live update, later for finished speech (the pause it waited for);
- `delivered` - the capture callback that carried that frame began (the
  capture's lag: the audio engine's buffer and the capture thread's wake);
- `detected` - speech detection and the timing decided to send it;
- `encoded` - its audio cut and encoded;
- `taken` - the send loop took it from the pipeline (latest wins there:
  one overtaken before it was taken ends `overtaken_in_app`);
- `sent` - the speech frame was handed to the connection;
- `received` - its answer was read off the connection, on the network
  thread;
- `handed` - the interface thread began applying the answer;
- `applied` - the caption feed applied it;
- `released` - in a paced caption mode (Steady), the playout let it out:
  each word is shown a set delay after it was said, and the record's
  `pace` is that delay (polyglotic-hq 551: Steady's own pace had counted
  as a caption window's hold); not passed in a mode without one;
- `windowed` - a caption window put it into its view: at once, or after
  the mouse over the window let it in (`held` `mouse`) or the Lab's gap
  between new captions did (`held` `gap`);
- `painted` - a caption window painted after that.

From the server (its decision 0104), echoed in the answer by the frame's
number (`seq`): the time it waited in the session's queue, the frames
waiting then, each stage's time and the whole server time - so the
network's share is the round trip less the server's, with no clock sync.
And the server says which numbered live updates it never answered, and
why.

**Content-free.** Numbers, the caption's random id (its first 8
characters, enough to group a caption's updates), the speech's kind and
section, the source's category and fixed words for outcomes. Never text,
audio, an app's name or a source's id.

**Sound without speech** (polyglotic-hq 549, decision 0256). A trace sees
only what was sent, so a source that played sound speech detection never
heard as speech - a song's band, a game's music, or speech the detector
missed - left nothing in it, and a 28 s gap with nothing sent couldn't be
told from silence. Each such stretch over 3 s (`platform.sound_unheard`)
is a record of its own, kind `UNHEARD`: when it began and ended, its
level's p10, p50 and p90 in dBFS, how many times speech detection forgot
its state in it (decision 0254) and how long after the last of them it
ended, and what ended it. Levels and times only, never audio. A stretch
still going on is in `recent` as it stands (`end` `open`).

**Where records go.** A record is done when it's painted, applied with no
window showing its source, dropped, or `DONE_AFTER_SEC` old. Done records
are kept in memory for the last `KEEP_SEC` ("Report a problem" attaches
them), counted into the session's summary (`perf.trace_summary`), and -
when the owner's PC asked for the detail (`main`: the `trace-detail`
marker) - written as JSON lines to the rolling trace file by the logger
`TRACE_LOG`.

Thread-safe: the captures', the session's and the interface threads all
mark stages. One lock, held for dictionary updates only.
"""

import json
import logging
import threading
import time
from collections import OrderedDict, deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

TRACE_LOG = "polyglotic_desktop.trace"
"""The rolling trace file's logger: one JSON line per done record."""

APP_STAGES = (
    "captured",
    "heard",
    "delivered",
    "detected",
    "encoded",
    "taken",
    "sent",
    "received",
    "handed",
    "applied",
    "released",
    "windowed",
    "painted",
)
"""The app's stages, in the order an update passes them."""

KEEP_SEC = 300.0
"""Done records kept in memory: the last 5 minutes ("Report a problem")."""
DONE_AFTER_SEC = 30.0
"""A record nothing has marked for this long is done as it stands (an
update no window showed, an answer that never came)."""
OPEN_MOST = 2000
"""Open records at most: the oldest is done early past it."""
PRE_SEND_MOST = 200
"""Decisions waiting for their send at most (overtaken ones fall out)."""

log = logging.getLogger(TRACE_LOG)

SpeechKey = tuple[str, str, int | None, float]
"""A decision before it has a number: its caption, kind, section and
speech end (ms-rounded) - what the pipeline and the session both know."""


def speech_key(
    caption_id: str, kind: str, section: int | None, speech_end: float
) -> SpeechKey:
    return (caption_id, kind, section, round(speech_end, 3))


UNHEARD = "sound_unheard"
"""The kind of a record of sound without speech (decision 0256)."""


@dataclass(frozen=True)
class Unheard:
    """A stretch of sound without speech on one source (module docstring):
    `began` and `ended` on the app's clock; `dbfs` its frames' level (root
    mean square) at p10, p50 and p90; `resets` the times speech detection
    forgot its state in it, `after_reset` the seconds from the last of them
    to its end (None without one); `end` what ended it - `speech` heard,
    `quiet` (the sound stopped), `stopped` (the source did) or `open` (it
    goes on)."""

    source: str
    began: float
    ended: float
    dbfs: tuple[int, int, int]
    resets: int
    after_reset: float | None
    end: str

    @property
    def seconds(self) -> float:
        return self.ended - self.began

    def as_json(self) -> dict[str, Any]:
        return {
            "kind": UNHEARD,
            "src": self.source,
            "t": {"began": round(self.began, 4), "ended": round(self.ended, 4)},
            "len": round(self.seconds, 2),
            "dbfs": list(self.dbfs),
            "resets": self.resets,
            "after_reset": None
            if self.after_reset is None
            else round(self.after_reset, 2),
            "end": self.end,
        }


@dataclass
class Record:
    """One speech frame's timeline. `t`: each stage's moment (seconds,
    the app's clock); `server`: the server's numbers (milliseconds, and
    `queued` frames); `end`: how it ended (`painted`, `applied`,
    `unanswered:<why>`, `overtaken_in_app`, `not_sent:<why>`, `lost`);
    `pace`: the playout's delay it was let out at (seconds; `released`)."""

    seq: int | None
    caption: str
    kind: str
    section: int | None
    source: str
    audio: float
    t: dict[str, float] = field(default_factory=dict)
    server: dict[str, int] = field(default_factory=dict)
    held: str | None = None
    end: str | None = None
    last: float = 0.0
    pace: float | None = None

    def as_json(self) -> dict[str, Any]:
        found: dict[str, Any] = {
            "seq": self.seq,
            "cap": self.caption,
            "kind": self.kind,
            "sec": self.section,
            "src": self.source,
            "audio": round(self.audio, 2),
            "t": {k: round(v, 4) for k, v in self.t.items()},
            "end": self.end,
        }
        if self.server:
            found["srv"] = dict(self.server)
        if self.held is not None:
            found["held"] = self.held
        if self.pace is not None:
            found["pace"] = round(self.pace, 2)
        return found


class Tracer:
    """The process's caption updates' timelines (module docstring)."""

    def __init__(
        self,
        clock: Callable[[], float] = time.perf_counter,
        keep_sec: float = KEEP_SEC,
    ) -> None:
        self.clock = clock
        self.keep_sec = keep_sec
        self.detail = False
        """Write each done record to the rolling trace file (`TRACE_LOG`)."""
        self._lock = threading.Lock()
        self._pre: OrderedDict[SpeechKey, dict[str, float]] = OrderedDict()
        self._open: OrderedDict[int, Record] = OrderedDict()
        self._unpainted: list[int] = []
        self._done: deque[dict[str, Any]] = deque()
        self._next_seq = 0
        self._swept = 0.0
        self._listeners: list[Callable[[dict[str, Any]], None]] = []
        self._sounding: dict[int, dict[str, Any]] = {}
        """Stretches of sound without speech going on now, by their key."""
        self.stalls: deque[tuple[float, float]] = deque(maxlen=512)
        """Interface-thread stalls: (when, ms) - the watchdog's."""

    # -- listeners: the session's summary, the problem report ------------------

    def listen(self, listener: Callable[[dict[str, Any]], None]) -> None:
        """`listener` hears each done record (as JSON), on whichever thread
        finished it. It must be quick and must not mark stages."""
        with self._lock:
            self._listeners.append(listener)

    def unlisten(self, listener: Callable[[dict[str, Any]], None]) -> None:
        with self._lock:
            if listener in self._listeners:
                self._listeners.remove(listener)

    # -- the pipeline (capture threads) ----------------------------------------

    def decided(
        self, key: SpeechKey, delivered: float, detected: float, heard: float
    ) -> None:
        """A decision was made at `detected`, at the frame that ended at
        `heard` (the capture's clock), from audio delivered at `delivered`."""
        with self._lock:
            self._pre[key] = {
                "captured": key[3],
                "heard": heard,
                "delivered": delivered,
                "detected": detected,
            }
            while len(self._pre) > PRE_SEND_MOST:
                self._pre.popitem(last=False)

    def encoded(self, key: SpeechKey, at: float) -> None:
        with self._lock:
            found = self._pre.get(key)
            if found is not None:
                found["encoded"] = at

    def sounding(self, key: int, stretch: Unheard) -> None:
        """A stretch of sound without speech goes on, as it stands now
        (`key`: its tracker's, the same until it ends): `recent` has it."""
        found = stretch.as_json()
        with self._lock:
            self._sounding[key] = found

    def unheard(self, key: int, stretch: Unheard) -> None:
        """A stretch of sound without speech ended: done, as a record."""
        found = stretch.as_json()
        with self._lock:
            self._sounding.pop(key, None)
            self._publish_locked(found)

    # -- the session (its own thread) --------------------------------------------

    def sending(
        self,
        key: SpeechKey,
        source: str,
        audio: float,
        taken: float,
    ) -> int:
        """The send loop took the decision `key`: its number (`seq`), sent
        with it. Decisions for the same caption, kind and section made
        before it and never taken were overtaken in the app."""
        caption, kind, section, end = key
        with self._lock:
            seq = self._next_seq
            self._next_seq += 1
            stages = self._pre.pop(key, None) or {"captured": end}
            for older in [k for k in self._pre if k[:3] == key[:3] and k[3] <= end]:
                gone = self._pre.pop(older)
                self._finish_locked(
                    Record(None, caption[:8], kind, section, source, 0.0, t=gone),
                    "overtaken_in_app",
                )
            record = Record(seq, caption[:8], kind, section, source, audio, t=stages)
            record.t["taken"] = taken
            record.last = taken
            self._open[seq] = record
            while len(self._open) > OPEN_MOST:
                _, oldest = self._open.popitem(last=False)
                self._finish_locked(oldest, "lost")
        return seq

    def mark(self, seq: int | None, stage: str, at: float | None = None) -> None:
        """`seq` passed `stage` at `at` (now if None)."""
        if seq is None:
            return
        now = self.clock() if at is None else at
        with self._lock:
            record = self._open.get(seq)
            if record is None:
                return
            record.t.setdefault(stage, now)
            record.last = now
            self._sweep_locked(now)

    def answered(
        self,
        seq: int,
        received: float,
        server: Mapping[str, int] | None,
        unanswered: Mapping[int, str] | None = None,
    ) -> None:
        """Its answer was read at `received`; `server`: the server's numbers
        (milliseconds; None from a server before decision 0104);
        `unanswered`: the numbered live updates the server says it won't
        answer, and why."""
        with self._lock:
            record = self._open.get(seq)
            if record is not None:
                record.t.setdefault("received", received)
                record.last = received
                if server:
                    record.server.update(server)
            for other, why in (unanswered or {}).items():
                dropped = self._open.pop(other, None)
                if dropped is not None:
                    self._finish_locked(dropped, f"unanswered:{why}")
            self._sweep_locked(received)

    def not_sent(self, key: SpeechKey, why: str) -> None:
        """The session dropped the decision instead of sending it."""
        with self._lock:
            stages = self._pre.pop(key, None)
            if stages is not None:
                caption, kind, section, _ = key
                self._finish_locked(
                    Record(None, caption[:8], kind, section, "", 0.0, t=stages),
                    f"not_sent:{why}",
                )

    def dropped(self, seq: int | None, why: str) -> None:
        """A sent frame that won't be answered (an error, given up)."""
        if seq is None:
            return
        with self._lock:
            record = self._open.pop(seq, None)
            if record is not None:
                self._finish_locked(record, why)

    # -- the interface thread ----------------------------------------------------

    def held(self, seq: int | None, why: str) -> None:
        """A caption window kept it waiting: `mouse` or `gap`."""
        if seq is None:
            return
        with self._lock:
            record = self._open.get(seq)
            if record is not None and record.held is None:
                record.held = why

    def released(self, seq: int | None, pace: float, at: float | None = None) -> None:
        """The playout let it out (a paced mode), `pace` seconds after its
        words were said: what it waited for was the mode's own pace."""
        if seq is None:
            return
        now = self.clock() if at is None else at
        with self._lock:
            record = self._open.get(seq)
            if record is None or "released" in record.t:
                return
            record.t["released"] = now
            record.pace = pace
            record.last = now

    def windowed(self, seq: int | None, at: float | None = None) -> None:
        """A caption window put it into its view; it shows at the next paint."""
        if seq is None:
            return
        now = self.clock() if at is None else at
        with self._lock:
            record = self._open.get(seq)
            if record is None or "windowed" in record.t:
                return
            record.t["windowed"] = now
            record.last = now
            self._unpainted.append(seq)

    def painted(self, at: float | None = None) -> None:
        """A caption window painted: what was windowed before shows now."""
        if not self._unpainted:
            return
        now = self.clock() if at is None else at
        with self._lock:
            waiting, self._unpainted = self._unpainted, []
            for seq in waiting:
                record = self._open.pop(seq, None)
                if record is not None:
                    record.t.setdefault("painted", now)
                    self._finish_locked(record, "painted")
            self._sweep_locked(now)

    def stalled(self, ms: float) -> None:
        """The interface thread was busy `ms` (the watchdog's report)."""
        with self._lock:
            self.stalls.append((self.clock(), ms))

    # -- reading -------------------------------------------------------------------

    def recent(self, seconds: float = KEEP_SEC) -> list[dict[str, Any]]:
        """Done records of the last `seconds`, oldest first (as JSON), then
        the stretches of sound without speech going on now."""
        now = self.clock()
        with self._lock:
            self._sweep_locked(now, force=True)
            done = [r for r in self._done if _ended_at(r) >= now - seconds]
            return done + [dict(r) for r in self._sounding.values()]

    def open_now(self) -> list[dict[str, Any]]:
        """The records not done yet, as they stand (as JSON) - left open:
        what a session's summary counts at its end."""
        with self._lock:
            found = []
            for record in self._open.values():
                now = record.as_json()
                now["end"] = _ending(record)
                found.append(now)
            return found

    def sounding_now(self) -> list[dict[str, Any]]:
        """The stretches of sound without speech going on now (as JSON)."""
        with self._lock:
            return [dict(r) for r in self._sounding.values()]

    def flush(self) -> None:
        """Every open record done as it stands (a session's end)."""
        with self._lock:
            for record in list(self._open.values()):
                self._finish_locked(record, _ending(record))
            self._open.clear()
            self._unpainted.clear()

    # -- inside the lock ----------------------------------------------------------

    def _sweep_locked(self, now: float, force: bool = False) -> None:
        """Records nothing marked for `DONE_AFTER_SEC` are done; done ones
        older than `keep_sec` are forgotten. At most once a second."""
        if not force and now - self._swept < 1.0:
            return
        self._swept = now
        stale = [s for s, r in self._open.items() if now - r.last >= DONE_AFTER_SEC]
        for seq in stale:
            record = self._open.pop(seq)
            self._finish_locked(record, _ending(record))
        for key in [
            k for k, r in self._sounding.items() if now - _ended_at(r) >= DONE_AFTER_SEC
        ]:  # given as it stood, then never ended: its source went
            del self._sounding[key]
        while self._done and _ended_at(self._done[0]) < now - self.keep_sec:
            self._done.popleft()

    def _finish_locked(self, record: Record, end: str) -> None:
        record.end = end
        self._publish_locked(record.as_json())

    def _publish_locked(self, found: dict[str, Any]) -> None:
        """A done record (as JSON): kept, heard by the listeners, and
        written to the trace file when asked."""
        self._done.append(found)
        for listener in self._listeners:
            try:
                listener(found)
            except Exception:
                logging.getLogger(__name__).exception("a trace listener failed")
        if self.detail:
            log.info(json.dumps(found, separators=(",", ":")))


def _ending(record: Record) -> str:
    """How an open record ends when it's done as it stands."""
    if "applied" in record.t:
        return "applied"  # no window showed its source
    if "received" in record.t:
        return "received"
    return "lost"  # no answer came


def _ended_at(found: Mapping[str, Any]) -> float:
    times = found.get("t") or {}
    return max(times.values(), default=0.0)


_tracer = Tracer()


def tracer() -> Tracer:
    """The process's tracer (as `logging.getLogger` gives a logger)."""
    return _tracer


def use(new: Tracer) -> Tracer:
    """Makes `new` the process's tracer (tests); returns the one before."""
    global _tracer
    before, _tracer = _tracer, new
    return before
