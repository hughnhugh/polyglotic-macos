"""When the app updates itself (decision 0017).

The rules (polyglotic-hq ENGINEERING.md, "Releases"; project 032's
checklist for D5, item 9):
- **Look early and quietly:** at start, before the rest of the app is
  built, and every few hours while it runs; download in the background.
- **Apply at the next start, never mid-capture:** the installer applies a
  newer downloaded version when the app next starts. Nothing restarts the
  app by itself while it runs, except -
- **`update_required` goes straight to the updater:** the server has
  refused this version, so no captions can come until it's updated:
  download if needed and restart into it now. What it found
  (`UpdateNow`) tells the learner what to do while there's nothing to
  restart into (polyglotic-hq 137).
- **Follow the channel the server names** (`welcome.channel`) when it's one
  this app knows, for its own platform's builds - never another's: a
  Linux app told Windows' channel offered Windows' 0.1.9 (polyglotic-hq
  579, from 574) - **a lower version only when changing channel**
  (`AllowVersionDowngrade` nowhere else). The installer doesn't apply a
  lower version by itself at start, so a downgrade applies as the app
  exits.
- **A downloaded update is offered, never forced** (polyglotic-hq 299;
  the user, 2026-11-13: "Updates should happen automatically and pop up
  to install it"): "Version X is ready", with what's new in two lines
  (`whats_new`), Restart now and Later - where the learner looks, never
  over what they're doing (`RestartOffer`). Restart now applies it as the
  app quits and starts the new version (`restart_when_quitting`); Later
  stops the asking until the next start, which installs it anyway. What a
  look found (`Found`) is what Settings says.
- **On a metered connection, an update waits for the learner**
  (polyglotic-hq 345): a look on a connection Windows calls metered -
  the same check the dictionary packs make (decision 0122) - finds the
  update but doesn't download it (`held`, `Found.METERED`); Home's card
  says how big it is and offers Download anyway (`download_anyway`). The
  next look on a connection that isn't metered downloads it as before.
  "Update required" downloads whatever the connection: without it there
  are no captions at all.
- **The Microsoft Store's copy updates through the Store** (decision
  0056): the app looks for nothing and downloads nothing - the Store
  installs each new package - and "update required" tells the learner to
  get it from the Store.

No I/O here: `Updates` asks the `Updater` port, on whatever thread `main`
gives it - one at a time.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from polyglotic_desktop.core.releases.notes import plain_items
from polyglotic_desktop.ports.updates import (
    DownloadFailed,
    FeedUnreachable,
    NotWritable,
    Update,
    Updater,
)

CHANNELS = (
    "win-x64-alpha",
    "win-x64-beta",
    "win-x64-stable",
    "macos-arm64-alpha",
    "macos-arm64-beta",
    "macos-arm64-stable",
    "linux-x64-alpha",
    "linux-x64-beta",
    "linux-x64-stable",
)
"""The update channels (protocol.md): names fixed once testers install.
Each platform's alpha, beta and stable - Windows', the Mac's and Linux's,
as their builds are stamped and polyglotic-server's `channel_for` names
them - so a Mac or Linux app follows its test group to a beta or stable
channel, never another platform's (`check_for`; polyglotic-hq 580: only
Windows' were listed, so a Mac or Linux app ignored every channel the
server named)."""

CHECK_EVERY_HOURS = 6


class UpdateNow(StrEnum):
    """What `update_now` found - what the learner is told while the server
    refuses this version."""

    RESTARTING = "restarting"
    """Downloaded: the app restarts into it now."""
    DOWNLOADED = "downloaded"
    """Downloaded, but not restarted into: it installs at the next start."""
    NONE_YET = "none_yet"
    """Nothing newer on the feed yet, or the feed couldn't be reached."""
    NOT_INSTALLED = "not_installed"
    """Not installed by the installer: this copy can't update itself."""
    FROM_STORE = "from_store"
    """The Microsoft Store's copy: the Store updates it, and the learner can
    ask it to now."""


class Found(StrEnum):
    """What a look for an update found - what Settings says of it."""

    UP_TO_DATE = "up_to_date"
    """Nothing newer on the feed."""
    READY = "ready"
    """Downloaded: it installs at the next start, or now with a restart."""
    NO_FEED = "no_feed"
    """The feed couldn't be read (no internet, the address down) or
    trusted: it's looked at again later."""
    NOT_DOWNLOADED = "not_downloaded"
    """Found, but the download failed: tried again at the next look."""
    NOT_WRITABLE = "not_writable"
    """Found, not downloaded: the app's folder can't be changed by this
    user (e.g. a Linux AppImage in /opt or a read-only mount), so an
    update can't replace it (polyglotic-hq 640)."""
    METERED = "metered"
    """Found, not downloaded: the connection is metered, and the learner
    hasn't said Download anyway (`Updates.held`)."""
    NOT_INSTALLED = "not_installed"
    """Not installed by the installer: this copy can't update itself."""


@dataclass(frozen=True, slots=True)
class UpdateCheck:
    """Where to look: `channel` None for the one this copy came from; a
    lower version allowed only when changing channel."""

    channel: str | None = None
    allow_downgrade: bool = False


def platform_of(channel: str) -> str:
    """A channel's platform and processor - all but its last part
    (`win-x64-alpha` -> `win-x64`): what the server keeps when it moves an
    app to its test group's channel (polyglotic-server's `channel_for`)."""
    return channel.rsplit("-", 1)[0]


def another_platforms(installed_channel: str, server_channel: str | None) -> bool:
    """Whether the server named a channel for another platform's builds -
    which this app never follows (579)."""
    if not server_channel:
        return False
    return platform_of(server_channel) != platform_of(installed_channel)


def check_for(installed_channel: str, server_channel: str | None) -> UpdateCheck:
    """The installed channel, unless the server names another channel this
    app knows, for its own platform's builds - then that one, and its
    newest release even if lower. A channel this app doesn't know is
    ignored (protocol.md's versioning rule 1), and so is another
    platform's (579)."""
    if (
        server_channel in CHANNELS
        and server_channel != installed_channel
        and not another_platforms(installed_channel, server_channel)
    ):
        return UpdateCheck(server_channel, allow_downgrade=True)
    return UpdateCheck()


class Updates:
    """This copy's updates: what to look for, what's downloaded, when it
    applies."""

    def __init__(
        self,
        updater: Updater | None,
        installed_channel: str,
        metered: Callable[[], bool] = lambda: False,
        apply_on_quit: bool = False,
    ) -> None:
        """`updater` None: the Microsoft Store's copy, which the Store
        updates - nothing here looks, downloads or applies. `metered`:
        whether Windows calls the connection metered now. `apply_on_quit`:
        on Linux, a downloaded AppImage update applies as the app quits
        rather than at the next start (decision 0259, polyglotic-hq 640)."""
        self._updater = updater
        self._installed_channel = installed_channel
        self._metered = metered
        self._apply_on_quit = apply_on_quit
        self._server_channel: str | None = None
        self.downloaded: Update | None = None
        self.held: Update | None = None
        """Found on a metered connection, not downloaded: Download anyway
        fetches it."""
        self._restart = False

    @property
    def wanted(self) -> UpdateCheck:
        return check_for(self._installed_channel, self._server_channel)

    def another_platforms(self, server_channel: str | None) -> bool:
        """Whether `server_channel` is for another platform's builds: not
        followed (`check_for`)."""
        return another_platforms(self._installed_channel, server_channel)

    def follow(self, server_channel: str | None) -> bool:
        """The channel the server's `welcome` named. True if that changes
        where to look (check again then)."""
        before = self.wanted
        self._server_channel = server_channel
        return self._updater is not None and self.wanted != before

    def check(self, metered_ok: bool = False) -> Update | None:
        """Looks for an update and downloads it, to apply at the next
        start - on a metered connection only with `metered_ok`, else it's
        `held`. Returns what's downloaded (None: nothing to update to, held,
        or not installed by the installer)."""
        if self._updater is None or not self._updater.installed():
            return None
        wanted = self.wanted
        update = self._updater.find(wanted.channel, wanted.allow_downgrade)
        self.held = None
        if update is None:
            return None
        if update != self.downloaded:
            if not metered_ok and self._metered():
                self.held = update
                return None
            self._updater.download(update)
            self.downloaded = update
        return update

    def look(self) -> Found:
        """`check`, saying what it found: a feed that can't be read and a
        download that fails are outcomes here, not errors - the app looks
        again later. Anything else the updater raises is raised."""
        if self._updater is None or not self._updater.installed():
            return Found.NOT_INSTALLED
        try:
            update = self.check()
        except FeedUnreachable:
            return Found.NO_FEED
        except NotWritable:
            return Found.NOT_WRITABLE
        except DownloadFailed:
            return Found.NOT_DOWNLOADED
        if self.held is not None:
            return Found.METERED
        return Found.UP_TO_DATE if update is None else Found.READY

    def download_anyway(self) -> Found:
        """The learner's Download anyway: the update held on a metered
        connection is downloaded now. READY once it is; NOT_WRITABLE if the
        folder can't take the new file; NOT_DOWNLOADED if it fails (held
        still); UP_TO_DATE when nothing was held."""
        held = self.held
        if self._updater is None or held is None:
            return Found.UP_TO_DATE
        try:
            self._updater.download(held)
        except NotWritable:
            self.held = None
            return Found.NOT_WRITABLE
        except DownloadFailed:
            return Found.NOT_DOWNLOADED
        self.downloaded, self.held = held, None
        return Found.READY

    def restart_when_quitting(self) -> Update | None:
        """The learner chose Restart now: what's downloaded applies as the
        app quits, and the new version starts. Returns it (None: nothing to
        restart into - the app then just quits)."""
        self._restart = self.downloaded is not None
        return self.downloaded

    def update_now(self) -> UpdateNow:
        """The server needs a newer app (`update_required`): download what
        the feed has and restart into it. Says what it found when there's
        nothing to restart into - not installed, or no newer release on the
        feed yet. A failure to download or restart raises; `downloaded`
        then says whether the next start installs one."""
        if self._updater is None:
            return UpdateNow.FROM_STORE
        if not self._updater.installed():
            return UpdateNow.NOT_INSTALLED
        update = self.check(metered_ok=True)  # no captions without it
        if update is None:
            return UpdateNow.NONE_YET
        self._updater.restart_into(update)
        return UpdateNow.RESTARTING

    def at_exit(self) -> None:
        """The app is quitting. After Restart now, what's downloaded applies
        and the new version starts; otherwise, on Linux (`apply_on_quit`) or
        for a downloaded downgrade (a change of channel), it applies now,
        and elsewhere a newer version is left for the next start."""
        if self._updater is None or self.downloaded is None:
            return
        if self._restart:
            self._updater.apply_at_exit(self.downloaded, restart=True)
        elif self._apply_on_quit or self.downloaded.downgrade:
            self._updater.apply_at_exit(self.downloaded)


class RestartOffer:
    """Whether the learner is asked to restart into a downloaded update
    (polyglotic-hq 299) - or, on a metered connection, to download one
    anyway (345): asked once one is ready; after Later, not again
    until the next start - whatever the looks every few hours find, a newer
    version included. It never restarts the app itself: only the learner's
    Restart now does, so captions and dictation are never cut off."""

    def __init__(self) -> None:
        self.ready: Update | None = None
        """The update downloaded, ready to restart into."""
        self.held: Update | None = None
        """Found on a metered connection, not downloaded (345) - while none
        is ready."""
        self._later = False

    def found(self, update: Update | None, held: Update | None = None) -> bool:
        """A look's update (None: nothing downloaded), and the one `held`
        on a metered connection. True if what's asked changed."""
        before = (self.asking, self.asking_to_download)
        self.ready = update
        self.held = None if update is not None else held
        return (self.asking, self.asking_to_download) != before

    def later(self) -> None:
        """Later: not asked again until the next start."""
        self._later = True

    @property
    def asking(self) -> Update | None:
        """The update the learner is asked to restart into, if any."""
        return None if self._later else self.ready

    @property
    def asking_to_download(self) -> Update | None:
        """The update the learner is asked to download anyway, on a metered
        connection, if any - the same Later stops it."""
        return None if self._later else self.held


WHATS_NEW_LINES = 2
WHATS_NEW_CHARS = 110
"""What's new in the offer: the notes' first lines, each one sentence cut
to about this long."""

_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=\S)")


def whats_new(
    notes: str, lines: int = WHATS_NEW_LINES, chars: int = WHATS_NEW_CHARS
) -> tuple[str, ...]:
    """What's new, from a release's notes (RELEASE-NOTES.md's section, as
    Markdown): the first `lines` items - New before Better and Fixed, as
    the file has them - each in plain text: its first sentence, cut at a
    word to at most `chars`, with an ellipsis. () when there are none."""
    said = []
    for item in plain_items(notes)[:lines]:
        text = _SENTENCE_END.split(item, maxsplit=1)[0].strip()
        if len(text) > chars:
            text = text[: chars - 1].rsplit(" ", 1)[0].rstrip(" ,;:-") + "…"
        said.append(text)
    return tuple(said)
