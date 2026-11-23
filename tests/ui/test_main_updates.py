"""`main`'s wiring of updates (decision 0017): core's rules on a thread of
their own, failures logged and never raised, the channel the server names
followed, and "update required" straight to the updater."""

import threading
import time
from collections.abc import Callable

import pytest
from PySide6.QtWidgets import QApplication
from tests.releases.test_updates import FakeUpdater
from tests.ui.fakes import FakeAppList, MemorySettingsStore

from polyglotic_desktop.adapters.signed_feed import FeedNotTrusted
from polyglotic_desktop.connection.reconnect import StopReason
from polyglotic_desktop.connection.session import SessionState, Status
from polyglotic_desktop.core.releases.updates import UpdateCheck, UpdateNow, Updates
from polyglotic_desktop.main import BackgroundUpdates, QtListener
from polyglotic_desktop.ports.updates import Update
from polyglotic_desktop.ui.app import ConnectionState, DesktopApp

ALPHA, BETA = "win-x64-alpha", "win-x64-beta"


def settle(updates: BackgroundUpdates) -> None:
    """Waits for the updates' thread to finish what it was given."""
    updates._worker.submit(lambda: None).result(timeout=5)


def wait_for(condition: Callable[[], bool], seconds: float = 5.0) -> None:
    deadline = time.monotonic() + seconds
    while not condition():
        assert time.monotonic() < deadline, "timed out"
        QApplication.processEvents()
        time.sleep(0.01)


def test_the_look_for_updates_runs_off_the_calling_thread() -> None:
    seen: list[str] = []

    class Recording(FakeUpdater):
        def find(self, channel: str | None, allow_downgrade: bool) -> Update | None:
            seen.append(threading.current_thread().name)
            return super().find(channel, allow_downgrade)

    updates = BackgroundUpdates(Updates(Recording({}), ALPHA))
    updates.check()
    settle(updates)
    assert seen and seen[0].startswith("updates")
    assert seen[0] != threading.current_thread().name


def test_a_failure_is_logged_never_raised(caplog: pytest.LogCaptureFixture) -> None:
    class Offline(FakeUpdater):
        def find(self, channel: str | None, allow_downgrade: bool) -> Update | None:
            raise OSError("no network")

    updates = BackgroundUpdates(Updates(Offline({}), ALPHA))
    updates.check()
    settle(updates)
    updates.at_exit()
    assert "updates: check failed (OSError)" in caplog.text
    assert "no network" not in caplog.text  # the kind of failure, not its details


def test_a_feed_check_that_failed_is_named(caplog: pytest.LogCaptureFixture) -> None:
    """302: a tester's log said only "check failed (FeedNotTrusted)" - a bad
    signature and a download cut short read the same. The check's own
    words are fixed text, never the feed's."""

    class CutShort(FakeUpdater):
        def find(self, channel: str | None, allow_downgrade: bool) -> Update | None:
            raise FeedNotTrusted("a package isn't the size the feed says")

    updates = BackgroundUpdates(Updates(CutShort({}), ALPHA))
    updates.check()
    settle(updates)
    updates.at_exit()
    assert (
        "updates: check failed (FeedNotTrusted: a package isn't the size the feed"
        " says)" in caplog.text
    )


def test_another_platforms_channel_is_logged_and_ignored(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """579: the packed Linux app, told Windows' channel by a stand-in
    server, offered Windows' 0.1.9."""
    updater = FakeUpdater({UpdateCheck(ALPHA, True): Update("0.1.9", downgrade=True)})
    updates = BackgroundUpdates(Updates(updater, "linux-x64-alpha"))
    updates.follow(ALPHA)
    settle(updates)
    updates.at_exit()
    assert updater.calls == []  # no look at Windows' feed, nothing downloaded
    assert (
        "updates: the server named another platform's channel: ignored" in caplog.text
    )


def test_the_servers_channel_is_followed_and_looked_at_once(qapp: QApplication) -> None:
    updater = FakeUpdater({UpdateCheck(BETA, True): Update("0.1.0", downgrade=True)})
    updates = BackgroundUpdates(Updates(updater, ALPHA))
    desktop = DesktopApp(MemorySettingsStore(), None, FakeAppList())
    listener = QtListener(desktop, None, updates)

    listener.status_changed(Status(SessionState.LISTENING, channel=BETA))
    listener.status_changed(Status(SessionState.LISTENING, channel=BETA))  # again
    settle(updates)
    updates.at_exit()

    assert updater.calls == [
        "find win-x64-beta True",
        "download 0.1.0",
        "apply at exit 0.1.0",
    ]
    desktop.close()


def test_update_required_goes_straight_to_the_updater(qapp: QApplication) -> None:
    updater = FakeUpdater({UpdateCheck(): Update("0.2.0")})
    updates = BackgroundUpdates(Updates(updater, ALPHA))
    desktop = DesktopApp(MemorySettingsStore(), None, FakeAppList())
    listener = QtListener(desktop, None, updates)

    listener.status_changed(
        Status(SessionState.STOPPED, stopped=StopReason.UPDATE_REQUIRED)
    )
    wait_for(lambda: "restart into 0.2.0" in updater.calls)
    settle(updates)

    assert updater.calls == [
        "find None False",
        "download 0.2.0",
        "restart into 0.2.0",
    ]
    assert desktop.connection is ConnectionState.UPDATE_NEEDED
    desktop.close()


@pytest.mark.parametrize(
    ("updater", "found"),
    [
        (FakeUpdater({UpdateCheck(): Update("0.2.0")}), UpdateNow.RESTARTING),
        (FakeUpdater({}), UpdateNow.NONE_YET),
        (FakeUpdater({}, installed=False), UpdateNow.NOT_INSTALLED),
    ],
)
def test_update_required_says_what_the_updater_found(
    qapp: QApplication, updater: FakeUpdater, found: UpdateNow
) -> None:
    """polyglotic-hq 133: "Update needed" didn't say what to do. What the
    updater found comes back to the interface thread, for Home to say."""
    updates = BackgroundUpdates(Updates(updater, ALPHA))
    desktop = DesktopApp(MemorySettingsStore(), None, FakeAppList())
    listener = QtListener(desktop, None, updates)
    told: list[tuple[object, bool]] = []
    main = threading.current_thread()
    listener.update_found.connect(
        lambda what: told.append((what, threading.current_thread() is main))
    )

    listener.status_changed(
        Status(SessionState.STOPPED, stopped=StopReason.UPDATE_REQUIRED)
    )
    wait_for(lambda: bool(told))
    assert told == [(found, True)]
    desktop.close()


def test_a_failed_update_says_whether_the_next_start_installs_one() -> None:
    class Failing(FakeUpdater):
        def restart_into(self, update: Update) -> None:
            raise OSError("couldn't restart")

    class Offline(FakeUpdater):
        def find(self, channel: str | None, allow_downgrade: bool) -> Update | None:
            raise OSError("no network")

    for updater, found in (
        (Failing({UpdateCheck(): Update("0.2.0")}), UpdateNow.DOWNLOADED),
        (Offline({}), UpdateNow.NONE_YET),
    ):
        updates = BackgroundUpdates(Updates(updater, ALPHA))
        told: list[UpdateNow] = []
        updates.update_now(told.append)
        settle(updates)
        assert told == [found]


def test_asking_the_server_again_doesnt_go_to_the_updater_again(
    qapp: QApplication,
) -> None:
    """While the server refuses this version, the session asks again every
    few minutes (137): each try is shown as "Update needed" still, but only
    a refusal goes to the updater - once per try, not twice."""
    updater = FakeUpdater({})
    updates = BackgroundUpdates(Updates(updater, ALPHA))
    desktop = DesktopApp(MemorySettingsStore(), None, FakeAppList())
    listener = QtListener(desktop, None, updates)
    refused = Status(SessionState.STOPPED, stopped=StopReason.UPDATE_REQUIRED)
    for status in (refused, Status(SessionState.CONNECTING), refused):
        listener.status_changed(status)
        QApplication.processEvents()  # queued to the interface thread
        settle(updates)
        assert desktop.connection is ConnectionState.UPDATE_NEEDED
    assert updater.calls == ["find None False"] * 2
    desktop.close()
