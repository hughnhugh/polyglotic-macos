"""`tools/public_copy_checks.py`: CI's Checks (Linux) on the public copy's
machines, sent and waited for from the light runner (polyglotic-hq 981).
What goes public is remote_test.py's tree and no more, scanned first; the
token never reaches a command line or the storage an artifact redirects
to; a failed test, a missing report or a missing secret is never a pass.
A stand-in GitHub here; the real one was run by hand (981's report)."""

import base64
import io
import json
import re
import subprocess
import urllib.error
import zipfile
import zlib
from email.message import Message
from pathlib import Path
from typing import Any

import pytest

from tools import public_copy_checks as checks


def git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, capture_output=True, text=True, check=True
    ).stdout.strip()


def repo(root: Path, files: dict[str, str]) -> Path:
    root.mkdir(parents=True)
    git(root, "init", "-q")
    for name, text in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text, encoding="utf-8")
    git(root, "add", "-A")
    git(
        root,
        "-c",
        "user.name=t",
        "-c",
        "user.email=t@example.com",
        "commit",
        "-q",
        "-m",
        "x",
    )
    return root


class StandIn:
    """GitHub's API as the tool calls it: answers by (method, path) prefix,
    every call recorded."""

    def __init__(self, answers: dict[tuple[str, str], Any]) -> None:
        self.answers = answers
        self.calls: list[tuple[str, str, Any]] = []

    def call(self, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
        self.calls.append((method, path, body))
        for (m, prefix), answer in self.answers.items():
            if m == method and path.startswith(prefix):
                return answer(path) if callable(answer) else answer
        return None

    def read(self, path: str) -> Any:
        return self.call("GET", path)

    def quietly(self, method: str, path: str) -> None:
        self.call(method, path)


def stand_in(answers: dict[tuple[str, str], Any]) -> Any:
    """A StandIn where the tool wants its GitHub."""
    return StandIn(answers)


def decoded(plan: checks.Plan) -> dict[str, Any]:
    return json.loads(zlib.decompress(base64.b64decode(plan.encoded())))


def test_the_plan_runs_every_test_file_once_in_pytests_order(tmp_path: Path) -> None:
    files = {
        "tests/test_a.py": "x" * 9000,
        "tests/test_schema_versions.py": "x",
        "tests/tools/test_b.py": "x" * 3000,
        "tests/ui_next/test_c.py": "x" * 6000,
        "tests/ui_next/test_d.py": "x" * 6000,
        "tests/helper.py": "x",
    }
    for name, text in files.items():
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text(text, encoding="utf-8")
    plan = checks.make_plan(tmp_path, 4, {}, 2, {})
    slices = [args for machine in plan.shards for args in machine]
    flat = [arg for args in slices for arg in args]
    assert flat == [
        "tests/test_a.py",
        "tests/tools/test_b.py",
        "tests/ui_next/test_c.py",
        "tests/ui_next/test_d.py",
    ]  # contiguous, once each; no schema test (the copy has no tags), no helper
    assert len(plan.shards) == 2 and all(len(m) == 2 for m in plan.shards)
    assert decoded(plan) == {"common": [], "shards": plan.shards}


def test_a_long_file_with_known_tests_is_cut_by_its_tests(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/test_long.py").write_text("x", encoding="utf-8")
    (tmp_path / "tests/test_short.py").write_text("x", encoding="utf-8")
    nodes = {
        "tests/test_long.py": [[f"tests/test_long.py::t{i}", 10.0] for i in range(4)]
    }
    times = {"tests/test_long.py": 40.0, "tests/test_short.py": 1.0}
    plan = checks.make_plan(tmp_path, 2, times, 1, nodes)
    first, second = (machine[0] for machine in plan.shards)
    assert first[0] == second[0] == "tests/test_long.py"
    assert "--deselect" in first and "--deselect" in second
    kept_first = {f"tests/test_long.py::t{i}" for i in range(4)} - set(first)
    kept_second = {f"tests/test_long.py::t{i}" for i in range(4)} - set(second)
    assert kept_first.isdisjoint(kept_second)  # each test runs in one slice


def test_the_static_checks_are_one_machines_commands() -> None:
    plan = checks.static_plan()
    data = decoded(plan)
    assert data["each"] == "{}" and data["processes"] == 1
    assert data["shards"] == [list(checks.STATIC)]
    assert checks.missing_reports(plan, []) == ["0"]


def test_the_public_tree_leaves_out_what_a_public_copy_never_carries(
    tmp_path: Path,
) -> None:
    root = repo(
        tmp_path / "r",
        {
            "src/a.py": "a = 1\n",
            "CLAUDE.md": "agent notes\n",
            "AGENTS.md": "agent notes\n",
            ".claude/settings.json": "{}\n",
            ".github/dependabot.yml": "x\n",
            ".github/workflows/ci.yml": "x\n",
        },
    )
    (root / "untracked.txt").write_text("a note at the root\n", encoding="utf-8")
    work = tmp_path / "w"
    work.mkdir()
    tree = checks.public_tree(root, work)
    names = git(root, "ls-tree", "-r", "--name-only", tree).splitlines()
    assert names == [".github/workflows/ci.yml", "src/a.py"]
    assert (
        git(root, "status", "--porcelain") == "?? untracked.txt"
    )  # its index unchanged


def scanned(tmp_path: Path, files: dict[str, str], gitleaks_code: int = 0) -> None:
    root = repo(tmp_path / "r", files)
    work = tmp_path / "w"
    work.mkdir()
    tree = checks.public_tree(root, work)
    real = subprocess.run

    def run(command: list[str], **kwargs: Any) -> Any:
        if command[0] == "gitleaks-stand-in":
            return subprocess.CompletedProcess(
                command, gitleaks_code, "leak: src/a.py", ""
            )
        return real(command, **kwargs)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(checks.subprocess, "run", run)
        checks.scan(
            root,
            tree,
            work,
            "gitleaks-stand-in",
            re.compile("ex owner|exowner", re.IGNORECASE),
        )


def test_the_owners_details_stop_the_push_and_are_never_printed(tmp_path: Path) -> None:
    with pytest.raises(checks.CheckError) as raised:
        scanned(tmp_path, {"src/a.py": "a = 1\n", "docs/b.md": "by Ex Owner\n"})
    assert "docs/b.md" in str(raised.value) and "Ex Owner" not in str(raised.value)
    scanned(tmp_path / "clean", {"src/a.py": "a = 1\n"})  # nothing found: no error


def test_a_gitleaks_finding_stops_the_push(tmp_path: Path) -> None:
    with pytest.raises(checks.CheckError, match="gitleaks"):
        scanned(tmp_path, {"src/a.py": "a = 1\n"}, gitleaks_code=1)


def test_no_secret_no_check(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fails closed: without the owner's patterns nothing is pushed."""
    monkeypatch.setenv("PUBLIC_COPY_TOKEN", "t")
    monkeypatch.setenv("GITLEAKS", "g")
    monkeypatch.delenv("PUBLIC_COPY_SCAN", raising=False)
    with pytest.raises(checks.CheckError, match="PUBLIC_COPY_SCAN not set"):
        checks.settings()
    monkeypatch.setenv("PUBLIC_COPY_SCAN", "a|b")
    assert checks.settings()[0] == "t"


def test_the_token_goes_to_git_through_its_environment_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[tuple[list[str], dict[str, str]]] = []

    def run(command: list[str], **kwargs: Any) -> Any:
        seen.append((command, kwargs["env"]))
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(checks.subprocess, "run", run)
    checks.push(
        Path("."),
        "abc",
        ["remote-test/ci-x-tests", "remote-test/ci-x-static"],
        "s3cret",
    )
    ((command, env),) = seen
    assert not any("s3cret" in arg for arg in command)
    assert command[-2:] == [
        "abc:refs/heads/remote-test/ci-x-tests",
        "abc:refs/heads/remote-test/ci-x-static",
    ]
    header = env["GIT_CONFIG_VALUE_0"].removeprefix("AUTHORIZATION: basic ")
    assert base64.b64decode(header).decode() == "x-access-token:s3cret"
    assert env["GIT_CONFIG_KEY_0"] == "http.https://github.com/.extraheader"


def test_a_run_is_found_by_its_id_or_else_by_its_branch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(checks.time, "sleep", lambda s: None)
    dispatches = ("POST", f"/repos/{checks.PUBLIC}/actions/workflows/")
    github = stand_in({dispatches: {"workflow_run_id": 7, "run_url": "x"}})
    assert checks.start(github, "remote-test/b", checks.static_plan()) == 7
    body = github.calls[0][2]
    assert body["ref"] == "main" and body["inputs"]["ref"] == "remote-test/b"
    assert body["inputs"]["os"] == "linux" and body["inputs"]["shards"] == "[0]"
    runs = {
        "workflow_runs": [
            {"id": 5, "display_title": "other"},
            {"id": 9, "display_title": "remote-test/b"},
        ]
    }
    older = stand_in(
        {dispatches: None, ("GET", f"/repos/{checks.PUBLIC}/actions/workflows/"): runs}
    )
    assert checks.start(older, "remote-test/b", checks.static_plan()) == 9


def junit(cases: str) -> bytes:
    return f"<testsuites><testsuite>{cases}</testsuite></testsuites>".encode()


def zipped(name: str, data: bytes) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(name, data)
    return buffer.getvalue()


def test_reports_come_back_without_the_token_and_are_deleted(tmp_path: Path) -> None:
    report = junit(
        '<testcase file="tests/test_a.py" classname="tests.test_a" name="t" time="1"/>'
    )
    artifacts = f"/repos/{checks.PUBLIC}/actions/artifacts/"
    github = stand_in({
        ("GET", f"/repos/{checks.PUBLIC}/actions/runs/3/artifacts"): {"artifacts": [{"id": 11}]},
        ("GET", artifacts): {"location": "https://storage.example/blob?sig=1"},
    })  # fmt: skip
    fetched: list[str] = []

    def download(url: str) -> bytes:
        fetched.append(url)  # a plain download: GitHub's token isn't passed to it
        return zipped("junit-0-1.xml", report)

    found = checks.fetch_reports(github, 3, tmp_path, download)
    assert [p.name for p in found] == ["junit-0-1.xml"]
    assert fetched == ["https://storage.example/blob?sig=1"]
    assert ("DELETE", artifacts + "11", None) in github.calls


def test_the_token_isnt_sent_after_a_redirect() -> None:
    """The API's artifact link answers 302 to storage: the tool reads the
    Location itself instead of following it with the token."""
    sent: list[Any] = []

    def opener(request: Any, timeout: float) -> Any:
        sent.append(request)
        headers = Message()
        headers["Location"] = "https://s/x"
        raise urllib.error.HTTPError(request.full_url, 302, "Found", headers, None)

    github = checks.GitHub("tok", opener)
    assert github.call("GET", "/repos/x/actions/artifacts/1/zip") == {
        "location": "https://s/x"
    }
    assert len(sent) == 1 and sent[0].get_header("Authorization") == "Bearer tok"


def test_a_failure_or_a_missing_report_is_never_a_pass(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    passing = tmp_path / "junit-0-0.xml"
    passing.write_bytes(
        junit(
            '<testcase file="tests/test_a.py" classname="tests.test_a" name="t" time="2"/>'
        )
    )
    failing = tmp_path / "junit-0.xml"
    failing.write_bytes(junit(
        '<testcase classname="each" name="uv run --no-sync mypy" file="each" time="9">'
        '<failure message="exit 1">src/x.py:1: error: no</failure></testcase>'
    ))  # fmt: skip
    results = checks.read_reports([passing])
    assert checks.report(results, []) == 0
    assert checks.report(results, ["tests 0-1"]) == 1
    results = checks.read_reports([failing], results)
    assert checks.report(results, []) == 1
    said = capsys.readouterr().out
    assert (
        "FAILED each::uv run --no-sync mypy - exit 1" in said
        and "src/x.py:1: error: no" in said
    )
    assert checks.summary(results, []) == "1 failed, 1 passed"


def test_the_times_are_kept_for_the_next_cut(tmp_path: Path) -> None:
    results = checks.Results(
        file_times={"tests/test_a.py": 70.0, "each": 9.0},
        node_times={"tests/test_a.py::t1": 30.0, "tests/test_a.py::t2": 40.0},
    )
    checks.remember(results, tmp_path / "times.json", tmp_path / "nodes.json")
    assert checks.load(tmp_path / "times.json") == {"tests/test_a.py": 70.0}
    assert checks.load(tmp_path / "nodes.json") == {
        "tests/test_a.py": [
            ["tests/test_a.py::t1", 30.0],
            ["tests/test_a.py::t2", 40.0],
        ]
    }


def test_waiting_ends_when_every_run_has(monkeypatch: pytest.MonkeyPatch) -> None:
    looks = {"n": 0}

    def status(path: str) -> dict[str, str]:
        looks["n"] += 1
        return {"status": "completed" if looks["n"] > 2 else "in_progress"}

    github = stand_in({
        ("GET", f"/repos/{checks.PUBLIC}/actions/runs/1/jobs"): {"jobs": [{"name": "linux 0", "status": "completed", "conclusion": "success"}]},
        ("GET", f"/repos/{checks.PUBLIC}/actions/runs/2/jobs"): {"jobs": []},
        ("GET", f"/repos/{checks.PUBLIC}/actions/runs/"): status,
    })  # fmt: skip
    slept: list[float] = []
    checks.wait(github, {"tests": 1, "static": 2}, slept.append)
    assert slept == [checks.POLL_S]


def test_clean_up_cancels_a_run_still_going_and_deletes_the_branches() -> None:
    github = stand_in({
        ("GET", f"/repos/{checks.PUBLIC}/actions/runs/4/artifacts"): {"artifacts": []},
        ("GET", f"/repos/{checks.PUBLIC}/actions/runs/4"): {"status": "in_progress"},
    })  # fmt: skip
    checks.clean_up(
        github, {"runs": {"tests": 4}, "branches": ["remote-test/ci-a-tests"]}
    )
    assert (
        "POST",
        f"/repos/{checks.PUBLIC}/actions/runs/4/cancel",
        None,
    ) in github.calls
    assert (
        "DELETE",
        f"/repos/{checks.PUBLIC}/git/refs/heads/remote-test/ci-a-tests",
        None,
    ) in github.calls


def test_what_leaves_is_what_remote_test_sends() -> None:
    """The same rules as polyglotic-hq's scripts/remote_test.py (its
    LEFT_OUT and NOT_REMOTE, 2026-11-27), which this repo can't read: a
    change to one is a change to both."""
    assert checks.LEFT_OUT == (
        "CLAUDE.md",
        "AGENTS.md",
        ".claude/",
        ".cursor/",
        ".github/dependabot.yml",
    )
    assert checks.NOT_REMOTE == ("tests/test_schema_versions.py",)


def test_a_missed_timing_budget_is_listed_not_failed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """As remote_test.py: GitHub's VMs are noisier than this PC (565), and
    the train's own runners judge the budgets."""
    path = tmp_path / "junit-0-0.xml"
    path.write_bytes(
        junit(
            '<testcase file="tests/test_t.py" classname="tests.test_t" name="b" time="1">'
            '<failure message="the frame took 30 ms, over its 8.0 ms (any one run)">'
            "x</failure></testcase>"
        )
    )
    results = checks.read_reports([path])
    assert checks.report(results, []) == 0
    assert "Over a timing budget" in capsys.readouterr().out
    assert checks.summary(results, []) == "0 passed, 1 over budget"


def test_a_missed_budget_whose_message_pytest_shortened_is_listed_not_failed(
    tmp_path: Path,
) -> None:
    """polyglotic-hq 1004: pytest shortens a failure's `message` attribute
    (about 500 characters), and a known debt's words come first (`tests/
    budget_debts.py`), so the look drag's "over its 8 ms (any one run" was
    cut off and failed five pull requests on the 0.1.13 train. The budget's
    words are read from the report's E lines too; another failure that
    only mentions a budget elsewhere in its report still fails."""
    debt = "worse than its known debt's ceiling of 10 ms (" + "measured " * 60 + "): "
    said = (
        f"AssertionError: {debt}frame over its 8 ms (any one run 50 ms) in both tries"
    )
    shortened = said[:480] + "...\n[+1 more line; full report in element text]"
    path = tmp_path / "junit-0-0.xml"
    path.write_bytes(
        junit(
            '<testcase file="tests/ui/test_d.py" classname="tests.ui.test_d"'
            f' name="drag" time="1"><failure message="{shortened}">'
            f"&gt;       assert passed, (\nE       {said}\n\ntests/budget_judge.py:300:"
            " AssertionError</failure></testcase>"
            '<testcase file="tests/test_o.py" classname="tests.test_o" name="other"'
            ' time="1"><failure message="AssertionError: assert 1 == 2">'
            "E       AssertionError: assert 1 == 2\n----- system-err -----\n"
            "frame over its 8 ms (any one run 50 ms)</failure></testcase>"
        )
    )
    results = checks.read_reports([path])
    assert [nid for nid, _, _ in results.over_budget] == ["tests/ui/test_d.py::drag"]
    assert [nid for nid, _, _ in results.failed] == ["tests/test_o.py::other"]


def test_the_base_is_fetched_whole_and_a_changed_one_is_not_used(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A base is a commit with no parent: `--depth` would only mark the
    checkout shallow (981's first run marked this PC's clone so). A base
    whose fetched commit isn't the one listed isn't built on."""
    commands: list[list[str]] = []
    fetched = {"sha": "b" * 40}

    def run(command: list[str], **kwargs: Any) -> Any:
        commands.append(command)
        said = fetched["sha"] if command[1] == "rev-parse" else ""
        return subprocess.CompletedProcess(command, 0, said, "")

    monkeypatch.setattr(checks.subprocess, "run", run)
    refs = [
        {"ref": "refs/heads/remote-test/base-20261127-x", "object": {"sha": "b" * 40}}
    ]
    github = stand_in({("GET", f"/repos/{checks.PUBLIC}/git/matching-refs/"): refs})
    assert checks.fetch_base(github, Path(".")) == "b" * 40
    fetch = commands[0]
    assert (
        fetch[:2] == ["git", "fetch"]
        and fetch[-1] == "refs/heads/remote-test/base-20261127-x"
    )
    assert not any(arg.startswith("--depth") for arg in fetch)
    fetched["sha"] = "c" * 40
    assert checks.fetch_base(github, Path(".")) is None
