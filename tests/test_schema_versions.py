"""The learning and outbox schema versions never go down between releases
(polyglotic-hq project 107, 104's G8; RELEASING.md section 5).

A downgraded version would let an older app open a file a newer one has
migrated (and write to it as if it knew the shape). The version is the
number of migrations in each adapter (`VERSION = len(_MIGRATIONS)`), so
removing or merging a migration lowers it.

The reference is the version at the newest release tag (`v*`) reachable
from HEAD; with no tag yet, at `origin/main` (or `main`). In CI the
checkout fetches full history and tags for this. On a machine with no git
or no reference the test is skipped - in CI, it fails instead.
"""

import os
import subprocess
from pathlib import Path

import pytest
from tools.release_check import migration_count

from polyglotic_desktop.adapters import sqlite_learning, sqlite_outbox

ROOT = Path(__file__).resolve().parents[1]
ADAPTERS = {
    "learning": ("src/polyglotic_desktop/adapters/sqlite_learning.py", sqlite_learning),
    "outbox": ("src/polyglotic_desktop/adapters/sqlite_outbox.py", sqlite_outbox),
}


def git(*args: str) -> str | None:
    try:
        done = subprocess.run(
            ["git", *args], cwd=ROOT, capture_output=True, text=True, check=True
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return done.stdout.strip()


def reference() -> str | None:
    """The newest release tag reachable from HEAD, else origin/main, else main."""
    tag = git("describe", "--tags", "--abbrev=0", "--match", "v*")
    if tag:
        return tag
    for ref in ("origin/main", "main"):
        if git("rev-parse", "--verify", "--quiet", ref):
            return ref
    return None


@pytest.mark.parametrize("name", sorted(ADAPTERS))
def test_a_schema_version_never_goes_down(name: str) -> None:
    path, module = ADAPTERS[name]
    ref = reference()
    old_source = git("show", f"{ref}:{path}") if ref else None
    if old_source is None:
        message = (
            "no release tag or main to compare with (git missing or a shallow clone)"
        )
        if os.environ.get("CI"):
            pytest.fail(message)
        pytest.skip(message)
    before = migration_count(old_source)
    assert before <= module.VERSION, (
        f"the {name} schema version is {module.VERSION}, lower than {before} at {ref}: "
        "add migrations, never remove or merge them (RELEASING.md section 5)"
    )
