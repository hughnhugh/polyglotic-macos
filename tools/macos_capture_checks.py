"""Mac capture proven on GitHub's Mac (polyglotic-hq 411's checks, 412): the
macOS job's `capture` part, after `measure` (BlackHole installed, the
system-audio permission written). Each check prints a pass, fail or
unknown line and goes in a JSON file; the job fails only on a fail -
unknown is what the machine didn't let us see, never a failure.

    uv run --no-sync python -m tools.macos_capture_checks OUT.json [--app dist/Polyglotic.app]
    uv run --no-sync python -m tools.macos_capture_checks OUT.json --dry-run  # any OS: the plan

In this order (the granted checks first: macOS's permission service may
remember an answer, so the denied one comes last):
- blackhole: BlackHole 2ch listed as a speaker and a mic, and macOS's
  defaults (411's 3); installed here if `measure` didn't, and made the
  defaults if it isn't (SwitchAudioSource).
- afplay, apps, app_tap: `afplay` plays a FLEURS clip (1); the apps list
  shows it playing (2); `AppCapture` of it hears it - non-zero 16kHz
  audio whose loudness follows the clip's - with no error (4).
- everything_else: two players, `afplay` with a 1kHz tone and a renamed
  copy of it (its bytes: `second_player`) with a 3kHz tone; `EverythingElseCapture` of the first hears
  only the second's tone (6). If Core Audio reports both as one app (one
  bundle ID), the app's own rule leaves both out, and it must hear neither.
- system_taps: `SystemCapture(None)` (a global tap) and
  `SystemCapture(<BlackHole's UID>)` (a device tap) hear the clip (7).
- mic: `MicCapture(<BlackHole's UID>)` hears the clip played into
  BlackHole: PortAudio, and the microphone permission (8).
- drift: a global tap for `--drift-minutes`: how often the stamps start
  again (`capture.Stamper`), and how far the audio's end drifts from the
  app's clock, in ms a minute (9).
- packed: with `--app`, the packed app's `--check-capture` while the clip
  plays: catap's and PortAudio's libraries load inside the bundle.
- not_allowed: the system-audio permission's rows written denied; a new
  process's `AppCapture` of afplay must say `NOT_ALLOWED` within about
  11 s (5).
- not_asked: the rows removed (never asked: macOS may hold the tap's start
  for an answer, 419's run 1); the same within about 11 s; the rows are
  written back allowed after.

Never the user's PC: this runs only on GitHub's macOS machine, which has
no microphone or speakers of its own - only BlackHole, a virtual device -
and plays only the app's own FLEURS sample (CC BY 4.0) and tones. The
audio heard is measured here and never kept.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import traceback
from collections.abc import Callable, Iterator
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from tools import macos_measure

PASS, FAIL, UNKNOWN = "pass", "fail", "unknown"
RATE = 16_000
"""What every capture delivers: 16kHz mono float32 (`AudioCallback`)."""
FRAME_SEC = 0.05
"""An envelope's frame: loudness every 50 ms."""
LIKE = 0.5
"""How closely a capture's loudness must follow what played (Pearson's r)."""
OVERLAP = 0.5
"""How much of the shorter envelope a lag must overlap to be judged."""
TONES = (1000.0, 3000.0)
"""The two players' tones: both under the resampler's 7.2kHz cut-off."""
TONE_HEARD = 0.02
"""A tone's amplitude (of 0.3 played) that counts as heard."""
NOT_ALLOWED_BY = 12.0
"""411's "within about 11 s": the watch's 10 s and a check's second."""
WAIT_NOT_ALLOWED = 16.0
RESTARTS_A_MINUTE = 2.0
"""More stamp restarts a minute than this is a fail: each can move the
audio up to 0.2 s (`capture.RESYNC_SEC`)."""
BLACKHOLE = "BlackHole"
SETTLE_SEC = 5.0
"""The drift's slope leaves out the tap's first seconds."""


@dataclass
class Result:
    check: str
    outcome: str
    said: str
    facts: dict[str, Any] = field(default_factory=dict)


# -- what was heard, judged (any OS) --------------------------------------------


def envelope(audio: np.ndarray, rate: float) -> np.ndarray:
    """Loudness (RMS) every FRAME_SEC."""
    size = max(1, round(rate * FRAME_SEC))
    frames = len(audio) // size
    if frames == 0:
        return np.zeros(0)
    shaped = audio[: frames * size].astype(np.float64).reshape(frames, size)
    return np.sqrt(np.mean(shaped**2, axis=1))


def likeness(heard: np.ndarray, played: np.ndarray) -> float:
    """How closely one envelope follows the other: the best Pearson's r over
    every lag at which they overlap by at least OVERLAP of the shorter (when
    the capture started is unknown, and it may run on past the end of what
    played: polyglotic-hq 419's app tap, which started 1.5 s into a clip
    played once and listened 2 s past its end). 0 when either is flat."""
    short, long_ = (heard, played) if len(heard) <= len(played) else (played, heard)
    n = len(short)
    need = max(10, int(np.ceil(n * OVERLAP)))
    if n < 10 or np.std(short) == 0:
        return 0.0
    best: float | None = None
    for lag in range(need - n, len(long_) - need + 1):
        a = short[max(0, -lag) : min(n, len(long_) - lag)]
        b = long_[max(0, lag) : max(0, lag) + len(a)]
        if a.std() == 0 or b.std() == 0:
            continue
        r = float(np.mean((a - a.mean()) * (b - b.mean())) / (a.std() * b.std()))
        best = r if best is None else max(best, r)
    return 0.0 if best is None else round(best, 3)


def tone_level(audio: np.ndarray, rate: float, hz: float) -> float:
    """The amplitude of the `hz` sine in `audio` (a single-frequency DFT)."""
    if len(audio) == 0:
        return 0.0
    n = np.arange(len(audio))
    value = np.dot(audio.astype(np.float64), np.exp(-2j * np.pi * hz * n / rate))
    return round(float(2 * abs(value) / len(audio)), 4)


def tone(
    hz: float, seconds: float, rate: int = 48_000, level: float = 0.3
) -> np.ndarray:
    n = np.arange(round(seconds * rate))
    return (level * np.sin(2 * np.pi * hz * n / rate)).astype(np.float32)


def looped(clip: np.ndarray, rate: int, seconds: float, gap: float = 1.0) -> np.ndarray:
    """`clip` again and again, `gap` of silence between, `seconds` long."""
    one = np.concatenate([clip, np.zeros(round(gap * rate), dtype=clip.dtype)])
    times = int(np.ceil(seconds * rate / len(one)))
    return np.tile(one, times)[: round(seconds * rate)]


def drift_ms_a_minute(lags: list[tuple[float, float]]) -> float | None:
    """The slope of (when, how far the audio's end trails the app's clock),
    in ms a minute - how fast the device's clock leaves the app's - after
    the first SETTLE_SEC."""
    if lags:
        lags = [(t, d) for t, d in lags if t - lags[0][0] >= SETTLE_SEC]
    if len(lags) < 10:
        return None
    when = np.array([t for t, _ in lags])
    lag = np.array([d for _, d in lags])
    slope = np.polyfit(when - when[0], lag, 1)[0]
    return round(float(slope) * 60_000, 2)


def heard_verdict(
    peak: float, like: float | None, error: str | None
) -> tuple[str, str]:
    """A capture of something playing: sound, following what played, no error."""
    if peak == 0:
        if error == "not allowed":
            return UNKNOWN, "only zeros and NOT_ALLOWED: the grant wasn't honoured here"
        return FAIL, f"only zeros (error: {error})"
    if error not in (None, "The app has closed.", "not allowed"):
        return FAIL, f"sound, but the capture says: {error}"
    if like is not None and like < LIKE:
        return FAIL, f"sound that doesn't follow the clip (r = {like})"
    return PASS, f"sound (peak {peak:.3f}), r = {like}"


def everything_else_verdict(
    same_app: bool, first: float, second: float, permission: bool
) -> tuple[str, str]:
    """`first`, `second`: each tone's amplitude in the capture."""
    if not permission:
        return UNKNOWN, "no tap has heard sound in this run: nothing to judge by"
    if same_app:
        if max(first, second) < TONE_HEARD:
            return PASS, "both players are one app to Core Audio: both left out"
        return FAIL, f"one app, left out, but heard ({first}, {second})"
    if second >= TONE_HEARD and first < max(TONE_HEARD, second / 10):
        return PASS, f"only the second player ({second} against {first})"
    return FAIL, f"tones heard: first {first}, second {second}"


def not_allowed_verdict(
    peak: float, said_after: float | None, playing: bool, error: str | None
) -> tuple[str, str]:
    """The denied check: `said_after`, seconds until the capture said
    NOT_ALLOWED (None if it didn't)."""
    if not playing:
        return UNKNOWN, "Core Audio never listed afplay playing: no tap was opened"
    if peak > 0:
        return (
            UNKNOWN,
            (
                "heard sound with the rows changed: macOS didn't take the"
                " permission away (GitHub's Mac doesn't honour a written"
                " denial: polyglotic-hq 419)"
            ),
        )
    if said_after is None:
        return FAIL, f"only zeros, but never NOT_ALLOWED (error: {error})"
    if said_after > NOT_ALLOWED_BY:
        return FAIL, f"NOT_ALLOWED, but after {said_after:.1f} s"
    return PASS, f"NOT_ALLOWED after {said_after:.1f} s"


def drift_verdict(heard: bool, restarts: int, minutes: float) -> tuple[str, str]:
    if not heard:
        return UNKNOWN, "the tap heard nothing: no clock to compare"
    rate = restarts / minutes if minutes else 0.0
    said = f"{restarts} restart(s) in {minutes:g} min"
    return (PASS if rate <= RESTARTS_A_MINUTE else FAIL), said


def exit_code(results: list[Result]) -> int:
    return 1 if any(r.outcome == FAIL for r in results) else 0


def report(results: list[Result], facts: dict[str, Any]) -> dict[str, Any]:
    counts = {o: sum(r.outcome == o for r in results) for o in (PASS, FAIL, UNKNOWN)}
    return {"summary": counts, "facts": facts, "checks": [asdict(r) for r in results]}


def plan(app: Path | None, drift_minutes: float) -> list[str]:
    """What a run does, in order (`--dry-run`)."""
    steps = [
        (
            "blackhole: list the devices; brew install --cask blackhole-2ch and restart"
            " Core Audio if missing; SwitchAudioSource -t output/input if not the defaults"
        ),
        (
            f"grant: {macos_measure.SERVICE} written for {macos_measure.AGENT} and"
            f" {macos_measure.BUNDLE_ID}, in the system's and the user's TCC.db"
        ),
        "afplay, apps, app_tap: afplay <the FLEURS clip>; the apps list; AppCapture",
        "everything_else: afplay <1kHz>, <renamed copy> <3kHz>; EverythingElseCapture",
        "system_taps: afplay <the clip, looped>; SystemCapture(None), (BlackHole)",
        "mic: MicCapture(BlackHole) while the clip plays into BlackHole",
        f"drift: SystemCapture(None) for {drift_minutes:g} min",
    ]
    if app is not None:
        steps.append(f"packed: {app}/Contents/MacOS/Polyglotic --check-capture")
    steps += [
        (
            f"not_allowed: {macos_measure.SERVICE} rows written denied; a new"
            " process's AppCapture of afplay"
        ),
        (
            f"not_asked: DELETE {macos_measure.SERVICE} rows; a new process's"
            " AppCapture of afplay; the rows written back allowed"
        ),
    ]
    return steps


# -- on the Mac -------------------------------------------------------------------


def sh(command: list[str], seconds: int = 60) -> dict[str, Any]:
    return macos_measure.run(command, seconds)


class Listened:
    """A capture run for a while: what it delivered, as one array."""

    def __init__(self) -> None:
        self.pieces: list[bytes] = []
        self.lags: list[tuple[float, float]] = []
        self.capturing: set[str] = set()
        self.error: str | None = None
        self.not_allowed_after: float | None = None
        self.stacks: dict[str, list[str]] = {}

    def __call__(self, start: float, samples: bytes) -> None:
        self.pieces.append(samples)
        end = start + len(samples) / 4 / RATE
        now = time.perf_counter()
        self.lags.append((now, now - end))

    @property
    def audio(self) -> np.ndarray:
        return np.frombuffer(b"".join(self.pieces), dtype="<f4")

    @property
    def peak(self) -> float:
        audio = self.audio
        return round(float(np.max(np.abs(audio))), 4) if len(audio) else 0.0

    def facts(self) -> dict[str, Any]:
        return {
            "seconds": round(len(self.audio) / RATE, 2),
            "peak": self.peak,
            "error": self.error,
            "capturing": sorted(self.capturing),
            "not_allowed_after": self.not_allowed_after,
        } | ({"stacks": self.stacks} if self.stacks else {})


def listen(capture: Any, seconds: float) -> Listened:
    """Runs `capture` for `seconds`, watching its name and error."""
    got = Listened()
    started = time.perf_counter()
    capture.start(got)
    try:
        while (elapsed := time.perf_counter() - started) < seconds:
            time.sleep(0.25)
            if capture.capturing:
                got.capturing.add(str(capture.capturing))
            if capture.error is not None:
                got.error = capture.error
            if capture.error == "not allowed" and got.not_allowed_after is None:
                got.not_allowed_after = round(elapsed, 2)
    finally:
        if capture.capturing is None:  # never opened, or stopped: where it is
            got.stacks = stacks(type(capture).__name__)
        capture.stop()
    return got


def stacks(prefix: str) -> dict[str, list[str]]:
    """Where each thread whose name starts `prefix` is now, innermost last:
    file names and functions only (what holds a capture that never opened)."""
    frames = sys._current_frames()
    return {
        t.name: [
            f"{Path(f.filename).name}:{f.name}:{f.lineno}"
            for f in traceback.extract_stack(frames[t.ident])[-6:]
        ]
        for t in threading.enumerate()
        if t.name.startswith(prefix) and t.ident in frames
    }


@contextlib.contextmanager
def playing(program: str, wav: Path) -> Iterator[subprocess.Popen[bytes]]:
    """`program wav` playing (our own child, stopped by its handle)."""
    player = subprocess.Popen([program, str(wav)])
    try:
        yield player
    finally:
        if player.poll() is None:
            player.terminate()
            with contextlib.suppress(subprocess.TimeoutExpired):
                player.wait(5)


def second_player(afplay: str, folder: Path) -> Path:
    """A renamed copy of `afplay`, a second app to Core Audio (a command
    line tool is known by its executable's name): its bytes only. Copying
    its file flags as well (`shutil.copy2`) is refused - System Integrity
    Protection marks /usr/bin's files restricted, and only the system may
    set that flag (polyglotic-hq 419: run 1's PermissionError)."""
    copy = folder / "afplay-second"
    shutil.copyfile(afplay, copy)
    copy.chmod(0o755)
    return copy


def write_wav(path: Path, audio: np.ndarray, rate: int) -> Path:
    import soundfile as sf

    sf.write(str(path), audio, rate, subtype="FLOAT")
    return path


class Run:
    """One run's state: its folder, the sounds, the results so far."""

    def __init__(self, out: Path, app: Path | None, drift_minutes: float) -> None:
        from polyglotic_desktop.platform.replay import read_clip
        from polyglotic_desktop.platform.sample import sample_file

        self.out, self.app, self.drift_minutes = out, app, drift_minutes
        self.work = Path(tempfile.mkdtemp(prefix="polyglotic-412-"))
        sample = sample_file("zh")
        assert sample is not None, "the app's FLEURS sample"
        clip = read_clip(sample)
        self.clip_rate = 16_000
        self.clip = np.asarray(clip, dtype=np.float32).reshape(-1)
        self.clip_wav = write_wav(self.work / "clip.wav", self.clip, self.clip_rate)
        long_seconds = drift_minutes * 60 + 240
        self.long = looped(self.clip, self.clip_rate, long_seconds)
        self.long_wav = write_wav(self.work / "long.wav", self.long, self.clip_rate)
        self.tone_wavs = [
            write_wav(self.work / f"tone{int(hz)}.wav", tone(hz, 20), 48_000)
            for hz in TONES
        ]
        self.results: list[Result] = []
        self.facts: dict[str, Any] = {"macos": platform.mac_ver()[0]}
        self.blackhole_uid: str | None = None

    def add(self, check: str, verdict: tuple[str, str], **facts: Any) -> None:
        outcome, said = verdict
        self.results.append(Result(check, outcome, said, facts))
        print(f"{outcome:7} {check}: {said}", flush=True)

    # -- the devices
    def blackhole(self) -> None:
        from polyglotic_desktop.platform.macos import devices

        def found() -> list[Any]:
            try:
                return [d for d in devices.audio_devices() if BLACKHOLE in d.name]
            except OSError:
                return []

        steps = {name: command for name, command, _ in macos_measure.plan(None, 0)}
        if not found():
            self.facts["blackhole_installed_here"] = sh(steps["blackhole"], 600)["ok"]
            sh(steps["coreaudio_restart"])
            time.sleep(5)
        hole = found()
        if not hole:
            self.add("blackhole", (UNKNOWN, "BlackHole isn't listed: nothing can play"))
            return
        device = hole[0]
        self.blackhole_uid = device.uid
        if not (device.default_output and device.default_input):
            switch = shutil.which("SwitchAudioSource")
            if switch is None:
                sh(["brew", "install", "switchaudio-osx"], 300)
                switch = shutil.which("SwitchAudioSource")
            for kind in ("output", "input"):
                if switch:
                    sh([switch, "-t", kind, "-s", device.name])
            device = found()[0]
        listed = devices.sound_devices()
        both = device.uid in {s.id for s in listed.speakers} and device.uid in {
            s.id for s in listed.mics
        }
        defaults = (listed.default_speaker, listed.default_mic) == (
            device.uid,
            device.uid,
        )
        if not both:
            verdict = (FAIL, f"{device.name} isn't listed as both a speaker and a mic")
        elif not defaults:
            verdict = (UNKNOWN, f"{device.name} listed, but not made the defaults")
        else:
            verdict = (PASS, f"{device.name}: a speaker and a mic, and the defaults")
        self.add(
            "blackhole",
            verdict,
            uid=device.uid,
            speakers=[s.name for s in listed.speakers],
            mics=[s.name for s in listed.mics],
        )

    def grant(self, allowed: bool = True) -> None:
        """The permission's rows written, allowing it - or, `allowed` False,
        denying it (as a learner's "Don't Allow" leaves it)."""
        now = int(time.time())
        written = {}
        for client, kind in macos_measure.CLIENTS:
            for db, sudo in (
                (macos_measure.SYSTEM_TCC, ["sudo"]),
                (macos_measure.USER_TCC, []),
            ):
                row = macos_measure.grant(client, kind, now, allowed)
                written[f"{client} {db}"] = sh([*sudo, "sqlite3", db, row], 30)["ok"]
        key = "grants_written" if allowed else "denials_written"
        self.facts.setdefault(key, []).append(written)
        read = (
            "SELECT client, auth_value, auth_reason FROM access"
            f" WHERE service = '{macos_measure.SERVICE}';"
        )
        system = sh(["sudo", "sqlite3", macos_measure.SYSTEM_TCC, read])
        user = sh(["sqlite3", macos_measure.USER_TCC, read])
        self.facts.setdefault("rows_after", []).append(
            {"system": system.get("out"), "user": user.get("out")}
        )

    def revoke(self) -> dict[str, bool]:
        delete = f"DELETE FROM access WHERE service = '{macos_measure.SERVICE}';"
        return {
            "system": sh(["sudo", "sqlite3", macos_measure.SYSTEM_TCC, delete], 30)[
                "ok"
            ],
            "user": sh(["sqlite3", macos_measure.USER_TCC, delete], 30)["ok"],
        }

    # -- one app: 1, 2, 4
    def one_app(self) -> None:
        from polyglotic_desktop.platform.macos import apps
        from polyglotic_desktop.platform.macos.capture import AppCapture

        seconds = len(self.clip) / self.clip_rate
        started = time.perf_counter()
        with playing("afplay", self.clip_wav) as player:
            time.sleep(1.5)
            members = apps.grouped(apps.audio_processes())
            key = next(
                (k for k, m in members.items() if any(p.pid == player.pid for p in m)),
                None,
            )
            listed = apps.MacAppList().playing_apps()
            mine = [a for a in listed if a.process_id == player.pid]
            self.add(
                "apps",
                (PASS, f"listed as {mine[0].name!r}, {mine[0].category}")
                if mine and mine[0].playing
                else (FAIL, f"not listed playing ({len(listed)} apps listed)"),
                apps=[(a.name, a.playing, str(a.category)) for a in listed],
            )
            got = (
                listen(AppCapture(player.pid, key), seconds + 2)
                if key is not None
                else None
            )
            player.wait(seconds + 30)
        took = time.perf_counter() - started
        self.add(
            "afplay",
            (PASS, f"played {took:.1f} s of {seconds:.1f}")
            if player.returncode == 0 and took >= seconds * 0.9
            else (FAIL, f"exit {player.returncode} after {took:.1f} s"),
        )
        if got is None:
            self.add("app_tap", (UNKNOWN, "Core Audio never listed afplay"))
            return
        like = likeness(envelope(got.audio, RATE), envelope(self.clip, self.clip_rate))
        self.add(
            "app_tap",
            heard_verdict(got.peak, like, got.error),
            key=key,
            r=like,
            **got.facts(),
        )

    # -- 6
    def everything_else(self) -> None:
        from polyglotic_desktop.platform.macos import apps, capture

        copy = second_player(shutil.which("afplay") or "/usr/bin/afplay", self.work)
        with (
            playing("afplay", self.tone_wavs[0]) as first,
            playing(str(copy), self.tone_wavs[1]) as second,
        ):
            time.sleep(1.5)
            groups = apps.grouped(apps.audio_processes())
            keys = [
                next(
                    (k for k, m in groups.items() if any(p.pid == pid for p in m)), None
                )
                for pid in (first.pid, second.pid)
            ]
            got = listen(capture.EverythingElseCapture(first.pid), 8)
            exits = [first.poll(), second.poll()]  # None: still playing
        audio = got.audio[RATE:]  # past the tap's start
        levels = [tone_level(audio, RATE, hz) for hz in TONES]
        if None in keys:
            verdict = (UNKNOWN, f"Core Audio didn't list both players: {keys}")
        else:
            low, high = levels
            verdict = everything_else_verdict(
                keys[0] == keys[1], low, high, capture.TAPS.given
            )
        self.add(
            "everything_else",
            verdict,
            keys=keys,
            levels=levels,
            exits=exits,
            **got.facts(),
        )

    # -- 7, 8, 9, packed: the clip looped
    def while_looped(self) -> None:
        from polyglotic_desktop.platform.macos import capture

        played = envelope(self.long, self.clip_rate)
        with playing("afplay", self.long_wav):
            time.sleep(1.5)
            for name, device in (("global", None), ("device", self.blackhole_uid)):
                got = listen(capture.SystemCapture(device), 10)
                like = likeness(envelope(got.audio, RATE), played)
                self.add(
                    f"system_tap_{name}",
                    heard_verdict(got.peak, like, got.error),
                    r=like,
                    **got.facts(),
                )
            if self.blackhole_uid is None:
                self.add("mic", (UNKNOWN, "no BlackHole to listen to"))
            else:
                got = listen(capture.MicCapture(self.blackhole_uid), 10)
                like = likeness(envelope(got.audio, RATE), played)
                self.add(
                    "mic",
                    heard_verdict(got.peak, like, got.error),
                    r=like,
                    **got.facts(),
                )
            self.drift()
            self.packed()

    def drift(self) -> None:
        from polyglotic_desktop.platform.macos import capture

        restarts = [0]
        plain = capture.Stamper

        class Counted(capture.Stamper):
            """Counts each time the stamps start again from an arrival."""

            def __call__(self, arrival: float, seconds: float) -> float:
                before = self._next
                start = super().__call__(arrival, seconds)
                if before is not None and start != before:
                    restarts[0] += 1
                return start

        # the capture makes its Stamper by this name: counted for this tap only
        capture.Stamper = Counted  # type: ignore[misc]
        try:
            got = listen(capture.SystemCapture(None), self.drift_minutes * 60)
        finally:
            capture.Stamper = plain  # type: ignore[misc]
        slope = drift_ms_a_minute(got.lags)
        self.add(
            "drift",
            drift_verdict(got.peak > 0, restarts[0], self.drift_minutes),
            restarts=restarts[0],
            drift_ms_a_minute=slope,
            **got.facts(),
        )

    def packed(self) -> None:
        if self.app is None:
            return
        program = self.app / "Contents" / "MacOS" / "Polyglotic"
        if not program.is_file():
            self.add("packed", (UNKNOWN, f"no packed app at {program}"))
            return
        found_at = self.out.parent / "packed-capture.json"
        done = sh([str(program), "--check-capture", str(found_at)], 120)
        found = (
            json.loads(found_at.read_text(encoding="utf-8"))
            if found_at.is_file()
            else {}
        )
        heard = {k: v.get("heard") for k, v in found.items() if isinstance(v, dict)}
        if not found:
            verdict = (
                FAIL,
                f"no report (exit {done.get('code')}): {done.get('said', '')[-300:]}",
            )
        elif heard and all(heard.values()):
            verdict = (PASS, f"the packed app heard {sorted(heard)}")
        elif any(
            "Couldn't" in str(v.get("error"))
            for v in found.values()
            if isinstance(v, dict)
        ):
            verdict = (FAIL, "a capture couldn't start in the bundle")
        else:
            verdict = (UNKNOWN, f"started, but heard {heard}: the app's permission")
        self.add("packed", verdict, report=found, exit=done.get("code"))

    # -- 5, last: denied, then never asked
    def not_allowed(self) -> None:
        """The permission denied (its rows say so): the tap opens and hears
        zeros."""
        self.grant(allowed=False)
        self.denied_check("not_allowed")

    def not_asked(self) -> None:
        """The permission never asked (its rows removed): run 1 found the
        tap's start held while macOS waits for an answer nobody gives."""
        self.facts["revoked"] = self.revoke()
        try:
            self.denied_check("not_asked")
        finally:
            self.grant()

    def denied_check(self, check: str) -> None:
        child = self.out.parent / f"{check.replace('_', '-')}.json"
        sh(
            [
                sys.executable,
                "-m",
                "tools.macos_capture_checks",
                str(child),
                "--child-not-allowed",
            ],
            90,
        )
        found = json.loads(child.read_text(encoding="utf-8")) if child.is_file() else {}
        if not found:
            self.add(check, (UNKNOWN, "the child process wrote nothing"))
            return
        self.add(
            check,
            not_allowed_verdict(
                found["peak"],
                found["not_allowed_after"],
                found["playing"],
                found["error"],
            ),
            **found,
        )


def child_not_allowed(out: Path) -> int:
    """In a process of its own (`capture.TAPS` is per process): afplay's
    tap, with the permission's rows removed."""
    from polyglotic_desktop.platform.macos import apps
    from polyglotic_desktop.platform.macos.capture import AppCapture
    from polyglotic_desktop.platform.replay import read_clip
    from polyglotic_desktop.platform.sample import sample_file

    sample = sample_file("zh")
    assert sample is not None
    found: dict[str, Any] = {"playing": False}
    work = Path(tempfile.mkdtemp(prefix="polyglotic-412-"))
    clip = np.asarray(read_clip(sample), dtype=np.float32).reshape(-1)
    wav = write_wav(work / "clip.wav", looped(clip, 16_000, 40), 16_000)
    with playing("afplay", wav) as player:
        time.sleep(1.5)
        groups = apps.grouped(apps.audio_processes())
        key = next(
            (k for k, m in groups.items() if any(p.pid == player.pid for p in m)), None
        )
        found["playing"] = key is not None and any(p.playing for p in groups[key])
        if key is not None:
            got = listen(AppCapture(player.pid, key), WAIT_NOT_ALLOWED)
            found.update(got.facts())
    found.setdefault("peak", 0.0)
    found.setdefault("not_allowed_after", None)
    found.setdefault("error", None)
    out.write_text(json.dumps(found, indent=1), encoding="utf-8")
    shutil.rmtree(work, ignore_errors=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m tools.macos_capture_checks")
    parser.add_argument("out", type=Path)
    parser.add_argument("--app", type=Path)
    parser.add_argument("--drift-minutes", type=float, default=3.0)
    parser.add_argument("--dry-run", action="store_true", help="print the plan")
    parser.add_argument(
        "--child-not-allowed", action="store_true", help=argparse.SUPPRESS
    )
    args = parser.parse_args(argv)
    if args.dry_run:
        print("\n".join(plan(args.app, args.drift_minutes)))
        return 0
    if sys.platform != "darwin":
        print("macOS only: GitHub's macOS machine (the macOS job's capture part)")
        return 2
    if args.child_not_allowed:
        return child_not_allowed(args.out)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    run = Run(args.out, args.app, args.drift_minutes)
    steps: list[Callable[[], None]] = [
        run.blackhole,
        run.grant,
        run.one_app,
        run.everything_else,
        run.while_looped,
        run.not_allowed,
        run.not_asked,
    ]
    for step in steps:
        if step != run.blackhole and run.blackhole_uid is None:
            run.add(step.__name__, (UNKNOWN, "no BlackHole: nothing can play"))
            continue
        try:
            step()
        except Exception as e:  # noqa: BLE001 - one check's crash isn't the run's
            run.add(step.__name__, (FAIL, f"crashed: {type(e).__name__}: {e}"))
    found = report(run.results, run.facts)
    args.out.write_text(json.dumps(found, indent=1), encoding="utf-8")
    print(json.dumps(found["summary"]))
    shutil.rmtree(run.work, ignore_errors=True)
    return exit_code(run.results)


if __name__ == "__main__":
    os.environ.setdefault("PYTHONUNBUFFERED", "1")
    sys.exit(main())
