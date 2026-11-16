"""The apps with sound on a Mac, for the app picker (the `AppList` port), and
the processes a capture of one app taps (polyglotic-hq 411).

Core Audio keeps a process object for each process using audio (macOS
14.2+; read through catap): its PID, bundle ID and whether it plays now.
An app often plays from a helper process of its own - Chrome and every
Electron app (Discord, Slack, Teams) from a "Helper" app inside its
bundle - so processes are grouped by **the app they belong to**: the
outermost `.app` in the executable's path (Chrome's helper lives inside
`Google Chrome.app`), named by that app's bundle ID. A few play from
outside their bundle (WebKit's media process plays Safari's sound:
`categories.ALIASES`). Each group is one entry, named by its bundle ID -
the same in every language - and captured as one tap of all its processes
(`capture.AppCapture`), which follows helpers as they come and go.

Polyglotic's own processes are never an app to caption (polyglotic-hq 368):
this process, and any copy of the app by its executable's name.
"""

import contextlib
import ctypes
import functools
import os
import plistlib
import sys
import threading
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import PurePosixPath

from polyglotic_desktop.platform.macos.categories import (
    ALIASES,
    category_of,
    known_name,
    shown_name,
)
from polyglotic_desktop.ports.capture import PlayingApp

APP_EXECUTABLE = "polyglotic"
"""Every packed copy's executable, inside `Polyglotic.app/Contents/MacOS/`
(polyglotic-hq 410's spec), the installed app and a preview alike."""
SNAPSHOT_SEC = 0.5
"""How long one look at Core Audio's processes serves every capture: four
captures checking each second share it."""
_USER_APPS = ("/Applications/", "/System/Applications/", "/Users/")
"""Where the apps a learner opens live (Apple's own - Music, TV,
QuickTime Player - in /System/Applications), as against macOS' helpers."""


@dataclass(frozen=True, slots=True)
class AudioProcess:
    """A process using audio, as Core Audio reports it: its process object
    (what a tap names), PID, bundle ID (None if it has none), its name for
    the learner's eyes, whether it plays sound now, and its executable's
    path (None if it can't be read)."""

    object_id: int
    pid: int
    bundle_id: str | None
    name: str
    playing: bool
    path: str | None = None


def outer_app(path: str | None) -> str | None:
    """The outermost `.app` bundle the executable at `path` is inside
    (`/Applications/Google Chrome.app` for Chrome's helper), or None."""
    if not path:
        return None
    parts = PurePosixPath(path).parts
    for i, part in enumerate(parts):
        if part.lower().endswith(".app"):
            return str(PurePosixPath(*parts[: i + 1]))
    return None


@functools.lru_cache(maxsize=256)
def bundle_info(app: str) -> tuple[str | None, str | None]:
    """The bundle ID and display name in the `.app` at `app`'s Info.plist;
    (None, None) if it can't be read. Read once per app."""
    try:
        with open(os.path.join(app, "Contents", "Info.plist"), "rb") as file:
            info = plistlib.load(file)
    except (OSError, plistlib.InvalidFileException, ValueError):
        return None, None
    bundle_id = info.get("CFBundleIdentifier")
    name = info.get("CFBundleDisplayName") or info.get("CFBundleName")
    return (
        bundle_id if isinstance(bundle_id, str) else None,
        name if isinstance(name, str) else None,
    )


def app_key(
    process: AudioProcess,
    info: Callable[[str], tuple[str | None, str | None]] | None = None,
) -> str:
    """The app `process` belongs to, by bundle ID: an alias's app; else the
    outermost `.app`'s; else its own; else its executable's name (a command
    line tool: `afplay`). `info`: an app's bundle ID and name (`bundle_info`)."""
    info = info or bundle_info
    own = process.bundle_id
    if own and own.lower() in ALIASES:
        return ALIASES[own.lower()]
    app = outer_app(process.path)
    if app is not None:
        bundle_id, _ = info(app)
        if bundle_id:
            return bundle_id
    if own:
        return own
    if process.path:
        return PurePosixPath(process.path).name
    return process.name


def grouped(
    processes: Iterable[AudioProcess],
    info: Callable[[str], tuple[str | None, str | None]] | None = None,
) -> dict[str, list[AudioProcess]]:
    """The processes using audio, by the app they belong to (`app_key`)."""
    info = info or bundle_info
    groups: dict[str, list[AudioProcess]] = {}
    for process in processes:
        groups.setdefault(app_key(process, info), []).append(process)
    return groups


def is_polyglotic(members: Iterable[AudioProcess], this: int) -> bool:
    """Whether an app's processes are Polyglotic's: this process (from
    source, Python), or any copy of it by its executable's name."""
    return any(
        p.pid == this
        or (p.path is not None and PurePosixPath(p.path).name.lower() == APP_EXECUTABLE)
        for p in members
    )


def main_process(key: str, members: list[AudioProcess]) -> AudioProcess:
    """The process that stands for an app: the one with the app's own
    bundle ID, else the oldest (the lowest PID: helpers start after)."""
    own = [p for p in members if (p.bundle_id or "").lower() == key.lower()]
    return min(own or members, key=lambda p: p.pid)


def playing_apps(
    processes: Iterable[AudioProcess],
    this: int,
    info: Callable[[str], tuple[str | None, str | None]] | None = None,
) -> list[PlayingApp]:
    """The apps with sound, one entry per app (`grouped`), playing first:
    each named by its bundle ID, shown by the known-apps list's name, its
    bundle's or Core Audio's. An app that isn't playing is listed only if
    it's an app the learner installed - not one of macOS' own helpers,
    which keep audio open all the time."""
    info = info or bundle_info
    apps = []
    for key, members in grouped(processes, info).items():
        if is_polyglotic(members, this):
            continue  # its own sounds: never an app to caption (368)
        playing = any(p.playing for p in members)
        main = main_process(key, members)
        app = outer_app(main.path)
        if not playing and not (app and app.startswith(_USER_APPS)):
            continue
        own_name = shown_name(key) or (info(app)[1] if app else None) or main.name
        apps.append(
            PlayingApp(
                main.pid,
                key,
                playing,
                category_of(key, main.path),
                known_name(key),
                own_name,
            )
        )
    return sorted(apps, key=lambda a: (not a.playing, a.title.lower()))


def alive(pid: int) -> bool:
    """Whether the process `pid` is still running (signal 0: only looks)."""
    if sys.platform == "win32":  # there os.kill ends the process: never
        raise OSError("macOS only")
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # someone else's, but there
    return True


# -- Core Audio, through catap: only on a Mac --------------------------------


@functools.cache
def _libproc() -> ctypes.CDLL:
    lib = ctypes.CDLL("/usr/lib/libproc.dylib")
    lib.proc_pidpath.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_uint32]
    lib.proc_pidpath.restype = ctypes.c_int
    return lib


def executable(pid: int) -> str | None:
    """The full path of `pid`'s executable (libproc), or None."""
    buffer = ctypes.create_string_buffer(4096)
    try:
        size = _libproc().proc_pidpath(pid, buffer, len(buffer))
    except OSError:
        return None
    return buffer.value.decode("utf-8", "replace") if size > 0 else None


def _read() -> list[AudioProcess]:
    import catap  # macOS 14.2+ only: imported when first asked

    found = []
    for p in catap.list_audio_processes():
        found.append(
            AudioProcess(
                int(p.audio_object_id),
                int(p.pid),
                p.bundle_id,
                str(p.name),
                bool(p.is_outputting),
                executable(int(p.pid)),
            )
        )
    return found


class _Snapshot:
    """Core Audio's processes, looked at once per SNAPSHOT_SEC however many
    ask (the picker, and each capture once a second)."""

    def __init__(self, read: Callable[[], list[AudioProcess]] = _read) -> None:
        self._read = read
        self._lock = threading.Lock()
        self._at = -SNAPSHOT_SEC
        self._found: list[AudioProcess] = []

    def __call__(self) -> list[AudioProcess]:
        with self._lock:
            now = time.monotonic()
            if now - self._at >= SNAPSHOT_SEC:
                found: list[AudioProcess] = []
                with contextlib.suppress(OSError, RuntimeError):
                    found = self._read()
                self._found, self._at = found, now
            return self._found


audio_processes = _Snapshot()
"""Every process using audio now, as Core Audio reports it."""


class MacAppList:
    """The `AppList` port on macOS."""

    def playing_apps(self) -> list[PlayingApp]:
        return playing_apps(audio_processes(), os.getpid())
