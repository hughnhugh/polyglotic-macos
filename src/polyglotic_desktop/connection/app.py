"""What the app tells the server about itself: its version, update channel and Windows.

Sent when redeeming an invite code and in every `hello` (protocol.md).
Never the user's name, the PC's name, or anything about the captioned app.

The version and channel are the release's: the release build writes them
into the app as `release.json` - the version from the git tag (`v0.1.0`
-> `0.1.0`), the channel it was packed for (decision 0015) and, from 313,
when it was built (decision 0104: never sent; the floor for a certificate's
dates). Run from source, there's no such file: the copy is `0.0.0` on
`win-x64-alpha` - not a release - but it tells the server the newest
release its RELEASE-NOTES.md names, whose changes its code holds, so the
server's minimum lets it in as it would that release (decision 0224).
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.resources import files
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import TYPE_CHECKING, get_args

from polyglotic_desktop.core.releases.notes import newest_released, sections

if TYPE_CHECKING:
    # imported at runtime only to read a release stamp: `protocol` brings
    # pydantic (about 0.1 s), which the window needn't wait for (136)
    from polyglotic_desktop.connection.protocol import Channel, Os

log = logging.getLogger(__name__)

RELEASE_FILE = "release.json"
FROM_SOURCE_VERSION = "0.0.0"
FIRST_CHANNEL: Channel = "win-x64-alpha"
MAC_FIRST_CHANNEL: Channel = "macos-arm64-alpha"
VERSION = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")
"""protocol.md's versions: `MAJOR.MINOR.PATCH`, no leading zeros."""


@dataclass(frozen=True, slots=True)
class Release:
    """The release this copy of the app is: its version and channel."""

    version: str
    channel: Channel
    built: datetime | None = None
    """When it was built (UTC): a time that has certainly passed, whatever
    the PC's clock says (connection.tls, decision 0104). None in a stamp
    from before 313."""


BUILT = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ")
"""The stamp's `built`: UTC to the second (`2026-11-14T05:12:00Z`)."""


def read_release(text: str) -> Release:
    """`release.json`'s contents, or ValueError: not a version protocol.md
    accepts, not a channel it knows, or a `built` that isn't a UTC time."""
    from polyglotic_desktop.connection import protocol

    channels: dict[str, Channel] = {c: c for c in get_args(protocol.Channel)}
    data = json.loads(text)
    fields = data if isinstance(data, dict) else {}
    version = fields.get("version")
    channel = channels.get(str(fields.get("channel")))
    built = fields.get("built")
    if not isinstance(version, str) or not VERSION.fullmatch(version):
        raise ValueError("release.json: the version isn't MAJOR.MINOR.PATCH")
    if channel is None:
        raise ValueError("release.json: not a known channel")
    if built is not None and not (isinstance(built, str) and BUILT.fullmatch(built)):
        raise ValueError("release.json: built isn't a UTC time")
    when = (
        datetime.strptime(built, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
        if built
        else None
    )
    return Release(version, channel, when)


def first_channel(os: Os) -> Channel:
    """The first channel of the OS's builds (`os`: protocol.md's), for a copy
    run from source: a Mac's is `macos-arm64-alpha` (polyglotic-hq 409)."""
    return MAC_FIRST_CHANNEL if os.startswith("macos-") else FIRST_CHANNEL


def this_release(
    stamped: Traversable | None = None, first: Channel = FIRST_CHANNEL
) -> Release:
    """The release the build stamped into the app; `0.0.0` on the first
    channel (`first`: the OS's) when run from source. A stamp that can't be
    read is logged and taken as `0.0.0`, which the server answers with
    `update_required` - so a broken build still updates itself."""
    file = stamped or files("polyglotic_desktop") / RELEASE_FILE
    if not file.is_file():
        return Release(FROM_SOURCE_VERSION, first)
    try:
        return read_release(file.read_text(encoding="utf-8"))
    except ValueError as e:  # json.JSONDecodeError is a ValueError
        log.error("the release stamp can't be read: %s", e)
        return Release(FROM_SOURCE_VERSION, first)


@dataclass(frozen=True, slots=True)
class AppInfo:
    app_version: str
    os: Os
    channel: Channel = FIRST_CHANNEL
    os_version: str = ""
    """The OS's version number ("10.0.26200"): feedback carries it; `hello`
    and sign-in don't."""

    @property
    def platform(self) -> str:
        """The app's platform, `os`'s first part (`windows`): all its
        session's summary says about the PC (polyglotic-server's tracking
        plan, 051)."""
        return self.os.split("-", 1)[0]

    @classmethod
    def this_app(
        cls,
        os: Os,
        os_version: str,
        stamped: Traversable | None = None,
        notes: Path | None = None,
    ) -> AppInfo:
        """This copy of the app on this OS: its name and version number come
        from the OS's adapters (`main.os_adapters`, decision 0038). A release
        build tells its stamp's version; a copy run from source (no stamp)
        the newest release its notes name (`source_version`)."""
        stamp = stamped or files("polyglotic_desktop") / RELEASE_FILE
        release = this_release(stamp, first_channel(os))
        version = release.version if stamp.is_file() else source_version(notes)
        return cls(version, os, release.channel, os_version)


def source_notes() -> Path:
    """The repo's RELEASE-NOTES.md, for a copy run from source
    (`src/polyglotic_desktop/connection/app.py` -> the repo's root). Asked
    only without a stamp: a release build never looks."""
    return Path(__file__).resolve().parents[3] / "RELEASE-NOTES.md"


def source_version(notes: Path | None = None) -> str:
    """What a copy run from source tells the server it is (decision 0224):
    the newest release its RELEASE-NOTES.md names (`notes`, by default
    `source_notes()`), whose changes its code holds - so a developer's copy
    of the code passes the server's minimum as that release would; `0.0.0`
    without notes that name one."""
    try:
        text = (notes or source_notes()).read_text(encoding="utf-8")
    except OSError:
        return FROM_SOURCE_VERSION
    newest = newest_released(sections(text))
    return (
        newest
        if newest is not None and VERSION.fullmatch(newest)
        else FROM_SOURCE_VERSION
    )
