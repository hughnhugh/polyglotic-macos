"""Keeps this repo's copy of polyglotic-server's protocol examples current (decision 0011).

The server owns the protocol and its examples (`docs/protocol-examples/`);
the app's tests check its messages against a copy in
`tests/protocol_examples/`, with a manifest (`MANIFEST.txt`) of where it
came from - the server's commit - and each file's SHA-256, one
`<sha256>  <path>` line per file, as `sha256sum` writes them.
`tests/test_protocol.py` fails if the copy and its manifest disagree, so
the copy is only ever changed by this tool.

    git -C ../polyglotic-server fetch
    uv run python -m tools.protocol_examples check ../polyglotic-server
    uv run python -m tools.protocol_examples copy ../polyglotic-server

`check` says whether the copy matches the server's examples at `--ref`
(default `origin/main`) and exits 1 if not; `copy` replaces the copy with
them. Both read the server checkout through git, so its working tree and
branch don't matter.
"""

import argparse
import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
COPY = REPO / "tests" / "protocol_examples"
MANIFEST = COPY / "MANIFEST.txt"
SERVER_PATH = "docs/protocol-examples"
VERSIONS = ("v1",)  # the protocol versions this app speaks


def digest(content: bytes) -> str:
    """SHA-256 of a file with its line endings as LF (git may check text
    out with CRLF on Windows)."""
    return hashlib.sha256(content.replace(b"\r\n", b"\n")).hexdigest()


def _git(server: Path, *args: str) -> bytes:
    return subprocess.run(
        ["git", "-C", str(server), *args], check=True, capture_output=True
    ).stdout


def server_examples(server: Path, ref: str) -> tuple[str, dict[str, bytes]]:
    """The server's commit at `ref` and its example files, by path relative
    to docs/protocol-examples/ (`v1/hello.json`)."""
    commit = _git(server, "rev-parse", f"{ref}^{{commit}}").decode().strip()
    files: dict[str, bytes] = {}
    for version in VERSIONS:
        listing = _git(
            server, "ls-tree", "-r", "--name-only", commit, f"{SERVER_PATH}/{version}"
        )
        for path in listing.decode().split():
            if path.endswith(".json"):
                relative = path.removeprefix(f"{SERVER_PATH}/")
                files[relative] = _git(server, "show", f"{commit}:{path}")
    return commit, files


def read_manifest() -> tuple[str, dict[str, str]]:
    """The server commit the copy came from, and each file's SHA-256 by path."""
    commit, digests = "", {}
    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        if line.startswith("# commit "):
            commit = line.removeprefix("# commit ").strip()
        elif line and not line.startswith("#"):
            sha, path = line.split(maxsplit=1)
            digests[path] = sha
    return commit, digests


def copied_files() -> dict[str, bytes]:
    """The copy's files, by path relative to tests/protocol_examples/."""
    return {
        path.relative_to(COPY).as_posix(): path.read_bytes()
        for path in sorted(COPY.rglob("*.json"))
    }


def check(server: Path, ref: str) -> int:
    commit, theirs = server_examples(server, ref)
    ours = copied_files()
    added = sorted(set(theirs) - set(ours))
    removed = sorted(set(ours) - set(theirs))
    changed = sorted(
        p for p in set(ours) & set(theirs) if digest(ours[p]) != digest(theirs[p])
    )
    copied_from, _ = read_manifest()
    if not (added or removed or changed):
        print(f"The copy matches the server's examples at {ref} ({commit[:7]}).")
        return 0
    print(f"The copy (from {copied_from[:7]}) differs from {ref} ({commit[:7]}):")
    for label, paths in (("new", added), ("gone", removed), ("changed", changed)):
        for path in paths:
            print(f"  {label}: {path}")
    print("Run `copy` to take them, then make the app's tests pass.")
    return 1


def copy(server: Path, ref: str) -> int:
    commit, theirs = server_examples(server, ref)
    for version in VERSIONS:
        shutil.rmtree(COPY / version, ignore_errors=True)
    for path, content in theirs.items():
        target = COPY / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content.replace(b"\r\n", b"\n"))
    lines = [
        "# Written by tools/protocol_examples.py; don't edit the copy by hand.",
        f"# From hughnhugh/polyglotic-server {SERVER_PATH}/ at",
        f"# commit {commit}",
        *(f"{digest(theirs[path])}  {path}" for path in sorted(theirs)),
    ]
    MANIFEST.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print(f"Copied {len(theirs)} examples from {ref} ({commit[:7]}).")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m tools.protocol_examples")
    parser.add_argument("command", choices=["check", "copy"])
    parser.add_argument("server", type=Path, help="a polyglotic-server checkout")
    parser.add_argument("--ref", default="origin/main")
    args = parser.parse_args(argv)
    return (check if args.command == "check" else copy)(args.server, args.ref)


if __name__ == "__main__":
    sys.exit(main())
