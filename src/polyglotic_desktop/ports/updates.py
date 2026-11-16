"""What the app needs from its installer to update itself (decision 0017).

`Updater` looks for a newer release on a channel's feed, downloads it, and
applies it - at the next start, or now. Implemented by Velopack
(`adapters/velopack_updates.py`); core's Releases decides when
(`core/releases/updates.py`).
"""

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True, slots=True)
class Update:
    """A release on the feed this copy could move to. `downgrade`: a lower
    or equal version, which only a change of channel may bring. `notes`:
    its release notes as the feed carries them (Markdown, RELEASE-NOTES.md's
    section for it), "" when the feed has none; `size`: the bytes this
    copy would download for it - its deltas' when the installer would use
    them, else the full package's - 0 when not known (polyglotic-hq 345).
    Neither is part of what makes two the same release."""

    version: str
    downgrade: bool = False
    notes: str = field(default="", compare=False)
    size: int = field(default=0, compare=False)


class FeedUnreachable(Exception):
    """The feed couldn't be read, or couldn't be trusted (its signature):
    nothing is known about a newer release. `find` raises it."""


class DownloadFailed(Exception):
    """The release was found but couldn't be downloaded, or wasn't what
    the feed said it was. `download` raises it."""


class Updater(Protocol):
    def installed(self) -> bool:
        """Installed by the installer: False when run from source, or from
        the packed folder without installing - nothing to update then."""
        ...

    def find(self, channel: str | None, allow_downgrade: bool) -> Update | None:
        """The newest release on `channel`'s feed (None: the channel this
        copy was installed from), if this copy should move to it.
        `FeedUnreachable` when the feed can't be read or trusted."""
        ...

    def download(self, update: Update) -> None:
        """Fetches `update` (checked against the feed's size and SHA-256)
        and keeps it, ready for the next start. `DownloadFailed` on
        failure."""
        ...

    def apply_at_exit(self, update: Update, restart: bool = False) -> None:
        """Applies a downloaded `update` once the app has exited - for what
        the next start won't apply by itself, or (`restart`) to start the
        new version once it's applied: the learner's Restart now."""
        ...

    def restart_into(self, update: Update) -> None:
        """Applies a downloaded `update` now: the app exits and starts
        again as the new version."""
        ...
