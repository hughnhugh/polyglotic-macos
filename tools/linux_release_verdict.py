r"""Linux's release check, read as one verdict (polyglotic-hq 574; 546's
section 3): what each part of `.github/workflows/linux-release.yml` found,
as the seven checks a release waits for - and a red one stops it.

    python -m tools.linux_release_verdict PARTS [--out VERDICT.json]

PARTS holds each part's findings as the jobs left them:
- `package/linkage-*/linkage.txt`, `package/updates/summary.txt`,
  `package/fedora-update/summary.txt`: `pass NAME ...` / `fail NAME ...`
  lines (tools/package/linux_linkage.sh, linux_update_rehearsal.sh);
- `capture/summary.txt`: the same, for the sound server's and the keyring's
  own tests in a desktop session;
- `tour-DESKTOP/checks.json`: the packed AppImage's tour on each
  desktop (tools/linux_packed_tour.py).

The seven (546's section 3), and what each is made of:
1. **linkage** - every library the packed app loads is its own or the
   system's, on clean Ubuntu 24.04 and 26.04;
2. **starts** - the AppImage starts with no FUSE 2 and its own check passes
   (linkage's `--check-install`), and on each desktop it starts and stays up
   with no crash;
3. **capture** - the sound server's tests (system, mic, one app, everything
   else, measured), and on each desktop the stand-in heard what the PC
   plays, the mic and one app alone;
4. **windows** - on each desktop the caption window above a full-screen
   window;
5. **keyring** - the keyring's tests, and on each desktop the token kept
   where the app looks (the Secret Service, or the file on Xfce) and the
   sign-in with it;
6. **update** - from one version to the next through a local feed, the file
   replaced in place as the app exits;
7. **fedora** - 1, 2 and 6 on Fedora 45.

And an eighth, **manners**: everything else each desktop's tour checked
(the tray, light or dark, the menu entry). A part that's missing is a fail:
a job that didn't finish proved nothing. Exits 0 when all eight passed.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

DESKTOPS = ("gnome", "ubuntu", "fedora-gnome", "kde", "xfce")
FEDORA_DESKTOPS = ("fedora-gnome", "kde")
CHECKS = (
    "linkage",
    "starts",
    "capture",
    "windows",
    "keyring",
    "update",
    "fedora",
    "manners",
)


@dataclass
class Found:
    """One check's findings: what passed, what failed, what was missing."""

    passed: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return bool(self.passed) and not self.failed and not self.missing


def lines(path: Path) -> list[tuple[bool, str]] | None:
    """`pass NAME` / `fail NAME` lines, or None: no such file."""
    if not path.is_file():
        return None
    found = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        word, _, rest = line.partition(" ")
        if word in ("pass", "fail"):
            found.append((word == "pass", rest.strip()))
    return found


def tour(parts: Path, desktop: str) -> list[tuple[bool, str]] | None:
    """The desktop's tour, as its artifact keeps it (its folder's contents
    at the top) or as the tour wrote it (`DESKTOP/checks.json`)."""
    folder = parts / f"tour-{desktop}"
    path = next(
        (
            p
            for p in (folder / "checks.json", folder / desktop / "checks.json")
            if p.is_file()
        ),
        None,
    )
    if path is None:
        return None
    said = json.loads(path.read_text(encoding="utf-8"))
    return [(bool(c["ok"]), str(c["check"])) for c in said.get("checks", [])]


def add(
    found: Found,
    where: str,
    results: list[tuple[bool, str]] | None,
    keep: tuple[str, ...] = (),
) -> None:
    """`results` into `found`, those whose name has one of `keep` in it
    (all of them with none given); None is a part missing."""
    if results is None:
        found.missing.append(where)
        return
    for ok, name in results:
        if keep and not any(k in name for k in keep):
            continue
        (found.passed if ok else found.failed).append(f"{where}: {name}")


STARTS = ("started and stayed up", "no crash")
CAPTURE = ("was captioned", "one app")
WINDOWS = ("caption window", "full-screen")
KEYRING = ("token is kept", "signed in")


def verdict(parts: Path) -> dict[str, Found]:
    checks = {name: Found() for name in CHECKS}
    package = parts / "package"
    for system in ("ubuntu-24.04", "ubuntu-26.04"):
        add(
            checks["linkage"],
            f"linkage {system}",
            lines(package / f"linkage-{system}" / "linkage.txt"),
        )
        add(
            checks["starts"],
            f"linkage {system}",
            lines(package / f"linkage-{system}" / "linkage.txt"),
            ("--check-install",),
        )
    add(checks["update"], "update", lines(package / "updates" / "summary.txt"))
    add(
        checks["fedora"],
        "linkage fedora-45",
        lines(package / "linkage-fedora-45" / "linkage.txt"),
    )
    add(
        checks["fedora"],
        "update fedora-45",
        lines(package / "fedora-update" / "summary.txt"),
    )
    capture = lines(parts / "capture" / "summary.txt")
    add(checks["capture"], "sound server", capture, ("capture",))
    add(checks["keyring"], "keyring", capture, ("keyring",))
    for desktop in DESKTOPS:
        found = tour(parts, desktop)
        add(checks["starts"], desktop, found, STARTS)
        add(checks["capture"], desktop, found, CAPTURE)
        add(checks["windows"], desktop, found, WINDOWS)
        add(checks["keyring"], desktop, found, KEYRING)
        if desktop in FEDORA_DESKTOPS:
            add(checks["fedora"], desktop, found, STARTS)
        if found is not None:
            rest = [
                (ok, name)
                for ok, name in found
                if not any(k in name for k in STARTS + CAPTURE + WINDOWS + KEYRING)
            ]
            add(checks["manners"], desktop, rest)
        else:
            checks["manners"].missing.append(desktop)
    return checks


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m tools.linux_release_verdict")
    parser.add_argument("parts", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    checks = verdict(args.parts)
    said = {
        name: {
            "ok": found.ok,
            "passed": len(found.passed),
            "failed": found.failed,
            "missing": found.missing,
        }
        for name, found in checks.items()
    }
    for number, (name, found) in enumerate(checks.items(), 1):
        mark = "pass" if found.ok else "FAIL"
        print(
            f"{mark} {number}. {name}: {len(found.passed)} passed, "
            f"{len(found.failed)} failed, {len(found.missing)} missing"
        )
        for line in found.failed + [f"missing: {m}" for m in found.missing]:
            print(f"     {line[:200]}")
    ok = all(found.ok for found in checks.values())
    print(f"Linux's release check: {'passed' if ok else 'FAILED'}")
    if args.out:
        args.out.write_text(
            json.dumps({"ok": ok, "checks": said}, indent=2), encoding="utf-8"
        )
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
