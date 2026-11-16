"""The app's release check, before the tag (polyglotic-hq RELEASING.md section 2).

    uv run python -m tools.release_check v0.1.0 [--commit origin/main]
        [--server ../polyglotic-server]

Reports the checklist's items that the repos can answer, each PASS or FAIL
with its evidence, and exits 1 on any FAIL:

1. the commit is on `main`, CI passed on it, and Package passed on it or
   on the last commit before it that changed what Package builds (its
   build runs `--check-install` on the packed app);
2. `RELEASE-NOTES.md` at the commit has the version's notes;
3. the part of "what the release needs from the server" the repos can
   answer: the app's built-in server and update addresses are real (not
   the `.invalid` placeholders), its protocol is one polyglotic-server's
   `origin/main` takes, and its version isn't below the server's default
   `min_app_version` - the live copy is checked by hand;
4. the local schemas (learning, outbox) since the last release tag: none
   went down, and any that went up is named - it runs first on the alpha,
   the user's own PC, so it isn't promoted until it has;
5. the flags polyglotic-server declares: each with an owner and an expiry
   still to come, and at most 10.

The live server (the rest of item 3) and item 6 (the user's signed tag)
aren't for a script: they are printed as reminders.
Reads git and GitHub (`gh`, signed in); writes nothing.
"""

from __future__ import annotations

import argparse
import ast
import json
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import yaml

from tools.package import release_notes

REPO = Path(__file__).resolve().parents[1]
SERVER = next(
    (p for p in (REPO.parent / "polyglotic-server", REPO.parent.parent / "polyglotic-server")
     if p.is_dir()),
    REPO.parent / "polyglotic-server",
)  # fmt: skip
"""polyglotic-server beside this clone (or beside its worktrees' folder)."""
SCHEMAS = {
    "learning": "src/polyglotic_desktop/adapters/sqlite_learning.py",
    "outbox": "src/polyglotic_desktop/adapters/sqlite_outbox.py",
}
SERVER_FLAGS = "src/polyglotic_server/core/releases/flags.py"
MOST_FLAGS = 10  # ENGINEERING.md, "Feature flags": at most about 10 live

Git = Callable[..., "str | None"]
"""`git(*args)` -> its output, or None if it failed."""
Runs = Callable[[str, str], "list[dict[str, object]]"]
"""`runs(workflow, sha_or_branch)` -> GitHub's runs, newest first."""


@dataclass
class Item:
    number: int
    title: str
    passed: bool = True
    evidence: list[str] = field(default_factory=list)

    def fail(self, line: str) -> None:
        self.passed = False
        self.evidence.append(line)


# -- 1. main is green ---------------------------------------------------------------


def package_paths(workflow: str) -> list[str]:
    """The paths whose change makes Package run on a push to main."""
    on = yaml.safe_load(workflow)[True]  # YAML reads the key `on` as True
    return [str(path).removesuffix("/**") for path in on["push"]["paths"]]


def latest(runs: list[dict[str, object]]) -> dict[str, object] | None:
    """The newest run that wasn't cancelled (a newer push cancels an older one)."""
    for run in runs:
        if run.get("conclusion") != "cancelled":
            return run
    return None


def main_is_green(sha: str, git: Git, runs: Runs) -> Item:
    item = Item(1, "main is green, and Package's --check-install passed")
    if git("merge-base", "--is-ancestor", sha, "origin/main") is None:
        item.fail(f"{sha[:7]} isn't on origin/main: a release is a tag on main")
        return item
    ci = latest(runs("ci.yml", sha))
    if ci is None:
        item.fail(f"CI hasn't run on {sha[:7]}")
    elif ci.get("status") != "completed":
        item.fail(f"CI on {sha[:7]} is {ci.get('status')} (run {ci.get('databaseId')})")
    elif ci.get("conclusion") != "success":
        item.fail(
            f"CI on {sha[:7]}: {ci.get('conclusion')} (run {ci.get('databaseId')})"
        )
    else:
        item.evidence.append(f"CI passed on {sha[:7]} (run {ci.get('databaseId')})")

    workflow = git("show", f"{sha}:.github/workflows/package.yml") or ""
    paths = package_paths(workflow)
    for run in runs("package.yml", "main"):
        head = str(run.get("headSha"))
        if run.get("conclusion") == "cancelled":
            continue
        if head != sha and git("merge-base", "--is-ancestor", head, sha) is None:
            continue  # newer than the commit, or not under it
        if run.get("status") != "completed":
            item.fail(
                f"Package on {head[:7]} is {run.get('status')} (run {run.get('databaseId')})"
            )
        elif run.get("conclusion") != "success":
            item.fail(
                f"Package on {head[:7]}: {run.get('conclusion')} (run {run.get('databaseId')})"
            )
        else:
            changed = git("diff", "--name-only", head, sha, "--", *paths) or ""
            if changed.strip():
                item.fail(
                    f"Package last ran on {head[:7]}; what it builds changed since"
                    f" ({len(changed.split())} files): run Package by hand on main"
                )
            else:
                item.evidence.append(
                    f"Package passed on {head[:7]} (run {run.get('databaseId')}),"
                    " with --check-install on the packed app; nothing it builds changed since"
                )
        return item
    item.fail("no Package run on main at or before the commit")
    return item


# -- 2. the release notes -----------------------------------------------------------


def notes_written(sha: str, version: str, git: Git) -> Item:
    item = Item(2, "the release notes are written (RELEASE-NOTES.md)")
    text = git("show", f"{sha}:RELEASE-NOTES.md")
    if text is None:
        item.fail(f"no RELEASE-NOTES.md at {sha[:7]}")
        return item
    try:
        section = release_notes.notes_for(text, version)
    except (LookupError, ValueError) as e:
        item.fail(str(e))
        return item
    counts = ", ".join(f"{len(v)} {k}" for k, v in section.groups.items() if v)
    item.evidence.append(f"{version} - {section.date}: {counts}")
    return item


# -- 4. local schema migrations -----------------------------------------------------


def migration_count(source: str) -> int:
    """How many migrations `_MIGRATIONS` holds, read without importing old
    code (the schema's version is that count: `VERSION = len(_MIGRATIONS)`)."""
    for node in ast.parse(source).body:
        names: list[ast.expr]
        if isinstance(node, ast.AnnAssign):
            names, value = [node.target], node.value
        elif isinstance(node, ast.Assign):
            names, value = node.targets, node.value
        else:
            continue
        if any(isinstance(n, ast.Name) and n.id == "_MIGRATIONS" for n in names):
            if not isinstance(value, ast.Tuple):
                raise TypeError("_MIGRATIONS isn't a tuple")
            return len(value.elts)
    raise ValueError("no _MIGRATIONS found")


def schemas_since_last_release(sha: str, git: Git) -> Item:
    item = Item(4, "local schema migrations have run on alpha first")
    previous = git("describe", "--tags", "--abbrev=0", "--match", "v*", f"{sha}^")
    for name, path in SCHEMAS.items():
        now = migration_count(git("show", f"{sha}:{path}") or "")
        before_source = git("show", f"{previous}:{path}") if previous else None
        if before_source is None:
            item.evidence.append(
                f"{name}: version {now}, the first release - nothing to migrate from"
            )
            continue
        before = migration_count(before_source)
        if now < before:
            item.fail(f"{name}: version {now}, lower than {before} at {previous}")
        elif now > before:
            item.evidence.append(
                f"{name}: {before} -> {now} since {previous} - it runs first on the alpha"
                " (the user's PC); promote only after it has"
            )
        else:
            item.evidence.append(f"{name}: version {now}, unchanged since {previous}")
    return item


# -- 5. flags -----------------------------------------------------------------------


def declared_flags(source: str) -> list[dict[str, object]]:
    """polyglotic-server's `DECLARED` flags, read from its source: each
    `Flag(...)`'s name, owner and expiry (`date(Y, M, D)`)."""
    for node in ast.parse(source).body:
        target: ast.expr | None = None
        if isinstance(node, ast.AnnAssign):
            target = node.target
        elif isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
        if not (isinstance(target, ast.Name) and target.id == "DECLARED"):
            continue
        value = getattr(node, "value", None)
        if not isinstance(value, ast.Tuple):
            raise TypeError("DECLARED isn't a tuple")
        flags = []
        for call in value.elts:
            if not isinstance(call, ast.Call):
                raise TypeError("DECLARED holds something that isn't a Flag(...)")
            fields: dict[str, object] = {}
            for keyword in call.keywords:
                if isinstance(keyword.value, ast.Constant):
                    fields[str(keyword.arg)] = keyword.value.value
                elif isinstance(keyword.value, ast.Call):  # date(2027, 1, 31)
                    parts = [
                        a.value
                        for a in keyword.value.args
                        if isinstance(a, ast.Constant) and isinstance(a.value, int)
                    ]
                    fields[str(keyword.arg)] = date(*parts)
            flags.append(fields)
        return flags
    raise ValueError("no DECLARED found")


def flags_in_order(source: str | None, today: date) -> Item:
    item = Item(5, "flags: an owner and an expiry each, at most 10 live")
    if source is None:
        item.fail(f"polyglotic-server's {SERVER_FLAGS} can't be read (--server)")
        return item
    flags = declared_flags(source)
    for flag in flags:
        name = flag.get("name", "?")
        expires = flag.get("expires")
        if not flag.get("owner"):
            item.fail(f"{name}: no owner")
        if not isinstance(expires, date):
            item.fail(f"{name}: no expiry date")
        elif expires <= today:
            item.fail(f"{name}: expired on {expires}")
        else:
            item.evidence.append(f"{name}: {flag.get('owner')}, expires {expires}")
    if len(flags) > MOST_FLAGS:
        item.fail(f"{len(flags)} flags declared: more than {MOST_FLAGS}")
    item.evidence.append(
        f"{len(flags)} declared on polyglotic-server's origin/main; the app reads none by name"
        " (welcome.features). At 100% for two releases: the live table, by hand"
        " (polyglotic-admin flags)"
    )
    return item


# -- 3, the part the repos answer: addresses and the server's code -------------------

APP_MAIN = "src/polyglotic_desktop/main.py"
APP_PROTOCOL = "src/polyglotic_desktop/connection/protocol.py"
SERVER_SESSION = "src/polyglotic_server/api/session.py"
SERVER_MAIN = "src/polyglotic_server/main.py"


def constants(source: str) -> dict[str, object]:
    """A module's top-level `NAME = <literal>` assignments (annotated or not)."""
    found: dict[str, object] = {}
    for node in ast.parse(source).body:
        target: ast.expr | None = None
        if isinstance(node, ast.AnnAssign) and node.value is not None:
            target, value = node.target, node.value
        elif isinstance(node, ast.Assign) and len(node.targets) == 1:
            target, value = node.targets[0], node.value
        if isinstance(target, ast.Name):
            try:
                found[target.id] = ast.literal_eval(value)
            except (ValueError, TypeError, SyntaxError):
                continue
    return found


def server_default_minimum(source: str) -> str | None:
    """polyglotic-server's `min_app_version` default (`main.py`'s settings)."""
    for node in ast.walk(ast.parse(source)):
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "min_app_version"
            and isinstance(node.value, ast.Constant)
        ):
            return str(node.value.value)
    return None


def _version(text: str) -> tuple[int, ...]:
    return tuple(int(part) for part in text.split("."))


def what_the_app_needs(sha: str, version: str, git: Git, server_git: Git) -> Item:
    item = Item(3, "(the repos' part) real addresses; the server's code takes this app")
    app = constants(git("show", f"{sha}:{APP_MAIN}") or "")
    for name in ("SERVER", "UPDATES"):
        address = str(app.get(name, ""))
        host = address.removeprefix("https://").split("/")[0]
        if not address.startswith("https://") or host.endswith(".invalid") or not host:
            item.fail(
                f"main.{name} is {address!r}: set the real address before the tag"
            )
        else:
            item.evidence.append(f"main.{name}: {address}")
    keys = app.get("FEED_KEYS", ())
    item.evidence.append(
        f"main.FEED_KEYS: {len(keys) if isinstance(keys, tuple) else '?'} key(s)"
        + (
            ""
            if keys
            else " - the feed's signature isn't checked (DECISIONS #13: before the beta)"
        )
    )
    protocol = constants(git("show", f"{sha}:{APP_PROTOCOL}") or "").get("PROTOCOL")
    served = constants(server_git("show", f"origin/main:{SERVER_SESSION}") or "").get(
        "PROTOCOLS"
    )
    if not isinstance(served, set) or protocol not in served:
        item.fail(
            f"protocol {protocol}: polyglotic-server's origin/main takes {served}"
        )
    else:
        item.evidence.append(
            f"protocol {protocol}: polyglotic-server's origin/main takes {sorted(served)}"
        )
    minimum = server_default_minimum(
        server_git("show", f"origin/main:{SERVER_MAIN}") or ""
    )
    if minimum is None:
        item.fail("polyglotic-server's default min_app_version can't be read")
    elif _version(version) < _version(minimum):
        item.fail(f"{version} is below the server's default min_app_version {minimum}")
    else:
        item.evidence.append(
            f"{version} >= the server's default min_app_version {minimum}"
            " (the live copy's POLYGLOTIC_MIN_APP_VERSION(S): by hand)"
        )
    return item


# -- running it ---------------------------------------------------------------------

REMINDERS = (
    (
        "3. (by hand) the live server: running this protocol, its"
        " min_app_version for the channel at or below this version, any new"
        " limit or flag set"
    ),
    "6. (the user) the signed tag: git tag -s vX.Y.Z <commit> && git push origin vX.Y.Z",
)


def check(
    version: str, sha: str, git: Git, server_git: Git, runs: Runs, today: date
) -> list[Item]:
    return [
        main_is_green(sha, git, runs),
        notes_written(sha, version, git),
        what_the_app_needs(sha, version, git, server_git),
        schemas_since_last_release(sha, git),
        flags_in_order(server_git("show", f"origin/main:{SERVER_FLAGS}"), today),
    ]


def report(version: str, sha: str, items: list[Item]) -> str:
    lines = [f"Release check for v{version} at {sha[:7]}"]
    for item in items:
        lines.append(
            f"{'PASS' if item.passed else 'FAIL'}  {item.number}. {item.title}"
        )
        lines += [f"        {line}" for line in item.evidence]
    lines += ["      " + reminder for reminder in REMINDERS]
    return "\n".join(lines)


def git_in(folder: Path) -> Git:
    def git(*args: str) -> str | None:
        try:
            done = subprocess.run(
                ["git", "-C", str(folder), *args],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=True,
            )
        except (OSError, subprocess.CalledProcessError):
            return None
        return done.stdout

    return git


def github_runs(workflow: str, sha_or_branch: str) -> list[dict[str, object]]:
    """Runs of `workflow` on a commit (40 hex characters) or a branch, newest first."""
    which = "--commit" if len(sha_or_branch) == 40 else "--branch"
    fields = "databaseId,status,conclusion,headSha,event,createdAt"
    done = subprocess.run(
        ["gh", "run", "list", "--workflow", workflow, which, sha_or_branch,
         "--limit", "40", "--json", fields],
        capture_output=True, text=True, encoding="utf-8", check=True, cwd=REPO,
    )  # fmt: skip
    runs: list[dict[str, object]] = json.loads(done.stdout)
    return sorted(runs, key=lambda r: str(r.get("createdAt")), reverse=True)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m tools.release_check")
    parser.add_argument("tag", help="the release's tag, e.g. v0.1.0")
    parser.add_argument("--commit", default="origin/main", help="the commit to tag")
    parser.add_argument(
        "--server", type=Path, default=SERVER, help="a polyglotic-server clone"
    )
    args = parser.parse_args(argv)
    version = args.tag.removeprefix("v")
    git = git_in(REPO)
    sha = (git("rev-parse", f"{args.commit}^{{commit}}") or "").strip()
    if not sha:
        print(f"{args.commit} isn't a commit here (git fetch first?)", file=sys.stderr)
        return 1
    items = check(version, sha, git, git_in(args.server), github_runs, date.today())
    print(report(version, sha, items))
    return 0 if all(item.passed for item in items) else 1


if __name__ == "__main__":
    sys.exit(main())
