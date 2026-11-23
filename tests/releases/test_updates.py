"""When the app updates itself (decision 0017): core's rules against a
fake updater - look and download quietly, apply at the next start, the
server's channel followed, a downgrade only when changing channel,
"update required" straight to the updater."""

from typing import get_args

from polyglotic_desktop.connection.protocol import Channel
from polyglotic_desktop.core.releases.updates import (
    CHANNELS,
    Found,
    RestartOffer,
    UpdateCheck,
    UpdateNow,
    Updates,
    check_for,
    whats_new,
)
from polyglotic_desktop.ports.updates import DownloadFailed, FeedUnreachable, Update

ALPHA, BETA = "win-x64-alpha", "win-x64-beta"
NEWER = Update("0.2.0")


class FakeUpdater:
    def __init__(self, feed: dict[UpdateCheck, Update], installed: bool = True) -> None:
        self.feed = feed
        self.is_installed = installed
        self.calls: list[str] = []
        self.fails = ""  # "find" or "download": that call fails

    def installed(self) -> bool:
        return self.is_installed

    def find(self, channel: str | None, allow_downgrade: bool) -> Update | None:
        self.calls.append(f"find {channel} {allow_downgrade}")
        if self.fails == "find":
            raise FeedUnreachable("OSError")
        return self.feed.get(UpdateCheck(channel, allow_downgrade))

    def download(self, update: Update) -> None:
        self.calls.append(f"download {update.version}")
        if self.fails == "download":
            raise DownloadFailed("OSError")

    def apply_at_exit(self, update: Update, restart: bool = False) -> None:
        self.calls.append(
            f"apply at exit {update.version}" + (" and start" if restart else "")
        )

    def restart_into(self, update: Update) -> None:
        self.calls.append(f"restart into {update.version}")


def test_a_newer_release_is_downloaded_once_and_left_for_the_next_start() -> None:
    updater = FakeUpdater({UpdateCheck(): NEWER})
    updates = Updates(updater, ALPHA)

    assert updates.check() == NEWER
    assert updates.check() == NEWER
    updates.at_exit()

    assert updater.calls == [
        "find None False",
        "download 0.2.0",
        "find None False",  # looked again; already downloaded
    ]  # nothing restarts or applies it: the next start does


def test_nothing_newer_nothing_downloaded() -> None:
    updater = FakeUpdater({})
    assert Updates(updater, ALPHA).check() is None
    assert updater.calls == ["find None False"]


def test_run_from_source_nothing_is_looked_for() -> None:
    updater = FakeUpdater({UpdateCheck(): NEWER}, installed=False)
    updates = Updates(updater, ALPHA)
    assert updates.check() is None
    assert updates.update_now() is UpdateNow.NOT_INSTALLED  # "install the newest"
    assert updater.calls == []


def test_update_required_goes_straight_to_the_updater() -> None:
    updater = FakeUpdater({UpdateCheck(): NEWER})
    assert Updates(updater, ALPHA).update_now() is UpdateNow.RESTARTING
    assert updater.calls == [
        "find None False",
        "download 0.2.0",
        "restart into 0.2.0",
    ]


def test_update_required_with_nothing_on_the_feed_restarts_nothing() -> None:
    updater = FakeUpdater({})
    assert Updates(updater, ALPHA).update_now() is UpdateNow.NONE_YET
    assert updater.calls == ["find None False"]


def test_a_downgrade_is_allowed_only_when_the_server_names_another_channel() -> None:
    assert check_for(ALPHA, None) == UpdateCheck()
    assert check_for(ALPHA, ALPHA) == UpdateCheck()
    assert check_for(ALPHA, BETA) == UpdateCheck(BETA, allow_downgrade=True)
    assert check_for(BETA, "win-x64-stable") == UpdateCheck(
        "win-x64-stable", allow_downgrade=True
    )


def test_a_channel_this_app_doesnt_know_is_ignored() -> None:
    assert check_for(ALPHA, "win-x64-canary") == UpdateCheck()
    assert check_for(ALPHA, "") == UpdateCheck()


def test_another_platforms_channel_is_never_followed() -> None:
    """579 (from 574): a stand-in server named Windows' channel, and the
    packed Linux app offered Windows' 0.1.9 from Windows' feed."""
    linux, mac = "linux-x64-alpha", "macos-arm64-alpha"
    assert check_for(linux, ALPHA) == UpdateCheck()
    assert check_for(mac, BETA) == UpdateCheck()
    assert check_for(ALPHA, "macos-arm64-beta") == UpdateCheck()
    updater = FakeUpdater({UpdateCheck(ALPHA, True): Update("0.1.9", downgrade=True)})
    updates = Updates(updater, linux)
    assert updates.another_platforms(ALPHA) and not updates.another_platforms(None)
    assert not updates.follow(ALPHA)  # nothing changes where to look
    assert updates.check() is None and updater.calls == ["find None False"]


def test_its_own_platforms_channel_is_still_followed() -> None:
    assert not Updates(FakeUpdater({}), ALPHA).another_platforms(BETA)
    assert check_for(ALPHA, BETA) == UpdateCheck(BETA, allow_downgrade=True)


MAC = ("macos-arm64-alpha", "macos-arm64-beta", "macos-arm64-stable")
LINUX = ("linux-x64-alpha", "linux-x64-beta", "linux-x64-stable")
WINDOWS = (ALPHA, BETA, "win-x64-stable")


def test_a_mac_app_follows_its_test_groups_mac_channel() -> None:
    """580: only Windows' channels were known, so a Mac app ignored the
    beta or stable channel the server named and stayed on the alpha."""
    assert check_for(MAC[0], "macos-arm64-beta") == UpdateCheck(
        "macos-arm64-beta", allow_downgrade=True
    )
    assert check_for(MAC[1], "macos-arm64-stable") == UpdateCheck(
        "macos-arm64-stable", allow_downgrade=True
    )
    lower = Update("0.1.6", downgrade=True)
    updater = FakeUpdater({UpdateCheck("macos-arm64-beta", True): lower})
    updates = Updates(updater, MAC[0])
    assert updates.follow("macos-arm64-beta") is True  # where to look changed
    assert updates.check() == lower
    assert updater.calls == ["find macos-arm64-beta True", "download 0.1.6"]


def test_a_linux_app_follows_its_test_groups_linux_channel() -> None:
    """580: the same for Linux's builds."""
    assert check_for(LINUX[0], "linux-x64-stable") == UpdateCheck(
        "linux-x64-stable", allow_downgrade=True
    )
    assert check_for(LINUX[2], "linux-x64-beta") == UpdateCheck(
        "linux-x64-beta", allow_downgrade=True
    )
    updates = Updates(FakeUpdater({}), LINUX[0])
    assert updates.follow("linux-x64-stable") is True


def test_neither_follows_the_others_or_windows_channel() -> None:
    """Every installed channel against every channel the server might
    name: followed only when it's another of its own platform's (579, 580)."""
    for own in (WINDOWS, MAC, LINUX):
        for installed in own:
            for named in (*WINDOWS, *MAC, *LINUX):
                followed = named in own and named != installed
                expected = UpdateCheck(named, True) if followed else UpdateCheck()
                assert check_for(installed, named) == expected, (installed, named)


def test_every_channel_an_app_can_be_stamped_with_is_followed() -> None:
    """The protocol's channels - what a build stamps into the app and says
    in `hello` - are all channels core follows: the Mac's were added to the
    protocol (409) but not here (580)."""
    assert set(get_args(Channel)) <= set(CHANNELS)


def test_another_channels_release_is_downloaded_and_a_downgrade_applied_at_exit() -> (
    None
):
    lower = Update("0.1.0", downgrade=True)
    updater = FakeUpdater({UpdateCheck(BETA, True): lower})
    updates = Updates(updater, ALPHA)

    assert updates.follow(BETA) is True  # where to look changed
    assert updates.follow(BETA) is False
    assert updates.check() == lower
    updates.at_exit()

    assert updater.calls == [
        "find win-x64-beta True",
        "download 0.1.0",
        "apply at exit 0.1.0",  # the next start wouldn't apply a lower version
    ]


def test_back_on_the_installed_channel_no_downgrade() -> None:
    updater = FakeUpdater({})
    updates = Updates(updater, BETA)
    updates.follow(ALPHA)
    assert updates.follow(BETA) is True  # back where it was installed from
    updates.check()
    assert updater.calls == ["find None False"]


def test_the_store_copy_looks_for_nothing_and_says_update_from_the_store() -> None:
    """The Microsoft Store's copy (decision 0056): the Store installs each
    new package, so the app neither looks nor downloads - whatever channel
    the server names - and "update required" sends the learner to the
    Store, not to us for an installer."""
    updates = Updates(None, ALPHA)
    assert updates.check() is None
    assert updates.follow(BETA) is False  # nothing to look for again
    assert updates.check() is None
    assert updates.update_now() is UpdateNow.FROM_STORE
    updates.at_exit()  # nothing to apply
    assert updates.downloaded is None


# -- the offer: "Version X is ready. Restart to install" (polyglotic-hq 299) ----------


def test_a_look_says_what_it_found() -> None:
    """What Settings says: up to date, ready, the feed out of reach, the
    download failed - failures are outcomes, and the next look tries again."""
    updater = FakeUpdater({})
    updates = Updates(updater, ALPHA)
    assert updates.look() is Found.UP_TO_DATE
    updater.fails = "find"
    assert updates.look() is Found.NO_FEED
    updater.feed = {UpdateCheck(): NEWER}
    updater.fails = "download"
    assert updates.look() is Found.NOT_DOWNLOADED
    assert updates.downloaded is None
    updater.fails = ""
    assert updates.look() is Found.READY
    assert updates.downloaded == NEWER
    assert (
        Updates(FakeUpdater({}, installed=False), ALPHA).look() is Found.NOT_INSTALLED
    )
    assert Updates(None, ALPHA).look() is Found.NOT_INSTALLED  # the Store's copy


def test_restart_now_applies_it_as_the_app_quits_and_starts_the_new_version() -> None:
    updater = FakeUpdater({UpdateCheck(): NEWER})
    updates = Updates(updater, ALPHA)
    updates.look()
    assert updates.restart_when_quitting() == NEWER
    updates.at_exit()
    assert updater.calls[-1] == "apply at exit 0.2.0 and start"


def test_without_restart_now_quitting_leaves_it_for_the_next_start() -> None:
    updater = FakeUpdater({UpdateCheck(): NEWER})
    updates = Updates(updater, ALPHA)
    updates.look()
    updates.at_exit()
    assert not any(call.startswith("apply") for call in updater.calls)


def test_restart_now_with_nothing_downloaded_applies_nothing() -> None:
    updater = FakeUpdater({})
    updates = Updates(updater, ALPHA)
    updates.look()
    assert updates.restart_when_quitting() is None
    updates.at_exit()
    assert updater.calls == ["find None False"]


def test_the_offer_asks_until_later_then_not_until_the_next_start() -> None:
    """Later stops the asking for this run: the looks every few hours find
    the same update - or a newer one - and don't ask again."""
    offer = RestartOffer()
    assert offer.asking is None
    assert offer.found(NEWER)  # asked now
    assert offer.asking == NEWER
    assert not offer.found(NEWER)  # the next look: nothing new to say
    offer.later()
    assert offer.asking is None
    assert not offer.found(Update("0.3.0"))  # a newer one: still not asked
    assert offer.ready == Update("0.3.0")  # the tray still offers it
    assert RestartOffer().asking is None  # the next start asks afresh


def test_whats_new_is_the_notes_first_two_items_in_plain_words() -> None:
    notes = (
        "A paragraph first.\n\n"
        "### New\n\n"
        "- **Hear a word:** the speaker on a word's card says it aloud. Again\n"
        "  more slowly on the next click.\n"
        "- Text size: Settings > App > Text size, see [Help](https://x.example).\n"
        "- A third.\n\n"
        "### Fixed\n\n"
        "- Something fixed.\n"
    )
    assert whats_new(notes) == (
        "Hear a word: the speaker on a word's card says it aloud.",
        "Text size: Settings > App > Text size, see Help.",
    )


def test_whats_new_cuts_a_long_line_at_a_word() -> None:
    long = "- " + " ".join(["word"] * 60) + "\n"
    (line,) = whats_new(long, chars=40)
    assert len(line) <= 40 and line.endswith("…") and " wor…" not in line


def test_no_notes_no_whats_new() -> None:
    assert whats_new("") == ()
    assert whats_new("### New\n\nJust a paragraph.") == ()


# -- on a metered connection (polyglotic-hq 345) -----------------------------------------


def test_on_a_metered_connection_an_update_is_found_not_downloaded() -> None:
    updater = FakeUpdater({UpdateCheck(): NEWER})
    metered = [True]
    updates = Updates(updater, ALPHA, lambda: metered[0])

    assert updates.look() is Found.METERED
    assert updates.held == NEWER and updates.downloaded is None
    assert updater.calls == ["find None False"]  # nothing downloaded

    metered[0] = False  # the next look, on a connection that isn't
    assert updates.look() is Found.READY
    assert updates.held is None and updates.downloaded == NEWER
    assert updater.calls[-1] == "download 0.2.0"


def test_download_anyway_downloads_what_was_held() -> None:
    updater = FakeUpdater({UpdateCheck(): NEWER})
    updates = Updates(updater, ALPHA, lambda: True)
    assert updates.look() is Found.METERED

    updater.fails = "download"
    assert updates.download_anyway() is Found.NOT_DOWNLOADED
    assert updates.held == NEWER  # still held: Download anyway again
    updater.fails = ""
    assert updates.download_anyway() is Found.READY
    assert updates.downloaded == NEWER and updates.held is None
    assert updates.look() is Found.READY  # still metered: already downloaded
    assert updater.calls.count("download 0.2.0") == 2


def test_download_anyway_with_nothing_held_does_nothing() -> None:
    updater = FakeUpdater({})
    updates = Updates(updater, ALPHA, lambda: True)
    assert updates.look() is Found.UP_TO_DATE
    assert updates.download_anyway() is Found.UP_TO_DATE
    assert Updates(None, ALPHA).download_anyway() is Found.UP_TO_DATE  # the Store's
    assert updater.calls == ["find None False"]


def test_update_required_downloads_even_on_a_metered_connection() -> None:
    """Without it there are no captions at all."""
    updater = FakeUpdater({UpdateCheck(): NEWER})
    updates = Updates(updater, ALPHA, lambda: True)
    assert updates.update_now() is UpdateNow.RESTARTING
    assert updater.calls == ["find None False", "download 0.2.0", "restart into 0.2.0"]


def test_nothing_on_the_feed_any_more_nothing_held() -> None:
    updater = FakeUpdater({UpdateCheck(): NEWER})
    updates = Updates(updater, ALPHA, lambda: True)
    updates.look()
    updater.feed = {}
    assert updates.look() is Found.UP_TO_DATE and updates.held is None


def test_unmetered_the_connection_isnt_asked_about_once_downloaded() -> None:
    asked: list[int] = []

    def metered() -> bool:
        asked.append(1)
        return False

    updater = FakeUpdater({UpdateCheck(): NEWER})
    updates = Updates(updater, ALPHA, metered)
    updates.check()
    updates.check()
    assert len(asked) == 1  # only before a download


def test_the_offer_asks_to_download_anyway_until_one_is_ready_or_later() -> None:
    offer = RestartOffer()
    assert offer.found(None, held=NEWER)
    assert offer.asking is None and offer.asking_to_download == NEWER
    assert not offer.found(None, held=NEWER)  # the next look: nothing new
    assert offer.found(NEWER)  # downloaded: Restart now instead
    assert offer.asking == NEWER and offer.asking_to_download is None
    later = RestartOffer()
    later.found(None, held=NEWER)
    later.later()
    assert later.asking_to_download is None


# -- Linux: not writable and apply on quit (polyglotic-hq 640) --------------------------


def test_not_writable_is_its_own_outcome() -> None:
    """640: an AppImage in a read-only folder raises NotWritable, so look()
    and download_anyway() report Found.NOT_WRITABLE instead of a generic
    download failure."""
    from polyglotic_desktop.ports.updates import NotWritable

    class ReadOnlyUpdater(FakeUpdater):
        def download(self, update: Update) -> None:
            self.calls.append(f"download {update.version}")
            raise NotWritable("NotWritable")

    updates = Updates(ReadOnlyUpdater({UpdateCheck(): NEWER}), "linux-x64-alpha")
    assert updates.look() is Found.NOT_WRITABLE
    assert updates.downloaded is None

    metered = Updates(
        ReadOnlyUpdater({UpdateCheck(): NEWER}), "linux-x64-alpha", lambda: True
    )
    assert metered.look() is Found.METERED
    assert metered.held == NEWER
    assert metered.download_anyway() is Found.NOT_WRITABLE
    assert metered.held is None


def test_apply_on_quit_applies_a_downloaded_update_on_normal_exit() -> None:
    """640: on Linux, a downloaded update applies as the app quits (without
    restarting), so Quit applies it through at_exit()."""
    updater = FakeUpdater({UpdateCheck(): NEWER})
    updates = Updates(updater, "linux-x64-alpha", apply_on_quit=True)
    assert updates.look() is Found.READY
    updates.at_exit()
    assert updater.calls == ["find None False", "download 0.2.0", "apply at exit 0.2.0"]
