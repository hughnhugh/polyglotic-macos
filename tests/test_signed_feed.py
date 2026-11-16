"""The signed feed (decisions 0019 and 0020): a feed and package we signed
are let through to a folder for Velopack; a tampered feed, a feed signed by
anyone else or for another channel, a swapped package or a path in a file
name are refused - and leave no feed for Velopack to read. And the release
workflow's half: the feed it signs is the storage's merge of the built one,
checked first."""

import base64
import hashlib
import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import ClassVar

import pytest
from nacl.signing import SigningKey
from tools.package import sign_feed

from polyglotic_desktop.adapters.signed_feed import (
    FeedNotTrusted,
    VerifiedFeed,
    fetch_to,
    public_keys,
    signed_message,
    verify,
)

BASE = "https://updates.example.org/"
CHANNEL = "win-x64-alpha"
FEED_NAME = f"releases.{CHANNEL}.json"
PACKAGE = b"PK\x03\x04 the 0.2.0 package"
OLD_PACKAGE = b"PK\x03\x04 the 0.1.0 package"


def public(key: SigningKey) -> str:
    return base64.b64encode(key.verify_key.encode()).decode()


def signature_of(key: SigningKey, feed: bytes, channel: str = CHANNEL) -> bytes:
    """The .sig file for `channel`'s feed: base64 of the 64-byte signature
    of the channel's name and the feed."""
    return base64.b64encode(key.sign(signed_message(channel, feed)).signature)


def asset(
    version: str, data: bytes, kind: str = "Full", name: str = ""
) -> dict[str, object]:
    return {
        "PackageId": "Polyglotic",
        "Version": version,
        "Type": kind,
        "FileName": name or f"Polyglotic-{version}-full.nupkg",
        "SHA1": hashlib.sha1(data).hexdigest(),
        "SHA256": hashlib.sha256(data).hexdigest(),
        "Size": len(data),
        "NotesMarkdown": "",
        "NotesHtml": "",
    }


def feed_bytes(*assets: dict[str, object]) -> bytes:
    return json.dumps({"Assets": list(assets)}).encode()


class Storage:
    """The update storage, as the app sees it over HTTPS."""

    def __init__(self, files: dict[str, bytes]) -> None:
        self.files = files
        self.asked: list[str] = []
        self.limits: list[int] = []  # the byte limit of each package download

    def get(self, url: str) -> bytes:
        self.asked.append(url.removeprefix(BASE))
        return self.files[url.removeprefix(BASE)]

    def get_to(self, url: str, path: Path, limit: int) -> None:
        self.limits.append(limit)
        path.write_bytes(self.get(url)[:limit])  # as fetch_to: no more than limit


def published(key: SigningKey, feed: bytes, package: bytes = PACKAGE) -> Storage:
    signature = signature_of(key, feed)
    return Storage(
        {
            FEED_NAME: feed,
            FEED_NAME + ".sig": signature,
            "Polyglotic-0.2.0-full.nupkg": package,
            "Polyglotic-0.1.0-full.nupkg": OLD_PACKAGE,
        }
    )


@pytest.fixture
def key() -> SigningKey:
    return SigningKey.generate()


def checked(storage: Storage, key: SigningKey, folder: Path) -> VerifiedFeed:
    return VerifiedFeed(
        BASE, public_keys([public(key)]), folder, storage.get, storage.get_to
    )


FEED = feed_bytes(asset("0.1.0", OLD_PACKAGE), asset("0.2.0", PACKAGE))


def test_a_feed_we_signed_and_its_newest_package_reach_velopacks_folder(
    key: SigningKey, tmp_path: Path
) -> None:
    storage = published(key, FEED)

    folder = checked(storage, key, tmp_path).refresh(CHANNEL, "0.1.0", switching=False)

    assert folder == tmp_path / CHANNEL
    assert (folder / FEED_NAME).read_bytes() == FEED  # exactly the signed bytes
    assert (folder / "Polyglotic-0.2.0-full.nupkg").read_bytes() == PACKAGE
    assert storage.asked == [
        FEED_NAME,
        FEED_NAME + ".sig",
        "Polyglotic-0.2.0-full.nupkg",
    ]


def test_the_feed_alone_is_checked_and_its_package_fetched_when_asked(
    key: SigningKey, tmp_path: Path
) -> None:
    """polyglotic-hq 345: a look on a metered connection finds the update
    without downloading it - the package comes with `fetch_package`, the
    learner's Download anyway or a look off a metered connection."""
    storage = published(key, FEED)
    feed = checked(storage, key, tmp_path)

    folder = feed.refresh(CHANNEL, "0.1.0", switching=False, package=False)

    assert (folder / FEED_NAME).read_bytes() == FEED
    assert storage.asked == [FEED_NAME, FEED_NAME + ".sig"]  # no package
    assert not list(folder.glob("*.nupkg*"))

    feed.fetch_package(CHANNEL)
    assert (folder / "Polyglotic-0.2.0-full.nupkg").read_bytes() == PACKAGE
    feed.fetch_package(CHANNEL)  # already there and checked: not fetched again
    assert storage.asked.count("Polyglotic-0.2.0-full.nupkg") == 1


def test_a_package_fetched_with_no_checked_feed_is_refused(
    key: SigningKey, tmp_path: Path
) -> None:
    with pytest.raises(FeedNotTrusted):
        checked(published(key, FEED), key, tmp_path).fetch_package(CHANNEL)


def test_a_swapped_package_fetched_later_is_refused(
    key: SigningKey, tmp_path: Path
) -> None:
    storage = published(key, FEED, package=b"not the signed package")
    feed = checked(storage, key, tmp_path)
    folder = feed.refresh(CHANNEL, "0.1.0", switching=False, package=False)
    with pytest.raises(FeedNotTrusted):
        feed.fetch_package(CHANNEL)
    assert not list(folder.glob("*.nupkg*"))


def test_nothing_newer_no_package_downloaded(key: SigningKey, tmp_path: Path) -> None:
    storage = published(key, FEED)
    folder = checked(storage, key, tmp_path).refresh(CHANNEL, "0.2.0", switching=False)
    assert (folder / FEED_NAME).is_file()
    assert "Polyglotic-0.2.0-full.nupkg" not in storage.asked


def test_once_installed_the_checked_package_is_removed(
    key: SigningKey, tmp_path: Path
) -> None:
    """Project 042, Low 7: the package checked for 0.2.0 stayed in the
    folder after 0.2.0 was installed - 82 MB until the next release. When
    nothing is wanted, nothing is kept (a half-downloaded one neither)."""
    storage = published(key, FEED)
    feed = checked(storage, key, tmp_path)
    folder = feed.refresh(CHANNEL, "0.1.0", switching=False)  # 0.2.0 checked
    (folder / "Polyglotic-0.2.0-full.nupkg.part").write_bytes(b"PK half")
    assert (folder / "Polyglotic-0.2.0-full.nupkg").is_file()

    feed.refresh(CHANNEL, "0.2.0", switching=False)  # 0.2.0 installed since

    assert sorted(path.name for path in folder.iterdir()) == [FEED_NAME]


def test_a_package_still_wanted_is_kept(key: SigningKey, tmp_path: Path) -> None:
    """Checked, not installed yet (Velopack applies it at the next start):
    the next check finds it there and keeps it, without downloading again."""
    storage = published(key, FEED)
    feed = checked(storage, key, tmp_path)
    feed.refresh(CHANNEL, "0.1.0", switching=False)

    folder = feed.refresh(CHANNEL, "0.1.0", switching=False)

    assert (folder / "Polyglotic-0.2.0-full.nupkg").read_bytes() == PACKAGE
    assert storage.asked.count("Polyglotic-0.2.0-full.nupkg") == 1


def test_an_older_feed_downloads_nothing(key: SigningKey, tmp_path: Path) -> None:
    """A feed whose newest release is older than this copy (an old feed
    served again, or a build installed by hand) is checked and written, but
    its package isn't fetched: Velopack never installs a lower version
    without a change of channel."""
    storage = published(key, FEED)  # newest 0.2.0
    folder = checked(storage, key, tmp_path).refresh(CHANNEL, "0.10.0", switching=False)
    assert (folder / FEED_NAME).is_file()
    assert not [asked for asked in storage.asked if asked.endswith(".nupkg")]


def test_a_tampered_feed_is_refused_and_velopack_gets_no_feed(
    key: SigningKey, tmp_path: Path
) -> None:
    storage = published(key, FEED)
    evil = asset("0.2.0", b"MZ someone else's code")
    storage.files[FEED_NAME] = feed_bytes(asset("0.1.0", OLD_PACKAGE), evil)

    with pytest.raises(FeedNotTrusted, match="no key we trust"):
        checked(storage, key, tmp_path).refresh(CHANNEL, "0.1.0", switching=False)

    assert not (tmp_path / CHANNEL / FEED_NAME).exists()
    assert "Polyglotic-0.2.0-full.nupkg" not in storage.asked


def test_one_changed_byte_is_enough_to_refuse(key: SigningKey) -> None:
    signature = signature_of(key, FEED)
    changed = FEED.replace(b"0.2.0", b"0.2.1", 1)
    with pytest.raises(FeedNotTrusted):
        verify(signed_message(CHANNEL, changed), signature, public_keys([public(key)]))


def test_another_channels_signed_feed_is_refused(
    key: SigningKey, tmp_path: Path
) -> None:
    """Project 042, Low 6: the beta's feed and signature, ours and intact,
    served under the alpha's names (by whoever holds the storage) would move
    alpha testers to the beta. The channel is inside what's signed."""
    storage = published(key, FEED)
    storage.files[FEED_NAME + ".sig"] = signature_of(key, FEED, "win-x64-beta")

    with pytest.raises(FeedNotTrusted, match="no key we trust"):
        checked(storage, key, tmp_path).refresh(CHANNEL, "0.1.0", switching=False)

    assert not (tmp_path / CHANNEL / FEED_NAME).exists()


def test_the_feed_alone_signed_is_refused(key: SigningKey) -> None:
    """A signature of the feed's bytes alone (decision 0019's first format,
    never published) doesn't pass: the channel must be in it."""
    bare = base64.b64encode(key.sign(FEED).signature)
    with pytest.raises(FeedNotTrusted):
        verify(signed_message(CHANNEL, FEED), bare, public_keys([public(key)]))


def test_a_channel_name_with_a_line_break_cant_be_signed() -> None:
    with pytest.raises(ValueError):
        signed_message("win-x64-alpha\nwin-x64-beta", FEED)


def test_a_feed_signed_by_another_key_is_refused(
    key: SigningKey, tmp_path: Path
) -> None:
    storage = published(SigningKey.generate(), FEED)  # their key, not ours
    with pytest.raises(FeedNotTrusted):
        checked(storage, key, tmp_path).refresh(CHANNEL, "0.1.0", switching=False)


@pytest.mark.parametrize("signature", [b"", b"not base64!", base64.b64encode(b"short")])
def test_a_missing_or_malformed_signature_is_refused(
    key: SigningKey, signature: bytes
) -> None:
    with pytest.raises(FeedNotTrusted):
        verify(signed_message(CHANNEL, FEED), signature, public_keys([public(key)]))


def test_a_swapped_package_is_refused_and_not_kept(
    key: SigningKey, tmp_path: Path
) -> None:
    storage = published(key, FEED, package=b"PK\x03\x04 a different package!")

    with pytest.raises(FeedNotTrusted, match="isn't the"):
        checked(storage, key, tmp_path).refresh(CHANNEL, "0.1.0", switching=False)

    assert list((tmp_path / CHANNEL).iterdir()) == []  # no package, no feed


def test_a_package_is_downloaded_no_further_than_the_signed_size(
    key: SigningKey, tmp_path: Path
) -> None:
    """Whoever holds the storage can serve a package of any length under the
    signed name; the app reads one byte past the signed size and stops, so
    it can refuse it without filling the disk."""
    storage = published(key, FEED, package=PACKAGE + b" and gigabytes more")

    with pytest.raises(FeedNotTrusted, match="isn't the size"):
        checked(storage, key, tmp_path).refresh(CHANNEL, "0.1.0", switching=False)

    assert storage.limits == [len(PACKAGE) + 1]
    assert list((tmp_path / CHANNEL).iterdir()) == []  # no package, no feed


def test_fetch_to_stops_at_the_limit(tmp_path: Path) -> None:
    served = tmp_path / "served.nupkg"
    served.write_bytes(b"x" * 3_000_000)  # more than one read block
    out = tmp_path / "part"

    fetch_to(served.as_uri(), out, 1_500_001)

    assert out.stat().st_size == 1_500_001


def test_a_path_in_a_file_name_is_refused_even_signed(
    key: SigningKey, tmp_path: Path
) -> None:
    sneaky = feed_bytes(asset("0.2.0", PACKAGE, name="../../current/Polyglotic.exe"))
    with pytest.raises(FeedNotTrusted, match="plain name"):
        checked(published(key, sneaky), key, tmp_path).refresh(
            CHANNEL, "0.1.0", switching=False
        )


def test_during_a_key_change_either_key_is_accepted(
    key: SigningKey, tmp_path: Path
) -> None:
    new = SigningKey.generate()
    storage = published(new, FEED)
    both = VerifiedFeed(
        BASE,
        public_keys([public(key), public(new)]),
        tmp_path,
        storage.get,
        storage.get_to,
    )
    assert (both.refresh(CHANNEL, "0.1.0", switching=False) / FEED_NAME).is_file()


def test_changing_channel_to_the_same_version_still_fetches_its_package(
    key: SigningKey, tmp_path: Path
) -> None:
    storage = published(key, FEED)
    folder = checked(storage, key, tmp_path).refresh(CHANNEL, "0.2.0", switching=True)
    assert (folder / "Polyglotic-0.2.0-full.nupkg").is_file()


def keys_made(capsys: pytest.CaptureFixture[str]) -> tuple[str, str]:
    """A key pair from `sign_feed generate`: (private, public)."""
    assert sign_feed.main(["generate"]) == 0
    lines = capsys.readouterr().out.splitlines()
    return lines[0].split(": ")[1].strip(), lines[1].split(": ")[1].strip()


BUILT = feed_bytes(asset("0.2.0", PACKAGE))
"""The feed `vpk pack` wrote for 0.2.0: only what it built."""
SERVED = feed_bytes(asset("0.2.0", PACKAGE), asset("0.1.0", OLD_PACKAGE))
"""The feed the storage serves after `vpk upload`: the built assets first,
then what was there before (Velopack's _ObjectStore.cs)."""


def test_what_the_release_workflow_signs_the_app_accepts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The workflow signs the feed as served - the merge - for its channel,
    and the app, fetching that feed, accepts it (decision 0020)."""
    private, public_text = keys_made(capsys)
    built, served = tmp_path / "built.json", tmp_path / FEED_NAME
    built.write_bytes(BUILT)
    served.write_bytes(SERVED)
    monkeypatch.setenv(sign_feed.KEY_VARIABLE, private)

    args = ["sign", str(served), "--channel", CHANNEL, "--built", str(built)]
    assert sign_feed.main(args) == 0

    assert private not in capsys.readouterr().out  # never printed when signing
    signature = (tmp_path / (FEED_NAME + ".sig")).read_bytes()
    storage = Storage(
        {
            FEED_NAME: SERVED,
            FEED_NAME + ".sig": signature,
            "Polyglotic-0.2.0-full.nupkg": PACKAGE,
        }
    )
    app = VerifiedFeed(
        BASE, public_keys([public_text]), tmp_path / "app", storage.get, storage.get_to
    )
    folder = app.refresh(CHANNEL, "0.1.0", switching=False)
    assert (folder / "Polyglotic-0.2.0-full.nupkg").read_bytes() == PACKAGE
    verifying = ["verify", str(served), "--key", public_text, "--channel"]
    assert sign_feed.main([*verifying, CHANNEL]) == 0
    assert sign_feed.main([*verifying, "win-x64-beta"]) == 1


def test_signing_without_a_key_signs_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(sign_feed.KEY_VARIABLE, raising=False)
    feed = tmp_path / FEED_NAME
    feed.write_bytes(FEED)
    args = ["sign", str(feed), "--channel", CHANNEL, "--built", str(feed)]
    assert sign_feed.main(args) == 1
    assert not (tmp_path / (FEED_NAME + ".sig")).exists()


def test_the_merge_vpk_uploads_is_accepted() -> None:
    """Older releases the storage had, after ours or before: a merge."""
    sign_feed.check_merge(BUILT, SERVED)
    older_first = feed_bytes(asset("0.1.0", OLD_PACKAGE), asset("0.2.0", PACKAGE))
    sign_feed.check_merge(BUILT, older_first)
    sign_feed.check_merge(BUILT, BUILT)  # the first release: nothing there before


def test_with_the_last_release_fetched_for_deltas_its_still_a_merge() -> None:
    """With UPDATE_FEED set, the last release is fetched for deltas and is
    in the built feed too: it must be served as it was."""
    delta = asset("0.2.0", b"delta", kind="Delta", name="Polyglotic-0.2.0-delta.nupkg")
    built = feed_bytes(asset("0.1.0", OLD_PACKAGE), asset("0.2.0", PACKAGE), delta)
    served = feed_bytes(asset("0.2.0", PACKAGE), delta, asset("0.1.0", OLD_PACKAGE))
    sign_feed.check_merge(built, served)


THEIRS = b"MZ someone else's code"
TAMPERED = [
    pytest.param(
        feed_bytes(asset("0.1.0", OLD_PACKAGE)),
        "built, not served",
        id="our package missing",
    ),
    pytest.param(
        feed_bytes(asset("0.2.0", THEIRS), asset("0.1.0", OLD_PACKAGE)),
        "not as built",
        id="our package changed",
    ),
    pytest.param(
        feed_bytes(asset("0.2.0", PACKAGE), asset("0.3.0", THEIRS)),
        "not built here",
        id="a newer release that isn't ours",
    ),
    pytest.param(
        feed_bytes(
            asset("0.2.0", PACKAGE),
            asset("0.2.0", THEIRS, name="Polyglotic-0.2.0-other-full.nupkg"),
        ),
        "not built here",
        id="a second package of our version",
    ),
    pytest.param(
        feed_bytes(asset("0.2.0", PACKAGE), asset("0.2.0", PACKAGE)),
        "served twice",
        id="one file name twice",
    ),
    pytest.param(
        feed_bytes(asset("0.2.0", PACKAGE), asset("0.1.0-beta", OLD_PACKAGE)),
        "a version that isn't ours",
        id="a version we never make",
    ),
    pytest.param(b"<html>not a feed</html>", "can't be read", id="not a feed"),
]


@pytest.mark.parametrize(("served", "why"), TAMPERED)
def test_a_served_feed_that_isnt_our_merge_is_refused(served: bytes, why: str) -> None:
    with pytest.raises(sign_feed.NotOurMerge, match=why):
        sign_feed.check_merge(BUILT, served)


def test_a_feed_that_isnt_our_merge_is_never_signed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    private, _ = keys_made(capsys)
    built, served = tmp_path / "built.json", tmp_path / FEED_NAME
    built.write_bytes(BUILT)
    served.write_bytes(feed_bytes(asset("0.2.0", PACKAGE), asset("0.3.0", THEIRS)))
    monkeypatch.setenv(sign_feed.KEY_VARIABLE, private)

    assert sign_feed.main(["check", str(built), str(served)]) == 1
    args = ["sign", str(served), "--channel", CHANNEL, "--built", str(built)]
    assert sign_feed.main(args) == 1

    assert not (tmp_path / (FEED_NAME + ".sig")).exists()
    assert "0.3.0-full.nupkg: as new as this release" in capsys.readouterr().err


def test_a_signed_feed_needs_https_and_keys() -> None:
    with pytest.raises(ValueError):
        VerifiedFeed(BASE, [], Path("."))


def test_a_pasted_private_key_with_a_line_break_still_signs(
    capsys: pytest.CaptureFixture[str],
) -> None:
    private, public_text = keys_made(capsys)
    key = sign_feed.private_key_from(private + "\r\n")
    assert sign_feed.public_key_text(key) == public_text


class CutShort(Storage):
    """Storage whose connection drops after `cut` bytes of a package, on
    the first try only; each try carries on from what's there, as
    `fetch_to` does (polyglotic-hq 302)."""

    def __init__(self, files: dict[str, bytes], cut: int) -> None:
        super().__init__(files)
        self.cut = cut
        self.from_byte: list[int] = []  # where each try began

    def get_to(self, url: str, path: Path, limit: int) -> None:
        have = path.stat().st_size if path.is_file() else 0
        self.from_byte.append(have)
        rest = self.get(url)[have:limit]
        if len(self.from_byte) == 1:
            rest = rest[: self.cut]
        with path.open("ab") as out:
            out.write(rest)


def test_a_download_cut_short_is_kept_and_carried_on_at_the_next_check(
    key: SigningKey, tmp_path: Path
) -> None:
    """polyglotic-hq 302: a tester's 0.1.4 (about 90 MB) was cut short on a
    connection that dropped every few minutes - "FeedNotTrusted" - and
    each try began from nothing."""
    storage = CutShort(published(key, FEED).files, cut=7)
    feed = checked(storage, key, tmp_path)

    with pytest.raises(FeedNotTrusted, match="cut short"):
        feed.refresh(CHANNEL, "0.1.0", switching=False)
    part = tmp_path / CHANNEL / "Polyglotic-0.2.0-full.nupkg.part"
    assert part.read_bytes() == PACKAGE[:7]  # kept
    assert not (tmp_path / CHANNEL / FEED_NAME).exists()  # no feed until it's whole

    folder = feed.refresh(CHANNEL, "0.1.0", switching=False)

    assert storage.from_byte == [0, 7]
    assert (folder / "Polyglotic-0.2.0-full.nupkg").read_bytes() == PACKAGE
    assert sorted(p.name for p in folder.iterdir()) == [
        "Polyglotic-0.2.0-full.nupkg",
        FEED_NAME,
    ]


def test_a_part_carried_on_into_another_package_is_refused_and_removed(
    key: SigningKey, tmp_path: Path
) -> None:
    """The part kept is trusted for nothing: carried on from, the whole is
    checked, and a mismatch starts the next try from nothing."""
    folder = tmp_path / CHANNEL
    folder.mkdir()
    part = folder / "Polyglotic-0.2.0-full.nupkg.part"
    part.write_bytes(b"XX")  # not the package's first bytes
    storage = CutShort(published(key, FEED).files, cut=len(PACKAGE))

    with pytest.raises(FeedNotTrusted, match="isn't the one"):
        checked(storage, key, tmp_path).refresh(CHANNEL, "0.1.0", switching=False)
    assert not part.exists()


def test_a_whole_part_is_checked_without_fetching_it_again(
    key: SigningKey, tmp_path: Path
) -> None:
    folder = tmp_path / CHANNEL
    folder.mkdir()
    (folder / "Polyglotic-0.2.0-full.nupkg.part").write_bytes(PACKAGE)
    (folder / "Polyglotic-0.1.0-full.nupkg.part").write_bytes(b"PK an old")
    storage = published(key, FEED)

    checked(storage, key, tmp_path).refresh(CHANNEL, "0.1.0", switching=False)

    assert storage.limits == []
    assert sorted(p.name for p in folder.iterdir()) == [
        "Polyglotic-0.2.0-full.nupkg",
        FEED_NAME,
    ]


RANGED = bytes(range(256)) * 12_000  # about 3 MB: more than one read block


class Ranges(BaseHTTPRequestHandler):
    """Serves RANGED, honouring `Range: bytes=N-` unless told not to, or
    answering it from the wrong place."""

    honour = "yes"  # "yes", "no" (the whole file, 200) or "wrong" (206 from 0)
    asked: ClassVar[list[str | None]] = []

    def do_GET(self) -> None:
        wanted = self.headers.get("Range")
        Ranges.asked.append(wanted)
        start = int(wanted.removeprefix("bytes=").rstrip("-")) if wanted else 0
        if wanted and Ranges.honour != "no":
            sent_from = start if Ranges.honour == "yes" else 0
            body = RANGED[sent_from:]
            self.send_response(206)
            self.send_header(
                "Content-Range", f"bytes {sent_from}-{len(RANGED) - 1}/{len(RANGED)}"
            )
        else:
            body = RANGED
            self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_: object) -> None:
        pass


@pytest.fixture
def ranges() -> Iterator[str]:
    Ranges.asked = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), Ranges)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}/package.nupkg"
    finally:
        server.shutdown()
        server.server_close()
        Ranges.honour = "yes"


def test_fetch_to_asks_for_only_the_rest_of_a_part(ranges: str, tmp_path: Path) -> None:
    part = tmp_path / "package.nupkg.part"
    part.write_bytes(RANGED[:1_000_000])

    fetch_to(ranges, part, len(RANGED) + 1)

    assert Ranges.asked == ["bytes=1000000-"]
    assert part.read_bytes() == RANGED


def test_fetch_to_starts_again_when_the_whole_file_comes(
    ranges: str, tmp_path: Path
) -> None:
    Ranges.honour = "no"
    part = tmp_path / "package.nupkg.part"
    part.write_bytes(RANGED[:1_000_000])

    fetch_to(ranges, part, len(RANGED) + 1)

    assert part.read_bytes() == RANGED  # not the first MB twice


def test_fetch_to_drops_a_part_answered_from_the_wrong_place(
    ranges: str, tmp_path: Path
) -> None:
    Ranges.honour = "wrong"
    part = tmp_path / "package.nupkg.part"
    part.write_bytes(RANGED[:1_000_000])

    fetch_to(ranges, part, len(RANGED) + 1)

    assert not part.exists()  # the next try starts from nothing
