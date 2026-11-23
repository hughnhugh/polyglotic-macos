"""Relaunching the app into a newly chosen interface language (polyglotic-hq 658).

A change to the interface language needs a fresh process so Qt loads the new
language's translations before any window is built (decision 0034). Each OS
restarts from the binary the learner launched:

- **Windows:** the installed app's own executable through Velopack's install
  (`current\\Polyglotic.exe`, or a packed build's `Polyglotic.exe`), or
  `sys.executable -m polyglotic_desktop.main` from source;
- **Linux:** `$APPIMAGE` when running as an AppImage, else the packed
  executable or `sys.executable -m polyglotic_desktop.main` from source;
- **macOS:** `open -n <Polyglotic.app>` for a packed app bundle, else
  `sys.executable -m polyglotic_desktop.main` from source.

Flags that would hide the window (`--in-tray`) or only message an existing
copy (`--lock`, `--pause`, `--hide`, `--veloapp-*`) are stripped; data folder,
server, dictionaries and test flags pass through so rehearsal installs and
private-desktop runs relaunch against the same environment.
"""

from __future__ import annotations

import logging
import os
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import PurePosixPath
from typing import Any

from polyglotic_desktop.ports.startup import IN_TRAY

log = logging.getLogger(__name__)

VELOPACK_HOOK = "--veloapp-"
"""Velopack installer hooks: never forwarded on relaunch."""
STRIP_FLAGS = frozenset({IN_TRAY, "--lock", "--pause", "--hide"})
"""One-shot or background-only flags dropped when relaunching interactively."""


def passthrough_args(argv: Sequence[str]) -> list[str]:
    """Command-line arguments from `argv` safe to pass to the relaunched copy."""
    kept: list[str] = []
    skip_next = False
    for arg in argv:
        if skip_next:
            skip_next = False
            if not arg.startswith("-"):
                continue
        if arg in STRIP_FLAGS:
            continue
        if arg.startswith(VELOPACK_HOOK):
            if "=" not in arg:
                skip_next = True
            continue
        kept.append(arg)
    return kept


def _mac_app_bundle(executable: str) -> PurePosixPath | None:
    """The `.app` bundle containing `Contents/MacOS/<exe>`, or None."""
    path = PurePosixPath(executable)
    contents = path.parent.parent
    if path.parent.name != "MacOS" or contents.name != "Contents":
        return None
    return contents.parent if contents.parent.suffix == ".app" else None


def relaunch_command(
    argv: Sequence[str] = (),
    *,
    frozen: bool | None = None,
    executable: str | None = None,
    system: str = sys.platform,
    environ: Mapping[str, str] | None = None,
) -> list[str]:
    """The command that starts a fresh copy of this app on `system`."""
    env = os.environ if environ is None else environ
    exe = sys.executable if executable is None else executable
    is_frozen = bool(getattr(sys, "frozen", False)) if frozen is None else frozen
    extra = passthrough_args(argv)
    if system.startswith("linux"):
        appimage = env.get("APPIMAGE", "")
        if appimage:
            return [appimage, *extra]
    if system == "darwin" and is_frozen:
        bundle = _mac_app_bundle(exe)
        if bundle is not None:
            return (
                ["/usr/bin/open", "-n", str(bundle), "--args", *extra]
                if extra
                else ["/usr/bin/open", "-n", str(bundle)]
            )
    if is_frozen:
        return [exe, *extra]
    return [exe, "-m", "polyglotic_desktop.main", *extra]


def relaunch(
    argv: Sequence[str] = (),
    *,
    frozen: bool | None = None,
    executable: str | None = None,
    system: str = sys.platform,
    environ: Mapping[str, str] | None = None,
    popen: Callable[..., Any] | None = None,
) -> bool:
    """Starts a fresh copy of Polyglotic and returns True if it launched.

    Call only after saving settings, closing the local socket (`SecondStarts`)
    and releasing the single-instance lock (`CopyLock.release`) so the new copy
    can take the lock immediately.
    """
    import subprocess

    is_frozen = bool(getattr(sys, "frozen", False)) if frozen is None else frozen
    command = relaunch_command(
        argv,
        frozen=is_frozen,
        executable=executable,
        system=system,
        environ=environ,
    )
    starter = subprocess.Popen if popen is None else popen
    kwargs: dict[str, Any] = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "close_fds": True,
    }
    if system == "win32":
        if not is_frozen:
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    else:
        kwargs["start_new_session"] = True
    try:
        starter(command, **kwargs)
    except OSError as error:
        log.warning("couldn't relaunch Polyglotic (%s)", type(error).__name__)
        return False
    log.info(
        "relaunching Polyglotic (%s)",
        "installed" if is_frozen else "source",
    )
    return True
