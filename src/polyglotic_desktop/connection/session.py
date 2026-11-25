"""A session with the server: one WebSocket while the user listens, or a short sync session.

protocol.md, step by step. Opens `wss://<server>/v1/session` and says
`hello` with the device token and the session's purpose. A **listening
session**, on `welcome`, sends the user's `settings` and follows the pace
hint it carries. Then, until stopped:
- **speech out:** each decision the speech pipeline has waiting (latest
  wins there, so nothing piles up while the network is slow), as a binary
  speech frame or a `withdraw` message;
- **captions in:** each `caption_update`, as core's `CaptionUpdate`, to
  the listener - and `minutes`, `pace` and `notice` likewise; a finished
  caption that failed on the server (`processing_failed`) is told too, and
  so is a stalled connection - finished speech unanswered, or the server
  silent, for too long (core.listening.unstable) - and its end. Every
  finished caption that won't come - failed or refused on the server,
  given up, or never sent - is told by its id (`caption_dropped`), so the
  app ends its live caption: it stayed provisional for good (polyglotic-hq
  557, 529's B3);
- **keepalive:** `ping` every `limits.ping_seconds` (25); 60 seconds
  without any message from the server is a dead connection, closed and
  opened again;
- **reconnecting:** whenever a session ends, `Reconnects` says whether to
  back off and try again, or stop until the user acts (a new invite code,
  an update). A token the server refuses is forgotten. Waiting, the
  status says why the server couldn't be reached or ended the session,
  when that's known (`connection.failures`; polyglotic-hq 251). A
  listening session that fails in the app itself - an exception nobody
  foresaw, in the session or in reading the credentials - is logged by
  the exception's type and where (never its text) and tries again after
  `Reconnects.after_failure`'s wait: it stopped for good until the
  learner changed sources (polyglotic-hq 557, 529's B2; decision 0266);
- **learning data, consent, usage and exposures:** what the
  `DataExchange` has waiting goes out on every session, and its answers
  (`received`, `learning_state`, `learning_deleted`) go back to it.

A listening session keeps a content-free `SessionSummary` across its
reconnects (speech sent, captions back, errors, reconnects, and lookups
and saves while it's open - `learned`; what is captured - `captured` -
and what the learner did - `did`, and "Original only" from its settings,
polyglotic-hq project 134); `ended()` gives it once the session has
stopped.

A **sync session** (`purpose="sync"`, no speech) sends what the exchange
has waiting and syncs learning, then closes normally once everything is
answered - or after `Timings.sync_within`. It never reconnects by itself:
`connection.client` opens another when something waits again.

**Resuming** (server decision 0040): a reconnect's `hello` names the
listening session it had (`resume`, the last `welcome.session_id`), and
the server carries that session's captions on - their translation's
context, a caption's earlier live sections - if it lost it less than two
minutes ago; `welcome.resumed` says whether it did. Either way the new
session starts with `settings` and the unanswered speech.

Speech that waits while the connection is down stays in the pipeline and
goes out when it's back (up to two minutes of it: `core.listening.pending`).
Finished speech the server hasn't answered when a
connection drops - even a frame being sent at that moment - is kept in
memory (`UnansweredSpeech`) and sent again first on the next session.
An `error` naming a caption whose finished speech is unanswered answers
it if it says it refused finished speech (`kind`, from a server since
2026-11-11) or can only be about finished speech
(`FINISHED_SPEECH_ONLY`); otherwise it may be one of the caption's live
updates, refused (project 127). Finished speech that won't be answered -
speech sent after it has been, or it's too old to show - is given up and
counted dropped, so it doesn't hold the stall up (polyglotic-hq 271).


**Stopping drains:** finished speech still waiting in the pipeline (or to
be sent again) goes out, and its answers are awaited for up to
`Timings.drain_within`, before the session closes - so the last thing said
before the user stops is still captioned (project 031). Live updates
still waiting are dropped. Stopped while the connection is down, the
speech waiting is dropped with the session (memory only) - unless a newer
listening session takes it on: once stopped, a session `hand_over`s the
finished speech it never had answered, and the next one `take_on`s it
and sends it again first (polyglotic-hq 277: when what's captured
changes, the server closes the old session as the new one's `hello`
arrives, and the old one's wait ended at once).

Runs on asyncio in a thread of its own (decision 0012), so the Qt thread
and the capture threads never wait on the network: they call `start`,
`stop`, `speech_ready` and `change_settings`, which return at once. The
listener is called on the session's thread - `main` passes what the UI
needs over to the Qt thread.

Logs states, close codes and error codes only: never caption text,
audio, settings or the token.
"""

import asyncio
import contextlib
import logging
import ssl
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any, Protocol

from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import (
    ConnectionClosed,
    InvalidHandshake,
    InvalidProxy,
    InvalidURI,
)

from polyglotic_desktop.connection import listening, protocol, tls
from polyglotic_desktop.connection.addresses import SECURE, server_address
from polyglotic_desktop.connection.app import AppInfo
from polyglotic_desktop.connection.exchange import DataExchange
from polyglotic_desktop.connection.failures import (
    ANNOUNCED_GOING_AWAY,
    why_closed,
    why_not_opened,
    why_refused,
)
from polyglotic_desktop.connection.reconnect import (
    NO_CLOSE_FRAME,
    NORMAL,
    Ended,
    Reconnects,
    Refusal,
    RetryIn,
    Stop,
    StopReason,
)
from polyglotic_desktop.connection.unanswered import Handed, UnansweredSpeech
from polyglotic_desktop.core.listening import delays, unstable
from polyglotic_desktop.core.listening import maintenance as planned
from polyglotic_desktop.core.listening.captions import (
    CaptionKind,
    CaptionUpdate,
    SpeechTimes,
)
from polyglotic_desktop.core.listening.held_back import (
    LIVE_UPDATES_HELD_BACK,
    HeldBack,
)
from polyglotic_desktop.core.listening.maintenance import Maintenance
from polyglotic_desktop.core.listening.pace import WordCount, spaced_word_count
from polyglotic_desktop.core.listening.recheck import (
    ANSWER_WITHIN_SEC,
    RecheckRequest,
    RecheckResult,
)
from polyglotic_desktop.core.listening.settings import ListeningSettings
from polyglotic_desktop.core.listening.sources import Capture
from polyglotic_desktop.core.listening.summary import (
    ListeningSessionEnded,
    PresetStep,
    SessionAction,
    SessionSummary,
)
from polyglotic_desktop.core.listening.timing import (
    LIVE_UPDATE_INTERVAL_SEC,
    CaptionId,
    CaptionMode,
    Decision,
    SpeechKind,
    TranscriptionRequest,
)
from polyglotic_desktop.core.listening.unreachable import Unreachable, after_restart
from polyglotic_desktop.core.listening.unstable import stalled
from polyglotic_desktop.core.shared import LearningEvent, WordLookedUp, WordSaved
from polyglotic_desktop.core.shared.client import USER_AGENT
from polyglotic_desktop.perf import trace
from polyglotic_desktop.perf.trace_summary import SessionTimelines
from polyglotic_desktop.ports.credentials import CredentialStore, DeviceCredentials

log = logging.getLogger(__name__)
caption_log = logging.getLogger(delays.CAPTION_LOG)
SPEECH_TIMES_KEPT = 256
"""How many sent frames' times wait for an answer at most: live updates
that latest wins dropped are never answered, and mustn't pile up."""

_websocket_log = logging.getLogger(f"{__name__}.websocket")
# websockets logs every frame at DEBUG - hello's token, caption text. Its
# logger here never goes below INFO, whatever the app's logging is set to.
_websocket_log.setLevel(logging.INFO)

SpeechSource = Callable[[], tuple[Decision, bytes | None] | None]
"""Where speech waits to be sent: returns the next decision with its Ogg
Opus audio, or None (the speech pipeline's `take`)."""

MAX_MESSAGE_BYTES = 1 << 20  # the largest message accepted from the server
_NAMES = {"listen": "listening", "sync": "sync"}

FINISHED_SPEECH_ONLY = frozenset({"processing_failed"})
"""The `error` codes naming a caption that the server sends only for its
finished speech (protocol.md, 2026-11-07). The others that name one -
`settings_missing`, `codec_not_supported`, `speech_header_not_valid`,
`speech_not_decodable`, `speech_limit_reached` - and any code this app
doesn't know may be about a live update instead."""


class SessionState(StrEnum):
    CONNECTING = "connecting"
    LISTENING = "listening"
    WAITING = "waiting"  # to reconnect
    STOPPED = "stopped"


@dataclass(frozen=True, slots=True)
class Status:
    """Where the session is. `retry_in`: seconds until the next attempt
    (waiting). `stopped`: why it stopped. `close_code`: how the last
    connection ended. `session_id`: the server's id (listening).
    `channel`: the update channel the server says to follow (listening,
    from `welcome`; any string - the updater ignores channels it doesn't
    know). `account_id`: the account signed in, from `welcome` (None from
    a server before 2026-11-05), for the user to quote. `server_busy`:
    waiting because the server is full (it refused `hello` with
    `server_busy`), not because of the learner's connection (208). `tier`:
    the tier a listening session holds until it ends - its `welcome`'s
    plan's (None: the server didn't say). A plan that lowers it mid-session
    is shown at once, but the session keeps it (protocol.md, `plan`).
    `unreachable`: waiting, why the server couldn't be reached or ended
    the session, if that's known (connection.failures; polyglotic-hq 251).
    `source_fields`: listening, the optional fields of a speech header's
    `source` the server uses, from `welcome` (none from a server before
    2026-11-09); None when not listening (polyglotic-hq 263). `cohort`: the
    account's test group, from `welcome` (alpha testers get "Report a
    problem" with everything attached, polyglotic-hq 275)."""

    state: SessionState
    retry_in: float | None = None
    stopped: StopReason | None = None
    close_code: int | None = None
    session_id: str | None = None
    channel: str | None = None
    account_id: str | None = None
    server_busy: bool = False
    tier: str | None = None
    unreachable: Unreachable | None = None
    source_fields: tuple[str, ...] | None = None
    cohort: str | None = None
    clock_looks_wrong: bool = False
    """Listening, but let through only once the leaf's dates were checked
    against when the app was built, with this PC's time outside them: its
    date or time looks wrong (connection.tls, decision 0104; 313)."""


class SessionListener(Protocol):
    """What the session tells the rest of the app, on the session's thread."""

    def status_changed(self, status: Status) -> None: ...

    def caption_updated(self, update: CaptionUpdate) -> None: ...

    def pace_changed(self, live_interval_min: float | None) -> None:
        """The server's pace hint (None: none); the timing rules follow it."""
        ...

    def minutes_changed(self, used: float, left: float | None) -> None: ...

    def allowance_changed(
        self, allowance: protocol.AllowanceUpdate | protocol.AllowanceExhausted
    ) -> None: ...

    def notice(self, code: str) -> None:
        """Something to show, by protocol.md's code; unknown codes may come."""
        ...

    def connection_stalled(self, stalled: bool) -> None:
        """The connection is stalled (True) - finished speech unanswered, or
        the server silent, for too long - or answers flow again (False)
        (core.listening.unstable.stalled)."""
        ...

    def caption_failed(self) -> None:
        """A finished caption failed on the server (`error`
        `processing_failed`): it is counted dropped; several in a row mean
        captions are failing there (core.listening.failing)."""
        ...

    def caption_dropped(self, caption_id: CaptionId) -> None:
        """A caption's finished caption won't come: it failed or was refused
        on the server, was given up, or was never sent. Its live caption, if
        shown, is to end with what it shows (polyglotic-hq 557)."""
        ...

    def rechecked(self, result: RecheckResult) -> None:
        """The answer to a recheck ("Looks wrong?"): the best model's version
        of a line, or why there's none."""
        ...

    def plan_changed(self, plan: protocol.PlanState) -> None:
        """The account's plan, as the server states it: in `welcome`, then
        again whenever it changes (polyglotic-hq 178, 185)."""
        ...

    def maintenance_changed(self, window: Maintenance | None) -> None:
        """The planned maintenance window the app holds changed - told in
        `welcome`, a `maintenance` message or a refusal for it - or there's
        none now (core.listening.maintenance; polyglotic-hq 319)."""
        ...


@dataclass(frozen=True, slots=True)
class Timings:
    """protocol.md's numbers; tests shorten them."""

    dead_after: float = 60.0  # no message from the server for this long
    answer_within: float = 10.0  # connecting, and the answer to `hello`
    close_within: float = 2.0  # waiting for a closing handshake
    ping_every: float | None = None  # None: as `welcome.limits` says
    sync_within: float = 30.0  # a sync session closes after this, answered or not
    drain_within: float = 3.0  # stopping: wait this long for the last answers
    update_retry: float = 300.0
    """Update required, or Plus ended (4009): a listening session asks
    again this often, so the app listens again by itself once the server
    takes its version again (polyglotic-hq 137) - each refusal sends it to
    the updater again - or once the account has Plus again: nothing else
    is open to bring the new plan (polyglotic-hq 203)."""


def session_url(server: str) -> str:
    """The session's address from the server's: `https://host` ->
    `wss://host/v1/session`; `http://127.0.0.1:8080` -> `ws://...`. Plain
    `ws://` only to this PC (connection/addresses.py): the token is in `hello`."""
    scheme, _, rest = server_address(server).partition("://")
    websocket = "wss" if scheme in SECURE else "ws"
    return f"{websocket}://{rest}/v1/session"


def _close_code(closed: ConnectionClosed) -> int:
    return closed.rcvd.code if closed.rcvd is not None else NO_CLOSE_FRAME


def _no_speech() -> tuple[Decision, bytes | None] | None:
    return None


class ListeningSession:
    """One session with the server: a listening session, kept open until
    stopped, or (`purpose="sync"`) a sync session, closed once done."""

    def __init__(
        self,
        server: str,
        credentials: CredentialStore,
        app: AppInfo,
        settings: ListeningSettings,
        take_speech: SpeechSource,
        listener: SessionListener,
        *,
        timings: Timings | None = None,
        reconnects: Reconnects | None = None,
        exchange: DataExchange | None = None,
        purpose: protocol.Purpose = "listen",
        live_interval: float | None = LIVE_UPDATE_INTERVAL_SEC,
        caption_mode: CaptionMode | None = None,
        capture: Capture | None = None,
        maintenance: Maintenance | None = None,
        wall_clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        capture_restarts: Callable[[], int] | None = None,
        time_zone: str | None = None,
        count_words: WordCount = spaced_word_count,
    ) -> None:
        """`live_interval` is the live-update interval followed (None:
        none), `caption_mode` the learner's caption mode and `capture` what
        is captured as it starts (None: not known yet), for the session's
        summary; so is `capture_restarts`, the captures' restarts since it
        was last called (the speech pipeline's `take_restarts`; polyglotic-hq
        566). `maintenance`: the planned maintenance window the app
        holds as it starts (kept between starts; polyglotic-hq 319);
        `wall_clock`: this PC's time, which the window is placed against."""
        self._url = session_url(server)
        self._clock_looks_wrong = False
        """The last session's leaf let through with this PC's time outside
        its dates (connection.tls)."""
        self._exchange = exchange
        self._purpose: protocol.Purpose = purpose
        self._live_translation = False
        self._time_zone = time_zone
        self._capture_restarts = capture_restarts
        self.unanswered = UnansweredSpeech()
        """Finished speech sent and not yet answered, across reconnects."""
        self._handed: list[Handed] = []
        """Finished speech a session before this one never had answered,
        handed over from another thread (`take_on`): the session's own
        thread takes it into `unanswered` and sends it."""
        self._handed_lock = threading.Lock()
        self._held_back = HeldBack()
        self._summary = SessionSummary(
            live_interval,
            settings.targets[0] if settings.targets else None,
            caption_mode,
            capture,
            time.perf_counter(),
            count_words=count_words,
        )
        if settings.original_only:
            self._summary.did(SessionAction.ORIGINAL_ONLY)
        self._welcomes = 0
        self._lost_at: float | None = None
        """When the last session open ended (time.monotonic), until the
        next `welcome`: the log says how long the learner was without
        captions (polyglotic-hq 302)."""
        self._resume: str | None = None
        """The listening session to resume on the next connection."""
        self._again: list[bytes] = []
        self._rechecks: list[tuple[float, bytes]] = []  # when asked, the frame
        self._first: list[str] = []
        if purpose == "sync":
            take_speech = _no_speech
        self._credentials = credentials
        self._app = app
        self._settings = settings
        self._take_speech = take_speech
        self._listener = listener
        self._timings = timings or Timings()
        self._reconnects = reconnects or Reconnects()
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._started = threading.Event()
        self._last_heard = 0.0
        self._stalled = False  # as last told (`connection_stalled`)
        self._listening = False
        self._closed_with: int | None = None
        self._terminal: Refusal | None = None
        self._limits = protocol.Limits()
        self._stopped_for = StopReason.CLOSED  # what `stop` was asked for
        self._mode = caption_mode.usage_value if caption_mode is not None else None
        self._live_interval = live_interval
        self.preset_usage: dict[str, protocol.UsageValue] = {}
        """The preset in use as the session started, as its summary's
        optional properties (`ui.use_presets.usage`, polyglotic-hq 556):
        sent with it, with consent to usage statistics."""
        # the session's caption timelines, summarised for its usage
        # statistics (perf.trace; polyglotic-hq 543)
        self._timelines = SessionTimelines(trace.tracer())
        self._speech_sent: dict[tuple[str, str], tuple[float, float, float]] = {}
        # each numbered frame's speech times and when it went (perf.trace):
        # its answer names it, so a live update's round trip is its own
        self._sent_by_seq: dict[int, tuple[float, float, float]] = {}
        # each caption's latest numbered frame of each kind: what an answer
        # from a server that doesn't echo the number (before its decision
        # 0104) is taken to answer, as the caption log always took it
        self._latest_seq: dict[tuple[str, str], int] = {}
        """Speech sent and not yet answered, by caption and kind: its start
        and end and when it went, for its answer's times (the latest live
        update's; `SPEECH_TIMES_KEPT` at most)."""
        self._restarting_since: float | None = None
        """When the server last said it's restarting (close 1001), until a
        session opens again (core.listening.unreachable.after_restart)."""
        self._going_away_told = False
        """This session's server announced its close 1001 (a `notice` in
        `failures.ANNOUNCED_GOING_AWAY`): only then is it a restart (368)."""
        self._maintenance = maintenance
        """The planned maintenance window held: what the last `welcome`,
        `maintenance` message or refusal for it said (319)."""
        self._wall_clock = wall_clock
        self._ahead = maintenance.pc_ahead if maintenance else timedelta(0)
        """How far this PC's clock is ahead of the server's: from the last
        `welcome.server_time`, else the window held."""

    # --- From any thread ----------------------------------------------------

    def start(self) -> None:
        """Opens the session on a thread of its own."""
        if self._thread is not None:
            raise RuntimeError("the session has already started")
        if self._purpose == "listen":
            self._timelines.start()
        self._thread = threading.Thread(
            target=asyncio.run, args=(self._main(),), name="session", daemon=True
        )
        self._thread.start()
        self._started.wait()

    def stop(
        self, timeout: float | None = None, reason: StopReason = StopReason.CLOSED
    ) -> None:
        """Closes the session (normally, 1000) once finished speech still
        waiting has gone out and been answered, or `drain_within` has
        passed; waits for its thread (by default as long as that and the
        closing handshake can take). Its last status says it stopped for
        `reason` - `SIGN_IN_NEEDED` when the user signed out, so Home asks
        them to sign in rather than saying it stopped."""
        if timeout is None:
            timings = self._timings
            timeout = timings.drain_within + timings.close_within + 1.0
        self._stopped_for = reason
        self._call(lambda: self._stop.set())
        if self._thread is not None:
            self._thread.join(timeout)

    def speech_ready(self) -> None:
        """Something new waits in the speech source (called by the speech
        pipeline, on a capture thread)."""
        self.wake()

    def wake(self) -> None:
        """Something new waits to be sent - speech, or in the exchange."""
        self._call(lambda: self._wake.set())

    def recheck(self, request: RecheckRequest) -> bool:
        """Sends a flagged line's speech to be checked on the best models
        (server decision 0031); the answer comes to the listener's
        `rechecked`. False if this session can't send it: a sync session,
        not started or over, or a frame over the limit. One waiting while
        the session reconnects goes out once it's back, unless it has
        waited longer than the comparison does."""
        if self._purpose != "listen":
            return False
        frame = listening.recheck_frame(request)
        if len(frame) > self._limits.speech_frame_bytes:
            return False
        loop = self._loop
        if loop is None or loop.is_closed():
            return False

        def queue() -> None:
            self._rechecks.append((time.monotonic(), frame))
            self._wake.set()

        self._call(queue)
        return True

    def take_on(self, handed: list[Handed]) -> None:
        """Finished speech the listening session before this one sent and
        never had answered (its `hand_over`): sent again first - as soon
        as this session is open, or now if it is - and waited for as this
        session's own."""
        if not handed:
            return
        with self._handed_lock:
            self._handed.extend(handed)
        self.wake()

    def hand_over(self) -> list[Handed]:
        """Once stopped - its thread over - the finished speech it sent, or
        took on, that was never answered, oldest first: for the next
        listening session to send (`take_on`). Empty while its thread
        runs on."""
        if self._thread is not None and self._thread.is_alive():
            return []
        with self._handed_lock:
            waiting, self._handed = self._handed, []
        return waiting + self.unanswered.hand_over()

    def change_settings(self, settings: ListeningSettings) -> None:
        def change() -> None:
            self._settings = settings
            if settings.original_only:
                self._summary.did(SessionAction.ORIGINAL_ONLY)
            self._settings_changed.set()
            self._wake.set()

        loop = self._loop
        if loop is None or loop.is_closed():
            # not started yet (or over): no thread reads them, so the first
            # session's `settings` carries these
            self._settings = settings
            if settings.original_only:
                self._summary.did(SessionAction.ORIGINAL_ONLY)
            return
        self._call(change)

    def learned(self, event: LearningEvent) -> None:
        """One of Learning's events while the session is open: a lookup or
        a save is counted in its summary (on the session's thread, which
        owns the summary)."""
        if isinstance(event, WordLookedUp):
            self._call(self._summary.looked_up)
        elif isinstance(event, WordSaved):
            self._call(self._summary.saved)

    def captured(self, capture: Capture) -> None:
        """What is captured changed (its summary's per app vs whole system)."""
        at = time.perf_counter()
        self._call(lambda: self._summary.captured(capture, at))

    def did(self, action: SessionAction) -> None:
        """The learner did something the session's summary counts."""
        self._call(lambda: self._summary.did(action))

    def preset_step(self, step: PresetStep, changes: int) -> None:
        """A step on the chosen preset, counted in the summary (587)."""
        self._call(lambda: self._summary.preset_step(step, changes))

    def songs(self, on: bool) -> None:
        """Songs mode came on or went off (its summary's `lyrics_seconds`)."""
        at = time.perf_counter()
        self._call(lambda: self._summary.songs(on, at))

    def ended(self) -> ListeningSessionEnded | None:
        """The session's summary, once it has stopped (None for a sync
        session)."""
        if self._purpose != "listen":
            return None
        left = self._held_back.left_to_log()
        if left is not None:
            self._log_held_back(left.waited, left.refused)
        self._timelines.stop()
        restarts = self._capture_restarts
        exchange = self._exchange
        return self._summary.ended(
            time.perf_counter(),
            capture_restarts=restarts() if restarts is not None else 0,
            unreadable_dropped=exchange.take_unreadable() if exchange else 0,
        )

    def speaking_pace(self) -> None:
        """Publish current pace, including its fade during silence."""

        def publish() -> None:
            pace_listener = getattr(self._listener, "speaking_pace", None)
            if pace_listener is not None:
                self._notify(
                    pace_listener,
                    self._summary.pace_by_source(time.perf_counter()),
                )

        self._call(publish)

    def timelines(self) -> dict[str, protocol.UsageValue] | None:
        """Where the session's caption time went, as the tracking plan's
        `caption_timeline_summarised` - once it has stopped (`ended`); None
        for a sync session, or one that sent nothing and had no sound go
        unheard (polyglotic-hq 549: a session that heard no speech at all
        in sound that went on is the one to see)."""
        summary = self._timelines.summary
        if self._purpose != "listen" or not (
            summary.updates or summary.unheard.stretches
        ):
            return None
        return listening.timeline_summarised(
            self._timelines, self._mode, self._live_interval
        )

    def _call(self, action: Callable[[], None]) -> None:
        loop = self._loop
        if loop is None or loop.is_closed():
            return
        with contextlib.suppress(RuntimeError):  # closed meanwhile
            loop.call_soon_threadsafe(action)

    # --- On the session's thread ---------------------------------------------

    async def _main(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._stop = asyncio.Event()
        self._wake = asyncio.Event()
        self._settings_changed = asyncio.Event()
        self._started.set()
        try:
            await self._keep_open()
        except Exception:
            log.exception("the session failed")
            self._status(Status(SessionState.STOPPED, stopped=StopReason.CLOSED))

    async def _keep_open(self) -> None:
        while not self._stop.is_set():
            began = time.monotonic()
            try:
                credentials = self._credentials.load()
            except Exception as error:
                if self._purpose != "listen":
                    raise  # a sync session stops; the next one tries again
                await self._wait_after(
                    self._failed("reading the sign-in", began, error)
                )
                continue
            if credentials is None:
                self._status(
                    Status(SessionState.STOPPED, stopped=StopReason.SIGN_IN_NEEDED)
                )
                return
            self._status(Status(SessionState.CONNECTING))
            session = asyncio.create_task(self._one_session(credentials))
            stopping = asyncio.create_task(self._stop.wait())
            await asyncio.wait({session, stopping}, return_when=asyncio.FIRST_COMPLETED)
            if not session.done() and not self._listening:  # stopped while connecting
                session.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await session
                break
            try:
                ended = await session  # a listening session closes itself, normally
            except Exception as error:
                stopping.cancel()
                if self._purpose != "listen" or self._stop.is_set():
                    raise
                await self._wait_after(self._failed("the session", began, error))
                continue
            stopping.cancel()
            if ended.lasted > 0 or self._lost_at is None:
                self._lost_at = time.monotonic()  # away from now, till welcomed
            if self._stop.is_set():
                break
            if ended.new_hello:
                continue
            step = self._reconnects.after(ended)
            if self._purpose == "sync" and not isinstance(step, Stop):
                log.info("sync session ended (close %s)", ended.close_code)
                self._status(
                    Status(
                        SessionState.STOPPED,
                        stopped=StopReason.CLOSED,
                        close_code=ended.close_code,
                    )
                )
                return
            if isinstance(step, Stop):
                log.info(
                    "session stopped (close %s): %s", ended.close_code, step.reason
                )
                if step.reason is StopReason.SIGN_IN_NEEDED:
                    self._credentials.forget()
                self._status(
                    Status(
                        SessionState.STOPPED,
                        stopped=step.reason,
                        close_code=ended.close_code,
                    )
                )
                if not self._asks_again(step.reason):
                    return
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(
                        self._stop.wait(), self._timings.update_retry
                    )
                continue
            why = self._unreachable(ended)
            step = self._in_maintenance(why, ended, step)
            if why is Unreachable.MAINTENANCE:
                self._give_up_for_maintenance()
            log.info(
                "session ended (close %s, %s) after %.0fs; trying again in %.1fs",
                ended.close_code,
                why,
                ended.lasted,
                step.seconds,
            )
            self._status(
                Status(
                    SessionState.WAITING,
                    retry_in=step.seconds,
                    close_code=ended.close_code,
                    server_busy=isinstance(ended.refusal, protocol.ServerBusy)
                    and why is not Unreachable.MAINTENANCE,
                    unreachable=why,
                )
            )
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._stop.wait(), step.seconds)
        self._status(
            Status(SessionState.STOPPED, stopped=self._stopped_for, close_code=NORMAL)
        )

    def _failed(self, what: str, began: float, error: Exception) -> float:
        """`what` failed in the app itself with `error`, `began` (monotonic)
        being when this attempt started: logged by the error's type and
        where (the log file's `ContentFreeLog` - never its text), and how
        long to wait before trying again (decision 0266)."""
        step = self._reconnects.after_failure(time.monotonic() - began)
        self._summary.session_failed()  # counted in its summary (566)
        log.error(
            "%s failed (%d in a row); trying again in %.1fs",
            what,
            self._reconnects.failures,
            step.seconds,
            exc_info=error,
        )
        if self._lost_at is None:
            self._lost_at = time.monotonic()  # away from now, till welcomed
        return step.seconds

    async def _wait_after(self, seconds: float) -> None:
        """Waiting to try again after a failure: said, and over early if
        the session is stopped."""
        self._status(Status(SessionState.WAITING, retry_in=seconds))
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(self._stop.wait(), seconds)

    def _unreachable(self, ended: Ended) -> Unreachable | None:
        """Why the server couldn't be reached, or ended the session - a
        restart said as one while the server comes back from it."""
        why = (
            ended.unreachable
            or why_refused(ended.refusal)
            or why_closed(ended.close_code, self._going_away_told)
        )
        self._going_away_told = False  # said of this session's end only
        now = time.monotonic()
        if why is Unreachable.RESTARTING:
            self._restarting_since = now
        if why is None:
            return None
        since = self._restarting_since
        why = after_restart(why, None if since is None else now - since)
        return planned.during_maintenance(why, self._maintenance, self._wall_clock())

    def _in_maintenance(
        self, why: Unreachable | None, ended: Ended, step: RetryIn
    ) -> RetryIn:
        """Waiting in a planned maintenance window the app holds: try again
        at most every 2 minutes, then at its end plus a random 0-60 s - not
        every few seconds, and not all apps in the same second (319). A
        refusal for the window already waits so (`Reconnects`)."""
        window = self._maintenance
        if why is not Unreachable.MAINTENANCE or window is None or ended.refusal:
            return step
        seconds = planned.wait(window, self._wall_clock(), self._reconnects.random())
        return step if seconds is None else RetryIn(seconds)

    def _told(self, window: protocol.MaintenanceWindow | None) -> Maintenance | None:
        """A window as the server wrote it, placed with the clock difference held."""
        if window is None:
            return None
        return planned.told(window.starts_at, window.ends_at, self._pc_ahead())

    def _pc_ahead(self) -> timedelta:
        """How far this PC's clock is ahead of the server's, as last told."""
        held = self._maintenance
        return held.pc_ahead if held is not None else self._ahead

    def _hold_welcomes(self, welcome: protocol.Welcome) -> None:
        """`welcome` says the window that stands, or none - a server from
        before 2026-11-14 plans none, so a window held from a newer one is
        let go - and the server's time places it."""
        ahead = planned.pc_ahead_of(welcome.server_time, self._wall_clock())
        if ahead is not None:
            self._ahead = ahead
        window = welcome.maintenance
        self._hold(
            None
            if window is None
            else planned.told(window.starts_at, window.ends_at, self._ahead)
        )

    def _hold(self, window: Maintenance | None) -> None:
        if window == self._maintenance:
            return
        self._maintenance = window
        log.info(
            "planned maintenance: %s",
            "none"
            if window is None
            else f"{window.starts_at:%Y-%m-%d %H:%M}Z to {window.ends_at:%H:%M}Z",
        )
        self._notify(self._listener.maintenance_changed, window)

    @property
    def maintenance(self) -> Maintenance | None:
        """The planned maintenance window this session holds."""
        return self._maintenance

    def _asks_again(self, reason: StopReason) -> bool:
        """A listening session refused for its version asks again later:
        the server may take it again (its minimum lowered), and there may
        be nothing to update to yet. So does one Plus ending stopped (4009):
        Plus bought or renewed on the site reaches the app only in a new
        session's `welcome.plan` - Help and Home promise captions "start
        again by themselves" (polyglotic-hq 185, 203). Every other stop
        waits for the user."""
        return self._purpose == "listen" and reason in (
            StopReason.UPDATE_REQUIRED,
            StopReason.LIMIT_REACHED,
        )

    async def _one_session(self, credentials: DeviceCredentials) -> Ended:
        began = time.monotonic()
        try:
            secure = tls.context() if self._url.startswith("wss://") else None
            try:
                websocket = await self._connect(secure)
            except ssl.SSLCertVerificationError as error:
                # a certificate's dates: once more, everything else still
                # checked (connection.tls, decision 0104; polyglotic-hq 313)
                failed = tls.on_dates(error)
                if failed is None:
                    raise
                secure = tls.context(failed)
                websocket = await self._connect(secure)
            self._clock_looks_wrong = tls.clock_looks_wrong(tls.let_for(secure))
            async with websocket:
                return await self._open(websocket, credentials)
        except (
            OSError,
            TimeoutError,
            InvalidHandshake,
            InvalidURI,
            InvalidProxy,  # the PC's proxy setting: not one websockets can use
        ) as error:
            why = why_not_opened(error)
            # how long it took tells a reset at once from no answer at all
            log.info(
                "couldn't open a session after %.1fs: %s (%s)",
                time.monotonic() - began,
                type(error).__name__,
                why,
            )
            return Ended(None, unreachable=why)
        except ConnectionClosed as closed:
            return Ended(_close_code(closed))

    async def _connect(self, secure: ssl.SSLContext | None) -> ClientConnection:
        """The WebSocket, opened: over `wss://` with connection.tls's
        context `secure` - after a failure on dates, the one that checks the
        leaf's dates itself (decision 0104). `ws://` (a server on this PC)
        has none; websockets refuses `ssl=None` for `wss://`."""
        return await connect(
            self._url,
            open_timeout=self._timings.answer_within,
            close_timeout=self._timings.close_within,
            ping_interval=None,  # the app's own `ping` (protocol.md)
            compression=None,  # speech is Opus already
            max_size=MAX_MESSAGE_BYTES,
            logger=_websocket_log,
            # the app's own name, as every other request (core/shared/
            # client.py): websockets' default is "Python/3.x websockets/y"
            user_agent_header=USER_AGENT,
            ssl=secure,
        )

    async def _open(
        self, websocket: ClientConnection, credentials: DeviceCredentials
    ) -> Ended:
        self._live_translation = (
            self._purpose == "listen" and self._settings.live_translation
        )
        hello = protocol.Hello(
            live_translation=self._live_translation or None,
            app_version=self._app.app_version,
            install_id=credentials.install_id,
            channel=self._app.channel,
            os=self._app.os,
            purpose=self._purpose,
            auth=protocol.HelloAuth(device_token=credentials.device_token),
            resume=self._resume,
            time_zone=self._time_zone,
        )
        await websocket.send(protocol.encode(hello))
        try:
            answer = await asyncio.wait_for(
                websocket.recv(), self._timings.answer_within
            )
        except TimeoutError:
            log.warning("the server didn't answer hello")
            return Ended(None, unreachable=Unreachable.SERVER_ERROR)
        message = self._decode(answer)
        if isinstance(message, Refusal):
            log.info("the server refused the session: %s", message.type)
            if isinstance(message, protocol.LimitReached) and message.plan:
                self._notify(self._listener.plan_changed, message.plan)
            if isinstance(message, protocol.AllowanceExhausted):
                self._notify(self._listener.allowance_changed, message)
            if (
                isinstance(message, protocol.ServerBusy)
                and message.reason == "maintenance"
            ):  # the window's end, which may have moved since it was told
                self._hold(
                    planned.ends_at(
                        self._maintenance, message.until, self._wall_clock()
                    )
                )
            try:
                await asyncio.wait_for(websocket.recv(), self._timings.close_within)
            except ConnectionClosed as closed:
                return Ended(_close_code(closed), message)
            except TimeoutError:
                pass
            return Ended(websocket.close_code, message)
        if not isinstance(message, protocol.Welcome):
            log.warning("the server didn't answer hello with welcome")
            return Ended(None, unreachable=Unreachable.SERVER_ERROR)
        return await self._listen(websocket, message, credentials.install_id)

    async def _listen(
        self, websocket: ClientConnection, welcome: protocol.Welcome, install_id: str
    ) -> Ended:
        welcomed = time.monotonic()
        self._last_heard = welcomed
        self._listening = True
        self._restarting_since = None  # back: a restart's over
        self._going_away_told = False
        try:
            return await self._listen_until_closed(
                websocket, welcome, welcomed, install_id
            )
        finally:
            self._listening = False
            if self._exchange is not None:
                self._exchange.closed()

    async def _listen_until_closed(
        self,
        websocket: ClientConnection,
        welcome: protocol.Welcome,
        welcomed: float,
        install_id: str,
    ) -> Ended:
        self._closed_with = None
        self._terminal = None
        self._limits = welcome.limits
        self._welcomes += 1
        if self._welcomes > 1:
            self._summary.reconnected()
            log.info(
                "session resumed: %s, %.1fs after the last one ended",
                "yes" if welcome.resumed else "no",
                0.0 if self._lost_at is None else time.monotonic() - self._lost_at,
            )
        self._lost_at = None
        if self._purpose == "listen":
            self._resume = welcome.session_id
        if self._exchange is not None:
            self._first = self._exchange.opened(
                install_id, welcome.limits, welcome.learning_epoch, welcome.account_id
            )
        self._take_handed()  # sent below, with what this session kept
        self._again = self.unanswered.to_send_again()
        if self._again:
            log.info(
                "sending %d unanswered finished caption(s) again", len(self._again)
            )
        log.info(
            "%s session open (protocol %d)", _NAMES[self._purpose], welcome.protocol
        )
        self._status(
            Status(
                SessionState.LISTENING,
                session_id=welcome.session_id,
                channel=welcome.channel,
                account_id=welcome.account_id,
                cohort=welcome.cohort,
                tier=welcome.plan.tier if welcome.plan is not None else None,
                source_fields=welcome.source_fields,
                clock_looks_wrong=self._clock_looks_wrong,
            )
        )
        if welcome.plan is not None:
            self._notify(self._listener.plan_changed, welcome.plan)
        self._hold_welcomes(welcome)
        if self._purpose == "listen":
            self._notify(self._listener.pace_changed, welcome.live_interval_min)
            self._settings_changed.set()  # a new session starts with `settings`
        self._wake.set()  # and sends whatever waited while it was away
        every = self._timings.ping_every or float(welcome.limits.ping_seconds)
        tasks = {
            asyncio.create_task(self._receive(websocket), name="receive"),
            asyncio.create_task(self._send(websocket), name="send"),
            asyncio.create_task(self._ping(websocket, every), name="ping"),
            asyncio.create_task(self._watch(), name="watch"),
            asyncio.create_task(self._stop.wait(), name="stop"),
        }
        if self._purpose == "sync":
            tasks.add(asyncio.create_task(self._settled(), name="settled"))
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        (receive,) = [t for t in tasks if t.get_name() == "receive"]
        draining = (
            self._purpose == "listen"
            and self._stop.is_set()
            and self._closed_with is None
            and not receive.done()
        )
        for task in pending:
            if not (draining and task is receive):
                task.cancel()
        await asyncio.gather(
            *(t for t in pending if t is not receive or not draining),
            return_exceptions=True,
        )
        if draining:
            await self._drain(websocket, receive)
            receive.cancel()
            await asyncio.gather(receive, return_exceptions=True)
        for task in done:
            failure = None if task.cancelled() else task.exception()
            if failure is not None:
                raise failure
        lasted = time.monotonic() - welcomed
        if self._terminal is not None:
            return Ended(self._closed_with, self._terminal, lasted)
        if self._stop.is_set() or any(t.get_name() == "settled" for t in done):
            await websocket.close(NORMAL)
            return Ended(NORMAL, lasted=lasted)
        if (
            self._closed_with is None
            and self._purpose == "listen"
            and self._live_translation != self._settings.live_translation
        ):
            # A hello capability changed. Resume immediately with the new
            # choice. Unanswered finished speech is retained across the close.
            await websocket.close(NORMAL)
            return Ended(NORMAL, lasted=lasted, new_hello=True)
        if self._closed_with is None:  # the watch: no message for too long
            log.info("no message from the server for %.0fs", self._timings.dead_after)
            with contextlib.suppress(Exception):
                await asyncio.wait_for(websocket.close(), self._timings.close_within)
            return Ended(NO_CLOSE_FRAME, lasted=lasted)
        return Ended(self._closed_with, lasted=lasted)

    async def _receive(self, websocket: ClientConnection) -> None:
        translations = listening.LiveTranslations(SPEECH_TIMES_KEPT)
        while True:
            try:
                data = await websocket.recv()
            except ConnectionClosed as closed:
                self._closed_with = _close_code(closed)
                return
            self._last_heard = time.monotonic()
            message = self._decode(data)
            if isinstance(message, protocol.CaptionUpdate):
                if message.kind != "live":
                    self.unanswered.answered(message.caption_id, message.replaces or ())
                update = self._timed(listening.caption_update(message), message.trace)
                is_respoken = getattr(self._listener, "respoken", None)
                if is_respoken is not None and is_respoken(update.caption_id):
                    update = replace(update, respoken=True)
                if self._live_translation:
                    translations.original(
                        update, message.trace.seq if message.trace else None
                    )
                wpm = self._summary.caption_updated(update, time.perf_counter())
                if wpm is not None:
                    update = replace(update, pace_wpm=wpm)
                self._notify(self._listener.caption_updated, update)
                if update.kind is CaptionKind.FINISHED:
                    pace_listener = getattr(self._listener, "speaking_pace", None)
                    if pace_listener is not None:
                        self._notify(
                            pace_listener,
                            self._summary.pace_by_source(time.perf_counter()),
                        )
            elif isinstance(message, protocol.LiveTranslation):
                if self._live_translation and self._settings.live_translation:
                    translated = translations.translated(message)
                    if translated is not None:
                        self._notify(self._listener.caption_updated, translated)
            elif isinstance(message, protocol.Pace):
                self._notify(self._listener.pace_changed, message.live_interval_min)
            elif isinstance(message, protocol.Minutes):
                self._notify(self._listener.minutes_changed, message.used, message.left)
            elif isinstance(message, protocol.AllowanceUpdate):
                self._notify(self._listener.allowance_changed, message)
            elif isinstance(
                message,
                (
                    protocol.AllowanceExhausted,
                    protocol.RegistrationRequired,
                    protocol.CrossBorderConsentRequired,
                ),
            ):
                self._terminal = message
                if isinstance(message, protocol.AllowanceExhausted):
                    self._notify(self._listener.allowance_changed, message)
                return
            elif isinstance(message, protocol.Notice):
                if message.code in ANNOUNCED_GOING_AWAY:
                    self._going_away_told = True  # its close 1001 is the restart
                self._notify(self._listener.notice, message.code)
            elif isinstance(message, protocol.Plan):
                self._notify(self._listener.plan_changed, message)
            elif isinstance(message, protocol.Maintenance):
                self._hold(self._told(message.window))
            elif isinstance(message, protocol.LimitReached):  # then 4009
                log.info("listening stops: %s", message.kind)
                if message.plan is not None:
                    self._notify(self._listener.plan_changed, message.plan)
            elif isinstance(message, protocol.RecheckResult):
                result = listening.recheck_result(message)
                self._notify(self._listener.rechecked, result)
            elif self._exchange is not None and isinstance(
                message,
                protocol.Received | protocol.LearningState | protocol.LearningDeleted,
            ):
                self._exchange.heard(message)
                self._wake.set()  # answers, or what was held back, can go now
            if isinstance(message, protocol.Error):
                if message.caption_id is not None and self._answers_finished_speech(
                    message.code, message.caption_id, message.kind
                ):
                    ended = self._ends_the_caption(message)
                    self.unanswered.answered(message.caption_id)
                    self._summary.failed(CaptionId(message.caption_id))
                    self._speech_sent.pop((message.caption_id, "finished"), None)
                    if ended:
                        self._notify(
                            self._listener.caption_dropped,
                            CaptionId(message.caption_id),
                        )
                if message.caption_id is not None:
                    caption_log.info(
                        delays.line(
                            "error",
                            message.caption_id,
                            code=message.code,
                            kind=message.kind,
                        )
                    )
                if message.code == "processing_failed":
                    self._notify(self._listener.caption_failed)
                if self._refuses_a_live_update(message):
                    # one line a minute, not one per live update (decision 0097)
                    self._live_update_held(self._held_back.refused(time.monotonic()))
                else:
                    log.warning(
                        "the server: error %s (fatal: %s)",
                        message.code,
                        message.fatal,
                    )
                if self._exchange is not None:
                    self._exchange.heard(message)

    def _ends_the_caption(self, message: protocol.Error) -> bool:
        """Whether an `error` naming a caption means its finished caption
        won't come, so its live caption ends (557): it refused or failed the
        finished speech - said so (`kind`), only ever said of finished
        speech (`FINISHED_SPEECH_ONLY`), or, from a server that doesn't say,
        about a caption whose finished speech awaits its answer. Not a live
        update refused before its finished speech was sent: that comes."""
        if message.kind is not None:
            return message.kind == "finished"
        return (
            message.code in FINISHED_SPEECH_ONLY
            or message.caption_id in self.unanswered
        )

    def _refuses_a_live_update(self, message: protocol.Error) -> bool:
        """Whether an `error` is the server refusing a live update at its
        speech limit: the caption carries on, and so does the session. A
        server that doesn't say which kind it refused (before 2026-11-11)
        is taken to mean a live update unless the caption's finished
        speech is waiting for its answer."""
        if message.code != "speech_limit_reached" or message.caption_id is None:
            return False
        if message.kind is not None:
            return message.kind == "live"
        return message.caption_id not in self.unanswered

    def _live_update_held(self, tell: bool) -> None:
        """A live update was held back - it waited its turn in the app, or
        the server refused it: the learner is told once in a while
        (`HeldBack`), and the log says how many once a minute."""
        if tell:
            self._notify(self._listener.notice, LIVE_UPDATES_HELD_BACK)
        counted = self._held_back.to_log(time.monotonic())
        if counted is not None:
            self._log_held_back(counted.waited, counted.refused)

    @staticmethod
    def _log_held_back(waited: int, refused: int) -> None:
        if refused:
            log.warning(
                "live updates held back since the last such line: the server "
                "refused %d at its speech limit, %d waited their turn here",
                refused,
                waited,
            )
        else:
            log.info(
                "live updates held back since the last such line: %d waited "
                "their turn under the speech ceiling",
                waited,
            )

    def _answers_finished_speech(
        self, code: str, caption_id: str, kind: str | None
    ) -> bool:
        """Whether an `error` naming a caption answers the caption's
        finished speech - the caption then failed - or may be refusing one
        of its live updates. A server since 2026-11-11 says which (`kind`,
        its decision 0052): refused finished speech is answered, and isn't
        waited for (polyglotic-hq 271: waiting, it held "Connection
        unstable" up for good). One that doesn't say: while the caption's
        finished speech is unanswered, only `processing_failed` answers it;
        any other error (a live update refused by `speech_limit_reached`
        above all) leaves the caption waiting for its finished answer, and
        a reconnect still sends its speech again - until it's given up
        (`UnansweredSpeech.give_up`)."""
        if kind == "finished":
            return True
        return code in FINISHED_SPEECH_ONLY or caption_id not in self.unanswered

    async def _send(self, websocket: ClientConnection) -> None:
        try:
            while True:
                await self._wake.wait()
                self._wake.clear()
                if self._settings_changed.is_set():
                    self._settings_changed.clear()
                    if (
                        self._purpose == "listen"
                        and self._live_translation != self._settings.live_translation
                    ):
                        return
                    settings = listening.settings(self._settings, self._limits.targets)
                    await websocket.send(protocol.encode(settings))
                if self._exchange is not None:
                    first, self._first = self._first, []
                    for message in first + self._exchange.more():
                        await websocket.send(message)
                again, self._again = self._again, []
                for frame in again + self._take_handed():
                    await websocket.send(self._resend(frame))
                rechecks, self._rechecks = self._rechecks, []
                for asked, frame in rechecks:
                    if time.monotonic() - asked < ANSWER_WITHIN_SEC:
                        await websocket.send(frame)
                while (item := self._take_speech()) is not None:
                    decision, speech = item
                    seq = self._numbered(decision)
                    out = listening.outgoing(
                        decision, speech, self._settings, self._limits.targets, seq
                    )
                    if out is None:
                        self._not_sent(decision, "no_audio", seq)
                        continue
                    if (
                        isinstance(out, bytes)
                        and len(out) > self._limits.speech_frame_bytes
                    ):
                        log.warning(
                            "a %d-byte speech frame is over the limit", len(out)
                        )
                        self._not_sent(decision, "over_frame_limit", seq)
                        continue
                    if (
                        isinstance(decision, TranscriptionRequest)
                        and decision.kind is SpeechKind.FINISHED
                        and isinstance(out, bytes)
                    ):
                        self.unanswered.sending(
                            decision.caption_id, decision.replaces, out
                        )
                    if isinstance(decision, TranscriptionRequest):
                        self._summary.speech_sent(decision, time.perf_counter())
                        if decision.held:
                            self._live_update_held(
                                self._held_back.waited(time.monotonic())
                            )
                    else:  # withdrawn: the server answers nothing more for it
                        self.unanswered.withdrawn(decision.caption_id)
                    self._sending(decision, out, seq)
                    await websocket.send(out)
                    trace.tracer().mark(seq, "sent")
        except ConnectionClosed as closed:
            self._closed_with = _close_code(closed)

    async def _ping(self, websocket: ClientConnection, every: float) -> None:
        try:
            while True:
                await asyncio.sleep(every)
                await websocket.send(protocol.encode(protocol.Ping()))
        except ConnectionClosed as closed:
            self._closed_with = _close_code(closed)

    async def _drain(
        self, websocket: ClientConnection, receive: "asyncio.Task[Any]"
    ) -> None:
        """Stopping: the finished speech still waiting goes out, and its
        answers are awaited for up to `drain_within`."""
        deadline = time.monotonic() + self._timings.drain_within
        try:
            again, self._again = self._again, []
            for frame in again + self._take_handed():
                await websocket.send(self._resend(frame))
            while (item := self._take_speech()) is not None:
                decision, speech = item
                if (
                    isinstance(decision, TranscriptionRequest)
                    and decision.kind is SpeechKind.LIVE
                ):
                    continue
                seq = self._numbered(decision) if self._live_translation else None
                out = listening.outgoing(
                    decision, speech, self._settings, self._limits.targets, seq
                )
                if out is None or (
                    isinstance(out, bytes)
                    and len(out) > self._limits.speech_frame_bytes
                ):
                    continue
                if isinstance(decision, TranscriptionRequest) and isinstance(
                    out, bytes
                ):
                    self.unanswered.sending(decision.caption_id, decision.replaces, out)
                    self._summary.speech_sent(decision, time.perf_counter())
                self._sending(decision, out, seq)
                await websocket.send(out)
                trace.tracer().mark(seq, "sent")
            while (
                len(self.unanswered)
                and not receive.done()
                and time.monotonic() < deadline
            ):
                await asyncio.sleep(0.05)
        except ConnectionClosed:
            return
        if len(self.unanswered):
            log.info(
                "stopped with %d finished caption(s) unanswered", len(self.unanswered)
            )

    def _resend(self, frame: bytes) -> bytes:
        """A retried finished frame keeps its caption but has a fresh wire revision."""
        if not self._live_translation:
            return frame
        h, audio = protocol.read_speech_frame(frame)
        now = time.perf_counter()
        seq = trace.tracer().sending(
            trace.speech_key(h.caption_id, h.kind, h.section, h.speech_end),
            h.source.category,
            h.speech_end - h.speech_start,
            now,
        )
        self._remember_sent(
            h.caption_id, h.kind, h.speech_start, h.speech_end, now, seq
        )
        trace.tracer().mark(seq, "sent")
        return protocol.speech_frame(h.model_copy(update={"seq": seq}), audio)

    def _take_handed(self) -> list[bytes]:
        """On the session's thread: finished speech handed over since last
        asked (`take_on`), kept as this session's own unanswered speech;
        returns its frames, to send."""
        with self._handed_lock:
            handed, self._handed = self._handed, []
        if handed:
            self.unanswered.take_on(handed)
            log.info(
                "%d finished caption(s) a closed session left unanswered,"
                " sent again here",
                len(handed),
            )
        return [h.frame for h in handed]

    async def _settled(self) -> None:
        """Returns once a sync session's exchange is done, or it has had
        `sync_within` seconds."""
        deadline = time.monotonic() + self._timings.sync_within
        while time.monotonic() < deadline:
            if self._exchange is None or (not self._first and self._exchange.settled()):
                return
            await asyncio.sleep(0.05)
        log.info("sync session: not every answer came in time")

    async def _watch(self) -> None:
        """Returns once the server has been silent for `dead_after`; until
        then, says when the connection stalls and when it's over."""
        every = self._timings.ping_every or float(self._limits.ping_seconds)
        opened = time.monotonic()
        try:
            while True:
                now = time.monotonic()
                silent = now - self._last_heard
                if silent >= self._timings.dead_after:
                    return
                if self._purpose == "listen":
                    self._give_up()
                    waiting = self.unanswered.waiting_since()
                    self._say_stalled(
                        stalled(
                            # speech sent again after a reconnect waits from
                            # now: this connection hasn't kept it waiting yet
                            None if waiting is None else max(waiting, opened),
                            self._last_heard,
                            every,
                            now,
                        )
                    )
                await asyncio.sleep(min(1.0, self._timings.dead_after - silent))
        finally:
            self._say_stalled(
                False
            )  # this connection is over: its state says what's next

    def _give_up_for_maintenance(self) -> None:
        """A planned maintenance window: finished speech still unanswered
        from before it isn't sent after it - minutes old by then, and every
        app at once (polyglotic-hq 319). Counted as dropped."""
        for caption_id in self.unanswered.give_up_all():
            caption_log.info(delays.line("dropped", caption_id, why="maintenance"))
            self._speech_sent.pop((caption_id, "finished"), None)
            self._summary.failed(CaptionId(caption_id))
            self._notify(self._listener.caption_dropped, CaptionId(caption_id))

    def _give_up(self) -> None:
        """Finished speech that won't be answered stops being waited for,
        and counts as dropped: it mustn't hold the stall up for good."""
        for caption_id, why in self.unanswered.give_up(unstable.STALL_SEC):
            log.warning("a finished caption went unanswered: %s", why.value)
            caption_log.info(delays.line("dropped", caption_id, why=why.value))
            self._speech_sent.pop((caption_id, "finished"), None)
            self._summary.failed(CaptionId(caption_id))
            self._notify(self._listener.caption_dropped, CaptionId(caption_id))

    # --- The caption log, and each update's times (core.listening.delays) ----

    def _numbered(self, decision: Decision) -> int | None:
        """A transcription request the send loop just took: its number in
        the caption timelines (perf.trace), sent in its header. None for a
        withdrawal."""
        if not isinstance(decision, TranscriptionRequest):
            return None
        return trace.tracer().sending(
            trace.speech_key(
                decision.caption_id,
                decision.kind.value,
                decision.section,
                decision.speech_end,
            ),
            decision.source.category.value,
            decision.speech_end - decision.speech_start,
            time.perf_counter(),
        )

    def _sending(
        self, decision: Decision, out: bytes | str, seq: int | None = None
    ) -> None:
        """Speech (or a withdrawal) is about to go: logged, and its times
        kept for its answer."""
        if not isinstance(decision, TranscriptionRequest):
            caption_log.info(delays.line("withdrawn", decision.caption_id, by="app"))
            return
        now = time.perf_counter()
        kind = decision.kind.value
        self._remember_sent(
            decision.caption_id,
            kind,
            decision.speech_start,
            decision.speech_end,
            now,
            seq,
        )
        caption_log.info(
            delays.line(
                "sent",
                decision.caption_id,
                kind=kind,
                section=decision.section,
                source=decision.source.category.value,
                mode=self._mode,
                audio_s=f"{decision.speech_end - decision.speech_start:.2f}",
                bytes=len(out),
                joins=len(decision.replaces) or None,
                since_end_ms=delays.milliseconds(now - decision.speech_end),
            )
        )

    def _remember_sent(
        self,
        caption_id: str,
        kind: str,
        start: float,
        end: float,
        now: float,
        seq: int | None,
    ) -> None:
        self._speech_sent[(caption_id, kind)] = (
            start,
            end,
            now,
        )
        while len(self._speech_sent) > SPEECH_TIMES_KEPT:
            del self._speech_sent[next(iter(self._speech_sent))]
        if seq is not None:
            self._sent_by_seq[seq] = (start, end, now)
            self._latest_seq[(caption_id, kind)] = seq
            while len(self._latest_seq) > SPEECH_TIMES_KEPT:
                del self._latest_seq[next(iter(self._latest_seq))]
            while len(self._sent_by_seq) > SPEECH_TIMES_KEPT:
                del self._sent_by_seq[next(iter(self._sent_by_seq))]

    def _not_sent(self, decision: Decision, why: str, seq: int | None = None) -> None:
        trace.tracer().dropped(seq, f"not_sent:{why}")
        kind = (
            decision.kind.value if isinstance(decision, TranscriptionRequest) else None
        )
        caption_log.info(
            delays.line("dropped", decision.caption_id, kind=kind, why=why)
        )
        if kind == SpeechKind.FINISHED.value:  # never sent: it won't come
            self._notify(self._listener.caption_dropped, decision.caption_id)

    def _timed(
        self, update: CaptionUpdate, traced: protocol.UpdateTrace | None = None
    ) -> CaptionUpdate:
        """`update` with its speech's times, if this session sent that
        speech; its answer logged, and marked in the caption timelines
        with the server's `traced` times (perf.trace)."""
        now = time.perf_counter()
        live = update.kind is CaptionKind.LIVE
        key = (str(update.caption_id), "live" if live else "finished")
        sent = self._speech_sent.get(key) if live else self._speech_sent.pop(key, None)
        latest = self._latest_seq.get(key) if live else self._latest_seq.pop(key, None)
        seq = None
        if traced is not None and traced.seq in self._sent_by_seq:
            seq = traced.seq  # the very frame it answers, not the latest sent
            sent = self._sent_by_seq.pop(seq)
            trace.tracer().answered(
                seq,
                now,
                {
                    "waited": traced.waited_ms,
                    "queued": traced.queued,
                    "server": traced.server_ms,
                    **traced.stages_ms,
                },
                {n.seq: n.why for n in traced.unanswered},
            )
        elif traced is None and latest is not None and sent is not None:
            seq = latest  # an older server: the latest sent, as before
            server = None if update.processing_ms is None else update.processing_ms
            trace.tracer().answered(
                seq, now, None if server is None else {"processing": server}
            )
        times = None if sent is None else SpeechTimes(*sent, received=now, seq=seq)
        if not live:
            for caption_id in (update.caption_id, *update.replaces):
                self._speech_sent.pop((str(caption_id), "live"), None)
        caption_log.info(
            delays.line(
                "answered", update.caption_id, **delays.answered_fields(update, times)
            )
        )
        return update if times is None else replace(update, times=times)

    def _say_stalled(self, now_stalled: bool) -> None:
        if now_stalled != self._stalled:
            self._stalled = now_stalled
            if now_stalled:
                waiting = self.unanswered.waiting_since()
                now = time.monotonic()
                log.info(
                    "connection stalled: %d finished caption(s) unanswered, the"
                    " oldest for %.1fs; the server last heard %.1fs ago",
                    len(self.unanswered),
                    0.0 if waiting is None else now - waiting,
                    now - self._last_heard,
                )
            else:
                log.info("connection no longer stalled")
            self._notify(self._listener.connection_stalled, now_stalled)

    def _decode(self, data: str | bytes) -> protocol.Message | None:
        if isinstance(data, bytes):
            return None  # the server sends no binary frames
        try:
            return protocol.decode(data)
        except protocol.ProtocolError as error:
            log.warning("a message from the server was dropped: %s", error)
            return None

    def _status(self, status: Status) -> None:
        self._notify(self._listener.status_changed, status)

    def _notify[*A](self, call: Callable[[*A], None], *args: *A) -> None:
        """Calls the listener; its failure doesn't end the session."""
        try:
            call(*args)
        except Exception:
            log.exception("the session's listener failed")
