"""The Mac's hotkeys, voice, menu-bar icon and login item proven on GitHub's
Mac (polyglotic-hq 428): the macOS job's `parity` part, after `pack` and
`capture` (it installs BlackHole itself if capture didn't run). Each check
prints a pass, fail or unknown line and goes in a JSON file beside a
picture of the menu-bar icon; the job fails only on a fail - unknown is
what the machine didn't let us see.

    uv run --no-sync python -m tools.macos_parity_checks OUT_DIR [--app dist/Polyglotic.app]
    uv run --no-sync python -m tools.macos_parity_checks OUT_DIR --dry-run  # any OS: the plan

The app's own pieces run as the app runs them - Qt's event loop on the
main thread (cocoa), the speaker on its own:
- hotkeys_pressed: ⌃⌘L, ⌃⌘P and ⌃⌘H taken (`MacHotkeys`), then each
  pressed by AppleScript (System Events' `keystroke`, which the runner
  lets osascript send): each one's binding must run.
- hotkeys_taken: while this process holds them, another process asks for
  the same three: it must be told all three are taken; and once given
  back, they can be taken again.
- menu_keys: Qt writes the menus' keys "⌃⌘L" (the app's `shortcut_text`).
- voices_listed: macOS's voices through AVFoundation, the novelty voices
  left out, English among them.
- voice_made: "hello" made into sound (`MacVoices.synthesize`) on a
  thread of its own; how long it took, and how long the word is at each
  pace the card uses (`av_rate`).
- voice_moved: a word is made in a voice whose id macOS doesn't know - its
  name and language found in macOS's list, and a name it hasn't gives
  way to the language's own voice (`voices.av_voice`; polyglotic-hq 452:
  macOS's voices changed under a running process and the card said
  nothing).
- voice_heard: the card's whole path - `SpeakerThread` over `MacVoices`
  and `AudioPlayer` - says a word on macOS's default output, BlackHole,
  and the mic on BlackHole hears it; `sounding` and `ended` are told.
- said_recorded (polyglotic-hq 523): a recorded word as a learner hears
  it - a stand-in recording (a tone, Ogg Opus at 24 kHz as the packs'
  words) through `RecordedVoices`, its decoder, `SpeakerThread` and
  `AudioPlayer`, out on BlackHole and heard back: not silent, not clipped,
  loud enough, and as long and as high as it was made (a wrong rate moves
  both).
- said_by_macos (523): "Say it" in macOS's own voices - an English
  sentence and a Chinese phrase - made into sound first to know its
  length, then said on BlackHole and heard back: not silent, not clipped,
  loud enough, and as long as it was made.
- menu_bar: the menu bar has room for the icon, it is a template
  (`isMask`), shown; and a picture of it as macOS draws a template on a
  light and a dark menu bar (`menu-bar.png`, made here from the icon -
  never a screen capture). Dark mode switched on and off by AppleScript,
  `light_menu_bar` must follow.
- login_item: with `--app`, the packed app's `--check-parity`: Carbon,
  AVFoundation and ServiceManagement load inside the bundle, and macOS
  adds the app to its login items and takes it off again.

Never the user's PC: GitHub's Mac only, which has no speakers or mic of
its own - BlackHole only. Nothing heard is kept; the words said are
"hello" and "Polyglotic".
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
import threading
import time
import traceback
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from functools import partial
from pathlib import Path
from typing import Any

PASS, FAIL, UNKNOWN = "pass", "fail", "unknown"
KEYS = "LPH"
PRESS_WAIT_SEC = 4.0
"""How long a pressed hotkey's binding has to run."""
PACES = (1.0, 0.85, 0.7, 0.6)
"""The paces a word is made at: the card's are 1.0 and 0.7."""


@dataclass
class Result:
    check: str
    outcome: str
    said: str
    facts: dict[str, Any] = field(default_factory=dict)


def plan(app: Path | None) -> list[str]:
    steps = [
        (
            "hotkeys_pressed: MacHotkeys(L, P, H).start(); osascript keystroke each"
            " with {control down, command down}; each binding ran"
        ),
        (
            "hotkeys_taken: a child process's MacHotkeys(L, P, H).start() says all"
            " three taken while held here; given back, taken again"
        ),
        "menu_keys: QKeySequence('Meta+Ctrl+L') as NativeText is ⌃⌘L",
        "voices_listed: MacVoices().found()",
        "voice_made: synthesize('hello', an English voice) at each pace",
        (
            "voice_moved: synthesize('hello') in that voice under an id macOS"
            " hasn't, then with a name it hasn't too"
        ),
        (
            "voice_heard: BlackHole the default output; SpeakerThread(MacVoices,"
            " AudioPlayer).say('Polyglotic') while MicCapture(BlackHole) listens"
        ),
        (
            "said_recorded: RecordedVoices(a stand-in tone, Ogg Opus 24 kHz) said on"
            " BlackHole and heard: length, pitch, level, clipping"
        ),
        (
            "said_by_macos: MacVoices says an English sentence and a Chinese phrase"
            " on BlackHole; heard against the made clip: length, level, clipping"
        ),
        (
            "menu_bar: QSystemTrayIcon(menu_bar_icon) shown; menu-bar.png; dark mode"
            " on and off by osascript, light_menu_bar() follows"
        ),
    ]
    if app is not None:
        steps.append(f"login_item: {app}/Contents/MacOS/Polyglotic --check-parity")
    return steps


def keystroke(key: str) -> dict[str, Any]:
    """⌃⌘ and `key` pressed through System Events (the runner allows
    osascript Accessibility and Apple Events to System Events)."""
    script = (
        'tell application "System Events" to keystroke "'
        + key.lower()
        + '" using {control down, command down}'
    )
    return run(["osascript", "-e", script], 30)


def run(command: list[str], seconds: int) -> dict[str, Any]:
    try:
        done = subprocess.run(
            command, capture_output=True, text=True, timeout=seconds, check=False
        )
    except (OSError, subprocess.TimeoutExpired) as problem:
        return {"ok": False, "said": f"{type(problem).__name__}: {problem}"}
    return {
        "ok": done.returncode == 0,
        "out": done.stdout.strip()[-2000:],
        "said": done.stderr.strip()[-1000:],
    }


@contextmanager
def warnings_of(name: str) -> Iterator[list[str]]:
    """The warnings logger `name` writes meanwhile, as text: the speaker
    says why a word wasn't said (`speaking.SpeakerThread._say`) only in its
    log, which the check otherwise loses (polyglotic-hq 443: voice_heard's
    "ended [False]" in two runs of five, with nothing saying why)."""
    said: list[str] = []

    class Kept(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            said.append(record.getMessage())

    logger = logging.getLogger(name)
    handler = Kept(logging.WARNING)
    logger.addHandler(handler)
    try:
        yield said
    finally:
        logger.removeHandler(handler)


def peak(samples: list[bytes]) -> float:
    import numpy as np

    audio = np.frombuffer(b"".join(samples), dtype="<f4")
    return round(float(np.max(np.abs(audio))), 4) if len(audio) else 0.0


def clip_peak(pcm: bytes) -> int:
    from array import array

    samples = array("h")
    samples.frombytes(pcm)
    return max((abs(s) for s in samples), default=0)


# -- sound out (polyglotic-hq 523): measuring what was heard, on any OS ----------------

HEARD_RATE = 16_000
"""What the mic hands on (`MicCapture`: the speech detector's rate)."""
TONE_HZ, TONE_SEC = 880.0, 0.7
"""The stand-in recording: a tone, so its pitch shows a wrong rate."""
SAID = (
    ("en", "Polyglotic says this sentence at its own pace."),
    ("zh", "你好，我在学习中文。"),
)
"""What "Say it" says in macOS's voices: a sentence, and a Chinese phrase."""
FRAME_SEC = 0.02
CLIPPED = 0.999
"""A sample this near full scale is clipped."""
QUIET_DBFS = -45.0
"""Quieter than this (the voiced part's RMS) and a learner hears too little."""
LENGTH_WITHIN = {True: 0.12, False: 0.25}
"""How far the heard length may be from the made one: a tone's (True) is
exact; a voice's start and end are softer."""
PITCH_WITHIN = 0.03


def tone_ogg(
    hz: float = TONE_HZ, seconds: float = TONE_SEC, rate: int = 24_000
) -> bytes:
    """The stand-in recorded word: a tone faded in and out, as Ogg Opus at
    24 kHz - the packs' words' format (decoded by `clip_of_ogg`)."""
    import io

    import numpy as np
    import soundfile

    t = np.arange(int(seconds * rate)) / rate
    fade = np.minimum(1.0, np.minimum(t, seconds - t) / 0.02)
    out = io.BytesIO()
    soundfile.write(out, 0.5 * fade * np.sin(2 * np.pi * hz * t), rate,
                    format="OGG", subtype="OPUS")  # fmt: skip
    return out.getvalue()


def _made_trimmed(voices: Any, text: str, voice: Any, trimmed: Any) -> Any:
    """`text` made into sound by `voices` and trimmed as the speaker trims it."""
    return trimmed(voices.synthesize(text, voice, 1.0))


class _OneClip:
    """`WordClips` with one recording for every word."""

    def __init__(self, data: bytes) -> None:
        self.data = data

    def clip(self, _word: str) -> bytes:
        return self.data


def listened(samples: Any, rate: int) -> dict[str, Any]:
    """What a recording of something said shows: how long it is from its
    first sound to its last (`voiced_sec`), its peak, how much of it is
    clipped, its level (the voiced part's RMS, dBFS) and its strongest
    pitch."""
    import numpy as np

    audio = np.asarray(samples, dtype=np.float64)
    found: dict[str, Any] = {"heard_sec": round(len(audio) / rate, 3), "voiced_sec": 0.0,
                             "peak": 0.0, "clipped": 0.0, "level_dbfs": None,
                             "pitch_hz": None}  # fmt: skip
    size = int(FRAME_SEC * rate)
    if len(audio) < size:
        return found
    frames = audio[: len(audio) // size * size].reshape(-1, size)
    loudness = np.sqrt(np.mean(frames**2, axis=1))
    floor = max(1e-3, float(loudness.max()) * 10 ** (-30 / 20))
    loud = np.flatnonzero(loudness > floor)
    found["peak"] = round(float(np.max(np.abs(audio))), 4)
    if len(loud) == 0:
        return found
    voiced = audio[loud[0] * size : (loud[-1] + 1) * size]
    found["voiced_sec"] = round(len(voiced) / rate, 3)
    found["clipped"] = round(float(np.mean(np.abs(voiced) >= CLIPPED)), 5)
    rms = float(np.sqrt(np.mean(voiced**2)))
    found["level_dbfs"] = round(float(20 * np.log10(max(rms, 1e-9))), 1)
    padded = 1 << int(np.ceil(np.log2(len(voiced) * 4)))
    spectrum = np.abs(np.fft.rfft(voiced * np.hanning(len(voiced)), padded))
    found["pitch_hz"] = round(float(np.argmax(spectrum[1:]) + 1) * rate / padded, 1)
    return found


def voiced_seconds_of_clip(clip: Any) -> float:
    """A made clip's length from its first sound to its last (`listened`)."""
    import numpy as np

    pcm = np.frombuffer(clip.pcm, dtype="<i2").astype(np.float64) / 32768.0
    if clip.channels > 1:
        pcm = pcm.reshape(-1, clip.channels).mean(axis=1)
    return float(listened(pcm, clip.rate)["voiced_sec"])


def sound_problems(
    found: dict[str, Any], made_sec: float, made_hz: float | None
) -> list[str]:
    """What's wrong with what was heard, against what was made: silence,
    clipping, too quiet, the wrong length (a wrong rate), the wrong pitch."""
    if not found["voiced_sec"]:
        return ["nothing heard: silent"]
    problems = []
    if found["clipped"] > 0.001:
        problems.append(f"clipped: {found['clipped']:.2%} of it at full scale")
    if found["level_dbfs"] is not None and found["level_dbfs"] < QUIET_DBFS:
        problems.append(f"too quiet: {found['level_dbfs']} dBFS")
    within = LENGTH_WITHIN[made_hz is not None]
    if made_sec and abs(found["voiced_sec"] / made_sec - 1) > within:
        problems.append(
            f"{found['voiced_sec']} s heard of {made_sec:.3f} s made: the wrong speed"
        )
    if (
        made_hz
        and found["pitch_hz"]
        and abs(found["pitch_hz"] / made_hz - 1) > PITCH_WITHIN
    ):
        problems.append(
            f"{found['pitch_hz']} Hz heard of {made_hz} Hz made: the wrong rate"
        )
    return problems


class Checks:
    def __init__(self, out: Path, app: Path | None) -> None:
        from PySide6.QtWidgets import QApplication

        self.out, self.app_path = out, app
        self.qt = QApplication.instance() or QApplication(sys.argv[:1])
        self.results: list[Result] = []
        self.facts: dict[str, Any] = {}

    def add(self, check: str, outcome: str, said: str, **facts: Any) -> None:
        self.results.append(Result(check, outcome, said, facts))
        print(f"{outcome:7} {check}: {said}", flush=True)

    def pump(self, until: Callable[[], bool], seconds: float) -> bool:
        """Qt's (and so macOS's) events handled until `until` or `seconds`."""
        give_up = time.monotonic() + seconds
        while time.monotonic() < give_up:
            self.qt.processEvents()
            if until():
                return True
            time.sleep(0.02)
        self.qt.processEvents()
        return until()

    def in_thread(self, work: Callable[[], Any], seconds: float) -> Any:
        """`work` on a thread of its own while the main thread runs the
        event loop (as the speaker's thread runs beside the app's)."""
        got: list[Any] = []
        problem: list[BaseException] = []

        def go() -> None:
            try:
                got.append(work())
            except BaseException as e:  # noqa: BLE001 - handed back
                problem.append(e)

        worker = threading.Thread(target=go, daemon=True)
        worker.start()
        self.pump(lambda: not worker.is_alive(), seconds)
        if problem:
            raise problem[0]
        if not got:
            raise TimeoutError(f"not done in {seconds} s")
        return got[0]

    # -- hotkeys
    def hotkeys_pressed(self) -> None:
        from polyglotic_desktop.platform.macos.hotkeys import MacHotkeys

        pressed: list[str] = []
        keys = MacHotkeys({k: partial(pressed.append, k) for k in KEYS})
        taken = keys.start()
        sent: dict[str, Any] = {}
        try:
            self.pump(lambda: False, 0.5)
            for key in KEYS:
                sent[key] = keystroke(key)
                self.pump(partial(pressed.__contains__, key), PRESS_WAIT_SEC)
        finally:
            keys.stop()
        facts = {"taken": taken, "pressed": pressed, "osascript": sent}
        if taken:
            self.add("hotkeys_pressed", FAIL, f"taken by another app: {taken}", **facts)
        elif sorted(pressed) == sorted(KEYS):
            self.add(
                "hotkeys_pressed",
                PASS,
                "⌃⌘L, ⌃⌘P and ⌃⌘H each ran their action",
                **facts,
            )
        elif not all(s["ok"] for s in sent.values()):
            self.add(
                "hotkeys_pressed",
                UNKNOWN,
                "osascript couldn't press keys here",
                **facts,
            )
        else:
            self.add(
                "hotkeys_pressed", FAIL, f"pressed, but only {pressed} ran", **facts
            )

    def hotkeys_taken(self) -> None:
        from polyglotic_desktop.platform.macos.hotkeys import MacHotkeys

        child = (
            "from polyglotic_desktop.platform.macos.hotkeys import MacHotkeys\n"
            "import json\n"
            "keys = MacHotkeys({k: (lambda: None) for k in 'LPH'})\n"
            "print(json.dumps(keys.start()))\n"
            "keys.stop()\n"
        )
        held = MacHotkeys({k: (lambda: None) for k in KEYS})
        held.start()
        try:
            other = run([sys.executable, "-c", child], 60)
        finally:
            held.stop()
        same = MacHotkeys({k: (lambda: None) for k in KEYS})
        same_taken = same.start()  # given back: ours again
        same.stop()
        try:
            told = json.loads(other.get("out", "").splitlines()[-1])
        except (ValueError, IndexError):
            told = None
        facts = {"other_process": other, "told": told, "again": same_taken}
        if told == list(KEYS) and same_taken == []:
            self.add(
                "hotkeys_taken",
                PASS,
                "another process is told all three are taken; given back, they're free",
                **facts,
            )
        elif same_taken:
            self.add(
                "hotkeys_taken", FAIL, f"given back, still taken: {same_taken}", **facts
            )
        elif told == []:
            self.add(
                "hotkeys_taken",
                UNKNOWN,
                "macOS let another process register them too",
                **facts,
            )
        else:
            self.add("hotkeys_taken", UNKNOWN, "the other process didn't say", **facts)

    def menu_keys(self) -> None:
        from PySide6.QtGui import QKeySequence

        text = QKeySequence("Meta+Ctrl+L").toString(
            QKeySequence.SequenceFormat.NativeText
        )
        outcome = PASS if text == "⌃⌘L" else FAIL
        self.add("menu_keys", outcome, f"the menus write {text!r}", text=text)

    # -- the voice
    def voices_listed(self) -> None:
        from polyglotic_desktop.platform.macos.voices import MacVoices

        found = self.in_thread(lambda: MacVoices().found(), 30)
        languages = sorted({v.language for v in found})
        self.facts["voices"] = [
            f"{v.language} {v.name} {v.quality.name}" for v in found
        ]
        english = [v for v in found if v.language.startswith("en")]
        outcome = PASS if english else FAIL
        # each language's first voice is the one used, and its quality what
        # brings the better-voice notice (polyglotic-hq 518)
        first = {v.language: v for v in reversed(found)}
        basic = sorted(t for t, v in first.items() if v.quality.name == "BASIC")
        self.add(
            "voices_listed",
            outcome,
            f"{len(found)} voices in {len(languages)} languages; first English:"
            f" {english[0].name if english else None}; {len(basic)} languages"
            " said in a basic voice",
            languages=languages,
            basic=basic,
        )

    def voice_made(self) -> None:
        from polyglotic_desktop.platform.macos.voices import MacVoices, av_rate
        from polyglotic_desktop.platform.speaking import trimmed

        speech = MacVoices()
        paces: dict[str, Any] = {}
        made: dict[str, Any] = {}

        def make_them() -> None:
            """On one thread, as the app's speaker makes every word."""
            found = speech.found()
            english = next((v for v in found if v.language == "en-US"), None) or next(
                (v for v in found if v.language.startswith("en")), None
            )
            if english is None:
                return
            made["english"] = english
            for pace in PACES:
                started = time.perf_counter()
                clip = speech.synthesize("hello", english, pace)
                took = round((time.perf_counter() - started) * 1000)
                made.setdefault("clip", clip)
                paces[str(pace)] = {
                    "av_rate": av_rate(pace),
                    "ms_to_make": took,
                    "seconds": round(clip.seconds, 3),
                    "word_seconds": round(trimmed(clip).seconds, 3),
                    "rate": clip.rate,
                }
            chinese = next((v for v in found if v.language == "zh-CN"), None)
            if chinese is not None:
                said = speech.synthesize("你好", chinese, 1.0)
                paces["zh-CN"] = {
                    "voice": chinese.name,
                    "seconds": round(said.seconds, 3),
                }

        self.in_thread(make_them, 60)
        english = made.get("english")
        if english is None:
            self.add("voice_made", UNKNOWN, "no English voice to make a word with")
            return
        clip = made.get("clip")
        assert clip is not None
        loud = clip_peak(clip.pcm)
        own, slower = paces["1.0"]["word_seconds"], paces["0.7"]["word_seconds"]
        facts = {"voice": english.name, "paces": paces, "peak": loud,
                 "slower_takes": round(slower / own, 2) if own else None,
                 "formats": sorted(speech.formats)}  # fmt: skip
        if clip.seconds > 0.2 and loud > 1000:
            self.add(
                "voice_made",
                PASS,
                f"'hello' made: {clip.seconds:.2f} s at {clip.rate} Hz",
                **facts,
            )
        else:
            self.add(
                "voice_made",
                FAIL,
                f"'hello' made silent or short: {clip.seconds:.2f} s, peak {loud}",
                **facts,
            )

    def voice_moved(self) -> None:
        from polyglotic_desktop.platform.macos.voices import MacVoices
        from polyglotic_desktop.ports.speaker import Voice

        speech = MacVoices()
        made: dict[str, Any] = {}

        def make_them() -> None:
            """As GitHub's Mac did to a running process (polyglotic-hq 452):
            the voice the card holds has an id macOS no longer knows."""
            found = speech.found()
            english = next((v for v in found if v.language == "en-US"), None)
            if english is None:
                return
            made["voice"] = english.name
            moved = Voice(f"{english.id}.moved", english.name, english.language)
            made["moved"] = round(speech.synthesize("hello", moved, 1.0).seconds, 3)
            gone = Voice("polyglotic.gone", "Nobody", english.language)
            made["gone"] = round(speech.synthesize("hello", gone, 1.0).seconds, 3)

        self.in_thread(make_them, 60)
        if "voice" not in made:
            self.add("voice_moved", UNKNOWN, "no en-US voice to move")
        elif made["moved"] > 0.2 and made["gone"] > 0.2:
            said = (
                f"'hello' made under an unknown id: {made['moved']} s, {made['gone']} s"
            )
            self.add("voice_moved", PASS, said, **made)
        else:
            self.add("voice_moved", FAIL, f"a word too short: {made}", **made)

    def voice_heard(self, blackhole_uid: str | None) -> None:
        from polyglotic_desktop.platform.macos import capture
        from polyglotic_desktop.platform.macos.voices import AudioPlayer, MacVoices
        from polyglotic_desktop.platform.speaking import SpeakerThread

        if blackhole_uid is None:
            self.add("voice_heard", UNKNOWN, "no BlackHole: nothing to hear it on")
            return
        speaker = SpeakerThread(MacVoices(), AudioPlayer)
        speaker.look_for_voices()
        self.pump(lambda: bool(speaker.voices()), 30)
        found = speaker.voices()
        english = next((v for v in found if v.language.startswith("en")), None)
        if english is None:
            speaker.close()
            self.add("voice_heard", UNKNOWN, "no English voice listed by the speaker")
            return
        heard: list[bytes] = []
        sounding: list[tuple[float, float]] = []
        ended: list[bool] = []
        mic = capture.MicCapture(blackhole_uid)
        mic.start(lambda _start, samples: heard.append(samples))
        speaking = "polyglotic_desktop.platform.speaking"
        with warnings_of(speaking) as why:
            try:
                self.pump(lambda: False, 1.5)
                speaker.say(
                    "Polyglotic",
                    english,
                    1.0,
                    lambda at, seconds: sounding.append((at, seconds)),
                    ended.append,
                )
                self.pump(lambda: bool(ended), 15)
                self.pump(lambda: False, 1.0)
            finally:
                mic.stop()
                speaker.close()
        loud = peak(heard)
        facts = {"voice": english.name, "sounding": sounding, "ended": ended,
                 "peak_heard": loud, "mic_error": mic.error,
                 "speaker_warned": why}  # fmt: skip
        if ended == [True] and sounding and loud > 0.01:
            self.add(
                "voice_heard",
                PASS,
                f"said on BlackHole and heard (peak {loud})",
                **facts,
            )
        elif mic.error:
            self.add(
                "voice_heard", UNKNOWN, f"the mic couldn't listen: {mic.error}", **facts
            )
        else:
            self.add(
                "voice_heard",
                FAIL,
                f"ended {ended}, sounding {bool(sounding)}, peak {loud}"
                + (f"; the speaker: {'; '.join(why)}" if why else ""),
                **facts,
            )

    # -- sound out (polyglotic-hq 523): what the learner hears, measured
    def _heard_saying(
        self,
        speaker: Any,
        voice: Any,
        text: str,
        blackhole_uid: str,
    ) -> tuple[Any, list[bool], str | None, list[str]]:
        """`text` said by `speaker` in `voice` while the mic on BlackHole
        listens: what was heard (16 kHz float), how it ended, the mic's
        error and the speaker's warnings."""
        import numpy as np

        from polyglotic_desktop.platform.macos import capture

        heard: list[bytes] = []
        ended: list[bool] = []
        mic = capture.MicCapture(blackhole_uid)
        mic.start(lambda _start, samples: heard.append(samples))
        with warnings_of("polyglotic_desktop.platform.speaking") as why:
            try:
                self.pump(lambda: False, 1.5)
                speaker.say(text, voice, 1.0, lambda _at, _s: None, ended.append)
                self.pump(lambda: bool(ended), 20)
                self.pump(lambda: False, 1.0)
            finally:
                mic.stop()
        return np.frombuffer(b"".join(heard), dtype="<f4"), ended, mic.error, why

    def said_recorded(self, blackhole_uid: str | None) -> None:
        """A recorded word as a learner hears it: a stand-in recording (a
        tone of `TONE_HZ` for `TONE_SEC`, Ogg Opus at 24 kHz as the packs'
        words are) through the card's whole path - `RecordedVoices`, its
        decoder, `SpeakerThread`, `AudioPlayer` - out on BlackHole and heard
        back. A wrong rate anywhere moves both its length and its pitch."""
        from polyglotic_desktop.platform.macos.voices import AudioPlayer, MacVoices
        from polyglotic_desktop.platform.recorded_voices import (
            RecordedVoices,
            Recordings,
        )
        from polyglotic_desktop.platform.speaking import SpeakerThread
        from polyglotic_desktop.ports.speaker import RECORDED

        if blackhole_uid is None:
            self.add("said_recorded", UNKNOWN, "no BlackHole: nothing to hear it on")
            return
        recordings = Recordings()
        recordings.use(
            "zh", "zh-CN", "Recorded (a stand-in tone)", _OneClip(tone_ogg())
        )
        speaker = SpeakerThread(RecordedVoices(MacVoices(), recordings), AudioPlayer)
        try:
            speaker.look_for_voices()
            self.pump(lambda: bool(speaker.voices()), 30)
            voice = next(
                (v for v in speaker.voices() if v.id.startswith(RECORDED)), None
            )
            if voice is None:
                self.add("said_recorded", FAIL, "the recorded voice wasn't listed")
                return
            heard, ended, error, why = self._heard_saying(
                speaker, voice, "你好", blackhole_uid
            )
        finally:
            speaker.close()
        if error:
            self.add("said_recorded", UNKNOWN, f"the mic couldn't listen: {error}")
            return
        found = listened(heard, HEARD_RATE)
        problems = sound_problems(found, TONE_SEC, TONE_HZ)
        facts = {"heard": found, "ended": ended, "speaker_warned": why,
                 "made_sec": TONE_SEC, "made_hz": TONE_HZ}  # fmt: skip
        if ended != [True]:
            problems.append(f"the speaker ended {ended}")
        if problems:
            self.add("said_recorded", FAIL, "; ".join(problems), **facts)
        else:
            self.add("said_recorded", PASS, f"heard {found['voiced_sec']} s at"
                     f" {found['pitch_hz']} Hz, peak {found['peak']},"
                     f" {found['level_dbfs']} dBFS", **facts)  # fmt: skip

    def said_by_macos(self, blackhole_uid: str | None) -> None:
        """ "Say it" in macOS's own voices, as a learner hears it: an English
        sentence and a Chinese phrase, each made into sound first (to know
        its length), then said through `SpeakerThread` on BlackHole and
        heard back - not silent, not clipped, loud enough, and as long as
        it was made (a wrong rate would stretch or squash it)."""
        from polyglotic_desktop.platform.macos.voices import AudioPlayer, MacVoices
        from polyglotic_desktop.platform.speaking import SpeakerThread, trimmed

        if blackhole_uid is None:
            self.add("said_by_macos", UNKNOWN, "no BlackHole: nothing to hear it on")
            return
        voices = MacVoices()
        speaker = SpeakerThread(voices, AudioPlayer)
        results: dict[str, Any] = {}
        problems: list[str] = []
        try:
            speaker.look_for_voices()
            self.pump(lambda: bool(speaker.voices()), 30)
            for tag, text in SAID:
                voice = next(
                    (v for v in speaker.voices() if v.language.startswith(tag)), None
                )
                if voice is None:
                    results[tag] = "no voice"
                    continue
                made = self.in_thread(
                    partial(_made_trimmed, voices, text, voice, trimmed), 60
                )
                made_sec = voiced_seconds_of_clip(made)
                heard, ended, error, why = self._heard_saying(
                    speaker, voice, text, blackhole_uid
                )
                if error:
                    results[tag] = f"the mic couldn't listen: {error}"
                    continue
                found = listened(heard, HEARD_RATE)
                wrong = sound_problems(found, made_sec, None)
                if ended != [True]:
                    wrong.append(f"the speaker ended {ended}")
                results[tag] = {"voice": voice.name, "made_sec": made_sec,
                                "heard": found, "warned": why, "problems": wrong}  # fmt: skip
                problems += [f"{tag}: {p}" for p in wrong]
        finally:
            speaker.close()
        said = [t for t, r in results.items() if isinstance(r, dict)]
        if problems:
            self.add("said_by_macos", FAIL, "; ".join(problems), results=results)
        elif not said:
            self.add(
                "said_by_macos", UNKNOWN, f"nothing said: {results}", results=results
            )
        else:
            self.add("said_by_macos", PASS, "heard as made: " + ", ".join(
                f"{t} {results[t]['heard']['voiced_sec']} s of"
                f" {results[t]['made_sec']} s" for t in said), results=results)  # fmt: skip

    # -- the menu bar
    def menu_bar(self) -> None:
        from PySide6.QtWidgets import QSystemTrayIcon

        from polyglotic_desktop.platform.macos import system
        from polyglotic_desktop.ui import icons

        available = QSystemTrayIcon.isSystemTrayAvailable()
        icon = icons.menu_bar_icon(icons.TrayState.LISTENING)
        tray = QSystemTrayIcon(icon)
        tray.show()
        self.pump(lambda: tray.geometry().isValid(), 3)
        geometry = tray.geometry()
        picture = self.out / "menu-bar.png"
        drawn_as_macos(picture)
        modes: dict[str, Any] = {"before": system.light_menu_bar()}
        for dark in (True, False):
            said = run(
                [
                    "osascript",
                    "-e",
                    (
                        'tell application "System Events" to tell appearance preferences'
                        f" to set dark mode to {'true' if dark else 'false'}"
                    ),
                ],
                30,
            )
            time.sleep(1)
            modes["dark" if dark else "light"] = {
                "light_menu_bar": system.light_menu_bar(),
                "osascript": said["ok"] or said["said"],
                # macOS's own answer, from another process
                "defaults": run(
                    ["defaults", "read", "-g", "AppleInterfaceStyle"], 20
                ).get("out", ""),
            }
        tray.hide()
        follows = (
            modes["dark"]["light_menu_bar"] is False
            and modes["light"]["light_menu_bar"] is True
        )
        facts = {"available": available, "is_mask": icon.isMask(),
                 "geometry": [geometry.x(), geometry.y(), geometry.width(), geometry.height()],
                 "modes": modes, "picture": picture.name}  # fmt: skip
        if not icon.isMask():
            self.add("menu_bar", FAIL, "the icon isn't a template", **facts)
        elif not available:
            self.add(
                "menu_bar", UNKNOWN, "Qt says this Mac has no menu bar for it", **facts
            )
        elif follows:
            self.add(
                "menu_bar",
                PASS,
                "a template in the menu bar; light and dark read as macOS switches",
                **facts,
            )
        elif modes["dark"]["defaults"] != "Dark":
            self.add(
                "menu_bar",
                UNKNOWN,
                "a template in the menu bar; dark mode couldn't be switched here",
                **facts,
            )
        else:
            self.add(
                "menu_bar",
                UNKNOWN,  # the icon is a template either way: the menu's colours
                "a template in the menu bar; macOS went dark but light_menu_bar"
                " didn't follow (it styles the menu, not the icon)",
                **facts,
            )

    # -- the login item
    def login_item(self) -> None:
        if self.app_path is None:
            self.add(
                "login_item",
                UNKNOWN,
                "no packed app (--app): only it can be a login item",
            )
            return
        report = self.out / "packed-parity.json"
        program = self.app_path / "Contents" / "MacOS" / "Polyglotic"
        done = run([str(program), "--check-parity", str(report)], 180)
        try:
            found = json.loads(report.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.add(
                "login_item",
                FAIL,
                f"the packed app wrote no report: {done.get('said')}",
                run=done,
            )
            return
        states = (
            found.get("status_before"),
            found.get("status_registered"),
            found.get("status_after"),
        )
        if found.get("ok") and found.get("status_registered") == 1:
            self.add(
                "login_item", PASS, f"added and taken off (states {states})", **found
            )
        elif found.get("ok"):
            self.add(
                "login_item",
                UNKNOWN,
                f"added and taken off, but macOS said {states} (2: waiting for approval)",
                **found,
            )
        else:
            self.add("login_item", FAIL, f"macOS: {found}", **found)


def drawn_as_macos(path: Path) -> None:
    """The template icon's three states drawn as macOS draws a template: in
    the menu bar's text colour, on a light and a dark menu bar - made from
    the icon here, never captured from the screen."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor, QImage, QPainter

    from polyglotic_desktop.ui import icons

    size, gap = 36, 12
    states = list(icons.TrayState)
    width = gap + len(states) * (size + gap)
    image = QImage(width, 2 * (size + 2 * gap), QImage.Format.Format_ARGB32)
    painter = QPainter(image)
    for row, (bar, ink) in enumerate((("#ececec", "#000000"), ("#2a2a2a", "#ffffff"))):
        top = row * (size + 2 * gap)
        painter.fillRect(0, top, width, size + 2 * gap, QColor(bar))
        for i, state in enumerate(states):
            glyph = icons.menu_bar_icon(state).pixmap(size).toImage()
            tinted = QImage(glyph.size(), QImage.Format.Format_ARGB32_Premultiplied)
            tinted.fill(Qt.GlobalColor.transparent)
            paint = QPainter(tinted)
            paint.drawImage(0, 0, glyph)
            paint.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
            paint.fillRect(tinted.rect(), QColor(ink))
            paint.end()
            painter.drawImage(gap + i * (size + gap), top + gap, tinted)
    painter.end()
    image.save(str(path))


def report(results: list[Result], facts: dict[str, Any]) -> dict[str, Any]:
    summary = {r.check: r.outcome for r in results}
    return {"summary": summary, "checks": [asdict(r) for r in results], "facts": facts}


ISOLATED = (
    "voices_listed",
    "voice_made",
    "voice_moved",
    "voice_heard",
    "said_recorded",
    "said_by_macos",
)
"""AVFoundation's checks, each in a process of its own with faulthandler:
a crash there (2026-11-17's first run: exit 139 making a word) names its
line and leaves the other checks to run."""


def isolated(out: Path, name: str, blackhole: str | None) -> list[Result]:
    """`name` run in a child process; its results, or a fail saying how the
    child ended and where it was (faulthandler's stacks)."""
    command = [sys.executable, "-X", "faulthandler", "-m", "tools.macos_parity_checks"]
    command += [str(out), "--only", name]
    if blackhole is not None:
        command += ["--blackhole", blackhole]
    try:
        done = subprocess.run(
            command, capture_output=True, text=True, timeout=240, check=False
        )
    except subprocess.TimeoutExpired:
        return [Result(name, FAIL, "the child process didn't end in 240 s")]
    print(done.stdout, end="", flush=True)
    part = out / f"{name}.json"
    try:
        return [Result(**r) for r in json.loads(part.read_text(encoding="utf-8"))]
    except (OSError, ValueError, TypeError):
        said = f"the child process ended with {done.returncode} and wrote nothing"
        return [Result(name, FAIL, said, {"stderr": done.stderr[-4000:]})]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m tools.macos_parity_checks")
    parser.add_argument(
        "out", type=Path, help="a folder for parity.json and the picture"
    )
    parser.add_argument("--app", type=Path)
    parser.add_argument("--dry-run", action="store_true", help="print the plan")
    parser.add_argument("--only", help=argparse.SUPPRESS)  # one check, in a child
    parser.add_argument("--blackhole", help=argparse.SUPPRESS)  # its UID, for --only
    args = parser.parse_args(argv)
    if args.dry_run:
        print("\n".join(plan(args.app)))
        return 0
    if sys.platform != "darwin":
        print("macOS only: GitHub's macOS machine (the macOS job's parity part)")
        return 2
    args.out.mkdir(parents=True, exist_ok=True)
    checks = Checks(args.out, args.app)
    blackhole: str | None = args.blackhole
    if args.only is None:
        try:
            from tools.macos_capture_checks import Run

            bench = Run(args.out / "blackhole.json", None, 0)
            bench.blackhole()
            blackhole = bench.blackhole_uid
            checks.facts["blackhole"] = [asdict(r) for r in bench.results]
        except Exception as e:  # noqa: BLE001 - the voice is then unknown, said why
            checks.facts["blackhole"] = f"{type(e).__name__}: {e}"
    steps: list[tuple[str, Callable[[], None]]] = [
        ("hotkeys_pressed", checks.hotkeys_pressed),
        ("hotkeys_taken", checks.hotkeys_taken),
        ("menu_keys", checks.menu_keys),
        ("voices_listed", checks.voices_listed),
        ("voice_made", checks.voice_made),
        ("voice_moved", checks.voice_moved),
        ("voice_heard", lambda: checks.voice_heard(blackhole)),
        ("said_recorded", lambda: checks.said_recorded(blackhole)),
        ("said_by_macos", lambda: checks.said_by_macos(blackhole)),
        ("menu_bar", checks.menu_bar),
        ("login_item", checks.login_item),
    ]
    for name, step in steps:
        if args.only is not None and name != args.only:
            continue
        if args.only is None and name in ISOLATED:
            checks.results += isolated(args.out, name, blackhole)
            continue
        try:
            step()
        except Exception as e:  # noqa: BLE001 - one check's crash isn't the run's
            checks.add(name, FAIL, f"crashed: {type(e).__name__}: {e}",
                       where=traceback.format_exc(limit=4))  # fmt: skip
    if args.only is not None:
        part = [asdict(r) for r in checks.results]
        for r in part:
            r["facts"] |= {f"run_{k}": v for k, v in checks.facts.items()}
        (args.out / f"{args.only}.json").write_text(json.dumps(part), encoding="utf-8")
        return 0
    found = report(checks.results, checks.facts)
    (args.out / "parity.json").write_text(json.dumps(found, indent=1), encoding="utf-8")
    print(json.dumps(found["summary"]))
    return 1 if any(r.outcome == FAIL for r in checks.results) else 0


if __name__ == "__main__":
    os.environ.setdefault("PYTHONUNBUFFERED", "1")
    sys.exit(main())
