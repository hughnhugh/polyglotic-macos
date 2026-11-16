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
signed in to a desktop session. Runs on Windows and Linux too: offscreen
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
from pathlib import Path
from typing import Any

import numpy as np
from PySide6.QtCore import QPointF, Qt, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QAbstractButton, QApplication, QWidget
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
PAGES = ("words", "settings")

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

        def speaker() -> Any:
            from polyglotic_desktop.platform.speaking import SpeakerThread

            return SpeakerThread(NoVoices(), SilentOutput)

        swaps: dict[str, Any] = {
            "app_list": PlayerListed,
            "app_capture": app_capture,
            "everything_else_capture": lambda *_a, **_k: silence(),
            "system_capture": lambda *_a, **_k: silence(),
            "mic_capture": lambda *_a, **_k: silence(),
            "credentials": lambda _entry: MemoryCredentialStore(TOKEN),
            "hotkeys": Nothing,
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
    (data / "settings.json").write_text(json.dumps(settings, ensure_ascii=False),
                                        encoding="utf-8")  # fmt: skip


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
        STATE["interface"].windows.windows.get(PLAYER) if "interface" in STATE else None
    )


def finished_lines() -> list[Any]:
    found = caption_window()
    return [ln for ln in found.view.lines if not ln.live] if found is not None else []


def a_word(window: Any) -> QPointF | None:
    """A word drawn on the caption window, found as a mouse would."""
    for y in range(6, window.height() - 4, 4):
        for x in range(6, window.width() - 4, 6):
            at = QPointF(x, y)
            marked = window._marked_at(at)
            if marked is not None and window.canvas.shown_row(marked.key, marked.row):
                return at
    return None


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
        if name in ("ConsentDialog", "LevelPicker"):
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

    if caption_window() is None:  # not opened from the settings: Home's picker
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

    spot = a_word(captions) if captions is not None else None
    if check("a word on the caption window to look up", spot is not None) and spot:
        QTest.mouseClick(captions, Qt.MouseButton.LeftButton, pos=spot.toPoint())
        card = lambda: STATE["interface"].windows.card
        yield wait(lambda: card() is not None and card().isVisible(), 10, "the card")
        yield pause(1.5)
        picture(card(), "card", "The lookup card")
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

    STATE["interface"].transcripts.show(PLAYER)
    transcript = lambda: next(
        (w for w in QApplication.topLevelWidgets()
         if w.isVisible() and "Transcript" in type(w).__name__), None)  # fmt: skip
    yield wait(lambda: transcript() is not None, 10, "the transcript")
    yield pause(1.0)
    picture(transcript(), "transcript", "The transcript")
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


def main(argv: list[str] | None = None) -> int:
    global OUT
    parser = argparse.ArgumentParser(prog="python -m tools.app_tour")
    parser.add_argument("out", type=Path)
    parser.add_argument("--dictionaries", default="build/dictionaries")
    parser.add_argument("--limit", type=float, default=300.0, help="seconds")
    args = parser.parse_args(argv)
    OUT = args.out
    OUT.mkdir(parents=True, exist_ok=True)
    data = OUT / "data"
    seed_settings(data)
    sample = sample_file("zh")
    if sample is None:
        check("the app's FLEURS sample is there", False)
        write_results()
        return 1
    audio = join([read_clip(sample)], gap=1.0)

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
    try:
        app.main(["--server", server.url, "--data", str(data),
                  "--dictionaries", str(args.dictionaries)])  # fmt: skip
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
