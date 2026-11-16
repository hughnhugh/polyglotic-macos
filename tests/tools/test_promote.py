"""A build promoted to another channel with no rebuild (decision 0044):
the build's files unpacked and stamped for the channel, and the promoted
package checked to be those files byte for byte - against packages made
here in Velopack's layout (package.yml rehearses it with Velopack itself)."""

import json
import zipfile
from pathlib import Path

import pytest
from tools.package import build as package_build
from tools.package import promote
from tools.package.promote import NotTheBuild, compare, recorded_sha256, sha256, unpack

STAMP = "lib/app/_internal/polyglotic_desktop/release.json"


def manifest(channel: str) -> str:
    return f"<package><metadata><version>0.1.0</version><channel>{channel}</channel></metadata></package>"


def package(path: Path, channel: str, **changes: bytes) -> Path:
    """A full package as `vpk pack` lays it out, for `channel`."""
    files = {
        "Polyglotic.nuspec": manifest(channel).encode(),
        "lib/app/Polyglotic.exe": b"the app",
        "lib/app/_internal/python312.dll": b"python",
        STAMP: json.dumps({"version": "0.1.0", "channel": channel}).encode(),
        "lib/app/sq.version": manifest(channel).encode(),
        "lib/app/Squirrel.exe": b"velopack's updater",
        "lib/app/Polyglotic_ExecutionStub.exe": b"velopack's stub",
    }
    files.update({f"lib/app/{name}": data for name, data in changes.items()})
    with zipfile.ZipFile(path, "w") as z:
        for name, data in files.items():
            z.writestr(name, data)
    return path


@pytest.fixture
def no_qt(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        package_build, "write_icon", lambda path: path.write_bytes(b"ico")
    )


@pytest.mark.usefixtures("no_qt")
def test_the_build_is_unpacked_without_velopacks_files_and_stamped_for_the_channel(
    tmp_path: Path,
) -> None:
    build = package(
        tmp_path / "Polyglotic-0.1.0-win-x64-alpha-full.nupkg", "win-x64-alpha"
    )
    app = unpack(build, "win-x64-beta", tmp_path / "out", expected=sha256(build))
    found = sorted(p.relative_to(app).as_posix() for p in app.rglob("*") if p.is_file())
    assert found == [
        "Polyglotic.exe",
        "_internal/polyglotic_desktop/release.json",
        "_internal/python312.dll",
    ]
    assert json.loads((app / promote.STAMP).read_text(encoding="utf-8")) == {
        "version": "0.1.0",
        "channel": "win-x64-beta",
    }
    assert (tmp_path / "out" / "Polyglotic.ico").read_bytes() == b"ico"


@pytest.mark.usefixtures("no_qt")
def test_a_promoted_build_keeps_the_time_it_was_built(tmp_path: Path) -> None:
    """The stamp's `built` (decision 0104) is the build's, not the promotion's."""
    stamped = {
        "version": "0.1.0",
        "channel": "win-x64-alpha",
        "built": "2026-11-14T05:12:00Z",
    }
    build = package(
        tmp_path / "Polyglotic-0.1.0-win-x64-alpha-full.nupkg",
        "win-x64-alpha",
        **{promote.STAMP: json.dumps(stamped).encode()},
    )
    app = unpack(build, "win-x64-beta", tmp_path / "out", expected=None)
    assert json.loads((app / promote.STAMP).read_text(encoding="utf-8")) == {
        "version": "0.1.0",
        "channel": "win-x64-beta",
        "built": "2026-11-14T05:12:00Z",
    }


def test_a_build_that_isnt_the_recorded_one_isnt_unpacked(tmp_path: Path) -> None:
    build = package(tmp_path / "build.nupkg", "win-x64-alpha")
    with pytest.raises(NotTheBuild, match="recorded 00"):
        unpack(build, "win-x64-beta", tmp_path / "out", expected="00" * 32)
    assert not (tmp_path / "out").exists()


@pytest.mark.usefixtures("no_qt")
def test_a_path_outside_the_app_folder_isnt_written(tmp_path: Path) -> None:
    build = package(
        tmp_path / "build.nupkg", "win-x64-alpha", **{"../../escaped.txt": b"x"}
    )
    with pytest.raises(NotTheBuild, match="outside the app folder"):
        unpack(build, "win-x64-beta", tmp_path / "out", expected=None)
    assert not (tmp_path / "escaped.txt").exists()


def test_the_same_files_with_the_channel_changed_are_the_same_build(
    tmp_path: Path,
) -> None:
    build = package(tmp_path / "alpha.nupkg", "win-x64-alpha")
    promoted = package(tmp_path / "beta.nupkg", "win-x64-beta")
    assert compare(build, promoted, "win-x64-beta") == []
    assert (
        promote.main(
            ["compare", str(build), str(promoted), "--channel", "win-x64-beta"]
        )
        == 0
    )


@pytest.mark.parametrize(
    ("changes", "says"),
    [
        ({"Polyglotic.exe": b"a rebuild"}, "Polyglotic.exe: not the build's bytes"),
        ({"Squirrel.exe": b"another updater"}, "Squirrel.exe: not the build's bytes"),
        ({"extra.dll": b"x"}, "extra.dll: not in the build"),
        (
            {
                "_internal/polyglotic_desktop/release.json": b'{"version": "0.1.1", "channel": "win-x64-beta"}'
            },
            "not the build's stamp on win-x64-beta",
        ),
        (
            {"sq.version": manifest("win-x64-beta").replace("0.1.0", "0.1.1").encode()},
            "more than the channel",
        ),
    ],
)
def test_anything_else_changed_isnt_the_same_build(
    tmp_path: Path, changes: dict[str, bytes], says: str
) -> None:
    build = package(tmp_path / "alpha.nupkg", "win-x64-alpha")
    promoted = package(tmp_path / "beta.nupkg", "win-x64-beta", **changes)
    assert says in " ".join(compare(build, promoted, "win-x64-beta"))
    assert (
        promote.main(
            ["compare", str(build), str(promoted), "--channel", "win-x64-beta"]
        )
        == 1
    )


def test_packed_for_another_channel_than_asked_isnt_the_promotion(
    tmp_path: Path,
) -> None:
    build = package(tmp_path / "alpha.nupkg", "win-x64-alpha")
    promoted = package(tmp_path / "beta.nupkg", "win-x64-beta")
    problems = compare(build, promoted, "win-x64-stable")
    assert len(problems) == 2  # the stamp and the manifest


def test_the_recorded_sha256_is_read_from_sha256sum_lines() -> None:
    sums = f"{'ab' * 32} *Polyglotic-0.1.0-win-x64-alpha-full.nupkg\n{'cd' * 32}  summary.json\n"
    assert (
        recorded_sha256(sums, "Polyglotic-0.1.0-win-x64-alpha-full.nupkg") == "ab" * 32
    )
    with pytest.raises(NotTheBuild, match="isn't in the recorded"):
        recorded_sha256(sums, "Polyglotic-0.1.0-win-x64-beta-full.nupkg")


@pytest.mark.usefixtures("no_qt")
def test_unpack_reads_the_recorded_sha256(tmp_path: Path) -> None:
    build = package(
        tmp_path / "Polyglotic-0.1.0-win-x64-alpha-full.nupkg", "win-x64-alpha"
    )
    sums = tmp_path / "SHA256SUMS-build"
    sums.write_text(f"{sha256(build)} *{build.name}\n", encoding="utf-8")
    args = [
        "unpack",
        str(build),
        "--channel",
        "win-x64-beta",
        "--out",
        str(tmp_path / "out"),
    ]
    assert promote.main([*args, "--sums", str(sums)]) == 0
    sums.write_text(f"{'00' * 32} *{build.name}\n", encoding="utf-8")
    assert promote.main([*args, "--sums", str(sums)]) == 1
