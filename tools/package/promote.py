"""A build promoted to another channel with no rebuild (decision 0044).

    python -m tools.package.promote unpack BUILD.nupkg --channel win-x64-beta \\
        --out FOLDER [--sums SHA256SUMS-build]
    bash tools/package/pack.sh VERSION win-x64-beta FOLDER/app RELEASES FOLDER/Polyglotic.ico
    python -m tools.package.promote compare BUILD.nupkg PROMOTED.nupkg --channel win-x64-beta

The channel is stamped twice into a packed build: the app's own
`release.json` (decision 0015: what `hello` says, which feed the updater
checks) and Velopack's `sq.version` (which channel the installed copy
follows). So a channel can't be handed another channel's package - its
testers would follow that channel's feed. Instead the build's full
package is unpacked, its stamp given the new channel, and Velopack packs
the same files again for it:

- `unpack` checks the build's full package against its recorded SHA-256,
  takes out the app's files (leaving Velopack's own, which it adds again),
  stamps the channel, and writes the installer's icon;
- `compare` checks the promoted package holds exactly the build's files,
  byte for byte (SHA-256), except `release.json` and `sq.version`, which
  differ only in the channel.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
import zipfile
from collections.abc import Sequence
from pathlib import Path, PurePosixPath

from tools.package import stamp

APP = "lib/app/"
"""Where a Velopack full package keeps the app's files."""
STAMP = "_internal/polyglotic_desktop/release.json"
"""The release stamp in the PyInstaller folder (polyglotic.spec's datas)."""
MANIFEST = "sq.version"
"""Velopack's manifest in the package: the version, and `<channel>`."""
VELOPACK_ADDS = re.compile(r"^(sq\.version|Squirrel\.exe|[^/]+_ExecutionStub\.exe)$")
"""What `vpk pack` adds beside the app's files, and adds again."""
CHANNEL_TAG = re.compile(r"<channel>[^<]*</channel>")


class NotTheBuild(Exception):
    """The package isn't the build it should be: the reason."""


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while piece := f.read(1 << 20):
            digest.update(piece)
    return digest.hexdigest()


def recorded_sha256(sums: str, name: str) -> str:
    """`name`'s SHA-256 in a SHA256SUMS (sha256sum's format)."""
    for line in sums.splitlines():
        if line.strip():
            digest, file = line.split(maxsplit=1)
            if file.removeprefix("*") == name:
                return digest.lower()
    raise NotTheBuild(f"{name} isn't in the recorded SHA256SUMS")


def app_files(package: Path) -> dict[str, str]:
    """Each file under the package's `lib/app/`, by path, -> its SHA-256."""
    with zipfile.ZipFile(package) as z:
        return {
            info.filename.removeprefix(APP): hashlib.sha256(z.read(info)).hexdigest()
            for info in z.infolist()
            if info.filename.startswith(APP) and not info.is_dir()
        }


def _read(package: Path, name: str) -> str:
    with zipfile.ZipFile(package) as z:
        return z.read(APP + name).decode("utf-8")


def unpack(build: Path, channel: str, out: Path, expected: str | None) -> Path:
    """The build's app folder, stamped for `channel`, in `out/app`; with
    the installer's icon at `out/Polyglotic.ico`. Returns the app folder."""
    if expected is not None and sha256(build) != expected:
        raise NotTheBuild(f"{build.name}: SHA-256 {sha256(build)}, recorded {expected}")
    built = json.loads(_read(build, STAMP))
    app = out / "app"
    if app.exists():
        shutil.rmtree(app)
    with zipfile.ZipFile(build) as z:
        for info in z.infolist():
            name = info.filename.removeprefix(APP)
            if (
                not info.filename.startswith(APP)
                or info.is_dir()
                or VELOPACK_ADDS.match(name)
            ):
                continue
            target = app / PurePosixPath(name)
            if app.resolve() not in target.resolve().parents:
                raise NotTheBuild(f"{info.filename} would land outside the app folder")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(z.read(info))
    (app / STAMP).write_text(
        stamp.stamp(built["version"], channel, built.get("built")), encoding="utf-8"
    )
    from tools.package.build import write_icon  # Qt, only here

    write_icon(out / "Polyglotic.ico")
    return app


def compare(build: Path, promoted: Path, channel: str) -> list[str]:
    """What isn't the same build: one line per problem, none if the promoted
    package is the build's files with only the channel changed."""
    before, after = app_files(build), app_files(promoted)
    problems = [
        f"{name}: only in the build" for name in sorted(before.keys() - after.keys())
    ]
    problems += [
        f"{name}: not in the build" for name in sorted(after.keys() - before.keys())
    ]
    changed = {
        name for name in before.keys() & after.keys() if before[name] != after[name]
    }
    for name in sorted(changed - {STAMP, MANIFEST}):
        problems.append(f"{name}: not the build's bytes")
    if STAMP in before and STAMP in after:
        old, new = json.loads(_read(build, STAMP)), json.loads(_read(promoted, STAMP))
        if new.get("channel") != channel or {**old, "channel": channel} != new:
            problems.append(f"{STAMP}: {new}, not the build's stamp on {channel}")
    if MANIFEST in before and MANIFEST in after:
        old_manifest, new_manifest = _read(build, MANIFEST), _read(promoted, MANIFEST)
        on_channel = f"<channel>{channel}</channel>"
        if CHANNEL_TAG.sub(on_channel, old_manifest) != new_manifest:
            problems.append(
                f"{MANIFEST}: differs from the build's in more than the channel"
            )
    return problems


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m tools.package.promote")
    commands = parser.add_subparsers(dest="command", required=True)
    unpacking = commands.add_parser(
        "unpack", help="the build's files, stamped for a channel"
    )
    unpacking.add_argument("build", type=Path)
    unpacking.add_argument("--channel", required=True)
    unpacking.add_argument("--out", type=Path, required=True)
    unpacking.add_argument(
        "--sums", type=Path, help="the SHA256SUMS that records the build"
    )
    comparing = commands.add_parser("compare", help="the promoted package is the build")
    comparing.add_argument("build", type=Path)
    comparing.add_argument("promoted", type=Path)
    comparing.add_argument("--channel", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "unpack":
            expected = None
            if args.sums:
                expected = recorded_sha256(
                    args.sums.read_text(encoding="utf-8"), args.build.name
                )
            app = unpack(args.build, args.channel, args.out, expected)
            print(f"{args.build.name} unpacked for {args.channel} into {app}")
            return 0
        problems = compare(args.build, args.promoted, args.channel)
    except (NotTheBuild, ValueError, KeyError, OSError, zipfile.BadZipFile) as e:
        print(f"::error::Not the build: {e}")
        return 1
    for problem in problems:
        print(f"::error::Not the same build: {problem}")
    if problems:
        return 1
    same = len(app_files(args.build)) - 2
    print(
        f"{args.promoted.name} is {args.build.name}'s build: {same} files byte for byte"
        f" the same, release.json and sq.version on {args.channel}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
