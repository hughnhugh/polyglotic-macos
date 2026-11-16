"""App Translocation (polyglotic-hq 433, decision 0205): `ports.system`'s
`Translocation` for the Mac.

A quarantined app - downloaded, unzipped, and opened anywhere but where
Finder moved it - runs from a read-only copy macOS makes at a random path,
`/private/var/folders/<..>/<..>/T/AppTranslocation/<UUID>/d/Polyglotic.app`.
Velopack 1.2.161 doesn't look for it (its `apply_osx_impl.rs`): it would try
to replace the copy, and the app could never update.

- `translocated`: the copy's path says so, or Security's
  `SecTranslocateIsTranslocatedURL` does.
- `original`: where the app really is (`SecTranslocateCreateOriginalPathForURL`):
  the app moved is that one, never the copy.
- `move_to_applications`: into `/Applications`, or `~/Applications` when the
  learner can't write there (a standard user). A Polyglotic already there
  goes to the Bin, not deleted. Then macOS's quarantine attribute comes off
  the moved app - the learner already chose Open Anyway for it, and with the
  attribute on, macOS would translocate it again even from Applications
  (only a move in Finder clears it).
- `reopen_after`: `open` the moved app once this process has ended, so its
  one copy (`one_copy.FileLock`) is free.

Security's calls load on first use, as `cf`'s do: this module imports, and
its logic is tested, on any OS.
"""

import ctypes
import logging
import os
import re
import shutil
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from functools import cache
from pathlib import Path

from polyglotic_desktop.platform.macos import cf

log = logging.getLogger(__name__)

QUARANTINE = "com.apple.quarantine"
TRANSLOCATED = re.compile(r"^(/private)?/var/folders/.+/AppTranslocation/")
"""The copy's place: under the user's temporary folder (`/var` is a link to
`/private/var`)."""


class MoveFailed(OSError):
    """The app couldn't be moved: says why, for the log."""


def app_bundle(executable: str | Path) -> Path | None:
    """The `.app` a packed app's executable is in (`Contents/MacOS/<name>`),
    or None when it isn't in one (from source)."""
    path = Path(executable)
    contents = path.parent.parent
    if path.parent.name != "MacOS" or contents.name != "Contents":
        return None
    return contents.parent if contents.parent.suffix == ".app" else None


def path_says(bundle: Path) -> bool:
    """Whether `bundle`'s path is a translocated copy's."""
    return bool(TRANSLOCATED.match(bundle.as_posix()))


def translocated(bundle: Path, asked: Callable[[Path], bool] | None = None) -> bool:
    """Whether `bundle` runs translocated: its path says so, or Security does
    (`asked`: `security_says` on a Mac; nothing else asked elsewhere)."""
    if path_says(bundle):
        return True
    if asked is None:
        asked = security_says if sys.platform == "darwin" else lambda _: False
    try:
        return asked(bundle)
    except OSError as problem:
        log.warning("couldn't ask macOS whether the app is translocated: %s", problem)
        return False


def move_to_applications(
    app: Path,
    folders: Sequence[Path],
    trash: Path,
    unquarantine: Callable[[Path], None],
) -> Path:
    """Moves `app` (the real one, not the translocated copy) into the first
    of `folders` it can, and returns where it is now. One already named
    alike there goes to `trash` first, under a name of its own. Raises
    `MoveFailed` when none of them takes it."""
    problems: list[str] = []
    for folder in folders:
        target = folder / app.name
        if target == app:  # already there, put there by something other than Finder
            unquarantine(target)
            return target
        try:
            folder.mkdir(exist_ok=True)
            if not os.access(folder, os.W_OK):
                problems.append(f"{folder}: can't be written")
                continue
            if target.exists() or target.is_symlink():
                trash.mkdir(parents=True, exist_ok=True)
                shutil.move(str(target), str(_free_name(trash, app.name)))
            shutil.move(str(app), str(target))
        except OSError as problem:
            problems.append(f"{folder}: {problem}")
            continue
        unquarantine(target)
        return target
    raise MoveFailed("; ".join(problems) or "nowhere to move it")


def _free_name(folder: Path, name: str) -> Path:
    """`folder/name`, or `folder/<stem> <time><suffix>` if that's taken."""
    place = folder / name
    if not place.exists():
        return place
    stem, suffix = Path(name).stem, Path(name).suffix
    return folder / f"{stem} {time.strftime('%Y-%m-%d %H.%M.%S')}{suffix}"


def unquarantine(app: Path) -> None:
    """macOS's quarantine attribute off everything in `app`, with the
    system's own `xattr`; a file without it is no problem."""
    done = subprocess.run(
        ["/usr/bin/xattr", "-d", "-r", QUARANTINE, str(app)],
        capture_output=True,
        check=False,
    )
    if done.returncode:
        log.info("xattr ended with %d (files without the attribute)", done.returncode)


def reopen_after(pid: int, app: Path) -> None:
    """Opens `app` with `open` once process `pid` has ended: a shell of its
    own, in a session of its own, so it outlives this one."""
    if sys.platform == "win32":
        raise OSError("reopening is macOS's")
    subprocess.Popen(
        [
            "/bin/sh",
            "-c",
            'while /bin/kill -0 "$1" 2>/dev/null; do /bin/sleep 0.2; done; exec /usr/bin/open "$2"',
            "polyglotic-reopen",
            str(pid),
            str(app),
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        close_fds=True,
    )


class MacTranslocation:
    """`Translocation` for the app this process runs (`executable`:
    `sys.executable` unless given)."""

    def __init__(
        self,
        executable: str | Path | None = None,
        home: Path | None = None,
        applications: Path = Path("/Applications"),
    ) -> None:
        self.bundle = app_bundle(
            executable if executable is not None else sys.executable
        )
        self.home = home or Path.home()
        self.applications = applications
        """The system's Applications folder (a test's own in tests)."""

    def translocated(self) -> bool:
        return self.bundle is not None and translocated(self.bundle)

    def move(self) -> Path:
        if self.bundle is None:
            raise MoveFailed("not a packed app")
        real = original(self.bundle)
        if real is None:
            raise MoveFailed("macOS didn't say where the app really is")
        folders = (self.applications, self.home / "Applications")
        try:
            moved = move_to_applications(
                real, folders, self.home / ".Trash", unquarantine
            )
        except MoveFailed as problem:  # for the log: no user name in it
            raise MoveFailed(self.private(str(problem))) from None
        log.info("moved the app to %s", self.private(str(moved.parent)))
        return moved

    def private(self, text: str) -> str:
        """`text` with the home folder (it names the user) said as `~`."""
        return text.replace(str(self.home), "~")

    def reopen(self, app: Path) -> None:
        reopen_after(os.getpid(), app)


# Security's translocation calls (macOS 10.12 and later; in its headers,
# SecTranslocate.h, though not in Apple's documentation).


class _Calls:
    def __init__(self) -> None:
        libs = cf.libraries()
        self.cf, self.security = libs.cf, libs.security
        p, b = ctypes.c_void_p, ctypes.c_bool
        _typed(
            self.cf.CFURLCreateFromFileSystemRepresentation,
            p,
            [p, ctypes.c_char_p, ctypes.c_long, b],
        )
        _typed(
            self.cf.CFURLGetFileSystemRepresentation,
            b,
            [p, b, ctypes.c_char_p, ctypes.c_long],
        )
        _typed(
            self.security.SecTranslocateIsTranslocatedURL, b, [p, ctypes.POINTER(b), p]
        )
        _typed(self.security.SecTranslocateCreateOriginalPathForURL, p, [p, p])
        _typed(self.security.SecTranslocateCreateSecureDirectoryForURL, p, [p, p, p])
        _typed(self.cf.CFErrorCopyDescription, p, [p])

    def url(self, path: Path) -> int:
        raw = os.fsencode(path)
        ref = self.cf.CFURLCreateFromFileSystemRepresentation(None, raw, len(raw), True)
        if not ref:
            raise OSError(f"no URL for {path}")
        return int(ref)

    def path(self, url: int) -> Path:
        buffer = ctypes.create_string_buffer(4096)
        if not self.cf.CFURLGetFileSystemRepresentation(url, True, buffer, len(buffer)):
            raise OSError("no path for a URL")
        return Path(os.fsdecode(buffer.value))


def _typed(call: object, restype: object, argtypes: list[object]) -> None:
    call.restype = restype  # type: ignore[attr-defined]
    call.argtypes = argtypes  # type: ignore[attr-defined]


@cache
def _calls() -> _Calls:
    return _Calls()


def security_says(bundle: Path) -> bool:
    """`SecTranslocateIsTranslocatedURL` on `bundle`."""
    calls = _calls()
    url = calls.url(bundle)
    with cf.owned(url):
        answer = ctypes.c_bool(False)
        if not calls.security.SecTranslocateIsTranslocatedURL(
            url, ctypes.byref(answer), None
        ):
            raise OSError("SecTranslocateIsTranslocatedURL failed")
        return answer.value


def original(bundle: Path) -> Path | None:
    """Where the translocated `bundle` really is, or None if macOS won't say."""
    try:
        calls = _calls()
        url = calls.url(bundle)
        with cf.owned(url):
            real = calls.security.SecTranslocateCreateOriginalPathForURL(url, None)
            if not real:
                return None
            with cf.owned(real):
                return calls.path(real)
    except OSError as problem:
        log.warning("couldn't ask macOS where the app really is: %s", problem)
        return None


def translocate(bundle: Path) -> Path:
    """A translocated copy of the quarantined `bundle`, as macOS makes when
    it's opened (`SecTranslocateCreateSecureDirectoryForURL`) - for the
    check on GitHub's Mac (tests/test_macos_translocation.py)."""
    calls = _calls()
    url = calls.url(bundle)
    with cf.owned(url):
        error = ctypes.c_void_p()
        copy = calls.security.SecTranslocateCreateSecureDirectoryForURL(
            url, None, ctypes.byref(error)
        )
        if not copy:
            raise OSError(f"macOS didn't translocate {bundle}: {_said(calls, error)}")
        with cf.owned(copy):
            return calls.path(copy)


def _said(calls: _Calls, error: ctypes.c_void_p) -> str:
    """What a CFError says, released after."""
    if not error.value:
        return "no error given"
    with cf.owned(error.value):
        described = calls.cf.CFErrorCopyDescription(error.value)
        with cf.owned(described):
            return cf.text(described) or "an error with no description"
