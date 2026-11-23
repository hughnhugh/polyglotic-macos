"""The daily feed check (feed-check.yml, tools/package/feed_check.py): each
channel's public feed against that channel's latest Release - not only the
newest Release overall, which once a beta exists would leave the alpha's
feed unchecked while alpha testers still run it (polyglotic-hq project 066,
Low 5). Without GitHub or the network: the Releases, their SHA256SUMS and
what the feed serves are stand-ins."""

import hashlib
from pathlib import Path

import pytest
from tools.package import feed_check

from polyglotic_desktop.core.releases import updates

REPO = Path(__file__).resolve().parents[2]
FEED = "https://updates.example.invalid/"


def release(tag: str, *channels: str, draft: bool = False) -> dict[str, object]:
    """One row of `list_releases`: a tag's Release, with a SHA256SUMS for
    each channel its build was published to (decision 0044)."""
    assets = ["SHA256SUMS-build", f"Polyglotic-{tag[1:]}-win-x64-alpha-full.nupkg"]
    return {
        "tagName": tag,
        "isDraft": draft,
        "assets": assets + [f"SHA256SUMS-{channel}" for channel in channels],
    }


RELEASES = [
    release("v0.2.0", "win-x64-beta"),  # the newest overall
    release("v0.1.1", "win-x64-alpha"),
    release("v0.1.0", "win-x64-alpha"),
    release("v0.1.2", "win-x64-alpha", draft=True),  # nothing published
]


def sums(channel: str, version: str) -> str:
    """A Release's SHA256SUMS, as publish.sh writes it (sha256sum's format)."""
    files = [
        f"releases.{channel}.json",
        f"releases.{channel}.json.sig",
        f"RELEASES-{channel}",
        f"assets.{channel}.json",
        f"Polyglotic-{channel}-Setup.exe",
        f"Polyglotic-{version}-{channel}-full.nupkg",
        f"Polyglotic-{version}-{channel}-delta.nupkg",
    ]
    return "".join(f"{hash_of(name)}  {name}\n" for name in files)


def hash_of(name: str) -> str:
    return hashlib.sha256(name.encode()).hexdigest()


def test_each_channel_follows_its_own_latest_published_release() -> None:
    assert feed_check.latest_per_channel(RELEASES) == {
        "win-x64-alpha": "v0.1.1",
        "win-x64-beta": "v0.2.0",
    }


def test_a_release_recording_no_known_channel_is_left_out() -> None:
    hotfix = release("v9.0.0")  # built, published nowhere yet
    odd = release("v9.0.1", "win-x64-nightly")
    not_a_release = {
        "tagName": "notes",
        "isDraft": False,
        "assets": ["SHA256SUMS-win-x64-alpha"],
    }
    assert feed_check.latest_per_channel([hotfix, odd, not_a_release]) == {}


def test_a_promotion_onto_an_older_tag_is_its_channels_latest() -> None:
    """v0.1.0 promoted to beta after v0.2.0 went to the alpha (decision
    0044): the beta follows v0.1.0, the alpha v0.2.0 - by version, not by
    when each Release was first published."""
    releases = [
        release("v0.2.0", "win-x64-alpha"),
        release("v0.1.0", "win-x64-alpha", "win-x64-beta"),
        release("v0.10.0", "win-x64-stable"),
        release("v0.9.0", "win-x64-stable"),
    ]
    assert feed_check.latest_per_channel(releases) == {
        "win-x64-alpha": "v0.2.0",
        "win-x64-beta": "v0.1.0",
        "win-x64-stable": "v0.10.0",
    }


def test_the_feed_signature_installer_and_full_package_are_compared() -> None:
    names = [name for name, _ in feed_check.recorded(sums("win-x64-alpha", "0.1.1"))]
    assert names == [
        "releases.win-x64-alpha.json",
        "releases.win-x64-alpha.json.sig",
        "Polyglotic-win-x64-alpha-Setup.exe",
        "Polyglotic-0.1.1-win-x64-alpha-full.nupkg",
    ]


def test_a_binary_mode_line_is_read_too() -> None:
    line = f"{hash_of('x')} *releases.win-x64-alpha.json\n"
    assert feed_check.recorded(line) == [("releases.win-x64-alpha.json", hash_of("x"))]


def served_as_published(url: str) -> str | None:
    return hash_of(url.removeprefix(FEED))


def test_a_feed_as_published_passes() -> None:
    recorded = sums("win-x64-alpha", "0.1.1")
    assert (
        feed_check.check_channel("win-x64-alpha", recorded, FEED, served_as_published)
        == []
    )


def test_a_changed_or_missing_file_fails() -> None:
    def served(url: str) -> str | None:
        name = url.removeprefix(FEED)
        if name.endswith("-Setup.exe"):
            return "0" * 64
        if name.endswith(".sig"):
            return None
        return hash_of(name)

    problems = feed_check.check_channel(
        "win-x64-alpha", sums("win-x64-alpha", "0.1.1"), FEED, served
    )
    setup = "Polyglotic-win-x64-alpha-Setup.exe"
    assert problems == [
        "releases.win-x64-alpha.json.sig: not served",
        f"{setup}: served {'0' * 64}, published {hash_of(setup)}",
    ]


def test_a_release_that_records_no_feed_for_its_channel_fails() -> None:
    """Its title and its files disagree: nothing would be checked."""
    problems = feed_check.check_channel(
        "win-x64-alpha", sums("win-x64-beta", "0.2.0"), FEED, served_as_published
    )
    assert problems == [
        "the Release for win-x64-alpha records no releases.win-x64-alpha.json"
    ]


def test_the_alpha_is_checked_after_a_beta_release() -> None:
    """The case 066 found: the newest Release is the beta's; the alpha's feed
    is still compared - with the alpha's own latest Release."""
    asked = []

    def download(tag: str, channel: str) -> str:
        asked.append(tag)
        return sums(channel, tag.removeprefix("v"))

    def served(url: str) -> str | None:
        if url.endswith("releases.win-x64-alpha.json"):
            return "f" * 64  # the alpha's feed tampered with
        return served_as_published(url)

    assert feed_check.run(FEED, RELEASES, download, served) == 1
    assert sorted(asked) == ["v0.1.1", "v0.2.0"]
    assert feed_check.run(FEED, RELEASES, download, served_as_published) == 0


def test_no_published_release_at_all_fails() -> None:
    """The check runs once UPDATE_FEED is set, which comes after a release."""
    drafts = [release("v0.1.0", "win-x64-alpha", draft=True)]
    assert (
        feed_check.run(FEED, drafts, lambda tag, channel: "", served_as_published) == 1
    )


def test_the_channels_are_the_apps_windows_ones() -> None:
    """The tool runs without the app installed, so it keeps its own list:
    Windows' - a tag's Release publishes Windows' builds only (580)."""
    windows = tuple(c for c in updates.CHANNELS if updates.platform_of(c) == "win-x64")
    assert windows == feed_check.CHANNELS


def test_the_daily_workflow_runs_the_check() -> None:
    workflow = (REPO / ".github" / "workflows" / "feed-check.yml").read_text("utf-8")
    assert "python -m tools.package.feed_check" in workflow
    assert "gh release download --pattern SHA256SUMS --dir" not in workflow


def test_the_check_needs_no_gh() -> None:
    """The Linux runner image has no `gh`: GitHub is read over HTTPS with
    GH_TOKEN."""
    source = (REPO / "tools" / "package" / "feed_check.py").read_text("utf-8")
    assert "subprocess" not in source


def test_releases_come_from_the_api_with_the_token_and_every_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GH_TOKEN", "t")
    seen: list[tuple[str, str | None]] = []

    def api_json(path: str) -> object:
        request = feed_check._request(feed_check.API + path, "x")
        seen.append((path, request.get_header("Authorization")))
        page = int(path.rsplit("=", 1)[1])
        count = 100 if page == 1 else 1
        return [
            {
                "tag_name": f"v{page}.{i}.0",
                "name": f"Polyglotic {page}.{i}.0",
                "draft": False,
                "published_at": "2026-01-01T00:00:00Z",
                "assets": [{"name": "SHA256SUMS-win-x64-alpha", "url": "u"}],
            }
            for i in range(count)
        ]

    monkeypatch.setattr(feed_check, "api_json", api_json)
    rows = feed_check.list_releases("o/r")
    assert len(rows) == 101
    assert rows[0] == {
        "tagName": "v1.0.0",
        "isDraft": False,
        "assets": ["SHA256SUMS-win-x64-alpha"],
    }
    assert [path for path, _ in seen] == [
        "/repos/o/r/releases?per_page=100&page=1",
        "/repos/o/r/releases?per_page=100&page=2",
    ]
    assert {auth for _, auth in seen} == {"Bearer t"}


def test_a_release_without_sha256sums_is_said_as_an_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("GH_REPO", "o/r")
    monkeypatch.setattr(
        feed_check,
        "api_json",
        lambda path: {"assets": [{"name": "SHA256SUMS-win-x64-beta"}]},
    )
    assert feed_check._sums("v1", "win-x64-alpha") == ""
    assert "::error::v1: no SHA256SUMS-win-x64-alpha" in capsys.readouterr().out


def _signed_linux_feed(
    channel: str = "linux-x64-alpha",
    version: str = "0.1.10",
    sign_for: str | None = None,
) -> tuple[bytes, bytes, str, str]:
    """A realistic Linux Velopack feed + valid Ed25519 signature made with PyNaCl."""
    import base64
    import json

    from nacl.signing import SigningKey

    from polyglotic_desktop.adapters.signed_feed import signed_message

    key = SigningKey.generate()
    pub = base64.b64encode(key.verify_key.encode()).decode()
    pkg = f"Polyglotic-{version}-{channel}-full.nupkg"
    feed = json.dumps(
        {
            "Assets": [
                {
                    "PackageId": "Polyglotic",
                    "Version": version,
                    "Type": "Full",
                    "FileName": pkg,
                    "SHA1": "a" * 40,
                    "SHA256": "b" * 64,
                    "Size": 123_456,
                }
            ]
        }
    ).encode("utf-8")
    sig = (
        base64.b64encode(key.sign(signed_message(sign_for or channel, feed)).signature)
        + b"\n"
    )
    return feed, sig, pub, pkg


def test_feed_keys_match_the_apps_keys() -> None:
    """`feed_check` runs with stdlib only, so it keeps a copy of `main.FEED_KEYS`."""
    from polyglotic_desktop import main

    assert feed_check.FEED_KEYS == main.FEED_KEYS


def test_linux_missing_feed_is_not_published_yet_not_a_failure(
    capsys: pytest.CaptureFixture[str],
) -> None:
    problems = feed_check.check_linux_channel(
        "linux-x64-alpha",
        FEED,
        fetch=lambda _url: (404, b""),
        answers=lambda _url: False,
    )
    assert problems == []
    assert "not published yet" in capsys.readouterr().out


@pytest.mark.parametrize("status", [500, 403, None])
def test_linux_unreachable_or_error_feed_fails(status: int | None) -> None:
    problems = feed_check.check_linux_channel(
        "linux-x64-alpha",
        FEED,
        fetch=lambda _url: (status, b""),
        answers=lambda _url: True,
    )
    assert len(problems) == 1
    assert "releases.linux-x64-alpha.json" in problems[0]


def test_linux_present_feed_with_valid_signature_and_appimage_passes() -> None:
    feed_bytes, sig_bytes, pub, pkg = _signed_linux_feed()
    files = {
        f"{FEED}releases.linux-x64-alpha.json": (200, feed_bytes),
        f"{FEED}releases.linux-x64-alpha.json.sig": (200, sig_bytes),
    }
    present = {
        f"{FEED}Polyglotic-linux-x64-alpha.AppImage",
        f"{FEED}{pkg}",
    }
    problems = feed_check.check_linux_channel(
        "linux-x64-alpha",
        FEED,
        fetch=lambda url: files.get(url, (404, b"")),
        answers=lambda url: url in present,
        keys=(pub,),
    )
    assert problems == []


def test_linux_present_feed_rejects_bad_signature_wrong_channel_or_missing_appimage() -> (
    None
):
    feed_bytes, sig_bytes, pub, pkg = _signed_linux_feed()
    present = {f"{FEED}Polyglotic-linux-x64-alpha.AppImage", f"{FEED}{pkg}"}

    # Tampered feed bytes
    tampered = feed_check.check_linux_channel(
        "linux-x64-alpha",
        FEED,
        fetch=lambda url: (
            (200, feed_bytes + b" ") if url.endswith(".json") else (200, sig_bytes)
        ),
        answers=lambda url: url in present,
        keys=(pub,),
    )
    assert any("no key we trust signed this feed" in p for p in tampered)

    # Signature made for win-x64-alpha replayed on linux-x64-alpha
    wrong_feed, wrong_sig, wrong_pub, _ = _signed_linux_feed(sign_for="win-x64-alpha")
    replayed = feed_check.check_linux_channel(
        "linux-x64-alpha",
        FEED,
        fetch=lambda url: (
            (200, wrong_feed) if url.endswith(".json") else (200, wrong_sig)
        ),
        answers=lambda url: url in present,
        keys=(wrong_pub,),
    )
    assert any("no key we trust signed this feed" in p for p in replayed)

    # Missing .sig
    no_sig = feed_check.check_linux_channel(
        "linux-x64-alpha",
        FEED,
        fetch=lambda url: (200, feed_bytes) if url.endswith(".json") else (404, b""),
        answers=lambda url: url in present,
        keys=(pub,),
    )
    assert "releases.linux-x64-alpha.json.sig: not served" in no_sig

    # AppImage doesn't answer
    no_appimage = feed_check.check_linux_channel(
        "linux-x64-alpha",
        FEED,
        fetch=lambda url: (
            (200, feed_bytes) if url.endswith(".json") else (200, sig_bytes)
        ),
        answers=lambda url: url == f"{FEED}{pkg}",
        keys=(pub,),
    )
    assert no_appimage == ["Polyglotic-linux-x64-alpha.AppImage: not served"]

    # Newest full package doesn't answer
    no_pkg = feed_check.check_linux_channel(
        "linux-x64-alpha",
        FEED,
        fetch=lambda url: (
            (200, feed_bytes) if url.endswith(".json") else (200, sig_bytes)
        ),
        answers=lambda url: url.endswith(".AppImage"),
        keys=(pub,),
    )
    assert no_pkg == [f"{pkg}: not served"]


def test_run_checks_windows_and_linux_channels_together() -> None:
    feed_bytes, sig_bytes, pub, pkg = _signed_linux_feed()
    download = lambda tag, channel: sums(channel, tag.removeprefix("v"))
    # Missing Linux feed -> still passes
    assert (
        feed_check.run(
            FEED,
            RELEASES,
            download,
            served_as_published,
            fetch_bytes=lambda _url: (404, b""),
            answers=lambda _url: False,
            keys=(pub,),
        )
        == 0
    )
    # Present Linux feed with missing AppImage -> fails
    assert (
        feed_check.run(
            FEED,
            RELEASES,
            download,
            served_as_published,
            fetch_bytes=lambda url: (
                (200, feed_bytes) if url.endswith(".json") else (200, sig_bytes)
            ),
            answers=lambda url: url == f"{FEED}{pkg}",
            keys=(pub,),
        )
        == 1
    )
    # Present Linux feed with valid sig + AppImage + package -> passes
    assert (
        feed_check.run(
            FEED,
            RELEASES,
            download,
            served_as_published,
            fetch_bytes=lambda url: (
                (200, feed_bytes) if url.endswith(".json") else (200, sig_bytes)
            ),
            answers=lambda url: (
                url in {f"{FEED}Polyglotic-linux-x64-alpha.AppImage", f"{FEED}{pkg}"}
            ),
            keys=(pub,),
        )
        == 0
    )
