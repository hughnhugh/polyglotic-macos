"""Linux's release check (polyglotic-hq 574; 546's section 3): the workflow
the release script starts on the public Linux copy, and the verdict it ends
with (`tools/linux_release_verdict.py`). The checks themselves run on
GitHub's runners (`.github/workflows/linux-release.yml`)."""

import json
from pathlib import Path

import pytest
import yaml

from tools import linux_release_verdict as verdict

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "linux-release.yml"


def workflow() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def everything_passed(parts: Path) -> None:
    """Each part as its job leaves it, every line passing."""
    package = parts / "package"
    for system in ("ubuntu-24.04", "ubuntu-26.04", "fedora-45"):
        (package / f"linkage-{system}").mkdir(parents=True)
        (package / f"linkage-{system}" / "linkage.txt").write_text(
            f"== {system}\npass every library the app loads on X11 is found\n"
            "pass the app's own check passes (--check-install) (exit 0)\n",
            encoding="utf-8",
        )
    for part in ("updates", "fedora-update"):
        (package / part).mkdir(parents=True)
        (package / part / "summary.txt").write_text(
            "pass applied as the app exited: the file is 0.1.12\n", encoding="utf-8"
        )
    (parts / "capture").mkdir()
    (parts / "capture" / "summary.txt").write_text(
        "pass the sound server's capture tests (system, mic, one app)\n"
        "pass the keyring tests, unlocked\npass the keyring tests, locked\n",
        encoding="utf-8",
    )
    for desktop in verdict.DESKTOPS:
        tour(parts, desktop, [])


def tour(parts: Path, desktop: str, failing: list[str]) -> None:
    names = [
        "the token is kept where the app looks",
        "the AppImage started and stayed up",
        "signed in to the stand-in with the kept token (its hello)",
        "everything the PC plays was captioned",
        "the mic was captioned",
        "the caption window shows",
        "over the full-screen window, the caption window is what's drawn",
        "Home follows the desktop's dark scheme",
        "its menu entry is written, starting this AppImage",
        "one app: the app chosen was captioned on its own source",
        "no crash in its log",
    ]
    folder = parts / f"tour-{desktop}"  # its artifact: the folder's contents
    folder.mkdir(parents=True, exist_ok=True)
    checks = [{"check": n, "ok": n not in failing, "detail": ""} for n in names]
    (folder / "checks.json").write_text(
        json.dumps({"checks": checks}), encoding="utf-8"
    )


def test_every_part_passing_is_a_pass(tmp_path: Path) -> None:
    everything_passed(tmp_path)
    found = verdict.verdict(tmp_path)
    assert list(found) == list(verdict.CHECKS)
    assert all(f.ok for f in found.values()), {k: f.failed for k, f in found.items()}
    assert verdict.main([str(tmp_path), "--out", str(tmp_path / "v.json")]) == 0
    assert json.loads((tmp_path / "v.json").read_text(encoding="utf-8"))["ok"] is True


@pytest.mark.parametrize(
    ("failing", "red"),
    [
        ("over the full-screen window, the caption window is what's drawn", "windows"),
        ("the mic was captioned", "capture"),
        ("one app: the app chosen was captioned on its own source", "capture"),
        ("signed in to the stand-in with the kept token (its hello)", "keyring"),
        ("the AppImage started and stayed up", "starts"),
        ("Home follows the desktop's dark scheme", "manners"),
        ("its menu entry is written, starting this AppImage", "manners"),
    ],
)
def test_a_desktops_red_check_is_its_checks_red(
    tmp_path: Path, failing: str, red: str
) -> None:
    everything_passed(tmp_path)
    tour(tmp_path, "xfce", [failing])
    found = verdict.verdict(tmp_path)
    assert [name for name, f in found.items() if not f.ok] == [red]
    assert found[red].failed == [f"xfce: {failing}"]
    assert verdict.main([str(tmp_path)]) == 1


def test_fedoras_desktops_count_for_fedora_too(tmp_path: Path) -> None:
    everything_passed(tmp_path)
    tour(tmp_path, "fedora-gnome", ["the AppImage started and stayed up"])
    red = [name for name, f in verdict.verdict(tmp_path).items() if not f.ok]
    assert red == ["starts", "fedora"]


def test_a_part_that_never_came_is_a_fail(tmp_path: Path) -> None:
    """A job that didn't finish proved nothing: its checks are red."""
    everything_passed(tmp_path)
    (tmp_path / "package" / "updates" / "summary.txt").unlink()
    for name in ("checks.json",):
        (tmp_path / "tour-xfce" / name).unlink()
    found = verdict.verdict(tmp_path)
    assert found["update"].missing == ["update"]
    assert "xfce" in found["windows"].missing and "xfce" in found["manners"].missing
    assert not found["update"].ok and not found["windows"].ok


def test_a_fail_line_of_the_scripts_is_read(tmp_path: Path) -> None:
    everything_passed(tmp_path)
    (tmp_path / "package" / "linkage-ubuntu-26.04" / "linkage.txt").write_text(
        "pass every library the app loads on X11 is found\n"
        "fail the app's own check passes (--check-install) (exit 1)\n",
        encoding="utf-8",
    )
    found = verdict.verdict(tmp_path)
    assert not found["linkage"].ok and not found["starts"].ok
    assert found["fedora"].ok


def test_the_workflow_runs_only_on_the_public_copy_and_keeps_nothing_long() -> None:
    """GitHub's own runners are free for a public repository; this private
    repo's runners are the user's PCs. Nothing is kept more than a day,
    and nothing of the live server's is asked for: no secret at all."""
    found = workflow()
    for name, job in found["jobs"].items():
        assert "!github.event.repository.private" in str(job.get("if", "")), name
        for step in job.get("steps", []):
            if "upload-artifact" in str(step.get("uses", "")):
                assert step["with"]["retention-days"] == 1, (name, step)
    assert "secrets." not in WORKFLOW.read_text(encoding="utf-8")


def test_the_release_script_starts_it_by_a_release_branch_and_the_desktops_are_the_verdicts() -> (
    None
):
    """The release script pushes a snapshot to `linux-release-X.Y.Z`
    (polyglotic-hq's linux_mirror.sh --release): the push starts it, and
    the build takes X.Y.Z from the branch's name."""
    found = workflow()
    on = found[True] if True in found else found["on"]  # YAML reads `on:` as True
    assert "linux-release-*" in on["push"]["branches"]
    assert "workflow_dispatch" in on
    build = WORKFLOW.read_text(encoding="utf-8")
    assert "${GITHUB_REF_NAME#linux-release-}" in build
    desktops = [
        i["desktop"] for i in found["jobs"]["desktops"]["strategy"]["matrix"]["include"]
    ]
    assert sorted(desktops) == sorted(verdict.DESKTOPS)
    assert set(found["jobs"]["verdict"]["needs"]) == {
        "build",
        "package",
        "capture",
        "desktops",
    }


def test_what_is_published_is_what_every_job_checked() -> None:
    """polyglotic-hq 592: the build packs VERSION as the release is (beside
    the channel's published releases, with its notes), sets apart what the
    release script publishes - kept a day as `linux-publish-<run id>` - and
    the update checks read that set's feed back: an older AppImage updates
    from the very feed and package that would be uploaded."""
    found = workflow()
    build = found["jobs"]["build"]["steps"]
    runs = "\n".join(str(s.get("run", "")) for s in build)
    assert '-e RELEASE_FROM="$UPDATES"' in runs and "-e RELEASE_NOTES=" in runs
    assert found["env"]["UPDATES"] == "https://updates.polyglotic.io/"
    assert (
        'tools.package.linux_publish_set "$OUT/release" "$VERSION" "$CHANNEL" publish'
        in runs
    )
    assert (
        'cmp "appimage/Polyglotic-$VERSION.AppImage" "publish/Polyglotic-$CHANNEL.AppImage"'
        in runs
    )
    kept = [s for s in build if "upload-artifact" in str(s.get("uses", ""))]
    publish = [
        s for s in kept if s["with"]["name"] == "linux-publish-${{ github.run_id }}"
    ]
    assert publish and publish[0]["with"]["path"] == "publish"
    assert "continue-on-error" not in publish[0]  # no set, no release
    package = found["jobs"]["package"]["steps"]
    fetched = [
        s["with"]["name"]
        for s in package
        if "download-artifact" in str(s.get("uses", ""))
    ]
    assert "linux-publish-${{ github.run_id }}" in fetched
    updates = [
        str(s["run"]) for s in package if "linux_update_" in str(s.get("run", ""))
    ]
    assert len(updates) == 2
    for run in updates:
        assert (
            '"$OUT/updates" publish ' in run or '"$OUT/fedora-update" publish' in run
        ), run
    assert any("sha256sum -c SHA256SUMS" in str(s.get("run", "")) for s in package)


def test_the_build_packs_the_release_beside_the_channels_published_releases() -> None:
    script = (ROOT / "tools" / "package" / "linux_build.sh").read_text(encoding="utf-8")
    assert (
        'dotnet vpk download http --url "$release_from" --channel "$channel"' in script
    )
    assert "--allowEmptyChannel" in script
    assert 'folder="$out/release" notes=${RELEASE_NOTES:-}' in script


def test_the_release_check_verifies_the_packed_appimage_says_a_word(
    tmp_path: Path,
) -> None:
    """polyglotic-hq 646: xfce installs speech-dispatcher and runs `--voice`,
    which checks speech-dispatcher isn't running before a card asks and that
    the packed AppImage speaks a word; any failure turns check 8 (manners) red."""
    found = workflow()
    xfce = next(
        entry
        for entry in found["jobs"]["desktops"]["strategy"]["matrix"]["include"]
        if entry["desktop"] == "xfce"
    )
    parts = set(str(xfce["parts"]).split())
    assert {
        "xdotool",
        "speech-dispatcher",
        "speech-dispatcher-espeak-ng",
        "speech-dispatcher-audio-plugins",
    } <= parts
    tour_sh = (ROOT / "tools" / "linux_packed_tour.sh").read_text(encoding="utf-8")
    assert "voice=(--voice)" in tour_sh
    assert '"${voice[@]}"' in tour_sh
    everything_passed(tmp_path)
    voice_check = "Say it: the packed AppImage said a word through speech-dispatcher"
    folder = tmp_path / "tour-xfce"
    data = json.loads((folder / "checks.json").read_text(encoding="utf-8"))
    data["checks"].append({"check": voice_check, "ok": False, "detail": "silent"})
    (folder / "checks.json").write_text(json.dumps(data), encoding="utf-8")
    result = verdict.verdict(tmp_path)
    assert [name for name, f in result.items() if not f.ok] == ["manners"]
    assert result["manners"].failed == [f"xfce: {voice_check}"]


def test_rehearsal_channel_is_supported_by_workflow_and_build() -> None:
    """640: linux-release.yml accepts a channel (for linux-x64-rehearsal) and
    linux_build.sh stamps a protocol channel while packing the rehearsal one."""
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "linux-x64-rehearsal" in text
    assert "linux-release-linux-*" in text
    script = (ROOT / "tools" / "package" / "linux_build.sh").read_text(encoding="utf-8")
    assert "*-rehearsal" in script and '"$stamp_channel"' in script
