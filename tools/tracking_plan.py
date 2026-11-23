"""Keeps this repo's copy of polyglotic-server's tracking plan current (decision 0271).

The server owns the tracking plan (`docs/tracking-plan.yaml`): a usage
event, or a property or value it doesn't list, is dropped whole when the
app sends it. The app's tests check every event it can send against a copy
in `tests/tracking_plan/` (`tests/test_usage_events_fit_the_plan.py`), with
a manifest (`MANIFEST.txt`) of where it came from - the server's commit -
and the file's SHA-256, as `tools/protocol_examples.py` keeps the protocol
examples (decision 0011). The test fails if the copy and its manifest
disagree, so the copy is only ever changed by this tool.

    git -C ../polyglotic-server fetch
    uv run python -m tools.tracking_plan check ../polyglotic-server
    uv run python -m tools.tracking_plan copy ../polyglotic-server

`check` says whether the copy matches the server's plan at `--ref`
(default `origin/main`) and exits 1 if not; `copy` replaces the copy with
it. Both read the server checkout through git, so its working tree and
branch don't matter.
"""

import argparse
import subprocess
import sys
from pathlib import Path

from tools.protocol_examples import digest

REPO = Path(__file__).resolve().parents[1]
COPY = REPO / "tests" / "tracking_plan"
PLAN = COPY / "tracking-plan.yaml"
MANIFEST = COPY / "MANIFEST.txt"
SERVER_PATH = "docs/tracking-plan.yaml"


def _git(server: Path, *args: str) -> bytes:
    return subprocess.run(
        ["git", "-C", str(server), *args], check=True, capture_output=True
    ).stdout


def server_plan(server: Path, ref: str) -> tuple[str, bytes]:
    """The server's commit at `ref`, and its tracking plan there."""
    commit = _git(server, "rev-parse", f"{ref}^{{commit}}").decode().strip()
    return commit, _git(server, "show", f"{commit}:{SERVER_PATH}")


def read_manifest() -> tuple[str, str]:
    """The server commit the copy came from, and the plan's SHA-256."""
    commit, sha = "", ""
    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        if line.startswith("# commit "):
            commit = line.removeprefix("# commit ").strip()
        elif line and not line.startswith("#"):
            sha = line.split(maxsplit=1)[0]
    return commit, sha


def check(server: Path, ref: str) -> int:
    commit, theirs = server_plan(server, ref)
    copied_from, _ = read_manifest()
    if digest(PLAN.read_bytes()) == digest(theirs):
        print(f"The copy matches the server's plan at {ref} ({commit[:7]}).")
        return 0
    print(f"The copy (from {copied_from[:7]}) differs from {ref} ({commit[:7]}).")
    print("Run `copy` to take it, then make the app's tests pass.")
    return 1


def copy(server: Path, ref: str) -> int:
    commit, theirs = server_plan(server, ref)
    COPY.mkdir(parents=True, exist_ok=True)
    PLAN.write_bytes(theirs.replace(b"\r\n", b"\n"))
    lines = [
        "# Written by tools/tracking_plan.py; don't edit the copy by hand.",
        f"# From hughnhugh/polyglotic-server {SERVER_PATH} at",
        f"# commit {commit}",
        f"{digest(theirs)}  tracking-plan.yaml",
    ]
    MANIFEST.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print(f"Copied the tracking plan from {ref} ({commit[:7]}).")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m tools.tracking_plan")
    parser.add_argument("command", choices=["check", "copy"])
    parser.add_argument("server", type=Path, help="a polyglotic-server checkout")
    parser.add_argument("--ref", default="origin/main")
    args = parser.parse_args(argv)
    return (check if args.command == "check" else copy)(args.server, args.ref)


if __name__ == "__main__":
    sys.exit(main())
