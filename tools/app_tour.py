r"""The app's tour on this OS's real windows (polyglotic-hq 410): the app
from source, signed in to a stand-in server on this machine
(`tests/fake_server.py`), captioning a recording fed straight into it
(`platform/replay.py`: the app's own FLEURS sample, CC BY 4.0) - no sound
device, no microphone, no account, nothing leaves the machine.

    uv run --no-sync python -m tools.app_tour OUT [--dictionaries DIR] [--limit S]

OUT gets `checks.json` (what was checked, pass or fail, and the facts: the
OS, Qt's platform plugin, the screens) and a picture of each window by its
own `grab()` - never a picture of the screen: `home.png`,
`caption-window.png`, `card.png` (the lookup card on a word of the
caption), `words.png`, `settings.png`, `transcript.png`. Exits 0 when every
check passed.

What's swapped, as polyglotic-hq 346's loop does: the capture (the
recording for the one app listed, silence for the rest), the apps playing,
the device token (in memory, for the stand-in server), hotkeys, the
dictation key, voices and sound out, staying on top and the copy lock
(nothing of the OS's session is taken), links opened. Everything else is
the OS's own adapters (`main.os_adapters`), so on macOS this is the first
look at `platform/macos` running.

Run by `.github/workflows/macos.yml` on GitHub's macOS machine, which is
signed in to a desktop session.

`--unlocking` (Linux, polyglotic-hq 570; `.github/workflows/linux.yml`):
once captions show, the OS's own hotkeys (not swapped) and real input
through the session's compositor (`tools/linux_input.py`): Ctrl+Alt+Shift+L
pressed over the full-screen window - it locks where the app says its
hotkeys work and not where it says they don't; `--lock`, `--pause` and
`--hide` from a second process, each on and back; on a Wayland desktop the
locked window's corner, the mouse arriving on it offering Unlock and a
click there unlocking; the first lock's notice; and the settings popover
closed by Esc and by a click elsewhere (`unlocking.json`'s facts beside the
checks, the desktop's pictures of each).

`--real-capture` (Linux, polyglotic-hq 550; `.github/workflows/linux.yml`
on GitHub's Ubuntu runner): nothing is fed in. The recording is *played*
through the sound server to its default output, and a second one into the
input the session made the default mic, and the app captions everything
the PC plays and the mic with the OS's own captures; the device token is
kept in the OS's own keyring under an entry of the tour's (`--credentials`),
deleted at the end. With `--one-app` (polyglotic-hq 561) one app is
captioned alone: the recording played by `pw-play` (listed as `pw-cat`, its
executable) - the app captioned,
chosen as a learner would on Home - while `paplay`, a second app, plays a
1 kHz tone; the tour checks the app list names both, the stand-in server
hears the app's source, and the audio captioned has the recording and not
the tone (`one_app.json`). On Linux the card's Say it is pressed with the
OS's own speaker (polyglotic-hq 591): speech-dispatcher's stream heard on
the sound server, its level measured from that stream alone, and the card
pictured after it (`card-said.png`: 518's notice worded for Linux, or why
there's no voice where speech-dispatcher isn't installed). Runs on Windows
and Linux too: offscreen
with `QT_QPA_PLATFORM=offscreen` (how it was tried before its first macOS
run), or on a private desktop on Windows (`tools/private_desktop.py`).
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import platform
import sys
import threading
import time
import traceback
from collections.abc import Callable, Generator
from functools import partial
from pathlib import Path
from typing import Any

import numpy as np
from PySide6.QtCore import QPoint, QPointF, Qt, QTimer
from PySide6.QtGui import QGuiApplication, QPixmap, QRegion
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QAbstractButton, QApplication, QScrollArea, QWidget
from tests import fake_server
from tests.fakes import MemoryCredentialStore

from polyglotic_desktop import main as app
from polyglotic_desktop.platform.replay import ReplayCapture, join, read_clip
from polyglotic_desktop.platform.sample import sample_file
from polyglotic_desktop.ports.capture import PlayingApp, SourceCategory
from polyglotic_desktop.ports.credentials import DeviceCredentials

PLAYER = "Stand-in player"
"""The one app listed as playing: the recording is its sound."""
PLAYER_ID = 4346
CAPTION = "今天天气很好，我们一起去公园散步吧。"
TRANSLATION = "The weather is nice today; let's go for a walk in the park."
"""What the stand-in server answers each speech with (a stand-in's words,
not the recording's)."""
TOKEN = DeviceCredentials("install-410-tour", "pgd_" + "t" * 43)
"""The stand-in server takes any token of the protocol's shape."""
SYSTEM_KEY = "system"
ONE_PLAYER, ONE_APP = "pw-play", "pw-cat"
"""`--one-app`: the app captioned alone - PipeWire's own player, whose
executable and process are only on its client (547). Listed by its
executable's name: `pw-play` is a link to `pw-cat` (561's first run)."""
OTHER_PLAYER, OTHER_APP = "paplay", "pacat"
"""`--one-app`: the app playing something else meanwhile (a tone);
`paplay` is a link to `pacat`."""
TONE_HZ = 1000.0
ONE_APP_SEC = 240.0
"""How long each `--one-app` player plays: the whole tour."""
"""The caption window of everything the PC plays (`--real-capture`)."""
REAL: dict[str, Any] = {"on": False, "one_app": False, "prefix": "", "unlocking": False}
"""`--real-capture`: the OS's own captures and keyring, and the players."""
PAGES = ("words", "settings")
MORE_PAGES = ("learning", "account", "help")
"""Pictured too, never failing the tour: the rest of the sidebar."""

RESULTS: dict[str, Any] = {"checks": [], "facts": {}, "pictures": []}
STATE: dict[str, Any] = {}
OUT = Path()


# -- the stand-ins -----------------------------------------------------------------


def caption_for(header: Any) -> dict[str, Any]:
    """The stand-in server's caption for a speech frame: Mandarin, with
    English (`tests.fake_server.caption_for`'s shape)."""
    return {
        "type": "caption_update",
        "caption_id": header.caption_id,
        "source_id": header.source.id,
        "kind": header.kind,
        "language": "zh",
        "languages_heard": ["zh"],
        "clauses": [{"original": CAPTION, "translations": {"en": TRANSLATION}}],
        "replaces": list(header.replaces),
        "processing_ms": 5,
    }


def silence() -> ReplayCapture:
    return ReplayCapture(np.zeros(16_000 * 3600, dtype=np.float32))


class Nothing:
    """Hotkeys, the foreground watch, start at sign-in, staying on top, the
    copy lock and sound out: nothing registered with the OS."""

    def __init__(self, *_a: object, **_k: object) -> None:
        pass

    def start(self, *_a: object) -> Any:
        return []

    def stop(self) -> None:
        pass

    def game_in_front(self) -> bool:
        return False

    def put_on_top(self, _windows: object) -> None:
        pass

    def enabled(self) -> bool:
        return False

    def set_enabled(self, _on: bool) -> None:
        pass

    def take(self) -> bool:
        return True

    def release(self) -> None:
        pass

    def play(self, _audio: object, _rate: int) -> bool:
        return False


class HoldKey(Nothing):
    def start(self, *_a: object) -> bool:
        return True


class NoVoices:
    def found(self) -> tuple[()]:
        return ()

    def synthesize(self, *_a: object) -> Any:
        raise RuntimeError("no voices on the tour")


class SilentOutput:
    def start(self, _clip: object) -> bool:
        return True

    def playing(self) -> bool:
        return False

    def stop(self) -> None:
        pass


class PlayerListed:
    def playing_apps(self) -> list[PlayingApp]:
        return [PlayingApp(PLAYER_ID, PLAYER, True, SourceCategory.VIDEO)]


class NoLinks:
    @staticmethod
    def openUrl(url: Any) -> bool:
        STATE.setdefault("links_opened", []).append(url.toString())
        return True


def window_key() -> str:
    """The caption window the tour looks at: the player's, or everything the
    PC plays' with `--real-capture`."""
    if REAL["one_app"]:
        return ONE_APP
    return SYSTEM_KEY if REAL["on"] else PLAYER


def noted(make: Callable[..., Any]) -> Callable[..., Any]:
    """The OS's own capture, its start noted for the tour's waits."""

    def made(*args: Any, **kwargs: Any) -> Any:
        STATE.setdefault("capture_started", time.monotonic())
        return make(*args, **kwargs)

    return made


class Kept:
    """`--one-app`: the OS's own capture of the app, what it delivers kept
    too (the samples, for `one_app.json`'s measures)."""

    def __init__(self, capture: Any) -> None:
        self._capture = capture
        self.samples: list[bytes] = []
        STATE["one_app_capture"] = self

    def start(self, on_audio: Callable[[float, bytes], None]) -> None:
        STATE.setdefault("capture_started", time.monotonic())

        def kept(at: float, data: bytes) -> None:
            self.samples.append(data)
            on_audio(at, data)

        self._capture.start(kept)

    def stop(self) -> None:
        self._capture.stop()

    @property
    def capturing(self) -> str | None:
        return self._capture.capturing

    @property
    def error(self) -> str | None:
        return self._capture.error


def adapters(real: Callable[[str], Any], audio: np.ndarray) -> Callable[..., Any]:
    def os_adapters(system: str = sys.platform) -> Any:
        found = real(system)
        names = {f.name for f in dataclasses.fields(found)}

        def app_capture(_pid: int, _name: str, trial: Any = None) -> ReplayCapture:
            if trial is not None:
                from polyglotic_desktop.ports.capture import TrialOutcome

                threading.Timer(1.0, trial.tell, args=(TrialOutcome(True),)).start()
            STATE.setdefault("capture_started", time.monotonic())
            return ReplayCapture(audio)

        def speaker(*_recordings: object) -> Any:
            from polyglotic_desktop.platform.speaking import SpeakerThread

            return SpeakerThread(NoVoices(), SilentOutput)

        swaps: dict[str, Any] = {
            "app_list": PlayerListed,
            "app_capture": app_capture,
            "everything_else_capture": lambda *_a, **_k: silence(),
            "system_capture": lambda *_a, **_k: silence(),
            "mic_capture": lambda *_a, **_k: silence(),
            "credentials": lambda _entry: MemoryCredentialStore(TOKEN),
            "hotkeys": found.hotkeys if REAL["unlocking"] else Nothing,
            "hold_key": HoldKey,
            "foreground_watch": Nothing,
            "on_top": Nothing,
            "start_at_sign_in": lambda _exe: Nothing(),
            "copy_lock": lambda _name: Nothing(),
            "keys": lambda _name: False,
            "sound_out": Nothing,
            "speaker": speaker,
            "show_error": lambda title, text: STATE.setdefault(
                "error_boxes", []
            ).append(f"{title}: {text}"),
        }
        if "app_capture_support" in names:
            from polyglotic_desktop.ports.capture import AppCaptureSupport

            swaps["app_capture_support"] = lambda: AppCaptureSupport("yes")
        if REAL["on"]:  # the OS's own captures and keyring (550)
            for kept in ("app_capture_support", "credentials", "app_list"):
                swaps.pop(kept, None)
            if sys.platform.startswith("linux"):  # the OS's own voice (591)
                swaps.pop("speaker", None)
            swaps["system_capture"] = noted(found.system_capture)
            swaps["mic_capture"] = noted(found.mic_capture)
            if REAL["one_app"]:  # the OS's own capture of one app (561)
                real_app = found.app_capture
                swaps["app_capture"] = lambda *a, **k: Kept(real_app(*a, **k))
        return dataclasses.replace(
            found, **{k: v for k, v in swaps.items() if k in names}
        )

    return os_adapters


def seed_settings(data: Path) -> None:
    """A learner of Mandarin, translated into English, with the player
    captioned: written before the app starts, as 346's loop does."""
    data.mkdir(parents=True, exist_ok=True)
    window = {"position": "bottom_centre", "spoken_language": "detect",
              "translate_into": "en", "text_size": 1.0, "translation_size": 1.0,
              "show_mic": False, "geometry": None}  # fmt: skip
    settings = {
        "learning": "zh",
        "apps": [PLAYER],
        "whole_system": False,
        "caption_windows": {"windows": {PLAYER: window}, "last": dict(window)},
    }
    if REAL["one_app"]:  # one app alone, chosen on Home below (561)
        settings |= {"apps": [], "whole_system": False, "caption_windows": {
            "windows": {ONE_APP: window}, "last": dict(window)}}  # fmt: skip
    elif REAL["on"]:  # everything the PC plays, and the mic in its window
        heard = dict(window, show_mic=True)
        settings |= {
            "apps": [],
            "whole_system": True,
            "caption_mic": True,
            "caption_windows": {"windows": {SYSTEM_KEY: heard}, "last": heard},
        }
    (data / "settings.json").write_text(json.dumps(settings, ensure_ascii=False),
                                        encoding="utf-8")  # fmt: skip


class Players:
    """`--real-capture`: each clip played again and again through the sound
    server (`paplay`, else `pw-play`) to a device - the default output, or
    a sink by name - until stopped."""

    def __init__(self) -> None:
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []

    def play(self, clip: Path, device: str | None, app: str | None = None) -> None:
        """`app`: this player only (`pw-play` or `paplay`), as an app of its
        own (561); else whichever there is."""
        import shutil
        import subprocess

        player = shutil.which(app) if app else None
        player = player or shutil.which("paplay") or shutil.which("pw-play")
        if player is None:
            check("a player for the sound server (paplay or pw-play)", False)
            return
        target = []
        if device:
            target = (
                [f"--device={device}"] if "paplay" in player else ["--target", device]
            )

        def loop() -> None:
            while not self._stop.is_set():  # until stopped: never left playing
                playing = subprocess.Popen([player, *target, str(clip)])
                while playing.poll() is None and not self._stop.wait(0.2):
                    pass
                if playing.poll() is None:
                    playing.kill()
                self._stop.wait(0.5)

        thread = threading.Thread(target=loop, name="tour player", daemon=True)
        thread.start()
        self._threads.append(thread)

    def stop(self) -> None:
        self._stop.set()


# -- results -----------------------------------------------------------------------


def check(name: str, ok: object, detail: object = "") -> bool:
    RESULTS["checks"].append(
        {"check": name, "ok": bool(ok), "detail": str(detail)[:800]}
    )
    print(f"[{'pass' if ok else 'FAIL'}] {name} {str(detail)[:200]}", flush=True)
    return bool(ok)


def picture(widget: QWidget | None, name: str, what: str) -> None:
    """The widget's own picture (`grab()`) - never the screen's."""
    shown = widget is not None and widget.isVisible()
    if check(f"{what} shows", shown) and widget is not None:
        widget.grab().save(str(OUT / f"{name}.png"))
        RESULTS["pictures"].append(
            {
                "file": f"{name}.png",
                "what": what,
                "size": [widget.width(), widget.height()],
            }
        )


def extra(widget: QWidget | None, name: str, what: str) -> None:
    """A picture for the record (the whole app shown, page by page): taken
    when it can be, noted when not, and never a failed check."""
    try:
        if widget is None:
            raise LookupError("not there")
        widget.grab().save(str(OUT / f"{name}.png"))
        RESULTS["pictures"].append(
            {
                "file": f"{name}.png",
                "what": what,
                "size": [widget.width(), widget.height()],
            }
        )
    except Exception as error:  # noqa: BLE001 - a missing picture isn't a failure
        RESULTS["facts"].setdefault("pictures_missed", []).append(f"{name}: {error}")


def whole(page: QWidget | None, name: str, what: str) -> None:
    """The page's content at its full length (its scroll area's widget),
    over the page's own colour (the viewport paints it, not the content)."""
    areas = [page] if isinstance(page, QScrollArea) else []
    if page is not None:
        areas += page.findChildren(QScrollArea)
    for area in areas:
        inner = area.widget()
        if inner is None or not area.isVisible():
            continue
        if inner.height() <= area.viewport().height():
            continue
        try:
            # the window's own picture: on a Mac a viewport grabbed alone
            # comes out in the system's light colour, not the page's
            win = area.window()
            ground = (
                win.grab()
                .toImage()
                .pixelColor(area.viewport().mapTo(win, QPoint(2, 2)))
            )
            shot = QPixmap(inner.size())
            shot.fill(ground)
            inner.render(shot, QPoint(0, 0), QRegion(), QWidget.RenderFlag.DrawChildren)
            shot.save(str(OUT / f"{name}.png"))
            RESULTS["pictures"].append(
                {
                    "file": f"{name}.png",
                    "what": what,
                    "size": [inner.width(), inner.height()],
                }
            )
        except Exception as error:  # noqa: BLE001 - a missing picture isn't a failure
            RESULTS["facts"].setdefault("pictures_missed", []).append(
                f"{name}: {error}"
            )
        return
    RESULTS["facts"].setdefault("pictures_missed", []).append(
        f"{name}: fits one screen"
    )


def facts() -> dict[str, Any]:
    screens = [
        {"size": [s.size().width(), s.size().height()], "ratio": s.devicePixelRatio()}
        for s in QGuiApplication.screens()
    ]
    return {
        "os": sys.platform,
        "macos": platform.mac_ver()[0] or None,
        "machine": platform.machine(),
        "qt_platform": QGuiApplication.platformName(),
        "screens": screens,
        "error_boxes": STATE.get("error_boxes", []),
        "links_opened": STATE.get("links_opened", []),
    }


def write_results() -> None:
    RESULTS["facts"] |= facts() if QGuiApplication.instance() else {}
    (OUT / "checks.json").write_text(
        json.dumps(RESULTS, indent=1, ensure_ascii=False, default=str), encoding="utf-8"
    )


# -- the tour, stepped in the app's own event loop ---------------------------------

Step = Generator[tuple[Callable[[], object], float, str], None, None]


class VoiceStream:
    """Linux (591): speech-dispatcher's stream on the sound server, watched on
    a thread of its own while the card says its word - when it was first
    and last seen, and its loudest 20 ms, recorded from that stream alone
    (its output's monitor, `monitor_of`), so the recording the tour plays
    beside it isn't counted."""

    def __init__(self) -> None:
        self.first: float | None = None
        self.last: float | None = None
        self.peak = -120.0
        self.error = ""
        self.seen: set[str] = set()
        """Every stream's app seen meanwhile, paused or not: what the check
        says when it fails."""
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    @staticmethod
    def _ours(stream: Any) -> bool:
        """A voice's stream: "speech-dispatcher-espeak-ng" (played by
        speech-dispatcher itself), never its dummy's, which is never paused
        and never sounds (591's probe)."""
        name = stream.app_name or ""
        return name.startswith("speech-dispatcher") and not name.endswith("-dummy")

    def _run(self) -> None:
        from polyglotic_desktop.platform.linux import pulse

        try:
            server = pulse.PulseServer("Polyglotic tour voice")
        except OSError as error:
            self.error = str(error)
            return
        recording = None
        try:
            while not self._stop.is_set():
                streams = server.streams()
                self.seen.update(f"{s.app_name}{' (paused)' if s.corked else ''}"
                                 for s in streams)  # fmt: skip
                found = next(
                    (s for s in streams if self._ours(s) and not s.corked), None
                )
                if found is not None:
                    now = time.perf_counter()
                    self.first = self.first or now
                    self.last = now
                    if recording is None:
                        monitor = next(
                            (
                                k.monitor
                                for k in server.sinks()
                                if k.index == found.sink
                            ),
                            None,
                        )
                        if monitor:
                            recording = server.record(monitor, monitor_of=found.index)
                server.run(0.02)
                for _at, data in recording.take() if recording is not None else ():
                    samples = np.frombuffer(data, dtype="<f4").astype(np.float64)
                    rms = float(np.sqrt(np.mean(samples**2))) if len(samples) else 0.0
                    if rms > 1e-9:
                        self.peak = max(self.peak, 20 * float(np.log10(rms)))
        except OSError as error:
            self.error = str(error)
        finally:
            if recording is not None:
                recording.close()
            server.close()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(5)


def say_it(card: Any) -> Step:
    """The card's Say it, pressed as a learner does (Linux, 591): with
    speech-dispatcher, its stream plays the word on the sound server; the
    card then shows 518's notice for Linux. Without it, the card says why."""
    speech = card.speech
    if not check("the card can say its word", speech is not None):
        return
    watched = VoiceStream()
    asked = time.perf_counter()
    card.do("say")
    yield pause(0.3)
    yield wait(lambda: speech.speaking is None, 15, "the word said")
    yield pause(0.5)
    watched.stop()
    voiced = speech.system_voice()
    said = {
        "system_voice": voiced,
        "stream_after_ask_ms": (
            round((watched.first - asked) * 1000) if watched.first else None
        ),
        "stream_seconds": (
            round(watched.last - watched.first, 2)
            if watched.first and watched.last
            else 0
        ),
        "peak_dbfs": round(watched.peak, 1),
        "error": watched.error,
        "streams_seen": sorted(watched.seen),
    }
    RESULTS["facts"]["say_it"] = said
    if voiced:
        check("Say it: the word played by speech-dispatcher on the sound server",
              watched.first is not None and watched.peak > -40, said)  # fmt: skip
    picture(card, "card-said", "The card after Say it")


def wait(predicate: Callable[[], object], seconds: float, what: str) -> Any:
    return (predicate, seconds, what)


def pause(seconds: float) -> Any:
    return (lambda: False, seconds, "")


def modal(name: str) -> Any:
    found = QApplication.activeModalWidget()
    return found if found is not None and type(found).__name__ == name else None


def hub() -> Any:
    return STATE["interface"].hub


def ready() -> bool:
    return (
        "interface" in STATE
        and hub().window.isVisible()
        and QApplication.activeModalWidget() is None
    )


def caption_window() -> Any:
    return (
        STATE["interface"].windows.windows.get(window_key())
        if "interface" in STATE
        else None
    )


def finished_lines() -> list[Any]:
    found = caption_window()
    return [ln for ln in found.view.lines if not ln.live] if found is not None else []


def second_start(*more: str) -> Any:
    """`polyglotic --lock` and the like (570): the app started again on
    the tour's data folder, from source, as a desktop's shortcut starts it."""
    import subprocess

    return subprocess.Popen(
        [sys.executable, "-m", "polyglotic_desktop.main", "--data", str(STATE["data"]),
         *more],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )  # fmt: skip


def ended(run: Any) -> bool:
    return run.poll() is not None


def closed(window: Any) -> bool:
    return window is None or not window.isVisible()


def unlocking() -> Step:
    """Linux's hotkeys, commands, unlock spot, first lock and popover
    (polyglotic-hq 570), through the compositor's own input."""
    from tools.linux_input import Input

    desktop = STATE["desktop"]
    windows = STATE["interface"].windows
    captions = caption_window()
    facts: dict[str, Any] = RESULTS["facts"].setdefault("unlocking", {})
    try:
        given = Input.make()
    except Exception as error:  # noqa: BLE001 - said in the results
        check("real input through the session's compositor", False, repr(error))
        return
    working = [k for k, a in desktop.hotkeys.items() if not a.shortcut().isEmpty()]
    facts["hotkeys_working"] = working
    facts["lock_keys"] = captions.unlock_keys
    lock = desktop.lock_windows
    screen = QGuiApplication.primaryScreen().geometry()
    away = (screen.left() + 60, screen.bottom() - 60)  # the full-screen window
    home = hub().window

    # 1. the lock hotkey, over the full-screen window that has the keyboard
    given.move(*away)
    given.click(*away)  # the window beneath takes the keyboard back
    yield pause(1.0)
    given.press("ctrl", "alt", "shift", "l")
    if "lock" in working:  # Lock's key, by its name (567)
        yield wait(lock.isChecked, 4, "the lock hotkey")
    else:
        yield pause(2.0)  # said not to work here: nothing should lock
    by_key = lock.isChecked()
    check("Ctrl+Alt+Shift+L locks exactly where the app says it works",
          by_key == ("lock" in working), f"locked={by_key}, working={working}")  # fmt: skip
    if by_key:
        facts["first_lock_notice"] = captions.notice.text()
        yield pause(1.0)
        picture(captions, "locked-by-hotkey", "Locked by its hotkey, the first lock")
        yield from desk("locked-by-hotkey", home_hidden=True)
        given.press("ctrl", "alt", "shift", "l")
        yield wait(lambda: not lock.isChecked(), 4, "unlocked by the hotkey")
        check("Ctrl+Alt+Shift+L unlocks again", not lock.isChecked())
    lock.setChecked(False)

    # 2. --lock, --pause and --hide from a second process, each on and back
    for command, action in (
        ("lock", lock),
        ("pause", desktop.pause),
        ("hide", desktop.hide_windows),
    ):
        for turn in ("on", "back"):
            before = action.isChecked()
            run = second_start(f"--{command}")
            yield wait(partial(ended, run), 25, f"--{command}")
            yield pause(0.8)
            said = (run.communicate()[0] or "").strip()[-300:]
            check(f"--{command} from a second process ({turn})",
                  run.returncode == 0 and action.isChecked() != before,
                  f"exit {run.returncode}, {before} -> {action.isChecked()}; {said}")  # fmt: skip
            if turn == "on" and command != "pause":
                if command == "lock":
                    facts.setdefault("first_lock_notice", captions.notice.text())
                    facts["notice_on_lock_by_command"] = captions.notice.text()
                    picture(captions, "locked-by-command", "Locked by --lock")
                yield from desk(f"{command}-by-command", home_hidden=True)
    lock.setChecked(False)
    desktop.hide_windows.setChecked(False)
    desktop.pause.setChecked(False)
    yield pause(1.0)

    # 3. a Wayland desktop: the locked window's corner offers Unlock
    facts["unlock_spot"] = bool(getattr(windows, "unlock_spot", False))
    if facts["unlock_spot"]:
        home.hide()
        lock.setChecked(True)
        yield pause(1.5)
        spot = captions.unlock_spot
        catcher = spot.catcher
        check("a locked window's corner takes the mouse",
              catcher is not None and catcher.isVisible())  # fmt: skip
        if catcher is not None:
            corner = catcher.geometry().center()
            given.move(*away)
            yield pause(0.8)
            given.move(corner.x(), corner.y())
            yield wait(lambda: spot.shown, 4, "Unlock on the corner")
            check("the mouse arriving on the corner offers Unlock over a Wayland app",
                  spot.shown)  # fmt: skip
            yield from desk("unlock-offered")
            given.move(*away)  # gone, unheard: Unlock goes by itself
            yield wait(lambda: not spot.shown, 6, "Unlock gone")
            check("Unlock goes by itself once the mouse has gone", not spot.shown)
            given.move(corner.x(), corner.y())
            yield wait(lambda: spot.shown, 4, "Unlock again")
            if spot.shown and spot.button is not None:
                at = spot.button.geometry().center()
                given.click(at.x(), at.y())
                yield wait(lambda: not lock.isChecked(), 4, "Unlock clicked")
            check("a click on Unlock unlocks", not lock.isChecked())
        lock.setChecked(False)
        home.show()
        yield pause(1.0)

    # 4. the settings popover: Esc, then a click elsewhere
    home.hide()
    yield pause(1.0)
    managed = os.environ.get("LINUX_SESSION_SCREEN") in ("gnome", "kde")
    facts["window_manager"] = managed  # a bare X server has none to move the keyboard
    for how in ("esc", "click") if managed else ("esc",):
        middle = captions.mapToGlobal(captions.rect().center())
        given.move(middle.x(), middle.y())  # its strip shows
        yield pause(1.0)
        button = captions.buttons["settings"]
        at = button.mapToGlobal(button.rect().center())
        given.click(at.x(), at.y())
        yield wait(lambda: captions.popover is not None and captions.popover.isVisible(),
                   4, "the settings popover")  # fmt: skip
        popover = captions.popover
        opened = popover is not None and popover.isVisible()
        if how == "esc" and opened:
            picture(popover, "popover-open", "The settings popover")
            yield from desk("popover-open")
        if how == "esc":
            given.press("esc")
        else:
            given.click(*away)
        yield wait(partial(closed, popover), 4, f"closed by {how}")
        check(f"the settings popover closes on {'Esc' if how == 'esc' else 'a click elsewhere'}",
              opened and popover is not None and not popover.isVisible(),
              f"opened={opened}")  # fmt: skip
    home.show()
    yield pause(1.0)
    (OUT / "unlocking.json").write_text(json.dumps(facts, indent=1), encoding="utf-8")


def a_word(window: Any) -> QPointF | None:
    """A word drawn on the caption window, found as a mouse would."""
    for y in range(6, window.height() - 4, 4):
        for x in range(6, window.width() - 4, 6):
            at = QPointF(x, y)
            marked = window._marked_at(at)
            if marked is not None and window.canvas.shown_row(marked.key, marked.row):
                return at
    return None


def desk(name: str, home_hidden: bool = False) -> Step:
    """The desktop's own picture of its screen at this moment, where the
    run has a window manager that takes one (POLYGLOTIC_DESK_PICTURES: a
    folder `tools/linux_desktop_pictures.py serve` answers, 550) - asked
    for, and waited for up to 40 s; never a failed check. `home_hidden`:
    with the main window hidden meanwhile, so what's beneath the caption
    windows - a full-screen window, focused again - is what shows."""
    folder = os.environ.get("POLYGLOTIC_DESK_PICTURES")
    if not folder:
        return
    if home_hidden:
        home = hub().window
        home.hide()
        yield pause(2.0)
        yield from desk(name)
        home.show()
        yield pause(1.0)
        return
    asked = Path(folder)
    name = f"{REAL['prefix']}{name}"  # the one-app tour's own (561)
    (asked / f"{name}.want").write_text("", encoding="utf-8")
    for _ in range(80):
        if (asked / f"{name}.png").exists() or (asked / f"{name}.failed").exists():
            break
        yield pause(0.5)
    took = (asked / f"{name}.png").exists()
    RESULTS["facts"].setdefault("desktop_pictures", []).append(
        name if took else f"{name}: not taken"
    )


def tour() -> Step:
    for _ in range(5):  # the first run's questions, answered as a learner would
        yield wait(lambda: QApplication.activeModalWidget() or ready(), 90,
                   "the first question or the main window")  # fmt: skip
        question = QApplication.activeModalWidget()
        if question is None:
            break
        name = type(question).__name__
        STATE.setdefault("asked", []).append(name)
        if name == "ConsentDialog" and getattr(question, "agree", None) is not None:
            question.agree.setChecked(True)  # type: ignore[attr-defined]
        if name in ("LanguagePicker", "ConsentDialog", "LevelPicker"):
            question.accept()  # type: ignore[attr-defined]
        else:  # the sign-in, or anything unexpected: closed, and a failed check
            check(f"no {name} on a signed-in start", False)
            question.close()
        yield pause(1.0)
    yield wait(ready, 60, "the main window")
    check("the main window showed", ready(), STATE.get("asked"))
    window = hub().window
    window.resize(1100, 760)
    window.go_to("home")
    yield pause(2.0)
    picture(window, "home", "Home")

    if REAL["one_app"]:  # the app, chosen on Home's list as a learner does
        yield wait(lambda: window.findChild(QAbstractButton, f"picker.add.{ONE_APP}"),
                   30, "the app on Home's list")  # fmt: skip
        listed = sorted(a.name for a in STATE["app_list"].playing_apps())
        RESULTS["facts"]["apps_listed"] = listed
        check(
            "Home lists both apps playing", {ONE_APP, OTHER_APP} <= set(listed), listed
        )
        picture(window, "home-apps", "Home's list of the apps playing")
        yield from desk("home-apps")
        button = window.findChild(QAbstractButton, f"picker.add.{ONE_APP}")
        if check("the app can be chosen on Home", button is not None):
            button.click()
    elif caption_window() is None and not REAL["on"]:  # Home's picker
        button = window.findChild(QAbstractButton, f"picker.add.{PLAYER}")
        if button is not None:
            button.click()
    yield wait(lambda: caption_window() is not None and caption_window().isVisible(), 30,
               "the caption window")  # fmt: skip
    yield wait(lambda: "capture_started" in STATE, 30, "the recording to start")
    yield wait(lambda: len(finished_lines()) >= 1, 90, "a finished caption")
    yield pause(2.0)
    check("captions came back from the stand-in server", finished_lines(),
          f"{len(finished_lines())} finished")  # fmt: skip
    captions = caption_window()
    picture(captions, "caption-window", "A caption window with captions")
    yield from desk("captions-and-home")
    yield from desk("captions", home_hidden=True)
    if REAL["unlocking"]:
        yield from unlocking()

    spot = a_word(captions) if captions is not None else None
    if check("a word on the caption window to look up", spot is not None) and spot:
        QTest.mouseClick(captions, Qt.MouseButton.LeftButton, pos=spot.toPoint())
        card = lambda: STATE["interface"].windows.card
        yield wait(lambda: card() is not None and card().isVisible(), 10, "the card")
        yield pause(1.5)
        picture(card(), "card", "The lookup card")
        yield from desk("card", home_hidden=True)
        if REAL["on"] and sys.platform.startswith("linux") and card() is not None:
            yield from say_it(card())
        if card() is not None:
            QTest.keyClick(card(), Qt.Key.Key_Escape)
            card().hide()
        yield pause(0.5)

    for page in PAGES:
        found = page in getattr(window, "pages", {})
        if check(
            f"the main window has {page}", found, list(getattr(window, "pages", {}))
        ):
            window.go_to(page)
            yield pause(1.5)
            picture(window, page, page.capitalize())

    for page in MORE_PAGES:
        if page in getattr(window, "pages", {}):
            window.go_to(page)
            yield pause(1.5)
            extra(window, page, page.capitalize())
            whole(window.pages[page], f"{page}-full", f"{page.capitalize()}, all of it")
    for page in ("home", "words"):
        window.go_to(page)
        yield pause(1.0)
        whole(window.pages[page], f"{page}-full", f"{page.capitalize()}, all of it")
    settings = getattr(window, "pages", {}).get("settings")
    sections = next((w for w in [settings, *(settings.findChildren(QWidget) if settings else [])]
                     if hasattr(w, "show_section")), None)  # fmt: skip
    if sections is not None:
        window.go_to("settings")
        for key in (  # Settings' sections (settings_page.SECTIONS)
            "look", "links", "readings", "timing", "speech", "dictation", "app", "lab",
        ):  # fmt: skip
            try:
                sections.show_section(key)
            except Exception as error:  # noqa: BLE001
                RESULTS["facts"].setdefault("pictures_missed", []).append(
                    f"{key}: {error}"
                )
                continue
            yield pause(1.2)
            extra(window, f"settings-{key}", f"Settings, {key}")
            whole(settings, f"settings-{key}-full", f"Settings, {key}, all of it")
    window.go_to("home")
    yield pause(0.5)

    captions = caption_window()
    if captions is not None and hasattr(captions, "toggle_settings"):
        captions.toggle_settings()
        yield pause(1.2)
        extra(getattr(captions, "popover", None), "caption-settings",
              "The caption window's settings")  # fmt: skip
        if getattr(captions, "settings_open", False):
            captions.toggle_settings()
        yield pause(0.5)

    tray = getattr(STATE.get("desktop"), "tray", None)
    if tray is not None:
        try:
            tray.icon().pixmap(88, 88).save(str(OUT / "menu-bar-icon.png"))
            RESULTS["pictures"].append(
                {
                    "file": "menu-bar-icon.png",
                    "what": "The menu-bar icon",
                    "size": [88, 88],
                }
            )
        except Exception as error:  # noqa: BLE001
            RESULTS["facts"].setdefault("pictures_missed", []).append(
                f"menu-bar-icon: {error}"
            )
        menu = tray.contextMenu()
        if menu is None:
            RESULTS["facts"].setdefault("pictures_missed", []).append(
                "menu-bar-menu: none set"
            )
        else:
            menu.adjustSize()
            extra(menu, "menu-bar-menu", "The menu-bar icon's menu")
    else:
        RESULTS["facts"].setdefault("pictures_missed", []).append(
            "menu-bar: no tray (none on this desktop)"
        )

    STATE["interface"].transcripts.show(window_key())
    transcript = lambda: next(
        (w for w in QApplication.topLevelWidgets()
         if w.isVisible() and "Transcript" in type(w).__name__), None)  # fmt: skip
    yield wait(lambda: transcript() is not None, 10, "the transcript")
    yield pause(1.0)
    picture(transcript(), "transcript", "The transcript")
    shown = transcript()
    if shown is not None and hasattr(shown, "_open_popover"):
        try:
            shown._open_popover()
        except Exception as error:  # noqa: BLE001
            RESULTS["facts"].setdefault("pictures_missed", []).append(
                f"transcript-settings: {error}"
            )
        yield pause(1.0)
        extra(shown, "transcript-settings", "The transcript with its settings open")
    check("no error box", not STATE.get("error_boxes"), STATE.get("error_boxes"))


class Driver:
    """The tour stepped on a timer inside the app's event loop (modal
    dialogs' loops too). A wait that times out is a failed check."""

    def __init__(self, limit: float) -> None:
        self.limit = limit
        self.steps = tour()
        self.pending: tuple[Callable[[], object], float, str] | None = None
        self.until = 0.0
        self.busy = False

    def start(self) -> None:
        self.began = time.monotonic()
        self.timer = QTimer()
        self.timer.timeout.connect(self.tick)
        self.timer.start(50)

    def tick(self) -> None:
        if self.busy:
            return
        self.busy = True
        try:
            self.step()
        except Exception:  # noqa: BLE001 - said in the results, then the end
            check(
                "the tour ran without an error", False, traceback.format_exc()[-1500:]
            )
            self.end()
        finally:
            self.busy = False

    def step(self) -> None:
        if time.monotonic() - self.began > self.limit:
            check("the tour finished in its time limit", False, f"{self.limit:.0f} s")
            self.end()
            return
        if self.pending is not None:
            predicate, _seconds, what = self.pending
            if not predicate():
                if time.monotonic() < self.until:
                    return
                if what:
                    check(f"waited for {what}", False, "timed out")
            self.pending = None
        try:
            self.pending = next(self.steps)
            self.until = time.monotonic() + self.pending[1]
        except StopIteration:
            self.end()

    def end(self) -> None:
        self.timer.stop()
        write_results()

        def give_up() -> None:  # the app's Quit must end it
            time.sleep(20)
            check("the app ended at Quit", False, "still running 20 s after")
            write_results()
            os._exit(3)

        threading.Thread(target=give_up, daemon=True).start()
        desktop = STATE.get("desktop")
        if desktop is not None:
            QTimer.singleShot(0, desktop.quit.trigger)
        else:
            QApplication.quit()


def tone_over_neighbours(samples: np.ndarray, hz: float) -> tuple[float, float]:
    """The tone at `hz` in `samples` (16kHz): its level in dB of full scale
    (the strongest bin within 3 Hz), and how far it stands over the bins
    around it (50 Hz either side, the 5 Hz nearest left out) - a played
    tone stands 40 dB or more over speech; speech alone, a few dB."""
    spectrum = np.abs(np.fft.rfft(samples * np.hanning(len(samples))))
    freqs = np.fft.rfftfreq(len(samples), 1 / 16_000)
    peak = float(spectrum[(freqs > hz - 3) & (freqs < hz + 3)].max())
    around = spectrum[(abs(freqs - hz) < 50) & (abs(freqs - hz) > 5)]
    level = 20 * np.log10(max(peak / (len(samples) / 4), 1e-12))
    over = 20 * np.log10(max(peak, 1e-12) / max(float(np.median(around)), 1e-12))
    return round(float(level), 1), round(float(over), 1)


def one_app_checks(heard: list[str]) -> None:
    """`--one-app` (561): the app's own source heard, and in what it
    delivered the recording but not the other app's tone."""
    apps_heard = [h for h in heard if h.startswith("app-")]
    check("the app was captioned on its own source", apps_heard, heard)
    check("nothing else was captioned", set(heard) <= set(apps_heard), heard)
    kept = STATE.get("one_app_capture")
    raw = b"".join(kept.samples) if kept is not None else b""
    samples = np.frombuffer(raw, "<f4")
    measured: dict[str, Any] = {"seconds": round(len(samples) / 16_000, 1)}
    if len(samples) >= 16_000 * 4:
        loud = samples[np.abs(samples) > 0][-16_000 * 20 :]
        measured["rms_dbfs"] = round(
            float(20 * np.log10(max(float(np.sqrt(np.mean(loud**2))), 1e-12))), 1
        )
        measured["tone_dbfs"], measured["tone_over_neighbours_db"] = (
            tone_over_neighbours(loud, TONE_HZ)
        )
    RESULTS["facts"]["one_app"] = measured
    (OUT / "one_app.json").write_text(json.dumps(measured, indent=2), encoding="utf-8")
    check("the app's recording was in what it captured",
          measured.get("rms_dbfs", -200) > -45, measured)  # fmt: skip
    check("the other app's tone wasn't",
          measured.get("tone_over_neighbours_db", 99) < 20, measured)  # fmt: skip


def main(argv: list[str] | None = None) -> int:
    global OUT
    parser = argparse.ArgumentParser(prog="python -m tools.app_tour")
    parser.add_argument("out", type=Path)
    parser.add_argument("--dictionaries", default="build/dictionaries")
    parser.add_argument("--limit", type=float, default=300.0, help="seconds")
    parser.add_argument(
        "--real-capture",
        action="store_true",
        help="Linux (550): the samples played through the sound server, the"
        " OS's own captures and keyring",
    )
    parser.add_argument("--mic-sink", help="with --real-capture: the mic's feed")
    parser.add_argument(
        "--one-app",
        action="store_true",
        help="with --real-capture (561): one app captioned alone, another"
        " playing a tone",
    )
    parser.add_argument(
        "--unlocking",
        action="store_true",
        help="Linux (570): the hotkeys, the commands, the unlock spot, the first"
        " lock and the popover, through the compositor's own input",
    )
    parser.add_argument(
        "--credentials",
        default="Polyglotic/tour-550",
        help="with --real-capture: the keyring's entry for the tour's token",
    )
    args = parser.parse_args(argv)
    REAL["on"] = args.real_capture
    REAL["one_app"] = args.real_capture and args.one_app
    REAL["unlocking"] = args.unlocking
    REAL["prefix"] = "one-app-" if REAL["one_app"] else ""
    if args.unlocking:
        REAL["prefix"] = "unlocking-"
    OUT = args.out
    OUT.mkdir(parents=True, exist_ok=True)
    data = OUT / "data"
    STATE["data"] = data
    seed_settings(data)
    sample = sample_file("zh")
    if sample is None:
        check("the app's FLEURS sample is there", False)
        write_results()
        return 1
    audio = join([read_clip(sample)], gap=1.0)
    players = Players()
    store: Any = None
    if REAL["on"]:
        import soundfile

        clip = OUT / "played-zh.wav"
        soundfile.write(str(clip), audio, 16_000)
        if REAL["one_app"]:  # the app's recording, and another app's tone
            # each as one long file: one player process for the whole tour,
            # as an app is (a player started again for each file is an app
            # closing and opening again)
            long = OUT / "played-zh-long.wav"
            times = int(np.ceil(ONE_APP_SEC * 16_000 / len(audio)))
            soundfile.write(str(long), np.tile(audio, times), 16_000)
            players.play(long, None, ONE_PLAYER)
            tone = OUT / "other-app-tone.wav"
            seconds = np.arange(int(16_000 * ONE_APP_SEC)) / 16_000
            soundfile.write(str(tone), 0.3 * np.sin(2 * np.pi * TONE_HZ * seconds),
                            16_000)  # fmt: skip
            players.play(tone, None, OTHER_PLAYER)
            STATE["app_list"] = app.os_adapters().app_list()
        else:
            players.play(clip, None)  # everything the PC plays
            mine = sample_file("en") or sample
            spoken = OUT / "spoken-en.wav"
            soundfile.write(str(spoken), join([read_clip(mine)], gap=1.0), 16_000)
            players.play(spoken, args.mic_sink)  # the learner's own speech
        store = app.os_adapters().credentials(args.credentials)
        try:
            store.save(TOKEN)  # the keyring keeps it; the app reads it there
            check("the keyring kept the tour's token", store.load() == TOKEN)
        except OSError as error:  # the app then asks to sign in: a failed check
            check("the keyring kept the tour's token", False, error)

    fake_server.caption_for = caption_for
    server = fake_server.FakeServer()
    driver = Driver(args.limit)

    class Driven(QApplication):
        def __init__(self, qt_argv: list[str]) -> None:
            super().__init__(qt_argv)
            if self.platformName() == "offscreen" and sys.platform == "win32":
                from PySide6.QtGui import QFontDatabase  # offscreen reads no .ttc

                for collection in sorted(Path("C:/Windows/Fonts").glob("*.ttc")):
                    QFontDatabase.addApplicationFont(str(collection))
            driver.start()

    real_interface = app.new_interface

    def new_interface(*a: Any, **k: Any) -> Any:
        STATE["interface"] = real_interface(*a, **k)
        return STATE["interface"]

    class Recorded(app.DesktopApp):
        def __init__(self, *a: Any, **k: Any) -> None:
            super().__init__(*a, **k)
            STATE["desktop"] = self

    from polyglotic_desktop.ui import widgets
    from polyglotic_desktop.ui_next import controls

    widgets.QDesktopServices = NoLinks  # type: ignore[misc, assignment]
    controls.QDesktopServices = NoLinks  # type: ignore[misc, assignment]
    app.os_adapters = adapters(app.os_adapters, audio)
    app.QApplication = Driven  # type: ignore[misc, assignment]
    app.new_interface = new_interface
    app.DesktopApp = Recorded  # type: ignore[misc]
    began = time.monotonic()
    given = ["--credentials", args.credentials] if REAL["on"] else []
    try:
        app.main(["--server", server.url, "--data", str(data),
                  "--dictionaries", str(args.dictionaries), *given])  # fmt: skip
    except SystemExit:
        pass
    except Exception:  # noqa: BLE001 - said in the results
        check("the app started", False, traceback.format_exc()[-1500:])
    RESULTS["facts"]["seconds"] = round(time.monotonic() - began, 1)
    RESULTS["facts"]["server"] = {
        "sessions": len(server.hellos),
        "speech_frames": len(server.speech),
        "os": [hello.get("os") for hello in server.hellos],
    }
    check("the stand-in server heard speech", server.speech, len(server.speech))
    if REAL["on"]:
        players.stop()
        heard = sorted({str(header.source.id) for header, _ in server.speech})
        RESULTS["facts"]["sources_heard"] = heard
        if REAL["one_app"]:
            one_app_checks(heard)
        else:
            check("everything the PC plays was captioned", "system" in heard, heard)
            check("the mic was captioned", "mic" in heard, heard)
        try:
            store.delete()
        except OSError as error:
            check("the tour's token deleted from the keyring", False, error)
    write_results()
    server.stop()
    failed = [c["check"] for c in RESULTS["checks"] if not c["ok"]]
    print(
        f"app tour: {len(RESULTS['checks']) - len(failed)} passed, {len(failed)} failed"
    )
    return 1 if failed else 0


if __name__ == "__main__":
    code = main()
    sys.stdout.flush()
    os._exit(code)  # the app's threads don't hold the end
