"""The packed app as a learner's Mac meets it, on GitHub's Mac (polyglotic-hq
523; 512's lesson): the macOS job's `learner` part, after `pack`. GitHub's
Mac has what a learner's doesn't - python.org's Python, Homebrew, Xcode and
the developer tools - and 512's sign-in bug hid behind python.org's own root
list. So, with those moved aside for the whole part:

- hidden: python.org's Python, Homebrew and the developer tools moved aside
  (`HIDDEN`), and put back at the end, or by `--show` in a step that always
  runs. One the checks themselves run on (this Python, uv) stays, said.
- linkage: every Mach-O file in the app loads only from inside the app or
  macOS itself (`/System`, `/usr/lib`): nothing from Homebrew, python.org,
  `/usr/local`, a developer's folder or uv's Pythons.
- downloaded: the zip a learner downloads (the release's portable zip, or
  the app zipped as the release does), put in ~/Downloads with Safari's
  quarantine attribute, and opened as Finder's Archive Utility opens it.
  The app that comes out must still verify (`codesign --deep --strict`)
  with the built app's designated requirement - the one macOS keeps a
  learner's permissions and keychain item under - and Gatekeeper's verdict
  (`spctl -a -vv`) is kept: rejected for a self-signed app is expected
  (no Developer ID yet); a broken seal is a fail.
- opened_from_downloads: the app opened from Downloads with `open`, as a
  double-click does. Gatekeeper refuses it first (not notarised: its dialog
  is closed, as a learner closes it), so it's marked approved as Open
  Anyway marks it and opened again. It must then run from macOS's
  translocated copy, offer to move to Applications (its log), and - Return
  pressed, Move being the default - move there, lose the quarantine
  attribute and open again from Applications (433, decision 0205). If
  Gatekeeper still won't let a script open it, that's unknown, said.
- fresh_account: a new macOS user made with `sysadminctl`; as that user,
  with an empty home, the installed app's `--check-install` (offscreen)
  and `--check-tls` (live's /health and sign-in path) must pass. The user
  is deleted at the end; its password is random, never printed or kept.

    uv run --no-sync python -m tools.macos_learner_checks OUT --app dist/Polyglotic.app [--zip Z]
    uv run --no-sync python -m tools.macos_learner_checks OUT --hide   # only move them aside
    uv run --no-sync python -m tools.macos_learner_checks OUT --show   # put back what was hidden
    uv run --no-sync python -m tools.macos_learner_checks OUT --dry-run  # any OS: the plan

Each check prints a pass, fail or unknown line and goes in OUT/learner.json;
the job fails only on a fail - unknown is what the machine didn't let us
see. GitHub's Mac only: it moves system folders aside, adds a user and
opens the app; never run it on a person's Mac.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import secrets
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

PASS, FAIL, UNKNOWN = "pass", "fail", "unknown"
APP_NAME = "Polyglotic.app"
EXECUTABLE = "Contents/MacOS/Polyglotic"
HIDDEN = (
    "/Library/Frameworks/Python.framework",  # python.org's Python (512)
    "/opt/homebrew",  # Homebrew, Apple silicon
    "/usr/local/Homebrew",  # Homebrew, Intel
    "/usr/local/Cellar",
    "/usr/local/opt",
    "/usr/local/lib",
    "/usr/local/bin",  # python.org's and Homebrew's links among the rest
    "/Library/Developer/CommandLineTools",  # the developer tools
    "/Applications/Xcode*.app",  # and Xcode, every version the image has
)
"""What GitHub's Mac has that a learner's Mac needn't: moved aside."""
ASIDE = ".hidden-523"
"""What a hidden folder's name gets while it's aside."""
SYSTEM = ("/System/", "/usr/lib/")
"""Where a packed app may load from outside itself: macOS's own."""
SAFARI = "0083"
"""Safari's quarantine flags on a download (a learner's browser)."""
APPROVED = "00c3"
"""The same with the user-approved flag (0x40) that Open Anyway adds."""
OPEN_SEC = 25
"""How long a double-click's start may take before it's said not to have."""
LEARNER = "polyglotic-learner"
"""The fresh account's short name."""
OFFERED = "offering to move to Applications"
"""What the app logs when it offers the move (main.moved_to_applications)."""


@dataclass
class Result:
    check: str
    outcome: str
    said: str
    facts: dict[str, Any] = field(default_factory=dict)


def plan() -> list[str]:
    return [
        f"hidden: {', '.join(HIDDEN)} moved aside (sudo mv ... {ASIDE})",
        (
            "linkage: every Mach-O in the app loads from @rpath/@loader_path/"
            f"@executable_path or {' '.join(SYSTEM)}"
        ),
        (
            "downloaded: the zip in ~/Downloads with Safari's quarantine; opened by"
            " Archive Utility; codesign --verify --deep --strict; the designated"
            " requirement the built app's; spctl -a -vv kept"
        ),
        (
            "opened_from_downloads: open; translocated; the move offered (the log);"
            " Return; in /Applications without quarantine; running from there"
        ),
        (
            f"fresh_account: sysadminctl -addUser {LEARNER}; --check-install and"
            " --check-tls as that user; the user deleted"
        ),
    ]


# -- Mach-O: what a binary loads ------------------------------------------------------

_LOADS = {0xC, 0x80000018, 0x8000001F, 0x20, 0x80000023}
"""LC_LOAD_DYLIB, LC_LOAD_WEAK_DYLIB, LC_REEXPORT_DYLIB, LC_LAZY_LOAD_DYLIB,
LC_LOAD_UPWARD_DYLIB: each names a library by a string at its offset."""
_RPATH = 0x8000001C
_THIN = {b"\xcf\xfa\xed\xfe": "<", b"\xfe\xed\xfa\xcf": ">"}  # 64-bit, by byte order
_FAT = {b"\xca\xfe\xba\xbe": 20, b"\xca\xfe\xba\xbf": 32}  # fat_arch, fat_arch_64


def _string_at(data: bytes, start: int, end: int) -> str:
    raw = data[start:end]
    return raw.split(b"\0", 1)[0].decode("utf-8", "replace")


def _thin_loads(data: bytes, base: int) -> tuple[list[str], list[str]]:
    order = _THIN[data[base : base + 4]]
    ncmds = struct.unpack_from(order + "I", data, base + 16)[0]
    at = base + 32  # mach_header_64
    libraries: list[str] = []
    rpaths: list[str] = []
    for _ in range(ncmds):
        cmd, size = struct.unpack_from(order + "II", data, at)
        if cmd in _LOADS or cmd == _RPATH:
            offset = struct.unpack_from(order + "I", data, at + 8)[0]
            name = _string_at(data, at + offset, at + size)
            (rpaths if cmd == _RPATH else libraries).append(name)
        at += max(size, 8)
    return libraries, rpaths


def loads(data: bytes) -> tuple[list[str], list[str]] | None:
    """What a Mach-O file loads - its libraries and its rpaths, every
    architecture of a fat one - or None when `data` isn't one (64-bit only:
    every Mac build here is)."""
    magic = data[:4]
    if magic in _THIN:
        return _thin_loads(data, 0)
    if magic in _FAT:
        count = struct.unpack_from(">I", data, 4)[0]
        if count > 16:  # Java's class files share 0xcafebabe
            return None
        libraries: list[str] = []
        rpaths: list[str] = []
        for n in range(count):
            entry = 8 + n * _FAT[magic]
            if _FAT[magic] == 20:
                offset = struct.unpack_from(">I", data, entry + 8)[0]
            else:
                offset = struct.unpack_from(">Q", data, entry + 8)[0]
            if data[offset : offset + 4] in _THIN:
                found, paths = _thin_loads(data, offset)
                libraries += [x for x in found if x not in libraries]
                rpaths += [x for x in paths if x not in rpaths]
        return libraries, rpaths
    return None


def outside(reference: str) -> bool:
    """Whether a library or rpath points outside the app and outside
    macOS's own: what a learner's Mac may not have."""
    if reference.startswith("@"):
        return False
    return not reference.startswith(SYSTEM)


def linkage_of(app: Path) -> dict[str, list[str]]:
    """Each Mach-O file in `app` (relative path) with what it loads from
    outside the app and macOS - empty when all is well."""
    found: dict[str, list[str]] = {}
    for path in sorted(app.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        with path.open("rb") as file:
            head = file.read(4)
            if head not in _THIN and head not in _FAT:
                continue
            data = head + file.read()
        loaded = loads(data)
        if loaded is None:
            continue
        libraries, rpaths = loaded
        bad = [x for x in [*libraries, *rpaths] if outside(x)]
        if bad:
            found[str(path.relative_to(app))] = bad
    return found


# -- Gatekeeper's verdict ---------------------------------------------------------------

BROKEN = (
    "sealed resource is missing or invalid",
    "invalid signature",
    "code object is not signed",
    "has been modified",
    "resource envelope is obsolete",
    "nested code is modified or invalid",
)
"""What spctl or codesign says when the download path broke the signature."""


def gatekeeper_said(text: str) -> str:
    """spctl's verdict on the downloaded app: "accepted", "rejected" (the
    signature whole, only not from a Developer ID or notarised - expected
    until the app is), or "broken"."""
    lowered = text.lower()
    if any(words in lowered for words in BROKEN):
        return "broken"
    if "accepted" in lowered:
        return "accepted"
    return "rejected"


def quarantine_value(flags: str = SAFARI, at: float | None = None) -> str:
    """The `com.apple.quarantine` value a browser writes on a download:
    flags;hex time;agent;UUID."""
    stamp = int(time.time() if at is None else at)
    return f"{flags};{stamp:08x};Safari;{str(uuid.uuid4()).upper()}"


# -- on the Mac -------------------------------------------------------------------------


def sh(command: list[str], seconds: float = 120, **kw: Any) -> dict[str, Any]:
    try:
        done = subprocess.run(
            command, capture_output=True, text=True, timeout=seconds, check=False, **kw
        )
        return {"code": done.returncode, "out": (done.stdout + done.stderr)[-3000:]}
    except subprocess.TimeoutExpired:
        return {"code": None, "out": f"timed out after {seconds:.0f} s"}
    except OSError as e:
        return {"code": None, "out": f"{type(e).__name__}: {e}"}


def kept_by_the_checks() -> list[str]:
    """What the checks themselves run on - this Python and uv - which can't
    be moved aside under them."""
    kept = [os.path.realpath(sys.base_prefix), os.path.realpath(sys.executable)]
    uv = shutil.which("uv")
    if uv:
        kept.append(os.path.realpath(uv))
    return kept


def hideable(place: str, kept: list[str]) -> bool:
    """Whether `place` (a real path) holds none of `kept`."""
    return not any(k == place or k.startswith(place.rstrip("/") + "/") for k in kept)


def requirement(app: Path) -> str:
    said = sh(["codesign", "--display", "--requirements", "-", str(app)])["out"]
    lines = [x for x in said.splitlines() if x.startswith("designated =>")]
    return lines[-1] if lines else said.strip()[-300:]


def pids_of(app: Path) -> list[int]:
    """The processes running `app`'s executable (or its translocated copy's,
    when `app` is only its name)."""
    found = sh(["pgrep", "-f", f"{APP_NAME}/{EXECUTABLE}"])["out"]
    pids = [int(x) for x in found.split() if x.isdigit()]
    return [p for p in pids if p != os.getpid()]


def command_of(pid: int) -> str:
    return sh(["ps", "-o", "command=", "-p", str(pid)])["out"].strip()


def end(pids: list[int]) -> None:
    """Our own app's processes, by PID (on GitHub's Mac)."""
    for pid in pids:
        sh(["kill", str(pid)])
    time.sleep(2)
    for pid in pids:
        sh(["kill", "-9", str(pid)])


class Learner:
    def __init__(self, out: Path, app: Path | None, zipped: Path | None) -> None:
        self.out = out
        self.app = app
        self.zipped = zipped
        self.results: list[Result] = []
        self.facts: dict[str, Any] = {}
        self.unpacked: Path | None = None
        self.made: Path | None = None
        self.installed: Path | None = None

    def add(self, check: str, outcome: str, said: str, **facts: Any) -> None:
        self.results.append(Result(check, outcome, said, facts))
        print(f"{outcome} {check}: {said}", flush=True)

    # -- hidden
    @contextmanager
    def hidden(self) -> Iterator[None]:
        moved, stayed = hide(self.out)
        tools = {t: shutil.which(t) for t in ("python3", "brew", "git", "clang")}
        if stayed:
            self.add("hidden", UNKNOWN, "some stayed: " + ", ".join(stayed),
                     moved=moved, stayed=stayed, on_path=tools)  # fmt: skip
        else:
            self.add("hidden", PASS, f"{len(moved)} moved aside", moved=moved,
                     on_path=tools)  # fmt: skip
        try:
            yield
        finally:
            show(self.out)

    # -- linkage
    def linkage(self) -> None:
        assert self.app is not None
        found = linkage_of(self.app)
        if found:
            self.add("linkage", FAIL, f"{len(found)} file(s) load from outside the app"
                     " and macOS: " + json.dumps(found)[:600], outside=found)  # fmt: skip
        else:
            self.add("linkage", PASS, "every Mach-O loads only from the app and macOS")

    # -- downloaded
    def downloaded_zip(self) -> Path:
        """The zip a learner downloads: the release's portable zip when this
        run made one, else the app zipped as the release's zip is."""
        if self.zipped is not None:
            return self.zipped
        assert self.app is not None
        # in the runner's own temporary folder, never OUT: the job keeps OUT
        # as its artifact, and the zip is 90 MB
        made = Path(tempfile.mkdtemp(prefix="polyglotic-523-")) / "learner.zip"
        done = sh(["ditto", "-c", "-k", "--sequesterRsrc", "--keepParent",
                   str(self.app), str(made)], 300)  # fmt: skip
        self.made = made
        if done["code"] != 0:
            raise OSError(f"ditto: {done['out']}")
        return made

    def downloaded(self) -> None:
        assert self.app is not None
        downloads = Path.home() / "Downloads"
        downloads.mkdir(exist_ok=True)
        target = downloads / "Polyglotic-macos-arm64-alpha.zip"
        shutil.copyfile(self.downloaded_zip(), target)
        sh(["xattr", "-w", "com.apple.quarantine", quarantine_value(), str(target)])
        unpacked = downloads / APP_NAME
        shutil.rmtree(unpacked, ignore_errors=True)
        # as Finder's double-click opens it: Archive Utility, which gives the
        # quarantine to everything it unpacks
        by = "Archive Utility"
        sh(["open", "-a", "Archive Utility", str(target)], 30)
        # done when its app is there and Archive Utility has gone (523's
        # first run: mid-unpacking, its folders can't be read yet)
        for _ in range(120):
            busy = sh(["pgrep", "-x", "Archive Utility"])["out"].strip()
            if there(unpacked / EXECUTABLE) and not busy:
                break
            time.sleep(1)
        seen = sh(["ls", "-led@", str(unpacked), str(unpacked / "Contents"),
                   str(unpacked / "Contents" / "MacOS")])["out"][-800:]  # fmt: skip
        if not there(unpacked / EXECUTABLE):
            by = "ditto, the quarantine given by hand (Archive Utility didn't)"
            sh(["chmod", "-R", "u+rwx", str(unpacked)])
            shutil.rmtree(unpacked, ignore_errors=True)
            sh(["ditto", "-x", "-k", str(target), str(downloads)], 300)
            sh(["xattr", "-r", "-w", "com.apple.quarantine", quarantine_value(),
                str(unpacked)])  # fmt: skip
        if not there(unpacked / EXECUTABLE):
            self.add("downloaded", FAIL, f"no {APP_NAME} came out of the zip")
            return
        self.unpacked = unpacked
        verified = sh(
            ["codesign", "--verify", "--deep", "--strict", "-vv", str(unpacked)]
        )
        built, came = requirement(self.app), requirement(unpacked)
        spctl = sh(["spctl", "-a", "-vv", "-t", "exec", str(unpacked)])
        verdict = gatekeeper_said(spctl["out"])
        quarantined = sh(["xattr", "-p", "com.apple.quarantine", str(unpacked)])["out"]
        facts = {"unpacked_by": by, "as_unpacked": seen, "codesign": verified["out"][-600:],
                 "requirement": came, "built_requirement": built,
                 "spctl": spctl["out"][-600:], "gatekeeper": verdict,
                 "quarantine": quarantined.strip()[:120]}  # fmt: skip
        if verified["code"] != 0 or verdict == "broken":
            self.add("downloaded", FAIL, "the downloaded app's signature is broken: "
                     + (verified["out"] or spctl["out"])[-300:], **facts)  # fmt: skip
        elif came != built:
            self.add("downloaded", FAIL, "the downloaded app's designated requirement"
                     f" isn't the built app's: {came} vs {built}", **facts)  # fmt: skip
        else:
            self.add("downloaded", PASS, f"verifies as built; Gatekeeper: {verdict}"
                     f" (unpacked by {by})", **facts)  # fmt: skip

    # -- opened from Downloads
    def opened_from_downloads(self) -> None:
        if self.unpacked is None:
            self.add("opened_from_downloads", UNKNOWN, "nothing was downloaded")
            return
        end(pids_of(self.unpacked))
        for place in (
            Path("/Applications") / APP_NAME,
            Path.home() / "Applications" / APP_NAME,
        ):
            shutil.rmtree(place, ignore_errors=True)
        data = Path.home() / "Library" / "Application Support" / "Polyglotic"
        log = data / "logs" / "polyglotic.log"
        before = log.stat().st_size if log.exists() else 0
        # a double-click: Gatekeeper refuses an app that isn't notarised and
        # waits on its dialog (523's probe: `open` never returned); the
        # learner then chooses Open Anyway, which marks the download as
        # approved - done here by the same flag - and opens it again
        facts: dict[str, Any] = {}
        running = self.open_and_wait(facts, "first", log, before)
        if running:
            facts["gatekeeper_refused"] = False
        else:
            facts["gatekeeper_refused"] = True
            approved = quarantine_value(APPROVED)
            sh(
                [
                    "xattr",
                    "-r",
                    "-w",
                    "com.apple.quarantine",
                    approved,
                    str(self.unpacked),
                ]
            )
            running = self.open_and_wait(facts, "after_open_anyway", log, before)
        if not running:
            policy = sh(["log", "show", "--last", "3m", "--style", "compact", "--predicate",
                         'process == "syspolicyd" AND eventMessage CONTAINS "Polyglotic"'],
                        90)["out"][-1500:]  # fmt: skip
            self.add("opened_from_downloads", UNKNOWN, "it didn't start from Downloads,"
                     " even marked as Open Anyway marks it: Gatekeeper kept it from a"
                     " script", policy=policy, **facts)  # fmt: skip
            return
        where = command_of(running[0])
        facts["ran_as"] = where
        translocated = "/AppTranslocation/" in where
        offered = False
        for _ in range(45):
            text = _tail(log, before)
            if OFFERED in text:
                offered = True
                break
            time.sleep(1)
        facts["log"] = _tail(log, before)[-1500:]
        if not translocated or not offered:
            end(pids_of(self.unpacked))
            self.add("opened_from_downloads", FAIL, f"translocated {translocated},"
                     f" the move offered {offered}", **facts)  # fmt: skip
            return
        time.sleep(2)
        # the learner's choice: Move, its default button - the app brought
        # to the front first (523's third run: a bare Return went elsewhere)
        facts["pressed"] = sh(["osascript", "-e", press_move(running[0])], 30)["out"]
        moved_to: Path | None = None
        for _ in range(60):
            for place in (Path("/Applications"), Path.home() / "Applications"):
                if there(place / APP_NAME / EXECUTABLE):
                    moved_to = place / APP_NAME
            again = [
                p
                for p in pids_of(self.unpacked)
                if "/AppTranslocation/" not in command_of(p)
            ]
            if moved_to is not None and again:
                break
            time.sleep(1)
        facts["moved_to"] = str(moved_to)
        facts["log_after"] = _tail(log, before)[-1500:]
        if moved_to is None:
            end(pids_of(self.unpacked))
            self.add("opened_from_downloads", FAIL, "Return on the offer didn't move it"
                     " to Applications", **facts)  # fmt: skip
            return
        left = sh(["xattr", "-p", "com.apple.quarantine", str(moved_to)])
        reopened = [command_of(p) for p in pids_of(moved_to)]
        facts |= {"quarantine_left": left["code"] == 0, "reopened": reopened}
        end(pids_of(moved_to))
        self.installed = moved_to
        if left["code"] == 0 or not any(str(moved_to) in r for r in reopened):
            self.add("opened_from_downloads", FAIL, "moved, but quarantined still"
                     f" ({left['code'] == 0}) or not opened again from"
                     f" {moved_to}", **facts)  # fmt: skip
        else:
            self.add("opened_from_downloads", PASS, "translocated, offered the move,"
                     f" moved to {moved_to.parent} and opened again from there", **facts)  # fmt: skip

    def open_and_wait(
        self, facts: dict[str, Any], name: str, log: Path, before: int
    ) -> list[int]:
        """The downloaded app opened as a double-click opens it; its PIDs
        once it runs - its log has begun, since a process Gatekeeper holds
        for its dialog exists but never starts (523's second run) - or none
        in `OPEN_SEC`: then Gatekeeper's dialog is closed and the held
        process ended, as a learner closing the dialog would."""
        assert self.unpacked is not None
        opened = sh(["open", str(self.unpacked)], OPEN_SEC)
        started = False
        for _ in range(OPEN_SEC):
            started = bool(_tail(log, before).strip())
            if started:
                break
            time.sleep(1)
        running = pids_of(self.unpacked)
        facts[f"open_{name}"] = opened["out"][-300:]
        facts[f"held_{name}"] = bool(running) and not started
        if started:
            return running
        dialogs = sh(["pgrep", "-x", "CoreServicesUIAgent"])["out"].split()
        facts[f"gatekeeper_dialog_{name}"] = bool(dialogs)
        end([int(p) for p in dialogs if p.isdigit()])
        end(running)
        return []

    # -- a fresh account
    def fresh_account(self) -> None:
        app = self.installed or self.app
        assert app is not None
        if self.installed is None:
            # the account needs an app it can read: the built one, copied
            # where a learner keeps it
            place = Path("/Applications") / APP_NAME
            shutil.rmtree(place, ignore_errors=True)
            sh(["ditto", str(self.app), str(place)], 300)
            app = place
        password = secrets.token_urlsafe(18)
        made = sh(["sudo", "sysadminctl", "-addUser", LEARNER, "-fullName",
                   "Polyglotic learner", "-password", password, "-home",
                   f"/Users/{LEARNER}"], 120)  # fmt: skip
        del password
        if sh(["id", LEARNER])["code"] != 0:
            self.add("fresh_account", UNKNOWN, "sysadminctl made no user: "
                     + made["out"][-300:])  # fmt: skip
            return
        home = Path("/Users") / LEARNER
        sh(["sudo", "createhomedir", "-c", "-u", LEARNER], 120)
        reports = Path("/tmp") / "polyglotic-523-learner"
        sh(["sudo", "rm", "-rf", str(reports)])
        reports.mkdir(mode=0o777)
        os.chmod(reports, 0o777)
        program = str(app / EXECUTABLE)
        runs: dict[str, Any] = {}
        for flag, name in (
            ("--check-install", "install.json"),
            ("--check-tls", "tls.json"),
        ):
            runs[flag] = sh(["sudo", "-u", LEARNER, "-H", "env", f"HOME={home}",
                             program, flag, str(reports / name)], 300)  # fmt: skip
        found = {n: _json(reports / n) for n in ("install.json", "tls.json")}
        for n in ("install.json", "tls.json"):
            if (reports / n).exists():
                shutil.copyfile(reports / n, self.out / f"fresh-account-{n}")
        data = sh(
            ["sudo", "ls", "-la", f"{home}/Library/Application Support/Polyglotic"]
        )
        had_home = home.exists()
        sh(["sudo", "sysadminctl", "-deleteUser", LEARNER], 120)
        facts = {"home_existed": had_home, "runs": {k: v["out"][-400:] for k, v in runs.items()},
                 "install_ok": found["install.json"].get("ok"),
                 "tls_ok": found["tls.json"].get("ok"),
                 "tls": {k: found["tls.json"].get(k) for k in ("health", "sign_in", "roots")},
                 "data_folder": data["out"][-400:]}  # fmt: skip
        if (
            found["install.json"].get("ok") is True
            and found["tls.json"].get("ok") is True
        ):
            self.add("fresh_account", PASS, f"as a new user ({LEARNER}): --check-install"
                     " and --check-tls pass", **facts)  # fmt: skip
        else:
            self.add("fresh_account", FAIL, f"as a new user: --check-install"
                     f" {facts['install_ok']}, --check-tls {facts['tls_ok']}"
                     f" ({facts['tls']})", **facts)  # fmt: skip

    def tidy(self) -> None:
        made = None if self.zipped is not None else self.made
        for place in (
            self.unpacked,
            Path.home() / "Downloads" / "Polyglotic-macos-arm64-alpha.zip",
            made.parent if made is not None else None,
        ):
            if place is not None and place.exists():
                if place.is_dir():
                    shutil.rmtree(place, ignore_errors=True)
                else:
                    place.unlink()
        for place in (
            Path("/Applications") / APP_NAME,
            Path.home() / "Applications" / APP_NAME,
        ):
            end(pids_of(place))
            shutil.rmtree(place, ignore_errors=True)


MOVE = "Move to Applications"
"""The offer's default button (ui.move_to_applications.move_button)."""


def press_move(pid: int) -> str:
    """AppleScript for System Events: the process `pid` brought to the
    front, its offer's Move button clicked - or, if the button can't be
    found, Return pressed for the default one. Says which."""
    return f"""tell application "System Events"
  set p to first process whose unix id is {pid}
  set frontmost of p to true
  delay 1
  try
    click button "{MOVE}" of window 1 of p
    return "clicked {MOVE}"
  on error problem
    keystroke return
    return "pressed Return: " & problem
  end try
end tell"""


def there(path: Path) -> bool:
    """Whether `path` exists and can be seen: False, not an error, while a
    folder on the way can't be read yet."""
    try:
        return path.exists()
    except OSError:
        return False


def _tail(log: Path, start: int) -> str:
    try:
        with log.open("rb") as file:
            file.seek(start)
            return file.read().decode("utf-8", "replace")
    except OSError:
        return ""


def _json(path: Path) -> dict[str, Any]:
    try:
        found = json.loads(path.read_text(encoding="utf-8"))
        return found if isinstance(found, dict) else {}
    except (OSError, ValueError):
        return {}


def hide(out: Path) -> tuple[list[str], list[str]]:
    """What GitHub's Mac has and a learner's needn't (`HIDDEN`), moved aside
    and listed in OUT/hidden.json for `show`: (moved, stayed) - what the
    checks run on stays (`kept_by_the_checks`), as does what wouldn't move."""
    kept = kept_by_the_checks()
    moved: list[str] = []
    stayed: list[str] = []
    for pattern in HIDDEN:
        for place in sorted(glob.glob(pattern)) if "*" in pattern else [pattern]:
            if not os.path.lexists(place):
                continue
            if (
                hideable(os.path.realpath(place), kept)
                and sh(["sudo", "mv", place, place + ASIDE])["code"] == 0
            ):
                moved.append(place)
            else:
                stayed.append(place)
    (out / "hidden.json").write_text(json.dumps(moved), encoding="utf-8")
    return moved, stayed


def show(out: Path) -> list[str]:
    """What `hidden` moved aside, put back (also from a step that always
    runs: `--show`)."""
    try:
        moved = json.loads((out / "hidden.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    back = []
    for place in moved:
        aside = os.path.lexists(place + ASIDE) and not os.path.lexists(place)
        if aside and sh(["sudo", "mv", place + ASIDE, place])["code"] == 0:
            back.append(place)
    (out / "hidden.json").write_text("[]", encoding="utf-8")
    return back


def report(results: list[Result]) -> dict[str, Any]:
    return {"checks": [asdict(r) for r in results]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m tools.macos_learner_checks")
    parser.add_argument("out", type=Path)
    parser.add_argument("--app", type=Path, help="the built Polyglotic.app")
    parser.add_argument("--zip", type=Path, help="the release's portable zip, if made")
    parser.add_argument("--hide", action="store_true", help="only move aside (HIDDEN)")
    parser.add_argument("--show", action="store_true", help="put back what was hidden")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    if args.dry_run:
        print("\n".join(plan()))
        return 0
    args.out.mkdir(parents=True, exist_ok=True)
    if args.show:
        print("put back: " + (", ".join(show(args.out)) or "nothing"))
        return 0
    if sys.platform != "darwin":
        print("GitHub's Mac only (it moves system folders aside): --dry-run elsewhere")
        return 2
    if args.hide:
        moved, stayed = hide(args.out)
        print(
            f"moved aside: {', '.join(moved) or 'nothing'}; stayed: {', '.join(stayed) or 'nothing'}"
        )
        return 0
    if args.app is None or not (args.app / EXECUTABLE).exists():
        print(f"no packed app at {args.app}: nothing to check")
        return 2
    learner = Learner(args.out, args.app.resolve(), args.zip)
    steps = (learner.linkage, learner.downloaded, learner.opened_from_downloads,
             learner.fresh_account)  # fmt: skip
    try:
        with learner.hidden():
            for step in steps:
                try:
                    step()
                except Exception as e:  # noqa: BLE001 - said, then the next
                    learner.add(step.__name__, FAIL, f"{type(e).__name__}: {e}")
    finally:
        learner.tidy()
        (args.out / "learner.json").write_text(
            json.dumps(report(learner.results), indent=1), encoding="utf-8"
        )
    return 1 if any(r.outcome == FAIL for r in learner.results) else 0


if __name__ == "__main__":
    sys.exit(main())
