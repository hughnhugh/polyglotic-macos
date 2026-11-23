"""What a Linux release publishes, set apart and checked (polyglotic-hq 592).

Linux's release check (`.github/workflows/linux-release.yml`) packs the
release's AppImage into a folder of its own, beside the channel's published
releases (`linux_build.sh`'s RELEASE_FROM). This takes from that folder
exactly what the release script uploads to the update host, under the
names the host serves, and nothing else:

- the version's packages (`Polyglotic-VERSION-CHANNEL-full.nupkg`, and its
  delta when there was a release before it): what installed copies update to;
- the channel's feed (`releases.CHANNEL.json`), `assets.CHANNEL.json` and
  `RELEASES-CHANNEL`, as Velopack wrote them (the release script signs the
  feed on the PC that holds the key, never here);
- the AppImage under the channel's name, `Polyglotic-CHANNEL.AppImage`: one
  name per channel, so a beta or stable publish never overwrites the
  alpha's download (polyglotic-hq 580), as Windows' installer and the Mac's
  zip are named. The learner's saved file is still `Polyglotic.AppImage`
  (decision 0259): the host serves it with that file name.

and SHA256SUMS of them all. The release check's update checks then read
this set's feed back (an older AppImage updating from it), and the release
script downloads the same set and checks it against SHA256SUMS - so what
is published is what was checked.

    python -m tools.package.linux_publish_set RELEASE_FOLDER VERSION CHANNEL OUT

Refused (exit 1, saying why), with nothing written: a feed whose newest
full package isn't VERSION's, a package that isn't as the feed lists it,
or no AppImage. Standard library only.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import sys
from collections.abc import Sequence
from pathlib import Path

ID = "Polyglotic"
CHANNEL = re.compile(r"^linux-[a-z0-9]{2,12}-(alpha|beta|stable|rehearsal)$")
VERSION = re.compile(r"^\d+\.\d+\.\d+$")
SUMS = "SHA256SUMS"


class NotPublishable(Exception):
    """The folder isn't one release's, as the feed says it is."""


def appimage_name(channel: str) -> str:
    """The AppImage's name on the update host: the channel's own."""
    return f"{ID}-{channel}.AppImage"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _version(text: str) -> tuple[int, ...]:
    if not VERSION.match(text):
        raise NotPublishable(f"a version that isn't ours: {text!r}")
    return tuple(int(part) for part in text.split("."))


def chosen(folder: Path, version: str, channel: str) -> tuple[list[str], bool]:
    """The files of `folder` to publish for `version` on `channel` (the
    AppImage last, under its own name in the folder), and whether the feed
    carries the version's notes. NotPublishable when the feed and the
    files disagree."""
    if not CHANNEL.match(channel):
        raise NotPublishable(f"not a Linux channel: {channel}")
    _version(version)
    feed = folder / f"releases.{channel}.json"
    try:
        assets = json.loads(feed.read_text(encoding="utf-8-sig"))["Assets"]
    except (OSError, ValueError, KeyError, TypeError):
        raise NotPublishable(f"no feed to read: {feed.name}") from None
    full = [a for a in assets if str(a.get("Type", "")).lower() == "full"]
    if not full:
        raise NotPublishable(f"{feed.name} lists no full package")
    newest = max(full, key=lambda a: _version(str(a.get("Version", ""))))
    if newest.get("Version") != version:
        raise NotPublishable(
            f"{feed.name}'s newest full package is {newest.get('Version')}, not {version}"
        )
    mine = [a for a in assets if a.get("Version") == version]
    names: list[str] = []
    for asset in mine:
        name = str(asset.get("FileName", ""))
        if not re.fullmatch(
            rf"{ID}-{re.escape(version)}-{channel}-(full|delta)\.nupkg", name
        ):
            raise NotPublishable(f"{name}: not this release's package name")
        package = folder / name
        if not package.is_file():
            raise NotPublishable(f"{name}: listed, not built")
        if package.stat().st_size != asset.get("Size"):
            raise NotPublishable(f"{name}: not the size the feed lists")
        if _sha256(package) != str(asset.get("SHA256", "")).lower():
            raise NotPublishable(f"{name}: not the SHA-256 the feed lists")
        names.append(name)
    for extra in (f"assets.{channel}.json", f"RELEASES-{channel}"):
        if (folder / extra).is_file():
            names.append(extra)
    names.append(feed.name)
    if not (folder / f"{ID}.AppImage").is_file():
        raise NotPublishable(f"no {ID}.AppImage in {folder}")
    noted = bool(str(newest.get("NotesMarkdown") or "").strip())
    return names, noted


def publish_set(folder: Path, version: str, channel: str, out: Path) -> bool:
    """`folder`'s release for `version` copied into `out` as the host
    serves it, with SHA256SUMS; whether its feed carries notes."""
    names, noted = chosen(folder, version, channel)
    if out.exists() and any(out.iterdir()):
        raise NotPublishable(f"{out} isn't empty")
    out.mkdir(parents=True, exist_ok=True)
    for name in names:
        shutil.copyfile(folder / name, out / name)
    shutil.copyfile(folder / f"{ID}.AppImage", out / appimage_name(channel))
    lines = [
        f"{_sha256(out / n)}  {n}" for n in sorted(names + [appimage_name(channel)])
    ]
    (out / SUMS).write_bytes(("\n".join(lines) + "\n").encode("utf-8"))
    return noted


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 4:
        print(
            "usage: python -m tools.package.linux_publish_set RELEASE_FOLDER VERSION CHANNEL OUT",
            file=sys.stderr,
        )
        return 2
    folder, version, channel, out = Path(args[0]), args[1], args[2], Path(args[3])
    try:
        noted = publish_set(folder, version, channel, out)
    except NotPublishable as e:
        print(f"Not published: {e}", file=sys.stderr)
        return 1
    print((out / SUMS).read_text(encoding="utf-8"), end="")
    print(
        f"{version} on {channel}: "
        + ("with its notes" if noted else "no release notes")
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
