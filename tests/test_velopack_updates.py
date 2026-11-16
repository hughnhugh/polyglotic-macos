"""The updater on Velopack (decision 0017): the feed's address checked, the
options passed for a change of channel, and - for real - nothing to update
when run from source."""

from pathlib import Path
from typing import Any, ClassVar

import pytest
import velopack

from polyglotic_desktop.adapters import velopack_updates
from polyglotic_desktop.adapters.velopack_updates import (
    MAX_DELTAS,
    VelopackUpdater,
    download_size,
    feed_source,
    run_installer_hooks,
)
from polyglotic_desktop.ports.updates import DownloadFailed, FeedUnreachable, Update

FEED = "https://updates.example.org/"


def test_the_feed_is_https_or_a_folder_on_this_pc(tmp_path: Path) -> None:
    assert feed_source("https://updates.example.org") == FEED
    assert feed_source(FEED) == FEED
    assert feed_source(str(tmp_path)) == str(tmp_path.resolve())


@pytest.mark.parametrize(
    "address",
    [
        "http://updates.example.org/",  # anyone on the network could swap it
        "ftp://updates.example.org/",
        "https://",
        "C:/no/such/folder/anywhere",
    ],
)
def test_any_other_feed_is_refused(address: str) -> None:
    with pytest.raises(ValueError):
        feed_source(address)


def test_from_source_nothing_is_installed_and_the_hooks_return() -> None:
    """The real Velopack, from pytest's Python: no install to find."""
    run_installer_hooks()  # returns: not started by the installer
    assert VelopackUpdater(FEED).installed() is False


class FakeAsset:
    def __init__(self, version: str, notes: str = "", size: int = 0) -> None:
        self.Version = version
        self.NotesMarkdown = notes
        self.Size = size


class FakeInfo:
    def __init__(
        self, version: str, downgrade: bool, notes: str = "", size: int = 0
    ) -> None:
        self.TargetFullRelease = FakeAsset(version, notes, size)
        self.IsDowngrade = downgrade
        self.DeltasToTarget: list[FakeAsset] = []
        self.BaseRelease: FakeAsset | None = None


class FakeManager:
    made: ClassVar[list["FakeManager"]] = []
    feed: ClassVar[dict[str | None, FakeInfo]] = {}
    fails: ClassVar[str] = ""
    """"check" or "download": that call raises, as Velopack's do."""

    def __init__(self, source: str, options: Any) -> None:
        self.source, self.options = source, options
        self.calls: list[str] = []
        FakeManager.made.append(self)

    def check_for_updates(self) -> FakeInfo | None:
        if self.fails == "check":
            raise OSError("the feed's address didn't answer")
        return self.feed.get(self.options.ExplicitChannel)

    def download_updates(self, info: FakeInfo) -> None:
        if self.fails == "download":
            raise RuntimeError("the package's SHA-256 didn't match")
        self.calls.append(f"download {info.TargetFullRelease.Version}")

    def wait_exit_then_apply_updates(
        self, info: FakeInfo, silent: bool, restart: bool
    ) -> None:
        version = info.TargetFullRelease.Version
        self.calls.append(f"at exit {version} silent={silent} restart={restart}")

    def apply_updates_and_restart(self, info: FakeInfo) -> None:
        self.calls.append(f"restart {info.TargetFullRelease.Version}")


@pytest.fixture
def fake_velopack(monkeypatch: pytest.MonkeyPatch) -> type[FakeManager]:
    FakeManager.made = []
    FakeManager.feed = {}
    FakeManager.fails = ""
    monkeypatch.setattr(velopack_updates.velopack, "UpdateManager", FakeManager)
    return FakeManager


def test_a_newer_release_is_found_downloaded_and_restarted_into(
    fake_velopack: type[FakeManager],
) -> None:
    fake_velopack.feed = {None: FakeInfo("0.2.0", False)}
    updater = VelopackUpdater("https://updates.example.org")

    assert updater.installed() is True
    update = updater.find(None, False)
    assert update == Update("0.2.0")
    updater.download(update)
    updater.restart_into(update)

    (manager,) = fake_velopack.made
    assert manager.source == FEED
    assert manager.options.ExplicitChannel is None
    assert manager.options.AllowVersionDowngrade is False
    assert manager.calls == ["download 0.2.0", "restart 0.2.0"]


def asset(version: str, kind: str, size: int) -> velopack.VelopackAsset:
    return velopack.VelopackAsset(
        "Polyglotic", version, kind, f"{version}-{kind}.nupkg", "", "", size, "", ""
    )


def test_what_downloading_takes_is_the_deltas_when_velopack_would_use_them() -> None:
    """polyglotic-hq 345: Home's card on a metered connection says how big
    the update is - its deltas' size when Velopack would download those."""
    full = asset("0.1.7", "Full", 92_000_000)
    deltas = [asset("0.1.6", "Delta", 3_000_000), asset("0.1.7", "Delta", 2_000_000)]
    base = asset("0.1.5", "Full", 91_000_000)
    with_deltas = velopack.UpdateInfo(full, deltas, False, base)
    assert download_size(with_deltas, deltas=True) == 5_000_000
    # the signed feed: full packages only (decision 0019)
    assert download_size(with_deltas, deltas=False) == 92_000_000
    # no release here to start from, or none on the feed: the full package
    assert download_size(velopack.UpdateInfo(full, deltas, False), True) == 92_000_000
    assert download_size(velopack.UpdateInfo(full, [], False, base), True) == 92_000_000
    many = [asset(f"0.0.{n}", "Delta", 1) for n in range(MAX_DELTAS + 1)]
    assert (
        download_size(velopack.UpdateInfo(full, many, False, base), True) == 92_000_000
    )


def test_a_found_update_says_its_size(fake_velopack: type[FakeManager]) -> None:
    fake_velopack.feed = {None: FakeInfo("0.2.0", False, size=91_500_000)}
    update = VelopackUpdater("https://updates.example.org").find(None, False)
    assert update is not None and update.size == 91_500_000


def test_a_change_of_channel_allows_a_downgrade_applied_at_exit(
    fake_velopack: type[FakeManager],
) -> None:
    fake_velopack.feed = {"win-x64-beta": FakeInfo("0.1.0", True)}
    updater = VelopackUpdater(FEED)

    assert updater.find(None, False) is None
    update = updater.find("win-x64-beta", True)
    assert update == Update("0.1.0", downgrade=True)
    updater.download(update)
    updater.apply_at_exit(update)

    usual, switching = fake_velopack.made
    assert usual.options.ExplicitChannel is None
    assert usual.options.AllowVersionDowngrade is False
    assert switching.options.ExplicitChannel == "win-x64-beta"
    assert switching.options.AllowVersionDowngrade is True
    assert switching.calls == [
        "download 0.1.0",
        "at exit 0.1.0 silent=True restart=False",
    ]


def test_restart_now_applies_as_the_app_quits_then_starts_it(
    fake_velopack: type[FakeManager],
) -> None:
    """The learner's Restart now (polyglotic-hq 299): applied once the app
    has quit - its own quit, so everything is saved - and started again."""
    fake_velopack.feed = {None: FakeInfo("0.2.0", False, "### New\n\n- A thing.")}
    updater = VelopackUpdater(FEED)
    update = updater.find(None, False)
    assert update is not None and update.notes == "### New\n\n- A thing."
    updater.download(update)
    updater.apply_at_exit(update, restart=True)
    (manager,) = fake_velopack.made
    assert manager.calls == ["download 0.2.0", "at exit 0.2.0 silent=True restart=True"]


def test_a_feed_that_cant_be_read_and_a_failed_download_say_which(
    fake_velopack: type[FakeManager],
) -> None:
    """The port's errors, so Settings can say which went wrong (299)."""
    fake_velopack.feed = {None: FakeInfo("0.2.0", False)}
    updater = VelopackUpdater(FEED)
    fake_velopack.fails = "check"
    with pytest.raises(FeedUnreachable) as raised:
        updater.find(None, False)
    assert isinstance(raised.value.__cause__, OSError)
    fake_velopack.fails = "download"
    update = updater.find(None, False)
    assert update is not None
    with pytest.raises(DownloadFailed):
        updater.download(update)


def test_with_a_signed_feed_velopack_reads_only_the_checked_folder(
    fake_velopack: type[FakeManager], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Decision 0019: the feed is checked first (refresh), then Velopack is
    pointed at the checked folder, full packages only."""
    from nacl.signing import SigningKey
    from tests.test_signed_feed import public

    from polyglotic_desktop.adapters.signed_feed import FeedNotTrusted, VerifiedFeed

    refreshed: list[tuple[str, str, bool, bool]] = []
    fetched: list[str] = []

    def refresh(
        self: VerifiedFeed,
        channel: str,
        version: str,
        switching: bool,
        package: bool = True,
    ) -> Path:
        refreshed.append((channel, version, switching, package))
        return self.folder_for(channel)

    monkeypatch.setattr(VerifiedFeed, "refresh", refresh)
    monkeypatch.setattr(VerifiedFeed, "fetch_package", lambda _, c: fetched.append(c))
    fake_velopack.feed = {"win-x64-beta": FakeInfo("0.1.0", True)}
    key = public(SigningKey.generate())
    updater = VelopackUpdater(FEED, (key,), "win-x64-alpha", "0.2.0", tmp_path)

    assert updater.find(None, False) is None
    found = updater.find("win-x64-beta", True)
    assert found == Update("0.1.0", downgrade=True)

    # the feed only: the package waits for the download (polyglotic-hq 345)
    assert refreshed == [
        ("win-x64-alpha", "0.2.0", False, False),
        ("win-x64-beta", "0.2.0", True, False),
    ]
    assert fetched == []
    updater.download(found)
    assert fetched == ["win-x64-beta"]  # checked into its folder, then Velopack's
    usual, switching = fake_velopack.made
    assert usual.source == str(tmp_path / "win-x64-alpha")
    assert switching.source == str(tmp_path / "win-x64-beta")
    assert usual.options.MaximumDeltasBeforeFallback == -1

    def refuse(
        self: VerifiedFeed,
        channel: str,
        version: str,
        switching: bool,
        package: bool = True,
    ) -> Path:
        raise FeedNotTrusted("no key we trust signed this feed")

    monkeypatch.setattr(VerifiedFeed, "refresh", refuse)
    with pytest.raises(FeedUnreachable) as raised:  # a feed not trusted isn't read
        updater.find(None, False)
    assert isinstance(raised.value.__cause__, FeedNotTrusted)


def test_a_feed_check_that_failed_is_named_in_the_log(
    fake_velopack: type[FakeManager],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """polyglotic-hq 302: a tester's log said only "FeedNotTrusted" - a bad
    signature and a download cut short read the same. The check's own
    words are fixed text, never the feed's."""
    from nacl.signing import SigningKey
    from tests.test_signed_feed import public

    from polyglotic_desktop.adapters.signed_feed import FeedNotTrusted, VerifiedFeed

    def cut_short(
        self: VerifiedFeed,
        channel: str,
        version: str,
        switching: bool,
        package: bool = True,
    ) -> Path:
        raise FeedNotTrusted("a package isn't the size the feed says")

    monkeypatch.setattr(VerifiedFeed, "refresh", cut_short)
    key = public(SigningKey.generate())
    updater = VelopackUpdater(FEED, (key,), "win-x64-alpha", "0.2.0", tmp_path)
    with pytest.raises(FeedUnreachable):
        updater.find(None, False)
    assert (
        "the update feed couldn't be read (FeedNotTrusted: a package isn't the size"
        " the feed says)" in caplog.text
    )


def test_a_signed_feed_must_be_https(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        VelopackUpdater(str(tmp_path), ("AAAA",), "win-x64-alpha", "0.1.0", tmp_path)


def test_a_package_refused_at_the_download_is_named_in_the_log(
    fake_velopack: type[FakeManager],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The package is fetched by `download` now (polyglotic-hq 345): its
    check's words still reach the log (302), and nothing reaches Velopack."""
    from nacl.signing import SigningKey
    from tests.test_signed_feed import public

    from polyglotic_desktop.adapters.signed_feed import FeedNotTrusted, VerifiedFeed

    def cut_short(_: VerifiedFeed, channel: str) -> None:
        raise FeedNotTrusted("a package's download was cut short")

    monkeypatch.setattr(VerifiedFeed, "refresh", lambda self, *a, **k: tmp_path)
    monkeypatch.setattr(VerifiedFeed, "fetch_package", cut_short)
    fake_velopack.feed = {None: FakeInfo("0.3.0", False)}
    key = public(SigningKey.generate())
    updater = VelopackUpdater(FEED, (key,), "win-x64-alpha", "0.2.0", tmp_path)
    found = updater.find(None, False)
    assert found is not None
    with pytest.raises(DownloadFailed):
        updater.download(found)
    assert (
        "update 0.3.0 not downloaded (FeedNotTrusted: a package's download was cut"
        " short)" in caplog.text
    )
    assert fake_velopack.made[0].calls == []
