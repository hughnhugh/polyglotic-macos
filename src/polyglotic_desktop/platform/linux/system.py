"""Which Linux this is, where the user's own files live, how long ago the
process was launched, and the box an app shows when it can't start (decision 0038: `ports/system.py`'s pieces, and
protocol.md's `os`) - the Mac's `platform/macos/system.py` for Linux
(polyglotic-hq 546, 550).

The folders follow the XDG base directories: the learner's files in
`$XDG_DATA_HOME/Polyglotic` (`~/.local/share/Polyglotic`), with the log
and the outbox, as on the other two; what can be fetched again in
`$XDG_CACHE_HOME`; the one-copy lock in `$XDG_RUNTIME_DIR`.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
import time
from collections.abc import Mapping, MutableMapping
from pathlib import Path

APP_FOLDER = "Polyglotic"
"""The app ID (ENGINEERING.md, "Releases"), as the other OSes' folders."""

_IMPORTED = time.monotonic()


def _base(
    variable: str, fallback: str, environ: Mapping[str, str], home: Path | None
) -> Path:
    """An XDG base directory: the variable if it holds an absolute path (the
    specification ignores a relative one), else its fallback under home."""
    given = environ.get(variable, "")
    if given and Path(given).is_absolute():
        return Path(given)
    return (home or Path.home()) / fallback


def data_folder(
    environ: Mapping[str, str] | None = None, home: Path | None = None
) -> Path:
    """The user's own files - settings, learning data, the outbox, the log -
    in `$XDG_DATA_HOME/Polyglotic`, by default `~/.local/share/Polyglotic`:
    replacing or deleting the AppImage leaves them alone."""
    env = os.environ if environ is None else environ
    return _base("XDG_DATA_HOME", ".local/share", env, home) / APP_FOLDER


def cache_folder(
    environ: Mapping[str, str] | None = None, home: Path | None = None
) -> Path:
    """What can be fetched again (the verified update feed, its packages):
    `$XDG_CACHE_HOME/Polyglotic`, by default `~/.cache/Polyglotic`."""
    env = os.environ if environ is None else environ
    return _base("XDG_CACHE_HOME", ".cache", env, home) / APP_FOLDER


def runtime_folder(
    environ: Mapping[str, str] | None = None, home: Path | None = None
) -> Path:
    """Files for this sign-in only (the one-copy lock): `$XDG_RUNTIME_DIR/
    Polyglotic` - the user's own, emptied at sign-out - else, where a
    session has none, the data folder's `locks`."""
    env = os.environ if environ is None else environ
    given = env.get("XDG_RUNTIME_DIR", "")
    if given and Path(given).is_absolute():
        return Path(given) / APP_FOLDER
    return data_folder(env, home) / "locks"


def platform_kind(root: Path = Path("/")) -> str:
    """Tremplin mounts the milestone in the guest. Older images also carry
    the ChromeOS apt source and bind-mounted guest tools. Only test presence."""
    if (root / "dev/.cros_milestone").is_file() or (
        (root / "etc/apt/sources.list.d/cros.list").is_file()
        and (root / "opt/google/cros-containers").is_dir()
    ):
        return "crostini"
    return "linux"


def os_name(release: str | None = None) -> str:
    """`linux-<major>` (protocol.md's `os`: `linux-6`, as the server's own
    smoke test says hello), from the kernel's release - `platform.release()`
    (`6.8.0-49-generic`) unless one is given. The distribution and desktop
    go in `os_version`, which only feedback carries."""
    found = release if release is not None else platform.release()
    major = found.split(".", 1)[0]
    if not major.isdigit() or not 1 <= int(major) <= 999:
        raise OSError(f"the kernel's version can't be read ({found!r})")
    return f"linux-{int(major)}"


def os_release(path: Path = Path("/etc/os-release")) -> dict[str, str]:
    """`/etc/os-release`'s fields (`ID`, `VERSION_ID`...), quotes taken
    off; `/usr/lib/os-release` if the first isn't there; empty if neither."""
    for each in (path, Path("/usr/lib/os-release")):
        try:
            text = each.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        fields: dict[str, str] = {}
        for line in text.splitlines():
            key, sep, value = line.partition("=")
            if sep and key.strip() and not key.startswith("#"):
                fields[key.strip()] = value.strip().strip("\"'")
        return fields
    return {}


def os_version(
    fields: Mapping[str, str] | None = None, environ: Mapping[str, str] | None = None
) -> str:
    """The distribution, its version, the desktop and the session, as
    feedback carries them (`ubuntu 24.04 GNOME wayland`): every Linux
    problem report needs all four."""
    found = os_release() if fields is None else fields
    env = os.environ if environ is None else environ
    parts = [
        found.get("ID", "linux"),
        found.get("VERSION_ID", ""),
        env.get("XDG_CURRENT_DESKTOP", "").split(":", 1)[0],
        env.get("XDG_SESSION_TYPE", ""),
    ]
    return " ".join(part for part in parts if part)


def wayland_session(environ: Mapping[str, str]) -> bool:
    """Whether the desktop is a Wayland session (the app's windows then go
    through XWayland)."""
    return environ.get("XDG_SESSION_TYPE", "") == "wayland" or bool(
        environ.get("WAYLAND_DISPLAY")
    )


def desktop_names(environ: Mapping[str, str]) -> list[str]:
    """`XDG_CURRENT_DESKTOP`'s names, upper case ("UBUNTU", "GNOME")."""
    return [n.upper() for n in environ.get("XDG_CURRENT_DESKTOP", "").split(":") if n]


def seconds_since_launch(
    stat: str | None = None, uptime: str | None = None, ticks: int | None = None
) -> float:
    """Seconds since Linux started this process (`/proc/self/stat`'s start
    time against `/proc/uptime`); since this module was imported if Linux
    won't say - the interpreter's own start then isn't counted."""
    try:
        stat = stat if stat is not None else Path("/proc/self/stat").read_text()
        uptime = uptime if uptime is not None else Path("/proc/uptime").read_text()
        if ticks is None:
            if sys.platform == "win32":  # never asked there: for the type check
                raise OSError("no /proc on Windows")
            ticks = os.sysconf("SC_CLK_TCK")
        started = int(stat.rsplit(")", 1)[1].split()[19]) / ticks
        return max(0.0, float(uptime.split()[0]) - started)
    except (OSError, ValueError, IndexError):
        return time.monotonic() - _IMPORTED


ERROR_BOXES = (
    ("zenity", "--error", "--title={title}", "--text={text}", "--no-markup"),
    ("kdialog", "--title", "{title}", "--error", "{text}"),
    ("xmessage", "-center", "{title}: {text}"),
)
"""The desktops' own boxes, each tried in turn: GNOME's, KDE's, X's."""


def outside_environment(environ: Mapping[str, str] | None = None) -> dict[str, str]:
    """The environment for a program of the desktop's started from the
    packed app: the library path as it was before the app's own loader set
    it to the app's folder (PyInstaller keeps it in `LD_LIBRARY_PATH_ORIG`),
    so that program loads the system's libraries, not the app's."""
    env = dict(os.environ if environ is None else environ)
    if "LD_LIBRARY_PATH_ORIG" in env:
        env["LD_LIBRARY_PATH"] = env.pop("LD_LIBRARY_PATH_ORIG")
    elif getattr(sys, "frozen", False):
        env.pop("LD_LIBRARY_PATH", None)
    for name in loader_variables(env):
        del env[name]
    return env


LIBRARY_PATHS = ("LD_LIBRARY_PATH", "LD_LIBRARY_PATH_ORIG")
LOADER = "_PYI_"
"""PyInstaller's loader's own variables (`_PYI_APPLICATION_HOME_DIR`,
`_PYI_ARCHIVE_FILE`, `_PYI_PARENT_PROCESS_LEVEL`...): what it tells a
process it starts of itself. A program the app starts - Velopack's
updater, which starts the new AppImage after an update, above all - must
not have them, or a packed app it starts takes itself for this one's
child, in a folder that's gone (polyglotic-hq 561, 574; PyInstaller's
`PYINSTALLER_RESET_ENVIRONMENT` does the same from the child's side)."""


def loader_variables(environ: Mapping[str, str] | None = None) -> list[str]:
    """PyInstaller's loader's variables in `environ` (the process's own by
    default): none, once the start has left the packed environment."""
    return sorted(
        n for n in (os.environ if environ is None else environ) if n.startswith(LOADER)
    )


def leave_packed_environment(environ: MutableMapping[str, str] | None = None) -> None:
    """The process's own environment made the outside one
    (`outside_environment`), for every program the packed app starts from
    now on: the browser a link opens (Qt starts it through `xdg-open`, with
    this environment), the desktop's own boxes. With the app's folder on
    the library path, the browser loaded the app's copies of the libraries
    it shares names with (polyglotic-hq 550, 561). PyInstaller's loader's own
    variables go too (`LOADER`, 574). The app itself keeps its own
    libraries: the dynamic loader read the path once, as the process
    started."""
    env = os.environ if environ is None else environ
    outside = outside_environment(env)
    for name in (*LIBRARY_PATHS, *loader_variables(env)):
        if name in outside:
            env[name] = outside[name]
        else:
            env.pop(name, None)


def show_error(title: str, text: str) -> None:
    """`ErrorBox`: the desktop's own box (no Qt: the app couldn't start),
    until it's closed - zenity on GNOME, kdialog on KDE, xmessage on bare
    X - and always on the terminal too, which may be all there is."""
    print(f"{title}: {text}", file=sys.stderr)
    for program, *arguments in ERROR_BOXES:
        found = shutil.which(program)
        if found is None:
            continue
        given = [a.format(title=title, text=text) for a in arguments]
        try:
            subprocess.run(
                [found, *given], check=False, timeout=3600, env=outside_environment()
            )
        except (OSError, subprocess.SubprocessError):
            continue
        return
