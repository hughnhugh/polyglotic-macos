"""The release stamp (decision 0015): the tag's version, checked as the
app reads it."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from tools.package import stamp

from polyglotic_desktop.connection.app import Release, read_release, this_release


def test_the_tag_names_the_version() -> None:
    assert stamp.version_from_tag("v0.1.0") == "0.1.0"
    assert stamp.version_from_tag("refs/tags/v1.20.3") == "1.20.3"


@pytest.mark.parametrize("tag", ["0.1.0", "release-0.1.0", "v0.1", "v0.1.0-rc1"])
def test_a_tag_that_isnt_a_release_writes_nothing(tag: str, tmp_path: Path) -> None:
    out = tmp_path / "release.json"
    assert stamp.main([tag, "--out", str(out)]) == 1
    assert not out.exists()


def test_a_channel_protocol_md_doesnt_know_writes_nothing(tmp_path: Path) -> None:
    out = tmp_path / "release.json"
    assert stamp.main(["v0.1.0", "--channel", "alpha", "--out", str(out)]) == 1
    assert not out.exists()


def test_the_app_reads_what_the_build_stamps(tmp_path: Path) -> None:
    out = tmp_path / "package" / "release.json"
    before = datetime.now(UTC).replace(microsecond=0)
    assert stamp.main(["v0.1.0", "--channel", "win-x64-beta", "--out", str(out)]) == 0
    release = this_release(out)
    assert (release.version, release.channel) == ("0.1.0", "win-x64-beta")
    # when it was built, in UTC: the floor for a certificate's dates (0104)
    assert release.built is not None
    assert before <= release.built <= datetime.now(UTC)


def test_a_promoted_build_keeps_its_own_build_time_or_none() -> None:
    kept = stamp.stamp("0.1.0", "win-x64-beta", "2026-11-14T05:12:00Z")
    assert json.loads(kept)["built"] == "2026-11-14T05:12:00Z"
    assert "built" not in json.loads(stamp.stamp("0.1.0", "win-x64-beta"))
    assert read_release(kept) == Release(
        "0.1.0", "win-x64-beta", datetime(2026, 11, 14, 5, 12, tzinfo=UTC)
    )
