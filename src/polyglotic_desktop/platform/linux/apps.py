"""The apps with sound on Linux, for the app picker (the `AppList` port), and
the streams a capture of one app records (polyglotic-hq 546, 547, 561).

The sound server lists every stream an app plays (a sink input), with the
app it belongs to (`pulse.PlayingStream`): its executable's name, its own
name and its process, read from the stream or else from its client (a
native PipeWire player puts them only on its client - 547). An app often
plays several streams at once (a browser's tabs, a call's ringing and
voices), so streams are grouped by **the app they belong to**
(`app_key`): its executable's name - the same in every language - or,
for a program under Wine (a Windows game through Proton), the name the
program gives itself, since every such program's executable is Wine's
own. Each group is one entry, named by that key, and captured as the sum
of its streams (`capture.AppCapture`), which follows streams as they come
and go.

An app's stream exists only while it plays or holds its sound open, so an
app that has stopped altogether is no longer listed; a paused one
(`corked`) is listed as not playing. Polyglotic's own streams are never an
app to caption (polyglotic-hq 368): this process's, and any copy of the
app by its executable's name. Nor are the system voice's (591):
speech-dispatcher, which the app starts to say a word, holds a stream for
each of its voices ("speech-dispatcher-espeak-ng", and "-dummy" never
paused) while it runs.
"""

from __future__ import annotations

import contextlib
import os
import sys
import threading
import time
from collections.abc import Callable, Iterable
from pathlib import Path

from polyglotic_desktop.platform.linux import pulse
from polyglotic_desktop.platform.linux.categories import (
    category_of,
    known_name,
    shown_name,
)
from polyglotic_desktop.ports.capture import PlayingApp

APP_EXECUTABLE = "polyglotic"
"""The packed app's executable (`tools/package/build.py`'s LINUX), any
copy of it - the installed AppImage and a preview alike - lower-cased."""
WINE = frozenset({"wine", "wine64", "wine-preloader", "wine64-preloader", "wineserver"})
"""Wine's own executables: a program under them is known by its own name."""
SNAPSHOT_SEC = 0.5
"""How long one look at the sound server's streams serves every asker."""
LIST_CONNECT_SEC = 1.0
"""How long the picker waits for the sound server: it asks on the
interface's thread, so a sound server that doesn't answer lists no apps
rather than holding the window."""


def app_key(stream: pulse.PlayingStream) -> str | None:
    """The app a stream belongs to: its executable's name; under Wine, the
    program's own name; else its own name. None if it gives none."""
    binary = stream.binary
    if binary and binary.lower() not in WINE:
        return binary
    return stream.app_name or binary


def grouped(
    streams: Iterable[pulse.PlayingStream],
) -> dict[str, list[pulse.PlayingStream]]:
    """The streams, by the app they belong to (`app_key`); a stream that
    names no app is left out."""
    groups: dict[str, list[pulse.PlayingStream]] = {}
    for stream in streams:
        key = app_key(stream)
        if key:
            groups.setdefault(key, []).append(stream)
    return groups


def is_polyglotic(key: str, members: Iterable[pulse.PlayingStream], this: int) -> bool:
    """Whether an app is Polyglotic: this process (from source, Python), or
    any copy of it by its executable's name."""
    return key.lower() == APP_EXECUTABLE or any(s.process_id == this for s in members)


def is_system_voice(members: Iterable[pulse.PlayingStream]) -> bool:
    """Whether an app is speech-dispatcher's: its voices' streams, named
    "speech-dispatcher-<module>" by speech-dispatcher itself, or played by
    a module of its own (`sd_*`) - as GitHub's Ubuntu 24.04 runner showed
    them (591's probe)."""
    return all(
        (s.app_name or "").startswith("speech-dispatcher")
        or (s.binary or "").startswith("sd_")
        for s in members
    )


def process_of(members: Iterable[pulse.PlayingStream]) -> int:
    """The process that stands for an app: the oldest named (the lowest
    number: helpers start after), else 0."""
    found = [s.process_id for s in members if s.process_id]
    return min(found) if found else 0


def executable(process_id: int) -> str | None:
    """The full path of the process's executable (`/proc`), or None."""
    if not process_id:
        return None
    try:
        return os.readlink(f"/proc/{process_id}/exe")
    except OSError:
        return None


def ended(folder: Path) -> bool:
    """Whether the process in `folder` (`/proc/<pid>`) has ended: gone, or a
    zombie its parent hasn't collected yet (state Z, after the name's ")")."""
    try:
        stat = (folder / "stat").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return True
    return stat.rpartition(")")[2].split()[:1] == ["Z"]


def alive(process_id: int, proc: Path = Path("/proc")) -> bool:
    """Whether the process is still running: in `/proc`, and not a zombie
    (never a signal - on Windows `os.kill` ends a process: polyglotic-hq
    411)."""
    if proc == Path("/proc") and not sys.platform.startswith("linux"):
        raise OSError("Linux only")
    return bool(process_id) and not ended(proc / str(process_id))


COMM_CHARS = 15
"""How much of a process's name the kernel keeps (`/proc/<pid>/comm`)."""


def running(key: str, proc: Path = Path("/proc")) -> bool:
    """Whether any process of the app `key` runs: one whose executable has
    that name, or whose own name (Wine's programs name themselves) is it.
    An app's process can come and go while the app stays open - a browser's
    audio process, a player started again for each file - so one app's
    capture ends only once none is left."""
    wanted = key.lower()
    for folder in proc.glob("[0-9]*"):
        try:
            name = (folder / "comm").read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        try:
            mine = name.strip().lower() == wanted[:COMM_CHARS] or (
                os.path.basename(os.readlink(folder / "exe")).lower() == wanted
            )
        except OSError:
            continue
        if mine and not ended(folder):
            return True
    return False


def playing_apps(
    streams: Iterable[pulse.PlayingStream],
    this: int,
    path_of: Callable[[int], str | None] = executable,
) -> list[PlayingApp]:
    """The apps with sound, one entry per app (`grouped`), playing first:
    each named by its key, shown by the known-apps list's name, else the
    name it gives itself, else its key."""
    apps = []
    for key, members in grouped(streams).items():
        if is_polyglotic(key, members, this):
            continue  # its own sounds: never an app to caption (368)
        if is_system_voice(members):
            continue  # the voice that says a looked-up word (591)
        process = process_of(members)
        own_name = shown_name(key) or next(
            (s.app_name for s in members if s.app_name), key
        )
        apps.append(
            PlayingApp(
                process,
                key,
                any(not s.corked for s in members),
                category_of(key, path_of(process)),
                known_name(key),
                own_name,
            )
        )
    return sorted(apps, key=lambda a: (not a.playing, a.title.lower()))


def _read() -> list[pulse.PlayingStream]:
    server = pulse.PulseServer(wait=LIST_CONNECT_SEC)
    try:
        return server.streams()
    finally:
        server.close()


class _Snapshot:
    """The sound server's streams, looked at once per SNAPSHOT_SEC however
    many ask; none while there's no sound server."""

    def __init__(self, read: Callable[[], list[pulse.PlayingStream]] = _read) -> None:
        self._read = read
        self._lock = threading.Lock()
        self._at = -SNAPSHOT_SEC
        self._found: list[pulse.PlayingStream] = []

    def __call__(self) -> list[pulse.PlayingStream]:
        with self._lock:
            now = time.monotonic()
            if now - self._at >= SNAPSHOT_SEC:
                found: list[pulse.PlayingStream] = []
                with contextlib.suppress(OSError):
                    found = self._read()
                self._found, self._at = found, now
            return self._found


playing_streams = _Snapshot()
"""Every stream apps play now, as the sound server reports them."""


class LinuxAppList:
    """The `AppList` port on Linux."""

    def playing_apps(self) -> list[PlayingApp]:
        return playing_apps(playing_streams(), os.getpid())
