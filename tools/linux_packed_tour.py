r"""The packed AppImage's tour on a Linux desktop (polyglotic-hq 574, 546's
section 3): the release's own file, started as a learner starts it, and
checked from outside it - nothing of the tour runs inside the app.

    uv run --no-sync python -m tools.linux_packed_tour OUT --appimage FILE
        --desktop NAME [--tray yes|no] [--scheme dark|light] [--tls CERT KEY]
        [--pictures DIR]

The tour, from source, is only the outside: a stand-in server on this
machine (`tests/fake_server.py`, over TLS with `--tls`: its certificate
signed by a root the job added to the system's own store, so the packed
app's trust in the distribution's roots is what's checked), the players
(`tools/app_tour.Players`: a FLEURS clip through the sound server, a second
into the mic), the token kept where the app looks for it (the desktop's
Secret Service, or its file when the session has none) and a returning
learner's data folder (their settings, and the tester agreement's yes as
the app keeps it). Then the AppImage - copied to ~/Applications, made
executable, run - and:

- **signs in** to the stand-in with the kept token: the stand-in's `hello`
  says Linux and Linux's channel;
- **captions everything the PC plays and the mic**: the stand-in hears both
  sources;
- **its caption window is above a full-screen window**: in the desktop's own
  picture of its screen (the window manager's, `tools/linux_desktop_pictures`
  serving DIR, or Xvfb's root on Xfce), the caption window's place is drawn
  by the app, not by the full-screen window beneath - and on X11 its place in
  the stacking order is above that window;
- **light or dark**: with `--scheme`, Home - brought forward by a second
  start, as the launcher does (the app starts in the tray, as a sign-in
  starts it) - is dark or light in the desktop's picture;
- **its menu entry**: the desktop file the AppImage writes at its start,
  naming this file, valid by `desktop-file-validate`;
- **the tray** (`--tray yes`): its menu read over D-Bus by another process
  as the desktop's tray reads it (`tools/linux_tray_menu.py`) - Pause and
  Quit there, Dictation not (546's slice 8) - Pause clicked there pauses the
  speech sent, and Quit there ends the app;
- **the save dialogs** (`--dialogs`): Save transcript's and the export for
  Anki's, each opened by pressing the app's buttons as a screen reader
  does (AT-SPI, `tools/linux_atspi_press.py`) - the portal's file chooser
  asked for `SaveFile`, and no Qt dialog in the app (decision 0280);
- **one app at a time**: started again with one app chosen (`pw-play`'s
  recording) while another (`paplay`) plays a tone - the stand-in hears only
  the app's own source, and the speech it was sent has the recording and
  not the tone.

OUT gets `checks.json` (each check, pass or fail, and the facts), the
app's log and the desktop's pictures. Exits 0 when every check passed.
GitHub's runners only (`.github/workflows/linux-release.yml`).
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import re
import shutil
import signal
import ssl
import subprocess
import sys
import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

ENTRY = "Polyglotic/tour-574"
"""The token's entry in the keyring (the app's `--credentials`)."""
MENU_ENTRY = "io.polyglotic.Polyglotic.desktop"
GRADIENT = ((28, 64, 110), (10, 18, 34))
"""The full-screen window's ground, top to bottom (`linux_desktop_pictures`)."""
CARD_PINNED_MIN_WIDTH = 340
"""A pinned LookupCard is WIDTH=360 px at 100 % scale (hover cards max 320 px)."""
CAPTION_HEADER_SKIP_PX = 120
"""Pixels at the top of the caption window holding its title bar and detect
banner: never clicked when looking for a captioned word."""
CAPTION_BOTTOM_INSET_PX = 26
"""Pixels above the caption window's bottom edge where the newest line sits."""
CAPTION_SWEEP_STEP_PX = 18
"""Vertical step between probe clicks when locating a captioned word."""
CARD_SAY_RIGHT_INSET = 51
"""Say-it button centre from the pinned card's right edge (PAD 14 + close 22 + gap 4 + half 11)."""
CARD_CLOSE_RIGHT_INSET = 25
"""Close button centre from the pinned card's right edge (PAD 14 + half 11)."""
CARD_BUTTON_TOP_Y = 19
"""Top-bar button centre from the pinned card's top edge (top 8 + half 11)."""
VOICE_PEAK_DBFS = -40.0
"""Minimum peak loudness on speech-dispatcher's stream to count as audible (591)."""
VOICE_WAIT_SEC = 10.0
"""Seconds to wait for speech-dispatcher to start on demand or speak a word."""

RESULTS: dict[str, Any] = {"checks": [], "facts": {}, "pictures": []}


def runner_only() -> None:
    if os.environ.get("GITHUB_ACTIONS") != "true" or not sys.platform.startswith(
        "linux"
    ):
        sys.exit("574: this runs only on GitHub's Linux runners")


def check(name: str, ok: object, detail: object = "") -> bool:
    RESULTS["checks"].append(
        {"check": name, "ok": bool(ok), "detail": str(detail)[:800]}
    )
    print(f"[{'pass' if ok else 'FAIL'}] {name} {str(detail)[:240]}", flush=True)
    return bool(ok)


def wait(predicate: Callable[[], object], seconds: float) -> Any:
    end = time.monotonic() + seconds
    while True:
        found = predicate()
        if found or time.monotonic() > end:
            return found
        time.sleep(0.5)


# -- before the app starts: what a returning learner's PC has ----------------------


def returning_learner(data: Path, one_app: bool) -> None:
    """A learner of Mandarin who agreed to this tester agreement before
    (the app keeps the yes in its outbox: no first-run screen), captioning
    everything the PC plays and their own speech - or one app (`one_app`).
    The window's light or dark is the desktop's ("Like this PC")."""
    from polyglotic_desktop.adapters.sqlite_outbox import SqliteOutbox
    from polyglotic_desktop.core.shared.papers import TESTER_AGREEMENT_VERSION
    from polyglotic_desktop.ports.consent import Agreement, ConsentChoice
    from tools import app_tour as tour

    data.mkdir(parents=True, exist_ok=True)
    window = {
        "position": "bottom_centre",
        "spoken_language": "detect",
        "translate_into": "en",
        "text_size": 1.0,
        "translation_size": 1.0,
        "show_mic": False,
        "geometry": None,
    }
    if one_app:
        settings = {
            "learning": "zh",
            "apps": [tour.ONE_APP],
            "whole_system": False,
            "caption_windows": {
                "windows": {tour.ONE_APP: window},
                "last": dict(window),
            },
        }
    else:
        heard = dict(window, show_mic=True)
        settings = {
            "learning": "zh",
            "apps": [],
            "whole_system": True,
            "caption_mic": True,
            "caption_windows": {"windows": {tour.SYSTEM_KEY: heard}, "last": heard},
        }
    settings["window_theme"] = "system"  # Like this PC: the desktop's light or dark
    (data / "settings.json").write_text(json.dumps(settings), encoding="utf-8")
    now = datetime.now(UTC)
    outbox = SqliteOutbox(data / "outbox.sqlite")
    try:
        outbox.save_consent(
            ConsentChoice(
                str(uuid.uuid4()),
                now,
                False,
                False,
                False,
                Agreement(TESTER_AGREEMENT_VERSION, now),
            )
        )
    finally:
        outbox.close()


def keep_token() -> str:
    """The stand-in's token where the app looks: the desktop's Secret
    Service, or - with none in the session - the file the app falls back to
    (`platform/linux/secret_service`). Says which."""
    from polyglotic_desktop.platform.linux import secret_service
    from tools import app_tour as tour

    secret_service.SecretServiceStore(ENTRY).save(tour.TOKEN)
    if secret_service.SecretServiceStore(ENTRY).load() != tour.TOKEN:  # read afresh
        raise OSError("the token wasn't kept")
    try:
        secret_service.SecretService().read(ENTRY)
        return "the Secret Service"
    except secret_service.NoKeyring:
        return "the file (no Secret Service in this session)"


def learner_copy(appimage: Path) -> Path:
    """The AppImage as a learner puts it: ~/Applications, executable."""
    folder = Path.home() / "Applications"
    folder.mkdir(parents=True, exist_ok=True)
    app = folder / "Polyglotic.AppImage"
    shutil.copyfile(appimage, app)
    app.chmod(0o755)
    return app


# -- the app, from outside ---------------------------------------------------------


class Packed:
    """The AppImage running: its process group, its log. `in_tray`: started
    as a sign-in starts it, without Home (`--in-tray`), so nothing of the
    app's but its caption window is over the full-screen window."""

    def __init__(
        self, app: Path, server: str, data: Path, log: Path, in_tray: bool = False
    ) -> None:
        self.env = dict(os.environ)
        self.env.pop("QT_QPA_PLATFORM", None)  # the app chooses, as for a learner
        if not Path("/dev/fuse").exists():  # a container: no FUSE to mount it with
            self.env["APPIMAGE_EXTRACT_AND_RUN"] = "1"
        self.log = log
        self.data = data
        (data.parent / "no-feed").mkdir(
            parents=True, exist_ok=True
        )  # a feed of nothing
        self.command = [
            str(app),
            "--server",
            server,
            "--data",
            str(data),
            "--credentials",
            ENTRY,
            "--updates",
            str(data.parent / "no-feed"),
        ]
        self._log = log.open("wb")
        self.process = subprocess.Popen(
            [*self.command, *(["--in-tray"] if in_tray else [])],
            stdout=self._log,
            stderr=subprocess.STDOUT,
            env=self.env,
            start_new_session=True,
        )
        self.began = time.monotonic()

    def start_again(self) -> int | None:
        """A second start, as the desktop's launcher makes one: the copy
        running brings its window forward and this one ends (decision
        0101). Its exit code, or None if it didn't end."""
        try:
            return subprocess.run(
                self.command,
                env=self.env,
                timeout=90,
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            ).returncode
        except subprocess.TimeoutExpired:
            return None

    def running(self) -> bool:
        return self.process.poll() is None

    def end(self) -> None:
        if sys.platform == "win32":  # never: the tour runs on Linux only
            return
        if self.running():
            for sent in (signal.SIGTERM, signal.SIGKILL):
                try:
                    os.killpg(self.process.pid, sent)
                except ProcessLookupError:
                    break
                if wait(lambda: not self.running(), 10):
                    break
        self._log.close()

    def app_log(self) -> str:
        found = self.data / "logs" / "polyglotic.log"
        return (
            found.read_text(encoding="utf-8", errors="replace")
            if found.exists()
            else ""
        )


def x_windows() -> list[dict[str, Any]]:
    """The X server's top-level windows, bottom to top, as `xwininfo` says:
    each one's name, place, whether it's shown and override-redirect."""
    said = subprocess.run(
        ["xwininfo", "-root", "-children"],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    ).stdout
    found = []
    for line in said.splitlines():
        match = re.match(r'\s+(0x[0-9a-f]+) (?:"(.*)"|\(has no name\)):', line)
        if not match:
            continue
        number = match.group(1)
        info = subprocess.run(
            ["xwininfo", "-id", number],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        ).stdout
        field = dict(re.findall(r"^\s+([\w -]+):\s+(.*)$", info, re.MULTILINE))
        name = match.group(2) or ""
        if not name:  # a window manager's frame: its client's name
            tree = subprocess.run(
                ["xwininfo", "-id", number, "-children"],
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
            ).stdout
            inner = re.search(r'\s+0x[0-9a-f]+ "(.*)":', tree)
            name = inner.group(1) if inner else ""
        try:
            found.append(
                {
                    "id": number,
                    "name": name,
                    "x": int(field["Absolute upper-left X"]),
                    "y": int(field["Absolute upper-left Y"]),
                    "width": int(field["Width"]),
                    "height": int(field["Height"]),
                    "shown": field.get("Map State") == "IsViewable",
                    "override_redirect": field.get("Override Redirect State") == "yes",
                }
            )
        except (KeyError, ValueError):
            continue
    # `xwininfo -root -children` lists them top to bottom
    return list(reversed(found))


def window_class(number: str) -> str:
    """An X window's WM_CLASS: whose program drew it (the app's is
    Polyglotic; GTK's portal's, xdg-desktop-portal-gtk)."""
    said = subprocess.run(
        ["xprop", "-id", number, "WM_CLASS"],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    ).stdout
    return said.partition("=")[2].strip()


def caption_window(windows: list[dict[str, Any]]) -> dict[str, Any] | None:
    shown = [w for w in windows if w["shown"] and w["name"].endswith(" captions")]
    return shown[-1] if shown else None


def home_window(windows: list[dict[str, Any]]) -> dict[str, Any] | None:
    shown = [
        w
        for w in windows
        if w["shown"] and w["name"] == "Polyglotic" and w["width"] > 300
    ]
    return shown[-1] if shown else None


class Pictures:
    """The desktop's own picture of its virtual screen: the window manager's
    (`tools/linux_desktop_pictures serve DIR`), or the X server's root on a
    bare X desktop (Xfce on Xvfb)."""

    def __init__(self, folder: Path, desktop: str) -> None:
        self.folder = folder
        self.desktop = desktop
        folder.mkdir(parents=True, exist_ok=True)

    def take(self, name: str) -> Path | None:
        picture = self.folder / f"{name}.png"
        if self.desktop == "xfce":
            subprocess.run(
                ["import", "-window", "root", str(picture)], timeout=30, check=False
            )
        else:
            (self.folder / f"{name}.want").touch()
            wait(
                lambda: picture.exists() or (self.folder / f"{name}.failed").exists(),
                40,
            )
            time.sleep(0.5)  # written whole
        if picture.exists():
            RESULTS["pictures"].append({"file": f"desk/{name}.png", "what": name})
            return picture
        failed = self.folder / f"{name}.failed"
        RESULTS["facts"].setdefault("pictures_failed", {})[name] = (
            failed.read_text(errors="replace")[:300] if failed.exists() else "none"
        )
        return None


def drawn_by_the_app(picture: Path, window: dict[str, Any]) -> tuple[float, str]:
    """How much of `window`'s place in `picture` isn't the full-screen
    window's ground (its gradient at that height): the share of pixels
    more than 12 apart from it in any channel, and the mean colour. Not
    drawn there, the ground is all there is (the picture is lossless)."""
    from PySide6.QtGui import QImage

    image = QImage(str(picture))
    if image.isNull():
        return 0.0, "unreadable picture"
    height = image.height()
    differ = total = 0
    sums = [0, 0, 0]
    for y in range(max(window["y"], 0), min(window["y"] + window["height"], height), 3):
        t = y / max(height - 1, 1)
        ground = [a + (b - a) * t for a, b in zip(*GRADIENT, strict=True)]
        for x in range(
            max(window["x"], 0), min(window["x"] + window["width"], image.width()), 3
        ):
            colour = image.pixelColor(x, y)
            rgb = (colour.red(), colour.green(), colour.blue())
            total += 1
            sums = [s + c for s, c in zip(sums, rgb, strict=True)]
            if max(abs(c - g) for c, g in zip(rgb, ground, strict=True)) > 12:
                differ += 1
    if not total:
        return 0.0, "the window is off the picture"
    mean = tuple(round(s / total) for s in sums)
    return differ / total, f"mean {mean}"


def luminance(picture: Path, window: dict[str, Any]) -> float | None:
    """`window`'s mean luminance (0 black, 1 white) in `picture`."""
    from PySide6.QtGui import QImage

    image = QImage(str(picture))
    if image.isNull():
        return None
    values = []
    for y in range(
        max(window["y"], 0), min(window["y"] + window["height"], image.height()), 4
    ):
        for x in range(
            max(window["x"], 0), min(window["x"] + window["width"], image.width()), 4
        ):
            c = image.pixelColor(x, y)
            values.append(
                (0.2126 * c.red() + 0.7152 * c.green() + 0.0722 * c.blue()) / 255
            )
    return round(float(np.mean(values)), 3) if values else None


def tray_menu(out: Path, click: str | None = None) -> dict[str, Any] | None:
    """The app's tray menu, read (and an item clicked) over D-Bus by
    another process (`tools/linux_tray_menu.py`)."""
    command = [sys.executable, "-m", "tools.linux_tray_menu", str(out)]
    if click:
        command += ["--click", click]
    said = subprocess.run(
        command, capture_output=True, text=True, timeout=90, check=False
    )
    (out.with_suffix(".log")).write_text(said.stdout + said.stderr, encoding="utf-8")
    if said.returncode != 0 or not out.exists():
        return None
    return json.loads(out.read_text(encoding="utf-8"))


def labels(menu: dict[str, Any]) -> list[str]:
    found: list[str] = []

    def walk(items: list[dict[str, Any]]) -> None:
        for item in items:
            if item.get("visible", True) and item.get("label"):
                found.append(item["label"])
            walk(item.get("children", []))

    walk(menu.get("layout", {}).get("children", []))
    return found


def speech_audio(server: Any, kinds: tuple[str, ...] = ("finished",)) -> np.ndarray:
    """What the app sent the stand-in as speech, decoded (Ogg Opus, 16 kHz)."""
    import soundfile

    parts = []
    for header, payload in list(server.speech):
        if str(getattr(header, "kind", "")) not in kinds or not payload:
            continue
        try:
            samples, _rate = soundfile.read(io.BytesIO(payload), dtype="float32")
        except Exception:  # noqa: BLE001, S112 - one unreadable frame isn't the tour's end
            continue
        parts.append(samples.reshape(-1))
    return np.concatenate(parts) if parts else np.zeros(0, dtype=np.float32)


def heard_sources(server: Any) -> list[str]:
    return sorted({str(header.source.id) for header, _ in list(server.speech)})


# -- the tour ----------------------------------------------------------------------


def everything_and_mic(
    args: argparse.Namespace, app: Path, server: Any, pictures: Pictures
) -> None:
    import soundfile

    from polyglotic_desktop.platform.replay import join, read_clip
    from polyglotic_desktop.platform.sample import sample_file
    from tools import app_tour as tour

    out: Path = args.out
    sample = sample_file("zh")
    mine = sample_file("en") or sample
    assert sample is not None and mine is not None
    clip, spoken = out / "played-zh.wav", out / "spoken-en.wav"
    soundfile.write(str(clip), join([read_clip(sample)], gap=1.0), 16_000)
    soundfile.write(str(spoken), join([read_clip(mine)], gap=1.0), 16_000)
    players = tour.Players()
    players.play(clip, None)  # everything the PC plays
    players.play(spoken, os.environ.get("POLYGLOTIC_MIC_SINK"))  # the learner's own
    data = out / "data"
    returning_learner(data, one_app=False)
    packed = Packed(app, server.url, data, out / "app.log", in_tray=True)
    try:
        hello = wait(lambda: server.hellos, 120)
        said = hello[0] if hello else {}
        RESULTS["facts"]["hello"] = {
            k: said.get(k) for k in ("os", "channel", "app_version")
        }
        check(
            "the AppImage started and stayed up",
            packed.running(),
            f"after {round(time.monotonic() - packed.began)} s",
        )
        check(
            "signed in to the stand-in with the kept token (its hello)",
            hello,
            RESULTS["facts"]["hello"],
        )
        check(
            "its hello says Linux",
            str(said.get("os", "")).startswith("linux-"),
            said.get("os"),
        )
        wait(lambda: {"system", "mic"} <= set(heard_sources(server)), 150)
        heard = heard_sources(server)
        RESULTS["facts"]["sources_heard"] = heard
        check("everything the PC plays was captioned", "system" in heard, heard)
        check("the mic was captioned", "mic" in heard, heard)
        time.sleep(4)  # the captions shown
        windows = x_windows()
        RESULTS["facts"]["x_windows"] = [
            {
                k: w[k]
                for k in ("name", "x", "y", "width", "height", "override_redirect")
            }
            for w in windows
            if w["shown"]
        ]
        captions = caption_window(windows)
        check("the caption window shows", captions, captions)
        picture = pictures.take("captions-and-home")
        check(
            "the desktop's own picture of its screen",
            picture is not None,
            RESULTS["facts"].get("pictures_failed", {}),
        )
        if captions is not None:
            check(
                "the caption window is override-redirect (above every window)",
                captions["override_redirect"],
                captions,
            )
            beneath = [
                i
                for i, w in enumerate(windows)
                if w["shown"] and w["name"] == "A full-screen video"
            ]
            if beneath:  # an X11 full-screen window (Xfce): the stacking order
                check(
                    "above the full-screen window in X's stacking order",
                    windows.index(captions) > beneath[-1],
                    [w["name"] for w in windows if w["shown"]],
                )
            if picture is not None:
                share, said_colour = drawn_by_the_app(picture, captions)
                check(
                    "over the full-screen window, the caption window is what's drawn",
                    share > 0.3,
                    f"{round(share * 100, 1)} % of its place not the window beneath; {said_colour}",
                )
        if args.scheme:
            home_in_its_scheme(args.scheme, pictures, packed)
        entry = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
        entry = entry / "applications" / MENU_ENTRY
        written = entry.read_text(encoding="utf-8") if entry.exists() else ""
        shutil.copyfile(entry, out / MENU_ENTRY) if entry.exists() else None
        check(
            "its menu entry is written, starting this AppImage",
            f"Exec={app}" in written,
            entry,
        )
        if shutil.which("desktop-file-validate") and written:
            valid = subprocess.run(
                ["desktop-file-validate", str(entry)],
                capture_output=True,
                text=True,
                check=False,
            )
            check(
                "and it's valid (desktop-file-validate)",
                valid.returncode == 0,
                valid.stdout + valid.stderr,
            )
        if args.voice:
            the_voice(pictures)
        if args.tray == "yes":
            the_tray(out, packed, server)
        players.stop()
    finally:
        packed.end()
        players.stop()
        log = packed.app_log()
        (out / "polyglotic.log").write_text(log, encoding="utf-8")
        check(
            "no crash in its log",
            "Traceback" not in log and log,
            f"{len(log)} characters",
        )


def home_in_its_scheme(scheme: str, pictures: Pictures, packed: Packed) -> None:
    """Home, dark or light as the desktop prefers (the settings portal's
    `color-scheme`, 571): brought forward by a second start, as the
    launcher does (the app started in the tray), with the full-screen
    window beneath ended first (`POLYGLOTIC_BENEATH_PID`); then its mean
    luminance in the desktop's picture. The screen behind is black, so a
    dark Home must still be lighter than that: a Home not drawn reads as no
    scheme at all."""
    beneath = os.environ.get("POLYGLOTIC_BENEATH_PID", "")
    if beneath.isdigit() and sys.platform != "win32":
        with contextlib.suppress(ProcessLookupError):
            os.kill(int(beneath), signal.SIGTERM)
        time.sleep(2)
    again = packed.start_again()
    check("a second start brings Home forward and ends", again == 0, again)
    wait(lambda: home_window(x_windows()), 15)
    time.sleep(2)  # drawn
    picture = pictures.take("home")
    home = home_window(x_windows())
    light = luminance(picture, home) if picture and home else None
    RESULTS["facts"]["home_luminance"] = light
    RESULTS["facts"]["home_window"] = home
    if scheme == "dark":
        ok = light is not None and 0.04 < light < 0.4
    else:
        ok = light is not None and light > 0.6
    check(f"Home follows the desktop's {scheme} scheme", ok, f"luminance {light}")


def speech_dispatcher_running() -> tuple[bool, list[str]]:
    """Whether speech-dispatcher is running or has an open stream on the sound
    server (`(process_running, speechd_streams)`)."""
    from polyglotic_desktop.platform.linux import pulse

    proc = subprocess.run(
        ["pgrep", "-x", "speech-dispatcher"],
        capture_output=True,
        text=True,
        check=False,
    )
    streams: list[str] = []
    try:
        server = pulse.PulseServer("Polyglotic tour voice check")
        try:
            streams = [
                s.app_name
                for s in server.streams()
                if s.app_name and s.app_name.startswith("speech-dispatcher")
            ]
        finally:
            server.close()
    except OSError:
        pass
    return proc.returncode == 0, sorted(set(streams))


def _click(x: int, y: int) -> None:
    subprocess.run(
        ["xdotool", "mousemove", str(x), str(y), "click", "1"],
        timeout=15,
        check=False,
    )


def the_voice(pictures: Pictures) -> None:
    """The packed AppImage says a word on demand (polyglotic-hq 646):
    1. before any word card opens, speech-dispatcher is not running;
    2. clicking a captioned word pins LookupCard and starts speech-dispatcher;
    3. clicking Say it plays audible speech on speech-dispatcher's stream."""
    from tools import app_tour as tour

    running_before, streams_before = speech_dispatcher_running()
    RESULTS["facts"]["voice_before_card"] = {
        "process": running_before,
        "streams": streams_before,
    }
    check(
        "speech-dispatcher isn't running before a card asks",
        not running_before and not streams_before,
        RESULTS["facts"]["voice_before_card"],
    )
    windows = x_windows()
    captions = caption_window(windows)
    if not check("voice check: caption window present to click a word", captions):
        return
    assert captions is not None
    before_ids = {w["id"] for w in windows if w["shown"]}
    card: dict[str, Any] | None = None
    # Sweep bottom-up through the caption lines, staying below the top bar and
    # language-detect banner so we only click captioned words (never header popovers).
    y_start = captions["y"] + max(
        captions["height"] - CAPTION_BOTTOM_INSET_PX, CAPTION_HEADER_SKIP_PX
    )
    y_stop = captions["y"] + CAPTION_HEADER_SKIP_PX
    y_points = range(y_start, y_stop - 1, -CAPTION_SWEEP_STEP_PX)
    x_points = [
        captions["x"] + round(captions["width"] * frac)
        for frac in (0.08, 0.15, 0.22, 0.30, 0.40)
    ]
    for y in y_points:
        for x in x_points:
            _click(x, y)
            time.sleep(0.4)
            now = x_windows()
            card = next(
                (
                    w
                    for w in now
                    if w["shown"]
                    and w["override_redirect"]
                    and w["id"] not in before_ids
                    and w["width"] >= CARD_PINNED_MIN_WIDTH
                ),
                None,
            )
            if card is not None:
                break
        if card is not None:
            break
    if not check(
        "voice check: a word card pinned on a caption word", card is not None, card
    ):
        pictures.take("voice-no-card")
        return
    assert card is not None
    # Keep the pointer on the card so LEAVE_MS never closes it while speech-dispatcher starts
    say_x = card["x"] + card["width"] - CARD_SAY_RIGHT_INSET
    say_y = card["y"] + CARD_BUTTON_TOP_Y
    subprocess.run(
        ["xdotool", "mousemove", str(say_x), str(say_y)], timeout=15, check=False
    )
    started = wait(lambda: speech_dispatcher_running()[0], VOICE_WAIT_SEC)
    time.sleep(
        1.5
    )  # allow voice listing + WordSpeech._recheck (600 ms) to flip to READY
    refreshed = next(
        (w for w in x_windows() if w["shown"] and w["id"] == card["id"]), card
    )
    say_x = refreshed["x"] + refreshed["width"] - CARD_SAY_RIGHT_INSET
    say_y = refreshed["y"] + CARD_BUTTON_TOP_Y
    watched = tour.VoiceStream()
    asked = time.perf_counter()
    try:
        _click(say_x, say_y)
        heard = wait(
            lambda: watched.first is not None and watched.peak > VOICE_PEAK_DBFS,
            VOICE_WAIT_SEC / 2,
        )
        if not heard:
            # Retry once in case speech-dispatcher finished listing just after the first click
            refreshed = next(
                (w for w in x_windows() if w["shown"] and w["id"] == card["id"]),
                refreshed,
            )
            say_x = refreshed["x"] + refreshed["width"] - CARD_SAY_RIGHT_INSET
            say_y = refreshed["y"] + CARD_BUTTON_TOP_Y
            _click(say_x, say_y)
            heard = wait(
                lambda: watched.first is not None and watched.peak > VOICE_PEAK_DBFS,
                VOICE_WAIT_SEC,
            )
        time.sleep(1.5)
        pictures.take("card-said")
    finally:
        watched.stop()
        close_x = refreshed["x"] + refreshed["width"] - CARD_CLOSE_RIGHT_INSET
        close_y = refreshed["y"] + CARD_BUTTON_TOP_Y
        _click(close_x, close_y)
    said = {
        "speechd_started_on_card": bool(started),
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
    check(
        "Say it: the packed AppImage said a word through speech-dispatcher",
        watched.first is not None and watched.peak > VOICE_PEAK_DBFS,
        said,
    )


def the_tray(out: Path, packed: Packed, server: Any) -> None:
    menu = tray_menu(out / "tray.json")
    if not check(
        "the tray's menu is read over D-Bus, as the desktop's tray reads it",
        menu is not None,
    ):
        return
    assert menu is not None
    shown = labels(menu)
    RESULTS["facts"]["tray_menu"] = shown
    check(
        "Pause captions and Quit are in it",
        {"Pause captions", "Quit"} <= set(shown),
        shown,
    )
    check(
        "dictation isn't offered (Linux has none until slice 8)",
        not any("Dictation" in label for label in shown),
        shown,
    )
    before = len(server.speech)
    clicked = tray_menu(out / "tray-pause.json", click="Pause captions")
    time.sleep(4)  # what was on its way
    paused_at = len(server.speech)
    time.sleep(12)
    RESULTS["facts"]["speech_frames_around_pause"] = [
        before,
        paused_at,
        len(server.speech),
    ]
    check(
        "Pause captions clicked there pauses the speech sent",
        clicked is not None and len(server.speech) - paused_at <= 1,
        RESULTS["facts"]["speech_frames_around_pause"],
    )
    tray_menu(out / "tray-quit.json", click="Quit")
    check(
        "Quit there ends the app",
        wait(lambda: not packed.running(), 30),
        packed.process.poll(),
    )


def the_dialogs(
    args: argparse.Namespace, app: Path, server: Any, pictures: Pictures
) -> None:
    """Save transcript's dialog and the export for Anki's are the desktop's
    own (decision 0280): each button pressed as a screen reader presses it
    (`tools/linux_atspi_press.py`, AT-SPI, from another process; the app
    started with `QT_LINUX_ACCESSIBILITY_ALWAYS_ON=1`) - Home's Transcript,
    then the transcript's Save transcript as...; and, in a new start,
    Home's Words, then its Anki deck file (.apkg). The desktop's own dialog
    is the portal's: the app asks the portal's file chooser for `SaveFile`
    on the session bus, with the dialog's title, and the portal's process
    draws it - never Qt's own dialog in the app's windows."""
    out: Path = args.out / "dialogs"
    out.mkdir(parents=True, exist_ok=True)
    calls = out / "portal-calls.txt"
    watch = subprocess.Popen(
        [
            "dbus-monitor",
            "--session",
            "type='method_call',interface='org.freedesktop.portal.FileChooser'",
        ],
        stdout=calls.open("wb"),
        stderr=subprocess.STDOUT,
    )

    def said() -> str:
        return calls.read_text(errors="replace")

    press = Path(__file__).with_name("linux_atspi_press.py")
    dialogs: list[tuple[str, list[str], str]] = [
        (
            "anki-export",
            ["?Words", "Anki deck file (.apkg)"],
            "Export words as an Anki deck file",
        ),
    ]
    if args.tray == "yes":  # the transcript window, opened from the tray's menu
        # (Home's Transcript buttons aren't told apart over AT-SPI); a narrow
        # window folds Save into its "More" menu
        dialogs.insert(
            0,
            (
                "save-transcript",
                [
                    "Save transcript as… || More: Copy all, Save transcript as…",
                    "?menu:Save transcript as…",
                ],
                "Save transcript",
            ),
        )
    else:
        RESULTS["facts"]["save_transcript_dialog"] = (
            "not run here: no tray to open a transcript window from outside"
        )
    try:
        for name, buttons, title in dialogs:
            data = out / f"data-{name}"
            returning_learner(data, one_app=False)
            packed = Packed(app, server.url, data, out / f"app-{name}.log")
            try:
                wait(lambda: home_window(x_windows()), 60)
                time.sleep(3)
                if name == "save-transcript":
                    tray_menu(
                        out / "tray-transcript.json", click="Everything the PC plays"
                    )
                    shown = wait(
                        lambda: [
                            w
                            for w in x_windows()
                            if w["shown"] and "transcript" in w["name"].lower()
                        ],
                        20,
                    )
                    # wide enough that Save is a button of its own, not in
                    # "More" (FOLD_BELOW): a menu opened over AT-SPI never
                    # showed its items (run 44746214946)
                    for window in shown or []:
                        subprocess.run(
                            [
                                "xdotool",
                                "windowsize",
                                str(int(window["id"], 16)),
                                "1200",
                                "800",
                            ],
                            timeout=20,
                            check=False,
                        )
                    time.sleep(3)
                pressed = subprocess.run(
                    ["/usr/bin/python3", str(press), *buttons],
                    capture_output=True,
                    text=True,
                    timeout=150,
                    check=False,
                )
                (out / f"{name}-press.txt").write_text(
                    pressed.stdout + pressed.stderr, encoding="utf-8"
                )
                # the dialog's own button reached? If not, the harness
                # couldn't get to it here (GNOME Shell kept the transcript
                # window narrow, and a menu opened over AT-SPI showed no
                # items: run 44753352000) - said, not counted as the app's
                last = buttons[-1].lstrip("?").removeprefix("menu:")
                reached = any(
                    json.loads(line).get("pressed") in (last, *last.split(" || "))
                    for line in pressed.stdout.splitlines()
                    if line.startswith("{")
                )
                if not reached and name == "save-transcript":
                    RESULTS["facts"]["save_transcript_dialog"] = (
                        "not opened here: the harness couldn't reach its button"
                    )
                    pictures.take(f"{name}-not-reached")
                    continue
                wanted = f'"{title}"'
                asked = wait(lambda: wanted in said() and "SaveFile" in said(), 30)  # noqa: B023
                time.sleep(3)  # drawn
                drawn = {
                    w["id"]: window_class(w["id"])
                    for w in x_windows()
                    if w["shown"] and w["name"] == title
                }
                RESULTS["facts"][f"{name}_dialog_windows"] = drawn
                check(
                    f"{title}: the desktop's own dialog (the portal's SaveFile)",
                    asked,
                    (pressed.stdout + pressed.stderr)[-300:],
                )
                check(
                    f"{title}: drawn by the portal's process, not the app",
                    not any("polyglotic" in c.lower() for c in drawn.values()),
                    drawn or "a Wayland window (not in X's list)",
                )
                pictures.take(f"{name}-dialog")
            finally:
                packed.end()
    finally:
        watch.terminate()


def one_app(
    args: argparse.Namespace, app: Path, server: Any, pictures: Pictures
) -> None:
    import soundfile

    from polyglotic_desktop.platform.replay import join, read_clip
    from polyglotic_desktop.platform.sample import sample_file
    from tools import app_tour as tour

    out: Path = args.out / "one-app"
    out.mkdir(parents=True, exist_ok=True)
    sample = sample_file("zh")
    assert sample is not None
    audio = join([read_clip(sample)], gap=1.0)
    long = out / "played-zh-long.wav"
    soundfile.write(
        str(long), np.tile(audio, int(np.ceil(240 * 16_000 / len(audio)))), 16_000
    )
    tone = out / "other-app-tone.wav"
    seconds = np.arange(16_000 * 240) / 16_000
    soundfile.write(str(tone), 0.3 * np.sin(2 * np.pi * tour.TONE_HZ * seconds), 16_000)
    players = tour.Players()
    players.play(long, None, tour.ONE_PLAYER)
    players.play(tone, None, tour.OTHER_PLAYER)
    server.speech.clear()
    data = out / "data"
    returning_learner(data, one_app=True)
    packed = Packed(app, server.url, data, out / "app.log")
    try:
        wait(lambda: any(s.startswith("app-") for s in heard_sources(server)), 150)
        time.sleep(20)  # a few finished captions
        heard = heard_sources(server)
        RESULTS["facts"]["one_app_sources_heard"] = heard
        apps = [s for s in heard if s.startswith("app-")]
        check("one app: the app chosen was captioned on its own source", apps, heard)
        check("one app: nothing else was captioned", set(heard) <= set(apps), heard)
        samples = speech_audio(server, ("finished", "live"))
        measured: dict[str, Any] = {"seconds": round(len(samples) / 16_000, 1)}
        loud = samples[np.abs(samples) > 0][-16_000 * 20 :]
        if len(loud) >= 16_000 * 2:
            rms = float(np.sqrt(np.mean(loud**2)))
            measured["rms_dbfs"] = round(20 * float(np.log10(max(rms, 1e-12))), 1)
            measured["tone_dbfs"], measured["tone_over_neighbours_db"] = (
                tour.tone_over_neighbours(loud, tour.TONE_HZ)
            )
        RESULTS["facts"]["one_app"] = measured
        check(
            "one app: its recording is in the speech sent",
            measured.get("rms_dbfs", -200) > -45,
            measured,
        )
        check(
            "one app: the other app's tone isn't",
            measured.get("tone_over_neighbours_db", 99) < 20,
            measured,
        )
        pictures.take("one-app-captions")
    finally:
        packed.end()
        players.stop()
        (out / "polyglotic.log").write_text(packed.app_log(), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    runner_only()
    parser = argparse.ArgumentParser(prog="python -m tools.linux_packed_tour")
    parser.add_argument("out", type=Path)
    parser.add_argument("--appimage", type=Path, required=True)
    parser.add_argument("--desktop", required=True)
    parser.add_argument("--tray", choices=["yes", "no"], default="no")
    parser.add_argument("--scheme", choices=["dark", "light", ""], default="")
    parser.add_argument("--tls", nargs=2, metavar=("CERT", "KEY"))
    parser.add_argument("--pictures", type=Path)
    parser.add_argument(
        "--dialogs",
        action="store_true",
        help="with --tray yes: Save transcript's dialog, from Quit's question",
    )
    parser.add_argument(
        "--voice",
        action="store_true",
        help="check speech-dispatcher starts on demand and speaks a word (X11/xdotool)",
    )
    args = parser.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    from tests import fake_server

    from tools import app_tour as tour

    RESULTS["facts"] |= {
        "desktop": args.desktop,
        "session": os.environ.get("XDG_SESSION_TYPE", ""),
        "appimage_bytes": args.appimage.stat().st_size,
    }
    app = learner_copy(args.appimage)
    try:
        kept_in = keep_token()
        check("the token is kept where the app looks", True, kept_in)
        RESULTS["facts"]["keyring"] = kept_in
    except OSError as error:
        check("the token is kept where the app looks", False, error)
    tls = None
    if args.tls:
        tls = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        tls.load_cert_chain(*args.tls)
    fake_server.caption_for = tour.caption_for
    server = fake_server.FakeServer(tls=tls)
    # the stand-in's welcome names Windows' channel (the protocol's example),
    # which the app would follow (run 44736206098): Linux's, as the server
    # names the channel of the platform the app asked for
    if "channel" in server.welcome:
        server.welcome["channel"] = "linux-x64-alpha"
    url = server.url.replace("127.0.0.1", "localhost")
    RESULTS["facts"]["server"] = url
    server.url = url
    pictures = Pictures(args.pictures or args.out / "desk", args.desktop)
    try:
        everything_and_mic(args, app, server, pictures)
        one_app(args, app, server, pictures)
        if args.dialogs:
            the_dialogs(args, app, server, pictures)
    except Exception as error:  # noqa: BLE001 - said in the results
        import traceback

        check("the tour ran to its end", False, traceback.format_exc()[-1500:] or error)
    finally:
        server.stop()
        failed = [c["check"] for c in RESULTS["checks"] if not c["ok"]]
        (args.out / "checks.json").write_text(
            json.dumps(RESULTS, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(
            f"packed tour ({args.desktop}): {len(RESULTS['checks']) - len(failed)}"
            f" passed, {len(failed)} failed",
            flush=True,
        )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
