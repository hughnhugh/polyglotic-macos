"""CI's timing steps run alone on the PC both Windows runners share
(polyglotic-hq 312, decision 0105).

    python -m tools.ci_lock alone -- COMMAND...   # no other locked step meanwhile
    python -m tools.ci_lock shared -- COMMAND...  # beside other shared steps, never an alone one
    python -m tools.ci_lock shared --if-present -- COMMAND...  # off CI: only if CI's lock is here

The two Windows runners are two services on the user's PC. A UI lab's
timed steps (its budgets, the start) ran while the other runner ran its
pytest or the other UI lab's four-at-a-time language walk, and the start
went over its budget on load alone (312: 45-55 ms more for each 10 % of
the PC in use). GitHub's `concurrency` can't say this: a group lets one
job in it run at a time and the rest wait, so it would put every job in it
in a line, not just keep the timing apart, and it covers one repository.

So a lock on one file on the PC, a reader-writer lock through Windows'
`LockFileEx` on its first byte: the heavy steps hold it shared, so they
run beside each other as before; a timing step holds it alone, waiting
for the shared ones to finish and keeping new ones waiting until it ends.
A timing step that's waiting already keeps new shared ones waiting
(`WAITING`, the second byte, polyglotic-hq 344): it waits for the shared
steps running when it came, not for every one that starts after it.

- **Never left held:** a lock taken with `LockFileEx` belongs to the open
  file handle; Windows releases it when the handle closes, and closes every
  handle when the process ends - so a job cancelled, timed out or killed
  can't leave the PC locked.
- **Never hangs a job:** a step waits at most `MOST_MINUTES`, or its job's
  own `MINUTES_VARIABLE` (the UI lab's). A step held alone then fails with a line saying the lock was held by other CI steps
  throughout (a re-run is the answer, not a code change); a shared step
  runs unlocked and says so.
- **Never fails a step otherwise:** where the file can't be opened or
  locked, or off Windows, the command runs unlocked and the log says so.
  The step's own exit code is returned.
- **Leaves nothing running:** the step's command, and everything it
  starts, ends with this process (`ending_with_this_process`, polyglotic-hq
  344): a cancelled job can't leave a process holding the runner's folder.
- **Off CI, optional:** `--if-present` locks only if CI's lock file is
  already there (this PC), never making it - so `local_ci.sh` or an
  agent's own UI lab run can keep out of CI's timed steps' way, and runs
  unlocked anywhere else.

It orders the jobs and runs that take it: the user's own work and anything
else on the PC still load it (the start test reads that load: decision
0103).
"""

from __future__ import annotations

import argparse
import contextlib
import os
import subprocess
import sys
import time
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import BinaryIO

LOCK_FILE = (
    Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData"))
    / "polyglotic-ci"
    / "steps.lock"
)
"""Where both runners' accounts can reach it. Each runner's own folder
(`C:\\polyglotic-runner`, `C:\\polyglotic-runner2`) is its account's alone
(the user's account may read both), so neither runner could open the
other's; in ProgramData each account can make files and read the others'
(Windows' default: `Users:(OI)(CI)(RX)`, `(CI)(WD,AD,WEA,WA)`), and reading
is enough to lock. POLYGLOTIC_CI_LOCK names another file (the tests')."""

MOST_MINUTES = 10.0
"""How long a step waits for the lock: about two of the other runner's
pytest runs, or the start test's longest (4 tries, each waiting up to a
minute for a calm PC)."""

MINUTES_VARIABLE = "POLYGLOTIC_CI_LOCK_MINUTES"
"""A job's own wait, in minutes, instead of `MOST_MINUTES` for every step it
locks (`--most-minutes` still wins): the UI lab's, which outlasts a whole
Checks (Windows) run on the PC's other runner (windows.yml, polyglotic-hq
999)."""

POLL_SECONDS = 0.5

STEPS = 0
"""The byte the steps lock: shared, or alone."""

WAITING = 1
"""The byte an alone step locks first, alone, to say it's waiting - and a
shared step passes through, shared, before it locks `STEPS`. Without it,
`LockFileEx` keeps no queue: shared steps that started while an alone one
waited took the lock beside the others, and the alone step could wait out
its 10 minutes behind a chain of them (polyglotic-hq 344: the start with
real windows, 2026-11-14 11:56-12:06 UTC, behind the other runner's 9-minute
pytest and what started after it)."""

GAVE_UP = "gave up"
"""The start of what `held` yields when the wait ran out."""


def lock_file() -> Path:
    named = os.environ.get("POLYGLOTIC_CI_LOCK")
    return Path(named) if named else LOCK_FILE


def _open(path: Path, make: bool) -> BinaryIO | str:
    """The lock file, opened; or why it can't be."""
    if not make and not path.exists():
        return f"unlocked: no {path} here (CI's lock, taken only where it is)"
    try:
        if make:
            path.parent.mkdir(parents=True, exist_ok=True)
        try:
            return path.open("a+b")  # made here if it isn't yet
        except PermissionError:
            return path.open("rb")  # another account's: reading is enough
    except OSError as e:
        return f"unlocked: {path} can't be opened ({e.strerror})"


@contextlib.contextmanager
def held(
    alone: bool,
    path: Path | None = None,
    most_minutes: float = MOST_MINUTES,
    make: bool = True,
) -> Iterator[str]:
    """The lock on `path` held - alone, or shared - while the block runs,
    waiting at most `most_minutes` for it; yields what the log should say:
    how long it waited, why it's unlocked, or that it `GAVE_UP`."""
    path = path or lock_file()
    if sys.platform != "win32":
        yield "unlocked: not Windows"
        return
    import ctypes
    import msvcrt
    from ctypes import wintypes

    class Overlapped(ctypes.Structure):
        _fields_ = [
            ("Internal", ctypes.c_void_p),
            ("InternalHigh", ctypes.c_void_p),
            ("Offset", wintypes.DWORD),
            ("OffsetHigh", wintypes.DWORD),
            ("hEvent", wintypes.HANDLE),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.LockFileEx.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.POINTER(Overlapped),
    ]
    kernel32.LockFileEx.restype = wintypes.BOOL
    kernel32.UnlockFileEx.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.POINTER(Overlapped),
    ]
    opened = _open(path, make)
    if isinstance(opened, str):
        yield opened
        return

    def lock(handle: int, byte: int, exclusive: bool) -> int:
        """0 if `byte` is locked now; else Windows' error (33: held)."""
        # LOCKFILE_FAIL_IMMEDIATELY, asked again until the wait is up, so a
        # step never waits without bound; LOCKFILE_EXCLUSIVE_LOCK if alone
        flags = 0x1 | (0x2 if exclusive else 0)
        if kernel32.LockFileEx(
            handle, flags, 0, 1, 0, ctypes.byref(Overlapped(Offset=byte))
        ):
            return 0
        return ctypes.get_last_error() or 33

    def unlock(handle: int, byte: int) -> None:
        kernel32.UnlockFileEx(handle, 0, 1, 0, ctypes.byref(Overlapped(Offset=byte)))

    with opened as file:
        handle = msvcrt.get_osfhandle(file.fileno())
        started = time.monotonic()
        taken: list[int] = []  # the bytes held, to let go in the end

        def wait_for(byte: int, exclusive: bool) -> str | None:
            """`byte` locked, or why not (failed, or the wait ran out)."""
            while (error := lock(handle, byte, exclusive)) != 0:
                if error != 33:  # not ERROR_LOCK_VIOLATION: can't be locked
                    return f"unlocked: LockFileEx failed ({error})"
                if time.monotonic() - started >= most_minutes * 60:
                    return (
                        f"{GAVE_UP} after {most_minutes:g} min: other CI steps held"
                        f" the PC's lock ({path}) throughout - not this change;"
                        " re-run the job"
                    )
                time.sleep(POLL_SECONDS)
            taken.append(byte)
            return None

        try:
            # an alone step says it's waiting first (WAITING, alone): shared
            # steps that come after it wait for it, not it for them
            why = wait_for(WAITING, exclusive=True) if alone else None
            if why is None and not alone:
                # a shared step passes through WAITING (shared), so it waits
                # while an alone step waits or runs; then lets go of it
                why = wait_for(WAITING, exclusive=False)
            if why is None:
                why = wait_for(STEPS, exclusive=alone)
            if not alone and WAITING in taken:  # through it: never held running
                unlock(handle, WAITING)
                taken.remove(WAITING)
            waited = time.monotonic() - started
            yield (
                why or f"{'alone' if alone else 'shared'}, after {waited:.0f} s waiting"
            )
        finally:  # and Windows releases them anyway with the handle, or the process
            for byte in reversed(taken):
                unlock(handle, byte)


_JOB: list[int] = []
"""The job object `ending_with_this_process` made: its handle is never
closed by hand, only with this process."""


def ending_with_this_process() -> str:
    """Every process this one starts from now on - the step's command and
    whatever that starts, at any depth, whenever it starts it - ends when
    this process ends, however it ends: Windows' job object, "kill on job
    close", with this process in it (polyglotic-hq 344). What the log
    should say.

    A cancelled job left two Pythons behind on 2026-11-14 (started 20:47:57
    UTC by the UI lab's language walk, which went on starting a language
    for each one the cancel ended); they held the runner's work folder, and
    every job on that runner failed at checkout from then on. The runner's
    own cleanup ends the step's process tree and the orphans it finds, but
    each from one look at what's running: a process started after the look
    stays. A job object needs no look - membership is inherited from the
    moment a process starts - and nothing is ended by a name or a path."""
    if sys.platform != "win32":
        return "not Windows"
    import ctypes
    from ctypes import wintypes

    class Basic(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_int64),
            ("PerJobUserTimeLimit", ctypes.c_int64),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class Io(ctypes.Structure):
        _fields_ = [
            (name, ctypes.c_uint64)
            for name in ("Reads", "Writes", "Others", "Read", "Written", "Other")
        ]

    class Extended(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", Basic),
            ("IoInfo", Io),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel32.SetInformationJobObject.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
    ]
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    job = kernel32.CreateJobObjectW(None, None)  # its handle isn't inherited
    if not job:
        return f"not tied to it: CreateJobObject failed ({ctypes.get_last_error()})"
    limits = Extended()
    limits.BasicLimitInformation.LimitFlags = 0x2000  # KILL_ON_JOB_CLOSE
    extended_limit_information = 9
    if not kernel32.SetInformationJobObject(
        job, extended_limit_information, ctypes.byref(limits), ctypes.sizeof(limits)
    ) or not kernel32.AssignProcessToJobObject(job, kernel32.GetCurrentProcess()):
        return f"not tied to it: the job object failed ({ctypes.get_last_error()})"
    _JOB.append(job)
    return "end with it"


def main(argv: Sequence[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    split = argv.index("--") if "--" in argv else len(argv)
    own, command = argv[:split], argv[split + 1 :]
    parser = argparse.ArgumentParser(
        description=(__doc__ or "").split("\n\n")[0],
        usage="python -m tools.ci_lock {alone,shared} [options] -- COMMAND...",
    )
    parser.add_argument("how", choices=["alone", "shared"])
    parser.add_argument(
        "--if-present",
        action="store_true",
        help="lock only if CI's lock file is already here (off CI: optional)",
    )
    parser.add_argument(
        "--most-minutes",
        type=float,
        default=float(os.environ.get(MINUTES_VARIABLE) or MOST_MINUTES),
        help=f"how long to wait for the lock (default ${MINUTES_VARIABLE}, else "
        f"{MOST_MINUTES:g})",
    )
    args = parser.parse_args(own)
    if not command:
        parser.error("no command to run (after --)")
    alone = args.how == "alone"
    with held(alone, most_minutes=args.most_minutes, make=not args.if_present) as said:
        print(f"ci_lock: {said}", flush=True)
        print(f"ci_lock: the step's processes {ending_with_this_process()}", flush=True)
        if said.startswith(GAVE_UP) and alone:
            return 1  # a timed step on a PC CI's other steps never let go of
        return subprocess.run(command, check=False).returncode


if __name__ == "__main__":
    sys.exit(main())
