"""What the app tells the server about itself: the release the build
stamped into it (decision 0015), or `0.0.0` from source."""

import json
from pathlib import Path

import pytest

from polyglotic_desktop.connection.app import (
    AppInfo,
    Release,
    read_release,
    this_release,
)
from polyglotic_desktop.connection.protocol import Channel


def stamp(tmp_path: Path, content: object) -> Path:
    file = tmp_path / "release.json"
    file.write_text(
        content if isinstance(content, str) else json.dumps(content), encoding="utf-8"
    )
    return file


def test_a_release_build_reports_its_stamped_version_and_channel(
    tmp_path: Path,
) -> None:
    file = stamp(tmp_path, {"version": "0.1.0", "channel": "win-x64-alpha"})
    assert this_release(file) == Release("0.1.0", "win-x64-alpha")


def test_from_source_the_app_is_0_0_0_on_the_first_channel(tmp_path: Path) -> None:
    assert this_release(tmp_path / "release.json") == Release("0.0.0", "win-x64-alpha")
    # and the package itself carries no stamp: only release builds do
    assert AppInfo.this_app("windows-11", "10.0.26200").app_version == "0.0.0"
    assert AppInfo.this_app("windows-11", "10.0.26200").channel == "win-x64-alpha"


@pytest.mark.parametrize(
    "content",
    [
        {"version": "v0.1.0", "channel": "win-x64-alpha"},  # the tag, not the version
        {"version": "0.1", "channel": "win-x64-alpha"},
        {"version": "01.2.3", "channel": "win-x64-alpha"},
        {"version": "0.1.0-beta", "channel": "win-x64-alpha"},
        {"version": "0.1.0", "channel": "alpha"},
        {"version": "0.1.0"},
        ["0.1.0", "win-x64-alpha"],
        "not json",
        # when it was built: UTC to the second, or nothing (0104)
        {"version": "0.1.0", "channel": "win-x64-alpha", "built": "2026-11-14"},
        {"version": "0.1.0", "channel": "win-x64-alpha", "built": 1763097120},
        {
            "version": "0.1.0",
            "channel": "win-x64-alpha",
            "built": "2026-11-14T05:12:00+11:00",
        },
    ],
)
def test_a_stamp_protocol_md_wouldnt_accept_is_refused(content: object) -> None:
    with pytest.raises(ValueError):
        read_release(content if isinstance(content, str) else json.dumps(content))


def test_a_broken_stamp_is_taken_as_0_0_0_so_the_server_asks_for_an_update(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    file = stamp(tmp_path, {"version": "0.1", "channel": "win-x64-beta"})
    assert this_release(file) == Release("0.0.0", "win-x64-alpha")
    assert "release stamp can't be read" in caplog.text


def test_every_channel_protocol_md_knows_can_be_stamped(tmp_path: Path) -> None:
    channels: tuple[Channel, ...] = ("win-x64-alpha", "win-x64-beta", "win-x64-stable")
    for channel in channels:
        file = stamp(tmp_path, {"version": "1.20.300", "channel": channel})
        assert this_release(file) == Release("1.20.300", channel)


def test_the_platform_is_the_first_part_of_os() -> None:
    """The content-free platform the session's summary names (051)."""
    assert AppInfo("0.1.0", "windows-11").platform == "windows"
    assert AppInfo("0.1.0", "windows-10").platform == "windows"
