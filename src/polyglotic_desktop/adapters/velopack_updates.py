"""Updates through Velopack, the installer (decision 0017).

`run_installer_hooks()` must be the first thing the app does: when the
installer starts the app to run an install, update or uninstall hook,
Velopack handles it and exits; and a downloaded newer version is applied
here, before anything else starts. `VelopackUpdater` is the `Updater` port:
the feed's address is `https://updates.<domain>/` (main.UPDATES) or, for
trying it on this PC, a local folder - never plain `http://`, where anyone
on the network could swap the feed. Velopack checks each package's size
and SHA-256 against the feed (project 032, section 2).

With a signed feed (public keys given: decision 0019), Velopack never
reads the network: `signed_feed.VerifiedFeed` checks the feed's signature
and the package's SHA-256 into a folder, and Velopack reads that folder
(full packages only). `find` checks the feed only; the package is
fetched by `download` - so a look on a metered connection, which finds
but doesn't download, fetches no package (polyglotic-hq 345).

Run from source - or from the packed folder without installing - Velopack
finds no install: `installed()` is False and nothing else is called.

What fails says where (polyglotic-hq 299): reading or trusting the feed
raises `FeedUnreachable`, the download `DownloadFailed` - each with
Velopack's (or the network's) own error as its cause, for the log. A
release's notes come with it (`Update.notes`) when the feed has them
(`vpk pack --releaseNotes`), and what downloading it would take
(`Update.size`, `download_size`): its deltas' size when Velopack would use
them, else the full package's - always the full package's on the signed
feed (polyglotic-hq 345).
"""

from __future__ import annotations

import functools
import logging
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

import velopack

from polyglotic_desktop.ports.updates import DownloadFailed, FeedUnreachable, Update

if TYPE_CHECKING:
    from polyglotic_desktop.adapters.signed_feed import VerifiedFeed

log = logging.getLogger(__name__)

MAX_DELTAS = 10  # Velopack's default: more deltas than this, a full package
NO_DELTAS = -1  # Velopack: full packages only


def download_size(info: velopack.UpdateInfo, deltas: bool) -> int:
    """The bytes Velopack downloads for `info`: its deltas, when they're
    allowed (`deltas`: not the signed feed's full packages only), this copy
    has the release they start from, and there are at most `MAX_DELTAS` of
    them - else the full package. An estimate: a delta that fails falls
    back to the full package."""
    steps = list(info.DeltasToTarget)
    if deltas and info.BaseRelease is not None and 0 < len(steps) <= MAX_DELTAS:
        return sum(step.Size for step in steps)
    return int(info.TargetFullRelease.Size)


def run_installer_hooks() -> None:
    """Velopack's start-up: the installer's hooks (they exit), and a
    downloaded newer version applied now, by restarting into it - the "next
    start" updates apply at. Does nothing when not installed."""
    velopack.App().set_auto_apply_on_startup(True).run()


def feed_source(address: str) -> str:
    """The feed: an `https://` address, or a folder on this PC (for trying
    updates). ValueError for anything else - plain `http://` above all."""
    parts = urlsplit(address)
    if parts.scheme == "https" and parts.hostname:
        return address if address.endswith("/") else address + "/"
    if "://" not in address and Path(address).is_dir():
        return str(Path(address).resolve())
    raise ValueError("the update feed must be https:// or a folder on this PC")


class VelopackUpdater:
    """The `Updater` port on Velopack's `UpdateManager`. With `keys` (the
    signed feed's public keys, base64), `installed_channel`,
    `installed_version` and a `verified` folder, the feed is checked
    before Velopack reads it (decision 0019)."""

    def __init__(
        self,
        feed: str,
        keys: tuple[str, ...] = (),
        installed_channel: str = "",
        installed_version: str = "",
        verified: Path | None = None,
        open_url: Callable[..., Any] | None = None,
    ) -> None:
        """`open_url`: how the signed feed's files are fetched - main's is
        connection.tls's (decision 0104); urllib's own when None."""
        self._source = feed_source(feed)
        self._signed: VerifiedFeed | None = None
        if keys:
            # nacl and urllib.request (about 45 ms), only for a signed feed:
            # the updater is built before the window (136)
            from polyglotic_desktop.adapters.signed_feed import (
                VerifiedFeed,
                fetch,
                fetch_to,
                public_keys,
            )

            if verified is None or not self._source.startswith("https://"):
                raise ValueError("a signed feed needs https:// and a folder")
            self._signed = VerifiedFeed(
                self._source,
                public_keys(keys),
                verified,
                functools.partial(fetch, open_url=open_url),
                functools.partial(fetch_to, open_url=open_url),
            )
        self._installed_channel = installed_channel
        self._installed_version = installed_version
        self._found: dict[
            Update, tuple[velopack.UpdateInfo, velopack.UpdateManager]
        ] = {}
        self._channel_of: dict[Update, str] = {}
        """The channel each update was found on (the signed feed's folder)."""
        self._managers: dict[tuple[str | None, bool], velopack.UpdateManager] = {}

    def _manager(self, channel: str | None, downgrade: bool) -> velopack.UpdateManager:
        key = (channel, downgrade)
        if key not in self._managers:
            options = velopack.UpdateOptions(
                AllowVersionDowngrade=downgrade,
                MaximumDeltasBeforeFallback=MAX_DELTAS
                if self._signed is None
                else NO_DELTAS,
                ExplicitChannel=channel,
            )
            source = self._source
            if self._signed is not None:  # the checked folder, never the network
                source = str(
                    self._signed.folder_for(channel or self._installed_channel)
                )
            self._managers[key] = velopack.UpdateManager(source, options)
        return self._managers[key]

    def installed(self) -> bool:
        try:
            self._manager(None, False)
        except Exception as e:  # noqa: BLE001 - Velopack raises its own errors here
            log.info(
                "not installed by the installer: no updates (%s)", type(e).__name__
            )
            return False
        return True

    def find(self, channel: str | None, allow_downgrade: bool) -> Update | None:
        try:
            if self._signed is not None:  # FeedNotTrusted stops here
                # the feed only: the package waits for `download`, which a
                # metered connection may hold back (polyglotic-hq 345)
                self._signed.refresh(
                    channel or self._installed_channel,
                    self._installed_version,
                    switching=channel is not None,
                    package=False,
                )
            manager = self._manager(channel, allow_downgrade)
            info = manager.check_for_updates()
        except Exception as e:  # Velopack's, the network's, FeedNotTrusted
            from polyglotic_desktop.adapters.signed_feed import failure_named

            log.warning("the update feed couldn't be read (%s)", failure_named(e))
            raise FeedUnreachable(type(e).__name__) from e
        if info is None:
            return None
        target = info.TargetFullRelease
        update = Update(
            target.Version,
            info.IsDowngrade,
            target.NotesMarkdown or "",
            download_size(info, deltas=self._signed is None),
        )
        self._found[update] = (info, manager)
        self._channel_of[update] = channel or self._installed_channel
        log.info(
            "update found: %s%s, %.1f MB to download",
            update.version,
            " (downgrade)" if update.downgrade else "",
            update.size / 1_000_000,
        )
        return update

    def download(self, update: Update) -> None:
        info, manager = self._found[update]
        try:
            if self._signed is not None:  # checked into its folder first
                self._signed.fetch_package(self._channel_of[update])
            manager.download_updates(info)
        except Exception as e:  # Velopack's, the network's, FeedNotTrusted
            from polyglotic_desktop.adapters.signed_feed import failure_named

            log.warning(
                "update %s not downloaded (%s)", update.version, failure_named(e)
            )
            raise DownloadFailed(type(e).__name__) from e
        log.info("update downloaded: %s", update.version)

    def apply_at_exit(self, update: Update, restart: bool = False) -> None:
        info, manager = self._found[update]
        manager.wait_exit_then_apply_updates(info, silent=True, restart=restart)
        log.info(
            "update %s applies as the app exits%s",
            update.version,
            ", then starts" if restart else "",
        )

    def restart_into(self, update: Update) -> None:
        info, manager = self._found[update]
        log.info("restarting into update %s", update.version)
        manager.apply_updates_and_restart(info)
