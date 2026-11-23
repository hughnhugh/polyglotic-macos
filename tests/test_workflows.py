"""The workflows' checkouts keep no credentials (polyglotic-hq project 032, D5 item 4; project 066, Low 4).

By default `actions/checkout` writes the job's token into the checkout's
git config, where every later step can read it - and so can anything a
dependency runs during `uv sync`, the tests or the build. No job here
fetches or pushes after its checkout (the secret scan lists a pull
request's commits through the API with its own `GITHUB_TOKEN`; the
release's publish job uses `GH_TOKEN` for `gh release create`), so every
checkout says `persist-credentials: false`. Read as the YAML GitHub reads.
"""

import re
from pathlib import Path
from typing import Any

import yaml

WORKFLOWS = Path(__file__).resolve().parents[1] / ".github" / "workflows"


def checkouts() -> list[tuple[str, dict[str, Any]]]:
    """Every `actions/checkout` step, as (workflow / job, step)."""
    found = []
    for path in sorted(WORKFLOWS.glob("*.y*ml")):
        workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
        for job_id, job in workflow["jobs"].items():
            for step in job.get("steps") or []:
                if str(step.get("uses", "")).startswith("actions/checkout@"):
                    found.append((f"{path.name} / {job_id}", step))
    return found


def test_every_checkout_keeps_no_credentials() -> None:
    found = checkouts()
    assert len(found) >= 6, "ci, secrets, audit, package and release's two"
    keeping = [
        where
        for where, step in found
        if (step.get("with") or {}).get("persist-credentials") is not False
    ]
    assert keeping == [], "add `persist-credentials: false` to their checkout"


def test_the_tests_run_on_linux_too() -> None:
    """Decision 0038 (polyglotic-hq 179): the tests that don't need Windows
    run on the Linux runner, with Qt's libraries unpacked by
    `tools/linux_qt_libs.sh` (the runner can't install packages)."""
    ci = yaml.safe_load((WORKFLOWS / "ci.yml").read_text(encoding="utf-8"))
    linux = ci["jobs"]["linux"]
    assert linux["runs-on"] == ["self-hosted", "linux"]
    runs = [str(step.get("run", "")) for step in linux["steps"]]
    assert any("tools/linux_qt_libs.sh" in run for run in runs)
    assert any("uv run --no-sync pytest" in run for run in runs)  # in ci_memory (344)
    assert (WORKFLOWS.parents[1] / "tools" / "linux_qt_libs.sh").is_file()


def test_checks_on_windows_run_on_any_runner_labelled_checks() -> None:
    """Decision 0232 (polyglotic-hq 504): the second PC's runner carries only
    labels of its own (`gpubox`, `checks`), never `self-hosted` or
    `windows`, so it takes Checks (Windows) once it has `checks` and no
    other job: the UI lab's goldens and timings, and the release's secrets,
    stay on the user's PC by its labels alone. Its pytest took 16 minutes
    there (12-13 on the user's PC), so the job has 30."""
    windows = yaml.safe_load((WORKFLOWS / "windows.yml").read_text(encoding="utf-8"))
    release = yaml.safe_load((WORKFLOWS / "release.yml").read_text(encoding="utf-8"))
    assert windows["jobs"]["checks"]["runs-on"] == ["checks"]
    assert windows["jobs"]["checks"]["timeout-minutes"] >= 30
    on_this_pc = ["self-hosted", "windows"]
    assert windows["jobs"]["ui-lab"]["runs-on"] == on_this_pc
    assert release["jobs"]["release"]["runs-on"] == on_this_pc


def test_the_linux_tests_draw_chinese_with_a_real_font() -> None:
    """polyglotic-hq 386: with DejaVu alone the runner drew Chinese as empty
    boxes, and timed every Chinese layout through Qt's search for a font
    that has it - the pinyin budgets measured what no learner sees. The
    libraries the Linux job unpacks include a font with Chinese in it."""
    script = (WORKFLOWS.parents[1] / "tools" / "linux_qt_libs.sh").read_text(
        encoding="utf-8"
    )
    wanted = re.search(r"^wanted=\(([^)]*)\)", script, re.MULTILINE)
    assert wanted, "linux_qt_libs.sh's list of packages"
    cjk = {"fonts-wqy-microhei", "fonts-wqy-zenhei", "fonts-noto-cjk"}
    assert cjk & set(wanted[1].split()), "a CJK font among the packages"


def test_the_install_test_runs_only_in_a_runners_own_account() -> None:
    """Decision 0045 (polyglotic-hq DECISIONS.md #39, project 225): on the
    PC, Package installs the build only when run by hand with
    `install_here`, after checking the job runs as a runner's own Windows
    account - and uninstalls it only after that check passed, so a job in
    the user's account can neither install nor uninstall their copy."""
    package = yaml.safe_load((WORKFLOWS / "package.yml").read_text(encoding="utf-8"))
    steps = package["jobs"]["package"]["steps"]
    names = [str(step.get("name", "")) for step in steps]
    guard = names.index(
        "This job runs in a runner's own Windows account, not the user's"
    )
    install = names.index("Install it here, as a tester would (Setup.exe, silently)")
    uninstall = names.index("Uninstalled again, on the PC")
    assert guard < install < uninstall
    assert steps[guard]["if"] == (
        "${{ runner.environment != 'github-hosted' && inputs.install_here }}"
    )
    assert "polyglotic-runner|polyglotic-runner[0-9])" in steps[guard]["run"]
    assert "IN_RUNNER_ACCOUNT=yes" in steps[guard]["run"]
    on_github_or_here = (
        "${{ runner.environment == 'github-hosted' || inputs.install_here }}"
    )
    installing = [
        s for s in steps if "Polyglotic/current/Polyglotic.exe" in str(s.get("run", ""))
    ]
    assert len(installing) == 2
    assert all(s["if"] == on_github_or_here for s in installing)
    assert steps[uninstall]["if"] == "${{ always() && env.IN_RUNNER_ACCOUNT == 'yes' }}"
    assert sum("IN_RUNNER_ACCOUNT=yes" in str(s.get("run", "")) for s in steps) == 1
    dispatch = package[True]["workflow_dispatch"]["inputs"]
    assert dispatch["install_here"]["default"] is False


def workflow(name: str) -> dict[Any, Any]:
    """A workflow as GitHub reads it (YAML reads the key `on` as True)."""
    found: dict[Any, Any] = yaml.safe_load(
        (WORKFLOWS / name).read_text(encoding="utf-8")
    )
    return found


def uses(step: dict[str, Any], action: str) -> bool:
    return str(step.get("uses", "")).startswith(action)


def test_a_release_hands_nothing_over_through_the_artifact_storage() -> None:
    """Decision 0050 (polyglotic-hq 244): GitHub's artifact storage was full
    from 2026-11-08 to 2026-12-01, and at the account's $0 limit an upload
    is refused, not billed (DECISIONS.md #98) - so v0.1.0 would have
    failed handing its build from the build job to the publish job. One job
    builds or promotes, then publishes, from its own disk."""
    release = workflow("release.yml")
    steps = [step for job in release["jobs"].values() for step in job.get("steps", [])]
    assert not [
        s
        for s in steps
        if uses(s, "actions/upload-artifact@") or uses(s, "actions/download-artifact@")
    ]
    assert not [job for job in release["jobs"].values() if "uses" in job], (
        "a called workflow is a job of its own: its build would need handing over"
    )
    job = release["jobs"]["release"]
    runs = [str(s.get("run", "")) for s in job["steps"]]
    assert any(
        s.get("uses") == "./.github/actions/build-and-pack" for s in job["steps"]
    )
    assert any("tools.package.promote unpack" in run for run in runs)
    assert any("tools/package/publish.sh" in run for run in runs)
    assert any("gh release create" in run for run in runs)
    # what the publish takes is checked on the job's own disk, dry runs too
    check = next(s for s in job["steps"] if s.get("name", "").startswith("What the"))
    assert "if" not in check


def test_package_and_the_release_build_alike() -> None:
    """Package on main checks the build a release makes: the same steps,
    in one place (.github/actions/build-and-pack), so they can't drift; and
    Package runs again when they change (release_check reads its paths)."""
    package = workflow("package.yml")
    release = workflow("release.yml")
    for job in (package["jobs"]["package"], release["jobs"]["release"]):
        assert any(
            s.get("uses") == "./.github/actions/build-and-pack" for s in job["steps"]
        )
        runs = " ".join(str(s.get("run", "")) for s in job["steps"])
        assert "tools.package.build" not in runs, "build through the shared steps"
    assert ".github/actions/build-and-pack/**" in package[True]["push"]["paths"]
    assert "workflow_call" not in package[True], "the release calls no workflow"


def test_nothing_package_keeps_can_fail_it() -> None:
    """Nothing a release needs comes from Package's artifacts (decision
    0050), so a full storage mustn't fail Package on main: release_check's
    first item reads its result. The packed build (about 160 MB) is kept a
    day, on a run by hand only (three rehearsals at 30 days filled the
    plan's Actions storage, 2026-11-08, polyglotic-hq 225)."""
    uploads = [
        step
        for step in workflow("package.yml")["jobs"]["package"]["steps"]
        if uses(step, "actions/upload-artifact@")
    ]
    assert uploads and all(s.get("continue-on-error") is True for s in uploads)
    full = next(s for s in uploads if "releases" in s["with"]["path"])
    assert full["with"]["retention-days"] == 1
    assert full["if"] == "${{ github.event_name == 'workflow_dispatch' }}"
    assert all(s["with"]["retention-days"] in (1, 3) for s in uploads)


def test_the_store_package_is_the_same_build_recorded_beside_the_installer() -> None:
    """Decision 0056 (polyglotic-hq 264): one build, packed twice - the
    MSIX is packed in the shared steps from the folder Velopack packs, and
    checked to hold its files; a promotion packs it from the promoted
    files; the Release records it with the channel's installer, outside
    releases/, which the update feed is made from."""
    action = yaml.safe_load(
        (WORKFLOWS.parent / "actions" / "build-and-pack" / "action.yml").read_text(
            encoding="utf-8"
        )
    )
    steps = [str(s.get("run", "")) for s in action["runs"]["steps"]]
    velopack = next(i for i, run in enumerate(steps) if "tools/package/pack.sh" in run)
    store = next(i for i, run in enumerate(steps) if "tools.package.msix pack" in run)
    assert store > velopack
    assert "dist/Polyglotic" in steps[store] and "msix compare" in steps[store]
    assert "releases/" not in steps[store]
    release = " ".join(
        str(s.get("run", ""))
        for s in workflow("release.yml")["jobs"]["release"]["steps"]
    )
    assert 'tools.package.msix pack "${TAG#v}" build/promote/app' in release
    assert 'files+=("$store")' in release


def test_the_start_is_timed_alone_and_the_heavy_steps_share_the_pc() -> None:
    """polyglotic-hq 312: the two Windows runners share one PC, and the
    start went over its budget while the other ran its tests or the UI
    lab's four-at-a-time language walk. The start's step holds the PC's
    lock alone (`tools/ci_lock.py`); those heavy steps hold it shared."""
    windows = workflow("windows.yml")  # called by ci.yml and windows-parts.yml (379)
    runs = {
        job: [str(step.get("run", "")) for step in windows["jobs"][job]["steps"]]
        for job in ("checks", "ui-lab")
    }
    every = [run for steps in runs.values() for run in steps]
    start = [run for run in every if "test_start_with_a_big_learner" in run]
    assert start and all(
        r.startswith("uv run --no-sync python -m tools.ci_lock alone -- ")
        for r in start
    )
    shared = [
        run for run in every if "ui_lab languages " in run or run.endswith(" pytest")
    ]
    assert len(shared) == 2
    assert all(
        r.startswith("uv run --no-sync python -m tools.ci_lock shared -- ")
        for r in shared
    )


MOST_DAYS_KEPT = 7
"""The longest any workflow keeps what it uploads. GitHub's Free plan has
500 MB of artifact storage for the whole account (all three repos), counted
as storage over time: 55 packed builds kept 3 days used November's share by
2026-11-08, and every upload was refused until 2026-12-01 (polyglotic-hq
225, 312). An upload that names no `retention-days` is kept the repo's 90.
The UI lab's timings (about 60 KB, 7 days) are the longest kept today."""


def test_every_upload_is_kept_a_week_at_most_and_can_fail_nothing() -> None:
    """polyglotic-hq 344: what fills the storage is time, not size, so
    every upload names how long it's kept - never the repo's 90 days - and
    a full storage fails no check (the upload's `continue-on-error`). The
    secret scan uploads nothing of its own (1,327 empty SARIF reports, kept
    90 days, until it stopped on 2026-11-08)."""
    uploads = [
        (path.name, step)
        for path in sorted(WORKFLOWS.glob("*.y*ml"))
        for job in yaml.safe_load(path.read_text(encoding="utf-8"))["jobs"].values()
        for step in job.get("steps", [])
        if uses(step, "actions/upload-artifact@")
    ]
    assert uploads
    for name, step in uploads:
        kept = step.get("with", {}).get("retention-days")
        assert isinstance(kept, int) and 1 <= kept <= MOST_DAYS_KEPT, (name, step)
        # 592's release-set upload must fail the build if missing (no set, no
        # release; test_linux_release_check.py checks it has no continue-on-error)
        if (
            name == "linux-release.yml"
            and step.get("with", {}).get("name") == "linux-publish-${{ github.run_id }}"
        ):
            continue
        assert step.get("continue-on-error") is True, (name, step)
    scans = [
        step
        for job in workflow("secrets.yml")["jobs"].values()
        for step in job.get("steps", [])
        if uses(step, "gitleaks/gitleaks-action@")
    ]
    assert scans and all(
        s["env"]["GITLEAKS_ENABLE_UPLOAD_ARTIFACT"] == "false" for s in scans
    )


def runs(
    workflow_name: str, job: str, event: str, *labels: str, draft: bool = False
) -> bool:
    """Whether a job's `if` lets it run for this event, read as GitHub would
    for the few forms the workflows use: `github.event_name`, the pull
    request's `draft` and `contains(...labels.*.name, '...')`, with `!`,
    `&&`, `||`, `!=` and `==`. A job without an `if` always runs."""
    condition = str(workflow(workflow_name)["jobs"][job].get("if", "${{ true }}"))
    expression = condition.strip().removeprefix("${{").removesuffix("}}")
    expression = re.sub(
        r"contains\(github\.event\.pull_request\.labels\.\*\.name,\s*'([^']+)'\)",
        r"('\1' in labels)",
        expression,
    )
    expression = expression.replace("github.event.pull_request.draft", "draft")
    expression = expression.replace("github.event_name", "event")
    expression = expression.replace("&&", " and ").replace("||", " or ")
    expression = expression.replace("!=", " NOT_EQUAL ").replace("==", " EQUAL ")
    expression = expression.replace("!", " not ")
    expression = expression.replace(" NOT_EQUAL ", " != ").replace(" EQUAL ", " == ")
    expression = expression.replace("true", "True")
    assert "github" not in expression, f"a form runs() doesn't read: {condition}"
    pull_request = event == "pull_request"
    # the repo's own workflow, translated above, with no builtins
    found = eval(
        expression,
        {"__builtins__": {}},
        {
            "event": event,
            "labels": list(labels) if pull_request else [],
            "draft": draft if pull_request else None,
        },
    )
    return bool(found)


def test_a_pull_request_runs_the_quick_checks_and_the_train_the_windows_jobs() -> None:
    """Decision 0167 (polyglotic-hq 379, the release train, DECISIONS #177):
    2026-11-15's desktop queue reached 18-27 runs on three runners, and the
    two Windows jobs (20-30 min each, one runner each) were what it waited
    for. A pull request runs Checks (Linux); the Windows jobs run on a push
    to main, on the train's pull request (labelled `train`) and by hand.
    A draft runs nothing, and a lower branch of a stack (`stacked`, 344)
    runs nothing."""
    for event in ("push", "workflow_dispatch"):
        assert runs("ci.yml", "linux", event) and runs("ci.yml", "windows", event)
    assert runs("ci.yml", "linux", "pull_request")
    assert not runs("ci.yml", "windows", "pull_request")
    assert runs("ci.yml", "windows", "pull_request", "train")
    assert runs("ci.yml", "linux", "pull_request", "train")
    for job in ("linux", "windows"):
        assert not runs("ci.yml", job, "pull_request", "stacked")
        assert not runs("ci.yml", job, "pull_request", "train", "stacked")
        assert not runs("ci.yml", job, "pull_request", "train", draft=True)
    assert not runs("secrets.yml", "secrets", "pull_request", draft=True)
    assert runs("secrets.yml", "secrets", "pull_request")
    assert runs("secrets.yml", "secrets", "push")
    # the train opens as a draft with its label, then is marked ready: that
    # event starts its checks, with the label already on it
    for name in ("ci.yml", "windows-parts.yml", "secrets.yml"):
        types = workflow(name)[True]["pull_request"]["types"]
        assert "ready_for_review" in types and "synchronize" in types, name
        assert "labeled" not in types, f"{name}: a label starts nothing"
    assert "workflow_dispatch" in workflow("ci.yml")[True]


def test_the_windows_jobs_are_written_once() -> None:
    """Both callers run the one definition, which never runs on its own; the
    Windows parts' pull request skips a train (ci.yml has it), drafts and
    stacks, as ci.yml does."""
    assert set(workflow("windows.yml")[True]) == {"workflow_call"}
    assert set(workflow("windows.yml")["jobs"]) == {"checks", "ui-lab"}
    for name in ("ci.yml", "windows-parts.yml"):
        caller = workflow(name)["jobs"]["windows"]
        assert caller["uses"] == "./.github/workflows/windows.yml", name
    assert runs("windows-parts.yml", "windows", "pull_request")
    for labels in (("train",), ("stacked",)):
        assert not runs("windows-parts.yml", "windows", "pull_request", *labels)
    assert not runs("windows-parts.yml", "windows", "pull_request", draft=True)


def test_lint_and_types_run_on_every_pull_request_once() -> None:
    """They need no Windows (mypy checks as win32 on any machine,
    pyproject.toml), so they moved from Checks (Windows) to Checks (Linux):
    every pull request gets them, and the Windows runner doesn't repeat
    them."""
    quick = [
        str(s.get("run", "")) for s in workflow("ci.yml")["jobs"]["linux"]["steps"]
    ]
    heavy = [
        str(s.get("run", ""))
        for s in workflow("windows.yml")["jobs"]["checks"]["steps"]
    ]
    for command in (
        "uv run --no-sync ruff check --output-format=github",
        "uv run --no-sync ruff format --check",
        "uv run --no-sync mypy",
        "uv run --no-sync python -m tools.mypy_platforms",
        "uv run --no-sync lint-imports",
    ):
        assert command in quick and command not in heavy, command


def github_path(pattern: str) -> re.Pattern[str]:
    """A workflow `paths` pattern as GitHub matches it: `**` any characters,
    `*` any but `/`, `?` one character."""
    regex = ""
    for part in re.split(r"(\*\*/?|\*|\?)", pattern):
        if part in ("**", "**/"):
            regex += "(?:.*/)?" if part == "**/" else ".*"
        elif part == "*":
            regex += "[^/]*"
        elif part == "?":
            regex += "[^/]"
        else:
            regex += re.escape(part)
    return re.compile(regex + r"\Z")


def test_a_pull_request_that_changes_ci_itself_runs_the_windows_jobs() -> None:
    """windows-parts.yml's `paths`: what only CI's own Windows runs show -
    the workflows, CI's machinery on the runners and the dependencies. Not
    the interface or the UI lab: the agents run those on Windows before they
    push, and on 2026-11-15 a list with the UI lab and main.py in it matched
    52 of 80 pull requests (polyglotic-hq 379)."""
    paths = workflow("windows-parts.yml")[True]["pull_request"]["paths"]
    patterns = [github_path(p) for p in paths]

    def matched(path: str) -> bool:
        return any(p.match(path) for p in patterns)

    for path in [
        ".github/workflows/ci.yml",
        ".github/workflows/windows.yml",
        ".github/workflows/windows-parts.yml",
        "tools/ci_lock.py",
        "tools/timing_record.py",
        "tools/start_record.py",
        "uv.lock",
        "pyproject.toml",
    ]:
        assert matched(path), path
    for path in (
        "src/polyglotic_desktop/ui_next/home.py",
        "src/polyglotic_desktop/main.py",
        "tools/ui_lab/goldens/home.png",
        "tests/test_windows_hotkeys.py",
        "translations/polyglotic_ja.ts",
    ):
        assert not matched(path), path
    assert github_path("tests/**/test_*.py").match("tests/ui/test_x.py")
    assert not github_path("tools/*.py").match("tools/ui_lab/lab.py")


def test_the_linux_tests_say_their_memory_against_the_cap() -> None:
    """polyglotic-hq 350: the Linux runners are capped (the desktop's at
    2,200 MB, 2026-11-15); a kill for memory names the step and what it
    reached (`tools/ci_memory.py`, 344)."""
    steps = workflow("ci.yml")["jobs"]["linux"]["steps"]
    tests = [s for s in steps if str(s.get("name", "")).startswith("Tests")]
    # in two processes since 2026-11-18 (one grew past the cap at 98 %):
    # all but tests/ui_next, then tests/ui_next - together, the whole suite
    assert len(tests) == 2
    for step in tests:
        assert step["run"].startswith(
            'uv run --no-sync python -m tools.ci_memory --step "'
        )
    assert tests[0]["run"].endswith(
        "-- uv run --no-sync pytest -p no:cacheprovider --ignore=tests/ui_next"
    )
    assert tests[1]["run"].endswith(
        "-- uv run --no-sync pytest -p no:cacheprovider tests/ui_next"
    )


def test_the_macos_job_runs_only_by_hand_on_githubs_mac_and_keeps_a_day() -> None:
    """polyglotic-hq 408, 410: GitHub's macOS minutes are paid for on this
    private repo (DECISIONS #190), so the job runs only when Claude starts
    it on the user's word - never on a push, a pull request or a schedule -
    with a time limit, and keeps what it uploads one day."""
    macos = workflow("macos.yml")
    assert set(macos[True]) == {"workflow_dispatch"}
    (job,) = macos["jobs"].values()
    assert job["runs-on"] == "macos-26"
    assert 0 < job["timeout-minutes"] <= 90
    uploads = [s for s in job["steps"] if uses(s, "actions/upload-artifact@")]
    assert uploads and all(s["with"]["retention-days"] == 1 for s in uploads)
    app = [s for s in uploads if "Polyglotic-macos-arm64.zip" in s["with"]["path"]]
    assert app and all("inputs.keep_app" in s["if"] for s in app)
    measured = [s for s in job["steps"] if "macos_measure" in s.get("run", "")]
    assert measured and all(s["continue-on-error"] is True for s in measured)


def test_the_macos_job_builds_with_a_pinned_python_of_uvs_own() -> None:
    """polyglotic-hq 523 (512's finding): 0.1.7's Mac app was packed with
    whatever python.org Python the runner image had, and that Python's own
    root list hid a bug every learner met. The job pins an exact version of
    uv's own Python, refuses the image's, and checks the pin holds before
    anything is installed or packed."""
    (job,) = workflow("macos.yml")["jobs"].values()
    assert re.fullmatch(r"3\.12\.\d+", job["env"]["UV_PYTHON"])
    assert job["env"]["UV_PYTHON_PREFERENCE"] == "only-managed"
    runs = [s.get("run", "") for s in job["steps"]]
    checked = next(i for i, r in enumerate(runs) if "tools.package.macos_python" in r)
    pack = next(i for i, r in enumerate(runs) if "tools.package.build" in r)
    assert checked < pack
    assert "if" not in job["steps"][checked]  # every run, whatever its parts


def test_the_macos_job_checks_capture_after_measure_and_keeps_what_it_found() -> None:
    """polyglotic-hq 412: 411's checks run after measure (BlackHole, the
    permission written) and after pack (the packed app's own capture). A
    fail fails the job - so no continue-on-error - while an unknown never
    does (the script's exit code)."""
    (job,) = workflow("macos.yml")["jobs"].values()
    names = [s.get("run", "") for s in job["steps"]]
    measure = next(i for i, r in enumerate(names) if "tools.macos_measure" in r)
    pack = next(i for i, r in enumerate(names) if "tools.package.build" in r)
    capture = next(i for i, r in enumerate(names) if "tools.macos_capture_checks" in r)
    assert measure < capture and pack < capture
    step = job["steps"][capture]
    assert "inputs.capture" in step["if"] and "continue-on-error" not in step
    assert "--app dist/Polyglotic.app" in step["run"]
    assert "${{" not in step["run"]  # inputs reach the shell through env
    (kept,) = [
        s
        for s in job["steps"]
        if uses(s, "actions/upload-artifact@") and "measure.json" in s["with"]["path"]
    ]
    assert "${{ env.OUT }}/capture/" in kept["with"]["path"]


def test_the_macos_job_signs_with_the_release_certificate_in_a_keychain_it_deletes() -> (
    None
):
    """polyglotic-hq 422 (decision 0196): the self-signed certificate comes
    from the repo's secrets into a temporary keychain, through env only
    (never `${{` in a script, never printed), sets the identity the build
    signs with, and the keychain is deleted whatever happened. Without the
    secrets the app is signed ad hoc, as before, but a release refuses to.
    A release keeps its zip and .sha256 for publish-mac.sh."""
    (job,) = workflow("macos.yml")["jobs"].values()
    steps = job["steps"]
    runs = [s.get("run", "") for s in steps]
    signing = next(i for i, r in enumerate(runs) if "security import" in r)
    pack = next(i for i, r in enumerate(runs) if "tools.package.build" in r)
    deleted = next(i for i, r in enumerate(runs) if "security delete-keychain" in r)
    assert signing < pack < deleted
    step = steps[signing]
    assert "${{" not in step["run"]
    assert step["env"]["P12"] == "${{ secrets.MACOS_SIGNING_P12 }}"
    assert step["env"]["P12_PASSWORD"] == "${{ secrets.MACOS_SIGNING_PASSWORD }}"
    assert "POLYGLOTIC_CODESIGN_IDENTITY=" in step["run"]
    assert "a release needs the signing certificate" in step["run"]
    assert "set-key-partition-list" in step["run"] and "rm -f" in step["run"]
    assert (
        'echo "$P12' not in step["run"]
        and 'cat "$RUNNER_TEMP/signing.p12' not in step["run"]
    )
    assert steps[deleted]["if"] == "${{ always() }}"
    (kept,) = [
        s
        for s in steps
        if uses(s, "actions/upload-artifact@") and "release" in s["name"]
    ]
    assert kept["with"]["path"] == "build/package/release/"
    assert "inputs.release" in kept["if"]
    inputs = workflow("macos.yml")[True]["workflow_dispatch"]["inputs"]
    assert inputs["release"]["default"] is False and inputs["version"]["default"] == ""


def test_the_macos_jobs_learner_part_runs_as_a_learners_mac() -> None:
    """polyglotic-hq 523 (decision 0243): off by default (the mirror's
    `--parts learner` turns it on). The settings sweep runs from source
    before pack's sync takes the stand-in server's tools away; the packed
    app's learner checks and the update from the published release after
    pack and the rehearsal; what was hidden is put back whatever happened;
    and every result is kept with the run. A fail fails the job: no
    continue-on-error."""
    macos = workflow("macos.yml")
    inputs = macos[True]["workflow_dispatch"]["inputs"]
    assert inputs["learner"]["default"] is False
    (job,) = macos["jobs"].values()
    steps = job["steps"]
    runs = [s.get("run", "") for s in steps]

    def at(text: str) -> int:
        return next(i for i, r in enumerate(runs) if text in r)

    sweep, pack = at("tools.macos_settings_sweep"), at("tools.package.build")
    checks = at('macos_learner_checks "$OUT/learner" --app dist/Polyglotic.app')
    shown = at('macos_learner_checks "$OUT/learner" --show')
    published = at("tools/package/macos_update_from_release.sh")
    rehearsal = at("tools/package/macos_update_rehearsal.sh")
    assert at("tools.dictionaries.build") < sweep < pack < rehearsal < checks < shown
    assert checks < published
    for i in (sweep, checks, published):
        assert "inputs.learner" in steps[i]["if"]
        assert "continue-on-error" not in steps[i]
    assert steps[shown]["if"] == "${{ always() }}"
    assert "${{" not in runs[published]  # the version reaches it through env
    # 512's packed check: Homebrew and the developer tools away too
    tls = at("--check-tls")
    assert "--hide" in runs[tls] and "trap" in runs[tls] and "--show" in runs[tls]
    (kept,) = [
        s
        for s in steps
        if uses(s, "actions/upload-artifact@") and "measure.json" in s["with"]["path"]
    ]
    for part in ("learner/", "from-release/", "sweep/*.png", "sweep/*.json"):
        assert "${{ env.OUT }}/" + part in kept["with"]["path"]
