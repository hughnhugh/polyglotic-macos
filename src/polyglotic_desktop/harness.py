r"""A developer harness for listening, without the UI.

Lists the apps with sound, captures one of them (or the whole system),
optionally with the mic, and either prints what would be sent (`capture`:
each live update, finished caption and withdrawal, with its caption id,
live section, speech times, the captions it replaces and the size of its
Ogg Opus speech) or sends it to a server and prints the captions that come
back (`listen`: the bare caption view, until D1's interface). Not the
product: `main` wires the real app.

    uv run python -m polyglotic_desktop.harness list
    uv run python -m polyglotic_desktop.harness capture --app 1234 --seconds 30
    uv run python -m polyglotic_desktop.harness capture --system --mic
    uv run python -m polyglotic_desktop.harness capture --play clip.wav --play other.wav --gap 1.2
    uv run python -m polyglotic_desktop.harness sign-in --server http://127.0.0.1:8080
    uv run python -m polyglotic_desktop.harness listen --server http://127.0.0.1:8080 --play clip.wav --targets zh
    uv run python -m polyglotic_desktop.harness listen --server ... --replay clip.wav --replay other.wav
    uv run python -m polyglotic_desktop.harness consent --usage --exposures
    uv run python -m polyglotic_desktop.harness learn --save 榴莲 --known 今天 --look-up 天气
    uv run python -m polyglotic_desktop.harness sync --server http://127.0.0.1:8080
    uv run python -m polyglotic_desktop.harness words
    uv run python -m polyglotic_desktop.harness delete-learning --server ... --on-this-pc
    uv run python -m polyglotic_desktop.harness sign-out
    uv run python -m polyglotic_desktop.harness bleed --seconds 20

`--play` starts a test player of its own (a child Python process) and
captures only that: the clips are trimmed of silence at their ends, joined
with `--gap` seconds of silence, played quietly (peak -26 dBFS) and handed
to the player in memory. `--replay` feeds the clips straight into the app
instead, with no player and no audio device (`platform/replay.py`). Use
public test audio (polyglotic-hq's FLEURS clips), never someone's real
audio.

`bleed` is for a learner whose speakers' sound is captioned as their own
speech: with a video playing on the speakers and the learner silent, it
holds 20s of the mic and of what Windows' default output plays in memory,
then prints only numbers - how loud each was, how many outputs played,
how often the mic-bleed check calls the mic the speakers, and how late
the speakers reach the mic (decision 0082). Nothing is kept or sent.

`sign-in` asks for an invite code (not echoed) and keeps the device token
in Windows Credential Manager under `Polyglotic/harness` - not the app's
own entry; `sign-out` deletes it.

The connection's data - consent, learning data, the outbox - is the
harness's own, in `--data` (`%APPDATA%\\Polyglotic\\harness` unless
given): `consent` records the choices; `learn` looks up, saves or marks
words in the Chinese dictionary (`--dictionaries`, built by
`tools.dictionaries.build`), which puts learning events in the outbox,
offline; `sync` opens a sync session - consent, learning events, finished
days' exposure counts and usage go out, and statuses and saved words from
the server are applied; `words` lists the saved words and the statuses
set; `delete-learning` deletes the learning data on the server, and on
this "PC" too with `--on-this-pc`. A second install (a "second PC") is
another `--credentials` entry with another `--data` folder. `listen` uses
the same data: it syncs, and leaves its session summary (with consent).

Privacy: no audio, speech or caption text is written to disk; audio and
speech stay in memory and only their sizes and times are printed. The
`--data` folder holds learning data (entry IDs, no sentences from the
harness) and the outbox, which is content-free. `listen` prints the captions it
gets back to this console - that is its job - and logs nothing of them.
"""

import argparse
import getpass
import io
import logging
import os
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import soundfile as sf

from polyglotic_desktop.adapters.sqlite_dictionary import SqliteDictionary
from polyglotic_desktop.adapters.sqlite_learning import SqliteLearningStore
from polyglotic_desktop.adapters.sqlite_outbox import SqliteOutbox
from polyglotic_desktop.adapters.windows_credentials import WindowsCredentialStore
from polyglotic_desktop.connection import protocol
from polyglotic_desktop.connection.app import AppInfo
from polyglotic_desktop.connection.client import Connection
from polyglotic_desktop.connection.exchange import DataExchange
from polyglotic_desktop.connection.session import SessionListener, SessionState, Status
from polyglotic_desktop.connection.sign_in import SignedIn, redeem
from polyglotic_desktop.core.learning.lookups import LookupContext
from polyglotic_desktop.core.learning.statuses import StatusSource
from polyglotic_desktop.core.learning.vocabulary import (
    EntryText,
    Vocabulary,
    VocabularyChanged,
)
from polyglotic_desktop.core.lexicon.chinese import ChineseDictionary
from polyglotic_desktop.core.lexicon.entries import DEFAULT_CHINESE_SCHEME
from polyglotic_desktop.core.lexicon.meanings import short_meaning
from polyglotic_desktop.core.listening.captions import (
    CaptionKind,
    CaptionUpdate,
    Language,
)
from polyglotic_desktop.core.listening.maintenance import Maintenance
from polyglotic_desktop.core.listening.recheck import RecheckResult
from polyglotic_desktop.core.listening.settings import ListeningSettings
from polyglotic_desktop.core.listening.sources import Source, SourceId
from polyglotic_desktop.core.listening.timing import (
    CaptionId,
    CaptionTiming,
    Decision,
    TranscriptionRequest,
    WithdrawCaption,
)
from polyglotic_desktop.core.shared import (
    EntryFacts,
    EntryId,
    LearningEvent,
    WordStatus,
)
from polyglotic_desktop.platform.audio_buffer import AudioBuffer
from polyglotic_desktop.platform.mic_bleed import (
    BLEED_MAX_LAG_SEC,
    SURVEY_MAX_LAG_SEC,
    SURVEY_STRETCH_SEC,
    BleedSurvey,
    survey,
)
from polyglotic_desktop.platform.replay import ReplayCapture
from polyglotic_desktop.platform.speech_detection import (
    MIC_GAIN_MAX,
    SpeechDetector,
    load_model,
)
from polyglotic_desktop.platform.speech_pipeline import SpeechPipeline
from polyglotic_desktop.platform.windows.apps import WindowsAppList
from polyglotic_desktop.platform.windows.capture import (
    AppCapture,
    MicCapture,
    SystemCapture,
    app_capture_support,
)
from polyglotic_desktop.platform.windows.categories import category_of
from polyglotic_desktop.platform.windows.devices import (
    Flow,
    active_devices,
    default_device,
    outputs_playing,
)
from polyglotic_desktop.platform.windows.system import os_name, os_version
from polyglotic_desktop.ports.capture import AudioCapture, SourceCategory

PLAYBACK_PEAK = 0.05  # about -26 dBFS: quiet
SILENCE_BELOW = 0.02  # of the clip's peak: trimmed from its ends
TRAILING_SILENCE_SEC = 2.0  # after the last clip, so its caption finishes
HARNESS_ENTRY = "Polyglotic/harness"  # never the app's own entry
DATA = Path(os.environ.get("APPDATA") or ".") / "Polyglotic" / "harness"
DICTIONARIES = Path("build/dictionaries")
SYNC_WAIT_SEC = 20.0


def list_sources() -> None:
    print(f"Per-app capture (yes, try or no): {app_capture_support()}")
    print("Apps with sound (process id, name, playing, category):")
    for app in WindowsAppList().playing_apps():
        state = "playing" if app.playing else "idle"
        print(f"  {app.process_id:>7}  {app.name:<32} {state:<8} {app.category.value}")
    for flow, label in ((Flow.OUTPUT, "Outputs"), (Flow.INPUT, "Mics")):
        default = default_device(flow)
        print(f"{label}:")
        for device in active_devices(flow):
            mark = "*" if default and device.id == default.id else " "
            print(f"  {mark} {device.name}  [{device.id}]")


def _quiet_playlist(paths: list[str], gap: float) -> bytes:
    """The clips, trimmed, each made quiet (recordings differ a lot in
    level), joined by `gap` seconds of silence, as a 16-bit WAV in memory."""
    parts: list[np.ndarray] = []
    rate: int | None = None
    for path in paths:
        audio, clip_rate = sf.read(path, dtype="float32", always_2d=True)
        audio = audio.mean(axis=1)
        if rate is None:
            rate = clip_rate
        if clip_rate != rate:
            raise SystemExit(f"{path}: {clip_rate} Hz; the others are {rate} Hz")
        peak = max(1e-6, float(np.abs(audio).max()))
        loud = np.flatnonzero(np.abs(audio) >= SILENCE_BELOW * peak)
        if len(loud):
            audio = audio[loud[0] : loud[-1] + 1]
        if parts:
            parts.append(np.zeros(int(gap * rate), dtype=np.float32))
        parts.append(audio * (PLAYBACK_PEAK / peak))
    parts.append(np.zeros(int(TRAILING_SILENCE_SEC * (rate or 1)), dtype=np.float32))
    joined = np.concatenate(parts)
    out = io.BytesIO()
    sf.write(out, joined, rate, format="WAV", subtype="PCM_16")
    print(
        f"Test player: {len(paths)} clip(s), {len(joined) / (rate or 1):.1f}s, gap {gap}s"
    )
    return out.getvalue()


def _start_player(wav: bytes) -> subprocess.Popen[bytes]:
    """A child Python process playing `wav` from memory (winsound)."""
    script = "import sys, winsound; winsound.PlaySound(sys.stdin.buffer.read(), winsound.SND_MEMORY)"
    python = getattr(sys, "_base_executable", sys.executable)  # not a venv launcher
    player = subprocess.Popen([python, "-c", script], stdin=subprocess.PIPE)
    assert player.stdin is not None
    player.stdin.write(wav)
    player.stdin.close()
    return player


class _Printer:
    def __init__(self, t0: float) -> None:
        self.t0 = t0
        self.names: dict[str, str] = {}
        self.counts: dict[str, int] = {}
        self.bytes = 0

    def short(self, caption_id: str) -> str:
        return self.names.setdefault(caption_id, f"c{len(self.names) + 1}")

    def show(self, decision: Decision, speech: bytes | None) -> None:
        now = time.perf_counter() - self.t0
        source = f"{decision.source.id}/{decision.source.category.value}"
        if isinstance(decision, WithdrawCaption):
            kind = "withdrawn"
            line = f"{self.short(decision.caption_id):<4} {source:<14} reason {decision.reason.value}"
        else:
            assert isinstance(decision, TranscriptionRequest)
            kind = decision.kind.value
            section = f"s{decision.section}" if decision.section is not None else "  "
            start, end = decision.speech_start - self.t0, decision.speech_end - self.t0
            replaces = ",".join(self.short(c) for c in decision.replaces) or "-"
            size = f"{len(speech) / 1000:.1f} kB" if speech else "no audio"
            line = (
                f"{self.short(decision.caption_id):<4} {section} {source:<14} "
                f"speech {start:6.2f}-{end:6.2f} ({end - start:5.2f}s) "
                f"replaces {replaces:<6} {size}"
            )
            self.bytes += len(speech or b"")
        self.counts[kind] = self.counts.get(kind, 0) + 1
        print(f"+{now:6.2f}s  {kind:<9} {line}", flush=True)


class _Sources:
    """The sources a run captures, started on `pipeline`."""

    def __init__(self, args: argparse.Namespace, pipeline: SpeechPipeline) -> None:
        self.player: subprocess.Popen[bytes] | None = None
        self.replay: ReplayCapture | None = None
        main_capture: AudioCapture
        if args.play:
            self.player = _start_player(_quiet_playlist(args.play, args.gap))
            main_capture = AppCapture(self.player.pid, "test player")
            main_source = Source(SourceId("app"), SourceCategory.OTHER)
        elif args.replay:
            self.replay = ReplayCapture.from_files(args.replay, args.gap)
            print(f"Replay: {len(args.replay)} clip(s), {self.replay.seconds:.1f}s")
            main_capture = self.replay
            main_source = Source(SourceId("app"), SourceCategory.OTHER)
        elif args.app:
            apps = {a.process_id: a for a in WindowsAppList().playing_apps()}
            app = apps.get(args.app)
            name = app.name if app else f"process {args.app}"
            main_capture = AppCapture(args.app, name)
            main_source = Source(
                SourceId("app"), app.category if app else category_of(name)
            )
        else:
            main_capture = SystemCapture()
            main_source = Source(SourceId("system"), SourceCategory.SYSTEM)
        main_buffer = pipeline.add_source(main_source, main_capture)
        self.captures: dict[SourceId, AudioCapture] = {main_source.id: main_capture}
        if args.mic:
            reference: AudioBuffer = main_buffer
            if not isinstance(main_capture, SystemCapture):
                reference = pipeline.add_reference(SystemCapture())  # decision 0004
            mic = MicCapture(args.mic_device)
            pipeline.add_source(
                Source(SourceId("mic"), SourceCategory.MIC), mic, reference
            )
            self.captures[SourceId("mic")] = mic

    def report(self) -> None:
        for source_id, cap in self.captures.items():
            print(f"  {source_id}: capturing {cap.capturing!r}, error {cap.error!r}")

    def ended(self) -> bool:
        """The test player or the replay has finished."""
        if self.player is not None:
            return self.player.poll() is not None
        return self.replay is not None and self.replay.finished.is_set()

    def close(self) -> None:
        if self.player is not None and self.player.poll() is None:
            self.player.kill()


def _pipeline(args: argparse.Namespace, on_ready: Callable[[], None]) -> SpeechPipeline:
    timing = CaptionTiming(
        live_update_interval=None if args.interval <= 0 else args.interval
    )
    model = load_model()
    return SpeechPipeline(
        lambda: SpeechDetector(model),
        timing,
        on_ready=on_ready,
        new_mic_detector=lambda: SpeechDetector(model, MIC_GAIN_MAX, beds=False),
    )


def capture(args: argparse.Namespace) -> None:
    wake = threading.Event()
    pipeline = _pipeline(args, wake.set)
    t0, cpu0 = time.perf_counter(), time.process_time()
    printer = _Printer(t0)
    sources = _Sources(args, pipeline)

    every = f"every {args.interval}s" if pipeline.timing.live_update_interval else "off"
    print(f"Listening for {args.seconds:.0f}s (live updates {every})...")
    deadline = t0 + args.seconds
    reported = False
    try:
        while time.perf_counter() < deadline:
            wake.wait(0.2)
            wake.clear()
            while (item := pipeline.take()) is not None:
                printer.show(*item)
            if not reported and time.perf_counter() - t0 > 1.0:
                reported = True
                sources.report()
            if sources.ended() and args.stop_with_player:
                time.sleep(1.5)  # let the last finished caption come through
                while (item := pipeline.take()) is not None:
                    printer.show(*item)
                break
    except KeyboardInterrupt:
        pass
    finally:
        pipeline.stop()
        sources.close()
    elapsed = time.perf_counter() - t0
    cpu = time.process_time() - cpu0
    counts = ", ".join(f"{n} {k}" for k, n in printer.counts.items()) or "nothing"
    print(
        f"Done after {elapsed:.1f}s: {counts}; {printer.bytes / 1000:.1f} kB of speech; "
        f"CPU {cpu:.2f}s ({cpu / elapsed:.1%} of one core, this process)."
    )


def sign_in(args: argparse.Namespace) -> None:
    if sys.stdin.isatty():
        code = getpass.getpass("Invite code (not shown): ")
    else:
        code = sys.stdin.readline()
    store = WindowsCredentialStore(args.credentials)
    result = redeem(args.server, code, store, AppInfo.this_app(os_name(), os_version()))
    if isinstance(result, SignedIn):
        print(
            f"Signed in (cohort {result.cohort}); the token is in Credential Manager."
        )
    else:
        raise SystemExit(f"Not signed in: {result}")


def sign_out(args: argparse.Namespace) -> None:
    # all of it, install id too: a trial's entry leaves nothing behind (the
    # app's own sign-out keeps the install id - decision 0080)
    WindowsCredentialStore(args.credentials).delete()
    print("Signed out: the credential is deleted from Credential Manager.")


class _CaptionView:
    """The bare caption view: caption updates as lines in this console.

    Live updates are shown as they come; a finished caption with its
    translations; a joined caption names the captions it takes in; a
    withdrawn one its reason. Throwaway: D1 builds the real one."""

    def __init__(self, t0: float, pipeline: SpeechPipeline | None) -> None:
        self._t0 = t0
        self._pipeline = pipeline
        self._names: dict[str, str] = {}
        self.counts: dict[str, int] = {}
        self.processing: list[int] = []

    def _say(self, line: str) -> None:
        print(f"+{time.perf_counter() - self._t0:6.2f}s  {line}", flush=True)

    def _name(self, caption_id: str) -> str:
        return self._names.setdefault(caption_id, f"c{len(self._names) + 1}")

    def status_changed(self, status: Status) -> None:
        extra = ""
        if status.state is SessionState.WAITING and status.retry_in is not None:
            extra = f" - trying again in {status.retry_in:.1f}s"
        elif status.state is SessionState.STOPPED:
            extra = f" - {status.stopped}"
        code = f" (last closed {status.close_code})" if status.close_code else ""
        self._say(f"[session {status.state}{extra}{code}]")

    def caption_updated(self, update: CaptionUpdate) -> None:
        kind = update.kind.value
        self.counts[kind] = self.counts.get(kind, 0) + 1
        if update.processing_ms is not None:
            self.processing.append(update.processing_ms)
        name = self._name(update.caption_id)
        if update.kind is CaptionKind.WITHDRAWN:
            self._say(f"withdrawn {name} ({update.reason})")
            return
        joins = ",".join(self._name(c) for c in update.replaces)
        joined = f" (takes in {joins})" if joins else ""
        original = " ".join(c.original for c in update.clauses)
        self._say(f"{kind:<9} {name}{joined} [{update.language}] {original}")
        if update.kind is CaptionKind.FINISHED:
            languages = {lang for c in update.clauses for lang in c.translations}
            for language in sorted(languages):
                text = " ".join(
                    c.translations.get(language, "") for c in update.clauses
                )
                print(f"{'':10} {language}: {text}", flush=True)

    def pace_changed(self, live_interval_min: float | None) -> None:
        if self._pipeline is not None:
            self._pipeline.set_pace_hint(live_interval_min)
        if live_interval_min is not None:
            self._say(f"[pace: live updates at most every {live_interval_min}s]")

    def minutes_changed(self, used: float, left: float | None) -> None:
        self._say(f"[minutes used this month: {used}]")

    def allowance_changed(
        self, allowance: protocol.AllowanceUpdate | protocol.AllowanceExhausted
    ) -> None:
        self._say(f"[allowance: {allowance.left}%]")

    def notice(self, code: str) -> None:
        self._say(f"[notice: {code}]")

    def caption_failed(self) -> None:
        self._say("[a finished caption failed on the server]")

    def caption_dropped(self, caption_id: CaptionId) -> None:
        self._say("[a finished caption won't come: its live caption ends]")

    def connection_stalled(self, stalled: bool) -> None:
        self._say(f"[connection stalled: {'yes' if stalled else 'no'}]")

    def rechecked(self, result: RecheckResult) -> None:
        self._say(f"[recheck: {result.outcome.value}]")  # the harness never asks

    def plan_changed(self, plan: protocol.PlanState) -> None:
        self._say(f"[plan: {plan.tier}, {plan.status}]")

    def maintenance_changed(self, window: Maintenance | None) -> None:
        when = "none" if window is None else f"{window.starts_at:%H:%M}Z"
        self._say(f"[planned maintenance: {when}]")


class _Arrivals:
    """The exchange's listener: what the server sends back, kept for the
    main thread - the learning store is used from one thread."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._events: list[LearningEvent] = []
        self.deleted = threading.Event()

    def learning_arrived(self, events: Sequence[LearningEvent]) -> None:
        with self._lock:
            self._events.extend(events)

    def learning_deleted(self) -> None:
        self.deleted.set()

    def take(self) -> list[LearningEvent]:
        with self._lock:
            taken, self._events = self._events, []
        return taken


class _Data:
    """The harness's own consent, learning data and outbox, in `--data`."""

    def __init__(self, args: argparse.Namespace) -> None:
        self.folder = Path(args.data)
        self.folder.mkdir(parents=True, exist_ok=True)
        self.arrivals = _Arrivals()
        self.outbox = SqliteOutbox(self.folder / "outbox.sqlite")
        self.exchange = DataExchange(
            self.outbox, self.outbox, self.arrivals, "cedict"
        )  # the harness learns Chinese
        self._dictionaries = Path(args.dictionaries)
        self._vocabulary: Vocabulary | None = None
        self._dictionary: ChineseDictionary | None = None

    @property
    def dictionary(self) -> ChineseDictionary:
        if self._dictionary is None:
            path = self._dictionaries / "cedict.sqlite"
            if not path.exists():
                raise SystemExit(f"No dictionary at {path}: build it first.")
            self._dictionary = ChineseDictionary(SqliteDictionary(path))
        return self._dictionary

    @property
    def vocabulary(self) -> Vocabulary:
        if self._vocabulary is None:
            dictionary = self.dictionary

            def facts(entry_id: EntryId, scheme: str) -> EntryFacts | None:
                return dictionary.facts(entry_id, scheme)

            store = SqliteLearningStore(self.folder / "learning.sqlite")
            self._vocabulary = Vocabulary(store, facts, DEFAULT_CHINESE_SCHEME.id)
            self._vocabulary.subscribe(self._published)
        return self._vocabulary

    def _published(self, event: LearningEvent | VocabularyChanged) -> None:
        if not isinstance(event, VocabularyChanged):
            self.exchange.learning(event)

    def describe(self, entry_id: EntryId) -> EntryText | None:
        entry = self.dictionary.entry(entry_id)
        if entry is None:
            return None
        meaning = short_meaning([entry])
        return EntryText(entry.headword, entry.traditional, entry.reading, meaning)

    def connection(
        self, args: argparse.Namespace, listener: SessionListener | None = None
    ) -> Connection:
        store = WindowsCredentialStore(args.credentials)
        if store.load() is None:
            raise SystemExit("Not signed in: run `sign-in` first.")
        return Connection(
            args.server,
            store,
            AppInfo.this_app(os_name(), os_version()),
            self.exchange,
            listener or _CaptionView(time.perf_counter(), None),
            retry_waits=(5.0,),
        )

    def hand_over_exposures(self) -> None:
        """Finished days' exposure counts: to the outbox with consent,
        dropped without."""
        today = datetime.now(UTC).date()
        days = self.vocabulary.take_finished_exposure_days(today)
        if days:
            shared = self.exchange.exposures(days)
            print(
                f"{len(days)} finished day(s) of exposures {'kept to send' if shared else 'dropped: no consent'}."
            )

    def apply_arrivals(self) -> None:
        events = self.arrivals.take()
        if events:
            changed = self.vocabulary.apply_from_server(events, self.describe)
            print(
                f"From the server: {len(events)} status(es) and saved word(s), {changed} applied here."
            )

    def wait_for(self, connection: Connection) -> None:
        deadline = time.monotonic() + SYNC_WAIT_SEC
        time.sleep(0.3)
        while time.monotonic() < deadline and not connection.idle:
            time.sleep(0.2)
        connection.close()
        waiting = len(self.outbox.waiting())
        print(
            f"Outbox: {waiting} item(s) still waiting"
            + (" (the server wasn't reached)" if waiting else "")
            + f"; {self.outbox.dropped()} ever dropped for room."
        )


def consent(args: argparse.Namespace) -> None:
    data = _Data(args)
    choice = data.exchange.choose_consent(args.usage, args.crashes, args.exposures)
    print(
        f"Consent: usage statistics {choice.usage}, crash reports {choice.crashes}, "
        f"sharing exposures {choice.exposures} - waiting to be sent."
    )


def learn(args: argparse.Namespace) -> None:
    data = _Data(args)
    vocabulary = data.vocabulary
    actions = [
        (args.look_up, "look up"),
        (args.save, "save"),
        (args.unsave, "unsave"),
        (args.known, "known"),
        (args.learning, "learning"),
    ]
    before = len(data.outbox.waiting())
    for words, action in actions:
        for word in words or ():
            entries = data.dictionary.lookup(word)
            if not entries:
                raise SystemExit(f"{word}: not in the dictionary")
            entry = entries[0]
            if action == "look up":
                vocabulary.looked_up(entry.facts(vocabulary.scheme), pinned=False)
            elif action == "save":
                vocabulary.save(
                    entry.entry_id,
                    entry.headword,
                    entry.traditional,
                    entry.reading,
                    short_meaning(entries),
                    vocabulary.categories[0].id,
                    LookupContext("", ""),
                )
            elif action == "unsave":
                vocabulary.unsave(entry.entry_id)
            else:
                vocabulary.set_status(
                    entry.entry_id, WordStatus(action), StatusSource.LEARNER
                )
            print(f"{action}: {word} ({entry.entry_id})")
    added = len(data.outbox.waiting()) - before
    print(f"{added} item(s) added to the outbox; {len(data.outbox.waiting())} waiting.")


def sync(args: argparse.Namespace) -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )
    data = _Data(args)
    data.hand_over_exposures()
    print(f"Outbox: {len(data.outbox.waiting())} item(s) waiting before the sync.")
    connection = data.connection(args)
    connection.start()
    data.wait_for(connection)
    data.apply_arrivals()


def words(args: argparse.Namespace) -> None:
    data = _Data(args)
    vocabulary = data.vocabulary
    names = {c.id: c.name for c in vocabulary.categories}
    print(f"Saved words ({len(vocabulary.saved_words)}):")
    for word in vocabulary.saved_words:
        print(
            f"  {word.headword:<8} {word.entry_id}  in {names.get(word.category_id)!r}, "
            f"saved {word.saved_at:%Y-%m-%d %H:%M:%S}"
        )
    own = [r for r in vocabulary.vocabulary_list() if r.status.is_learners_own]
    print(f"Statuses set ({len(own)}):")
    for row in own:
        entry = data.dictionary.entry(row.entry_id)
        headword = entry.headword if entry else "?"
        print(f"  {headword:<8} {row.entry_id}  {row.status.status.value}")


def delete_learning(args: argparse.Namespace) -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )
    data = _Data(args)
    data.exchange.delete_learning()
    connection = data.connection(args)
    connection.start()
    data.wait_for(connection)
    data.arrivals.take()  # the sync after the deletion: nothing is left
    if not data.arrivals.deleted.is_set():
        print("The server didn't confirm the deletion yet; it waits in the outbox.")
        return
    print("Deleted on the server.")
    if args.on_this_pc:
        data.vocabulary.delete_learning_data()
        print(
            "Deleted on this PC too: statuses, saved words, exposure counts,"
            " and any copy set aside after damage."
        )


def listen(args: argparse.Namespace) -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )
    data = _Data(args)
    connection: Connection | None = None

    def speech_ready() -> None:
        session = connection.listening if connection is not None else None
        if session is not None:
            session.speech_ready()

    pipeline = _pipeline(args, speech_ready)
    t0 = time.perf_counter()
    view = _CaptionView(t0, pipeline)
    settings = ListeningSettings(
        spoken_language=Language(args.spoken) if args.spoken != "detect" else None,
        targets=tuple(Language(t) for t in args.targets.split(",") if t),
    )
    connection = data.connection(args, view)
    data.hand_over_exposures()
    connection.start_listening(
        settings, pipeline.take, None if args.interval <= 0 else args.interval
    )
    sources = _Sources(args, pipeline)
    deadline = t0 + args.seconds
    try:
        while time.perf_counter() < deadline:
            time.sleep(0.2)
            if sources.ended() and args.stop_with_player:
                time.sleep(3.0)  # the last finished caption, there and back
                break
    except KeyboardInterrupt:
        pass
    finally:
        pipeline.stop()
        sources.close()
        connection.stop_listening()  # its summary goes in a sync session, with consent
    counts = ", ".join(f"{n} {k}" for k, n in view.counts.items()) or "no captions"
    times = sorted(view.processing)
    server = f"; server time p50 {times[len(times) // 2]} ms" if times else ""
    print(f"Done after {time.perf_counter() - t0:.1f}s: {counts}{server}.")
    data.wait_for(connection)
    data.apply_arrivals()


def bleed(args: argparse.Namespace) -> None:
    """The mic beside what Windows' default output plays, for `--seconds`,
    in memory only: the mic-bleed check's numbers (decision 0082)."""
    seconds = max(args.seconds, SURVEY_STRETCH_SEC + 2.0)
    played, heard = AudioBuffer(seconds + 5.0), AudioBuffer(seconds + 5.0)
    output, mic = SystemCapture(), MicCapture(args.mic_device)

    def into(buffer: AudioBuffer) -> Callable[[float, bytes], None]:
        return lambda start, samples: buffer.append(
            start, np.frombuffer(samples, np.float32)
        )

    print(f"Play a video on your speakers and stay silent for {seconds:.0f}s.")
    output.start(into(played))
    mic.start(into(heard))
    start = time.perf_counter()
    playing: list[int] = []
    try:
        while time.perf_counter() - start < seconds:
            time.sleep(1.0)
            count = outputs_playing()
            if count is not None:
                playing.append(count)
            print(".", end="", flush=True)
    finally:
        output.stop()
        mic.stop()
    print()
    # the first second left out: the streams opening
    found = survey(heard, played, start + 1.0, time.perf_counter())
    for line in bleed_lines(found, max(playing, default=None)):
        print(line)


def bleed_lines(found: BleedSurvey, outputs: int | None) -> list[str]:
    """What `bleed` prints: numbers, then what they mean."""
    n = found.stretches

    def number(value: float | None, scale: float = 1.0, digits: int = 2) -> str:
        return "-" if value is None else f"{value * scale:.{digits}f}"

    played = (
        f"{found.played_db:.0f} dBFS; nearly silent in {found.played_silent} of {n}"
    )
    checked = (
        f"bleed in {found.caught} of {n}; correlation {number(found.correlation)};"
        f" cancelled {number(found.cancelled)}"
    )
    best = f"{number(found.lag, 1000, 0)} ms late, correlation {number(found.best)}"
    lines = [
        f"stretches of {SURVEY_STRETCH_SEC:.0f}s: {n}",
        f"what played (Windows' default output), loudest: {played}",
        f"the mic, loudest: {found.mic_db:.0f} dBFS",
        f"outputs playing: {'-' if outputs is None else outputs}",
        f"the check (the mic up to {BLEED_MAX_LAG_SEC:.1f}s late): {checked}",
        f"best match (up to {SURVEY_MAX_LAG_SEC:.1f}s late): {best}",
    ]
    if n == 0:
        meaning = "Too short to tell: run it for longer."
    elif found.played_silent * 2 > n:
        meaning = (
            "Windows' default output played next to nothing: is the sound going"
            " to another output?"
        )
    elif found.best is None or found.best < 0.4:
        meaning = (
            "The mic hardly hears the speakers (headphones, or the speakers"
            " quiet): nothing to catch."
        )
    elif found.lag is not None and found.lag > BLEED_MAX_LAG_SEC and found.best >= 0.6:
        meaning = (
            f"The speakers reach the mic {found.lag:.2f}s late, past the"
            f" check's {BLEED_MAX_LAG_SEC:.1f}s."
        )
    elif found.caught * 5 >= n * 4:
        meaning = "The check catches the speakers in the mic here."
    else:
        meaning = f"The check catches the speakers in {found.caught} of {n} stretches."
    return [*lines, meaning]


def _add_sources(run: argparse.ArgumentParser) -> None:
    what = run.add_mutually_exclusive_group()
    what.add_argument("--app", type=int, metavar="PID", help="one app, by process id")
    what.add_argument(
        "--system", action="store_true", help="the whole system (the default)"
    )
    what.add_argument(
        "--play", action="append", metavar="WAV", help="a test player of public clips"
    )
    what.add_argument(
        "--replay",
        action="append",
        metavar="WAV",
        help="public clips fed straight in: no player, no audio device",
    )
    run.add_argument(
        "--gap", type=float, default=1.2, help="seconds between --play/--replay clips"
    )
    run.add_argument("--mic", action="store_true", help="also caption the mic")
    run.add_argument(
        "--mic-device", metavar="ID", help="a mic's id (from list); default: Windows'"
    )
    run.add_argument("--seconds", type=float, default=30.0)
    run.add_argument(
        "--interval", type=float, default=1.5, help="live updates; 0 = off"
    )
    run.add_argument(
        "--keep-going",
        dest="stop_with_player",
        action="store_false",
        help="don't stop when --play or --replay ends",
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m polyglotic_desktop.harness")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list", help="apps with sound, outputs and mics")
    run = commands.add_parser("capture", help="capture and print what would be sent")
    _add_sources(run)
    talk = commands.add_parser("listen", help="send to a server and print captions")
    _add_sources(talk)
    talk.add_argument("--server", required=True, help="e.g. http://127.0.0.1:8080")
    talk.add_argument("--targets", default="zh", help="target languages, e.g. zh,en")
    talk.add_argument("--spoken", default="detect", help="the spoken language")
    enter = commands.add_parser("sign-in", help="redeem an invite code (asked for)")
    enter.add_argument("--server", required=True)
    leave = commands.add_parser("sign-out", help="delete the device token")
    agree = commands.add_parser("consent", help="record consent choices (default: no)")
    agree.add_argument("--usage", action="store_true", help="usage statistics")
    agree.add_argument("--crashes", action="store_true", help="crash reports")
    agree.add_argument("--exposures", action="store_true", help="share exposures")
    study = commands.add_parser("learn", help="look up, save or mark words, offline")
    for name in ("look-up", "save", "unsave", "known", "learning"):
        study.add_argument(f"--{name}", action="append", metavar="WORD")
    syncing = commands.add_parser("sync", help="a sync session: send and fetch")
    syncing.add_argument("--server", required=True)
    show = commands.add_parser("words", help="saved words and statuses set")
    delete = commands.add_parser("delete-learning", help="delete the learning data")
    delete.add_argument("--server", required=True)
    delete.add_argument("--on-this-pc", action="store_true", help="here too")
    check = commands.add_parser(
        "bleed", help="does the mic hear the speakers? numbers only, nothing kept"
    )
    check.add_argument("--seconds", type=float, default=20.0)
    check.add_argument(
        "--mic-device", metavar="ID", help="a mic's id (from list); default: Windows'"
    )
    for sub in (talk, enter, leave, syncing, delete):
        sub.add_argument(
            "--credentials",
            default=HARNESS_ENTRY,
            help="the Credential Manager entry (default: the harness's own)",
        )
    for sub in (talk, agree, study, syncing, show, delete):
        sub.add_argument("--data", default=str(DATA), help="the harness's own data")
        sub.add_argument("--dictionaries", default=str(DICTIONARIES))
    args = parser.parse_args(argv)
    if args.command == "list":
        list_sources()
    elif args.command == "capture":
        capture(args)
    elif args.command == "listen":
        listen(args)
    elif args.command == "sign-in":
        sign_in(args)
    elif args.command == "consent":
        consent(args)
    elif args.command == "learn":
        learn(args)
    elif args.command == "sync":
        sync(args)
    elif args.command == "words":
        words(args)
    elif args.command == "delete-learning":
        delete_learning(args)
    elif args.command == "bleed":
        bleed(args)
    else:
        sign_out(args)


if __name__ == "__main__":
    main()
