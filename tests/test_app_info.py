"""What the app tells the server about itself: the release the build
stamped into it (decision 0015), or from source the newest release its
RELEASE-NOTES.md names (decision 0224)."""

import json
from pathlib import Path

import pytest

from polyglotic_desktop.connection.app import (
    AppInfo,
    Release,
    read_release,
    source_version,
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


NOTES = """# Release notes

## Unreleased

- Not released yet.

## 0.1.7 - 2026-11-17

- Seven.

## 0.1.6 - 2026-11-16

- Six.
"""


def notes(tmp_path: Path, text: str = NOTES) -> Path:
    file = tmp_path / "RELEASE-NOTES.md"
    file.write_text(text, encoding="utf-8")
    return file


def test_from_source_the_copy_is_0_0_0_on_the_first_channel(tmp_path: Path) -> None:
    """Not a release: Settings, what's new and the packs' `min_app` see
    `0.0.0` (decision 0224 changes only what the server is told)."""
    assert this_release(tmp_path / "release.json") == Release("0.0.0", "win-x64-alpha")


def test_from_source_the_server_is_told_the_newest_release_the_notes_name(
    tmp_path: Path,
) -> None:
    """Decision 0224: told `0.0.0`, the live server (minimum 0.1.0 on
    2026-11-18) answered a copy built from the public source
    `update_required`, so it could never caption."""
    app = AppInfo.this_app(
        "windows-11", "10.0.26200", tmp_path / "release.json", notes(tmp_path)
    )
    assert (app.app_version, app.channel) == ("0.1.7", "win-x64-alpha")


def test_from_source_without_a_released_version_in_the_notes_0_0_0(
    tmp_path: Path,
) -> None:
    missing = tmp_path / "release.json"
    assert source_version(tmp_path / "none.md") == "0.0.0"
    unreleased = notes(tmp_path, "# Release notes\n\n## Unreleased\n\n- a\n")
    assert (
        AppInfo.this_app("windows-11", "", missing, unreleased).app_version == "0.0.0"
    )


def test_a_release_build_tells_its_stamp_never_the_notes(tmp_path: Path) -> None:
    file = stamp(tmp_path, {"version": "0.1.5", "channel": "win-x64-beta"})
    app = AppInfo.this_app("windows-11", "", file, notes(tmp_path))
    assert (app.app_version, app.channel) == ("0.1.5", "win-x64-beta")
    # a broken stamp stays 0.0.0, so the server asks for an update (0015)
    broken = stamp(tmp_path, {"version": "0.1", "channel": "win-x64-beta"})
    assert AppInfo.this_app("windows-11", "", broken, notes(tmp_path)).app_version == (
        "0.0.0"
    )


def test_this_repo_run_from_source_tells_a_released_version() -> None:
    """The package carries no stamp (only release builds do), and the
    repo's RELEASE-NOTES.md names a release."""
    app = AppInfo.this_app("windows-11", "10.0.26200")
    assert app.app_version == source_version() != "0.0.0"
    assert app.channel == "win-x64-alpha"
    assert AppInfo.this_app("macos-26", "26.1").channel == "macos-arm64-alpha"


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
