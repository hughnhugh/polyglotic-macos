"""What a Linux release publishes (polyglotic-hq 592;
`tools/package/linux_publish_set.py`): the release's own packages, feed and
AppImage under the channel's name, checked against the feed."""

import hashlib
import json
from pathlib import Path

import pytest
from tools.package import linux_publish_set as publish

CHANNEL = "linux-x64-alpha"


def package(folder: Path, name: str, body: bytes, version: str, kind: str) -> dict:
    (folder / name).write_bytes(body)
    return {
        "PackageId": "Polyglotic",
        "Version": version,
        "Type": kind,
        "FileName": name,
        "SHA256": hashlib.sha256(body).hexdigest().upper(),
        "Size": len(body),
        "NotesMarkdown": "",
    }


def release(folder: Path, version: str = "0.1.12", *, before: bool = True) -> Path:
    """A release folder as linux_build.sh leaves it: the channel's earlier
    release downloaded beside this one's full package and delta."""
    folder.mkdir(parents=True, exist_ok=True)
    assets = []
    if before:
        assets.append(
            package(
                folder,
                f"Polyglotic-0.1.11-{CHANNEL}-full.nupkg",
                b"old",
                "0.1.11",
                "Full",
            )
        )
        assets.append(
            package(
                folder,
                f"Polyglotic-{version}-{CHANNEL}-delta.nupkg",
                b"d",
                version,
                "Delta",
            )
        )
    full = package(
        folder, f"Polyglotic-{version}-{CHANNEL}-full.nupkg", b"new", version, "Full"
    )
    full["NotesMarkdown"] = "### New\n- something"
    assets.append(full)
    (folder / f"releases.{CHANNEL}.json").write_text(
        json.dumps({"Assets": assets}), "utf-8"
    )
    (folder / f"assets.{CHANNEL}.json").write_text("[]", "utf-8")
    (folder / f"RELEASES-{CHANNEL}").write_text("x", "utf-8")
    (folder / "Polyglotic.AppImage").write_bytes(b"appimage")
    return folder


def test_the_set_is_this_versions_files_under_the_hosts_names(tmp_path: Path) -> None:
    out = tmp_path / "publish"
    noted = publish.publish_set(release(tmp_path / "release"), "0.1.12", CHANNEL, out)
    assert noted
    assert sorted(p.name for p in out.iterdir()) == sorted(
        [
            f"Polyglotic-0.1.12-{CHANNEL}-delta.nupkg",
            f"Polyglotic-0.1.12-{CHANNEL}-full.nupkg",
            f"Polyglotic-{CHANNEL}.AppImage",
            f"RELEASES-{CHANNEL}",
            "SHA256SUMS",
            f"assets.{CHANNEL}.json",
            f"releases.{CHANNEL}.json",
        ]
    )
    # the earlier release is on the host already: never uploaded again
    assert not (out / f"Polyglotic-0.1.11-{CHANNEL}-full.nupkg").exists()
    sums = (out / "SHA256SUMS").read_text("utf-8")
    appimage = hashlib.sha256(b"appimage").hexdigest()
    assert f"{appimage}  Polyglotic-{CHANNEL}.AppImage\n" in sums
    assert "\r" not in sums  # sha256sum -c on Linux reads it


def test_the_first_release_has_no_delta(tmp_path: Path) -> None:
    out = tmp_path / "publish"
    publish.publish_set(release(tmp_path / "r", before=False), "0.1.12", CHANNEL, out)
    assert not list(out.glob("*-delta.nupkg"))
    assert (out / f"Polyglotic-0.1.12-{CHANNEL}-full.nupkg").is_file()


@pytest.mark.parametrize(
    ("spoil", "said"),
    [
        (
            lambda f: (f / f"Polyglotic-0.1.12-{CHANNEL}-full.nupkg").write_bytes(
                b"neu"
            ),
            "not the SHA-256",
        ),
        (
            lambda f: (f / f"Polyglotic-0.1.12-{CHANNEL}-full.nupkg").write_bytes(
                b"other"
            ),
            "not the size",
        ),
        (
            lambda f: (f / f"Polyglotic-0.1.12-{CHANNEL}-delta.nupkg").unlink(),
            "listed, not built",
        ),
        (lambda f: (f / "Polyglotic.AppImage").unlink(), "no Polyglotic.AppImage"),
        (lambda f: (f / f"releases.{CHANNEL}.json").unlink(), "no feed"),
    ],
)
def test_a_folder_the_feed_disagrees_with_is_refused(
    tmp_path: Path, spoil, said: str
) -> None:
    folder = release(tmp_path / "release")
    spoil(folder)
    with pytest.raises(publish.NotPublishable, match=said):
        publish.publish_set(folder, "0.1.12", CHANNEL, tmp_path / "publish")
    assert not (tmp_path / "publish").exists()


def test_a_feed_with_a_newer_release_than_this_one_is_refused(tmp_path: Path) -> None:
    """The version asked for must be what installed copies take: the
    feed's newest full package."""
    folder = release(tmp_path / "release")
    with pytest.raises(
        publish.NotPublishable, match="newest full package is 0.1.12, not 0.1.11"
    ):
        publish.publish_set(folder, "0.1.11", CHANNEL, tmp_path / "publish")


def test_only_a_linux_channel(tmp_path: Path) -> None:
    with pytest.raises(publish.NotPublishable, match="not a Linux channel"):
        publish.publish_set(
            release(tmp_path / "r"), "0.1.12", "win-x64-alpha", tmp_path / "o"
        )
    with pytest.raises(publish.NotPublishable, match="not a Linux channel"):
        publish.publish_set(
            release(tmp_path / "r2"), "0.1.12", "linux-x64-canary", tmp_path / "o2"
        )


def test_rehearsal_channel_is_accepted(tmp_path: Path) -> None:
    """640: the rehearsal channel linux-x64-rehearsal uses the same publish
    set layout on the real host without touching alpha/beta/stable."""
    ch = "linux-x64-rehearsal"
    folder = tmp_path / "release"
    folder.mkdir()
    full = package(
        folder, f"Polyglotic-0.1.10-{ch}-full.nupkg", b"new", "0.1.10", "Full"
    )
    (folder / f"releases.{ch}.json").write_text(json.dumps({"Assets": [full]}), "utf-8")
    (folder / "Polyglotic.AppImage").write_bytes(b"appimage")
    out = tmp_path / "publish"
    noted = publish.publish_set(folder, "0.1.10", ch, out)
    assert not noted
    assert (out / f"Polyglotic-{ch}.AppImage").is_file()
    assert (out / f"releases.{ch}.json").is_file()
    assert (out / f"Polyglotic-0.1.10-{ch}-full.nupkg").is_file()


def test_the_command_says_why_and_whether_the_notes_are_in_the_feed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = release(tmp_path / "release")
    assert publish.main([str(folder), "0.1.12", CHANNEL, str(tmp_path / "p")]) == 0
    assert "0.1.12 on linux-x64-alpha: with its notes" in capsys.readouterr().out
    assert publish.main([str(folder), "0.1.12", CHANNEL, str(tmp_path / "p")]) == 1
    assert "isn't empty" in capsys.readouterr().err
    assert publish.main([]) == 2
