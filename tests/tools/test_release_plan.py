"""What a Release run does (decision 0044): a tag on main releases to the
alpha, a hotfix tag on its release branch is built and recorded, a run by
hand on a tag promotes the recorded build, a run by hand on a branch is a
dry run - and anything else is refused."""

from pathlib import Path

import pytest
import yaml
from tools.package import release_plan
from tools.package.release_plan import Plan, Recorded, Refused, plan

ALPHA = Recorded(build=True, channels=("win-x64-alpha",))


def test_a_tag_on_main_is_built_and_published_to_the_alpha() -> None:
    chosen = plan(
        "tag", "v0.1.0", False, "", on_main=True, on_release_branch=False, recorded=None
    )
    assert (chosen.kind, chosen.channel, chosen.build, chosen.deltas) == (
        "release",
        "win-x64-alpha",
        True,
        True,
    )
    assert chosen.build_package == "Polyglotic-0.1.0-win-x64-alpha-full.nupkg"


def test_a_tag_on_main_that_is_also_on_its_release_branch_is_mains() -> None:
    """release/v0.4 starts at v0.4.0, which is on main: a release, not a hotfix."""
    chosen = plan(
        "tag", "v0.4.0", False, "", on_main=True, on_release_branch=True, recorded=None
    )
    assert chosen.kind == "release"


def test_a_hotfix_tag_is_built_and_recorded_but_published_nowhere() -> None:
    chosen = plan(
        "tag", "v0.1.1", False, "", on_main=False, on_release_branch=True, recorded=None
    )
    assert (chosen.kind, chosen.channel, chosen.build, chosen.deltas) == (
        "hotfix",
        "",
        True,
        False,
    )
    assert "release/v0.1" in chosen.summary
    assert "by hand on v0.1.1 with each channel" in chosen.summary


def test_a_tag_on_neither_main_nor_its_release_branch_is_refused() -> None:
    with pytest.raises(Refused, match=r"neither main nor release/v0\.2"):
        plan(
            "tag",
            "v0.2.1",
            False,
            "",
            on_main=False,
            on_release_branch=False,
            recorded=None,
        )


@pytest.mark.parametrize("tag", ["0.1.0", "v0.1", "v0.1.0-rc1", "v01.0.0"])
def test_a_tag_that_isnt_a_release_tag_is_refused(tag: str) -> None:
    with pytest.raises(Refused, match="isn't a release tag"):
        plan(
            "tag", tag, False, "", on_main=True, on_release_branch=False, recorded=None
        )


def test_by_hand_on_a_tag_promotes_the_recorded_build_without_a_rebuild() -> None:
    chosen = plan("tag", "v0.1.0", True, "win-x64-beta", True, False, ALPHA)
    assert (chosen.kind, chosen.channel, chosen.build, chosen.deltas) == (
        "promote",
        "win-x64-beta",
        False,
        False,
    )
    assert chosen.build_package == "Polyglotic-0.1.0-win-x64-alpha-full.nupkg"


def test_a_hotfixs_build_goes_to_each_channel_by_hand_the_alpha_too() -> None:
    hotfix = Recorded(build=True, channels=())
    for channel in ("win-x64-alpha", "win-x64-beta", "win-x64-stable"):
        assert (
            plan("tag", "v0.1.1", True, channel, False, True, hotfix).kind == "promote"
        )


@pytest.mark.parametrize(
    ("channel", "recorded", "says"),
    [
        ("", ALPHA, "names the channel"),
        ("win-x64-beta", None, "no published Release with its build"),
        ("win-x64-beta", Recorded(build=False, channels=()), "no published Release"),
        ("win-x64-alpha", ALPHA, "already on win-x64-alpha"),
        ("win-x64-nightly", ALPHA, "isn't a channel"),
    ],
)
def test_a_promotion_that_cant_be_is_refused(
    channel: str, recorded: Recorded | None, says: str
) -> None:
    with pytest.raises(Refused, match=says):
        plan("tag", "v0.1.0", True, channel, True, False, recorded)


@pytest.mark.parametrize(
    ("channel", "rehearsed"),
    [
        ("", "win-x64-beta"),
        ("win-x64-alpha", "win-x64-beta"),
        ("win-x64-stable", "win-x64-stable"),
    ],
)
def test_by_hand_on_a_branch_is_a_dry_run_that_rehearses_a_promotion(
    channel: str, rehearsed: str
) -> None:
    chosen = plan("branch", "", True, channel, False, False, None)
    assert chosen == Plan(
        "dry-run",
        "v0.0.1",
        rehearsed,
        build=True,
        deltas=False,
        summary=chosen.summary,
    )
    assert "nothing is published" in chosen.summary


def test_a_branch_push_starts_nothing() -> None:
    with pytest.raises(Refused, match="only a tag"):
        plan("branch", "", False, "", False, False, None)


def test_the_release_branch_is_the_tags_line() -> None:
    assert release_plan.release_branch("v0.1.1") == "release/v0.1"
    assert release_plan.release_branch("v12.3.0") == "release/v12.3"


def test_the_plan_is_written_for_the_workflow(tmp_path: Path) -> None:
    out = tmp_path / "output"
    assert (
        release_plan.main(["--ref-type", "branch", "--by-hand", "--output", str(out)])
        == 0
    )
    lines = dict(
        line.split("=", 1) for line in out.read_text(encoding="utf-8").splitlines()
    )
    assert lines["kind"] == "dry-run"
    assert lines["tag"] == "v0.0.1"
    assert lines["channel"] == "win-x64-beta"
    assert lines["build"] == "true"
    assert lines["deltas"] == "false"
    assert lines["build_channel"] == "win-x64-alpha"
    assert lines["build_package"] == "Polyglotic-0.0.1-win-x64-alpha-full.nupkg"
    assert release_plan.main(["--ref-type", "branch"]) == 1


def test_the_release_workflow_follows_the_plan() -> None:
    workflow = (
        Path(release_plan.__file__).parents[2] / ".github" / "workflows" / "release.yml"
    )
    jobs = yaml.safe_load(workflow.read_text(encoding="utf-8"))["jobs"]
    runs = " ".join(str(step.get("run", "")) for step in jobs["tag"]["steps"])
    assert "python -m tools.package.release_plan" in runs
    assert set(jobs) == {"tag", "release"}  # one job builds and publishes (0050)
    release = jobs["release"]
    assert release["if"] == (
        "needs.tag.outputs.build == 'true' || needs.tag.outputs.kind == 'promote'"
    )
    steps = {s.get("name", s.get("uses")): s for s in release["steps"]}
    build = steps["Build and pack (package.yml's steps)"]
    assert build["if"] == "needs.tag.outputs.build == 'true'"
    assert build["with"]["channel"] == "${{ needs.tag.outputs.build_channel }}"
    assert build["with"]["promote_to"] == (
        "${{ needs.tag.outputs.kind == 'dry-run' && needs.tag.outputs.channel || '' }}"
    )
    promote = [s for s in release["steps"] if "promote" in str(s.get("if", ""))]
    assert [s["if"] for s in promote] == ["needs.tag.outputs.kind == 'promote'"] * 2
    publishing = release["steps"][-3:]  # upload, the public feed, the Release
    assert all("github.ref_type == 'tag'" in s["if"] for s in publishing), (
        "only a tag uploads, checks the public feed and records the Release"
    )


def test_package_rehearses_a_promotion_on_every_build_but_a_releases() -> None:
    """The dry run's path (decision 0044): the build's own steps
    (.github/actions/build-and-pack, decision 0050) run a promotion's on
    the fresh build when asked - package.yml always asks (pushes to main,
    by hand), a release's dry run asks with its channel - and pack only
    through tools/package/pack.sh, as the promotion does, so the two packs
    can't drift apart."""
    repo = Path(release_plan.__file__).parents[2]
    package = yaml.safe_load(
        (repo / ".github" / "workflows" / "package.yml").read_text(encoding="utf-8")
    )
    assert package["env"]["REHEARSE_PROMOTION"] == "win-x64-beta"
    shared = next(
        s
        for s in package["jobs"]["package"]["steps"]
        if s.get("uses") == "./.github/actions/build-and-pack"
    )
    assert shared["with"]["promote_to"] == "${{ env.REHEARSE_PROMOTION }}"
    action = yaml.safe_load(
        (repo / ".github" / "actions" / "build-and-pack" / "action.yml").read_text(
            encoding="utf-8"
        )
    )
    steps = action["runs"]["steps"]
    rehearsal = next(s for s in steps if s.get("if") == "inputs.promote_to != ''")
    for command in (
        "tools.package.promote unpack",
        "tools/package/pack.sh",
        "tools.package.promote compare",
    ):
        assert command in rehearsal["run"]
    runs = [str(s.get("run", "")) for s in steps]
    assert not any("vpk pack" in run for run in runs), (
        "pack through tools/package/pack.sh"
    )
