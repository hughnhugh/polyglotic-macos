"""A Mac updating itself (polyglotic-hq 430, decision 0202): Velopack packs the
signed Polyglotic.app (`pack.sh`), signing it again as the build does
(`macos_codesign.sh`); the release's packages are checked where they're
made (`macos_release.py`); and the app keeps the signed feed outside its
bundle. Checked here on any OS (the scripts on Linux and macOS: on Windows
a bare `bash` is WSL's); the packing and an update applied are proved on
GitHub's Mac (.github/workflows/macos.yml, `updates` and `release`)."""

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml
from tools.package import macos_release

from polyglotic_desktop.main import verified_feed_folder

PACKAGE = Path(macos_release.__file__).parent
REPO = PACKAGE.parents[1]
CHANNEL = "macos-arm64-alpha"
needs_bash = pytest.mark.skipif(
    sys.platform == "win32" or shutil.which("bash") is None,
    reason="a bare bash on Windows is WSL's (polyglotic-hq 254)",
)


def test_the_signed_feed_waits_outside_a_mac_app_and_beside_current_on_windows(
    tmp_path: Path,
) -> None:
    """The bundle's signature seals everything inside it: the checked feed
    and package written into `Contents/` would break the signature macOS
    keeps the learner's permissions under, as `exe.parent.parent` put them
    before 430. Windows' place is unchanged."""
    exe = tmp_path / "Polyglotic" / "current" / "Polyglotic.exe"
    assert verified_feed_folder(exe, system="win32") == (
        tmp_path / "Polyglotic" / "verified-feed"
    )
    app = tmp_path / "Applications" / "Polyglotic.app"
    home = tmp_path / "home"
    mac = app / "Contents" / "MacOS" / "Polyglotic"
    folder = verified_feed_folder(mac, home, system="darwin")
    assert folder == home / "Library" / "Caches" / "Polyglotic" / "verified-feed"
    assert app not in folder.parents


def test_on_linux_the_signed_feed_waits_in_the_users_cache(tmp_path: Path) -> None:
    """An AppImage is one read-only file while it runs (polyglotic-hq 550):
    the checked feed waits in $XDG_CACHE_HOME, else ~/.cache."""
    exe = "/tmp/.mount_Polyglx/usr/bin/Polyglotic"
    home = tmp_path / "home"
    cache = home / ".cache" / "Polyglotic" / "verified-feed"
    assert verified_feed_folder(exe, home, "linux", {}) == cache
    own = {"XDG_CACHE_HOME": "/srv/cache"}
    assert verified_feed_folder(exe, home, "linux", own) == Path(
        "/srv/cache/Polyglotic/verified-feed"
    )


def feed(folder: Path, version: str, package: bytes) -> Path:
    """A channel's feed listing `version`'s full package, as vpk writes it."""
    name = macos_release.full_package(version, CHANNEL)
    (folder / name).write_bytes(package)
    asset = {
        "PackageId": "Polyglotic",
        "Version": version,
        "Type": "Full",
        "FileName": name,
        "SHA1": "",
        "SHA256": hashlib.sha256(package).hexdigest().upper(),
        "Size": len(package),
    }
    path = folder / f"releases.{CHANNEL}.json"
    path.write_text(json.dumps({"Assets": [asset]}), encoding="utf-8")
    return folder / name


def test_the_feed_must_list_the_versions_full_package_as_it_is(tmp_path: Path) -> None:
    package = feed(tmp_path, "0.1.7", b"a stand-in package")
    assert macos_release.feed_problems(tmp_path, "0.1.7", CHANNEL) == []
    assert macos_release.feed_problems(tmp_path, "0.1.8", CHANNEL) == [
        f"releases.{CHANNEL}.json doesn't list Polyglotic-0.1.8-{CHANNEL}-full.nupkg once"
    ]
    package.write_bytes(b"another package")
    found = macos_release.feed_problems(tmp_path, "0.1.7", CHANNEL)
    assert any("SHA-256 isn't the feed's" in f for f in found), found
    package.unlink()
    assert macos_release.feed_problems(tmp_path, "0.1.7", CHANNEL) == [
        f"Polyglotic-0.1.7-{CHANNEL}-full.nupkg is listed but missing"
    ]


def test_an_app_velopack_can_update_has_updatemac_and_its_version(
    tmp_path: Path,
) -> None:
    app = tmp_path / "Polyglotic.app"
    (app / "Contents" / "MacOS").mkdir(parents=True)
    (app / "Contents" / "Resources").mkdir()
    assert macos_release.velopack_problems(app, "0.0.2") == [
        "no UpdateMac in the app: it can't update itself",
        "sq.version says None, not 0.0.2",
    ]
    (app / macos_release.UPDATE_MAC).write_bytes(b"")
    nuspec = "<package><metadata><id>Polyglotic</id><version>0.0.2</version></metadata></package>"
    (app / macos_release.SQ_VERSION).write_text(nuspec, encoding="utf-8")
    assert macos_release.velopack_problems(app, "0.0.2") == []
    assert macos_release.velopack_problems(app, "0.0.1") == [
        "sq.version says 0.0.2, not 0.0.1"
    ]


def test_the_requirement_must_be_the_builds_when_signed_with_the_certificate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With the certificate, an updated app must keep the built app's
    designated requirement (decision 0196); ad hoc, the requirement is the
    code's hash, which every signing changes, so it isn't compared."""
    app = tmp_path / "Polyglotic.app"
    like = tmp_path / "built" / "Polyglotic.app"
    authority = {app: ["Polyglotic Mac Signing"], like: ["Polyglotic Mac Signing"]}
    requirement = {app: 'identifier "x" and certificate root = H"1"', like: "same?"}
    monkeypatch.setattr(macos_release, "velopack_problems", lambda a, v: [])
    monkeypatch.setattr(macos_release, "authority", lambda a: authority[a])
    monkeypatch.setattr(macos_release, "requirement", lambda a: requirement[a])

    def codesign(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(["codesign", *args], 0, "", "")

    monkeypatch.setattr(macos_release, "_codesign", codesign)
    assert macos_release.app_problems(app, "0.0.2", like) == [
        "its designated requirement isn't the built app's"
    ]
    requirement[like] = requirement[app]
    assert macos_release.app_problems(app, "0.0.2", like) == []
    authority[like] = []  # ad hoc
    requirement[like] = 'cdhash H"2"'
    assert macos_release.app_problems(app, "0.0.2", like) == []


def recorder(path: Path, script: str) -> Path:
    path.write_text("#!/bin/bash\n" + script, encoding="utf-8", newline="\n")
    path.chmod(0o755)
    return path


@needs_bash
def test_vpks_codesign_signs_as_the_build_does(tmp_path: Path) -> None:
    """vpk asks for Apple's timestamp service (which refuses a self-signed
    certificate: polyglotic-hq 422) and the hardened runtime with .NET's
    entitlements; the build signs with neither."""
    seen = tmp_path / "seen"
    real = recorder(tmp_path / "codesign", f'printf "%s\\n" "$@" > "{seen}"\n')
    env = dict(os.environ, POLYGLOTIC_REAL_CODESIGN=str(real))
    vpk = ["-s", "ABC123", "-f", "-v", "--timestamp", "--options", "runtime",
           "--entitlements", "/x/velopack.entitlements", "--keychain", "/k/kc",
           "/a b/Polyglotic.app"]  # fmt: skip
    script = PACKAGE / "macos_codesign.sh"
    subprocess.run(["bash", str(script), *vpk], env=env, check=True)
    assert seen.read_text(encoding="utf-8").splitlines() == [
        "--timestamp=none", "-s", "ABC123", "-f", "-v", "--keychain", "/k/kc",
        "/a b/Polyglotic.app",
    ]  # fmt: skip
    subprocess.run(["bash", str(script), "-s", "-", "-f", "--timestamp", "/p"],
                   env=env, check=True)  # fmt: skip
    assert seen.read_text(encoding="utf-8").splitlines() == ["-s", "-", "-f", "/p"]


@needs_bash
def test_a_mac_is_packed_portable_and_signed_again_through_the_shim(
    tmp_path: Path,
) -> None:
    """pack.sh on a Mac's channel: the .app as it is, no .pkg (it would need
    Apple's installer certificate), the build's identity, only what vpk
    adds signed again - and vpk's own `codesign` call reaches
    macos_codesign.sh."""
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    args = tmp_path / "vpk-args"
    signed = tmp_path / "signed"
    recorder(
        bin_ / "dotnet",
        f'printf "%s\\n" "$@" > "{args}"\n'
        'codesign -s "$POLYGLOTIC_CODESIGN_IDENTITY" -f -v --timestamp '
        "--options runtime --entitlements e /out/Polyglotic.app\n",
    )
    real = recorder(tmp_path / "real", f'printf "%s\\n" "$@" > "{signed}"\n')
    env = dict(
        os.environ,
        PATH=f"{bin_}{os.pathsep}{os.environ['PATH']}",
        POLYGLOTIC_CODESIGN_IDENTITY="ABC123",
        POLYGLOTIC_REAL_CODESIGN=str(real),
    )
    env.pop("SIGNING_KEYCHAIN", None)
    notes = tmp_path / "notes.md"
    notes.write_text("- New", encoding="utf-8")
    subprocess.run(
        ["bash", str(PACKAGE / "pack.sh"), "0.1.7", CHANNEL, "dist/Polyglotic.app",
         "out", "", str(notes)],
        env=env, check=True,
    )  # fmt: skip
    said = args.read_text(encoding="utf-8").splitlines()
    pairs = dict(zip(said, [*said[1:], ""], strict=True))
    assert said[:2] == ["vpk", "pack"]
    assert pairs["--packDir"] == "dist/Polyglotic.app"
    assert pairs["--mainExe"] == "Polyglotic"
    assert pairs["--runtime"] == "osx-arm64"
    assert pairs["--channel"] == CHANNEL
    assert pairs["--signAppIdentity"] == "ABC123"
    assert pairs["--releaseNotes"] == str(notes)
    assert {"--noInst", "--signDisableDeep"} <= set(said)
    assert "--aumid" not in said and "--keychain" not in said
    assert signed.read_text(encoding="utf-8").splitlines() == [
        "--timestamp=none", "-s", "ABC123", "-f", "-v", "/out/Polyglotic.app",
    ]  # fmt: skip


def macos_job() -> dict[str, Any]:
    text = (REPO / ".github" / "workflows" / "macos.yml").read_text(encoding="utf-8")
    (job,) = yaml.safe_load(text)["jobs"].values()
    return dict(job)


def test_a_mac_release_is_velopacks_packages_checked_and_its_feed_left_unsigned() -> (
    None
):
    """The release part packs with pack.sh after the build and its
    signature checks, with the version's notes, checks the packages with
    macos_release and keeps them with SHA256SUMS. The feed's key is never
    on GitHub: publish-mac.sh signs the feed on the PC."""
    steps = macos_job()["steps"]
    runs = [s.get("run", "") for s in steps]
    built = next(i for i, r in enumerate(runs) if "tools.package.build" in r)
    restore = next(i for i, r in enumerate(runs) if "dotnet tool restore" in r)
    release = next(i for i, r in enumerate(runs) if "tools/package/pack.sh" in r)
    assert built < restore < release
    run = runs[release]
    assert "inputs.release" in steps[release]["if"]
    assert run.index("Authority=Polyglotic Mac Signing") < run.index("pack.sh")
    assert 'release_notes "$TAG" --out "$notes"' in run
    assert run.rstrip().endswith("shasum -a 256 -c SHA256SUMS")
    assert "tools.package.macos_release check build/package/release" in run
    assert "FEED_SIGNING_KEY" not in "\n".join(runs)
    assert all("FEED_SIGNING_KEY" not in json.dumps(s.get("env", {})) for s in steps)


def test_the_mac_updating_itself_is_rehearsed_only_when_asked() -> None:
    steps = macos_job()["steps"]
    (rehearsal,) = [s for s in steps if "macos_update_rehearsal.sh" in s.get("run", "")]
    assert "inputs.updates" in rehearsal["if"]
    assert rehearsal["timeout-minutes"] <= 30
    script = (PACKAGE / "macos_update_rehearsal.sh").read_text(encoding="utf-8")
    assert '"update_found": "0.0.2"' in script
    # Velopack restarts the updated app through `open`, from `/`, with the
    # same arguments: a relative report path was lost (run 43872700892)
    assert 'out=$(cd "$out" && pwd)' in script
    assert "macos_release app" in script and "--like" in script
    # its own copy only, removed whatever happens
    assert 'installed="$HOME/Applications/Polyglotic.app"' in script
    assert "trap cleanup EXIT" in script
