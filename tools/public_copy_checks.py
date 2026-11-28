"""Checks (Linux) on the public copy's free machines (polyglotic-hq 981).

    python -m tools.public_copy_checks              # CI's Checks (Linux), on `light`
    python -m tools.public_copy_checks --clean-up   # cancel and delete what a run left

A pull request's (and main's) Linux checks no longer need this PC's Linux
runner, which is off (polyglotic-hq 963a: its 3.8 GB suite beside live's
models). DECISIONS #266-#267: they run on the public test copy
`polyglotic-linux-spike`, whose standard runners are free, through the path
polyglotic-hq's `scripts/remote_test.py` already takes. This job runs on
the `light` runner (768 MiB, one CPU), so it only sends and waits:

1. The checkout's tree - the commit the job checked out, committed files
   only - less what a public copy never carries (`LEFT_OUT`, as
   remote_test.py), scanned before anything leaves: gitleaks with the
   repo's rules, and the owner's name, email and home paths
   (`PUBLIC_COPY_SCAN`, a secret: the patterns can't be written here, in a
   tree that goes public).
2. One commit of it on the copy's newest base snapshot of main
   (remote_test.py's `remote-test/base-*`, so the push carries only what
   differs), pushed to two scratch branches.
3. The copy's `remote-test.yml` started on each: the tests, cut into
   contiguous slices across machines as remote_test.py cuts them, and the
   static checks (`STATIC`), one command each.
4. Waits, brings the JUnit reports back, prints the failures and the
   totals, deletes the branches and the reports, and exits 0 when
   everything passed, 1 when a check failed or a report is missing, 2 when
   the run itself didn't work. The links go in the job's summary.

Not run there: tests/test_schema_versions.py (it compares with the private
repo's release tags, which the copy doesn't have); Checks (Windows) runs it
on the train and main. The token (`PUBLIC_COPY_TOKEN`) is a fine-grained
one for the public copy alone; it never goes into a command line or the
tree, and the copy's jobs have no secrets at all.
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import os
import re
import signal
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
import zlib
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager, suppress
from dataclasses import dataclass, field
from pathlib import Path
from types import FrameType
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = "hughnhugh/polyglotic-linux-spike"
WORKFLOW = "remote-test.yml"
API = "https://api.github.com"

LEFT_OUT = ("CLAUDE.md", "AGENTS.md", ".claude/", ".cursor/", ".github/dependabot.yml")
"""What a public copy never carries (remote_test.py's LEFT_OUT, the mirrors'
rules). The workflows stay: tests read them."""
NOT_REMOTE = ("tests/test_schema_versions.py",)
"""Test files that can't run in the copy (it has no release tags)."""
BASE = "remote-test/base-"
"""The copy's daily snapshots of main that remote_test.py keeps (one a day)."""
STATIC = (
    "uv run --no-sync ruff check --output-format=full",
    "uv run --no-sync ruff format --check",
    "uv run --no-sync mypy",
    "uv run --no-sync python -m tools.mypy_platforms",
    "uv run --no-sync lint-imports",
)
"""Checks (Linux)' lint, format, types (as win32, and as macOS and Linux:
decision 0038) and import rule, which every pull request gets (decision
0167). One machine, one at a time: the mypy runs share a cache. About 40 s
on the old runner (2026-11-25, run 45606862098)."""

SHARDS = 3
"""Machines for the tests, 1-5. remote_test.py's Linux default: the free
plan runs 20 jobs at once across the account, shared with every agent's
remote suite (565)."""
PROCESSES = 3
"""pytest processes side by side on each machine, 1-4 (GitHub's 4 CPUs)."""
POLL_S = 20
"""Seconds between looks at the runs, 10-60: two runs, about 3 calls each."""
WAIT_S = 50 * 60
"""Seconds to wait for both runs before giving up, under the job's 60 min:
a shard's own limit is 30 min, plus a queue behind other runs."""
RETRY_S = (5, 15, 45)
"""Seconds before each new try of a call that only reads (remote_test.py,
569: one GitHub 500 while polling once ended a run)."""
BUDGET = re.compile(r"over its [\d.]+ ms \(any one run|the interface thread froze")
"""A timing budget's failure (tests/budget_judge.py). GitHub's VMs are slower
and noisier than this PC (565), so a budget missed there is listed, not
failed, as remote_test.py lists it: the train's own runners judge the
budgets (the UI lab, Checks (Windows)). Searched in the failure's message
and, as pytest shortens that to about 500 characters, in its E lines
(polyglotic-hq 1004)."""
LONG_FILE_S = 60.0
"""A test file this long or longer keeps its tests' times, to cut it in parts."""
STATE = ROOT / "build" / "public-copy"
"""This run's branches and runs (for --clean-up), the reports and the
files' times (kept between runs by the workflow's cache)."""


class CheckError(RuntimeError):
    """The run itself didn't work (exit 2)."""


# --- the plan (remote_test.py's, the same cuts) ---------------------------------


@dataclass
class Plan:
    common: list[str]
    shards: list[Any]
    each: str | None = None
    processes: int = 1

    def encoded(self) -> str:
        whole: dict[str, Any] = (
            {"each": self.each, "processes": self.processes}
            if self.each
            else {"common": self.common}
        )
        data = json.dumps({**whole, "shards": self.shards}, separators=(",", ":"))
        return base64.b64encode(zlib.compress(data.encode(), 9)).decode()


def test_files(root: Path) -> list[str]:
    """The test files pytest finds under tests/ (test_*.py, *_test.py),
    less `NOT_REMOTE`."""
    found = {
        p.relative_to(root).as_posix()
        for pattern in ("test_*.py", "*_test.py")
        for p in (root / "tests").rglob(pattern)
        if "__pycache__" not in p.parts
    }
    return sorted(f for f in found if f not in NOT_REMOTE)


def collection_order(name: str) -> tuple[str, ...]:
    """Where pytest reaches a file: each folder's entries by name."""
    return tuple(name.split("::")[0].split("/"))


def make_plan(
    root: Path,
    slices: int,
    times: dict[str, float],
    processes: int,
    nodes: dict[str, list[list[Any]]],
) -> Plan:
    """The whole suite in `slices` contiguous runs in pytest's order, cut
    where the running time (a file's time from earlier runs, else its size)
    reaches each slice's share; `processes` slices to a machine. A file
    longer than a slice whose tests' times are known is cut by its tests
    (`--deselect`). remote_test.py's make_plan, for the whole suite."""
    items: list[tuple[str, float]] = []
    for name in test_files(root):
        weight = times.get(name)
        if weight is None:
            weight = (root / name).stat().st_size / 2000  # about 1 s per 2 KB, a guess
        items.append((name, weight))
    items.sort(key=lambda item: collection_order(item[0]))
    total = sum(weight for _, weight in items) or 1.0
    parts: dict[str, list[list[str]]] = {}
    if nodes and slices > 1:
        split: list[tuple[str, float]] = []
        for name, weight in items:
            known = nodes.get(name) or []
            pieces = min(len(known), int(-(-weight // (total / slices))))
            if pieces < 2:
                split.append((name, weight))
                continue
            share, load = sum(t for _, t in known) / pieces, 0.0
            groups: list[list[str]] = [[]]
            for nid, seconds in known:
                if load >= share * len(groups) and len(groups) < pieces:
                    groups.append([])
                groups[-1].append(nid)
                load += seconds
            parts[name] = groups
            for index, group in enumerate(groups):
                part = sum(t for n, t in known if n in group) / max(load, 1e-9)
                split.append((f"{name}#{index}", weight * part))
        items = split
    slices = max(1, min(slices, len(items)))
    plan: list[list[str]] = [[] for _ in range(slices)]
    done = 0.0
    for name, weight in items:
        # the slice whose share this file's middle falls in
        index = min(slices - 1, int((done + weight / 2) / total * slices))
        plan[index].append(name)
        done += weight
    arguments = [as_arguments(share, parts) for share in plan if share]
    per = -(-len(arguments) // max(1, -(-len(arguments) // max(1, processes))))
    return Plan([], [arguments[i : i + per] for i in range(0, len(arguments), per)])


def as_arguments(share: list[str], parts: dict[str, list[list[str]]]) -> list[str]:
    """A slice's pytest arguments: a part of a cut file ("file#2") as the file
    less the tests of its parts that aren't in this slice."""
    arguments: list[str] = []
    for item in share:
        name, _, index = item.partition("#")
        if not index:
            arguments.append(item)
            continue
        if name in arguments:
            continue  # its other part in this slice wrote it already
        here = {int(x.partition("#")[2]) for x in share if x.partition("#")[0] == name}
        kept = [
            nid for i, group in enumerate(parts[name]) if i in here for nid in group
        ]
        arguments.append(name)
        for i, group in enumerate(parts[name]):
            if i in here:
                continue
            for nid in group:
                if not any(other.startswith(nid) for other in kept):
                    arguments += ["--deselect", nid]
    return arguments


def static_plan() -> Plan:
    """The static checks as one machine's items, one after another."""
    return Plan([], [list(STATIC)], each="{}", processes=1)


# --- the tree ---------------------------------------------------------------------


def git(*args: str, env: dict[str, str] | None = None, cwd: Path = ROOT) -> str:
    done = subprocess.run(
        ["git", *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if done.returncode != 0:
        sys.stderr.write(done.stderr[-2000:])
        raise CheckError(f"git {args[0]} failed")
    return done.stdout.strip()


def public_tree(root: Path, work: Path) -> str:
    """HEAD's tree less `LEFT_OUT`, in the checkout's own object store (the
    checkout's index doesn't change)."""
    env = {**os.environ, "GIT_INDEX_FILE": str(work / "index")}
    git("read-tree", "HEAD", env=env, cwd=root)
    for path in LEFT_OUT:
        git(
            "rm",
            "-r",
            "-q",
            "--cached",
            "--ignore-unmatch",
            "--",
            path.rstrip("/"),
            env=env,
            cwd=root,
        )
    return git("write-tree", env=env, cwd=root)


def scan(
    root: Path, tree: str, work: Path, gitleaks: str, owner: re.Pattern[str]
) -> None:
    """The mirrors' scans of the tree as it would be pushed: gitleaks with
    the repo's own rules, and none of the owner's patterns in a text file.
    Says only where, never what."""
    copy = work / "tree"
    copy.mkdir()
    archive = subprocess.Popen(
        ["git", "archive", tree], cwd=root, stdout=subprocess.PIPE
    )
    assert archive.stdout is not None
    with tarfile.open(fileobj=archive.stdout, mode="r|") as stream:
        stream.extractall(copy, filter="data")
    if archive.wait() != 0:
        raise CheckError("git archive failed")
    command = [
        gitleaks,
        "dir",
        str(copy),
        "--no-banner",
        "--redact",
        "--exit-code",
        "1",
    ]
    if (copy / ".gitleaks.toml").is_file():
        command += ["--config", str(copy / ".gitleaks.toml")]
    leaks = subprocess.run(
        command, capture_output=True, text=True, errors="replace", check=False
    )
    if leaks.returncode != 0:
        raise CheckError(
            "gitleaks found something in the tree: nothing was pushed\n"
            + leaks.stdout[-1500:]
        )
    hits = []
    for path in sorted(copy.rglob("*")):
        if path.is_file():
            data = path.read_bytes()
            if b"\0" not in data[:8000] and owner.search(
                data.decode("utf-8", "replace")
            ):
                hits.append(path.relative_to(copy).as_posix())
    if hits:
        raise CheckError(
            f"the owner's details are in {', '.join(hits[:10])}: nothing was pushed"
        )


# --- GitHub -----------------------------------------------------------------------


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None


class GitHub:
    """The REST API as the public copy's token (urllib: the runner has no gh)."""

    def __init__(self, token: str, opener: Callable[..., Any] | None = None) -> None:
        self._token = token
        self._open = opener or urllib.request.build_opener(_NoRedirect).open

    def call(self, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
        request = urllib.request.Request(
            API + path,
            method=method,
            data=None if body is None else json.dumps(body).encode(),
            headers={
                "Authorization": f"Bearer {self._token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "polyglotic-ci",
            },
        )
        try:
            with self._open(request, timeout=60) as answer:
                text = answer.read()
        except urllib.error.HTTPError as error:
            if error.code in (301, 302, 303, 307, 308):
                return {"location": error.headers.get("Location", "")}
            raise
        return json.loads(text) if text else None

    def read(self, path: str) -> Any:
        """A call that only reads, tried again after `RETRY_S` on a server
        error or a dropped connection."""
        for attempt, pause in enumerate(RETRY_S, 1):
            try:
                return self.call("GET", path)
            except urllib.error.HTTPError as error:
                if error.code < 500:
                    raise
                said = f"HTTP {error.code}"
            except (urllib.error.URLError, TimeoutError) as error:
                said = str(error)[:80]
            print(
                f"  GitHub didn't answer ({said}): again in {pause} s ({attempt}/{len(RETRY_S)})",
                flush=True,
            )
            time.sleep(pause)
        return self.call("GET", path)

    def quietly(self, method: str, path: str) -> None:
        """A clean-up call whose failure changes nothing."""
        with suppress(urllib.error.URLError, TimeoutError, ValueError):
            self.call(method, path)


def newest_base(github: GitHub) -> tuple[str, str] | None:
    """The copy's newest base snapshot, (branch, sha), or None."""
    refs = github.read(f"/repos/{PUBLIC}/git/matching-refs/heads/{BASE}") or []
    named = sorted(
        (r["ref"].removeprefix("refs/heads/"), r["object"]["sha"]) for r in refs
    )
    return named[-1] if named else None


def fetch_base(github: GitHub, root: Path) -> str | None:
    """The newest base commit, fetched (the copy is public: no token), or
    None for a whole-tree push, saying why. A base is a commit with no
    parent: no `--depth`, which would mark the checkout shallow."""
    try:
        found = newest_base(github)
    except (urllib.error.URLError, TimeoutError, ValueError) as error:
        print(f"  no base: GitHub didn't list them ({type(error).__name__})")
        return None
    if not found:
        print("  no base of main on the copy yet")
        return None
    branch, sha = found
    command = ["git", "fetch", "-q", "--no-tags", f"https://github.com/{PUBLIC}.git"]
    done = subprocess.run(
        [*command, f"refs/heads/{branch}"],
        cwd=root,
        capture_output=True,
        text=True,
        errors="replace",
        check=False,
    )
    fetched = git("rev-parse", "FETCH_HEAD", cwd=root) if done.returncode == 0 else ""
    if fetched != sha:
        said = done.stderr.strip().splitlines()
        print(
            f"  no base: {branch} {said[-1][:120] if said else 'changed while fetched'}"
        )
        return None
    return sha


@contextmanager
def token_header(token: str) -> Iterator[dict[str, str]]:
    """git's environment with the token as an HTTP header for github.com, set
    through GIT_CONFIG_* (never in a command line or a URL)."""
    basic = base64.b64encode(f"x-access-token:{token}".encode()).decode()
    yield {
        **os.environ,
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": "http.https://github.com/.extraheader",
        "GIT_CONFIG_VALUE_0": f"AUTHORIZATION: basic {basic}",
        "GIT_TERMINAL_PROMPT": "0",
    }


def push(root: Path, sha: str, branches: Sequence[str], token: str) -> None:
    """The commit to each scratch branch in one push, tried three times
    (GitHub refuses a push now and then)."""
    refs = [f"{sha}:refs/heads/{branch}" for branch in branches]
    with token_header(token) as env:
        for wait_s in (10, 30, 0):
            done = subprocess.run(
                ["git", "push", "-q", f"https://github.com/{PUBLIC}.git", *refs],
                cwd=root,
                env=env,
                capture_output=True,
                text=True,
                errors="replace",
                check=False,
            )
            if done.returncode == 0:
                return
            said = done.stderr.strip().splitlines()
            if not wait_s:
                sys.stderr.write("\n".join(said[-6:]) + "\n")
                raise CheckError("git push to the public copy failed three times")
            print(
                f"  the push was refused ({said[-1][:120] if said else 'no reason given'}); again in {wait_s} s"
            )
            time.sleep(wait_s)


def start(github: GitHub, branch: str, plan: Plan) -> int:
    """remote-test.yml on the branch; its run's id."""
    body = {
        "ref": "main",
        "inputs": {
            "ref": branch,
            "os": "linux",
            "shards": json.dumps(list(range(len(plan.shards)))),
            "plan": plan.encoded(),
        },
        "return_run_details": True,
    }
    answer = github.call(
        "POST", f"/repos/{PUBLIC}/actions/workflows/{WORKFLOW}/dispatches", body
    )
    if isinstance(answer, dict) and answer.get("workflow_run_id"):
        return int(answer["workflow_run_id"])
    # an older API answers 204: the run's title is its branch (run-name)
    for _ in range(40):
        time.sleep(3)
        listed = github.read(
            f"/repos/{PUBLIC}/actions/workflows/{WORKFLOW}/runs?event=workflow_dispatch&per_page=40"
        )
        for run in listed.get("workflow_runs", []):
            if run.get("display_title") == branch:
                return int(run["id"])
    raise CheckError("the run didn't appear on the public copy within 2 minutes")


def link(run_id: int) -> str:
    return f"https://github.com/{PUBLIC}/actions/runs/{run_id}"


def wait(
    github: GitHub, runs: dict[str, int], sleep: Callable[[float], None] = time.sleep
) -> None:
    """Until every run has finished, saying when each job does."""
    seen: set[tuple[str, str]] = set()
    began = time.monotonic()
    pending = dict(runs)
    while pending:
        for name, run_id in list(pending.items()):
            jobs = github.read(
                f"/repos/{PUBLIC}/actions/runs/{run_id}/jobs?per_page=50"
            ).get("jobs", [])
            for job in jobs:
                if job.get("status") == "completed" and (name, job["name"]) not in seen:
                    seen.add((name, job["name"]))
                    print(
                        f"  {name} / {job['name']}: {job.get('conclusion')}", flush=True
                    )
            if (
                github.read(f"/repos/{PUBLIC}/actions/runs/{run_id}").get("status")
                == "completed"
            ):
                del pending[name]
        if pending:
            if time.monotonic() - began > WAIT_S:
                raise CheckError(
                    f"waited {WAIT_S // 60} min for the public copy: {', '.join(pending)} not done"
                )
            sleep(POLL_S)


def fetch_reports(
    github: GitHub,
    run_id: int,
    into: Path,
    download: Callable[[str], bytes] | None = None,
) -> list[Path]:
    """The run's JUnit reports, brought back and deleted from the copy. An
    artifact's link redirects to storage that must not see the token."""
    into.mkdir(parents=True, exist_ok=True)
    get = download or (lambda url: urllib.request.urlopen(url, timeout=120).read())
    listed = github.read(
        f"/repos/{PUBLIC}/actions/runs/{run_id}/artifacts?per_page=100"
    )
    for artifact in listed.get("artifacts", []):
        moved = github.call(
            "GET", f"/repos/{PUBLIC}/actions/artifacts/{artifact['id']}/zip"
        )
        location = moved.get("location") if isinstance(moved, dict) else None
        if location:
            with zipfile.ZipFile(io.BytesIO(get(location))) as archive:
                for name in archive.namelist():
                    if re.fullmatch(r"junit-[\w-]+\.xml", Path(name).name):
                        (into / Path(name).name).write_bytes(archive.read(name))
        github.quietly("DELETE", f"/repos/{PUBLIC}/actions/artifacts/{artifact['id']}")
    return sorted(into.glob("junit-*.xml"))


def missing_reports(plan: Plan, reports: list[Path]) -> list[str]:
    """The reports a run should have brought back and didn't ("shard" or
    "shard-part"): a pytest process that crashed writes none."""
    have = {path.stem.removeprefix("junit-") for path in reports}
    expected: list[str] = []
    for shard, share in enumerate(plan.shards):
        nested = not plan.each and bool(share) and isinstance(share[0], list)
        expected += (
            [f"{shard}-{part}" for part in range(len(share))]
            if nested
            else [str(shard)]
        )
    return [name for name in expected if name not in have]


# --- the results ------------------------------------------------------------------


@dataclass
class Results:
    passed: int = 0
    skipped: int = 0
    failed: list[tuple[str, str, str]] = field(
        default_factory=list
    )  # node id, message, text
    over_budget: list[tuple[str, str, str]] = field(default_factory=list)
    file_times: dict[str, float] = field(default_factory=dict)
    node_times: dict[str, float] = field(default_factory=dict)


def node_id(case: ET.Element) -> str:
    file = (case.get("file") or "").replace("\\", "/")
    classname = case.get("classname") or ""
    name = case.get("name") or ""
    if file and classname:
        stem = file.removesuffix(".py")
        inner = classname[len(stem.replace("/", ".")) :].lstrip(".")
        return "::".join(part for part in (file, inner, name) if part)
    return f"{classname.replace('.', '/')}.py::{name}" if classname else name


def read_reports(paths: list[Path], results: Results | None = None) -> Results:
    results = results or Results()
    for path in paths:
        for case in ET.parse(path).getroot().iter("testcase"):
            nid = node_id(case)
            seconds = float(case.get("time") or 0)
            results.node_times[nid] = results.node_times.get(nid, 0.0) + seconds
            file = nid.split("::")[0]
            results.file_times[file] = results.file_times.get(file, 0.0) + seconds
            outcome = next(
                (c for c in case if c.tag in ("failure", "error", "skipped")), None
            )
            if outcome is None:
                results.passed += 1
            elif outcome.tag == "skipped":
                results.skipped += 1
            else:
                text = outcome.text or ""
                for extra in ("system-out", "system-err"):
                    for part in case.iter(extra):
                        if part.text and part.text.strip():
                            text += f"\n----- {extra} -----\n{part.text.rstrip()}"
                message = (outcome.get("message") or "").splitlines()
                entry = (nid, message[0][:200] if message else "", text)
                # pytest shortens `message` (a known debt's words come first,
                # tests/budget_debts.py): the raised error's own E lines too
                raised = "\n".join(
                    line
                    for line in (outcome.text or "").splitlines()
                    if line.startswith("E ")
                )
                if BUDGET.search(outcome.get("message") or "") or BUDGET.search(raised):
                    results.over_budget.append(entry)
                else:
                    results.failed.append(entry)
    return results


def report(results: Results, missing: list[str]) -> int:
    for nid, _, text in results.failed:
        print(f"::group::FAILED {nid}\n{text.rstrip()[-6000:]}\n::endgroup::")
    for nid, message, _ in results.failed:
        print(f"FAILED {nid} - {message}")
    for nid, message, _ in results.over_budget:
        print(
            f"::warning title=Over a timing budget on GitHub's machine (the train judges budgets)::{nid} - {message}"
        )
    for name in missing:
        print(f"NO REPORT {name}")
    print(summary(results, missing))
    return 1 if (results.failed or missing) else 0


def summary(results: Results, missing: list[str]) -> str:
    parts = [f"{len(results.failed)} failed"] if results.failed else []
    parts.append(f"{results.passed} passed")
    if results.skipped:
        parts.append(f"{results.skipped} skipped")
    if results.over_budget:
        parts.append(f"{len(results.over_budget)} over budget")
    if missing:
        parts.append(f"{len(missing)} reports missing")
    return ", ".join(parts)


def remember(results: Results, times_path: Path, nodes_path: Path) -> None:
    """Each file's time, and each long file's tests' times, for the next cut."""
    times = load(times_path)
    times.update(
        {name: round(s, 2) for name, s in results.file_times.items() if name != "each"}
    )
    nodes = load(nodes_path)
    for name, seconds in results.file_times.items():
        if seconds >= LONG_FILE_S and name != "each":
            nodes[name] = [
                [nid, round(t, 2)]
                for nid, t in results.node_times.items()
                if nid.split("::")[0] == name
            ]
    times_path.parent.mkdir(parents=True, exist_ok=True)
    times_path.write_text(json.dumps(times, indent=0, sort_keys=True), encoding="utf-8")
    nodes_path.write_text(json.dumps(nodes, indent=0, sort_keys=True), encoding="utf-8")


def load(path: Path) -> dict[str, Any]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


# --- the whole --------------------------------------------------------------------


def settings() -> tuple[str, re.Pattern[str], str]:
    """The token, the owner's patterns and gitleaks, or why the check can't
    run. Fails closed: with no patterns nothing is pushed."""
    token = os.environ.get("PUBLIC_COPY_TOKEN", "")
    patterns = os.environ.get("PUBLIC_COPY_SCAN", "")
    gitleaks = os.environ.get("GITLEAKS", "")
    lacking = [
        name
        for name, value in (
            ("PUBLIC_COPY_TOKEN", token),
            ("PUBLIC_COPY_SCAN", patterns),
            ("GITLEAKS", gitleaks),
        )
        if not value
    ]
    if lacking:
        raise CheckError(
            f"{' and '.join(lacking)} not set: nothing was pushed (polyglotic-hq 981's report)"
        )
    try:
        owner = re.compile(patterns, re.IGNORECASE)
    except re.error:
        raise CheckError(
            "PUBLIC_COPY_SCAN isn't a regular expression: nothing was pushed"
        ) from None
    return token, owner, gitleaks


def author(github: GitHub) -> tuple[str, str]:
    """The copy's commit author: the owner's GitHub no-reply address, as
    remote_test.py's (`PUBLIC_COPY_AUTHOR` "login|id", else the token's user)."""
    given = os.environ.get("PUBLIC_COPY_AUTHOR", "")
    if "|" in given:
        login, number = given.split("|", 1)
    else:
        user = github.read("/user")
        login, number = user["login"], str(user["id"])
    return login, f"{number}+{login}@users.noreply.github.com"


def save_state(state: dict[str, Any]) -> None:
    STATE.mkdir(parents=True, exist_ok=True)
    (STATE / "state.json").write_text(json.dumps(state), encoding="utf-8")


def clean_up(github: GitHub, state: dict[str, Any]) -> None:
    """Cancel any run still going, delete the reports and the branches. Never
    raises: it runs on the way out of an error too."""
    for run_id in state.get("runs", {}).values():
        try:
            if (
                github.call("GET", f"/repos/{PUBLIC}/actions/runs/{run_id}").get(
                    "status"
                )
                != "completed"
            ):
                github.quietly("POST", f"/repos/{PUBLIC}/actions/runs/{run_id}/cancel")
                print(f"  cancelled {link(run_id)}")
            listed = github.call(
                "GET", f"/repos/{PUBLIC}/actions/runs/{run_id}/artifacts?per_page=100"
            )
        except (urllib.error.URLError, TimeoutError, ValueError, AttributeError):
            continue
        for artifact in listed.get("artifacts", []):
            github.quietly(
                "DELETE", f"/repos/{PUBLIC}/actions/artifacts/{artifact['id']}"
            )
    for branch in state.get("branches", []):
        github.quietly("DELETE", f"/repos/{PUBLIC}/git/refs/heads/{branch}")


def write_summary(lines: list[str]) -> None:
    where = os.environ.get("GITHUB_STEP_SUMMARY")
    if where:
        with open(where, "a", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")


def check(
    root: Path, github: GitHub, token: str, owner: re.Pattern[str], gitleaks: str
) -> int:
    head = git("rev-parse", "HEAD", cwd=root)
    label = re.sub(
        r"[^A-Za-z0-9._-]+", "-", os.environ.get("PUBLIC_COPY_LABEL", "local")
    )[:40]
    stamp = f"{os.environ.get('GITHUB_RUN_ID', int(time.time()))}-{os.environ.get('GITHUB_RUN_ATTEMPT', '1')}"
    branches = {
        kind: f"remote-test/ci-{label}-{head[:8]}-{stamp}-{kind}"
        for kind in ("tests", "static")
    }
    state: dict[str, Any] = {"branches": [], "runs": {}}
    times_path, nodes_path = STATE / "times-linux.json", STATE / "nodes-linux.json"
    plans = {
        "tests": make_plan(
            root, SHARDS * PROCESSES, load(times_path), PROCESSES, load(nodes_path)
        ),
        "static": static_plan(),
    }
    try:
        with tempfile.TemporaryDirectory(prefix="public-copy-") as scratch:
            tree = public_tree(root, Path(scratch))
            scan(root, tree, Path(scratch), gitleaks, owner)
        login, email = author(github)
        parent = fetch_base(github, root)
        env = {**os.environ, "GIT_AUTHOR_NAME": login, "GIT_AUTHOR_EMAIL": email,
               "GIT_COMMITTER_NAME": login, "GIT_COMMITTER_EMAIL": email}  # fmt: skip
        message = f"Remote test of the desktop (private {head[:8]}, CI)"
        sha = git(
            "commit-tree",
            tree,
            *(["-p", parent] if parent else []),
            "-m",
            message,
            env=env,
            cwd=root,
        )
        state["branches"] = list(branches.values())
        save_state(state)
        push(root, sha, list(branches.values()), token)
        print(
            f"  pushed {head[:8]}'s tree to {PUBLIC} ({'on its base of main' if parent else 'whole'})"
        )
        for kind, branch in branches.items():
            state["runs"][kind] = start(github, branch, plans[kind])
            save_state(state)
            print(f"  {kind}: {link(state['runs'][kind])}", flush=True)
        print(f"::notice title=Checks (Linux) on the public copy::tests {link(state['runs']['tests'])} "
              f"static {link(state['runs']['static'])}")  # fmt: skip
        wait(github, state["runs"])
        results, missing = Results(), []
        for kind, run_id in state["runs"].items():
            reports = fetch_reports(github, run_id, STATE / str(run_id))
            missing += [f"{kind} {m}" for m in missing_reports(plans[kind], reports)]
            read_reports(reports, results)
        remember(results, times_path, nodes_path)
        code = report(results, missing)
        write_summary([
            f"**Checks (Linux) on the public copy:** {'passed' if code == 0 else 'failed'} - {summary(results, missing)}",
            "",
            f"- The tests: {link(state['runs']['tests'])}",
            f"- The static checks: {link(state['runs']['static'])}",
            *[f"- FAILED `{nid}` - {message}" for nid, message, _ in results.failed[:30]],
        ])  # fmt: skip
        return code
    finally:
        # a run still going (an error, a cancelled job) is cancelled too
        clean_up(github, state)


def _interrupted(signum: int, frame: FrameType | None) -> None:
    raise KeyboardInterrupt


def main(argv: Sequence[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
    parser = argparse.ArgumentParser(
        description=__doc__.split("\n\n")[0] if __doc__ else None
    )
    parser.add_argument(
        "--clean-up",
        action="store_true",
        help="cancel and delete what this job's run left",
    )
    args = parser.parse_args(argv)
    signal.signal(signal.SIGTERM, _interrupted)  # a cancelled job: clean up as for ^C
    try:
        if args.clean_up:
            state = load(STATE / "state.json")
            if state and os.environ.get("PUBLIC_COPY_TOKEN"):
                clean_up(GitHub(os.environ["PUBLIC_COPY_TOKEN"]), state)
            return 0
        token, owner, gitleaks = settings()
        return check(ROOT, GitHub(token), token, owner, gitleaks)
    except CheckError as error:
        print(f"::error title=Checks (Linux) didn't run on the public copy::{error}")
        return 2
    except KeyboardInterrupt:
        print("stopped")  # check()'s clean-up has run on the way out
        return 2
    except (urllib.error.URLError, TimeoutError, ValueError, KeyError) as error:
        print(
            f"::error title=Checks (Linux) didn't run on the public copy::GitHub: {type(error).__name__} {error}"[
                :400
            ]
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
