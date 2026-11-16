# 0167 A pull request runs the quick checks; the Windows jobs run once, on a train of ready pull requests

- **Status:** accepted (reversible; changes when decision 0025's jobs run, not where)
- **Date:** 2026-11-16
- **Decided by:** the user, 2026-11-16 ~00:25 (polyglotic-hq DECISIONS.md
  #177: "yes approved go ahead"), on Claude's proposal; built by
  polyglotic-hq project 379. Claude reviews it with the pull request.

## Situation

On 2026-11-15 the desktop's CI queue reached 18-27 runs on its three
runners (two Windows, one Linux), and pull requests waited up to 90 minutes
to start. That day (polyglotic-hq 379, from `gh run list` and each run's
jobs):
- 147 CI runs: 131 on 80 pull requests' branches, 16 on pushes to main.
- The Windows jobs ran 182 times: Checks (Windows) 92, about 8 minutes each,
  and UI lab (Windows) 90, about 10 minutes each. That is 1,642 runner-minutes
  on two runners; another 112 were cancelled before they started.
- A Windows job's wait from its run's creation: median 22-26 minutes, p90
  148-239, longest 358-411.

Every push to every pull request ran both Windows jobs, though the agents
work on Windows and run the touched tests and the UI lab before they push
(polyglotic-hq projects/README.md). Claude had already combined four pull
requests into one by hand (#700) to check them once.

## Decision

- **A pull request** runs Checks (Linux) and the secret scan. Lint, format,
  types (mypy, and mypy as macOS and Linux) and the import rule move from
  Checks (Windows) to Checks (Linux): mypy checks as win32 on any machine
  (`pyproject.toml`), so the result is the same, and every pull request gets
  them.
- **The Windows jobs** (Checks (Windows), UI lab (Windows)) are written once,
  in `windows.yml` (a reusable workflow), and run:
  - from `ci.yml`: on a push to main; on a pull request labelled `train`;
    and by hand (Actions > CI > Run workflow, on any branch);
  - from `windows-parts.yml`: on a pull request that changes the workflows,
    CI's machinery on the runners (`tools/ci_lock.py`, `timing_record.py`,
    `start_record.py`) or the dependencies (`pyproject.toml`, `uv.lock`).
    GitHub matches the paths against the pull request's whole diff, before
    any runner is used.
- **The train:** Claude merges ready pull requests (their quick checks green,
  their reports reviewed) into one `claude-train-<date-time>` branch from
  main with merge commits, and opens it as a pull request labelled `train`.
  Merging it (a merge commit) marks each pull request in it merged. A red
  train drops the pull request whose files the failure touches and is built
  again. polyglotic-hq's `scripts/train.py` does this; its merge-stack skill
  says how.
- **A draft** pull request runs nothing (CI or the secret scan) until it's
  marked ready. The train opens as a draft with its label and is then marked
  ready, so its first run already sees the label: adding a label starts
  nothing (`labeled` isn't a trigger, so a label can't cancel a running
  check either).
- `stacked` (344) is kept: a lower branch of a stack runs nothing.
- Enforced by `tests/test_workflows.py`, which reads each job's `if` as
  GitHub would for each event and label.

## Why

- **The Windows runners were the queue.** Replayed on a first-come queue
  with the minutes each job really took, 2026-11-15 as it ran gives a
  median Windows wait of 22 minutes and a longest of 111 (the real ones were
  longer: re-runs aren't in the replay). With the train - one per moment
  main was merged that day (12), plus the pull requests that changed CI
  itself (10 of 80) - the Windows jobs would have run 70 times, 633
  runner-minutes, with a median wait of 0 and a longest of 8 minutes.
- **The agents already run the Windows side on Windows.** What only CI
  shows is CI itself: its workflows, its lock and records on the runners, a
  dependency update no one ran at a desk.
- **Alternatives not taken:**
  - **A first job that reads the pull request's files and decides:** it
    would run on the one Linux runner, so the Windows jobs on main and the
    train would wait behind the Linux queue too.
  - **A longer `paths` list** (the UI lab and its goldens, `main.py`, every
    test marked `windows_only`): on 2026-11-15 it matched 52 of the 80 pull
    requests, most of them for the UI lab, and the queue would have stayed.
  - **`labeled` as a trigger:** adding any label to a pull request would
    start a run and cancel the one in progress.

## What it costs

- **The Linux runner becomes the queue.** It does every pull request's
  quick checks, now about 1.5 minutes longer, and the train's. The same
  replay puts its median wait at 42 minutes (16 as it ran) and its longest
  at 197; with a second Linux runner for the desktop, 0.3 and 36. Adding one
  is a change to the PC's runners (polyglotic-hq scripts/RUNNERS.md): the
  user's call.
- **A pull request's Windows failure shows up on the train,** not on the
  pull request: the train finds whose it is (the files the failure touches)
  and drops it.

## What would make us reverse it

- Trains that fail often, or whose failures can't be laid at one pull
  request: then the Windows jobs go back on each pull request, with a second
  Windows runner if the PC can carry it.
- Main going red after trains more than before.
