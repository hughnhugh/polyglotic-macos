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
- voice_heard: the card's whole path - `SpeakerThread` over `MacVoices`
  and `AudioPlayer` - says a word on macOS's default output, BlackHole,
  and the mic on BlackHole hears it; `sounding` and `ended` are told.
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
import os
import subprocess
import sys
import threading
import time
import traceback
from collections.abc import Callable
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
            "voice_heard: BlackHole the default output; SpeakerThread(MacVoices,"
            " AudioPlayer).say('Polyglotic') while MicCapture(BlackHole) listens"
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


def peak(samples: list[bytes]) -> float:
    import numpy as np

    audio = np.frombuffer(b"".join(samples), dtype="<f4")
    return round(float(np.max(np.abs(audio))), 4) if len(audio) else 0.0


def clip_peak(pcm: bytes) -> int:
    from array import array

    samples = array("h")
    samples.frombytes(pcm)
    return max((abs(s) for s in samples), default=0)


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
        self.facts["voices"] = [f"{v.language} {v.name}" for v in found]
        english = [v for v in found if v.language.startswith("en")]
        outcome = PASS if english else FAIL
        self.add(
            "voices_listed",
            outcome,
            f"{len(found)} voices in {len(languages)} languages; first English:"
            f" {english[0].name if english else None}",
            languages=languages,
        )

    def voice_made(self) -> None:
        from polyglotic_desktop.platform.macos.voices import MacVoices, av_rate
        from polyglotic_desktop.platform.speaking import trimmed

        speech = MacVoices()
        found = self.in_thread(speech.found, 30)
        english = next((v for v in found if v.language == "en-US"), None) or next(
            (v for v in found if v.language.startswith("en")), None
        )
        if english is None:
            self.add("voice_made", UNKNOWN, "no English voice to make a word with")
            return
        paces: dict[str, Any] = {}
        clip = None
        for pace in PACES:
            started = time.perf_counter()
            made = self.in_thread(
                partial(speech.synthesize, "hello", english, pace), 15
            )
            took = round((time.perf_counter() - started) * 1000)
            clip = clip or made
            paces[str(pace)] = {
                "av_rate": av_rate(pace),
                "ms_to_make": took,
                "seconds": round(made.seconds, 3),
                "word_seconds": round(trimmed(made).seconds, 3),
                "rate": made.rate,
            }
        chinese = next((v for v in found if v.language == "zh-CN"), None)
        if chinese is not None:
            made = self.in_thread(lambda: speech.synthesize("你好", chinese, 1.0), 15)
            paces["zh-CN"] = {"voice": chinese.name, "seconds": round(made.seconds, 3)}
        assert clip is not None
        loud = clip_peak(clip.pcm)
        own, slower = paces["1.0"]["word_seconds"], paces["0.7"]["word_seconds"]
        facts = {"voice": english.name, "paces": paces, "peak": loud,
                 "slower_takes": round(slower / own, 2) if own else None}  # fmt: skip
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
                 "peak_heard": loud, "mic_error": mic.error}  # fmt: skip
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
                f"ended {ended}, sounding {bool(sounding)}, peak {loud}",
                **facts,
            )

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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m tools.macos_parity_checks")
    parser.add_argument(
        "out", type=Path, help="a folder for parity.json and the picture"
    )
    parser.add_argument("--app", type=Path)
    parser.add_argument("--dry-run", action="store_true", help="print the plan")
    args = parser.parse_args(argv)
    if args.dry_run:
        print("\n".join(plan(args.app)))
        return 0
    if sys.platform != "darwin":
        print("macOS only: GitHub's macOS machine (the macOS job's parity part)")
        return 2
    args.out.mkdir(parents=True, exist_ok=True)
    checks = Checks(args.out, args.app)
    blackhole: str | None = None
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
        ("voice_heard", lambda: checks.voice_heard(blackhole)),
        ("menu_bar", checks.menu_bar),
        ("login_item", checks.login_item),
    ]
    for name, step in steps:
        try:
            step()
        except Exception as e:  # noqa: BLE001 - one check's crash isn't the run's
            checks.add(name, FAIL, f"crashed: {type(e).__name__}: {e}",
                       where=traceback.format_exc(limit=4))  # fmt: skip
    found = report(checks.results, checks.facts)
    (args.out / "parity.json").write_text(json.dumps(found, indent=1), encoding="utf-8")
    print(json.dumps(found["summary"]))
    return 1 if any(r.outcome == FAIL for r in checks.results) else 0


if __name__ == "__main__":
    os.environ.setdefault("PYTHONUNBUFFERED", "1")
    sys.exit(main())
