"""What a Release run does: build, publish, promote - or refuse (decision 0044).

    python -m tools.package.release_plan --ref-type tag --tag v0.1.0 \\
        [--channel win-x64-beta] [--by-hand] [--output $GITHUB_OUTPUT]

One build per tag, published to each channel as **the same build**:

- **A tag on `main`, pushed:** build it (packed for the alpha, the build's
  first channel) and publish it to `win-x64-alpha`, as before.
- **A tag on its `release/vX.Y` branch, pushed (a hotfix):** build it and
  record the build on its GitHub Release, but publish it nowhere: the
  alpha follows `main` and its feed may already be ahead (RELEASING.md
  section 3). Each channel that has the bug is then a run by hand.
- **Release run by hand on a tag, with a channel:** promote - the build
  recorded on the tag's Release, checked by SHA-256, repacked for that
  channel with no rebuild (`promote.py`), published there. Refused if the
  tag has no published Release with its build, or is already on that
  channel.
- **Release run by hand on a branch:** a dry run - the build, the
  promotion rehearsed on it (.github/actions/build-and-pack), nothing published.
- **Anything else** (a tag on neither, a branch push): refused.

The decision is `plan()`, plain Python; `main()` asks git where the tag's
commit is and GitHub's API what its Release holds. Standard library only:
the tag job runs it on the Linux runner without installing the app.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
from collections.abc import Sequence
from dataclasses import asdict, dataclass

from tools.package import feed_check

BUILD_CHANNEL = "win-x64-alpha"
"""The channel the build is packed for first: every tag on main goes there."""
CHANNELS = feed_check.CHANNELS
TAG = re.compile(r"^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
DRY_RUN_TAG = "v0.0.1"
REHEARSAL_CHANNEL = "win-x64-beta"
"""A dry run rehearses promoting its build here (unless asked for another)."""


class Refused(Exception):
    """The run does nothing: the reason, said in the run's log."""


@dataclass(frozen=True)
class Recorded:
    """What the tag's published GitHub Release holds."""

    build: bool
    """The build: its full package and `SHA256SUMS-build`."""
    channels: tuple[str, ...]
    """The channels it's published to: a `SHA256SUMS-<channel>` each."""


@dataclass(frozen=True)
class Plan:
    kind: str
    """`release`, `hotfix`, `promote` or `dry-run`."""
    tag: str
    channel: str
    """Where it's published (or, for a dry run, where the promotion is
    rehearsed); empty for a hotfix's own run."""
    build: bool
    """Build from source (.github/actions/build-and-pack, as Package does); a
    promotion repacks the recorded build."""
    deltas: bool
    """Fetch the channel's last release from the public feed for delta
    packages: only for a release from main, whose alpha feed is behind it."""
    summary: str

    @property
    def build_package(self) -> str:
        """The build's full package, as Velopack names it."""
        return f"Polyglotic-{self.tag.removeprefix('v')}-{BUILD_CHANNEL}-full.nupkg"


def release_branch(tag: str) -> str:
    """`v0.4.1` -> `release/v0.4`: the line a hotfix tag belongs to."""
    major, minor, _ = tag.removeprefix("v").split(".")
    return f"release/v{major}.{minor}"


def plan(
    ref_type: str,
    tag: str,
    by_hand: bool,
    channel: str,
    on_main: bool,
    on_release_branch: bool,
    recorded: Recorded | None,
) -> Plan:
    """The run's plan, or Refused. `tag` is the ref's name for a tag;
    `channel` the input of a run by hand (empty for a push)."""
    if channel and channel not in CHANNELS:
        raise Refused(f"{channel} isn't a channel ({', '.join(CHANNELS)})")
    if ref_type != "tag":
        if not by_hand:
            raise Refused("only a tag, or a run by hand, starts a release")
        target = channel if channel and channel != BUILD_CHANNEL else REHEARSAL_CHANNEL
        return Plan(
            "dry-run",
            DRY_RUN_TAG,
            target,
            build=True,
            deltas=False,
            summary=f"A dry run as {DRY_RUN_TAG}: built for {BUILD_CHANNEL}, promoted to"
            f" {target} as a rehearsal; nothing is published",
        )
    if not TAG.match(tag):
        raise Refused(f"{tag} isn't a release tag (v plus MAJOR.MINOR.PATCH)")
    if by_hand:
        if not channel:
            raise Refused("a run by hand on a tag names the channel to publish to")
        if recorded is None or not recorded.build:
            raise Refused(
                f"{tag} has no published Release with its build: the tag's own run"
                " (on its push) builds and records it - re-run that, or set up the"
                " update storage first (a draft published nothing)"
            )
        if channel in recorded.channels:
            raise Refused(f"{tag} is already on {channel}")
        return Plan(
            "promote",
            tag,
            channel,
            build=False,
            deltas=False,
            summary=f"{tag}'s build, as {BUILD_CHANNEL} got it, repacked for {channel}"
            " and published there - no rebuild",
        )
    if on_main:
        return Plan(
            "release",
            tag,
            BUILD_CHANNEL,
            build=True,
            deltas=True,
            summary=f"{tag} on main: built and published to {BUILD_CHANNEL}",
        )
    if on_release_branch:
        return Plan(
            "hotfix",
            tag,
            "",
            build=True,
            deltas=False,
            summary=f"{tag} on {release_branch(tag)}: a hotfix, built and recorded, published"
            f" nowhere yet - run Release by hand on {tag} with each channel that has the bug",
        )
    raise Refused(
        f"{tag} is on neither main nor {release_branch(tag)}: nothing is built"
    )


# -- the run's facts ----------------------------------------------------------------


def _is_ancestor(commit: str, ref: str) -> bool:
    done = subprocess.run(
        ["git", "merge-base", "--is-ancestor", commit, ref],
        capture_output=True,
        check=False,
    )
    return done.returncode == 0


def recorded_on_github(repo: str, tag: str) -> Recorded | None:
    """The tag's published Release (a draft isn't found: it published
    nothing), or None."""
    try:
        release = feed_check.api_json(f"/repos/{repo}/releases/tags/{tag}")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise
    assert isinstance(release, dict)
    names = {str(asset["name"]) for asset in release.get("assets", [])}
    return Recorded(
        build="SHA256SUMS-build" in names,
        channels=tuple(c for c in CHANNELS if f"SHA256SUMS-{c}" in names),
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m tools.package.release_plan")
    parser.add_argument(
        "--ref-type", required=True, help="github.ref_type: tag or branch"
    )
    parser.add_argument("--tag", default="", help="the tag's name, for a tag")
    parser.add_argument("--channel", default="", help="a run by hand's channel")
    parser.add_argument("--by-hand", action="store_true", help="workflow_dispatch")
    parser.add_argument("--output", help="append the plan here ($GITHUB_OUTPUT)")
    args = parser.parse_args(argv)
    tag = args.tag
    tagged = args.ref_type == "tag" and bool(TAG.match(tag))
    commit = f"refs/tags/{tag}^{{commit}}"
    on_main = tagged and _is_ancestor(commit, "origin/main")
    on_branch = tagged and _is_ancestor(commit, f"origin/{release_branch(tag)}")
    recorded = None
    if tagged and args.by_hand:
        recorded = recorded_on_github(os.environ["GH_REPO"], tag)
    try:
        chosen = plan(
            args.ref_type, tag, args.by_hand, args.channel, on_main, on_branch, recorded
        )
    except Refused as e:
        print(f"::error::{e}")
        return 1
    print(chosen.summary)
    print(json.dumps(asdict(chosen)))
    if args.output:
        with open(args.output, "a", encoding="utf-8") as out:
            for key, value in asdict(chosen).items():
                text = str(value).lower() if isinstance(value, bool) else str(value)
                out.write(f"{key}={text}\n")
            out.write(f"build_channel={BUILD_CHANNEL}\n")
            out.write(f"build_package={chosen.build_package}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
