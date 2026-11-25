"""The app's connection to the server: a listening session while the user listens, short sync sessions otherwise.

protocol.md: "The app opens a session when listening starts, and a sync
session when it has learning data, consent or usage events waiting and
isn't listening." `Connection` makes that choice for `main`:
- `start()`: a sync session straight away - learning syncs from the server
  when the app starts, and whatever waited since it last ran goes out;
- `start_listening` / `stop_listening`: the listening session; while it's
  open, everything the `DataExchange` has waiting goes out on it, and
  `learned` counts lookups and saves in its summary;
- whenever the exchange has something new and nobody is listening: a sync
  session after `sync_delay` seconds (so a burst of lookups goes in one);
  one that couldn't connect is tried again after a growing wait
  (`RETRY_WAITS`), and stops for good only when the user must act (a new
  invite code, an update).

One session uses the exchange at a time: listening stops a sync session.
Sessions run on threads of their own (decision 0012); every method here
returns at once, from any thread.

When listening moves to another device (close 4011) the listening session
stops and stays `listening` - Home offers "Listen here", and nothing else
takes listening back - but it no longer sends: what waits goes in sync
sessions beside it, as if nobody listened (polyglotic-hq project 117,
Low 2).
"""

import logging
import threading
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime

from polyglotic_desktop.connection import listening, protocol
from polyglotic_desktop.connection.app import AppInfo
from polyglotic_desktop.connection.exchange import DataExchange
from polyglotic_desktop.connection.milestones import Milestones
from polyglotic_desktop.connection.reconnect import NORMAL, StopReason
from polyglotic_desktop.connection.session import (
    ListeningSession,
    SessionListener,
    SessionState,
    SpeechSource,
    Status,
    Timings,
)
from polyglotic_desktop.core.listening.captions import CaptionKind, CaptionUpdate
from polyglotic_desktop.core.listening.maintenance import Maintenance
from polyglotic_desktop.core.listening.pace import (
    PaceReading,
    WordCount,
    spaced_word_count,
)
from polyglotic_desktop.core.listening.recheck import RecheckRequest, RecheckResult
from polyglotic_desktop.core.listening.settings import ListeningSettings
from polyglotic_desktop.core.listening.sources import Capture
from polyglotic_desktop.core.listening.summary import PresetStep, SessionAction
from polyglotic_desktop.core.listening.timing import (
    LIVE_UPDATE_INTERVAL_SEC,
    CaptionId,
    CaptionMode,
)
from polyglotic_desktop.core.shared import LearningEvent
from polyglotic_desktop.ports.credentials import CredentialStore

log = logging.getLogger(__name__)

SYNC_DELAY_SEC = 2.0
RETRY_WAITS: Sequence[float] = (15.0, 30.0, 60.0, 120.0, 300.0, 600.0)
"""Seconds before trying a sync session again after each failure in a row."""


class Connection:
    def __init__(
        self,
        server: str,
        credentials: CredentialStore,
        app: AppInfo,
        exchange: DataExchange,
        listener: SessionListener,
        *,
        timings: Timings | None = None,
        sync_delay: float = SYNC_DELAY_SEC,
        retry_waits: Sequence[float] = RETRY_WAITS,
        milestones: Milestones | None = None,
        capture_restarts: Callable[[], int] | None = None,
        time_zone: str | None = None,
        count_words: WordCount = spaced_word_count,
    ) -> None:
        """`listener` hears the listening session; sync sessions are this
        object's own business. `milestones`: the install's, told of the
        first caption and sent when listening starts (project 134).
        `capture_restarts`: the captures' restarts since it was last called
        (the speech pipeline's `take_restarts`), for each listening
        session's summary (polyglotic-hq 566)."""
        self._server = server
        self._credentials = credentials
        self._app = app
        self._exchange = exchange
        self._listener = listener
        self._timings = timings
        self._sync_delay = sync_delay
        self._retry_waits = retry_waits
        self.milestones = milestones
        self._capture_restarts = capture_restarts
        self._count_words = count_words
        self._time_zone = time_zone
        self._lock = threading.Lock()
        self._listening: ListeningSession | None = None
        self._sync: ListeningSession | None = None
        self._timer: threading.Timer | None = None
        self._failures = 0
        self._stopping = 0  # listening sessions still closing
        self._closed = False
        self._moved = False  # the listening session stopped: listening moved
        self._capture: Capture | None = None  # what is captured, for summaries
        self._joined = False  # the joined window is on
        self._songs = False  # a music player is heard in songs mode (595)
        self.sync_stopped: StopReason | None = None
        """Set when sync sessions stopped for good (the user must act)."""
        self.maintenance: Maintenance | None = None
        """The planned maintenance window the app holds - kept between
        starts by `main` - handed to each session as it opens, and updated
        by what any session is told (polyglotic-hq 319)."""
        exchange.wake = self._something_waiting

    # --- From the app ---------------------------------------------------------------

    def start(self) -> None:
        """Syncs now: learning from the server, and whatever waits. Call it
        when the app starts, and after signing in."""
        with self._lock:
            self.sync_stopped = None
            self._failures = 0
        self._sync_soon(0.0)

    def start_listening(
        self,
        settings: ListeningSettings,
        take_speech: SpeechSource,
        live_interval: float | None = LIVE_UPDATE_INTERVAL_SEC,
        caption_mode: CaptionMode | None = None,
        preset: Mapping[str, protocol.UsageValue] | None = None,
    ) -> ListeningSession:
        """Opens the listening session (stopping a sync session); returns
        it, for `speech_ready` and `change_settings`. `live_interval` (the
        live-update interval followed; None: none), `caption_mode` and
        `preset` (the preset in use, as the summary's properties:
        polyglotic-hq 556) are for its summary."""
        with self._lock:
            if self._listening is not None:
                raise RuntimeError("already listening")
            self._cancel_timer()
            sync, self._sync = self._sync, None
            listener = _ListeningListener(self, self._listener)
            session = ListeningSession(
                self._server,
                self._credentials,
                self._app,
                settings,
                take_speech,
                listener,
                timings=self._timings,
                exchange=self._exchange,
                live_interval=live_interval,
                caption_mode=caption_mode,
                capture=self._capture,
                maintenance=self.maintenance,
                capture_restarts=self._capture_restarts,
                time_zone=self._time_zone,
                count_words=self._count_words,
            )
            listener.session = session
            session.preset_usage = dict(preset or {})
            self._listening = session
            self._moved = False
        if sync is not None:
            sync.stop(timeout=0)
        session.start()
        if self.milestones is not None:  # the consent may have come since
            self.milestones.send_due()
        if self._joined:
            session.did(SessionAction.JOINED_WINDOW)
        if self._songs:
            session.songs(True)
        return session

    def stop_listening(self) -> None:
        """Closes the listening session, returning at once: on a thread of
        its own the session sends the finished speech still waiting and
        awaits its answers (a few seconds at most), then closes. Its
        summary is kept to send - only with consent to usage statistics -
        and what's still waiting goes in a sync session."""
        with self._lock:
            session, self._listening = self._listening, None
            self._moved = False
            if session is not None:
                self._stopping += 1
        if session is None:
            if self._exchange.has_waiting():
                self._sync_soon(self._sync_delay)
            return
        threading.Thread(
            target=self._finish_listening,
            args=(session,),
            name="stop-listening",
            daemon=True,
        ).start()

    def speaking_pace(self) -> None:
        """Publish pace for the open listening session's shared UI timer."""
        with self._lock:
            session = self._listening
        if session is not None:
            session.speaking_pace()

    def _finish_listening(self, session: ListeningSession) -> None:
        try:
            session.stop()
            self._hand_on(session)
            summary = session.ended()
            if summary is not None:
                session_ended = getattr(self._listener, "session_ended", None)
                if session_ended is not None:
                    session_ended(summary)
                properties = listening.session_ended(summary, self._app.platform)
                properties.update(session.preset_usage)  # optional (556)
                self._exchange.usage(
                    listening.SESSION_ENDED, properties, datetime.now(UTC)
                )
            timelines = session.timelines()
            if timelines is not None:  # where its caption time went (543)
                timelines["platform"] = self._app.platform
                self._exchange.usage(
                    listening.TIMELINE_SUMMARISED, timelines, datetime.now(UTC)
                )
        finally:
            with self._lock:
                self._stopping -= 1
        if self._exchange.has_waiting():
            self._sync_soon(self._sync_delay)

    def _hand_on(self, session: ListeningSession) -> None:
        """A stopped listening session's finished speech that was never
        answered goes to the listening session open now, if there is one,
        to be sent again (polyglotic-hq 277). When what's captured changes
        the app opens a new session at once, and the server closes the old
        one as the new one's `hello` arrives: the old one's wait for its
        last answers ends then. With no session open, nobody is listening:
        it's dropped, as before."""
        handed = session.hand_over()
        if not handed:
            return
        with self._lock:
            successor = self._listening
        if successor is None:
            return
        log.info(
            "%d finished caption(s) unanswered handed to the new session",
            len(handed),
        )
        successor.take_on(handed)

    def learned(self, event: LearningEvent) -> None:
        """One of Learning's events: while a listening session is open, a
        lookup or a save is counted in its summary - the only usage
        statistics about them (polyglotic-hq DECISIONS.md #20)."""
        session = self._listening
        if session is not None:
            session.learned(event)

    def captured(self, capture: Capture) -> None:
        """What is captured now: each listening session's summary keeps
        how long in each mode and at each number of apps (polyglotic-hq
        project 134) - sent only with consent to usage statistics."""
        self._capture = capture
        session = self._listening
        if session is not None:
            session.captured(capture)

    def did(self, action: SessionAction) -> None:
        """The learner did something the listening session's summary
        counts: opened a transcript, flagged a line. Nothing while no one
        listens."""
        session = self._listening
        if session is not None:
            session.did(action)

    def preset_step(self, step: PresetStep, changes: int) -> None:
        """A step on the chosen preset - saved, saved as new, discarded -
        that carried `changes` settings, counted in the listening session's
        summary (polyglotic-hq 587). Nothing while no one listens."""
        session = self._listening
        if session is not None:
            session.preset_step(step, changes)

    def joined(self, on: bool) -> None:
        """The joined window is on (or off): a listening session open while
        it's on says so in its summary."""
        self._joined = on
        if on:
            self.did(SessionAction.JOINED_WINDOW)

    def songs(self, on: bool) -> None:
        """Whether a music player is heard in songs mode now (595): a
        listening session's summary keeps how long - sent only with consent
        to usage statistics."""
        if on == self._songs:
            return
        self._songs = on
        session = self._listening
        if session is not None:
            session.songs(on)

    def recheck(self, request: RecheckRequest) -> bool:
        """A flagged line's speech, to check on the best models: sent on the
        listening session, the answer to the listener's `rechecked`. False
        when nobody is listening (or the session can't send it)."""
        session = self._listening
        return session is not None and session.recheck(request)

    @property
    def listening(self) -> ListeningSession | None:
        return self._listening

    @property
    def idle(self) -> bool:
        """No session open and none due (nothing waits, or sync sessions
        have stopped for good)."""
        with self._lock:
            return (
                self._listening is None
                and self._sync is None
                and self._timer is None
                and not self._stopping
            )

    def sign_out(self) -> None:
        """Closes every session, drops what waits to be sent - it was the
        signed-out account's, and the next to sign in on this PC may be
        someone else - and forgets this install's device token. Signing in
        again takes a new invite code; then `start`."""
        self.disconnect_account(StopReason.SIGN_IN_NEEDED)
        self._exchange.drop_waiting()
        self._credentials.forget()

    def disconnect_account(self, reason: StopReason = StopReason.CLOSED) -> None:
        """Stop sessions before replacing a credential. Call off the UI thread."""
        with self._lock:
            self.sync_stopped = StopReason.SIGN_IN_NEEDED
            self._cancel_timer()
            sessions = [s for s in (self._listening, self._sync) if s is not None]
            self._listening = self._sync = None
            self._moved = False
        for session in sessions:
            session.stop(reason=reason)

    def close(self) -> None:
        """Stops every session (the app is quitting), waiting for them: the
        listening session sends its last finished speech first and its
        summary is kept; what's waiting stays in the outbox for next time."""
        with self._lock:
            self._closed = True
            self._cancel_timer()
            listening, sync = self._listening, self._sync
            self._listening = self._sync = None
            self._moved = False
            if listening is not None:
                self._stopping += 1
        if sync is not None:
            sync.stop()
        if listening is not None:
            self._finish_listening(listening)

    # --- Sync sessions --------------------------------------------------------------

    def _something_waiting(self) -> None:
        session = self._listening
        if session is not None and not self._moved:
            session.wake()
        else:
            self._sync_soon(self._sync_delay)

    def _listening_parked(self, session: ListeningSession) -> None:
        """A terminal listening refusal leaves learning sync available."""
        with self._lock:
            if self._listening is not session:
                return  # already let go
            self._moved = True
        if self._exchange.has_waiting():
            self._sync_soon(self._sync_delay)

    def _listening_open(self) -> bool:
        """A listening session that sends what waits (called with the lock)."""
        return self._listening is not None and not self._moved

    def _sync_soon(self, delay: float) -> None:
        with self._lock:
            if (
                self._closed
                or self.sync_stopped is not None
                or self._listening_open()
                or self._sync is not None
                or self._timer is not None
            ):
                return
            self._timer = threading.Timer(delay, self._sync_now)
            self._timer.daemon = True
            self._timer.start()

    def _sync_now(self) -> None:
        with self._lock:
            self._timer = None
            if self._closed or self._listening_open() or self._sync is not None:
                return
            session = ListeningSession(
                self._server,
                self._credentials,
                self._app,
                ListeningSettings(),
                lambda: None,
                _SyncListener(self),
                timings=self._timings,
                exchange=self._exchange,
                purpose="sync",
                maintenance=self.maintenance,
                time_zone=self._time_zone,
            )
            self._sync = session
        session.start()

    def _sync_ended(self, status: Status) -> None:
        """On the sync session's thread, as it stops: done, or try again
        later - after a failure, or what the server didn't take."""
        waiting = self._exchange.has_waiting()
        with self._lock:
            self._sync = None
            if status.stopped not in (None, StopReason.CLOSED):
                self.sync_stopped = status.stopped
                log.info("sync sessions stopped: %s", status.stopped)
                return
            if status.close_code == NORMAL and not waiting:
                self._failures = 0
                return
            wait = self._retry_waits[min(self._failures, len(self._retry_waits) - 1)]
            self._failures += 1
        self._sync_soon(wait)

    def _maintenance_told(self, window: Maintenance | None) -> None:
        """A session was told the planned maintenance window (or none):
        kept for the next session, and `main` told."""
        self.maintenance = window
        self._listener.maintenance_changed(window)

    def _cancel_timer(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None


class _ListeningListener:
    """The listening session's listener: `main`'s, told everything - and
    the connection, told when listening moves to another device."""

    def __init__(self, connection: Connection, listener: SessionListener) -> None:
        self._connection = connection
        self._listener = listener
        self.session: ListeningSession | None = None

    def _superseded(self) -> bool:
        """A newer listening session is open: this one - closing, on its own
        thread, once its last speech is answered - is no longer the one
        whose state the app shows."""
        current = self._connection.listening
        return current is not None and current is not self.session

    def status_changed(self, status: Status) -> None:
        if (
            status.stopped
            in (
                StopReason.LISTENING_MOVED,
                StopReason.ALLOWANCE_EXHAUSTED,
                StopReason.REGISTRATION_REQUIRED,
                StopReason.CROSS_BORDER_CONSENT_REQUIRED,
            )
            and self.session is not None
        ):
            self._connection._listening_parked(self.session)
        if self._superseded():
            # Its "stopped" came after its successor's "connecting" or
            # "listening" whenever what's captured changed, and the windows
            # said "Stopped" while captions came (polyglotic-hq 271).
            log.info("a closing session's %s isn't shown", status.state.value)
            return
        self._listener.status_changed(status)

    def caption_updated(self, update: CaptionUpdate) -> None:
        milestones = self._connection.milestones
        if milestones is not None and update.kind is CaptionKind.FINISHED:
            milestones.caption_shown()
        self._listener.caption_updated(update)

    def respoken(self, caption_id: CaptionId) -> bool:
        """Preserve the app-local learner identity through this proxy."""
        is_respoken = getattr(self._listener, "respoken", None)
        return bool(is_respoken is not None and is_respoken(caption_id))

    def pace_changed(self, live_interval_min: float | None) -> None:
        self._listener.pace_changed(live_interval_min)

    def speaking_pace(
        self,
        pace: tuple[dict[str, PaceReading], dict[str, PaceReading]],
    ) -> None:
        """Carry the measured pace through the listening-session proxy."""
        listener = getattr(self._listener, "speaking_pace", None)
        if listener is not None:
            listener(pace)

    def minutes_changed(self, used: float, left: float | None) -> None:
        self._listener.minutes_changed(used, left)

    def allowance_changed(
        self, allowance: protocol.AllowanceUpdate | protocol.AllowanceExhausted
    ) -> None:
        if not self._superseded():
            self._listener.allowance_changed(allowance)

    def notice(self, code: str) -> None:
        self._listener.notice(code)

    def caption_failed(self) -> None:
        self._listener.caption_failed()

    def caption_dropped(self, caption_id: CaptionId) -> None:
        self._listener.caption_dropped(caption_id)

    def connection_stalled(self, stalled: bool) -> None:
        if stalled and self._superseded():
            return  # its end still clears a stall it said (False goes on)
        self._listener.connection_stalled(stalled)

    def rechecked(self, result: RecheckResult) -> None:
        self._listener.rechecked(result)

    def plan_changed(self, plan: protocol.PlanState) -> None:
        self._listener.plan_changed(plan)

    def maintenance_changed(self, window: Maintenance | None) -> None:
        self._connection._maintenance_told(window)


class _SyncListener:
    """A sync session's listener: its end - and the account's plan, which
    `main` shows whichever session brought it."""

    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def status_changed(self, status: Status) -> None:
        if status.state is SessionState.STOPPED:
            self._connection._sync_ended(status)

    def caption_updated(self, update: CaptionUpdate) -> None:
        pass

    def pace_changed(self, live_interval_min: float | None) -> None:
        pass

    def minutes_changed(self, used: float, left: float | None) -> None:
        pass

    def allowance_changed(
        self, allowance: protocol.AllowanceUpdate | protocol.AllowanceExhausted
    ) -> None:
        pass

    def notice(self, code: str) -> None:
        pass

    def caption_failed(self) -> None:
        pass

    def caption_dropped(self, caption_id: CaptionId) -> None:
        pass

    def connection_stalled(self, stalled: bool) -> None:
        pass

    def rechecked(self, result: RecheckResult) -> None:
        pass

    def plan_changed(self, plan: protocol.PlanState) -> None:
        self._connection._listener.plan_changed(plan)

    def maintenance_changed(self, window: Maintenance | None) -> None:
        self._connection._maintenance_told(window)
