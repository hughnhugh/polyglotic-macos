"""A Mac release's packages, checked where they're made (polyglotic-hq 430; decision 0202).

    python -m tools.package.macos_release check RELEASES --version 0.1.7 \\
        --channel macos-arm64-alpha --built dist/Polyglotic.app
        What `pack.sh` made in RELEASES for VERSION: the feed lists its full
        package, whose size and SHA-256 are the file's; the portable zip's
        Polyglotic.app has Velopack's UpdateMac and the version's
        sq.version, verifies (`codesign --verify --deep --strict`) and has
        the built app's designated requirement - what macOS keeps a
        learner's permissions under (decision 0196). Then RELEASES/SHA256SUMS
        for this version's files, which publish-mac.sh checks before it
        uploads anything. Exit 1, saying what's wrong, otherwise.

    python -m tools.package.macos_release app APP --version 0.0.2 --like OTHER.app
        The same checks on an app as installed (an update applied in place).

`vpk pack` adds UpdateMac and sq.version to the bundle and signs it again
(`pack.sh`, `macos_codesign.sh`), so these are the checks that the bundle
testers download is still the one the build signed. Runs on a Mac (codesign,
ditto); the feed's and sq.version's checks on any OS.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path

NAME = "Polyglotic"
SUMS = "SHA256SUMS"
SQ_VERSION = "Contents/Resources/sq.version"
UPDATE_MAC = "Contents/MacOS/UpdateMac"


def portable_zip(channel: str) -> str:
    """Velopack's name for the portable zip (its `DefaultName`): the one
    the alpha page's Mac button downloads, under a fixed name."""
    return f"{NAME}-{channel}-Portable.zip"


def full_package(version: str, channel: str) -> str:
    return f"{NAME}-{version}-{channel}-full.nupkg"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def feed_problems(releases: Path, version: str, channel: str) -> list[str]:
    """What's wrong with `releases.<channel>.json` for `version`'s full
    package: missing, or its size or SHA-256 not the file's."""
    feed = releases / f"releases.{channel}.json"
    try:
        assets = json.loads(feed.read_bytes())["Assets"]
    except (OSError, ValueError, KeyError, TypeError):
        return [f"{feed.name} can't be read"]
    name = full_package(version, channel)
    listed = [
        a
        for a in assets
        if isinstance(a, dict)
        and a.get("FileName") == name
        and str(a.get("Type", "")).lower() == "full"
    ]
    if len(listed) != 1:
        return [f"{feed.name} doesn't list {name} once"]
    package = releases / name
    if not package.is_file():
        return [f"{name} is listed but missing"]
    found = []
    if listed[0].get("Size") != package.stat().st_size:
        found.append(f"{name}'s size isn't the feed's")
    if str(listed[0].get("SHA256", "")).lower() != sha256(package):
        found.append(f"{name}'s SHA-256 isn't the feed's")
    return found


def sq_version(text: str) -> str | None:
    """The version in Velopack's sq.version (a nuspec's `<version>`)."""
    found = re.search(r"<version>\s*([^<\s]+)\s*</version>", text)
    return found.group(1) if found else None


def velopack_problems(app: Path, version: str) -> list[str]:
    """What's missing for Velopack to update `app` as `version`."""
    found = []
    if not (app / UPDATE_MAC).is_file():
        found.append("no UpdateMac in the app: it can't update itself")
    try:
        said = sq_version((app / SQ_VERSION).read_text(encoding="utf-8"))
    except OSError:
        said = None
    if said != version:
        found.append(f"sq.version says {said}, not {version}")
    return found


def _codesign(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["codesign", *args], capture_output=True, text=True, check=False
    )


def requirement(app: Path) -> str:
    """The app's designated requirement, as `codesign` shows it."""
    return _codesign("--display", "--requirements", "-", str(app)).stdout.strip()


def authority(app: Path) -> list[str]:
    shown = _codesign("--display", "--verbose=2", str(app)).stderr
    return [
        line.partition("=")[2]
        for line in shown.splitlines()
        if line.startswith("Authority=")
    ]


def app_problems(app: Path, version: str, like: Path) -> list[str]:
    """`velopack_problems`, and the signature: it verifies, and - signed
    with a certificate - its designated requirement is `like`'s (the app
    as the build signed it). An ad-hoc signature's requirement is the
    code's own hash, which every signing changes: nothing carries over
    there anyway (decision 0196)."""
    found = velopack_problems(app, version)
    verified = _codesign("--verify", "--deep", "--strict", str(app))
    if verified.returncode != 0:
        found.append(f"the signature doesn't verify: {verified.stderr.strip()[-500:]}")
    if authority(like) and requirement(app) != requirement(like):
        found.append("its designated requirement isn't the built app's")
    return found


def check(releases: Path, version: str, channel: str, built: Path) -> dict[str, object]:
    """`feed_problems` and `app_problems` on the portable zip's app, then
    SHA256SUMS for this version's files."""
    found = feed_problems(releases, version, channel)
    zipped = releases / portable_zip(channel)
    seen: dict[str, object] = {}
    if not zipped.is_file():
        found.append(f"no {zipped.name}")
    else:
        with tempfile.TemporaryDirectory() as unzipped:
            subprocess.run(["ditto", "-x", "-k", str(zipped), unzipped], check=True)
            app = Path(unzipped) / f"{NAME}.app"
            found += app_problems(app, version, built)
            seen = {"authority": authority(app), "requirement": requirement(app)}
    files = [
        zipped.name,
        full_package(version, channel),
        f"releases.{channel}.json",
        f"assets.{channel}.json",
    ]
    present = [f for f in files if (releases / f).is_file()]
    (releases / SUMS).write_bytes(
        "".join(f"{sha256(releases / f)}  {f}\n" for f in present).encode()
    )
    return {"version": version, "files": present, "problems": found, **seen}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m tools.package.macos_release")
    sub = parser.add_subparsers(dest="command", required=True)
    checked = sub.add_parser("check", help="a release's packages, where they're made")
    checked.add_argument("releases", type=Path)
    checked.add_argument("--version", required=True)
    checked.add_argument("--channel", required=True)
    checked.add_argument("--built", type=Path, required=True)
    installed = sub.add_parser("app", help="an app as installed, or updated in place")
    installed.add_argument("app", type=Path)
    installed.add_argument("--version", required=True)
    installed.add_argument("--like", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "check":
        result = check(args.releases, args.version, args.channel, args.built)
    else:
        result = {
            "version": args.version,
            "problems": app_problems(args.app, args.version, args.like),
            "authority": authority(args.app),
        }
    print(json.dumps(result, indent=2))
    return 1 if result["problems"] else 0


if __name__ == "__main__":
    sys.exit(main())
