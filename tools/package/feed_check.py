"""The daily feed check: is each channel's public update feed what we published?

Run by `.github/workflows/feed-check.yml` (polyglotic-hq project 032, D5
item 8; decisions 0018, 0020 and 0044). A tag has one GitHub Release; each
channel the tag's build is published to records on it a
`SHA256SUMS-<channel>` of what it published there: the channel's feed as
the storage served it after the upload merged it, the feed's signature,
the installer and the full package. Anyone who could write the update storage or change the domain's
DNS could serve testers other code; this compares those files as the
public feed serves them now.

**Each channel against its own latest published Release** (project 066,
Low 5): following only the newest Release overall would stop checking the
alpha's feed once a beta release is newest - while alpha testers still run
the alpha. A channel's latest is the highest version whose Release records
that channel - not the latest by date: a promotion adds a channel to an
older tag's Release (decision 0044). A channel with no published Release
yet is skipped; drafts (release.yml's runs before the update storage
existed) published nothing.

    GH_TOKEN=... GH_REPO=owner/repo UPDATE_FEED=https://updates.<domain>/ \\
        python -m tools.package.feed_check

Exits 1 - which emails the repo's owner from Actions - on any difference,
a file not served, a Release that records no feed for its channel, or no
published Release at all. Standard library only: the workflow runs it
without installing the app.
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.request
from collections.abc import Callable, Iterable, Mapping

CHANNELS = ("win-x64-alpha", "win-x64-beta", "win-x64-stable")
"""The app's update channels (core.releases.updates.CHANNELS; a test keeps
them equal - this runs without the app installed)."""

COMPARED = ("releases.*.json", "releases.*.json.sig", "*-Setup.exe", "*-full.nupkg")
"""The files compared: the feed, its signature, the installer and the full
package. Velopack's other files (RELEASES-<channel>, assets.<channel>.json,
deltas) aren't what the app reads."""

TAG = re.compile(r"^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")


def sums_asset(channel: str) -> str:
    """The asset that records what a channel was published: `SHA256SUMS-win-x64-beta`."""
    return f"SHA256SUMS-{channel}"


Served = Callable[[str], "str | None"]
"""A URL -> the SHA-256 of what it serves now, or None if it serves nothing."""


def latest_per_channel(releases: Iterable[Mapping[str, object]]) -> dict[str, str]:
    """Each channel's latest published Release's tag, from `list_releases`
    rows (`tagName`, `isDraft`, `assets`): the highest version that records
    the channel."""
    latest: dict[str, tuple[tuple[int, ...], str]] = {}
    for row in releases:
        tag = str(row.get("tagName") or "")
        if row.get("isDraft") or not TAG.match(tag):
            continue
        version = tuple(int(part) for part in tag[1:].split("."))
        assets = row.get("assets") or ()
        assert isinstance(assets, list | tuple)
        for channel in CHANNELS:
            if sums_asset(channel) in assets and (
                channel not in latest or version > latest[channel][0]
            ):
                latest[channel] = (version, tag)
    return {channel: tag for channel, (_, tag) in latest.items()}


def recorded(sums: str) -> list[tuple[str, str]]:
    """The compared files in a SHA256SUMS (sha256sum's format), as (name,
    SHA-256), in its order."""
    files = []
    for line in sums.splitlines():
        if not line.strip():
            continue
        digest, name = line.split(maxsplit=1)
        name = name.removeprefix("*")  # sha256sum's binary-mode mark
        if any(fnmatch.fnmatchcase(name, pattern) for pattern in COMPARED):
            files.append((name, digest.lower()))
    return files


def check_channel(channel: str, sums: str, feed: str, served: Served) -> list[str]:
    """What the feed serves for one channel against its Release's
    SHA256SUMS: one line per problem, none if all is as published."""
    files = recorded(sums)
    if f"releases.{channel}.json" not in {name for name, _ in files}:
        return [f"the Release for {channel} records no releases.{channel}.json"]
    problems = []
    for name, published in files:
        actual = served(f"{feed.rstrip('/')}/{name}")
        if actual is None:
            problems.append(f"{name}: not served")
        elif actual != published:
            problems.append(f"{name}: served {actual}, published {published}")
        else:
            print(f"{name}: as published")
    return problems


def run(
    feed: str,
    releases: Iterable[Mapping[str, object]],
    download_sums: Callable[[str, str], str],
    served: Served,
) -> int:
    """Every channel with a published Release, against its latest one."""
    latest = latest_per_channel(releases)
    if not latest:
        print("::error::no published Release to compare the feed with")
        return 1
    problems = []
    for channel in CHANNELS:
        if channel not in latest:
            print(f"{channel}: no published Release yet - not checked")
            continue
        tag = latest[channel]
        print(f"{channel}: the feed against {tag}")
        problems += check_channel(channel, download_sums(tag, channel), feed, served)
    for problem in problems:
        print(f"::error::{problem}")
    return 1 if problems else 0


API = "https://api.github.com"


def _request(url: str, accept: str) -> urllib.request.Request:
    """A GitHub API request with GH_TOKEN (the Linux runner image has no
    `gh`; this needs only the standard library)."""
    headers = {"Accept": accept, "X-GitHub-Api-Version": "2022-11-28"}
    if token := os.environ.get("GH_TOKEN"):
        headers["Authorization"] = f"Bearer {token}"
    return urllib.request.Request(url, headers=headers)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Lets a redirect through as an error, so the download's storage
    address can be fetched without GitHub's token (the storage refuses a
    second credential)."""

    def redirect_request(self, *args: object, **kwargs: object) -> None:
        return None


def api_json(path: str) -> object:
    with urllib.request.urlopen(
        _request(f"{API}{path}", "application/vnd.github+json"), timeout=60
    ) as response:
        return json.load(response)


def list_releases(repo: str) -> list[dict[str, object]]:
    """Every Release of `repo`, in the keys `latest_per_channel` reads: its
    tag, whether it's a draft, and its assets' names."""
    rows: list[dict[str, object]] = []
    page = 1
    while True:
        chunk = api_json(f"/repos/{repo}/releases?per_page=100&page={page}")
        assert isinstance(chunk, list)
        rows += [
            {
                "tagName": r["tag_name"],
                "isDraft": r["draft"],
                "assets": [str(a["name"]) for a in r.get("assets", [])],
            }
            for r in chunk
        ]
        if len(chunk) < 100:
            return rows
        page += 1


def _sums_for(repo: str, tag: str, channel: str) -> str:
    """The Release's SHA256SUMS for `channel`; LookupError if it has none."""
    release = api_json(f"/repos/{repo}/releases/tags/{tag}")
    assert isinstance(release, dict)
    for asset in release.get("assets", []):
        if asset["name"] != sums_asset(channel):
            continue
        opener = urllib.request.build_opener(_NoRedirect)
        try:
            opener.open(_request(asset["url"], "application/octet-stream"), timeout=60)
        except urllib.error.HTTPError as redirect:
            if redirect.code not in (301, 302, 303, 307, 308):
                raise
            location = redirect.headers["Location"]
        else:
            raise LookupError(f"{tag}: the asset did not redirect")
        with urllib.request.urlopen(location, timeout=60) as response:
            return str(response.read().decode("utf-8"))
    raise LookupError(tag)


def _sums(tag: str, channel: str) -> str:
    """The Release's SHA256SUMS for `channel`; empty, said as an error, if
    it has none (check_channel then fails the channel)."""
    try:
        return _sums_for(os.environ["GH_REPO"], tag, channel)
    except (LookupError, urllib.error.URLError):
        print(f"::error::{tag}: no {sums_asset(channel)} on its Release")
        return ""


def _served(url: str) -> str | None:
    """The SHA-256 of what `url` serves, read in pieces (a full package is
    ~77MB); None for an HTTP error or no answer (curl -f's "not served")."""
    digest = hashlib.sha256()
    try:
        with urllib.request.urlopen(url, timeout=60) as response:
            while piece := response.read(1 << 20):
                digest.update(piece)
    except (urllib.error.URLError, TimeoutError):
        return None
    return digest.hexdigest()


def main() -> int:
    feed = os.environ.get("UPDATE_FEED", "")
    if not feed.startswith("https://"):
        print("::error::UPDATE_FEED isn't an https:// address")
        return 1
    releases = list_releases(os.environ["GH_REPO"])
    return run(feed, releases, _sums, _served)


if __name__ == "__main__":
    sys.exit(main())
