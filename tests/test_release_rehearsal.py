"""A release, end to end, against stand-ins (polyglotic-hq project 081).

- A tag becomes the version the app reports in `hello`, and the channel it
  was packed for (decision 0015): tag -> stamp -> the app's reader -> the
  session's `hello` on the wire.
- `welcome.channel` reaches the update rules, which follow a channel they
  know (changing channel is the one case a lower version is allowed) and
  ignore one they don't.
- A signed feed served from a local address, fetched by the app's own
  network code (not a stand-in for it): the feed and package are let
  through; a tampered package, a tampered feed and an unsigned feed are
  refused and leave nothing for Velopack to install.
"""

import re
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import ClassVar
from urllib.error import HTTPError

import pytest
import yaml
from nacl.signing import SigningKey
from tests.fake_server import FakeServer, wait_until
from tests.test_session import Harness
from tests.test_signed_feed import (
    CHANNEL,
    FEED_NAME,
    PACKAGE,
    asset,
    feed_bytes,
    public,
    signature_of,
)
from tools.package import stamp

from polyglotic_desktop.adapters.signed_feed import (
    FeedNotTrusted,
    VerifiedFeed,
    public_keys,
)
from polyglotic_desktop.connection.app import AppInfo, this_release
from polyglotic_desktop.core.releases.updates import UpdateCheck, Updates
from polyglotic_desktop.ports.updates import Update

TAG = "v1.2.3"


@pytest.fixture
def server() -> Iterator[FakeServer]:
    fake = FakeServer()
    yield fake
    fake.stop()


def stamped(tmp_path: Path, tag: str, channel: str) -> AppInfo:
    out = tmp_path / "release.json"
    assert stamp.main([tag, "--channel", channel, "--out", str(out)]) == 0
    release = this_release(out)  # as the app reads the file in a release build
    return AppInfo(release.version, "windows-11", release.channel)


@pytest.mark.parametrize("channel", ["win-x64-alpha", "win-x64-beta", "win-x64-stable"])
def test_hello_carries_the_tags_version_and_the_channel_packed_for(
    server: FakeServer, tmp_path: Path, channel: str
) -> None:
    app = stamped(tmp_path, f"refs/tags/{TAG}", channel)
    harness = Harness(server)
    harness.session._app = app  # the release build's identity
    harness.session.start()
    try:
        wait_until(lambda: bool(server.hellos))
        hello = server.hellos[-1]
    finally:
        harness.session.stop()
    assert (hello["app_version"], hello["channel"]) == ("1.2.3", channel)


class RecordingUpdater:
    def __init__(self) -> None:
        self.looked: list[tuple[str | None, bool]] = []

    def find(self, channel: str | None, allow_downgrade: bool) -> Update | None:
        self.looked.append((channel, allow_downgrade))
        return None

    def installed(self) -> bool:
        return True


@pytest.mark.parametrize(
    ("named", "looks_at"),
    [
        ("win-x64-beta", ("win-x64-beta", True)),  # changing channel: may go lower
        ("win-x64-alpha", (None, False)),  # the one installed
        ("win-x64-nightly", (None, False)),  # unknown: ignored
        (None, (None, False)),
    ],
)
def test_the_channel_welcome_names_decides_where_the_app_looks(
    server: FakeServer, named: str | None, looks_at: tuple[str | None, bool]
) -> None:
    updater = RecordingUpdater()
    updates = Updates(updater, "win-x64-alpha")  # type: ignore[arg-type]
    if named is not None:
        server.welcome = server.welcome | {"channel": named}
    with Harness(server) as harness:
        wait_until(lambda: harness.listener.listening())
        updates.follow(harness.listener.last().channel)
    updates.check()
    assert updater.looked == [looks_at]
    assert UpdateCheck(*looks_at) == updates.wanted


# --- a signed feed served from a local address -------------------------------


class Storage(BaseHTTPRequestHandler):
    files: ClassVar[dict[str, bytes]] = {}

    def do_GET(self) -> None:
        body = self.files.get(self.path.lstrip("/"))
        self.send_response(200 if body is not None else 404)
        self.end_headers()
        self.wfile.write(body or b"")

    def log_message(self, *args: object) -> None:
        pass


@pytest.fixture
def storage() -> Iterator[tuple[str, dict[str, bytes]]]:
    files: dict[str, bytes] = {}
    handler = type("Served", (Storage,), {"files": files})
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_port}/", files
    httpd.shutdown()
    httpd.server_close()
    thread.join(timeout=5)


def serve(files: dict[str, bytes], key: SigningKey, package: bytes = PACKAGE) -> None:
    feed = feed_bytes(asset("1.2.3", PACKAGE))
    files[FEED_NAME] = feed
    files[FEED_NAME + ".sig"] = signature_of(key, feed)
    files["Polyglotic-1.2.3-full.nupkg"] = package


def check(base: str, key: SigningKey, folder: Path) -> Path:
    return VerifiedFeed(base, public_keys([public(key)]), folder).refresh(
        CHANNEL,
        "1.2.2",
        switching=False,  # the app is 1.2.2; the feed has 1.2.3
    )


def test_the_feed_and_package_from_a_local_address_are_let_through(
    storage: tuple[str, dict[str, bytes]], tmp_path: Path
) -> None:
    base, files = storage
    key = SigningKey.generate()
    serve(files, key)
    folder = check(base, key, tmp_path)
    assert (folder / "Polyglotic-1.2.3-full.nupkg").read_bytes() == PACKAGE


def test_a_tampered_package_is_refused_and_nothing_is_left(
    storage: tuple[str, dict[str, bytes]], tmp_path: Path
) -> None:
    base, files = storage
    key = SigningKey.generate()
    serve(files, key, package=PACKAGE[:-1] + b"X")  # one byte changed
    with pytest.raises(FeedNotTrusted):
        check(base, key, tmp_path)
    assert not (tmp_path / CHANNEL / "releases.win-x64-alpha.json").exists()
    assert list((tmp_path / CHANNEL).glob("*.nupkg")) == []


def test_a_tampered_feed_is_refused_and_nothing_is_left(
    storage: tuple[str, dict[str, bytes]], tmp_path: Path
) -> None:
    base, files = storage
    key = SigningKey.generate()
    serve(files, key)
    files[FEED_NAME] = files[FEED_NAME].replace(b"1.2.3", b"9.9.9")
    with pytest.raises(FeedNotTrusted):
        check(base, key, tmp_path)
    assert not (tmp_path / CHANNEL / "releases.win-x64-alpha.json").exists()
    assert list((tmp_path / CHANNEL).glob("*.nupkg")) == []


def test_a_feed_without_its_signature_is_refused(
    storage: tuple[str, dict[str, bytes]], tmp_path: Path
) -> None:
    base, files = storage
    key = SigningKey.generate()
    serve(files, key)
    del files[FEED_NAME + ".sig"]
    with pytest.raises((FeedNotTrusted, HTTPError)):  # the storage says 404
        check(base, key, tmp_path)


def test_a_dry_run_is_a_version_velopack_accepts() -> None:
    """The first dry run (2026-11-06) failed at `vpk pack`: v0.0.0 is
    refused, a package version must be >= 0.0.1."""
    workflows = Path(__file__).parent.parent / ".github" / "workflows"
    release = (workflows / "release.yml").read_text("utf-8")
    found = re.search(r"else tag=v(\d+)\.(\d+)\.(\d+); fi", release)
    assert found, "release.yml no longer names a dry run's version"
    assert tuple(map(int, found.groups())) >= (0, 0, 1)
    package = yaml.safe_load((workflows / "package.yml").read_text("utf-8"))
    assert package["env"]["TAG"] == "v0.0.1"  # Package builds the same version
